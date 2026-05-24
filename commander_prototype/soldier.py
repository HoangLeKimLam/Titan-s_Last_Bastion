"""soldier.py — ally foot-soldiers deployed in squads against titans.

Three classes with distinct roles (locked with the team):

    ArcherSoldier  — ranged, high damage, fragile (low HP / no defense).
    LancerSoldier  — fast, medium defense, lower damage than the archer.
    WarriorSoldier — tanky (high HP / defense) but slow + low damage, and
                     TAUNTS: nearby titans prefer to attack a warrior, shielding
                     the squishier archers/lancers behind it.

Behaviour (Soldier.update):
    1. If it has no live titan target, acquire the nearest titan.
    2. Walk straight toward the target (no collision in the prototype).
    3. Once inside attack range, attack on cooldown — melee deals damage
       directly; the archer fires an Arrow projectile instead.

Soldiers are plain `Entity`s registered in `WorldQuery`, so the main loop's
update/draw pass and the follow-camera render them for free. Damage taken is
reduced by the soldier's defense: `max(1, incoming - defense)`.
"""
from __future__ import annotations

import math
from typing import Optional

import pygame

from _core.entity import Entity
from _core.interfaces import IAttackable, IMovable
from animation import CommanderAnimator, load_clips
import assets_config as ac


