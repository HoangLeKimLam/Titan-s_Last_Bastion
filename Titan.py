# characters/titans/titan.py
"""Titan.py — Toàn bộ tham số + thân xác (sprite/animation) của Titan thường.

Trách nhiệm:
    • Khai báo tham số mặc định (HP, speed, damage, attack_range, attack_cooldown)
      cho mỗi class Titan dưới dạng **class constants** `_DEFAULT_*`. File
      check chỉ override khi cần test giá trị khác.
    • Khai báo cấu hình spritesheet (rows, FPS, frame size) cho từng class.
    • Implement logic animation (Walk/Run/Attack/...) + `draw(screen)`.
    • Implement cơ chế thân xác đặc thù (vd Armored Dash/Stagger/Recoil,
      Kamikaze pause + flash + nổ, Wolf cắn antiheal).

KHÔNG bao gồm:
    • Logic chọn mục tiêu → xem `Priority.py`.
    • Logic AI tự hành (sense/decide/act) → xem `AI.py`.
    • Cách đánh (damage formula) → xem `AttackStrategy.py`.

Mỗi class Titan = thân xác (file này) + khẩu vị (`Priority.py`) +
đòn đánh (`AttackStrategy.py`) + bộ não (`AI.py`).

Truyền tham số:
    Mỗi class Titan có `_DEFAULT_HP`, `_DEFAULT_SPEED`, … ở class level
    (xem ở mỗi class). `__init__(x, y, config=None)` đọc `config` để override
    bất kỳ tham số nào, fallback default. File check chỉ cần truyền `{}`
    nếu muốn dùng default.

    Ví dụ:
        RegularTitan(x, y)                  # dùng default
        RegularTitan(x, y, {'hp': 500})     # override HP, giữ rest
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
#  TITAN BASE — class cha trừu tượng
# ═══════════════════════════════════════════════════════

class Titan(Entity, IAttackable, IMovable):
    """Cha trừu tượng của mọi Titan.

    Không tạo trực tiếp — chỉ để kế thừa. Chứa AI logic chung
    (`update`/`_find_best_target`) — phục vụ chế độ "manual / không AI".
    Trong môi trường demo CHECKAI, vòng AI thật được lo bởi `AI.py`.

    Quy ước class constants — subclass override để có tham số riêng:
        _DEFAULT_HP             — HP gốc
        _DEFAULT_SPEED          — tốc độ đi bộ (px/s)
        _DEFAULT_DAMAGE         — damage base (chưa nhân multiplier strategy)
        _DEFAULT_ATTACK_RANGE   — tầm đánh (px)
        _DEFAULT_ATTACK_COOLDOWN — hồi chiêu (s)

    `config` truyền vào `__init__` để override bất kỳ tham số nào.
    """

    # ── Tham số mặc định (subclass override) ─────────────────────
    _DEFAULT_HP              = 100
    _DEFAULT_SPEED           = 60.0
    _DEFAULT_DAMAGE          = 20
    _DEFAULT_ATTACK_RANGE    = 60.0
    _DEFAULT_ATTACK_COOLDOWN = 1.5

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y)
        cfg = config or {}
        # Đọc từ config; thiếu thì lấy class constant.
        self._hp              = int(cfg.get('hp',              self._DEFAULT_HP))
        self._max_hp          = self._hp
        self._speed           = float(cfg.get('speed',         self._DEFAULT_SPEED))
        self._damage          = int(cfg.get('damage',          self._DEFAULT_DAMAGE))
        self._attack_range    = float(cfg.get('attack_range',  self._DEFAULT_ATTACK_RANGE))
        self._attack_cooldown = float(cfg.get('attack_cooldown', self._DEFAULT_ATTACK_COOLDOWN))
        self._reward          = cfg.get('reward', {})

        self._target          = None
        self._attack_strategy = None    # subclass khởi tạo
        self._attack_timer    = 0.0     # đếm hồi chiêu

    # ─── METHODS BẮT BUỘC (Entity yêu cầu) ─────────────

    def update(self, dt: float) -> None:
        """AI cơ bản: tìm target → di chuyển → tấn công.

        Chế độ "manual" (không AI ngoài) — game thật và CHECKAI thay thế
        vòng này bằng `AI.update()` riêng.
        """
        if not self.is_alive:
            return

        self._attack_timer -= dt

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
        """Vẽ sprite + HP bar. Subclass override."""
        pass

    # ─── IAttackable ─────────────────────────────────────

    def take_damage(self, amount: int, dtype: str) -> None:
        """Nhận damage. Class con override nếu có giáp/kháng."""
        self._hp -= amount
        if self._hp <= 0:
            self.on_death()

    def on_death(self) -> None:
        """Gọi khi HP = 0. Emit event để ResourceManager cộng thưởng."""
        self.is_alive = False
        GameEventBus.get_instance().publish(
            'titan_died',
            {'titan': self, 'reward': self._reward},
        )

    # ─── IMovable ─────────────────────────────────────────

    def move(self, destination: tuple) -> None:
        """Di chuyển trực tiếp đến tọa độ (dùng cho teleport)."""
        self.x, self.y = destination

    # ─── PRIVATE HELPERS ─────────────────────────────────

    def _find_best_target(self):
        """Tìm mục tiêu theo thứ tự ưu tiên mặc định.

        Ưu tiên 1: HQ nếu có thể vào thẳng
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

    def _move_toward(self, target, dt: float) -> None:
        """Di chuyển về phía target với tốc độ _speed * dt."""
        dx = target.x - self.x
        dy = target.y - self.y
        dist = (dx**2 + dy**2) ** 0.5
        if dist > 0:
            self.x += (dx / dist) * self._speed * dt
            self.y += (dy / dist) * self._speed * dt

    def _distance_to(self, target) -> float:
        """Khoảng cách Euclidean đến target."""
        dx = target.x - self.x
        dy = target.y - self.y
        return (dx**2 + dy**2) ** 0.5


