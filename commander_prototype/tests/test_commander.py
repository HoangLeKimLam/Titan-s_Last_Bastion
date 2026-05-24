"""Unit tests for Commander logic (headless — no display, no sprite I/O)."""
from __future__ import annotations

import os
import sys

import pytest

# Make prototype root importable when pytest is run from project5/
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from _core.event_bus import GameEventBus  # noqa: E402
from _core.exceptions import InsufficientResourceError  # noqa: E402
from _core.game_state import ResourceBundle  # noqa: E402
from armin import ArminCommander  # noqa: E402
from eren import ErenCommander  # noqa: E402
from mikasa import MikasaCommander  # noqa: E402
from stubs import (  # noqa: E402
    DummyTitan,
    LargeTitan,
    ResourceManager,
    StunnedDecorator,
    WorldQuery,
)


@pytest.fixture(autouse=True)
def _reset_globals():
    WorldQuery.clear()
    ResourceManager.reset()
    GameEventBus.get_instance().clear()
    yield
    WorldQuery.clear()
    ResourceManager.reset()
    GameEventBus.get_instance().clear()


@pytest.fixture
def eren():
    return ErenCommander(x=100, y=100, headless=True)


# ---------- Identity & stats ----------

@pytest.mark.unit
def test_starts_at_level_one_with_full_hp(eren):
    assert eren.level == 1
    assert eren.hp == eren.max_hp
    assert eren.NAME == "Eren Yeager"
    assert eren.STAGE == 1


@pytest.mark.unit
def test_higher_level_has_more_hp():
    low = ErenCommander(0, 0, level=1, headless=True)
    high = ErenCommander(0, 0, level=5, headless=True)
    assert high.max_hp > low.max_hp


# ---------- take_damage / defeat ----------

@pytest.mark.unit
def test_take_damage_reduces_hp(eren):
    start = eren.hp
    eren.take_damage(50, "slash")
    assert eren.hp == start - 50


@pytest.mark.unit
def test_invincible_blocks_damage(eren):
    eren._invincible = True
    eren._inv_timer = 5.0
    start = eren.hp
    eren.take_damage(9999, "aoe")
    assert eren.hp == start


@pytest.mark.unit
def test_defeat_drops_one_level_and_revives_full_hp():
    e = ErenCommander(0, 0, level=3, headless=True)
    e.take_damage(999_999, "ram")
    assert e.level == 2
    assert e.hp == e.max_hp


@pytest.mark.unit
def test_defeat_floors_at_level_one():
    e = ErenCommander(0, 0, level=1, headless=True)
    e.take_damage(999_999, "ram")
    assert e.level == 1
    assert e.hp == e.max_hp


@pytest.mark.unit
def test_commander_defeated_event_published():
    received: list = []
    GameEventBus.get_instance().subscribe(
        "commander_defeated", lambda data: received.append(data)
    )
    e = ErenCommander(0, 0, level=2, headless=True)
    e.take_damage(999_999, "ram")
    assert len(received) == 1
    assert received[0]["new_level"] == 1
    assert received[0]["old_level"] == 2


# ---------- Skills & cooldowns ----------

@pytest.mark.unit
def test_invalid_skill_raises(eren):
    with pytest.raises(ValueError):
        eren.use_skill("X")


@pytest.mark.unit
def test_skill_sets_cooldown(eren):
    eren.use_skill("Q")
    assert eren.get_cooldown("Q") == pytest.approx(
        ErenCommander.SKILL_COOLDOWNS["Q"]
    )


@pytest.mark.unit
def test_cooldown_blocks_reuse(eren):
    eren.use_skill("Q")
    cd_before = eren.get_cooldown("Q")
    eren.use_skill("Q")  # second call should be a no-op
    assert eren.get_cooldown("Q") == cd_before


@pytest.mark.unit
def test_cooldown_ticks_down(eren):
    eren.use_skill("Q")
    eren.update(dt=2.0)
    expected = ErenCommander.SKILL_COOLDOWNS["Q"] - 2.0
    assert eren.get_cooldown("Q") == pytest.approx(expected)


# ---------- Movement ----------

@pytest.mark.unit
def test_movement_steps_toward_target(eren):
    start_x = eren.x
    eren.move((500, 100))
    eren.update(dt=1.0)
    assert eren.x > start_x


# ---------- Q: Slash Combo ----------

