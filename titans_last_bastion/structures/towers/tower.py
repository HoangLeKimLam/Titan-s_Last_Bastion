# structures/towers/tower.py
import math
import os
import pygame
from systems.sound_system import SoundManager
from core.entity import Entity
from core.interfaces import IAttackable, IUpgradable
from structures.towers.attackstrategy import (
    TowerTargetingStrategy,
    NearestTargeting,
)
from structures.towers.projectile import (
    BasicProjectile,
    ExplosiveProjectile,
    ElectricProjectile,
    IceProjectile,
    WaterProjectile,
)
from characters.soldiers.soldier import SOLDIER_TYPES
from config import balance

_TOWER_IMG = None

_TOWER_WIDTH = 85  # px — điều chỉnh chiều rộng, chiều cao tự tính theo tỉ lệ gốc

def _get_tower_img():
    """Nạp `tower.png` MỘT LẦN cho MỌI tháp đất (module-level cache, không phải class).

    Mọi loại tháp (Basic/Electric/Water/Ice) dùng CHUNG 1 SPRITE THÂN THÁP —
    khác biệt giữa các loại chỉ ở "badge" (đạn/hiệu ứng) vẽ đè lên trên (xem
    `Tower.draw()`). Scale theo `_TOWER_WIDTH` (85px), chiều cao tự tính theo tỉ
    lệ gốc để không méo ảnh. Lỗi nạp → tạo Surface rỗng cùng kích thước (không crash).
    """
    global _TOWER_IMG
    if _TOWER_IMG is None:
        path = os.path.join(os.path.dirname(__file__), 'tower.png')
        try:
            raw = pygame.image.load(path).convert_alpha()
            w, h = raw.get_size()
            new_h = int(h * _TOWER_WIDTH / w)
            _TOWER_IMG = pygame.transform.scale(raw, (_TOWER_WIDTH, new_h))
        except Exception as e:
            print("tower.png load error:", e)
            _TOWER_IMG = pygame.Surface((_TOWER_WIDTH, _TOWER_WIDTH), pygame.SRCALPHA)
    return _TOWER_IMG


# ═══════════════════════════════════════════════════════
#  TOWER BASE
# ═══════════════════════════════════════════════════════

