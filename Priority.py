# Priority.py — Hệ thống ưu tiên mục tiêu tấn công của Titan
#
# Tại sao cần file này?
#     Mỗi loại Titan có một "khẩu vị" mục tiêu khác nhau: Titan thường luôn
#     hướng về HQ, ArmoredTitan thèm phá tường, Beast săn tháp, Kamikaze lao
#     vào lính... Thay vì nhét hàng tá if/else "tôi là loại nào → đánh ai"
#     vào trong class Titan, ta tách phần "chọn mục tiêu" ra thành Strategy
#     riêng — y hệt cách `AttackStrategy.py` tách phần "đánh như thế nào".
#
#     => Đổi khẩu vị mục tiêu = đổi TargetPriorityStrategy, không sửa Titan.
#
# Ai gọi?
#     Hiện tại CHƯA gắn vào `Titan.update()` — phần AI sẽ nối sau. File này
#     đứng độc lập, tự kiểm thử được. Khi dựng AI, mỗi Titan sẽ HAS-A một
#     `TargetPriorityStrategy` và gọi `strategy.select_target(self, context)`
#     mỗi frame để biết nên đánh ai.
#
# Quy ước phân loại entity:
#     Mọi mục tiêu tiềm năng (HQ, Wall, Tower, Soldier, Commander) đều có
#     thuộc tính string `entity_type` ∈ {'hq', 'wall', 'tower', 'soldier',
#     'commander'}. Priority chỉ đọc `entity_type` — không phụ thuộc các
#     class Tower/WallSection/... (vốn chưa được dựng trong dự án).
#
# Ví dụ dùng (khi đã có AI):
#     ctx = TargetContext(hq=hq, towers=towers, soldiers=soldiers, ...)
#     titan._priority = ArmoredPriority()
#     muc_tieu = titan._priority.select_target(titan, ctx)

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ── Hằng số entity_type ──────────────────────────────────────────
# Gom lại 1 chỗ thay vì rải "magic string" khắp file.

HQ        = 'hq'
WALL      = 'wall'
TOWER     = 'tower'
SOLDIER   = 'soldier'
COMMANDER = 'commander'


# ─────────────────────────────────────────────────────────────────
#  TargetContext — ảnh chụp thế giới mà Titan "nhìn thấy"
# ─────────────────────────────────────────────────────────────────

@dataclass
class TargetContext:
    """Gói toàn bộ thông tin một Titan cần để chọn mục tiêu.

    Tại sao gói thành 1 object thay vì truyền rời từng tham số?
        `select_target(titan, context)` chỉ có 2 tham số — sau này thêm
        dữ liệu mới (vd 'buildings') chỉ cần thêm field, không phải sửa
        chữ ký của cả 7 strategy con.

    Ai dựng context?
        Phần AI / game loop (sau này). Priority.py chỉ ĐỌC, không tự
        truy vấn WorldQuery — nhờ vậy test được độc lập.

    Quy ước dữ liệu:
        • Các danh sách (walls, towers...) chứa MỌI entity còn tồn tại
          trên map — KHÔNG cần lọc trước. Priority tự bỏ qua entity đã
          chết (`is_alive == False`).
        • `blocking_wall` và `can_reach_hq` là kết quả pathfinding do
          AI/WorldQuery tính sẵn — Priority không tự tính hình học.
        • `attackers` là các entity ĐANG tấn công titan này (do Titan
          ghi lại trong `take_damage`). Dùng cho luật "chỉ đánh Tower/
          Soldier khi bị chúng tấn công".
        • `current_target` là mục tiêu titan đang đánh ở frame trước —
          cần cho cơ chế "khóa mục tiêu" (lock).
    """

    hq:         object       = None   # entity HQ (entity_type='hq')
    walls:      list         = field(default_factory=list)
    towers:     list         = field(default_factory=list)
    soldiers:   list         = field(default_factory=list)
    commanders: list         = field(default_factory=list)

    # Kết quả pathfinding (AI tính sẵn)
    blocking_wall: object    = None    # Wall đang chắn đường tới HQ, None nếu thông
    can_reach_hq:  bool      = False   # True nếu có đường vào thẳng HQ

    # Trạng thái chiến đấu
    attackers:      list     = field(default_factory=list)  # ai đang đánh titan
    current_target: object   = None    # mục tiêu titan đang khóa (frame trước)


