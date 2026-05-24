"""towerhuntercheck.py — Demo trực quan TowerHunter (walk/run/attack + bonus siege).

Phím điều khiển:
  WASD          — di chuyển TowerHunter (cập nhật hướng nhìn)
  Shift + WASD  — chạy (Run animation)
  SPACE         — đòn siege (TowerHunterStrategy: ×1.5 nếu target là Tower)
                  Nếu trong tầm 60 px của dummy gần nhất → execute()
  R             — respawn titan + 2 dummy mới
  Q / ESC       — thoát

Mục đích kiểm tra:
  • Walk (rows 8–11, 9 frame) vs Run (rows 37–40, 8 frame)
  • Attack (rows 12–15, 6 frame) loop 1 s
  • Sprite `towerhunter.png` cố định
  • TowerHunterStrategy.execute():
      - Tower dummy (isinstance Tower)   → damage ×1.5, dtype='siege'
      - Soldier dummy (KHÔNG phải Tower) → damage ×1.0, dtype='siege'
"""
import sys
import os
import math
import types

import pygame


# ── 1. Mock modules ──────────────────────────────────────────────────────────

def _mod(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


class _MockEntity:
    _next_id = 1

    def __init__(self, x: float, y: float):
        self.id = _MockEntity._next_id
        _MockEntity._next_id += 1
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen) -> None:
        pass


_mod('core')
_entity_mod = _mod('core.entity')
_entity_mod.Entity = _MockEntity


class _IAttackable:
    pass


class _IMovable:
    pass


_iface_mod = _mod('core.interfaces')
_iface_mod.IAttackable = _IAttackable
_iface_mod.IMovable    = _IMovable


