"""
ImportAll.py — Cổng nhập duy nhất cho cả dự án Titan's Last Bastion.

Mục đích sư phạm
----------------
File này đóng vai trò **facade** (mặt tiền) — gom toàn bộ các "mảnh ghép"
của hệ thống Titan vào một chỗ, để các thành viên trong nhóm chỉ cần viết:

    from ImportAll import *

là có ngay:
  * Tất cả các class Titan thường (RegularTitan, ArmoredTitan, Wolf, ...)
  * Tất cả các Boss (ColossalTitan, BeastTitan, FoundingTitan)
  * Tất cả các Strategy tấn công (MeleeRushStrategy, GroundSlamStrategy, ...)
  * Tất cả các Priority chọn mục tiêu (DefaultPriority, ArmoredPriority, ...)
  * Tất cả các AI tự hành (RegularAI, ColossalAI, ...) + WorldView
  * Hàm tiện ích `spawn_titan(kind, x, y, world)` để tạo 1 dòng là xong.

Quan trọng — không thay đổi cách chỉnh sửa source
-------------------------------------------------
File này CHỈ làm nhiệm vụ **re-export**. Nó KHÔNG sao chép logic.
Mọi chỉnh sửa thông số HP, tốc độ, sát thương, AI behavior, … vẫn được
thực hiện trực tiếp ở các file gốc:

    Titan.py            — các Titan thường + lớp cha Titan
    Boss.py             — 3 Boss
    AttackStrategy.py   — chiến thuật tấn công (Strategy Pattern)
    Priority.py         — cách chọn mục tiêu (Strategy Pattern)
    AI.py               — bộ não tự hành (WorldView + TitanAI + factory)

Khi ai đó sửa Titan.py, lần import tiếp theo qua ImportAll.py sẽ tự
nhận thay đổi (Python re-load module bình thường). Không có cache, không
có bản sao — đây chỉ là "danh bạ" trỏ tới class gốc.

Ví dụ sử dụng
-------------
    # Cách 1 — gom hết:
    from ImportAll import *
    titan = RegularTitan(x=100, y=200)

    # Cách 2 — dùng factory tiện lợi (gắn sẵn AI):
    from ImportAll import spawn_titan
    titan, ai = spawn_titan('regular', 100, 200, world)
    # … rồi trong game loop:
    ai.update(dt)
    titan.update(dt)
    titan.draw(screen)

Lưu ý cho Soldier/Commander production
--------------------------------------
BeastTitan (boss M4) ném đá AOE đẩy lùi soldier + commander. Vector
pushback được set qua attribute `pushback_vx/pushback_vy` của entity và
tween qua nhiều frame. Lớp Soldier/Commander phải:

  1. Khởi tạo 2 attribute trong `__init__`:
        self.pushback_vx = 0.0
        self.pushback_vy = 0.0
     (Hoặc kế thừa từ lớp cha đã có sẵn — xem `CHECKAI/_ai_dummies.py`
      `TargetEntity` để tham khảo mẫu.)

  2. Gọi `RockProjectile.apply_pushback_tween(self, dt)` ở đầu `update(dt)`:
        from ImportAll import RockProjectile
        class Soldier:
            def update(self, dt):
                RockProjectile.apply_pushback_tween(self, dt)
                # … logic riêng …

Nếu quên bước 2 → vector được set nhưng vị trí không bao giờ di chuyển
→ pushback "biến mất" về mặt visual.

Lưu ý cho `SoldierHunterStrategy` (cleave AoE)
---------------------------------------------
Từ bản này, SoldierHunter chém lan quét MỌI loại entity (soldier +
commander + tower + wall + hq) trong bán kính `_splash_radius` quanh
ATTACKER (không phải quanh target). Mặc định khi SoldierHunter khởi
tạo strategy, nó truyền `splash_radius = self._attack_range` để vùng
cleave đồng bộ với tầm đánh.

Hệ quả với hệ thống world query:
  • `WorldQuery.find_in_radius(cx, cy, radius, entity_type)` PHẢI hỗ
    trợ đủ 5 entity_type: 'soldier', 'commander', 'tower', 'wall', 'hq'.
    Nếu world của team thiếu loại nào (vd chưa có 'wall'), strategy
    vẫn an toàn — `find_in_radius` chỉ trả list rỗng cho loại đó.
"""

# =============================================================================
# 1. RE-EXPORT TOÀN BỘ CLASS TỪ 5 FILE GỐC
# =============================================================================
# Dùng `from X import *` để teammate viết `from ImportAll import *` là có hết.
# Thứ tự import quan trọng: Titan trước (vì Boss kế thừa Titan), rồi Strategy/
# Priority/AI (chúng tham chiếu Titan qua duck-typing nên ít ràng buộc hơn).

from Titan import *            # noqa: F401,F403  — Titan base + 7 Titan con
from Boss import *             # noqa: F401,F403  — 3 Boss
from AttackStrategy import *   # noqa: F401,F403  — Strategy tấn công + projectile
from Priority import *         # noqa: F401,F403  — Strategy chọn mục tiêu
from AI import *               # noqa: F401,F403  — WorldView + AI + make_ai_for


