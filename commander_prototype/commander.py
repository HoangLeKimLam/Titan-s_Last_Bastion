"""commander.py — abstract base Commander class.

Design decisions locked with the team:
    1. NO `Character` intermediate class. Commander inherits Entity directly.
       (Documentation hinted at one, but the team voted to skip it.)
    2. A stage defeat (HP <= 0) drops the commander's level by 1
       (floor = 1) and then revives at full HP for the next attempt.
       This happens INSIDE Commander.take_damage() so subclasses get it free.

Inherits:
    Entity        — id, x, y, is_alive, abstract update/draw
    IAttackable   — take_damage(amount, dtype)
    IMovable      — move(destination)
    ISkillUser    — use_skill(skill_id), get_cooldown(skill_id)
    IUpgradable   — upgrade(), get_upgrade_cost()

Subclasses (Eren, Mikasa, Levi, Armin, Hange) must override:
    NAME, STAGE, SPRITE_FOLDER          — identity / asset hooks
    SKILL_COOLDOWNS                     — {'Q': float, 'E': float, 'R': float}
    _activate_skill(skill_id)           — dispatch to concrete skill methods
"""
from __future__ import annotations

import logging
import math
from abc import abstractmethod
from typing import Optional

import pygame

from _core.entity import Entity
from _core.event_bus import GameEventBus
from _core.game_state import ResourceBundle
from _core.interfaces import IAttackable, IMovable, ISkillUser, IUpgradable
from animation import CommanderAnimator, load_clips

logger = logging.getLogger(__name__)