# ── Helper dùng chung ────────────────────────────────────────────

def _is_alive(entity) -> bool:
    """True nếu entity tồn tại và còn sống.

    Dùng `getattr` để an toàn cả với mock entity thiếu thuộc tính.
    """
    return entity is not None and getattr(entity, 'is_alive', False)


def _type_of(entity) -> str:
    """Đọc `entity_type` của entity; trả '' nếu không có.

    Priority phân loại mục tiêu hoàn toàn qua string này.
    """
    return getattr(entity, 'entity_type', '')


def _distance(a, b) -> float:
    """Khoảng cách Euclid giữa 2 entity (theo x, y)."""
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _nearest(origin, candidates: list):
    """Trả entity còn sống gần `origin` nhất; None nếu danh sách rỗng.

    Dùng cho luật "bị nhiều kẻ tấn công cùng lúc → đánh kẻ gần nhất".
    """
    alive = [e for e in candidates if _is_alive(e)]
    if not alive:
        return None
    return min(alive, key=lambda e: _distance(origin, e))


def _attackers_of_types(titan, context: TargetContext, types: tuple):
    """Lọc danh sách attacker, chỉ giữ những kẻ thuộc `types` và còn sống,
    rồi trả về kẻ GẦN titan nhất.

    Đây là khối dùng lại của hầu hết priority: "nếu đang bị <loại X>
    tấn công thì quay sang đánh kẻ gần nhất trong số đó".
    """
    hits = [a for a in context.attackers
            if _is_alive(a) and _type_of(a) in types]
    return _nearest(titan, hits)


# ─────────────────────────────────────────────────────────────────
#  TargetPriorityStrategy — ABC cho mọi bộ ưu tiên
# ─────────────────────────────────────────────────────────────────

class TargetPriorityStrategy(ABC):
    """Hợp đồng cho mọi bộ ưu tiên chọn mục tiêu của Titan.

    Titan HAS-A một strategy loại này. Đổi strategy → đổi khẩu vị mục
    tiêu, không cần sửa class Titan.

    Method bắt buộc: `select_target(titan, context)` → entity | None.
    """

    # Các loại mục tiêu mà titan CHỈ đánh khi bị chúng tấn công trước.
    # Mặc định: Tower + Soldier (theo luật chung). Class con ghi đè nếu
    # khẩu vị khác (vd Wolf coi Commander là mục tiêu chủ động).
    _reactive_types: tuple = (TOWER, SOLDIER)

    @abstractmethod
    def select_target(self, titan, context: TargetContext):
        """Chọn mục tiêu titan nên đánh ở frame này.

        Tham số:
            titan: con Titan đang cần mục tiêu (có .x, .y, .is_alive).
            context: TargetContext — ảnh chụp thế giới.

        Trả về:
            entity mục tiêu, hoặc None nếu không có gì để đánh.
        """
        ...

    # ── Khối dùng lại cho các class con ──────────────────────────

    def _locked_reactive_target(self, context: TargetContext):
        """Cơ chế KHÓA MỤC TIÊU cho Tower/Soldier.

        Luật chung: khi titan đã quay sang đánh một Tower/Soldier, nó
        "khóa" mục tiêu đó — đánh đến chết mới đổi. Hàm này kiểm tra
        `current_target`: nếu nó là Tower/Soldier và còn sống thì giữ
        nguyên (trả lại chính nó); ngược lại trả None để caller chọn mới.

        `_reactive_types` quyết định loại nào được coi là "đáng khóa".
        """
        ct = context.current_target
        if _is_alive(ct) and _type_of(ct) in self._reactive_types:
            return ct
        return None

    def _path_target(self, context: TargetContext):
        """Mục tiêu theo "đường tiến về HQ" — phần lõi của khẩu vị
        chung: vào thẳng HQ nếu được, không thì phá Wall đang cản.

        Trả None nếu cả hai đều không khả dụng (caller fallback tiếp).
        """
        if context.can_reach_hq and _is_alive(context.hq):
            return context.hq
        if _is_alive(context.blocking_wall):
            return context.blocking_wall
        return None