# =============================================================================
# 2. IMPORT TƯỜNG MINH NHỮNG CÁI FACTORY CẦN DÙNG
# =============================================================================
# `from X import *` chỉ "rải" tên ra namespace, nhưng bên trong file này muốn
# gọi class cụ thể (để viết factory) thì phải import lại tường minh — như vậy
# IDE và type checker mới thấy được.

from Titan import (
    Titan,
    RegularTitan,
    ArmoredTitan,
    Wolf,
    TowerHunter,
    SoldierHunter,
    Kamikaze,
)
from Boss import (
    ColossalTitan,
    BeastTitan,
    FoundingTitan,
)
from AI import make_ai_for, WorldView


# =============================================================================
# 3. BẢNG TRA "TÊN GỌI TẮT" → CLASS
# =============================================================================
# Dùng kiểu chuỗi ('regular', 'armored', …) cho factory để code gọi spawn
# trông tự nhiên (giống cách config WaveManager đọc từ JSON sau này).
#
# Khi thêm Titan mới vào dự án:
#   1. Tạo class trong Titan.py / Boss.py như bình thường.
#   2. Thêm 1 dòng vào bảng dưới đây — KHÔNG cần sửa logic factory.

_TITAN_REGISTRY: dict = {
    # Titan thường — file Titan.py
    'regular':        RegularTitan,
    'armored':        ArmoredTitan,
    'wolf':           Wolf,
    'tower_hunter':   TowerHunter,
    'soldier_hunter': SoldierHunter,
    'kamikaze':       Kamikaze,

    # Boss — file Boss.py
    'colossal':       ColossalTitan,
    'beast':          BeastTitan,
    'founding':       FoundingTitan,
}


# =============================================================================
# 4. FACTORY TIỆN LỢI: spawn_titan
# =============================================================================
def spawn_titan(kind: str,
                x: float,
                y: float,
                world: WorldView,
                config: dict = None) -> tuple:
    """
    Tạo một Titan đã gắn sẵn AI tự hành — chỉ một dòng là xong.

    Tham số
    -------
    kind : str
        Tên gọi tắt của Titan, lấy từ bảng `_TITAN_REGISTRY`.
        Ví dụ: 'regular', 'armored', 'wolf', 'kamikaze',
        'colossal', 'beast', 'founding', …
    x, y : float
        Toạ độ spawn ban đầu (đơn vị pixel theo hệ trục game).
    world : WorldView
        "Đôi mắt" của AI — phải truyền vào để AI biết hỏi
        ai gần nhất, tường nào đang chặn, … (xem AI.py).
    config : dict, optional
        Cấu hình ghi đè (HP, tốc độ, sát thương…). Để None
        thì Titan dùng giá trị mặc định khai báo trong file gốc.

    Trả về
    ------
    (titan, ai) : tuple[Titan, TitanAI]
        * `titan` — instance của class Titan tương ứng.
        * `ai`    — bộ não đã được map đúng nhờ `make_ai_for()`
                    trong AI.py (RegularAI, ArmoredAI, ColossalAI, …).

    Ngoại lệ
    --------
    ValueError
        Khi `kind` không có trong bảng registry — kèm thông báo
        liệt kê các tên hợp lệ để dễ debug.

    Ví dụ
    -----
        from ImportAll import spawn_titan
        titan, ai = spawn_titan('armored', 300, 50, world)

        # Trong game loop:
        ai.update(dt)        # AI quyết định di chuyển/tấn công
        titan.update(dt)     # Titan thực thi
        titan.draw(screen)   # Render lên màn hình

    Ghi chú thiết kế
    ----------------
    Factory này KHÔNG tự gắn `Priority` — vì `Priority.make_priority_for()`
    đã được Titan tự gọi trong `__init__` (xem AttackStrategy/Priority).
    Nó CHỈ thêm bước lắp AI để teammate khỏi nhớ gọi `make_ai_for`.
    """
    cls = _TITAN_REGISTRY.get(kind.lower())
    if cls is None:
        valid = ', '.join(sorted(_TITAN_REGISTRY.keys()))
        raise ValueError(
            f"spawn_titan: không nhận diện được kind={kind!r}. "
            f"Tên hợp lệ: {valid}"
        )

    titan = cls(x, y, config) if config is not None else cls(x, y)
    ai    = make_ai_for(titan, world)
    return titan, ai


def list_available_titans() -> list:
    """
    Trả về danh sách tên gọi tắt đang được `spawn_titan` hỗ trợ.

    Dùng cho HUD debug, lệnh `/spawn` trong console, hoặc test:

        >>> from ImportAll import list_available_titans
        >>> list_available_titans()
        ['armored', 'beast', 'colossal', 'founding', 'kamikaze',
         'regular', 'soldier_hunter', 'tower_hunter', 'wolf']
    """
    return sorted(_TITAN_REGISTRY.keys())
