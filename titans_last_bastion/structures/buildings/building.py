# structures/buildings/building.py
import math
import os

from core.entity import Entity
from core.interfaces import IAttackable, IUpgradable, IProducible
from core.game_state import ResourceBundle
from core.event_bus import GameEventBus
from config import balance

try:
    import pygame
    from systems.sound_system import SoundManager
    _PYGAME_OK = True
except ImportError:
    _PYGAME_OK = False

_HERE = os.path.dirname(os.path.abspath(__file__))
_BLDG_SCALE = 1.5   # visual scale multiplier for demo

# Cache các frame đã được pre-scale: (class_name, level, frame_idx) -> Surface
# Giúp tránh gọi transform.scale mỗi frame (nặng CPU)
_scaled_frame_cache: dict = {}


# ═══════════════════════════════════════════════════════
#  FOOD = NĂNG SUẤT/S (THÊM MỚI)
# ═══════════════════════════════════════════════════════
# Food KHÔNG còn là kho tiêu được — chỉ là 1 con số food/s = tổng năng suất
# của mọi Farm còn sống, dùng để giới hạn huấn luyện. Tách ra hàm module-level
# (thuộc "hệ thống kho đồ") thay vì method trên TrainingCamp, để LUÔN gọi được
# kể cả khi chưa có TrainingCamp nào — sửa bug cũ: UI hiển thị luôn rơi về
# fallback cứng 50 vì lúc mới vào game chưa có TrainingCamp để gọi method.

def total_food_production_rate() -> float:
    """Tổng food/s của mọi Farm còn sống. Trả 0.0 nếu không có Farm nào
    (KHÔNG còn fallback cứng 50 như bản cũ)."""
    from systems.world_query import WorldQuery
    total = 0.0
    for b in WorldQuery.get_all_buildings():
        if type(b).__name__ == 'Farm' and getattr(b, 'is_alive', False):
            total += getattr(b, 'PRODUCTION_RATE', 0) / max(getattr(b, 'CYCLE_TIME', 1), 0.001)
    return total


# ═══════════════════════════════════════════════════════
#  UPKEEP & WEAPON_USED CỦA LÍNH — SUY RA TỪ SỐ LÍNH
# ═══════════════════════════════════════════════════════
# Mô hình: chỉ có 2 ranh giới làm đổi số — "phục vụ ↔ thiếu" và "sinh ↔ tử".
#
#   Tập ĐANG PHỤC VỤ = idle (mọi trại) + trong tháp + trên bản đồ + thám hiểm.
#       → tất cả đều ĂN (upkeep) và GIỮ VŨ KHÍ (weapon_used).
#   Tập THIẾU (_hungry / _disarmed_soldiers) = bị đình chỉ → tiêu thụ 0.
#       (2 dict chỉ là NHÃN lý do để hiển thị; logic coi như MỘT pool.)
#
# Bất biến: upkeep <= food_production  VÀ  weapon_used <= weapon_total.
#
# QUYẾT ĐỊNH THIẾT KẾ QUAN TRỌNG: upkeep và phần soldier của `weapon_used`
# đều được TÍNH SUY RA (derive) từ số lính đang phục vụ, KHÔNG phải bộ đếm
# cộng/trừ thủ công. Nhờ vậy mọi sự kiện (lính chết trong combat, chết khi
# thám hiểm, đẩy vào thiếu, kéo về idle...) tự động đúng, không cần hook ở
# từng chỗ và không thể rò rỉ. Bản cũ dùng bộ đếm `Forge._weapon_used` chỉ
# tăng khi train mà không bao giờ giảm khi lính chết trong combat
# (`on_soldier_died()` là code chết) → used chỉ phình lên qua từng trận.

SOLDIER_KINDS_ORDER = ('Warrior', 'Archer', 'Lancer')


def _all_training_camps() -> list:
    """Mọi TrainingCamp còn sống trên map — nguồn dữ liệu cho "sổ lính dùng
    chung" (mọi thuật toán reconcile bên dưới coi TẤT CẢ trại như 1 pool
    duy nhất, không phân biệt trại nào chứa lính nào)."""
    from systems.world_query import WorldQuery
    return [b for b in WorldQuery.get_all_buildings()
            if type(b).__name__ == 'TrainingCamp']


def _all_live_towers() -> list:
    """Mọi tháp còn sống — lấy qua WorldQuery nên bao gồm CẢ tháp gắn tường
    lẫn tháp đặt đất (2 loại này nằm ở 2 list khác nhau trong game.py, quét
    theo list dễ bỏ sót một loại)."""
    from systems.world_query import WorldQuery
    return [e for e in WorldQuery.all()
            if getattr(e, 'ENTITY_TYPE', '') == 'tower' and getattr(e, 'is_alive', False)]


def count_active_soldiers() -> dict:
    """Số lính ĐANG PHỤC VỤ theo loại (ăn + giữ vũ khí).

    Gồm 6 nguồn, cố ý không đếm trùng:
      1. idle ở mọi TrainingCamp
      2. squad trong tháp chưa spawn ra map (`_garrison_sizes`)
      3. squad đã rút về tháp, entity đã gỡ khỏi map (`_reserve_squads`)
      4. entity lính còn sống trên map (gồm squad đang deploy + lính mồ côi
         khi tháp bị phá) — `_deployed_squads` KHÔNG đếm riêng vì thành viên
         của nó chính là các entity này.
      5. lính đang đi thám hiểm (đã bị trừ khỏi `_idle` lúc điều đi)
      6. lính đang trong HÀNG ĐỢI huấn luyện — `start_training()` đã gọi
         `equip()` giữ chỗ vũ khí cho họ. Không đếm ở đây thì
         `sync_soldier_weapon_used()` sẽ ghi đè và XOÁ MẤT phần giữ chỗ đó
         (reconcile chạy giữa lúc đang train → train vượt giới hạn vũ khí).
    """
    from systems.world_query import WorldQuery
    counts = {t: 0 for t in SOLDIER_KINDS_ORDER}

    for camp in _all_training_camps():
        for t in counts:
            counts[t] += max(0, camp._idle.get(t, 0))
        for entry in (getattr(camp, '_queue', []) or []):
            st = entry.get('type') if isinstance(entry, dict) else None
            if st in counts:
                counts[st] += 1

    for tw in _all_live_towers():
        for t, sizes in (getattr(tw, '_garrison_sizes', {}) or {}).items():
            if t in counts:
                counts[t] += sum(int(s) for s in sizes)
        for sq in (getattr(tw, '_reserve_squads', []) or []):
            st = getattr(sq, 'soldier_type', None)
            if st in counts:
                counts[st] += sum(1 for m in sq.members if getattr(m, 'is_alive', False))

    for e in WorldQuery.all():
        if getattr(e, 'ENTITY_TYPE', '') == 'soldier' and getattr(e, 'is_alive', False):
            st = getattr(e, 'NAME', None)
            if st in counts:
                counts[st] += 1

    try:
        from systems.dispatch_system import DispatchManager
        for t, n in DispatchManager.get_instance().total_dispatched_soldiers().items():
            if t in counts:
                counts[t] += int(n)
    except Exception:
        pass

    return counts


def total_active_upkeep() -> float:
    """Tổng food/s mà lính đang phục vụ tiêu thụ. Lính "thiếu" KHÔNG tính."""
    counts = count_active_soldiers()
    return sum(counts[t] * TrainingCamp.SOLDIER_STATS[t]['upkeep']
               for t in SOLDIER_KINDS_ORDER)


def sync_soldier_weapon_used() -> None:
    """Ghi lại phần SOLDIER của `Forge._weapon_used` từ số lính đang phục vụ.

    Chỉ chạm các field của lính (`soldier_weapon` + `sword`/`arrow`/`spear`) —
    field của tháp (`tower_weapon`, `basic_projectlie`...) và bẫy (`trap`...)
    do hệ thống riêng của chúng quản lý, KHÔNG đụng vào."""
    counts = count_active_soldiers()
    wu = Forge._weapon_used
    general_total = 0
    specific_totals: dict = {}
    for t in SOLDIER_KINDS_ORDER:
        gen, spec, amt = TrainingCamp.WEAPON_COST[t]
        general_total += counts[t] * amt
        specific_totals[spec] = specific_totals.get(spec, 0) + counts[t] * amt
    setattr(wu, 'soldier_weapon', general_total)
    for spec, val in specific_totals.items():
        setattr(wu, spec, val)


# ── Sổ lính dùng chung trên MỌI TrainingCamp ──────────────────────────────
# Các trại được coi như 1 sổ chung (rút/thêm lính ở trại nào cũng được).

def _ensure_pools(camp) -> None:
    """Đảm bảo `camp._hungry`/`camp._disarmed_soldiers` tồn tại (dict rỗng
    theo mọi loại lính) — TrainingCamp tạo sẵn 2 dict này trong `__init__`,
    nhưng hàm này là lưới an toàn cho instance cũ (vd load save trước khi
    2 field này tồn tại) hoặc test tạo camp thủ công không qua `__init__`."""
    if not hasattr(camp, '_hungry'):
        camp._hungry = {t: 0 for t in camp.SOLDIER_STATS}
    if not hasattr(camp, '_disarmed_soldiers'):
        camp._disarmed_soldiers = {t: 0 for t in camp.SOLDIER_STATS}