# ─────────────────────────────────────────────────────────────────
#  DefaultPriority — luật chung cho Titan thường
# ─────────────────────────────────────────────────────────────────

class DefaultPriority(TargetPriorityStrategy):
    """Bộ ưu tiên mặc định — áp dụng cho RegularTitan, ArmoredTitan
    (giai đoạn thường) và các Titan dùng luật chung.

    Thứ tự ưu tiên (cao → thấp):
        1. HQ — nếu có đường vào thẳng.
        2. WallSection — nếu đang cản đường tiến vào HQ.
        3. Tower / Soldier — NGANG nhau; chỉ đánh khi chúng tấn công
           titan. Khi đã khóa một con thì đánh tới chết mới đổi.
        4. Fallback: luôn quay về HQ.

    Lưu ý cơ chế ngắt:
        Dù đang trên đường tới HQ/Wall, NẾU titan bị Tower/Soldier
        tấn công thì lập tức chuyển sự chú ý sang chúng (mục 3 chèn
        lên trên mục 1, 2). Đây là lý do `_reactive` được kiểm tra
        TRƯỚC `_path_target`.
    """

    def select_target(self, titan, context: TargetContext):
        # (3) Đang khóa một Tower/Soldier còn sống → giữ tới khi nó chết.
        locked = self._locked_reactive_target(context)
        if locked is not None:
            return locked

        # (3) Bị Tower/Soldier tấn công → quay sang đánh kẻ gần nhất.
        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        # (1) + (2) Đường tới HQ: vào thẳng HQ, hoặc phá Wall cản đường.
        path = self._path_target(context)
        if path is not None:
            return path

        # (4) Fallback: luôn tiến về HQ (kể cả khi can_reach_hq=False —
        #     titan vẫn nhắm HQ và để pathfinding lo phần còn lại).
        return context.hq if _is_alive(context.hq) else None


# ─────────────────────────────────────────────────────────────────
#  ArmoredPriority — ArmoredTitan
# ─────────────────────────────────────────────────────────────────

class ArmoredPriority(TargetPriorityStrategy):
    """Bộ ưu tiên của ArmoredTitan — "cỗ máy phá thành".

    Thứ tự ưu tiên (cao → thấp):
        1. Wall (TUYỆT ĐỐI) — khi titan CÒN GIÁP và có Wall chặn đường,
           Armored phớt lờ mọi soldier/tower/commander đang bắn nó, dồn
           toàn lực dash húc Wall cho tới khi Wall sập HOẶC giáp vỡ
           (đủ 10 hit). Đây là điểm khác biệt so với mọi Priority khác.
        2. HQ — khi đường vào HQ THÔNG (Wall đã sập). Lúc này Armored
           lao thẳng vào HQ, vẫn miễn nhiễm reactive (đã quyết tâm
           phá thành thì không quay đầu).
        3. Tower / Soldier / Commander — chỉ phản ứng khi GIÁP ĐÃ VỠ
           và đang bị 3 thứ này tấn công. Trước thời điểm đó Armored
           xem chúng như không tồn tại.
        4. Wall (giáp vỡ) — nếu Wall còn sống và không bị ai đánh,
           Armored tiếp tục đập Wall bằng melee (HeavyStrikeStrategy).
        5. Fallback: HQ.

    Vì sao đảo thứ tự reactive xuống dưới Wall?
        Yêu cầu thiết kế: ArmoredRamStrategy phải chạy đủ 10 dash vào
        Wall mặc kệ ai tấn công. Nếu reactive đứng trên Wall như
        DefaultPriority, soldier/tower xuất hiện sẽ cắt ngang chuỗi
        dash → giáp không bao giờ vỡ đúng cách, không thể hiện được
        bản chất "cỗ máy phá thành" của Armored.

    Lưu ý kiến trúc: Priority chỉ trả về MỤC TIÊU. Việc chọn đòn đánh
    nào (Ram khi Wall + còn giáp, Heavy khi vỡ giáp) thuộc về tầng AI
    và AttackStrategy — xem `ArmoredAI._on_decide` trong Titan_AI.py.
    """

    _reactive_types = (TOWER, SOLDIER, COMMANDER)

    def select_target(self, titan, context: TargetContext):
        armor_intact = bool(getattr(titan, '_armor_intact', True))

        # (1) CÒN GIÁP + có Wall chặn → Wall TUYỆT ĐỐI, bỏ qua reactive.
        if armor_intact and _is_alive(context.blocking_wall):
            return context.blocking_wall

        # (2) CÒN GIÁP + đường HQ thông → lao thẳng HQ, vẫn bỏ qua reactive.
        if armor_intact and context.can_reach_hq and _is_alive(context.hq):
            return context.hq

        # (3) Giáp vỡ → mở khoá phản ứng với Tower/Soldier/Commander.
        locked = self._locked_reactive_target(context)
        if locked is not None:
            return locked
        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        # (4) Giáp vỡ + đường HQ thông → vào HQ.
        if context.can_reach_hq and _is_alive(context.hq):
            return context.hq

        # (5) Giáp vỡ + còn Wall → tiếp tục đập Wall bằng melee.
        if _is_alive(context.blocking_wall):
            return context.blocking_wall

        # (6) Fallback: HQ.
        return context.hq if _is_alive(context.hq) else None


