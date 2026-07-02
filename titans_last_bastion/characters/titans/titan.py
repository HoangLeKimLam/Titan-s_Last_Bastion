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

from core.entity import Entity
from core.interfaces import IAttackable, IMovable
from core.event_bus import GameEventBus
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
    _DEFAULT_HP              = 100
    _DEFAULT_SPEED           = 60.0
    _DEFAULT_DAMAGE          = 20
    _DEFAULT_ATTACK_RANGE    = 60.0
    _DEFAULT_SOLDIER_ATTACK_RANGE = 60.0
    _DEFAULT_ATTACK_COOLDOWN = 1.5
    VISUAL_RANGE             = 250.0  # Phát hiện soldiers/commanders trong tầm này

    def __init__(self, x: float, y: float, config: dict = None) -> None:
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
        pass

    # ─── IAttackable ─────────────────────────────────────

    def take_damage(self, amount: int, dtype: str, attacker=None) -> None:
        self._hp -= amount
   
        if attacker is not None:
            ai = getattr(self, '_ai', None)
            if ai is not None:
                ai.notify_attacked(attacker)
        if self._hp <= 0:
            self.on_death()

    def on_death(self) -> None:
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

    _DEFAULT_HP              = 1000
    _DEFAULT_SPEED           = 60.0
    _DEFAULT_DAMAGE          = 60
    _DEFAULT_ATTACK_RANGE    = 30.0
    _DEFAULT_ATTACK_COOLDOWN = 0.75

    _HEAVY_HP_RATIO = 0.5

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
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_attack(self) -> None:
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def update(self, dt: float) -> None:
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

    _DEFAULT_HP              = 2500
    _DEFAULT_SPEED           = 60.0
    _DEFAULT_DAMAGE          = 150
    _DEFAULT_ATTACK_RANGE    = 40.0
    _DEFAULT_ATTACK_COOLDOWN = 1.0

    ARMOR_REDUCTION  = 0.7
    _HITS_TO_BREAK   = 25
    _DASH_SPEED_MULT = 3.0
    _DASH_MAX_DIST   = 300.0
    _DASH_HIT_RADIUS = 18.0
    _RAM_HIT_RADIUS  = 55.0   # 55px → sprite half=60 → 5px overlap = "chạm tường"
    _STAGGER_DURATION = 0.3
    _RECOIL_DIST     = 120.0

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
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Special', 'armored.png')
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_dash(self, dx: float, dy: float, run_speed: float,
                     dash_target=None) -> bool:
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
        self._anim_col            = 0
        self._anim_timer          = 0.0

        if abs(self._dash_dx) > abs(self._dash_dy):
            self._direction = 3 if self._dash_dx > 0 else 1
        else:
            self._direction = 2 if self._dash_dy > 0 else 0
        return True

    def dash_step(self, dt: float, world_bounds: tuple = None) -> tuple:
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
        """AABB distance từ titan center đến wall section (32×32 rect)."""
        rx, ry = float(ws.x), float(ws.y)
        near_x = max(rx, min(self.x, rx + 32.0))
        near_y = max(ry, min(self.y, ry + 32.0))
        dx = self.x - near_x
        dy = self.y - near_y
        return (dx * dx + dy * dy) ** 0.5

    def begin_recoil(self, wall) -> None:
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
        """Lái vòng Stagger/Recoil/Dash 1 frame. Trả 'stagger'/'recoil'/'dash'/'idle'.

        wall_check(nx, ny)  : callback từ AI — chỉ dùng khi _dash_target đã chết/None
                              (ngăn titan lao vô định qua tường khác khi target bị phá).
        recoil_check(nx, ny): trả True nếu vị trí bị chặn (ngăn xuyên tường sau lưng).
                              exclude _dash_target để không bị block ngay khi vừa húc.
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
        if self._is_attacking or self._is_dashing:
            return False
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0
        return True

    def update_anim(self, dt: float) -> None:
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
        # Báo AI biết kẻ tấn công (đồng nhất với Titan.take_damage)
        if attacker is not None:
            ai = getattr(self, '_ai', None)
            if ai is not None:
                ai.notify_attacked(attacker)
        if self._hp <= 0:
            self.on_death()

    def draw(self, screen: pygame.Surface) -> None:
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

    _DEFAULT_HP              = 1500
    _DEFAULT_SPEED           = 70.0
    _DEFAULT_DAMAGE          = 70
    _DEFAULT_ATTACK_RANGE    = 30.0
    _DEFAULT_ATTACK_COOLDOWN = 0.75

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
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Titan', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_attack(self) -> None:
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def update_anim(self, dt: float) -> None:
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

    _DEFAULT_HP              = 1500
    _DEFAULT_SPEED           = 70.0
    _DEFAULT_DAMAGE          = 70
    _DEFAULT_ATTACK_RANGE    = 30.0
    _DEFAULT_ATTACK_COOLDOWN = 0.75

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
        target = getattr(self, '_target', None)
        # Dùng ENTITY_TYPE (uppercase) để đồng bộ với hệ thống chính
        if target is not None and getattr(target, 'ENTITY_TYPE', '') == 'tower':
            self._attack_strategy = self._siege_strategy
        else:
            self._attack_strategy = self._heavy_strategy
        super().update(dt)

    def _load_sprite(self) -> None:
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Titan', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_attack(self) -> None:
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def update_anim(self, dt: float) -> None:
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

    _DEFAULT_HP              = 1500
    _DEFAULT_SPEED           = 70.0
    _DEFAULT_DAMAGE          = 70
    _DEFAULT_ATTACK_RANGE    = 40.0
    _DEFAULT_ATTACK_COOLDOWN = 0.75

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
        target = getattr(self, '_target', None)
        # Dùng ENTITY_TYPE (uppercase) để đồng bộ với hệ thống chính
        if target is not None and getattr(target, 'ENTITY_TYPE', '') == 'soldier':
            self._attack_strategy = self._soldier_strategy
        else:
            self._attack_strategy = self._heavy_strategy
        super().update(dt)

    def _load_sprite(self) -> None:
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Titan', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def _get_attack_frame(self, col: int = 0):
        if self._sprite_sheet is None:
            return None
        afs = self._ATTACK_FRAME_SIZE
        y_top = self._ATTACK_Y[self._direction]
        region = pygame.Rect(col * afs, y_top, afs, afs)
        frame = pygame.Surface((afs, afs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def trigger_attack(self) -> None:
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    def update_anim(self, dt: float) -> None:
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

    _DEFAULT_HP              = 1000
    _DEFAULT_SPEED           = 80.0
    _DEFAULT_DAMAGE          = 100
    _DEFAULT_ATTACK_RANGE    = 60.0
    _DEFAULT_ATTACK_COOLDOWN = 1.0

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

    _DETECT_RADIUS     = 300.0
    _EXPLODE_RADIUS    = 60.0
    _CLUSTER_RADIUS    = 60.0
    _RUN_SPEED_MULT    = 2.0
    _PRE_EXPLODE_PAUSE = 1.0

    _EXP_AOE_RADIUS   = 80.0
    _EXP_KNOCKBACK    = 80.0
    _EXP_SPLASH_RATIO = 0.75

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)
        self._explosion_strategy = Explosion(
            splash_ratio=self._EXP_SPLASH_RATIO,
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
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__), 'Assets', 'Special', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    def _pick_clustering_target(self, candidates: list):
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
        if self._is_pausing or self._has_exploded:
            return False
        self._is_pausing      = True
        self._pause_timer     = self._PRE_EXPLODE_PAUSE
        self._flash_intensity = 0.0
        self._is_moving       = False
        self._is_running      = False
        return True

    def _release_explosion(self) -> None:
        if self._has_exploded:
            return
        self._has_exploded = True
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
                self._release_explosion()
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
        """1 tick AI manual — dùng khi không gắn ai.py."""
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
        if not self._has_exploded:
            self._release_explosion()
        super().on_death()

    def draw(self, screen: pygame.Surface) -> None:
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