class _MockBus:
    _inst = None

    @classmethod
    def get_instance(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def publish(self, event: str, data: dict) -> None:
        print(f"  [EventBus] publish('{event}', keys={list(data.keys())})")


_bus_mod = _mod('core.event_bus')
_bus_mod.GameEventBus = _MockBus


# ── 2. Mock structures.towers.tower.Tower — bắt buộc để isinstance() chạy ───
#
# TowerHunterStrategy.execute() làm `from structures.towers.tower import Tower`
# rồi check `isinstance(target, Tower)`. Nên ta phải cung cấp class Tower thật
# qua mock module — TowerDummy bên dưới sẽ kế thừa class này.

class _MockTower:
    """Mock Tower base class — đủ để isinstance check trong Strategy hoạt động."""

    def __init__(self, x: float, y: float, hp: int = 600):
        self.x = float(x)
        self.y = float(y)
        self._hp     = hp
        self._max_hp = hp
        self.is_alive = True


_mod('structures')
_mod('structures.towers')
_tower_mod = _mod('structures.towers.tower')
_tower_mod.Tower = _MockTower


# ── 3. Mock characters.titans.attackstrategy ─────────────────────────────────

_mod('characters')
_mod('characters.titans')

# File này nằm trong Check/ — sys.path phải trỏ về parent (chứa Titan.py, AttackStrategy.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import AttackStrategy as _atk_src  # noqa: E402
_strat_mod = _mod('characters.titans.attackstrategy')
# Inject TẤT CẢ strategy mà Titan.py import (Wolf/SoldierHunter cũng được import)
_strat_mod.MeleeRushStrategy      = _atk_src.MeleeRushStrategy
_strat_mod.HeavyStrikeStrategy    = _atk_src.HeavyStrikeStrategy
_strat_mod.ArmoredRamStrategy     = _atk_src.ArmoredRamStrategy
_strat_mod.Incurable              = _atk_src.Incurable
_strat_mod.TowerHunterStrategy    = _atk_src.TowerHunterStrategy
_strat_mod.SoldierHunterStrategy  = _atk_src.SoldierHunterStrategy
_strat_mod.Explosion              = _atk_src.Explosion


class _MockWorldQuery:
    soldiers:   list = []
    commanders: list = []
    towers:     list = []

    @classmethod
    def get_headquarters(cls):
        return None

    @classmethod
    def can_reach_direct(cls, *_a, **_kw) -> bool:
        return False

    @classmethod
    def find_blocking_wall(cls, *_a, **_kw):
        return None

    @classmethod
    def find_nearest_attacker(cls, *_a, **_kw):
        return None

    @classmethod
    def find_nearest(cls, cx: float, cy: float, entity_type: str):
        pool = {'soldier':   cls.soldiers,
                'commander': cls.commanders,
                'tower':     cls.towers}.get(entity_type, [])
        best, best_d = None, float('inf')
        for e in pool:
            if not e.is_alive:
                continue
            d = ((e.x - cx) ** 2 + (e.y - cy) ** 2) ** 0.5
            if d < best_d:
                best_d, best = d, e
        return best

    @classmethod
    def find_in_radius(cls, cx: float, cy: float, radius: float,
                       entity_type: str) -> list:
        pool = {'soldier':   cls.soldiers,
                'commander': cls.commanders,
                'tower':     cls.towers}.get(entity_type, [])
        return [e for e in pool
                if e.is_alive
                and ((e.x - cx) ** 2 + (e.y - cy) ** 2) ** 0.5 <= radius]


_mod('systems')
_wq_mod = _mod('systems.world_query')
_wq_mod.WorldQuery = _MockWorldQuery


# ── 4. Import TowerHunter thật ───────────────────────────────────────────────

from Titan import TowerHunter  # noqa: E402


# ── 5. Dummies: Tower (subclass) + Soldier (plain) ───────────────────────────

class TowerDummy(_MockTower):
    """Dummy thừa kế Tower — TowerHunterStrategy sẽ x1.5 damage lên dummy này."""

    def __init__(self, x: float, y: float, hp: int = 600):
        super().__init__(x, y, hp)

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp = max(0, self._hp - amount)
        print(f"  [TOWER]   take_damage(amount={amount}, dtype='{dtype}')  "
              f"→ HP={self._hp}/{self._max_hp}")
        if self._hp <= 0:
            self.is_alive = False


class SoldierDummy:
    """Dummy KHÔNG kế thừa Tower — chỉ nhận damage ×1.0."""

    def __init__(self, x: float, y: float, hp: int = 300):
        self.x = float(x)
        self.y = float(y)
        self._hp     = hp
        self._max_hp = hp
        self.is_alive = True

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp = max(0, self._hp - amount)
        print(f"  [SOLDIER] take_damage(amount={amount}, dtype='{dtype}')  "
              f"→ HP={self._hp}/{self._max_hp}")
        if self._hp <= 0:
            self.is_alive = False


# ── 6. Pygame setup ──────────────────────────────────────────────────────────

pygame.init()
W, H   = 1000, 720
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "TowerHunter Demo  (WASD=move  Shift=run  SPACE=siege  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font  = pygame.font.SysFont("Consolas", 15)
big   = pygame.font.SysFont("Consolas", 22, bold=True)


# ── 7. Spawn ─────────────────────────────────────────────────────────────────

CX, CY     = 200, H // 2
WALK_SPEED = 95.0
RUN_SPEED  = 150.0
ATTACK_RANGE = 60.0


def make_titan() -> TowerHunter:
    t = TowerHunter(float(CX), float(CY), {
        'hp': 800,
        'speed': WALK_SPEED,
        'damage': 40,
    })
    t._load_sprite()
    sprite_ok = t._sprite_sheet is not None
    sprite_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.modules['Titan'].__file__)),
        'Assets', 'Titan', 'towerhunter.png',
    )
    print(f"\n=== Spawn TowerHunter  HP={t._hp}  damage={t._damage}  "
          f"strategy={type(t._attack_strategy).__name__}  "
          f"sprite={'OK' if sprite_ok else 'MISSING'} ===")
    if not sprite_ok:
        print(f"  [WARN] Sprite không tải được: {sprite_path}")
        print(f"  → Titan sẽ hiển thị bằng hình tròn tím")
    return t


