"""resource_map.py — mini-map resource-collection model (pure logic, no pygame).

This is the headless-testable core of the "Dispatch System" the codebase already
envisioned (see `_core/interfaces.ILootable`): the player sends abstract teams to
explore locked zones / collect random items, and to mine resources from opened
zones. All gameplay rules live here; `resource_map_screen.py` only renders them.

Concepts
--------
ResourceZone
    A node on the symbolic mini-map. Forests yield wood, caves yield stone.
    1 forest + 1 cave start unlocked; the rest are locked until an expedition
    reaches them. Random "item" nodes appear over time and are collected by an
    expedition (one-shot bundle reward).

DispatchJob
    One in-flight team assignment — either "explore" (unlock a zone / collect an
    item) or "mine" (extract a chosen amount from an opened zone). It is just a
    countdown: `update(dt)` accumulates `elapsed`; at `duration` it completes.

MapState
    Owns all zones, the shared pool of `TEAMS_TOTAL` teams, the upgradable
    "exploration ability" (implements `IUpgradable`), and the random item spawner.
    `update(dt)` ticks jobs (completing + freeing teams) and spawns items.

Time model
----------
    explore_time(zone) = zone.base_explore_time * EXPLORE_LEVEL_FACTOR**(level-1)
    mine_time(amount)  = MINE_BASE_TIME + amount * MINE_TIME_PER_UNIT

Completed mining / item collection credits the shared `ResourceManager` stock via
`earn(...)`, so the meta-layer feeds the same economy the towers/commanders use.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from _core.game_state import ResourceBundle
from _core.interfaces import IUpgradable

# Which ResourceBundle field each zone kind deposits.
ZONE_RESOURCE: dict = {"forest": "wood", "cave": "stone"}
# Resource types a random item node can award.
_ITEM_RESOURCES: tuple = ("gas", "ore", "crystal", "serum")


@dataclass(eq=False)
class ResourceZone:
    """A single node on the mini-map (forest / cave / item).

    `eq=False` keeps identity-based equality/hashing (like the game's Entities)
    so `zone in zones` / `zones.remove(zone)` / `job.zone is zone` all refer to
    the exact object, never another node that happens to share field values.
    """

    kind: str                       # "forest" | "cave" | "item"
    name: str
    gx: int                         # grid column
    gy: int                         # grid row
    unlocked: bool = False
    reserve: int = 0                # remaining extractable units (forest/cave)
    resource_type: str = "wood"     # ResourceBundle field for mining
    base_explore_time: float = 8.0  # seconds before exploration-level scaling
    item_bundle: Optional[ResourceBundle] = None  # reward for collecting an item

    @property
    def is_item(self) -> bool:
        return self.kind == "item"

    @property
    def exhausted(self) -> bool:
        """A mineable zone whose reserve is fully depleted."""
        return self.kind in ZONE_RESOURCE and self.reserve <= 0


class DispatchJob:
    """An in-flight team assignment — a simple countdown timer."""

    def __init__(self, kind: str, zone: ResourceZone, duration: float,
                 amount: int = 0) -> None:
        self.kind = kind            # "explore" | "mine"
        self.zone = zone
        self.duration = float(duration)
        self.amount = int(amount)
        self.elapsed: float = 0.0
        self.done: bool = False

    @property
    def progress(self) -> float:
        """0.0 → 1.0 completion ratio (for the UI progress bar)."""
        if self.duration <= 0:
            return 1.0
        return max(0.0, min(1.0, self.elapsed / self.duration))

    @property
    def remaining(self) -> float:
        return max(0.0, self.duration - self.elapsed)

    def update(self, dt: float) -> None:
        if self.done:
            return
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.done = True


class MapState(IUpgradable):
    """Central controller for the mini-map dispatch/collection gameplay."""

    # --- Tunables -------------------------------------------------------
    TEAMS_TOTAL: int = 3
    GRID_COLS: int = 8
    GRID_ROWS: int = 5
    MAX_EXPLORATION_LEVEL: int = 5
    EXPLORE_LEVEL_FACTOR: float = 0.8        # ~20% faster per level
    MINE_BASE_TIME: float = 2.0
    MINE_TIME_PER_UNIT: float = 0.1
    ITEM_SPAWN_INTERVAL: float = 18.0
    MAX_ITEMS_ON_MAP: int = 3

    # Cost to upgrade FROM the given level to the next.
    EXPLORE_UPGRADE_COSTS: dict = {
        1: ResourceBundle(wood=60, stone=40),
        2: ResourceBundle(wood=100, stone=80),
        3: ResourceBundle(wood=160, stone=120, ore=20),
        4: ResourceBundle(wood=240, stone=180, ore=40, crystal=10),
    }

    def __init__(self, *, rng: Optional[random.Random] = None) -> None:
        self.zones: list = []
        self.jobs: list = []
        self.exploration_level: int = 1
        self._item_timer: float = 0.0
        self._item_counter: int = 0
        self._rng = rng if rng is not None else random.Random()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def seed_default_zones(self) -> None:
        """1 forest + 1 cave unlocked; 2 more forests + 2 more caves locked."""
        self.zones = [
            ResourceZone("forest", "Rung Khoi Dau", 1, 1, unlocked=True,
                         reserve=500, resource_type="wood", base_explore_time=8.0),
            ResourceZone("cave", "Hang Khoi Dau", 6, 1, unlocked=True,
                         reserve=400, resource_type="stone", base_explore_time=8.0),
            ResourceZone("forest", "Rung Sau", 2, 3, unlocked=False,
                         reserve=650, resource_type="wood", base_explore_time=9.0),
            ResourceZone("forest", "Rung Co Thu", 5, 4, unlocked=False,
                         reserve=800, resource_type="wood", base_explore_time=13.0),
            ResourceZone("cave", "Hang Toi", 3, 0, unlocked=False,
                         reserve=520, resource_type="stone", base_explore_time=10.0),
            ResourceZone("cave", "Hang Pha Le", 6, 3, unlocked=False,
                         reserve=900, resource_type="stone", base_explore_time=15.0),
        ]

    # ------------------------------------------------------------------
    # Team pool
    # ------------------------------------------------------------------

    @property
    def teams_busy(self) -> int:
        return len(self.jobs)

    @property
    def teams_free(self) -> int:
        return self.TEAMS_TOTAL - self.teams_busy

    def has_free_team(self) -> bool:
        return self.teams_free > 0

    def job_for(self, zone: ResourceZone) -> Optional[DispatchJob]:
        """Return the active job targeting `zone`, if any (one per zone)."""
        for j in self.jobs:
            if j.zone is zone and not j.done:
                return j
        return None

    # ------------------------------------------------------------------
    # Time formulas
    # ------------------------------------------------------------------

    def explore_time(self, zone: ResourceZone) -> float:
        factor = self.EXPLORE_LEVEL_FACTOR ** (self.exploration_level - 1)
        return zone.base_explore_time * factor

    def mine_time(self, amount: int) -> float:
        return self.MINE_BASE_TIME + max(0, int(amount)) * self.MINE_TIME_PER_UNIT

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def start_explore(self, zone: ResourceZone) -> Optional[DispatchJob]:
        """Send an expedition to a locked zone (to unlock) or an item (to
        collect). Returns the job, or None if rejected (no team / already
        unlocked forest-cave / a job is already running on this zone)."""
        if not self.has_free_team():
            return None
        if zone not in self.zones:
            return None
        if self.job_for(zone) is not None:
            return None
        if not zone.is_item and zone.unlocked:
            return None  # forests/caves only need exploring once
        job = DispatchJob("explore", zone, self.explore_time(zone))
        self.jobs.append(job)
        return job

    def start_mine(self, zone: ResourceZone, amount: int) -> Optional[DispatchJob]:
        """Send a mining team to an opened zone for `amount` units. Returns the
        job, or None if rejected (no team / locked / item / bad amount / a job is
        already running on this zone)."""
        amount = int(amount)
        if not self.has_free_team():
            return None
        if zone not in self.zones or zone.is_item:
            return None
        if not zone.unlocked:
            return None
        if amount <= 0 or amount > zone.reserve:
            return None
        if self.job_for(zone) is not None:
            return None
        job = DispatchJob("mine", zone, self.mine_time(amount), amount=amount)
        self.jobs.append(job)
        return job

    # ------------------------------------------------------------------
    # IUpgradable — "Khả năng thám hiểm"
    # ------------------------------------------------------------------

    def get_upgrade_cost(self) -> ResourceBundle:
        """Cost to raise exploration ability to the next level (empty at max)."""
        return self.EXPLORE_UPGRADE_COSTS.get(self.exploration_level,
                                              ResourceBundle())

    def upgrade(self) -> bool:
        """Spend resources to raise exploration ability one level. Returns False
        (no change) at max level or when the stock can't afford the cost."""
        from _core.exceptions import InsufficientResourceError
        from stubs import ResourceManager

        if self.exploration_level >= self.MAX_EXPLORATION_LEVEL:
            return False
        cost = self.get_upgrade_cost()
        try:
            ResourceManager.get_instance().spend(cost)
        except InsufficientResourceError:
            return False
        self.exploration_level += 1
        return True

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        # Tick jobs; complete + free the team for any that finished.
        still_running: list = []
        for job in self.jobs:
            job.update(dt)
            if job.done:
                self._complete_job(job)
            else:
                still_running.append(job)
        self.jobs = still_running

        # Random item spawner.
        self._item_timer += dt
        if self._item_timer >= self.ITEM_SPAWN_INTERVAL:
            self._item_timer -= self.ITEM_SPAWN_INTERVAL
            if self._count_items() < self.MAX_ITEMS_ON_MAP:
                self._spawn_item()

    def _complete_job(self, job: DispatchJob) -> None:
        from stubs import ResourceManager

        zone = job.zone
        if job.kind == "explore":
            if zone.is_item:
                if zone.item_bundle is not None:
                    ResourceManager.get_instance().earn(zone.item_bundle)
                if zone in self.zones:
                    self.zones.remove(zone)
            else:
                zone.unlocked = True
        elif job.kind == "mine":
            actual = min(job.amount, zone.reserve)
            if actual > 0:
                bundle = ResourceBundle(**{zone.resource_type: actual})
                ResourceManager.get_instance().earn(bundle)
                zone.reserve -= actual

    # ------------------------------------------------------------------
    # Item spawning
    # ------------------------------------------------------------------

    def _count_items(self) -> int:
        return sum(1 for z in self.zones if z.is_item)

    def _occupied_cells(self) -> set:
        return {(z.gx, z.gy) for z in self.zones}

    def _spawn_item(self) -> Optional[ResourceZone]:
        free = [(c, r) for c in range(self.GRID_COLS) for r in range(self.GRID_ROWS)
                if (c, r) not in self._occupied_cells()]
        if not free:
            return None
        gx, gy = self._rng.choice(free)
        rtype = self._rng.choice(_ITEM_RESOURCES)
        amount = self._rng.randint(5, 20)
        self._item_counter += 1
        zone = ResourceZone(
            "item", f"Vat pham {self._item_counter}", gx, gy,
            unlocked=False,
            base_explore_time=float(self._rng.randint(5, 9)),
            item_bundle=ResourceBundle(**{rtype: amount}),
        )
        self.zones.append(zone)
        return zone
