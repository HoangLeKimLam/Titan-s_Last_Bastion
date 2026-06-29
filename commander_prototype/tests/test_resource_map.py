"""Unit tests for the mini-map Dispatch System (headless — pure logic)."""
from __future__ import annotations

import os
import random
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from _core.event_bus import GameEventBus  # noqa: E402
from _core.game_state import ResourceBundle  # noqa: E402
from resource_map import MapState, ResourceZone, ZONE_RESOURCE  # noqa: E402
from stubs import ResourceManager, WorldQuery  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_globals():
    WorldQuery.clear()
    GameEventBus.get_instance().clear()
    ResourceManager.reset()
    yield
    WorldQuery.clear()
    GameEventBus.get_instance().clear()
    ResourceManager.reset()


def _map(seed: int = 0) -> MapState:
    m = MapState(rng=random.Random(seed))
    m.seed_default_zones()
    return m


def _tick(m: MapState, seconds: float, step: float = 1 / 60) -> None:
    n = int(seconds / step)
    for _ in range(n):
        m.update(step)


def _locked_zone(m: MapState, kind: str = "forest") -> ResourceZone:
    return next(z for z in m.zones if z.kind == kind and not z.unlocked)


def _unlocked_zone(m: MapState, kind: str = "forest") -> ResourceZone:
    return next(z for z in m.zones if z.kind == kind and z.unlocked)


# ---------- Setup ----------

@pytest.mark.unit
def test_default_zones():
    m = _map()
    forests_open = [z for z in m.zones if z.kind == "forest" and z.unlocked]
    caves_open = [z for z in m.zones if z.kind == "cave" and z.unlocked]
    assert len(forests_open) == 1
    assert len(caves_open) == 1
    # There are locked zones to explore.
    assert any(not z.unlocked for z in m.zones)
    # Resource types match the kind.
    for z in m.zones:
        if z.kind in ZONE_RESOURCE:
            assert z.resource_type == ZONE_RESOURCE[z.kind]


# ---------- Team pool ----------

@pytest.mark.unit
def test_dispatch_pool_caps_at_three():
    m = _map()
    locked = [z for z in m.zones if not z.unlocked]
    j1 = m.start_explore(locked[0])
    j2 = m.start_explore(locked[1])
    j3 = m.start_explore(locked[2])
    assert all(j is not None for j in (j1, j2, j3))
    assert m.teams_busy == 3
    assert m.teams_free == 0
    # 4th dispatch is rejected — no free team.
    j4 = m.start_explore(locked[3])
    assert j4 is None


@pytest.mark.unit
def test_team_frees_after_completion():
    m = _map()
    locked = _locked_zone(m)
    m.start_explore(locked)
    assert m.teams_busy == 1
    _tick(m, m.explore_time(locked) + 0.1)
    assert m.teams_busy == 0
    assert m.teams_free == MapState.TEAMS_TOTAL


# ---------- Exploration ----------

@pytest.mark.unit
def test_explore_unlocks_locked_zone():
    m = _map()
    locked = _locked_zone(m, "cave")
    assert locked.unlocked is False
    m.start_explore(locked)
    _tick(m, m.explore_time(locked) + 0.1)
    assert locked.unlocked is True


@pytest.mark.unit
def test_explore_time_scales_with_level():
    m = _map()
    locked = _locked_zone(m)
    t1 = m.explore_time(locked)
    m.exploration_level = 2
    t2 = m.explore_time(locked)
    assert t2 < t1
    assert t2 == pytest.approx(t1 * MapState.EXPLORE_LEVEL_FACTOR)


@pytest.mark.unit
def test_start_explore_rejects_unlocked_forest():
    m = _map()
    opened = _unlocked_zone(m, "forest")
    assert m.start_explore(opened) is None


# ---------- Exploration-ability upgrade (IUpgradable) ----------

@pytest.mark.unit
def test_upgrade_cost_lookup_returns_bundle():
    m = _map()
    cost = m.get_upgrade_cost()
    assert isinstance(cost, ResourceBundle)
    assert cost == MapState.EXPLORE_UPGRADE_COSTS[1]


