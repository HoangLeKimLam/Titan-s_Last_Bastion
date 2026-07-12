# characters/titans/priority.py
"""Hệ thống ưu tiên mục tiêu tấn công của Titan — Strategy Pattern.

Mỗi loại Titan có một "khẩu vị" mục tiêu khác nhau. Thay vì nhét
if/else vào trong class Titan, ta tách phần "chọn mục tiêu" ra thành
Strategy riêng. Đổi khẩu vị = đổi TargetPriorityStrategy.

Quy ước phân loại entity:
    Mọi mục tiêu tiềm năng đều có class constant `ENTITY_TYPE` ∈
    {'hq', 'wall', 'tower', 'soldier', 'commander'}.
    Priority đọc `ENTITY_TYPE` — không phụ thuộc các class cụ thể.
"""

import random
from config import balance
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Import lazy để tránh circular (systems → characters).
# Dùng _same_zone() helper bên dưới — gọi WorldQuery khi cần.
def _same_zone(ax, ay, bx, by) -> bool:
    """True nếu 2 điểm nằm CÙNG một vùng tường (Maria / Rose / Sina / field).

    Vì sao cần: nếu không check vùng, titan sẽ "nhìn xuyên tường" và khoá 1 lính
    ở vùng trong dù đang đứng ngoài → chạy húc đầu vào tường mãi. Check vùng ép
    titan phải PHÁ TƯỜNG trước rồi mới đánh được người bên trong.

    Thuật toán: uỷ quyền cho `WorldQuery.same_zone(..., strict=True)`.
    `strict=True` = không nới lỏng ở biên: đứng sát mép ngoài vẫn KHÔNG được coi
    là cùng vùng với bên trong.

    Import LAZY (bên trong hàm) để tránh vòng lặp import: systems → characters.

    Trả về: bool. Lỗi bất kỳ → True (fallback "cho phép"), vì chặn nhầm sẽ làm
    titan đứng đơ, nguy hiểm hơn là cho đánh nhầm.

    Liên kết: `systems/world_query.py::same_zone/zone_of`.
    """
    try:
        from systems.world_query import WorldQuery
        # Buộc Titan tuân thủ nghiêm ngặt vùng (strict=True)
        # để không tự ý khóa mục tiêu ngoài vùng dù đứng sát biên.
        return WorldQuery.same_zone(ax, ay, bx, by, strict=True)
    except Exception:
        return True   # fallback: coi như cùng zone (an toàn hơn là block)


def _wall_reachable(titan, entity) -> bool:
    """True nếu `entity` là tháp GẮN TƯỜNG và titan đang đứng ở 1 trong 2 vùng
    THỰC SỰ giáp đúng cây tường đó ("đánh được từ 2 phía" — nhưng chỉ 2 phía
    của TƯỜNG ĐÓ, không phải bất kỳ tường nào trên bản đồ).

    FIX: các chỗ gọi `getattr(entity, '_wall_name', None)` làm điều kiện OR
    riêng (bỏ qua zone check hoàn toàn hễ có `_wall_name`, không cần biết
    tường đó nằm ở đâu) khiến titan có thể khoá/nhắm 1 tháp gắn tường Ở BẤT
    KỲ VÙNG NÀO trên bản đồ — kể cả cách xa, khác vùng hoàn toàn với titan.
    Dùng hàm này thay thế: chỉ miễn zone check khi titan thực sự đứng cạnh
    ĐÚNG cây tường mà tháp đó gắn lên."""
    wall_name = getattr(entity, '_wall_name', None)
    if not wall_name:
        return False
    try:
        from systems.world_query import WorldQuery
        return WorldQuery.zone_of(titan.x, titan.y) in WorldQuery.zones_for_wall(wall_name)
    except Exception:
        return False   # an toàn hơn: không rõ vùng thì coi như KHÔNG miễn


# ── Hằng số ENTITY_TYPE ──────────────────────────────────────────

HQ        = 'hq'
WALL      = 'wall'
TOWER     = 'tower'
SOLDIER   = 'soldier'
COMMANDER = 'commander'