# ─────────────────────────────────────────────────────────────────
#  BeastPriority — BeastTitan
# ─────────────────────────────────────────────────────────────────

class BeastPriority(TargetPriorityStrategy):
    """Bộ ưu tiên của BeastTitan — "thợ săn tháp tầm xa".

    Thứ tự ưu tiên (chủ động, không cần bị tấn công mới phản ứng):
        1. Tower — aim một con là theo tới chết (current_target là Tower
           còn sống → giữ nguyên). Hết Tower mới xuống bước kế.
        2. Soldier — Beast chủ động ném đá vào Soldier gần nhất.
        3. Commander — sau khi quét hết Soldier, săn Commander.
        4. Wall — chỉ khi còn Wall chặn đường vào HQ.
        5. HQ — khi đường vào HQ thông (hoặc Wall đã sập hết).

    Khác BeastPriority cũ:
        • Soldier/Commander KHÔNG còn là "reactive" (chỉ đánh khi bị bắn)
          mà là mục tiêu CHỦ ĐỘNG — Beast tự đi tìm và ném đá vào chúng.
        • Wall hạ ưu tiên xuống dưới Soldier/Commander vì Beast là boss
          tầm xa: nên dọn sạch lực lượng phòng thủ trước khi đập Wall.
        • Đòn đánh KHÔNG đổi — vẫn dùng RockProjectile (BeastAI.act sẽ
          gọi `trigger_attack(target)` cho mọi loại target trong tầm).
    """

    def select_target(self, titan, context: TargetContext):
        # (1) Đang aim một Tower còn sống → theo tới chết.
        ct = context.current_target
        if _is_alive(ct) and _type_of(ct) == TOWER:
            return ct

        # (1) Chưa aim ai (hoặc target cũ chết) → chọn Tower gần nhất.
        tower = _nearest(titan, context.towers)
        if tower is not None:
            return tower

        # (2) Hết Tower → săn Soldier gần nhất.
        soldier = _nearest(titan, context.soldiers)
        if soldier is not None:
            return soldier

        # (3) Hết Soldier → săn Commander gần nhất.
        commander = _nearest(titan, context.commanders)
        if commander is not None:
            return commander

        # (4) Hết lực lượng phòng thủ → đập Wall nếu còn chặn.
        if _is_alive(context.blocking_wall):
            return context.blocking_wall

        # (5) Đường thông → HQ.
        if _is_alive(context.hq):
            return context.hq

        return None


# ─────────────────────────────────────────────────────────────────
#  KamikazePriority — Kamikaze
# ─────────────────────────────────────────────────────────────────

