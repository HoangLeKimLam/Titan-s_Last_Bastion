# characters/commanders/commander.py — abstract base Commander class.
#
# Design decisions (locked with team):
#   1. No Character intermediate class — Commander inherits Entity directly.
#   2. Stage defeat (HP <= 0) drops commander level by 1 (floor 1), revives at full HP.
#
# Subclasses (Eren, Mikasa, Armin) must override:
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

    SKILL_COOLDOWNS: dict = {"Q": 5.0, "E": 8.0, "R": 30.0}

    # --- Skill tuning (subclasses may override per character) --------------
    Q_RADIUS: int = 80
    Q_HIT_COUNT: int = 3
    Q_DAMAGE_PER_HIT: int = 40
    Q_DASH_GAP: int = 60

    # E (Grappling Swing) state machine: idle → aiming → flying → (aiming|idle).
    # Aim is VALID only when the landing spot (arrow tip) is on a tower or titan.
    E_RANGE_PX: int = 250
    E_MIN_RANGE_PX: int = 60
    E_MAX_RANGE_PX: int = 480
    E_BASE_CHARGES: int = 6
    E_MAX_CHARGES: int = 11        # base + up to 5 bonus charges
    E_BONUS_LIFETIME: float = 6.0  # bonus pool expiry (seconds)
    E_FLIGHT_DURATION: float = 0.35
    E_AIM_TIMEOUT: float = 3.0
    E_DOWNSWING_SLOWDOWN: float = 1.3   # downward swings are 30% slower
    E_TARGET_PAD_PX: float = 24.0       # snap tolerance around a target body

    # --- Titan-damage stack -----------------------------------------------
    # Consecutive LMB hits on titans build a stack. The Nth hit deals
    # base × TITAN_DMG_STACK_MULTS[min(N-1,3)]:  125%/150%/200%/250%.
    # No hit for TITAN_STACK_RESET_WINDOW seconds resets to 0.
    TITAN_DMG_STACK_MULTS: tuple = (1.25, 1.50, 2.00, 2.50)
    TITAN_STACK_RESET_WINDOW: float = 1.5

    R_DURATION: float = 10.0
    R_RADIUS: int = 150
    R_DAMAGE: int = 150

    # --- Basic-attack combo (LMB: attack1 → attack2 → attack3 → wrap) ----
    BASIC_ATTACK_RADIUS: int = 90
    BASIC_ATTACK_CONE_HALF_ANGLE_DEG: float = 28.0   # 56° total opening
    BASIC_ATTACK_MIN_LATERAL_PX: float = 40.0        # point-blank forgiveness
    BASIC_ATTACK_DAMAGES: tuple = (25, 35, 60)
    COMBO_RESET_WINDOW: float = 1.5
    COMBO_CANCEL_THRESHOLD: float = 0.5   # cancel allowed in second half of swing

    # --- Stat scaling -----------------------------------------------------
    BASE_HP: int = 200
    HP_PER_LEVEL: int = 40
    BASE_SPEED: float = 150.0
    MAX_LEVEL: int = 10

    UPGRADE_COSTS: dict = {
        1: ResourceBundle(stone=30, wood=20),
        2: ResourceBundle(stone=50, wood=30, ore=5),
        3: ResourceBundle(stone=80, wood=40, ore=10),
        4: ResourceBundle(stone=120, wood=60, ore=20, fire_ore=2),
        5: ResourceBundle(stone=180, wood=90, ore=30, fire_ore=5),
    }

    # --- Construction -------------------------------------------------------

    def __init__(self, x: float, y: float, level: int = 1, xp: int = 0, *,
                 headless: bool = False) -> None:
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
        return self.BASE_HP + (level - 1) * self.HP_PER_LEVEL

    def _compute_max_xp(self, level: int) -> int:
        return 100 * level

    def gain_xp(self, amount: int) -> None:
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
        return self._hp

    @property
    def max_hp(self) -> int:
        return self._max_hp

    @property
    def level(self) -> int:
        return self._level

    @property
    def xp(self) -> int:
        return self._xp

    @property
    def max_xp(self) -> int:
        return self._max_xp

    @property
    def is_invincible(self) -> bool:
        return self._invincible

    @property
    def titan_stack(self) -> int:
        return self._titan_stack

    @property
    def combo_step(self) -> int:
        return self._combo_step

    # --- Entity contract ---------------------------------------------------

    def update(self, dt: float) -> None:

        # Rock AoE pushback tween từ BeastTitan
        if getattr(self, 'pushback_vx', 0.0) != 0.0 or getattr(self, 'pushback_vy', 0.0) != 0.0:
            from characters.titans.attackstrategy import RockProjectile
            RockProjectile.apply_pushback_tween(self, dt)

        for sid in self._skill_cd:
            if self._skill_cd[sid] > 0:
                self._skill_cd[sid] = max(0.0, self._skill_cd[sid] - dt)

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
        if not self.is_alive:
            return
        if self._invincible:
            logger.debug("%s ignored %d %s damage (invincible)",
                         self.NAME, amount, dtype)
            return
        self._hp -= max(0, int(amount))
        if self._hp <= 0:
            self._on_defeat()
        else:
            self._animator.set_state("hurt")


    def _on_defeat(self) -> None:
        """Defeat: giảm 1 level, ẩn khỏi màn, đặt timer hồi sinh tại HQ."""
        old_level = self._level
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

    def basic_attack(self) -> None:
        """3-hit melee combo attack1 → attack2 → attack3 → wrap.

        Hitting a titan advances the titan-damage stack (125%/150%/200%/250%).
        Hitting a LargeTitan during an E session grants +1 bonus E charge.
        """
        if (self._combo_anim_total > 0
                and self._combo_anim_left > self._combo_anim_total
                * self.COMBO_CANCEL_THRESHOLD):
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
        damage = int(round(base_damage * mult))

        self._animator.set_state(state)

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
        self._move_target = (float(destination[0]), float(destination[1]))

    # --- ISkillUser --------------------------------------------------------

    def use_skill(self, skill_id: str) -> None:
        if skill_id not in self.SKILL_COOLDOWNS:
            raise ValueError(f"Invalid skill id: {skill_id!r} (expected Q/E/R)")
        if self._skill_cd[skill_id] > 0:
            return
        self._activate_skill(skill_id)
        self._skill_cd[skill_id] = float(self.SKILL_COOLDOWNS[skill_id])

    def get_cooldown(self, skill_id: str) -> float:
        return max(0.0, float(self._skill_cd.get(skill_id, 0.0)))

    @abstractmethod
    def _activate_skill(self, skill_id: str) -> None:
        """Subclass dispatches skill_id → its concrete skill method."""
        ...

    # --- Q / E / R default implementations (Eren-flavoured) ---------------

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
        """Consume one charge and start a flight along the current aim. Assumes aim is valid."""
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
        self._invincible = True
        self._inv_timer = self.R_DURATION
        for titan in WorldQuery.find_in_radius(cx=self.x, cy=self.y,
                                               radius=self.R_RADIUS,
                                               entity_type="titan"):
            titan.take_damage(amount=self.R_DAMAGE, dtype="aoe", attacker=self)

    # --- IUpgradable -------------------------------------------------------

    def upgrade(self) -> None:
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
        return self.UPGRADE_COSTS.get(self._level, ResourceBundle())