# Tầm "thù hằn" (px): titan chỉ phản đòn / khóa kẻ tấn công trong tầm này.
# Ngoài tầm → nhả lock, quay lại đường chính. Tránh bug "tách từ xa": 1 tháp/lính
# bắn titan 1 phát rồi titan đuổi nó xuyên cả bản đồ (vì _ai_attackers không bao
# giờ tự xóa). ~1.4× VISUAL_RANGE (250) để titan đang đánh nhau không flip-flop ở rìa.
AGGRO_RANGE = balance.PRIORITY_AGGRO_RANGE


# ─────────────────────────────────────────────────────────────────
#  TargetContext — ảnh chụp thế giới mà Titan "nhìn thấy"
# ─────────────────────────────────────────────────────────────────

@dataclass
class TargetContext:
    """Gói toàn bộ thông tin một Titan cần để chọn mục tiêu.

    AI/game loop dựng context, Priority chỉ ĐỌC.
    """

    hq:         object       = None
    walls:      list         = field(default_factory=list)
    towers:     list         = field(default_factory=list)
    soldiers:   list         = field(default_factory=list)
    commanders: list         = field(default_factory=list)

    # Visual range detection (phát hiện được nhìn thấy)
    visible_soldiers:   list = field(default_factory=list)
    visible_commanders: list = field(default_factory=list)
    visible_towers:     list = field(default_factory=list)

    blocking_wall: object    = None
    can_reach_hq:  bool      = False

    attackers:      list     = field(default_factory=list)
    current_target: object   = None


# ── Helper dùng chung ────────────────────────────────────────────

def _is_alive(entity) -> bool:
    """True nếu entity tồn tại VÀ còn sống.

    Gộp 2 phép kiểm tra hay quên: `is not None` và `is_alive`. Dùng `getattr`
    với mặc định False → object lạ không có cờ `is_alive` bị coi như đã chết
    (an toàn: không nhắm vào thứ không rõ).
    """
    return entity is not None and getattr(entity, 'is_alive', False)


def _type_of(entity) -> str:
    """Đọc `ENTITY_TYPE` của entity; trả '' nếu không có.

    Đây là mấu chốt để Priority KHÔNG phụ thuộc class cụ thể: nó chỉ so chuỗi
    ('hq'/'wall'/'tower'/'soldier'/'commander') chứ không `isinstance`. Thêm loại
    entity mới chỉ cần khai `ENTITY_TYPE`, không phải sửa file này.
    """
    return getattr(entity, 'ENTITY_TYPE', '')


def _distance(a, b) -> float:
    """Khoảng cách Euclid (px) giữa 2 entity.

    Dùng `sqrt` thật (không phải bình phương) vì kết quả được đem SO SÁNH với
    `AGGRO_RANGE` tính bằng px.
    """
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _nearest(origin, candidates: list):
    """Trả entity CÒN SỐNG gần `origin` nhất; None nếu danh sách rỗng/chết hết.

    Thuật toán: lọc `_is_alive` → `min()` theo `_distance`. Lọc trước rồi mới
    min để không bao giờ trả về xác chết.
    """
    alive = [e for e in candidates if _is_alive(e)]
    if not alive:
        return None
    return min(alive, key=lambda e: _distance(origin, e))


def _same_zone_only(titan, candidates: list) -> list:
    """Lọc `candidates` chỉ giữ entity CÙNG ZONE với titan — dùng khi titan
    CHỦ ĐỘNG chọn soldier/commander (không phải phản ứng lại kẻ tấn công).
    `context.visible_soldiers`/`visible_commanders` chỉ lọc theo khoảng cách
    (VISUAL_RANGE), KHÔNG lọc theo zone/tường — nếu dùng thẳng, titan có thể
    "nhìn xuyên tường" nhắm 1 lính/tướng ở vùng khác đứng đủ gần."""
    return [c for c in candidates if _same_zone(titan.x, titan.y, c.x, c.y)]


