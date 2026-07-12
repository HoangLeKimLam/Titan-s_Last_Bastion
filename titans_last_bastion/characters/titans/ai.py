# characters/titans/ai.py — Bộ não tự hành của mọi Titan/Boss
#
# Trách nhiệm:
#     ĐIỀU PHỐI 3 thành phần có sẵn ở mỗi frame:
#       1. priority.py  — chọn mục tiêu
#       2. titan.py / boss.py — kích hoạt kỹ năng/animation/di chuyển
#       3. attackstrategy.py — tung đòn đánh
#
# Kiến trúc OOP:
#     WorldView (ABC)        — "giác quan": AI nhìn thế giới qua đây.
#       └─ SimpleWorldView   — bản cụ thể dựng từ các list entity.
#     TitanAI (ABC)          — vòng AI chung: sense → decide → act.
#       ├─ DefaultAI         — Titan thường (fallback).
#       ├─ RegularAI         — animation vung tay khi đánh.
#       ├─ ArmoredAI         — Wall + còn giáp → kích Dash; thân xác tự lo.
#       ├─ WolfAI            — cắn nhanh, khẩu vị Wolf.
#       ├─ TowerHunterAI     — săn tháp.
#       ├─ SoldierHunterAI   — săn lính (cleave AoE).
#       ├─ KamikazeAI        — lao vào cụm lính rồi tự nổ.
#       ├─ ColossalAI        — boss: skill AoE theo cooldown.
#       ├─ BeastAI           — boss: ném đá tầm xa.
#       └─ FoundingAI        — boss: 3 phase + summon.
#
# Composition (HAS-A), KHÔNG kế thừa Titan:
#     ai = make_ai_for(titan, world)
#     ai.update(dt)   # gọi mỗi frame thay cho titan.update(dt)

import math
from abc import ABC, abstractmethod
from config import balance

from characters.titans.priority import (
    TargetContext, TargetPriorityStrategy, make_priority_for,
    HQ, WALL, TOWER, SOLDIER, COMMANDER,
)


# ═════════════════════════════════════════════════════════════════
#  Hằng số trạng thái AI
# ═════════════════════════════════════════════════════════════════

STATE_IDLE      = 'idle'
STATE_SEEKING   = 'seeking'
STATE_MOVING    = 'moving'
STATE_ATTACKING = 'attacking'
STATE_SKILL     = 'skill'
STATE_DEAD      = 'dead'


# ═════════════════════════════════════════════════════════════════
#  WorldView — "giác quan" của AI
# ═════════════════════════════════════════════════════════════════

class WorldView(ABC):
    """Lớp trừu tượng: AI nhìn thế giới game QUA đây.

    Tại sao trừu tượng?
        AI chỉ cần một object cho ra `TargetContext` + vài truy vấn phụ.
        WorldView là "bản hợp đồng" tách AI khỏi module hệ thống thật —
        dùng SimpleWorldView cho demo/test, WorldQueryView cho game thật.

    Method bắt buộc:
        build_context(titan) → TargetContext
    """

    @abstractmethod
    def build_context(self, titan) -> TargetContext:
        """Dựng `TargetContext` — "ảnh chụp" thế giới mà `titan` nhìn thấy frame này.

        Đây là GIÁC QUAN của AI. AI không bao giờ tự đi hỏi WorldQuery; nó chỉ đọc
        context. Nhờ vậy có thể thay thế nguồn dữ liệu (game thật vs test) mà không
        sửa 1 dòng nào trong AI.

        Tham số: titan — con titan cần dựng context (dùng x, y, VISUAL_RANGE của nó).
        Trả về: `TargetContext` (priority.py) gồm hq/walls/towers/soldiers/commanders,
            các list `visible_*` (đã lọc tầm nhìn), `blocking_wall`, `can_reach_hq`,
            `attackers`, `current_target`.

        2 bản cài đặt: `SimpleWorldView` (demo/test) và `WorldQueryView` (game.py, thật).
        """
        ...

    def soldiers_in_radius(self, cx: float, cy: float,
                           radius: float) -> list:
        """Lính còn sống trong bán kính quanh (cx, cy) — phục vụ skill AoE.

        KHÔNG abstract: mặc định trả list RỖNG. Nghĩa là WorldView nào không cần
        skill AoE thì khỏi phải cài đặt. Bản con override khi cần thật.

        Tham số: cx, cy — tâm vùng (px); radius — bán kính (px).
        Trả về: list soldier còn sống (rỗng nếu chưa override).
        """
        return []


class SimpleWorldView(WorldView):
    """Bản WorldView cụ thể dựng từ các danh sách entity rời.

    Dùng cho demo/test và mọi tình huống chưa có module hệ thống thật.
    Nhận thẳng các list entity, tự lo lọc still-alive + tính
    `blocking_wall` + `can_reach_hq` bằng hình học đơn giản.
    """

    def __init__(self, hq=None, walls=None, towers=None,
                 soldiers=None, commanders=None,
                 block_radius: float = 70.0) -> None:
        """Gói các list entity rời thành 1 WorldView (dùng cho demo/test).

        Tham số:
            hq, walls, towers, soldiers, commanders: entity của phe phòng thủ.
                None → coi như list rỗng (`list(x or [])`), nên gọi
                `SimpleWorldView()` không tham số vẫn hợp lệ.
            block_radius: khoảng cách vuông góc (px) để coi 1 đoạn tường là ĐANG
                CHẮN đường titan→HQ. Càng lớn càng dễ coi là bị chắn.
                (xem `_find_blocking_wall`)

        Khác `WorldQueryView` (game.py thật): bản này KHÔNG dùng WorldQuery, tự
        tính mọi thứ bằng hình học đơn giản → tránh lỗi "entity chưa spawn_entity"
        trong test.
        """
        self.hq         = hq
        self.walls      = list(walls or [])
        self.towers     = list(towers or [])
        self.soldiers   = list(soldiers or [])
        self.commanders = list(commanders or [])
        self._block_radius = block_radius

    def build_context(self, titan) -> TargetContext:
        """Dựng TargetContext từ các list entity (bản demo/test).

        Thuật toán:
          1. Đọc `_ai_attackers` (ai đang đánh titan) và `_ai_current_target` (mục
             tiêu đang khoá) TỪ CHÍNH TITAN — đây là bộ nhớ AI gắn trên titan.
          2. `_find_blocking_wall()` → tường chắn đường titan→HQ.
             `can_reach_hq = (blocking is None)`: không có tường chắn = đi thẳng được.
          3. Lọc TẦM NHÌN: so bình phương khoảng cách với `VISUAL_RANGE²`
             (so bình phương để KHỎI tính căn bậc hai — nhanh hơn, gọi rất nhiều lần).
             → `visible_soldiers` / `visible_commanders` / `visible_towers`.

        LƯU Ý QUAN TRỌNG: các list `visible_*` CHỈ lọc theo KHOẢNG CÁCH, KHÔNG lọc
        theo VÙNG (zone). Việc lọc vùng do `priority.py` làm (`_same_zone_only`).
        Nếu Priority quên lọc vùng → titan sẽ "nhìn xuyên tường".

        Trả về: TargetContext đầy đủ.
        Chỉ số: balance.TITAN_VISUAL_RANGE.
        """
        attackers = list(getattr(titan, '_ai_attackers', []))
        current   = getattr(titan, '_ai_current_target', None)
        blocking  = self._find_blocking_wall(titan)

        # Visual range — tính thẳng từ danh sách của SimpleWorldView,
        # không đi qua WorldQuery (tránh lỗi entity chưa được spawn_entity).
        vr2 = float(getattr(titan, 'VISUAL_RANGE', 250.0)) ** 2

        def _in_vrange(e):
            """True nếu `e` còn sống VÀ nằm trong tầm nhìn của titan.

            So `dx²+dy² <= vr2` (bình phương) thay vì tính căn — tránh `sqrt()`
            cho mỗi entity mỗi frame.
            """
            if not getattr(e, 'is_alive', False):
                return False
            dx = e.x - titan.x
            dy = e.y - titan.y
            return dx * dx + dy * dy <= vr2

        visible_soldiers   = [e for e in self.soldiers   if _in_vrange(e)]
        visible_commanders = [e for e in self.commanders if _in_vrange(e)]
        visible_towers     = [e for e in self.towers     if _in_vrange(e)]

        return TargetContext(
            hq=self.hq,
            walls=self.walls,
            towers=self.towers,
            soldiers=self.soldiers,
            commanders=self.commanders,
            visible_soldiers=visible_soldiers,
            visible_commanders=visible_commanders,
            visible_towers=visible_towers,
            blocking_wall=blocking,
            can_reach_hq=(blocking is None),
            attackers=attackers,
            current_target=current,
        )

    def soldiers_in_radius(self, cx: float, cy: float,
                           radius: float) -> list:
        """Quét thẳng list `self.soldiers` lấy lính còn sống trong bán kính.

        Thuật toán: duyệt tuyến tính O(n), so bình phương khoảng cách với `r2`
        (không tính căn). Không dùng WorldQuery → an toàn trong test.

        Tham số: cx, cy — tâm (px); radius — bán kính (px).
        Trả về: list soldier còn sống trong vùng.
        """
        r2 = radius * radius
        out = []
        for s in self.soldiers:
            if not getattr(s, 'is_alive', False):
                continue
            dx = s.x - cx
            dy = s.y - cy
            if dx * dx + dy * dy <= r2:
                out.append(s)
        return out

    def _find_blocking_wall(self, titan):
        """Tìm đoạn tường CHẮN đường thẳng titan → HQ (gần titan nhất).

        Thuật toán — chiếu điểm lên đoạn thẳng:
          1. Coi đường titan→HQ là ĐOẠN thẳng AB (A=titan, B=HQ).
          2. Với mỗi tường W còn sống, tính tham số chiếu:
                 `t = ((W-A)·(B-A)) / |B-A|²`
             `t` cho biết hình chiếu của W rơi ở đâu trên AB:
                 t <= 0 → W nằm SAU lưng titan   → bỏ (không chắn)
                 t >= 1 → W nằm SAU lưng HQ      → bỏ (không chắn)
                 0<t<1  → W nằm GIỮA hai điểm    → xét tiếp.
          3. Tính khoảng cách VUÔNG GÓC `perp` từ W tới đoạn AB.
             `perp <= _block_radius` (70px) → tường này thực sự chắn đường.
          4. Trong các tường chắn, chọn cái GẦN TITAN NHẤT (titan phải đập cái
             trước mặt trước, không phải cái xa nhất).

        Trả về: entity tường chắn gần nhất, hoặc None (đường thông → về thẳng HQ).

        Đây là bản HÌNH HỌC ĐƠN GIẢN cho demo/test. Game thật dùng
        `WorldQuery.find_blocking_wall()` (chính xác hơn, có xét vùng/lỗ thủng).
        """
        if not _alive(self.hq):
            return None
        ax, ay = titan.x, titan.y
        bx, by = self.hq.x, self.hq.y
        seg_dx, seg_dy = bx - ax, by - ay
        seg_len2 = seg_dx * seg_dx + seg_dy * seg_dy
        if seg_len2 == 0:
            return None

        best, best_d = None, float('inf')
        for w in self.walls:
            if not _alive(w):
                continue
            t = ((w.x - ax) * seg_dx + (w.y - ay) * seg_dy) / seg_len2
            if t <= 0.0 or t >= 1.0:
                continue
            px, py = ax + t * seg_dx, ay + t * seg_dy
            perp = ((w.x - px) ** 2 + (w.y - py) ** 2) ** 0.5
            if perp <= self._block_radius:
                d = _dist(titan, w)
                if d < best_d:
                    best_d, best = d, w
        return best


# ── Helper hình học (module-private) ─────────────────────────────

def _alive(e) -> bool:
    """True nếu entity tồn tại VÀ còn sống.

    Gộp `is not None` + `is_alive`. Object lạ không có cờ `is_alive` bị coi như
    đã chết (mặc định False) — an toàn hơn là coi như còn sống.
    """
    return e is not None and getattr(e, 'is_alive', False)


def _dist(a, b) -> float:
    """Khoảng cách Euclid (px) giữa 2 entity, dùng TÂM đã hiệu chỉnh.

    Không lấy thẳng `a.x`/`b.x` mà đi qua `_entity_xy()` — vì tường neo góc
    trên-trái chứ không neo tâm (xem `_entity_xy`). Bỏ qua bước này thì titan sẽ
    tính sai khoảng cách tới tường ~16px và dừng hụt/đâm lố.
    """
    ax, ay = _entity_xy(a)
    bx, by = _entity_xy(b)
    dx = ax - bx
    dy = ay - by
    return (dx * dx + dy * dy) ** 0.5


def _entity_xy(e) -> tuple:
    """Trả TÂM của entity — bù trừ riêng cho TƯỜNG.

    Vì sao cần: hầu hết entity (titan/lính/tháp) neo tại TÂM, nhưng `WallSection`
    neo tại GÓC TRÊN-TRÁI của ô 32×32. Nếu dùng thẳng `wall.x` thì mọi phép đo
    khoảng cách tới tường bị lệch nửa ô.

    Thuật toán: `ENTITY_TYPE == 'wall'` → cộng +16 (nửa ô 32px) vào cả x lẫn y.
    Còn lại → trả nguyên (x, y).

    Trả về: tuple (x, y) toạ độ tâm.
    """
    if getattr(e, 'ENTITY_TYPE', '') == WALL:
        return float(e.x) + 16.0, float(e.y) + 16.0
    return float(e.x), float(e.y)


def _direction_to(src, dst) -> int:
    """Hướng `src` phải QUAY MẶT để nhìn `dst` (0=N, 1=W, 2=S, 3=E).

    Thuật toán: lấy vector src→dst (dùng tâm đã hiệu chỉnh), so `|dx|` với `|dy|`:
        `|dx| >= |dy|` → lệch NGANG nhiều hơn → Đông (dx>0) / Tây.
        ngược lại      → lệch DỌC  nhiều hơn → Nam  (dy>0) / Bắc.
    Tức chia mặt phẳng thành 4 góc phần tư bởi 2 đường chéo 45°.

    Trả về: int 0-3, dùng để tra hàng sprite (`_WALK_ROWS[dir]`, ...).
    """
    sx, sy = _entity_xy(src)
    dx = _entity_xy(dst)[0] - sx
    dy = _entity_xy(dst)[1] - sy
    if abs(dx) >= abs(dy):
        return 3 if dx > 0 else 1
    return 2 if dy > 0 else 0


def _type_of(e) -> str:
    """`ENTITY_TYPE` của entity, '' nếu không có.

    Cho phép AI phân loại mục tiêu bằng CHUỖI, không cần `isinstance` → không phải
    import class (tránh vòng lặp import). Thêm loại entity mới chỉ cần khai
    `ENTITY_TYPE`, không phải sửa ai.py.
    """
    return getattr(e, 'ENTITY_TYPE', '')

def _get_target_radius(e) -> float:
    """Bán kính "vỏ ngoài" của mục tiêu — titan dừng ở RÌA, không đâm vào TÂM.

    Vấn đề: titan di chuyển tới toạ độ TÂM của mục tiêu. Với công trình to (tháp,
    HQ, tường), đi tới tâm nghĩa là ĐI XUYÊN VÀO TRONG nó → titan lún vào giữa
    tháp, trông sai và có thể kẹt.

    Cách xử lý: trừ bớt bán kính này khỏi khoảng cách khi tính "đã tới nơi chưa"
    và khi tính tầm đánh (xem `_attack_range` / `act()`).

    Bảng bán kính (px):
        'tower', 'hq' → 40.0   (công trình lớn)
        'wall'        → 42.0   (tường dày hơn chút)
        còn lại (lính/tướng/titan) → 0.0  (thân nhỏ, đi thẳng tới tâm được)

    Trả về: float (px).
    """
    etype = _type_of(e)
    if etype in ('tower', 'hq'):
        return 40.0
    if etype == 'wall':
        return 42.0
    return 0.0


def _describe(e) -> str:
    """Tên ngắn gọn của entity — CHỈ dùng để log/debug, không ảnh hưởng gameplay.

    Thuật toán: thử lần lượt `_label` → `name` → `ENTITY_TYPE` → tên class, lấy
    cái đầu tiên khác None/rỗng (chuỗi `or` nối tiếp). `None` → trả 'None'.

    Trả về: str.
    """
    if e is None:
        return 'None'
    return (getattr(e, '_label', None) or getattr(e, 'name', None)
            or getattr(e, 'ENTITY_TYPE', None) or type(e).__name__)


# ═════════════════════════════════════════════════════════════════
#  TitanAI — bộ não chung (ABC)
# ═════════════════════════════════════════════════════════════════