class Soldier(Entity, IAttackable, IMovable):
    """Abstract base for all ally soldiers."""

    ENTITY_TYPE: str = "soldier"
    FACTION: str = "ally"
    NAME: str = "Soldier"

    # --- Subclass sprite hooks ------------------------------------------
    SPRITE_FOLDER: str = ""
    SPRITE_FRAMES: dict = {}
    FRAME_SIZE: int = 192          # square strip frame (px)
    TARGET_HEIGHT_PX: int = 42     # rendered standing height (small)

    # --- Subclass combat stats ------------------------------------------
    BASE_HP: int = 60
    DEFENSE: int = 0               # flat damage reduction
    SPEED: float = 90.0            # px / second
    ATTACK_DAMAGE: int = 15
    ATTACK_RANGE: float = 42.0     # distance at which it can hit a titan
    ATTACK_COOLDOWN: float = 1.0
    IS_RANGED: bool = False
    TAUNTS: bool = False           # warriors set True → pull titan aggro

    # "Đi vào thành": when the soldier walks home and reaches its slot
    # (within HOME_VANISH_DIST_PX), it's marked dead so the main loop culls
    # it on the next pass. Visually this reads as the soldier walking into
    # the tower and disappearing from the map. No on-map healing.
    HOME_VANISH_DIST_PX: float = 6.0

    # Placeholder body colour when sprites are unavailable (headless/missing).
    BODY_COLOR: tuple = (90, 160, 220)
    BODY_RADIUS: int = 10

    def __init__(self, x: float, y: float, *, target=None,
                 headless: bool = False,
                 home_pos: tuple | None = None,
                 home_radius: float = 600.0) -> None:
        super().__init__(x, y)
        self._max_hp = int(self.BASE_HP)
        self._hp = int(self.BASE_HP)
        self._target = target          # the titan this soldier is attacking
        self._atk_timer: float = 0.0
        self._headless = headless
        # Squad/formation: kept for back-compat (Squad still sets _squad to
        # itself); the soldier no longer relies on Squad.regroup_center —
        # retreat anchors on the soldier's *home* instead.
        self._squad = None
        self._slot_offset: tuple = (0.0, 0.0)
        # "Thành gốc": this soldier only engages titans inside `home_radius`
        # of `home_pos`, and retreats here when there's nothing left to fight.
        # On arrival the soldier "đi vào thành" — it sets is_alive=False so
        # the main loop's cull pass removes it.
        self._home_pos: tuple = (
            (float(x), float(y)) if home_pos is None
            else (float(home_pos[0]), float(home_pos[1]))
        )
        self._home_radius: float = float(home_radius)

        clips = load_clips(
            self.SPRITE_FOLDER, self.SPRITE_FRAMES,
            frame_width=self.FRAME_SIZE, frame_height=self.FRAME_SIZE,
            target_character_height=self.TARGET_HEIGHT_PX,
            headless=headless,
        )
        self._animator = CommanderAnimator(clips, initial_state="idle")

    # --- read-only props -------------------------------------------------

    @property
    def hp(self) -> int:
        return self._hp

    @property
    def max_hp(self) -> int:
        return self._max_hp

    @property
    def is_taunting(self) -> bool:
        """True while a living taunt-soldier is pulling titan aggro."""
        return self.TAUNTS and self.is_alive

    # --- targeting -------------------------------------------------------

    def set_target(self, titan) -> None:
        self._target = titan

    def _acquire_nearest_titan(self) -> None:
        """Acquire the alive titan nearest to ME, restricted to ones inside
        my home zone (`_home_radius` from `_home_pos`). Titans outside the
        zone are ignored — the soldier defends a region, not the whole map."""
        from stubs import WorldQuery
        hx, hy = self._home_pos
        rh2 = self._home_radius * self._home_radius
        best, best_d2 = None, float("inf")
        for e in WorldQuery.all():
            if getattr(e, "ENTITY_TYPE", None) != "titan":
                continue
            if not getattr(e, "is_alive", False):
                continue
            # Inside home zone?
            if (e.x - hx) ** 2 + (e.y - hy) ** 2 > rh2:
                continue
            d2 = (e.x - self.x) ** 2 + (e.y - self.y) ** 2
            if d2 < best_d2:
                best, best_d2 = e, d2
        self._target = best

    def _target_outside_home_zone(self, target) -> bool:
        """True when our current target is alive but has wandered out of zone."""
        hx, hy = self._home_pos
        rh2 = self._home_radius * self._home_radius
        return (target.x - hx) ** 2 + (target.y - hy) ** 2 > rh2

    # --- IMovable (manual move unused by squads; satisfies interface) ----

    def move(self, destination: tuple) -> None:
        # Soldiers steer toward titans, not manual waypoints. A manual move
        # simply re-homes the soldier by clearing its titan target and walking
        # one step toward the destination on the next update is overkill — we
        # just teleport-free seek titans. Keep the hook a no-op-ish setter.
        self._target = None

    # --- IAttackable -----------------------------------------------------

    def take_damage(self, amount: int, dtype: str = "phys") -> None:
        if not self.is_alive:
            return
        dealt = max(1, int(amount) - self.DEFENSE)
        self._hp -= dealt
        if self._hp <= 0:
            self._hp = 0
            self.is_alive = False

    # --- Entity ----------------------------------------------------------

    def update(self, dt: float) -> None:
        if not self.is_alive:
            return
        if self._atk_timer > 0:
            self._atk_timer = max(0.0, self._atk_timer - dt)

        # (Re)acquire a target if ours is gone, dead, or wandered out of zone.
        if (self._target is None
                or not getattr(self._target, "is_alive", False)
                or self._target_outside_home_zone(self._target)):
            self._acquire_nearest_titan()

        target = self._target
        if target is None:
            # Nothing to fight in our zone → walk back to home and vanish.
            self._retreat_into_home(dt)
            if not self.is_alive:
                return                # already "entered the city"
            self._animator.update(dt)
            return

        dx = target.x - self.x
        dy = target.y - self.y
        dist = math.hypot(dx, dy)
        if abs(dx) > 0.5:
            self._animator.set_facing(dx > 0)

        if dist > self.ATTACK_RANGE:
            step = self.SPEED * dt
            if step < dist:
                self.x += (dx / dist) * step
                self.y += (dy / dist) * step
            if self._animator.state != "walk":
                self._animator.set_state("walk")
        else:
            if self._atk_timer <= 0:
                self._do_attack(target)
                self._atk_timer = self.ATTACK_COOLDOWN

        self._animator.update(dt)

    def _retreat_into_home(self, dt: float) -> None:
        """Walk back to the soldier's home slot (`_home_pos + _slot_offset`);
        when it gets there the soldier vanishes — `is_alive = False` so the
        main loop's cull pass removes it from the world. Reads as "đi vào
        thành" visually. Used when there's no titan in our zone to fight."""
        hx = self._home_pos[0] + self._slot_offset[0]
        hy = self._home_pos[1] + self._slot_offset[1]
        dx, dy = hx - self.x, hy - self.y
        d = math.hypot(dx, dy)
        if d > self.HOME_VANISH_DIST_PX:
            if abs(dx) > 0.5:
                self._animator.set_facing(dx > 0)
            step = self.SPEED * dt
            if step < d:
                self.x += (dx / d) * step
                self.y += (dy / d) * step
            else:
                self.x, self.y = hx, hy
            if self._animator.state != "walk":
                self._animator.set_state("walk")
            return
        # Arrived at home — "enter the city" and disappear from the map.
        self.is_alive = False

    def _do_attack(self, target) -> None:
        """Melee: hit the target directly. Ranged subclasses override."""
        self._animator.set_state("attack")
        target.take_damage(self.ATTACK_DAMAGE, "phys")

    # --- draw ------------------------------------------------------------

    def draw(self, screen) -> None:
        frame = self._animator.current_frame()
        sprite_h = self.BODY_RADIUS * 2
        if frame is not None:
            rect = frame.get_rect(midbottom=(int(self.x), int(self.y)))
            screen.blit(frame, rect)
            sprite_h = frame.get_height()
        else:
            pygame.draw.circle(
                screen, self.BODY_COLOR,
                (int(self.x), int(self.y) - self.BODY_RADIUS), self.BODY_RADIUS)

        # Small HP bar above the soldier.
        bar_w = 26
        ratio = self._hp / self._max_hp if self._max_hp else 0.0
        bx = int(self.x) - bar_w // 2
        by = int(self.y) - sprite_h - 6
        try:
            pygame.draw.rect(screen, (120, 20, 20), (bx, by, bar_w, 4))
            pygame.draw.rect(screen, (60, 210, 90),
                             (bx, by, int(bar_w * ratio), 4))
            if self.is_taunting:
                # Faint ring marks the taunt presence.
                pygame.draw.circle(screen, (230, 180, 70),
                                   (int(self.x), int(self.y) - self.BODY_RADIUS),
                                   self.BODY_RADIUS + 6, 1)
        except (AttributeError, pygame.error):
            pass