def make_dummies() -> tuple:
    tower   = TowerDummy(W - 280, H // 2 - 100, hp=600)
    soldier = SoldierDummy(W - 280, H // 2 + 100, hp=300)
    return tower, soldier


titan = make_titan()
tower_dummy, soldier_dummy = make_dummies()


# ── 7b. Spawn 10 soldier + 3 hero + 3 tower (background) ─────────────────────
from _demo_dummies import (  # noqa: E402
    spawn_world, draw_all, update_all,
    TowerDummy as _DTowerDummy,
)


class _TowerHybrid(_DTowerDummy, _MockTower):
    """Tower kết hợp: render từ _demo_dummies.TowerDummy + isinstance(Tower)."""

    def __init__(self, x: float, y: float, label: str = "Tower",
                 hp: int = 800) -> None:
        # Khởi tạo TowerDummy (chính) — đã set x, y, hp, label, ...
        _DTowerDummy.__init__(self, x, y, label=label, hp=hp)


def _spawn_with_hybrid_tower():
    soldiers, heroes, towers_bg = spawn_world(W, H, titan.x, titan.y)
    # Convert TowerDummy → _TowerHybrid để được isinstance(Tower)
    hybrid = []
    for t in towers_bg:
        hybrid.append(_TowerHybrid(t.x, t.y, label=t._label, hp=t._max_hp))
    return soldiers, heroes, hybrid


soldiers, heroes, towers_bg = _spawn_with_hybrid_tower()
# Pool tower bao gồm cả tower_dummy chính
_MockWorldQuery.soldiers   = soldiers + [soldier_dummy]
_MockWorldQuery.commanders = heroes
_MockWorldQuery.towers     = [tower_dummy] + towers_bg
print(f"[Spawn] soldiers={len(soldiers) + 1}  heroes={len(heroes)}  "
      f"towers={len(towers_bg) + 1} (incl. main)")


DIR_NAMES = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}


def _distance(a, b) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _find_nearest(titan, dummies) -> tuple:
    """Trả về (target, dist) của dummy còn sống gần nhất, hoặc (None, inf)."""
    best = None
    best_d = float('inf')
    for d in dummies:
        if not d.is_alive:
            continue
        dist = _distance(titan, d)
        if dist < best_d:
            best_d = dist
            best = d
    return best, best_d


def _target_name(e) -> str:
    """Tên hiển thị an toàn cho mọi loại target."""
    return getattr(e, '_label', None) or getattr(e, 'name', None) \
        or type(e).__name__


def _all_targets() -> list:
    """Gộp MỌI mục tiêu có thể đánh: tower + soldier + hero.

    Gồm cả tower_dummy/soldier_dummy chính lẫn background từ
    _demo_dummies. Đọc động → cập nhật đúng sau khi bấm R (respawn).
    """
    return ([tower_dummy] + list(towers_bg)
            + [soldier_dummy] + list(soldiers)
            + list(heroes))


# ── 8. Vòng lặp ──────────────────────────────────────────────────────────────

running = True

while running:
    dt = min(clock.tick(60) / 1000.0, 0.05)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

            elif event.key == pygame.K_SPACE:
                titan.trigger_attack()
                # Đánh mục tiêu gần nhất trong MỌI loại (tower/soldier/
                # hero). TowerHunterStrategy giữ hiệu ứng đặc thù: ×1.5
                # damage nếu target là Tower (isinstance check), ×1.0
                # với các loại khác.
                target, dist = _find_nearest(titan, _all_targets())
                if target is not None and dist <= ATTACK_RANGE:
                    is_tower = isinstance(target, _MockTower)
                    mult = 1.5 if is_tower else 1.0
                    expected = int(titan._damage * mult)
                    print(f"[SIEGE]   dir={DIR_NAMES[titan._direction]}  "
                          f"target={_target_name(target)}  "
                          f"expected={titan._damage}×{mult}={expected}")
                    titan._attack_strategy.execute(titan, target)
                elif target is not None:
                    print(f"[SIEGE miss]  nearest dist={dist:.0f} > {ATTACK_RANGE:.0f}")
                else:
                    print(f"[SIEGE miss]  hết mục tiêu")

            elif event.key == pygame.K_r:
                titan = make_titan()
                tower_dummy, soldier_dummy = make_dummies()
                soldiers, heroes, towers_bg = _spawn_with_hybrid_tower()
                _MockWorldQuery.soldiers   = soldiers + [soldier_dummy]
                _MockWorldQuery.commanders = heroes
                _MockWorldQuery.towers     = [tower_dummy] + towers_bg
                print(f"[Respawn] soldiers={len(soldiers) + 1}  "
                      f"heroes={len(heroes)}  towers={len(towers_bg) + 1}")

    # Movement (chặn khi đang đánh)
    if not titan._is_attacking:
        keys = pygame.key.get_pressed()
        titan._is_running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        speed = RUN_SPEED if titan._is_running else WALK_SPEED

        dx = dy = 0.0
        if keys[pygame.K_w]:
            dy -= 1.0
        if keys[pygame.K_s]:
            dy += 1.0
        if keys[pygame.K_a]:
            dx -= 1.0
        if keys[pygame.K_d]:
            dx += 1.0

        # Hướng nhìn: ưu tiên trục ngang (A/D) hơn trục dọc (W/S).
        #   W+D → D, A+W → A. A+D (hoặc W+S) triệt tiêu → giữ hướng cũ.
        if dx < 0:
            titan._direction = 1   # West  (A)
        elif dx > 0:
            titan._direction = 3   # East  (D)
        elif dy < 0:
            titan._direction = 0   # North (W)
        elif dy > 0:
            titan._direction = 2   # South (S)

        if dx != 0.0 and dy != 0.0:
            inv = 1.0 / math.sqrt(2.0)
            dx *= inv
            dy *= inv

        mx = dx * speed * dt
        my = dy * speed * dt
        titan._is_moving = (mx != 0.0 or my != 0.0)
        if titan._is_moving:
            titan.x = max(32.0, min(float(W - 32), titan.x + mx))
            titan.y = max(32.0, min(float(H - 32), titan.y + my))
    else:
        titan._is_moving = False

    titan.update_anim(dt)

    # ── Draw ─────────────────────────────────────────────────────────────────
    screen.fill((28, 32, 38))

    for gx in range(0, W, 64):
        pygame.draw.line(screen, (45, 50, 58), (gx, 0), (gx, H))
    for gy in range(0, H, 64):
        pygame.draw.line(screen, (45, 50, 58), (0, gy), (W, gy))

    # Update + Draw background entities (10 soldier + 3 hero + 3 tower)
    update_all(dt, soldiers, heroes, towers_bg)
    draw_all(screen, font, soldiers, heroes, towers_bg)

    # Tower dummy (hình vuông đá xám)
    if tower_dummy.is_alive:
        tx, ty = int(tower_dummy.x), int(tower_dummy.y)
        rect = pygame.Rect(tx - 32, ty - 36, 64, 72)
        pygame.draw.rect(screen, (130, 130, 150), rect)
        pygame.draw.rect(screen, (220, 220, 240), rect, 2)
        # Crenellation
        for cx in range(tx - 30, tx + 30, 14):
            pygame.draw.rect(screen, (130, 130, 150), (cx, ty - 46, 10, 10))
            pygame.draw.rect(screen, (220, 220, 240), (cx, ty - 46, 10, 10), 1)
        # HP bar
        ratio = tower_dummy._hp / tower_dummy._max_hp if tower_dummy._max_hp > 0 else 0
        bx = tx - 50
        by = ty - 60
        pygame.draw.rect(screen, (60, 0, 0), (bx, by, 100, 6))
        pygame.draw.rect(screen, (240, 200, 80), (bx, by, int(100 * ratio), 6))
        pygame.draw.rect(screen, (200, 200, 200), (bx, by, 100, 6), 1)
        lbl = font.render(f"TOWER {tower_dummy._hp}/{tower_dummy._max_hp}", True,
                          (220, 220, 220))
        screen.blit(lbl, (bx, by - 16))
    else:
        dead = big.render("TOWER DEAD", True, (255, 80, 80))
        screen.blit(dead, (int(tower_dummy.x - 70), int(tower_dummy.y - 12)))

    # Soldier dummy (hình tròn xanh lá)
    if soldier_dummy.is_alive:
        sx, sy = int(soldier_dummy.x), int(soldier_dummy.y)
        pygame.draw.circle(screen, (100, 180, 110), (sx, sy), 26)
        pygame.draw.circle(screen, (200, 240, 200), (sx, sy), 26, 2)
        ratio = soldier_dummy._hp / soldier_dummy._max_hp if soldier_dummy._max_hp > 0 else 0
        bx = sx - 50
        by = sy - 40
        pygame.draw.rect(screen, (60, 0, 0), (bx, by, 100, 6))
        pygame.draw.rect(screen, (120, 220, 120), (bx, by, int(100 * ratio), 6))
        pygame.draw.rect(screen, (200, 200, 200), (bx, by, 100, 6), 1)
        lbl = font.render(f"SOLDIER {soldier_dummy._hp}/{soldier_dummy._max_hp}", True,
                          (220, 220, 220))
        screen.blit(lbl, (bx, by - 16))
    else:
        dead = big.render("SOLDIER DEAD", True, (255, 80, 80))
        screen.blit(dead, (int(soldier_dummy.x - 80), int(soldier_dummy.y - 12)))

    # Titan
    titan.draw(screen)
    if titan._sprite_sheet is None:
        cx_t, cy_t = int(titan.x), int(titan.y)
        pygame.draw.circle(screen, (170, 90, 200), (cx_t, cy_t), 28)
        pygame.draw.circle(screen, (230, 200, 240), (cx_t, cy_t), 28, 2)
        angle_map = {0: -math.pi / 2, 1: math.pi, 2: math.pi / 2, 3: 0.0}
        ang = angle_map[titan._direction]
        tip_x = cx_t + int(math.cos(ang) * 34)
        tip_y = cy_t + int(math.sin(ang) * 34)
        pygame.draw.line(screen, (255, 255, 255), (cx_t, cy_t), (tip_x, tip_y), 3)

    # Vòng tầm siege
    pygame.draw.circle(screen, (200, 140, 220),
                       (int(titan.x), int(titan.y)), int(ATTACK_RANGE), 1)

    # HP bar titan
    bar_w = 80
    hp_ratio = titan._hp / titan._max_hp if titan._max_hp > 0 else 0
    bx = int(titan.x - bar_w // 2)
    by = int(titan.y - 50)
    pygame.draw.rect(screen, (60, 0, 0),  (bx, by, bar_w, 6))
    pygame.draw.rect(screen, (220, 40, 40), (bx, by, int(bar_w * hp_ratio), 6))
    pygame.draw.rect(screen, (200, 200, 200), (bx, by, bar_w, 6), 1)

    # HUD
    if titan._is_attacking:
        state = "SIEGE"
        row   = titan._ATTACK_ROWS[titan._direction]
    elif titan._is_moving and titan._is_running:
        state = "RUN"
        row   = titan._RUN_ROWS[titan._direction]
    elif titan._is_moving:
        state = "WALK"
        row   = titan._WALK_ROWS[titan._direction]
    else:
        state = "IDLE"
        row   = titan._WALK_ROWS[titan._direction]

    sprite_status = "OK" if titan._sprite_sheet is not None else "MISSING (fallback)"
    nearest, ndist = _find_nearest(titan, [tower_dummy, soldier_dummy])
    if nearest is not None:
        kind = "TOWER" if isinstance(nearest, _MockTower) else "SOLDIER"
        nearest_str = f"{kind} @ {ndist:.0f}px"
    else:
        nearest_str = "—"

    hud = [
        f"sprite  : Assets/Titan/towerhunter.png  [{sprite_status}]",
        f"state   : {state}   dir={DIR_NAMES[titan._direction]}   "
        f"row={row}   col={titan._anim_col}",
        f"hp      : {titan._hp}/{titan._max_hp}  ({hp_ratio*100:.0f}%)",
        f"damage  : {titan._damage}  →  TOWER ×1.5 = "
        f"{int(titan._damage*1.5)}   SOLDIER ×1.0 = {titan._damage}",
        f"strategy: {type(titan._attack_strategy).__name__}  (dtype='siege')",
        f"nearest : {nearest_str}",
        "",
        "WASD=move  Shift=run  SPACE=siege (tầm 60px → dummy gần nhất)",
        "R=respawn  Q=quit",
    ]
    for i, line in enumerate(hud):
        surf = font.render(line, True, (220, 220, 220))
        screen.blit(surf, (12, 12 + i * 18))

    pygame.display.flip()

pygame.quit()
sys.exit()
