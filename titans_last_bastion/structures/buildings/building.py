# structures/buildings/building.py
import os

from core.entity import Entity
from core.interfaces import IAttackable, IUpgradable, IProducible
from core.game_state import ResourceBundle
from core.event_bus import GameEventBus

try:
    import pygame
    _PYGAME_OK = True
except ImportError:
    _PYGAME_OK = False

_HERE = os.path.dirname(os.path.abspath(__file__))
_BLDG_SCALE = 1.5   # visual scale multiplier for demo

# Cache các frame đã được pre-scale: (class_name, level, frame_idx) -> Surface
# Giúp tránh gọi transform.scale mỗi frame (nặng CPU)
_scaled_frame_cache: dict = {}


# ═══════════════════════════════════════════════════════
#  BUILDING BASE
# ═══════════════════════════════════════════════════════

class Building(Entity, IAttackable, IUpgradable, IProducible):
    """Cha của mọi công trình. Tự sản xuất theo timer."""

    CYCLE_TIME      = 60.0  # giây — class con override
    PRODUCTION_RATE = 0     # lượng sản xuất — class con override

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self._hp         = 300
        self._max_hp     = 300
        self._level      = 1
        self._timer      = 0.0
        self._anim_timer = 0.0
        self._stock      = ResourceBundle()

    def update(self, dt: float):
        """Đếm timer. Khi đủ CYCLE_TIME → tự produce()."""
        if not self.is_alive:
            return
        self._anim_timer += dt
        self._timer += dt
        if self._timer >= self.CYCLE_TIME:
            self._timer   = 0.0
            self._stock  += self.produce()

    def produce(self) -> ResourceBundle:
        """IProducible — tính lượng sản xuất. Class con override."""
        return ResourceBundle()

    def harvest(self) -> ResourceBundle:
        """Lấy toàn bộ _stock ra và reset về 0."""
        out         = self._stock
        self._stock = ResourceBundle()
        return out

    def take_damage(self, amount: int, dtype: str):
        """Titan vào Sina có thể phá công trình."""
        self._hp -= amount
        if self._hp <= 0:
            self.is_alive = False
            GameEventBus.get_instance().publish(
                'building_destroyed', {'building': self}
            )

    def upgrade(self):
        from structures.buildings.resource_manager import ResourceManager
        rm = ResourceManager.get_instance()
        if rm.get_stock() >= self.get_upgrade_cost():
            rm.spend(self.get_upgrade_cost())
            self._level          += 1
            self.PRODUCTION_RATE  = int(self.PRODUCTION_RATE * 1.2)

    def get_upgrade_cost(self) -> ResourceBundle:
        return ResourceBundle(
            wood  = 50 * self._level,
            stone = 30 * self._level
        )

    def draw(self, screen): pass


# ═══════════════════════════════════════════════════════
#  CÔNG TRÌNH CỤ THỂ
# ═══════════════════════════════════════════════════════

class Farm(Building):
    """→ 10 food/60s (lv1) · 15 food/60s (lv2) · 25 food/60s (lv3). 3 cấp."""

    CYCLE_TIME      = 60.0
    PRODUCTION_RATE = 10
    MAX_LEVEL       = 3

    LEVEL_UPGRADE = {
        1: {'cost': ResourceBundle(wood=50,  stone=30),  'rate_bonus': 5},
        2: {'cost': ResourceBundle(wood=100, stone=60),  'rate_bonus': 10},
    }

    _DISPLAY_SIZE  = (128, 128)
    _sprite_cache: "pygame.Surface | None" = None

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        if _PYGAME_OK and Farm._sprite_cache is None:
            raw = pygame.image.load(
                os.path.join(_HERE, 'Farm.png')
            ).convert_alpha()
            Farm._sprite_cache = pygame.transform.scale(raw, Farm._DISPLAY_SIZE)

    def draw(self, screen) -> None:
        if _PYGAME_OK and Farm._sprite_cache is not None and self.is_alive:
            screen.blit(Farm._sprite_cache, (int(self.x), int(self.y)))

    def produce(self) -> ResourceBundle:
        return ResourceBundle(food=self.PRODUCTION_RATE)

    def get_upgrade_cost(self) -> ResourceBundle:
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm    = ResourceManager.get_instance()
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry and rm.can_afford(entry['cost']):
            rm.spend(entry['cost'])
            self.PRODUCTION_RATE += entry['rate_bonus']
            self._level += 1


