"""Unit tests for Tower (headless — pygame.display never opened)."""
from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from _core.event_bus import GameEventBus  # noqa: E402
from soldier import SOLDIER_TYPES  # noqa: E402
from squad import SQUAD_SIZE  # noqa: E402
from stubs import DummyTitan, WorldQuery  # noqa: E402
from tower import Tower  # noqa: E402
from tower_menu import TowerMenu  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_globals():
    WorldQuery.clear()
    GameEventBus.get_instance().clear()
    yield
    WorldQuery.clear()
    GameEventBus.get_instance().clear()


def _tower(x=500, y=500, **kwargs):
    return Tower(x, y, headless=True, **kwargs)


# ---------- Construction & basic API ----------

@pytest.mark.unit
def test_tower_defaults():
    t = _tower()
    assert Tower.CAPACITY == 8
    assert t.total_garrison() == 8
    assert len(t.wave_order) == Tower.MAX_WAVES_PER_EVENT == 3
    assert t.state == "idle"
    assert t.ENTITY_TYPE == "tower"
    # All slots must be valid soldier types.
    for slot in t.wave_order:
        assert slot in SOLDIER_TYPES


@pytest.mark.unit
def test_set_garrison_respects_capacity():
    t = _tower()
    # Already 8/8 — raising any single type would push past cap → rejected.
    assert t.set_garrison("Warrior", 6) is False
    assert t.garrison["Warrior"] == 4   # unchanged
    # Lowering is always fine.
    assert t.set_garrison("Warrior", 1) is True
    assert t.garrison["Warrior"] == 1
    # Now we have headroom (1+2+2=5); raise Warrior back up to fill cap.
    assert t.set_garrison("Warrior", 4) is True
    assert t.total_garrison() == 8
    # Negative requests clamp to 0, not exception (frees slots, never adds).
    assert t.set_garrison("Lancer", -3) is True
    assert t.garrison["Lancer"] == 0


@pytest.mark.unit
def test_set_wave_slot_rejects_unknown_type():
    t = _tower()
    with pytest.raises(ValueError):
        t.set_wave_slot(0, "Wizard")
    with pytest.raises(IndexError):
        t.set_wave_slot(5, "Warrior")


@pytest.mark.unit
def test_cycle_wave_slot_rotates_through_types():
    t = _tower()
    t.set_wave_slot(0, "Warrior")
    first = t.cycle_wave_slot(0)
    second = t.cycle_wave_slot(0)
    third = t.cycle_wave_slot(0)
    # After 3 cycles we land back on "Warrior".
    assert third == "Warrior"
    assert first != second and second != third


# ---------- Idle behaviour ----------

@pytest.mark.unit
def test_tower_idle_without_titans():
    t = _tower()
    WorldQuery.register(t)
    for _ in range(60):                  # 1 second of ticks
        t.update(1 / 60)
    assert t.state == "idle"
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert soldiers == []


@pytest.mark.unit
def test_tower_idle_when_titan_out_of_aggro():
    t = _tower(x=500, y=500)
    titan = DummyTitan(500 + Tower.AGGRO_RADIUS + 50, 500, hp=200)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    for _ in range(60):
        t.update(1 / 60)
    assert t.state == "idle"


# ---------- Deployment ----------

@pytest.mark.unit
def test_tower_deploys_first_wave_when_titan_in_aggro():
    t = _tower(x=500, y=500)
    titan = DummyTitan(700, 500, hp=200)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    t.update(0.0)
    # One full cluster (10 soldiers) of the first wave's type.
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert len(soldiers) == SQUAD_SIZE == 10
    expected_type = SOLDIER_TYPES[t.wave_order[0]].__name__
    assert all(s.__class__.__name__ == expected_type for s in soldiers)
    # All target the triggering titan.
    assert all(getattr(s, "_target", None) is titan for s in soldiers)
    # Garrison decremented for that type, total dropped by 1.
    assert t.total_garrison() == 7
    assert t.state == "active"


