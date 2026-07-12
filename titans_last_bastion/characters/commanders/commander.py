# characters/commanders/commander.py — abstract base Commander class.
#
# Design decisions (locked with team):
#   1. No Character intermediate class — Commander inherits Entity directly.
#   2. Stage defeat (HP <= 0) drops commander level by 1 (floor 1), revives at full HP.
#
# Subclasses (Mikasa, Eren) must override:
#   NAME, STAGE, SPRITE_FOLDER     — identity / asset location
#   SPRITE_FRAMES, FRAME_WIDTH, FRAME_HEIGHT
#   SKILL_COOLDOWNS                — {'Q': float, 'E': float, 'R': float}
#   _activate_skill(skill_id)      — dispatch to concrete skill methods
#
# WorldQuery API required (systems/world_query.py):
#   .all()                                        — all live entities
#   .structures()                                 — list of pygame.Rect for towers
#   .find_nearest(cx, cy, entity_type)            — closest entity of type
#   .find_in_radius(cx, cy, radius, entity_type)  — entities within radius
from __future__ import annotations

import logging
import math
from abc import abstractmethod
from typing import Optional

import pygame

from core.entity import Entity
from core.event_bus import GameEventBus
from core.game_state import ResourceBundle
from core.interfaces import IAttackable, IMovable, ISkillUser, IUpgradable
from config import balance
from characters.soldiers.animation import CommanderAnimator, load_clips

logger = logging.getLogger(__name__)


