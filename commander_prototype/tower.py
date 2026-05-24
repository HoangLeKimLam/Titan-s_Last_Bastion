"""tower.py — defensive Tower entity that auto-deploys squads at nearby titans.

A `Tower` is an ally `Entity` that stands at a fixed world position and holds
up to `CAPACITY` squads (defaults split across Warrior/Lancer/Archer). When at
least one titan enters its `AGGRO_RADIUS`, the tower starts an *event*: it
spawns one squad per wave on `WAVE_COOLDOWN` ticks, picking the soldier type
from `wave_order[wave_index]` (with `len(wave_order) == MAX_WAVES_PER_EVENT`).
After 3 successful waves — or when the garrison runs dry / no titan remains in
range — the tower enters `EVENT_COOLDOWN` before another event can begin.

The player customises the tower via `TowerMenu`:
    - per-type garrison counts (total ≤ CAPACITY = 8)
    - the soldier type to deploy in each of the 3 waves

The tower itself is intentionally thin — it owns timer/state machine and
delegates the actual cluster spawning to `squad.deploy_squad`.
"""
from __future__ import annotations

import math

import pygame

from _core.entity import Entity
from soldier import SOLDIER_TYPES
from squad import deploy_squad


class Tower(Entity):
    """Ally defensive tower — see module docstring for behaviour."""

    ENTITY_TYPE: str = "tower"
    FACTION: str = "ally"
    NAME: str = "Tower"

    # --- Tunables (shared across instances) -----------------------------
    CAPACITY: int = 8                     # max total squads stored
    AGGRO_RADIUS: float = 600.0           # px — titan inside → start event
    WAVE_COOLDOWN: float = 3.0            # s between waves in an event
    EVENT_COOLDOWN: float = 8.0           # s rest after a finished event
    MAX_WAVES_PER_EVENT: int = 3

    # Rendering footprint (world space).
    BODY_W: int = 56
    BODY_H: int = 80
    ROOF_H: int = 26

    # Defaults — total = CAPACITY (8). User can rebalance via TowerMenu.
    DEFAULT_GARRISON: dict = {"Warrior": 4, "Lancer": 2, "Archer": 2}
    DEFAULT_WAVE_ORDER: tuple = ("Warrior", "Lancer", "Archer")

    def __init__(self, x: float, y: float, *,
                 garrison: dict | None = None,
                 wave_order: list | tuple | None = None,
                 headless: bool = False) -> None:
        super().__init__(x, y)
        self._headless = headless
        # Garrison: copy defaults; validate types against SOLDIER_TYPES.
        self.garrison: dict = {t: 0 for t in SOLDIER_TYPES}
        seed = self.DEFAULT_GARRISON if garrison is None else garrison
        for t, n in seed.items():
            if t in SOLDIER_TYPES and int(n) >= 0:
                self.garrison[t] = int(n)
        # Trim if caller seeded over capacity — keep behaviour predictable.
        self._trim_to_capacity()

        # Wave order: 3 soldier-type slots — pad/truncate to length 3.
        seed_order = (list(wave_order) if wave_order is not None
                      else list(self.DEFAULT_WAVE_ORDER))
        for t in seed_order:
            if t not in SOLDIER_TYPES:
                raise ValueError(f"Unknown soldier type in wave_order: {t!r}")
        if len(seed_order) < self.MAX_WAVES_PER_EVENT:
            # pad with the default order so we always have 3 slots.
            for t in self.DEFAULT_WAVE_ORDER:
                if len(seed_order) >= self.MAX_WAVES_PER_EVENT:
                    break
                seed_order.append(t)
        self.wave_order: list = seed_order[:self.MAX_WAVES_PER_EVENT]

        # State machine.
        self._state: str = "idle"           # idle | active | cooldown
        self._wave_timer: float = 0.0       # s until next wave deploys
        self._event_cd: float = 0.0         # s until cooldown ends
        self._wave_index: int = 0           # index into wave_order
        self._waves_done: int = 0           # waves deployed in current event
        self._active_squad = None           # Squad just deployed (wipe-detect)
        self._highlight_aggro: bool = False # draw dashed aggro ring (UI toggle)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    def bounds(self) -> pygame.Rect:
        """World-space rectangle covering the tower body + roof (click hit-test)."""
        w, h = self.BODY_W, self.BODY_H + self.ROOF_H
        return pygame.Rect(int(self.x - w / 2),
                           int(self.y - h),
                           w, h)

    def total_garrison(self) -> int:
        return sum(self.garrison.values())

    def set_garrison(self, soldier_type: str, count: int) -> bool:
        """Set the per-type squad count. Returns False (no-op) if the new total
        would exceed CAPACITY. Lowering counts is always allowed."""
        if soldier_type not in SOLDIER_TYPES:
            raise ValueError(f"Unknown soldier type: {soldier_type!r}")
        count = max(0, int(count))
        others = self.total_garrison() - self.garrison[soldier_type]
        if others + count > self.CAPACITY:
            return False
        self.garrison[soldier_type] = count
        return True

    def adjust_garrison(self, soldier_type: str, delta: int) -> bool:
        """Convenience for the +/- menu buttons."""
        return self.set_garrison(soldier_type,
                                 self.garrison.get(soldier_type, 0) + delta)

    def set_wave_slot(self, index: int, soldier_type: str) -> None:
        if not 0 <= index < self.MAX_WAVES_PER_EVENT:
            raise IndexError(f"wave slot out of range: {index}")
        if soldier_type not in SOLDIER_TYPES:
            raise ValueError(f"Unknown soldier type: {soldier_type!r}")
        self.wave_order[index] = soldier_type

    def cycle_wave_slot(self, index: int) -> str:
        """Cycle a wave slot through SOLDIER_TYPES (used by menu click).

        Returns the new type at that slot.
        """
        order = list(SOLDIER_TYPES.keys())
        cur = self.wave_order[index]
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else order[0]
        self.set_wave_slot(index, nxt)
        return nxt

    # ------------------------------------------------------------------
    # Entity hooks
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        if not self.is_alive:
            return

        if self._state == "cooldown":
            self._event_cd = max(0.0, self._event_cd - dt)
            if self._event_cd <= 0.0:
                self._state = "idle"
            return

        if self._state == "idle":
            if self.total_garrison() <= 0:
                return
            titan = self._find_titan_in_aggro()
            if titan is None:
                return
            # Begin event — fire the first wave immediately.
            self._state = "active"
            self._wave_index = 0
            self._waves_done = 0
            self._wave_timer = 0.0
            # Fall through into the active branch this same tick.

        if self._state == "active":
            # Wipe-triggers-next-wave: if our last squad is dead and the cap
            # hasn't been hit, fire the next wave immediately instead of
            # waiting for the remaining wave cooldown. The cap (3 waves/event)
            # is unchanged; only the timer is shortcut.
            if (self._active_squad is not None
                    and not self._active_squad.is_alive
                    and self._waves_done < self.MAX_WAVES_PER_EVENT):
                self._wave_timer = 0.0

            self._wave_timer = max(0.0, self._wave_timer - dt)
            if self._wave_timer > 0.0:
                return
            titan = self._find_titan_in_aggro()
            if titan is None:
                self._end_event()
                return
            spawned = self._spawn_next_wave(titan)
            if not spawned:
                # Garrison empty across all slots → cut the event short.
                self._end_event()
                return
            self._waves_done += 1
            self._wave_index = (self._wave_index + 1) % self.MAX_WAVES_PER_EVENT
            if (self._waves_done >= self.MAX_WAVES_PER_EVENT
                    or self.total_garrison() <= 0):
                self._end_event()
            else:
                self._wave_timer = self.WAVE_COOLDOWN

    def draw(self, screen) -> None:
        body = pygame.Rect(int(self.x - self.BODY_W / 2),
                           int(self.y - self.BODY_H),
                           self.BODY_W, self.BODY_H)
        try:
            pygame.draw.rect(screen, (110, 110, 130), body)
            pygame.draw.rect(screen, (60, 60, 80), body, 2)
            # Roof: triangle on top of body.
            roof = [
                (body.left - 6, body.top),
                (body.right + 6, body.top),
                (body.centerx, body.top - self.ROOF_H),
            ]
            pygame.draw.polygon(screen, (140, 50, 60), roof)
            pygame.draw.polygon(screen, (70, 22, 28), roof, 2)
            # Door slit.
            door = pygame.Rect(body.centerx - 7, body.bottom - 22, 14, 22)
            pygame.draw.rect(screen, (40, 30, 28), door)
            # Garrison count badge.
            font = pygame.font.SysFont("consolas", 14, bold=True)
            txt = font.render(f"{self.total_garrison()}/{self.CAPACITY}",
                              True, (235, 235, 235))
            screen.blit(txt, txt.get_rect(midbottom=(body.centerx, body.top - self.ROOF_H - 4)))
            # Active ring when deploying.
            if self._state == "active":
                pygame.draw.circle(screen, (250, 210, 90),
                                   (int(self.x), int(self.y) - 6),
                                   self.BODY_W // 2 + 8, 2)
            # Aggro radius preview when hover/menu open.
            if self._highlight_aggro:
                self._draw_dashed_circle(screen, (int(self.x), int(self.y)),
                                         int(self.AGGRO_RADIUS),
                                         (250, 220, 90), segments=64)
        except (AttributeError, pygame.error):
            pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _trim_to_capacity(self) -> None:
        """Reduce per-type counts (round-robin from end) until total ≤ CAPACITY."""
        keys = list(self.garrison.keys())
        i = len(keys) - 1
        while self.total_garrison() > self.CAPACITY and i >= 0:
            k = keys[i]
            if self.garrison[k] > 0:
                self.garrison[k] -= 1
            else:
                i -= 1
        # Sanity floor.
        for k in keys:
            if self.garrison[k] < 0:
                self.garrison[k] = 0

    def _find_titan_in_aggro(self):
        """Return the nearest alive titan within AGGRO_RADIUS, else None."""
        from stubs import WorldQuery  # local import to avoid cycle at import time
        nearest = WorldQuery.find_nearest(self.x, self.y, entity_type="titan")
        if nearest is None:
            return None
        d2 = (nearest.x - self.x) ** 2 + (nearest.y - self.y) ** 2
        if d2 > self.AGGRO_RADIUS * self.AGGRO_RADIUS:
            return None
        return nearest

    def _pick_wave_type(self) -> str | None:
        """Pick the soldier type for the current wave, walking past empty slots.

        Returns the type whose garrison count is > 0, advancing `_wave_index`
        as needed. Returns None when all slots are empty.
        """
        for step in range(self.MAX_WAVES_PER_EVENT):
            idx = (self._wave_index + step) % self.MAX_WAVES_PER_EVENT
            t = self.wave_order[idx]
            if self.garrison.get(t, 0) > 0:
                self._wave_index = idx
                return t
        return None

    def _spawn_next_wave(self, titan) -> bool:
        from stubs import WorldQuery
        t = self._pick_wave_type()
        if t is None:
            return False
        # Spawn just below the tower so the cluster fans out in front of it.
        # Bind the squad's home to this tower so members only chase titans
        # inside AGGRO_RADIUS and retreat here to heal when idle.
        base_pos = (self.x, self.y + 16)
        squad = deploy_squad(
            t, base_pos, titan, WorldQuery, headless=self._headless,
            home_pos=(self.x, self.y), home_radius=self.AGGRO_RADIUS,
        )
        self._active_squad = squad
        self.garrison[t] -= 1
        return True

    def _end_event(self) -> None:
        self._state = "cooldown"
        self._event_cd = self.EVENT_COOLDOWN
        self._waves_done = 0
        self._wave_index = 0
        self._wave_timer = 0.0
        # Drop the wipe-detect handle so the next event starts clean.
        self._active_squad = None

    @staticmethod
    def _draw_dashed_circle(screen, center: tuple, radius: int,
                            color: tuple, segments: int = 48) -> None:
        """Approximate dashed circle by skipping every other arc segment."""
        cx, cy = center
        for i in range(segments):
            if i % 2:
                continue
            a0 = (2 * math.pi * i) / segments
            a1 = (2 * math.pi * (i + 1)) / segments
            p0 = (int(cx + math.cos(a0) * radius), int(cy + math.sin(a0) * radius))
            p1 = (int(cx + math.cos(a1) * radius), int(cy + math.sin(a1) * radius))
            try:
                pygame.draw.line(screen, color, p0, p1, 1)
            except (AttributeError, pygame.error):
                return
