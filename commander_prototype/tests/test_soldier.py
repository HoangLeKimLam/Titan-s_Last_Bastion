"""Unit tests for the Soldier system (headless — no display, no sprite I/O)."""
from __future__ import annotations

import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from _core.event_bus import GameEventBus  # noqa: E402
from soldier import (  # noqa: E402
    ArcherSoldier,
    LancerSoldier,
    WarriorSoldier,
    SOLDIER_TYPES,
)
from squad import (  # noqa: E402
    Squad,
    deploy_squad,
    formation_offsets,
    SQUAD_SIZE,
    SQUAD_SPACING,
)
from stubs import DummyTitan, LargeTitan, WorldQuery  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_globals():
    WorldQuery.clear()
    GameEventBus.get_instance().clear()
    yield
    WorldQuery.clear()
    GameEventBus.get_instance().clear()


def _archer(x=100, y=100, target=None):
    return ArcherSoldier(x, y, target=target, headless=True)


def _lancer(x=100, y=100, target=None):
    return LancerSoldier(x, y, target=target, headless=True)


def _warrior(x=100, y=100, target=None):
    return WarriorSoldier(x, y, target=target, headless=True)


# ---------- Stats reflect the three roles ----------

@pytest.mark.unit
def test_role_stats_relative():
    # Archer hits hardest; Warrior tankiest + slowest; Lancer fastest.
    assert ArcherSoldier.ATTACK_DAMAGE > LancerSoldier.ATTACK_DAMAGE
    assert LancerSoldier.ATTACK_DAMAGE > WarriorSoldier.ATTACK_DAMAGE
    assert WarriorSoldier.BASE_HP > LancerSoldier.BASE_HP > ArcherSoldier.BASE_HP
    assert LancerSoldier.SPEED > ArcherSoldier.SPEED > WarriorSoldier.SPEED
    assert WarriorSoldier.DEFENSE > LancerSoldier.DEFENSE >= ArcherSoldier.DEFENSE
    assert ArcherSoldier.IS_RANGED is True
    assert ArcherSoldier.ATTACK_RANGE > LancerSoldier.ATTACK_RANGE


@pytest.mark.unit
def test_archer_is_fragile_warrior_is_tanky():
    assert _warrior().hp > _lancer().hp > _archer().hp


# ---------- take_damage applies defense ----------

@pytest.mark.unit
def test_defense_reduces_damage():
    w = _warrior()                 # DEFENSE 8
    w.take_damage(20, "phys")
    assert w.hp == WarriorSoldier.BASE_HP - (20 - 8)   # 170 - 12

    a = _archer()                  # DEFENSE 0
    a.take_damage(20, "phys")
    assert a.hp == ArcherSoldier.BASE_HP - 20


@pytest.mark.unit
def test_damage_minimum_one_even_through_high_defense():
    w = _warrior()
    w.take_damage(1, "phys")       # 1 - 8 would be negative → clamped to 1
    assert w.hp == WarriorSoldier.BASE_HP - 1


@pytest.mark.unit
def test_soldier_dies_at_zero_hp():
    a = _archer()
    a.take_damage(9999, "phys")
    assert a.hp == 0
    assert a.is_alive is False


# ---------- Movement + melee attack ----------

@pytest.mark.unit
def test_melee_in_range_damages_titan():
    titan = DummyTitan(120, 100, hp=200)
    WorldQuery.register(titan)
    lancer = _lancer(100, 100, target=titan)   # dist 20 < range 44
    lancer.update(0.1)
    assert titan.hp == 200 - LancerSoldier.ATTACK_DAMAGE


@pytest.mark.unit
def test_out_of_range_marches_toward_titan():
    # Titan inside the soldier's default home zone (radius 600) but well
    # beyond the lancer's 44px attack range — soldier should advance.
    titan = DummyTitan(300, 100, hp=200)
    WorldQuery.register(titan)
    lancer = _lancer(100, 100, target=titan)
    lancer.update(0.1)
    assert 100 < lancer.x < 300         # moved toward, not arrived
    assert titan.hp == 200              # too far to hit


# ---------- Archer fires an Arrow projectile ----------

@pytest.mark.unit
def test_archer_fires_arrow_that_damages_titan():
    titan = DummyTitan(200, 100, hp=200)   # dist 100 < archer range 220
    WorldQuery.register(titan)
    archer = _archer(100, 100, target=titan)
    archer.update(0.05)                    # in range → fires one arrow
    arrows = [e for e in WorldQuery.all()
              if getattr(e, "ENTITY_TYPE", None) == "projectile"]
    assert len(arrows) == 1
    # Fly the arrow to impact.
    for _ in range(40):
        arrows[0].update(0.03)
        if not arrows[0].is_alive:
            break
    assert titan.hp == 200 - ArcherSoldier.ATTACK_DAMAGE


