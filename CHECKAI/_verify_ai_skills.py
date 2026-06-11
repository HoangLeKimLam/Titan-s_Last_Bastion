"""_verify_ai_skills.py — Kiểm thử headless: AI có kích đúng KỸ NĂNG riêng
của từng titan không (Q4 — rà toàn bộ).

Chạy:  python CHECKAI/_verify_ai_skills.py

Kiểm từng titan đặc thù:
  • RegularTitan   — đòn đánh cơ bản gây sát thương cho HQ.
  • ArmoredTitan   — Dash (Ram) húc Wall → tích `_ram_hits`.
  • Wolf           — đòn cắn antiheal gây sát thương Commander.
  • TowerHunter    — đòn siege ×1.5 hạ máu Tower.
  • SoldierHunter  — cleave gây sát thương Soldier.
  • Kamikaze       — đã kiểm ở _verify_ai_fixes (chỉ smoke).
  • ColossalTitan  — Steam Burst + Jump Stomp kích được.
  • BeastTitan     — ném đá: _throw_timer tụt sau khi ném.
  • FoundingTitan  — P2 summon minion.

Không phải pytest — chạy thẳng, in PASS/FAIL, exit != 0 nếu có FAIL.
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import _ai_bootstrap  # noqa: F401,E402
from Titan import (  # noqa: E402
    RegularTitan, ArmoredTitan, Wolf, TowerHunter, SoldierHunter, Witch,
)
from Boss import ColossalTitan, BeastTitan, FoundingTitan  # noqa: E402
from AI import make_ai_for, SimpleWorldView  # noqa: E402
from _ai_dummies import (  # noqa: E402
    Headquarters, WallDummy, TowerDummy, SoldierDummy, CommanderDummy,
)

_FAILS: list = []
_DT = 1.0 / 30.0


def check(name: str, ok: bool, detail: str = '') -> None:
    tag = 'PASS' if ok else 'FAIL'
    print(f"  [{tag}] {name}" + (f"  — {detail}" if detail else ''))
    if not ok:
        _FAILS.append(name)


def run(ai, frames: int) -> None:
    for _ in range(frames):
        ai.update(_DT)


# ── RegularTitan — đánh cơ bản hạ máu HQ ─────────────────────────

def test_regular() -> None:
    print("\n[RegularTitan] Đòn đánh cơ bản hạ máu HQ")
    hq = RegularTitan  # placeholder
    hq = Headquarters(260.0, 360.0)
    t = RegularTitan(120.0, 360.0, {'hp': 1000, 'speed': 90.0, 'damage': 60})
    ai = make_ai_for(t, SimpleWorldView(hq=hq))
    hp0 = hq._hp
    run(ai, 200)
    check("HQ mất máu vì bị đánh", hq._hp < hp0, f"{hp0} → {hq._hp}")


# ── ArmoredTitan — Dash húc Wall tích _ram_hits ──────────────────

def test_armored() -> None:
    print("\n[ArmoredTitan] Dash (Ram) húc Wall → _ram_hits tăng → vỡ giáp")
    hq   = Headquarters(900.0, 360.0)
    # Wall HP cao để Ram húc đủ `_HITS_TO_BREAK` mà tường chưa sập trước.
    wall = WallDummy(500.0, 360.0, label='Wall', hp=10000)
    t = ArmoredTitan(120.0, 360.0, {'hp': 1500, 'speed': 80.0, 'damage': 70})
    ai = make_ai_for(t, SimpleWorldView(hq=hq, walls=[wall]))
    ram0 = getattr(t, '_ram_hits', 0)
    threshold = getattr(t, '_HITS_TO_BREAK', 15)
    run(ai, 2600)   # đủ lâu để húc ≥ threshold lần
    ram1   = getattr(t, '_ram_hits', 0)
    broken = not getattr(t, '_armor_intact', True)
    check("Dash húc Wall (_ram_hits tăng)", ram1 > ram0,
          f"_ram_hits {ram0} → {ram1}")
    check("Ram đủ ngưỡng → giáp vỡ", broken,
          f"_ram_hits={ram1}/{threshold}, "
          f"_armor_intact={getattr(t,'_armor_intact',True)}")


# ── Wolf — cắn antiheal hạ máu Commander ─────────────────────────

def test_wolf() -> None:
    print("\n[Wolf] Đòn cắn antiheal hạ máu Commander")
    cmdr = CommanderDummy(260.0, 360.0, name='Levi')
    t = Wolf(120.0, 360.0, {'hp': 700, 'speed': 100.0, 'damage': 50})
    ai = make_ai_for(t, SimpleWorldView(commanders=[cmdr]))
    # Wolf priority chỉ cắn commander khi bị tấn công → mô phỏng.
    ai.notify_attacked(cmdr)
    hp0 = cmdr._hp
    run(ai, 200)
    check("Commander mất máu vì bị cắn", cmdr._hp < hp0,
          f"{hp0} → {cmdr._hp}")


# ── TowerHunter — đòn siege hạ máu Tower ─────────────────────────

def test_towerhunter() -> None:
    print("\n[TowerHunter] Đòn siege ×1.5 hạ máu Tower")
    tower = TowerDummy(280.0, 360.0, label='Tower')
    t = TowerHunter(120.0, 360.0, {'hp': 1100, 'speed': 90.0, 'damage': 60})
    ai = make_ai_for(t, SimpleWorldView(towers=[tower]))
    hp0 = tower._hp
    run(ai, 250)
    check("Tower mất máu vì siege", tower._hp < hp0,
          f"{hp0} → {tower._hp}")


# ── SoldierHunter — cleave hạ máu Soldier ────────────────────────

def test_soldierhunter() -> None:
    print("\n[SoldierHunter] Cleave hạ máu Soldier")
    s1 = SoldierDummy(280.0, 350.0, label='S1')
    s2 = SoldierDummy(300.0, 370.0, label='S2')
    t = SoldierHunter(120.0, 360.0, {'hp': 1300, 'speed': 90.0, 'damage': 65})
    ai = make_ai_for(t, SimpleWorldView(soldiers=[s1, s2]))
    hp0 = s1._hp
    run(ai, 250)
    check("Soldier mất máu vì cleave", s1._hp < hp0,
          f"{hp0} → {s1._hp}")


# ── Witch — Cursed x10 toàn map ─────────────────────────────────

def test_witch() -> None:
    print("\n[Witch] Cursed x10 đánh soldier/commander/tower toàn map")
    s = SoldierDummy(500.0, 320.0, label='Sld')
    c = CommanderDummy(540.0, 360.0, name='Levi')
    tw = TowerDummy(580.0, 400.0, label='Tower')
    t = Witch(120.0, 360.0, {'hp': 1200, 'speed': 55.0, 'damage': 45})
    world = SimpleWorldView(soldiers=[s], commanders=[c], towers=[tw])
    _ai_bootstrap._MockWorldQuery.soldiers = [s]
    _ai_bootstrap._MockWorldQuery.commanders = [c]
    _ai_bootstrap._MockWorldQuery.towers = [tw]
    ai = make_ai_for(t, world)
    hp0 = (s._hp, c._hp, tw._hp)
    run(ai, 180)  # 6 giây: summon 1s + hold 2s + release
    check("Soldier trúng Cursed", s._hp < hp0[0], f"{hp0[0]} → {s._hp}")
    check("Commander trúng Cursed", c._hp < hp0[1], f"{hp0[1]} → {c._hp}")
    check("Tower trúng Cursed", tw._hp < hp0[2], f"{hp0[2]} → {tw._hp}")
    check("Witch release đúng 10 tia", getattr(t, '_last_bolt_count', 0) == 10,
          f"last_bolts={getattr(t, '_last_bolt_count', 0)}")
    _ai_bootstrap._MockWorldQuery.soldiers = []
    _ai_bootstrap._MockWorldQuery.commanders = []
    _ai_bootstrap._MockWorldQuery.towers = []


# ── ColossalTitan — Steam Burst + Jump Stomp ─────────────────────

def test_colossal() -> None:
    print("\n[ColossalTitan] Steam Burst + Jump Stomp kích được")
    hq = Headquarters(400.0, 360.0)
    t = ColossalTitan(250.0, 360.0, {'hp': 3000, 'speed': 40.0, 'damage': 90})
    ai = make_ai_for(t, SimpleWorldView(hq=hq))
    saw_steam = saw_jump = False
    for _ in range(900):   # 30 giây — đủ qua cooldown jump (15s)
        ai.update(_DT)
        if getattr(t, '_is_steaming', False):
            saw_steam = True
        if getattr(t, '_is_jumping', False):
            saw_jump = True
    check("Steam Burst kích được", saw_steam)
    check("Jump Stomp kích được", saw_jump)


# ── BeastTitan — ném đá làm tụt _throw_timer ─────────────────────

def test_beast() -> None:
    print("\n[BeastTitan] Ném đá — _throw_timer nạp lại sau khi ném")
    tower = TowerDummy(450.0, 360.0, label='Tower')
    t = BeastTitan(150.0, 360.0, {'hp': 1800, 'speed': 60.0, 'damage': 85})
    ai = make_ai_for(t, SimpleWorldView(towers=[tower]))
    threw = False
    for _ in range(400):
        ai.update(_DT)
        if getattr(t, '_throw_timer', 0.0) > 0.1:
            threw = True   # timer được nạp lại → đã ném ít nhất 1 lần
    check("BeastTitan đã ném đá (throw cooldown nạp)", threw)


# ── FoundingTitan — P2 summon minion ─────────────────────────────

def test_founding() -> None:
    print("\n[FoundingTitan] P2 (HP 20–60%) tự summon minion")
    hq = Headquarters(360.0, 360.0)
    t = FoundingTitan(150.0, 360.0, {'hp': 800, 'speed': 50.0, 'damage': 50})
    ai = make_ai_for(t, SimpleWorldView(hq=hq))
    # Ép HP về ~40% để vào Phase 2.
    if hasattr(t, '_hp'):
        t._hp = int(getattr(t, '_max_hp', 800) * 0.4)
    check_phase = getattr(t, '_check_phase', None)
    if callable(check_phase):
        check_phase()
    saw_summon = False
    for _ in range(400):   # đủ qua summon cooldown
        ai.update(_DT)
        if getattr(t, '_is_summoning', False):
            saw_summon = True
        n = len(getattr(t, '_summoned_minions', []))
        if n > 0:
            saw_summon = True
    phase = getattr(t, '_phase', 1)
    check("FoundingTitan vào Phase 2", phase == 2, f"_phase = {phase}")
    check("Founding P2 tự summon minion", saw_summon)


if __name__ == '__main__':
    print("=" * 60)
    print(" KIỂM THỬ KỸ NĂNG AI — từng titan kích đúng skill riêng")
    print("=" * 60)
    test_regular()
    test_armored()
    test_wolf()
    test_towerhunter()
    test_soldierhunter()
    test_witch()
    test_colossal()
    test_beast()
    test_founding()

    print("\n" + "=" * 60)
    if _FAILS:
        print(f" KẾT QUẢ: {len(_FAILS)} mục FAIL — {', '.join(_FAILS)}")
        sys.exit(1)
    print(" KẾT QUẢ: TẤT CẢ PASS")
    print("=" * 60)