class Commander(Entity, IAttackable, IMovable, ISkillUser, IUpgradable):
    """Abstract base for all commanders."""

    # Camera offset for debug drawing (set by main loop)
    _camera_offset: tuple = (0, 0)

    # --- Subclass overrides ------------------------------------------------
    NAME: str = "Commander"
    STAGE: int = 1
    SPRITE_FOLDER: str = ""        # absolute path set by each subclass
    SPRITE_FRAMES: dict = {}
    FRAME_WIDTH: int = 75
    FRAME_HEIGHT: int = 48
    # All commanders render at this final on-screen pixel height (idle
    # standing silhouette). Scale factor is computed per-subclass to
    # normalise size across different source frame proportions.
    TARGET_HEIGHT_PX: int = 48
    ENTITY_TYPE: str = "commander"

    SKILL_COOLDOWNS: dict = balance.COMMANDER_SKILL_COOLDOWNS

    # Cấp yêu cầu để dùng mỗi skill — mặc định RỖNG = không giới hạn cấp
    # (giữ nguyên hành vi cũ cho tướng nào không override).
    # Subclass override, ví dụ: {"Q": 5, "R": 10}. Khoá kiểm tra trong use_skill().
    SKILL_UNLOCK_LEVEL: dict = {}

    # --- Skill tuning (subclasses may override per character) --------------
    Q_RADIUS: int = balance.COMMANDER_Q_RADIUS
    Q_HIT_COUNT: int = balance.COMMANDER_Q_HIT_COUNT
    Q_DAMAGE_PER_HIT: int = balance.COMMANDER_Q_DAMAGE_PER_HIT
    Q_DASH_GAP: int = balance.COMMANDER_Q_DASH_GAP

    # E (Grappling Swing) state machine: idle → aiming → flying → (aiming|idle).
    # Aim is VALID only when the landing spot (arrow tip) is on a tower or titan.
    E_RANGE_PX: int = balance.COMMANDER_E_RANGE_PX
    E_MIN_RANGE_PX: int = balance.COMMANDER_E_MIN_RANGE_PX
    E_MAX_RANGE_PX: int = balance.COMMANDER_E_MAX_RANGE_PX
    E_BASE_CHARGES: int = balance.COMMANDER_E_BASE_CHARGES
    E_MAX_CHARGES: int = balance.COMMANDER_E_MAX_CHARGES        # base + up to 5 bonus charges
    E_BONUS_LIFETIME: float = balance.COMMANDER_E_BONUS_LIFETIME  # bonus pool expiry (seconds)
    E_FLIGHT_DURATION: float = balance.COMMANDER_E_FLIGHT_DURATION
    E_AIM_TIMEOUT: float = balance.COMMANDER_E_AIM_TIMEOUT
    E_DOWNSWING_SLOWDOWN: float = balance.COMMANDER_E_DOWNSWING_SLOWDOWN   # downward swings are 30% slower
    E_TARGET_PAD_PX: float = balance.COMMANDER_E_TARGET_PAD_PX       # snap tolerance around a target body

    # --- Titan-damage stack -----------------------------------------------
    # Consecutive LMB hits on titans build a stack. The Nth hit deals
    # base × TITAN_DMG_STACK_MULTS[min(N-1,3)]:  125%/150%/200%/250%.
    # No hit for TITAN_STACK_RESET_WINDOW seconds resets to 0.
    TITAN_DMG_STACK_MULTS: tuple = balance.COMMANDER_TITAN_DMG_STACK_MULTS
    TITAN_STACK_RESET_WINDOW: float = balance.COMMANDER_TITAN_STACK_RESET_WINDOW

    R_DURATION: float = balance.COMMANDER_R_DURATION
    R_RADIUS: int = balance.COMMANDER_R_RADIUS
    R_DAMAGE: int = balance.COMMANDER_R_DAMAGE

    # --- Basic-attack combo (LMB: attack1 → attack2 → attack3 → wrap) ----
    BASIC_ATTACK_RADIUS: int = balance.COMMANDER_BASIC_ATTACK_RADIUS
    BASIC_ATTACK_CONE_HALF_ANGLE_DEG: float = balance.COMMANDER_BASIC_ATTACK_CONE_HALF_ANGLE_DEG   # 56° total opening
    BASIC_ATTACK_MIN_LATERAL_PX: float = balance.COMMANDER_BASIC_ATTACK_MIN_LATERAL_PX        # point-blank forgiveness
    BASIC_ATTACK_DAMAGES: tuple = balance.COMMANDER_BASIC_ATTACK_DAMAGES
    COMBO_RESET_WINDOW: float = balance.COMMANDER_COMBO_RESET_WINDOW
    COMBO_CANCEL_THRESHOLD: float = balance.COMMANDER_COMBO_CANCEL_THRESHOLD   # cancel allowed in second half of swing

    # --- Stat scaling -----------------------------------------------------
    BASE_HP: int = balance.COMMANDER_BASE_HP
    HP_PER_LEVEL: int = balance.COMMANDER_HP_PER_LEVEL
    BASE_SPEED: float = balance.COMMANDER_BASE_SPEED
    MAX_LEVEL: int = balance.COMMANDER_MAX_LEVEL

    # Đòn đánh thường (LMB combo): dame + tốc đánh tăng theo cấp.
    # level 1 = hệ số x1.0 (không đổi so với trước). Chỉnh 2 số này để cân
    # bằng — KHÔNG sửa công thức trong basic_attack().
    DAMAGE_PCT_PER_LEVEL: float = balance.COMMANDER_DAMAGE_PCT_PER_LEVEL        # +8% dame mỗi cấp (lv10 = +72%)
    ATTACK_SPEED_PCT_PER_LEVEL: float = balance.COMMANDER_ATTACK_SPEED_PCT_PER_LEVEL  # +5% tốc đánh mỗi cấp (lv10 = +45%,
                                               # giảm thời gian "gồng đòn" cần chờ)

    # Đòn antiheal (Wolf, dtype='antiheal'): chặn heal() trong bấy nhiêu giây.
    ANTI_HEAL_DURATION: float = balance.COMMANDER_ANTI_HEAL_DURATION

    UPGRADE_COSTS: dict = balance.COMMANDER_UPGRADE_COSTS

    # --- Construction -------------------------------------------------------

    def __init__(self, x: float, y: float, level: int = 1, xp: int = 0, *,
                 headless: bool = False) -> None:
        """Khởi tạo tướng ở cấp `level` (HP/XP tính theo cấp) + nạp toàn bộ animation.

        Tham số:
            level: cấp khởi điểm (>=1, kẹp sàn). HP tối đa tính qua `_compute_max_hp`.
            xp: XP khởi điểm (>=0, kẹp sàn).
            headless: True khi chạy test/CI không có màn hình — truyền xuống
                `load_clips()` để bỏ qua thao tác pygame cần display thật.

        Nhóm state chính:
            `_skill_cd` — dict cooldown MỖI skill trong `SKILL_COOLDOWNS`, khởi
                tạo 0.0 (sẵn sàng dùng ngay).
            `_combo_*` — trạng thái chuỗi 3 đòn LMB (bước hiện tại, thời gian còn
                "gồng đòn", cửa sổ reset combo).
            `_titan_stack*` — số đòn LIÊN TIẾP trúng titan (stack damage tăng dần).
            `_e_*` — máy trạng thái skill E (móc câu): idle→aiming→flying.
            `_level_penalty_on_defeat` — mặc định BẬT (giữ hành vi Vượt Ải cũ);
                game.py TẮT cờ này khi ở chế độ Thao Trường (không phạt khi thua).

        Liên kết: `load_clips()` (animation.py) dựng `CommanderAnimator` từ
        `SPRITE_FOLDER`/`SPRITE_FRAMES` do class con (Mikasa/Eren) khai.
        Chỉ số: balance.COMMANDER_BASE_HP/_HP_PER_LEVEL/_BASE_SPEED, balance.COMMANDER_E_*.
        """
        super().__init__(x, y)
        self._level = max(1, int(level))
        self._xp = max(0, int(xp))
        self._max_xp = self._compute_max_xp(self._level)
        self._max_hp = self._compute_max_hp(self._level)
        self._hp = self._max_hp
        self._speed = self.BASE_SPEED

        self._skill_cd: dict = {sid: 0.0 for sid in self.SKILL_COOLDOWNS}
        self._invincible: bool = False
        self._inv_timer: float = 0.0
        self._anti_heal_timer: float = 0.0   # >0 = đang bị chặn heal() (Wolf antiheal)

        # 3-hit combo state
        self._combo_step: int = 0
        self._combo_anim_left: float = 0.0
        self._combo_anim_total: float = 0.0
        self._combo_reset_left: float = 0.0

        # Titan-damage stack
        self._titan_stack: int = 0
        self._titan_stack_timer: float = 0.0

        # E (Grappling Swing) state
        self._e_state: str = "idle"           # "idle" | "aiming" | "flying"
        self._e_charges: int = 0
        self._e_bonus_given_this_aim: bool = False
        self._e_aim_timer: float = 0.0
        self._e_aim_dir: tuple = (1.0, 0.0)
        self._e_aim_range: float = self.E_RANGE_PX
        self._e_flight_start: tuple = (0.0, 0.0)
        self._e_flight_target: tuple = (0.0, 0.0)
        self._e_flight_progress: float = 0.0
        self._e_aim_valid: bool = False
        self._e_flight_dur: float = self.E_FLIGHT_DURATION

        self._move_target: Optional[tuple] = None
        self._headless = headless

        # Phạt trừ cấp khi chết (_on_defeat) — mặc định BẬT, giữ đúng hành vi cũ.
        # game.py TẮT cờ này khi combat_mode là Thao Trường (luyện tập, không
        # phạt theo thiết kế — xem systems/screen_manager.py).
        self._level_penalty_on_defeat: bool = True

        clips = load_clips(
            self.SPRITE_FOLDER, self.SPRITE_FRAMES,
            frame_width=self.FRAME_WIDTH,
            frame_height=self.FRAME_HEIGHT,
            target_character_height=self.TARGET_HEIGHT_PX,
            headless=headless,
        )
        self._animator = CommanderAnimator(clips, initial_state="idle")

    # --- Stats / properties ------------------------------------------------

    def _compute_max_hp(self, level: int) -> int:
        """HP tối đa ở `level`: `BASE_HP + (level-1) × HP_PER_LEVEL` — tuyến tính theo cấp.

        Chỉ số: balance.COMMANDER_BASE_HP, balance.COMMANDER_HP_PER_LEVEL.
        """
        return self.BASE_HP + (level - 1) * self.HP_PER_LEVEL

    def _compute_max_xp(self, level: int) -> int:
        """XP cần để lên cấp TIẾP THEO từ `level`: `100 × level` — tăng dần mỗi cấp.

        Số `100` là hằng CỨNG (không nằm trong balance.py).
        """
        return 100 * level

    def gain_xp(self, amount: int) -> None:
        """Cộng XP, tự động lên nhiều cấp liên tiếp nếu đủ, HỒI ĐẦY MÁU mỗi lần lên cấp.

        Thuật toán:
          1. Đã max cấp (`MAX_LEVEL` = 10) → không cộng gì nữa (XP thừa mất luôn).
          2. Cộng XP.
          3. Vòng `while xp >= max_xp` (không phải `if` — cho phép LÊN NHIỀU CẤP
             cùng lúc nếu 1 nguồn XP lớn, vd giết Boss): trừ `max_xp` khỏi `xp`
             dư, tăng `_level`, tính lại `max_xp`/`max_hp` theo cấp mới, **HỒI ĐẦY
             MÁU** (`_hp = _max_hp`) — lên cấp là 1 lần hồi phục miễn phí.
          4. Có lên cấp → phát âm thanh `'upgrade_success'` qua GameEventBus.

        Tham số: amount — XP nhận được (thường từ giết titan, xem loot_system.py).
        Chỉ số: balance.COMMANDER_MAX_LEVEL.
        """
        if self._level >= self.MAX_LEVEL:
            return

        self._xp += amount
        leveled_up = False
        while self._xp >= self._max_xp and self._level < self.MAX_LEVEL:
            self._xp -= self._max_xp
            self._level += 1
            self._max_xp = self._compute_max_xp(self._level)
            self._max_hp = self._compute_max_hp(self._level)
            self._hp = self._max_hp  # Heal to full on level up
            leveled_up = True
            
        if leveled_up:
            GameEventBus.get_instance().publish('play_sound', {'name': 'upgrade_success', 'volume': 0.8})

    @property
    def hp(self) -> int:
        """HP hiện tại — chỉ đọc từ bên ngoài (HUD). Sửa HP qua `take_damage()`/`heal()`."""
        return self._hp

    @property
    def max_hp(self) -> int:
        """HP tối đa ở cấp hiện tại (đã tính theo `_compute_max_hp`)."""
        return self._max_hp

    @property
    def level(self) -> int:
        """Cấp hiện tại (1-10). Chỉ đổi qua `gain_xp()` hoặc phạt thua trận."""
        return self._level

    @property
    def xp(self) -> int:
        """XP tích luỹ trong CẤP HIỆN TẠI (đã trừ phần dùng để lên cấp trước đó)."""
        return self._xp

    @property
    def max_xp(self) -> int:
        """XP cần để lên cấp tiếp theo — HUD dùng vẽ thanh XP."""
        return self._max_xp

    @property
    def is_invincible(self) -> bool:
        """True nếu đang bất tử tạm thời (vd sau khi hồi sinh) — `take_damage()` bỏ qua."""
        return self._invincible

    @property
    def is_anti_healed(self) -> bool:
        """True nếu đang bị chặn heal() (dính antiheal, đếm ngược trong
        `_anti_heal_timer`) — UI dùng để hiện icon trái tim gạch chéo."""
        return self._anti_heal_timer > 0.0

    @property
    def titan_stack(self) -> int:
        """Số đòn LIÊN TIẾP vừa trúng titan (0-3+) — tra `TITAN_DMG_STACK_MULTS`
        để biết hệ số nhân damage của đòn tiếp theo."""
        return self._titan_stack

    @property
    def combo_step(self) -> int:
        """Bước hiện tại trong chuỗi combo LMB 3 đòn (0/1/2) — quyết định damage
        + animation của đòn TIẾP THEO khi click."""
        return self._combo_step

    # --- Entity contract ---------------------------------------------------

    def update(self, dt: float) -> None:
        """Vòng update mỗi frame: đếm ngược MỌI timer + di chuyển + animation.

        Thuật toán, theo thứ tự:
          1. Đang bị đẩy lùi bởi đá Beast (`pushback_vx/vy != 0`) →
             `RockProjectile.apply_pushback_tween()` (attackstrategy.py) trượt
             tướng theo vector đẩy, giảm dần theo hàm mũ.
          2. Đếm ngược MỌI cooldown skill trong `_skill_cd`.
          3. Đếm ngược `_anti_heal_timer` (debuff Wolf).
          4. Đếm ngược `_inv_timer` (bất tử tạm thời), hết → tắt `_invincible`.
          5. Đếm ngược `_combo_anim_left` ("gồng đòn" — khoá click liên tiếp) và
             `_combo_reset_left` (cửa sổ giữ combo); hết cửa sổ reset → combo về 0.
          6. Đếm ngược `_titan_stack_timer`; hết → stack damage về 0.
          7. Máy trạng thái E: "aiming" → đếm ngược `_e_aim_timer`, hết thời gian
             ngắm → `cancel_swing()`. "flying" → `_step_flight(dt)` (đang bay dây).
          8. Có `_move_target` VÀ không đang bay E → `_step_toward()` (đi bộ).
          9. `_animator.update(dt)` — tiến animation.

        Chỉ số: balance.COMMANDER_ANTI_HEAL_DURATION, balance.COMMANDER_E_AIM_TIMEOUT,
        balance.COMMANDER_TITAN_STACK_RESET_WINDOW.
        """

        # Rock AoE pushback tween từ BeastTitan
        if getattr(self, 'pushback_vx', 0.0) != 0.0 or getattr(self, 'pushback_vy', 0.0) != 0.0:
            from characters.titans.attackstrategy import RockProjectile
            RockProjectile.apply_pushback_tween(self, dt)

        for sid in self._skill_cd:
            if self._skill_cd[sid] > 0:
                self._skill_cd[sid] = max(0.0, self._skill_cd[sid] - dt)

        if self._anti_heal_timer > 0.0:
            self._anti_heal_timer = max(0.0, self._anti_heal_timer - dt)

        if self._invincible:
            self._inv_timer -= dt
            if self._inv_timer <= 0:
                self._invincible = False
                self._inv_timer = 0.0

        if self._combo_anim_left > 0:
            self._combo_anim_left = max(0.0, self._combo_anim_left - dt)

        if self._combo_reset_left > 0:
            self._combo_reset_left = max(0.0, self._combo_reset_left - dt)
            if self._combo_reset_left == 0:
                self._combo_step = 0

        if self._titan_stack_timer > 0:
            self._titan_stack_timer = max(0.0, self._titan_stack_timer - dt)
            if self._titan_stack_timer == 0.0:
                self._titan_stack = 0

        if self._e_state == "aiming":
            self._e_aim_timer -= dt
            if self._e_aim_timer <= 0:
                self.cancel_swing()
        elif self._e_state == "flying":
            self._step_flight(dt)

        if self._move_target is not None and self._e_state != "flying":
            self._step_toward(self._move_target, dt)

        self._animator.update(dt)

    def _step_toward(self, destination: tuple, dt: float) -> None:
        """Đi bộ 1 bước về `destination`, né tường, tự dừng khi tới hoặc bị chặn.

        Thuật toán:
          1. Còn cách < 1px → coi như đã tới: xoá `_move_target`, chuyển animation
             về "idle" nếu đang "walk".
          2. Đổi hướng nhìn theo dx (`set_facing`), chuyển animation sang "walk"
             nếu đang "idle".
          3. `step = _speed * dt`. Nếu `step >= dist` (bước này đủ tới đích):
             kiểm tra `WorldQuery.is_wall_blocked(destination, radius=20,
             extend_down=48)` — không chặn thì SNAP thẳng tới đích; bị chặn thì
             HUỶ di chuyển (không đi tiếp, không lết dần).
          4. Ngược lại (chưa tới): tính vị trí kế tiếp theo vector đơn vị, kiểm
             tra va chạm tương tự — không chặn thì đi, bị chặn thì huỷ di chuyển.

        `radius=20, extend_down=48`: hộp va chạm KHÔNG ĐỐI XỨNG — mở rộng xuống
        dưới nhiều hơn (chân tướng), phù hợp góc nhìn top-down của sprite.

        Tham số: destination — (x, y) đích; dt.
        Liên kết: `WorldQuery.is_wall_blocked()`.
        """
        dx = destination[0] - self.x
        dy = destination[1] - self.y
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            self._move_target = None
            if self._animator.state == "walk":
                self._animator.set_state("idle")
            return
        if abs(dx) > 0.5:
            self._animator.set_facing(dx > 0)
        if self._animator.state == "idle":
            self._animator.set_state("walk")
        step = self._speed * dt
        if step >= dist:
            from systems.world_query import WorldQuery
            if not WorldQuery.is_wall_blocked(destination[0], destination[1],
                                              radius=20.0, extend_down=48.0):
                self.x, self.y = destination
                self._move_target = None
            else:
                self._move_target = None
        else:
            nx = self.x + (dx / dist) * step
            ny = self.y + (dy / dist) * step
            from systems.world_query import WorldQuery
            if not WorldQuery.is_wall_blocked(nx, ny, radius=20.0, extend_down=48.0):
                self.x, self.y = nx, ny
            else:
                self._move_target = None

    def draw(self, screen) -> None:
        """Vẽ sprite + HP bar + thanh hồi đòn + vòng bất tử + vòng cung tấn công + aim overlay.

        Thuật toán, theo lớp (dưới lên trên):
          1. Frame hiện tại từ `_animator`, neo `midbottom` tại (x, y) — chân
             sprite chạm đúng vị trí logic. Không có frame → vẽ vòng tròn xanh
             thay thế (fallback).
          2. HP bar (đỏ nền + xanh theo tỉ lệ `_hp/_max_hp`) phía trên đầu.
          3. `_draw_recovery_bar()` — thanh trắng mảnh cảnh báo đang "gồng đòn".
          4. Đang bất tử → vòng tròn vàng viền quanh sprite.
          5. Đang trong combo animation (`_combo_anim_left > 0`) → vẽ vùng đánh
             (`_draw_attack_cone`).
          6. Đang ngắm/bay E → vẽ overlay ngắm + hitbox debug.

        CHỈ ĐỒ HOẠ — không đổi trạng thái logic.
        """
        frame = self._animator.current_frame()
        sprite_h = 36
        if frame is not None:
            rect = frame.get_rect(midbottom=(int(self.x), int(self.y)))
            screen.blit(frame, rect)
            sprite_h = frame.get_height()
        else:
            pygame.draw.circle(screen, (40, 200, 90),
                               (int(self.x), int(self.y) - sprite_h // 2),
                               sprite_h // 2)

        # HP bar
        bar_w = 60
        ratio = self._hp / self._max_hp if self._max_hp else 0.0
        bx = int(self.x) - bar_w // 2
        by = int(self.y) - sprite_h - 12
        pygame.draw.rect(screen, (180, 30, 30), (bx, by, bar_w, 6))
        pygame.draw.rect(screen, (60, 220, 60), (bx, by, int(bar_w * ratio), 6))

        # Thanh hồi đòn (mảnh, trắng) — cảnh báo đang trong lúc "gồng đòn"
        self._draw_recovery_bar(screen, bx, by - 5, bar_w)

        # Invincibility ring
        if self._invincible:
            cx, cy = int(self.x), int(self.y) - sprite_h // 2
            pygame.draw.circle(screen, (255, 215, 0), (cx, cy),
                               sprite_h // 2 + 8, 3)

        if self._combo_anim_left > 0:
            self._draw_attack_cone(screen)

        if self._e_state in ("aiming", "flying"):
            self._draw_aim_overlay(screen)
            self._draw_e_hitboxes_debug(screen)
    def _draw_aim_overlay(self, screen) -> None:
        """Aim circle + direction arrow. Bright when valid, faint when not."""
        cx, cy = int(self.x), int(self.y) - 40
        r = int(self._e_aim_range)
        valid = self._e_aim_valid
        arrow_col = (255, 230, 100) if valid else (150, 138, 80)
        ring_col = (235, 215, 90) if valid else (110, 100, 50)
        width = 4 if valid else 2
        try:
            pygame.draw.circle(screen, (90, 80, 30),
                               (cx, cy), self.E_MAX_RANGE_PX, 1)
            pygame.draw.circle(screen, ring_col, (cx, cy), r, 2)
            dx, dy = self._e_aim_dir
            tip = (int(cx + dx * r), int(cy + dy * r))
            pygame.draw.line(screen, arrow_col, (cx, cy), tip, width)
            ang = math.atan2(dy, dx)
            head_len = 16 if valid else 12
            head_spread = 0.45
            left = (int(tip[0] - head_len * math.cos(ang - head_spread)),
                    int(tip[1] - head_len * math.sin(ang - head_spread)))
            right = (int(tip[0] - head_len * math.cos(ang + head_spread)),
                     int(tip[1] - head_len * math.sin(ang + head_spread)))
            pygame.draw.line(screen, arrow_col, tip, left, width)
            pygame.draw.line(screen, arrow_col, tip, right, width)
        except (AttributeError, pygame.error):
            pass

    def _draw_e_hitboxes_debug(self, screen) -> None:
        """Debug visualization: show all valid E-swing target hitboxes."""
        from systems.world_query import WorldQuery

        try:
            cam_x, cam_y = self._camera_offset
            pad = self.E_TARGET_PAD_PX

            for entity in WorldQuery.all():
                etype = getattr(entity, "ENTITY_TYPE", None)
                if etype not in ("titan", "wall"):
                    continue
                if not getattr(entity, "is_alive", False):
                    continue

                if etype == "titan":
                    radius = 22.0 * getattr(entity, "_size_scale", 1.0) + pad
                    color = (100, 255, 100) if self._e_aim_valid else (100, 100, 100)
                    pygame.draw.circle(screen, color,
                                     (int(entity.x - cam_x), int(entity.y - cam_y)),
                                     int(radius), 2)
                else:  # wall — extended rect (khớp với sprite visual)
                    try:
                        collider = WorldQuery._wall_colliders.get(id(entity))
                        stype = getattr(entity, 'section_type', 'wall_h')
                        if collider:
                            rx, ry, rw, rh = collider
                            if stype == 'wall_h':
                                rect = pygame.Rect(int(rx - cam_x), int(ry - cam_y),
                                                   int(rw), int(rh) + 96)
                            else:
                                rect = pygame.Rect(int(rx - cam_x), int(ry - cam_y),
                                                   int(rw) + 42, int(rh))
                        else:
                            rect = pygame.Rect(int(entity.x - cam_x),
                                               int(entity.y - cam_y), 74, 32)
                        inflated = rect.inflate(int(pad * 2), int(pad * 2))
                        color = (100, 255, 255) if self._e_aim_valid else (100, 100, 100)
                        pygame.draw.rect(screen, color, inflated, 2)
                    except Exception:
                        pass

            # Draw tower hitboxes (already screen coords)
            for rect in WorldQuery.structures():
                screen_rect = rect.copy()
                screen_rect.x -= cam_x
                screen_rect.y -= cam_y
                inflated = screen_rect.inflate(int(pad * 2), int(pad * 2))
                color = (255, 255, 100) if self._e_aim_valid else (100, 100, 100)
                pygame.draw.rect(screen, color, inflated, 2)

            # Decoration + ground tower anchors (world coords → screen)
            for rect in WorldQuery.static_anchors():
                screen_rect = rect.copy()
                screen_rect.x -= cam_x
                screen_rect.y -= cam_y
                inflated = screen_rect.inflate(int(pad * 2), int(pad * 2))
                color = (160, 255, 120) if self._e_aim_valid else (70, 120, 60)
                pygame.draw.rect(screen, color, inflated, 2)

        except (AttributeError, pygame.error, Exception):
            pass

    # --- IAttackable -------------------------------------------------------

    def take_damage(self, amount: int, dtype: str) -> None:
        """Nhận damage — bỏ qua nếu đã chết hoặc đang BẤT TỬ; kích debuff antiheal.

        Thuật toán:
          1. Đã chết → không làm gì.
          2. Đang `_invincible` → log rồi bỏ qua HOÀN TOÀN (không trừ HP).
          3. `dtype == 'antiheal'` (đòn Wolf) → nạp `_anti_heal_timer =
             ANTI_HEAL_DURATION` (15s), chặn `heal()` trong thời gian đó.
          4. Trừ HP (kẹp `amount >= 0`).
          5. HP <= 0 → `_on_defeat()`. Còn sống → chuyển animation "hurt".

        Tham số: amount — damage thô; dtype — loại damage, chỉ 'antiheal' có xử lý riêng.
        Chỉ số: balance.COMMANDER_ANTI_HEAL_DURATION.
        """
        if not self.is_alive:
            return
        if self._invincible:
            logger.debug("%s ignored %d %s damage (invincible)",
                         self.NAME, amount, dtype)
            return
        if dtype == 'antiheal':
            self._anti_heal_timer = self.ANTI_HEAL_DURATION
        self._hp -= max(0, int(amount))
        if self._hp <= 0:
            self._on_defeat()
        else:
            self._animator.set_state("hurt")

    def heal(self, amount: int) -> None:
        """Hồi máu — không vượt max_hp, không hồi nếu đã chết (vd. đang chờ
        hồi sinh tại HQ) hoặc đang bị antiheal (Wolf, xem `is_anti_healed`).
        Dùng cho các cơ chế hồi máu ngoài combat (vd. đứng trong vùng castle)."""
        if not self.is_alive or self.is_anti_healed:
            return
        self._hp = min(self._max_hp, self._hp + max(0, int(amount)))


    def _on_defeat(self) -> None:
        """Defeat: giảm 1 level (trừ khi Thao Trường — xem `_level_penalty_on_defeat`),
        ẩn khỏi màn, đặt timer hồi sinh tại HQ."""
        old_level = self._level
        if self._level_penalty_on_defeat:
            self._level = max(1, self._level - 1)
            self._max_hp = self._compute_max_hp(self._level)
        self._invincible = False
        self._inv_timer  = 0.0
        self.is_alive    = False
        self._animator.set_state("dying")
        GameEventBus.get_instance().publish("commander_defeated", {
            "commander_id": self.id,
            "name": self.NAME,
            "old_level": old_level,
            "new_level": self._level,
        })
        logger.info("%s defeated lv %d → %d", self.NAME, old_level, self._level)

    # --- Basic attack (LMB) -----------------------------------------------

    def _attack_recovery_gate(self) -> float:
        """Thời gian (giây, tính từ lúc `_combo_anim_left` = `_combo_anim_total`)
        cần chờ trước khi 1 click mới được TÍNH — dùng chung bởi `basic_attack()`
        (chặn click hụt) và `_draw_recovery_bar()` (thanh trắng cảnh báo), để
        không lặp công thức 2 nơi. Tốc đánh tăng theo cấp → gate ngắn lại."""
        atk_speed_mult = 1.0 + (self._level - 1) * self.ATTACK_SPEED_PCT_PER_LEVEL
        return (self._combo_anim_total * self.COMBO_CANCEL_THRESHOLD) / atk_speed_mult

    def _draw_recovery_bar(self, screen, bar_x: int, bar_y: int, bar_w: int) -> None:
        """Thanh mảnh màu trắng cảnh báo đang "gồng đòn" (chưa click lại được).
        Chạy đầy (0 → 100%) đúng lúc hồi đòn kết thúc rồi biến mất ngay."""
        if self._combo_anim_total <= 0:
            return
        gate = self._attack_recovery_gate()
        if self._combo_anim_left <= gate:
            return   # đã qua gate — click tiếp theo được tính ngay, ẩn thanh
        recovery_total = self._combo_anim_total - gate
        if recovery_total <= 0:
            return
        elapsed = self._combo_anim_total - self._combo_anim_left
        progress = max(0.0, min(1.0, elapsed / recovery_total))
        bar_h = 2
        pygame.draw.rect(screen, (70, 70, 70), (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, (255, 255, 255),
                         (bar_x, bar_y, int(bar_w * progress), bar_h))

    def basic_attack(self) -> None:
        """3-hit melee combo attack1 → attack2 → attack3 → wrap.

        Hitting a titan advances the titan-damage stack (125%/150%/200%/250%).
        Hitting a LargeTitan during an E session grants +1 bonus E charge.
        """
        # Tốc đánh tăng theo cấp → rút ngắn thời gian "gồng đòn" cần chờ trước
        # khi 1 click mới được TÍNH (nhị phân: đủ giờ mới có dame, hụt = 0 dame,
        # không đổi combo — giữ nguyên hành vi cũ, chỉ đổi độ dài cửa sổ chờ).
        if (self._combo_anim_total > 0
                and self._combo_anim_left > self._attack_recovery_gate()):
            return

        if self._combo_reset_left <= 0:
            self._combo_step = 0
        if self._titan_stack_timer <= 0:
            self._titan_stack = 0

        step = self._combo_step
        state = f"attack{step + 1}"
        base_damage = self.BASIC_ATTACK_DAMAGES[step]
        stack_idx = min(self._titan_stack, len(self.TITAN_DMG_STACK_MULTS) - 1)
        mult = self.TITAN_DMG_STACK_MULTS[stack_idx]
        dmg_level_mult = 1.0 + (self._level - 1) * self.DAMAGE_PCT_PER_LEVEL
        damage = int(round(base_damage * mult * dmg_level_mult))

        self._animator.set_state(state)
        from systems.sound_system import SoundManager
        if not getattr(self, 'is_in_titan_form', False):
            SoundManager.get_instance().play('swing_sword', self.x, self.y)

        from systems.world_query import WorldQuery
        hit_any = False
        for entity in WorldQuery.all():
            if getattr(entity, "ENTITY_TYPE", None) != "titan":
                continue
            if not getattr(entity, "is_alive", False):
                continue
            _body_r = 32.0 * getattr(entity, '_size_scale', 1.0)
            if not self._in_attack_cone(entity.x, entity.y, body_radius=_body_r):
                continue
            # Vùng đầu = phần trên 30% body (commander cao hơn titan > 0.3 * body_r)
            _is_head = (self.y - entity.y) < -(_body_r * 0.3)
            _zone_mult = 1.2 if _is_head else 1.0
            entity.take_damage(amount=int(damage * _zone_mult), dtype="slash", attacker=self)
            hit_any = True
            if (self._e_state == "aiming"
                    and not self._e_bonus_given_this_aim
                    and getattr(entity, "IS_LARGE", False)):
                self._grant_bonus_charge()

        if hit_any:
            self._titan_stack = min(self._titan_stack + 1,
                                    len(self.TITAN_DMG_STACK_MULTS))
            self._titan_stack_timer = self.TITAN_STACK_RESET_WINDOW

        duration = self._animator.clip_duration(state)
        self._combo_anim_total = duration
        self._combo_anim_left = duration
        self._combo_reset_left = self.COMBO_RESET_WINDOW
        self._combo_step = (step + 1) % len(self.BASIC_ATTACK_DAMAGES)

    def _in_attack_cone(self, tx: float, ty: float,
                        body_radius: float = 0.0) -> bool:
        """True if target body overlaps the front-facing attack cone.

        body_radius: treat target as a circle of this radius so the full
        titan body (not just its anchor point) can receive damage.
        """
        dx = tx - self.x
        dy = ty - self.y
        facing = 1.0 if self._animator.facing_right else -1.0
        forward = dx * facing
        if forward < -body_radius or forward > self.BASIC_ATTACK_RADIUS + body_radius:
            return False
        half_angle_rad = math.radians(self.BASIC_ATTACK_CONE_HALF_ANGLE_DEG)
        max_lateral = max(self.BASIC_ATTACK_MIN_LATERAL_PX,
                          forward * math.tan(half_angle_rad)) + body_radius
        return abs(dy) <= max_lateral

    def _draw_attack_cone(self, screen) -> None:
        """Vẽ tam giác biểu diễn vùng đánh (hình quạt xấp xỉ bằng tam giác).

        Hình học: đỉnh tại (x, y-40) — hơi cao hơn chân tướng; 2 cạnh xa mở rộng
        theo `BASIC_ATTACK_CONE_HALF_ANGLE_DEG`, độ dài `BASIC_ATTACK_RADIUS`,
        hướng theo `facing_right`. Đây là hình ĐƠN GIẢN HOÁ của vùng va chạm thật
        (`_in_attack_cone` dùng công thức hình nón chính xác hơn, có `max_lateral`
        tăng dần theo khoảng cách + cận biên tối thiểu).
        CHỈ ĐỒ HOẠ.
        """
        facing = 1.0 if self._animator.facing_right else -1.0
        half = math.radians(self.BASIC_ATTACK_CONE_HALF_ANGLE_DEG)
        r = self.BASIC_ATTACK_RADIUS
        ox, oy = int(self.x), int(self.y) - 40
        far_x = ox + int(r * facing * math.cos(half))
        upper = (far_x, oy - int(r * math.sin(half)))
        lower = (far_x, oy + int(r * math.sin(half)))
        try:
            pygame.draw.polygon(screen, (255, 200, 80),
                                [(ox, oy), upper, lower], 2)
        except (AttributeError, pygame.error):
            pass

    # --- IMovable ----------------------------------------------------------

    def move(self, destination: tuple) -> None:
        """Đặt điểm đến — di chuyển THẬT diễn ra qua nhiều frame trong `update()`
        (gọi `_step_toward()`), KHÔNG dịch chuyển tức thì."""
        self._move_target = (float(destination[0]), float(destination[1]))

    # --- ISkillUser --------------------------------------------------------

    def use_skill(self, skill_id: str) -> None:
        """Kích hoạt skill — kiểm tra hợp lệ → mở khoá → cooldown, rồi mới thực thi.

        Thuật toán:
          1. `skill_id` không phải Q/E/R → `raise ValueError` (lỗi lập trình, nên
             raise thay vì âm thầm bỏ qua).
          2. Chưa đủ cấp mở khoá (`is_skill_unlocked`) → bỏ qua ÊM, KHÔNG tốn
             cooldown — tránh phí CD nếu người chơi lỡ bấm skill chưa mở.
          3. Còn cooldown → bỏ qua.
          4. Gọi `_activate_skill(skill_id)` (class con override, dispatch tới
             method skill cụ thể), rồi nạp `_skill_cd[skill_id] = SKILL_COOLDOWNS[skill_id]`.

        Tham số: skill_id — 'Q'/'E'/'R'.
        Chỉ số: balance.<COMMANDER>_SKILL_COOLDOWNS, balance.<COMMANDER>_SKILL_UNLOCK_LEVEL.
        """
        if skill_id not in self.SKILL_COOLDOWNS:
            raise ValueError(f"Invalid skill id: {skill_id!r} (expected Q/E/R)")
        if not self.is_skill_unlocked(skill_id):
            return
        if self._skill_cd[skill_id] > 0:
            return
        self._activate_skill(skill_id)
        self._skill_cd[skill_id] = float(self.SKILL_COOLDOWNS[skill_id])

    def is_skill_unlocked(self, skill_id: str) -> bool:
        """True nếu cấp hiện tại >= mốc mở khoá của skill (mặc định mốc 1 = luôn mở)."""
        return self._level >= self.SKILL_UNLOCK_LEVEL.get(skill_id, 1)

    def skill_unlock_level(self, skill_id: str) -> int:
        """Cấp cần để mở khoá `skill_id` — HUD dùng hiển thị "Lv N" trên icon khoá."""
        return self.SKILL_UNLOCK_LEVEL.get(skill_id, 1)

    def get_cooldown(self, skill_id: str) -> float:
        """Số giây cooldown còn lại của `skill_id` — HUD dùng vẽ vòng cooldown icon."""
        return max(0.0, float(self._skill_cd.get(skill_id, 0.0)))

    @abstractmethod
    def _activate_skill(self, skill_id: str) -> None:
        """Subclass dispatches skill_id → its concrete skill method."""
        ...

    # --- Q / E / R default implementations (Mikasa-flavoured) ---------------

    def _slash_combo(self) -> None:
        """Q — dash to nearest titan then 3-hit AoE on landing."""
        from systems.world_query import WorldQuery

        target = WorldQuery.find_nearest(cx=self.x, cy=self.y,
                                         entity_type="titan")
        if target is not None:
            if target.x >= self.x:
                self.x = target.x - self.Q_DASH_GAP
                self._animator.set_facing(True)
            else:
                self.x = target.x + self.Q_DASH_GAP
                self._animator.set_facing(False)
            self.y = target.y

        self._animator.set_state("skill_q")

        for titan in WorldQuery.find_in_radius(cx=self.x, cy=self.y,
                                               radius=self.Q_RADIUS,
                                               entity_type="titan"):
            for _ in range(self.Q_HIT_COUNT):
                titan.take_damage(amount=self.Q_DAMAGE_PER_HIT, dtype="slash", attacker=self)

    # E is driven directly by main.py via begin_aim / confirm_swing /
    # cancel_swing / redirect_flight. It is NOT routed through use_skill().

    def begin_aim(self) -> bool:
        """Press E from idle → enter AIMING with E_BASE_CHARGES (+bonus pool).

        Returns True if entry succeeded (cooldown ok), False otherwise.
        """
        if self._e_state != "idle":
            return False
        if self._skill_cd.get("E", 0.0) > 0:
            return False
        self._e_charges = self.E_BASE_CHARGES
        self._e_bonus_given_this_aim = False
        self._e_state = "aiming"
        self._e_aim_timer = self.E_AIM_TIMEOUT
        self._e_aim_valid = False
        self._animator.set_state("skill_e")
        GameEventBus.get_instance().publish("e_session_started", {
            "commander_id": self.id,
            "name": self.NAME,
            "charges": self._e_charges,
        })
        return True

    def set_aim_direction(self, vx: float, vy: float) -> None:
        """Update aim direction + range from raw (vx, vy) vector. No-op outside AIMING."""
        if self._e_state != "aiming":
            return
        if not self._compute_aim(vx, vy):
            return
        self._e_aim_timer = self.E_AIM_TIMEOUT
        if abs(vx) > 0.1:
            self._animator.set_facing(vx > 0)

    def update_flight_aim(self, vx: float, vy: float) -> None:
        """Keep aim preview live during flight for redirect targeting. No-op outside FLYING."""
        if self._e_state != "flying":
            return
        self._compute_aim(vx, vy)

    def _compute_aim(self, vx: float, vy: float) -> bool:
        """Set aim dir + range + validity from raw vector. Returns False if too small."""
        length = math.hypot(vx, vy)
        if length < 0.001:
            return False
        self._e_aim_dir = (vx / length, vy / length)
        self._e_aim_range = max(self.E_MIN_RANGE_PX,
                                min(self.E_MAX_RANGE_PX, length))
        self._e_aim_valid = self._aim_endpoint_on_target()
        return True

    def _aim_endpoint_on_target(self) -> bool:
        """True if the swing landing spot or aim ray hits a wall, tower, or titan.

        Titans use ray-line detection: valid when the aim ray passes through the
        titan body even if the mouse is past it — range snaps to titan distance.
        Walls use registered collider rect (actual sprite size, not 32×32).
        """
        from systems.world_query import WorldQuery

        dx, dy = self._e_aim_dir
        cx, cy = self.x, self.y
        ex = cx + dx * self._e_aim_range
        ey = cy + dy * self._e_aim_range
        pad = self.E_TARGET_PAD_PX

        for entity in WorldQuery.all():
            etype = getattr(entity, "ENTITY_TYPE", None)
            if etype not in ("titan", "wall"):
                continue
            if not getattr(entity, "is_alive", False):
                continue
            if etype == "titan":
                radius = 22.0 * getattr(entity, "_size_scale", 1.0) + pad
                tx, ty = entity.x, entity.y
                # Check 1: endpoint inside hitbox (classic)
                if (ex - tx) ** 2 + (ey - ty) ** 2 <= radius * radius:
                    return True
                # Check 2: aim ray passes through titan (point toward or past it)
                dist_to_titan = math.hypot(tx - cx, ty - cy)
                if dist_to_titan > self.E_MAX_RANGE_PX + radius:
                    continue
                dot = (tx - cx) * dx + (ty - cy) * dy
                if dot <= 0:
                    continue  # titan is behind commander
                perp = abs((tx - cx) * dy - (ty - cy) * dx)
                if perp <= radius:
                    # Snap range to land ON the titan instead of flying past
                    self._e_aim_range = max(
                        self.E_MIN_RANGE_PX,
                        min(self.E_MAX_RANGE_PX, dist_to_titan),
                    )
                    return True
            else:  # wall — extend theo orientation để khớp sprite visual
                try:
                    import pygame
                    collider = WorldQuery._wall_colliders.get(id(entity))
                    stype = getattr(entity, 'section_type', 'wall_h')
                    if collider:
                        rx, ry, rw, rh = collider
                        if stype == 'wall_h':
                            # Tường ngang: sprite ~122px cao → extend xuống
                            rect = pygame.Rect(int(rx), int(ry), int(rw), int(rh) + 96)
                        else:
                            # Tường dọc (wall_Y): sprite ~74px rộng → extend sang phải
                            rect = pygame.Rect(int(rx), int(ry), int(rw) + 42, int(rh))
                    else:
                        rect = pygame.Rect(int(entity.x), int(entity.y), 74, 32)
                    if rect.inflate(int(pad * 2), int(pad * 2)).collidepoint(ex, ey):
                        return True
                except Exception:
                    radius = 24.0 + pad
                    if (ex - entity.x) ** 2 + (ey - entity.y) ** 2 <= radius * radius:
                        return True

        for rect in WorldQuery.structures():
            if rect.inflate(int(pad * 2), int(pad * 2)).collidepoint(ex, ey):
                return True

        # Decoration + ground tower anchors (tree, stair, arch, ground tower)
        for rect in WorldQuery.static_anchors():
            if rect.inflate(int(pad * 2), int(pad * 2)).collidepoint(ex, ey):
                return True

        return False

    def confirm_swing(self, direction: Optional[tuple] = None) -> None:
        """Launch a flight from AIMING, consuming one charge.

        No-op when aim is invalid (not pointing at a tower/titan).
        Swinging downward runs E_DOWNSWING_SLOWDOWN× slower.
        """
        if self._e_state != "aiming" or self._e_charges <= 0:
            return
        if direction is not None:
            self.set_aim_direction(direction[0], direction[1])
        if not self._e_aim_valid:
            return
        self._launch_flight()

    def _launch_flight(self) -> None:
        """Commit aim and enter FLYING state towards target."""
        from systems.sound_system import SoundManager
        SoundManager.get_instance().play('skillE', self.x, self.y)
        self._e_charges -= 1
        dx, dy = self._e_aim_dir
        self._e_flight_start = (self.x, self.y)
        self._e_flight_target = (
            self.x + dx * self._e_aim_range,
            self.y + dy * self._e_aim_range,
        )
        going_down = self._e_flight_target[1] > self._e_flight_start[1]
        self._e_flight_dur = (self.E_FLIGHT_DURATION * self.E_DOWNSWING_SLOWDOWN
                              if going_down else self.E_FLIGHT_DURATION)
        self._e_flight_progress = 0.0
        self._e_aim_valid = False
        self._e_state = "flying"
        self._animator.set_state("skill_e")

    def cancel_swing(self) -> None:
        """SPACE — abort E session. Drops in place if flying."""
        if self._e_state == "idle":
            return
        self._end_session(set_cooldown=True)

    def _step_flight(self, dt: float) -> None:
        """During flight, commander swings freely — no wall collision."""
        if self._e_flight_dur <= 0:
            self._e_flight_progress = 1.0
        else:
            self._e_flight_progress += dt / self._e_flight_dur
        if self._e_flight_progress >= 1.0:
            self.x, self.y = self._find_safe_landing(self._e_flight_target[0], self._e_flight_target[1])
            self._e_flight_progress = 1.0
            if self._e_charges > 0:
                self._e_state = "aiming"
                self._e_aim_timer = self.E_AIM_TIMEOUT
                self._e_aim_valid = False
                self._e_bonus_given_this_aim = False
            else:
                self._end_session(set_cooldown=True)
        else:
            sx, sy = self._e_flight_start
            tx, ty = self._e_flight_target
            _t = self._e_flight_progress
            _t = _t * _t * (3.0 - 2.0 * _t)   # smoothstep: gia tốc đầu, giảm tốc cuối
            self.x = sx + (tx - sx) * _t
            self.y = sy + (ty - sy) * _t

    def _find_safe_landing(self, target_x: float, target_y: float) -> tuple:
        """Find valid landing position near target, avoiding walls via spiral search + backtrack."""
        from systems.world_query import WorldQuery

        if not WorldQuery.is_wall_blocked(target_x, target_y, radius=20.0, extend_down=48.0):
            return (target_x, target_y)

        # Spiral search: 8 directions, expanding outward
        for distance in [8, 16, 24, 32, 40, 48, 64, 80]:
            for angle_i in range(8):
                angle = 2 * math.pi * angle_i / 8
                test_x = target_x + math.cos(angle) * distance
                test_y = target_y + math.sin(angle) * distance
                if not WorldQuery.is_wall_blocked(test_x, test_y, radius=20.0, extend_down=48.0):
                    return (test_x, test_y)

        # Fallback: backtrack along flight path (enter & exit both work)
        sx, sy = self._e_flight_start
        dx = target_x - sx
        dy = target_y - sy
        dist = math.hypot(dx, dy) or 1.0

        for step_back in range(1, 20):
            back_dist = step_back * 8
            if back_dist >= dist:
                break
            test_x = target_x - (dx / dist) * back_dist
            test_y = target_y - (dy / dist) * back_dist
            if not WorldQuery.is_wall_blocked(test_x, test_y, radius=20.0, extend_down=48.0):
                return (test_x, test_y)

        return (target_x, target_y)

    def redirect_flight(self, vx: float, vy: float) -> bool:
        """Mid-flight: instantly switch to a new target if cursor is on a valid one.

        Consumes one charge. Returns True if redirected.
        """
        if self._e_state != "flying" or self._e_charges <= 0:
            return False
        if not self._compute_aim(vx, vy):
            return False
        if not self._e_aim_valid:
            return False
        self._launch_flight()
        return True

    def _grant_bonus_charge(self) -> None:
        """LMB trúng IS_LARGE titan khi đang aiming: +1 charge, một lần mỗi aim phase."""
        self._e_charges += 1
        self._e_bonus_given_this_aim = True
        GameEventBus.get_instance().publish("e_charge_bonus_added", {
            "commander_id": self.id,
            "name": self.NAME,
            "charges": self._e_charges,
        })

    def _end_session(self, *, set_cooldown: bool) -> None:
        """Kết thúc PHIÊN skill E (dù bay xong hay bị huỷ giữa chừng) — reset toàn bộ state.

        Reset: `_e_state` về "idle", xoá charge còn lại, mọi cờ/aim liên quan.
        `set_cooldown=True` (huỷ chủ động qua `cancel_swing`) → áp cooldown E
        ngay; `False` (bay xong tự nhiên) → không phạt cooldown thêm — cooldown
        thật đã được áp lúc `use_skill()` kích hoạt E.

        Tham số: set_cooldown — bắt buộc truyền qua keyword (`*`).
        """
        self._e_state = "idle"
        self._e_charges = 0
        self._e_bonus_given_this_aim = False
        self._e_aim_timer = 0.0
        self._e_flight_progress = 0.0
        self._e_aim_valid = False
        self._e_flight_dur = self.E_FLIGHT_DURATION
        if set_cooldown:
            self._skill_cd["E"] = float(self.SKILL_COOLDOWNS.get("E", 0.0))
        self._animator.set_state("idle")

    def _titan_form(self) -> None:
        """R — invincibility for R_DURATION + R_RADIUS AoE on activation."""
        from systems.world_query import WorldQuery

        self._animator.set_state("skill_r")
        from systems.sound_system import SoundManager
        SoundManager.get_instance().play('mikasa_skillR', self.x, self.y)
        self._invincible = True
        self._inv_timer = self.R_DURATION
        for titan in WorldQuery.find_in_radius(cx=self.x, cy=self.y,
                                               radius=self.R_RADIUS,
                                               entity_type="titan"):
            titan.take_damage(amount=self.R_DAMAGE, dtype="aoe", attacker=self)

    # --- IUpgradable -------------------------------------------------------

    def upgrade(self) -> None:
        """Nâng cấp tướng bằng TÀI NGUYÊN (đường lên cấp THỨ 2, song song với XP).

        ⚠️ GHI CHÚ QUAN TRỌNG (audit trước đó): hàm này KHÔNG được gọi ở đâu
        trong game hiện tại — đường lên cấp DUY NHẤT đang chạy thật là
        `gain_xp()` (qua giết titan, xem `loot_system.py`). `upgrade()` là API
        đã implement đầy đủ nhưng CHƯA được nối vào UI/gameplay nào. Giữ nguyên
        (không xoá) theo quyết định của nhóm — có thể dùng sau nếu thiết kế đổi ý.

        Thuật toán (nếu được gọi): đã max cấp → log rồi thôi. Chưa max →
        `ResourceManager.spend(get_upgrade_cost())` (raise/return False nếu không
        đủ — tuỳ implementation của `spend`), tăng `_level`, tính lại `_max_hp`,
        hồi thêm `HP_PER_LEVEL` (không vượt max mới).

        Chỉ số: balance.COMMANDER_UPGRADE_COSTS, balance.COMMANDER_HP_PER_LEVEL.
        """
        from structures.buildings.resource_manager import ResourceManager

        if self._level >= self.MAX_LEVEL:
            logger.info("%s already at max level", self.NAME)
            return
        cost = self.get_upgrade_cost()
        ResourceManager.get_instance().spend(cost)
        self._level += 1
        new_max = self._compute_max_hp(self._level)
        self._hp = min(new_max, self._hp + self.HP_PER_LEVEL)
        self._max_hp = new_max
        logger.info("%s upgraded → lv %d", self.NAME, self._level)

    def get_upgrade_cost(self) -> ResourceBundle:
        """Chi phí để nâng lên cấp TIẾP THEO — tra `UPGRADE_COSTS[level]`.

        Không có mốc giá cho cấp hiện tại (vd cấp > 5, bảng chỉ định nghĩa tới 5)
        → trả `ResourceBundle()` rỗng (miễn phí — cần xem xét nếu `upgrade()`
        được kích hoạt dùng thật trong tương lai).
        """
        return self.UPGRADE_COSTS.get(self._level, ResourceBundle())
