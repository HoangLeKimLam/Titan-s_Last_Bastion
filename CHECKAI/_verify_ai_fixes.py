"""_verify_ai_fixes.py — Kiểm thử headless 3 bug đã fix trong AI.

Chạy:  python CHECKAI/_verify_ai_fixes.py
(đặt SDL_VIDEODRIVER=dummy để không cần cửa sổ).

Kiểm:
  Bug 1 — animation: mọi titan phải LOOP frame (`_anim_col` đổi) khi
          di chuyển/tấn công; titan PHẢI thực sự dịch chuyển (x,y đổi).
  Run    — titan chuyển sang chạy (`_is_running=True`) khi mục tiêu xa.
  Bug 2 — Kamikaze: sau khi nổ, Tower & Commander trong tầm nổ phải
          mất máu (AoE) và bị đẩy lùi (knockback).

Không phải pytest — chạy thẳng, in PASS/FAIL từng mục, exit code != 0
nếu có mục FAIL.
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import _ai_bootstrap  # noqa: F401,E402
from Titan import (  # noqa: E402
    RegularTitan, ArmoredTitan, Wolf, TowerHunter, SoldierHunter, Kamikaze,
    Witch,
)
from Boss import ColossalTitan, BeastTitan, FoundingTitan  # noqa: E402
from AI import make_ai_for, SimpleWorldView  # noqa: E402
from _ai_dummies import (  # noqa: E402
    Headquarters, WallDummy, TowerDummy, SoldierDummy, CommanderDummy,
)

_FAILS: list = []


def check(name: str, ok: bool, detail: str = '') -> None:
    """In 1 dòng kết quả; gom mục FAIL để báo cuối cùng."""
    tag = 'PASS' if ok else 'FAIL'
    print(f"  [{tag}] {name}" + (f"  — {detail}" if detail else ''))
    if not ok:
        _FAILS.append(name)


# ── Bug 1 — animation loop + di chuyển ───────────────────────────

def test_animation_and_movement() -> None:
    """Mỗi titan: chạy AI nhiều frame, kỳ vọng x/y đổi + _anim_col đổi."""
    print("\n[Bug 1] Animation loop + di chuyển cho TỪNG titan")

    # HQ đặt xa để titan phải đi/chạy một quãng dài.
    hq = Headquarters(1100.0, 360.0)
    cfgs = {
        'hp': 1000, 'speed': 70.0, 'damage': 60,
    }

    cases = [
        ('RegularTitan',  RegularTitan(120.0, 360.0, dict(cfgs)),  True),
        ('ArmoredTitan',  ArmoredTitan(120.0, 360.0, dict(cfgs)),  True),
        ('Wolf',          Wolf(120.0, 360.0, dict(cfgs)),          True),
        ('TowerHunter',   TowerHunter(120.0, 360.0, dict(cfgs)),   True),
        ('SoldierHunter', SoldierHunter(120.0, 360.0, dict(cfgs)), True),
        ('Witch',         Witch(120.0, 360.0, dict(cfgs)),         True),
        ('ColossalTitan', ColossalTitan(120.0, 360.0, dict(cfgs)), True),
        ('FoundingTitan', FoundingTitan(120.0, 360.0, dict(cfgs)), True),
    ]

    for label, titan, has_anim in cases:
        world = SimpleWorldView(hq=hq)
        ai = make_ai_for(titan, world)
        x0, y0 = titan.x, titan.y
        seen_cols = set()
        dt = 1.0 / 30.0
        for _ in range(120):   # 4 giây
            ai.update(dt)
            seen_cols.add(getattr(titan, '_anim_col', 0))
        moved = abs(titan.x - x0) + abs(titan.y - y0)
        check(f"{label}: di chuyển", moved > 5.0,
              f"dịch {moved:.1f}px")
        if has_anim:
            check(f"{label}: loop frame anim", len(seen_cols) >= 2,
                  f"_anim_col đã qua {sorted(seen_cols)}")
        else:
            print(f"  [SKIP] {label}: loop frame anim — titan-stub "
                  f"chưa có spritesheet")


# ── Run — chạy khi mục tiêu xa, đi bộ khi gần ────────────────────

def test_running_when_far() -> None:
    """Titan ở rất xa HQ → phải bật _is_running; tới gần → tắt."""
    print("\n[Run] Chạy đúng lúc — xa thì chạy, gần thì đi bộ")

    hq = Headquarters(1200.0, 360.0)
    titan = RegularTitan(100.0, 360.0, {
        'hp': 1000, 'speed': 70.0, 'damage': 60})
    world = SimpleWorldView(hq=hq)
    ai = make_ai_for(titan, world)

    # Frame đầu: cách HQ ~1100px (> _RUN_THRESHOLD 250) → phải chạy.
    ai.update(1.0 / 30.0)
    check("xa HQ → _is_running=True", getattr(titan, '_is_running', False),
          f"cách {abs(hq.x - titan.x):.0f}px")

    # Dời titan tới sát HQ (trong ngưỡng run) → đi bộ.
    titan.x = hq.x - 120.0
    ai.update(1.0 / 30.0)
    check("gần HQ → _is_running=False",
          not getattr(titan, '_is_running', True),
          f"cách {abs(hq.x - titan.x):.0f}px")


# ── Bug 2 — Kamikaze AoE tower + commander ───────────────────────

def test_kamikaze_aoe() -> None:
    """Kamikaze nổ cạnh 1 Tower + 1 Commander → cả 2 mất máu & bị đẩy."""
    print("\n[Bug 2] Kamikaze AoE — tower/commander mất máu + đẩy lùi")

    # Soldier đặt cạnh để Kamikaze khóa & kích nổ ngay tại đó.
    soldier   = SoldierDummy(500.0, 360.0, label='Sld')
    tower     = TowerDummy(530.0, 360.0, label='Twr')      # trong tầm 80px
    commander = CommanderDummy(470.0, 360.0, name='Levi')  # trong tầm 80px

    kam = Kamikaze(500.0, 360.0, {
        'hp': 600, 'speed': 80.0, 'damage': 50})
    world = SimpleWorldView(
        soldiers=[soldier], towers=[tower], commanders=[commander])
    ai = make_ai_for(kam, world)

    tw_hp0 = tower._hp
    cm_hp0 = commander._hp
    tw_xy0 = (tower.x, tower.y)
    cm_xy0 = (commander.x, commander.y)

    # Chạy đủ lâu để: kích nổ → pause 1.5s → _release_explosion → AoE.
    dt = 1.0 / 30.0
    for _ in range(120):   # 4 giây
        ai.update(dt)
        if getattr(kam, '_has_exploded', False) and ai._aoe_done:
            break

    check("Kamikaze đã nổ", getattr(kam, '_has_exploded', False))
    check("_target được khóa trước khi nổ", kam._target is soldier,
          f"_target = {kam._target!r}")
    check("Tower mất máu (AoE)", tower._hp < tw_hp0,
          f"{tw_hp0} → {tower._hp}")
    check("Commander mất máu (AoE)", commander._hp < cm_hp0,
          f"{cm_hp0} → {commander._hp}")
    tw_moved = abs(tower.x - tw_xy0[0]) + abs(tower.y - tw_xy0[1])
    cm_moved = abs(commander.x - cm_xy0[0]) + abs(commander.y - cm_xy0[1])
    check("Tower bị đẩy lùi (knockback)", tw_moved > 1.0,
          f"dịch {tw_moved:.1f}px")
    check("Commander bị đẩy lùi (knockback)", cm_moved > 1.0,
          f"dịch {cm_moved:.1f}px")


if __name__ == '__main__':
    print("=" * 60)
    print(" KIỂM THỬ FIX BUG — AI / CHECKAI")
    print("=" * 60)
    test_animation_and_movement()
    test_running_when_far()
    test_kamikaze_aoe()

    print("\n" + "=" * 60)
    if _FAILS:
        print(f" KẾT QUẢ: {len(_FAILS)} mục FAIL — {', '.join(_FAILS)}")
        sys.exit(1)
    print(" KẾT QUẢ: TẤT CẢ PASS")
    print("=" * 60)