class StoneWorkshop(Building):
    """→ 8 stone/60s (lv1) · 12 stone/60s (lv2) · 20 stone/60s (lv3). 3 cấp."""

    CYCLE_TIME      = 60.0
    PRODUCTION_RATE = 8
    MAX_LEVEL       = 3

    LEVEL_UPGRADE = {
        1: {'cost': ResourceBundle(wood=60,  food=20),           'rate_bonus': 4},
        2: {'cost': ResourceBundle(wood=120, food=40, ore=10),   'rate_bonus': 8},
    }

    _COLS        = 3
    _ROWS        = 6
    _sheet_cache: "pygame.Surface | None" = None

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        if _PYGAME_OK and StoneWorkshop._sheet_cache is None:
            StoneWorkshop._sheet_cache = pygame.image.load(
                os.path.join(_HERE, 'StoneWorkshop.png')
            ).convert_alpha()
            # Pre-scale tất cả frame một lần — tránh transform.scale mỗi draw()
            sheet = StoneWorkshop._sheet_cache
            fw = sheet.get_width()  // StoneWorkshop._COLS
            fh = sheet.get_height() // StoneWorkshop._ROWS
            for _lv in (1, 2, 3):
                col = min(_lv - 1, StoneWorkshop._COLS - 1)
                if _lv <= 2:
                    src = pygame.Rect(col * fw - 15, 0, fw - 15, fh)
                else:
                    src = pygame.Rect(col * fw - 20, 0, fw + 10, fh)
                src = src.clip(sheet.get_rect())
                if src.w > 0 and src.h > 0:
                    raw_f = sheet.subsurface(src)
                    sw = max(1, int(src.w * _BLDG_SCALE))
                    sh = max(1, int(src.h * _BLDG_SCALE))
                    _scaled_frame_cache[('SW', _lv, 0)] = pygame.transform.scale(raw_f, (sw, sh))

    def draw(self, screen) -> None:
        if not _PYGAME_OK or StoneWorkshop._sheet_cache is None or not self.is_alive:
            return
        cached = _scaled_frame_cache.get(('SW', self._level, 0))
        if cached is not None:
            screen.blit(cached, (int(self.x), int(self.y)))
            return
        # Fallback (kó cache): vẽ như cũ
        sheet = StoneWorkshop._sheet_cache
        fw  = sheet.get_width()  // self._COLS
        fh  = sheet.get_height() // self._ROWS
        col = min(self._level - 1, self._COLS - 1)
        if self._level == 1 or self._level == 2:
            src = pygame.Rect(col * fw - 15, 0, fw - 15, fh)
        else:
            src = pygame.Rect(col * fw - 20, 0, fw + 10, fh)
        src = src.clip(sheet.get_rect())
        if src.w <= 0 or src.h <= 0:
            return
        frame_surf = sheet.subsurface(src)
        scaled = pygame.transform.scale(frame_surf,
            (max(1, int(src.w * _BLDG_SCALE)), max(1, int(src.h * _BLDG_SCALE))))
        screen.blit(scaled, (int(self.x), int(self.y)))

    def produce(self) -> ResourceBundle:
        return ResourceBundle(stone=self.PRODUCTION_RATE)

    def get_upgrade_cost(self) -> ResourceBundle:
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm    = ResourceManager.get_instance()
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry and rm.can_afford(entry['cost']):
            rm.spend(entry['cost'])
            self.PRODUCTION_RATE += entry['rate_bonus']
            self._level += 1