def _idle_count(camps: list, t: str) -> int:
    """Tổng lính loại `t` đang idle (đã train, sẵn sàng điều động) CỘNG DỒN
    qua mọi trại trong `camps` — vì sổ lính coi mọi trại là 1 pool chung."""
    return sum(max(0, c._idle.get(t, 0)) for c in camps)


def _take_idle(camps: list, t: str):
    """Rút 1 lính idle loại `t` khỏi trại ĐẦU TIÊN còn lính (thứ tự `camps`
    quyết định, không ưu tiên gì đặc biệt) — trừ `_idle` của trại đó, trả
    về chính trại (caller dùng để biết thêm lính vào pool khác của TRẠI ĐÓ,
    vd `_hungry`/`_disarmed_soldiers`, giữ lính "ở lại" đúng trại vật lý).
    Không còn lính idle loại này ở bất kỳ trại nào → None."""
    for c in camps:
        if c._idle.get(t, 0) > 0:
            c._idle[t] -= 1
            return c
    return None


def _deficient_count(camps: list, t: str) -> int:
    """Tổng lính loại `t` đang "thiếu" (đói HOẶC thiếu vũ khí — cộng dồn cả
    2 pool `_hungry`+`_disarmed_soldiers`) qua mọi trại. Đây là số lính bị
    ĐÌNH CHỈ (không ăn, không giữ vũ khí, không tham chiến) chờ `_pull_back`
    kéo về idle khi có dư tài nguyên."""
    total = 0
    for c in camps:
        _ensure_pools(c)
        total += max(0, c._hungry.get(t, 0)) + max(0, c._disarmed_soldiers.get(t, 0))
    return total


def _take_deficient(camps: list, t: str):
    """Rút 1 lính khỏi pool thiếu — ưu tiên `_hungry` trước, rồi `_disarmed`.
    (2 pool chỉ khác nhãn hiển thị, điều kiện quay lại giống hệt nhau.)"""
    for c in camps:
        _ensure_pools(c)
        if c._hungry.get(t, 0) > 0:
            c._hungry[t] -= 1
            return c
    for c in camps:
        if c._disarmed_soldiers.get(t, 0) > 0:
            c._disarmed_soldiers[t] -= 1
            return c
    return None


def _unit_cost(t: str, dim: str) -> float:
    """Chi phí CỦA 1 LÍNH loại `t` theo chiều `dim` — 'food' → upkeep/s
    (từ `SOLDIER_STATS`), bất kỳ giá trị khác (thực tế chỉ 'weapon') →
    lượng vũ khí chung tiêu tốn (từ `WEAPON_COST[t][2]`, phần tử thứ 3 =
    `amount`). Dùng bởi `_push_deficit`/`_pull_back` để quy đổi "bao nhiêu
    lính cần đẩy/kéo" thành "bao nhiêu tài nguyên tương ứng"."""
    if dim == 'food':
        return float(TrainingCamp.SOLDIER_STATS[t]['upkeep'])
    return float(TrainingCamp.WEAPON_COST[t][2])


def _push_deficit(camps: list, x: float, dim: str) -> None:
    """THUẬT TOÁN A — đẩy lính idle vào "thiếu" cho tới khi bù đủ `x`.

    Chia đều `x` cho 3 loại làm target. Mỗi loại bỏ lính TỪNG CON, dừng ngay
    khi lượng giải phóng >= target (cho phép VỪA VƯỢT — bỏ thừa thì an toàn,
    chỉ phí lính). Loại nào hết lính idle mà chưa chạm target → phần thiếu
    CHIA ĐỀU cho các loại còn lính idle, lặp lại.

    Chỉ rút từ `_idle` — không đụng lính đang thám hiểm hay đang ở tháp.
    """
    order = list(SOLDIER_KINDS_ORDER)
    targets = {t: x / 3.0 for t in order}
    released = {t: 0.0 for t in order}
    guard = 0
    while guard < 500:
        guard += 1
        for t in order:
            while released[t] + 1e-9 < targets[t] and _idle_count(camps, t) > 0:
                camp = _take_idle(camps, t)
                _ensure_pools(camp)
                if dim == 'food':
                    camp._hungry[t] = camp._hungry.get(t, 0) + 1
                else:
                    camp._disarmed_soldiers[t] = camp._disarmed_soldiers.get(t, 0) + 1
                released[t] += _unit_cost(t, dim)
        stuck = [t for t in order
                 if _idle_count(camps, t) == 0 and released[t] + 1e-9 < targets[t]]
        live = [t for t in order if _idle_count(camps, t) > 0]
        if not stuck or not live:
            break
        short = sum(targets[t] - released[t] for t in stuck)
        for t in stuck:
            targets[t] = released[t]
        for t in live:
            targets[t] += short / len(live)


def _pull_back(camps: list) -> None:
    """THUẬT TOÁN B — kéo lính "thiếu" về idle.

    Chia đều surplus (cả lương thực lẫn vũ khí) cho 3 loại làm budget. Mỗi
    loại thêm lính TỪNG CON, chỉ khi CẢ HAI vẫn thoả sau khi cộng con đó —
    vượt 1 trong 2 là dừng (KHÁC thuật toán A: vượt total là hỏng, nên B
    tuyệt đối không được vượt). Loại nào hết lính thiếu → budget dư của nó
    CHIA ĐỀU cho các loại còn lính thiếu, lặp tới điểm bất động.
    """
    from structures.buildings.resource_manager import ResourceManager
    order = list(SOLDIER_KINDS_ORDER)
    stock = ResourceManager.get_instance().get_stock()

    sync_soldier_weapon_used()
    surplus_food = total_food_production_rate() - total_active_upkeep()
    surplus_gen = getattr(stock, 'soldier_weapon', 0) - getattr(Forge._weapon_used, 'soldier_weapon', 0)

    budget_f = {t: surplus_food / 3.0 for t in order}
    budget_w = {t: surplus_gen / 3.0 for t in order}
    used_f = {t: 0.0 for t in order}
    used_w = {t: 0.0 for t in order}

    # Giới hạn vũ khí CỤ THỂ (sword/arrow/spear) — riêng từng loại, độc lập
    # với budget chung, nên không chia đều mà tính thẳng chỗ còn trống.
    active = count_active_soldiers()
    spec_left = {}
    for t in order:
        _gen, spec, amt = TrainingCamp.WEAPON_COST[t]
        spec_left[t] = getattr(stock, spec, 0) - active[t] * amt

    guard = 0
    while guard < 500:
        guard += 1
        moved = False
        for t in order:
            cf = _unit_cost(t, 'food')
            cw = _unit_cost(t, 'weapon')
            while _deficient_count(camps, t) > 0:
                if used_f[t] + cf > budget_f[t] + 1e-9:
                    break
                if used_w[t] + cw > budget_w[t] + 1e-9:
                    break
                if spec_left[t] < cw:
                    break
                camp = _take_deficient(camps, t)
                if camp is None:
                    break
                camp._idle[t] = camp._idle.get(t, 0) + 1
                used_f[t] += cf
                used_w[t] += cw
                spec_left[t] -= cw
                moved = True
        # Loại nào KHÔNG còn lính thiếu → nhường budget dư cho loại còn lính.
        donors = [t for t in order if _deficient_count(camps, t) == 0]
        recips = [t for t in order if _deficient_count(camps, t) > 0]
        if not donors or not recips:
            break
        left_f = sum(max(0.0, budget_f[t] - used_f[t]) for t in donors)
        left_w = sum(max(0.0, budget_w[t] - used_w[t]) for t in donors)
        if left_f <= 1e-9 and left_w <= 1e-9:
            break
        for t in donors:
            budget_f[t] = used_f[t]
            budget_w[t] = used_w[t]
        for t in recips:
            budget_f[t] += left_f / len(recips)
            budget_w[t] += left_w / len(recips)
        if not moved and left_f <= 1e-9 and left_w <= 1e-9:
            break

    sync_soldier_weapon_used()


def reconcile_soldiers() -> None:
    """A rồi B — lập lại 2 bất biến, rồi tận dụng phần dư.

    Idempotent và không dao động: A dừng ngay khi VỪA VƯỢT target nên phần dư
    của mỗi loại luôn nhỏ hơn upkeep một con loại đó → B không kéo ngược lại
    được cái A vừa làm.

    Gọi tại: xây/nâng cấp Farm · xây/nâng cấp Forge · Forge.upgrade_limit ·
    lính thám hiểm chết · cuối trận · sau khi load save · Forge/Farm bị phá.
    KHÔNG gọi giữa trận.
    """
    from structures.buildings.resource_manager import ResourceManager
    camps = _all_training_camps()
    if not camps:
        sync_soldier_weapon_used()
        return
    for c in camps:
        _ensure_pools(c)

    # ── A1: thiếu lương thực ────────────────────────────────────────────
    sync_soldier_weapon_used()
    x = total_active_upkeep() - total_food_production_rate()
    if x > 0:
        _push_deficit(camps, x, 'food')

    # ── A2: thiếu vũ khí CHUNG (tính lại — A1 đã tự làm giảm) ───────────
    sync_soldier_weapon_used()
    stock = ResourceManager.get_instance().get_stock()
    y = getattr(Forge._weapon_used, 'soldier_weapon', 0) - getattr(stock, 'soldier_weapon', 0)
    if y > 0:
        _push_deficit(camps, float(y), 'weapon')

    # ── A3: thiếu vũ khí CỤ THỂ từng loại (sword/arrow/spear) ───────────
    sync_soldier_weapon_used()
    active = count_active_soldiers()
    for t in SOLDIER_KINDS_ORDER:
        _gen, spec, amt = TrainingCamp.WEAPON_COST[t]
        over = active[t] * amt - getattr(stock, spec, 0)
        if over > 0 and amt > 0:
            need = int(math.ceil(over / float(amt)))
            for _ in range(need):
                if _idle_count(camps, t) <= 0:
                    break
                camp = _take_idle(camps, t)
                _ensure_pools(camp)
                camp._disarmed_soldiers[t] = camp._disarmed_soldiers.get(t, 0) + 1

    # ── B: kéo lính thiếu về idle bằng phần dư ──────────────────────────
    _pull_back(camps)


