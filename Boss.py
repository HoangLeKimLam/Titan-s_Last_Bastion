# characters/titans/boss.py
"""Boss.py — Toàn bộ tham số + thân xác (sprite/animation) của Boss.

Trách nhiệm: như `Titan.py` nhưng cho 3 boss — ColossalTitan (Boss màn 3),
BeastTitan (Boss màn 4), FoundingTitan (Final Boss).

Mỗi Boss khai báo class constants:
    _DEFAULT_HP / _DEFAULT_SPEED / _DEFAULT_DAMAGE / _DEFAULT_ATTACK_RANGE
    / _DEFAULT_ATTACK_COOLDOWN — như Titan thường.
+ Tham số kỹ năng riêng (cooldown, AoE, damage, animation duration):
    Colossal: _STEAM_COOLDOWN, _JUMP_COOLDOWN, _STEAM_PARTICLE_COUNT, ...
    Beast   : _THROW_COOLDOWN, _ROCK_VELOCITY, _ROCK_AOE_RADIUS, ...
    Founding: _SUMMON_WAVE_COOLDOWN, _SUMMON_TOTAL, _P1_HP_RATIO, ...

Tất cả tham số có thể override qua `config` dict truyền vào `__init__`,
hoặc sửa trực tiếp class const để áp dụng toàn dự án.
"""
import os
import math
import random
import pygame

from characters.titans.titan import Titan
from characters.titans.attackstrategy import (
    GroundSlamStrategy,
    HeavyStrikeStrategy,
    RockProjectile,
    HeatParticle,
)

# RockProjectile và HeatParticle vẫn ở AttackStrategy.py (NHÓM 6: Projectile
# / Particle phụ trợ). Boss.py import lại để dùng trong skill animation;
# tên được re-export ở đây để demo cũ (`from Boss import HeatParticle`)
# tiếp tục chạy không đổi.


# ═══════════════════════════════════════════════════════
#  COLOSSAL TITAN — Boss màn 3 (Steam Burst + Jump Stomp)
# ═══════════════════════════════════════════════════════