class WoodWorkshop(Building):
    """→ 15 wood/60s (lv1) · 23 wood/60s (lv2). 2 cấp."""

    CYCLE_TIME      = 60.0
    PRODUCTION_RATE = 15
    MAX_LEVEL       = 2

    LEVEL_UPGRADE = {
        1: {'cost': ResourceBundle(stone=40, food=20), 'rate_bonus': 8},
    }

    # 8 cột × 8 hàng, hàng cuối 4 frames → tổng 60 frames
    _COLS           = 8
    _ROWS           = 8
    _TOTAL_FRAMES   = 60
    _FRAME_DURATION = 0.08   # ~12 fps
    _sheet_paths    = {
        1: os.path.join(_HERE, 'WoodWorkshop_1.png'),
        2: os.path.join(_HERE, 'WoodWorkshop_2.png'),
    }
    _sheets: dict = {}

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        if _PYGAME_OK:
            for lv, path in WoodWorkshop._sheet_paths.items():
                if lv not in WoodWorkshop._sheets:
                    WoodWorkshop._sheets[lv] = pygame.image.load(path).convert_alpha()
                    # Pre-scale tất cả frame cho cấp độ này
                    sheet = WoodWorkshop._sheets[lv]
                    cols, rows = WoodWorkshop._COLS, WoodWorkshop._ROWS
                    total = WoodWorkshop._TOTAL_FRAMES
                    fw = sheet.get_width()  // cols
                    fh = sheet.get_height() // rows
                    sw = max(1, int(fw * _BLDG_SCALE))
                    sh = max(1, int(fh * _BLDG_SCALE))
                    for fi in range(total):
                        col = fi % cols
                        row = fi // cols
                        src = pygame.Rect(col * fw, row * fh, fw, fh)
                        raw_f = sheet.subsurface(src)
                        _scaled_frame_cache[('WW', lv, fi)] = pygame.transform.scale(raw_f, (sw, sh))

    def draw(self, screen) -> None:
        if not _PYGAME_OK or not self.is_alive:
            return
        frame = int(self._anim_timer / self._FRAME_DURATION) % self._TOTAL_FRAMES
        cached = _scaled_frame_cache.get(('WW', self._level, frame))
        if cached is not None:
            screen.blit(cached, (int(self.x), int(self.y)))
            return
        # Fallback
        sheet = WoodWorkshop._sheets.get(self._level)
        if sheet is None:
            return
        fw    = sheet.get_width()  // self._COLS
        fh    = sheet.get_height() // self._ROWS
        col   = frame % self._COLS
        row   = frame // self._COLS
        src        = pygame.Rect(col * fw, row * fh, fw, fh)
        frame_surf = sheet.subsurface(src)
        scaled     = pygame.transform.scale(frame_surf,
            (max(1, int(fw * _BLDG_SCALE)), max(1, int(fh * _BLDG_SCALE))))
        screen.blit(scaled, (int(self.x), int(self.y)))

    def produce(self) -> ResourceBundle:
        return ResourceBundle(wood=self.PRODUCTION_RATE)

    def get_upgrade_cost(self) -> ResourceBundle:
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm    = ResourceManager.get_instance()
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry and rm.can_afford(entry['cost']):
            rm.spend(entry['cost'])
            self.PRODUCTION_RATE += entry['rate_bonus']
            self._level += 1