@pytest.mark.unit
def test_exploration_upgrade_spends_and_caps():
    m = _map()
    rm = ResourceManager.get_instance()
    cost = m.get_upgrade_cost()
    wood_before = rm.stock.wood
    assert m.upgrade() is True
    assert m.exploration_level == 2
    assert rm.stock.wood == wood_before - cost.wood

    # Drain the (same singleton's) stock so the next upgrade can't be afforded.
    rm._stock = ResourceBundle()  # empty
    assert m.upgrade() is False
    assert m.exploration_level == 2     # unchanged


@pytest.mark.unit
def test_exploration_upgrade_caps_at_max():
    m = _map()
    # Give plenty of resources.
    rm = ResourceManager.get_instance()
    rm._stock = ResourceBundle(wood=99999, stone=99999, ore=9999, crystal=999)
    for _ in range(10):
        m.upgrade()
    assert m.exploration_level == MapState.MAX_EXPLORATION_LEVEL
    assert m.upgrade() is False


# ---------- Mining ----------

@pytest.mark.unit
def test_mine_time_formula():
    m = _map()
    assert m.mine_time(0) == MapState.MINE_BASE_TIME
    assert m.mine_time(30) == pytest.approx(
        MapState.MINE_BASE_TIME + 30 * MapState.MINE_TIME_PER_UNIT)


@pytest.mark.unit
def test_mining_earns_and_depletes():
    m = _map()
    rm = ResourceManager.get_instance()
    forest = _unlocked_zone(m, "forest")
    wood_before = rm.stock.wood
    reserve_before = forest.reserve
    job = m.start_mine(forest, 30)
    assert job is not None
    _tick(m, m.mine_time(30) + 0.1)
    assert rm.stock.wood == wood_before + 30
    assert forest.reserve == reserve_before - 30


@pytest.mark.unit
def test_mine_rejected_when_locked_or_bad_amount():
    m = _map()
    locked = _locked_zone(m, "cave")
    assert m.start_mine(locked, 10) is None       # locked
    opened = _unlocked_zone(m, "forest")
    assert m.start_mine(opened, 0) is None         # amount <= 0
    assert m.start_mine(opened, opened.reserve + 1) is None  # over reserve


@pytest.mark.unit
def test_mine_clamps_to_remaining_reserve():
    m = _map()
    rm = ResourceManager.get_instance()
    forest = _unlocked_zone(m, "forest")
    forest.reserve = 50
    wood_before = rm.stock.wood
    m.start_mine(forest, 50)
    # Reserve drops mid-job (e.g. simulated external depletion).
    forest.reserve = 20
    _tick(m, m.mine_time(50) + 0.1)
    # Only the remaining 20 is credited; reserve floors at 0.
    assert rm.stock.wood == wood_before + 20
    assert forest.reserve == 0


@pytest.mark.unit
def test_one_job_per_zone():
    m = _map()
    forest = _unlocked_zone(m, "forest")
    assert m.start_mine(forest, 10) is not None
    # A second dispatch to the same zone while one is running is rejected.
    assert m.start_mine(forest, 10) is None


# ---------- Random items ----------

@pytest.mark.unit
def test_item_spawns_over_time():
    m = _map()
    before = sum(1 for z in m.zones if z.is_item)
    _tick(m, MapState.ITEM_SPAWN_INTERVAL + 0.5)
    after = sum(1 for z in m.zones if z.is_item)
    assert after == before + 1
    # Spawning never exceeds the cap.
    _tick(m, MapState.ITEM_SPAWN_INTERVAL * 6)
    assert sum(1 for z in m.zones if z.is_item) <= MapState.MAX_ITEMS_ON_MAP


@pytest.mark.unit
def test_explore_item_collects_and_removes():
    m = _map()
    rm = ResourceManager.get_instance()
    # Force one item to spawn.
    _tick(m, MapState.ITEM_SPAWN_INTERVAL + 0.5)
    item = next(z for z in m.zones if z.is_item)
    bundle = item.item_bundle
    # Identify which resource the item awards.
    field_name, amount = next((k, v) for k, v in bundle.to_dict().items() if v > 0)
    before = getattr(rm.stock, field_name)

    m.start_explore(item)
    _tick(m, m.explore_time(item) + 0.1)
    assert item not in m.zones                         # collected → removed
    assert getattr(rm.stock, field_name) == before + amount