def _attackers_of_types(titan, context: TargetContext, types: tuple):
    """Chọn KẺ ĐANG TẤN CÔNG titan (gần nhất) thuộc các loại `types` — đòn phản công.

    Thuật toán, giữ lại 1 attacker chỉ khi thoả ĐỦ 3 điều kiện:
      1. Còn sống VÀ `ENTITY_TYPE` nằm trong `types`.
      2. Khoảng cách <= `AGGRO_RANGE` — hết tầm thù hằn thì QUÊN, quay về phá
         tường. Đây là thứ chặn bug "tách từ xa": 1 tháp bắn tỉa titan 1 phát rồi
         titan đuổi nó xuyên bản đồ.
      3. Cùng vùng, HOẶC là ĐÚNG tháp gắn trên cây tường giáp vùng titan
         (`_wall_reachable`). Khác vùng (nấp sau tường) → bỏ qua, titan phá tường.
    Rồi lấy cái GẦN NHẤT.

    Tham số:
        types: tuple ENTITY_TYPE được phép phản đòn. Mỗi Priority tự định nghĩa
            `_reactive_types` khác nhau (vd Kamikaze chỉ phản đòn TOWER).

    Trả về: entity hoặc None.
    """
    hits = []
    for a in context.attackers:
        if not (_is_alive(a) and _type_of(a) in types and _distance(titan, a) <= AGGRO_RANGE):
            continue
        # Chỉ đánh trả nếu mục tiêu ở cùng vùng (hoặc là ĐÚNG tháp trên tường
        # giáp vùng titan đang đứng — _wall_reachable(), không phải bất kỳ
        # tháp tường nào trên bản đồ). Nếu khác vùng (sau bức tường), bỏ qua
        # để titan tập trung phá tường.
        if _wall_reachable(titan, a) or _same_zone(titan.x, titan.y, a.x, a.y):
            hits.append(a)
    return _nearest(titan, hits)


# ─────────────────────────────────────────────────────────────────
#  TargetPriorityStrategy — ABC
# ─────────────────────────────────────────────────────────────────

class TargetPriorityStrategy(ABC):
    """Hợp đồng cho mọi bộ ưu tiên chọn mục tiêu của Titan."""

    _reactive_types: tuple = (TOWER, SOLDIER, COMMANDER)

    @abstractmethod
    def select_target(self, titan, context: TargetContext):
        """Chọn 1 mục tiêu cho titan trong frame này — MỌI Priority phải override.

        Tham số:
            titan: titan đang chọn (đọc x, y, và cờ riêng như `_armor_intact`).
            context: `TargetContext` — ảnh chụp thế giới, CHỈ ĐỌC.

        Trả về: entity mục tiêu, hoặc None nếu không có gì để đánh.

        Liên kết: được gọi mỗi frame bởi `TitanAI.decide()` (ai.py); context do
        `WorldQueryView.build_context()` (game.py) dựng.
        """
        ...

    def _locked_reactive_target(self, titan, context: TargetContext):
        """Lock logic:
        - Nếu đang attack (in attackers) và còn trong AGGRO_RANGE → LOCK
        - Nếu KHÔNG attack → chỉ lock nếu trong visual range
        """
        ct = context.current_target
        if not (_is_alive(ct) and _type_of(ct) in self._reactive_types):
            return None

        # Ngoài tầm thù hằn → nhả lock (tránh đuổi mục tiêu xuyên bản đồ "tách từ xa")
        if _distance(titan, ct) > AGGRO_RANGE:
            return None

        # Rule 1: Nếu đang attack (và trong tầm) → lock
        # CHỈ lock nếu ở cùng vùng (hoặc là tháp trên tường). Nếu khác vùng thì nhả lock
        # để tránh titan nhắm tới rồi bị kẹt/flicker với tường.
        if ct in context.attackers:
            if _wall_reachable(titan, ct) or _same_zone(titan.x, titan.y, ct.x, ct.y):
                if _type_of(ct) == COMMANDER:
                    # visible_towers không liên quan đến commander — chỉ check soldier/commander
                    in_vis = ct in (context.visible_soldiers + context.visible_commanders)
                    return ct if in_vis else None
                return ct
            return None

        # Rule 2: Nếu KHÔNG attack → chỉ lock nếu còn trong visual range VÀ
        # cùng vùng (visible_soldiers/commanders chỉ lọc khoảng cách, KHÔNG
        # lọc zone — thiếu check zone ở đây trước đây khiến titan giữ khoá 1
        # lính/tướng khác vùng miễn còn trong tầm nhìn thẳng).
        # visible_towers không liên quan đến soldier/commander
        in_visible = ct in (context.visible_soldiers + context.visible_commanders)
        if not in_visible:
            return None
        return ct if _same_zone(titan.x, titan.y, ct.x, ct.y) else None

    def _path_target(self, context: TargetContext):
        """Mục tiêu "đi đường chính": HQ nếu đường thông, nếu không thì tường đang cản.

        Đây là hành vi NỀN của mọi titan khi không có gì hấp dẫn hơn: cắm đầu về
        HQ; gặp tường chắn thì đập tường đó.

        Thuật toán:
            `can_reach_hq` (do WorldQuery tính, không có tường chắn giữa đường)
            → nhắm HQ. Ngược lại → nhắm `blocking_wall` (đoạn tường chắn đường).
            Cả 2 đều chết/không có → None.

        Liên kết: `can_reach_hq` và `blocking_wall` do
        `WorldQuery.find_blocking_wall()` tính, đóng gói vào context (game.py).
        """
        if context.can_reach_hq and _is_alive(context.hq):
            return context.hq
        if _is_alive(context.blocking_wall):
            return context.blocking_wall
        return None

    # Giây chờ giữa 2 lần roll 50% khi titan bỏ qua visible target
    _VIS_ROLL_COOLDOWN = balance.PRIORITY_VIS_ROLL_COOLDOWN

    def _maybe_visible_target(self, titan, context: TargetContext):
        """50% chance rẽ sang visible soldier/commander khi không có target khác.

        Cooldown 2s giữa các lần roll — titan không flip-flop mỗi frame.
        Roll True → nhắm nearest visible + đặt cooldown (tránh rẽ lại ngay khi lính chết).
        Roll False → đặt cooldown, titan tiếp tục đường cũ.
        """
        candidates = _same_zone_only(titan, [
            u for u in (context.visible_soldiers + context.visible_commanders)
            if _is_alive(u)])
        if not candidates:
            return None

        # Trong cooldown → không roll
        cd = getattr(titan, '_vis_roll_cd', 0.0)
        if cd > 0.0:
            return None

        # Đặt cooldown dù thành công hay thất bại — tránh flip-flop liên tục
        titan._vis_roll_cd = self._VIS_ROLL_COOLDOWN
        if random.random() > 0.5:
            return None

        return _nearest(titan, candidates)