# ═══════════════════════════════════════════════════════
#  REGULAR TITAN — Titan cơ bản (Walk/Run/Attack + Heavy threshold)
# ═══════════════════════════════════════════════════════

class RegularTitan(Titan):
    """Titan cơ bản — đi/chạy/đánh thường. HP < 40% → HeavyStrikeStrategy.

    Visual: spritesheet ngẫu nhiên trong Assets/Titan/{regular2..7}.png
    chọn 1 lần lúc spawn (truyền `config['variant']` để cố định).

    Spritesheet (mỗi frame 64×64, ánh xạ 0=N, 1=W, 2=S, 3=E):
        Walk   : 8 / 9 / 10 / 11   — 9 frame/hàng
        Run    : 38 / 39 / 40 / 41 — 8 frame/hàng
        Attack : 12 / 13 / 14 / 15 — 6 frame/hàng

    Public API cho demo/AI:
        • `trigger_attack()`        — kích hoạt 1 đòn (animation + damage)
        • `update(dt)` / `update_anim(dt)` — cập nhật animation
    """

    # ── Tham số gameplay (override Titan defaults) ────────────────
    _DEFAULT_HP              = 1000
    _DEFAULT_SPEED           = 60.0
    _DEFAULT_DAMAGE          = 60
    _DEFAULT_ATTACK_RANGE    = 30.0
    _DEFAULT_ATTACK_COOLDOWN = 0.75

    # ── Cờ chuyển strategy ────────────────────────────────────────
    _HEAVY_HP_RATIO = 0.5       # HP < 40% → switch HeavyStrikeStrategy

    # ── Sprite layout ─────────────────────────────────────────────
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

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)
        cfg = config or {}
        self._attack_strategy = MeleeRushStrategy()
        self._heavy_mode      = False

        # Chọn biến thể visual (2/4/5/6/7) — config['variant'] để cố định
        variant = cfg.get('variant')
        self._variant = variant if variant in self._VARIANTS \
            else random.choice(self._VARIANTS)

        # Animation state
        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._anim_col          = 0
        self._anim_timer        = 0.0

        # Spritesheet lazy-load
        self._sprite_sheet = None

    # ── Sprite helpers ───────────────────────────────────────────

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

    # ── Public API cho demo/AI ───────────────────────────────────

    def trigger_attack(self) -> None:
        """Kích hoạt animation tấn công 1 đòn."""
        if self._is_attacking:
            return
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0

    # ── Update ───────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Update tổng hợp — gọi khi NO AI ngoài. CHECKAI override bằng AI.py."""
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

        # HP < 40% → switch sang HeavyStrikeStrategy
        if not self._heavy_mode and self._max_hp > 0 \
                and self._hp / self._max_hp < self._HEAVY_HP_RATIO:
            self._heavy_mode      = True
            self._attack_strategy = HeavyStrikeStrategy()

        # Walk/Run animation khi đang di chuyển
        if self._is_moving:
            frames = self._RUN_FRAMES if self._is_running else self._WALK_FRAMES
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % frames
        else:
            self._anim_col = 0

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        self._load_sprite()

        if self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_moving and self._is_running:
            row = self._RUN_ROWS[self._direction]
        elif self._is_moving:
            row = self._WALK_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (self._is_moving or self._is_attacking) else 0
        frame = self._get_frame(row, col)

        if frame is not None:
            ox = int(self.x - self._FRAME_SIZE // 2)
            oy = int(self.y - self._FRAME_SIZE // 2)
            screen.blit(frame, (ox, oy))


# ═══════════════════════════════════════════════════════
#  ARMORED TITAN — Titan giáp, Dash + Armor Break
# ═══════════════════════════════════════════════════════

class ArmoredTitan(Titan):
    """Titan giáp — chặn 60% damage thường, Dash húc Wall.

    Visual: `Assets/Special/armored.png` (frame 64×64).
      Walk    : rows 8 / 9 / 10 / 11    — 9 frame
      Run     : rows 38 / 39 / 40 / 41 — 8 frame
      Dash    : tái dùng Run rows, FPS ×2 (lao bull rush)
      Attack  : rows 12 / 13 / 14 / 15 — 6 frame (dùng SAU khi giáp vỡ)

    Cơ chế Dash (`ArmoredRamStrategy` — chỉ khi còn giáp):
      • Tốc độ ×1.5 so với Run
      • Dừng khi va chạm target HOẶC đi hết `_DASH_MAX_DIST` px
      • Va chạm → execute strategy + `_ram_hits += 1`
      • Sau cú húc: stagger `_STAGGER_DURATION` s → walk lùi `_RECOIL_DIST` px

    Armor break — 2 con đường cộng dồn cả vòng đời (không reset):
      1. `_ram_hits ≥ _HITS_TO_BREAK` → vỡ giáp
      2. `_antiarmor_hits ≥ _HITS_TO_BREAK` → vỡ giáp
      Vỡ giáp → `_attack_strategy = HeavyStrikeStrategy()` (vĩnh viễn),
      Dash khóa, đổi sang melee đứng tại chỗ.

    Damage filter (`take_damage`):
      • Còn giáp + `dtype='anti_armor'` → full damage + +1 antiarmor_hits
      • Còn giáp + dtype khác           → chặn 60% (giảm còn 40%)
      • Giáp vỡ                          → full damage mọi dtype

    Public API:
        • `trigger_dash(dx, dy, run_speed)`   — bắt đầu dash (False nếu vỡ giáp)
        • `dash_step(dt)`                     — 1 bước dash (gọi mỗi frame)
        • `end_dash_on_hit(target)`           — kết thúc dash do va chạm
        • `update_dash_cycle(dt, wall_target)` — drive cả vòng Stagger/Recoil/Dash
        • `trigger_attack()`                  — melee đứng tại chỗ
        • `update_anim(dt)`                   — animation
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = 2500
    _DEFAULT_SPEED           = 60.0
    _DEFAULT_DAMAGE          = 150
    _DEFAULT_ATTACK_RANGE    = 40.0   # khớp tầm vung tay (frame 64px)
    _DEFAULT_ATTACK_COOLDOWN = 1.0

    # ── Tham số giáp / dash ─────────────────────────────────────
    ARMOR_REDUCTION  = 0.7      # chặn 60% damage thường
    _HITS_TO_BREAK   = 15       # ngưỡng vỡ giáp (Ram HOẶC anti_armor)
    _DASH_SPEED_MULT = 1.67      # ×1.5 so với Run speed
    _DASH_MAX_DIST   = 300.0    # khoảng dash tối đa (px)
    _DASH_HIT_RADIUS = 18.0     # va chạm sprite ↔ target
    _RAM_HIT_RADIUS  = 30.0     # AI: coi là "trúng Wall"
    _STAGGER_DURATION = 0.3     # s — đứng khựng sau cú húc
    _RECOIL_DIST     = 120.0    # px — walk lùi sau stagger

    # ── Sprite layout ────────────────────────────────────────────
    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _DASH_ROWS:   dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _DASH_FRAMES   = 8
    _ATTACK_FRAMES = 6
    _FRAME_SIZE    = 64
    _ANIM_FPS      = 10
    _DASH_FPS      = 18
    _ATTACK_FPS    = 18

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)
        self._attack_strategy = ArmoredRamStrategy()
        self._armor_intact    = True

        # Counter vỡ giáp — tích lũy cả vòng đời, KHÔNG reset
        self._ram_hits        = 0
        self._antiarmor_hits  = 0
        self._break_cause     = ''   # '' khi còn giáp; 'ram' | 'anti_armor'

        # Animation state
        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._anim_col          = 0
        self._anim_timer        = 0.0

        # Dash state
        self._is_dashing          = False
        self._dash_dx             = 0.0
        self._dash_dy             = 0.0
        self._dash_dist_remaining = 0.0
        self._dash_speed          = 0.0

        # Melee attack state (post-break)
        self._is_attacking      = False
        self._attack_anim_timer = 0.0

        # Stagger / Recoil (chuyển từ ArmoredAI về đây)
        self._stagger_timer    = 0.0
        self._recoil_dist_left = 0.0
        self._recoil_dx        = 0.0
        self._recoil_dy        = 0.0

        # Spritesheet lazy-load
        self._sprite_sheet = None

    # ── Sprite helpers ───────────────────────────────────────────

    def _load_sprite(self) -> None:
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Special', 'armored.png',
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

    # ── Public API: Dash ────────────────────────────────────────

    def trigger_dash(self, dx: float, dy: float, run_speed: float) -> bool:
        """Kích hoạt skill ArmoredRam — dash theo hướng (dx, dy).

        Trả False nếu: đang dash/đánh, giáp đã vỡ, hoặc vector = 0.
        """
        if self._is_dashing or self._is_attacking:
            return False
        if not self._armor_intact:
            return False
        mag = (dx * dx + dy * dy) ** 0.5
        if mag <= 0:
            return False

        self._dash_dx = dx / mag
        self._dash_dy = dy / mag
        self._dash_dist_remaining = self._DASH_MAX_DIST
        self._dash_speed          = run_speed * self._DASH_SPEED_MULT
        self._is_dashing          = True
        self._anim_col            = 0
        self._anim_timer          = 0.0

        # Cập nhật hướng nhìn theo vector trội
        if abs(self._dash_dx) > abs(self._dash_dy):
            self._direction = 3 if self._dash_dx > 0 else 1
        else:
            self._direction = 2 if self._dash_dy > 0 else 0
        return True

    def dash_step(self, dt: float, world_bounds: tuple = None) -> tuple:
        """Tính bước dash kế tiếp — trả (new_x, new_y, finished: bool)."""
        if not self._is_dashing:
            return self.x, self.y, True

        step = self._dash_speed * dt
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
        """Kết thúc dash do va chạm target — gọi Strategy + đếm hit.

        Trả (broke: bool, cause: str): broke=True nếu lần này vỡ giáp.
        """
        if not self._is_dashing:
            return False, ''

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
        """Vỡ giáp + chuyển VĨNH VIỄN sang HeavyStrikeStrategy."""
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

    # ── Public API: Stagger / Recoil (chuyển từ ArmoredAI về đây) ──

    def begin_recoil(self, wall) -> None:
        """Sau cú húc Wall: stagger + walk lùi để lấy đà dash tiếp.

        Vì sao chuyển từ AI sang Titan?
            Stagger/Recoil là PHẢN ỨNG THÂN XÁC của Armored sau cú húc
            (không phải quyết định AI). AI chỉ gọi `begin_recoil()` rồi
            `update_dash_cycle()` mỗi frame; thân xác tự đếm timer + bước lùi.
            Tách bạch giúp ArmoredAI nhỏ gọn.
        """
        dx = self.x - wall.x
        dy = self.y - wall.y
        d  = (dx * dx + dy * dy) ** 0.5
        if d <= 0:
            dx, dy, d = -1.0, 0.0, 1.0
        self._recoil_dx        = dx / d
        self._recoil_dy        = dy / d
        self._recoil_dist_left = self._RECOIL_DIST
        self._stagger_timer    = self._STAGGER_DURATION

    def update_dash_cycle(self, dt: float, wall_target=None) -> str:
        """Lái vòng Stagger/Recoil/Dash 1 frame.

        Tham số:
            dt: delta time
            wall_target: Wall đang nhắm (để check va chạm dash).
                AI truyền vào, có thể None nếu chưa có mục tiêu cụ thể.

        Trả về 1 trong các string:
            'stagger' — đang đứng khựng
            'recoil'  — đang walk lùi
            'dash'    — đang dash
            'idle'    — chưa làm gì (AI có thể trigger dash tiếp)

        Vì sao trả string?
            AI dùng giá trị này để biết "thân xác đang làm gì" và set
            `state`/`last_reason` cho HUD. Không trả gì → AI phải đoán
            qua các cờ rời (`_is_dashing`/`_stagger_timer`/...).
        """
        # 1) Stagger
        if self._stagger_timer > 0.0:
            self._stagger_timer -= dt
            self._is_moving  = False
            self._is_running = False
            return 'stagger'

        # 2) Recoil
        if self._recoil_dist_left > 0.0:
            speed = self._speed
            step  = speed * dt
            if step > self._recoil_dist_left:
                step = self._recoil_dist_left
            self._recoil_dist_left -= step
            self.x += self._recoil_dx * step
            self.y += self._recoil_dy * step
            self._is_moving  = True
            self._is_running = False
            # Cập nhật hướng nhìn theo hướng đang lùi
            if abs(self._recoil_dx) >= abs(self._recoil_dy):
                self._direction = 3 if self._recoil_dx > 0 else 1
            else:
                self._direction = 2 if self._recoil_dy > 0 else 0
            return 'recoil'

        # 3) Dash đang chạy → bước 1 đoạn + check va chạm
        if self._is_dashing:
            new_x, new_y, _finished = self.dash_step(dt)
            self.x, self.y = new_x, new_y
            self._is_moving = True
            # Va chạm Wall mục tiêu → end dash + có thể begin recoil
            if (wall_target is not None
                    and getattr(wall_target, 'is_alive', False)
                    and self._distance_to(wall_target) <= self._RAM_HIT_RADIUS):
                broke, _cause = self.end_dash_on_hit(wall_target)
                # Wall còn sống + giáp chưa vỡ → recoil để dash tiếp
                if (not broke
                        and getattr(wall_target, 'is_alive', False)
                        and self._armor_intact):
                    self.begin_recoil(wall_target)
            return 'dash'

        return 'idle'

    # ── Public API: Melee post-break ───────────────────────────

    def trigger_attack(self) -> bool:
        """Kích hoạt animation melee đứng tại chỗ.

        Còn giáp: đánh target không-Wall (HQ/Soldier...) bằng animation
        _ATTACK_ROWS. Giáp vỡ: dùng như đòn HeavyStrike chính.
        Trả False nếu đang dashing/đang attacking.
        """
        if self._is_attacking or self._is_dashing:
            return False
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0
        return True

    # ── Update animation (KHÔNG gọi super().update()) ──────────

    def update_anim(self, dt: float) -> None:
        """Cập nhật frame animation theo trạng thái hiện tại.

        Thứ tự ưu tiên: Attack > Dash > Walk/Run > Idle.
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

    # ── IAttackable: take_damage có giáp ───────────────────────

    def take_damage(self, amount: int, dtype: str) -> None:
        """Override: filter damage theo giáp + đếm anti_armor."""
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
        if self._hp <= 0:
            self.on_death()

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        self._load_sprite()

        if self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_dashing:
            row = self._DASH_ROWS[self._direction]
        elif self._is_moving and self._is_running:
            row = self._RUN_ROWS[self._direction]
        elif self._is_moving:
            row = self._WALK_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (
            self._is_moving or self._is_dashing or self._is_attacking
        ) else 0
        frame = self._get_frame(row, col)

        if frame is not None:
            ox = int(self.x - self._FRAME_SIZE // 2)
            oy = int(self.y - self._FRAME_SIZE // 2)
            screen.blit(frame, (ox, oy))


# ═══════════════════════════════════════════════════════
#  WOLF TITAN — chuyên chặn hồi máu (Incurable)
# ═══════════════════════════════════════════════════════

class Wolf(Titan):
    """Titan thân nhỏ giống chó sói — cắn chặn hồi máu.

    Strategy: `Incurable` cố định cả vòng đời. Damage ×0.8 đổi debuff
    `antiheal` — target tự xử lý dtype (set cờ ngăn regen).

    Visual: `Assets/Titan/wolf.png` cố định (không random variant).
      Walk   : rows 8 / 9 / 10 / 11   — 9 frame
      Run    : rows 38 / 39 / 40 / 41 — 8 frame
      Attack : rows 12 / 13 / 14 / 15 — 6 frame (đòn cắn antiheal)
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = 1500
    _DEFAULT_SPEED           = 70.0     # nhanh hơn Regular
    _DEFAULT_DAMAGE          = 70
    _DEFAULT_ATTACK_RANGE    = 30.0
    _DEFAULT_ATTACK_COOLDOWN = 0.75      # cắn nhanh

    # ── Sprite layout ────────────────────────────────────────────
    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _ATTACK_FRAMES = 6
    _FRAME_SIZE    = 64
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 18

    _SPRITE_FILE = 'wolf.png'

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
                os.path.dirname(__file__),
                'Assets', 'Titan', self._SPRITE_FILE,
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
        """Kích hoạt animation cắn 1 đòn."""
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
        elif self._is_moving:
            row = self._WALK_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (self._is_moving or self._is_attacking) else 0
        frame = self._get_frame(row, col)

        if frame is not None:
            ox = int(self.x - self._FRAME_SIZE // 2)
            oy = int(self.y - self._FRAME_SIZE // 2)
            screen.blit(frame, (ox, oy))


# ═══════════════════════════════════════════════════════
#  TOWER HUNTER TITAN — chuyên phá tháp (siege)
# ═══════════════════════════════════════════════════════

class TowerHunter(Titan):
    """Titan công thành — sinh ra để hạ Tower trước khi vào HQ.

    Strategy: `TowerHunterStrategy` cố định. Target là Tower → damage ×1.5,
    dtype='siege'. Target khác → damage ×1.0.

    Visual: `Assets/Titan/towerhunter.png` cố định.
      Walk/Run/Attack — layout chuẩn (rows 8-11 / 38-41 / 12-15).
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = 1500
    _DEFAULT_SPEED           = 70.0
    _DEFAULT_DAMAGE          = 70
    _DEFAULT_ATTACK_RANGE    = 30.0
    _DEFAULT_ATTACK_COOLDOWN = 0.75

    # ── Sprite layout ────────────────────────────────────────────
    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _ATTACK_FRAMES = 6
    _FRAME_SIZE    = 64
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 18

    _SPRITE_FILE = 'towerhunter.png'

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)

        # ── Hai strategy thường trực — switch tùy theo target ──
        #   • `_heavy_strategy`  : đòn mặc định cho mọi mục tiêu thường.
        #   • `_siege_strategy`  : đòn chuyên dụng — chỉ dùng khi đánh Tower.
        # Vì sao tạo sẵn 2 instance thay vì `new` mỗi frame?
        #   Tránh GC/allocation trong vòng lặp game; cũng cho phép strategy
        #   giữ state riêng (cooldown, charge…) nếu sau này mở rộng.
        self._heavy_strategy   = HeavyStrikeStrategy()
        self._siege_strategy   = TowerHunterStrategy()
        # Khởi đầu = Heavy (chưa biết target là gì); update() sẽ switch.
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
        """Switch strategy theo loại target hiện tại, rồi delegate base.update.

        Quy ước (theo yêu cầu balance):
            • Target là Tower (`entity_type == 'tower'`)
                → dùng TowerHunterStrategy (siege, ×1.5, dtype='siege').
            • Mọi target khác (soldier, commander, wall, hq, titan…)
                → fallback HeavyStrikeStrategy (×3.0, dtype='heavy').

        Ai gọi:
            Game loop mỗi frame. Base `Titan.update()` sẽ tự tìm target,
            tự đánh — ta chỉ cần đảm bảo `_attack_strategy` trỏ đúng
            instance TRƯỚC khi base gọi `execute()`.
        """
        # _target được base.update() refresh; nhưng ngay đầu update này
        # nó có thể là target của frame trước — vẫn đúng vì:
        #   1. Nếu target cũ còn sống & trong tầm → frame này đánh tiếp,
        #      strategy đã match từ frame trước.
        #   2. Nếu target đổi giữa frame → frame sau lập tức bắt được.
        target = getattr(self, '_target', None)
        if target is not None and getattr(target, 'entity_type', '') == 'tower':
            self._attack_strategy = self._siege_strategy
        else:
            self._attack_strategy = self._heavy_strategy

        super().update(dt)

    def _load_sprite(self) -> None:
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Titan', self._SPRITE_FILE,
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
        elif self._is_moving:
            row = self._WALK_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (self._is_moving or self._is_attacking) else 0
        frame = self._get_frame(row, col)

        if frame is not None:
            ox = int(self.x - self._FRAME_SIZE // 2)
            oy = int(self.y - self._FRAME_SIZE // 2)
            screen.blit(frame, (ox, oy))


# ═══════════════════════════════════════════════════════
#  SOLDIER HUNTER TITAN — chuyên săn lính (splash AoE)
# ═══════════════════════════════════════════════════════

class SoldierHunter(Titan):
    """Titan to xác cầm lưỡi hiểm — săn lính, gây splash AoE.

    Strategy: `SoldierHunterStrategy(splash_radius=self._attack_range)` —
    vùng cleave AoE bằng đúng tầm đánh, quét MỌI loại entity trong vùng.

    Cơ chế:
        • Target chính → damage ×1.0, dtype='normal'
        • Soldier trong 60px quanh target → damage ×0.5, dtype='aoe'

    Visual: `Assets/Titan/soldierhunter.png` — KÍCH THƯỚC ĐẶC BIỆT (1152×4224).
      Walk (64×64)  : rows 8 / 9 / 10 / 11   — 9 frame
      Run  (64×64)  : rows 38 / 39 / 40 / 41 — 8 frame
      Attack (192×192) : pixel-y 3456 / 3648 / 3840 / 4032 — 6 frame
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = 1500
    _DEFAULT_SPEED           = 70.0
    _DEFAULT_DAMAGE          = 70
    _DEFAULT_ATTACK_RANGE    = 40.0   # lưỡi hiểm vươn xa
    _DEFAULT_ATTACK_COOLDOWN = 0.75

    # ── Sprite layout (walk/run 64×64) ───────────────────────────
    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:    dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _FRAME_SIZE    = 64
    _ANIM_FPS      = 10

    # ── Attack — frame lớn 192×192 ───────────────────────────────
    _ATTACK_FRAME_SIZE = 192
    _ATTACK_FRAMES     = 6
    _ATTACK_FPS        = 20
    _ATTACK_Y:    dict = {0: 3456, 1: 3648, 2: 3840, 3: 4032}

    _SPRITE_FILE = 'soldierhunter.png'

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)

        # ── Hai strategy thường trực — switch theo target ──
        #   • `_heavy_strategy`   : đòn mặc định cho mọi target không phải lính.
        #   • `_soldier_strategy` : đòn AOE chuyên săn lính (splash 'aoe').
        # Lý do tạo sẵn 2 instance: tránh allocation mỗi frame trong vòng
        # lặp game; mỗi strategy có thể giữ state riêng nếu mở rộng sau này.
        self._heavy_strategy   = HeavyStrikeStrategy()
        # Splash AoE = tầm đánh (`_attack_range`) để teammate thấy
        # "vùng cleave đồng bộ với tầm đánh". Khi balance chỉnh
        # `_DEFAULT_ATTACK_RANGE`, splash cũng tự nới theo.
        self._soldier_strategy = SoldierHunterStrategy(
            splash_radius=self._attack_range,
        )
        # Khởi đầu = Heavy; update() sẽ switch khi nhìn thấy target soldier.
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
        """Switch strategy theo loại target hiện tại, rồi delegate base.update.

        Quy ước (theo yêu cầu balance):
            • Target là lính (`entity_type == 'soldier'`)
                → dùng SoldierHunterStrategy (AOE quanh lính, dtype='soldier'
                  cho đòn chính, 'aoe' cho splash).
            • Mọi target khác (tower, wall, commander, hq, titan…)
                → fallback HeavyStrikeStrategy (×3.0, dtype='heavy').

        Ai gọi:
            Game loop mỗi frame. Base `Titan.update()` tự tìm target và tự
            đánh — chúng ta chỉ đảm bảo `_attack_strategy` đã trỏ đúng
            instance TRƯỚC khi base gọi `execute()` trên target.
        """
        target = getattr(self, '_target', None)
        if target is not None and getattr(target, 'entity_type', '') == 'soldier':
            self._attack_strategy = self._soldier_strategy
        else:
            self._attack_strategy = self._heavy_strategy

        super().update(dt)

    def _load_sprite(self) -> None:
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Titan', self._SPRITE_FILE,
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
                afs = self._ATTACK_FRAME_SIZE
                ox = int(self.x - afs // 2)
                oy = int(self.y - afs // 2)
                screen.blit(frame, (ox, oy))
        else:
            if self._is_moving and self._is_running:
                row = self._RUN_ROWS[self._direction]
            else:
                row = self._WALK_ROWS[self._direction]
            col = self._anim_col if self._is_moving else 0
            frame = self._get_frame(row, col)
            if frame is not None:
                fs = self._FRAME_SIZE
                ox = int(self.x - fs // 2)
                oy = int(self.y - fs // 2)
                screen.blit(frame, (ox, oy))


# ═══════════════════════════════════════════════════════
#  KAMIKAZE TITAN — suicide bomber (clustering + explode)
# ═══════════════════════════════════════════════════════

class Kamikaze(Titan):
    """Titan tự sát — chạy đến cụm soldier rồi phát nổ.

    Hành vi (3 giai đoạn):
      1. **Idle/Walk**: không có soldier trong `_DETECT_RADIUS` → walk thường.
      2. **Run** (locked): target = clustering pick (soldier có nhiều đồng đội
         nhất trong `_CLUSTER_RADIUS`); tốc độ `_speed × _RUN_SPEED_MULT`.
      3. **Pause + Explode**: vào `_EXPLODE_RADIUS` → pause `_PRE_EXPLODE_PAUSE`
         giây + flash đỏ → `Explosion.execute()` → tự chết.

    Death-explode: HP về 0 trước khi pause kết thúc → vẫn nổ tại chỗ.

    Visual: `Assets/Special/kamikaze.png` (frame 64×64).
      Walk : rows 8 / 9 / 10 / 11   — 9 frame
      Run  : rows 38 / 39 / 40 / 41 — 8 frame
      Idle (khi pause): rows 23-26  — 2 frame, FPS chậm (4)

    Strategy: `Explosion(damage_main, damage_splash, radius, knockback)`.
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = 1000
    _DEFAULT_SPEED           = 80.0
    _DEFAULT_DAMAGE          = 100    # damage base (Explosion dùng cố định)
    _DEFAULT_ATTACK_RANGE    = 60.0  # = _EXPLODE_RADIUS (khoảng kích nổ)
    _DEFAULT_ATTACK_COOLDOWN = 1.0

    # ── Sprite layout ────────────────────────────────────────────
    _SPRITE_FILE = 'kamikaze.png'
    _FRAME_SIZE  = 64

    _WALK_ROWS: dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:  dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _IDLE_ROWS: dict = {0: 26, 1: 23, 2: 24, 3: 25}   # khi pause trước nổ
    _IDLE_FRAMES = 2
    _IDLE_FPS    = 4
    _WALK_FRAMES = 9
    _RUN_FRAMES  = 8
    _ANIM_FPS    = 10

    # ── Behavior radii ───────────────────────────────────────────
    _DETECT_RADIUS     = 300.0   # bán kính phát hiện soldier để chạy
    _EXPLODE_RADIUS    = 60.0    # khi target vào đây → pause + explode
    _CLUSTER_RADIUS    = 60.0    # đếm đồng đội quanh ứng viên target
    _RUN_SPEED_MULT    = 2.0
    _PRE_EXPLODE_PAUSE = 1.0     # giây pause trước khi nổ

    # ── Explosion params ─────────────────────────────────────────
    # Damage main/splash KHÔNG còn khai báo ở đây — Explosion strategy tự
    # scale theo `_DEFAULT_DAMAGE` (50) × `_DEFAULT_DAMAGE_MULT` (6.7) = 335.
    # Splash mặc định = main × 0.5. Muốn đổi balance: chỉnh `_DEFAULT_DAMAGE`
    # ở trên hoặc truyền `damage_mult=` / `splash_ratio=` khi khởi tạo Explosion.
    _EXP_AOE_RADIUS    = 80.0
    _EXP_KNOCKBACK     = 80.0
    _EXP_SPLASH_RATIO  = 0.75     # splash = main × ratio

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)
        self._attack_strategy = Explosion(
            splash_ratio=self._EXP_SPLASH_RATIO,
            radius=self._EXP_AOE_RADIUS,
            knockback=self._EXP_KNOCKBACK,
        )

        self._target = None        # soldier locked (clustering pick)

        self._direction   = 2
        self._is_moving   = False
        self._is_running  = False
        self._anim_col    = 0
        self._anim_timer  = 0.0

        # Pre-explode pause state
        self._is_pausing      = False
        self._pause_timer     = 0.0
        self._flash_intensity = 0.0

        # Death/explode guard — chỉ nổ 1 lần
        self._has_exploded = False

        self._sprite_sheet = None

    def _load_sprite(self) -> None:
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Special', self._SPRITE_FILE,
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

    # ── Target selection — clustering ────────────────────────────

    def _pick_clustering_target(self, candidates: list):
        """Chọn soldier có nhiều đồng đội nhất trong `_CLUSTER_RADIUS`.

        Tiebreaker: cùng count → gần kamikaze nhất.
        """
        best = None
        best_count = -1
        best_dist  = float('inf')
        for s in candidates:
            if not getattr(s, 'is_alive', True):
                continue
            count = 0
            for other in candidates:
                if other is s or not getattr(other, 'is_alive', True):
                    continue
                d = ((s.x - other.x) ** 2 + (s.y - other.y) ** 2) ** 0.5
                if d <= self._CLUSTER_RADIUS:
                    count += 1
            d_self = ((s.x - self.x) ** 2 + (s.y - self.y) ** 2) ** 0.5
            if count > best_count or (count == best_count and d_self < best_dist):
                best_count = count
                best_dist  = d_self
                best       = s
        return best

    def _refind_target(self) -> None:
        """Tìm target mới trong detect radius. None nếu không còn soldier."""
        from systems.world_query import WorldQuery
        soldiers = WorldQuery.find_in_radius(
            self.x, self.y, self._DETECT_RADIUS, 'soldier'
        )
        self._target = self._pick_clustering_target(soldiers)

    # ── Public API cho demo/AI ───────────────────────────────────

    def trigger_explosion(self) -> bool:
        """Chuyển sang pause rồi nổ. Trả False nếu đang pause / đã nổ."""
        if self._is_pausing or self._has_exploded:
            return False
        self._is_pausing      = True
        self._pause_timer     = self._PRE_EXPLODE_PAUSE
        self._flash_intensity = 0.0
        self._is_moving       = False
        self._is_running      = False
        return True

    def _release_explosion(self) -> None:
        """Gọi Explosion strategy + đánh dấu đã nổ + chết."""
        if self._has_exploded:
            return
        self._has_exploded = True
        if self._attack_strategy is not None:
            self._attack_strategy.execute(self, self._target)
        if self.is_alive:
            self.is_alive = False

    def update_anim(self, dt: float) -> None:
        """Cập nhật frame animation + pause/flash."""
        if self._has_exploded:
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

    # ── AI tick — gọi từ demo manual ─────────────────────────────

    def ai_tick(self, dt: float) -> None:
        """1 tick AI manual — chỉ dùng khi CHECK/* không gắn AI.py."""
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
        """Death-explode: nếu chết trước khi pause kết thúc, vẫn nổ tại chỗ."""
        if not self._has_exploded:
            self._release_explosion()
        super().on_death()

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        if self._has_exploded:
            return    # đã nổ → không vẽ sprite kamikaze nữa

        self._load_sprite()

        if self._is_pausing:
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
            fs = self._FRAME_SIZE
            ox = int(self.x - fs // 2)
            oy = int(self.y - fs // 2)
            screen.blit(frame, (ox, oy))

            # Outline đỏ nhấp nháy quanh sprite khi đang pause.
            if self._is_pausing and self._flash_intensity > 0:
                t     = self._flash_intensity
                freq  = 6 + t * 14
                phase = (1.0 - self._pause_timer / self._PRE_EXPLODE_PAUSE) * freq * math.pi
                pulse = abs(math.sin(phase))
                alpha = int(220 * t * pulse)
                if alpha > 0:
                    mask    = pygame.mask.from_surface(frame)
                    outline = mask.outline()
                    if outline:
                        glow_color = (255, 60, 40, alpha)
                        glow_surf  = pygame.Surface((fs, fs), pygame.SRCALPHA)
                        pts = [(px, py) for (px, py) in outline]
                        if len(pts) >= 2:
                            pygame.draw.lines(glow_surf, glow_color, True, pts, 2)
                        screen.blit(glow_surf, (ox, oy))