@pytest.mark.unit
def test_q_damages_titans_in_radius(eren):
    titan = DummyTitan(120, 100, hp=500)  # within Q_RADIUS (80) of (100,100)
    WorldQuery.register(titan)
    eren.use_skill("Q")
    expected = ErenCommander.Q_DAMAGE_PER_HIT * ErenCommander.Q_HIT_COUNT
    assert titan.hp == 500 - expected


@pytest.mark.unit
def test_q_dashes_to_nearest_titan(eren):
    titan = DummyTitan(400, 100, hp=500)
    WorldQuery.register(titan)
    eren.use_skill("Q")
    # Eren stops Q_DASH_GAP px short of the titan on its facing side
    assert eren.x == 400 - ErenCommander.Q_DASH_GAP
    assert eren.y == 100


@pytest.mark.unit
def test_q_dashes_left_when_titan_is_to_the_left():
    e = ErenCommander(500, 100, headless=True)
    titan = DummyTitan(100, 100, hp=500)
    WorldQuery.register(titan)
    e.use_skill("Q")
    assert e.x == 100 + ErenCommander.Q_DASH_GAP
    assert not e._animator.facing_right  # now facing left


@pytest.mark.unit
def test_q_uses_skill_q_animation(eren):
    titan = DummyTitan(300, 100, hp=500)
    WorldQuery.register(titan)
    eren.use_skill("Q")
    assert eren._animator.state == "skill_q"


@pytest.mark.unit
def test_q_with_no_titan_does_not_move(eren):
    start_x, start_y = eren.x, eren.y
    eren.use_skill("Q")
    assert eren.x == start_x and eren.y == start_y
    # And cooldown still triggers (handled by use_skill wrapper)
    assert eren.get_cooldown("Q") == ErenCommander.SKILL_COOLDOWNS["Q"]


@pytest.mark.unit
def test_q_skips_titans_outside_aoe_after_dash():
    """Q dashes to the nearest titan, then AoE-hits only those within
    Q_RADIUS of the landing position — distant unrelated titans survive."""
    e = ErenCommander(100, 100, headless=True)
    nearest = DummyTitan(400, 100, hp=500)
    far_unrelated = DummyTitan(900, 100, hp=500)  # > Q_RADIUS from landing
    WorldQuery.register(nearest)
    WorldQuery.register(far_unrelated)
    e.use_skill("Q")
    assert nearest.hp == 500 - ErenCommander.Q_DAMAGE_PER_HIT * ErenCommander.Q_HIT_COUNT
    assert far_unrelated.hp == 500


# ---------- E: Grappling Swing (mouse-scaled range, must aim at a target) ----------

def _aim_at(commander, vx, vy, large=False):
    """Place a titan exactly at commander+(vx, vy) — i.e. at the LANDING SPOT
    when aiming with vector (vx, vy) — and return that aim vector. |(vx,vy)|
    must be within [E_MIN_RANGE_PX, E_MAX_RANGE_PX] so the range isn't clamped
    away from the target."""
    tx, ty = commander.x + vx, commander.y + vy
    titan = LargeTitan(tx, ty) if large else DummyTitan(tx, ty, hp=99_999)
    WorldQuery.register(titan)
    return (vx, vy)


def _wall(commander):
    """Register a big tower rect spanning far ahead (+x) so successive landing
    spots stay on a valid target across a multi-swing session."""
    WorldQuery.register_structure(
        (commander.x + 60, commander.y - 400, 2400, 800)
    )


@pytest.mark.unit
def test_e_begin_aim_enters_aiming_state(eren):
    assert eren._e_state == "idle"
    eren.begin_aim()
    assert eren._e_state == "aiming"
    assert eren._e_charges == ErenCommander.E_BASE_CHARGES


@pytest.mark.unit
def test_e_begin_aim_blocked_by_cooldown(eren):
    eren._skill_cd["E"] = 5.0
    ok = eren.begin_aim()
    assert ok is False
    assert eren._e_state == "idle"


@pytest.mark.unit
def test_e_aim_invalid_when_landing_on_empty_space(eren):
    eren.begin_aim()
    eren.set_aim_direction(200.0, 0.0)  # lands on empty space
    assert eren._e_aim_valid is False


@pytest.mark.unit
def test_e_aim_valid_when_landing_on_titan(eren):
    vec = _aim_at(eren, 200.0, 0.0)
    eren.begin_aim()
    eren.set_aim_direction(*vec)
    assert eren._e_aim_valid is True