class Tower(Entity, IAttackable, IUpgradable):
    """
    Cha của mọi tháp.

    Cơ chế nâng cấp:
        - Dùng apply_orb() tiêu ore tương ứng → tăng stat
        - Khi stat đạt ngưỡng → tự lên level
        - Đạt MAX_LEVEL → can_apply_orb() = False, không nhận orb nữa

    Cơ chế strategy:
        - Mỗi tháp HAS-A TowerTargetingStrategy
        - Gọi set_targeting() bất kỳ lúc nào để đổi cách nhắm

    Cơ chế bắn:
        - shoot() tạo và trả về Projectile
        - update() spawn projectile vào WorldQuery để bay đến mục tiêu
        - Hiệu ứng khi trúng nằm hoàn toàn trong Projectile._on_hit()
    """

    ENTITY_TYPE       = 'tower'

    MAX_LEVEL         = balance.TOWER_MAX_LEVEL
    ORB_FIELD         = 'ore'
    DMG_PER_ORB       = balance.TOWER_DMG_PER_ORB
    LV2_DMG_THRESHOLD = balance.TOWER_LV2_DMG_THRESHOLD

    # --- Garrison / squad deployment constants ---------------------------
    CAPACITY           : int   = balance.TOWER_CAPACITY      # max total squads stored
    AGGRO_RADIUS       : float = balance.TOWER_AGGRO_RADIUS  # px — titan inside → start event
    WAVE_COOLDOWN      : float = balance.TOWER_WAVE_COOLDOWN    # s between waves in one event
    EVENT_COOLDOWN     : float = balance.TOWER_EVENT_COOLDOWN    # s rest after a finished event
    MAX_WAVES_PER_EVENT: int   = balance.TOWER_MAX_WAVES_PER_EVENT

    DEFAULT_GARRISON  : dict  = {}
    DEFAULT_WAVE_ORDER: tuple = ("Warrior", "Lancer", "Archer")

    def __init__(self, x: float, y: float, config: dict):
        """Khởi tạo tháp từ `config` (bắt buộc) + toàn bộ state garrison/dispatch.

        Tham số: config — dict {hp, damage, range, cooldown}. Class con LUÔN
            truyền config CỤ THỂ của mình (vd BasicTower truyền {hp:300,...}),
            KHÔNG có mặc định ở tầng base — nếu thiếu key thì fallback trong
            `.get()` mới áp dụng.

        Các cờ "buff vĩnh viễn" từ item túi đồ:
            `_stun_immune`     — anti_stun: `stun()` thành no-op HOÀN TOÀN.
            `_serum_buff`      — serum: MỌI đạn tháp bắn ra mang thêm hiệu ứng
                giảm hồi máu Founding (xem `Projectile._apply_serum_debuff`).
            `_anti_armor_buff` — anti_armor_ore: MỌI đạn tháp bắn ra dùng
                dtype='anti_armor' (xuyên giáp ArmoredTitan hoàn toàn, xem
                `Projectile._eff_dtype`), bất kể dtype gốc của loại đạn.
            `_disarmed`        — hết đạn cụ thể: tắt bắn nhưng VẪN chứa/điều lính.

        **GARRISON SYSTEM** (đóng quân trong tháp, điều lính ra đánh titan):
          - `garrison: dict{type: count}` — số SQUAD mỗi loại đang chứa, khởi
            tạo từ `DEFAULT_GARRISON` (class con override), rồi `_trim_to_capacity()`
            cắt bớt nếu vượt `CAPACITY`.
          - `_garrison_sizes: dict{type: [size,...]}` — LIST SONG SONG lưu SỐ
            LƯỢNG THẬT mỗi squad (có thể < SQUAD_SIZE tiêu chuẩn nếu squad đã bị
            hao hụt sau khi rút quân).
          - `wave_order` — 3 slot loại lính LUÂN PHIÊN mỗi đợt (wave) trong 1 sự
            kiện tấn công (event).
          - Máy trạng thái dispatch: `_squad_state` ("idle"→"active"→"cooldown"),
            `_wave_timer`/`_event_cd`/`_wave_index`/`_waves_done` (xem
            `_update_squad_dispatch`).
          - `_reserve_squads` — squad đã RÚT VỀ (lính "biến vào trong tháp") NHƯNG
            VẪN GIỮ ENTITY THẬT (không xoá, không tạo lại) — tái xuất hiện đúng
            những entity cũ khi có titan mới xuất hiện.

        Chỉ số: balance.BASIC_TOWER_*/etc (do class con truyền qua config),
        balance.TOWER_CAPACITY/_AGGRO_RADIUS/_WAVE_COOLDOWN/_EVENT_COOLDOWN/_MAX_WAVES_PER_EVENT.
        """
        super().__init__(x, y)
        self._hp          = config.get('hp',       300)
        self._max_hp      = config.get('hp',       300)
        self._damage      = config.get('damage',   40)
        self._range       = config.get('range',    180)
        self._cooldown    = config.get('cooldown', 2.0)
        self._level       = 1
        self._shoot_timer = 0.0
        self._stun_timer  = 0.0
        self._disarmed    = False   # tắt vũ khí → không bắn (vẫn chứa/điều lính)
        self._stun_immune = False   # anti_stun (item) — vĩnh viễn, stun() no-op
        self._serum_buff  = False   # serum (item) — vĩnh viễn, mọi đạn mang thêm
                                     # hiệu ứng giảm hồi máu Founding (xem Projectile)
        self._anti_armor_buff = False   # anti_armor_ore (item) — vĩnh viễn, mọi
                                     # đạn tháp này bắn ra dùng dtype='anti_armor'
                                     # (xuyên giáp hoàn toàn, xem Projectile._eff_dtype)
        self._wall_name   = None    # 'maria'/'rose'/'sina' nếu đặt trên tường
        self._targeting: TowerTargetingStrategy = NearestTargeting()

        # Badge: sprite/animation của đạn ghép lên trên tower.png
        self._badge_sprite = None
        self._badge_anim   = None

        # --- Garrison dict: per-type squad counts -------------------------
        self.garrison: dict = {t: 0 for t in SOLDIER_TYPES}
        for t, n in self.DEFAULT_GARRISON.items():
            if t in SOLDIER_TYPES and int(n) >= 0:
                self.garrison[t] = int(n)
        self._trim_to_capacity()
        # _garrison_sizes: parallel list of actual squad sizes (may be < SQUAD_SIZE after retreat)
        from characters.soldiers.squad import SQUAD_SIZE as _SZ
        self._garrison_sizes: dict = {t: [_SZ] * self.garrison.get(t, 0)
                                      for t in SOLDIER_TYPES}

        # Wave order: slots cycled per event, scaling to MAX_WAVES_PER_EVENT.
        _base = list(self.DEFAULT_WAVE_ORDER)
        self.wave_order: list = [_base[i % len(_base)] for i in range(self.MAX_WAVES_PER_EVENT)]

        # Squad-dispatch state machine: idle → active → cooldown
        self._squad_state : str   = "idle"
        self._wave_timer  : float = 0.0
        self._event_cd    : float = 0.0
        self._wave_index  : int   = 0
        self._waves_done  : int   = 0
        self._active_squad        = None   # Squad — for wipe-detection
        self._highlight_aggro: bool = False
        self._deployed_squads: list = []   # all squads sent out (for stats tab)
        # Entity reserve: squad đã rút về tháp (lính biến vào trong), GIỮ entity thật.
        # Tái xuất hiện đúng entity khi có titan. Đây là quản-lý-theo-entity.
        self._reserve_squads: list = []

    # ── Strategy ─────────────────────────────────────────────────────

    def set_targeting(self, strategy: TowerTargetingStrategy):
        """Đổi cách chọn mục tiêu (Strategy Pattern) — đổi được BẤT KỲ LÚC NÀO, kể
        cả lúc runtime, không cần khởi tạo lại tháp."""
        self._targeting = strategy

    def get_targeting(self) -> TowerTargetingStrategy:
        """Strategy chọn mục tiêu hiện tại (UI dùng hiển thị/cho phép đổi)."""
        return self._targeting

    # ── Garrison API (used by TowerMenu / HUD) ────────────────────────

    def total_garrison(self) -> int:
        """Tổng SỐ SQUAD đang chứa (mọi loại lính cộng lại) — so với `CAPACITY`.

        Cộng cả squad đã chuyển sang `_reserve_squads`/`_deployed_squads` trong
        combat (lúc `garrison` dict đã bị drain về 0 ở start_combat) — nếu không
        badge hiện 0/8 dù tháp còn đầy lính và capacity-check bị hụt. 3 nguồn
        loại trừ nhau theo pha nên KHÔNG đếm trùng: prep chỉ có dict, combat chỉ
        có reserve + deployed."""
        return (sum(self.garrison.values())
                + len(getattr(self, '_reserve_squads', []))
                + len(getattr(self, '_deployed_squads', [])))

    def set_garrison(self, soldier_type: str, count: int) -> bool:
        """Set per-type count. Returns False if new total would exceed CAPACITY."""
        if soldier_type not in SOLDIER_TYPES:
            raise ValueError(f"Unknown soldier type: {soldier_type!r}")
        count = max(0, int(count))
        others = self.total_garrison() - self.garrison[soldier_type]
        if others + count > self.CAPACITY:
            return False
        self.garrison[soldier_type] = count
        return True

    def adjust_garrison(self, soldier_type: str, delta: int, size: int = -1) -> bool:
        """Convenience for +/- buttons. `size` sets squad size when delta>0."""
        from characters.soldiers.squad import SQUAD_SIZE as _SZ
        if size < 0:
            size = _SZ
        result = self.set_garrison(soldier_type,
                                   self.garrison.get(soldier_type, 0) + delta)
        if result:
            sizes = self._garrison_sizes.setdefault(soldier_type, [])
            if delta > 0:
                sizes.append(size)
            elif delta < 0 and sizes:
                sizes.pop()
        return result

    def set_wave_slot(self, index: int, soldier_type: str) -> None:
        """Đặt loại lính cho 1 SLOT wave (0..MAX_WAVES_PER_EVENT-1) — điều khiển
        thứ tự lính xuất trận mỗi đợt tấn công. Chỉ số/loại sai → raise ngay."""
        if not 0 <= index < self.MAX_WAVES_PER_EVENT:
            raise IndexError(f"wave slot out of range: {index}")
        if soldier_type not in SOLDIER_TYPES:
            raise ValueError(f"Unknown soldier type: {soldier_type!r}")
        self.wave_order[index] = soldier_type

    def cycle_wave_slot(self, index: int) -> str:
        """Cycle wave slot through SOLDIER_TYPES. Returns the new type."""
        order = list(SOLDIER_TYPES.keys())
        cur = self.wave_order[index]
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else order[0]
        self.set_wave_slot(index, nxt)
        return nxt

    # ── Orb upgrade ──────────────────────────────────────────────────

    def can_apply_orb(self) -> bool:
        """True nếu tháp CHƯA đạt cấp tối đa — còn nhận orb nâng cấp được."""
        return self._level < self.MAX_LEVEL

    def apply_orb(self, amount: int = 1) -> bool:
        """Nạp `amount` orb (tài nguyên `ORB_FIELD`) vào tháp — TĂNG STAT + có thể LÊN CẤP.

        Thuật toán:
          1. Đã max cấp → False ngay.
          2. Tạo `ResourceBundle(**{ORB_FIELD: amount})` — mỗi loại tháp dùng
             LOẠI ORE RIÊNG (`ORB_FIELD`: 'ore'/'electric_ore'/'water_ore'/'ice_ore').
          3. Không đủ tài nguyên → False, KHÔNG trừ gì.
          4. Đủ → trừ tài nguyên, gọi `_on_orb_applied()` (class con override để
             tăng đúng stat của loại tháp đó) rồi `_check_levelup()`.

        SỬA LỖI: `amount` ở đây là GIÁ TIỀN mỗi lần bấm (balance.TOWER_ORB_COST,
        vd 5 ore/click) — KHÔNG phải số đơn vị tiến trình damage. Trước đây
        `_on_orb_applied(amount)` nhân thẳng `amount` này vào damage
        (`DMG_PER_ORB × amount`), nên khi TOWER_ORB_COST tăng lên 5, damage
        cũng vọt lên gấp 5 MỖI CLICK → tháp lên full cấp chỉ sau 1 lần bấm
        (đáng lẽ cần nhiều lần, tăng dần). Tách 2 khái niệm: `amount` VẪN
        dùng để trừ đúng giá tiền (`cost`), nhưng tiến trình damage LUÔN cố
        định +1 đơn vị mỗi lần bấm thành công — không phụ thuộc giá đắt/rẻ.

        Trả về: bool — True = nạp thành công.
        """
        if not self.can_apply_orb():
            return False
        from structures.buildings.resource_manager import ResourceManager
        from core.game_state import ResourceBundle
        rm   = ResourceManager.get_instance()
        cost = ResourceBundle(**{self.ORB_FIELD: amount})
        if not rm.can_afford(cost):
            return False
        rm.spend(cost)
        self._on_orb_applied(1)
        self._check_levelup()
        return True

    def _on_orb_applied(self, amount: int):
        """HOOK — tăng damage theo `DMG_PER_ORB × amount`. Class con override để
        tăng THÊM stat khác (chain damage, push radius, slow duration...)."""
        self._damage += self.DMG_PER_ORB * amount

    def _check_levelup(self):
        """HOOK — lên cấp khi damage đạt `LV2_DMG_THRESHOLD`. Một số loại tháp
        (IceTower) override để dùng ngưỡng khác (slow_duration) thay vì damage."""
        if self._level < self.MAX_LEVEL and self._damage >= self.LV2_DMG_THRESHOLD:
            self._level += 1

    # ── IUpgradable (không dùng — xài apply_orb()) ───────────────────

    def upgrade(self):
        """No-op — API `IUpgradable` bắt buộc phải có, nhưng tháp KHÔNG dùng cơ
        chế upgrade() chung; nâng cấp tháp đi qua `apply_orb()` riêng."""
        pass

    def get_upgrade_cost(self):
        """Trả `ResourceBundle()` rỗng — tháp không có "giá upgrade" cố định
        (chi phí thực tế là `amount` orb truyền vào `apply_orb()`)."""
        from core.game_state import ResourceBundle
        return ResourceBundle()

    # ── Combat ───────────────────────────────────────────────────────

    def update(self, dt: float):
        """Vòng update mỗi frame: badge animation → CHOÁNG (nếu có) → bắn → điều lính.

        Thuật toán:
          1. Có `_badge_anim` (hiệu ứng đạn hoạt hình trên đầu tháp) → tiến animation.
          2. **CHOÁNG** (`_stun_timer > 0`): đếm ngược rồi `return` NGAY — KHÔNG
             bắn, KHÔNG điều lính (đây là lý do đá Beast/Jump Stomp làm tháp "ngừng
             hoạt động hoàn toàn", không chỉ ngừng bắn).
          3. Đếm ngược `_shoot_timer`; hết → `_pick_target()` (uỷ quyền cho
             `_targeting` strategy) → có mục tiêu → `shoot()` tạo projectile,
             giao cho `WorldQuery.spawn_entity()` quản lý bay, nạp lại
             `_shoot_timer = _cooldown`.
          4. `_update_squad_dispatch(dt)` — máy trạng thái điều lính RIÊNG, chạy
             SONG SONG với bắn (một tháp vừa bắn vừa điều quân).

        Chỉ số: balance.<TOWER>_COOLDOWN.
        """
        if self._badge_anim:
            self._badge_anim.update(dt)
        # Hồi máu lính đang NGHỈ TRONG THÁP (reserve) — chạy mỗi frame, kể cả khi
        # tháp bị choáng (đứng TRƯỚC nhánh stun-return bên dưới).
        self._heal_reserve_soldiers(dt)
        if self._stun_timer > 0:
            self._stun_timer -= dt
            return
        self._shoot_timer -= dt
        if self._shoot_timer <= 0:
            target = self._pick_target()
            if target is not None:
                projectile = self.shoot(target)
                from systems.world_query import WorldQuery
                WorldQuery.spawn_entity(projectile)
                self._shoot_timer = self._cooldown
        self._update_squad_dispatch(dt)

    def _heal_reserve_soldiers(self, dt: float) -> None:
        """Hồi máu lính đang NGHỈ TRONG THÁP (`_reserve_squads`) — chúng đã bị
        `_absorb_idle_squads` gỡ khỏi map nên `Soldier.update()` KHÔNG còn chạy,
        nhánh heal IDLE của lính không kích hoạt → nếu không tick ở đây thì lính
        "về tháp" đứng yên ở HP thấp mãi. Tháp tự tick heal, DÙNG ĐÚNG luật của
        lính: mỗi `HEAL_TICK` giây hồi `HEAL_RATE`, chỉ khi `hp < max` và
        `_can_heal` (chưa dính antiheal Wolf). Reserve chỉ tồn tại khi KHÔNG có
        titan trong tầm (điều kiện absorb) nên hồi ở đây an toàn."""
        for sq in self._reserve_squads:
            for m in sq.members:
                if (getattr(m, 'is_alive', False)
                        and m._hp < m._max_hp
                        and getattr(m, '_can_heal', True)):
                    m._heal_timer += dt
                    if m._heal_timer >= m.HEAL_TICK:
                        m._heal_timer = 0.0
                        m._hp = min(m._max_hp, m._hp + m.HEAL_RATE)

    def shoot(self, target: IAttackable) -> BasicProjectile:
        """HOOK — tạo 1 viên đạn BASIC (dtype='normal') nhắm `target`. Mọi class
        con override để bắn đúng loại đạn của mình (Explosive/Electric/Water/Ice)."""
        return BasicProjectile(self.x, self.y, target, self._damage, 'normal',
                               shooter=self)

    def stun(self, duration: float):
        """Làm CHOÁNG tháp trong `duration` giây — no-op HOÀN TOÀN nếu có item anti_stun.

        Không CỘNG DỒN: `_stun_timer = max(hiện tại, duration)` — choáng 2 lần
        liên tiếp không kéo dài hơn, chỉ LÀM MỚI về giá trị lớn hơn.
        Nguồn gọi: `GroundSlamStrategy`/skill Jump Stomp (Colossal), đá Beast.
        """
        if self._stun_immune:
            return
        self._stun_timer = max(self._stun_timer, duration)

    def take_damage(self, amount: int, dtype: str):
        """Nhận damage — hết HP thì SẬP: publish event + XẢ TOÀN BỘ lính đang giấu trong tháp.

        Thuật toán: trừ HP thẳng (KHÔNG có giáp ở tầng Tower base). HP<=0 →
        `is_alive=False`, `spill_reserves()` (đẩy MỌI squad đang ẩn trong tháp ra
        ngoài — chúng không biến mất theo tháp, được "giải phóng" khi tháp sập),
        publish `'tower_destroyed'` (HUD/lính rút lui subscribe).
        """
        self._hp -= amount
        if self._hp <= 0:
            self.is_alive = False
            self.spill_reserves()
            from core.event_bus import GameEventBus
            GameEventBus.get_instance().publish('tower_destroyed', {'tower': self})

    def get_garrison_pos(self) -> tuple:
        """Điểm ĐỨNG GÁC của lính khi ở IDLE cạnh tháp (lệch phải 40px so với tâm tháp)."""
        return (self.x + 40, self.y)

    def draw(self, screen):
        """Vẽ thân tháp (sprite CHUNG cho mọi loại) + badge riêng (đạn/hiệu ứng đè lên trên).

        Badge ưu tiên: `_badge_anim` (hoạt hình, nếu có) > `_badge_sprite` (tĩnh).
        Vị trí badge: căn giữa NGANG với tháp, lệch LÊN 1/4 chiều cao sprite thân.
        CHỈ ĐỒ HOẠ.
        """
        img = _get_tower_img()
        rect = img.get_rect(center=(int(self.x), int(self.y)))
        screen.blit(img, rect.topleft)

        # Badge: frame loop của đạn, căn giữa phần trên tower
        badge_y = int(self.y) - img.get_height() // 4
        badge = None
        if self._badge_anim:
            badge = self._badge_anim.get_current_frame()
        elif self._badge_sprite:
            badge = self._badge_sprite
        if badge:
            brect = badge.get_rect(center=(int(self.x), badge_y))
            screen.blit(badge, brect.topleft)

        try:
            # Garrison count badge above tower
            font = pygame.font.SysFont("consolas", 13, bold=True)
            txt = font.render(f"{self.total_garrison()}/{self.CAPACITY}",
                              True, (235, 235, 235))
            screen.blit(txt, txt.get_rect(midbottom=(int(self.x),
                                                      rect.top - 4)))
            # Active ring when deploying squads
            if self._squad_state == "active":
                pygame.draw.circle(screen, (250, 210, 90),
                                   (int(self.x), int(self.y)),
                                   img.get_width() // 2 + 8, 2)
            # Dashed aggro ring when highlighted (menu open)
            if self._highlight_aggro:
                self._draw_dashed_circle(screen,
                                         (int(self.x), int(self.y)),
                                         int(self.AGGRO_RADIUS),
                                         (250, 220, 90), segments=64)
        except (AttributeError, pygame.error):
            pass

    def allowed_zones(self) -> tuple:
        """Vùng tháp được phép phát hiện/bắn.
        - Tháp trên tường → 2 vùng giáp tường (WALL_ZONE_PAIRS).
        - Tháp tự do trong 1 vùng → đúng vùng đó.
        """
        from systems.world_query import WorldQuery
        wn = getattr(self, '_wall_name', None)
        if wn:
            zones = WorldQuery.zones_for_wall(wn)
            if zones:
                return zones
        return (WorldQuery.zone_of(self.x, self.y),)

    def _in_allowed_zone(self, entity) -> bool:
        """True nếu `entity` đứng trong 1 trong các vùng tháp được phép tương tác
        (xem `allowed_zones()`)."""
        from systems.world_query import WorldQuery
        return WorldQuery.zone_of(entity.x, entity.y) in self.allowed_zones()

    def _pick_target(self):
        """Chọn 1 titan để BẮN — quét tầm, lọc vùng, rồi uỷ quyền cho targeting strategy.

        Thuật toán:
          1. `_disarmed` (hết đạn) → None ngay, không bắn.
          2. Quét mọi titan trong `_range` quanh tháp.
          3. **LỌC VÙNG**: chỉ giữ titan nằm trong `allowed_zones()` — tháp KHÔNG
             bắn xuyên qua tường vào vùng khác (trừ tháp gắn tường, được phép cả
             2 phía nó giáp).
          4. `_targeting.select_target()` (NearestTargeting mặc định, có thể đổi
             qua `set_targeting()`) chọn 1 trong danh sách đã lọc.

        Trả về: entity titan, hoặc None nếu không có mục tiêu hợp lệ.
        """
        from systems.world_query import WorldQuery
        if getattr(self, '_disarmed', False):
            return None  # tháp tắt vũ khí → không bắn
        titans = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self._range,
            entity_type='titan'
        )
        # Lọc theo vùng: chỉ bắn titan trong vùng cho phép
        zones = self.allowed_zones()
        titans = [t for t in titans if WorldQuery.zone_of(t.x, t.y) in zones]
        return self._targeting.select_target(self, titans)

    # ── Squad-dispatch state machine ─────────────────────────────────

    def _has_deployable(self) -> bool:
        """Còn lính để thả: reserve entity squad HOẶC kho count."""
        return len(self._reserve_squads) > 0 or self.total_garrison() > 0

    @staticmethod
    def _resolve_stuck_squad(squad, WorldQuery) -> None:
        """Nếu có lính kẹt tường, dồn nó vào vị trí của lính không kẹt trong cùng squad."""
        import random
        alive = [s for s in squad.members if s.is_alive]
        non_stuck = [s for s in alive if not (WorldQuery.is_wall_blocked(s.x, s.y, 10.0) or WorldQuery.is_wall_visual_blocked(s.x, s.y))]
        stuck = [s for s in alive if s not in non_stuck]
        if non_stuck and stuck:
            for s in stuck:
                ns = random.choice(non_stuck)
                s.x, s.y = ns.x, ns.y

    def spill_reserves(self) -> None:
        """Tháp chết → đổ lính ra thành MỒ CÔI.

        - Reserve (đang cất trong tháp, chưa trên map): xuất hiện tại điểm thoáng
          gần tháp (phía trong tường hướng HQ).
        - Deployed (đang chiến đấu trên map): CHỈ set homeless + cập nhật zone,
          KHÔNG di chuyển — tránh reset vị trí lính đang đánh.
        """
        from systems.world_query import WorldQuery
        hq = WorldQuery.get_headquarters()
        if hq is not None:
            idx, idy = hq.x - self.x, hq.y - self.y
            d = (idx * idx + idy * idy) ** 0.5 or 1.0
            inx, iny = idx / d, idy / d
        else:
            inx, iny = 0.0, 1.0

        bx, by = self.x + inx * 80.0, self.y + iny * 80.0
        if WorldQuery.is_wall_blocked(bx, by, 10.0):
            for step in (110, 140, 170, 200, 240):
                cx, cy = self.x + inx * step, self.y + iny * step
                if not WorldQuery.is_wall_blocked(cx, cy, 10.0):
                    bx, by = cx, cy
                    break
        zones = self.allowed_zones()

        def _clear_spot(s):
            """Tìm vị trí THOÁNG (không kẹt tường) cho lính `s` khi tháp sập.

            Thử vị trí offset theo đội hình gốc (`_slot_offset`) trước; nếu bị
            tường chặn thì fallback về điểm base chung `(bx, by)` (đã xác nhận
            thoáng ở bước trước đó trong `spill_reserves`).
            """
            ox, oy = getattr(s, '_slot_offset', (0.0, 0.0))
            px, py = bx + ox, by + oy
            if not WorldQuery.is_wall_blocked(px, py, 10.0):
                return px, py
            return bx, by

        # Reserve (chưa trên map) → tái xuất tại điểm thoáng
        for sq in list(self._reserve_squads):
            for s in sq.members:
                if not s.is_alive:
                    continue
                s.x, s.y = _clear_spot(s)
                s._state = "COMBAT"
                s._homeless = True
                s._transfer_target = None
                s._zones = zones
                s._home_pos = (bx, by)
            
            self._resolve_stuck_squad(sq, WorldQuery)
            
            for s in sq.members:
                if s.is_alive and s not in WorldQuery._entities:
                    WorldQuery.spawn_entity(s)

        # Deployed (đang trên map) → set homeless, GIỮ vị trí hiện tại
        for sq in list(self._deployed_squads):
            for s in sq.members:
                if not s.is_alive:
                    continue
                s._state = "COMBAT"
                s._homeless = True
                s._transfer_target = None
                # Neo "nhà" về ĐÚNG chỗ lính đang đứng (không bám toạ độ tháp đã
                # sập) → lính mồ côi phát hiện/giữ titan quanh chính nó, kể cả khi
                # đang transfer dở ở xa tháp. Vùng cho phép = zone gốc của tháp HỢP
                # thêm zone lính đang đứng, để lính transfer ở vùng khác vẫn đánh
                # được titan tại chỗ mà KHÔNG mất vùng cũ (lính deployed thường ở
                # trong zone tháp → union không đổi gì, tránh hồi quy).
                s._home_pos = (s.x, s.y)
                s._zones = tuple(set(zones) | {WorldQuery.zone_of(s.x, s.y)})
                # Không đổi x, y → giữ vị trí đang chiến đấu

        self._reserve_squads = []
        self._deployed_squads = []
        self._active_squad = None

    def _absorb_idle_squads(self) -> None:
        """Lính đã rút về tháp & idle (không có titan) → biến vào tháp (entity reserve).

        Gỡ entity khỏi map (biến mất) nhưng GIỮ object lính trong _reserve_squads.
        Tái xuất hiện đúng entity khi titan tới. Bỏ squad rỗng (chết sạch).
        """
        from systems.world_query import WorldQuery
        if self._find_titan_in_aggro() is not None:
            return  # có titan → để lính đánh, không hút vào tháp

        remaining = []
        for sq in self._deployed_squads:
            alive = [m for m in sq.members if m.is_alive]
            if not alive:
                continue  # squad chết sạch → bỏ
            # Tất cả thành viên còn sống đã về tháp (IDLE) → hút vào tháp
            if all(getattr(m, '_state', '') == 'IDLE' for m in alive):
                for m in alive:
                    WorldQuery.remove_entity(m)  # biến vào tháp (gỡ khỏi map)
                sq.members = alive               # giữ entity sống trong reserve
                if sq is self._active_squad:
                    self._active_squad = None
                self._reserve_squads.append(sq)
            else:
                remaining.append(sq)
        self._deployed_squads = remaining

    def _update_squad_dispatch(self, dt: float) -> None:
        """MÁY TRẠNG THÁI ĐIỀU LÍNH — 3 trạng thái: idle → active → cooldown → idle.

        Đây là "bộ não" của cơ chế garrison: tháp TỰ ĐỘNG phát hiện titan trong
        `AGGRO_RADIUS`, thả lính ra đánh theo NHIỀU ĐỢT (wave), rồi nghỉ.

        Thuật toán, MỖI FRAME:
          0. `_absorb_idle_squads()` — lính đã đánh xong quay về + IDLE → HÚT VÀO
             TRONG THÁP (biến khỏi bản đồ, giữ lại object để tái xuất sau).
          1. **`_squad_state == "cooldown"`**: đếm ngược `_event_cd`
             (`EVENT_COOLDOWN`), hết → về "idle". `return`.
          2. **`_squad_state == "idle"`**: không có gì để thả (`_has_deployable()`
             False) → chờ. Không có titan trong tầm → chờ. Có cả 2 → BẮT ĐẦU sự
             kiện: chuyển "active", reset `_wave_index/_waves_done/_wave_timer`.
          3. **`_squad_state == "active"`**:
             a. **WIPE-TRIGGERS-NEXT-WAVE**: squad hiện tại đã CHẾT SẠCH (không
                còn `is_alive`) và chưa hết số đợt → BỎ QUA thời gian chờ còn lại
                (`_wave_timer = 0`) → thả đợt TIẾP THEO NGAY, không đợi hết
                `WAVE_COOLDOWN`. (Squad chết sớm không phải đợi hết giờ mới có
                lính mới ra.)
             b. Đếm ngược `_wave_timer`; còn thời gian → chờ tiếp (`return`).
             c. Titan đã rời khỏi tầm → `_end_event()` (kết thúc sớm).
             d. `_spawn_next_wave(titan)` thất bại (hết quân) → `_end_event()`.
             e. Thành công → tăng `_waves_done`, xoay `_wave_index` sang slot kế.
                Đủ số đợt (`MAX_WAVES_PER_EVENT`) HOẶC hết quân để thả →
                `_end_event()`. Còn → nạp `_wave_timer = WAVE_COOLDOWN` (chờ đợt sau).

        Chỉ số: balance.TOWER_WAVE_COOLDOWN / _EVENT_COOLDOWN / _MAX_WAVES_PER_EVENT / _AGGRO_RADIUS.
        """
        # Hút lính idle đã về tháp vào entity-reserve (biến vào trong)
        self._absorb_idle_squads()

        if self._squad_state == "cooldown":
            self._event_cd = max(0.0, self._event_cd - dt)
            if self._event_cd <= 0.0:
                self._squad_state = "idle"
            return

        if self._squad_state == "idle":
            if not self._has_deployable():
                return
            titan = self._find_titan_in_aggro()
            if titan is None:
                return
            self._squad_state = "active"
            self._wave_index  = 0
            self._waves_done  = 0
            self._wave_timer  = 0.0

        if self._squad_state == "active":
            # Wipe-triggers-next-wave: skip remaining timer if squad is wiped
            if (self._active_squad is not None
                    and not self._active_squad.is_alive
                    and self._waves_done < self.MAX_WAVES_PER_EVENT):
                self._wave_timer = 0.0

            self._wave_timer = max(0.0, self._wave_timer - dt)
            if self._wave_timer > 0.0:
                return

            titan = self._find_titan_in_aggro()
            if titan is None:
                self._end_event()
                return

            if not self._spawn_next_wave(titan):
                self._end_event()
                return

            self._waves_done += 1
            self._wave_index = (self._wave_index + 1) % self.MAX_WAVES_PER_EVENT
            if (self._waves_done >= self.MAX_WAVES_PER_EVENT
                    or not self._has_deployable()):
                self._end_event()
            else:
                self._wave_timer = self.WAVE_COOLDOWN

    def _find_titan_in_aggro(self):
        """Return nearest alive titan within AGGRO_RADIUS & trong vùng cho phép, else None."""
        from systems.world_query import WorldQuery
        titans = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self.AGGRO_RADIUS,
            entity_type='titan'
        )
        zones = self.allowed_zones()
        titans = [t for t in titans if WorldQuery.zone_of(t.x, t.y) in zones]
        if not titans:
            return None
        return min(titans,
                   key=lambda e: (e.x - self.x) ** 2 + (e.y - self.y) ** 2)

    def _pick_wave_type(self) -> str | None:
        """Pick the soldier type for the current wave, skipping empty slots.
        Returns None when all garrison slots are empty."""
        for step in range(self.MAX_WAVES_PER_EVENT):
            idx = (self._wave_index + step) % self.MAX_WAVES_PER_EVENT
            t = self.wave_order[idx]
            if self.garrison.get(t, 0) > 0:
                self._wave_index = idx
                return t
        return None

    def _spawn_next_wave(self, titan) -> bool:
        """Thả 1 squad về phía `titan`.
        Ưu tiên tái xuất ENTITY RESERVE (lính thật đã cất trong tháp); hết mới
        sinh squad mới từ kho count. Returns False khi không còn gì để thả."""
        from systems.world_query import WorldQuery
        from characters.soldiers.squad import Squad, SQUAD_SIZE

        base_pos = self._safe_spawn_near(titan, WorldQuery)
        bx, by = base_pos

        # 1) Reserve entity squad (từ transfer hoặc đã rút về) → tái xuất đúng entity
        if self._reserve_squads:
            squad = self._reserve_squads.pop(0)
            squad._state = "COMBAT"
            for s in squad.members:
                if not s.is_alive:
                    continue
                ox, oy = getattr(s, '_slot_offset', (0.0, 0.0))
                s.x, s.y = bx + ox, by + oy
                if WorldQuery.is_wall_blocked(s.x, s.y, 10.0) or WorldQuery.is_wall_visual_blocked(s.x, s.y):
                    s.x, s.y = bx, by
                s._state = "COMBAT"
                s._target = None
                s._transfer_target = None
                s._home_pos = (self.x, self.y)
                s._home_radius = self.AGGRO_RADIUS
                s._zones = self.allowed_zones()
                if s not in WorldQuery._entities:
                    WorldQuery.spawn_entity(s)  # tái xuất hiện trên map
            self._active_squad = squad
            self._deployed_squads.append(squad)
            return True

        # 2) Kho count → sinh squad mới
        t = self._pick_wave_type()
        if t is None:
            return False
        sizes = self._garrison_sizes.get(t, [])
        squad_size = sizes.pop(0) if sizes else SQUAD_SIZE
        self.garrison[t] -= 1

        squad = Squad(t, base_pos, titan, size=squad_size,
                      home_pos=(self.x, self.y),
                      home_radius=self.AGGRO_RADIUS)
        squad.set_state("COMBAT")
        _zones = self.allowed_zones()
        for s in squad.members:
            if WorldQuery.is_wall_blocked(s.x, s.y, 10.0) or WorldQuery.is_wall_visual_blocked(s.x, s.y):
                s.x, s.y = bx, by
            s._zones = _zones
        
        self._resolve_stuck_squad(squad, WorldQuery)
        
        for s in squad.members:
            WorldQuery.spawn_entity(s)
            
        self._active_squad = squad
        self._deployed_squads.append(squad)
        return True

    def _safe_spawn_near(self, titan, WorldQuery) -> tuple:
        """Spawn tại tháp nhưng offset sang nửa mặt phẳng chứa titan (tường = đường chia).

        Dùng bán kính vật lý 22 px (> khe hàng rào 13.5 px) để đảm bảo lính không
        spawn lọt khe giữa 2 collider tường liền nhau.
        Fallback 4 hướng cardinal (E/W/S/N) khi tháp sát góc tường.
        """
        import math
        tx, ty = getattr(titan, 'x', self.x), getattr(titan, 'y', self.y)
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return (self.x, self.y)
        nx, ny = dx / dist, dy / dist

        # Thử hướng titan trước (offsets tăng dần để thoát khỏi tường gần)
        for offset in (48, 64, 80, 96, 120, 155, 195, 240):
            cx, cy = self.x + nx * offset, self.y + ny * offset
            if (not WorldQuery.is_wall_blocked(cx, cy, 22.0) and
                    not WorldQuery.is_wall_visual_blocked(cx, cy)):
                return (cx, cy)

        # Fallback 4 hướng cardinal: Đông, Tây, Nam, Bắc
        for cdx, cdy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for offset in (48, 80, 120, 180):
                cx, cy = self.x + cdx * offset, self.y + cdy * offset
                if (not WorldQuery.is_wall_blocked(cx, cy, 22.0) and
                        not WorldQuery.is_wall_visual_blocked(cx, cy)):
                    return (cx, cy)

        return (self.x, self.y)

    def _end_event(self) -> None:
        """Kết thúc sự kiện tấn công (hết đợt / hết quân / titan rời tầm) → nghỉ COOLDOWN.

        Chuyển `_squad_state = "cooldown"`, nạp `_event_cd = EVENT_COOLDOWN`, reset
        `_waves_done = 0`. Lính đã thả KHÔNG bị gọi về ngay — chúng tự đánh/tự rút
        theo máy trạng thái RIÊNG của `Soldier` (COMBAT→RETREAT→IDLE).

        Chỉ số: balance.TOWER_EVENT_COOLDOWN.
        """
        self._squad_state = "cooldown"
        self._event_cd    = self.EVENT_COOLDOWN
        self._waves_done  = 0
        self._wave_index  = 0
        self._wave_timer  = 0.0
        self._active_squad = None

    def _trim_to_capacity(self) -> None:
        """Reduce garrison counts round-robin from end until total ≤ CAPACITY."""
        keys = list(self.garrison.keys())
        i = len(keys) - 1
        while self.total_garrison() > self.CAPACITY and i >= 0:
            k = keys[i]
            if self.garrison[k] > 0:
                self.garrison[k] -= 1
            else:
                i -= 1
        for k in keys:
            if self.garrison[k] < 0:
                self.garrison[k] = 0

    @staticmethod
    def _draw_dashed_circle(screen, center: tuple, radius: int,
                            color: tuple, segments: int = 48) -> None:
        """Approximate dashed circle by skipping every other arc segment."""
        cx, cy = center
        for i in range(segments):
            if i % 2:
                continue
            a0 = (2 * math.pi * i) / segments
            a1 = (2 * math.pi * (i + 1)) / segments
            p0 = (int(cx + math.cos(a0) * radius), int(cy + math.sin(a0) * radius))
            p1 = (int(cx + math.cos(a1) * radius), int(cy + math.sin(a1) * radius))
            try:
                pygame.draw.line(screen, color, p0, p1, 1)
            except (AttributeError, pygame.error):
                return

    def _pick_reserve_type(self) -> str | None:
        """Chọn 1 loại lính còn trong garrison (ưu tiên wave_order)."""
        for t in self.wave_order:
            if self.garrison.get(t, 0) > 0:
                return t
        for t, n in self.garrison.items():
            if n > 0:
                return t
        return None

    def transfer_troops_to(self, target_tower, count: int = 0,
                           spawn_override: tuple | None = None,
                           squads: list = None) -> int:
        """Chuyển `count` SQUAD (hoặc các squad cụ thể trong list `squads`) từ tháp này sang `target_tower`.

        Mỗi squad được MANIFEST thành entity lính thật tại tháp này,
        đặt state=MOVING + _transfer_target=target, đi bộ (né tường) sang
        target. Khi tới phạm vi target → nhập biên chế target (deployed squad).

        `spawn_override`: nếu truyền vào, spawn lính tại điểm này thay vì cạnh
        tháp nguồn — dùng khi 2 tháp cùng 1 tường (spawn phía trong tường để
        tránh kẹt tường).

        Returns: số SQUAD chuyển được thực tế.
        """
        from characters.soldiers.squad import Squad, SQUAD_SIZE
        from systems.world_query import WorldQuery

        if target_tower is None or target_tower is self:
            return 0
            
        if squads is None and count <= 0:
            return 0

        t_radius = getattr(target_tower, 'AGGRO_RADIUS', 600.0)
        target_cap = getattr(target_tower, 'CAPACITY', 8)
        open_slots = target_cap - target_tower.total_garrison()
        
        if open_slots <= 0:
            return 0
            
        if squads is not None:
            squads = squads[:open_slots]
        elif count > 0:
            count = min(count, open_slots)

        def _send(squad) -> None:
            """Đặt squad vào trạng thái MOVING→target và bàn giao cho target."""
            if spawn_override is not None:
                base = spawn_override
            else:
                base = self._safe_spawn_near(target_tower, WorldQuery)
            bx, by = base
            squad._state = "MOVING"
            for s in squad.members:
                if not s.is_alive:
                    continue
                ox, oy = getattr(s, '_slot_offset', (0.0, 0.0))
                s.x, s.y = bx + ox, by + oy
                if WorldQuery.is_wall_blocked(s.x, s.y, 10.0):
                    s.x, s.y = bx, by
                s._state = "MOVING"
                s._transfer_target = target_tower
                s._original_home = (self.x, self.y)
                s._home_pos = (target_tower.x, target_tower.y)
                s._home_radius = t_radius
                s._zones = target_tower.allowed_zones()  # kế thừa vùng tháp đích
            
            self._resolve_stuck_squad(squad, WorldQuery)
            
            for s in squad.members:
                if s.is_alive and s not in WorldQuery._entities:
                    WorldQuery.spawn_entity(s)  # tái xuất nếu đang cất trong tháp
            target_tower._deployed_squads.append(squad)

        moved = 0
        if squads is not None:
            # Transfer các squad cụ thể
            for squad in squads:
                if squad in self._reserve_squads:
                    self._reserve_squads.remove(squad)
                    _send(squad)
                    moved += 1
                elif squad in self._deployed_squads:
                    self._deployed_squads.remove(squad)
                    _send(squad)
                    moved += 1
        else:
            for _ in range(count):
                # 1) Ưu tiên entity reserve có sẵn (lính thật đã ở trong tháp)
                if self._reserve_squads:
                    squad = self._reserve_squads.pop(0)
                    _send(squad)
                    moved += 1
                    continue

                # 2) Hết entity reserve → manifest squad mới từ kho count
                stype = self._pick_reserve_type()
                if stype is None:
                    break
                sizes = self._garrison_sizes.get(stype, [])
                sq_size = sizes.pop(0) if sizes else SQUAD_SIZE
                self.garrison[stype] -= 1
                squad = Squad(stype, (self.x, self.y), None, size=sq_size,
                              home_pos=(target_tower.x, target_tower.y),
                              home_radius=t_radius)
                _send(squad)
                moved += 1

        return moved