class KamikazePriority(TargetPriorityStrategy):
    """Bộ ưu tiên của Kamikaze — "bom tự sát săn lính".

    Thứ tự ưu tiên:
        1. Soldier / Commander — mục tiêu CHỦ ĐỘNG, lao vào ngay.
        2. HQ.
        3. Wall.
        4. Tower — chỉ đánh khi bị Tower tấn công thì mới chuyển ưu
           tiên từ HQ/Wall sang nó.

    Khác các titan khác:
        • Soldier/Commander là mục tiêu CHỦ ĐỘNG (không cần bị đánh
          mới đánh) — nên KHÔNG nằm trong `_reactive_types`.
        • Chỉ Tower mới là loại "phản ứng".

    Lưu ý: việc chọn cụm lính đông nhất (clustering) là logic riêng
    trong class `Kamikaze` (`_pick_clustering_target`). Priority chỉ
    trả "có Soldier/Commander thì nhắm vào", còn nhắm con CỤ THỂ nào
    do tầng AI quyết. Ở đây ta trả kẻ gần nhất làm mặc định hợp lý.
    """

    _reactive_types = (TOWER,)

    def select_target(self, titan, context: TargetContext):
        # (1) Soldier/Commander — mục tiêu chủ động, ưu tiên cao nhất.
        prey = _nearest(titan, list(context.soldiers) + list(context.commanders))
        if prey is not None:
            return prey

        # (4) Không còn lính/tướng nhưng bị Tower tấn công → quay sang Tower.
        locked = self._locked_reactive_target(context)
        if locked is not None:
            return locked
        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        # (2)+(3) Đường tới HQ: HQ nếu thông, ngược lại Wall đang cản.
        # Tránh bug Kamikaze "xuyên Wall" lao thẳng vào HQ.
        path = self._path_target(context)
        if path is not None:
            return path

        # Fallback cũ giữ lại cho compatibility (gần như không bao giờ chạy).
        if _is_alive(context.hq):
            return context.hq
        if _is_alive(context.blocking_wall):
            return context.blocking_wall

        return None


# ─────────────────────────────────────────────────────────────────
#  SoldierHunterPriority — SoldierHunter
# ─────────────────────────────────────────────────────────────────

class SoldierHunterPriority(TargetPriorityStrategy):
    """Bộ ưu tiên của SoldierHunter — "khắc tinh bộ binh".

    Thứ tự ưu tiên:
        1. Soldier — mục tiêu CHỦ ĐỘNG, luôn ưu tiên săn lính.
        2. HQ.
        3. Wall.
        4. Tower / Commander — chỉ đánh khi bị 2 thứ này tấn công
           thì mới chuyển ưu tiên từ HQ/Wall sang chúng.

    Khác Kamikaze: SoldierHunter chỉ chủ động với Soldier (không gồm
    Commander). Commander cùng Tower là loại "phản ứng".
    """

    _reactive_types = (TOWER, COMMANDER)

    def select_target(self, titan, context: TargetContext):
        # (1) Soldier — mục tiêu chủ động.
        prey = _nearest(titan, context.soldiers)
        if prey is not None:
            return prey

        # (4) Hết Soldier nhưng bị Tower/Commander tấn công → quay sang chúng.
        locked = self._locked_reactive_target(context)
        if locked is not None:
            return locked
        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        # (2)+(3) Đường tới HQ: HQ nếu thông, ngược lại Wall đang cản.
        # Trước đây trả thẳng context.hq → titan đi xuyên Wall vào HQ.
        path = self._path_target(context)
        if path is not None:
            return path

        return None


# ─────────────────────────────────────────────────────────────────
#  TowerHunterPriority — TowerHunter
# ─────────────────────────────────────────────────────────────────

class TowerHunterPriority(TargetPriorityStrategy):
    """Bộ ưu tiên của TowerHunter — "kẻ công thành phá tháp".

    Thứ tự ưu tiên:
        1. Tower — mục tiêu CHỦ ĐỘNG, luôn ưu tiên hạ tháp.
        2. HQ.
        3. Wall.
        4. Soldier / Commander — chỉ đánh khi bị 2 thứ này tấn công
           thì mới chuyển ưu tiên từ HQ/Wall sang chúng.

    Cơ chế khóa: khi đã nhắm một Tower, theo tới chết (current_target
    là Tower còn sống → giữ nguyên), rồi mới chọn Tower gần nhất kế.
    """

    _reactive_types = (SOLDIER, COMMANDER)

    def select_target(self, titan, context: TargetContext):
        # (1) Đang nhắm một Tower còn sống → theo tới chết.
        ct = context.current_target
        if _is_alive(ct) and _type_of(ct) == TOWER:
            return ct

        # (1) Chọn Tower gần nhất để bắt đầu.
        tower = _nearest(titan, context.towers)
        if tower is not None:
            return tower

        # (4) Hết Tower nhưng bị Soldier/Commander tấn công → quay sang chúng.
        reactive = _attackers_of_types(titan, context, self._reactive_types)
        if reactive is not None:
            return reactive

        # (2)+(3) Đường tới HQ: HQ nếu thông, ngược lại Wall đang cản.
        path = self._path_target(context)
        if path is not None:
            return path

        return None


