"""
dispatch_system.py — Hệ thống ĐIỀU QUÂN THÁM HIỂM (Resource Map, bản tích hợp).

Đây là bản KẾ THỪA Ý TƯỞNG từ prototype `resource_map.MapState` (commander_prototype,
code tham khảo của thành viên khác) rồi NÂNG CẤP + đấu nối vào hệ thống thật của
game chính. KHÔNG kế thừa class OOP của prototype (khác cây code, khác nền tảng).

Khác biệt so với prototype:
    - Kho lính = "kho trại" thật (TrainingCamp._idle) truyền vào qua interface
      `barracks` (get_idle / take_idle / return_idle) — dispatch TRỪ khỏi trại nên
      tháp không đụng được lính đang thám hiểm; rút về thì CỘNG lại trại.
    - Chọn số lính theo 3 loại (Warrior/Archer/Lancer), +/- BỘI 5.
    - Node bố trí quanh CĂN CỨ (tâm), mọi node cách tâm >= MIN_DISTANCE ("khoảng
      cách tới hạn"); node xa → tài nguyên QUÝ hơn.
    - Loot VÔ HẠN theo thời gian (không cạn), rate TĂNG theo số lính.
    - Rủi ro gặp Titan: xác suất ∝ số lính (đông→dễ) và khoảng cách (xa→dễ).
    - Thông báo gặp titan xử lý theo HÀNG ĐỢI FIFO; trong lúc xử lý 1 vụ thì MỌI
      đội khác PAUSE (không loot, không roll).
    - Chiến đấu = minigame "ping": qua đủ N lượt, TRƯỢT 1 lượt = THUA.

Thuần logic — KHÔNG import pygame. View (ui/resource_map_screen.py) chỉ đọc trạng
thái và gọi các method public ở đây. Loot khi rút về được đổ ra kho chính qua
callback `on_loot(ResourceBundle)` do game.py cung cấp (giữ core/systems sạch,
không import ngược game.py).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.game_state import ResourceBundle

# ---------------------------------------------------------------------------
# Hằng số cân bằng (tunables) — chỉnh thoải mái
# ---------------------------------------------------------------------------

# 3 loại lính, khớp TrainingCamp.SOLDIER_STATS / SOLDIER_TYPES.
SOLDIER_KINDS: tuple = ("Warrior", "Archer", "Lancer")
SOLDIER_STEP: int = 5                 # chọn số lính theo bội 5

# Khoảng cách (đơn vị logic; view ánh xạ ra pixel trên map.png).
MIN_DISTANCE: float = 350.0           # "khoảng cách tới hạn" — node gần nhất (đã tăng từ 150 -> 250 -> 350)
MAX_DISTANCE: float = 620.0           # dịch cùng lượng với MIN_DISTANCE để giữ nguyên độ rộng dải + tỉ lệ quý/hiếm

# Loot vô hạn: rate thực = zone.base_loot_rate * (tổng lính / SOLDIER_REF).
SOLDIER_REF: float = 15.0

# Xác suất gặp titan mỗi giây: λ = BASE_HAZARD * (lính/S_REF) * (distance/D_REF).
BASE_HAZARD: float = 0.03
HAZARD_S_REF: float = 15.0
HAZARD_D_REF: float = 400.0
ENCOUNTER_IMMUNE: float = 6.0         # miễn nhiễm sau khi thắng combat (giây)

# Độ khó combat: D = 0.5*(distance/D_MAX) + 0.5*(1 - lính/S_MAX). Xa & ít lính → khó.
DIFF_D_MAX: float = MAX_DISTANCE
DIFF_S_MAX: float = 60.0
ROUNDS_MIN, ROUNDS_MAX = 2, 6         # số lượt ping
ARC_MAX, ARC_MIN = 100.0, 30.0        # độ rộng vùng an toàn (độ) — khó → hẹp
SPD_MIN, SPD_MAX = 160.0, 340.0       # tốc kim (độ/giây) — khó → nhanh

# Thông báo gặp titan.
ALERT_TIME: float = 10.0              # hết giờ → auto rút bỏ đồ

# Item Cache ngẫu nhiên — 5 bậc độ hiếm (trọng số càng cao càng dễ ra):
#   Cao        : ore
#   Vừa        : acid_ore, wind_ore
#   Hơi hiếm   : ice_ore, water_ore, electric_ore
#   Hiếm       : anti_armor_ore, anti_stun
#   Siêu hiếm  : serum
ITEM_SPAWN_INTERVAL: float = 20.0
MAX_ITEMS: int = 3
ITEM_LIFETIME: float = 180.0          # 3 phút — node item chưa từng thám hiểm tự biến mất sau chừng này
ITEM_RESOURCE_WEIGHTS: dict = {
    "ore":             100,
    "acid_ore":         50,
    "wind_ore":         50,
    "ice_ore":          20,
    "water_ore":        20,
    "electric_ore":     20,
    "anti_armor_ore":    8,
    "anti_stun":         8,
    "serum":             2,
}
ITEM_RESOURCES: tuple = tuple(ITEM_RESOURCE_WEIGHTS.keys())

# Trạng thái party.
STATE_LOOTING = "looting"
STATE_ENCOUNTER = "encounter"
STATE_COMBAT = "combat"

# Banner kết quả tạm thời (vd "DEFEATED") — DispatchManager.last_result.
RESULT_BANNER_TIME: float = 3.0


def _clamp01(x: float) -> float:
    """Kẹp `x` vào [0.0, 1.0] — dùng để chuẩn hoá mọi tỉ lệ (độ khó, khoảng
    cách quy đổi...) trước khi đưa vào công thức tuyến tính."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def compute_difficulty(total_soldiers: int, distance: float) -> float:
    """Độ khó ∈ [0,1]: xa & ít lính → cao."""
    d_term = _clamp01(distance / DIFF_D_MAX)
    s_term = 1.0 - _clamp01(total_soldiers / DIFF_S_MAX)
    return _clamp01(0.5 * d_term + 0.5 * s_term)