# ---------- Warrior taunt pulls titan aggro ----------

@pytest.mark.unit
def test_warrior_is_taunting_flag():
    w = _warrior()
    assert w.is_taunting is True
    assert _lancer().is_taunting is False


@pytest.mark.unit
def test_titan_prefers_taunting_warrior_over_nearer_soldier():
    titan = DummyTitan(100, 100, hp=300)
    lancer = _lancer(110, 100, target=titan)   # very close, NOT taunting
    warrior = _warrior(260, 100, target=titan)  # farther, taunting
    WorldQuery.register(lancer)
    WorldQuery.register(warrior)
    picked = titan._pick_soldier_target()
    assert picked is warrior


# ---------- Titan fights back ----------

@pytest.mark.unit
def test_titan_attacks_nearby_soldier():
    titan = DummyTitan(100, 100, hp=300)        # ATK_DAMAGE 18, range 52
    lancer = _lancer(130, 100, target=titan)    # dist 30 < 52
    WorldQuery.register(titan)
    WorldQuery.register(lancer)
    titan.update(0.1)
    # Lancer DEFENSE 3 → takes 18 - 3 = 15.
    assert lancer.hp == LancerSoldier.BASE_HP - (DummyTitan.ATK_DAMAGE - 3)


@pytest.mark.unit
def test_titan_inert_without_soldiers():
    titan = DummyTitan(100, 100, hp=200)
    WorldQuery.register(titan)
    titan.update(0.5)
    assert (titan.x, titan.y) == (100, 100)     # no soldiers → stays put


# ---------- Squad ----------

@pytest.mark.unit
def test_squad_spawns_ten_spread_cluster():
    titan = DummyTitan(900, 500, hp=200)
    WorldQuery.register(titan)
    squad = deploy_squad("Warrior", (500, 500), titan, WorldQuery, headless=True)
    assert len(squad.members) == SQUAD_SIZE == 10
    pts = [(s.x, s.y) for s in squad.members]
    for s in squad.members:
        assert s._target is titan
    # No two soldiers stacked on top of each other.
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
            assert d > SQUAD_SPACING * 0.5      # clearly separated
    # The cluster genuinely spreads out (not all on a thin ring at the centre).
    max_r = max(math.hypot(x - 500, y - 500) for x, y in pts)
    assert max_r >= SQUAD_SPACING               # at least one outer ring
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert len(soldiers) == 10


@pytest.mark.unit
def test_formation_offsets_filled_cluster():
    offs = formation_offsets(10)
    assert len(offs) == 10
    assert offs[0] == (0.0, 0.0)               # a centre soldier
    # Distinct positions (no duplicate slots).
    assert len({(round(x, 1), round(y, 1)) for x, y in offs}) == 10


@pytest.mark.unit
def test_soldier_retargets_nearest_titan_when_target_dies():
    titan_a = DummyTitan(140, 100, hp=200)
    titan_b = DummyTitan(400, 100, hp=200)
    WorldQuery.register(titan_a)
    WorldQuery.register(titan_b)
    lancer = _lancer(100, 100, target=titan_a)
    titan_a.is_alive = False          # the original target dies
    lancer.update(0.05)               # should re-acquire the nearest alive titan
    assert lancer._target is titan_b


@pytest.mark.unit
def test_squad_regroups_and_spreads_when_no_titans():
    # No titans in the world → soldiers should fan back into formation.
    squad = deploy_squad("Lancer", (300, 300), None, WorldQuery, headless=True)
    # Simulate post-combat clumping: stack every member on one spot.
    for s in squad.members:
        s.x, s.y = 300.0, 300.0
    for _ in range(240):                # ~4s
        for s in squad.members:
            s.update(1 / 60)
    pts = [(s.x, s.y) for s in squad.members]
    mind = min(
        math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
        for i in range(len(pts)) for j in range(i + 1, len(pts))
    )
    assert mind > 20.0                  # no longer stacked — spread out