class Forge(Building):
    """Xưởng vũ khí trung tâm. Quản lý việc trang bị vũ khí và nâng cấp giới hạn.

    2 trục nâng cấp độc lập:
      • upgrade()        — nâng CẤP ĐỘ Xưởng (1→2→3), tăng nhóm tổng
                           (tower_weapon / soldier_weapon / trap).
      • upgrade_limit()  — tăng từng loại vũ khí lẻ (sword/arrow/spear…).
    """

    CYCLE_TIME      = 999
    PRODUCTION_RATE = 0
    MAX_LEVEL       = 3

    # Nâng cấp theo CẤP ĐỘ — tăng nhóm tổng
    # key = cấp hiện tại → nâng lên cấp kế tiếp
    LEVEL_UPGRADE = {
        1: {
            'cost':  ResourceBundle(wood=100, stone=60,  ore=20),
            'bonus': ResourceBundle(tower_weapon=50, soldier_weapon=50, trap=20),
        },
        2: {
            'cost':  ResourceBundle(wood=200, stone=120, ore=50),
            'bonus': ResourceBundle(tower_weapon=100, soldier_weapon=100, trap=40),
        },
    }

    # Level 1: 8 cột × 5 hàng, hàng cuối 3 frames → 35 frames
    # Level 2: 6 cột × 6 hàng, hàng cuối 5 frames → 35 frames
    # Level 3: 8 cột × 5 hàng, hàng cuối 3 frames → 35 frames
    _FRAME_CONFIG = {
        1: (8, 5, 35),
        2: (6, 6, 35),
        3: (8, 5, 35),
    }
    _FRAME_DURATION = 0.10   # 10 fps
    _sheet_paths = {
        1: os.path.join(_HERE, 'Forge_1.png'),
        2: os.path.join(_HERE, 'Forge_2.png'),
        3: os.path.join(_HERE, 'Forge_3.png'),
    }
    _sheets: dict = {}
    _weapon_used: ResourceBundle = ResourceBundle()  # shared across ALL Forge instances

    @property
    def weapon_used(self) -> ResourceBundle:
        return Forge._weapon_used

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        if _PYGAME_OK:
            for lv, path in Forge._sheet_paths.items():
                if lv not in Forge._sheets:
                    Forge._sheets[lv] = pygame.image.load(path).convert_alpha()
                    # Pre-scale tất cả frame cho cấp này
                    sheet = Forge._sheets[lv]
                    cols, rows, total = Forge._FRAME_CONFIG[lv]
                    fw = sheet.get_width()  // cols
                    fh = sheet.get_height() // rows
                    sw = max(1, int(fw * _BLDG_SCALE))
                    sh = max(1, int(fh * _BLDG_SCALE))
                    for fi in range(total):
                        col = fi % cols
                        row = fi // cols
                        src = pygame.Rect(col * fw, row * fh, fw, fh)
                        raw_f = sheet.subsurface(src)
                        _scaled_frame_cache[('FG', lv, fi)] = pygame.transform.scale(raw_f, (sw, sh))

    def draw(self, screen) -> None:
        if not _PYGAME_OK or not self.is_alive:
            return
        cols, rows, total = self._FRAME_CONFIG[self._level]
        frame = int(self._anim_timer / self._FRAME_DURATION) % total
        cached = _scaled_frame_cache.get(('FG', self._level, frame))
        if cached is not None:
            screen.blit(cached, (int(self.x), int(self.y)))
            return
        # Fallback
        sheet = Forge._sheets.get(self._level)
        if sheet is None:
            return
        fw    = sheet.get_width()  // cols
        fh    = sheet.get_height() // rows
        col   = frame % cols
        row   = frame // cols
        src        = pygame.Rect(col * fw, row * fh, fw, fh)
        frame_surf = sheet.subsurface(src)
        scaled     = pygame.transform.scale(frame_surf,
            (max(1, int(fw * _BLDG_SCALE)), max(1, int(fh * _BLDG_SCALE))))
        screen.blit(scaled, (int(self.x), int(self.y)))

    # ── Nâng cấp theo CẤP ĐỘ ────────────────────────────────────────

    def get_upgrade_cost(self) -> ResourceBundle:
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        """Nâng cấp độ Xưởng (tối đa cấp 3).

        Mỗi cấp: trừ tài nguyên → cộng thêm nhóm tổng
        (tower_weapon / soldier_weapon / trap) vào ResourceManager.
        """
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm    = ResourceManager.get_instance()
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry and rm.can_afford(entry['cost']):
            rm.spend(entry['cost'])
            rm.earn(entry['bonus'])
            self._level += 1

    # ── Giới hạn ban đầu khi xây Xưởng ─────────────────────────────

    def _add_initial_limits(self):
        from structures.buildings.resource_manager import ResourceManager
        from core.game_state import ResourceBundle
        rm = ResourceManager.get_instance()
        
        initial_limits = ResourceBundle(
            tower_weapon=200,
            soldier_weapon=100,
            trap=50,
            basic_projectlie=100,
            thorn_trap=20,
            sword=50,
            spear=50,
            arrow=40,
        )
        # Cộng giới hạn vào kho chứa chung
        rm.earn(initial_limits)

    def can_equip(self, general_type: str, specific_type: str, amount: int) -> bool:
        """Kiểm tra có đủ giới hạn vũ khí không (cả chung lẫn riêng)."""
        from structures.buildings.resource_manager import ResourceManager
        rm = ResourceManager.get_instance()
        stock = rm.get_stock()

        used_general = getattr(self.weapon_used, general_type, 0)
        limit_general = getattr(stock, general_type, 0)
        
        used_specific = getattr(self.weapon_used, specific_type, 0)
        limit_specific = getattr(stock, specific_type, 0)

        return (used_general + amount <= limit_general) and (used_specific + amount <= limit_specific)

    def equip(self, general_type: str, specific_type: str, amount: int) -> bool:
        """Trang bị vũ khí (chiếm slot). Trả về True nếu thành công."""
        if self.can_equip(general_type, specific_type, amount):
            setattr(self.weapon_used, general_type, getattr(self.weapon_used, general_type, 0) + amount)
            setattr(self.weapon_used, specific_type, getattr(self.weapon_used, specific_type, 0) + amount)
            return True
        return False

    def unequip(self, general_type: str, specific_type: str, amount: int):
        """Thu hồi vũ khí (giải phóng slot) khi tháp/lính/bẫy bị hủy."""
        new_gen = max(0, getattr(self.weapon_used, general_type, 0) - amount)
        new_spec = max(0, getattr(self.weapon_used, specific_type, 0) - amount)
        setattr(self.weapon_used, general_type, new_gen)
        setattr(self.weapon_used, specific_type, new_spec)

    def upgrade_limit(self, weapon_type: str, amount: int, cost: "ResourceBundle") -> bool:
        """Nâng cấp giới hạn của 1 loại vũ khí bất kỳ."""
        from structures.buildings.resource_manager import ResourceManager
        from core.game_state import ResourceBundle
        rm = ResourceManager.get_instance()
        if rm.get_stock() >= cost:
            rm.spend(cost)
            # Cộng lượng mở rộng vào ResourceManager
            upgrade_bundle = ResourceBundle()
            setattr(upgrade_bundle, weapon_type, amount)
            rm.earn(upgrade_bundle)
            return True
        return False