# ─────────────────────────────────────────────────────────────────
#  DefaultPriority
# ─────────────────────────────────────────────────────────────────

class DefaultPriority(TargetPriorityStrategy):
    """Bộ ưu tiên mặc định — RegularTitan, ArmoredTitan (thường).

    Thứ tự: locked(visual/attacker) → reactive(attacker) → visible soldier/cmd(50%) → path(HQ/Wall) → HQ fallback.
    """

    def select_target(self, titan, context: TargetContext):
        """Chọn mục tiêu cho titan thường — thang ưu tiên 5 bậc, dừng ở bậc đầu trúng.

        Thứ tự (return ngay khi có kết quả):
          1. `_locked_reactive_target` — đang khoá ai thì giữ khoá (chống đổi mục
             tiêu loạn xạ mỗi frame).
          2. `_attackers_of_types` — ai đang đánh mình thì đánh trả (gần nhất).
          3. `_maybe_visible_target` — 50% ngẫu nhiên rẽ sang lính/tướng nhìn thấy
             (có cooldown 2s), tạo cảm giác titan "bị phân tâm" chứ không như robot.
          4. `_path_target` — không có gì → về HQ / đập tường chắn.
          5. Fallback: HQ.

        Ai dùng: RegularTitan (và mặc định cho titan không có Priority riêng).
        """
        locked = self._locked_reactive_target(titan, context)
        if locked is not None:
            return locked

        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        visible = self._maybe_visible_target(titan, context)
        if visible is not None:
            return visible

        path = self._path_target(context)
        if path is not None:
            return path

        return context.hq if _is_alive(context.hq) else None


# ─────────────────────────────────────────────────────────────────
#  ArmoredPriority
# ─────────────────────────────────────────────────────────────────