@pytest.mark.unit
def test_squad_does_not_regroup_while_a_titan_lives():
    titan = DummyTitan(600, 300, hp=9999)
    WorldQuery.register(titan)
    squad = deploy_squad("Lancer", (300, 300), titan, WorldQuery, headless=True)
    m = squad.members[0]
    m.x, m.y = 300.0, 300.0
    m.update(1 / 60)
    # With a live titan it advances toward the enemy, not back to formation.
    assert m.x > 300.0


@pytest.mark.unit
def test_soldier_types_registry():
    assert SOLDIER_TYPES == {
        "Archer": ArcherSoldier,
        "Lancer": LancerSoldier,
        "Warrior": WarriorSoldier,
    }
    assert isinstance(Squad("Archer", (0, 0), None, headless=True).members[0],
                      ArcherSoldier)


# ---------- Home zone (Sprint 20) ----------

@pytest.mark.unit
def test_soldier_ignores_titans_outside_home_zone():
    # Soldier home anchored at (500, 500) with a tight 200px radius.
    # Titan at (900, 500) is 400px away — outside zone → must NOT be acquired.
    titan = DummyTitan(900, 500, hp=200)
    WorldQuery.register(titan)
    lancer = LancerSoldier(500, 500, target=None, headless=True,
                           home_pos=(500, 500), home_radius=200.0)
    lancer.update(0.05)
    assert lancer._target is None


@pytest.mark.unit
def test_soldier_drops_target_that_wanders_out_of_zone():
    titan = DummyTitan(560, 500, hp=200)
    WorldQuery.register(titan)
    lancer = LancerSoldier(500, 500, target=titan, headless=True,
                           home_pos=(500, 500), home_radius=200.0)
    # Confirm titan is in zone now → soldier engages.
    lancer.update(0.05)
    assert lancer._target is titan
    # Titan leaves the zone → soldier should drop it on the next tick.
    titan.x = 900.0
    lancer.update(0.05)
    assert lancer._target is None


@pytest.mark.unit
def test_soldier_walks_toward_home_when_no_titans():
    lancer = LancerSoldier(620, 500, target=None, headless=True,
                           home_pos=(500, 500), home_radius=400.0)
    # No titans in WorldQuery → must walk toward home on the first ticks
    # (not yet inside the vanish radius).
    start_x = lancer.x
    lancer.update(1 / 60)
    lancer.update(1 / 60)
    assert lancer.x < start_x
    assert lancer.is_alive is True       # still on the way back


@pytest.mark.unit
def test_soldier_vanishes_on_arrival_at_home():
    # No titans → walk home, then "đi vào thành" (is_alive=False on arrival).
    lancer = LancerSoldier(620, 500, target=None, headless=True,
                           home_pos=(500, 500), home_radius=400.0)
    for _ in range(int(3.0 * 60)):       # 3s — plenty for 120 px at 135 px/s
        lancer.update(1 / 60)
        if not lancer.is_alive:
            break
    assert lancer.is_alive is False      # entered the city
    # Final position: at the home anchor (slot offset (0,0) by default).
    assert math.hypot(lancer.x - 500, lancer.y - 500) <= LancerSoldier.HOME_VANISH_DIST_PX


@pytest.mark.unit
def test_soldier_does_not_vanish_while_still_walking_home():
    # Far from home → after one tick the soldier is still en route, alive.
    lancer = LancerSoldier(900, 500, target=None, headless=True,
                           home_pos=(500, 500), home_radius=600.0)
    lancer.update(0.02)
    assert lancer.is_alive is True
    assert math.hypot(lancer.x - 500, lancer.y - 500) > LancerSoldier.HOME_VANISH_DIST_PX


@pytest.mark.unit
def test_soldier_vanishes_only_when_no_titan_in_zone():
    # If a titan is present in the zone, the soldier must engage, NOT vanish,
    # even when it happens to be standing on its home slot.
    titan = DummyTitan(560, 500, hp=200)
    WorldQuery.register(titan)
    lancer = LancerSoldier(500, 500, target=None, headless=True,
                           home_pos=(500, 500), home_radius=400.0)
    lancer.update(1 / 60)
    assert lancer.is_alive is True
    assert lancer._target is titan


# ---------- Squad propagates home to members ----------

@pytest.mark.unit
def test_deploy_squad_propagates_home_to_members():
    squad = deploy_squad("Lancer", (500, 500), None, WorldQuery,
                        headless=True, home_pos=(500, 500), home_radius=300.0)
    assert squad.home_pos == (500.0, 500.0)
    assert squad.home_radius == 300.0
    for m in squad.members:
        assert m._home_pos == (500.0, 500.0)
        assert m._home_radius == 300.0