def combat_params(difficulty: float) -> tuple:
    """(số_lượt, độ_rộng_vùng_an_toàn_độ, tốc_kim_độ/giây) theo thang độ khó."""
    d = _clamp01(difficulty)
    rounds = ROUNDS_MIN + int(round(d * (ROUNDS_MAX - ROUNDS_MIN)))
    arc = ARC_MAX - d * (ARC_MAX - ARC_MIN)
    speed = SPD_MIN + d * (SPD_MAX - SPD_MIN)
    return rounds, arc, speed


# ---------------------------------------------------------------------------
# Barracks — interface kho trại (dispatch đọc/ghi lính qua đây)
# ---------------------------------------------------------------------------

class DictBarracks:
    """Kho trại đơn giản dựa trên dict — dùng cho test/standalone.

    Trong game thật, game.py truyền một adapter bọc `TrainingCamp._idle`
    (cùng 3 method: get_idle / take_idle / return_idle)."""

    def __init__(self, counts: Optional[dict] = None) -> None:
        """Tạo kho trại độc lập (không liên kết `TrainingCamp` thật) — dùng
        cho test hoặc chạy DispatchManager standalone. `counts` (nếu có)
        seed số lính idle ban đầu theo loại, âm/thiếu key bị bỏ qua an toàn."""
        self._idle = {k: 0 for k in SOLDIER_KINDS}
        for k, v in (counts or {}).items():
            if k in self._idle:
                self._idle[k] = max(0, int(v))

    def get_idle(self, kind: str) -> int:
        """Số lính `kind` hiện có trong kho (0 nếu loại không tồn tại)."""
        return self._idle.get(kind, 0)

    def take_idle(self, kind: str, n: int) -> bool:
        """Rút `n` lính `kind` khỏi kho — False nếu `n<=0` hoặc không đủ
        (kho KHÔNG bị trừ trong trường hợp thất bại — atomic all-or-nothing)."""
        n = int(n)
        if n <= 0 or self._idle.get(kind, 0) < n:
            return False
        self._idle[kind] -= n
        return True

    def return_idle(self, kind: str, n: int) -> None:
        """Trả `n` lính `kind` về kho (rút thám hiểm về, hoặc rút lui)."""
        if kind in self._idle:
            self._idle[kind] += max(0, int(n))

    def total(self) -> int:
        """Tổng lính idle mọi loại trong kho."""
        return sum(self._idle.values())


