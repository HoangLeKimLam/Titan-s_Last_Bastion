# characters/titans/titan.py
"""Toàn bộ tham số + thân xác (sprite/animation) của Titan thường.

Mỗi class Titan = thân xác (file này) + khẩu vị (priority.py) +
đòn đánh (attackstrategy.py) + bộ não (ai.py).

ENTITY_TYPE = 'titan' trên Titan base — WorldQuery dùng để filter.
"""
import os
import math
import random

import pygame
from systems.sound_system import SoundManager


from core.entity import Entity
from core.interfaces import IAttackable, IMovable
from core.event_bus import GameEventBus
from config import balance
from characters.titans.attackstrategy import (
    MeleeRushStrategy,
    HeavyStrikeStrategy,
    ArmoredRamStrategy,
    Incurable,
    TowerHunterStrategy,
    SoldierHunterStrategy,
    Explosion,
)


# ═══════════════════════════════════════════════════════
#  TITAN BASE
# ═══════════════════════════════════════════════════════

class Titan(Entity, IAttackable, IMovable):
    """Cha trừu tượng của mọi Titan.

    Không tạo trực tiếp — chỉ để kế thừa.
    Chứa AI logic cơ bản (`update`/`_find_best_target`) cho chế độ manual.
    Trong game thật, vòng AI được lo bởi `ai.py`.
    """

    ENTITY_TYPE = 'titan'
    IS_LARGE: bool = True

    # ── Tham số mặc định (subclass override) ─────────────────────
    _DEFAULT_HP              = balance.TITAN_HP
    _DEFAULT_SPEED           = balance.TITAN_SPEED
    _DEFAULT_DAMAGE          = balance.TITAN_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.TITAN_ATTACK_RANGE
    _DEFAULT_SOLDIER_ATTACK_RANGE = balance.TITAN_SOLDIER_ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = balance.TITAN_ATTACK_COOLDOWN
    VISUAL_RANGE             = balance.TITAN_VISUAL_RANGE  # Phát hiện soldiers/commanders trong tầm này
    COLLISION_RADIUS         = balance.TITAN_COLLISION_RADIUS   # bán kính thân — dùng cho get_rect() (giẫm đạp)

    def get_rect(self):
        """Hình vuông bao quanh thân titan (tâm x,y, cạnh 2×COLLISION_RADIUS)
        — dùng cho va chạm hình học đơn giản (vd. Building.check_trampling())."""
        import pygame
        r = float(getattr(self, 'COLLISION_RADIUS', 50.0))
        return pygame.Rect(int(self.x - r), int(self.y - r), int(r * 2), int(r * 2))

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo titan với stat lấy từ `config` (ghi đè) hoặc class const (mặc định).

        Thuật toán: mỗi field đọc `cfg.get('key', self._DEFAULT_KEY)` — cho phép
        boss/AI override từng chỉ số riêng lẻ (vd minion Founding truyền
        `{'hp': 280, 'speed': 40, 'damage': 10}`) mà không cần tạo class con mới.

        Tham số:
            config: dict override — khoá hợp lệ: hp, speed, damage, attack_range,
                soldier_attack_range, attack_cooldown, reward. None → dùng toàn bộ
                `_DEFAULT_*` của class.

        Trạng thái khởi tạo thêm:
            `_attack_strategy` — None ban đầu, class con PHẢI gán (vd
                `MeleeRushStrategy()`), nếu không `update()` sẽ crash khi đánh.
            `_slow_*`/`_kb_*` — hiệu ứng slow/knockback do đạn tháp áp lên.
            `_vx`/`_vy` — vận tốc hiện tại, WaterProjectile đọc để tính knockback.

        Chỉ số: balance.<TITAN>_HP/_SPEED/_DAMAGE/_ATTACK_RANGE/_ATTACK_COOLDOWN.
        """
        super().__init__(x, y)
        cfg = config or {}
        self._hp              = int(cfg.get('hp',              self._DEFAULT_HP))
        self._max_hp          = self._hp
        self._speed           = float(cfg.get('speed',         self._DEFAULT_SPEED))
        self._damage          = int(cfg.get('damage',          self._DEFAULT_DAMAGE))
        self._attack_range    = float(cfg.get('attack_range',  self._DEFAULT_ATTACK_RANGE))
        self.SOLDIER_ATTACK_RANGE = float(cfg.get('soldier_attack_range', self._DEFAULT_SOLDIER_ATTACK_RANGE))
        self._attack_cooldown = float(cfg.get('attack_cooldown', self._DEFAULT_ATTACK_COOLDOWN))
        self._reward          = cfg.get('reward', {})

        self._target          = None
        self.bait_target      = None
        self._attack_strategy = None
        self._attack_timer    = 0.0

        # Status effects (applied by tower projectiles)
        self._slow_timer  = 0.0
        self._slow_factor = 1.0   # speed multiplier; 1.0 = bình thường
        self._kb_vx       = 0.0   # knockback velocity x (px/s)
        self._kb_vy       = 0.0   # knockback velocity y (px/s)
        self._kb_timer    = 0.0   # thời gian knockback còn lại

        # Velocity tracking — dùng bởi WaterProjectile._knockback()
        self._vx          = 0.0
        self._vy          = 0.0

    # ─── METHODS BẮT BUỘC (Entity yêu cầu) ─────────────

    def _tick_status(self, dt: float) -> bool:
        """Tick slow/knockback timers. Trả về True nếu đang bị knockback.

        Gọi từ cả Titan.update() (manual mode) lẫn TitanAI.update() (AI mode)
        vì 2 path không overlap nhau.
        """
        if self._slow_timer > 0:
            self._slow_timer = max(0.0, self._slow_timer - dt)
            if self._slow_timer == 0.0:
                self._slow_factor = 1.0
        if self._kb_timer > 0:
            self._kb_timer = max(0.0, self._kb_timer - dt)
            self.x += self._kb_vx * dt
            self.y += self._kb_vy * dt
            return True
        return False

    def update(self, dt: float) -> None:
        """AI cơ bản: tìm target → di chuyển → tấn công (chế độ manual)."""
        if not self.is_alive:
            return

        if self._tick_status(dt):
            return  # bị knockback → không di chuyển tự ý frame này

        self._attack_timer -= dt * self._slow_factor  # Slow affects attack too

        if self._target is None or not self._target.is_alive:
            self._target = self._find_best_target()

        if self._target is not None:
            dist = self._distance_to(self._target)
            if dist > self._attack_range:
                self._move_toward(self._target, dt)
            elif self._attack_timer <= 0:
                self._attack_strategy.execute(self, self._target)
                self._attack_timer = self._attack_cooldown

    def draw(self, screen) -> None:
        """No-op — Titan base KHÔNG tự vẽ. Mọi class con PHẢI override.

        Đây là ABC nên `draw()` không phải `abstractmethod`, nhưng để trống có
        chủ đích: Titan base không có sprite riêng.
        """
        pass

    # ─── IAttackable ─────────────────────────────────────

    def take_damage(self, amount: int, dtype: str, attacker=None) -> None:
        """Nhận damage, xử lý hiệu ứng đặc thù theo `dtype`, và báo AI phản đòn.

        Thuật toán:
          1. Trừ thẳng `amount` khỏi `_hp` — KHÔNG có tính giáp ở đây (giáp do
             ArmoredTitan tự override `take_damage()` riêng).
          2. `dtype == 'suriken'` → áp slow CỨNG (0.3 tốc độ, 2s) — bẫy Suriken
             là nguồn stun/slow DUY NHẤT ngoài tháp Ice.
          3. Có `attacker` → gọi `ai.notify_attacked(attacker)` (qua backref
             `self._ai`) để AI biết "vừa bị ai đánh" → có thể phản đòn.
          4. HP <= 0 → `on_death()`.

        Tham số:
            amount: damage thô (đã tính hệ số ở AttackStrategy, KHÔNG tính lại ở đây).
            dtype: loại damage — hầu hết chỉ dùng để hiển thị/log, trừ 'suriken'.
            attacker: entity gây damage (None nếu damage môi trường, vd bẫy nổ).

        Liên kết: `GameEventBus`; `TitanAI.notify_attacked()`.
        Chỉ số: balance.SURIKEN_TRAP_DAMAGE (bẫy gây damage), slow 0.3/2.0 là số
        cứng CỦA `take_damage()`, không nằm trong balance.py.
        """
        self._hp -= amount

        if dtype == 'suriken':
            self._slow_factor = 0.3
            self._slow_timer  = 2.0

        if attacker is not None:
            ai = getattr(self, '_ai', None)
            if ai is not None:
                ai.notify_attacked(attacker)
        if self._hp <= 0:
            self.on_death()

    def on_death(self) -> None:
        """Titan chết: đánh dấu is_alive=False, phát event, rơi đồ.

        Thuật toán:
          1. `is_alive = False` — game loop sẽ dọn entity này khỏi WorldQuery.
          2. Publish `'titan_died'` kèm `{'titan': self, 'reward': self._reward}`
             — HUD/ResourceManager/WaveManager subscribe để cộng thưởng, cập nhật
             tiến độ wave.
          3. `LootSystem.spawn_loot(self)` — rơi đồ theo `LOOT_TABLE` (loot_system.py),
             tra theo TÊN CLASS titan này.

        ⚠️ KHÔNG được gọi trực tiếp từ bên ngoài — chỉ `take_damage()` (khi HP<=0)
        được phép gọi. Gọi tuỳ tiện sẽ phát trùng event/rơi đồ 2 lần.

        Liên kết: `GameEventBus`, `systems/loot_system.py::LootSystem`.
        """
        self.is_alive = False
        GameEventBus.get_instance().publish(
            'titan_died',
            {'titan': self, 'reward': self._reward},
        )

        # Spawn loot
        try:
            from systems.loot_system import LootSystem
            LootSystem.spawn_loot(self)
        except ImportError:
            pass

    # ─── IMovable ─────────────────────────────────────────

    def move(self, destination: tuple) -> None:
        """Dịch chuyển TỨC THÌ tới `destination` — KHÔNG có animation di chuyển.

        Đây là API cấp thấp của interface `IMovable`. Di chuyển MƯỢT theo tốc độ
        thật (dt-scaled) dùng `_move_toward()`, không phải hàm này.

        Tham số: destination — tuple (x, y).
        """
        self.x, self.y = destination

    # ─── PRIVATE HELPERS ─────────────────────────────────

    def _find_best_target(self):
        """Tìm mục tiêu theo thứ tự ưu tiên mặc định.

        Ưu tiên 1: HQ nếu có thể đi thẳng vào
        Ưu tiên 2: WallSection cản đường
        Ưu tiên 3: Tower/Soldier đang tấn công mình
        Fallback : HQ
        """
        from systems.world_query import WorldQuery
        hq = WorldQuery.get_headquarters()

        if WorldQuery.can_reach_direct(self, hq):
            return hq

        wall = WorldQuery.find_blocking_wall(self, hq)
        if wall:
            return wall

        attacker = WorldQuery.find_nearest_attacker(self)
        if attacker:
            return attacker

        return hq

    def _get_visible_units(self, unit_type: str) -> list:
        """Phát hiện soldiers/commanders trong VISUAL_RANGE."""
        from systems.world_query import WorldQuery

        entity_type_map = {'soldier': 'soldier', 'commander': 'commander', 'tower': 'tower'}
        if unit_type not in entity_type_map:
            return []

        candidates = WorldQuery.find_in_radius(
            self.x, self.y, self.VISUAL_RANGE,
            entity_type=entity_type_map[unit_type]
        )
        # Sort by distance (closest first)
        visible = [(u, (u.x - self.x) ** 2 + (u.y - self.y) ** 2) for u in candidates]
        visible.sort(key=lambda x: x[1])
        return [u[0] for u in visible]

    # ─── Status effects (gọi bởi tower projectiles) ─────

    def apply_slow(self, factor: float, duration: float) -> None:
        """Làm chậm titan: speed *= factor trong `duration` giây.
        Stack theo worst (factor nhỏ nhất) và duration dài nhất.
        """
        self._slow_factor = min(self._slow_factor, max(0.0, factor))
        self._slow_timer  = max(self._slow_timer, duration)

    def apply_knockback(self, vx: float, vy: float, duration: float) -> None:
        """Đẩy titan theo hướng (vx, vy) px/s trong `duration` giây.
        Titan không tự di chuyển trong thời gian bị knockback.
        """
        self._kb_vx    = vx
        self._kb_vy    = vy
        self._kb_timer = max(self._kb_timer, duration)

    def _move_toward(self, target, dt: float) -> None:
        """Tiến 1 bước về `target` với tốc độ thật (đã nhân slow), cập nhật vận tốc.

        Thuật toán: vector đơn vị (dx,dy)/dist × `_speed * _slow_factor` × dt.
        Lưu `_vx/_vy` (dùng bởi `WaterProjectile._knockback()` để biết hướng đang
        di chuyển mà tính lực đẩy).

        Chế độ MANUAL only (khi AI đang chạy, `ai.py::_move()` phức tạp hơn nhiều
        — có né tường, tìm khe hở — được dùng thay).
        """
        dx = target.x - self.x
        dy = target.y - self.y
        dist = (dx**2 + dy**2) ** 0.5
        if dist > 0:
            effective_speed = self._speed * self._slow_factor
            self._vx = (dx / dist) * effective_speed
            self._vy = (dy / dist) * effective_speed
            self.x += self._vx * dt
            self.y += self._vy * dt
        else:
            self._vx = 0.0
            self._vy = 0.0

    def _distance_to(self, target) -> float:
        """Khoảng cách Euclid (px) từ titan này tới `target`."""
        dx = target.x - self.x
        dy = target.y - self.y
        return (dx**2 + dy**2) ** 0.5


# ═══════════════════════════════════════════════════════
#  REGULAR TITAN — Titan cơ bản
# ═══════════════════════════════════════════════════════

class RegularTitan(Titan):
    """Titan cơ bản — đi/chạy/đánh thường. HP < 50% → HeavyStrikeStrategy.

    Visual: spritesheet ngẫu nhiên trong Assets/Titan/regular{2,4,5,6,7}.png.
    Spritesheet (frame 64×64, ánh xạ 0=N, 1=W, 2=S, 3=E):
        Walk   : rows 8-11  — 9 frame
        Run    : rows 38-41 — 8 frame
        Attack : rows 12-15 — 6 frame
    """

    _DEFAULT_HP              = balance.REGULAR_TITAN_HP
    _DEFAULT_SPEED           = balance.REGULAR_TITAN_SPEED
    _DEFAULT_DAMAGE          = balance.REGULAR_TITAN_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.REGULAR_TITAN_ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = balance.REGULAR_TITAN_ATTACK_COOLDOWN

    _HEAVY_HP_RATIO = balance.REGULAR_TITAN_HEAVY_HP_RATIO

    _VARIANTS:    tuple = (2, 4, 5, 6, 7)
    _WALK_ROWS:   dict  = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict  = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS: dict  = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _ATTACK_FRAMES = 6
    _FRAME_SIZE    = 64
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 18
    _DISPLAY_SIZE  = 120   # px — khung 64×64 được scale lên khi render

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo RegularTitan — gắn MeleeRushStrategy + chọn hình dáng ngẫu nhiên.

        `_variant` (2/4/5/6/7) chọn 1 trong 5 file sprite `regular{N}.png` —
        random nếu không truyền `config['variant']`, tạo cảm giác đàn titan
        không đồng phục. Minion do Founding triệu hồi cũng dùng class này với
        `_variant` gán tay (xem `boss.py::_release_summon`).

        `_heavy_mode = False` — cờ một-chiều cho enrage (xem `update()`).
        """
        super().__init__(x, y, config)
        cfg = config or {}
        self._attack_strategy = MeleeRushStrategy()
        self._heavy_mode      = False

        variant = cfg.get('variant')
        self._variant = variant if variant in self._VARIANTS \
            else random.choice(self._VARIANTS)

        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._anim_col          = 0
        self._anim_timer        = 0.0

        self._sprite_sheet = None

    def _load_sprite(self) -> None:
        """Nạp lazy sprite ĐÚNG BIẾN THỂ đã chọn (`regular{_variant}.png`).

        Giống mọi `_load_sprite` khác trong hệ thống: nạp 1 lần, lỗi → None
        (fallback vẽ hình thay thế), không crash.
        """
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Titan', f'regular{self._variant}.png',
            )
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt ô (row, col) khỏi spritesheet — lưới `_FRAME_SIZE` (64px), SRCALPHA."""
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_attack(self) -> None:
        """Bắt đầu animation vung tay (0.33s ở 18fps×6frame). Bỏ qua nếu đang đánh dở."""
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def update(self, dt: float) -> None:
        """Chế độ MANUAL: animation đánh → ENRAGE check → di chuyển/animation đi.

        Thuật toán:
          1. Đang đánh → chỉ chạy animation vung tay, `return` (khoá di chuyển).
          2. `super().update(dt)` — tìm target, di chuyển, tấn công (Titan base).
          3. **ENRAGE**: chưa `_heavy_mode` và `hp/max_hp < _HEAVY_HP_RATIO` (0.5)
             → bật cờ vĩnh viễn + đổi `_attack_strategy` sang HeavyStrike (×3.5).
             (Bản AI-mode của check này nằm ở `ai.py::RegularAI.update()` vì hàm
             này không chạy khi AI hoạt động.)
          4. Đang đi → animation walk/run theo `_is_running`. Đứng yên → frame 0.

        Chỉ số: balance.REGULAR_TITAN_HEAVY_HP_RATIO, balance.STRAT_HEAVY_STRIKE_MULT.
        """
        if self._is_attacking:
            self._attack_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES
            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
            return

        super().update(dt)

        if not self._heavy_mode and self._max_hp > 0 \
                and self._hp / self._max_hp < self._HEAVY_HP_RATIO:
            self._heavy_mode      = True
            self._attack_strategy = HeavyStrikeStrategy()

        if self._is_moving:
            frames = self._RUN_FRAMES if self._is_running else self._WALK_FRAMES
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % frames
        else:
            self._anim_col = 0

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ frame hiện tại, scale lên `_DISPLAY_SIZE` (120px), căn TÂM tại (x, y).

        Chọn hàng: attacking > running > walking. Cột = `_anim_col` khi đang
        đi/đánh, ngược lại 0 (đứng yên). Không có sprite → không vẽ gì (khác boss,
        RegularTitan không có fallback hình khối — đây là hành vi hiện tại, không
        phải cố ý thiết kế).
        """
        self._load_sprite()

        if self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_moving and self._is_running:
            row = self._RUN_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (self._is_moving or self._is_attacking) else 0
        frame = self._get_frame(row, col)

        if frame is not None:
            ds = self._DISPLAY_SIZE
            scaled = pygame.transform.scale(frame, (ds, ds))
            ox = int(self.x - ds // 2)
            oy = int(self.y - ds // 2)
            screen.blit(scaled, (ox, oy))


# ═══════════════════════════════════════════════════════
#  ARMORED TITAN — Titan giáp, Dash + Armor Break
# ═══════════════════════════════════════════════════════

class ArmoredTitan(Titan):
    """Titan giáp — chặn damage thường, Dash húc Wall.

    Cơ chế Dash: trigger_dash() → dash_step() → va chạm → end_dash_on_hit()
    → begin_recoil() → update_dash_cycle() lái toàn bộ vòng Stagger/Recoil.

    Armor break: _ram_hits >= _HITS_TO_BREAK HOẶC _antiarmor_hits >= _HITS_TO_BREAK.
    Vỡ giáp → switch vĩnh viễn sang HeavyStrikeStrategy.
    """

    _DEFAULT_HP              = balance.ARMORED_TITAN_HP
    _DEFAULT_SPEED           = balance.ARMORED_TITAN_SPEED
    _DEFAULT_DAMAGE          = balance.ARMORED_TITAN_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.ARMORED_TITAN_ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = balance.ARMORED_TITAN_ATTACK_COOLDOWN

    ARMOR_REDUCTION  = balance.ARMORED_TITAN_ARMOR_REDUCTION
    _HITS_TO_BREAK   = balance.ARMORED_TITAN_HITS_TO_BREAK
    _DASH_SPEED_MULT = balance.ARMORED_TITAN_DASH_SPEED_MULT
    _DASH_MAX_DIST   = balance.ARMORED_TITAN_DASH_MAX_DIST
    _DASH_HIT_RADIUS = balance.ARMORED_TITAN_DASH_HIT_RADIUS
    _RAM_HIT_RADIUS  = balance.ARMORED_TITAN_RAM_HIT_RADIUS   # 55px → sprite half=60 → 5px overlap = "chạm tường"
    _STAGGER_DURATION = balance.ARMORED_TITAN_STAGGER_DURATION
    _RECOIL_DIST     = balance.ARMORED_TITAN_RECOIL_DIST

    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _DASH_ROWS:   dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _DASH_FRAMES   = 8
    _ATTACK_FRAMES = 6
    _FRAME_SIZE    = 64
    _DISPLAY_SIZE  = 120
    _ANIM_FPS      = 10
    _DASH_FPS      = 18
    _ATTACK_FPS    = 18
    _wall_radius   = 58   # > attack_range+t_rad(40+16=56) để _on_decide trigger dash

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo ArmoredTitan — gắn ArmoredRamStrategy + toàn bộ state Dash/Stagger/Recoil.

        Nhóm state chính:
          `_armor_intact` — True = còn giáp (đòn ×6.7 'ram'); vỡ → False vĩnh viễn,
              đổi hẳn sang HeavyStrikeStrategy.
          `_ram_hits` / `_antiarmor_hits` — 2 bộ đếm riêng, đạt `_HITS_TO_BREAK` (25)
              CÁI NÀO TRƯỚC là vỡ giáp cái đó (húc tường 25 lần HOẶC ăn 25 đòn xuyên giáp).
          `_is_dashing` + `_dash_*` — trạng thái LAO HÚC (xem `trigger_dash`).
          `_stagger_timer` + `_recoil_*` — trạng thái SAU cú húc (choáng rồi lùi lại).

        `_wall_radius = 58` (KHÔNG lấy từ balance) — cố ý LỚN HƠN
        `attack_range + t_rad` (40+16=56px) để `ArmoredAI._on_decide()` luôn kích
        được dash trước khi vào tầm đánh thường.
        """
        super().__init__(x, y, config)
        self._attack_strategy = ArmoredRamStrategy()
        self._armor_intact    = True

        self._ram_hits        = 0
        self._antiarmor_hits  = 0
        self._break_cause     = ''

        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._anim_col          = 0
        self._anim_timer        = 0.0

        self._is_dashing          = False
        self._dash_target         = None  # wall section đang nhắm khi dash
        self._dash_dx             = 0.0
        self._dash_dy             = 0.0
        self._dash_dist_remaining = 0.0
        self._dash_speed          = 0.0

        self._is_attacking      = False
        self._attack_anim_timer = 0.0

        self._stagger_timer    = 0.0
        self._recoil_dist_left = 0.0
        self._recoil_dx        = 0.0
        self._recoil_dy        = 0.0

        self._sprite_sheet = None

    def _load_sprite(self) -> None:
        """Nạp lazy `Assets/Special/armored.png`. Lỗi → None (fallback vẽ hình)."""
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Special', 'armored.png')
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt ô (row, col) khỏi spritesheet — lưới `_FRAME_SIZE` (64px), SRCALPHA."""
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_dash(self, dx: float, dy: float, run_speed: float,
                     dash_target=None) -> bool:
        """BẮT ĐẦU cú lao húc — bước 1 trong chuỗi Dash→Hit→Stagger→Recoil.

        3 điều kiện từ chối (trả False):
          1. Đang dash/đang đánh dở.
          2. Giáp đã vỡ (`not _armor_intact`) — húc chỉ khi còn giáp.
          3. Vector hướng (dx,dy) độ dài 0.

        Thuật toán:
          1. Chuẩn hoá (dx,dy) thành vector đơn vị `_dash_dx/_dash_dy`.
          2. `_dash_dist_remaining = _DASH_MAX_DIST` (300px) — quãng đường tối đa
             sẽ lao, TRỪ KHI va chạm trước (xem `dash_step`).
          3. `_dash_speed = run_speed × _DASH_SPEED_MULT` (×3.0) — lao NHANH GẤP 3
             tốc độ đi bộ thường.
          4. Nhớ `_dash_target` (đoạn tường đang nhắm) — dùng làm `exclude` trong
             `ai.py::_dash_chk` để không tự chặn chính mình.
          5. `_dash_hit_entities = set()` — chống húc trúng CÙNG 1 entity 2 lần
             trong 1 cú lao.
          6. Xoay mặt theo hướng lao (so |dx| vs |dy|).

        Tham số: dx, dy — vector hướng (chưa chuẩn hoá); run_speed — tốc độ đi bộ
            gốc (đã nhân slow_factor từ caller); dash_target — mục tiêu nhắm.
        Trả về: bool — True = bắt đầu lao được.
        Chỉ số: balance.ARMORED_TITAN_DASH_MAX_DIST / _DASH_SPEED_MULT.
        """
        if self._is_dashing or self._is_attacking:
            return False
        if not self._armor_intact:
            return False
        mag = (dx * dx + dy * dy) ** 0.5
        if mag <= 0:
            return False

        self._dash_dx             = dx / mag
        self._dash_dy             = dy / mag
        self._dash_dist_remaining = self._DASH_MAX_DIST
        self._dash_speed          = run_speed * self._DASH_SPEED_MULT
        self._is_dashing          = True
        self._dash_target         = dash_target  # nhớ ai đang bị nhắm
        self._dash_hit_entities   = set()        # nhớ ai đã bị húc bay để không húc 2 lần 1 nhịp dash
        self._anim_col            = 0
        self._anim_timer          = 0.0

        if abs(self._dash_dx) > abs(self._dash_dy):
            self._direction = 3 if self._dash_dx > 0 else 1
        else:
            self._direction = 2 if self._dash_dy > 0 else 0
        return True

    def dash_step(self, dt: float, world_bounds: tuple = None) -> tuple:
        """Tiến 1 bước trong cú lao húc, trả vị trí MỚI (chưa commit) + đã xong chưa.

        Thuật toán:
          1. Không đang dash → trả nguyên vị trí hiện tại, `finished=True`.
          2. `step = _dash_speed × dt × _slow_factor` — dính IceTower thì lao chậm hơn.
          3. Kẹp `step` không vượt quá `_dash_dist_remaining` (không lao quá đích).
          4. Tính `new_x/new_y`, kẹp trong `world_bounds` nếu có (biên bản đồ).
          5. `finished = (dist_remaining <= 0)` — hết quãng đường mà CHƯA va chạm gì
             (húc trượt, không trúng tường) → tự tắt `_is_dashing`, reset animation.

        QUAN TRỌNG: hàm này KHÔNG tự gán `self.x/self.y` — chỉ TRẢ VỀ toạ độ đề
        xuất. Caller (`ai.py::update_dash_cycle` phía titan) tự kiểm tra va chạm
        (`wall_check`) rồi mới quyết định commit hay gọi `end_dash_on_hit()`.

        Tham số: dt; world_bounds — (min_x, min_y, max_x, max_y) tuỳ chọn.
        Trả về: tuple (new_x, new_y, finished).
        Chỉ số: balance.ARMORED_TITAN_DASH_MAX_DIST.
        """
        if not self._is_dashing:
            return self.x, self.y, True

        step = self._dash_speed * dt * self._slow_factor  # Apply slow to dash
        if step >= self._dash_dist_remaining:
            step = self._dash_dist_remaining
            self._dash_dist_remaining = 0.0
        else:
            self._dash_dist_remaining -= step

        new_x = self.x + self._dash_dx * step
        new_y = self.y + self._dash_dy * step

        if world_bounds is not None:
            min_x, min_y, max_x, max_y = world_bounds
            new_x = max(min_x, min(max_x, new_x))
            new_y = max(min_y, min(max_y, new_y))

        finished = (self._dash_dist_remaining <= 0)
        if finished:
            self._is_dashing = False
            self._anim_col   = 0
            self._anim_timer = 0.0
        return new_x, new_y, finished

    def end_dash_on_hit(self, target) -> tuple:
        """VA CHẠM: dừng dash, áp damage 'ram', và kiểm tra VỠ GIÁP.

        Không `return` sớm khi `_is_dashing` đã False — trường hợp dash vừa hết
        đúng 300px CÙNG LÚC AABB chạm tường (≤55px) vẫn phải tính damage, không
        được bỏ qua ("phantom recoil": tưởng chỉ là lết tới nơi nhưng thực ra vừa
        húc trúng).

        Thuật toán:
          1. Tắt `_is_dashing`, reset animation.
          2. `strategy.execute(self, target)` — ArmoredRamStrategy áp damage ×6.7,
             dtype='ram' (×3 sát thương lên tường theo dtype này).
          3. Còn giáp → `_ram_hits += 1`. Đạt `_HITS_TO_BREAK` (25) → `_break_armor
             (cause='ram')`.

        Tham số: target — thứ vừa bị húc trúng (thường là WallSection).
        Trả về: tuple (đã_vỡ_giáp: bool, nguyên_nhân: str) — dùng bởi caller để
            biết có cần chuyển sang animation vỡ giáp không.
        Chỉ số: balance.STRAT_ARMORED_RAM_MULT, balance.ARMORED_TITAN_HITS_TO_BREAK.
        """
        # Không return sớm khi _is_dashing=False: trường hợp 300px hết đúng frame AABB≤55
        # vẫn phải deal damage (không phải phantom recoil).
        strategy = self._attack_strategy
        self._is_dashing          = False
        self._dash_dist_remaining = 0.0
        self._anim_col            = 0
        self._anim_timer          = 0.0

        if strategy is not None:
            strategy.execute(self, target)

        if self._armor_intact:
            self._ram_hits += 1
            if self._ram_hits >= self._HITS_TO_BREAK:
                self._break_armor(cause='ram')
                return True, 'ram'
        return False, ''

    def _break_armor(self, cause: str) -> None:
        """VỠ GIÁP VĨNH VIỄN — đổi strategy, huỷ dash dở, và ĐẨY titan RA KHỎI tường.

        Thuật toán:
          1. Đã vỡ rồi → thoát (chỉ vỡ 1 lần).
          2. `_armor_intact = False`, ghi `_break_cause` (log/debug: 'ram' hoặc
             'antiarmor'), đổi HẲN `_attack_strategy` sang HeavyStrike.
          3. Đang dash dở → huỷ ngay (không được lao tiếp khi đã hết giáp).
          4. **ĐẨY RA KHỎI TƯỜNG** (fix bug "đứng yên như tượng"): sau khi giáp vỡ,
             titan thường đang NẰM TRONG collision zone của đoạn tường vừa húc
             (khoảng cách có thể chỉ ~42px < `_wall_radius` 50px). Nếu không đẩy
             ra ngay, `follow_path` bị chặn MỌI HƯỚNG → titan kẹt cứng, chỉ còn
             cách đập đúng đoạn tường đó mỗi 1.5s qua `_break_blocking_wall` →
             trông như đứng yên hoàn toàn không làm gì.
             Cách đẩy: với MỌI tường còn sống, tính điểm gần nhất trên hình chữ
             nhật 32×32 của nó; nếu titan cách điểm đó < `_wall_radius+1` thì đẩy
             titan RA THEO HƯỚNG NGƯỢC LẠI đúng phần overlap còn thiếu.

        Tham số: cause — chuỗi mô tả nguyên nhân vỡ giáp ('ram' hoặc 'antiarmor').
        Chỉ số: balance.ARMORED_TITAN_RAM_HIT_RADIUS (kích hoạt qua `_wall_radius`).
        """
        if not self._armor_intact:
            return
        self._armor_intact    = False
        self._break_cause     = cause
        self._attack_strategy = HeavyStrikeStrategy()
        if self._is_dashing:
            self._is_dashing          = False
            self._dash_dist_remaining = 0.0
            self._anim_col            = 0
            self._anim_timer          = 0.0
        self._dash_target = None
        # Sau khi giáp vỡ, titan thường nằm trong collision zone của section kề tiếp theo
        # (vd: D ở 42px < wall_radius=50). follow_path bị blocked mọi hướng → titan kẹt,
        # chỉ đánh D qua _break_blocking_wall mỗi 1.5s → trông như đứng yên hoàn toàn.
        # Fix: đẩy titan ra ngoài AABB+wall_radius của mọi section đang alive, ngay lúc này.
        try:
            import math as _m
            from systems.world_query import WorldQuery as _WQ
            _r = float(getattr(self, '_wall_radius', 50.0)) + 1.0
            for _w in _WQ._f_walls:
                _nx = max(float(_w.x), min(self.x, float(_w.x) + 32.0))
                _ny = max(float(_w.y), min(self.y, float(_w.y) + 32.0))
                _dx, _dy = self.x - _nx, self.y - _ny
                _d = _m.hypot(_dx, _dy)
                if 0.0 < _d < _r:
                    _push = _r - _d
                    self.x += _dx / _d * _push
                    self.y += _dy / _d * _push
        except Exception:
            pass

    def _aabb_dist_to_wall(self, ws) -> float:
        """Khoảng cách từ tâm titan tới HÌNH CHỮ NHẬT 32×32 của đoạn tường (không phải tới tâm).

        Thuật toán: kẹp toạ độ titan vào biên rect (AABB) để tìm điểm GẦN NHẤT
        trên rect, rồi đo khoảng cách Euclid từ titan tới điểm đó. Đứng cạnh
        MÉP tường thì khoảng cách gần 0, dù tâm 2 bên cách nhau tới ~23px.

        Chính xác hơn nhiều so với đo tâm-đến-tâm khi kiểm tra "có đang chạm tường không".
        """
        rx, ry = float(ws.x), float(ws.y)
        near_x = max(rx, min(self.x, rx + 32.0))
        near_y = max(ry, min(self.y, ry + 32.0))
        dx = self.x - near_x
        dy = self.y - near_y
        return (dx * dx + dy * dy) ** 0.5

    def begin_recoil(self, wall) -> None:
        """Bắt đầu pha STAGGER (choáng) rồi RECOIL (lùi lại) sau khi húc trúng tường.

        Thuật toán tính HƯỚNG lùi (điểm hay nhất):
          Hướng = vector từ titan → ĐIỂM GẦN NHẤT trên hình chữ nhật 32×32 của
          `wall`, rồi ĐẢO NGƯỢC hướng đó (thực chất `dx,dy = titan - near_point`
          nghĩa là "lùi ra xa điểm chạm", không phải "đi vào").
          Dùng AABB thay vì góc/tâm section: đảm bảo lùi ĐÚNG HƯỚNG dù húc từ bất
          kỳ phía nào (đặc biệt hướng NAM, nơi công thức góc-đơn giản hay sai).

          Trường hợp biên: titan center NẰM TRONG chính AABB đó (d<=0) → dùng
          hướng từ TÂM section thay thế. Cả 2 đều fail (d vẫn <=0, rất hiếm) →
          fallback hướng Tây (-1, 0) để không chia cho 0.

        Sau khi tính hướng: nạp `_recoil_dist_left = _RECOIL_DIST` (120px) và
        `_stagger_timer = _STAGGER_DURATION` (0.3s) — STAGGER LUÔN CHẠY TRƯỚC
        RECOIL (xem thứ tự if trong `update_dash_cycle`).

        Tham số: wall — đoạn tường vừa húc trúng (nguồn tính hướng lùi).
        Chỉ số: balance.ARMORED_TITAN_RECOIL_DIST / _STAGGER_DURATION.
        """
        # Hướng recoil = titan → ĐIỂM GẦN NHẤT trên AABB của wall section.
        # Dùng AABB thay vì corner giúp recoil đúng hướng từ mọi phía (đặc biệt phía nam).
        rx, ry = float(wall.x), float(wall.y)
        near_x = max(rx, min(self.x, rx + 32.0))
        near_y = max(ry, min(self.y, ry + 32.0))
        dx = self.x - near_x
        dy = self.y - near_y
        d  = (dx * dx + dy * dy) ** 0.5
        if d <= 0:
            # Titan center nằm trong AABB → dùng hướng từ tâm section
            dx = self.x - (rx + 16.0)
            dy = self.y - (ry + 16.0)
            d  = (dx * dx + dy * dy) ** 0.5
            if d <= 0:
                dx, dy, d = -1.0, 0.0, 1.0
        self._recoil_dx        = dx / d
        self._recoil_dy        = dy / d
        self._recoil_dist_left = self._RECOIL_DIST
        self._stagger_timer    = self._STAGGER_DURATION

    def update_dash_cycle(self, dt: float,
                          wall_check=None, recoil_check=None) -> str:
        """BỘ NÃO VẬT LÝ của toàn bộ chuỗi Dash→Hit→Stagger→Recoil, 1 frame/lần.

        Đây là hàm TRUNG TÂM: `ai.py::ArmoredAI.update()` gọi hàm này MỖI FRAME
        và hoàn toàn tuân theo giá trị trả về (thân xác tự lái, AI chỉ cung cấp
        2 hàm kiểm tra va chạm).

        Thứ tự ưu tiên (if-elif, cái nào đúng trước thì chạy, các cái sau bị bỏ qua):

        1. **STAGGER** (`_stagger_timer > 0`): đứng khựng lại sau cú húc, không di
           chuyển. Đếm ngược timer. Trả `'stagger'`.

        2. **RECOIL** (`_recoil_dist_left > 0`): lùi lại theo `_recoil_dx/dy` với
           tốc độ THƯỜNG (`_speed`, KHÔNG nhân dash mult). Mỗi bước gọi
           `recoil_check(nx, ny)` — bị chặn (có tường phía sau) → DỪNG RECOIL SỚM
           (`_recoil_dist_left = 0`) thay vì crash hay xuyên tường. Xoay mặt theo
           hướng lùi. Trả `'recoil'`.

        3. **DASH** (`_is_dashing`): đang lao.
           a. `dash_step()` tính vị trí đề xuất (new_x, new_y).
           b. Target đã chết/None (`not _wt_alive`) → dùng `wall_check(new_x, new_y)`
              để KHÔNG cho lao xuyên tường KHÁC một cách vô định (target ban đầu
              đã mất, không còn "cái cớ" để xuyên qua nữa). Bị chặn → huỷ dash
              ngay, trả `'dash'` (frame cuối của dash).
           c. Target còn sống → **BỎ QUA `wall_check`** — vì các đoạn tường KỀ
              BÊN hay bị AABB-overlap sai dẫn tới block giả; `end_dash_on_hit()`
              (bước e) tự lo việc dừng đúng chỗ dựa trên khoảng cách thật.
           d. Commit vị trí mới. **Húc bay lính/tướng dọc đường**: quét bán kính
              `_DASH_HIT_RADIUS` (18px) quanh vị trí mới, mọi soldier/commander
              CHƯA nằm trong `_dash_hit_entities` (chống húc 1 người 2 lần/1 lượt
              dash) ăn damage `_DEFAULT_DAMAGE` dtype='heavy' — đây là sát thương
              PHỤ, KHÔNG qua AttackStrategy.
           e. Đã tới đủ gần tường mục tiêu (`_aabb_dist_to_wall <= _RAM_HIT_RADIUS`
              = 55px) → `end_dash_on_hit()` (áp damage 'ram' thật + kiểm tra vỡ
              giáp) rồi LUÔN `begin_recoil()` — VỠ GIÁP hay KHÔNG đều phải recoil
              (vỡ giáp cũng cần thoát khỏi collision zone của tường). Trả `'dash'`.

        4. **IDLE**: không ở trạng thái nào trên → trả `'idle'` (AI được tự do
           quyết định: đi tới hoặc kích dash mới qua `_on_decide`).

        Tham số:
            dt: giây từ frame trước.
            wall_check(nx, ny) -> bool: callback AI, dùng CHỈ KHI `_dash_target`
                đã chết/None — ngăn lao vô định qua tường khác.
            recoil_check(nx, ny) -> bool: callback AI, ngăn lùi xuyên tường phía
                sau; đã `exclude` sẵn cụm tường vừa húc để không tự chặn chính mình.

        Trả về: str — 'stagger' | 'recoil' | 'dash' | 'idle'.
        Chỉ số: balance.ARMORED_TITAN_DASH_HIT_RADIUS / _RAM_HIT_RADIUS /
        _RECOIL_DIST / _STAGGER_DURATION.
        """
        if self._stagger_timer > 0.0:
            self._stagger_timer -= dt
            self._is_moving  = False
            self._is_running = False
            return 'stagger'

        if self._recoil_dist_left > 0.0:
            step = min(self._speed * dt, self._recoil_dist_left)
            nx = self.x + self._recoil_dx * step
            ny = self.y + self._recoil_dy * step
            if recoil_check is None or not recoil_check(nx, ny):
                self._recoil_dist_left -= step
                self.x, self.y = nx, ny
            else:
                self._recoil_dist_left = 0.0  # tường sau lưng — dừng recoil sớm
            self._is_moving  = True
            self._is_running = False
            if abs(self._recoil_dx) >= abs(self._recoil_dy):
                self._direction = 3 if self._recoil_dx > 0 else 1
            else:
                self._direction = 2 if self._recoil_dy > 0 else 0
            return 'recoil'

        if self._is_dashing:
            new_x, new_y, _finished = self.dash_step(dt)
            _wt       = self._dash_target
            _wt_alive = _wt is not None and getattr(_wt, 'is_alive', False)

            if not _wt_alive:
                # Target đã chết / không có — dùng wall_check để ngăn xuyên tường vô định
                if wall_check is not None and wall_check(new_x, new_y):
                    self._is_dashing          = False
                    self._dash_dist_remaining = 0.0
                    self._anim_col            = 0
                    self._anim_timer          = 0.0
                    return 'dash'

            # Apply vị trí (target còn sống: wall_check bỏ qua — adjacent sections
            # hay bị block sai do AABB overlap; end_dash_on_hit tự dừng đúng chỗ)
            self.x, self.y = new_x, new_y
            self._is_moving = True

            # THÊM MỚI: Húc bay lính và tướng trên đường Dash
            from systems.world_query import WorldQuery
            _hit_rad = getattr(self, '_DASH_HIT_RADIUS', 18.0)
            _dash_targets = WorldQuery.find_in_radius(self.x, self.y, _hit_rad, 'soldier') + \
                            WorldQuery.find_in_radius(self.x, self.y, _hit_rad, 'commander')
            for _tgt in _dash_targets:
                if getattr(_tgt, 'is_alive', False) and _tgt not in getattr(self, '_dash_hit_entities', set()):
                    _tgt.take_damage(amount=self._DEFAULT_DAMAGE, dtype='heavy')
                    if not hasattr(self, '_dash_hit_entities'):
                        self._dash_hit_entities = set()
                    self._dash_hit_entities.add(_tgt)

            if _wt_alive and self._aabb_dist_to_wall(_wt) <= self._RAM_HIT_RADIUS:
                broke, _cause = self.end_dash_on_hit(_wt)
                if broke:
                    # Giáp vỡ → vẫn recoil để thoát collision zone, rồi BTH mode
                    self.begin_recoil(_wt)
                    return 'recoil'
                if self._armor_intact:
                    # Luôn recoil sau khi húc dù wall còn sống hay đã chết
                    # (bỏ check is_alive — wall chết titan vẫn cần bounce về đúng vị trí)
                    self.begin_recoil(_wt)
            return 'dash'

        return 'idle'

    def trigger_attack(self) -> bool:
        """Bắt đầu animation đánh thường (chỉ khi KHÔNG đang đánh dở/đang dash).

        Dùng khi giáp đã vỡ (đánh thường thay vì húc) hoặc còn giáp mà đủ gần
        để đánh mà không cần lấy đà húc.

        Trả về: bool — True = bắt đầu được.
        """
        if self._is_attacking or self._is_dashing:
            return False
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0
        return True

    def update_anim(self, dt: float) -> None:
        """Máy trạng thái animation — ƯU TIÊN: đánh > dash > đi > đứng yên.

        Mỗi nhánh dùng fps/frame-count riêng: `_ATTACK_FPS`/`_ATTACK_FRAMES` khi
        đánh, `_DASH_FPS`/`_DASH_FRAMES` khi lao, `_ANIM_FPS` + (`_RUN_FRAMES` hay
        `_WALK_FRAMES` tuỳ `_is_running`) khi đi. Hết animation đánh → tự tắt cờ,
        reset frame 0. Đứng yên → reset frame 0.

        Gọi bởi AI (`ai.py::_advance_animation`) mỗi frame khi AI đang điều khiển.
        """
        if self._is_attacking:
            self._attack_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES
            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
                self._anim_timer   = 0.0
        elif self._is_dashing:
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._DASH_FPS:
                self._anim_timer -= 1.0 / self._DASH_FPS
                self._anim_col = (self._anim_col + 1) % self._DASH_FRAMES
        elif self._is_moving:
            frames = self._RUN_FRAMES if self._is_running else self._WALK_FRAMES
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % frames
        else:
            self._anim_col   = 0
            self._anim_timer = 0.0

    def take_damage(self, amount: int, dtype: str, attacker=None) -> None:
        """Nhận damage — CÒN GIÁP thì giảm mạnh (trừ đòn xuyên giáp), VỠ GIÁP thì ăn đủ.

        Thuật toán tính `actual` (damage thật sự trừ HP):
            Còn giáp + dtype == 'anti_armor' → ăn ĐỦ `amount` (giáp không chặn
                được đòn xuyên giáp), CỘNG THÊM `_antiarmor_hits += 1` → đạt
                `_HITS_TO_BREAK` thì `_break_armor(cause='anti_armor')`.
                (Đây là con đường VỠ GIÁP THỨ 2, song song với húc tường 25 lần.)
            Còn giáp + dtype khác   → `amount × (1 - ARMOR_REDUCTION)` — giảm 70%
                (ARMOR_REDUCTION = 0.7) mọi damage KHÔNG PHẢI xuyên giáp.
            Vỡ giáp                 → ăn đủ `amount`, không giảm.

        `dtype == 'suriken'` áp slow (0.3×, 2s) giống `Titan.take_damage()` gốc.

        Tham số: amount, dtype, attacker — giống chữ ký `Titan.take_damage()`.
        Chỉ số: balance.ARMORED_TITAN_ARMOR_REDUCTION, balance.ARMORED_TITAN_HITS_TO_BREAK.
        """
        if self._armor_intact:
            if dtype == 'anti_armor':
                actual = amount
                self._antiarmor_hits += 1
                if self._antiarmor_hits >= self._HITS_TO_BREAK:
                    self._break_armor(cause='anti_armor')
            else:
                actual = int(amount * (1 - self.ARMOR_REDUCTION))
        else:
            actual = amount

        self._hp -= actual
        
        if dtype == 'suriken':
            self._slow_factor = 0.3
            self._slow_timer  = 2.0
            
        # Báo AI biết kẻ tấn công (đồng nhất với Titan.take_damage)
        if attacker is not None:
            ai = getattr(self, '_ai', None)
            if ai is not None:
                ai.notify_attacked(attacker)
        if self._hp <= 0:
            self.on_death()

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ frame theo trạng thái: attacking > dashing > running > walking.

        Cùng công thức scale/vị trí như RegularTitan (`_DISPLAY_SIZE`, căn tâm).
        Cột = `_anim_col` khi đang đi/dash/đánh, ngược lại 0.
        """
        self._load_sprite()

        if self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_dashing:
            row = self._DASH_ROWS[self._direction]
        elif self._is_moving and self._is_running:
            row = self._RUN_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (
            self._is_moving or self._is_dashing or self._is_attacking) else 0
        frame = self._get_frame(row, col)

        if frame is not None:
            ds = self._DISPLAY_SIZE
            scaled = pygame.transform.scale(frame, (ds, ds))
            ox = int(self.x - ds // 2)
            oy = int(self.y - ds // 2)
            screen.blit(scaled, (ox, oy))


# ═══════════════════════════════════════════════════════
#  WOLF TITAN
# ═══════════════════════════════════════════════════════

class Wolf(Titan):
    """Titan thân nhỏ — cắn chặn hồi máu (dtype='antiheal')."""

    _DEFAULT_HP              = balance.WOLF_HP
    _DEFAULT_SPEED           = balance.WOLF_SPEED
    _DEFAULT_DAMAGE          = balance.WOLF_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.WOLF_ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = balance.WOLF_ATTACK_COOLDOWN

    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _ATTACK_FRAMES = 6
    _FRAME_SIZE    = 64
    _DISPLAY_SIZE  = 120
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 18
    _SPRITE_FILE   = 'wolf.png'

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo Wolf — gắn `Incurable` (đòn cắn dtype='antiheal').

        Damage thấp hơn các titan cùng cấp nhưng đòn cắn CHẶN HỒI MÁU mục tiêu
        (xem `attackstrategy.py::Incurable`). Kết hợp `WolfPriority` (ưu tiên
        phản đòn tướng) → chuyên gia "khắc chế" tướng người chơi.
        """
        super().__init__(x, y, config)
        self._attack_strategy = Incurable()
        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._anim_col          = 0
        self._anim_timer        = 0.0
        self._sprite_sheet = None

    def _load_sprite(self) -> None:
        """Nạp lazy `Assets/Titan/wolf.png`. Lỗi → None (fallback không vẽ gì)."""
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Titan', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt ô (row, col) khỏi spritesheet — lưới `_FRAME_SIZE` (64px), SRCALPHA."""
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_attack(self) -> None:
        """Bắt đầu animation cắn (0.33s). Bỏ qua nếu đang cắn dở."""
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def update_anim(self, dt: float) -> None:
        """Máy trạng thái animation: đánh > đi (walk/run) > đứng yên.

        Giống hệt mẫu chung của titan thường (RegularTitan) — hết animation đánh
        thì tự tắt cờ và reset frame.
        """
        if self._is_attacking:
            self._attack_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES
            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
                self._anim_timer   = 0.0
        elif self._is_moving:
            frames = self._RUN_FRAMES if self._is_running else self._WALK_FRAMES
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % frames
        else:
            self._anim_col   = 0
            self._anim_timer = 0.0

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ frame theo trạng thái (attacking > running > walking), scale + căn tâm."""
        self._load_sprite()
        if self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_moving and self._is_running:
            row = self._RUN_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]
        col = self._anim_col if (self._is_moving or self._is_attacking) else 0
        frame = self._get_frame(row, col)
        if frame is not None:
            ds = self._DISPLAY_SIZE
            scaled = pygame.transform.scale(frame, (ds, ds))
            screen.blit(scaled, (int(self.x - ds // 2), int(self.y - ds // 2)))


# ═══════════════════════════════════════════════════════
#  TOWER HUNTER TITAN
# ═══════════════════════════════════════════════════════

class TowerHunter(Titan):
    """Titan công thành — chuyên phá Tower.

    Switch strategy: target là Tower → TowerHunterStrategy (×1.5 siege),
    target khác → HeavyStrikeStrategy.
    """

    _DEFAULT_HP              = balance.TOWER_HUNTER_HP
    _DEFAULT_SPEED           = balance.TOWER_HUNTER_SPEED
    _DEFAULT_DAMAGE          = balance.TOWER_HUNTER_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.TOWER_HUNTER_ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = balance.TOWER_HUNTER_ATTACK_COOLDOWN

    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _ATTACK_FRAMES = 6
    _FRAME_SIZE    = 64
    _DISPLAY_SIZE  = 120
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 18
    _SPRITE_FILE   = 'towerhunter.png'

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo TowerHunter — giữ SẴN 2 strategy để hoán theo mục tiêu.

        `_heavy_strategy` (HeavyStrike, mặc định) và `_siege_strategy`
        (TowerHunterStrategy, ×1.5 khi trúng Tower) được tạo SẴN 1 lần, rồi
        `update()` (chế độ manual) hoặc `ai.py::TowerHunterAI` (chế độ AI) chỉ
        HOÁN CON TRỎ `_attack_strategy` chứ không tạo mới mỗi frame.
        """
        super().__init__(x, y, config)
        self._heavy_strategy  = HeavyStrikeStrategy()
        self._siege_strategy  = TowerHunterStrategy()
        self._attack_strategy = self._heavy_strategy

        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._anim_col          = 0
        self._anim_timer        = 0.0
        self._sprite_sheet = None

    def update(self, dt: float) -> None:
        """Chế độ MANUAL: hoán strategy theo mục tiêu HIỆN TẠI rồi chạy update chuẩn.

        Mục tiêu là Tower (so `ENTITY_TYPE`, KHÔNG `isinstance` — tránh vòng lặp
        import) → dùng `_siege_strategy`; còn lại → `_heavy_strategy`.

        (Bản AI-mode của hoán này nằm ở `ai.py::TowerHunterAI._act_in_range()` vì
        hàm này không chạy khi AI hoạt động.)
        """
        target = getattr(self, '_target', None)
        # Dùng ENTITY_TYPE (uppercase) để đồng bộ với hệ thống chính
        if target is not None and getattr(target, 'ENTITY_TYPE', '') == 'tower':
            self._attack_strategy = self._siege_strategy
        else:
            self._attack_strategy = self._heavy_strategy
        super().update(dt)

    def _load_sprite(self) -> None:
        """Nạp lazy `Assets/Titan/towerhunter.png`. Lỗi → None."""
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Titan', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt ô (row, col) khỏi spritesheet — lưới `_FRAME_SIZE` (64px), SRCALPHA."""
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_attack(self) -> None:
        """Bắt đầu animation vung tay (0.33s). Bỏ qua nếu đang đánh dở."""
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def update_anim(self, dt: float) -> None:
        """Máy trạng thái animation: đánh > đi (walk/run) > đứng yên (mẫu chung)."""
        if self._is_attacking:
            self._attack_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES
            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
                self._anim_timer   = 0.0
        elif self._is_moving:
            frames = self._RUN_FRAMES if self._is_running else self._WALK_FRAMES
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % frames
        else:
            self._anim_col   = 0
            self._anim_timer = 0.0

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ frame theo trạng thái (attacking > running > walking), scale + căn tâm."""
        self._load_sprite()
        if self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_moving and self._is_running:
            row = self._RUN_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]
        col = self._anim_col if (self._is_moving or self._is_attacking) else 0
        frame = self._get_frame(row, col)
        if frame is not None:
            ds = self._DISPLAY_SIZE
            scaled = pygame.transform.scale(frame, (ds, ds))
            screen.blit(scaled, (int(self.x - ds // 2), int(self.y - ds // 2)))


# ═══════════════════════════════════════════════════════
#  SOLDIER HUNTER TITAN
# ═══════════════════════════════════════════════════════

class SoldierHunter(Titan):
    """Titan to xác cầm lưỡi hiểm — săn lính, gây splash AoE.

    Switch strategy: target là soldier → SoldierHunterStrategy (AOE cleave),
    target khác → HeavyStrikeStrategy.

    Visual: spritesheet đặc biệt 1152×4224.
      Walk/Run (64×64) : rows 8-11 / 38-41
      Attack (192×192) : pixel-y 3456/3648/3840/4032, 6 frame
    """

    _DEFAULT_HP              = balance.SOLDIER_HUNTER_HP
    _DEFAULT_SPEED           = balance.SOLDIER_HUNTER_SPEED
    _DEFAULT_DAMAGE          = balance.SOLDIER_HUNTER_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.SOLDIER_HUNTER_ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = balance.SOLDIER_HUNTER_ATTACK_COOLDOWN

    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _FRAME_SIZE    = 64
    _DISPLAY_SIZE  = 120
    _ANIM_FPS      = 10
    _ATTACK_DISPLAY_SIZE= 360
    _ATTACK_FRAME_SIZE = 192
    _ATTACK_FRAMES     = 6
    _ATTACK_FPS        = 20
    _ATTACK_Y:    dict = {0: 3456, 1: 3648, 2: 3840, 3: 4032}

    _SPRITE_FILE = 'soldierhunter.png'

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo SoldierHunter — 2 strategy sẵn (heavy/cleave), hoán theo mục tiêu.

        `_soldier_strategy` được tạo với `splash_radius=self._attack_range` — bán
        kính chém lan BẰNG ĐÚNG tầm đánh của titan này, không phải hằng cố định.
        """
        super().__init__(x, y, config)
        self._heavy_strategy   = HeavyStrikeStrategy()
        self._soldier_strategy = SoldierHunterStrategy(splash_radius=self._attack_range)
        self._attack_strategy  = self._heavy_strategy

        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._anim_col          = 0
        self._anim_timer        = 0.0
        self._sprite_sheet = None

    def update(self, dt: float) -> None:
        """Chế độ MANUAL: mục tiêu là lính → cleave strategy, còn lại → heavy.

        (Bản AI-mode nằm ở `ai.py::SoldierHunterAI._act_in_range()`.)
        """
        target = getattr(self, '_target', None)
        # Dùng ENTITY_TYPE (uppercase) để đồng bộ với hệ thống chính
        if target is not None and getattr(target, 'ENTITY_TYPE', '') == 'soldier':
            self._attack_strategy = self._soldier_strategy
        else:
            self._attack_strategy = self._heavy_strategy
        super().update(dt)

    def _load_sprite(self) -> None:
        """Nạp lazy `Assets/Titan/soldierhunter.png` (sheet lớn 1152×4224 — chứa
        cả frame walk/run 64px LẪN frame attack 192px trong cùng 1 file)."""
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Titan', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt frame WALK/RUN (64px) khỏi sheet — dùng cho lúc KHÔNG đánh."""
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def _get_attack_frame(self, col: int = 0):
        """Cắt frame ATTACK (192px, LỚN HƠN hẳn frame đi) khỏi sheet.

        Khác `_get_frame()`: dùng toạ độ Y TUYỆT ĐỐI theo pixel (`_ATTACK_Y[dir]`
        = 3456/3648/3840/4032), KHÔNG phải theo hàng `row × _FRAME_SIZE`, vì frame
        đánh có kích thước KHÁC hẳn frame đi (192 vs 64) và nằm ở vùng riêng cuối
        sheet. Cột vẫn nhân theo `_ATTACK_FRAME_SIZE`.
        """
        if self._sprite_sheet is None:
            return None
        afs = self._ATTACK_FRAME_SIZE
        y_top = self._ATTACK_Y[self._direction]
        region = pygame.Rect(col * afs, y_top, afs, afs)
        frame = pygame.Surface((afs, afs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_attack(self) -> None:
        """Bắt đầu animation chém (0.3s ở 20fps×6frame). Bỏ qua nếu đang đánh dở."""
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def update_anim(self, dt: float) -> None:
        """Máy trạng thái animation: đánh > đi (walk/run) > đứng yên (mẫu chung)."""
        if self._is_attacking:
            self._attack_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES
            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
                self._anim_timer   = 0.0
        elif self._is_moving:
            frames = self._RUN_FRAMES if self._is_running else self._WALK_FRAMES
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % frames
        else:
            self._anim_col   = 0
            self._anim_timer = 0.0

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ frame — ĐÁNH thì dùng frame 192px riêng (scale lên 360px), ĐI thì
        dùng frame 64px thường (scale lên `_DISPLAY_SIZE`). 2 kích thước hiển thị
        khác nhau vì lưỡi hiểm vung ra cần khung hình lớn hơn thân titan."""
        self._load_sprite()
        if self._is_attacking:
            frame = self._get_attack_frame(self._anim_col)
            if frame is not None:
                afs = self._ATTACK_DISPLAY_SIZE
                scaled = pygame.transform.scale(frame, (afs, afs))
                screen.blit(scaled, (int(self.x - afs // 2), int(self.y - afs // 2)))
        else:
            if self._is_moving and self._is_running:
                row = self._RUN_ROWS[self._direction]
            else:
                row = self._WALK_ROWS[self._direction]
            col = self._anim_col if self._is_moving else 0
            frame = self._get_frame(row, col)
            if frame is not None:
                ds = self._DISPLAY_SIZE
                scaled = pygame.transform.scale(frame, (ds, ds))
                screen.blit(scaled, (int(self.x - ds // 2), int(self.y - ds // 2)))


# ═══════════════════════════════════════════════════════
#  KAMIKAZE TITAN — suicide bomber
# ═══════════════════════════════════════════════════════

class Kamikaze(Titan):
    """Titan tự sát — chạy đến cụm soldier rồi phát nổ.

    Hành vi 3 giai đoạn:
      1. Walk: không có soldier trong _DETECT_RADIUS.
      2. Run (locked): chạy về clustering target.
      3. Pause + Explode: vào _EXPLODE_RADIUS → pause → Explosion.execute() → chết.
    """

    _DEFAULT_HP              = balance.KAMIKAZE_HP
    _DEFAULT_SPEED           = balance.KAMIKAZE_SPEED
    _DEFAULT_DAMAGE          = balance.KAMIKAZE_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.KAMIKAZE_ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = balance.KAMIKAZE_ATTACK_COOLDOWN

    _SPRITE_FILE  = 'kamikaze.png'
    _FRAME_SIZE   = 64
    _DISPLAY_SIZE = 120

    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _IDLE_ROWS:   dict = {0: 26, 1: 23, 2: 24, 3: 25}
    _IDLE_FRAMES = 2
    _IDLE_FPS    = 4
    _WALK_FRAMES = 9
    _RUN_FRAMES  = 8
    _ATTACK_FRAMES = 6
    _ANIM_FPS    = 10
    _ATTACK_FPS  = 18

    _DETECT_RADIUS     = balance.KAMIKAZE_DETECT_RADIUS
    _EXPLODE_RADIUS    = balance.KAMIKAZE_EXPLODE_RADIUS
    _CLUSTER_RADIUS    = balance.KAMIKAZE_CLUSTER_RADIUS
    _RUN_SPEED_MULT    = balance.KAMIKAZE_RUN_SPEED_MULT
    _PRE_EXPLODE_PAUSE = balance.KAMIKAZE_PRE_EXPLODE_PAUSE

    _EXP_AOE_RADIUS   = balance.KAMIKAZE_EXP_AOE_RADIUS
    _EXP_KNOCKBACK    = balance.KAMIKAZE_EXP_KNOCKBACK

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo Kamikaze — 2 strategy sẵn (nổ/heavy), mặc định dùng heavy khi đi đường.

        `_explosion_strategy` chỉ dùng khi THỰC SỰ nổ (qua `_release_explosion`);
        `_attack_strategy` mặc định là heavy vì nếu titan bị buộc đánh tường dọc
        đường (đâm phải WallBlocked) thì đánh thường, KHÔNG lãng phí quả bom.

        `_explosion_particles`/`_explosion_flash` — hiệu ứng đồ hoạ vụ nổ (không
        ảnh hưởng gameplay).
        """
        super().__init__(x, y, config)
        self._explosion_strategy = Explosion(
            radius=self._EXP_AOE_RADIUS,
            knockback=self._EXP_KNOCKBACK,
        )
        # Tường: dùng HeavyStrike (tấn công thường)
        self._heavy_strategy = HeavyStrikeStrategy()
        self._attack_strategy = self._heavy_strategy

        self._target = None

        self._direction    = 2
        self._is_moving    = False
        self._is_running   = False
        self._is_attacking = False
        self._anim_col     = 0
        self._anim_timer   = 0.0
        self._attack_anim_timer = 0.0

        self._is_pausing      = False
        self._pause_timer     = 0.0
        self._flash_intensity = 0.0

        self._has_exploded = False
        self._sprite_sheet = None
        self._explosion_particles = []  # particle effects khi nổ
        self._explosion_flash = 0.0  # flash intensity (0-1)

    def _load_sprite(self) -> None:
        """Nạp lazy `Assets/Special/kamikaze.png`. Lỗi → None."""
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Special', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt ô (row, col) khỏi spritesheet — lưới `_FRAME_SIZE` (64px), SRCALPHA."""
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def _pick_clustering_target(self, candidates: list):
        """Chọn lính ở CHỖ ĐÔNG NHẤT để nổ hời nhất — không phải lính gần nhất.

        Thuật toán (O(n²), chấp nhận được vì `candidates` chỉ trong `_DETECT_RADIUS`):
          Với mỗi ứng viên `s`, đếm `count` = số lính KHÁC còn sống nằm trong
          `_CLUSTER_RADIUS` quanh `s` (bán kính CỤM, không phải bán kính nổ).
          Chọn `s` có `count` LỚN NHẤT. Hoà nhau → tie-break bằng khoảng cách tới
          BẢN THÂN Kamikaze GẦN NHẤT (`d_self` nhỏ hơn thắng).

        Ý đồ: Kamikaze không lao vào lính lẻ loi mà tìm ĐIỂM ĐÔNG NHẤT trong tầm
        phát hiện — tối đa hoá số nạn nhân của 1 lần tự sát.

        Tham số: candidates — list lính ứng viên (thường lấy từ `_refind_target`).
        Trả về: entity lính "tâm cụm" tốt nhất, hoặc None nếu candidates rỗng/chết hết.
        Chỉ số: balance.KAMIKAZE_CLUSTER_RADIUS.
        """
        best = None
        best_count = -1
        best_dist  = float('inf')
        for s in candidates:
            if not getattr(s, 'is_alive', True):
                continue
            count = sum(
                1 for other in candidates
                if other is not s and getattr(other, 'is_alive', True)
                and ((s.x - other.x)**2 + (s.y - other.y)**2)**0.5 <= self._CLUSTER_RADIUS
            )
            d_self = ((s.x - self.x)**2 + (s.y - self.y)**2)**0.5
            if count > best_count or (count == best_count and d_self < best_dist):
                best_count = count
                best_dist  = d_self
                best       = s
        return best

    def _refind_target(self) -> None:
        """Tìm lại mục tiêu: quét lính trong `_DETECT_RADIUS`, chọn cụm đông nhất.

        Gộp 2 bước: quét không gian (`WorldQuery.find_in_radius`) rồi giao cho
        `_pick_clustering_target()` chọn điểm tối ưu. Gọi khi mục tiêu cũ chết
        hoặc ra khỏi tầm phát hiện (xem `ai_tick`).

        Chỉ số: balance.KAMIKAZE_DETECT_RADIUS.
        """
        from systems.world_query import WorldQuery
        soldiers = WorldQuery.find_in_radius(
            self.x, self.y, self._DETECT_RADIUS, 'soldier')
        self._target = self._pick_clustering_target(soldiers)

    def trigger_attack(self) -> None:
        """Kích hoạt animation tấn công (6 frame x 18 FPS)."""
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def trigger_explosion(self) -> bool:
        """Bắt đầu ĐẾM NGƯỢC trước khi nổ — chưa nổ ngay, chỉ khựng lại và gồng mình.

        Cửa sổ đếm ngược (`_PRE_EXPLODE_PAUSE`, 1.0s mặc định — hoặc
        `_CMDR_EXPLODE_PAUSE` ngắn hơn nếu AI đặt riêng khi nhắm tướng, xem
        `ai.py::KamikazeAI`) là CƠ HỘI CHO NGƯỜI CHƠI CHẠY RA KHỎI vùng nổ.

        2 điều kiện từ chối: đang đếm ngược dở, hoặc đã nổ rồi.
        Thành công → dừng di chuyển (`_is_moving/_is_running = False`), reset
        `_flash_intensity` (dùng bởi `update_anim` để tính độ sáng nhấp nháy tăng
        dần báo hiệu sắp nổ).

        Trả về: bool — True = bắt đầu đếm ngược.
        Chỉ số: balance.KAMIKAZE_PRE_EXPLODE_PAUSE, balance.AI_KAMIKAZE_CMDR_EXPLODE_PAUSE.
        """
        if self._is_pausing or self._has_exploded:
            return False
        self._is_pausing      = True
        self._pause_timer     = self._PRE_EXPLODE_PAUSE
        self._flash_intensity = 0.0
        self._is_moving       = False
        self._is_running      = False
        return True

    def _release_explosion(self) -> None:
        """NỔ THẬT: áp damage AoE + hiệu ứng particle + TỰ SÁT.

        Thuật toán:
          1. Cờ `_has_exploded` — CHỐNG NỔ 2 LẦN (kiểm tra ở đầu hàm).
          2. Phát âm thanh nổ + bật `_explosion_flash = 1.0` (đồ hoạ, tắt dần
             trong `update_anim`).
          3. Sinh 20 particle lửa bay toả ra ngẫu nhiên (góc/tốc độ/màu random,
             chịu "trọng lực" ảo) — THUẦN ĐỒ HOẠ.
          4. `_attack_strategy.execute(self, self._target)` — đây LÀ LÚC DAMAGE
             THẬT XẢY RA. Lưu ý: strategy lúc này có thể là `_explosion_strategy`
             (nếu AI đã hoán trước khi vào tầm) hoặc `_heavy_strategy` (nếu titan
             tự đâm vào tường mà chưa kịp hoán) — tuỳ trạng thái `_attack_strategy`
             hiện tại lúc gọi, KHÔNG tự hoán ở đây.
          5. `is_alive = False` — Kamikaze CHẾT NGAY sau khi nổ (tự sát thật sự).

        Liên kết: `attackstrategy.py::Explosion.execute()` (đánh theo VÙNG, không
        ưu ái mục tiêu ban đầu).
        Chỉ số: balance.STRAT_EXPLOSION_MULT, balance.KAMIKAZE_EXP_AOE_RADIUS.
        """
        if self._has_exploded:
            return
        self._has_exploded = True
        SoundManager.get_instance().play('kazekage_explosion', self.x, self.y)
        self._explosion_flash = 1.0  # flash hiệu ứng sáng

        # Spawn explosion particles
        import random
        import math
        for _ in range(20):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(300, 500)
            px = self.x + random.uniform(-30, 30)
            py = self.y + random.uniform(-30, 30)
            vx = speed * math.cos(angle)
            vy = speed * math.sin(angle)
            colors = [(255, 160, 0), (255, 200, 50), (255, 100, 0), (255, 220, 100)]
            color = random.choice(colors)
            self._explosion_particles.append({
                'x': px, 'y': py, 'vx': vx, 'vy': vy, 'life': 1.0, 'color': color, 'size': random.randint(6, 12)
            })

        if self._attack_strategy is not None:
            self._attack_strategy.execute(self, self._target)
        if self.is_alive:
            self.is_alive = False

    def update_anim(self, dt: float) -> None:
        """Máy trạng thái animation Kamikaze — ĐẶC BIỆT: hiệu ứng nổ chạy KỂ CẢ SAU KHI CHẾT.

        Thuật toán, theo thứ tự:
          1. **Flash + particle nổ** — tắt/rơi dần MỌI LÚC, kể cả sau `_has_exploded`
             (để hiệu ứng nổ chơi nốt trên xác đã "chết"). `_explosion_flash` tắt
             dần trong 0.33s (`-dt*3`); particle bay theo vận tốc + "trọng lực" ảo
             (`vy += 300*dt`), sống 1.0s (`life -= dt`).
          2. Đã nổ → DỪNG (không còn animation trạng thái nào khác để chạy).
          3. Đang đánh (đâm tường) → animation vung tay, giống mẫu chung.
          4. **ĐANG ĐẾM NGƯỢC nổ** (`_is_pausing`):
             - Đếm ngược `_pause_timer`.
             - `_flash_intensity = 1 - pause_timer/_PRE_EXPLODE_PAUSE` → TĂNG DẦN
               từ 0 lên 1 khi càng gần nổ (dùng để nhấp nháy cảnh báo lúc `draw`).
             - Chạy animation IDLE (đứng gồng mình).
             - Hết đếm ngược → **`_release_explosion()`** — nổ xảy ra NGAY TẠI ĐÂY.
          5. Đang đi → animation walk/run. Đứng yên → reset frame 0.

        Chỉ số: balance.KAMIKAZE_PRE_EXPLODE_PAUSE.
        """
        # Update explosion flash
        if self._explosion_flash > 0:
            self._explosion_flash = max(0, self._explosion_flash - dt * 3)  # fade in 0.33s

        # Update explosion particles
        for p in self._explosion_particles:
            if p['life'] > 0:
                p['x'] += p['vx'] * dt
                p['y'] += p['vy'] * dt
                p['vy'] += 300 * dt  # gravity
                p['life'] -= dt

        if self._has_exploded:
            return

        if self._is_attacking:
            self._attack_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES
            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
                self._anim_timer   = 0.0
            return

        if self._is_pausing:
            self._pause_timer -= dt
            self._flash_intensity = 1.0 - max(0.0, self._pause_timer) / self._PRE_EXPLODE_PAUSE
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._IDLE_FPS:
                self._anim_timer -= 1.0 / self._IDLE_FPS
                self._anim_col = (self._anim_col + 1) % self._IDLE_FRAMES
            if self._pause_timer <= 0:
                # Tự nổ (hết đếm ngược) đi qua on_death() y như bị giết → publish
                # 'titan_died' + rơi loot (on_death tự gọi _release_explosion vì
                # _has_exploded còn False). Gọi thẳng _release_explosion trước đây
                # khiến Kamikaze tự sát KHÔNG rơi đồ / không phát event.
                self.on_death()
            return

        if self._is_moving:
            frames = self._RUN_FRAMES if self._is_running else self._WALK_FRAMES
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % frames
        else:
            self._anim_col   = 0
            self._anim_timer = 0.0

    def ai_tick(self, dt: float) -> None:
        """1 TICK AI THỦ CÔNG — dùng khi Kamikaze KHÔNG gắn `ai.py` (demo/test).

        ⚠️ Đây LÀ bản AI đơn giản hoá của `ai.py::KamikazeAI.update()`. Trong game
        thật, `KamikazeAI` mới là bộ não chính (có telegraph-circle cho tướng,
        v.v.); hàm này chỉ dùng khi test/demo Kamikaze độc lập.

        Thuật toán:
          1. Đã nổ / đang đếm ngược / đã chết → không làm gì.
          2. Mục tiêu chết HOẶC ra khỏi `_DETECT_RADIUS` → `_refind_target()`.
          3. Không có mục tiêu → đứng yên.
          4. Trong `_EXPLODE_RADIUS` → `trigger_explosion()`, thoát.
          5. Ngoài tầm nổ → CHẠY (`_RUN_SPEED_MULT` × speed) thẳng về mục tiêu,
             dịch chuyển TRỰC TIẾP (KHÔNG qua `_move()`/né tường của AI thật —
             đây là lý do hàm này chỉ dùng cho test đơn giản).

        Chỉ số: balance.KAMIKAZE_DETECT_RADIUS / _EXPLODE_RADIUS / _RUN_SPEED_MULT.
        """
        if self._has_exploded or self._is_pausing or not self.is_alive:
            return

        if self._target is None or not getattr(self._target, 'is_alive', True):
            self._refind_target()
        else:
            d = self._distance_to(self._target)
            if d > self._DETECT_RADIUS:
                self._refind_target()

        if self._target is None:
            self._is_running = False
            return

        d = self._distance_to(self._target)
        if d <= self._EXPLODE_RADIUS:
            self.trigger_explosion()
            return

        self._is_running = True
        self._is_moving  = True
        run_speed = self._speed * self._RUN_SPEED_MULT
        dx = self._target.x - self.x
        dy = self._target.y - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0:
            self.x += (dx / dist) * run_speed * dt
            self.y += (dy / dist) * run_speed * dt
        if abs(dx) > abs(dy):
            self._direction = 3 if dx > 0 else 1
        else:
            self._direction = 2 if dy > 0 else 0

    def on_death(self) -> None:
        """Chết vì lý do KHÁC vụ nổ (bị bắn chết trước khi kịp tự sát) → VẪN NỔ.

        Nếu chưa nổ (`not _has_exploded`) → gọi `_release_explosion()` TRƯỚC —
        Kamikaze chết theo bất kỳ cách nào cũng nổ, không có cách nào giết nó mà
        không ăn damage nổ (trừ khi nó đã tự nổ trước đó rồi).
        Sau đó `super().on_death()` — publish event 'titan_died' + rơi đồ như bình thường.
        """
        if not self._has_exploded:
            self._release_explosion()
        super().on_death()

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ: flash nổ (vòng tròn sáng to dần rồi tắt) + particle lửa + sprite thân.

        Thuật toán: vẽ flash trước (dưới cùng), particle đè lên, sprite Kamikaze
        vẽ cuối (trên cùng). Alpha của particle giảm dần theo `life` còn lại.
        CHỈ ĐỒ HOẠ.
        """
        # Vẽ explosion flash
        if self._explosion_flash > 0:
            flash_size = int(200 * self._explosion_flash)
            flash_color = (255, 220, 100)
            pygame.draw.circle(screen, flash_color, (int(self.x), int(self.y)), flash_size)

        # Vẽ explosion particles
        for p in self._explosion_particles:
            if p['life'] > 0:
                alpha_ratio = min(1.0, p['life'] / 1.0)
                size = max(1, int(p['size'] * alpha_ratio))
                pygame.draw.circle(screen, p['color'], (int(p['x']), int(p['y'])), size)

        if self._has_exploded:
            return

        self._load_sprite()

        if self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
            col = self._anim_col
        elif self._is_pausing:
            row = self._IDLE_ROWS[self._direction]
            col = self._anim_col % self._IDLE_FRAMES
        elif self._is_moving and self._is_running:
            row = self._RUN_ROWS[self._direction]
            col = self._anim_col
        elif self._is_moving:
            row = self._WALK_ROWS[self._direction]
            col = self._anim_col
        else:
            row = self._WALK_ROWS[self._direction]
            col = 0

        frame = self._get_frame(row, col)

        if frame is not None:
            ds = self._DISPLAY_SIZE
            scaled = pygame.transform.scale(frame, (ds, ds))
            ox = int(self.x - ds // 2)
            oy = int(self.y - ds // 2)
            screen.blit(scaled, (ox, oy))

            if self._is_pausing and self._flash_intensity > 0:
                t     = self._flash_intensity
                freq  = 6 + t * 14
                phase = (1.0 - self._pause_timer / self._PRE_EXPLODE_PAUSE) * freq * math.pi
                pulse = abs(math.sin(phase))
                alpha = int(220 * t * pulse)
                if alpha > 0:
                    mask    = pygame.mask.from_surface(scaled)
                    outline = mask.outline()
                    if outline:
                        glow_surf = pygame.Surface((ds, ds), pygame.SRCALPHA)
                        if len(outline) >= 2:
                            pygame.draw.lines(
                                glow_surf, (255, 60, 40, alpha), True, outline, 2)
                        screen.blit(glow_surf, (ox, oy))