@pytest.mark.unit
def test_e_aim_valid_when_landing_on_structure(eren):
    # Tower rect straddling the landing spot at (eren.x+200, eren.y).
    WorldQuery.register_structure((eren.x + 170, eren.y - 30, 60, 60))
    eren.begin_aim()
    eren.set_aim_direction(200.0, 0.0)
    assert eren._e_aim_valid is True


@pytest.mark.unit
def test_e_invalid_when_target_is_along_ray_but_not_at_tip(eren):
    """A titan partway along the aim line, but the cursor lands BEYOND it on
    empty space → must NOT be flyable (the screenshot bug)."""
    WorldQuery.register(DummyTitan(eren.x + 150, eren.y, hp=999))  # midway
    eren.begin_aim()
    eren.set_aim_direction(400.0, 0.0)  # lands at +400, well past the titan
    assert eren._e_aim_valid is False


@pytest.mark.unit
def test_e_cannot_swing_when_landing_on_empty_space(eren):
    eren.begin_aim()
    start_charges = eren._e_charges
    eren.confirm_swing((200.0, 0.0))   # empty landing spot → cannot fly
    assert eren._e_state == "aiming"
    assert eren._e_charges == start_charges


@pytest.mark.unit
def test_e_aim_too_short_to_reach_target_is_invalid(eren):
    eren.x, eren.y = 100.0, 100.0
    WorldQuery.register(DummyTitan(eren.x + 400, eren.y, hp=999))  # far target
    eren.begin_aim()
    eren.set_aim_direction(150.0, 0.0)  # zoom only 150 → lands short of target
    assert eren._e_aim_valid is False
    assert eren._e_aim_range == pytest.approx(150.0)  # range still follows mouse


@pytest.mark.unit
def test_e_confirm_swing_consumes_one_charge(eren):
    vec = _aim_at(eren, 200.0, 0.0)
    eren.begin_aim()
    start_charges = eren._e_charges
    eren.confirm_swing(vec)
    assert eren._e_state == "flying"
    assert eren._e_charges == start_charges - 1


@pytest.mark.unit
def test_e_session_exhausts_at_zero_charges_and_sets_cooldown(eren):
    _wall(eren)
    eren.begin_aim()
    for _ in range(ErenCommander.E_BASE_CHARGES):
        eren.confirm_swing((200.0, 0.0))
        eren.update(dt=eren._e_flight_dur + 0.01)  # fast-forward each flight
    assert eren._e_state == "idle"
    assert eren._e_charges == 0
    assert eren.get_cooldown("E") == ErenCommander.SKILL_COOLDOWNS["E"]


@pytest.mark.unit
def test_e_cancel_resets_session(eren):
    vec = _aim_at(eren, 200.0, 0.0)
    eren.begin_aim()
    eren.confirm_swing(vec)
    eren.cancel_swing()
    assert eren._e_state == "idle"
    assert eren._e_charges == 0
    assert eren.get_cooldown("E") == ErenCommander.SKILL_COOLDOWNS["E"]


@pytest.mark.unit
def test_e_aim_timeout_auto_cancels(eren):
    eren.begin_aim()
    eren.update(dt=ErenCommander.E_AIM_TIMEOUT + 0.1)
    assert eren._e_state == "idle"


@pytest.mark.unit
def test_e_swing_lerps_toward_target(eren):
    start_x = eren.x
    vec = _aim_at(eren, 250.0, 0.0)  # titan at the landing spot
    eren.begin_aim()
    eren.confirm_swing(vec)
    eren.update(dt=eren._e_flight_dur * 0.5)  # half-way
    assert eren.x > start_x
    assert eren.x < start_x + 250.0


# ---------- E: range scales with mouse distance ----------

@pytest.mark.unit
def test_e_aim_range_scales_with_vector_magnitude(eren):
    eren.begin_aim()
    eren.set_aim_direction(150.0, 0.0)  # length 150 → range 150 (within clamp)
    assert eren._e_aim_range == pytest.approx(150.0)
    assert eren._e_aim_dir == pytest.approx((1.0, 0.0))


@pytest.mark.unit
def test_e_aim_range_clamps_to_min(eren):
    eren.begin_aim()
    eren.set_aim_direction(5.0, 0.0)  # below E_MIN_RANGE_PX (60)
    assert eren._e_aim_range == ErenCommander.E_MIN_RANGE_PX