# ---------------------------------------------------------------------------
# ExpeditionZone — node trên map thám hiểm
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class ExpeditionZone:
    """Một node quanh căn cứ. `eq=False` giữ so-sánh-the-identity (như Entity)
    để `zone in zones` / `party.zone is zone` luôn trỏ đúng object."""

    name: str
    angle: float            # radian — hướng từ tâm (base) ra node
    distance: float         # >= MIN_DISTANCE (biến `a`)
    resource_type: str      # field hợp lệ của ResourceBundle
    base_loot_rate: float   # đơn vị/giây ở mốc SOLDIER_REF lính
    kind: str = "field"     # "field" | "item"
    age: float = 0.0        # giây đã tồn tại — CHỈ tính khi node item chưa
                            # từng được gửi đội tới (xem `ever_dispatched`)
    ever_dispatched: bool = False   # đã từng có đội thám hiểm gửi tới node này chưa

    @property
    def is_item(self) -> bool:
        """True nếu node này là "Item Cache" tạm thời (spawn ngẫu nhiên bởi
        `DispatchManager._spawn_item()`, tự hết hạn theo `ITEM_LIFETIME` hoặc
        biến mất ngay sau khi đội thám hiểm rời đi — xem `DispatchManager._expire_items`),
        khác node tài nguyên CỐ ĐỊNH tạo bởi `seed_default_zones()` (`kind='field'`)."""
        return self.kind == "item"


# ---------------------------------------------------------------------------
# ExpeditionParty — một đội đang đi thám hiểm
# ---------------------------------------------------------------------------

class ExpeditionParty:
    """Một đội lính đã gửi tới `zone`, loot vô hạn theo thời gian."""

    def __init__(self, zone: ExpeditionZone, soldiers: dict) -> None:
        """Tạo 1 đội đã được gửi tới `zone` với `soldiers` (dict loại→số
        lượng, đã trừ khỏi kho trại bởi caller — `DispatchManager.dispatch()`).
        `distance` copy TỪ zone tại thời điểm tạo (không tham chiếu động —
        zone không đổi vị trí nên không thành vấn đề). Bắt đầu ở trạng thái
        `STATE_LOOTING`, chưa miễn nhiễm titan."""
        self.zone = zone
        self.distance = zone.distance
        self.soldiers = {k: int(soldiers.get(k, 0)) for k in SOLDIER_KINDS}
        self.state = STATE_LOOTING
        self.elapsed = 0.0
        self.immune_timer = 0.0                  # miễn nhiễm titan sau khi thắng
        self._loot_acc: dict = {}                # resource_type -> float tích lũy

    @property
    def total_soldiers(self) -> int:
        """Tổng lính trong đội (mọi loại cộng dồn) — dùng tính rate loot
        (`tick_loot`) và nguy cơ gặp titan (`compute_difficulty`)."""
        return sum(self.soldiers.values())

    @property
    def loot(self) -> ResourceBundle:
        """Loot tích lũy (làm tròn xuống int cho từng loại tài nguyên)."""
        return ResourceBundle(**{k: int(v) for k, v in self._loot_acc.items()})

    def loot_amount(self) -> int:
        """Tổng số đơn vị đã loot (cho hiển thị nhanh ở tab tiến độ)."""
        return int(sum(self._loot_acc.values()))

    def tick_loot(self, dt: float) -> None:
        """Tích loot theo rate*số-lính; giảm miễn nhiễm. Gọi khi KHÔNG bị pause."""
        self.elapsed += dt
        if self.immune_timer > 0.0:
            self.immune_timer = max(0.0, self.immune_timer - dt)
        if self.total_soldiers <= 0:
            return
        factor = self.total_soldiers / SOLDIER_REF
        gained = self.zone.base_loot_rate * factor * dt
        rt = self.zone.resource_type
        self._loot_acc[rt] = self._loot_acc.get(rt, 0.0) + gained


# ---------------------------------------------------------------------------
# TitanEncounter — một vụ chạm titan (chờ trong hàng đợi)
# ---------------------------------------------------------------------------

class TitanEncounter:
    """Vụ gặp titan của 1 party. `timer` đếm ngược khi đang ở đầu hàng đợi."""

    def __init__(self, party: ExpeditionParty) -> None:
        """Tạo vụ gặp titan cho `party` — độ khó CHỐT NGAY LÚC TẠO (dùng
        `total_soldiers`/`distance` tại thời điểm gặp, không tính lại nếu
        đội thay đổi sau đó — nhưng đội không thể thay đổi quân số giữa lúc
        đang trong hàng đợi). `timer` đếm ngược `ALERT_TIME` giây — hết giờ
        mà người chơi chưa xử lý → tự động rút lui, bỏ đồ (xem `_update_front`)."""
        self.party = party
        self.timer = ALERT_TIME
        self.difficulty = compute_difficulty(party.total_soldiers, party.distance)


# ---------------------------------------------------------------------------
# PingCombat — minigame kim quay + vùng an toàn
# ---------------------------------------------------------------------------

