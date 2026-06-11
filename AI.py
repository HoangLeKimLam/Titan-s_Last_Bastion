# AI.py — Bộ não tự hành của mọi Titan/Boss
#
# Đổi tên: file này từng là `Titan_AI.py`. Đổi tên `Titan_AI` → `AI` để
# ngắn gọn và phản ánh đúng phạm vi (AI dùng chung cho cả Titan lẫn Boss).
#
# Trách nhiệm:
#     ĐIỀU PHỐI 3 thành phần có sẵn ở mỗi frame:
#       1. Priority.py  — chọn mục tiêu
#       2. Titan.py / Boss.py — kích hoạt kỹ năng/animation/di chuyển
#       3. AttackStrategy.py — tung đòn đánh
#
#     KHÔNG bao gồm:
#       - Tham số titan (HP/speed/damage)         → Titan.py / Boss.py
#       - Animation frame loop, sprite, draw      → Titan.py / Boss.py
#       - Cơ chế thân xác (Dash/Stagger/Recoil của Armored, pause + nổ
#         của Kamikaze, summon của Founding...)   → Titan.py / Boss.py
#       - Cách đánh (damage formula, AoE radius)  → AttackStrategy.py
#
# Mỗi Titan = thân xác (Titan/Boss) + khẩu vị (Priority) +
# đòn đánh (AttackStrategy) + bộ não (file này).
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
#
# Sau refactor 2026-05-23: logic Dash/Stagger/Recoil của ArmoredAI được
# chuyển hết về `Titan.py:ArmoredTitan`. ArmoredAI giờ chỉ phát lệnh
# `trigger_dash()` và gọi `update_dash_cycle(dt, wall)` — thân xác tự lái.

from abc import ABC, abstractmethod