# ═══════════════════════════════════════════════════════
#  THÁP CỤ THỂ
# ═══════════════════════════════════════════════════════

class BasicTower(Tower):
    """
    Tháp cơ bản — upgrade 2 giai đoạn.

    Lv1 — single target, dtype normal:
        - Giai đoạn 1: ore orb → +5 damage/orb
        - Damage đạt 60 → _upgrade_ready = True
        - Giai đoạn 2: cần 1 fire_ore → thực sự lên Lv2

    Lv2 — explosive shot (dtype 'fire'):
        - Đạn trúng → nổ trong EXPLOSION_RADIUS
        - Mục tiêu chính + titan trong vùng đều nhận cùng _damage
    """

    MAX_LEVEL         = balance.BASIC_TOWER_MAX_LEVEL
    ORB_FIELD         = 'ore'
    DMG_PER_ORB       = balance.BASIC_TOWER_DMG_PER_ORB
    LV2_DMG_THRESHOLD = balance.BASIC_TOWER_LV2_DMG_THRESHOLD
    EXPLOSION_RADIUS  = balance.BASIC_TOWER_EXPLOSION_RADIUS    # px

    def __init__(self, x: float, y: float):
        """Khởi tạo tháp cơ bản — nạp SẴN 2 badge (lv1/lv2) để đổi ngay khi lên cấp.

        `_upgrade_ready` — cờ "đã đủ damage, chỉ còn thiếu fire_ore để CHỐT cấp
        2" (xem `apply_orb`).
        """
        super().__init__(x, y, config={
            'hp': balance.BASIC_TOWER_HP, 'damage': balance.BASIC_TOWER_DAMAGE, 'range': balance.BASIC_TOWER_RANGE, 'cooldown': balance.BASIC_TOWER_COOLDOWN
        })
        self._upgrade_ready = False
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'base')
        self._badge_lv1 = self._badge_lv2 = None
        try:
            self._badge_lv1 = pygame.image.load(os.path.join(base_dir, 'lv1.png')).convert_alpha()
            self._badge_lv2 = pygame.image.load(os.path.join(base_dir, 'lv2.png')).convert_alpha()
        except Exception as e:
            print("BasicTower badge error:", e)

    def draw(self, screen):
        """Vẽ thân tháp + badge TĨNH (lv1/lv2) — override draw() base để dùng
        badge riêng của BasicTower thay vì `_badge_sprite`/`_badge_anim` chung."""
        img = _get_tower_img()
        rect = img.get_rect(center=(int(self.x), int(self.y)))
        screen.blit(img, rect.topleft)
        badge = self._badge_lv2 if self._level >= 2 else self._badge_lv1
        if badge:
            brect = badge.get_rect(center=(int(self.x), int(self.y) - img.get_height() // 4))
            screen.blit(badge, brect.topleft)

    def can_apply_orb(self) -> bool:
        """True nếu chưa đạt MAX_LEVEL (override giống base, không đổi logic)."""
        return self._level < self.MAX_LEVEL

    def apply_orb(self, amount: int = 1) -> bool:
        """Override HOÀN TOÀN base — nâng cấp 2 GIAI ĐOẠN thay vì 1 bước đơn giản.

        Thuật toán:
          GIAI ĐOẠN 1 (`not _upgrade_ready`): tốn `ore` → `+DMG_PER_ORB` mỗi orb.
              Damage đạt `LV2_DMG_THRESHOLD` (60) → bật `_upgrade_ready = True`
              (nhưng CHƯA lên `_level`).
          GIAI ĐOẠN 2 (`_upgrade_ready`): tốn `fire_ore` (LOẠI KHÁC!) →
              `_level = 2` NGAY (không cần tích luỹ, chỉ cần đủ tài nguyên).
              Từ lúc này `shoot()` chuyển sang bắn đạn NỔ (ExplosiveProjectile).

        Không đủ tài nguyên ở giai đoạn nào → False, không trừ gì.
        Chỉ số: balance.BASIC_TOWER_DMG_PER_ORB / _LV2_DMG_THRESHOLD.
        """
        if not self.can_apply_orb():
            return False
        from structures.buildings.resource_manager import ResourceManager
        from core.game_state import ResourceBundle
        rm = ResourceManager.get_instance()
        if not self._upgrade_ready:
            cost = ResourceBundle(ore=amount)
            if not rm.can_afford(cost):
                return False
            rm.spend(cost)
            # SỬA LỖI: `amount` là GIÁ TIỀN mỗi click (TOWER_ORB_COST, vd 5
            # ore), không phải số đơn vị tiến trình — trước đây nhân thẳng
            # vào damage khiến 1 click vượt LV2_DMG_THRESHOLD (60) ngay lập
            # tức (250 >= 60), sẵn sàng nhảy Giai đoạn 2 chỉ sau 1 lần bấm.
            # Tiến trình damage LUÔN cố định +1 đơn vị mỗi lần bấm thành
            # công, không phụ thuộc giá đắt/rẻ — giống fix ở Tower.apply_orb().
            self._damage += self.DMG_PER_ORB * 1
            if self._damage >= self.LV2_DMG_THRESHOLD:
                self._upgrade_ready = True
        else:
            cost = ResourceBundle(fire_ore=amount)
            if not rm.can_afford(cost):
                return False
            rm.spend(cost)
            self._level = 2
        return True

    def shoot(self, target: IAttackable):
        """Bắn đạn — Lv1 đạn thường (BasicProjectile), Lv2 đạn NỔ (ExplosiveProjectile).

        Chỉ số: balance.BASIC_TOWER_EXPLOSION_RADIUS.
        """
        SoundManager.get_instance().play('normal_tower', self.x, self.y)
        if self._level >= 2:
            return ExplosiveProjectile(
                x=self.x, y=self.y,
                target=target,
                damage=self._damage,
                explosion_radius=self.EXPLOSION_RADIUS,
                shooter=self,
            )
        return BasicProjectile(self.x, self.y, target, self._damage, 'normal',
                               shooter=self)


class ElectricTower(Tower):
    """
    Tháp điện — chain lightning.

    Lv1 (electric_ore, +6 dmg +3 chain_dmg +7px chain_range/orb):
        - Đạn trúng: damage mục tiêu + chain sang titan trong chain_range
        - _damage đạt 120 → lên Lv2

    Lv2 (mở khóa điện trường):
        - Sau khi đạn trúng → spawn ElectricField 5s tại vị trí mục tiêu
    """

    MAX_LEVEL            = balance.ELECTRIC_TOWER_MAX_LEVEL
    ORB_FIELD            = 'electric_ore'
    DMG_PER_ORB          = balance.ELECTRIC_TOWER_DMG_PER_ORB
    CHAIN_DMG_PER_ORB    = balance.ELECTRIC_TOWER_CHAIN_DMG_PER_ORB
    CHAIN_RADIUS_PER_ORB = balance.ELECTRIC_TOWER_CHAIN_RADIUS_PER_ORB
    LV2_DMG_THRESHOLD    = balance.ELECTRIC_TOWER_LV2_DMG_THRESHOLD

    def __init__(self, x: float, y: float):
        """Khởi tạo tháp điện — nạp SẴN 2 animation badge (lv1: 5 frame, lv2: 16
        frame vòng lặp từ frame 8) qua `visual_effects.load_animation_strip`."""
        super().__init__(x, y, config={
            'hp': balance.ELECTRIC_TOWER_HP, 'damage': balance.ELECTRIC_TOWER_DAMAGE, 'range': balance.ELECTRIC_TOWER_RANGE, 'cooldown': balance.ELECTRIC_TOWER_COOLDOWN
        })
        self._chain_damage = balance.ELECTRIC_TOWER_CHAIN_DAMAGE
        self._chain_range  = balance.ELECTRIC_TOWER_CHAIN_RANGE
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'elec')
        self._badge_lv1_anim = self._badge_lv2_anim = None
        try:
            from structures.towers.visual_effects import load_animation_strip
            self._badge_lv1_anim = load_animation_strip(os.path.join(base_dir, 'lv1.png'), 5, fps=30, loop=True)
            self._badge_lv2_anim = load_animation_strip(os.path.join(base_dir, 'lv2.png'), 16, fps=30, loop=True, loop_start_frame=8)
        except Exception as e:
            print("ElectricTower badge error:", e)
        self._badge_anim = self._badge_lv1_anim

    def update(self, dt: float):
        """Đổi badge animation theo cấp TRƯỚC khi gọi `super().update()` (cần
        `_badge_anim` đúng để base tick animation đúng bộ frame)."""
        # Switch badge animation when level changes
        self._badge_anim = self._badge_lv2_anim if self._level >= 2 else self._badge_lv1_anim
        super().update(dt)

    def _on_orb_applied(self, amount: int):
        """Mỗi orb: +damage, +chain damage, +chain range — CẢ 3 stat cùng tăng
        (khác BasicTower chỉ tăng damage)."""
        self._damage       += self.DMG_PER_ORB         * amount
        self._chain_damage += self.CHAIN_DMG_PER_ORB   * amount
        self._chain_range  += self.CHAIN_RADIUS_PER_ORB * amount

    def _check_levelup(self):
        """Lên Lv2 khi damage đạt `LV2_DMG_THRESHOLD` (120) — mở khoá spawn điện trường."""
        if self._level == 1 and self._damage >= self.LV2_DMG_THRESHOLD:
            self._level = 2

    def shoot(self, target: IAttackable) -> ElectricProjectile:
        """Bắn đạn điện — mang theo damage CHÍNH + chain (giật sang titan gần).
        Lv2 (`spawn_field=True`) → đạn trúng còn SPAWN THÊM 1 điện trường 5s."""
        return ElectricProjectile(
            x=self.x, y=self.y,
            target=target,
            damage=self._damage,
            chain_damage=self._chain_damage,
            chain_range=self._chain_range,
            spawn_field=(self._level >= 2),
            level=self._level,
            shooter=self,
        )


class WaterTower(Tower):
    """
    Tháp nước.

    Lv1 — knockback (water_ore, +4 dmg +10px push_radius/orb):
        - Đạn trúng: damage + knockback mục tiêu chính + knockback titan trong push_radius
        - _damage đạt 55 → lên Lv2

    Lv2 — water vortex (cùng orb stat):
        - Đạn trúng: damage + spawn WaterVortex 3s tại vị trí mục tiêu
        - Vortex hút titan xung quanh theo hình xoắn ốc
    """

    MAX_LEVEL         = balance.WATER_TOWER_MAX_LEVEL
    ORB_FIELD         = 'water_ore'
    DMG_PER_ORB       = balance.WATER_TOWER_DMG_PER_ORB
    RADIUS_PER_ORB    = balance.WATER_TOWER_RADIUS_PER_ORB
    LV2_DMG_THRESHOLD = balance.WATER_TOWER_LV2_DMG_THRESHOLD
    PUSH_FORCE        = balance.WATER_TOWER_PUSH_FORCE
    KB_DURATION       = balance.WATER_TOWER_KB_DURATION

    def __init__(self, x: float, y: float):
        """Khởi tạo tháp nước — nạp sheet WaterBall, CẮT LẤY 6 FRAME CUỐI làm badge
        tĩnh lặp lại (không dùng full sheet startup+loop, chỉ giữ phần loop mượt)."""
        super().__init__(x, y, config={
            'hp': balance.WATER_TOWER_HP, 'damage': balance.WATER_TOWER_DAMAGE, 'range': balance.WATER_TOWER_RANGE, 'cooldown': balance.WATER_TOWER_COOLDOWN
        })
        self._push_radius = balance.WATER_TOWER_PUSH_RADIUS
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'water')
        try:
            from structures.towers.visual_effects import load_spritesheet
            anim = load_spritesheet(
                os.path.join(base_dir, 'WaterBall - Startup and Infinite.png'),
                cols=5, rows=5, fps=30, loop=True, loop_start_frame=0
            )
            # Chỉ giữ 6 frame loop cuối làm badge tĩnh
            anim.frames = anim.frames[16:21]
            anim.loop_start_frame = 0
            self._badge_anim = anim
        except Exception as e:
            print("WaterTower badge error:", e)

    def _on_orb_applied(self, amount: int):
        """Mỗi orb: +damage, +bán kính đẩy lùi (`_push_radius`)."""
        self._damage      += self.DMG_PER_ORB    * amount
        self._push_radius += self.RADIUS_PER_ORB * amount

    def shoot(self, target: IAttackable) -> WaterProjectile:
        """Bắn đạn nước — Lv1 knockback mục tiêu chính + titan trong `_push_radius`;
        Lv2 (`vortex_mode=True`) thêm spawn xoáy nước hút titan xung quanh."""
        return WaterProjectile(
            x=self.x, y=self.y,
            target=target,
            damage=self._damage,
            push_radius=self._push_radius,
            push_force=self.PUSH_FORCE,
            kb_duration=self.KB_DURATION,
            vortex_mode=(self._level >= 2),
            shooter=self,
        )


