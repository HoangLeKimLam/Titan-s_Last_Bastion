# prioritycheck.py — Test độc lập cho Priority.py
#
# File này KHÔNG mở cửa sổ pygame. Nó chỉ dựng các entity giả (mock)
# rồi kiểm tra từng bộ TargetPriorityStrategy trả về đúng mục tiêu kỳ
# vọng theo luật ưu tiên đã đặc tả.
#
# Chạy:  python prioritycheck.py
# File nằm trong CHECK/ nên lùi 1 cấp để import Priority.py ở root.

import os
import sys

# CHECK/ → lùi 1 cấp về root (chứa Priority.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Priority import (  # noqa: E402
    TargetContext,
    DefaultPriority, ArmoredPriority, BeastPriority, KamikazePriority,
    SoldierHunterPriority, TowerHunterPriority, WitchPriority, WolfPriority,
    make_priority_for,
    HQ, WALL, TOWER, SOLDIER, COMMANDER,
)


# ── Entity giả ────────────────────────────────────────────────────

class MockEntity:
    """Entity tối giản: đủ x, y, is_alive, entity_type cho Priority đọc."""

    def __init__(self, name: str, etype: str, x: float = 0.0,
                 y: float = 0.0, alive: bool = True):
        self.name        = name
        self.entity_type = etype
        self.x           = float(x)
        self.y           = float(y)
        self.is_alive    = alive

    def __repr__(self):
        return self.name


class MockTitan:
    """Titan giả — chỉ cần vị trí cho phép tính khoảng cách."""

    def __init__(self, kind: str, x: float = 0.0, y: float = 0.0):
        self._kind    = kind
        self.x        = float(x)
        self.y        = float(y)
        self.is_alive = True

    # make_priority_for() đọc type(titan).__name__ → ta giả lập bằng cách
    # đặt __class__.__name__ động không tiện; thay vào đó test gọi class
    # Priority trực tiếp. make_priority_for được test riêng bên dưới.


# ── Khung chạy test ───────────────────────────────────────────────

_passed = 0
_failed = 0


def check(label: str, got, expected):
    """So sánh kết quả; in PASS/FAIL và đếm."""
    global _passed, _failed
    ok = got is expected
    if ok:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")
        print(f"        ky vong = {expected!r}")
        print(f"        nhan duoc = {got!r}")


# ─────────────────────────────────────────────────────────────────
#  Bộ entity dùng chung cho phần lớn test
# ─────────────────────────────────────────────────────────────────

def make_world():
    """Dựng 1 thế giới chuẩn: HQ + 2 wall + 2 tower + 2 soldier + 1 commander."""
    hq        = MockEntity('HQ', HQ, x=500, y=500)
    wall      = MockEntity('Wall', WALL, x=300, y=300)
    tower_a   = MockEntity('TowerA', TOWER, x=120, y=100)
    tower_b   = MockEntity('TowerB', TOWER, x=400, y=420)
    soldier_a = MockEntity('SoldierA', SOLDIER, x=110, y=90)
    soldier_b = MockEntity('SoldierB', SOLDIER, x=380, y=400)
    commander = MockEntity('Commander', COMMANDER, x=130, y=110)
    return dict(hq=hq, wall=wall, tower_a=tower_a, tower_b=tower_b,
                soldier_a=soldier_a, soldier_b=soldier_b, commander=commander)


# ─────────────────────────────────────────────────────────────────
#  TEST 1 — DefaultPriority
# ─────────────────────────────────────────────────────────────────