from Priority import (
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
        Các module hệ thống thật (WorldQuery, Tower, WallSection, HQ...)
        chưa được dựng. Nếu AI gọi thẳng chúng thì không test được.
        WorldView là "bản hợp đồng": AI chỉ cần một object cho ra
        `TargetContext` + vài truy vấn phụ.

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

    Dùng cho demo/test (CHECKAI) và mọi tình huống chưa có module hệ thống
    thật. Nhận thẳng các list entity, tự lo lọc still-alive + tính
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
        return TargetContext(
            hq=self.hq,
            walls=self.walls,
            towers=self.towers,
            soldiers=self.soldiers,
            commanders=self.commanders,
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
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _direction_to(src, dst) -> int:
    """Hướng nhìn (0=N,1=W,2=S,3=E) từ `src` tới `dst`."""
    dx = dst.x - src.x
    dy = dst.y - src.y
    if abs(dx) >= abs(dy):
        return 3 if dx > 0 else 1
    return 2 if dy > 0 else 0


def _type_of(e) -> str:
    """entity_type của entity, '' nếu không có."""
    return getattr(e, 'entity_type', '')


def _describe(e) -> str:
    """Chuỗi mô tả ngắn cho entity — ưu tiên label/name, fallback type."""
    if e is None:
        return 'None'
    return (getattr(e, '_label', None) or getattr(e, 'name', None)
            or getattr(e, 'entity_type', None) or type(e).__name__)


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

    # Tầm đánh mặc định nếu titan không tự khai báo `_attack_range`.
    _DEFAULT_ATTACK_RANGE = 60.0

    # Khoảng cách (px) tới mục tiêu mà từ đó titan chuyển sang CHẠY.
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

        # Bộ đếm hồi đòn riêng của AI — độc lập với timer nội bộ titan.
        self._attack_cd  = 0.0

        if not hasattr(titan, '_ai_attackers'):
            titan._ai_attackers = []
        titan._ai_current_target = None

    # ── API công khai ────────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Chạy 1 frame AI: sense → decide → act → đẩy animation."""
        if not getattr(self.titan, 'is_alive', False):
            self.state = STATE_DEAD
            return

        self._attack_cd = max(0.0, self._attack_cd - dt)

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
        """Pha 2 — chọn mục tiêu (ủy quyền cho Priority)."""
        target = self.priority.select_target(self.titan, context)
        self._on_decide(context, target)
        if target is None:
            self.state = STATE_IDLE
            self.last_reason = 'không có mục tiêu'
        else:
            self.state = STATE_SEEKING
            self.last_reason = f'chọn {_describe(target)}'
        return target

    def act(self, dt: float, context: TargetContext) -> None:
        """Pha 3 — hành động: tiến tới mục tiêu rồi tấn công."""
        if self.target is None:
            return
        dist = _dist(self.titan, self.target)
        if dist > self._attack_range():
            self.state = STATE_MOVING
            self._move(dt, self.target)
        else:
            self._stop_moving()
            self._act_in_range(dt, context)

    # ── Điểm mở rộng cho class con (template method) ──────────────

    def _on_decide(self, context: TargetContext, target) -> None:
        """Hook sau khi Priority chọn target, trước khi di chuyển."""
        pass

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        """Hành động khi đã ở trong tầm đánh — mặc định: đòn đánh cơ bản."""
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        self._basic_attack()

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

    def _move(self, dt: float, target) -> None:
        """Di chuyển titan tiến về `target` — tự chọn ĐI BỘ hay CHẠY."""
        titan = self.titan
        dx = target.x - titan.x
        dy = target.y - titan.y
        dist = (dx * dx + dy * dy) ** 0.5

        can_run  = hasattr(titan, '_RUN_ROWS')
        running  = can_run and dist > self._RUN_THRESHOLD
        speed    = float(getattr(titan, '_speed', 60.0))
        if running:
            speed *= self._RUN_SPEED_MULT

        if dist > 0:
            titan.x += (dx / dist) * speed * dt
            titan.y += (dy / dist) * speed * dt
        titan._direction = _direction_to(titan, target)
        if hasattr(titan, '_is_moving'):
            titan._is_moving = True
        if hasattr(titan, '_is_running'):
            titan._is_running = running

    def _stop_moving(self) -> None:
        if hasattr(self.titan, '_is_moving'):
            self.titan._is_moving = False
        if hasattr(self.titan, '_is_running'):
            self.titan._is_running = False

    def _advance_animation(self, dt: float) -> None:
        """Đẩy animation của titan tiến 1 frame.

        • Titan CÓ `update_anim()`  → gọi (giữ logic gốc).
        • Titan KHÔNG có            → AI tự đẩy theo cờ trạng thái.
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

    RegularTitan tự đổi HeavyStrikeStrategy khi HP < 40% (logic trong
    chính class) — AI không can thiệp.
    """

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        if self._attack_cd <= 0.0:
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        self._basic_attack()


# ═════════════════════════════════════════════════════════════════
#  ArmoredAI — ArmoredTitan (đã rút gọn sau refactor)
# ═════════════════════════════════════════════════════════════════

class ArmoredAI(TitanAI):
    """AI cho ArmoredTitan — "cỗ máy phá thành".

    Sau refactor 2026-05-23: logic Dash/Stagger/Recoil đã chuyển hết về
    `Titan.py:ArmoredTitan.update_dash_cycle()`. AI giờ chỉ:
        1. Phát hiện target=Wall + còn giáp + ngoài tầm → `trigger_dash()`.
        2. Mỗi frame: nếu thân xác đang dash/stagger/recoil → gọi
           `update_dash_cycle(dt, wall)` và để thân xác tự lái.
        3. Còn lại → vòng AI chung (move → attack basic).

    Hành vi:
        • Còn giáp + Wall mục tiêu: trigger Dash → recoil → Dash lại.
        • Giáp vỡ: Dash khóa → AI chuyển sang melee đứng tại chỗ
          (trigger_attack + _basic_attack).
    """

    def update(self, dt: float) -> None:
        titan = self.titan
        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            return
        self._attack_cd = max(0.0, self._attack_cd - dt)

        # Hỏi thân xác xem đang ở pha gì (Dash/Stagger/Recoil/Idle).
        wall_target = self.target if _type_of(self.target) == WALL else None
        phase = titan.update_dash_cycle(dt, wall_target=wall_target)

        if phase == 'stagger':
            self.state = STATE_SKILL
            self.last_reason = f'stagger sau húc'
            self._advance_animation(dt)
            return
        if phase == 'recoil':
            self.state = STATE_MOVING
            self.last_reason = f'walk lùi ({titan._recoil_dist_left:.0f}px còn lại)'
            self._advance_animation(dt)
            return
        if phase == 'dash':
            self.state = STATE_SKILL
            self.last_reason = f'Ram húc Wall — _ram_hits={getattr(titan,"_ram_hits",0)}'
            self._advance_animation(dt)
            return

        # phase == 'idle' → vòng AI chung
        context = self.sense()
        self.target = self.decide(context)
        titan._ai_current_target = self.target
        self.act(dt, context)
        self._advance_animation(dt)

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
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
        if dist <= self._attack_range():
            return
        trig = getattr(titan, 'trigger_dash', None)
        if callable(trig):
            dx = target.x - titan.x
            dy = target.y - titan.y
            run_speed = float(getattr(titan, '_speed', 60.0))
            if trig(dx, dy, run_speed):
                self.state = STATE_SKILL
                self.last_reason = 'Dash húc Wall'


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
    """AI cho TowerHunter — chuyên hạ tháp ("siege")."""

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
        if self._attack_cd <= 0.0:
            trig = getattr(self.titan, 'trigger_attack', None)
            if callable(trig):
                trig()
        self._basic_attack()


# ═════════════════════════════════════════════════════════════════
#  SoldierHunterAI — SoldierHunter
# ═════════════════════════════════════════════════════════════════

class SoldierHunterAI(TitanAI):
    """AI cho SoldierHunter — Titan to xác săn lính, đòn cleave AoE."""

    def _act_in_range(self, dt: float, context: TargetContext) -> None:
        self.state = STATE_ATTACKING
        self.titan._direction = _direction_to(self.titan, self.target)
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

        context = self.sense()

        detect_r = float(getattr(titan, '_DETECT_RADIUS', 300.0))
        prey = self._nearest_prey(context, detect_r)

        if prey is not None:
            self.target = prey
            titan._ai_current_target = prey
            dist = _dist(titan, prey)
            explode_r = float(getattr(titan, '_EXPLODE_RADIUS', 80.0))
            if dist <= explode_r:
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
            target = self.priority.select_target(titan, context)
            self.target = target
            titan._ai_current_target = target
            if target is None:
                self.state = STATE_IDLE
                self._stop_moving()
            else:
                self.state = STATE_MOVING
                self.last_reason = f'tiến về {_describe(target)}'
                self._move(dt, target)

        self._advance_animation(dt)

    def _nearest_prey(self, context: TargetContext, radius: float):
        """Soldier/Commander còn sống gần nhất trong bán kính phát hiện."""
        titan = self.titan
        best, best_d = None, radius
        for e in list(context.soldiers) + list(context.commanders):
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
            speed = float(getattr(titan, '_speed', 80.0)) * mult
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

    Cooldown do ColossalTitan tự quản — AI chỉ đọc cờ và gọi skill.
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

        # Tick particle hơi nóng (ColossalTitan.update bị override).
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
        • Trong `_THROW_RANGE` + hồi → `trigger_attack(target)`.
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

    Hành vi theo phase (FoundingTitan tự quản phase qua `_check_phase`):
        • P1 (HP>60%) / P3 (HP≤20%): áp sát đánh HeavyStrike.
        • P2 (20–60%): tự summon mỗi `_SUMMON_WAVE_COOLDOWN` giây.
        • Đang summon/attacking → đứng yên chờ animation.

    AI cũng tick AI cho mỗi minion summon — minion vì thế tự đi đánh
    Tower/Soldier/Commander/Wall/HQ như entity độc lập.
    """

    def update(self, dt: float) -> None:
        titan = self.titan
        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            self._tick_minions(dt)
            return

        if hasattr(titan, '_summon_cd_timer'):
            titan._summon_cd_timer = max(0.0, titan._summon_cd_timer - dt)
        if hasattr(titan, '_attack_cd_timer'):
            titan._attack_cd_timer = max(0.0, titan._attack_cd_timer - dt)
        self._attack_cd = max(0.0, self._attack_cd - dt)

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

        if self.target is not None:
            dist = _dist(titan, self.target)
            if dist > self._attack_range():
                self.state = STATE_MOVING
                self._move(dt, self.target)
            else:
                self.state = STATE_ATTACKING
                titan._direction = _direction_to(titan, self.target)
                self._founding_attack()
        else:
            self.state = STATE_IDLE

        self._advance_animation(dt)
        self._tick_minions(dt)

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

    def _founding_attack(self) -> None:
        """Tung đòn HeavyStrike — gọi trigger_attack(target) của Founding."""
        if self._attack_cd > 0.0:
            return
        trig = getattr(self.titan, 'trigger_attack', None)
        if callable(trig):
            trig(self.target)
            self._attack_cd  = float(getattr(self.titan,
                                             '_ATTACK_COOLDOWN', 3.0))
            self.last_reason = f'HeavyStrike {_describe(self.target)}'


class WitchAI(TitanAI):
    """AI cho Witch — caster đứng xa, summon Cursed toàn map.

    Khi còn soldier/commander/tower, Witch đứng yên và cast theo cooldown.
    Khi hết lực lượng phòng thủ, Witch dùng fallback như Titan thường:
    đi tới Wall/HQ và cast 1 tia ở cận chiến.
    """

    _DEFENDER_TYPES = (SOLDIER, COMMANDER, TOWER)

    def update(self, dt: float) -> None:
        titan = self.titan
        if not getattr(titan, 'is_alive', False):
            self.state = STATE_DEAD
            self._advance_animation(dt)
            return

        if getattr(titan, '_is_casting', False):
            self.state = STATE_SKILL
            self.last_reason = 'đang giữ frame summon trước khi gọi sét'
            self._stop_moving()
            self._advance_animation(dt)
            return

        context = self.sense()
        self.target = self.decide(context)
        titan._ai_current_target = self.target

        if self._has_defenders(context):
            self._stop_moving()
            if getattr(titan, '_cast_cd_timer', 0.0) <= 0.0:
                trig = getattr(titan, 'trigger_attack', None)
                if callable(trig) and trig(None):
                    self.state = STATE_SKILL
                    self.last_reason = 'Cursed x10 toàn map'
            else:
                self.state = STATE_SEEKING
                cd = getattr(titan, '_cast_cd_timer', 0.0)
                self.last_reason = f'chờ Cursed hồi {cd:.1f}s'
            self._advance_animation(dt)
            return

        if self.target is None:
            self.state = STATE_IDLE
            self._stop_moving()
            self._advance_animation(dt)
            return

        dist = _dist(titan, self.target)
        if dist > self._attack_range():
            self.state = STATE_MOVING
            self._move(dt, self.target)
        else:
            self.state = STATE_ATTACKING
            self._stop_moving()
            titan._direction = _direction_to(titan, self.target)
            if getattr(titan, '_cast_cd_timer', 0.0) <= 0.0:
                trig = getattr(titan, 'trigger_attack', None)
                if callable(trig) and trig(self.target):
                    self.last_reason = f'Cursed fallback {_describe(self.target)}'
            else:
                cd = getattr(titan, '_cast_cd_timer', 0.0)
                self.last_reason = f'chờ Cursed fallback {cd:.1f}s'

        self._advance_animation(dt)

    def _has_defenders(self, context: TargetContext) -> bool:
        for entity in (
                list(context.soldiers)
                + list(context.commanders)
                + list(context.towers)):
            if _alive(entity) and _type_of(entity) in self._DEFENDER_TYPES:
                return True
        return False


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
    'Witch':         WitchAI,
    'ColossalTitan': ColossalAI,
    'BeastTitan':    BeastAI,
    'FoundingTitan': FoundingAI,
}


def make_ai_for(titan, world: WorldView,
                priority: TargetPriorityStrategy = None) -> TitanAI:
    """Tạo bộ AI phù hợp cho `titan` dựa theo tên class.

    Loại không có AI riêng → DefaultAI. Priority None → tự suy ra
    theo loại titan (qua Priority.make_priority_for).

    Ví dụ:
        ai = make_ai_for(titan, SimpleWorldView(hq=hq, towers=towers))
        while running:
            ai.update(dt)
    """
    cls = AI_BY_TITAN.get(type(titan).__name__, DefaultAI)
    return cls(titan, world, priority)