@pytest.mark.unit
def test_e_aim_range_clamps_to_max(eren):
    eren.begin_aim()
    eren.set_aim_direction(9999.0, 0.0)  # above E_MAX_RANGE_PX (480)
    assert eren._e_aim_range == ErenCommander.E_MAX_RANGE_PX


@pytest.mark.unit
def test_e_confirm_swing_uses_current_aim_range(eren):
    eren.x, eren.y = 100.0, 100.0
    vec = _aim_at(eren, 200.0, 0.0)  # titan at the landing spot (300, 100)
    eren.begin_aim()
    eren.set_aim_direction(*vec)
    eren.confirm_swing()
    assert eren._e_flight_target == pytest.approx((300.0, 100.0))


# ---------- E: down-swing is slower ----------

@pytest.mark.unit
def test_e_downswing_is_slower_than_level_swing():
    # Swing UP at a target above → normal duration.
    up = ErenCommander(100, 300, headless=True)
    vec_up = _aim_at(up, 0.0, -200.0)
    up.begin_aim()
    up.confirm_swing(vec_up)
    assert up._e_state == "flying"
    assert up._e_flight_dur == pytest.approx(ErenCommander.E_FLIGHT_DURATION)

    # Swing DOWN at a target below → ×E_DOWNSWING_SLOWDOWN duration.
    down = ErenCommander(100, 100, headless=True)
    vec_down = _aim_at(down, 0.0, 200.0)
    down.begin_aim()
    down.confirm_swing(vec_down)
    assert down._e_state == "flying"
    assert down._e_flight_dur == pytest.approx(
        ErenCommander.E_FLIGHT_DURATION * ErenCommander.E_DOWNSWING_SLOWDOWN
    )


# ---------- E: mid-flight redirect (one press, no stop-to-aim) ----------

@pytest.mark.unit
def test_e_redirect_flight_midair_to_new_target(eren):
    # Launch toward target A (right).
    eren.begin_aim()
    eren.confirm_swing(_aim_at(eren, 200.0, 0.0))
    assert eren._e_state == "flying"
    charges_after_first = eren._e_charges
    # Mid-flight: a NEW target above; one E press redirects (no stop-to-aim).
    vec_up = _aim_at(eren, 0.0, -200.0)
    ok = eren.redirect_flight(*vec_up)
    assert ok is True
    assert eren._e_state == "flying"                     # still flying
    assert eren._e_charges == charges_after_first - 1    # redirect costs 1 charge
    assert eren._e_flight_target[1] < eren._e_flight_start[1]  # now heading up


@pytest.mark.unit
def test_e_flight_aim_preview_updates_validity(eren):
    """While flying, the aim preview tracks the cursor so the player can see
    which target they'd switch to (update_flight_aim sets _e_aim_valid)."""
    eren.begin_aim()
    eren.confirm_swing(_aim_at(eren, 200.0, 0.0))  # now flying
    assert eren._e_state == "flying"
    # Preview toward empty space → not valid.
    eren.update_flight_aim(0.0, -150.0)
    assert eren._e_aim_valid is False
    # A target appears up there; preview toward it → valid (still flying).
    _aim_at(eren, 0.0, -150.0)
    eren.update_flight_aim(0.0, -150.0)
    assert eren._e_aim_valid is True
    assert eren._e_state == "flying"


@pytest.mark.unit
def test_e_redirect_into_empty_space_keeps_flying(eren):
    eren.begin_aim()
    eren.confirm_swing(_aim_at(eren, 200.0, 0.0))
    charges = eren._e_charges
    ok = eren.redirect_flight(0.0, -200.0)   # empty space above → no target
    assert ok is False
    assert eren._e_state == "flying"          # keeps flying
    assert eren._e_charges == charges         # no charge spent


@pytest.mark.unit
def test_e_redirect_requires_remaining_charge(eren):
    _wall(eren)
    eren.begin_aim()
    # Consume every charge — the last confirm leaves us flying with 0 left.
    for _ in range(ErenCommander.E_BASE_CHARGES - 1):
        eren.confirm_swing((200.0, 0.0))
        eren.update(dt=eren._e_flight_dur + 0.01)
    eren.confirm_swing((200.0, 0.0))  # final charge → flying, 0 left
    assert eren._e_state == "flying"
    assert eren._e_charges == 0
    assert eren.redirect_flight(200.0, 0.0) is False  # no charge → cannot redirect
    assert eren._e_state == "flying"


