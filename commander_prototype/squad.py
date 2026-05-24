"""squad.py — deploy a cluster (~10) of one soldier type from a spawn anchor.

A Squad spawns SQUAD_SIZE soldiers of a single type arranged in a filled hex
cluster around the spawn position (the "thành" — a Tower in the current game,
the only valid spawn anchor), assigns them an initial titan target, and
registers each in WorldQuery so the main loop updates/draws them.

Each member of the squad is bound to the same *home* — the spawn anchor and
its home_radius — so it will:
    1. Only engage titans inside `home_radius` of `home_pos`.
    2. Retreat to its slot in the spread cluster when there's nothing to fight.
    3. Heal at home (handled by Soldier itself).

The Squad object stays thin: it carries the spawn metadata + member list,
exposes `is_alive` for the Tower's wipe-detection, and stops there.
"""
from __future__ import annotations

import math

from soldier import SOLDIER_TYPES

SQUAD_SIZE: int = 10
# Gap between neighbouring soldiers in the spawn cluster. Big enough that the
# ~48px sprites don't overlap, so the cluster reads clearly.
SQUAD_SPACING: float = 52.0


def formation_offsets(n: int, spacing: float = SQUAD_SPACING) -> list:
    """Return n (dx, dy) offsets packed as a FILLED cluster of concentric hex
    rings (1 centre + 6 + 12 + …). Neighbours sit ~`spacing` apart so sprites
    spread out instead of stacking on a single thin circle."""
    offsets = [(0.0, 0.0)]
    ring = 1
    while len(offsets) < n:
        radius = ring * spacing
        slots = max(1, int(round(2 * math.pi * ring)))  # ≈ 6, 12, 18 …
        phase = ring * 0.5                              # stagger rings a bit
        for i in range(slots):
            if len(offsets) >= n:
                break
            ang = (2 * math.pi * i) / slots + phase
            offsets.append((math.cos(ang) * radius, math.sin(ang) * radius))
        ring += 1
    return offsets[:n]


class Squad:
    """A deployed cluster of same-type soldiers bound to one spawn anchor."""

    def __init__(self, soldier_type: str, base_pos: tuple, target=None,
                 *, size: int = SQUAD_SIZE, headless: bool = False,
                 home_pos: tuple | None = None,
                 home_radius: float = 600.0) -> None:
        if soldier_type not in SOLDIER_TYPES:
            raise ValueError(f"Unknown soldier type: {soldier_type!r}")
        self.soldier_type = soldier_type
        cls = SOLDIER_TYPES[soldier_type]
        bx, by = base_pos
        # Default the home anchor to the spawn point itself so call sites that
        # don't pass a home still get sensible patrol/retreat behaviour.
        home = base_pos if home_pos is None else home_pos
        self.home_pos: tuple = (float(home[0]), float(home[1]))
        self.home_radius: float = float(home_radius)
        self.members: list = []

        for dx, dy in formation_offsets(size):
            soldier = cls(
                bx + dx, by + dy, target=target, headless=headless,
                home_pos=self.home_pos, home_radius=self.home_radius,
            )
            # Each soldier remembers its slot so it can fan back to the
            # cluster shape when retreating to home.
            soldier._squad = self
            soldier._slot_offset = (dx, dy)
            self.members.append(soldier)

    def register_all(self, world) -> None:
        """Register every member with the given WorldQuery-like registry."""
        for s in self.members:
            world.register(s)

    @property
    def alive_members(self) -> list:
        return [s for s in self.members if s.is_alive]

    @property
    def is_alive(self) -> bool:
        """True while ≥1 member is alive. Tower uses this for wipe-detection."""
        return any(s.is_alive for s in self.members)


def deploy_squad(soldier_type: str, base_pos: tuple, target, world,
                 *, size: int = SQUAD_SIZE, headless: bool = False,
                 home_pos: tuple | None = None,
                 home_radius: float = 600.0) -> Squad:
    """Create a Squad and register all its members in `world`. Returns the Squad.

    `home_pos` / `home_radius` define the soldiers' patrol zone — they will
    only chase titans inside it and retreat to that anchor when idle. Tower
    callers pass its world position + AGGRO_RADIUS; tests that don't care
    leave the defaults (home = spawn, radius = 600).
    """
    squad = Squad(soldier_type, base_pos, target, size=size, headless=headless,
                  home_pos=home_pos, home_radius=home_radius)
    squad.register_all(world)
    return squad