# ---------------------------------------------------------------------------
# Concrete soldier types
# ---------------------------------------------------------------------------

class ArcherSoldier(Soldier):
    """Ranged, high damage, fragile."""

    NAME = "Archer"
    SPRITE_FOLDER = "../Archer"
    SPRITE_FRAMES = ac.ARCHER_SPRITE_FRAMES
    FRAME_SIZE = ac.FRAME_SIZE_ARCHER
    TARGET_HEIGHT_PX = 40

    BASE_HP = 40
    DEFENSE = 0
    SPEED = 70.0
    ATTACK_DAMAGE = 30
    ATTACK_RANGE = 220.0
    ATTACK_COOLDOWN = 1.0
    IS_RANGED = True
    BODY_COLOR = (90, 200, 120)

    def _do_attack(self, target) -> None:
        """Fire an Arrow projectile toward the target (registered in the world)."""
        from stubs import WorldQuery
        from projectile import Arrow
        self._animator.set_state("attack")
        arrow = Arrow(self.x, self.y - 18, target, self.ATTACK_DAMAGE,
                      headless=self._headless)
        WorldQuery.register(arrow)


class LancerSoldier(Soldier):
    """Fast, medium defense, damage below the archer."""

    NAME = "Lancer"
    SPRITE_FOLDER = "../Lancer"
    SPRITE_FRAMES = ac.LANCER_SPRITE_FRAMES
    FRAME_SIZE = ac.FRAME_SIZE_LANCER
    TARGET_HEIGHT_PX = 44

    BASE_HP = 75
    DEFENSE = 3
    SPEED = 135.0
    ATTACK_DAMAGE = 18
    ATTACK_RANGE = 44.0
    ATTACK_COOLDOWN = 0.6
    BODY_COLOR = (110, 150, 235)


class WarriorSoldier(Soldier):
    """Tanky, slow, low damage — TAUNTS to pull titan aggro."""

    NAME = "Warrior"
    SPRITE_FOLDER = "../Warrior"
    SPRITE_FRAMES = ac.WARRIOR_SOLDIER_SPRITE_FRAMES
    FRAME_SIZE = ac.FRAME_SIZE_WARRIOR_SOLDIER
    TARGET_HEIGHT_PX = 48

    BASE_HP = 170
    DEFENSE = 8
    SPEED = 48.0
    ATTACK_DAMAGE = 10
    ATTACK_RANGE = 38.0
    ATTACK_COOLDOWN = 1.0
    TAUNTS = True
    BODY_COLOR = (210, 140, 80)


# Public registry used by the deploy UI (HUD buttons) and Squad.
SOLDIER_TYPES: dict = {
    "Archer": ArcherSoldier,
    "Lancer": LancerSoldier,
    "Warrior": WarriorSoldier,
}