# ---------- E: bonus charges (LMB-on-LargeTitan during a swing) ----------

@pytest.mark.unit
def test_lmb_on_large_titan_during_swing_adds_bonus_charge(eren):
    big = LargeTitan(120, 100)  # close + ahead → lockable and in attack cone
    WorldQuery.register(big)
    eren.begin_aim()
    eren.confirm_swing((1.0, 0.0))  # consume 1 base charge → 2 left
    start_charges = eren._e_charges
    eren.basic_attack()  # cone hits the large titan
    assert eren._e_charges == start_charges + 1
    assert eren._e_bonus_pool == 1
    assert eren._e_bonus_timer == pytest.approx(ErenCommander.E_BONUS_LIFETIME)


@pytest.mark.unit
def test_lmb_on_normal_titan_does_not_add_bonus_charge(eren):
    normal = DummyTitan(120, 100, hp=500)
    WorldQuery.register(normal)
    eren.begin_aim()
    eren.confirm_swing((1.0, 0.0))
    start_charges = eren._e_charges
    eren.basic_attack()
    assert eren._e_charges == start_charges  # no bonus from regular titan
    assert eren._e_bonus_pool == 0


@pytest.mark.unit
def test_bonus_pool_expires_after_lifetime(eren):
    big = LargeTitan(120, 100)
    WorldQuery.register(big)
    eren.begin_aim()
    eren.confirm_swing((1.0, 0.0))
    eren.basic_attack()  # earn 1 bonus
    assert eren._e_bonus_pool == 1
    # Tick past the bonus lifetime
    eren.update(dt=ErenCommander.E_BONUS_LIFETIME + 0.1)
    assert eren._e_bonus_pool == 0


@pytest.mark.unit
def test_e_charges_never_exceed_max():
    e = ErenCommander(0, 0, headless=True)
    big = LargeTitan(20, 0)
    WorldQuery.register(big)
    e.begin_aim()
    e.confirm_swing((1.0, 0.0))
    # Spam LMB to repeatedly award bonus charges
    for _ in range(20):
        e.basic_attack()
    assert e._e_charges <= ErenCommander.E_MAX_CHARGES


@pytest.mark.unit
def test_large_titan_is_marked_is_large():
    assert LargeTitan.IS_LARGE is True
    big = LargeTitan(0, 0)
    assert big.IS_LARGE is True
    # Default DummyTitan must NOT be flagged large
    small = DummyTitan(0, 0)
    assert small.IS_LARGE is False


# ---------- Titan-damage STACK (125/150/200/250% over 4 consecutive hits) ----------

def _stacked(commander, combo_step: int, stack_index: int) -> int:
    """Expected LMB damage for combo_step under stack_index (0-based)."""
    base = commander.BASIC_ATTACK_DAMAGES[combo_step]
    mult = commander.TITAN_DMG_STACK_MULTS[
        min(stack_index, len(commander.TITAN_DMG_STACK_MULTS) - 1)
    ]
    return int(round(base * mult))


@pytest.mark.unit
def test_titan_stack_first_hit_is_125_percent(eren):
    titan = DummyTitan(120, 100, hp=9_999)
    WorldQuery.register(titan)
    eren.basic_attack()  # combo step0, stack idx0 → 125%
    assert titan.hp == 9_999 - _stacked(eren, 0, 0)
    assert eren.titan_stack == 1


@pytest.mark.unit
def test_titan_stack_escalates_125_150_200_250(eren):
    titan = DummyTitan(120, 100, hp=99_999)
    WorldQuery.register(titan)
    hp = 99_999
    # combo cycles 0,1,2,0 while stack idx grows 0,1,2,3
    for combo_step, stack_idx in [(0, 0), (1, 1), (2, 2), (0, 3)]:
        eren.basic_attack()
        hp -= _stacked(eren, combo_step, stack_idx)
        assert titan.hp == hp
    assert eren.titan_stack == 4


