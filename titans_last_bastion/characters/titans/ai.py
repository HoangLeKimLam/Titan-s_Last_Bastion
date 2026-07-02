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
        """Dựng TargetContext — ảnh chụp thế giới cho `titan` ở frame này."""
        ...

    def soldiers_in_radius(self, cx: float, cy: float,
                           radius: float) -> list:
        """Soldier còn sống trong bán kính (cho skill AoE)."""
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
        self.hq         = hq
        self.walls      = list(walls or [])
        self.towers     = list(towers or [])
        self.soldiers   = list(soldiers or [])
        self.commanders = list(commanders or [])
        self._block_radius = block_radius

    def build_context(self, titan) -> TargetContext:
        attackers = list(getattr(titan, '_ai_attackers', []))
        current   = getattr(titan, '_ai_current_target', None)
        blocking  = self._find_blocking_wall(titan)

        # Visual range — tính thẳng từ danh sách của SimpleWorldView,
        # không đi qua WorldQuery (tránh lỗi entity chưa được spawn_entity).
        vr2 = float(getattr(titan, 'VISUAL_RANGE', 250.0)) ** 2

        def _in_vrange(e):
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
        """Tìm wall còn sống nằm chắn giữa titan và HQ (hình học đơn giản)."""
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
    return e is not None and getattr(e, 'is_alive', False)


def _dist(a, b) -> float:
    ax, ay = _entity_xy(a)
    bx, by = _entity_xy(b)
    dx = ax - bx
    dy = ay - by
    return (dx * dx + dy * dy) ** 0.5


def _entity_xy(e) -> tuple:
    if getattr(e, 'ENTITY_TYPE', '') == WALL:
        return float(e.x) + 16.0, float(e.y) + 16.0
    return float(e.x), float(e.y)


def _direction_to(src, dst) -> int:
    """Hướng nhìn (0=N,1=W,2=S,3=E) từ `src` tới `dst`."""
    sx, sy = _entity_xy(src)
    dx = _entity_xy(dst)[0] - sx
    dy = _entity_xy(dst)[1] - sy
    if abs(dx) >= abs(dy):
        return 3 if dx > 0 else 1
    return 2 if dy > 0 else 0


def _type_of(e) -> str:
    """ENTITY_TYPE của entity, '' nếu không có."""
    return getattr(e, 'ENTITY_TYPE', '')

def _get_target_radius(e) -> float:
    """Bán kính rìa ngoài của công trình để titan không đi đâm xuyên vào tâm."""
    etype = _type_of(e)
    if etype in ('tower', 'hq'):
        return 40.0
    if etype == 'wall':
        return 42.0
    return 0.0