class ArmoredPriority(TargetPriorityStrategy):
    """Bộ ưu tiên ArmoredTitan — "cỗ máy phá thành".

    Còn giáp: Wall TUYỆT ĐỐI → HQ (đường thông). Bỏ qua reactive khi còn giáp.
    Giáp vỡ: mở reactive Tower/Soldier/Commander → HQ → Wall.
    """

    _reactive_types = (TOWER, SOLDIER, COMMANDER)

    def select_target(self, titan, context: TargetContext):
        """Chọn mục tiêu cho ArmoredTitan — hành vi ĐỔI HẲN khi giáp vỡ.

        CÒN GIÁP (`titan._armor_intact` True) — "cỗ máy phá thành", MẶC KỆ bị bắn:
          1. Có tường chắn → đập tường (TUYỆT ĐỐI, bỏ qua mọi phản đòn).
          2. Đường thông → húc thẳng HQ.
          (Không hề gọi `_locked_reactive_target`/`_attackers_of_types` → lính và
           tháp bắn nó cũng vô ích trong việc kéo aggro.)

        GIÁP ĐÃ VỠ — hạ cấp thành titan thường, mở phản đòn:
          3. locked → 4. phản đòn (tower/soldier/commander) → 5. visible 50%
          → 6. HQ nếu thông → 7. tường → 8. HQ fallback.

        Liên kết: cờ `_armor_intact` do `ArmoredTitan.take_damage()` hạ xuống sau
        `_HITS_TO_BREAK` đòn (titan.py ← balance.ARMORED_TITAN_HITS_TO_BREAK).
        Chiến thuật: muốn kéo aggro Armored, người chơi PHẢI phá giáp trước.
        """
        armor_intact = bool(getattr(titan, '_armor_intact', True))

        if armor_intact and _is_alive(context.blocking_wall):
            return context.blocking_wall

        if armor_intact and context.can_reach_hq and _is_alive(context.hq):
            return context.hq

        locked = self._locked_reactive_target(titan, context)
        if locked is not None:
            return locked
        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        visible = self._maybe_visible_target(titan, context)
        if visible is not None:
            return visible

        if context.can_reach_hq and _is_alive(context.hq):
            return context.hq

        if _is_alive(context.blocking_wall):
            return context.blocking_wall

        return context.hq if _is_alive(context.hq) else None


# ─────────────────────────────────────────────────────────────────
#  BeastPriority
# ─────────────────────────────────────────────────────────────────