@pytest.mark.unit
def test_titan_stack_caps_at_250_percent_on_fifth_hit(eren):
    titan = DummyTitan(120, 100, hp=999_999)
    WorldQuery.register(titan)
    for _ in range(4):
        eren.basic_attack()
    assert eren.titan_stack == 4
    hp_before = titan.hp
    eren.basic_attack()  # 5th hit: combo step1 (base35), stack capped at 250%
    assert titan.hp == hp_before - _stacked(eren, 1, 3)
    assert eren.titan_stack == 4  # stays capped


@pytest.mark.unit
def test_titan_stack_resets_after_window(eren):
    titan = DummyTitan(120, 100, hp=99_999)
    WorldQuery.register(titan)
    eren.basic_attack()
    eren.basic_attack()
    assert eren.titan_stack == 2
    # No hit for longer than TITAN_STACK_RESET_WINDOW → stack clears.
    # (This wait also exceeds COMBO_RESET_WINDOW, so the combo resets to
    # attack1/step0 too.)
    eren.update(dt=ErenCommander.TITAN_STACK_RESET_WINDOW + 0.1)
    assert eren.titan_stack == 0
    hp_before = titan.hp
    eren.basic_attack()  # fresh chain: combo step0 (base25) at 125%
    assert titan.hp == hp_before - _stacked(eren, 0, 0)
    assert eren.titan_stack == 1


@pytest.mark.unit
def test_q_damage_not_affected_by_titan_stack(eren):
    # Build a stack with LMB, then Q should still deal flat Q damage.
    titan = DummyTitan(120, 100, hp=99_999)
    WorldQuery.register(titan)
    eren.basic_attack()
    eren.basic_attack()  # stack now 2
    hp_before = titan.hp
    eren.use_skill("Q")
    expected = ErenCommander.Q_DAMAGE_PER_HIT * ErenCommander.Q_HIT_COUNT
    assert titan.hp == hp_before - expected


# ---------- R: Titan Form ----------

@pytest.mark.unit
def test_r_activates_invincibility_and_aoe(eren):
    titan = DummyTitan(150, 100, hp=500)  # within R_RADIUS 150
    WorldQuery.register(titan)
    eren.use_skill("R")
    assert eren.is_invincible
    assert titan.hp == 500 - ErenCommander.R_DAMAGE


@pytest.mark.unit
def test_invincibility_expires():
    e = ErenCommander(0, 0, headless=True)
    e.use_skill("R")
    e.update(dt=ErenCommander.R_DURATION + 0.1)
    assert not e.is_invincible


# ---------- Upgrades ----------

@pytest.mark.unit
def test_upgrade_costs_resources():
    e = ErenCommander(0, 0, headless=True)
    rm = ResourceManager.get_instance()
    before_wood = rm.stock.wood
    e.upgrade()
    assert e.level == 2
    assert rm.stock.wood < before_wood


# ---------- Basic attack (LMB combo) ----------

@pytest.mark.unit
def test_basic_attack_first_click_uses_attack1_state(eren):
    eren.basic_attack()
    assert eren._animator.state == "attack1"


@pytest.mark.unit
def test_basic_attack_combo_cycles_through_three_states(eren):
    eren.basic_attack()
    assert eren._animator.state == "attack1"
    eren.basic_attack()
    assert eren._animator.state == "attack2"
    eren.basic_attack()
    assert eren._animator.state == "attack3"


@pytest.mark.unit
def test_basic_attack_combo_wraps_back_to_attack1(eren):
    for _ in range(3):
        eren.basic_attack()
    eren.basic_attack()  # 4th click
    assert eren._animator.state == "attack1"


@pytest.mark.unit
def test_basic_attack_damage_escalates_with_base_and_stack(eren):
    """Base 25/35/60 combo, scaled by the 125/150/200% stack multipliers."""
    titan = DummyTitan(120, 100, hp=9_999)  # within range of eren (100,100)
    WorldQuery.register(titan)
    hp = 9_999
    eren.basic_attack()
    hp -= _stacked(eren, 0, 0)            # attack1 ×125%
    assert titan.hp == hp
    eren.basic_attack()
    hp -= _stacked(eren, 1, 1)            # attack2 ×150%
    assert titan.hp == hp
    eren.basic_attack()
    hp -= _stacked(eren, 2, 2)            # attack3 ×200%
    assert titan.hp == hp


@pytest.mark.unit
def test_basic_attack_misses_titan_outside_radius(eren):
    far = DummyTitan(600, 600, hp=500)
    WorldQuery.register(far)
    eren.basic_attack()
    assert far.hp == 500