class ColossalTitan(Titan):
    """Boss màn 3 — to lớn, hai skill AoE: Steam Burst + Jump Stomp.

    Skill 1 — Steam Burst (`_steam_burst`):
        • Cooldown `_STEAM_COOLDOWN` giây
        • Vành khuyên annulus [`_STEAM_R_IN`, `_STEAM_R_OUT`] quanh Colossal
        • `_STEAM_PARTICLE_COUNT` particle chia đều quanh 360° + jitter
        • Mỗi particle: AoE `_STEAM_PARTICLE_AOE` tại spawn point
        • Lính: `_STEAM_FIRE_DMG` fire + BurnDoT + pushback
        • Tướng: `_STEAM_BURN_DMG` burn + BurnDoT
        • Standing `_STEAM_ANIM_DUR` giây

    Skill 2 — Jump Stomp (`_jump_stomp`):
        • Cooldown `_JUMP_COOLDOWN` giây
        • AoE `_STOMP_AOE` quanh Colossal
        • Tháp: stun `_STOMP_STUN_DUR` giây
        • Lính / Tướng: `_STOMP_DMG` damage 'stomp'
        • Standing `_JUMP_ANIM_DUR` giây

    Đòn basic: GroundSlamStrategy — damage target chính + stun tower
    trong `radius=160`.

    Visual: `Assets/Boss/clossal.png` (chú ý spelling). Frame 64×64.
      Walk    : rows 8-11   — 9 frame
      Steam   : rows 23-26  — 2 frame (loop)
      Jump    : rows 26-29  — 5 frame (loop)
      Attack  : rows 12-15  — 6 frame (vung tay melee 0.25s)
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = 2000
    _DEFAULT_SPEED           = 35.0     # to → đi chậm
    _DEFAULT_DAMAGE          = 50
    _DEFAULT_ATTACK_RANGE    = 120.0    # GroundSlam có radius
    _DEFAULT_ATTACK_COOLDOWN = 2.0

    # ── Sprite mapping ───────────────────────────────────────────
    _STEAM_ROWS:  dict = {0: 26, 1: 23, 2: 24, 3: 25}
    _JUMP_ROWS:   dict = {0: 26, 1: 27, 2: 28, 3: 29}
    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _IDLE_ROWS:   dict = {0: 26, 1: 23, 2: 24, 3: 25}   # col 0 tĩnh
    _FRAME_SIZE    = 64
    _STEAM_FRAMES  = 2
    _STOMP_FRAMES  = 5
    _WALK_FRAMES   = 9
    _ATTACK_FRAMES = 6
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 24                  # nhanh — 0.25s/đòn vung tay

    # ── Skill 1: Steam Burst ─────────────────────────────────────
    _STEAM_AOE              = 120        # tham chiếu HUD (không dùng damage)
    _STEAM_R_IN             = 40         # bán kính trong annulus
    _STEAM_R_OUT            = 140        # bán kính ngoài annulus
    _STEAM_PARTICLE_COUNT   = 200        # N particle chia đều quanh vòng
    _STEAM_PARTICLE_AOE     = 35         # bán kính damage tại mỗi spawn point
    _STEAM_FIRE_DMG         = 15         # damage lính khi bị steam
    _STEAM_BURN_DMG         = 15         # damage tướng khi bị steam
    _STEAM_COOLDOWN         = 8.0
    _STEAM_ANIM_DUR         = 3.0
    _BURN_DPS               = 5.0
    _BURN_DURATION          = 5.0

    # ── Skill 2: Jump Stomp ──────────────────────────────────────
    _STOMP_AOE              = 160
    _STOMP_STUN_DUR         = 3.5
    _STOMP_DMG              = 100
    _JUMP_COOLDOWN          = 15.0
    _JUMP_ANIM_DUR          = 1.5

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)
        self._attack_strategy = GroundSlamStrategy(
            radius=160, stun_duration=3.0)
        # Timer skill — bắt đầu = 0 (AI nạp sẵn cooldown sau).
        self._steam_timer    = 0.0
        self._steam_cooldown = self._STEAM_COOLDOWN
        self._jump_timer     = 0.0
        self._jump_cooldown  = self._JUMP_COOLDOWN

        # Particle system
        self._heat_particles: list = []

        # Animation state
        self._direction         = 2
        self._is_steaming       = False
        self._steam_anim_timer  = 0.0
        self._is_jumping        = False
        self._jump_anim_timer   = 0.0
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._is_moving         = False
        self._anim_col          = 0
        self._anim_timer        = 0.0

        self._sprite_sheet = None

    # ── Sprite helpers ───────────────────────────────────────────

    def _load_sprite(self) -> None:
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Boss', 'clossal.png')
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

    # ── Direction ────────────────────────────────────────────────

    def _compute_direction(self) -> int:
        """Tính hướng (0=N,1=W,2=S,3=E) từ vector titan→target."""
        target = self._find_best_target()
        if target is None:
            return self._direction
        dx = target.x - self.x
        dy = target.y - self.y
        if abs(dx) >= abs(dy):
            return 3 if dx >= 0 else 1
        return 2 if dy >= 0 else 0

    # ── Update (chế độ manual — không có AI ngoài) ───────────────

    def update(self, dt: float) -> None:
        # Particle hơi nóng luôn chạy.
        self._heat_particles = [
            p for p in self._heat_particles if p.update(dt)
        ]

        if self._is_steaming:
            self._steam_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % self._STEAM_FRAMES
            if self._steam_anim_timer <= 0:
                self._is_steaming = False
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
            return

        if self._is_jumping:
            self._jump_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % self._STOMP_FRAMES
            if self._jump_anim_timer <= 0:
                self._is_jumping = False
            return

        super().update(dt)

        self._steam_timer -= dt
        if self._steam_timer <= 0:
            self._steam_burst()
            self._steam_timer = self._steam_cooldown

        self._jump_timer -= dt
        if self._jump_timer <= 0:
            self._jump_stomp()
            self._jump_timer = self._jump_cooldown

        if self._is_moving:
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % self._WALK_FRAMES

    # ── Skill 1: Steam Burst ─────────────────────────────────────

    def _steam_burst(self) -> None:
        """Phun hơi nóng theo VÀNH KHUYÊN quanh Colossal.

        Hình học + Damage: xem class docstring + class const _STEAM_*.
        Dedupe target: 1 target chỉ ăn damage 1 lần dù bị nhiều particle phủ.
        """
        from systems.world_query import WorldQuery
        from patterns.decorator import BurnDecorator

        N = self._STEAM_PARTICLE_COUNT
        slice_angle = 2 * math.pi / N
        max_jitter  = slice_angle * 0.5
        aoe_r       = self._STEAM_PARTICLE_AOE

        damaged_soldiers   = set()
        damaged_commanders = set()

        for i in range(N):
            angle  = i * slice_angle + random.uniform(-max_jitter, max_jitter)
            radius = random.uniform(self._STEAM_R_IN, self._STEAM_R_OUT)
            sx = self.x + math.cos(angle) * radius
            sy = self.y + math.sin(angle) * radius

            self._heat_particles.append(HeatParticle(sx, sy))

            soldiers = WorldQuery.find_in_radius(
                cx=sx, cy=sy, radius=aoe_r, entity_type='soldier')
            for s in soldiers:
                if s in damaged_soldiers:
                    continue
                damaged_soldiers.add(s)
                s.take_damage(amount=self._STEAM_FIRE_DMG, dtype='fire')
                BurnDecorator(s, damage_per_sec=self._BURN_DPS,
                              duration=self._BURN_DURATION)
                s.take_damage(amount=0, dtype='pushback')

            commanders = WorldQuery.find_in_radius(
                cx=sx, cy=sy, radius=aoe_r, entity_type='commander')
            for c in commanders:
                if c in damaged_commanders:
                    continue
                damaged_commanders.add(c)
                c.take_damage(amount=self._STEAM_BURN_DMG, dtype='burn')
                BurnDecorator(c, damage_per_sec=self._BURN_DPS,
                              duration=self._BURN_DURATION)

        self._is_steaming      = True
        self._steam_anim_timer = self._STEAM_ANIM_DUR
        self._anim_col         = 0

    # ── Skill 2: Jump Stomp ──────────────────────────────────────

    def _jump_stomp(self) -> None:
        """Nhảy tại chỗ rồi đáp đất: stun tháp + damage lính & tướng."""
        from systems.world_query import WorldQuery

        towers = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self._STOMP_AOE, entity_type='tower')
        for t in towers:
            t.stun(self._STOMP_STUN_DUR)

        soldiers = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self._STOMP_AOE, entity_type='soldier')
        for s in soldiers:
            s.take_damage(amount=self._STOMP_DMG, dtype='stomp')

        commanders = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self._STOMP_AOE, entity_type='commander')
        for c in commanders:
            c.take_damage(amount=self._STOMP_DMG, dtype='stomp')

        self._is_jumping      = True
        self._jump_anim_timer = self._JUMP_ANIM_DUR
        self._anim_col        = 0

    # ── Attack animation (melee vung tay) ────────────────────────

    def trigger_attack(self, target=None) -> bool:
        """Kích hoạt animation vung tay melee — 0.25s.

        Vì sao Colossal có trigger_attack?
            Khi AI gọi đòn basic (GroundSlamStrategy) ở khoảng cách gần,
            người chơi cần thấy visual vung tay — giống Armored sau khi
            vỡ giáp. Animation chỉ kéo dài 0.25s, KHÔNG chặn cooldown
            skill Steam/Stomp.
        """
        if self._is_attacking or self._is_steaming or self._is_jumping:
            return False
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0
        if target is not None:
            dx = target.x - self.x
            dy = target.y - self.y
            if abs(dx) > abs(dy):
                self._direction = 3 if dx > 0 else 1
            else:
                self._direction = 2 if dy > 0 else 0
        return True

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        self._load_sprite()

        if self._is_steaming:
            frame = self._get_frame(self._STEAM_ROWS[self._direction], self._anim_col)
        elif self._is_jumping:
            frame = self._get_frame(self._JUMP_ROWS[self._direction], self._anim_col)
        elif self._is_attacking:
            frame = self._get_frame(self._ATTACK_ROWS[self._direction], self._anim_col)
        elif self._is_moving:
            frame = self._get_frame(self._WALK_ROWS[self._direction], self._anim_col)
        else:
            frame = self._get_frame(self._IDLE_ROWS[self._direction], 0)

        if frame is not None:
            ox = int(self.x - self._FRAME_SIZE // 2)
            oy = int(self.y - self._FRAME_SIZE // 2)
            screen.blit(frame, (ox, oy))
        else:
            super().draw(screen)

        # Vẽ particles hơi nóng lên trên sprite
        for p in self._heat_particles:
            p.draw(screen)


# ═══════════════════════════════════════════════════════
#  BEAST TITAN — Boss màn 4 (Rock Throw + parabol AoE)
# ═══════════════════════════════════════════════════════

class BeastTitan(Titan):
    """Boss màn 4 — ném đá tầm xa, ưu tiên phá tháp trước khi tiến vào HQ.

    Skill ném đá (`trigger_attack(target)`):
      • Range: `_THROW_RANGE` (ngoài tầm → walk lại gần)
      • Vật lý: velocity adaptive, angle `_ROCK_ANGLE_DEG`, gravity `_ROCK_GRAVITY`
      • Visual đá: spritesheet Rock Pile (frame 85×85 tại row=9, col=5)
      • Tay phát sinh: `_HAND_OFFSET` + `_HAND_LIFT` px
      • Release tại frame `_ROCK_RELEASE_FRAME`/6 (~0.125s)
      • Damage AoE `_ROCK_AOE_RADIUS` px khi rock land: main + splash, dtype='rock'
      • Cooldown `_THROW_COOLDOWN` giây

    Adaptive velocity (`_release_rock`): tính v theo công thức parabol
    `v = sqrt(R · g / sin(2θ))` để đáp đúng target, clamp [`_ROCK_VELOCITY_MIN`,
    `_ROCK_VELOCITY_MAX`].

    Visual: `Assets/Boss/beast.png` (frame 64×64).
      Walk/Run/Attack — layout chuẩn rows 8-11 / 38-41 / 12-15.
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = 1500
    _DEFAULT_SPEED           = 50.0
    _DEFAULT_DAMAGE          = 40
    _DEFAULT_ATTACK_RANGE    = 350.0    # = _THROW_RANGE
    _DEFAULT_ATTACK_COOLDOWN = 2.0      # đồng nhất _THROW_COOLDOWN

    # ── Sprite layout ────────────────────────────────────────────
    _SPRITE_FILE   = 'beast.png'
    _FRAME_SIZE    = 64
    _WALK_ROWS:    dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:     dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS:  dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _ATTACK_FRAMES = 6
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 24      # nhanh — 0.25s/đòn ném

    # ── Skill ném đá ─────────────────────────────────────────────
    _THROW_RANGE          = 350.0
    THROW_RANGE           = _THROW_RANGE   # alias public cho AI/demo
    _THROW_COOLDOWN       = 2.0
    _ROCK_VELOCITY        = 580.0    # fallback nếu công thức adaptive fail
    _ROCK_VELOCITY_MIN    = 200.0
    _ROCK_VELOCITY_MAX    = 800.0
    _ROCK_ANGLE_DEG       = 15.0
    _ROCK_GRAVITY         = 600.0
    _ROCK_DAMAGE_MAIN     = 80
    _ROCK_DAMAGE_SPLASH   = 40
    _ROCK_AOE_RADIUS      = 80.0
    _ROCK_KNOCKBACK       = 40.0
    _ROCK_RELEASE_FRAME   = 3
    _HAND_OFFSET          = 24.0
    _HAND_LIFT            = 12.0

    # ── Rock sprite — sheet Rock Pile (510×2550) ─────────────────
    _ROCK_SHEET_FILE   = os.path.join('Assets', 'Rock', 'Rock Pile - Spritesheet.png')
    _ROCK_FRAME_SIZE   = 85
    _ROCK_FRAME_COL    = 5
    _ROCK_FRAME_ROW    = 9

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)
        self._throw_timer    = 0.0
        self._throw_cooldown = self._THROW_COOLDOWN

        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._anim_col          = 0
        self._anim_timer        = 0.0

        self._rock_released_this_attack = False
        self._attack_target             = None

        self._sprite_sheet = None
        self._rock_frame   = None

        self._rocks: list = []

    # ── Sprite helpers ───────────────────────────────────────────

    def _load_sprite(self) -> None:
        if self._sprite_sheet is None:
            try:
                path = os.path.join(
                    os.path.dirname(__file__),
                    'Assets', 'Boss', self._SPRITE_FILE)
                self._sprite_sheet = pygame.image.load(path).convert_alpha()
            except Exception:
                self._sprite_sheet = None
        if self._rock_frame is None:
            try:
                path = os.path.join(
                    os.path.dirname(__file__),
                    self._ROCK_SHEET_FILE)
                sheet = pygame.image.load(path).convert_alpha()
                fs = self._ROCK_FRAME_SIZE
                region = pygame.Rect(
                    self._ROCK_FRAME_COL * fs,
                    self._ROCK_FRAME_ROW * fs,
                    fs, fs)
                self._rock_frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
                self._rock_frame.blit(sheet, (0, 0), region)
            except Exception:
                self._rock_frame = None

    def _get_frame(self, row: int, col: int = 0):
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    # ── Public API cho demo/AI ───────────────────────────────────

    def trigger_attack(self, target) -> bool:
        """Kích hoạt animation ném đá. Rock release tại frame `_ROCK_RELEASE_FRAME`."""
        if self._is_attacking:
            return False
        if target is None or not getattr(target, 'is_alive', True):
            return False

        self._is_attacking              = True
        self._attack_anim_timer         = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col                  = 0
        self._anim_timer                = 0.0
        self._rock_released_this_attack = False
        self._attack_target             = target

        dx = target.x - self.x
        dy = target.y - self.y
        if abs(dx) > abs(dy):
            self._direction = 3 if dx > 0 else 1
        else:
            self._direction = 2 if dy > 0 else 0
        return True

    def update_anim(self, dt: float) -> None:
        """Cập nhật frame animation + bay đá. Gọi từ demo thay cho update()."""
        for r in self._rocks:
            r.update(dt)
        self._rocks = [r for r in self._rocks if r.alive]

        if self._is_attacking:
            self._attack_anim_timer -= dt
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES

            if (not self._rock_released_this_attack
                    and self._anim_col >= self._ROCK_RELEASE_FRAME):
                self._release_rock()
                self._rock_released_this_attack = True

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

    def _release_rock(self) -> None:
        """Spawn RockProjectile từ tay beast hướng về `_attack_target`.

        Adaptive velocity: `v = sqrt(R · g / sin(2θ))` để đáp đúng target,
        clamp [`_ROCK_VELOCITY_MIN`, `_ROCK_VELOCITY_MAX`].
        """
        target = self._attack_target
        if target is None:
            return
        dx = target.x - self.x
        dy = target.y - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0:
            hx = self.x + (dx / dist) * self._HAND_OFFSET
            hy = self.y + (dy / dist) * self._HAND_OFFSET
        else:
            hx, hy = self.x, self.y
        hy -= self._HAND_LIFT

        rdx = target.x - hx
        rdy = target.y - hy
        range_px = (rdx * rdx + rdy * rdy) ** 0.5

        angle_rad = math.radians(self._ROCK_ANGLE_DEG)
        sin_2theta = math.sin(2 * angle_rad)
        if sin_2theta > 0 and range_px > 0:
            v = math.sqrt(range_px * self._ROCK_GRAVITY / sin_2theta)
            velocity = max(self._ROCK_VELOCITY_MIN,
                           min(self._ROCK_VELOCITY_MAX, v))
        else:
            velocity = self._ROCK_VELOCITY

        rock = RockProjectile(
            start_x=hx, start_y=hy, target=target,
            velocity=velocity,
            angle_deg=self._ROCK_ANGLE_DEG,
            gravity=self._ROCK_GRAVITY,
            damage_main=self._ROCK_DAMAGE_MAIN,
            damage_splash=self._ROCK_DAMAGE_SPLASH,
            aoe_radius=self._ROCK_AOE_RADIUS,
            knockback_dist=self._ROCK_KNOCKBACK,
        )
        self._rocks.append(rock)

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

        for r in self._rocks:
            r.draw(screen, self._rock_frame)

    # ── Update tự hành (chế độ manual) ───────────────────────────

    def update(self, dt: float) -> None:
        """AI nội bộ: tower trong tầm → trigger_attack; xa → walk lại gần."""
        self.update_anim(dt)
        if not self.is_alive:
            return
        if self._is_attacking:
            self._is_moving = False
            return

        self._throw_timer -= dt
        nearest_tower = self._find_nearest_tower()
        if nearest_tower is None:
            self._is_moving = False
            return

        dist = self._distance_to(nearest_tower)
        if dist <= self._THROW_RANGE:
            self._is_moving = False
            if self._throw_timer <= 0:
                if self.trigger_attack(nearest_tower):
                    self._throw_timer = self._throw_cooldown
        else:
            self._is_moving = True
            dx = nearest_tower.x - self.x
            dy = nearest_tower.y - self.y
            if abs(dx) > abs(dy):
                self._direction = 3 if dx > 0 else 1
            else:
                self._direction = 2 if dy > 0 else 0
            self._move_toward(nearest_tower, dt)

    def _rock_volley(self, tower):
        """Backward-compat alias — gọi trigger_attack."""
        self.trigger_attack(tower)

    def _find_nearest_tower(self):
        from systems.world_query import WorldQuery
        return WorldQuery.find_nearest(
            cx=self.x, cy=self.y, entity_type='tower')