class PingCombat:
    """Kim quay quanh vòng tròn; SPACE lúc kim trong vùng an toàn = qua 1 lượt.
    Qua đủ `rounds_total` lượt = THẮNG; trượt 1 lượt = THUA ngay."""

    def __init__(self, difficulty: float,
                 rng: Optional[random.Random] = None) -> None:
        """Khởi tạo minigame với `difficulty` ∈ [0,1] chốt sẵn (từ
        `TitanEncounter.difficulty`) — quy đổi ra 3 tham số cụ thể qua
        `combat_params()`: số lượt cần qua, độ rộng vùng an toàn, tốc độ
        kim (khó hơn → nhiều lượt hơn, vùng an toàn hẹp hơn, kim quay
        nhanh hơn). `rng` cho phép TIÊM Random có seed (test xác định);
        mặc định tạo Random mới mỗi lần (không seed)."""
        self._rng = rng if rng is not None else random.Random()
        self.difficulty = difficulty
        self.rounds_total, self.safe_arc, self.speed = combat_params(difficulty)
        self.rounds_done = 0
        self.angle = 0.0                 # vị trí kim (độ, 0..360)
        self.safe_start = 0.0            # mép đầu vùng an toàn (độ)
        self.state = "active"            # active | won | lost
        self._new_safe()

    def _new_safe(self) -> None:
        """Vùng an toàn mới ngẫu nhiên; đặt kim ở phía đối diện cho công bằng."""
        self.safe_start = self._rng.uniform(0.0, 360.0)
        self.angle = (self.safe_start + 180.0) % 360.0

    def _in_safe(self) -> bool:
        """Kim có đang nằm trong vùng an toàn không — đo khoảng cách góc
        THEO CHIỀU DƯƠNG từ `safe_start` (MOD 360° để luôn dương), vùng an
        toàn kéo dài `safe_arc` độ kể từ đó."""
        d = (self.angle - self.safe_start) % 360.0
        return d <= self.safe_arc

    def update(self, dt: float) -> None:
        """Quay kim theo `speed` độ/giây (MOD 360°) — chỉ khi còn `active`,
        đã thắng/thua thì kim đứng yên."""
        if self.state != "active":
            return
        self.angle = (self.angle + self.speed * dt) % 360.0

    def press(self) -> str:
        """Người chơi bấm SPACE. Trả về trạng thái mới (active/won/lost)."""
        if self.state != "active":
            return self.state
        if self._in_safe():
            self.rounds_done += 1
            if self.rounds_done >= self.rounds_total:
                self.state = "won"
            else:
                self._new_safe()
        else:
            self.state = "lost"
        return self.state


# ---------------------------------------------------------------------------
# DispatchManager — Singleton điều phối toàn bộ
# ---------------------------------------------------------------------------