class TitanAI(ABC):
    """Bộ não tự hành cho một Titan. Lớp cha của mọi AI cụ thể.

    Vòng đời mỗi frame (`update(dt)`):
        1. sense()   — dựng TargetContext qua WorldView.
        2. decide()  — dùng Priority chọn mục tiêu.
        3. act()     — di chuyển / tấn công / tung kỹ năng.

    AI HAS-A: titan, world, priority — không kế thừa Titan.

    Class con override:
        • _act_in_range()  — làm gì khi đã tới sát mục tiêu.
        • _on_decide()     — xử lý đặc thù trước khi di chuyển.
    """

    _DEFAULT_ATTACK_RANGE = balance.AI_DEFAULT_ATTACK_RANGE
    _RUN_THRESHOLD = balance.AI_RUN_THRESHOLD
    _RUN_SPEED_MULT = balance.AI_RUN_SPEED_MULT

    def __init__(self, titan, world: WorldView,
                 priority: TargetPriorityStrategy = None) -> None:
        """Gắn 1 bộ não vào 1 titan (quan hệ HAS-A, không kế thừa).

        3 thành phần rời được lắp vào đây:
            `titan`    — thân xác (titan.py/boss.py): sprite, HP, animation.
            `world`    — giác quan (WorldView): dựng TargetContext.
            `priority` — khẩu vị (priority.py): chọn mục tiêu.
                None → tự suy ra từ TÊN CLASS titan qua `make_priority_for()`.
        Đổi 1 trong 3 là đổi hành vi mà không sửa 2 cái kia — đây là lý do tách
        AI/Priority/Strategy ra 3 file.

        Trạng thái AI khởi tạo:
            `state` (idle/seeking/moving/attacking/skill/dead), `target`,
            `last_reason` (chuỗi debug giải thích vì sao chọn mục tiêu đó).
            `_attack_cd` — cooldown đánh.
            `_telegraph_*` — pha "ra đòn báo trước" (xem `_tick_telegraph`).

        GẮN NGƯỢC LÊN TITAN (quan trọng):
            `titan._ai_attackers`      — list kẻ đang đánh titan (bộ nhớ aggro).
            `titan._ai_current_target` — mục tiêu đang khoá; `boss.py` ĐỌC biến này
                                          trong `trigger_attack()`.
            `titan._ai = self`         — backref, để `Titan.take_damage()` gọi
                                          được `notify_attacked()` khi bị đánh.
            Xoá/đổi tên mấy biến này sẽ làm gãy aggro và đòn đánh của boss.
        """
        self.titan    = titan
        self.world    = world
        self.priority = priority or make_priority_for(titan)

        self.state        = STATE_IDLE
        self.target       = None
        self.last_reason  = ''

        self._attack_cd       = 0.0
        self._telegraph_timer  = 0.0   # giây còn lại của phase telegraph
        self._telegraph_target = None  # commander đang bị telegraph
        self._telegraph_range  = 0.0   # bán kính vòng tròn hiển thị

        if not hasattr(titan, '_ai_attackers'):
            titan._ai_attackers = []
        titan._ai_current_target = None
        titan._ai = self          # backref — cho phép Titan.take_damage gọi notify_attacked

    # ── API công khai ────────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Chạy 1 frame AI: sense → decide → act. ĐÂY LÀ ĐIỂM VÀO DUY NHẤT.

        QUAN TRỌNG: khi AI đang chạy, game loop KHÔNG gọi `titan.update()` nữa.
        Vì vậy AI phải tự lo mọi thứ mà `titan.update()` từng lo (tick slow,
        knockback, animation) — nếu quên, titan sẽ bị "đơ" hiệu ứng.

        Thuật toán theo thứ tự (mỗi bước có thể `return` sớm = "nuốt" cả frame):
          1. Titan chết → `state = DEAD`, thoát.
          2. Đếm ngược `_attack_cd`. Nhân `_slow_factor` → dính IceTower thì
             cooldown đánh trôi CHẬM hơn (đánh thưa hơn).
          3. Đếm ngược `_vis_roll_cd` (nhịp 2s cho cú roll 50% chọn mục tiêu nhìn
             thấy — xem `priority._maybe_visible_target`).
          4. **`_tick_telegraph(dt)`** — nếu đang "gồng đòn báo trước" thì titan
             ĐỨNG YÊN, không di chuyển, và `return` ngay.
             (AI con nào override `update()` mà QUÊN gọi `_tick_telegraph` sẽ làm
              titan ĐỨNG ĐƠ VĨNH VIỄN vì timer không bao giờ giảm — đây từng là
              bug thật của FoundingAI.)
          5. `_tick_status(dt)` — tick slow/knockback. Đang bị knockback → chỉ
             chạy animation rồi thoát (không tự đi được).
          6. sense → decide → act.

        Tham số: dt — giây trôi qua từ frame trước.
        Chỉ số: balance.AI_TELEGRAPH_DELAY.
        """
        if not getattr(self.titan, 'is_alive', False):
            self.state = STATE_DEAD
            return

        self._attack_cd = max(0.0, self._attack_cd - dt * getattr(self.titan, '_slow_factor', 1.0))

        # Tick cooldown xét visible target (50% roll)
        cd = getattr(self.titan, '_vis_roll_cd', 0.0)
        if cd > 0.0:
            self.titan._vis_roll_cd = max(0.0, cd - dt)

        # Tick telegraph — titan KHÔNG di chuyển (xem _tick_telegraph)
        if self._tick_telegraph(dt):
            return

        # Tick slow/knockback — titan.update() không được gọi khi AI active
        if hasattr(self.titan, '_tick_status') and self.titan._tick_status(dt):
            self._advance_animation(dt)
            return  # bị knockback → bỏ qua AI movement frame này

        context = self.sense()
        self.target = self.decide(context)
        self.titan._ai_current_target = self.target
        self.act(dt, context)
        self._advance_animation(dt)

    def notify_attacked(self, attacker) -> None:
        """Ghi nhớ "kẻ vừa đánh tôi" → cơ sở để titan PHẢN ĐÒN.

        Ai gọi: `Titan.take_damage()` (titan.py) gọi qua backref `titan._ai`.

        Thuật toán: thêm `attacker` vào `titan._ai_attackers` nếu CHƯA có
        (chống trùng — 1 tháp bắn 10 phát vẫn chỉ nằm 1 lần trong list).

        Danh sách này được:
          - LỌC XÁC ở `sense()` mỗi frame (kẻ đánh mình đã chết thì quên).
          - LỌC TẦM ở `priority._attackers_of_types()` (`AGGRO_RANGE`) — ra khỏi
            tầm thù hằn thì thôi đuổi. Đây là thứ chặn bug "tách từ xa": 1 tháp
            bắn tỉa 1 phát rồi titan đuổi nó xuyên bản đồ.

        Tham số: attacker — entity vừa gây damage (None → bỏ qua).
        Chỉ số: balance.PRIORITY_AGGRO_RANGE.
        """
        lst = self.titan._ai_attackers
        if attacker is not None and attacker not in lst:
            lst.append(attacker)

    # ── Ba pha của vòng AI ───────────────────────────────────────

    def sense(self) -> TargetContext:
        """PHA 1 — GIÁC QUAN: dọn danh sách aggro rồi dựng ảnh chụp thế giới.

        Thuật toán:
          1. LỌC XÁC khỏi `_ai_attackers` (giữ lại `_alive`). BẮT BUỘC làm mỗi
             frame — nếu không, list phình mãi và titan còn "thù" cả xác chết.
          2. `world.build_context(titan)` → TargetContext.

        Trả về: TargetContext — dữ liệu CHỈ ĐỌC cho `decide()` và `act()`.
        Liên kết: `WorldQueryView.build_context()` (game.py) trong game thật.
        """
        self.titan._ai_attackers = [
            a for a in self.titan._ai_attackers if _alive(a)
        ]
        return self.world.build_context(self.titan)

    def decide(self, context: TargetContext):
        """PHA 2 — chọn mục tiêu: Priority chọn trước, rồi AI ÁP các luật chặn.

        Priority (priority.py) chỉ biết "tôi THÍCH đánh ai". `decide()` mới biết
        "tôi CÓ TỚI ĐƯỢC chỗ đó không". Vì vậy target của Priority có thể bị ĐÈ.

        Thứ tự xét (trên đè dưới):
          1. **BẪY MỒI (bait_target) — ƯU TIÊN TUYỆT ĐỐI.** Có `bait_target` còn
             sống → nhắm ngay, xoá `_breach_wall`, bỏ qua MỌI luật khác. Đây là
             cách BaitTrap (trap.py) kéo titan đi chỗ khác.
          2. Priority chọn target.
          3. **PHẢN ĐÒN không bị đè**: target nằm trong `context.attackers` VÀ
             (là tháp gắn tường HOẶC cùng vùng) → đánh trả ngay, xoá `_breach_wall`
             và `_cross_commit`. (Vẫn phải cùng vùng — kẻ nấp sau tường bắn ra thì
             titan KHÔNG được phép bỏ tường mà đuổi theo.)
          4. **Tháp GẮN TƯỜNG**: xoá `_breach_wall`/`_cross_commit` TRƯỚC guard bên
             dưới. Nếu không, guard sẽ đè target = HQ và nhánh else reset
             `_cross_commit = 30` mỗi frame → titan KẸT VĨNH VIỄN trong vòng lặp HQ.
          5. **ĐANG BĂNG QUA LỖ TƯỜNG** (`_cross_commit > 0`): GIỮ NGUYÊN mục tiêu
             cũ, không cho đổi. Vì đổi hướng giữa lỗ thủng → titan quay ngang → kẹt
             cứng trong lỗ. Mục tiêu cũ chết giữa chừng → fallback HQ (vẫn đi thẳng).
          6. Còn lại → kiểm tra tường chắn + điều hướng qua lỗ (phần dưới).

        Trả về: entity mục tiêu cuối cùng (có thể KHÁC cái Priority chọn).
        Ghi `self.last_reason` (chuỗi debug giải thích quyết định).
        Liên kết: `WorldQuery.same_zone()`; `priority.select_target()`.
        """
        # Bait Trap Absolute Override
        bt = getattr(self.titan, 'bait_target', None)
        if bt and getattr(bt, 'is_alive', False):
            self.titan._breach_wall = None
            return bt

        target = self.priority.select_target(self.titan, context)

        # If target is an attacker, bypass all overrides and counter immediately
        # Nhưng CHỈ bypass nếu attacker KHÔNG bị chặn bởi tường (cùng zone).
        if target in context.attackers:
            from systems.world_query import WorldQuery
            if getattr(target, '_wall_name', None) or WorldQuery.same_zone(self.titan.x, self.titan.y, target.x, target.y, strict=True):
                self.titan._breach_wall = None
                self.titan._cross_commit = 0
                self._on_decide(context, target)
                return target

        # Wall-tower pre-check: Priority chọn tháp trên tường → clear cross_commit TRƯỚC
        # guard bên dưới. Nếu không, guard đè target=HQ và else-block reset cross_commit=30
        # mỗi frame (tìm thấy lỗ Rose/Sina) → titan không bao giờ thoát HQ-loop khi ở trong.
        if (_type_of(target) == TOWER and getattr(target, '_wall_name', None)
                and _alive(target)):
            self.titan._breach_wall = None
            self.titan._cross_commit = 0

        # Đang BĂNG QUA lỗ → GIỮ mục tiêu cũ; nếu target chết giữa lỗ → fallback HQ
        if getattr(self.titan, '_cross_commit', 0) > 0:
            if _alive(self.target) and _type_of(self.target) != WALL:
                target = self.target
            elif _alive(context.hq):
                target = context.hq  # tránh đổi hướng giữa lỗ khi target vừa chết

        self._on_decide(context, target)
        self.last_reason = ''   # reset mỗi frame — tránh giữ lý do cũ

        # ── Kiểm tra tường chặn + gap navigation ────────────────────
        from systems.world_query import WorldQuery
        _vision = float(getattr(self.titan, 'VISUAL_RANGE', 250.0))
        _hq     = context.hq

        # Zone filter: titan CHỈ đánh tower/lính/commander CÙNG VÙNG với nó.
        # Mục tiêu bên kia tường (khác vùng) → bỏ, đẩy về HQ. Tránh titan đuổi
        # lính/tháp bên kia tường rồi kẹt (và đỡ lệ thuộc vào lỗi nav của lính).
        # Ngoại lệ: tháp TRÊN TƯỜNG (_wall_name) được đánh từ 2 phía (trong/ngoài)
        # → KHÔNG lọc, dù titan đang ở vùng khác với tháp.
        if (target is not None
                and _type_of(target) in (TOWER, SOLDIER, COMMANDER)
                and not getattr(target, '_wall_name', None)):
            if not WorldQuery.same_zone(self.titan.x, self.titan.y, target.x, target.y, strict=True):
                target = _hq if _alive(_hq) else None
            elif _type_of(target) == COMMANDER:
                # Commander cần check thêm Line of Sight
                _blocked = False
                _cx, _cy = target.x, target.y
                _tx, _ty = self.titan.x, self.titan.y
                _dx, _dy = _cx - _tx, _cy - _ty
                _len2 = _dx * _dx + _dy * _dy
                if _len2 > 0:
                    for w in context.walls:
                        if not getattr(w, 'is_alive', False):
                            continue
                        t = ((w.x - _tx) * _dx + (w.y - _ty) * _dy) / _len2
                        if 0.0 < t < 1.0:
                            px, py = _tx + t * _dx, _ty + t * _dy
                            if ((w.x - px) ** 2 + (w.y - py) ** 2) ** 0.5 <= 70.0:
                                _blocked = True
                                break
                if _blocked:
                    target = _hq if _alive(_hq) else None

        # ── Vượt tường (logic THỐNG NHẤT — hết giật/xung đột) ─────────────
        # Nếu đường tới target bị VÒNG TƯỜNG chặn:
        #   • Có lỗ ≥2-tile liền kề → GIỮ target (HQ), _move() lách qua giữa lỗ.
        #   • Chưa có lỗ / chỉ 1-tile → BREACH: target = section cần phá, KHÓA lại
        #     (titan._breach_wall) để act() tiến tới & đập NHẤT QUÁN một chỗ:
        #       - có lỗ 1-tile → phá ô KỀ cùng hàng/cột (nối thành 2-tile liền kề)
        #       - chưa lỗ      → phá section chắn ngay trên đường
        #     Khi đã thành 2-tile → nhánh trên tiếp quản (đi qua lỗ).
        # KHÔNG còn: target nhảy HQ↔wall mỗi frame, _move nhắm lỗ trong khi đập ô
        # khác (tấn công lệch), hay dao động quanh tầm đánh.
        if (target is not None and _alive(target)
                and _type_of(target) == TOWER
                and not getattr(target, '_wall_name', None)):
            locked = getattr(self.titan, '_breach_wall', None)
            if _alive(locked) and math.hypot(
                    locked.x + 16.0 - self.titan.x,
                    locked.y + 16.0 - self.titan.y) <= 140.0:
                target = locked
                self.last_reason = 'phá tường (khóa)'

        if target is not None and _alive(target):
            nav_to = target if _type_of(target) != WALL else _hq
            if not _alive(nav_to):
                nav_to = target
            # ── Tháp TRÊN TƯỜNG: titan đứng phía nào đánh phía đó ────────────────
            # Kiểm tra TRƯỚC locked/commit/gap: _break_blocking_wall() đặt _breach_wall
            # → nếu check ở else-cuối, locked branch sẽ đè mất và titan đập tường section.
            if _type_of(nav_to) == TOWER and getattr(nav_to, '_wall_name', None):
                self.titan._breach_wall = None   # xóa lock tường do _break_blocking_wall đặt
                self.titan._cross_commit = 0     # không gap-crossing; aim thẳng vào tháp
                target = nav_to
                self.last_reason = 'tấn công tháp tường'
            else:
                locked = getattr(self.titan, '_breach_wall', None)
                if not _alive(locked):
                    locked = None
                # Lỗ ≥2-tile phía trước (RẺ — dùng cache cụm). Cam kết băng qua ~0.5s.
                wide = WorldQuery.find_nearest_gap_center(
                    self.titan.x, self.titan.y, nav_to.x, nav_to.y, _vision,
                    min_sections=2)
                if wide is not None:
                    self.titan._cross_commit = 30
                _commit = getattr(self.titan, '_cross_commit', 0)

                if wide is not None:
                    self.titan._breach_wall = None
                    target = nav_to                         # băng qua lỗ ≥2-tile
                    self.last_reason = 'đi qua lỗ ≥2'
                elif locked is not None:
                    # STICKY: đang phá 1 section → BÁM phá tới khi vỡ (hết giật/đập 2
                    # bên xen kẽ/đứng yên). KHÔNG quét find_blocking_wall_to (tiết kiệm).
                    self.titan._cross_commit = 0
                    target = locked
                    self.last_reason = 'phá tường (khóa)'
                elif _commit > 0:
                    self.titan._cross_commit = _commit - 1
                    self.titan._breach_wall = None
                    target = nav_to                         # vừa qua lỗ, đi tiếp
                    self.last_reason = 'đi qua lỗ ≥2'
                else:
                    # Pre-gate RẺ (grid): chỉ quét find_blocking_wall_to (đắt: 506 tường)
                    # khi có tường GẦN phía trước → titan ở xa không tốn → đỡ lag đông.
                    wall_near = False
                    _dnav = math.hypot(nav_to.x - self.titan.x, nav_to.y - self.titan.y)
                    if _dnav > 1.0:
                        ux = (nav_to.x - self.titan.x) / _dnav
                        uy = (nav_to.y - self.titan.y) / _dnav
                        for _dd in (70.0, 140.0, 200.0):
                            if WorldQuery.is_wall_blocked(
                                    self.titan.x + ux * _dd,
                                    self.titan.y + uy * _dd, 80.0):
                                wall_near = True
                                break
                    if not wall_near:
                        self.titan._breach_wall = None
                        target = nav_to                     # đường thông → tới đích
                    else:
                        # block_radius=75: lỗ 1-tile có 2 mép cách tâm ~58-60px, phải >55
                        # mới nhận tường còn chặn khi titan đứng giữa lỗ 1-tile.
                        blocking = WorldQuery.find_blocking_wall_to(
                            self.titan.x, self.titan.y, nav_to.x, nav_to.y,
                            block_radius=75.0)
                        if blocking is None or not _alive(blocking):
                            self.titan._breach_wall = None
                            target = nav_to
                        else:
                            # BỎ trường hợp 1-tile: titan to (r=50) KHÔNG chui lỗ
                            # 1-tile → cứ phá section chắn gần nhất (KHÓA sticky).
                            self.titan._prev_breach_wall = getattr(self.titan, '_breach_wall', None)
                            self.titan._breach_wall = blocking
                            target = blocking
                            self.last_reason = 'phá tường mở lối'

        if target is None:
            self.state = STATE_IDLE
            self.last_reason = self.last_reason or 'không có mục tiêu'
        else:
            self.state = STATE_SEEKING
            self.last_reason = self.last_reason or f'chọn {_describe(target)}'
        return target

    def act(self, dt: float, context: TargetContext) -> None:
        """PHA 3 — HÀNH ĐỘNG: ngoài tầm thì đi tới, trong tầm thì đánh.

        Thuật toán:
          1. Không có target → không làm gì.
          2. Đang telegraph HOẶC đang trong animation đánh → ĐỨNG YÊN, thoát.
             (Không được huỷ đòn giữa chừng.)
          3. Tính `dist` và TẦM ĐÁNH `_atk_range`, có 3 trường hợp ĐẶC BIỆT:
             a. Mục tiêu là LÍNH → dùng `SOLDIER_ATTACK_RANGE` riêng (thường ngắn hơn).
             b. Mục tiêu là THÁP GẮN TƯỜNG → `tower.x/y` là tâm SPRITE, lệch xa so
                với collider của đoạn tường (vd wall_h lệch tới 90px). Nên phải đo
                `dist` tới TÂM WALL SECTION (`_wall_section` + 16px), và nới tầm
                đánh tối thiểu 55px. Không làm vậy → titan đứng cạnh tháp mà "với
                không tới", đánh mãi không trúng ở vài hướng.
             c. Mục tiêu là TƯỜNG → nới tầm = `_wall_radius (50) + 12`.
                **SỬA LỖI ĐỨNG ĐƠ**: thân titan bán kính ~50 bị đoạn tường KỀ BÊN
                chặn nên dừng cách 73–99px, trong khi ngưỡng đánh cũ chỉ ~72px →
                tiến VUÔNG GÓC thì vừa đủ, tiến XIÊN thì hụt vài px → titan đứng
                yên vĩnh viễn không đập tường. Nới theo bán kính thân để bao vùng kẹt.
          4. So `dist - t_rad > _atk_range` (trừ `_get_target_radius` để dừng ở RÌA
             công trình, không đâm vào tâm):
             - NGOÀI TẦM → `_move()` tiến tới. Kèm 2 cứu cánh chống kẹt:
                 · `_path_blocked` và target KHÔNG phải tường → `_break_blocking_wall()`.
                 · target LÀ tường nhưng frame này titan KHÔNG NHÍCH ĐƯỢC (dịch
                   chuyển < 0.05px) → đập đoạn tường chắn gần nhất để mở kẹt.
             - TRONG TẦM → dừng, rồi:
                 · Mục tiêu là **COMMANDER** → BẮT BUỘC qua TELEGRAPH trước
                   (`_telegraph_timer = _TELEGRAPH_DELAY` = 1s, vẽ vòng tròn cảnh
                   báo bán kính = tầm đánh × 2). Đây là cơ chế cho người chơi CƠ HỘI
                   NÉ — chỉ áp cho tướng, lính/tháp/tường bị đánh ngay không báo trước.
                 · Còn lại → `_act_in_range()` (đánh luôn).

        Chỉ số: balance.AI_TELEGRAPH_DELAY, balance.TITAN_SOLDIER_ATTACK_RANGE.
        """
        if self.target is None:
            return

        # Khi telegraph đang chạy, hoặc đang trong animation tấn công: dừng di chuyển
        if self._telegraph_timer > 0.0 or getattr(self.titan, '_is_attacking', False):
            self._stop_moving()
            return

        dist  = _dist(self.titan, self.target)
        t_rad = _get_target_radius(self.target)
        
        if _type_of(self.target) == SOLDIER:
            _atk_range = float(getattr(self.titan, 'SOLDIER_ATTACK_RANGE', 60.0))
        else:
            _atk_range = self._attack_range()
            
        # Tháp trên tường: tower.x/y là tâm sprite visual — có thể lệch nhiều so với
        # wall section collider (vd wall_h: tower.y = ws.y+90 nhưng titan dừng ở ws.y-55).
        # Đo dist tới tâm wall section (ws center 32×32) để attack range check đúng 4 hướng.
        if _type_of(self.target) == TOWER and getattr(self.target, '_wall_name', None):
            _atk_range = max(_atk_range, 55.0)
            _ws_atk = getattr(self.target, '_wall_section', None)
            if _ws_atk is not None:
                dist = math.hypot(_ws_atk.x + 16.0 - self.titan.x,
                                  _ws_atk.y + 16.0 - self.titan.y)
        # Tường: nới tầm đánh đủ rộng để không kẹt khi tiếp cận XIÊN. Thân titan
        # (r≈50) bị section KỀ chặn nên dừng ở 73–99px; tầm đánh gốc (~30) + bán
        # kính tường (42) = ngưỡng 72px → tiến vuông góc vừa đủ, tiến xiên hụt vài
        # px → đứng yên vĩnh viễn không đập. Nới theo bán kính thân để bao vùng kẹt.
        # CHỈ áp cho mục tiêu WALL — không đổi hành vi với mục tiêu khác.
        if _type_of(self.target) == WALL:
            _atk_range = max(_atk_range,
                             float(getattr(self.titan, '_wall_radius', 50.0)) + 12.0)
        if dist - t_rad > _atk_range:
            self.state = STATE_MOVING
            _px_before, _py_before = self.titan.x, self.titan.y
            self._move(dt, self.target)
            # Phá tường CHỈ là cứu cánh khi target KHÔNG phải tường mà vẫn kẹt
            # (không có lỗ ≥2 + không vào được). KHÔNG phá khi đang lách qua lỗ
            # ≥2-tile (target=HQ) — sẽ phá thừa làm lệch tâm. Breach thật sự đã do
            # decide() đặt target=section + _act_in_range đập khi vào tầm.
            if (getattr(self.titan, '_path_blocked', False)
                    and _type_of(self.target) != WALL):
                self._break_blocking_wall(context)
            # ── FIX FREEZE tiến XIÊN vào TƯỜNG (kể cả SAU khi phá mảnh đầu) ──
            # target=WALL nhưng thân titan (r≈50) bị section KỀ chặn → _move KHÔNG
            # nhích được → kẹt ngoài tầm đánh (≤104px) vĩnh viễn, không đập. Nếu
            # frame này titan đứng im (vị trí không đổi) → đập section chắn gần nhất
            # (LOCK + giữ nguyên self.target + theo cooldown) để mở kẹt. Khi còn xa
            # tường (>~80px) đây là no-op an toàn (find_blocking_wall_to rỗng).
            elif (_type_of(self.target) == WALL
                  and abs(self.titan.x - _px_before) < 0.05
                  and abs(self.titan.y - _py_before) < 0.05):
                self._break_blocking_wall(context)
        else:
            self._stop_moving()
            # Commander: bắt buộc qua telegraph trước khi _act_in_range
            is_cmdr = (_type_of(self.target) == COMMANDER)
            cd_ok = (self._attack_cd <= 0.0)
            tele_ok = (self._telegraph_timer == 0.0)
            if is_cmdr and cd_ok and tele_ok:
                self._telegraph_timer  = self._TELEGRAPH_DELAY
                self._telegraph_target = self.target
                self._telegraph_range  = self._attack_range() * 2.0
                self._attack_cd        = self._attack_cooldown()
                self.state = STATE_SKILL
                return
            self._act_in_range(dt, context)

    # ── Điểm mở rộng cho class con (template method) ──────────────

    def _on_decide(self, context: TargetContext, target) -> None:
        """HOOK (template method) — chạy ngay sau khi chọn xong target, trước khi đi.

        Mặc định KHÔNG LÀM GÌ. Class con override để cài xử lý đặc thù mà không
        phải chép lại toàn bộ `decide()`.
        Ví dụ: `ArmoredAI._on_decide()` dùng nó để quyết định có LAO HÚC (dash) hay không.

        Tham số: context — ảnh chụp thế giới; target — mục tiêu vừa chọn.
        """
        pass

    _TELEGRAPH_DELAY = balance.AI_TELEGRAPH_DELAY   # 1s tấn công, check dodge khi hết

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """HOOK (template method) — làm gì khi ĐÃ Ở TRONG TẦM. Mặc định: đánh thường.

        Đây là điểm mở rộng CHÍNH của mọi AI con: Colossal override để tung
        Steam/Stomp, Beast để ném đá, Founding để triệu hồi, Kamikaze để tự nổ…

        Thuật toán mặc định:
          - Xoay mặt về mục tiêu (`_direction_to`).
          - Hết `_attack_cd` → gọi `titan.trigger_attack()` (nếu titan có hàm này)
            để chạy animation, RỒI áp damage qua `_basic_attack()`.
          - Nạp lại cooldown.

        Tham số: dt; context.
        Chỉ số: balance.<TITAN>_ATTACK_COOLDOWN.
        """
        if _type_of(self.target) == SOLDIER:
            self.state = STATE_ATTACKING
            self.titan._direction = _direction_to(self.titan, self.target)
            if self._attack_cd <= 0.0:
                trig = getattr(self.titan, 'trigger_attack', None)
                if callable(trig):
                    trig()
                strat = getattr(self.titan, '_attack_strategy', None)
                if strat is not None:
                    strat.execute(self.titan, self.target)
                self._attack_cd = self._attack_cooldown()
                self.last_reason = f'đánh nhanh lính {_describe(self.target)}'
            return

        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        self._basic_attack()

    def _resolve_telegraph(self) -> None:
        """KẾT ĐÒN telegraph sau 1s: tướng còn trong vòng đỏ → ăn damage; chạy kịp → NÉ.

        Đây là "khoảnh khắc phán quyết" của cơ chế né đòn.

        Thuật toán:
          1. Lấy `_telegraph_target` và `check_range` (bán kính vòng đỏ đã vẽ), rồi
             XOÁ NGAY 2 biến này (dù trúng hay trượt, telegraph coi như kết thúc).
          2. Mục tiêu đã chết → thôi.
          3. Đo `dist` TÂM-ĐẾN-TÂM. **CỐ Ý KHÔNG trừ `t_rad`** — để hitbox trùng
             KHÍT với vòng tròn đỏ mà người chơi nhìn thấy. Trừ `t_rad` sẽ khiến
             "đứng ngoài vòng đỏ mà vẫn ăn đòn" → cảm giác bị ăn gian.
          4. `dist <= check_range` → TRÚNG: chạy animation (`trigger_attack`) rồi
             áp damage (`strategy.execute`), nạp lại cooldown.
             Ngược lại → TRƯỢT, không damage (người chơi né thành công).

        ⚠️ CẠM BẪY (bug thật đã từng xảy ra — "boss đánh gấp đôi"):
        Hàm này gọi CẢ `trigger_attack()` LẪN `strategy.execute()`. Với titan
        thường thì `trigger_attack()` CHỈ chạy animation → tổng 1 đòn, đúng.
        NHƯNG `FoundingTitan.trigger_attack()` TỰ ÁP DAMAGE bên trong → thành 2 đòn,
        tướng ăn gấp đôi (400×2). Vì vậy `FoundingAI` PHẢI override hàm này để chỉ
        gọi `trigger_attack()`. Ai thêm boss mới mà `trigger_attack()` tự gây damage
        thì cũng phải override tương tự.

        Liên kết: `boss.py::FoundingTitan.trigger_attack()`, `FoundingAI._resolve_telegraph()`.
        """
        target      = self._telegraph_target
        check_range = self._telegraph_range if self._telegraph_range > 0 else self._attack_range()
        self._telegraph_target = None
        self._telegraph_range  = 0.0
        if not _alive(target):
            return
        dist   = _dist(self.titan, target)
        t_rad  = _get_target_radius(target)
        # Bỏ trừ t_rad để hitbox khớp hoàn toàn với vòng đỏ trực quan (tâm đến tâm)
        if dist <= check_range:
            # Kích animation đánh đúng lúc damage xảy ra
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
            strat = getattr(self.titan, '_attack_strategy', None)
            if strat is not None:
                strat.execute(self.titan, target)
            self._attack_cd = self._attack_cooldown()  # Reset cooldown sau khi tính damage
            self.last_reason = f'telegraph hit {_describe(target)}'
        else:
            self.last_reason = f'{_describe(target)} né telegraph'

    def _tick_telegraph(self, dt: float) -> bool:
        """Đếm ngược pha "gồng đòn báo trước"; trả True nghĩa là ĐÃ NUỐT frame này.

        Trong lúc telegraph, titan ĐỨNG YÊN gồng tay 1 giây và vẽ vòng tròn đỏ —
        cửa sổ để người chơi chạy ra khỏi vòng mà né.

        Thuật toán:
          1. `_telegraph_timer <= 0` → không telegraph → trả False (caller chạy tiếp
             sense/decide/act bình thường).
          2. Trừ `dt` (kẹp sàn 0). Vừa CHẠM 0 → `_resolve_telegraph()` (phán quyết
             trúng/né).
          3. Ép `self.target` = mục tiêu telegraph, KHÔNG cho `decide()` đổi mục tiêu
             giữa chừng.
          4. `_stop_moving()` — đứng im, đây là điều kiện để né được.
          5. Xoay mặt + chạy animation đánh (nếu chưa chạy).
          6. Trả **True** → caller (`update()`) PHẢI `return` ngay.

        ⚠️ CẠM BẪY (bug thật): AI con nào override `update()` mà KHÔNG gọi
        `super().update()` thì PHẢI tự gọi hàm này ở đầu `update()`. Quên gọi →
        `_telegraph_timer` KHÔNG BAO GIỜ giảm → `act()` thấy timer > 0 nên cứ dừng
        di chuyển → **titan đứng đơ vĩnh viễn**. Đây đúng là lỗi FoundingAI từng mắc
        (boss đứng bất động khi bị tướng đánh). ArmoredAI/ColossalAI/FoundingAI đều
        override `update()` nên đều phải tự gọi.

        Trả về: bool — True = đang telegraph, caller return ngay; False = chạy tiếp.
        Chỉ số: balance.AI_TELEGRAPH_DELAY (1.0s).
        """
        if self._telegraph_timer <= 0.0:
            return False
        self._telegraph_timer = max(0.0, self._telegraph_timer - dt)
        if self._telegraph_timer == 0.0:
            self._resolve_telegraph()
        self.target = self._telegraph_target
        self.titan._ai_current_target = self.target
        self._stop_moving()
        if self.target is not None:
            self.state = STATE_ATTACKING
            self.titan._direction = _direction_to(self.titan, self.target)
            if not getattr(self.titan, '_is_attacking', False):
                trig = getattr(self.titan, 'trigger_attack', None)
                if callable(trig):
                    trig()
        self._advance_animation(dt)
        return True

    # ── Khối dùng lại ────────────────────────────────────────────

    def _attack_range(self) -> float:
        """Tầm đánh (px) của titan này.

        Thuật toán: đọc `titan._attack_range` (mỗi loại titan tự đặt qua class const
        `_DEFAULT_ATTACK_RANGE` ← balance). Titan nào không khai → dùng
        `TitanAI._DEFAULT_ATTACK_RANGE` (← balance.AI_DEFAULT_ATTACK_RANGE = 60px).

        Vì sao dùng `getattr` có mặc định: AI phải chạy được với BẤT KỲ object nào
        (kể cả dummy trong test) mà không vỡ.

        Trả về: float (px).
        Chỉ số: balance.<TITAN>_ATTACK_RANGE, balance.AI_DEFAULT_ATTACK_RANGE.
        """
        return float(getattr(self.titan, '_attack_range',
                             self._DEFAULT_ATTACK_RANGE))

    def _attack_cooldown(self) -> float:
        """Số giây chờ giữa 2 đòn của titan này.

        Đọc `titan._attack_cooldown`; không có → mặc định 1.5s (bằng
        balance.TITAN_ATTACK_COOLDOWN của Titan base).

        Trả về: float (giây). Dùng để nạp lại `self._attack_cd` sau mỗi đòn.
        Chỉ số: balance.<TITAN>_ATTACK_COOLDOWN.
        """
        return float(getattr(self.titan, '_attack_cooldown', 1.5))

    def _basic_attack(self) -> bool:
        """Tung 1 đòn thường qua AttackStrategy — CHỈ áp damage, KHÔNG chạy animation.

        Thuật toán:
          1. Còn cooldown (`_attack_cd > 0`) → trả False (chưa đánh được).
          2. Titan không có `_attack_strategy`, hoặc không có target → False.
          3. `strategy.execute(titan, target)` → damage thật sự xảy ra Ở ĐÂY
             (xem attackstrategy.py: mỗi Strategy tự quyết đánh đơn hay AoE).
          4. Nạp lại `_attack_cd = _attack_cooldown()`.

        Lưu ý phân vai: hàm này KHÔNG gọi `trigger_attack()` (animation). Bên gọi
        (`_act_in_range`) lo phần animation. Tách vậy để boss như Founding — vốn tự
        áp damage trong `trigger_attack()` — không bị đánh 2 lần.

        Trả về: bool — True = đã ra đòn; False = còn cooldown / thiếu điều kiện.
        Chỉ số: balance.STRAT_*_MULT (hệ số damage), balance.<TITAN>_DAMAGE.
        """
        if self._attack_cd > 0.0:
            return False
        strat = getattr(self.titan, '_attack_strategy', None)
        if strat is None or self.target is None:
            return False
        strat.execute(self.titan, self.target)
        self._attack_cd  = self._attack_cooldown()
        self.last_reason = f'đánh {_describe(self.target)}'
        return True

    @staticmethod
    def _gap_aim(titan, target, gc, wall_r):
        """Điểm nhắm để titan vào GIỮA lỗ rồi mới xuyên qua — 2 pha theo hướng tường.

        gc = (cx, cy, is_horizontal). Trục CHẮN (vuông góc tường) cần CĂN GIỮA;
        trục TỰ DO (dọc hướng xuyên) cứ tiến.
          • Pha 1 (chưa căn trục chắn): nhắm tâm-lỗ trên trục chắn, đứng ở PHÍA
            TITAN (cy ± near) → căn giữa mà chưa qua. Tránh đi vào MÉP.
          • Pha 2 (đã căn): lật sang PHÍA TARGET → xuyên qua đúng giữa lỗ.
        near = wall_r + 28: điểm dừng/thoát cách mặt tường đủ để không kẹt.
        """
        cx, cy, is_h = gc
        near = wall_r + 28.0
        if is_h:                                   # tường ngang: căn X, xuyên theo Y
            if abs(titan.x - cx) > 12.0:           # pha 1: chưa căn X
                side = 1.0 if titan.y > cy else -1.0
            else:                                  # pha 2: đã căn → qua phía target
                side = 1.0 if target.y > cy else -1.0
            return cx, cy + side * near
        else:                                      # tường dọc: căn Y, xuyên theo X
            if abs(titan.y - cy) > 12.0:
                side = 1.0 if titan.x > cx else -1.0
            else:
                side = 1.0 if target.x > cx else -1.0
            return cx + side * near, cy

    def _move(self, dt: float, target) -> None:
        """Di chuyển titan tiến về `target`, né tường.

        Luồng (đơn giản, KHÔNG phụ thuộc lưới 32px — tường thật cách 59/54px):
            1. Probe ~30px phía trước. Trống → nhắm thẳng target.
            2. Vướng tường → nhắm tâm THỰC của lỗ hổng gần đường đi nhất
               (find_nearest_gap_center). Nếu đã ở ngay lỗ (<26px) → nhắm
               thẳng target để follow_path tự lách (tránh kẹt trong dải tường).
            3. follow_path lo né cục bộ; bị chặn hoàn toàn → _path_blocked=True
               → act() gọi _break_blocking_wall phá tường.
        """
        from systems.pathmove import follow_path
        titan = self.titan
        tx, ty = _entity_xy(target)
        dx = tx - titan.x
        dy = ty - titan.y
        dist = (dx * dx + dy * dy) ** 0.5

        can_run  = hasattr(titan, '_RUN_ROWS')
        running  = can_run and dist > self._RUN_THRESHOLD
        speed    = float(getattr(titan, '_speed', 60.0)) * float(getattr(titan, '_slow_factor', 1.0))
        if running:
            speed *= self._RUN_SPEED_MULT

        from systems.world_query import WorldQuery
        _px, _py = titan.x, titan.y
        did_move     = False
        path_blocked = False
        WALL_R = float(getattr(titan, '_wall_radius', 50.0))

        # ── BREACH: target là TƯỜNG → ÉP THẲNG vào đúng section đó ───────────
        # Đi THẲNG, KHÔNG né: follow_path sẽ TRƯỢT dọc tường khiến titan lệch khỏi
        # ô cần đập → không bao giờ vào tầm đánh (đứng yên/giật). act() tự dừng &
        # đánh khi `dist - t_rad <= attack_range`. Vị trí khớp ô đang đập → đập
        # NHẤT QUÁN, hết "tấn công lệch", hết xung đột nhắm-lỗ vs đập-ô.
        # safe_stop = WALL_R: titan dừng trước khi chạm vào collision zone của tường
        # (tránh titan bị đẩy vào trong wall → kẹt sau khi section đầu bị phá).
        if _type_of(target) == WALL:
            step = speed * dt
            if dist > 1e-6 and step > 0:
                t_radius = _get_target_radius(target)
                safe_stop = max(WALL_R, t_radius + 20.0)  # Fixed safe distance, not scaled by attack_range
                step = min(step, max(0.0, dist - safe_stop))
                nx = titan.x + dx / dist * step
                ny = titan.y + dy / dist * step
                # Không dịch vào vùng bị chặn bởi tường KHÁC (section kề đang còn sống).
                # Cũng exclude section trước (_prev_breach_wall) nếu titan còn sát bên cạnh —
                # tránh kẹt khi mục tiêu vừa chuyển sang section kề mà chưa thoát khỏi section cũ.
                _prev_excl = getattr(titan, '_prev_breach_wall', None)
                _excl: object = target
                if (_prev_excl is not None and _prev_excl is not target
                        and getattr(_prev_excl, 'is_alive', False)
                        and math.hypot(_prev_excl.x + 16 - titan.x,
                                       _prev_excl.y + 16 - titan.y) <= WALL_R + 6):
                    _excl = {target, _prev_excl}
                if step > 0 and not WorldQuery.is_wall_blocked(nx, ny, WALL_R,
                                                                exclude=_excl):
                    titan.x, titan.y = nx, ny
                    did_move = True
            if dt > 0:
                titan._vx = (titan.x - _px) / dt
                titan._vy = (titan.y - _py) / dt
            titan._path_blocked = False
            titan._direction = _direction_to(titan, target)
            if hasattr(titan, '_is_moving'):
                titan._is_moving = did_move
            if hasattr(titan, '_is_running'):
                titan._is_running = running and did_move
            return

        # ── HQ navigation: lách qua GIỮA lỗ ≥2-tile (hệ thống đang NGON) ──────
        # ARRIVE_R < ngưỡng căn-giữa (12 trong _gap_aim): 'arrived' tại điểm tạm
        # = đã căn đủ → vào pha 2 xuyên qua. Lớn hơn → kẹt pha 1.
        ARRIVE_R = 9.0
        aim_x, aim_y = tx, ty
        _wall_tower = _type_of(target) == TOWER and getattr(target, '_wall_name', None)
        if _wall_tower and dist > 1e-6:
            # Tháp TRÊN TƯỜNG: nhắm mặt tường phía titan đứng, tính từ WALL SECTION.
            # Dùng target.x ± offset không chính xác vì tower.x nằm giữa sprite wall_Y
            # (offset so với ws.x thay đổi theo scale), gây aim point rơi TRONG section
            # mẹ → is_wall_blocked chặn → titan kẹt không vào tầm đánh từ bên trong.
            # Fix: tính aim từ ws.x/ws.y (left/top edge của section 32×32) ± WALL_R + margin.
            _ws = getattr(target, '_wall_section', None)
            _stype = getattr(_ws, 'section_type', '')
            _safe = WALL_R + 5.0    # 55px: đảm bảo không overlap section mẹ (r=50)
            if _stype == 'wall_Y' and _ws is not None:
                # Tường dọc: section rect (ws.x, ws.y, 32, 32).
                # Titan bên trái (trong) → aim tại ws.x - _safe (phía trong tường)
                # Titan bên phải (ngoài) → aim tại ws.x + 32 + _safe (phía ngoài)
                if titan.x < _ws.x + 16:   # titan bên trái = phía trong
                    aim_x = _ws.x - _safe
                else:                       # titan bên phải = phía ngoài
                    aim_x = _ws.x + 32.0 + _safe
                aim_y = target.y
            elif _stype == 'wall_h' and _ws is not None:
                # Tường ngang: section rect (ws.x, ws.y, 32, 32).
                # Titan bên trên (ngoài) → aim tại ws.y - _safe
                # Titan bên dưới (trong) → aim tại ws.y + 32 + _safe
                aim_x = target.x
                if titan.y < _ws.y + 16:   # titan bên trên
                    aim_y = _ws.y - _safe
                else:                       # titan bên dưới
                    aim_y = _ws.y + 32.0 + _safe
            else:
                # Fallback (không có _wall_section hoặc section type khác)
                _off = WALL_R + 1.0
                if abs(dx) >= abs(dy):
                    aim_x = target.x - math.copysign(_off, dx)
                    aim_y = target.y
                else:
                    aim_x = target.x
                    aim_y = target.y - math.copysign(_off, dy)
            ARRIVE_R = 3.0
        elif dist > 1e-6:
            # Phát hiện VÒNG TƯỜNG phía trước bằng DẢI RỘNG (DETECT_BAND) quanh
            # đường đi — KHÔNG chỉ điểm giữa. Lỗ RỘNG có đường-giữa thông nhưng 2
            # MÉP tường vẫn nằm trong dải → vẫn phát hiện → lái vào GIỮA kịp.
            # (Ray-march hẹp = WALL_R chỉ thấy tường khi đâm thẳng vào nó → lỗ
            #  rộng bị coi là "thông" → titan đi thẳng vào MÉP, đúng lỗi đang gặp.)
            ux, uy = dx / dist, dy / dist
            DETECT_BAND = WALL_R + 85.0       # ~135: bắt được mép lỗ tới ~5 tile
            look = dist if dist < 260.0 else 260.0
            d_step = DETECT_BAND * 0.8
            blocking = False
            dd = d_step
            while dd <= look:
                if WorldQuery.is_wall_blocked(titan.x + ux * dd,
                                              titan.y + uy * dd, radius=DETECT_BAND):
                    blocking = True
                    break
                dd += d_step
            if blocking:
                vision = float(getattr(titan, 'VISUAL_RANGE', 250.0))
                gc = WorldQuery.find_nearest_gap_center(
                    titan.x, titan.y, target.x, target.y, vision, min_sections=2
                )
                if gc is not None:
                    # Lỗ ≥2-tile: căn vào điểm-vào (giữa/né-mép) rồi mới xuyên qua.
                    # (Không xử lý lỗ 1-tile ở đây — decide() đã chuyển sang phá tường.)
                    aim_x, aim_y = self._gap_aim(titan, target, gc, WALL_R)

        aim_dist_before = math.hypot(aim_x - _px, aim_y - _py)
        # Nếu titan vừa rời section cũ (_prev_breach_wall) mà còn sát bên,
        # truyền nó làm exclude để follow_path không bị kẹt khi bước đầu rời wall.
        _fp_prev = getattr(titan, '_prev_breach_wall', None)
        _fp_excl = None
        if (_fp_prev is not None and getattr(_fp_prev, 'is_alive', False)
                and math.hypot(_fp_prev.x + 16 - titan.x,
                               _fp_prev.y + 16 - titan.y) <= WALL_R + 6):
            _fp_excl = _fp_prev
        if path_blocked:
            res = 'blocked'
        else:
            res = follow_path(titan, aim_x, aim_y, speed, dt,
                              radius=ARRIVE_R, collide_radius=WALL_R,
                              exclude=_fp_excl)
        did_move = (res == 'moved')
        if res == 'blocked':
            path_blocked = True
            did_move = False
        elif res == 'moved':
            # follow_path có thể né NGANG/LÙI (góc ±90/±110°) → 'moved' nhưng KHÔNG
            # lại gần đích. Với titan (phải xuyên tường vòng), đó là dấu hiệu bị chặn
            # → đánh dấu để _break_blocking_wall phá tường, tránh dao động tại chỗ.
            aim_dist_after = math.hypot(aim_x - titan.x, aim_y - titan.y)
            if aim_dist_after >= aim_dist_before - 0.3:
                path_blocked = True
                did_move = False
        elif res == 'arrived' and (aim_x, aim_y) != (target.x, target.y):
            # Đã tới tâm lỗ — coi như di chuyển; frame sau probe sẽ thông và đi tiếp.
            did_move = True

        # Lưu vận tốc thực (theo đường đi) để knockback nước đẩy ngược hướng đúng
        if dt > 0:
            titan._vx = (titan.x - _px) / dt
            titan._vy = (titan.y - _py) / dt
        titan._path_blocked = path_blocked
        titan._direction = _direction_to(titan, target)
        if hasattr(titan, '_is_moving'):
            titan._is_moving = did_move
        if hasattr(titan, '_is_running'):
            titan._is_running = running and did_move

    def _break_blocking_wall(self, context: TargetContext) -> None:
        """Phá tường CÓ CHỦ ĐÍCH để mở lối — KHÔNG đánh lung tung, KHÔNG giật.

        Quy tắc:
          1. LOCK: đang phá section nào thì phá tới khi VỠ (không đổi mỗi frame).
             → hết "tấn công lung tung".
          2. Đã có lỗ 1-tile nhưng CHƯA có lỗ 2-tile liền kề → phá ô KỀ (cùng
             hàng/cột) để nối thành 2-tile LIỀN NHAU → hệ thống đi-qua-lỗ tiếp quản.
             → hết "kẹt vì các lỗ rời rạc không nối được".
          3. Chưa có lỗ → phá section chắn ngay trên đường titan→target.
        """
        titan  = self.titan
        target = self.target
        if target is None:
            return
        from systems.world_query import WorldQuery

        # 1) LOCK — phá tiếp section đang dở (nếu còn sống & còn ở gần phía trước)
        locked = getattr(titan, '_breach_wall', None)
        if locked is not None and _alive(locked):
            if math.hypot(locked.x + 16.0 - titan.x,
                          locked.y + 16.0 - titan.y) <= 120.0:
                self._attack_wall(locked)
                return
            titan._breach_wall = None      # lock cũ ở xa/sau lưng → bỏ

        # Phá section chắn đường gần nhất (KHÓA sticky). KHÔNG xử lý riêng lỗ 1-tile:
        # phá section trên đường → frame sau section KỀ là gần nhất → phá tiếp →
        # 2-tile LIỀN KỀ tự nhiên (titan to không chui lỗ 1-tile nên coi như tường).
        wall = WorldQuery.find_blocking_wall_to(
            titan.x, titan.y, target.x, target.y, block_radius=70.0)
        if wall is None and _type_of(target) == WALL and _alive(target):
            wall = target
        if wall is None:
            best_wall, best_dist = None, 80.0
            dx_t, dy_t = target.x - titan.x, target.y - titan.y
            far = math.hypot(dx_t, dy_t) > 40.0
            for w in WorldQuery._f_walls:
                cx, cy = w.x + 16.0, w.y + 16.0
                if far and (cx - titan.x) * dx_t + (cy - titan.y) * dy_t < 0:
                    continue                    # bỏ tường sau lưng
                d = math.hypot(cx - titan.x, cy - titan.y)
                if d < best_dist:
                    best_dist, best_wall = d, w
            wall = best_wall

        if wall is not None and _alive(wall):
            titan._prev_breach_wall = getattr(titan, '_breach_wall', None)
            titan._breach_wall = wall
            self._attack_wall(wall)

    def _attack_wall(self, wall) -> None:
        """Tung 1 đòn vào `wall` kèm animation, giữ nguyên self.target.

        Kích trigger_attack (như _act_in_range) — nếu thiếu, tường vẫn bể nhưng
        titan đứng im không hoạt họa ("phá từ xa, mất hoạt họa").
        """
        titan = self.titan
        self.state = STATE_ATTACKING
        titan._direction = _direction_to(titan, wall)
        if self._attack_cd <= 0.0:
            trig = getattr(titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        saved = self.target
        self.target = wall
        try:
            self._basic_attack()
        finally:
            self.target = saved
        self.last_reason = f'phá tường → {_describe(wall)}'

    def _stop_moving(self) -> None:
        """Tắt 2 cờ đi/chạy → titan chuyển sang animation ĐỨNG YÊN.

        Chỉ đụng CỜ ĐỒ HOẠ (`_is_moving`, `_is_running`), KHÔNG đụng x/y. Việc
        titan có thực sự dừng hay không là do `act()` không gọi `_move()` nữa.

        Dùng `hasattr` vì không phải titan nào cũng khai đủ 2 cờ (vd Founding
        không có `_is_running` — nó không biết chạy).

        Gọi khi: đang telegraph, đã vào tầm đánh, hoặc không có mục tiêu.
        """
        if hasattr(self.titan, '_is_moving'):
            self.titan._is_moving = False
        if hasattr(self.titan, '_is_running'):
            self.titan._is_running = False

    def _advance_animation(self, dt: float) -> None:
        """Đẩy animation titan tiến 1 frame — ưu tiên `update_anim()` của titan.

        Thuật toán (uỷ quyền có fallback):
          1. Titan CÓ `update_anim()` (Colossal/Beast/Founding — boss.py) → gọi nó
             và DỪNG. Boss tự lo animation phức tạp (thả đá đúng frame, pause
             triệu hồi…), AI không được giành việc.
          2. Titan KHÔNG có → AI tự đẩy frame bằng `_tick_frames()` (titan thường).

        Vì sao cần: khi AI hoạt động, game loop KHÔNG gọi `titan.update()`, nên nếu
        AI không đẩy animation thì titan sẽ ĐỨNG HÌNH (kẹt ở 1 frame).
        """
        titan = self.titan
        fn = getattr(titan, 'update_anim', None)
        if callable(fn):
            fn(dt)
            return
        self._tick_frames(dt)

    def _tick_frames(self, dt: float) -> None:
        """Máy trạng thái animation cho titan KHÔNG tự quản lý animation.

        Thuật toán — chọn (fps, số frame) theo cờ trạng thái, ưu tiên từ trên xuống,
        mỗi nhánh `return` ngay (loại trừ nhau):
            `_is_attacking` → `_ATTACK_FPS` / `_ATTACK_FRAMES`; đếm ngược
                `_attack_anim_timer`, hết thì tắt cờ và reset về frame 0.
            `_is_steaming`  → `_STEAM_FRAMES`  (Colossal)
            `_is_jumping`   → `_STOMP_FRAMES`  (Colossal)
            `_is_moving`    → `_RUN_FRAMES` nếu đang chạy, ngược lại `_WALK_FRAMES`
            đứng yên       → reset frame 0.

        Mọi hằng số đọc bằng `getattr(..., mặc_định)` → titan thiếu khai báo nào
        vẫn chạy được, không AttributeError.

        Đây đều là số ANIMATION (nằm trong titan.py/boss.py), KHÔNG nằm ở balance.py.
        """
        titan = self.titan
        if not hasattr(titan, '_anim_col'):
            return

        if getattr(titan, '_is_attacking', False):
            fps    = float(getattr(titan, '_ATTACK_FPS',
                                   getattr(titan, '_ANIM_FPS', 10)))
            frames = int(getattr(titan, '_ATTACK_FRAMES', 6))
            if hasattr(titan, '_attack_anim_timer'):
                titan._attack_anim_timer -= dt
            self._step_col(dt, fps, frames)
            if getattr(titan, '_attack_anim_timer', 1.0) <= 0.0:
                titan._is_attacking = False
                titan._anim_col   = 0
                titan._anim_timer = 0.0
            return

        if getattr(titan, '_is_steaming', False):
            self._step_col(dt, float(getattr(titan, '_ANIM_FPS', 10)),
                           int(getattr(titan, '_STEAM_FRAMES', 2)))
            if hasattr(titan, '_steam_anim_timer'):
                titan._steam_anim_timer -= dt
                if titan._steam_anim_timer <= 0.0:
                    titan._is_steaming = False
            return

        if getattr(titan, '_is_jumping', False):
            self._step_col(dt, float(getattr(titan, '_ANIM_FPS', 10)),
                           int(getattr(titan, '_STOMP_FRAMES', 5)))
            if hasattr(titan, '_jump_anim_timer'):
                titan._jump_anim_timer -= dt
                if titan._jump_anim_timer <= 0.0:
                    titan._is_jumping = False
            return

        if getattr(titan, '_is_moving', False):
            running = getattr(titan, '_is_running', False)
            frames  = int(getattr(titan, '_RUN_FRAMES', 8)) if running \
                else int(getattr(titan, '_WALK_FRAMES', 9))
            self._step_col(dt, float(getattr(titan, '_ANIM_FPS', 10)),
                           frames)
            return

        titan._anim_col   = 0
        titan._anim_timer = 0.0

    def _step_col(self, dt: float, fps: float, frames: int) -> None:
        """Tăng cột animation (`_anim_col`) theo nhịp `fps`, lặp vòng khi hết frame.

        Thuật toán — bộ tích luỹ thời gian (time accumulator):
            `step = 1/fps` (giây mỗi frame)
            `_anim_timer += dt`
            `while _anim_timer >= step:`  ← dùng WHILE, không phải IF
                `_anim_timer -= step`
                `_anim_col = (_anim_col + 1) % frames`

        Vì sao WHILE mà không IF: nếu 1 frame game bị giật (dt lớn, vd 0.3s) thì
        animation phải NHẢY NHIỀU FRAME cho kịp, chứ không chỉ 1. Dùng IF sẽ khiến
        animation chạy chậm dần mỗi khi máy lag.
        Vì sao TRỪ `step` thay vì gán 0: giữ lại phần dư thời gian → nhịp animation
        không bị trôi/lệch dần theo thời gian.
        `% frames` → tự lặp vòng về frame 0.

        Bảo vệ: `fps <= 0` hoặc `frames <= 0` → thoát ngay (tránh chia 0 / chia lấy dư 0).
        """
        titan = self.titan
        if fps <= 0 or frames <= 0:
            return
        step = 1.0 / fps
        titan._anim_timer = getattr(titan, '_anim_timer', 0.0) + dt
        while titan._anim_timer >= step:
            titan._anim_timer -= step
            titan._anim_col = (getattr(titan, '_anim_col', 0) + 1) % frames


# ═════════════════════════════════════════════════════════════════
#  DefaultAI — Titan thường (fallback)
# ═════════════════════════════════════════════════════════════════

class DefaultAI(TitanAI):
    """AI DỰ PHÒNG — dùng khi titan không có AI chuyên biệt.

    KHÔNG override gì cả (`pass`): giữ nguyên toàn bộ hành vi của `TitanAI` —
    sense → decide (qua Priority) → act (tiến tới, vào tầm thì đánh thường).

    `make_ai_for()` trả class này khi tên class titan không có trong `AI_BY_TITAN`.
    Nhờ vậy thêm titan mới KHÔNG BAO GIỜ crash vì thiếu AI; nó chỉ đánh thường
    cho tới khi ai đó viết AI riêng.
    """
    pass


# ═════════════════════════════════════════════════════════════════
#  RegularAI — RegularTitan
# ═════════════════════════════════════════════════════════════════

class RegularAI(TitanAI):
    """AI cho RegularTitan — đánh thường có animation vung tay.

    Enrage: HP < _HEAVY_HP_RATIO → đổi sang HeavyStrikeStrategy. (Trước đây
    logic này ở RegularTitan.update() nhưng update() KHÔNG chạy trong AI mode,
    nên AI phải tự kích hoạt.)
    """

    def update(self, dt: float) -> None:
        """Mỗi frame: kiểm tra NỔI KHÙNG (enrage) rồi chạy vòng AI chung.

        Thuật toán ENRAGE (chỉ xảy ra 1 lần, không đảo ngược):
            Chưa nổi khùng VÀ `hp/max_hp < _HEAVY_HP_RATIO` (0.5)
            → bật `_heavy_mode = True` và ĐỔI VĨNH VIỄN `_attack_strategy`
              từ `MeleeRushStrategy` (×1.5) sang `HeavyStrikeStrategy` (×3.5).
            → RegularTitan sắp chết đánh MẠNH HƠN GẤP ĐÔI.
        Cờ `_heavy_mode` đảm bảo chỉ đổi 1 lần (hồi máu lên lại cũng không quay về).

        ⚠️ Vì sao kiểm tra ở ĐÂY chứ không trong `RegularTitan.update()`:
        khi AI hoạt động, game loop KHÔNG gọi `titan.update()` nữa → logic enrage
        đặt trong đó sẽ KHÔNG BAO GIỜ CHẠY. Đây là bug thật đã được chuyển lên AI.

        Sau đó gọi `super().update(dt)` → vòng AI chuẩn (sense → decide → act),
        nên telegraph vẫn được tick bình thường (không cần tự gọi `_tick_telegraph`).

        Chỉ số: balance.REGULAR_TITAN_HEAVY_HP_RATIO, balance.STRAT_HEAVY_STRIKE_MULT.
        """
        t = self.titan
        if (not getattr(t, '_heavy_mode', False)
                and getattr(t, '_max_hp', 0) > 0
                and t._hp / t._max_hp < getattr(t, '_HEAVY_HP_RATIO', 0.4)):
            from characters.titans.attackstrategy import HeavyStrikeStrategy
            t._heavy_mode      = True
            t._attack_strategy = HeavyStrikeStrategy()
        super().update(dt)

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """Đánh thường KÈM animation vung tay.

        Khác bản mặc định của `TitanAI` ở chỗ: gọi thêm `titan.trigger_attack()`
        để CHẠY ANIMATION trước, rồi mới `_basic_attack()` áp damage.
        Không có bước này → tường/lính vẫn mất máu nhưng titan đứng im như tượng
        ("đánh vô hình").

        An toàn: `trigger_attack()` của RegularTitan CHỈ chạy animation, không tự
        gây damage → không bị đánh 2 lần (khác Founding).
        """
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        if self._attack_cd <= 0.0:
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        self._basic_attack()


# ═════════════════════════════════════════════════════════════════
#  ArmoredAI — ArmoredTitan
# ═════════════════════════════════════════════════════════════════

class ArmoredAI(TitanAI):
    """AI cho ArmoredTitan — "cỗ máy phá thành".

    Logic Dash/Stagger/Recoil đã chuyển hết về `titan.py:ArmoredTitan.update_dash_cycle()`.
    AI chỉ:
        1. Phát hiện target=Wall + còn giáp + ngoài tầm → `trigger_dash()`.
        2. Mỗi frame: nếu thân xác đang dash/stagger/recoil → gọi
           `update_dash_cycle(dt, wall)` và để thân xác tự lái.
        3. Còn lại → vòng AI chung (move → attack basic).
    """

    def update(self, dt: float) -> None:
        """Vòng AI của Armored — máy trạng thái VẬT LÝ (dash/stagger/recoil) đè lên AI thường.

        ⚠️ Override `update()` và KHÔNG gọi `super().update()` → PHẢI tự gọi
        `_tick_telegraph(dt)` (dòng dưới), nếu quên thì titan đứng đơ vĩnh viễn.

        Thuật toán, theo thứ tự:
          1. **ĐÃ BIẾN HÌNH** (`_replacement_ai`): giáp vỡ → titan này đã bị thay
             bằng RegularTitan. Uỷ quyền toàn bộ cho AI mới, chỉ sao chép lại
             state/target/last_reason để bên ngoài đọc. (Giữ `self` trong list
             `titan_ais` của game loop, không phải gỡ ra → tránh sửa game loop.)
          2. Chết → DEAD.
          3. **BIẾN HÌNH khi vỡ giáp**: `_armor_intact == False` VÀ không còn đang
             dash/stagger/recoil → `_transform_to_regular()`.
             Phải chờ hết vật lý (`_still_phys`) rồi mới biến hình, nếu không titan
             sẽ biến hình GIỮA cú lùi → nhảy vị trí đột ngột.
          4. Tick cooldown + `_tick_telegraph`.
          5. **`update_dash_cycle()`** — thân xác (titan.py) tự lái, AI chỉ đưa vào
             2 hàm kiểm tra va chạm:
               · `_dash_chk`  dùng bán kính NHỎ `_DASH_HIT_RADIUS` (18px). Vì sao
                 nhỏ: tường wall_Y cách nhau 54px; nếu dùng bán kính thân đầy đủ
                 (~58) thì cú húc bị coi là "va tường bên cạnh" và ABORT SỚM.
               · `_recoil_chk` dùng bán kính THÂN ĐẦY ĐỦ `_wall_radius` (50px) để
                 lùi lại không xuyên qua tường phía sau.
               · Cả 2 đều `exclude` chính đoạn tường vừa húc. Không exclude thì lúc
                 lùi, khoảng cách tới tường đó chỉ ~23px < 58 → bị coi là "đang kẹt
                 trong tường" → recoil bị chặn → **titan kẹt cứng vào tường**.
          6. Phase trả về quyết định frame này:
               'stagger' → choáng sau húc, đứng im.
               'recoil'  → đang lùi lại lấy đà.
               'dash'    → đang lao húc.
             Cả 3 đều `return` ngay (chỉ chạy animation) — AI thường KHÔNG chen vào.
          7. Phase 'idle' → mới chạy vòng AI chuẩn (sense → decide → act).
             `_on_decide()` sẽ kích cú dash tiếp theo nếu cần.

        Chỉ số: balance.ARMORED_TITAN_DASH_* / _RECOIL_DIST / _STAGGER_DURATION /
        _HITS_TO_BREAK / _RAM_HIT_RADIUS.
        """
        # Sau khi transform: delegate tới RegularAI (giữ self trong titan_ais list)
        if hasattr(self, '_replacement_ai') and self._replacement_ai is not None:
            self._replacement_ai.update(dt)
            self.state = self._replacement_ai.state
            self.target = self._replacement_ai.target
            self.last_reason = self._replacement_ai.last_reason
            return

        titan = self.titan
        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            return

        # Giáp vỡ + không còn recoil/stagger → spawn RegularTitan thay thế.
        # Nếu vẫn đang recoil/stagger: tiếp tục dash_cycle để titan lùi đúng
        # vị trí trước khi transform.
        _still_phys = (
            getattr(titan, '_stagger_timer', 0.0) > 0.0
            or getattr(titan, '_recoil_dist_left', 0.0) > 0.0
            or getattr(titan, '_is_dashing', False)
        )
        if not getattr(titan, '_armor_intact', True) and not _still_phys:
            self._transform_to_regular()
            return

        self._attack_cd = max(0.0, self._attack_cd - dt * getattr(self.titan, '_slow_factor', 1.0))
        if self._tick_telegraph(dt):  # override không gọi super() → phải tick ở đây
            return

        from systems.world_query import WorldQuery as _WQ
        # Dash dùng _DASH_HIT_RADIUS nhỏ (18px) để không bị block bởi section lân cận
        # (wall_Y cách nhau 54px — nếu dùng _wall_radius=58 thì bị abort sớm).
        # Recoil dùng _wall_radius đầy đủ (58px) để titan không lùi xuyên tường sau.
        # _dash_target được lưu trong titan khi trigger_dash() — dùng làm exclude cho dash_chk.
        _dr = float(getattr(titan, '_DASH_HIT_RADIUS', 18.0))
        _wr = float(getattr(titan, '_wall_radius', 50.0))
        _dash_tgt = getattr(titan, '_dash_target', None)
        def _dash_chk(nx, ny, _wt=_dash_tgt, _r=_dr):
            """True nếu điểm (nx, ny) bị TƯỜNG chặn — dùng trong lúc LAO HÚC.

            Bán kính NHỎ `_DASH_HIT_RADIUS` (18px) để không bị đoạn tường KỀ BÊN
            (cách 54px) coi là va chạm → cú húc không bị huỷ giữa chừng.
            `exclude` = đúng đoạn tường đang húc (nó là MỤC TIÊU, không phải vật cản).

            (Tham số `_wt`/`_r` bind qua default-arg để "đóng băng" giá trị tại
            thời điểm tạo closure, tránh late-binding.)
            """
            return _WQ.is_wall_blocked(nx, ny, _r, exclude=_wt)
        # Recoil exclude _dash_target: titan vừa húc xong → đang di chuyển RA KHỎI
        # section đó. Nếu không exclude, AABB distance từ phía nam chỉ ~23px < 58
        # → is_wall_blocked = True ngay lập tức → recoil bị block, titan kẹt tường.
        _recoil_excl = _dash_tgt
        if _dash_tgt is not None:
            _recoil_excl = [w for w in _WQ.all()
                            if getattr(w, 'ENTITY_TYPE', None) == 'wall'
                            and (w.x - _dash_tgt.x)**2 + (w.y - _dash_tgt.y)**2 <= 70.0**2]

        def _recoil_chk(nx, ny, _wt=_recoil_excl, _r=_wr):
            """True nếu điểm (nx, ny) bị TƯỜNG chặn — dùng trong lúc LÙI LẠI (recoil).

            Khác `_dash_chk`: dùng bán kính THÂN ĐẦY ĐỦ `_wall_radius` (50px) để
            titan lùi lại không lún xuyên qua tường phía sau lưng.

            `exclude` KHÔNG chỉ là 1 đoạn tường vừa húc mà là CẢ CỤM tường quanh nó
            (mọi wall trong bán kính 70px của `_dash_target`). Lý do: sau khi húc,
            titan nằm sát cụm tường đó; đo khoảng cách AABB từ phía nam chỉ ~23px
            < 50 → mọi điểm lùi đều bị coi là "trong tường" → recoil bị chặn hoàn
            toàn → **titan kẹt dính vào tường vĩnh viễn**.
            """
            return _WQ.is_wall_blocked(nx, ny, _r, exclude=_wt)
        phase = titan.update_dash_cycle(dt, wall_check=_dash_chk, recoil_check=_recoil_chk)

        if phase == 'stagger':
            self.state = STATE_SKILL
            self.last_reason = 'stagger sau húc'
            self._advance_animation(dt)
            return
        if phase == 'recoil':
            self.state = STATE_MOVING
            self.last_reason = f'walk lùi ({titan._recoil_dist_left:.0f}px còn lại)'
            self._advance_animation(dt)
            return
        if phase == 'dash':
            self.state = STATE_SKILL
            _dt = getattr(titan, '_dash_target', None)
            self.last_reason = (f'Ram húc {_dt.__class__.__name__ if _dt else "?"}'
                                f' — hits={getattr(titan,"_ram_hits",0)}')
            self._advance_animation(dt)
            return

        # phase == 'idle' và giáp còn → _on_decide sẽ trigger dash nếu cần
        context = self.sense()
        self.target = self.decide(context)
        titan._ai_current_target = self.target
        self.act(dt, context)
        self._advance_animation(dt)

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """Đánh khi vào tầm — giáp vỡ thì hạ cấp về đòn thường của TitanAI.

        Thuật toán:
          - `_armor_intact == False` (đã vỡ giáp) → gọi thẳng `super()._act_in_range()`
            (hành vi titan thường).
          - Còn giáp → xoay mặt, chạy animation (`trigger_attack`), rồi `_basic_attack()`
            (lúc này `_attack_strategy` là `ArmoredRamStrategy` ×6.7, dtype='ram' —
            đòn phá tường cực mạnh).

        Ghi chú: cú LAO HÚC (dash) KHÔNG diễn ra ở đây; nó do `_on_decide()` kích
        khi mục tiêu là tường VÀ còn Ở NGOÀI tầm.
        Chỉ số: balance.STRAT_ARMORED_RAM_MULT.
        """
        if not getattr(self.titan, '_armor_intact', True):
            super()._act_in_range(dt, context)
            return
        self.state = STATE_ATTACKING
        titan = self.titan
        titan._direction = _direction_to(titan, self.target)
        if self._attack_cd <= 0.0:
            trig = getattr(titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        self._basic_attack()

    def _on_decide(self, context: TargetContext, target) -> None:
        """KÍCH CÚ LAO HÚC (dash) — khi nhắm TƯỜNG, còn giáp, và đang Ở XA.

        Đây là lý do Armored đáng sợ: nó không đi bộ tới tường mà LẤY ĐÀ LAO VÀO,
        gây damage 'ram' ×6.7.

        4 điều kiện BẮT BUỘC (thiếu 1 là thôi):
          1. Có target VÀ `_armor_intact` (vỡ giáp thì hết húc).
          2. Chưa đang dash (`_is_dashing`) — không chồng cú húc.
          3. Mục tiêu phải là **WALL** — không húc lính/tháp.
          4. **Đang NGOÀI tầm đánh** (`dist - t_rad > _attack_range()`). Đã đứng sát
             tường rồi thì đánh thường, không cần lấy đà.

        Đủ điều kiện → `titan.trigger_dash()` (titan.py), truyền hướng + tốc độ chạy
        (đã nhân `_slow_factor` → dính IceTower thì húc chậm hơn).

        Đây là HOOK được `decide()` gọi tự động, không ai gọi trực tiếp.
        Chỉ số: balance.ARMORED_TITAN_DASH_SPEED_MULT / _DASH_MAX_DIST.
        """
        titan = self.titan
        if target is None or not getattr(titan, '_armor_intact', True):
            return
        if getattr(titan, '_is_dashing', False):
            return
        if _type_of(target) != WALL:
            return
        dist = _dist(titan, target)
        t_rad = _get_target_radius(target)
        if dist - t_rad <= self._attack_range():
            return
        trig = getattr(titan, 'trigger_dash', None)
        if callable(trig):
            dx = target.x - titan.x
            dy = target.y - titan.y
            run_speed = float(getattr(titan, '_speed', 60.0)) * float(getattr(titan, '_slow_factor', 1.0))
            if trig(dx, dy, run_speed, dash_target=target):
                self.state = STATE_SKILL
                self.last_reason = 'Dash húc Wall'

    def _transform_to_regular(self) -> None:
        """Giáp vỡ + recoil xong → spawn RegularTitan, delegate AI to it.

        RegularTitan nhận HP còn lại + slow effect từ ArmoredTitan.
        ArmoredAI tự thay đổi titan reference + delegate update() tới RegularAI.
        Không trigger on_death() → không cấp reward khi transform.
        """
        from systems.world_query import WorldQuery
        from characters.titans.titan import RegularTitan
        titan = self.titan

        # Tạo RegularTitan mới tại chỗ
        new_t = RegularTitan(titan.x, titan.y)
        new_t._hp        = max(1, int(getattr(titan, '_hp', 1)))
        new_t._max_hp    = int(getattr(titan, '_max_hp', new_t._hp))
        new_t._reward    = dict(getattr(titan, '_reward', {}))
        new_t._direction = int(getattr(titan, '_direction', 2))
        new_t._slow_timer  = float(getattr(titan, '_slow_timer', 0.0))
        new_t._slow_factor = float(getattr(titan, '_slow_factor', 1.0))

        # Tạo RegularAI cho titan mới
        new_ai = make_ai_for(new_t, self.world)

        # Spawn + dọn dẹp
        WorldQuery.spawn_entity(new_t)
        WorldQuery.remove_entity(titan)
        titan.is_alive = False

        # Chuyển đổi ArmoredAI → delegation mode (giữ nguyên reference trong titan_ais)
        self.titan = new_t  # thay đổi titan reference
        self.priority = new_ai.priority  # share priority object
        self._replacement_ai = new_ai  # backup ref for debugging
        self.state = new_ai.state
        self.target = new_ai.target


# ═════════════════════════════════════════════════════════════════
#  WolfAI — Wolf
# ═════════════════════════════════════════════════════════════════

class WolfAI(TitanAI):
    """AI cho Wolf — cắn nhanh, truyền debuff CHẶN HỒI MÁU (antiheal).

    Bản thân AI này không có logic đặc biệt (chỉ thêm animation). Sự nguy hiểm của
    Wolf nằm ở 2 chỗ KHÁC:
      · `WolfPriority` (priority.py) — ưu tiên phản đòn TƯỚNG trước mọi thứ.
      · `Incurable` (attackstrategy.py) — dtype='antiheal' → cắn trúng tướng là
        chặn `heal()` 15 giây, kể cả hồi máu ở vùng castle.
    """

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """Cắn: xoay mặt → chạy animation → áp damage (kèm debuff antiheal).

        Giống bản mặc định nhưng thêm `trigger_attack()` để có animation vung tay.
        Debuff antiheal KHÔNG áp ở đây — nó nằm trong `dtype='antiheal'` của
        `Incurable`, do chính mục tiêu tự xử lý trong `take_damage()`.

        Chỉ số: balance.STRAT_INCURABLE_MULT, balance.COMMANDER_ANTI_HEAL_DURATION.
        """
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        if self._attack_cd <= 0.0:
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        self._basic_attack()


# ═════════════════════════════════════════════════════════════════
#  TowerHunterAI — TowerHunter
# ═════════════════════════════════════════════════════════════════

class TowerHunterAI(TitanAI):
    """AI cho TowerHunter — chuyên hạ tháp ("siege").

    Skill: target=Tower → siege ×1.5 (TowerHunterStrategy), khác → HeavyStrike.
    (Trước đây switch ở TowerHunter.update() nhưng update() không chạy trong AI.)
    """

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """ĐỔI STRATEGY ngay trước khi đánh: mục tiêu là tháp → siege, còn lại → heavy.

        Thuật toán:
          1. Xoay mặt về mục tiêu.
          2. **Hoán strategy theo loại mục tiêu** (mấu chốt):
                 target.ENTITY_TYPE == 'tower' → `_siege_strategy`
                     (TowerHunterStrategy: ×3.0 và còn ×1.5 THÊM khi trúng Tower)
                 ngược lại                      → `_heavy_strategy` (HeavyStrike ×3.5)
             Chỉ hoán khi titan có SẴN cả 2 strategy (`getattr` khác None) — an toàn.
          3. Chạy animation + `_basic_attack()`.

        ⚠️ Vì sao đặt ở AI: trước đây việc hoán strategy nằm trong
        `TowerHunter.update()`, nhưng khi AI hoạt động thì `titan.update()` KHÔNG
        được gọi → strategy KHÔNG BAO GIỜ đổi → titan mất hẳn đòn siege. Đã chuyển
        lên đây. (Cùng loại lỗi với enrage của RegularAI.)

        Chỉ số: balance.STRAT_TOWER_HUNTER_MULT, balance.STRAT_HEAVY_STRIKE_MULT.
        """
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        # Switch strategy theo loại target
        _siege = getattr(self.titan, '_siege_strategy', None)
        _heavy = getattr(self.titan, '_heavy_strategy', None)
        if _siege is not None and _heavy is not None:
            if (self.target is not None
                    and getattr(self.target, 'ENTITY_TYPE', '') == 'tower'):
                self.titan._attack_strategy = _siege
            else:
                self.titan._attack_strategy = _heavy
        if self._attack_cd <= 0.0:
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        self._basic_attack()


# ═════════════════════════════════════════════════════════════════
#  SoldierHunterAI — SoldierHunter
# ═════════════════════════════════════════════════════════════════

class SoldierHunterAI(TitanAI):
    """AI cho SoldierHunter — Titan to xác săn lính, đòn cleave AoE.

    Skill: target=Soldier → cleave AoE (SoldierHunterStrategy), khác → HeavyStrike.
    (Trước đây switch ở SoldierHunter.update() nhưng update() không chạy trong AI.)
    """

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """ĐỔI STRATEGY trước khi đánh: mục tiêu là LÍNH → cleave AoE, còn lại → heavy.

        Thuật toán:
          1. Xoay mặt về mục tiêu.
          2. **Hoán strategy theo loại mục tiêu**:
                 target.ENTITY_TYPE == 'soldier' → `_soldier_strategy`
                     (SoldierHunterStrategy: đánh chính + CHÉM LAN nửa damage ra
                      mọi entity quanh attacker — kể cả tường/tháp/HQ)
                 ngược lại                        → `_heavy_strategy` (HeavyStrike)
          3. Chạy animation + `_basic_attack()`.

        ⚠️ Cùng lý do với TowerHunterAI: việc hoán strategy vốn nằm trong
        `SoldierHunter.update()` — hàm KHÔNG chạy khi AI hoạt động → đòn cleave
        không bao giờ kích hoạt. Đã chuyển lên AI.

        Hệ quả gameplay: lính đứng CỤM rất nguy hiểm — 1 đòn lan ra cả đám.
        Chỉ số: balance.STRAT_SOLDIER_HUNTER_MULT.
        """
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        # Switch strategy theo loại target
        _soldier = getattr(self.titan, '_soldier_strategy', None)
        _heavy   = getattr(self.titan, '_heavy_strategy', None)
        if _soldier is not None and _heavy is not None:
            if (self.target is not None
                    and getattr(self.target, 'ENTITY_TYPE', '') == 'soldier'):
                self.titan._attack_strategy = _soldier
            else:
                self.titan._attack_strategy = _heavy
        if self._attack_cd <= 0.0:
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        self._basic_attack()


# ═════════════════════════════════════════════════════════════════
#  KamikazeAI — Kamikaze
# ═════════════════════════════════════════════════════════════════

class KamikazeAI(TitanAI):
    """AI cho Kamikaze — bom tự sát lao vào cụm lính.

    Hành vi 3 giai đoạn:
        • Phát hiện Soldier/Commander trong `_DETECT_RADIUS` → khóa kẻ gần
          nhất, CHẠY về phía nó với tốc độ ×`_RUN_SPEED_MULT`.
        • Vào `_EXPLODE_RADIUS` → set `titan._target` rồi `trigger_explosion()`.
        • Không còn lính/tướng → đi bộ về mục tiêu theo Priority.

    Bù AoE: Explosion strategy chỉ quét 'soldier'. AI bù sát thương cho
    tower/commander quanh tâm nổ — chạy đúng 1 lần khi `_has_exploded`.

    Riêng khi mục tiêu kích nổ là COMMANDER (THÊM MỚI): đếm ngược rút ngắn còn
    `_CMDR_EXPLODE_PAUSE` (thay vì `_PRE_EXPLODE_PAUSE` mặc định) + hiện vòng
    tròn cảnh báo phạm vi nổ (tái dùng cơ chế telegraph-circle có sẵn trong
    game.py) — bù lại việc `Explosion.execute()` giờ chỉ gây damage chính cho
    commander nếu NÓ CÒN Ở TRONG vùng nổ lúc phát nổ (né được nếu chạy kịp).
    Soldier/Tower giữ nguyên hành vi cũ (luôn dính, không cảnh báo).
    """

    _CMDR_EXPLODE_PAUSE = balance.AI_KAMIKAZE_CMDR_EXPLODE_PAUSE   # giây — ngắn hơn _PRE_EXPLODE_PAUSE (1.0s) mặc định

    def update(self, dt: float) -> None:
        """Vòng AI của Kamikaze — 3 giai đoạn: SĂN → ĐẾM NGƯỢC → NỔ.

        ⚠️ Override `update()` không gọi `super()` → phải TỰ tick telegraph.

        Thuật toán, theo thứ tự:
          1. **ĐÃ NỔ** (`_has_exploded`) → DEAD, chỉ chạy nốt animation. Đây là cờ
             một-chiều chống nổ 2 lần.
          2. Chết (bị giết trước khi kịp nổ) → DEAD.
          3. **ĐANG ĐẾM NGƯỢC** (`_is_pausing`): đứng yên gồng mình chờ nổ.
             - Nếu mục tiêu là TƯỚNG → đồng bộ `_telegraph_timer` với `_pause_timer`
               thật của titan → **vòng tròn đỏ cảnh báo** hiển thị đúng thời gian
               còn lại. Đây là cơ chế cho người chơi CƠ HỘI NÉ (tái dùng hệ thống
               telegraph-circle sẵn có của game.py).
             - Nổ xong → xoá telegraph.
          4. Chưa nổ → săn mồi: phát hiện lính/tướng trong `_DETECT_RADIUS` (300px)
             → khoá con GẦN NHẤT và CHẠY tới với tốc độ ×`_RUN_SPEED_MULT` (×2).
          5. Vào `_EXPLODE_RADIUS` (60px) → `trigger_explosion()`:
             - Mục tiêu là TƯỚNG → đếm ngược NGẮN `_CMDR_EXPLODE_PAUSE` (0.5s) +
               bật vòng cảnh báo.
             - Lính/tháp → `_PRE_EXPLODE_PAUSE` (1.0s), KHÔNG cảnh báo (luôn dính).
          6. Không có mồi → đi bộ về mục tiêu do Priority chọn.

        Điểm gameplay quan trọng: `Explosion.execute()` nổ theo VÙNG quanh Kamikaze
        — tướng CHẠY RA KHỎI vùng kịp thì KHÔNG dính, y như mọi entity khác.

        Chỉ số: balance.KAMIKAZE_DETECT_RADIUS / _EXPLODE_RADIUS / _RUN_SPEED_MULT /
        _PRE_EXPLODE_PAUSE / _EXP_AOE_RADIUS, balance.AI_KAMIKAZE_CMDR_EXPLODE_PAUSE.
        """
        titan = self.titan

        if getattr(titan, '_has_exploded', False):
            self.state = STATE_DEAD
            self._advance_animation(dt)
            return

        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            return

        if getattr(titan, '_is_pausing', False):
            self.state = STATE_SKILL
            self.last_reason = 'pause — sắp nổ'
            self._stop_moving()
            # Đồng bộ vòng tròn cảnh báo (nếu target là commander) với đúng
            # thời gian đếm ngược thật của titan — chỉ set khi telegraph đã
            # được bật lúc trigger (xem nhánh explode_r bên dưới).
            if self._telegraph_target is not None:
                self._telegraph_timer = getattr(titan, '_pause_timer', 0.0)
            self._advance_animation(dt)
            if getattr(titan, '_has_exploded', False):
                self._telegraph_target = None
                self._telegraph_timer  = 0.0
            return

        # Tick cooldown (parent không gọi được)
        self._attack_cd = max(0.0, self._attack_cd - dt * getattr(self.titan, '_slow_factor', 1.0))

        context = self.sense()
        detect_r = float(getattr(titan, '_DETECT_RADIUS', 300.0))
        prey = self._nearest_prey(context, detect_r)

        if prey is not None:
            # Soldier/Commander detected → explosion strategy
            self.target = prey
            titan._ai_current_target = prey
            titan._attack_strategy = getattr(titan, '_explosion_strategy', None)
            dist = _dist(titan, prey)
            explode_r = float(getattr(titan, '_EXPLODE_RADIUS', 80.0))
            t_rad = _get_target_radius(prey)
            if dist - t_rad <= explode_r:
                self.state = STATE_SKILL
                self.last_reason = f'kích nổ tại {_describe(prey)}'
                titan._target = prey
                if _type_of(prey) == COMMANDER:
                    # Tướng: đếm ngược rút ngắn + vòng tròn cảnh báo (THÊM MỚI)
                    titan._PRE_EXPLODE_PAUSE = self._CMDR_EXPLODE_PAUSE
                    self._telegraph_target   = prey
                    self._telegraph_range    = float(getattr(titan, '_EXP_AOE_RADIUS', 80.0))
                    self._TELEGRAPH_DELAY    = self._CMDR_EXPLODE_PAUSE
                    self._telegraph_timer    = self._CMDR_EXPLODE_PAUSE
                trig = getattr(titan, 'trigger_explosion', None)
                if callable(trig):
                    trig()
            else:
                self.state = STATE_MOVING
                self.last_reason = f'lao vào {_describe(prey)}'
                self._rush(dt, prey)
        else:
            # Không có lính/tướng → nhắm tường chắn hoặc HQ trực tiếp
            if _alive(context.blocking_wall):
                target = context.blocking_wall
            elif _alive(context.hq):
                target = context.hq
            else:
                target = None

            self.target = target
            titan._ai_current_target = target
            titan._attack_strategy = getattr(titan, '_heavy_strategy', None)

            if target is None:
                self.state = STATE_IDLE
                self._stop_moving()
            else:
                dist    = _dist(titan, target)
                t_rad   = _get_target_radius(target)
                atk_r   = self._attack_range()
                # Nới tầm đánh cho TƯỜNG (giống base act) để không kẹt tiến xiên
                if _type_of(target) == WALL:
                    atk_r = max(atk_r,
                                float(getattr(titan, '_wall_radius', 50.0)) + 12.0)

                if dist - t_rad > atk_r:
                    self.state = STATE_MOVING
                    _kpx, _kpy = titan.x, titan.y
                    self._move(dt, target)
                    # FIX FREEZE: kẹt tiến XIÊN vào tường (thân bị section KỀ chặn,
                    # _move đứng im) → đập section chắn gần nhất để mở kẹt. Kamikaze
                    # override update() nên phải vá riêng ở đây (không qua base act).
                    if (_type_of(target) == WALL
                            and abs(titan.x - _kpx) < 0.05
                            and abs(titan.y - _kpy) < 0.05):
                        self._break_blocking_wall(context)
                else:
                    self.state = STATE_ATTACKING
                    self._stop_moving()
                    titan._direction = _direction_to(titan, target)
                    if self._attack_cd <= 0.0:
                        trig = getattr(titan, 'trigger_attack', None)
                        if callable(trig):
                            trig()
                    self._basic_attack()

        self._advance_animation(dt)

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """Kamikaze vào tầm: mục tiêu là NGƯỜI → dùng đòn NỔ; là công trình → heavy.

        Thuật toán hoán strategy (đặt ở đây vì "sắp đánh thật"):
            target là 'soldier' hoặc 'commander' → `_explosion_strategy`
                (Explosion ×6.7, nổ theo VÙNG quanh Kamikaze)
            còn lại (tường/tháp/HQ)              → `_heavy_strategy`
                (đập bình thường, KHÔNG tự sát — Kamikaze không phí mạng vào tường)

        Rồi chạy animation + `_basic_attack()`.

        Chỉ số: balance.STRAT_EXPLOSION_MULT, balance.KAMIKAZE_EXP_AOE_RADIUS.
        """
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)

        # Chuyển đổi strategy TẠI ĐÂY (sắp đánh thực tế)
        if self.target is not None:
            if _type_of(self.target) == SOLDIER or _type_of(self.target) == COMMANDER:
                self.titan._attack_strategy = getattr(self.titan, '_explosion_strategy', None)
            else:
                self.titan._attack_strategy = getattr(self.titan, '_heavy_strategy', None)

        if self._attack_cd <= 0.0:
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        self._basic_attack()

    def _nearest_prey(self, context: TargetContext, radius: float):
        """Soldier/Commander/Tower còn sống gần nhất trong bán kính phát hiện,
        CÙNG VÙNG với titan (trừ tháp trên tường, đánh được từ 2 phía — NHƯNG
        chỉ 2 vùng THỰC SỰ giáp đúng tường đó) — KamikazeAI tự implement
        _nearest_prey riêng (không qua decide()/Priority) nên phải tự check
        zone ở đây, không thì titan "xuyên tường" lao vào lính/tướng/tháp
        khác vùng miễn đủ gần theo đường chim bay.

        FIX: bản cũ `getattr(e, '_wall_name', None) or same_zone(...)` miễn
        zone-check cho BẤT KỲ tháp gắn tường nào (dù ở tường khác, vùng khác
        hoàn toàn) — y hệt bug đã sửa ở TowerHunterPriority/BeastPriority
        (priority.py). Giờ chỉ miễn khi titan đang đứng ở 1 trong 2 vùng
        THỰC SỰ giáp ĐÚNG cây tường mà tháp đó gắn lên."""
        from systems.world_query import WorldQuery
        titan = self.titan
        best, best_d = None, radius
        titan_zone = WorldQuery.zone_of(titan.x, titan.y)
        for e in list(context.soldiers) + list(context.commanders) + list(context.towers):
            if not _alive(e):
                continue
            wall_name = getattr(e, '_wall_name', None)
            if wall_name:
                ok = titan_zone in WorldQuery.zones_for_wall(wall_name)
            else:
                ok = WorldQuery.same_zone(titan.x, titan.y, e.x, e.y, strict=True)
            if not ok:
                continue
            d = _dist(titan, e)
            if d <= best_d:
                best_d, best = d, e
        return best

    def _rush(self, dt: float, target) -> None:
        """CHẠY nhanh (run ×`_RUN_SPEED_MULT`) về phía target — có né tường.

        FIX: bản cũ cộng thẳng (dx/dist)*speed*dt vào titan.x/y, KHÔNG hề kiểm
        tra va chạm tường (khác `_move()` — luôn gọi `is_wall_blocked` trước khi
        commit bước đi) → nếu cùng zone bị tính sai (hoặc target là tháp trên
        tường ở phía đối diện), titan xuyên thẳng qua tường CÒN NGUYÊN VẸN.
        Giờ kiểm tra vị trí đích trước; nếu bị chặn thật bởi tường còn sống thì
        nhường lại cho `_move()` (đã có sẵn né tường/tìm khe hở/tự aim đúng mặt
        tường khi target là tháp gắn tường) thay vì xuyên qua.
        """
        from systems.world_query import WorldQuery
        titan = self.titan
        mult = float(getattr(titan, '_RUN_SPEED_MULT', 1.5))
        dx = target.x - titan.x
        dy = target.y - titan.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0:
            speed = float(getattr(titan, '_speed', 80.0)) * mult * float(getattr(titan, '_slow_factor', 1.0))
            step = speed * dt
            nx = titan.x + (dx / dist) * step
            ny = titan.y + (dy / dist) * step
            wall_r = float(getattr(titan, '_wall_radius', 50.0))
            if WorldQuery.is_wall_blocked(nx, ny, wall_r):
                self._move(dt, target)
                return
            titan.x, titan.y = nx, ny
        titan._direction = _direction_to(titan, target)
        if hasattr(titan, '_is_moving'):
            titan._is_moving = True
        if hasattr(titan, '_is_running'):
            titan._is_running = True


# ═════════════════════════════════════════════════════════════════
#  ColossalAI — ColossalTitan (Boss màn 3)
# ═════════════════════════════════════════════════════════════════

class ColossalAI(TitanAI):
    """AI cho ColossalTitan — boss to lớn, 2 kỹ năng AoE theo cooldown.

    Hành vi:
        • Tiến về mục tiêu (DefaultPriority — hướng HQ/Wall).
        • `_jump_timer` ≤ 0 → Jump Stomp.
        • `_steam_timer` ≤ 0 → Steam Burst.
        • Đang tung skill → đứng yên chờ.
    """

    def __init__(self, titan, world: WorldView,
                 priority: TargetPriorityStrategy = None) -> None:
        """Gắn AI + NẠP SẴN cooldown 2 skill để boss không tung skill ngay frame đầu.

        Vấn đề: `ColossalTitan.__init__` đặt `_steam_timer = _jump_timer = 0.0`
        (nghĩa là "sẵn sàng ngay"). Nếu để nguyên, boss vừa xuất hiện đã lập tức
        Steam Burst + Jump Stomp — người chơi chưa kịp thấy gì đã ăn combo.

        Cách xử lý: nếu timer đang <= 0 thì NẠP ĐẦY bằng cooldown → boss phải đi bộ
        một lúc trước cú skill đầu tiên.

        Chỉ số: balance.COLOSSAL_STEAM_COOLDOWN (8s), balance.COLOSSAL_JUMP_COOLDOWN (10s).
        """
        super().__init__(titan, world, priority)
        # Seed cooldown để titan đi bộ trước, chưa tung skill ngay frame đầu.
        if getattr(titan, '_steam_timer', 0.0) <= 0.0:
            titan._steam_timer = float(getattr(titan, '_steam_cooldown', 8.0))
        if getattr(titan, '_jump_timer', 0.0) <= 0.0:
            titan._jump_timer = float(getattr(titan, '_jump_cooldown', 15.0))

    def update(self, dt: float) -> None:
        """Vòng AI của Colossal — 2 skill AoE theo cooldown, ưu tiên hơn đánh thường.

        ⚠️ Override `update()` không gọi `super()` → phải TỰ gọi `_tick_telegraph`.

        Thuật toán:
          1. Cập nhật hạt hơi nóng (đồ hoạ) — chạy MỌI LÚC, kể cả khi boss chết dở.
          2. Chết → DEAD.
          3. Đếm ngược `_steam_timer`, `_jump_timer`, `_attack_cd`.
          4. `_tick_telegraph(dt)` → đang gồng đòn thì thoát.
          5. **ĐANG TUNG SKILL** (`_is_steaming` / `_is_jumping`) → đứng yên, chỉ
             chạy animation. Không đi, không đánh, không ra quyết định mới.
          6. sense → decide (chọn mục tiêu).
          7. **ƯU TIÊN SKILL HƠN ĐÁNH THƯỜNG**: thử `_try_jump_stomp()` trước, rồi
             `_try_steam_burst()`. Hễ tung được skill là `return` NGAY (bỏ qua
             `act()`) → boss không vừa đánh vừa tung skill.
             Thứ tự có chủ đích: Jump Stomp (stun tháp) xét TRƯỚC Steam Burst.
          8. Không skill nào sẵn sàng → `act()` (đi tới / đánh thường).

        Lưu ý: skill KHÔNG cần mục tiêu trong tầm — chúng nổ theo VÙNG quanh boss,
        cứ hết cooldown là tung.

        Chỉ số: balance.COLOSSAL_STEAM_COOLDOWN / _JUMP_COOLDOWN / _STOMP_AOE /
        _STEAM_R_IN / _STEAM_R_OUT.
        """
        titan = self.titan

        if hasattr(titan, '_heat_particles'):
            titan._heat_particles = [
                p for p in titan._heat_particles if p.update(dt)
            ]

        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            return

        titan._steam_timer = max(0.0, getattr(titan, '_steam_timer', 0.0) - dt)
        titan._jump_timer  = max(0.0, getattr(titan, '_jump_timer', 0.0) - dt)
        self._attack_cd    = max(0.0, self._attack_cd - dt)
        if self._tick_telegraph(dt):  # override không gọi super() → phải tick ở đây
            return

        busy = getattr(titan, '_is_steaming', False) \
            or getattr(titan, '_is_jumping', False)
        if busy:
            self.state = STATE_SKILL
            self._stop_moving()
            self._advance_animation(dt)
            return

        context = self.sense()
        self.target = self.decide(context)
        titan._ai_current_target = self.target

        if self._try_jump_stomp():
            self._advance_animation(dt)
            return
        if self._try_steam_burst():
            self._advance_animation(dt)
            return

        self.act(dt, context)
        self._advance_animation(dt)

    def _try_jump_stomp(self) -> bool:
        """Tung SKILL 2 (Jump Stomp) nếu đã hồi xong. Trả True = đã tung.

        Thuật toán:
          1. `_jump_timer > 0` → chưa hồi → False.
          2. Titan không có hàm `_jump_stomp` → False (an toàn).
          3. Gọi skill → giậm đất: STUN mọi tháp trong 160px + damage lính/tướng
             (hình TRÒN ĐẶC, áp sát KHÔNG né được).
          4. Nạp lại `_jump_timer = _jump_cooldown`.

        Trả về: bool — True thì `update()` phải `return` ngay (không đánh thường nữa).
        Chỉ số: balance.COLOSSAL_JUMP_COOLDOWN / _STOMP_AOE / _STOMP_STUN_DUR / _STOMP_DMG.
        """
        if getattr(self.titan, '_jump_timer', 1.0) > 0.0:
            return False
        skill = getattr(self.titan, '_jump_stomp', None)
        if not callable(skill):
            return False
        skill()
        self.titan._jump_timer = getattr(self.titan, '_jump_cooldown', 15.0)
        self.state = STATE_SKILL
        self.last_reason = 'Jump Stomp (AoE 160px)'
        return True

    def _try_steam_burst(self) -> bool:
        """Tung SKILL 1 (Steam Burst) nếu đã hồi xong. Trả True = đã tung.

        Giống `_try_jump_stomp` về cấu trúc, nhưng skill này phun hơi theo VÀNH
        KHUYÊN (bán kính trong 40 → ngoài 140) → **đứng SÁT NÁCH boss thì an toàn**.
        Đây là điểm khác biệt gameplay quan trọng so với Jump Stomp.

        Trả về: bool — True thì `update()` return ngay.
        Chỉ số: balance.COLOSSAL_STEAM_COOLDOWN / _STEAM_R_IN / _STEAM_R_OUT /
        _STEAM_FIRE_DMG / _STEAM_BURN_DMG.
        """
        if getattr(self.titan, '_steam_timer', 1.0) > 0.0:
            return False
        skill = getattr(self.titan, '_steam_burst', None)
        if not callable(skill):
            return False
        skill()
        self.titan._steam_timer = getattr(self.titan, '_steam_cooldown', 8.0)
        self.state = STATE_SKILL
        self.last_reason = 'Steam Burst (vành khuyên)'
        return True

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """Đòn thường của Colossal (GroundSlam — đánh + STUN tháp quanh 160px).

        Khác các AI khác: `trigger_attack(self.target)` được truyền THAM SỐ target
        (Colossal cần biết mục tiêu để xoay mặt đúng trong animation).

        Lưu ý: ngay cả đòn THƯỜNG của Colossal cũng stun tháp, vì
        `_attack_strategy = GroundSlamStrategy(radius=160, stun_duration=3.0)`.

        Chỉ số: balance.STRAT_GROUND_SLAM_MULT, balance.COLOSSAL_DAMAGE.
        """
        self.state = STATE_ATTACKING
        titan = self.titan
        titan._direction = _direction_to(titan, self.target)
        if self._attack_cd <= 0.0:
            trig = getattr(titan, 'trigger_attack', None)
            if callable(trig):
                trig(self.target)
        self._basic_attack()


# ═════════════════════════════════════════════════════════════════
#  BeastAI — BeastTitan (Boss màn 4)
# ═════════════════════════════════════════════════════════════════

class BeastAI(TitanAI):
    """AI cho BeastTitan — boss ném đá tầm xa, săn tháp.

    Hành vi:
        • BeastPriority chọn mục tiêu (ưu tiên Tower).
        • Trong `THROW_RANGE` + hồi → `trigger_attack(target)`.
        • Ngoài tầm → đi bộ lại gần.
        • Đang trong animation ném → đứng yên.
    """

    def update(self, dt: float) -> None:
        """Vòng AI của Beast — PHÁO BINH: đứng ngoài tầm tháp mà ném đá.

        ⚠️ Override `update()` → gọi `titan.update_anim()` (qua `_advance_animation`)
        chứ TUYỆT ĐỐI không gọi `titan.update()` (đó là AI nội bộ demo, sẽ đánh nhau
        với AI này).
        Lưu ý: AI này KHÔNG gọi `_tick_telegraph` — Beast không telegraph (nó đánh
        tầm xa, không cần cơ chế né cận chiến).

        Thuật toán:
          1. Chết → DEAD (vẫn chạy animation cho đá đang bay rơi nốt).
          2. Đếm ngược `_throw_timer` (nhịp ném).
          3. **ĐANG VUNG TAY NÉM** (`_is_attacking`) → đứng yên, chỉ chạy animation
             rồi thoát. Đây là lúc `update_anim()` sẽ thả đá đúng frame
             `_ROCK_RELEASE_FRAME`. Không được huỷ giữa chừng.
          4. sense → decide (BeastPriority ưu tiên THÁP).
          5. Không có mục tiêu → IDLE.
          6. So `dist` với `THROW_RANGE` (350px):
             - TRONG tầm + hết cooldown → `trigger_attack(target)` (bắt đầu vung
               tay; đá bay ra sau). Nạp lại `_throw_timer = _throw_cooldown`.
             - NGOÀI tầm → `_move()` đi lại gần.
             - TRONG tầm nhưng CÒN cooldown → **ĐỨNG YÊN** (SEEKING), KHÔNG áp sát.
               Đây chính là hành vi "pháo binh": giữ khoảng cách, không xông vào
               tầm bắn của tháp.

        Chỉ số: balance.BEAST_ATTACK_RANGE (tầm ném 350), balance.BEAST_ATTACK_COOLDOWN.
        """
        titan = self.titan
        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            self._advance_animation(dt)
            return

        titan._throw_timer = max(0.0, getattr(titan, '_throw_timer', 0.0) - dt)

        if getattr(titan, '_is_attacking', False):
            self.state = STATE_SKILL
            self._stop_moving()
            self._advance_animation(dt)
            return

        context = self.sense()
        self.target = self.decide(context)
        titan._ai_current_target = self.target

        if self.target is None:
            self.state = STATE_IDLE
            self._advance_animation(dt)
            return

        throw_range = float(getattr(titan, '_THROW_RANGE',
                                    getattr(titan, 'THROW_RANGE', 350.0)))
        dist = _dist(titan, self.target)

        if dist <= throw_range and getattr(titan, '_throw_timer', 1.0) <= 0.0:
            trig = getattr(titan, 'trigger_attack', None)
            if callable(trig) and trig(self.target):
                titan._throw_timer = getattr(titan, '_throw_cooldown', 5.0)
                titan._direction   = _direction_to(titan, self.target)
                self.state = STATE_SKILL
                self.last_reason = f'ném đá vào {_describe(self.target)}'
        elif dist > throw_range:
            self.state = STATE_MOVING
            self._move(dt, self.target)
        else:
            self.state = STATE_SEEKING
            self._stop_moving()

        self._advance_animation(dt)


# ═════════════════════════════════════════════════════════════════
#  FoundingAI — FoundingTitan (Final Boss)
# ═════════════════════════════════════════════════════════════════

class FoundingAI(TitanAI):
    """AI cho FoundingTitan — final boss 3 phase.

    Hành vi theo phase:
        • P1 (HP>80%) / P3 (HP≤30%): áp sát đánh HeavyStrike.
        • P2 (30–80%): tự summon mỗi `_SUMMON_WAVE_COOLDOWN` giây.
        • Đang summon/attacking → đứng yên chờ animation.

    AI cũng tick AI cho mỗi minion summon — minion tự đi đánh
    Tower/Soldier/Commander/Wall/HQ như entity độc lập.
    """

    def update(self, dt: float) -> None:
        """Vòng AI của FINAL BOSS — 3 phase, phase 2 triệu hồi thay vì đánh.

        ⚠️ Override `update()` không gọi `super()` → **BẮT BUỘC tự gọi
        `_tick_telegraph(dt)`**. Thiếu dòng đó chính là bug thật đã xảy ra: khi boss
        nhắm TƯỚNG, `act()` bật `_telegraph_timer` rồi return; các frame sau `act()`
        thấy timer > 0 nên cứ dừng di chuyển, mà KHÔNG AI GIẢM TIMER →
        **boss đứng bất động vĩnh viễn ngay khi bị tướng đánh**.

        Thuật toán:
          1. Gắn `titan.world` (cần để tạo AI cho minion sau này).
          2. Chết → DEAD, nhưng VẪN `_tick_minions()` — minion phải sống tiếp và
             đánh nốt dù boss đã chết.
          3. Đếm ngược `_summon_cd_timer`, `_attack_cd_timer`, `_attack_cd`.
          4. `_check_phase()` — cập nhật phase theo HP MỖI FRAME (có thể khoá vĩnh
             viễn phase 3, xem boss.py).
          5. `_tick_telegraph(dt)` → đang gồng đòn thì thoát, NHƯNG vẫn tick minion
             (không để minion đơ theo boss).
          6. Đang TRIỆU HỒI hoặc đang VUNG TAY → đứng yên, chạy animation, tick
             minion, thoát.
          7. sense → decide.
          8. **PHASE 2 → `_try_summon()` ưu tiên hơn đánh**. Triệu hồi được là
             `return` ngay. (Phase 1 và 3 bỏ qua bước này → chỉ đánh thường.)
          9. Còn lại → `act()` (logic cha, đã kiểm chứng).

        Ghi chú: minion là entity ĐỘC LẬP, có `_ai` riêng do game loop tự update.
        `_tick_minions()` ở đây chỉ là dự phòng cho các nhánh return sớm.

        Chỉ số: balance.FOUNDING_P1_HP_RATIO / _P3_HP_RATIO / _SUMMON_WAVE_COOLDOWN,
        balance.AI_TELEGRAPH_DELAY.
        """
        titan = self.titan
        # Ensure titan has world reference for minion AI creation
        if not hasattr(titan, 'world'):
            titan.world = self.world
        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            self._tick_minions(dt)
            return

        if hasattr(titan, '_summon_cd_timer'):
            titan._summon_cd_timer = max(0.0, titan._summon_cd_timer - dt)
        if hasattr(titan, '_attack_cd_timer'):
            titan._attack_cd_timer = max(0.0, titan._attack_cd_timer - dt)
        self._attack_cd = max(0.0, self._attack_cd - dt * getattr(self.titan, '_slow_factor', 1.0))

        check = getattr(titan, '_check_phase', None)
        if callable(check):
            check()

        # SỬA LỖI: FoundingAI override update() và KHÔNG gọi super(), nên phải
        # tự tick telegraph ở đây (y hệt ArmoredAI/ColossalAI). Thiếu dòng này
        # thì khi boss nhắm COMMANDER, `act()` bật `_telegraph_timer` rồi return;
        # từ frame sau `act()` gặp `if self._telegraph_timer > 0: stop; return`
        # mà không ai giảm timer → boss ĐỨNG YÊN VĨNH VIỄN ngay khi tướng đánh nó.
        # Vẫn tick minion trong lúc telegraph để chúng không bị đơ theo.
        if self._tick_telegraph(dt):
            self._tick_minions(dt)
            return

        if getattr(titan, '_is_summoning', False):
            self.state = STATE_SKILL
            self.last_reason = 'đang summon minion'
            self._stop_moving()
            self._advance_animation(dt)
            self._tick_minions(dt)
            return

        if getattr(titan, '_is_attacking', False):
            self.state = STATE_ATTACKING
            self.last_reason = 'HeavyStrike (đang vung tay)'
            self._stop_moving()
            self._advance_animation(dt)
            self._tick_minions(dt)
            return

        context = self.sense()
        self.target = self.decide(context)
        titan._ai_current_target = self.target

        if getattr(titan, '_phase', 1) == 2 and self._try_summon():
            self._advance_animation(dt)
            self._tick_minions(dt)
            return

        # Use proven parent logic for movement/attack
        self.act(dt, context)

        self._advance_animation(dt)
        # NOTE: Minion AI no longer ticked here — each minion has independent _ai updated by game loop

    # ── Quản lý AI minion summon ─────────────────────────────────

    def _tick_minions(self, dt: float) -> None:
        """Gắn AI cho minion MỚI và chạy AI cho từng con (dự phòng khi boss return sớm).

        Thuật toán:
          1. Không có minion → thoát.
          2. `_minion_ais`: dict `{id(minion): AI}` — tạo lazy lần đầu.
          3. Minion nào CHƯA có AI → `make_ai_for(m, world)` (tự chọn AI theo tên
             class minion). Lỗi → lưu None, KHÔNG crash cả boss.
          4. Duyệt minion:
             - Chết → gỡ AI khỏi dict (tránh rò rỉ bộ nhớ).
             - Sống → `ai.update(dt)`, bọc try/except: 1 minion lỗi KHÔNG được làm
               sập AI của boss.

        Dùng `id(m)` làm khoá vì entity không hashable ổn định theo giá trị.

        Lưu ý: trong game thật, mỗi minion đã có `_ai` riêng được GAME LOOP update.
        Hàm này chủ yếu để minion không bị "đơ" ở những frame mà boss `return` sớm
        (đang telegraph / đang triệu hồi / đã chết).
        """
        titan = self.titan
        minions = getattr(titan, '_summoned_minions', None)
        if not minions:
            return

        if not hasattr(self, '_minion_ais'):
            self._minion_ais: dict = {}

        for m in minions:
            mid = id(m)
            if mid in self._minion_ais:
                continue
            try:
                self._minion_ais[mid] = make_ai_for(m, self.world)
            except Exception:
                self._minion_ais[mid] = None

        for m in list(minions):
            if not getattr(m, 'is_alive', False):
                self._minion_ais.pop(id(m), None)
                continue
            ai = self._minion_ais.get(id(m))
            if ai is not None:
                try:
                    ai.update(dt)
                except Exception:
                    pass

    def _try_summon(self) -> bool:
        """Thử TRIỆU HỒI nếu đã hồi cooldown. Trả True = đã bắt đầu triệu hồi.

        Thuật toán:
          1. `_summon_cd_timer > 0` → chưa hồi → False.
          2. Titan không có `start_summon` → False.
          3. `start_summon()` tự kiểm tra thêm 3 điều kiện nữa (phải đúng phase 2,
             không đang bận, và `_summon_locked` chưa bật) → nó có thể vẫn từ chối.
          4. Thành công → `return True`, `update()` sẽ `return` ngay (không đánh nữa).

        Lưu ý: minion CHƯA ra đời ở đây — mới chỉ bắt đầu ANIMATION gồng. Minion ra
        đời (và boss hồi máu) ở `_release_summon()`, sau animation + 2s pause.

        Chỉ số: balance.FOUNDING_SUMMON_WAVE_COOLDOWN (15s), _SUMMON_TOTAL.
        """
        if getattr(self.titan, '_summon_cd_timer', 1.0) > 0.0:
            return False
        start = getattr(self.titan, 'start_summon', None)
        if not callable(start):
            return False
        if start():
            self.state = STATE_SKILL
            self.last_reason = 'SUMMON 10 minion'
            return True
        return False

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """Đòn thường của Founding — CHỈ gọi `trigger_attack()`, KHÔNG `_basic_attack()`.

        ⚠️ ĐÂY LÀ ĐIỂM DỄ SAI NHẤT: `FoundingTitan.trigger_attack()` **tự áp damage**
        bên trong (khác mọi titan khác, vốn chỉ chạy animation). Vì vậy ở đây TUYỆT
        ĐỐI KHÔNG được gọi thêm `self._basic_attack()` — làm vậy tướng sẽ ăn
        **damage 2 lần**.

        Thuật toán:
          1. Xoay mặt về mục tiêu.
          2. Hết cooldown → gán `titan._ai_current_target = target` (vì
             `trigger_attack()` KHÔNG nhận tham số, nó ĐỌC biến này), rồi gọi
             `trigger_attack()` → animation + damage cùng lúc.
          3. Animation do `trigger_attack()` + `update_anim()` lo, không cần
             `_advance_animation` ở đây.

        Chỉ số: balance.FOUNDING_DAMAGE, balance.FOUNDING_ATTACK_COOLDOWN.
        """
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        if self._attack_cd <= 0.0:
            self.titan._ai_current_target = self.target  # Set target for trigger_attack()
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        # Note: animation managed by trigger_attack() + update_anim()

    def _resolve_telegraph(self) -> None:
        """OVERRIDE BẮT BUỘC — sửa bug "boss đánh gấp đôi".

        Vấn đề gốc: `TitanAI._resolve_telegraph()` (lớp cha) gọi CẢ
        `titan.trigger_attack()` LẪN `strategy.execute()`.
          · Titan thường: `trigger_attack()` chỉ chạy ANIMATION → tổng 1 đòn. ĐÚNG.
          · **Founding**: `trigger_attack()` TỰ ÁP DAMAGE → thành 2 đòn → tướng ăn
            gấp đôi (vd 400 × 2 = 800). SAI.

        Bản override này CHỈ gọi `trigger_attack()` (đã bao gồm damage), bỏ hẳn
        `strategy.execute()`.

        Thuật toán (giống cha, trừ bước áp damage):
          1. Lấy target + `check_range`, xoá ngay `_telegraph_*`.
          2. Target chết → thôi.
          3. Đo TÂM-ĐẾN-TÂM (không trừ `t_rad`) để khớp khít vòng đỏ người chơi thấy.
          4. Trong vòng → gán `_ai_current_target` rồi `trigger_attack()` → ăn ĐÚNG
             1 đòn. Ngoài vòng → NÉ được, không damage.

        📌 Quy tắc chung: boss nào có `trigger_attack()` tự gây damage thì PHẢI
        override hàm này y như vậy.
        """
        target      = self._telegraph_target
        check_range = self._telegraph_range if self._telegraph_range > 0 else self._attack_range()
        self._telegraph_target = None
        self._telegraph_range  = 0.0
        if not _alive(target):
            return
        dist = _dist(self.titan, target)
        if dist <= check_range:
            self.titan._ai_current_target = target
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
            self._attack_cd = self._attack_cooldown()
            self.last_reason = f'telegraph hit {_describe(target)}'
        else:
            self.last_reason = f'{_describe(target)} né telegraph'


# ═════════════════════════════════════════════════════════════════
#  Bảng tra cứu + Factory
# ═════════════════════════════════════════════════════════════════

AI_BY_TITAN: dict = {
    'RegularTitan':  RegularAI,
    'ArmoredTitan':  ArmoredAI,
    'Wolf':          WolfAI,
    'TowerHunter':   TowerHunterAI,
    'SoldierHunter': SoldierHunterAI,
    'Kamikaze':      KamikazeAI,
    'ColossalTitan': ColossalAI,
    'BeastTitan':    BeastAI,
    'FoundingTitan': FoundingAI,
}


def make_ai_for(titan, world: WorldView,
                priority: TargetPriorityStrategy = None) -> TitanAI:
    """Tạo bộ AI phù hợp cho `titan` dựa theo tên class.

    Loại không có AI riêng → DefaultAI. Priority None → tự suy ra
    theo loại titan (qua priority.make_priority_for).

    Ví dụ:
        ai = make_ai_for(titan, SimpleWorldView(hq=hq, towers=towers))
        while running:
            ai.update(dt)
    """
    cls = AI_BY_TITAN.get(type(titan).__name__, DefaultAI)
    return cls(titan, world, priority)