class BeastPriority(TargetPriorityStrategy):
    """Bộ ưu tiên BeastTitan — "thợ săn tháp tầm xa" (ném đá).

    Khác mọi titan khác: Beast CHỦ ĐỘNG đi tìm tháp để ném, không cần bị bắn
    trước. Thứ tự chủ động: Tower → Soldier → Commander → Wall → HQ.
    """

    def select_target(self, titan, context: TargetContext):
        """Chọn mục tiêu cho Beast — ưu tiên tuyệt đối là THÁP.

        Thuật toán:
          1. GIỮ KHOÁ tháp đang nhắm nếu: còn sống, là TOWER, VÀ (trong
             `AGGRO_RANGE` HOẶC là wall-tower giáp vùng), VÀ cùng vùng (hoặc
             wall-tower giáp vùng). Giữ khoá để Beast ném hết loạt đá vào 1 tháp
             thay vì đổi mục tiêu giữa chừng.
          2. Chưa khoá → tháp GẦN NHẤT trong `visible_towers` (đã lọc
             VISUAL_RANGE) và cùng vùng.
             LƯU Ý: quét `visible_towers` chứ KHÔNG phải `context.towers` (toàn
             bản đồ) — nếu quét toàn bản đồ, Beast sẽ "thấy" tháp cách rất xa
             trong cùng vùng lớn và chạy tới, rất vô lý.
          3. Hết tháp → lính gần nhất (cùng vùng) → tướng gần nhất (cùng vùng).
          4. Cuối cùng → tường chắn → HQ.

        Chỉ số: balance.PRIORITY_AGGRO_RANGE, balance.TITAN_VISUAL_RANGE,
        balance.BEAST_ATTACK_RANGE (tầm ném đá 350px).
        """
        ct = context.current_target
        # Lock tower hiện tại chỉ khi cùng zone HOẶC là ĐÚNG wall-tower giáp
        # vùng titan đang đứng (_wall_reachable — không phải bất kỳ tường nào
        # trên bản đồ, xem docstring hàm đó).
        if (_is_alive(ct) and _type_of(ct) == TOWER
                and (_distance(titan, ct) <= AGGRO_RANGE
                     or _wall_reachable(titan, ct))
                and (_wall_reachable(titan, ct)
                     or _same_zone(titan.x, titan.y, ct.x, ct.y))):
            return ct

        # Nearest tower trong TẦM NHÌN (visible_towers, không phải toàn bản
        # đồ) VÀ cùng zone (hoặc ĐÚNG wall-tower giáp vùng titan) — THÊM MỚI:
        # trước đây quét context.towers (mọi tháp trên TOÀN BẢN ĐỒ, không
        # giới hạn khoảng cách) — chỉ lọc zone thôi, khiến titan "thấy" được
        # tháp cách rất xa trong cùng 1 vùng lớn, vô lý. Giờ giới hạn thêm
        # trong tầm nhìn (VISUAL_RANGE) giống hệt cách soldier/commander đã
        # làm (_same_zone_only(titan, context.visible_soldiers)).
        tower = _nearest(titan, [
            t for t in context.visible_towers
            if _is_alive(t) and (_wall_reachable(titan, t)
                                 or _same_zone(titan.x, titan.y, t.x, t.y))
        ])
        if tower is not None:
            return tower

        soldier = _nearest(titan, _same_zone_only(titan, context.visible_soldiers))
        if soldier is not None:
            return soldier

        commander = _nearest(titan, _same_zone_only(titan, context.visible_commanders))
        if commander is not None:
            return commander

        if _is_alive(context.blocking_wall):
            return context.blocking_wall

        if _is_alive(context.hq):
            return context.hq

        return None


# ─────────────────────────────────────────────────────────────────
#  KamikazePriority
# ─────────────────────────────────────────────────────────────────

class KamikazePriority(TargetPriorityStrategy):
    """Bộ ưu tiên Kamikaze — "bom tự sát săn lính".

    Thứ tự: Soldier/Commander (chủ động) → Tower (phản ứng) → HQ/Wall.
    """

    _reactive_types = (TOWER,)

    def select_target(self, titan, context: TargetContext):
        """Chọn mục tiêu cho Kamikaze — "bom tự sát", săn NGƯỜI trước hết.

        Thuật toán:
          1. CHỦ ĐỘNG: lính/tướng gần nhất nhìn thấy được và CÙNG VÙNG → lao vào
             (đây là mồi ngon nhất; nổ giữa cụm lính là hiệu quả nhất).
          2. Không có người → mới xét phản đòn, và `_reactive_types = (TOWER,)`
             thôi: Kamikaze CHỈ phản đòn tháp, KHÔNG bị lính/tướng kéo aggro
             (vì nếu có người thì bước 1 đã bắt rồi).
          3. → `_path_target` (HQ / tường) → HQ → tường.

        Lưu ý: chọn mục tiêu ở đây chỉ để BAY TỚI. Việc nổ do
        `KamikazeAI` quyết định khi vào `_EXPLODE_RADIUS`, và lúc nổ thì
        `Explosion.execute()` đánh theo VÙNG — target ban đầu có thể né được.

        Chỉ số: balance.KAMIKAZE_DETECT_RADIUS / _EXPLODE_RADIUS.
        """
        prey = _nearest(titan, _same_zone_only(
            titan, context.visible_soldiers + context.visible_commanders))
        if prey is not None:
            return prey

        locked = self._locked_reactive_target(titan, context)
        if locked is not None:
            return locked
        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        path = self._path_target(context)
        if path is not None:
            return path

        if _is_alive(context.hq):
            return context.hq
        if _is_alive(context.blocking_wall):
            return context.blocking_wall

        return None


# ─────────────────────────────────────────────────────────────────
#  SoldierHunterPriority
# ─────────────────────────────────────────────────────────────────