# ═══════════════════════════════════════════════════════
#  FOUNDING TITAN — Final Boss (3 Phase + Auto Summon)
# ═══════════════════════════════════════════════════════

class FoundingTitan(Titan):
    """Final Boss màn 5 — 3 phase HP-based, sticky summon-lock.

    Phase logic (`_check_phase`):
      • HP > `_P1_HP_RATIO` (60%) → Phase 1: HeavyStrike (range 80, cd 3s)
      • `_P3_HP_RATIO` (20%) < HP ≤ `_P1_HP_RATIO` → Phase 2: auto-summon
      • HP ≤ `_P3_HP_RATIO` → Phase 3: TẮT summon vĩnh viễn (sticky lock)

    Cờ sticky `_summon_locked` latches `True` khi HP chạm ≤ 20% lần đầu —
    one-way transition (dù HP có hồi lên > 20%, summon không bật lại).

    Summon spec (Phase 2):
      • Mỗi đợt `_SUMMON_TOTAL` minion, random từ `_MINION_POOL`
      • Vòng tròn bán kính `_SUMMON_RADIUS`
      • Animation 1s + hold col=5 `_SUMMON_PAUSE` giây → spawn
      • Cooldown `_SUMMON_WAVE_COOLDOWN` giây giữa đợt

    Visual: `Assets/Boss/founding.png` (frame 64×64).
      Walk/Attack/Summon — rows lần lượt 8-11 / 12-15 / 0-3.
      KHÔNG có Run (Founding chỉ Walk khi di chuyển).
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = 800     # thấp hơn game thật để dễ test phase
    _DEFAULT_SPEED           = 50.0
    _DEFAULT_DAMAGE          = 50
    _DEFAULT_ATTACK_RANGE    = 80.0   # = _ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = 3.0    # = _ATTACK_COOLDOWN

    # ── Sprite layout — KHÔNG có Run ─────────────────────────────
    _SPRITE_FILE   = 'founding.png'
    _FRAME_SIZE    = 64
    _WALK_ROWS:    dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _ATTACK_ROWS:  dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _SUMMON_ROWS:  dict = {0: 0,  1: 1,  2: 2,  3: 3}    # user tự chỉnh mapping
    _WALK_FRAMES   = 9
    _ATTACK_FRAMES = 6
    _SUMMON_FRAMES = 6
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 10
    _SUMMON_FPS    = 6
    _SUMMON_PAUSE  = 2.0

    # ── Phase / HP thresholds ────────────────────────────────────
    _P1_HP_RATIO   = 0.6           # > 0.6 = P1
    _P3_HP_RATIO   = 0.2           # ≤ 0.2 = P3 (sticky)

    # ── Phase 1 attack ───────────────────────────────────────────
    _ATTACK_RANGE    = 80.0
    _ATTACK_COOLDOWN = 3.0

    # ── Phase 2 summon ───────────────────────────────────────────
    _SUMMON_TOTAL         = 10
    _SUMMON_RADIUS        = 180.0
    _SUMMON_WAVE_COOLDOWN = 10.0   # giây sau pause trước đợt kế

    # Pool: mỗi đợt random `_SUMMON_TOTAL` con từ 8 LOẠI titan
    _MINION_POOL = (
        'regular2', 'regular4', 'regular5', 'regular6', 'regular7',
        'wolf', 'towerhunter', 'soldierhunter',
    )

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        super().__init__(x, y, config)
        self._attack_strategy = HeavyStrikeStrategy(damage_mult=2.0)

        self._phase          = 1
        self._summon_locked  = False

        # Animation state — KHÔNG có Run
        self._direction          = 2
        self._is_moving          = False
        self._is_attacking       = False
        self._is_summoning       = False
        self._summon_pause_timer = 0.0
        self._summon_released    = False
        self._anim_col           = 0
        self._anim_timer         = 0.0
        self._attack_anim_timer  = 0.0
        self._summon_anim_timer  = 0.0

        # Cooldown timers
        self._attack_cd_timer = 0.0
        self._summon_cd_timer = 0.0

        self._sprite_sheet = None

        # Danh sách minion đã spawn
        self._summoned_minions: list = []

    # ── Sprite helpers ───────────────────────────────────────────

    def _load_sprite(self) -> None:
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Boss', self._SPRITE_FILE)
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

    # ── Phase logic ──────────────────────────────────────────────

    def _check_phase(self) -> None:
        """Cập nhật `_phase` + cờ sticky `_summon_locked` theo HP."""
        ratio = self._hp / self._max_hp if self._max_hp > 0 else 0
        if ratio <= self._P3_HP_RATIO:
            self._summon_locked = True

        if ratio > self._P1_HP_RATIO:
            self._phase = 1
        elif self._summon_locked:
            self._phase = 3
        elif ratio > self._P3_HP_RATIO:
            self._phase = 2
        else:
            self._phase = 3

    # ── Public API cho demo/AI ───────────────────────────────────

    def trigger_attack(self, target=None) -> bool:
        """Phase 1/3 attack — HeavyStrike. LUÔN chạy animation.

        Damage CHỈ áp khi target hợp lệ và trong `_ATTACK_RANGE`.
        """
        if self._is_attacking or self._is_summoning:
            return False
        if self._attack_cd_timer > 0:
            return False

        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0
        self._attack_cd_timer   = self._ATTACK_COOLDOWN

        if target is not None:
            dx, dy = target.x - self.x, target.y - self.y
            if abs(dx) > abs(dy):
                self._direction = 3 if dx > 0 else 1
            else:
                self._direction = 2 if dy > 0 else 0

        if (target is not None
                and getattr(target, 'is_alive', True)
                and self._distance_to(target) <= self._ATTACK_RANGE):
            self._attack_strategy.execute(self, target)

        return True

    def start_summon(self) -> bool:
        """Phase 2 only — kích hoạt animation summon."""
        if self._phase != 2:
            return False
        if self._is_attacking or self._is_summoning or self._summon_locked:
            return False
        if self._summon_cd_timer > 0:
            return False

        self._is_summoning       = True
        self._summon_anim_timer  = self._SUMMON_FRAMES / self._SUMMON_FPS
        self._summon_pause_timer = 0.0
        self._summon_released    = False
        self._anim_col           = 0
        self._anim_timer         = 0.0
        return True

    def _release_summon(self) -> None:
        """Spawn `_SUMMON_TOTAL` minion thành vòng tròn quanh founding.

        Mỗi minion = random `_MINION_POOL` → đúng CLASS Titan tương ứng,
        kế thừa đầy đủ strategy + khả năng tấn công riêng.
        """
        from characters.titans.titan import (
            RegularTitan, Wolf, TowerHunter, SoldierHunter,
        )

        config = {'hp': 200, 'speed': 60.0, 'damage': 10}
        slice_angle = 2 * math.pi / self._SUMMON_TOTAL

        for idx in range(self._SUMMON_TOTAL):
            angle = idx * slice_angle
            mx = self.x + math.cos(angle) * self._SUMMON_RADIUS
            my = self.y + math.sin(angle) * self._SUMMON_RADIUS

            kind = random.choice(self._MINION_POOL)
            if kind.startswith('regular'):
                minion = RegularTitan(mx, my, config)
                minion._variant = int(kind[len('regular'):])
            elif kind == 'wolf':
                minion = Wolf(mx, my, config)
            elif kind == 'towerhunter':
                minion = TowerHunter(mx, my, config)
            else:  # 'soldierhunter'
                minion = SoldierHunter(mx, my, config)

            minion._sprite_sheet = None
            minion._direction = self._direction
            self._summoned_minions.append(minion)

    # ── Update animation ─────────────────────────────────────────

    def update_anim(self, dt: float) -> None:
        """Cập nhật animation + summon pause/release. Gọi từ demo."""
        if self._attack_cd_timer > 0:
            self._attack_cd_timer = max(0.0, self._attack_cd_timer - dt)
        if self._summon_cd_timer > 0:
            self._summon_cd_timer = max(0.0, self._summon_cd_timer - dt)

        self._check_phase()

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

        if self._is_summoning:
            if self._summon_anim_timer > 0:
                self._summon_anim_timer -= dt
                self._anim_timer += dt
                if self._anim_timer >= 1.0 / self._SUMMON_FPS:
                    self._anim_timer -= 1.0 / self._SUMMON_FPS
                    if self._anim_col < self._SUMMON_FRAMES - 1:
                        self._anim_col += 1
                if (self._anim_col >= self._SUMMON_FRAMES - 1
                        and self._summon_anim_timer <= 0):
                    self._summon_anim_timer  = 0.0
                    self._summon_pause_timer = self._SUMMON_PAUSE
            else:
                self._summon_pause_timer -= dt
                if self._summon_pause_timer <= 0:
                    if not self._summon_released:
                        self._release_summon()
                        self._summon_released = True
                    self._is_summoning    = False
                    self._anim_col        = 0
                    self._anim_timer      = 0.0
                    self._summon_cd_timer = self._SUMMON_WAVE_COOLDOWN
            return

        if self._is_moving:
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % self._WALK_FRAMES
        else:
            self._anim_col   = 0
            self._anim_timer = 0.0

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ minion TRƯỚC sprite Founding để Founding nổi lên trên cùng."""
        for m in self._summoned_minions:
            if not getattr(m, 'is_alive', True):
                continue
            load = getattr(m, '_load_sprite', None)
            if callable(load):
                load()
            try:
                m.draw(screen)
            except Exception:
                pass
            if getattr(m, '_sprite_sheet', None) is None:
                mx, my = int(m.x), int(m.y)
                pygame.draw.circle(screen, (180, 100, 100), (mx, my), 18)
                pygame.draw.circle(screen, (240, 200, 200), (mx, my), 18, 2)

        self._load_sprite()

        if self._is_summoning:
            row = self._SUMMON_ROWS[self._direction]
        elif self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_moving:
            row = self._WALK_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (
            self._is_moving or self._is_attacking or self._is_summoning
        ) else 0
        frame = self._get_frame(row, col)
        if frame is not None:
            ox = int(self.x - self._FRAME_SIZE // 2)
            oy = int(self.y - self._FRAME_SIZE // 2)
            screen.blit(frame, (ox, oy))

    # ── AI gốc (chế độ manual) ───────────────────────────────────

    def update(self, dt: float) -> None:
        """AI nội bộ: P1/P3 attack target gần nhất; P2 auto-summon."""
        self.update_anim(dt)
        if not self.is_alive:
            return
        if self._is_attacking or self._is_summoning:
            self._is_moving = False
            return

        if self._phase == 2 and self._summon_cd_timer <= 0:
            self.start_summon()
            return

        from systems.world_query import WorldQuery
        target = WorldQuery.find_nearest_attacker(self)
        if target is None:
            self._is_moving = False
            return
        dist = self._distance_to(target)
        if dist <= self._ATTACK_RANGE and self._attack_cd_timer <= 0:
            self._is_moving = False
            self.trigger_attack(target)
        elif dist > self._ATTACK_RANGE:
            self._is_moving = True
            self._move_toward(target, dt)

    # ── Backward-compat helpers ──────────────────────────────────

    def _summon_minions(self, count: int):
        """Alias cũ — gọi start_summon."""
        del count
        self.start_summon()

    def _has_serum_fragment(self) -> bool:
        """Stub — chờ tài nguyên serum được thiết kế. Hiện luôn False."""
        return False