class IceTower(Tower):
    """
    Tháp băng — làm chậm mục tiêu. Orb luôn là ice_ore.

    Lv1 → Lv2 (orb tăng slow_duration):
        - Đạn trúng: damage + apply_slow mục tiêu chính
        - Mỗi orb: +0.5s slow_duration
        - slow_duration đạt 4.0s → lên Lv2

    Lv2 (mở khóa AoE slow, orb tăng slow_factor + splash_radius):
        - Đạn trúng: damage + slow mục tiêu chính + slow titan trong splash_radius
        - Mỗi orb: +0.05 slow_factor, +8px splash_radius
        - slow_factor đạt 0.75 → lên Lv3

    Lv3 (near-freeze):
        - Khi lên Lv3, slow_factor tự boost lên 0.97 (titan còn 3% tốc độ)
        - Không nhận orb thêm
    """

    MAX_LEVEL              = balance.ICE_TOWER_MAX_LEVEL
    ORB_FIELD              = 'ice_ore'
    DURATION_PER_ORB       = balance.ICE_TOWER_DURATION_PER_ORB
    LV2_DURATION_THRESHOLD = balance.ICE_TOWER_LV2_DURATION_THRESHOLD
    SLOW_FACTOR_PER_ORB    = balance.ICE_TOWER_SLOW_FACTOR_PER_ORB
    SPLASH_RADIUS_PER_ORB  = balance.ICE_TOWER_SPLASH_RADIUS_PER_ORB
    LV3_FACTOR_THRESHOLD   = balance.ICE_TOWER_LV3_FACTOR_THRESHOLD

    def __init__(self, x: float, y: float):
        """Khởi tạo tháp băng — 3 CẤP, mỗi cấp nâng theo chỉ số KHÁC nhau (xem `_on_orb_applied`)."""
        super().__init__(x, y, config={
            'hp': balance.ICE_TOWER_HP, 'damage': balance.ICE_TOWER_DAMAGE, 'range': balance.ICE_TOWER_RANGE, 'cooldown': balance.ICE_TOWER_COOLDOWN
        })
        self._slow_duration = balance.ICE_TOWER_SLOW_DURATION
        self._slow_factor   = balance.ICE_TOWER_SLOW_FACTOR
        self._splash_radius = balance.ICE_TOWER_SPLASH_RADIUS
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'ice')
        try:
            from structures.towers.visual_effects import load_animation_strip
            self._badge_anim = load_animation_strip(
                os.path.join(base_dir, 'Ice VFX 1 Repeatable.png'), 10, fps=30, loop=True
            )
        except Exception as e:
            print("IceTower badge error:", e)

    def can_apply_orb(self) -> bool:
        """True nếu chưa max cấp (3) — giống base, override chỉ để rõ ràng."""
        return self._level < self.MAX_LEVEL

    def _on_orb_applied(self, amount: int):
        """Mỗi orb tăng CHỈ SỐ KHÁC NHAU TUỲ CẤP HIỆN TẠI (khác mọi tháp khác —
        đây là tháp DUY NHẤT có 3 cấp với 3 công thức orb riêng biệt):
            Cấp 1 → tăng `_slow_duration` (thời gian làm chậm).
            Cấp 2 → tăng `_slow_factor` (mức độ chậm) VÀ `_splash_radius` (AoE).
            Cấp 3 (max) → không nhận orb nữa (`can_apply_orb` đã chặn).
        """
        if self._level == 1:
            self._slow_duration += self.DURATION_PER_ORB * amount
        elif self._level == 2:
            self._slow_factor   += self.SLOW_FACTOR_PER_ORB   * amount
            self._splash_radius += self.SPLASH_RADIUS_PER_ORB * amount

    def _check_levelup(self):
        """2 ngưỡng lên cấp KHÁC NHAU tuỳ cấp hiện tại:
            Cấp 1→2: `_slow_duration >= LV2_DURATION_THRESHOLD` (4.0s).
            Cấp 2→3: `_slow_factor >= LV3_FACTOR_THRESHOLD` (0.75) — lên cấp 3
                THÌ TỰ ĐỘNG BOOST `_slow_factor` lên `ICE_TOWER_LV3_SLOW_FACTOR`
                (0.97 — gần đóng băng hoàn toàn, titan chỉ còn 3% tốc độ),
                KHÔNG phải giá trị người chơi tích luỹ dừng ở đó.
        """
        if self._level == 1 and self._slow_duration >= self.LV2_DURATION_THRESHOLD:
            self._level = 2
        elif self._level == 2 and self._slow_factor >= self.LV3_FACTOR_THRESHOLD:
            self._level = 3
            self._slow_factor = balance.ICE_TOWER_LV3_SLOW_FACTOR

    def shoot(self, target: IAttackable) -> IceProjectile:
        """Bắn đạn băng — quy đổi `_slow_factor` (tháp: "phần bị xoá" của tốc độ)
        sang `1 - _slow_factor` (titan: "phần TỐC ĐỘ CÒN LẠI"), 2 quy ước ngược
        nhau nên PHẢI ĐỔI DẤU ở đây. Splash chỉ có ở cấp >= 2 (cấp 1 → radius=0)."""
        return IceProjectile(
            x=self.x, y=self.y,
            target=target,
            damage=self._damage,
            slow_factor=1.0 - self._slow_factor,   # convert: tower dùng "phần bị xóa", titan dùng "phần còn lại"
            slow_duration=self._slow_duration,
            splash_radius=self._splash_radius if self._level >= 2 else 0,
            shooter=self,
        )
