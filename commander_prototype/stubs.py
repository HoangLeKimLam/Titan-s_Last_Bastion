"""stubs.py — stand-in modules for systems written by other teammates.

The real WorldQuery, ResourceManager, decorator classes, and Titan classes
live in the main game tree (and are owned by other team members). For the
standalone commander prototype we replicate just enough of each so that
commander.py + eren.py can run end-to-end.

When the real modules ship, swap the imports in commander.py / eren.py and
delete this file.

Contents:
    WorldQuery         — central registry: find_nearest, find_in_radius,
                         replace_entity, register/unregister/clear/all
    ResourceManager    — singleton kho: can_afford, spend (raises
                         InsufficientResourceError), earn
    _EntityDecorator   — base decorator that delegates via __getattr__
    StunnedDecorator   — wrap titan, freeze movement N seconds, unwrap
    SlowedDecorator    — wrap titan, tick wrapped at 50% speed
    FrozenDecorator    — wrap titan, freeze entirely
    DummyTitan         — minimal Entity+IAttackable+IMovable target dummy
"""
from __future__ import annotations

import logging
import math

import pygame

from _core.entity import Entity
from _core.event_bus import GameEventBus
from _core.exceptions import InsufficientResourceError
from _core.game_state import ResourceBundle
from _core.interfaces import IAttackable, IMovable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WorldQuery
# ---------------------------------------------------------------------------

class WorldQuery:
    """Central registry of every live entity in the prototype.

    Also tracks static *structures* (công trình / địa hình) — rectangular
    buildings such as the terrain towers. They are not Entity instances but
    they ARE valid grappling-swing targets: the E-aim ray-casts against them
    (plus titans) to decide whether a swing is allowed.
    """

    _entities: list = []
    _structures: list = []   # list[pygame.Rect] — grapple targets (towers)

    @classmethod
    def register(cls, entity) -> None:
        if entity not in cls._entities:
            cls._entities.append(entity)

    @classmethod
    def unregister(cls, entity) -> None:
        try:
            cls._entities.remove(entity)
        except ValueError:
            pass

    @classmethod
    def register_structure(cls, rect) -> None:
        """Register a static grapple target. `rect` = pygame.Rect or (x,y,w,h)."""
        r = rect if isinstance(rect, pygame.Rect) else pygame.Rect(*rect)
        if r not in cls._structures:
            cls._structures.append(r)

    @classmethod
    def structures(cls) -> list:
        """Return the registered structure rects (công trình / địa hình)."""
        return list(cls._structures)

    @classmethod
    def clear(cls) -> None:
        cls._entities.clear()
        cls._structures.clear()

    @classmethod
    def all(cls) -> list:
        return list(cls._entities)

    @staticmethod
    def _matches(entity, entity_type) -> bool:
        if not getattr(entity, "is_alive", False):
            return False
        if entity_type is None:
            return True
        return getattr(entity, "ENTITY_TYPE", None) == entity_type

    @classmethod
    def find_nearest(cls, cx: float, cy: float, entity_type=None):
        best, best_d2 = None, float("inf")
        for e in cls._entities:
            if not cls._matches(e, entity_type):
                continue
            d2 = (e.x - cx) ** 2 + (e.y - cy) ** 2
            if d2 < best_d2:
                best, best_d2 = e, d2
        return best

    @classmethod
    def find_in_radius(cls, cx: float, cy: float, radius: float,
                       entity_type=None) -> list:
        r2 = radius * radius
        out = []
        for e in cls._entities:
            if not cls._matches(e, entity_type):
                continue
            if (e.x - cx) ** 2 + (e.y - cy) ** 2 <= r2:
                out.append(e)
        return out

    @classmethod
    def replace_entity(cls, old, new) -> None:
        for i, e in enumerate(cls._entities):
            if e is old:
                cls._entities[i] = new
                return
        cls._entities.append(new)


# ---------------------------------------------------------------------------
# ResourceManager
# ---------------------------------------------------------------------------

_RESOURCE_FIELDS = (
    "wood", "stone", "gas", "food",
    "ore", "crystal", "serum", "anti_armor_bolt",
)