# ═══════════════════════════════════════════════════════
#  BUILDING BASE
# ═══════════════════════════════════════════════════════

class Building(Entity, IAttackable, IUpgradable, IProducible):
    """Cha của mọi công trình. Tự sản xuất theo timer.

    Vòng đời chuẩn: mỗi `CYCLE_TIME` giây, `update()` tự gọi `produce()`
    và CỘNG DỒN kết quả vào `_stock` nội bộ (KHÔNG tự động vào
    ResourceManager — caller bên ngoài phải chủ động gọi `harvest()` định
    kỳ để rút `_stock` ra và cộng vào kho chung, xem game.py vòng lặp
    combat). `is_starter=True` (công trình khởi đầu) → bất tử, bỏ qua
    `take_damage()`/`check_trampling()` hoàn toàn.
    """

    # THÊM MỚI: trước đây chỉ TrainingCamp tự khai ENTITY_TYP="building" riêng,
    # nên Farm/Forge/StoneWorkshop/WoodWorkshop không có thuộc tính này —
    # WorldQuery.get_all_buildings() (lọc theo ENTITY_TYPE=="building") không
    # bao giờ thấy chúng, khiến _get_total_food_production_rate() không tìm
    # được Farm nào và luôn rơi về fallback cứng 50.0 bất kể xây/nâng cấp bao
    # nhiêu farm. Đặt ở đây để MỌI building con kế thừa đúng.
    ENTITY_TYPE     = "building"
    CYCLE_TIME      = balance.BUILDING_CYCLE_TIME  # giây — class con override
    PRODUCTION_RATE = balance.BUILDING_PRODUCTION_RATE     # lượng sản xuất — class con override
    TILE_W          = 3     # bề rộng footprint (ô 32px) — class con override
    TILE_H          = 3     # bề cao footprint (ô 32px) — class con override
    _WORLD_TILE     = 32     # khớp TILE thật của lưới thế giới (game.py) —
                              # KHÔNG dùng TILE cục bộ 48 của trap.py (khác ý nghĩa)

    def __init__(self, x: float, y: float):
        """Khởi tạo công trình với HP cứng 300/300 (KHÔNG tham chiếu
        `balance.*` — HP building hiện chưa được tách vào config/balance.py,
        vẫn là hằng số tại chỗ) và cấp 1. `is_starter` mặc định False,
        caller (game.py khi setup công trình khởi đầu) tự set True sau khi
        tạo nếu cần bất tử."""
        super().__init__(x, y)
        self._hp         = 300
        self._max_hp     = 300
        self._level      = 1
        self._timer      = 0.0
        self._anim_timer = 0.0
        self._stock      = ResourceBundle()
        self.is_starter  = False  # True cho building khởi đầu (bất tử)

    def update(self, dt: float):
        """Đếm timer. Khi đủ CYCLE_TIME → tự produce()."""
        if not self.is_alive:
            return
        self._anim_timer += dt
        self._timer += dt
        if self._timer >= self.CYCLE_TIME:
            self._timer   = 0.0
            self._stock  += self.produce()

    def produce(self) -> ResourceBundle:
        """IProducible — tính lượng sản xuất. Class con override."""
        return ResourceBundle()

    def harvest(self) -> ResourceBundle:
        """Lấy toàn bộ _stock ra và reset về 0."""
        out         = self._stock
        self._stock = ResourceBundle()
        return out

    def take_damage(self, amount: int, dtype: str):
        """Titan vào Sina có thể phá công trình."""
        if getattr(self, 'is_starter', False) or not self.is_alive:
            return
        self._hp -= amount
        if self._hp <= 0:
            SoundManager.get_instance().play('wall_collapse_1', self.x, self.y)
            self.is_alive = False
            GameEventBus.get_instance().publish(
                'building_destroyed', {'building': self}
            )

    def get_rect(self):
        """Hình chữ nhật footprint (TILE_W×TILE_H ô 32px, neo góc trên-trái tại
        x,y) — dùng cho va chạm hình học (check_trampling()). FIX: trước đây
        gọi self.get_rect()/t.get_rect() nhưng KHÔNG hề định nghĩa ở Building
        HAY Titan (chỉ có ở Trap) → check_trampling() CRASH ngay lập tức
        (AttributeError) với BẤT KỲ building không phải starter nào một khi
        vào combat, vì được gọi mỗi frame cho mọi building."""
        import pygame
        return pygame.Rect(int(self.x), int(self.y),
                           self.TILE_W * self._WORLD_TILE, self.TILE_H * self._WORLD_TILE)

    def check_trampling(self, dt: float, titans: list):
        """Kiểm tra bị Titan giẫm đạp trong combat (thay thế cho tấn công building)."""
        if getattr(self, 'is_starter', False) or not self.is_alive:
            return
        rect = self.get_rect()
        for t in titans:
            if t.is_alive and t.get_rect().colliderect(rect):
                # 1s titan đứng trên building = đúng damage của titan (chưa x factor nào)
                damage_amt = getattr(t, '_damage', 20) * dt
                self.take_damage(damage_amt, 'trample')

    def upgrade(self):
        """Nâng cấp mặc định (dùng bởi mọi Building KHÔNG override riêng —
        thực tế MỌI subclass cụ thể trong file này ĐỀU override `upgrade()`
        của chính nó với logic MAX_LEVEL/LEVEL_UPGRADE riêng; hàm này chỉ
        còn là fallback lý thuyết): đủ tài nguyên → trừ, áp bonus cấp, rồi
        `reconcile_soldiers()` (vì nâng cấp bất kỳ building nào SẢN XUẤT
        food/vũ khí đều có thể thay đổi surplus, kéo lính thiếu về idle)."""
        from structures.buildings.resource_manager import ResourceManager
        rm = ResourceManager.get_instance()
        if rm.get_stock() >= self.get_upgrade_cost():
            rm.spend(self.get_upgrade_cost())
            self._apply_level_bonus()
            # Nâng cấp Farm làm food_production tăng → surplus tăng → kéo lính
            # "thiếu" về idle được. (Forge override upgrade() và tự gọi riêng.)
            reconcile_soldiers()

    def _apply_level_bonus(self) -> None:
        """Áp dụng hiệu ứng lên cấp (tăng chỉ số + `_level += 1`) — TÁCH RIÊNG
        khỏi việc kiểm tra/trừ tài nguyên (THÊM MỚI) để UI (dùng pool tài
        nguyên `res` khác với `ResourceManager` ở trên) có thể gọi thẳng hàm
        này ngay sau khi UI đã tự trừ đúng rồi, không cần đi qua `upgrade()`.
        Class con override để áp bonus riêng (PRODUCTION_RATE, weapon-capacity...).
        """
        self.PRODUCTION_RATE = int(self.PRODUCTION_RATE * balance.BUILDING_UPGRADE_RATE_MULT)
        self._level          += 1

    def get_upgrade_cost(self) -> ResourceBundle:
        """Chi phí nâng cấp mặc định (tuyến tính theo cấp hiện tại) — dùng
        bởi `Building.upgrade()` fallback. Mọi subclass cụ thể override
        hàm này bằng bảng `LEVEL_UPGRADE` riêng nên công thức tuyến tính
        này thực tế KHÔNG được gọi trong game hiện tại."""
        return ResourceBundle(
            wood  = 50 * self._level,
            stone = 30 * self._level
        )

    def draw(self, screen):
        """No-op ở base class — MỌI subclass cụ thể override để vẽ sprite riêng."""
        pass


# ═══════════════════════════════════════════════════════
#  CÔNG TRÌNH CỤ THỂ
# ═══════════════════════════════════════════════════════