def test_default():
    print("\n[1] DefaultPriority (Titan thuong)")
    w = make_world()
    titan = MockTitan('Regular', x=100, y=100)
    p = DefaultPriority()

    # 1a. Đường vào HQ thông → đánh HQ.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True)
    check("duong thong -> HQ", p.select_target(titan, ctx), w['hq'])

    # 1b. Có Wall cản, không bị quấy rối → đánh Wall.
    ctx = TargetContext(hq=w['hq'], blocking_wall=w['wall'], can_reach_hq=False)
    check("wall can duong -> Wall", p.select_target(titan, ctx), w['wall'])

    # 1c. Đang đi tới Wall NHƯNG bị Tower tấn công → chuyển sang Tower.
    ctx = TargetContext(hq=w['hq'], blocking_wall=w['wall'], can_reach_hq=False,
                        attackers=[w['tower_a']])
    check("bi Tower danh -> Tower (chen len Wall)",
          p.select_target(titan, ctx), w['tower_a'])

    # 1d. Bị nhiều attacker (1 tower xa + 1 soldier gần) → chọn kẻ gần nhất.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        attackers=[w['tower_b'], w['soldier_a']])
    check("nhieu attacker -> ke gan nhat (SoldierA)",
          p.select_target(titan, ctx), w['soldier_a'])

    # 1e. Khóa mục tiêu: đang đánh TowerA (còn sống) → giữ nguyên dù
    #     đường vào HQ đang thông.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        current_target=w['tower_a'])
    check("dang khoa TowerA con song -> giu TowerA",
          p.select_target(titan, ctx), w['tower_a'])

    # 1f. Mục tiêu khóa đã chết → bỏ khóa, fallback HQ.
    w['tower_a'].is_alive = False
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        current_target=w['tower_a'])
    check("TowerA khoa da chet -> fallback HQ",
          p.select_target(titan, ctx), w['hq'])

    # 1g. Commander tấn công nhưng KHÔNG phải loại reactive của Default
    #     (Default reactive = Tower/Soldier) → bỏ qua, vẫn về HQ.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        attackers=[w['commander']])
    check("bi Commander danh -> Default bo qua, ve HQ",
          p.select_target(titan, ctx), w['hq'])


# ─────────────────────────────────────────────────────────────────
#  TEST 2 — ArmoredPriority
# ─────────────────────────────────────────────────────────────────

def test_armored():
    print("\n[2] ArmoredPriority")
    w = make_world()
    titan = MockTitan('Armored', x=100, y=100)
    p = ArmoredPriority()

    # 2a. Có Wall → đánh Wall kể cả khi đường vào HQ thông.
    ctx = TargetContext(hq=w['hq'], blocking_wall=w['wall'], can_reach_hq=True)
    check("co Wall -> Wall (uu tien tren HQ)",
          p.select_target(titan, ctx), w['wall'])

    # 2b. Không có Wall → HQ.
    ctx = TargetContext(hq=w['hq'], blocking_wall=None, can_reach_hq=True)
    check("khong Wall -> HQ", p.select_target(titan, ctx), w['hq'])

    # 2c. Còn giáp + có Wall → Armored bỏ qua reactive, tiếp tục phá Wall.
    ctx = TargetContext(hq=w['hq'], blocking_wall=w['wall'],
                        attackers=[w['commander']])
    check("con giap + bi Commander danh -> van Wall",
          p.select_target(titan, ctx), w['wall'])

    # 2d. Còn giáp + bị Soldier tấn công → vẫn ưu tiên Wall tuyệt đối.
    ctx = TargetContext(hq=w['hq'], blocking_wall=w['wall'],
                        attackers=[w['soldier_b']])
    check("con giap + bi Soldier danh -> van Wall",
          p.select_target(titan, ctx), w['wall'])


# ─────────────────────────────────────────────────────────────────
#  TEST 3 — BeastPriority
# ─────────────────────────────────────────────────────────────────

def test_beast():
    print("\n[3] BeastPriority")
    w = make_world()
    titan = MockTitan('Beast', x=100, y=100)
    p = BeastPriority()

    # 3a. Chưa aim ai → chọn Tower gần nhất (TowerA gần hơn TowerB).
    ctx = TargetContext(hq=w['hq'], towers=[w['tower_a'], w['tower_b']])
    check("chua aim -> Tower gan nhat (TowerA)",
          p.select_target(titan, ctx), w['tower_a'])

    # 3b. Đang aim TowerB (còn sống) → theo tới chết, không nhảy sang TowerA.
    ctx = TargetContext(hq=w['hq'], towers=[w['tower_a'], w['tower_b']],
                        current_target=w['tower_b'])
    check("dang aim TowerB -> giu TowerB",
          p.select_target(titan, ctx), w['tower_b'])

    # 3c. Đang aim TowerB thì khóa TowerB tới chết, không bị Soldier cắt ngang.
    ctx = TargetContext(hq=w['hq'], towers=[w['tower_a'], w['tower_b']],
                        current_target=w['tower_b'],
                        attackers=[w['soldier_a']])
    check("aim TowerB + bi Soldier danh -> giu TowerB",
          p.select_target(titan, ctx), w['tower_b'])

    # 3d. Xử lý xong Soldier (soldier chết), quay lại — TowerB còn sống
    #     nên aim tiếp TowerB.
    w['soldier_a'].is_alive = False
    ctx = TargetContext(hq=w['hq'], towers=[w['tower_a'], w['tower_b']],
                        current_target=w['tower_b'],
                        attackers=[w['soldier_a']])
    check("Soldier chet -> quay lai TowerB",
          p.select_target(titan, ctx), w['tower_b'])

    # 3e. Hết Tower → HQ.
    ctx = TargetContext(hq=w['hq'], towers=[])
    check("het Tower -> HQ", p.select_target(titan, ctx), w['hq'])

    # 3f. Hết Tower, HQ chết → Wall.
    w['hq'].is_alive = False
    ctx = TargetContext(hq=w['hq'], towers=[], blocking_wall=w['wall'])
    check("het Tower + HQ chet -> Wall",
          p.select_target(titan, ctx), w['wall'])