def _describe(e) -> str:
    """Chuỗi mô tả ngắn cho entity — ưu tiên label/name, fallback ENTITY_TYPE."""
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

    _DEFAULT_ATTACK_RANGE = 60.0
    _RUN_THRESHOLD = 250.0
    _RUN_SPEED_MULT = 1.5

    def __init__(self, titan, world: WorldView,
                 priority: TargetPriorityStrategy = None) -> None:
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
        """Chạy 1 frame AI: sense → decide → act → đẩy animation."""
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
        """Báo cho AI biết `attacker` vừa tấn công titan này."""
        lst = self.titan._ai_attackers
        if attacker is not None and attacker not in lst:
            lst.append(attacker)

    # ── Ba pha của vòng AI ───────────────────────────────────────

    def sense(self) -> TargetContext:
        """Pha 1 — thu thập thông tin thế giới."""
        self.titan._ai_attackers = [
            a for a in self.titan._ai_attackers if _alive(a)
        ]
        return self.world.build_context(self.titan)

    def decide(self, context: TargetContext):
        """Pha 2 — chọn mục tiêu (ủy quyền cho Priority).

        Sau khi Priority chọn target, kiểm tra thêm:
        Nếu target là soldier/commander/tower nhưng có tường bao chặn đường
        titan → đổi sang tường đó (phải phá trước mới tới được target thật).

        NGOẠI LỆ: target trong attackers list (vừa tấn công) → KHÔNG override, trực tiếp counter-attack.
        """
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
        """Pha 3 — hành động: tiến tới mục tiêu rồi tấn công."""
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
        """Hook sau khi Priority chọn target, trước khi di chuyển."""
        pass

    _TELEGRAPH_DELAY = 1.0   # 1s tấn công, check dodge khi hết

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """Hành động khi đã ở trong tầm đánh — mặc định: đòn đánh cơ bản."""
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
        """Sau 1s telegraph: kiểm tra tướng còn trong tầm không → damage hoặc miss."""
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
        """Tick telegraph phase; trả True → caller nên return ngay.

        ArmoredAI / ColossalAI override update() không gọi super() nên
        phải tự gọi method này ở đầu update() để telegraph hoạt động đúng.
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
        return float(getattr(self.titan, '_attack_range',
                             self._DEFAULT_ATTACK_RANGE))

    def _attack_cooldown(self) -> float:
        return float(getattr(self.titan, '_attack_cooldown', 1.5))

    def _basic_attack(self) -> bool:
        """Tung 1 đòn đánh cơ bản qua AttackStrategy nếu đã hồi xong."""
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
        if hasattr(self.titan, '_is_moving'):
            self.titan._is_moving = False
        if hasattr(self.titan, '_is_running'):
            self.titan._is_running = False

    def _advance_animation(self, dt: float) -> None:
        """Đẩy animation của titan tiến 1 frame.

        Titan CÓ `update_anim()` → gọi (giữ logic gốc).
        Titan KHÔNG có → AI tự đẩy theo cờ trạng thái.
        """
        titan = self.titan
        fn = getattr(titan, 'update_anim', None)
        if callable(fn):
            fn(dt)
            return
        self._tick_frames(dt)

    def _tick_frames(self, dt: float) -> None:
        """Tự đẩy frame cho titan KHÔNG có `update_anim()`."""
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
    """AI mặc định: tiến về mục tiêu, tới tầm thì đánh cơ bản."""
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
        t = self.titan
        if (not getattr(t, '_heavy_mode', False)
                and getattr(t, '_max_hp', 0) > 0
                and t._hp / t._max_hp < getattr(t, '_HEAVY_HP_RATIO', 0.4)):
            from characters.titans.attackstrategy import HeavyStrikeStrategy
            t._heavy_mode      = True
            t._attack_strategy = HeavyStrikeStrategy()
        super().update(dt)

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
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
        """Mục tiêu là Wall + còn giáp + ngoài tầm → kích Dash lao húc."""
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
    """AI cho Wolf — Titan thân nhỏ cắn nhanh, truyền debuff antiheal."""

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
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
    """

    def __init__(self, titan, world: WorldView,
                 priority: TargetPriorityStrategy = None) -> None:
        super().__init__(titan, world, priority)
        self._aoe_done = False
        self._blast_xy = None

    def update(self, dt: float) -> None:
        titan = self.titan

        if getattr(titan, '_has_exploded', False):
            self.state = STATE_DEAD
            self._explosion_aoe_extra()
            self._advance_animation(dt)
            return

        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            return

        if getattr(titan, '_is_pausing', False):
            self.state = STATE_SKILL
            self.last_reason = 'pause — sắp nổ'
            self._stop_moving()
            self._advance_animation(dt)
            if getattr(titan, '_has_exploded', False):
                self._explosion_aoe_extra()
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
                self._blast_xy = (titan.x, titan.y)
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
        """Trong tầm: set strategy đúng lúc rồi đánh."""
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
        """Soldier/Commander/Tower còn sống gần nhất trong bán kính phát hiện."""
        titan = self.titan
        best, best_d = None, radius
        for e in list(context.soldiers) + list(context.commanders) + list(context.towers):
            if not _alive(e):
                continue
            d = _dist(titan, e)
            if d <= best_d:
                best_d, best = d, e
        return best

    def _rush(self, dt: float, target) -> None:
        """CHẠY nhanh (run ×`_RUN_SPEED_MULT`) về phía target."""
        titan = self.titan
        mult = float(getattr(titan, '_RUN_SPEED_MULT', 1.5))
        dx = target.x - titan.x
        dy = target.y - titan.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0:
            speed = float(getattr(titan, '_speed', 80.0)) * mult * float(getattr(titan, '_slow_factor', 1.0))
            titan.x += (dx / dist) * speed * dt
            titan.y += (dy / dist) * speed * dt
        titan._direction = _direction_to(titan, target)
        if hasattr(titan, '_is_moving'):
            titan._is_moving = True
        if hasattr(titan, '_is_running'):
            titan._is_running = True

    def _explosion_aoe_extra(self) -> None:
        """Bù damage + đẩy lùi AoE cho Tower/Commander trong tầm nổ."""
        if self._aoe_done:
            return
        self._aoe_done = True

        titan = self.titan
        cx, cy = self._blast_xy or (titan.x, titan.y)
        radius = float(getattr(titan, '_EXP_AOE_RADIUS', 80.0))
        strat  = getattr(titan, '_attack_strategy', None)
        splash = int(getattr(strat, '_damage_splash',
                             getattr(titan, '_EXP_DAMAGE_SPLASH', 100)))
        knock  = float(getattr(strat, '_knockback',
                               getattr(titan, '_EXP_KNOCKBACK', 60.0)))

        r2 = radius * radius
        victims = list(getattr(self.world, 'towers', [])) \
            + list(getattr(self.world, 'commanders', []))
        for e in victims:
            if not _alive(e):
                continue
            dx = e.x - cx
            dy = e.y - cy
            if dx * dx + dy * dy > r2:
                continue
            hit = getattr(e, 'take_damage', None)
            if callable(hit):
                try:
                    hit(amount=splash, dtype='explode')
                except TypeError:
                    hit(splash, 'explode')
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > 0:
                e.x += (dx / dist) * knock
                e.y += (dy / dist) * knock
        self.last_reason = 'nổ AoE — bù tower/commander'


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
        super().__init__(titan, world, priority)
        # Seed cooldown để titan đi bộ trước, chưa tung skill ngay frame đầu.
        if getattr(titan, '_steam_timer', 0.0) <= 0.0:
            titan._steam_timer = float(getattr(titan, '_steam_cooldown', 8.0))
        if getattr(titan, '_jump_timer', 0.0) <= 0.0:
            titan._jump_timer = float(getattr(titan, '_jump_cooldown', 15.0))

    def update(self, dt: float) -> None:
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
        """Trong tầm: kích animation vung tay + áp damage."""
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
        """Mỗi frame: phát hiện minion mới → gắn AI, tick AI cho mỗi minion."""
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
        """Gọi start_summon() nếu đã hồi."""
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
        """Override parent: call trigger_attack() for animation support."""
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        if self._attack_cd <= 0.0:
            self.titan._ai_current_target = self.target  # Set target for trigger_attack()
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        # Note: animation managed by trigger_attack() + update_anim()

    def _founding_attack(self) -> None:
        """DEPRECATED: Use _act_in_range() instead."""
        pass


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