class Farm(Building):
    """Năng suất food/s = PRODUCTION_RATE / CYCLE_TIME. Trong game CYCLE_TIME=15
    nên: lv1 40/15≈2.7/s · lv2 60/15=4/s · lv3 100/15≈6.7/s mỗi Farm.
    (Tăng ~4× so với bản cũ 10/15≈0.67/s — user thấy quá ít.)"""

    CYCLE_TIME      = balance.FARM_CYCLE_TIME
    PRODUCTION_RATE = balance.FARM_PRODUCTION_RATE
    MAX_LEVEL       = balance.FARM_MAX_LEVEL
    TILE_W          = 4     # khớp BUILDING_DEFS['Farm'] (game.py)
    TILE_H          = 4

    LEVEL_UPGRADE = balance.FARM_LEVEL_UPGRADE

    _DISPLAY_SIZE  = (128, 128)
    _sprite_cache: "pygame.Surface | None" = None

    def __init__(self, x: float, y: float):
        """Tạo Farm — nạp sprite tĩnh (không animation) 1 LẦN vào cache
        class-level. `PRODUCTION_RATE`/`CYCLE_TIME`/`MAX_LEVEL`/`LEVEL_UPGRADE`
        đều lấy từ `balance.FARM_*` (khai báo ở cấp class, không phải ở đây)."""
        super().__init__(x, y)
        if _PYGAME_OK and Farm._sprite_cache is None:
            raw = pygame.image.load(
                os.path.join(_HERE, 'Farm.png')
            ).convert_alpha()
            Farm._sprite_cache = pygame.transform.scale(raw, Farm._DISPLAY_SIZE)

    def draw(self, screen) -> None:
        """Vẽ sprite tĩnh nếu còn sống — Farm không có animation theo cấp
        (khác StoneWorkshop/WoodWorkshop/Forge có nhiều frame theo level)."""
        if _PYGAME_OK and Farm._sprite_cache is not None and self.is_alive:
            screen.blit(Farm._sprite_cache, (int(self.x), int(self.y)))

    def produce(self) -> ResourceBundle:
        """Trả túi RỖNG có chủ đích — Farm KHÔNG tích food vào kho tiêu
        được như Stone/Wood Workshop. Food chỉ tồn tại dưới dạng "tốc độ"
        (food/s) được tính TỔNG HỢP qua `total_food_production_rate()` (module-
        level, quét mọi Farm còn sống), dùng để so sánh với upkeep lính —
        KHÔNG BAO GIỜ trừ/cộng vào `ResourceBundle.food` như 1 tài nguyên
        tích luỹ thông thường. Đổi hàm này để trả khác rỗng SẼ làm food bị
        cộng dồn qua `harvest()` — phá vỡ mô hình "food = rate, không phải
        stock" mà toàn hệ thống reconcile dựa vào."""
        return ResourceBundle()

    def get_upgrade_cost(self) -> ResourceBundle:
        """Chi phí nâng lên cấp kế tiếp, tra từ `LEVEL_UPGRADE[self._level]`.
        Không còn cấp tiếp theo (đã max hoặc key không tồn tại) → túi rỗng
        (miễn phí — nhưng `upgrade()` đã tự chặn bằng `MAX_LEVEL` trước đó)."""
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        """Nâng cấp Farm lên 1 cấp (tối đa `MAX_LEVEL`): đủ tài nguyên theo
        `LEVEL_UPGRADE[self._level]['cost']` → trừ, tăng `PRODUCTION_RATE`
        theo `rate_bonus`, rồi `reconcile_soldiers()` — food/s tổng tăng có
        thể đủ nuôi lại lính đang "đói" (thuật toán B trong reconcile kéo
        họ về idle ngay khi surplus dương)."""
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm    = ResourceManager.get_instance()
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry and rm.can_afford(entry['cost']):
            rm.spend(entry['cost'])
            self._apply_level_bonus()
            # Nâng cấp làm production/total tăng → surplus tăng → kéo lính
            # "thiếu" về idle (thuật toán B bên trong reconcile).
            reconcile_soldiers()

    def _apply_level_bonus(self) -> None:
        """Áp bonus rate lên cấp — TÁCH RIÊNG khỏi trừ tài nguyên (THÊM MỚI)
        để UI (dùng pool `res`, không phải `ResourceManager`) gọi thẳng được
        sau khi UI đã tự trừ đúng rồi."""
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry:
            self.PRODUCTION_RATE += entry.get('rate_bonus', 0)
        self._level += 1


class StoneWorkshop(Building):
    """→ 8 stone/60s (lv1) · 12 stone/60s (lv2) · 20 stone/60s (lv3). 3 cấp."""

    CYCLE_TIME      = balance.STONE_WS_CYCLE_TIME
    PRODUCTION_RATE = balance.STONE_WS_PRODUCTION_RATE
    MAX_LEVEL       = balance.STONE_WS_MAX_LEVEL
    TILE_W          = 3     # khớp BUILDING_DEFS['StoneWorkshop'] (game.py)
    TILE_H          = 3

    LEVEL_UPGRADE = balance.STONE_WS_LEVEL_UPGRADE

    _COLS        = 3
    _ROWS        = 6
    _sheet_cache: "pygame.Surface | None" = None

    def __init__(self, x: float, y: float):
        """Tạo StoneWorkshop — nạp sprite sheet DUY NHẤT (KHÔNG phải nhiều
        file theo cấp như WoodWorkshop/Forge) rồi PRE-SCALE sẵn 3 frame ứng
        3 cấp độ, cache theo key `('SW', level, 0)` trong `_scaled_frame_cache`
        DÙNG CHUNG với mọi building khác (WW/FG) — tránh gọi `transform.scale`
        mỗi frame vẽ (nặng CPU nếu làm ở `draw()`)."""
        super().__init__(x, y)
        if _PYGAME_OK and StoneWorkshop._sheet_cache is None:
            StoneWorkshop._sheet_cache = pygame.image.load(
                os.path.join(_HERE, 'StoneWorkshop.png')
            ).convert_alpha()
            # Pre-scale tất cả frame một lần — tránh transform.scale mỗi draw()
            sheet = StoneWorkshop._sheet_cache
            fw = sheet.get_width()  // StoneWorkshop._COLS
            fh = sheet.get_height() // StoneWorkshop._ROWS
            for _lv in (1, 2, 3):
                col = min(_lv - 1, StoneWorkshop._COLS - 1)
                if _lv <= 2:
                    src = pygame.Rect(col * fw - 15, 0, fw - 15, fh)
                else:
                    src = pygame.Rect(col * fw - 20, 0, fw + 10, fh)
                src = src.clip(sheet.get_rect())
                if src.w > 0 and src.h > 0:
                    raw_f = sheet.subsurface(src)
                    sw = max(1, int(src.w * _BLDG_SCALE))
                    sh = max(1, int(src.h * _BLDG_SCALE))
                    _scaled_frame_cache[('SW', _lv, 0)] = pygame.transform.scale(raw_f, (sw, sh))

    def draw(self, screen) -> None:
        """Vẽ frame ĐÚNG CẤP hiện tại từ cache pre-scale. Cache-miss (lý
        thuyết không nên xảy ra vì `__init__` đã nạp đủ 3 cấp) → fallback
        cắt+scale trực tiếp từ `_sheet_cache` (chậm hơn nhưng không crash)."""
        if not _PYGAME_OK or StoneWorkshop._sheet_cache is None or not self.is_alive:
            return
        cached = _scaled_frame_cache.get(('SW', self._level, 0))
        if cached is not None:
            screen.blit(cached, (int(self.x), int(self.y)))
            return
        # Fallback (kó cache): vẽ như cũ
        sheet = StoneWorkshop._sheet_cache
        fw  = sheet.get_width()  // self._COLS
        fh  = sheet.get_height() // self._ROWS
        col = min(self._level - 1, self._COLS - 1)
        if self._level == 1 or self._level == 2:
            src = pygame.Rect(col * fw - 15, 0, fw - 15, fh)
        else:
            src = pygame.Rect(col * fw - 20, 0, fw + 10, fh)
        src = src.clip(sheet.get_rect())
        if src.w <= 0 or src.h <= 0:
            return
        frame_surf = sheet.subsurface(src)
        scaled = pygame.transform.scale(frame_surf,
            (max(1, int(src.w * _BLDG_SCALE)), max(1, int(src.h * _BLDG_SCALE))))
        screen.blit(scaled, (int(self.x), int(self.y)))

    def produce(self) -> ResourceBundle:
        """Mỗi chu kỳ (`CYCLE_TIME` giây) tạo `PRODUCTION_RATE` đá — TÍCH LUỸ
        THẬT vào `_stock` (khác Farm — đá là tài nguyên kho, không phải rate)."""
        return ResourceBundle(stone=self.PRODUCTION_RATE)

    def get_upgrade_cost(self) -> ResourceBundle:
        """Chi phí nâng cấp cấp kế tiếp, tra `LEVEL_UPGRADE[self._level]`."""
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        """Nâng cấp lên 1 cấp (tối đa `MAX_LEVEL`, 3 cấp): đủ tài nguyên →
        trừ, tăng `PRODUCTION_RATE` theo `rate_bonus`. KHÔNG gọi
        `reconcile_soldiers()` (khác Farm/Forge) vì đá không liên quan
        upkeep/vũ khí lính."""
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm    = ResourceManager.get_instance()
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry and rm.can_afford(entry['cost']):
            rm.spend(entry['cost'])
            self._apply_level_bonus()

    def _apply_level_bonus(self) -> None:
        """Áp bonus rate lên cấp — TÁCH RIÊNG khỏi trừ tài nguyên (THÊM MỚI)
        để UI (dùng pool `res`, không phải `ResourceManager`) gọi thẳng được
        sau khi UI đã tự trừ đúng rồi."""
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry:
            self.PRODUCTION_RATE += entry.get('rate_bonus', 0)
        self._level += 1