@pytest.mark.unit
def test_basic_attack_misses_titan_directly_behind_commander(eren):
    """Cone faces forward — titan behind takes 0 damage."""
    # Eren defaults to facing_right=True; place titan to the left (behind).
    behind = DummyTitan(50, 100, hp=500)  # dx = -50 from eren at (100,100)
    WorldQuery.register(behind)
    eren.basic_attack()
    assert behind.hp == 500


@pytest.mark.unit
def test_basic_attack_misses_titan_too_far_to_the_side(eren):
    """In-front but outside the 35° lateral half-angle."""
    # At forward=20px, max lateral ≈ 20 * tan(35°) ≈ 14px. Put titan at dy=80.
    wide = DummyTitan(120, 180, hp=500)  # 20 ahead, 80 above
    WorldQuery.register(wide)
    eren.basic_attack()
    assert wide.hp == 500


@pytest.mark.unit
def test_basic_attack_hits_far_in_front_within_new_130_range(eren):
    """The new range (130) reaches further than the old 70."""
    far_front = DummyTitan(220, 100, hp=500)  # 120px in front (was out of 70)
    WorldQuery.register(far_front)
    eren.basic_attack()
    assert far_front.hp == 500 - _stacked(eren, 0, 0)  # attack1 ×125%


@pytest.mark.unit
def test_basic_attack_hits_enemy_on_top_point_blank(eren):
    """Standing essentially on the titan (forward ~ 0) still connects."""
    on_top = DummyTitan(100, 120, hp=500)  # dx=0, dy=20 from eren (100,100)
    WorldQuery.register(on_top)
    eren.basic_attack()
    assert on_top.hp < 500


@pytest.mark.unit
def test_basic_attack_hits_close_offaxis_enemy(eren):
    """Close + in front but off the narrow cone axis — now connects via the
    minimum-lateral close-range rule (previously missed)."""
    close = DummyTitan(120, 140, hp=500)  # dx=20 fwd, dy=40 — outside raw 35° cone
    WorldQuery.register(close)
    eren.basic_attack()
    assert close.hp < 500


@pytest.mark.unit
def test_basic_attack_facing_left_hits_titan_on_the_left(eren):
    """Flip facing — cone follows the sprite direction."""
    eren._animator.set_facing(False)  # now facing left
    left_titan = DummyTitan(20, 100, hp=500)   # 80px to the LEFT of eren
    right_titan = DummyTitan(180, 100, hp=500)  # 80px to the RIGHT (now behind)
    WorldQuery.register(left_titan)
    WorldQuery.register(right_titan)
    eren.basic_attack()
    assert left_titan.hp == 500 - _stacked(eren, 0, 0)  # hit (attack1 ×125%)
    assert right_titan.hp == 500          # behind facing direction → miss


@pytest.mark.unit
def test_combo_resets_after_window_of_inactivity(eren):
    titan = DummyTitan(120, 100, hp=9_999)
    WorldQuery.register(titan)
    hp = 9_999
    eren.basic_attack()  # attack1, stack idx0
    hp -= _stacked(eren, 0, 0)
    eren.basic_attack()  # attack2, stack idx1
    hp -= _stacked(eren, 1, 1)
    assert titan.hp == hp
    # Wait longer than COMBO_RESET_WINDOW (and the stack window) → both reset
    eren.update(dt=2.0)
    eren.basic_attack()  # resets → attack1 at fresh stack idx0
    assert eren._animator.state == "attack1"
    hp -= _stacked(eren, 0, 0)
    assert titan.hp == hp


@pytest.mark.unit
def test_combo_locked_during_first_half_of_swing(eren):
    titan = DummyTitan(120, 100, hp=9_999)
    WorldQuery.register(titan)
    hp = 9_999
    eren.basic_attack()  # attack1, stack idx0
    hp -= _stacked(eren, 0, 0)
    assert titan.hp == hp
    # Simulate being mid-swing (anim_left > 50% of total)
    eren._combo_anim_total = 0.5
    eren._combo_anim_left = 0.4
    eren.basic_attack()  # should be ignored (no damage, no stack change)
    assert titan.hp == hp
    assert eren._animator.state == "attack1"
    assert eren.titan_stack == 1
    # Move into the second half — cancel window opens
    eren._combo_anim_left = 0.1
    eren.basic_attack()  # chains to attack2, stack idx1
    assert eren._animator.state == "attack2"
    hp -= _stacked(eren, 1, 1)
    assert titan.hp == hp