class SoldierHunterPriority(TargetPriorityStrategy):
    """Bộ ưu tiên SoldierHunter — "khắc tinh bộ binh".

    Thứ tự: Soldier trong visual range (chủ động) → Tower/Commander (phản ứng) → HQ/Wall.
    """

    _reactive_types = (TOWER, COMMANDER)

    def select_target(self, titan, context: TargetContext):
        """Chọn mục tiêu cho SoldierHunter — "khắc tinh bộ binh".

        Thuật toán:
          1. CHỦ ĐỘNG: LÍNH gần nhất trong tầm nhìn + cùng vùng (chỉ
             `visible_soldiers`, KHÔNG thèm tướng ở bước này).
          2. Hết lính → locked → phản đòn với `_reactive_types = (TOWER, COMMANDER)`
             (tức là tướng chỉ bị nhắm khi tướng ĐÁNH nó trước).
          3. → visible 50% → `_path_target`.
          4. Không có gì → None (khác Default: KHÔNG fallback về HQ).

        Kết hợp với `SoldierHunterStrategy` (cleave AoE) → cực nguy hiểm khi lính
        đứng cụm: 1 đòn trúng lính chính + lan nửa damage ra tường/tháp/HQ quanh đó.
        """
        prey = _nearest(titan, _same_zone_only(titan, context.visible_soldiers))
        if prey is not None:
            return prey

        locked = self._locked_reactive_target(titan, context)
        if locked is not None:
            return locked
        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        visible = self._maybe_visible_target(titan, context)
        if visible is not None:
            return visible

        path = self._path_target(context)
        if path is not None:
            return path

        return None


# ─────────────────────────────────────────────────────────────────
#  TowerHunterPriority
# ─────────────────────────────────────────────────────────────────

class TowerHunterPriority(TargetPriorityStrategy):
    """Bộ ưu tiên TowerHunter — "kẻ công thành phá tháp".

    Thứ tự: Tower (chủ động, khóa tới chết) → Soldier/Commander (phản ứng) → HQ/Wall.
    """

    _reactive_types = (SOLDIER, COMMANDER)

    def select_target(self, titan, context: TargetContext):
        """Chọn mục tiêu cho TowerHunter — "kẻ công thành", khoá tháp tới chết.

        Thuật toán (giống BeastPriority ở 2 bước đầu, khác ở phần sau):
          1. GIỮ KHOÁ tháp đang nhắm (còn sống + trong AGGRO_RANGE/wall-tower +
             cùng vùng) → không đổi mục tiêu giữa chừng.
          2. Tháp GẦN NHẤT trong `visible_towers` + cùng vùng (không quét toàn
             bản đồ — xem ghi chú ở BeastPriority).
          3. Hết tháp → phản đòn với `_reactive_types = (SOLDIER, COMMANDER)`
             (lính/tướng chỉ được nhắm nếu ĐÁNH nó trước).
          4. → visible 50% → `_path_target` → None.

        Kết hợp `TowerHunterStrategy` (×1.5 damage khi mục tiêu là Tower) → sát
        thủ chuyên phá tháp.
        Chỉ số: balance.STRAT_TOWER_HUNTER_MULT, balance.TOWER_HUNTER_*.
        """
        ct = context.current_target
        # Lock tower hiện tại chỉ khi cùng zone HOẶC là ĐÚNG wall-tower giáp
        # vùng titan đang đứng (_wall_reachable — không phải bất kỳ tường nào
        # trên bản đồ, xem docstring hàm đó).
        if (_is_alive(ct) and _type_of(ct) == TOWER
                and (_distance(titan, ct) <= AGGRO_RANGE
                     or _wall_reachable(titan, ct))
                and (_wall_reachable(titan, ct)
                     or _same_zone(titan.x, titan.y, ct.x, ct.y))):
            return ct

        # Nearest tower trong TẦM NHÌN (visible_towers, không phải toàn bản
        # đồ) VÀ cùng zone (hoặc ĐÚNG wall-tower giáp vùng titan) — THÊM MỚI:
        # trước đây quét context.towers (mọi tháp trên TOÀN BẢN ĐỒ, không
        # giới hạn khoảng cách) — chỉ lọc zone thôi, khiến titan "thấy" được
        # tháp cách rất xa trong cùng 1 vùng lớn, vô lý. Giờ giới hạn thêm
        # trong tầm nhìn (VISUAL_RANGE) giống hệt cách soldier/commander đã
        # làm (_same_zone_only(titan, context.visible_soldiers)).
        tower = _nearest(titan, [
            t for t in context.visible_towers
            if _is_alive(t) and (_wall_reachable(titan, t)
                                 or _same_zone(titan.x, titan.y, t.x, t.y))
        ])
        if tower is not None:
            return tower

        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        visible = self._maybe_visible_target(titan, context)
        if visible is not None:
            return visible

        path = self._path_target(context)
        if path is not None:
            return path

        return None