class WoodWorkshop(Building):
    """→ 15 wood/60s (lv1) · 23 wood/60s (lv2). 2 cấp."""

    CYCLE_TIME      = balance.WOOD_WS_CYCLE_TIME
    PRODUCTION_RATE = balance.WOOD_WS_PRODUCTION_RATE
    MAX_LEVEL       = balance.WOOD_WS_MAX_LEVEL
    TILE_W          = 4     # khớp BUILDING_DEFS['WoodWorkshop'] (game.py)
    TILE_H          = 3

    LEVEL_UPGRADE = balance.WOOD_WS_LEVEL_UPGRADE

    # 8 cột × 8 hàng, hàng cuối 4 frames → tổng 60 frames
    _COLS           = 8
    _ROWS           = 8
    _TOTAL_FRAMES   = 60
    _FRAME_DURATION = 0.08   # ~12 fps
    _sheet_paths    = {
        1: os.path.join(_HERE, 'WoodWorkshop_1.png'),
        2: os.path.join(_HERE, 'WoodWorkshop_2.png'),
    }
    _sheets: dict = {}

    def __init__(self, x: float, y: float):
        """Tạo WoodWorkshop — nạp 2 sprite sheet RIÊNG BIỆT theo cấp
        (`WoodWorkshop_1.png`/`_2.png` — KHÁC StoneWorkshop dùng 1 sheet
        chung có 3 cột cấp độ), pre-scale sẵn 60 frame animation MỖI cấp
        vào `_scaled_frame_cache` (key `('WW', level, frame_idx)`)."""
        super().__init__(x, y)
        if _PYGAME_OK:
            for lv, path in WoodWorkshop._sheet_paths.items():
                if lv not in WoodWorkshop._sheets:
                    WoodWorkshop._sheets[lv] = pygame.image.load(path).convert_alpha()
                    # Pre-scale tất cả frame cho cấp độ này
                    sheet = WoodWorkshop._sheets[lv]
                    cols, rows = WoodWorkshop._COLS, WoodWorkshop._ROWS
                    total = WoodWorkshop._TOTAL_FRAMES
                    fw = sheet.get_width()  // cols
                    fh = sheet.get_height() // rows
                    sw = max(1, int(fw * _BLDG_SCALE))
                    sh = max(1, int(fh * _BLDG_SCALE))
                    for fi in range(total):
                        col = fi % cols
                        row = fi // cols
                        src = pygame.Rect(col * fw, row * fh, fw, fh)
                        raw_f = sheet.subsurface(src)
                        _scaled_frame_cache[('WW', lv, fi)] = pygame.transform.scale(raw_f, (sw, sh))

    def draw(self, screen) -> None:
        """Chọn frame theo `_anim_timer` (không phải đếm frame thủ công —
        tính trực tiếp từ thời gian trôi qua nên KHÔNG BAO GIỜ trôi lệch dù
        frame-rate dao động) MODULO `_TOTAL_FRAMES` (60) để lặp vô hạn, vẽ
        từ cache; cache-miss → fallback cắt+scale trực tiếp."""
        if not _PYGAME_OK or not self.is_alive:
            return
        frame = int(self._anim_timer / self._FRAME_DURATION) % self._TOTAL_FRAMES
        cached = _scaled_frame_cache.get(('WW', self._level, frame))
        if cached is not None:
            screen.blit(cached, (int(self.x), int(self.y)))
            return
        # Fallback
        sheet = WoodWorkshop._sheets.get(self._level)
        if sheet is None:
            return
        fw    = sheet.get_width()  // self._COLS
        fh    = sheet.get_height() // self._ROWS
        col   = frame % self._COLS
        row   = frame // self._COLS
        src        = pygame.Rect(col * fw, row * fh, fw, fh)
        frame_surf = sheet.subsurface(src)
        scaled     = pygame.transform.scale(frame_surf,
            (max(1, int(fw * _BLDG_SCALE)), max(1, int(fh * _BLDG_SCALE))))
        screen.blit(scaled, (int(self.x), int(self.y)))

    def produce(self) -> ResourceBundle:
        """Mỗi chu kỳ tạo `PRODUCTION_RATE` gỗ — tích luỹ thật vào `_stock`."""
        return ResourceBundle(wood=self.PRODUCTION_RATE)

    def get_upgrade_cost(self) -> ResourceBundle:
        """Chi phí nâng cấp cấp kế tiếp, tra `LEVEL_UPGRADE[self._level]`."""
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        """Nâng cấp lên 1 cấp (tối đa `MAX_LEVEL`, 2 cấp): đủ tài nguyên →
        trừ, tăng `PRODUCTION_RATE`. Không gọi `reconcile_soldiers()` (gỗ
        không liên quan food/vũ khí lính)."""
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm    = ResourceManager.get_instance()
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry and rm.can_afford(entry['cost']):
            rm.spend(entry['cost'])
            self._apply_level_bonus()

    def _apply_level_bonus(self) -> None:
        """Áp bonus rate lên cấp — TÁCH RIÊNG khỏi trừ tài nguyên (THÊM MỚI)
        để UI (dùng pool `res`, không phải `ResourceManager`) gọi thẳng được
        sau khi UI đã tự trừ đúng rồi."""
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry:
            self.PRODUCTION_RATE += entry.get('rate_bonus', 0)
        self._level += 1