@pytest.mark.unit
def test_combo_step_property_reflects_next_attack(eren):
    assert eren.combo_step == 0
    eren.basic_attack()
    assert eren.combo_step == 1
    eren.basic_attack()
    assert eren.combo_step == 2
    eren.basic_attack()
    assert eren.combo_step == 0  # wrapped


# ---------- Upgrades (continued) ----------

# ---------- Mikasa (separate sprite pack, same template) ----------

@pytest.mark.unit
def test_mikasa_identity_and_sprite_pack():
    m = MikasaCommander(0, 0, headless=True)
    assert m.NAME == "Mikasa Ackerman"
    assert m.STAGE == 2
    assert "Knight 2D Pixel Art" in m.SPRITE_FOLDER
    assert "with_outline" in m.SPRITE_FOLDER
    assert m.FRAME_WIDTH == 96
    assert m.FRAME_HEIGHT == 84


@pytest.mark.unit
def test_mikasa_q_dashes_and_aoe_like_eren():
    m = MikasaCommander(100, 100, headless=True)
    titan = DummyTitan(400, 100, hp=500)
    WorldQuery.register(titan)
    m.use_skill("Q")
    assert m.x == 400 - MikasaCommander.Q_DASH_GAP
    expected = MikasaCommander.Q_DAMAGE_PER_HIT * MikasaCommander.Q_HIT_COUNT
    assert titan.hp == 500 - expected


@pytest.mark.unit
def test_mikasa_basic_attack_combo_cycles():
    m = MikasaCommander(100, 100, headless=True)
    titan = DummyTitan(120, 100, hp=999)
    WorldQuery.register(titan)
    m.basic_attack()
    m.basic_attack()
    m.basic_attack()
    assert m._animator.state == "attack3"
    # Base 25/35/60 scaled by the 125/150/200% stack
    expected = (_stacked(m, 0, 0) + _stacked(m, 1, 1) + _stacked(m, 2, 2))
    assert titan.hp == 999 - expected


@pytest.mark.unit
def test_mikasa_r_invincibility():
    m = MikasaCommander(0, 0, headless=True)
    m.use_skill("R")
    assert m.is_invincible
    m.update(dt=MikasaCommander.R_DURATION + 0.1)
    assert not m.is_invincible


# ---------- Armin (Warrior pack, folder-mode loader) ----------

@pytest.mark.unit
def test_armin_identity_and_sprite_pack():
    a = ArminCommander(0, 0, headless=True)
    assert a.NAME == "Armin Arlert"
    assert a.STAGE == 4
    assert "Warrior" in a.SPRITE_FOLDER
    # Folder-mode spec uses 'folder'+'prefix'+'count', not 'file'
    assert "folder" in a.SPRITE_FRAMES["idle"]
    assert a.SPRITE_FRAMES["idle"]["prefix"] == "Warrior_Idle_"
    assert a.SPRITE_FRAMES["idle"]["count"] == 6


@pytest.mark.unit
def test_armin_q_dashes_and_aoes():
    a = ArminCommander(100, 100, headless=True)
    titan = DummyTitan(400, 100, hp=500)
    WorldQuery.register(titan)
    a.use_skill("Q")
    assert a.x == 400 - ArminCommander.Q_DASH_GAP
    expected = ArminCommander.Q_DAMAGE_PER_HIT * ArminCommander.Q_HIT_COUNT
    assert titan.hp == 500 - expected


@pytest.mark.unit
def test_armin_basic_attack_combo_cycles():
    a = ArminCommander(100, 100, headless=True)
    titan = DummyTitan(120, 100, hp=999)
    WorldQuery.register(titan)
    a.basic_attack()
    a.basic_attack()
    a.basic_attack()
    assert a._animator.state == "attack3"
    expected = (_stacked(a, 0, 0) + _stacked(a, 1, 1) + _stacked(a, 2, 2))
    assert titan.hp == 999 - expected


@pytest.mark.unit
def test_upgrade_raises_when_broke():
    e = ErenCommander(0, 0, headless=True)
    ResourceManager.reset()
    ResourceManager.get_instance()._stock = ResourceBundle()  # empty
    with pytest.raises(InsufficientResourceError):
        e.upgrade()