# ─────────────────────────────────────────────────────────────────
#  WolfPriority
# ─────────────────────────────────────────────────────────────────

class WolfPriority(TargetPriorityStrategy):
    """Bộ ưu tiên Wolf — giống DefaultPriority nhưng thèm Commander hơn.

    Thứ tự: HQ (thông) → Wall cản → Commander (phản ứng ưu tiên cao)
    → Tower/Soldier (phản ứng) → HQ fallback.
    """

    _reactive_types = (COMMANDER, TOWER, SOLDIER)

    def select_target(self, titan, context: TargetContext):
        """Chọn mục tiêu cho Wolf — như titan thường nhưng THÈM TƯỚNG hơn hẳn.

        Thuật toán:
          1. locked → giữ khoá.
          2. Phản đòn TƯỚNG trước (`_attackers_of_types(..., (COMMANDER,))`) —
             tách riêng thành 1 bước ĐỨNG TRƯỚC, nên nếu vừa có tướng vừa có
             tháp/lính đang đánh nó, Wolf luôn quay sang cắn TƯỚNG.
          3. Rồi mới phản đòn tháp/lính.
          4. → visible 50% → `_path_target` → HQ fallback.

        Vì sao nguy hiểm: Wolf mang `Incurable` (dtype='antiheal') → cắn trúng
        tướng là CHẶN HỒI MÁU tướng 15s (balance.COMMANDER_ANTI_HEAL_DURATION),
        kể cả hồi máu ở vùng castle. Đây là combo Priority + Strategy có chủ đích.
        """
        locked = self._locked_reactive_target(titan, context)
        if locked is not None:
            return locked

        by_commander = _attackers_of_types(titan, context, (COMMANDER,))
        if by_commander is not None:
            return by_commander

        by_tower_soldier = _attackers_of_types(titan, context, (TOWER, SOLDIER))
        if by_tower_soldier is not None:
            return by_tower_soldier

        visible = self._maybe_visible_target(titan, context)
        if visible is not None:
            return visible

        path = self._path_target(context)
        if path is not None:
            return path

        return context.hq if _is_alive(context.hq) else None


# ─────────────────────────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────────────────────────

PRIORITY_BY_TITAN: dict = {
    'ArmoredTitan':  ArmoredPriority,
    'BeastTitan':    BeastPriority,
    'Kamikaze':      KamikazePriority,
    'SoldierHunter': SoldierHunterPriority,
    'TowerHunter':   TowerHunterPriority,
    'Wolf':          WolfPriority,
}


def make_priority_for(titan) -> TargetPriorityStrategy:
    """FACTORY: tạo bộ ưu tiên đúng "khẩu vị" cho `titan`.

    Thuật toán: tra `PRIORITY_BY_TITAN` bằng TÊN CLASS của titan
    (`type(titan).__name__`), không có trong bảng → `DefaultPriority`.

    Vì sao tra theo tên chuỗi thay vì isinstance: tránh phải import mọi class
    titan vào file này (sẽ gây vòng lặp import titan.py ↔ priority.py).

    Thêm titan mới muốn có khẩu vị riêng:
      1. Viết class `XxxPriority(TargetPriorityStrategy)` trong file này.
      2. Thêm 1 dòng vào `PRIORITY_BY_TITAN`: `'TenClassTitan': XxxPriority`.
      Không cần sửa gì trong titan.py/ai.py.

    Liên kết: được gọi bởi `titan.py` / `ai.py` lúc tạo titan.
    """
    cls = PRIORITY_BY_TITAN.get(type(titan).__name__, DefaultPriority)
    return cls()