class Forge(Building):
    """Xưởng vũ khí trung tâm. Quản lý việc trang bị vũ khí và nâng cấp giới hạn.

    2 trục nâng cấp độc lập:
      • upgrade()        — nâng CẤP ĐỘ Xưởng (1→2→3), tăng nhóm tổng
                           (tower_weapon / soldier_weapon / trap).
      • upgrade_limit()  — tăng từng loại vũ khí lẻ (sword/arrow/spear…).
    """

    CYCLE_TIME      = balance.FORGE_CYCLE_TIME
    PRODUCTION_RATE = balance.FORGE_PRODUCTION_RATE
    MAX_LEVEL       = balance.FORGE_MAX_LEVEL
    TILE_W          = 3     # khớp BUILDING_DEFS['Forge'] (game.py)
    TILE_H          = 4

    # Nâng cấp theo CẤP ĐỘ — tăng nhóm tổng
    # key = cấp hiện tại → nâng lên cấp kế tiếp
    LEVEL_UPGRADE = balance.FORGE_LEVEL_UPGRADE

    # Level 1: 8 cột × 5 hàng, hàng cuối 3 frames → 35 frames
    # Level 2: 6 cột × 6 hàng, hàng cuối 5 frames → 35 frames
    # Level 3: 8 cột × 5 hàng, hàng cuối 3 frames → 35 frames
    _FRAME_CONFIG = {
        1: (8, 5, 35),
        2: (6, 6, 35),
        3: (8, 5, 35),
    }
    _FRAME_DURATION = 0.10   # 10 fps
    _sheet_paths = {
        1: os.path.join(_HERE, 'Forge_1.png'),
        2: os.path.join(_HERE, 'Forge_2.png'),
        3: os.path.join(_HERE, 'Forge_3.png'),
    }
    _sheets: dict = {}
    _weapon_used: ResourceBundle = ResourceBundle()  # shared across ALL Forge instances

    @property
    def weapon_used(self) -> ResourceBundle:
        """Truy cập `Forge._weapon_used` — biến CẤP CLASS dùng chung cho
        MỌI instance Forge (không phải mỗi Forge có sổ vũ khí riêng — có
        nhiều Forge thì tất cả cùng đọc/ghi 1 sổ, vì slot vũ khí là tài
        nguyên TOÀN CỤC, không thuộc về 1 xưởng cụ thể nào)."""
        return Forge._weapon_used

    def __init__(self, x: float, y: float):
        """Tạo Forge — nạp 3 sprite sheet riêng theo cấp (giống WoodWorkshop),
        pre-scale theo `_FRAME_CONFIG[level]` (cols,rows,total frame — KHÁC
        NHAU giữa các cấp, không cố định như WoodWorkshop). Khởi tạo
        `_contributed_limits` RỖNG — theo dõi RIÊNG lượng giới hạn vũ khí mà
        CHÍNH instance Forge NÀY đã cộng vào ResourceManager (dùng để hoàn
        tác đúng phần của nó khi bị phá, xem `on_destroyed`)."""
        super().__init__(x, y)
        if _PYGAME_OK:
            for lv, path in Forge._sheet_paths.items():
                if lv not in Forge._sheets:
                    Forge._sheets[lv] = pygame.image.load(path).convert_alpha()
                    # Pre-scale tất cả frame cho cấp này
                    sheet = Forge._sheets[lv]
                    cols, rows, total = Forge._FRAME_CONFIG[lv]
                    fw = sheet.get_width()  // cols
                    fh = sheet.get_height() // rows
                    sw = max(1, int(fw * _BLDG_SCALE))
                    sh = max(1, int(fh * _BLDG_SCALE))
                    for fi in range(total):
                        col = fi % cols
                        row = fi // cols
                        src = pygame.Rect(col * fw, row * fh, fw, fh)
                        raw_f = sheet.subsurface(src)
                        _scaled_frame_cache[('FG', lv, fi)] = pygame.transform.scale(raw_f, (sw, sh))
        self._contributed_limits = ResourceBundle()

    def draw(self, screen) -> None:
        """Chọn frame theo `_anim_timer` MODULO tổng frame CỦA ĐÚNG CẤP
        (`_FRAME_CONFIG[level][2]` — số frame khác nhau giữa các cấp, không
        cố định 60 như WoodWorkshop), vẽ từ cache; cache-miss → fallback."""
        if not _PYGAME_OK or not self.is_alive:
            return
        cols, rows, total = self._FRAME_CONFIG[self._level]
        frame = int(self._anim_timer / self._FRAME_DURATION) % total
        cached = _scaled_frame_cache.get(('FG', self._level, frame))
        if cached is not None:
            screen.blit(cached, (int(self.x), int(self.y)))
            return
        # Fallback
        sheet = Forge._sheets.get(self._level)
        if sheet is None:
            return
        fw    = sheet.get_width()  // cols
        fh    = sheet.get_height() // rows
        col   = frame % cols
        row   = frame // cols
        src        = pygame.Rect(col * fw, row * fh, fw, fh)
        frame_surf = sheet.subsurface(src)
        scaled     = pygame.transform.scale(frame_surf,
            (max(1, int(fw * _BLDG_SCALE)), max(1, int(fh * _BLDG_SCALE))))
        screen.blit(scaled, (int(self.x), int(self.y)))

    # ── Nâng cấp theo CẤP ĐỘ ────────────────────────────────────────

    def get_upgrade_cost(self) -> ResourceBundle:
        """Chi phí nâng CẤP ĐỘ Xưởng lên kế tiếp, tra `LEVEL_UPGRADE[self._level]`
        (KHÁC `upgrade_limit()` — trục nâng cấp lẻ từng loại vũ khí, có chi
        phí truyền trực tiếp bởi caller, không qua hàm này)."""
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        """Nâng cấp độ Xưởng (tối đa cấp 3).

        Mỗi cấp: trừ tài nguyên → cộng thêm nhóm tổng
        (tower_weapon / soldier_weapon / trap) vào ResourceManager.
        """
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm    = ResourceManager.get_instance()
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry and rm.can_afford(entry['cost']):
            rm.spend(entry['cost'])
            self._apply_level_bonus()
            # Nâng cấp làm production/total tăng → surplus tăng → kéo lính
            # "thiếu" về idle (thuật toán B bên trong reconcile).
            reconcile_soldiers()

    def _apply_level_bonus(self) -> None:
        """Cộng nhóm tổng vũ khí (tower_weapon/soldier_weapon/trap) vào
        ResourceManager (pool DÙNG CHUNG cho mọi Forge) — TÁCH RIÊNG khỏi trừ
        tài nguyên (THÊM MỚI) để UI gọi thẳng được sau khi đã tự trừ `res`."""
        from structures.buildings.resource_manager import ResourceManager
        entry = self.LEVEL_UPGRADE.get(self._level)
        if entry:
            ResourceManager.get_instance().earn(entry['bonus'])
            self._contributed_limits += entry['bonus']
        self._level += 1

    # ── Giới hạn ban đầu khi xây Xưởng ─────────────────────────────

    def _add_initial_limits(self):
        """CHỈ dùng cho 3 Xưởng KHỞI ĐẦU: cộng vũ khí CHUNG + các vũ khí CỤ THỂ
        cơ bản (basic_projectlie/sword/spear/arrow/thorn_trap)."""
        from structures.buildings.resource_manager import ResourceManager
        from core.game_state import ResourceBundle
        rm = ResourceManager.get_instance()

        initial_limits = balance.FORGE_INITIAL_LIMITS
        # Cộng giới hạn vào kho chứa chung
        rm.earn(initial_limits)
        
        # Chỉ track vũ khí chung (sẽ bị xóa khi Forge vỡ)
        self._contributed_limits += balance.FORGE_INITIAL_GENERAL

    def _add_build_limits(self):
        """Dùng khi XÂY THÊM Xưởng trong game (THÊM MỚI): CHỈ cộng vũ khí CHUNG
        (tower_weapon/soldier_weapon/trap), KHÔNG cộng vũ khí cụ thể nào. Lượng
        bằng nửa phần chung của xưởng khởi đầu."""
        from structures.buildings.resource_manager import ResourceManager
        from core.game_state import ResourceBundle
        bonus = balance.FORGE_BUILD_LIMITS
        ResourceManager.get_instance().earn(bonus)
        self._contributed_limits += bonus
        # Xây thêm Forge làm soldier_weapon total tăng → kéo lính về idle.
        reconcile_soldiers()

    def can_equip(self, general_type: str, specific_type: str, amount: int) -> bool:
        """Kiểm tra có đủ giới hạn vũ khí không (cả chung lẫn riêng)."""
        from structures.buildings.resource_manager import ResourceManager
        rm = ResourceManager.get_instance()
        stock = rm.get_stock()

        used_general = getattr(self.weapon_used, general_type, 0)
        limit_general = getattr(stock, general_type, 0)
        
        used_specific = getattr(self.weapon_used, specific_type, 0)
        limit_specific = getattr(stock, specific_type, 0)

        return (used_general + amount <= limit_general) and (used_specific + amount <= limit_specific)

    def equip(self, general_type: str, specific_type: str, amount: int) -> bool:
        """Trang bị vũ khí (chiếm slot). Trả về True nếu thành công."""
        if self.can_equip(general_type, specific_type, amount):
            setattr(self.weapon_used, general_type, getattr(self.weapon_used, general_type, 0) + amount)
            setattr(self.weapon_used, specific_type, getattr(self.weapon_used, specific_type, 0) + amount)
            return True
        return False

    def unequip(self, general_type: str, specific_type: str, amount: int):
        """Thu hồi vũ khí (giải phóng slot) khi tháp/lính/bẫy bị hủy."""
        new_gen = max(0, getattr(self.weapon_used, general_type, 0) - amount)
        new_spec = max(0, getattr(self.weapon_used, specific_type, 0) - amount)
        setattr(self.weapon_used, general_type, new_gen)
        setattr(self.weapon_used, specific_type, new_spec)

    def upgrade_limit(self, weapon_type: str, amount: int, cost: "ResourceBundle") -> bool:
        """Nâng cấp giới hạn của 1 loại vũ khí bất kỳ."""
        from structures.buildings.resource_manager import ResourceManager
        from core.game_state import ResourceBundle
        rm = ResourceManager.get_instance()
        if rm.get_stock() >= cost:
            rm.spend(cost)
            # Cộng lượng mở rộng vào ResourceManager
            upgrade_bundle = ResourceBundle()
            setattr(upgrade_bundle, weapon_type, amount)
            rm.earn(upgrade_bundle)
            # NOTE: Limit nâng cấp lẻ không bị xóa khi Forge chết
            # Nâng giới hạn soldier_weapon/sword/arrow/spear làm total tăng →
            # kéo lính "thiếu vũ khí" về idle. (Trước đây BỎ SÓT: chỉ upgrade()
            # theo cấp mới gọi recover, upgrade_limit() thì không.)
            reconcile_soldiers()
            return True
        return False

    def on_destroyed(self) -> tuple[int, int]:
        """Gọi khi Forge bị phá hủy trong combat. Trừ vũ khí chung và trả về (tower_weapon_deficit, soldier_weapon_deficit)."""
        from structures.buildings.resource_manager import ResourceManager
        rm = ResourceManager.get_instance()
        
        # Tạo bundle giả cost để dùng spend() (do spend yêu cầu >= 0)
        cost_bundle = ResourceBundle(
            tower_weapon=self._contributed_limits.tower_weapon,
            soldier_weapon=self._contributed_limits.soldier_weapon,
            trap=self._contributed_limits.trap
        )
        # Force spend (cho phép âm stock nếu deficit > 0)
        # ResourceManager spend method không cho phép nếu can_afford là False
        # Do đó ta sửa trực tiếp stock
        stock = rm.get_stock()
        stock.tower_weapon = max(0, stock.tower_weapon - cost_bundle.tower_weapon)
        stock.soldier_weapon = max(0, stock.soldier_weapon - cost_bundle.soldier_weapon)
        stock.trap = max(0, stock.trap - cost_bundle.trap)
        
        deficit_tw = max(0, getattr(Forge._weapon_used, 'tower_weapon', 0) - stock.tower_weapon)
        deficit_sw = max(0, getattr(Forge._weapon_used, 'soldier_weapon', 0) - stock.soldier_weapon)

        self._contributed_limits = ResourceBundle()

        # 3 field total cùng tụt, mỗi field một LÀN ĐỘC LẬP:
        #   • tower_weapon  → caller (game.py) cascade disarm tháp, xa→gần HQ
        #   • soldier_weapon→ reconcile_soldiers() đẩy lính vào "thiếu" (ở đây)
        #   • trap          → KHÔNG có cơ chế (bẫy đã đặt là tiêu hao vĩnh viễn,
        #                     không "gỡ ra" được như disarm tháp) — chấp nhận lệch.
        # Tháp và lính là 2 hệ thống riêng: sự kiện tháp KHÔNG kéo lính về idle,
        # và ngược lại. Gọi reconcile ở đây chỉ chạm phần lính.
        reconcile_soldiers()
        return deficit_tw, deficit_sw