# ─────────────────────────────────────────────────────────────────
#  WolfPriority — Wolf
# ─────────────────────────────────────────────────────────────────

class WolfPriority(TargetPriorityStrategy):
    """Bộ ưu tiên của Wolf — gần giống luật chung nhưng ĐẢO vị trí
    Commander và Tower/Soldier.

    Thứ tự ưu tiên:
        1. HQ — nếu có đường vào thẳng.
        2. WallSection — nếu đang cản đường tiến vào HQ.
        3. Commander (tướng) — Wolf coi tướng là mục tiêu đáng đánh
           hơn lính/tháp.
        4. Tower / Soldier — NGANG nhau; chỉ đánh khi chúng tấn công
           titan.

    So với DefaultPriority:
        • Default: mục 3 = Tower/Soldier, mục 4 = Commander.
        • Wolf:    mục 3 = Commander,     mục 4 = Tower/Soldier.
        Tức Wolf "thèm" tướng hơn. Nhưng cả Commander lẫn Tower/Soldier
        đều là loại "phản ứng" (bị đánh mới đánh) — Wolf không chủ động
        rời đường tới HQ để đi săn tướng; nó chỉ đổi mục tiêu khi BỊ
        tấn công, và khi đó tướng được ưu tiên hơn tower/lính.
    """

    _reactive_types = (COMMANDER, TOWER, SOLDIER)

    def select_target(self, titan, context: TargetContext):
        # (3) Đang khóa một mục tiêu phản ứng còn sống → giữ tới chết.
        locked = self._locked_reactive_target(context)
        if locked is not None:
            return locked

        # (3) Bị Commander tấn công → ưu tiên cao hơn Tower/Soldier.
        by_commander = _attackers_of_types(titan, context, (COMMANDER,))
        if by_commander is not None:
            return by_commander

        # (4) Bị Tower/Soldier tấn công → quay sang kẻ gần nhất.
        by_tower_soldier = _attackers_of_types(titan, context, (TOWER, SOLDIER))
        if by_tower_soldier is not None:
            return by_tower_soldier

        # (1) + (2) Đường tới HQ: vào thẳng HQ, hoặc phá Wall cản đường.
        path = self._path_target(context)
        if path is not None:
            return path

        # Fallback: luôn tiến về HQ.
        return context.hq if _is_alive(context.hq) else None


# ─────────────────────────────────────────────────────────────────
#  Bảng tra cứu: tên loại Titan → class Priority
# ─────────────────────────────────────────────────────────────────
#
# Tiện cho tầng AI sau này: từ tên class Titan lấy ngay bộ ưu tiên
# phù hợp. Các loại không có tên riêng (RegularTitan, ColossalTitan,
# FoundingTitan...) dùng DefaultPriority.

PRIORITY_BY_TITAN: dict = {
    'ArmoredTitan':  ArmoredPriority,
    'BeastTitan':    BeastPriority,
    'Kamikaze':      KamikazePriority,
    'SoldierHunter': SoldierHunterPriority,
    'TowerHunter':   TowerHunterPriority,
    'Wolf':          WolfPriority,
}


def make_priority_for(titan) -> TargetPriorityStrategy:
    """Tạo bộ ưu tiên phù hợp cho `titan` dựa theo tên class của nó.

    Loại nào không có bộ ưu tiên riêng → DefaultPriority.

    Ví dụ:
        titan._priority = make_priority_for(titan)
    """
    cls = PRIORITY_BY_TITAN.get(type(titan).__name__, DefaultPriority)
    return cls()