class TrainingCamp(Building):
    """Tuyển lính: Warrior (cận chiến), Archer (tầm xa), Lancer (kỵ binh).

    Keys khớp với SOLDIER_TYPES trong characters/soldiers/soldier.py.
    Điều kiện train: upkeep + train_cost < tốc độ sản xuất Farm.
    """

    ENTITY_TYPE = "building"
    MAX_LEVEL   = 3

    # Keys phải khớp với SOLDIER_TYPES: 'Warrior', 'Archer', 'Lancer'
    SOLDIER_STATS = {
        'Warrior': {'train_time': 10.0, 'upkeep': 1.0, 'train_cost': 2.0},
        'Archer':  {'train_time': 12.0, 'upkeep': 0.8, 'train_cost': 1.5},
        'Lancer':  {'train_time': 20.0, 'upkeep': 2.0, 'train_cost': 4.0},
    }

    # Chi phí vũ khí: (general_slot, specific_slot, amount)
    WEAPON_COST = {
        'Warrior': ('soldier_weapon', 'sword',  1),
        'Archer':  ('soldier_weapon', 'arrow',  10),
        'Lancer':  ('soldier_weapon', 'spear',  1),
    }

    # Chi phí nâng cấp trại: lv1→2, lv2→3
    LEVEL_UPGRADE = {
        1: {'cost': ResourceBundle(wood=80,  stone=50)},
        2: {'cost': ResourceBundle(wood=160, stone=100, ore=20)},
    }

    _DISPLAY_SIZE = (128, 128)
    _sprite_cache: "pygame.Surface | None" = None

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self._queue: list = []
        self._current_food_upkeep: float = 0.0
        self._idle: dict = {t: 0 for t in self.SOLDIER_STATS}  # trained, not yet dispatched
        if _PYGAME_OK and TrainingCamp._sprite_cache is None:
            raw = pygame.image.load(
                os.path.join(_HERE, 'Trainingcamp.png')
            ).convert_alpha()
            TrainingCamp._sprite_cache = pygame.transform.scale(raw, TrainingCamp._DISPLAY_SIZE)

    def draw(self, screen) -> None:
        if _PYGAME_OK and TrainingCamp._sprite_cache is not None and self.is_alive:
            screen.blit(TrainingCamp._sprite_cache, (int(self.x), int(self.y)))

    def get_upgrade_cost(self) -> ResourceBundle:
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm = ResourceManager.get_instance()
        cost = self.get_upgrade_cost()
        if rm.can_afford(cost):
            rm.spend(cost)
            self._level += 1
            
            # Retroactively apply buffs to all existing soldiers
            buffs = self.get_soldier_buffs()
            hp_mult = buffs.get('hp_mult', 1.0)
            dmg_mult = buffs.get('dmg_mult', 1.0)
            from systems.world_query import WorldQuery
            for ent in getattr(WorldQuery, '_entities', []):
                if getattr(ent, 'ENTITY_TYPE', '') == 'soldier' and getattr(ent, 'is_alive', False):
                    old_max = ent._max_hp
                    ent._max_hp = int(ent.BASE_HP * hp_mult)
                    ent._hp += (ent._max_hp - old_max)
                    ent._damage = int(ent.ATTACK_DAMAGE * dmg_mult)

    def get_soldier_buffs(self) -> dict:
        """Cấp trại càng cao lính ra càng mạnh (+15% HP/Damage mỗi cấp)."""
        mult = 1.0 + (self._level - 1) * 0.15
        return {'hp_mult': mult, 'dmg_mult': mult}

    def count_live_soldiers(self, towers: list | None = None) -> dict:
        """Đếm lính còn sống từ mọi nguồn: idle ở trại + deployed/reserve trong tháp.

        Returns: {type: {'idle': n, 'deployed': n, 'total': n}}
        Luôn gọi được trong combat loop — chỉ đọc, không mutate state.
        """
        result = {t: {'idle': 0, 'deployed': 0, 'total': 0}
                  for t in self.SOLDIER_STATS}
        # Idle trong trại (đã train xong, chưa dispatch)
        for t in self.SOLDIER_STATS:
            result[t]['idle'] = max(0, self._idle.get(t, 0))
        # Deployed / reserve trong tất cả tháp
        for tw in (towers or []):
            for sq in (getattr(tw, '_deployed_squads', [])
                       + getattr(tw, '_reserve_squads', [])):
                alive = sum(1 for m in sq.members if m.is_alive)
                st = sq.soldier_type
                if st in result:
                    result[st]['deployed'] += alive
        # Tổng mỗi loại
        for t in result:
            result[t]['total'] = result[t]['idle'] + result[t]['deployed']
        return result

    def total_upkeep_from_roster(self, towers: list | None = None) -> float:
        """Tính food upkeep thực tế từ roster live (không dùng _current_food_upkeep cached).

        Dùng cho tab ROSTER để hiển thị đúng khi lính chết giữa combat.
        """
        roster = self.count_live_soldiers(towers)
        total = 0.0
        for t, stats in self.SOLDIER_STATS.items():
            total += roster[t]['total'] * stats['upkeep']
        return total

    def _get_total_food_production_rate(self) -> float:
        from systems.world_query import WorldQuery
        total = 0.0
        for b in WorldQuery.get_all_buildings():
            if type(b).__name__ == 'Farm' and b.is_alive:
                total += getattr(b, 'PRODUCTION_RATE', 0) / max(getattr(b, 'CYCLE_TIME', 1), 0.001)
        return total if total > 0 else 50.0

    def start_training(self, soldier_type: str, amount: int = 1) -> bool:
        """Bắt đầu huấn luyện. Trả về True nếu đủ điều kiện."""
        if soldier_type not in self.SOLDIER_STATS:
            return False
        if soldier_type == 'Lancer' and self._level < 3:
            return False

        stats = self.SOLDIER_STATS[soldier_type]
        queued_cost = sum(self.SOLDIER_STATS[s['type']]['train_cost'] for s in self._queue)
        new_cost = stats['train_cost'] * amount
        if self._current_food_upkeep + queued_cost + new_cost >= self._get_total_food_production_rate():
            return False

        from systems.world_query import WorldQuery
        forges = [b for b in WorldQuery.get_all_buildings() if type(b).__name__ == 'Forge']
        if forges:
            gen_type, spec_type, wp_amount = self.WEAPON_COST[soldier_type]
            if not forges[0].equip(gen_type, spec_type, wp_amount * amount):
                return False

        for _ in range(amount):
            self._queue.append({'type': soldier_type, 'timer': stats['train_time']})
        return True

    def update(self, dt: float):
        super().update(dt)
        remaining = []
        for s in self._queue:
            s['timer'] -= dt
            if s['timer'] <= 0:
                self._spawn_soldier(s['type'])
            else:
                remaining.append(s)
        self._queue = remaining

    def _spawn_soldier(self, soldier_type: str):
        """Training done — soldier enters idle pool at camp (no entity yet)."""
        self._current_food_upkeep += self.SOLDIER_STATS[soldier_type]['upkeep']
        self._idle[soldier_type] = self._idle.get(soldier_type, 0) + 1

    def on_soldier_died(self, soldier_type: str):
        """Gọi khi lính chết — giảm upkeep và hoàn trả slot vũ khí."""
        upkeep = self.SOLDIER_STATS.get(soldier_type, {}).get('upkeep', 0.0)
        self._current_food_upkeep = max(0.0, self._current_food_upkeep - upkeep)
        from systems.world_query import WorldQuery
        forges = [b for b in WorldQuery.get_all_buildings() if type(b).__name__ == 'Forge']
        if forges:
            gen_type, spec_type, wp_amount = self.WEAPON_COST.get(soldier_type, ('soldier_weapon', 'sword', 0))
            forges[0].unequip(gen_type, spec_type, wp_amount)


class RepairStation(Building):
    """Tự sửa tường 50 HP/section mỗi cycle."""

    REPAIR_AMOUNT = 50  # HP sửa mỗi cycle

    def repair_walls(self, walls: list):
        """Gọi ở cuối mỗi wave."""
        for wall in walls:
            wall.repair_all(self.REPAIR_AMOUNT)