class TrainingCamp(Building):
    """Tuyển lính: Warrior (cận chiến), Archer (tầm xa), Lancer (kỵ binh).

    Keys khớp với SOLDIER_TYPES trong characters/soldiers/soldier.py.
    Điều kiện train: upkeep + train_cost < tốc độ sản xuất Farm.
    """

    ENTITY_TYPE = "building"
    MAX_LEVEL   = balance.TRAININGCAMP_MAX_LEVEL
    TILE_W      = 4     # khớp BUILDING_DEFS['TrainingCamp'] (game.py)
    TILE_H      = 4

    # Keys phải khớp với SOLDIER_TYPES: 'Warrior', 'Archer', 'Lancer'
    SOLDIER_STATS = balance.TRAININGCAMP_SOLDIER_STATS

    # Chi phí vũ khí: (general_slot, specific_slot, amount)
    WEAPON_COST = balance.TRAININGCAMP_WEAPON_COST

    # Chi phí nâng cấp trại: lv1→2, lv2→3
    LEVEL_UPGRADE = balance.TRAININGCAMP_LEVEL_UPGRADE

    _DISPLAY_SIZE = (128, 128)
    _sprite_cache: "pygame.Surface | None" = None

    def __init__(self, x: float, y: float):
        """Tạo TrainingCamp — khởi tạo 3 dict trạng thái lính RIÊNG CỦA TRẠI
        NÀY: `_idle` (sẵn sàng điều động), `_hungry` (đói, tạm đình chỉ),
        `_disarmed_soldiers` (thiếu vũ khí, tạm đình chỉ). Dù mỗi trại giữ
        dict riêng, các hàm module-level (`_all_training_camps`,
        `reconcile_soldiers`...) LUÔN thao tác qua TẤT CẢ trại như 1 sổ
        chung — trại nào chứa lính nào chỉ có ý nghĩa lưu trữ, không có ý
        nghĩa nghiệp vụ (rút lính không quan tâm trại nguồn)."""
        super().__init__(x, y)
        self._queue: list = []
        self._current_food_upkeep: float = 0.0
        self._idle: dict = {t: 0 for t in self.SOLDIER_STATS}  # trained, not yet dispatched
        self._hungry: dict = {t: 0 for t in self.SOLDIER_STATS}  # lính thiếu lương thực
        self._disarmed_soldiers: dict = {t: 0 for t in self.SOLDIER_STATS}  # lính thiếu vũ khí
        if _PYGAME_OK and TrainingCamp._sprite_cache is None:
            raw = pygame.image.load(
                os.path.join(_HERE, 'Trainingcamp.png')
            ).convert_alpha()
            TrainingCamp._sprite_cache = pygame.transform.scale(raw, TrainingCamp._DISPLAY_SIZE)

    def draw(self, screen) -> None:
        """Vẽ sprite tĩnh (không animation, không thay đổi theo cấp — trại
        trông giống nhau ở mọi level, chỉ khác năng lực bên trong)."""
        if _PYGAME_OK and TrainingCamp._sprite_cache is not None and self.is_alive:
            screen.blit(TrainingCamp._sprite_cache, (int(self.x), int(self.y)))

    def get_upgrade_cost(self) -> ResourceBundle:
        """Chi phí nâng cấp trại lên cấp kế tiếp, tra `LEVEL_UPGRADE[self._level]`."""
        entry = self.LEVEL_UPGRADE.get(self._level)
        return entry['cost'] if entry else ResourceBundle()

    def upgrade(self):
        """Nâng cấp trại lên 1 cấp (tối đa `MAX_LEVEL`) — MỞ KHOÁ Lancer ở
        cấp 3 (xem check trong `start_training`). Đặc biệt: nâng cấp trại
        ÁP DỤNG BUFF HỒI TỐ (`get_soldier_buffs()`, +15% HP/damage mỗi cấp)
        cho TOÀN BỘ lính ĐANG SỐNG trên map ngay lập tức (không chỉ lính
        train mới sau này) — quét `WorldQuery._entities` trực tiếp (không
        qua `get_all_buildings()`/`all()` public API), tính lại `_max_hp`
        từ `BASE_HP * hp_mult` rồi CỘNG PHẦN CHÊNH LỆCH vào `_hp` hiện tại
        (giữ nguyên % máu đang có, không hồi đầy) và `_damage` từ
        `ATTACK_DAMAGE * dmg_mult` (ghi đè thẳng, không cộng dồn qua nhiều
        lần nâng cấp vì luôn tính lại từ `ATTACK_DAMAGE` gốc)."""
        if self._level >= self.MAX_LEVEL:
            return
        from structures.buildings.resource_manager import ResourceManager
        rm = ResourceManager.get_instance()
        cost = self.get_upgrade_cost()
        if rm.can_afford(cost):
            rm.spend(cost)
            self._level += 1
            
            # Retroactively apply buffs to all existing soldiers
            buffs = self.get_soldier_buffs()
            hp_mult = buffs.get('hp_mult', 1.0)
            dmg_mult = buffs.get('dmg_mult', 1.0)
            from systems.world_query import WorldQuery
            for ent in getattr(WorldQuery, '_entities', []):
                if getattr(ent, 'ENTITY_TYPE', '') == 'soldier' and getattr(ent, 'is_alive', False):
                    old_max = ent._max_hp
                    ent._max_hp = int(ent.BASE_HP * hp_mult)
                    ent._hp += (ent._max_hp - old_max)
                    ent._damage = int(ent.ATTACK_DAMAGE * dmg_mult)

    def get_soldier_buffs(self) -> dict:
        """Cấp trại càng cao lính ra càng mạnh (+15% HP/Damage mỗi cấp)."""
        mult = 1.0 + (self._level - 1) * 0.15
        return {'hp_mult': mult, 'dmg_mult': mult}

    def count_live_soldiers(self, towers: list | None = None) -> dict:
        """Đếm lính còn sống từ mọi nguồn: idle ở trại + deployed/reserve trong tháp.

        Returns: {type: {'idle': n, 'deployed': n, 'total': n}}
        Luôn gọi được trong combat loop — chỉ đọc, không mutate state.
        """
        result = {t: {'idle': 0, 'deployed': 0, 'total': 0}
                  for t in self.SOLDIER_STATS}
        # Idle trong trại (đã train xong, chưa dispatch)
        for t in self.SOLDIER_STATS:
            result[t]['idle'] = max(0, self._idle.get(t, 0))
        # Deployed / reserve trong tất cả tháp
        for tw in (towers or []):
            for sq in (getattr(tw, '_deployed_squads', [])
                       + getattr(tw, '_reserve_squads', [])):
                alive = sum(1 for m in sq.members if m.is_alive)
                st = sq.soldier_type
                if st in result:
                    result[st]['deployed'] += alive
        # Tổng mỗi loại
        for t in result:
            result[t]['total'] = result[t]['idle'] + result[t]['deployed']
        return result

    def total_upkeep_from_roster(self, towers: list | None = None) -> float:
        """Tính food upkeep thực tế từ roster live (không dùng _current_food_upkeep cached).

        Dùng cho tab ROSTER để hiển thị đúng khi lính chết giữa combat.
        """
        roster = self.count_live_soldiers(towers)
        total = 0.0
        for t, stats in self.SOLDIER_STATS.items():
            total += roster[t]['total'] * stats['upkeep']
        return total

    def _get_total_food_production_rate(self) -> float:
        """Uỷ quyền cho `total_food_production_rate()` module-level — giữ
        method này chỉ để `start_training()` gọi qua `self.` (dễ override
        trong test nếu cần), KHÔNG còn fallback cứng 50 như bản cũ."""
        # Ủy quyền cho hàm module-level (THÊM MỚI) — không còn fallback cứng 50.
        return total_food_production_rate()

    def start_training(self, soldier_type: str, amount: int = 1) -> bool:
        """Bắt đầu huấn luyện. Trả về True nếu đủ điều kiện."""
        if soldier_type not in self.SOLDIER_STATS:
            return False
        if soldier_type == 'Lancer' and self._level < 3:
            return False

        # CHẶN TRAIN khi còn BẤT KỲ lính nào ở trạng thái "thiếu" (ở BẤT KỲ
        # trại nào — sổ lính dùng chung). Đang không nuôi/trang bị nổi lính cũ
        # thì không được đẻ thêm lính mới; lối thoát duy nhất là xây/nâng cấp
        # Farm hoặc Forge để kéo lính thiếu về idle trước.
        for _camp in _all_training_camps():
            _ensure_pools(_camp)
            if sum(_camp._hungry.values()) + sum(_camp._disarmed_soldiers.values()) > 0:
                return False

        stats = self.SOLDIER_STATS[soldier_type]
        queued_cost = sum(self.SOLDIER_STATS[s['type']]['train_cost'] for s in self._queue)
        new_cost = stats['train_cost'] * amount
        # Dùng upkeep SUY RA từ số lính thật, KHÔNG dùng `_current_food_upkeep`
        # (bộ đếm chỉ tăng, không bao giờ giảm khi lính chết — đã lỗi thời).
        #
        # `total_active_upkeep()` CÓ đếm lính trong hàng đợi (bắt buộc, để không
        # mất phần vũ khí đã `equip()` giữ chỗ cho họ). Nhưng công thức gate gốc
        # tính hàng đợi bằng `train_cost`, nên phải TRỪ phần upkeep của hàng đợi
        # ra khỏi baseline, tránh đếm họ hai lần (vừa upkeep vừa train_cost) —
        # nếu không sẽ siết điều kiện train chặt hơn bản gốc.
        queued_upkeep = sum(self.SOLDIER_STATS[s['type']]['upkeep'] for s in self._queue)
        base_upkeep = total_active_upkeep() - queued_upkeep
        if base_upkeep + queued_cost + new_cost >= self._get_total_food_production_rate():
            return False

        from systems.world_query import WorldQuery
        forges = [b for b in WorldQuery.get_all_buildings() if type(b).__name__ == 'Forge']
        if forges:
            gen_type, spec_type, wp_amount = self.WEAPON_COST[soldier_type]
            if not forges[0].equip(gen_type, spec_type, wp_amount * amount):
                return False

        for _ in range(amount):
            self._queue.append({'type': soldier_type, 'timer': stats['train_time']})
        return True

    def update(self, dt: float):
        """Chạy `Building.update()` gốc (chu kỳ sản xuất — TrainingCamp
        không thực sự "sản xuất" gì qua `produce()`, nhưng vẫn kế thừa
        timer/anim cho đồng nhất), rồi đếm ngược `timer` của TỪNG lính
        trong hàng đợi huấn luyện (`_queue`). Lính hết giờ (`timer <= 0`)
        → `_spawn_soldier()` (vào pool idle), bị loại khỏi `_queue`; lính
        chưa xong → giữ lại (`remaining`). Xây `_queue` MỚI mỗi frame thay
        vì xoá phần tử tại chỗ — tránh lỗi sửa list đang lặp."""
        super().update(dt)
        remaining = []
        for s in self._queue:
            s['timer'] -= dt
            if s['timer'] <= 0:
                self._spawn_soldier(s['type'])
            else:
                remaining.append(s)
        self._queue = remaining

    def _spawn_soldier(self, soldier_type: str):
        """Training done — soldier enters idle pool at camp (no entity yet)."""
        self._current_food_upkeep += self.SOLDIER_STATS[soldier_type]['upkeep']
        self._idle[soldier_type] = self._idle.get(soldier_type, 0) + 1

    def on_soldier_died(self, soldier_type: str):
        """Gọi khi lính chết — giảm upkeep và hoàn trả slot vũ khí."""
        upkeep = self.SOLDIER_STATS.get(soldier_type, {}).get('upkeep', 0.0)
        self._current_food_upkeep = max(0.0, self._current_food_upkeep - upkeep)
        from systems.world_query import WorldQuery
        forges = [b for b in WorldQuery.get_all_buildings() if type(b).__name__ == 'Forge']
        if forges:
            gen_type, spec_type, wp_amount = self.WEAPON_COST.get(soldier_type, ('soldier_weapon', 'sword', 0))
            forges[0].unequip(gen_type, spec_type, wp_amount)

    # --- API cho hệ thống ĐIỀU QUÂN THÁM HIỂM (THÊM MỚI) ---------------------
    # "Kho trại" = lính đã train xong, CHƯA điều đi tháp (self._idle). Dispatch
    # thám hiểm rút lính từ đây; rút về thì cộng lại. Public API để bên ngoài
    # không phải chạm _idle trực tiếp.
    def idle_count(self, soldier_type: str) -> int:
        """Số lính `soldier_type` sẵn sàng điều động — CHỈ CỦA TRẠI NÀY
        (khác `_idle_count()` module-level cộng dồn mọi trại)."""
        return max(0, self._idle.get(soldier_type, 0))

    def hungry_count(self, soldier_type: str) -> int:
        """Số lính `soldier_type` đang "đói" (đình chỉ do thiếu food) —
        CHỈ CỦA TRẠI NÀY. `getattr` guard cho instance cũ chưa có `_hungry`."""
        return max(0, getattr(self, '_hungry', {}).get(soldier_type, 0))

    def disarmed_soldier_count(self, soldier_type: str) -> int:
        """Số lính `soldier_type` đang "thiếu vũ khí" (đình chỉ) — CHỈ CỦA
        TRẠI NÀY. `getattr` guard cho instance cũ chưa có `_disarmed_soldiers`."""
        return max(0, getattr(self, '_disarmed_soldiers', {}).get(soldier_type, 0))

    def reserve_expedition(self, soldier_type: str, n: int) -> bool:
        """Rút `n` lính idle đi thám hiểm (trừ kho trại). False nếu không đủ."""
        n = int(n)
        if n <= 0 or self._idle.get(soldier_type, 0) < n:
            return False
        # Không rút lính đang ở trạng thái đói / thiếu vũ khí
        # (Thực ra idle count không bao gồm hungry/disarmed, nhưng cứ chắc chắn)
        self._idle[soldier_type] -= n
        return True

    def return_expedition(self, soldier_type: str, n: int) -> None:
        """Trả lính thám hiểm về kho trại (idle)."""
        if soldier_type in self._idle:
            self._idle[soldier_type] += max(0, int(n))
            
    def _total_soldier_upkeep(self) -> float:
        """Tổng upkeep TẤT CẢ lính còn sống (idle + hungry + disarmed + ĐANG
        THÁM HIỂM — vẫn đang ăn dù không có mặt tại trại, chỉ khác trạng thái
        điều động được hay không).

        FIX #1: settle_post_combat()/try_recover_soldiers() trước đây dùng
        `self._current_food_upkeep` — biến này CHỈ TĂNG (mỗi lần train lính
        qua `_spawn_soldier()`) và chỉ giảm qua `on_soldier_died()`, nhưng
        `on_soldier_died()` KHÔNG BAO GIỜ được gọi ở bất kỳ đâu trong code
        sống (lính chết trong combat thường không hề trừ lại upkeep). Hậu quả:
        sau mỗi trận có lính chết, `_current_food_upkeep` bị tính THỪA →
        food_deficit bị thổi phồng, lính bị đẩy vào "đói" sai và dồn lại qua
        nhiều trận.

        FIX #2: bản đầu của fix #1 chỉ cộng `_idle+_hungry+_disarmed`, BỎ SÓT
        lính đang đi thám hiểm (đã bị trừ khỏi `_idle` NGAY lúc điều đi qua
        `reserve_expedition()`, không phải lúc chết) → tính THIẾU. Hậu quả:
        lúc đang có lính đi thám hiểm, `try_recover_soldiers()` có thể tưởng
        dư lương thực (vì thiếu người trong phép tính) rồi giải "đói" cho lính
        khác — rồi ngay khi đội thám hiểm VỀ (cộng lại `_idle`), tổng cầu tăng
        đột ngột vượt quá sản lượng thật mà không ai kiểm tra lại → lính vừa
        hết đói lại rơi vào đói ngay, nhấp nháy trạng thái. Cộng thêm phần
        đang thám hiểm (`DispatchManager.total_dispatched_soldiers()`) vào đây
        để LUÔN tính đủ, bất kể lính đang ở đâu — khi họ chết giữa thám hiểm,
        party bị xoá khỏi DispatchManager nên lần tính TIẾP THEO tự động
        không còn đếm họ nữa (không cần trigger tính lại riêng lúc chết).

        Tính lại TƯƠI mỗi lần gọi (không cache) — luôn khớp đúng số lính THẬT
        SỰ đang tồn tại dù ở trại, đói, thiếu vũ khí, hay đang thám hiểm."""
        # FIX #3 (mô hình mới): lính "thiếu" KHÔNG ăn → phải LOẠI khỏi upkeep.
        # Đồng thời lính trong THÁP vẫn ăn → phải CỘNG (bản cũ bỏ sót, vì họ
        # đã rời `_idle` khi được điều vào tháp). Ủy quyền cho hàm module-level
        # `total_active_upkeep()` — nguồn sự thật duy nhất, suy ra từ số lính.
        return total_active_upkeep()

    def settle_post_combat(self, food_production: float = 0.0,
                           soldier_weapon_deficit: int = 0):
        """Quyết toán cuối trận — nay chỉ là vỏ mỏng gọi `reconcile_soldiers()`.

        Tham số giữ lại cho tương thích ngược nhưng KHÔNG dùng nữa: reconcile
        tự đọc `total_food_production_rate()` và `ResourceManager` tại thời
        điểm gọi, luôn tươi hơn giá trị caller truyền vào.

        Bản cũ chia đều bằng `ceil(deficit/3)` rồi `ceil(share/upkeep)` cho
        từng loại — làm tròn lên HAI lần, không tính lại sau mỗi con, và không
        chia lại target khi một loại hết lính. Với deficit 1.0 nó bỏ tới 4.6
        đơn vị lương thực (thừa 4.6 lần). Nay dùng thuật toán A đúng đặc tả.
        """
        reconcile_soldiers()

    def try_recover_soldiers(self, food_production: float = 0.0,
                             weapon_stock: int = 0, weapon_used: int = 0):
        """Kéo lính "thiếu" về idle — nay chỉ là vỏ mỏng gọi `reconcile_soldiers()`.

        Tham số giữ lại cho tương thích ngược nhưng KHÔNG dùng nữa (reconcile
        tự đọc số liệu tươi). Bản cũ ĐẾM HAI LẦN chi phí của lính được kéo về
        (baseline upkeep vẫn gồm lính `_disarmed` đang "ăn", baseline weapon
        vẫn gồm lính `_hungry` đang "giữ vũ khí"), và không chia đều theo loại.
        """
        reconcile_soldiers()


class RepairStation(Building):
    """Tự sửa tường 50 HP/section mỗi cycle."""

    REPAIR_AMOUNT = balance.REPAIR_STATION_AMOUNT  # HP sửa mỗi cycle

    def repair_walls(self, walls: list):
        """Gọi ở cuối mỗi wave."""
        for wall in walls:
            wall.repair_all(self.REPAIR_AMOUNT)