class ResourceManager:
    """Singleton kho tài nguyên — only enough surface for prototype."""

    _instance: "ResourceManager" = None

    def __init__(self) -> None:
        self._stock = ResourceBundle(
            wood=200, stone=200, gas=100, food=100,
            ore=50, crystal=20, serum=5, anti_armor_bolt=10,
        )

    @classmethod
    def get_instance(cls) -> "ResourceManager":
        if cls._instance is None:
            cls._instance = ResourceManager()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Wipe the singleton — test helper."""
        cls._instance = None

    @property
    def stock(self) -> ResourceBundle:
        return self._stock

    def can_afford(self, cost: ResourceBundle) -> bool:
        return self._stock >= cost

    def spend(self, cost: ResourceBundle) -> None:
        if not self.can_afford(cost):
            for fname in _RESOURCE_FIELDS:
                req = getattr(cost, fname)
                have = getattr(self._stock, fname)
                if have < req:
                    raise InsufficientResourceError(
                        resource=fname, required=req, available=have,
                    )
        # Subtract field-by-field (ResourceBundle has no __sub__).
        self._stock = ResourceBundle(**{
            fname: getattr(self._stock, fname) - getattr(cost, fname)
            for fname in _RESOURCE_FIELDS
        })

    def earn(self, bundle: ResourceBundle) -> None:
        self._stock = self._stock + bundle


# ---------------------------------------------------------------------------
# Decorators (Stunned / Slowed / Frozen)
# ---------------------------------------------------------------------------

class _EntityDecorator:
    """Wraps an entity, delegates everything not overridden to it.

    The decorator IS the object the world sees while the effect is active.
    When the timer expires, it asks WorldQuery to swap itself back out for
    the original wrapped entity.
    """

    _color = (200, 200, 200)

    def __init__(self, wrapped, duration: float) -> None:
        self._wrapped = wrapped
        self._duration = float(duration)
        self._timer = float(duration)

    # Anything not defined on the decorator → forward to wrapped.
    def __getattr__(self, name):
        # Important: __getattr__ only fires when normal lookup fails,
        # so accessing self._wrapped here is safe (it's in __dict__).
        return getattr(self._wrapped, name)

    def take_damage(self, amount: int, dtype: str):
        return self._wrapped.take_damage(amount, dtype)

    def draw(self, screen) -> None:
        self._wrapped.draw(screen)
        try:
            pygame.draw.circle(
                screen, self._color,
                (int(self._wrapped.x), int(self._wrapped.y) - 40),
                26, 2,
            )
        except (AttributeError, pygame.error):
            pass

    def update(self, dt: float) -> None:
        # Wrapped may die from external damage → unwrap and let main cull it.
        if not getattr(self._wrapped, "is_alive", True):
            WorldQuery.replace_entity(self, self._wrapped)
            return

        self._timer -= dt
        if self._timer <= 0:
            WorldQuery.replace_entity(self, self._wrapped)
            return
        self._tick_wrapped(dt)

    def _tick_wrapped(self, dt: float) -> None:
        """Override to control how wrapped ticks while the effect is on."""
        self._wrapped.update(dt)


class StunnedDecorator(_EntityDecorator):
    """Target cannot act for `duration` seconds."""
    _color = (255, 220, 60)

    def _tick_wrapped(self, dt: float) -> None:
        # Stunned = no movement, no AI tick.
        pass


class SlowedDecorator(_EntityDecorator):
    """Target ticks at 50% speed."""
    _color = (100, 200, 255)

    def _tick_wrapped(self, dt: float) -> None:
        self._wrapped.update(dt * 0.5)


class FrozenDecorator(_EntityDecorator):
    """Target completely frozen (no tick) — visually distinct from stun."""
    _color = (180, 230, 255)

    def _tick_wrapped(self, dt: float) -> None:
        pass


# ---------------------------------------------------------------------------
# DummyTitan — placeholder target for prototype skill tests
# ---------------------------------------------------------------------------

class DummyTitan(Entity, IAttackable, IMovable):
    """Minimal titan: walks toward an optional target, takes damage, dies."""

    ENTITY_TYPE = "titan"
    IS_LARGE: bool = False    # set True by LargeTitan subclass

    # --- Combat vs ally soldiers (titan fights back) --------------------
    AGGRO_RADIUS: float = 360.0   # will chase/attack soldiers within this range
    ATK_DAMAGE: int = 18
    ATK_RANGE: float = 52.0
    ATK_COOLDOWN: float = 1.1

    def __init__(self, x: float, y: float, hp: int = 200):
        super().__init__(x, y)
        self._max_hp = int(hp)
        self._hp = int(hp)
        self._speed = 30.0
        self._target = None           # optional manual destination (pos tuple)
        self._size_scale: float = 1.0
        self._atk_timer: float = 0.0  # attack cooldown countdown

    @property
    def hp(self) -> int:
        return self._hp

    @property
    def max_hp(self) -> int:
        return self._max_hp

    def set_target(self, pos: tuple) -> None:
        self._target = (float(pos[0]), float(pos[1]))

    # --- Entity ----------------------------------------------------------

    def update(self, dt: float) -> None:
        if not self.is_alive:
            return
        if self._atk_timer > 0:
            self._atk_timer = max(0.0, self._atk_timer - dt)

        # Fight ally soldiers first: chase the chosen target and attack it.
        # A taunting Warrior is preferred over a (possibly nearer) other unit.
        soldier = self._pick_soldier_target()
        if soldier is not None:
            dx = soldier.x - self.x
            dy = soldier.y - self.y
            d = math.hypot(dx, dy)
            if d > self.ATK_RANGE:
                if d > 1.0:
                    self.x += (dx / d) * self._speed * dt
                    self.y += (dy / d) * self._speed * dt
            elif self._atk_timer <= 0:
                soldier.take_damage(self.ATK_DAMAGE, "titan")
                self._atk_timer = self.ATK_COOLDOWN
            return

        # No soldiers nearby → fall back to the optional manual destination
        # (keeps the old "walk toward a point" behaviour, and stays inert
        # when there's nothing to do — so commander unit tests are unaffected).
        if self._target is None:
            return
        dx = self._target[0] - self.x
        dy = self._target[1] - self.y
        d = math.hypot(dx, dy)
        if d > 1.0:
            self.x += (dx / d) * self._speed * dt
            self.y += (dy / d) * self._speed * dt

    def _pick_soldier_target(self):
        """Nearest ally soldier in AGGRO_RADIUS, preferring taunting Warriors."""
        ax2 = self.AGGRO_RADIUS * self.AGGRO_RADIUS
        in_range = []
        for e in WorldQuery.all():
            if getattr(e, "ENTITY_TYPE", None) != "soldier":
                continue
            if not getattr(e, "is_alive", False):
                continue
            d2 = (e.x - self.x) ** 2 + (e.y - self.y) ** 2
            if d2 <= ax2:
                in_range.append((d2, e))
        if not in_range:
            return None
        taunters = [(d2, e) for d2, e in in_range
                    if getattr(e, "is_taunting", False)]
        pool = taunters if taunters else in_range
        return min(pool, key=lambda pair: pair[0])[1]

    def draw(self, screen) -> None:
        try:
            radius = int(22 * self._size_scale)
            pygame.draw.circle(screen, (180, 50, 50),
                               (int(self.x), int(self.y)), radius)
            bar_w = int(44 * self._size_scale)
            ratio = self._hp / self._max_hp if self._max_hp else 0.0
            bx = int(self.x) - bar_w // 2
            by = int(self.y) - radius - 14
            pygame.draw.rect(screen, (60, 0, 0), (bx, by, bar_w, 5))
            pygame.draw.rect(screen, (220, 60, 60),
                             (bx, by, int(bar_w * ratio), 5))
        except (AttributeError, pygame.error):
            pass

    # --- IAttackable -----------------------------------------------------

    def take_damage(self, amount: int, dtype: str) -> None:
        if not self.is_alive:
            return
        self._hp -= max(0, int(amount))
        if self._hp <= 0:
            self._hp = 0
            self.is_alive = False
            GameEventBus.get_instance().publish("titan_died", {
                "titan_id": self.id,
                "pos": self.position,
            })

    # --- IMovable --------------------------------------------------------

    def move(self, destination: tuple) -> None:
        self.set_target(destination)


class LargeTitan(DummyTitan):
    """Bigger, tougher titan — hitting one with LMB during a swing flight
    grants the commander a bonus E charge (see Commander.basic_attack)."""

    IS_LARGE = True

    # Hits harder and reaches further than a regular titan.
    AGGRO_RADIUS = 460.0
    ATK_DAMAGE = 34
    ATK_RANGE = 70.0
    ATK_COOLDOWN = 1.3

    def __init__(self, x: float, y: float, hp: int = 600):
        super().__init__(x, y, hp=hp)
        self._size_scale = 1.8
        self._speed = 20.0  # slower than DummyTitan