class DispatchManager:
    """Trung tâm điều quân thám hiểm. Giữ zones, parties, hàng đợi encounter và
    trận combat đang diễn ra. View chỉ đọc + gọi các method public."""

    _instance: "Optional[DispatchManager]" = None

    def __init__(self, barracks: Optional[object] = None,
                 on_loot: Optional[Callable[[ResourceBundle], None]] = None,
                 on_soldiers_lost: Optional[Callable[[dict], None]] = None,
                 rng: Optional[random.Random] = None) -> None:
        """Tạo manager (thường KHÔNG gọi trực tiếp — dùng `get_instance()`).

        `barracks` — adapter kho lính, mặc định `DictBarracks()` chuẩn lập
        (game thật truyền adapter bọc `TrainingCamp._idle` qua `configure()`
        sau khi Singleton đã tồn tại — game.py không có kho trại lúc module
        này khởi tạo lần đầu). `on_loot`/`on_soldiers_lost` — callback GIỮ
        module này THUẦN LOGIC, không import ngược `game.py`/`ResourceManager`
        trực tiếp: game.py cung cấp callback để đổ loot vào kho thật / xử lý
        lính chết (hoàn vũ khí Forge...). `rng` — Random tiêm được (test)."""
        self.barracks = barracks if barracks is not None else DictBarracks()
        self._on_loot = on_loot
        self._on_soldiers_lost = on_soldiers_lost
        self._rng = rng if rng is not None else random.Random()
        self.zones: list = []
        self.parties: list = []
        self.encounter_queue: list = []      # front = [0] đang xử lý
        self.active_combat: Optional[PingCombat] = None
        self._item_timer = 0.0
        self._item_counter = 0
        # Banner kết quả tạm thời (thua trận) — view đọc để hiện "DEFEATED".
        self.last_result: Optional[dict] = None

    # --- Singleton ------------------------------------------------------
    @classmethod
    def get_instance(cls) -> "DispatchManager":
        """Trả Singleton, tạo mới lần đầu gọi (với `DictBarracks()` tạm —
        game.py PHẢI gọi `configure(barracks=...)` sau đó để gắn kho trại
        thật, nếu không dispatch sẽ thao tác trên kho giả rỗng)."""
        if cls._instance is None:
            cls._instance = DispatchManager()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Xoá Singleton — gọi khi khởi động lại game (New Game/Continue)
        để không mang zones/parties/encounter của phiên cũ sang."""
        cls._instance = None

    def total_dispatched_soldiers(self) -> dict:
        """Tổng lính ĐANG thám hiểm (mọi party còn hoạt động), theo loại.

        Lính thám hiểm đã bị trừ khỏi `_idle` NGAY LÚC điều đi (xem
        `TrainingCamp.reserve_expedition`) nên vẫn "vắng mặt" khỏi trại suốt
        chuyến đi — nhưng vẫn phải TÍNH VÀO tổng upkeep lương thực (vẫn đang
        ăn, chỉ không có mặt tại trại), nếu không thì lúc họ VỀ (return_expedition
        cộng lại vào _idle) tổng cầu lương thực tăng đột ngột mà không ai kiểm
        tra lại deficit → lính có thể vừa được giải "đói" (try_recover_soldiers,
        tính thiếu vì bỏ sót phần đang đi) rồi ngay khi họ về lại rơi vào thiếu
        lần nữa — nhấp nháy trạng thái. Tính LUÔN cả phần đang đi ở đây để
        _total_soldier_upkeep() (building.py) cộng vào, tránh kẽ hở đó."""
        totals: dict = {k: 0 for k in SOLDIER_KINDS}
        for party in self.parties:
            for k, n in party.soldiers.items():
                if k in totals:
                    totals[k] += int(n)
        return totals

    def configure(self, *, barracks: Optional[object] = None,
                  on_loot: Optional[Callable[[ResourceBundle], None]] = None,
                  on_soldiers_lost: Optional[Callable[[dict], None]] = None,
                  rng: Optional[random.Random] = None) -> None:
        """Cấu hình runtime (game.py gọi khi vào Sảnh)."""
        if barracks is not None:
            self.barracks = barracks
        if on_loot is not None:
            self._on_loot = on_loot
        if on_soldiers_lost is not None:
            self._on_soldiers_lost = on_soldiers_lost
        if rng is not None:
            self._rng = rng

    # --- Setup ----------------------------------------------------------
    def seed_default_zones(self) -> None:
        """6 node cố định quanh vành đai, CHỈ gồm gỗ/đá rải rác đều 8 hướng
        (tài nguyên cơ bản, luôn sẵn có ngay từ đầu) — mọi tài nguyên khác
        (quặng, item đặc biệt) chỉ xuất hiện qua Item Cache ngẫu nhiên
        (`_spawn_item`), không có mặt trong bộ node cố định này. Mọi node
        đều cách tâm >= MIN_DISTANCE."""
        specs = [
            # (name, angle_deg, distance, resource_type, base_loot_rate)
            ("Near Forest",   20.0, 370.0, "wood",  6.0),
            ("Stone Quarry",  80.0, 390.0, "stone", 5.0),
            ("Old Grove",    140.0, 420.0, "wood",  5.5),
            ("Rock Outcrop", 200.0, 450.0, "stone", 5.0),
            ("Timber Camp",  260.0, 480.0, "wood",  5.0),
            ("Granite Ridge",320.0, 510.0, "stone", 4.5),
        ]
        self.zones = [
            ExpeditionZone(n, math.radians(a), d, rt, br)
            for (n, a, d, rt, br) in specs
        ]

    # --- Truy vấn cho UI ------------------------------------------------
    def available(self, kind: str) -> int:
        """Số lính `kind` sẵn sàng điều đi thám hiểm — uỷ quyền thẳng cho
        `barracks.get_idle()` (view gọi để hiển thị thanh chọn quân số)."""
        return self.barracks.get_idle(kind)

    def expedition_counts(self) -> dict:
        """Tổng lính ĐANG thám hiểm theo loại (mục thống kê 'đang thám hiểm')."""
        out = {k: 0 for k in SOLDIER_KINDS}
        for p in self.parties:
            for k in SOLDIER_KINDS:
                out[k] += p.soldiers[k]
        return out

    @property
    def current_encounter(self) -> Optional[TitanEncounter]:
        """Vụ gặp titan ĐANG XỬ LÝ (đầu hàng đợi FIFO) — None nếu hàng đợi
        rỗng. View (overlay thông báo) đọc property này để hiển thị."""
        return self.encounter_queue[0] if self.encounter_queue else None

    @property
    def is_paused(self) -> bool:
        """True khi đang xử lý 1 encounter → mọi đội khác dừng loot/roll."""
        return bool(self.encounter_queue)

    # --- Dispatch -------------------------------------------------------
    def can_dispatch(self, soldiers: dict) -> bool:
        """Hợp lệ khi: mỗi loại là bội 5, không vượt kho trại, tổng > 0."""
        total = 0
        for k in SOLDIER_KINDS:
            n = int(soldiers.get(k, 0))
            if n < 0 or n % SOLDIER_STEP != 0:
                return False
            if n > self.barracks.get_idle(k):
                return False
            total += n
        return total > 0

    def dispatch(self, zone: ExpeditionZone,
                 soldiers: dict) -> Optional[ExpeditionParty]:
        """Gửi 1 đội tới `zone`. Trừ lính khỏi kho trại. None nếu không hợp lệ.

        Nếu `zone` là Item Cache (`is_item`), đánh dấu `ever_dispatched=True`
        NGAY LÚC GỬI — mốc này khiến node bị `_expire_items()` xoá VĨNH VIỄN
        ngay khi đội cuối cùng rời khỏi nó (thắng/thua/rút lui đều tính),
        bất kể tuổi node đã bao lâu."""
        if zone not in self.zones:
            return None
        if not self.can_dispatch(soldiers):
            return None
        for k in SOLDIER_KINDS:
            n = int(soldiers.get(k, 0))
            if n > 0:
                self.barracks.take_idle(k, n)
        if zone.is_item:
            zone.ever_dispatched = True
        party = ExpeditionParty(zone, soldiers)
        self.parties.append(party)
        return party

    # --- Rút lui --------------------------------------------------------
    def retreat(self, party: ExpeditionParty) -> None:
        """Rút CHỦ ĐỘNG (từ tab tiến độ) — GIỮ đồ: đổ loot vào kho, lính về trại.
        Chỉ áp dụng cho đội đang loot (đội đang gặp titan xử lý qua overlay)."""
        if party not in self.parties or party.state != STATE_LOOTING:
            return
        self._deposit_loot(party)
        self._return_soldiers(party)
        self._remove_party(party)

    def retreat_all(self) -> None:
        """Rút HẾT (thoát game / vào pha chiến đấu) — giữ đồ, lính về trại.
        Dọn luôn mọi encounter/combat đang treo."""
        for p in list(self.parties):
            self._deposit_loot(p)
            self._return_soldiers(p)
        self.parties.clear()
        self.encounter_queue.clear()
        self.active_combat = None

    # --- Xử lý gặp titan (overlay gọi) ---------------------------------
    def resolve_retreat(self) -> None:
        """Gặp titan → chọn RÚT: bỏ đồ (loot=0), lính về trại an toàn."""
        enc = self.current_encounter
        if enc is None or self.active_combat is not None:
            return
        self._return_soldiers(enc.party)      # KHÔNG deposit loot
        self._remove_party(enc.party)
        self._pop_front()

    def resolve_fight(self) -> Optional[PingCombat]:
        """Gặp titan → chọn CHIẾN ĐẤU: mở minigame ping."""
        enc = self.current_encounter
        if enc is None or self.active_combat is not None:
            return None
        self.active_combat = PingCombat(enc.difficulty, rng=self._rng)
        enc.party.state = STATE_COMBAT
        return self.active_combat

    def combat_press(self) -> Optional[str]:
        """SPACE trong minigame. Thắng → loot tiếp (giữ đồ). Thua → mất lính+đồ."""
        if self.active_combat is None:
            return None
        st = self.active_combat.press()
        if st == "won":
            enc = self._pop_front()
            if enc is not None:
                enc.party.state = STATE_LOOTING
                enc.party.immune_timer = ENCOUNTER_IMMUNE
            self.active_combat = None
        elif st == "lost":
            enc = self._pop_front()
            if enc is not None:
                p = enc.party
                self.last_result = {
                    "kind": "defeat",
                    "zone_name": p.zone.name,
                    "resource_type": p.zone.resource_type,
                    "lost_loot": p.loot_amount(),
                    "lost_soldiers": dict(p.soldiers),
                    "timer": RESULT_BANNER_TIME,
                }
                # Lính thua trận thám hiểm coi như CHẾT (khác rút lui) — vũ khí
                # đã trang bị cho họ phải hoàn lại Forge, cùng cơ chế với lính
                # chết trong combat thường (game.py lo phần thật qua callback,
                # module này giữ nguyên tắc thuần logic, không import ngược).
                if self._on_soldiers_lost is not None:
                    self._on_soldiers_lost(dict(p.soldiers))
                self._remove_party(p)   # mất lính + mất đồ
            self.active_combat = None
        return st

    def dismiss_result(self) -> None:
        """Đóng sớm banner kết quả (người chơi click/bấm phím để bỏ qua)."""
        self.last_result = None

    # --- Vòng cập nhật --------------------------------------------------
    def update(self, dt: float) -> None:
        """Gọi mỗi frame (chạy ngầm ở Sảnh kể cả khi đóng tab)."""
        if self.last_result is not None:
            self.last_result["timer"] -= dt
            if self.last_result["timer"] <= 0.0:
                self.last_result = None
        if self.encounter_queue:
            self._update_front(dt)          # đang xử lý encounter → pause phần còn lại
            return
        for party in list(self.parties):
            party.tick_loot(dt)
        self._roll_encounters(dt)
        self._tick_items(dt)

    def _update_front(self, dt: float) -> None:
        """Xử lý vụ gặp titan Ở ĐẦU hàng đợi (chỉ 1 vụ được xử lý tại 1
        thời điểm — mọi party khác PAUSE hoàn toàn trong lúc này, xem
        `update()` gọi hàm này thay vì `tick_loot`/`_roll_encounters`).

        Đang trong combat (`active_combat` khác None) → chỉ quay kim
        (`update`), thắng/thua do người chơi bấm SPACE xử lý ở `combat_press`.
        Chưa vào combat → đếm ngược `timer`; hết giờ (người chơi không phản
        hồi) → TỰ ĐỘNG rút lui — trả lính về trại, BỎ ĐỒ (không deposit
        loot, khác `resolve_retreat` chủ động cũng bỏ đồ tương tự nhưng do
        người chơi chọn), rồi bỏ vụ này khỏi hàng đợi."""
        enc = self.encounter_queue[0]
        if self.active_combat is not None:
            self.active_combat.update(dt)   # kim quay; thắng/thua do combat_press
            return
        enc.timer -= dt
        if enc.timer <= 0.0:                 # hết 10s → auto rút bỏ đồ
            self._return_soldiers(enc.party)
            self._remove_party(enc.party)
            self._pop_front()

    def _roll_encounters(self, dt: float) -> None:
        """Mỗi đội roll gặp titan; đội trúng đẩy vào hàng đợi (FIFO)."""
        for party in list(self.parties):
            if party.immune_timer > 0.0:
                continue
            lam = (BASE_HAZARD
                   * (party.total_soldiers / HAZARD_S_REF)
                   * (party.distance / HAZARD_D_REF))
            if self._rng.random() < lam * dt:
                party.state = STATE_ENCOUNTER
                self.encounter_queue.append(TitanEncounter(party))

    def _zone_has_party(self, zone: ExpeditionZone) -> bool:
        """True nếu đang có ÍT NHẤT 1 đội (party) đang thám hiểm tại `zone`."""
        return any(p.zone is zone for p in self.parties)

    def _expire_items(self, dt: float) -> None:
        """Dọn Item Cache theo 2 luật, xét TỪNG node MỖI FRAME:

        1. Node ĐANG có đội thám hiểm (`_zone_has_party`) → giữ nguyên, KHÔNG
           tính tuổi, KHÔNG xoá — node vẫn giữ NGUYÊN VẸN mọi chức năng (đội
           vẫn loot/gặp titan bình thường) dù đã quá `ITEM_LIFETIME`.
        2. Node KHÔNG có đội:
           a. `ever_dispatched=True` (đã TỪNG được gửi đội, giờ đội cuối cùng
              vừa rời đi — thắng/thua/rút lui đều tính) → xoá NGAY LẬP TỨC,
              bất kể tuổi node là bao nhiêu.
           b. `ever_dispatched=False` (chưa từng được dùng) → cộng dồn `age`;
              đạt `ITEM_LIFETIME` (3 phút) → xoá do hết hạn tự nhiên.
        """
        for z in list(self.zones):
            if not z.is_item:
                continue
            if self._zone_has_party(z):
                continue
            if z.ever_dispatched:
                self.zones.remove(z)
                continue
            z.age += dt
            if z.age >= ITEM_LIFETIME:
                self.zones.remove(z)

    def _tick_items(self, dt: float) -> None:
        """Dọn Item Cache hết hạn (`_expire_items`), rồi cứ mỗi
        `ITEM_SPAWN_INTERVAL` giây, nếu số Item Cache ĐANG TÍNH VÀO giới hạn
        CHƯA đạt `MAX_ITEMS`, spawn thêm 1 node mới (`_spawn_item`).

        Node đang có đội thám hiểm (`_zone_has_party`) KHÔNG được tính vào
        giới hạn `MAX_ITEMS` — "trừ sẵn" khỏi tổng ngay khi có đội tới, dù
        node đó vẫn tồn tại và hoạt động bình thường. Nhờ vậy 1 node đang
        được khai thác không chiếm mất suất, luôn có thể spawn node mới thay thế.
        """
        self._item_timer += dt
        self._expire_items(dt)
        if self._item_timer >= ITEM_SPAWN_INTERVAL:
            self._item_timer -= ITEM_SPAWN_INTERVAL
            _countable = sum(1 for z in self.zones
                             if z.is_item and not self._zone_has_party(z))
            if _countable < MAX_ITEMS:
                self._spawn_item()

    def _spawn_item(self) -> ExpeditionZone:
        """Tạo 1 node "Item Cache" tại vị trí NGẪU NHIÊN (góc đều, khoảng
        cách trong dải `[MIN_DISTANCE, MAX_DISTANCE]`), loại tài nguyên rút
        thăm CÓ TRỌNG SỐ theo `ITEM_RESOURCE_WEIGHTS` (5 bậc độ hiếm — ore
        dễ ra nhất, serum khó ra nhất; khác `seed_default_zones` — node cố
        định theo tài nguyên/khoảng cách THIẾT KẾ, không rút thăm), rate
        loot ngẫu nhiên 1.5-3.0. Thêm vào `zones`, trả về node vừa tạo."""
        self._item_counter += 1
        ang = self._rng.uniform(0.0, 2 * math.pi)
        dist = self._rng.uniform(MIN_DISTANCE, MAX_DISTANCE)
        rt = self._rng.choices(
            list(ITEM_RESOURCE_WEIGHTS.keys()),
            weights=list(ITEM_RESOURCE_WEIGHTS.values()), k=1)[0]
        rate = self._rng.uniform(1.5, 3.0)
        z = ExpeditionZone(f"Item Cache {self._item_counter}", ang, dist, rt,
                           rate, kind="item")
        self.zones.append(z)
        return z

    # --- Nội bộ ---------------------------------------------------------
    def _deposit_loot(self, party: ExpeditionParty) -> None:
        """Đổ toàn bộ loot tích luỹ của `party` vào kho chính, qua callback
        `_on_loot` (nếu game.py đã cấu hình) — module này KHÔNG tự cộng vào
        ResourceManager (giữ nguyên tắc thuần logic, không import ngược)."""
        if self._on_loot is not None:
            self._on_loot(party.loot)

    def _return_soldiers(self, party: ExpeditionParty) -> None:
        """Trả TOÀN BỘ lính của `party` về kho trại (`barracks.return_idle`
        từng loại) — gọi khi rút lui/thắng combat, KHÔNG gọi khi thua (lính
        thua trận "chết", xem `combat_press` nhánh 'lost')."""
        for k in SOLDIER_KINDS:
            if party.soldiers[k] > 0:
                self.barracks.return_idle(k, party.soldiers[k])

    def _remove_party(self, party: ExpeditionParty) -> None:
        """Gỡ `party` khỏi `parties` — bọc try/except vì `party` có thể đã
        bị gỡ trước đó (gọi từ nhiều nhánh xử lý khác nhau, an toàn double-remove)."""
        try:
            self.parties.remove(party)
        except ValueError:
            pass

    def _pop_front(self) -> Optional[TitanEncounter]:
        """Lấy VÀ GỠ vụ gặp titan đầu hàng đợi FIFO — None nếu hàng đợi rỗng.
        Sau khi gỡ, vụ KẾ TIẾP (nếu có) tự động trở thành `current_encounter`."""
        if self.encounter_queue:
            return self.encounter_queue.pop(0)
        return None