class Commander(Entity, IAttackable, IMovable, ISkillUser, IUpgradable):
    """Abstract base for all 5 commanders."""

    # --- Subclass overrides ---------------------------------------------
    NAME: str = "Commander"
    STAGE: int = 1
    SPRITE_FOLDER: str = ""
    SPRITE_FRAMES: dict = {}        # subclass picks an EREN_/MIKASA_ map
    FRAME_WIDTH: int = 100          # depends on the chosen sprite pack
    FRAME_HEIGHT: int = 64
    # All commanders render at this final on-screen pixel height (idle
    # standing silhouette). Each pack has different source-frame
    # proportions, so the scale factor is computed per-subclass to
    # normalise size — see animation.load_clips().
    TARGET_HEIGHT_PX: int = 100
    ENTITY_TYPE: str = "commander"

    SKILL_COOLDOWNS: dict = {"Q": 5.0, "E": 8.0, "R": 30.0}

    # --- Q / E / R skill tuning (subclasses can override per character) -
    Q_RADIUS: int = 80
    Q_HIT_COUNT: int = 3
    Q_DAMAGE_PER_HIT: int = 40
    Q_DASH_GAP: int = 60

    # E (Grappling Swing) — replaces ODM Surge.
    # State machine: idle → aiming → flying → (aiming|idle). See module
    # docstring of begin_aim() for full semantics.
    #
    # Aiming: the player scales the swing DISTANCE with the mouse cursor
    # (range = cursor magnitude, clamped), but the swing only LAUNCHES when
    # the aim DIRECTION points at a công trình (terrain tower) or a titan
    # (small/large) within E_MAX_RANGE_PX. Pointing at empty space leaves the
    # aim "invalid" (faint arrow) and confirm_swing is a no-op.
    E_RANGE_PX: int = 250            # default swing distance (mouse 1:1)
    E_MIN_RANGE_PX: int = 60         # clamp lower — prevents micro-jumps
    E_MAX_RANGE_PX: int = 480        # clamp upper — caps tele + aim ray length
    E_BASE_CHARGES: int = 6          # base charges granted when E starts
    # Absolute cap (base + bonus stack). Kept at base + 5 so the bonus
    # mechanic still has the same +5 headroom it had at base 3 / cap 8.
    E_MAX_CHARGES: int = 11
    E_BONUS_LIFETIME: float = 6.0    # bonus pool expires after this many s
    E_FLIGHT_DURATION: float = 0.35  # how long one swing flight lasts (up/level)
    E_AIM_TIMEOUT: float = 3.0       # auto-cancel aim after no input
    # Swinging DOWN (target below the commander) is a little slower so the
    # descent reads as a controlled drop rather than a teleport.
    E_DOWNSWING_SLOWDOWN: float = 1.3   # flight duration ×1.3 when going down
    # The swing only launches when the LANDING SPOT (arrow tip = mouse cursor =
    # origin + dir*range) lands on a target. E_TARGET_PAD_PX is the snap
    # tolerance around a target's body so the cursor doesn't have to be pixel-perfect.
    E_TARGET_PAD_PX: float = 24.0       # snap tolerance around a target's body

    # --- Titan-damage STACK mechanic (replaces the old flat ×2.5 bonus) ---
    # Consecutive basic-attack (LMB) hits on titans build a stack. The Nth
    # consecutive hit deals base × TITAN_DMG_STACK_MULTS[min(N-1, 3)] so the
    # 1st/2nd/3rd/4th hit = 125%/150%/200%/250% of base. The 5th hit onward
    # stays at 250%. Missing for TITAN_STACK_RESET_WINDOW seconds resets it.
    TITAN_DMG_STACK_MULTS: tuple = (1.25, 1.50, 2.00, 2.50)
    TITAN_STACK_RESET_WINDOW: float = 1.5

    R_DURATION: float = 10.0
    R_RADIUS: int = 150
    R_DAMAGE: int = 150

    # --- Basic-attack combo (LMB: attack1 → attack2 → attack3 → wrap) ----
    # Hit zone is a CONE in front of the commander (oriented by facing dir).
    # `RADIUS` = cone length (depth); `CONE_HALF_ANGLE_DEG` = half-opening.
    BASIC_ATTACK_RADIUS: int = 130
    BASIC_ATTACK_CONE_HALF_ANGLE_DEG: float = 35.0   # 70° total opening
    # Close-range forgiveness: at short forward distances the cone is too
    # narrow, so an enemy you're standing right next to (slightly off-axis or
    # on top of you) would miss. Enforce a minimum lateral half-width so
    # point-blank melee always connects in the forward hemisphere.
    BASIC_ATTACK_MIN_LATERAL_PX: float = 55.0
    BASIC_ATTACK_DAMAGES: tuple = (25, 35, 60)       # damage per combo step
    COMBO_RESET_WINDOW: float = 1.5                  # idle seconds → reset
    # Cancel allowed once `anim_left <= anim_total * COMBO_CANCEL_THRESHOLD`
    # (i.e. in the second half of the current swing).
    COMBO_CANCEL_THRESHOLD: float = 0.5

    # --- Stat scaling ----------------------------------------------------
    BASE_HP: int = 200
    HP_PER_LEVEL: int = 40
    BASE_SPEED: float = 160.0  # pixels / second
    MAX_LEVEL: int = 10

    UPGRADE_COSTS: dict = {
        1: ResourceBundle(stone=30, wood=20),
        2: ResourceBundle(stone=50, wood=30, ore=5),
        3: ResourceBundle(stone=80, wood=40, ore=10),
        4: ResourceBundle(stone=120, wood=60, ore=20, crystal=2),
        5: ResourceBundle(stone=180, wood=90, ore=30, crystal=5),
    }

    # --- Construction ----------------------------------------------------

    def __init__(self, x: float, y: float, level: int = 1, *,
                 headless: bool = False) -> None:
        super().__init__(x, y)
        self._level = max(1, int(level))
        self._max_hp = self._compute_max_hp(self._level)
        self._hp = self._max_hp
        self._speed = self.BASE_SPEED

        self._skill_cd: dict = {sid: 0.0 for sid in self.SKILL_COOLDOWNS}
        self._invincible: bool = False
        self._inv_timer: float = 0.0

        # 3-hit basic-attack combo state
        self._combo_step: int = 0          # which attack index to play NEXT
        self._combo_anim_left: float = 0.0  # remaining swing time
        self._combo_anim_total: float = 0.0
        self._combo_reset_left: float = 0.0  # COMBO_RESET_WINDOW countdown

        # Titan-damage stack: counts consecutive LMB hits on titans.
        self._titan_stack: int = 0            # 0..len(TITAN_DMG_STACK_MULTS)
        self._titan_stack_timer: float = 0.0  # resets stack when it hits 0

        # E (Grappling Swing) state
        self._e_state: str = "idle"           # "idle" | "aiming" | "flying"
        self._e_charges: int = 0              # charges left in current session
        self._e_bonus_count_in_session: int = 0  # subset that are bonus
        self._e_bonus_pool: int = 0           # carryover bonus charges
        self._e_bonus_timer: float = 0.0      # expiry countdown for bonus pool
        self._e_aim_timer: float = 0.0        # auto-cancel countdown
        self._e_aim_dir: tuple = (1.0, 0.0)   # current aim unit vector
        self._e_aim_range: float = self.E_RANGE_PX  # current swing distance
        self._e_flight_start: tuple = (0.0, 0.0)
        self._e_flight_target: tuple = (0.0, 0.0)
        self._e_flight_progress: float = 0.0  # 0..1 lerp
        self._e_is_bonus_swing: bool = False  # current flight came from a bonus charge
        self._e_aim_valid: bool = False       # True when aim direction hits a target
        self._e_flight_dur: float = self.E_FLIGHT_DURATION  # per-flight duration

        self._move_target: Optional[tuple] = None
        self._headless = headless

        # Use character-bbox-based scaling so the actual CHARACTER (not
        # the canvas padding) ends up at the same on-screen height across
        # every commander, regardless of source-frame proportions.
        clips = load_clips(
            self.SPRITE_FOLDER, self.SPRITE_FRAMES,
            frame_width=self.FRAME_WIDTH,
            frame_height=self.FRAME_HEIGHT,
            target_character_height=self.TARGET_HEIGHT_PX,
            headless=headless,
        )
        self._animator = CommanderAnimator(clips, initial_state="idle")

    # --- Stats / read-only props -----------------------------------------

    def _compute_max_hp(self, level: int) -> int:
        return self.BASE_HP + (level - 1) * self.HP_PER_LEVEL

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
    def is_invincible(self) -> bool:
        return self._invincible

    # --- Entity contract (update + draw) ---------------------------------

    def update(self, dt: float) -> None:
        # Skill cooldowns
        for sid in self._skill_cd:
            if self._skill_cd[sid] > 0:
                self._skill_cd[sid] = max(0.0, self._skill_cd[sid] - dt)

        # Invincibility timer
        if self._invincible:
            self._inv_timer -= dt
            if self._inv_timer <= 0:
                self._invincible = False
                self._inv_timer = 0.0

        # Basic-attack swing timer
        if self._combo_anim_left > 0:
            self._combo_anim_left = max(0.0, self._combo_anim_left - dt)

        # Combo reset window — when it elapses, next click starts at attack1
        if self._combo_reset_left > 0:
            self._combo_reset_left = max(0.0, self._combo_reset_left - dt)
            if self._combo_reset_left == 0:
                self._combo_step = 0

        # Titan-damage stack window — no hit for TITAN_STACK_RESET_WINDOW
        # seconds drops the stack back to 0 (next hit starts again at 125%).
        if self._titan_stack_timer > 0:
            self._titan_stack_timer = max(0.0, self._titan_stack_timer - dt)
            if self._titan_stack_timer == 0.0:
                self._titan_stack = 0

        # E session timers
        if self._e_bonus_pool > 0 and self._e_bonus_timer > 0:
            self._e_bonus_timer = max(0.0, self._e_bonus_timer - dt)
            if self._e_bonus_timer == 0.0:
                # Bonus pool expired — drop any carryover bonus charges
                self._e_bonus_pool = 0
                # Also drop bonus charges from active session if any
                if self._e_state != "idle" and self._e_bonus_count_in_session > 0:
                    drop = self._e_bonus_count_in_session
                    self._e_charges = max(0, self._e_charges - drop)
                    self._e_bonus_count_in_session = 0
                    if self._e_charges == 0 and self._e_state == "aiming":
                        self._end_session(set_cooldown=False)

        if self._e_state == "aiming":
            self._e_aim_timer -= dt
            if self._e_aim_timer <= 0:
                self.cancel_swing()
        elif self._e_state == "flying":
            self._step_flight(dt)

        # Movement toward queued target — disabled while in E flight
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
        # Face the direction of travel
        if abs(dx) > 0.5:
            self._animator.set_facing(dx > 0)
        # Walk animation only when no higher-priority one-shot is running.
        if self._animator.state == "idle":
            self._animator.set_state("walk")
        step = self._speed * dt
        if step >= dist:
            self.x, self.y = destination
            self._move_target = None
        else:
            self.x += (dx / dist) * step
            self.y += (dy / dist) * step

    def draw(self, screen) -> None:
        frame = self._animator.current_frame()
        sprite_h = 36  # fallback radius for circle placeholder
        if frame is not None:
            rect = frame.get_rect(midbottom=(int(self.x), int(self.y)))
            screen.blit(frame, rect)
            sprite_h = frame.get_height()
        else:
            pygame.draw.circle(screen, (40, 200, 90),
                               (int(self.x), int(self.y) - sprite_h // 2),
                               sprite_h // 2)

        # HP bar — anchored above the actual sprite top
        bar_w = 60
        ratio = self._hp / self._max_hp if self._max_hp else 0.0
        bx = int(self.x) - bar_w // 2
        by = int(self.y) - sprite_h - 12
        pygame.draw.rect(screen, (180, 30, 30), (bx, by, bar_w, 6))
        pygame.draw.rect(screen, (60, 220, 60),
                         (bx, by, int(bar_w * ratio), 6))

        # Invincibility ring around sprite center
        if self._invincible:
            cx, cy = int(self.x), int(self.y) - sprite_h // 2
            pygame.draw.circle(screen, (255, 215, 0), (cx, cy),
                               sprite_h // 2 + 8, 3)

        # Basic-attack cone outline while a swing is in progress
        if self._combo_anim_left > 0:
            self._draw_attack_cone(screen)

        # E-session overlays: aim circle + bonus-pool timer ring.
        # Shown while AIMING and also while FLYING, so the player can see and
        # pick the next target to switch to mid-air (press E to redirect).
        if self._e_state in ("aiming", "flying"):
            self._draw_aim_overlay(screen)
        if self._e_bonus_pool > 0 or self._e_bonus_count_in_session > 0:
            self._draw_bonus_ring(screen)

    def _draw_aim_overlay(self, screen) -> None:
        """Aim circle (mouse-scaled range) + direction arrow.

        Brightness encodes validity: when the aim direction points at a công
        trình / titan (`_e_aim_valid`) the arrow + ring are BOLD/bright (the
        swing will fire); otherwise they are FAINT (cannot fly yet). The circle
        radius reflects `_e_aim_range` so the player still sees the zoom.
        """
        cx, cy = int(self.x), int(self.y) - 40
        r = int(self._e_aim_range)
        valid = self._e_aim_valid
        # Same yellow hue, brighter + thicker when a swing is possible.
        arrow_col = (255, 230, 100) if valid else (150, 138, 80)
        ring_col = (235, 215, 90) if valid else (110, 100, 50)
        width = 4 if valid else 2
        try:
            # Faint max-range ring (so player sees the upper bound)
            pygame.draw.circle(screen, (90, 80, 30),
                               (cx, cy), self.E_MAX_RANGE_PX, 1)
            # Live aim circle at current (mouse-scaled) range
            pygame.draw.circle(screen, ring_col, (cx, cy), r, 2)
            dx, dy = self._e_aim_dir
            tip = (int(cx + dx * r), int(cy + dy * r))
            pygame.draw.line(screen, arrow_col, (cx, cy), tip, width)
            # Arrowhead — two short lines back from tip
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

    def _draw_bonus_ring(self, screen) -> None:
        """Circular progress ring around head showing bonus-pool TTL + count."""
        cx, cy = int(self.x), int(self.y) - 90
        radius = 22
        try:
            # Background ring
            pygame.draw.circle(screen, (60, 50, 20), (cx, cy), radius, 2)
            # Filled arc proportional to timer
            frac = (self._e_bonus_timer / self.E_BONUS_LIFETIME
                    if self.E_BONUS_LIFETIME > 0 else 0.0)
            frac = max(0.0, min(1.0, frac))
            if frac > 0:
                end_angle = -math.pi / 2 + frac * 2 * math.pi
                rect = pygame.Rect(cx - radius, cy - radius,
                                   radius * 2, radius * 2)
                pygame.draw.arc(screen, (255, 200, 80), rect,
                                -math.pi / 2, end_angle, 4)
            # Count label
            total_bonus = self._e_bonus_pool + self._e_bonus_count_in_session
            font = pygame.font.SysFont("consolas", 16, bold=True)
            label = font.render(str(total_bonus), True, (255, 220, 100))
            screen.blit(label, label.get_rect(center=(cx, cy)))
        except (AttributeError, pygame.error):
            pass

    # --- IAttackable -----------------------------------------------------

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
        """Stage defeat penalty: -1 level (floor 1), revive at full HP."""
        old_level = self._level
        self._level = max(1, self._level - 1)
        self._max_hp = self._compute_max_hp(self._level)
        self._hp = self._max_hp
        self._invincible = False
        self._inv_timer = 0.0
        self._animator.set_state("dying")

        GameEventBus.get_instance().publish("commander_defeated", {
            "commander_id": self.id,
            "name": self.NAME,
            "old_level": old_level,
            "new_level": self._level,
        })
        logger.info("%s defeated: lv %d → %d (revived at full HP)",
                    self.NAME, old_level, self._level)

    # --- Basic attack (LMB) ----------------------------------------------

    def basic_attack(self) -> None:
        """3-hit melee combo: attack1 → attack2 → attack3 → wrap to attack1.

        Rules (locked with team):
        - **Cancel sớm**: clicking during the second half of the current swing
          cancels its remaining frames and chains immediately. Clicks during
          the first half are ignored.
        - **Reset window**: COMBO_RESET_WINDOW seconds of no clicks resets the
          combo back to step 0 (attack1).
        - **Damage**: BASIC_ATTACK_DAMAGES[step] is the *base*; the actual hit
          is base × the current titan-damage STACK multiplier.
        - **Stack** (new): each LMB that connects with a titan raises the stack;
          the 1st/2nd/3rd/4th consecutive hit deals 125%/150%/200%/250% of base
          and the 5th+ stays at 250%. No hit for TITAN_STACK_RESET_WINDOW
          seconds resets the stack to 0.
        - **AoE**: every titan inside the front-facing cone takes the damage.
        """
        # First-half lockout
        if (self._combo_anim_total > 0
                and self._combo_anim_left > self._combo_anim_total
                * self.COMBO_CANCEL_THRESHOLD):
            return

        # Reset combo if idle window elapsed
        if self._combo_reset_left <= 0:
            self._combo_step = 0

        # Reset the titan-damage stack if its window already elapsed, so this
        # swing starts a fresh chain at 125%.
        if self._titan_stack_timer <= 0:
            self._titan_stack = 0

        step = self._combo_step
        state = f"attack{step + 1}"
        base_damage = self.BASIC_ATTACK_DAMAGES[step]
        stack_idx = min(self._titan_stack, len(self.TITAN_DMG_STACK_MULTS) - 1)
        mult = self.TITAN_DMG_STACK_MULTS[stack_idx]
        damage = int(round(base_damage * mult))

        # Visual
        self._animator.set_state(state)

        # Damage every titan inside the front-facing cone.
        # Side-effect: LMB hit on a LargeTitan while in an active E session
        # grants +1 bonus charge (capped at E_MAX_CHARGES) and refreshes the
        # bonus-pool expiry timer.
        from stubs import WorldQuery
        e_session_active = self._e_state in ("aiming", "flying")
        hit_any = False
        for entity in WorldQuery.all():
            if getattr(entity, "ENTITY_TYPE", None) != "titan":
                continue
            if not getattr(entity, "is_alive", False):
                continue
            if not self._in_attack_cone(entity.x, entity.y):
                continue
            entity.take_damage(amount=damage, dtype="slash")
            hit_any = True
            if e_session_active and getattr(entity, "IS_LARGE", False):
                self._grant_bonus_charge()

        # A connecting swing advances the stack and refreshes its window.
        if hit_any:
            self._titan_stack = min(self._titan_stack + 1,
                                    len(self.TITAN_DMG_STACK_MULTS))
            self._titan_stack_timer = self.TITAN_STACK_RESET_WINDOW

        # Swing lockout + idle-reset window
        duration = self._animator.clip_duration(state)
        self._combo_anim_total = duration
        self._combo_anim_left = duration
        self._combo_reset_left = self.COMBO_RESET_WINDOW

        # Advance combo counter for the next click
        self._combo_step = (step + 1) % len(self.BASIC_ATTACK_DAMAGES)

    @property
    def titan_stack(self) -> int:
        """Current consecutive-hit stack on titans (0..len multipliers)."""
        return self._titan_stack

    @property
    def combo_step(self) -> int:
        """Index (0..2) of the attack the NEXT basic_attack() will play."""
        return self._combo_step

    def _in_attack_cone(self, tx: float, ty: float) -> bool:
        """True if (tx, ty) lies inside the front-facing basic-attack cone.

        Cone origin = commander position, oriented along facing direction.
        Depth = BASIC_ATTACK_RADIUS, half-opening = CONE_HALF_ANGLE_DEG.

        Close-range fix: the lateral half-width never drops below
        BASIC_ATTACK_MIN_LATERAL_PX, so an enemy you're standing right next to
        (or directly on top of, forward == 0) still connects. Targets strictly
        BEHIND the facing direction still miss.
        """
        dx = tx - self.x
        dy = ty - self.y
        facing = 1.0 if self._animator.facing_right else -1.0
        forward = dx * facing       # >=0 means in front of / level with commander
        if forward < 0 or forward > self.BASIC_ATTACK_RADIUS:
            return False
        half_angle_rad = math.radians(self.BASIC_ATTACK_CONE_HALF_ANGLE_DEG)
        max_lateral = max(self.BASIC_ATTACK_MIN_LATERAL_PX,
                          forward * math.tan(half_angle_rad))
        return abs(dy) <= max_lateral

    def _draw_attack_cone(self, screen) -> None:
        """Faint outline of the basic-attack cone (drawn while swinging)."""
        facing = 1.0 if self._animator.facing_right else -1.0
        half = math.radians(self.BASIC_ATTACK_CONE_HALF_ANGLE_DEG)
        r = self.BASIC_ATTACK_RADIUS
        # Origin ~ chest height for a more readable shape
        ox, oy = int(self.x), int(self.y) - 40
        far_x = ox + int(r * facing * math.cos(half))
        upper = (far_x, oy - int(r * math.sin(half)))
        lower = (far_x, oy + int(r * math.sin(half)))
        try:
            pygame.draw.polygon(screen, (255, 200, 80),
                                [(ox, oy), upper, lower], 2)
        except (AttributeError, pygame.error):
            pass

    # --- IMovable --------------------------------------------------------

    def move(self, destination: tuple) -> None:
        self._move_target = (float(destination[0]), float(destination[1]))

    # --- ISkillUser ------------------------------------------------------

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

    # --- Default Q / E / R implementations (Eren-flavoured) --------------
    # Subclasses may override any of these for character-specific behaviour;
    # default tuning lives in the Q_ / E_ / R_ class constants above.

    def _slash_combo(self) -> None:
        """Q — dash to the nearest titan, then 3-hit AoE on landing."""
        from stubs import WorldQuery

        target = WorldQuery.find_nearest(
            cx=self.x, cy=self.y, entity_type="titan",
        )
        if target is not None:
            if target.x >= self.x:
                self.x = target.x - self.Q_DASH_GAP
                self._animator.set_facing(True)
            else:
                self.x = target.x + self.Q_DASH_GAP
                self._animator.set_facing(False)
            self.y = target.y

        self._animator.set_state("skill_q")

        for titan in WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self.Q_RADIUS,
            entity_type="titan",
        ):
            for _ in range(self.Q_HIT_COUNT):
                titan.take_damage(amount=self.Q_DAMAGE_PER_HIT, dtype="slash")

    # E is no longer dispatched via use_skill — main.py calls
    # begin_aim() / confirm_swing() / cancel_swing() directly. See
    # those methods below. The old _odm_surge() is removed.

    # --- E (Grappling Swing) ---------------------------------------------

    def begin_aim(self) -> bool:
        """Press E from idle → enter AIMING with E_BASE_CHARGES (+bonus pool).

        Returns True if entry succeeded (cooldown ok), False otherwise.
        Cooldown is enforced via the regular SKILL_COOLDOWNS dict so the HUD
        keeps showing E's cooldown bar like Q and R.
        """
        if self._e_state != "idle":
            return False
        if self._skill_cd.get("E", 0.0) > 0:
            return False
        # Snapshot bonus pool into session
        bonus = self._e_bonus_pool
        self._e_charges = min(self.E_MAX_CHARGES, self.E_BASE_CHARGES + bonus)
        self._e_bonus_count_in_session = bonus
        self._e_bonus_pool = 0  # consumed — pool moves into the session
        self._e_state = "aiming"
        self._e_aim_timer = self.E_AIM_TIMEOUT
        self._e_aim_valid = False
        self._animator.set_state("skill_e")
        GameEventBus.get_instance().publish("e_session_started", {
            "commander_id": self.id,
            "name": self.NAME,
            "charges": self._e_charges,
            "bonus_in_session": self._e_bonus_count_in_session,
        })
        return True

    def set_aim_direction(self, vx: float, vy: float) -> None:
        """Update the aim arrow direction + range from raw (vx, vy) vector.

        DISTANCE: the vector magnitude becomes the swing range (clamped to
        [E_MIN_RANGE_PX, E_MAX_RANGE_PX]) — the player zooms with the mouse.

        VALIDITY: `_e_aim_valid` is True only when the LANDING SPOT (the arrow
        tip = mouse cursor = origin + dir*range) lands on a công trình (terrain
        tower) or a titan (small/large). The swing can only launch while valid
        (see confirm_swing). No-op outside AIMING.
        """
        if self._e_state != "aiming":
            return
        if not self._compute_aim(vx, vy):
            return
        # Refresh aim timer on any input
        self._e_aim_timer = self.E_AIM_TIMEOUT
        # Face the aim direction
        if abs(vx) > 0.1:
            self._animator.set_facing(vx > 0)

    def update_flight_aim(self, vx: float, vy: float) -> None:
        """Keep the aim preview LIVE during flight so the player can pick the
        next target to switch to. Updates arrow/range/validity for the overlay
        only — does not launch (use redirect_flight to actually switch). No-op
        outside FLYING.
        """
        if self._e_state != "flying":
            return
        self._compute_aim(vx, vy)

    def _compute_aim(self, vx: float, vy: float) -> bool:
        """Set aim dir + (mouse-scaled) range + landing-spot validity from a raw
        vector. Returns False if the vector is too small to use."""
        length = math.hypot(vx, vy)
        if length < 0.001:
            return False
        self._e_aim_dir = (vx / length, vy / length)
        self._e_aim_range = max(self.E_MIN_RANGE_PX,
                                min(self.E_MAX_RANGE_PX, length))
        self._e_aim_valid = self._aim_endpoint_on_target()
        return True

    # --- Landing-spot target detection (công trình / titan) --------------

    def _aim_endpoint_on_target(self) -> bool:
        """True if the swing DESTINATION lands on a valid target.

        Destination = where the arrow tip / mouse cursor is = origin +
        aim_dir * aim_range. The swing is "fly to where you point": you can
        only launch when that landing spot sits on a công trình (tower) or a
        titan (small/large), within E_TARGET_PAD_PX. A target merely lying
        somewhere along the aim line (but not at the tip) does NOT count.
        """
        from stubs import WorldQuery

        ex = self.x + self._e_aim_dir[0] * self._e_aim_range
        ey = self.y + self._e_aim_dir[1] * self._e_aim_range
        pad = self.E_TARGET_PAD_PX

        # Titans — landing spot within the (padded) body radius.
        for entity in WorldQuery.all():
            if getattr(entity, "ENTITY_TYPE", None) != "titan":
                continue
            if not getattr(entity, "is_alive", False):
                continue
            radius = 22.0 * getattr(entity, "_size_scale", 1.0) + pad
            if (ex - entity.x) ** 2 + (ey - entity.y) ** 2 <= radius * radius:
                return True

        # Structures — landing spot inside the (padded) tower rect.
        for rect in WorldQuery.structures():
            if rect.inflate(pad * 2, pad * 2).collidepoint(ex, ey):
                return True
        return False

    def confirm_swing(self, direction: Optional[tuple] = None) -> None:
        """Launch a flight from AIMING. Consumes one charge.

        If `direction` is given, overrides the current aim_dir first. The swing
        fires at the mouse-scaled range but ONLY when the aim direction is valid
        (pointing at a công trình / titan); otherwise it is a no-op (no charge
        spent). Swinging DOWN (target below) runs E_DOWNSWING_SLOWDOWN× slower.
        Prefers bonus charges (they expire) for bookkeeping.
        """
        if self._e_state != "aiming" or self._e_charges <= 0:
            return
        if direction is not None:
            self.set_aim_direction(direction[0], direction[1])

        # Must be aimed at a công trình / titan to launch.
        if not self._e_aim_valid:
            return

        self._launch_flight()

    def _launch_flight(self) -> None:
        """Consume one charge and start a flight from the CURRENT position
        along the current aim dir/range. Assumes the aim is already validated.
        Shared by confirm_swing() (from aiming) and redirect_flight() (mid-air).
        """
        # Prefer bonus charges (they expire) for bookkeeping.
        if self._e_bonus_count_in_session > 0:
            self._e_is_bonus_swing = True
            self._e_bonus_count_in_session -= 1
        else:
            self._e_is_bonus_swing = False

        self._e_charges -= 1
        dx, dy = self._e_aim_dir
        self._e_flight_start = (self.x, self.y)
        self._e_flight_target = (
            self.x + dx * self._e_aim_range,
            self.y + dy * self._e_aim_range,
        )
        # Slow the flight a touch when swinging downward.
        going_down = self._e_flight_target[1] > self._e_flight_start[1]
        self._e_flight_dur = (self.E_FLIGHT_DURATION * self.E_DOWNSWING_SLOWDOWN
                              if going_down else self.E_FLIGHT_DURATION)
        self._e_flight_progress = 0.0
        self._e_aim_valid = False
        self._e_state = "flying"
        self._animator.set_state("skill_e")

    def cancel_swing(self) -> None:
        """SPACE = abort E session. Drops in place if flying."""
        if self._e_state == "idle":
            return
        self._end_session(set_cooldown=True)

    def _step_flight(self, dt: float) -> None:
        """Lerp toward flight target; transition out when progress hits 1."""
        if self._e_flight_dur <= 0:
            self._e_flight_progress = 1.0
        else:
            self._e_flight_progress += dt / self._e_flight_dur
        if self._e_flight_progress >= 1.0:
            self.x, self.y = self._e_flight_target
            self._e_flight_progress = 1.0
            self._e_is_bonus_swing = False
            if self._e_charges > 0:
                # Chain to next aim
                self._e_state = "aiming"
                self._e_aim_timer = self.E_AIM_TIMEOUT
                self._e_aim_valid = False
            else:
                self._end_session(set_cooldown=True)
        else:
            # Lerp position
            sx, sy = self._e_flight_start
            tx, ty = self._e_flight_target
            self.x = sx + (tx - sx) * self._e_flight_progress
            self.y = sy + (ty - sy) * self._e_flight_progress

    def redirect_flight(self, vx: float, vy: float) -> bool:
        """Mid-flight E: instantly change course toward a new target.

        While FLYING the player can press E to redirect WITHOUT stopping to aim:
        if the cursor (vx, vy from the commander's current position) lands on a
        valid công trình / titan, a fresh flight launches from the current
        position toward it, consuming one charge. If the cursor isn't on a
        valid target, or no charge remains, nothing happens and the current
        flight continues. Returns True if it redirected.
        """
        if self._e_state != "flying" or self._e_charges <= 0:
            return False
        # Set the prospective aim, then validate the landing spot from HERE.
        if not self._compute_aim(vx, vy):
            return False
        if not self._e_aim_valid:
            return False
        self._launch_flight()   # new flight from current position, costs 1 charge
        return True

    def _grant_bonus_charge(self) -> None:
        """LMB-hit-LargeTitan reward: +1 charge (cap E_MAX_CHARGES), refresh timer."""
        if self._e_charges >= self.E_MAX_CHARGES:
            # Already at cap — still refresh timer so the pool isn't wasted
            self._e_bonus_timer = self.E_BONUS_LIFETIME
            return
        self._e_charges += 1
        self._e_bonus_count_in_session += 1
        self._e_bonus_pool = min(self._e_bonus_pool + 1,
                                 self.E_MAX_CHARGES - self.E_BASE_CHARGES)
        self._e_bonus_timer = self.E_BONUS_LIFETIME
        GameEventBus.get_instance().publish("e_charge_bonus_added", {
            "commander_id": self.id,
            "name": self.NAME,
            "charges": self._e_charges,
            "bonus_in_session": self._e_bonus_count_in_session,
        })

    def _end_session(self, *, set_cooldown: bool) -> None:
        """Reset all E session state. Optionally apply E cooldown."""
        self._e_state = "idle"
        self._e_charges = 0
        self._e_bonus_count_in_session = 0
        self._e_aim_timer = 0.0
        self._e_flight_progress = 0.0
        self._e_is_bonus_swing = False
        self._e_aim_valid = False
        self._e_flight_dur = self.E_FLIGHT_DURATION
        if set_cooldown:
            self._skill_cd["E"] = float(self.SKILL_COOLDOWNS.get("E", 0.0))
        self._animator.set_state("idle")

    def _titan_form(self) -> None:
        """R — invincibility for R_DURATION + R_RADIUS AoE on activation."""
        from stubs import WorldQuery

        self._animator.set_state("skill_r")
        self._invincible = True
        self._inv_timer = self.R_DURATION
        for titan in WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self.R_RADIUS,
            entity_type="titan",
        ):
            titan.take_damage(amount=self.R_DAMAGE, dtype="aoe")

    # --- IUpgradable -----------------------------------------------------

    def upgrade(self) -> None:
        # Imported lazily so unit tests can patch / reset ResourceManager.
        from stubs import ResourceManager

        if self._level >= self.MAX_LEVEL:
            logger.info("%s already at max level", self.NAME)
            return

        cost = self.get_upgrade_cost()
        ResourceManager.get_instance().spend(cost)  # raises if not enough

        self._level += 1
        new_max = self._compute_max_hp(self._level)
        # Add the per-level gain to current HP rather than full heal
        self._hp = min(new_max, self._hp + self.HP_PER_LEVEL)
        self._max_hp = new_max
        logger.info("%s upgraded → lv %d", self.NAME, self._level)

    def get_upgrade_cost(self) -> ResourceBundle:
        return self.UPGRADE_COSTS.get(self._level, ResourceBundle())
