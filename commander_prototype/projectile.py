"""projectile.py — lightweight projectiles (currently just the Archer's arrow).

An Arrow flies in a straight line toward the position a target had when it was
fired, then deals damage to that target (if still alive & near the impact) and
expires. Kept deliberately simple — no homing, no collision grid — matching the
prototype's straight-line movement model.
"""
from __future__ import annotations

import math
import os

import pygame

from _core.entity import Entity

# Arrow sprite lives in the Archer pack (one 64×64 image).
_ARROW_PATH = os.path.join("..", "Archer", "Arrow.png")


class Arrow(Entity):
    """Straight-line arrow that damages `target` on arrival."""

    ENTITY_TYPE = "projectile"

    SPEED = 520.0          # px/second
    HIT_RADIUS = 26.0      # how close to the impact point counts as a hit
    MAX_LIFETIME = 2.0     # safety despawn

    _sprite_cache = None    # class-level shared sprite (loaded once)

    def __init__(self, x: float, y: float, target, damage: int,
                 *, headless: bool = False) -> None:
        super().__init__(x, y)
        self._target = target
        self._damage = int(damage)
        self._headless = headless
        self._life = self.MAX_LIFETIME
        # Aim at the target's CURRENT position (fire-and-forget).
        tx, ty = target.x, target.y
        dx, dy = tx - x, ty - y
        dist = math.hypot(dx, dy) or 1.0
        self._vx = dx / dist * self.SPEED
        self._vy = dy / dist * self.SPEED
        self._impact = (tx, ty)
        self._sprite = self._load_sprite() if not headless else None

    @classmethod
    def _load_sprite(cls):
        if cls._sprite_cache is not None:
            return cls._sprite_cache
        try:
            img = pygame.image.load(_ARROW_PATH)
            img = pygame.transform.scale(img, (18, 18))
            cls._sprite_cache = img
        except (pygame.error, FileNotFoundError):
            cls._sprite_cache = None
        return cls._sprite_cache

    # --- Entity ----------------------------------------------------------

    def update(self, dt: float) -> None:
        if not self.is_alive:
            return
        self._life -= dt
        self.x += self._vx * dt
        self.y += self._vy * dt

        # Impact when we reach the aimed point or pass close to a live target.
        reached = math.hypot(self._impact[0] - self.x,
                             self._impact[1] - self.y) <= self.HIT_RADIUS
        if reached or self._life <= 0:
            tgt = self._target
            if (tgt is not None and getattr(tgt, "is_alive", False)
                    and math.hypot(tgt.x - self.x, tgt.y - self.y)
                    <= self.HIT_RADIUS * 2):
                tgt.take_damage(self._damage, "ranged")
            self.is_alive = False

    def draw(self, screen) -> None:
        try:
            if self._sprite is not None:
                ang = math.degrees(math.atan2(-self._vy, self._vx))
                rot = pygame.transform.rotate(self._sprite, ang)
                screen.blit(rot, rot.get_rect(center=(int(self.x), int(self.y))))
            else:
                pygame.draw.circle(screen, (240, 230, 160),
                                   (int(self.x), int(self.y)), 3)
        except (AttributeError, pygame.error):
            pass