@pytest.mark.unit
def test_tower_caps_at_three_waves_per_event():
    t = _tower(x=500, y=500,
               garrison={"Warrior": 8, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Warrior", "Warrior"])
    titan = DummyTitan(700, 500, hp=99999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    # Run plenty of time for waves to space out (> 3 × WAVE_COOLDOWN).
    for _ in range(int((3 * Tower.WAVE_COOLDOWN + 1.0) / (1 / 60))):
        t.update(1 / 60)
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert len(soldiers) == 3 * SQUAD_SIZE
    assert t.state == "cooldown"


@pytest.mark.unit
def test_tower_wave_order_followed():
    t = _tower(x=500, y=500,
               garrison={"Warrior": 1, "Lancer": 1, "Archer": 1},
               wave_order=["Archer", "Warrior", "Lancer"])
    titan = DummyTitan(700, 500, hp=99999)
    WorldQuery.register(t)
    WorldQuery.register(titan)

    seen_types: list = []
    captured_ids: set = set()
    steps = int((3 * Tower.WAVE_COOLDOWN + 1.0) / (1 / 60))
    for _ in range(steps):
        t.update(1 / 60)
        for e in WorldQuery.all():
            if getattr(e, "ENTITY_TYPE", None) != "soldier":
                continue
            if e.id in captured_ids:
                continue
            captured_ids.add(e.id)
            seen_types.append(e.__class__.__name__)

    # 30 soldiers, 10 of each — Archer first 10, Warrior next 10, Lancer last 10.
    cls = {t_name: SOLDIER_TYPES[t_name].__name__
           for t_name in ("Archer", "Warrior", "Lancer")}
    first10 = seen_types[:10]
    next10 = seen_types[10:20]
    last10 = seen_types[20:30]
    assert all(n == cls["Archer"] for n in first10)
    assert all(n == cls["Warrior"] for n in next10)
    assert all(n == cls["Lancer"] for n in last10)


@pytest.mark.unit
def test_tower_skips_empty_type():
    # Archer is requested first but its garrison is 0 → wave 0 should deploy
    # the next non-empty type in the wave_order (Lancer).
    t = _tower(x=500, y=500,
               garrison={"Warrior": 1, "Lancer": 1, "Archer": 0},
               wave_order=["Archer", "Lancer", "Warrior"])
    titan = DummyTitan(700, 500, hp=99999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    t.update(0.0)
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert len(soldiers) == 10
    expected_cls = SOLDIER_TYPES["Lancer"].__name__
    assert all(s.__class__.__name__ == expected_cls for s in soldiers)


@pytest.mark.unit
def test_tower_stops_when_garrison_empty():
    t = _tower(x=500, y=500,
               garrison={"Warrior": 1, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Warrior", "Warrior"])
    titan = DummyTitan(700, 500, hp=99999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    steps = int((3 * Tower.WAVE_COOLDOWN + 1.0) / (1 / 60))
    for _ in range(steps):
        t.update(1 / 60)
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert len(soldiers) == 10   # only the single available squad
    # After spawning that last cluster the tower enters cooldown; once the
    # 8s reset elapses it returns to idle and stays there (garrison empty).
    assert t.state in ("cooldown", "idle")


@pytest.mark.unit
def test_tower_resumes_after_event_cooldown():
    t = _tower(x=500, y=500,
               garrison={"Warrior": 8, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Warrior", "Warrior"])
    titan = DummyTitan(700, 500, hp=999999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    # Burn the first event (3 waves + cooldown start).
    for _ in range(int((3 * Tower.WAVE_COOLDOWN + 0.5) / (1 / 60))):
        t.update(1 / 60)
    assert t.state == "cooldown"
    # Tick through the event cooldown — tower returns to idle then immediately
    # re-engages because the titan is still in aggro and garrison is full.
    for _ in range(int((Tower.EVENT_COOLDOWN + 0.2) / (1 / 60))):
        t.update(1 / 60)
    assert t.state in ("idle", "active")
    # One more wave tick → must deploy again.
    for _ in range(int((Tower.WAVE_COOLDOWN + 0.2) / (1 / 60))):
        t.update(1 / 60)
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"
                and e.is_alive]
    assert len(soldiers) >= 4 * 10 - 5  # 4th squad arrived (allow a few KIA)


@pytest.mark.unit
def test_tower_titan_leaves_aggro_ends_event():
    t = _tower(x=500, y=500,
               garrison={"Warrior": 8, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Warrior", "Warrior"])
    titan = DummyTitan(700, 500, hp=999999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    t.update(0.0)
    assert t.state == "active"
    # Yank the titan far away → no titan in aggro anymore.
    titan.x = 500 + Tower.AGGRO_RADIUS + 200
    for _ in range(int((Tower.WAVE_COOLDOWN + 0.2) / (1 / 60))):
        t.update(1 / 60)
    # State must have ended (cooldown after the truncated event).
    assert t.state in ("cooldown", "idle")
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    # Only the initial wave deployed before the titan left.
    assert len(soldiers) == 10


# ---------- Bounds / draw ----------

@pytest.mark.unit
def test_tower_bounds_rect_covers_body():
    t = _tower(x=500, y=500)
    r = t.bounds()
    assert r.width == Tower.BODY_W
    assert r.height == Tower.BODY_H + Tower.ROOF_H
    # Bottom of the tower sits at y (its anchor).
    assert r.bottom == 500


# ---------- Menu logic ----------

@pytest.mark.unit
def test_tower_menu_cycle_and_close():
    import pygame
    t = _tower()
    menu = TowerMenu(t, screen_size=(960, 600))
    assert menu.is_open is True
    # Cycle wave slot 0 once via tower API used by the menu button.
    before = t.wave_order[0]
    t.cycle_wave_slot(0)
    assert t.wave_order[0] != before
    # Close the menu and ensure the aggro highlight is cleared.
    assert t._highlight_aggro is True
    menu.close()
    assert menu.is_open is False
    assert t._highlight_aggro is False


@pytest.mark.unit
def test_tower_menu_consumes_outside_click_and_closes():
    import pygame
    t = _tower()
    menu = TowerMenu(t, screen_size=(960, 600))
    fake_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5))
    consumed = menu.handle_event(fake_event)
    assert consumed is True
    assert menu.is_open is False


@pytest.mark.unit
def test_tower_menu_adjust_garrison_via_plus_button():
    import pygame
    t = _tower(garrison={"Warrior": 0, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Lancer", "Archer"])
    menu = TowerMenu(t, screen_size=(960, 600))
    plus = menu._row_rects["Warrior"][1]
    fake_event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=plus.center,
    )
    consumed = menu.handle_event(fake_event)
    assert consumed is True
    assert t.garrison["Warrior"] == 1


# ---------- Wipe-triggers-next-wave (Sprint 20) ----------

@pytest.mark.unit
def test_tower_squad_carries_home_bound_to_tower():
    # The squad the tower deploys must inherit the tower's position +
    # AGGRO_RADIUS as its home so members only chase titans inside it.
    t = _tower(x=500, y=500,
               garrison={"Warrior": 8, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Warrior", "Warrior"])
    titan = DummyTitan(700, 500, hp=99999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    t.update(0.0)
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert soldiers
    for s in soldiers:
        assert s._home_pos == (500.0, 500.0)
        assert s._home_radius == Tower.AGGRO_RADIUS


@pytest.mark.unit
def test_tower_redeploys_next_wave_when_squad_wiped():
    # Squad spawns, then we instantly kill every member of that squad — with
    # a titan still in aggro and waves remaining, the tower must NOT wait
    # for WAVE_COOLDOWN; the next wave should fire on the next tick.
    t = _tower(x=500, y=500,
               garrison={"Warrior": 8, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Warrior", "Warrior"])
    titan = DummyTitan(700, 500, hp=99999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    t.update(0.0)
    first_wave = [e for e in WorldQuery.all()
                  if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert len(first_wave) == 10
    # Tower is in active state with a wave cooldown ahead.
    assert t.state == "active"
    assert t._wave_timer > 0.0
    # Wipe the whole squad before the cooldown elapses.
    for s in first_wave:
        s.is_alive = False
    # One tick → wipe detection should reset wave_timer to 0 and the next
    # wave should fire immediately on the second update.
    t.update(1 / 60)
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"
                and e.is_alive]
    assert len(soldiers) == 10                # wave 2 already deployed
    assert t._waves_done == 2


@pytest.mark.unit
def test_tower_wipe_still_respects_three_wave_cap():
    t = _tower(x=500, y=500,
               garrison={"Warrior": 8, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Warrior", "Warrior"])
    titan = DummyTitan(700, 500, hp=99999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    # Repeatedly: deploy, wipe, deploy, wipe, … until tower stops.
    for _ in range(50):
        t.update(1 / 60)
        living = [e for e in WorldQuery.all()
                  if getattr(e, "ENTITY_TYPE", None) == "soldier"
                  and e.is_alive]
        for s in living:
            s.is_alive = False
    # After 3 wipes the tower must be in cooldown (cap unchanged).
    assert t._waves_done == 0  # reset on _end_event
    assert t.state == "cooldown"
    # Total soldiers ever spawned = 3 (all dead now) → garrison dropped 3.
    assert t.total_garrison() == 8 - 3


@pytest.mark.unit
def test_tower_normal_cooldown_when_squad_still_alive():
    t = _tower(x=500, y=500,
               garrison={"Warrior": 8, "Lancer": 0, "Archer": 0},
               wave_order=["Warrior", "Warrior", "Warrior"])
    titan = DummyTitan(700, 500, hp=99999)
    WorldQuery.register(t)
    WorldQuery.register(titan)
    t.update(0.0)
    # Squad alive → wave 2 must wait the full WAVE_COOLDOWN.
    halfway = Tower.WAVE_COOLDOWN * 0.5
    for _ in range(int(halfway / (1 / 60))):
        t.update(1 / 60)
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert len(soldiers) == 10                # still only wave 1
    # Past full cooldown → wave 2 deploys.
    for _ in range(int((halfway + 0.2) / (1 / 60))):
        t.update(1 / 60)
    soldiers = [e for e in WorldQuery.all()
                if getattr(e, "ENTITY_TYPE", None) == "soldier"]
    assert len(soldiers) == 20