# ─────────────────────────────────────────────────────────────────
#  TEST 4 — KamikazePriority
# ─────────────────────────────────────────────────────────────────

def test_kamikaze():
    print("\n[4] KamikazePriority")
    w = make_world()
    titan = MockTitan('Kamikaze', x=100, y=100)
    p = KamikazePriority()

    # 4a. Có Soldier → lao vào Soldier (kể cả khi đường HQ thông).
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        soldiers=[w['soldier_a'], w['soldier_b']],
                        commanders=[w['commander']])
    # SoldierA (110,90) gần titan (100,100) hơn Commander (130,110).
    check("co Soldier/Commander -> ke gan nhat (SoldierA)",
          p.select_target(titan, ctx), w['soldier_a'])

    # 4b. Chỉ còn Commander → vẫn lao vào (Commander là mục tiêu chủ động).
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        soldiers=[], commanders=[w['commander']])
    check("chi con Commander -> Commander",
          p.select_target(titan, ctx), w['commander'])

    # 4c. Hết lính/tướng, đường HQ thông → HQ.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True, soldiers=[])
    check("het linh/tuong -> HQ", p.select_target(titan, ctx), w['hq'])

    # 4d. Hết lính/tướng nhưng bị Tower tấn công → quay sang Tower.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True, soldiers=[],
                        attackers=[w['tower_b']])
    check("bi Tower danh -> Tower", p.select_target(titan, ctx), w['tower_b'])


# ─────────────────────────────────────────────────────────────────
#  TEST 5 — SoldierHunterPriority
# ─────────────────────────────────────────────────────────────────

def test_soldierhunter():
    print("\n[5] SoldierHunterPriority")
    w = make_world()
    titan = MockTitan('SoldierHunter', x=100, y=100)
    p = SoldierHunterPriority()

    # 5a. Có Soldier → săn Soldier gần nhất.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        soldiers=[w['soldier_a'], w['soldier_b']])
    check("co Soldier -> SoldierA gan nhat",
          p.select_target(titan, ctx), w['soldier_a'])

    # 5b. Hết Soldier → HQ.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True, soldiers=[])
    check("het Soldier -> HQ", p.select_target(titan, ctx), w['hq'])

    # 5c. Hết Soldier nhưng bị Commander tấn công → quay sang Commander.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True, soldiers=[],
                        attackers=[w['commander']])
    check("bi Commander danh -> Commander",
          p.select_target(titan, ctx), w['commander'])

    # 5d. Commander KHÔNG chủ động: có Commander trên map nhưng không
    #     tấn công → SoldierHunter bỏ qua, về HQ.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True, soldiers=[],
                        commanders=[w['commander']])
    check("Commander khong tan cong -> bo qua, ve HQ",
          p.select_target(titan, ctx), w['hq'])


# ─────────────────────────────────────────────────────────────────
#  TEST 6 — TowerHunterPriority
# ─────────────────────────────────────────────────────────────────

def test_towerhunter():
    print("\n[6] TowerHunterPriority")
    w = make_world()
    titan = MockTitan('TowerHunter', x=100, y=100)
    p = TowerHunterPriority()

    # 6a. Có Tower → nhắm Tower gần nhất.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        towers=[w['tower_a'], w['tower_b']])
    check("co Tower -> TowerA gan nhat",
          p.select_target(titan, ctx), w['tower_a'])

    # 6b. Đang nhắm TowerB → theo tới chết.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        towers=[w['tower_a'], w['tower_b']],
                        current_target=w['tower_b'])
    check("dang nham TowerB -> giu TowerB",
          p.select_target(titan, ctx), w['tower_b'])

    # 6c. Hết Tower → HQ.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True, towers=[])
    check("het Tower -> HQ", p.select_target(titan, ctx), w['hq'])

    # 6d. Hết Tower nhưng bị Soldier tấn công → quay sang Soldier.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True, towers=[],
                        attackers=[w['soldier_b']])
    check("bi Soldier danh -> Soldier",
          p.select_target(titan, ctx), w['soldier_b'])


# ─────────────────────────────────────────────────────────────────
#  TEST 7 — WolfPriority
# ─────────────────────────────────────────────────────────────────

def test_wolf():
    print("\n[7] WolfPriority")
    w = make_world()
    titan = MockTitan('Wolf', x=100, y=100)
    p = WolfPriority()

    # 7a. Đường vào HQ thông → HQ.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True)
    check("duong thong -> HQ", p.select_target(titan, ctx), w['hq'])

    # 7b. Wall cản → Wall.
    ctx = TargetContext(hq=w['hq'], blocking_wall=w['wall'], can_reach_hq=False)
    check("wall can -> Wall", p.select_target(titan, ctx), w['wall'])

    # 7c. Bị CẢ Commander lẫn Tower tấn công → Wolf ưu tiên Commander.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        attackers=[w['tower_a'], w['commander']])
    check("bi Commander + Tower -> uu tien Commander",
          p.select_target(titan, ctx), w['commander'])

    # 7d. Chỉ bị Tower/Soldier tấn công → quay sang kẻ gần nhất trong đó.
    ctx = TargetContext(hq=w['hq'], can_reach_hq=True,
                        attackers=[w['tower_b'], w['soldier_a']])
    check("bi Tower + Soldier -> ke gan nhat (SoldierA)",
          p.select_target(titan, ctx), w['soldier_a'])


# ─────────────────────────────────────────────────────────────────
#  TEST 8 — WitchPriority
# ─────────────────────────────────────────────────────────────────

def test_witch():
    print("\n[8] WitchPriority")
    w = make_world()
    titan = MockTitan('Witch', x=100, y=100)
    p = WitchPriority()

    ctx = TargetContext(
        hq=w['hq'],
        towers=[w['tower_a']],
        soldiers=[w['soldier_a'], w['soldier_b']],
        commanders=[w['commander']],
        can_reach_hq=True,
    )
    check("co phong thu -> defender gan nhat",
          p.select_target(titan, ctx), w['soldier_a'])

    ctx = TargetContext(
        hq=w['hq'],
        blocking_wall=w['wall'],
        can_reach_hq=False,
        towers=[],
        soldiers=[],
        commanders=[],
    )
    check("het phong thu + co Wall chan -> Wall",
          p.select_target(titan, ctx), w['wall'])

    ctx = TargetContext(
        hq=w['hq'],
        can_reach_hq=True,
        towers=[],
        soldiers=[],
        commanders=[],
    )
    check("het phong thu + duong thong -> HQ",
          p.select_target(titan, ctx), w['hq'])


# ─────────────────────────────────────────────────────────────────
#  TEST 9 — make_priority_for ánh xạ đúng class
# ─────────────────────────────────────────────────────────────────

def test_factory():
    print("\n[8] make_priority_for - anh xa ten class -> Priority")

    # Tạo các class titan giả với đúng tên để factory nhận diện.
    def fake(name):
        return type(name, (), {})()

    cases = [
        ('ArmoredTitan',  ArmoredPriority),
        ('BeastTitan',    BeastPriority),
        ('Kamikaze',      KamikazePriority),
        ('SoldierHunter', SoldierHunterPriority),
        ('TowerHunter',   TowerHunterPriority),
        ('Witch',         WitchPriority),
        ('Wolf',          WolfPriority),
        ('RegularTitan',  DefaultPriority),   # không có riêng → Default
        ('ColossalTitan', DefaultPriority),   # boss thường → Default
    ]
    global _passed, _failed
    for name, expected_cls in cases:
        got = make_priority_for(fake(name))
        ok = isinstance(got, expected_cls)
        if ok:
            _passed += 1
            print(f"  PASS  {name} -> {expected_cls.__name__}")
        else:
            _failed += 1
            print(f"  FAIL  {name} -> {type(got).__name__} "
                  f"(ky vong {expected_cls.__name__})")


# ── Main ──────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  KIEM TRA Priority.py")
    print("=" * 60)

    test_default()
    test_armored()
    test_beast()
    test_kamikaze()
    test_soldierhunter()
    test_towerhunter()
    test_wolf()
    test_witch()
    test_factory()

    print("\n" + "=" * 60)
    print(f"  KET QUA: {_passed} PASS / {_failed} FAIL")
    print("=" * 60)
    return 0 if _failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
