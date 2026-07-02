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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Import lazy để tránh circular (systems → characters).
# Dùng _same_zone() helper bên dưới — gọi WorldQuery khi cần.
def _same_zone(ax, ay, bx, by) -> bool:
    try:
        from systems.world_query import WorldQuery
        # Buộc Titan tuân thủ nghiêm ngặt vùng (strict=True)
        # để không tự ý khóa mục tiêu ngoài vùng dù đứng sát biên.
        return WorldQuery.same_zone(ax, ay, bx, by, strict=True)
    except Exception:
        return True   # fallback: coi như cùng zone (an toàn hơn là block)


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
AGGRO_RANGE = 360.0


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
    return entity is not None and getattr(entity, 'is_alive', False)


def _type_of(entity) -> str:
    """Đọc ENTITY_TYPE của entity; trả '' nếu không có."""
    return getattr(entity, 'ENTITY_TYPE', '')


def _distance(a, b) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _nearest(origin, candidates: list):
    alive = [e for e in candidates if _is_alive(e)]
    if not alive:
        return None
    return min(alive, key=lambda e: _distance(origin, e))


def _attackers_of_types(titan, context: TargetContext, types: tuple):
    from systems.world_query import WorldQuery
    hits = []
    for a in context.attackers:
        if not (_is_alive(a) and _type_of(a) in types and _distance(titan, a) <= AGGRO_RANGE):
            continue
        # Chỉ đánh trả nếu mục tiêu ở cùng vùng (hoặc là tháp trên tường).
        # Nếu khác vùng (sau bức tường), bỏ qua để titan tập trung phá tường.
        if getattr(a, '_wall_name', None) or WorldQuery.same_zone(titan.x, titan.y, a.x, a.y):
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
            from systems.world_query import WorldQuery
            if getattr(ct, '_wall_name', None) or WorldQuery.same_zone(titan.x, titan.y, ct.x, ct.y):
                if _type_of(ct) == COMMANDER:
                    # visible_towers không liên quan đến commander — chỉ check soldier/commander
                    in_vis = ct in (context.visible_soldiers + context.visible_commanders)
                    return ct if in_vis else None
                return ct
            return None

        # Rule 2: Nếu KHÔNG attack → chỉ lock nếu còn trong visual range
        # visible_towers không liên quan đến soldier/commander
        in_visible = ct in (context.visible_soldiers + context.visible_commanders)
        return ct if in_visible else None

    def _path_target(self, context: TargetContext):
        if context.can_reach_hq and _is_alive(context.hq):
            return context.hq
        if _is_alive(context.blocking_wall):
            return context.blocking_wall
        return None

    # Giây chờ giữa 2 lần roll 50% khi titan bỏ qua visible target
    _VIS_ROLL_COOLDOWN = 2.0

    def _maybe_visible_target(self, titan, context: TargetContext):
        """50% chance rẽ sang visible soldier/commander khi không có target khác.

        Cooldown 2s giữa các lần roll — titan không flip-flop mỗi frame.
        Roll True → nhắm nearest visible + đặt cooldown (tránh rẽ lại ngay khi lính chết).
        Roll False → đặt cooldown, titan tiếp tục đường cũ.
        """
        candidates = [u for u in (context.visible_soldiers + context.visible_commanders)
                      if _is_alive(u)]
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
    """Bộ ưu tiên BeastTitan — "thợ săn tháp tầm xa".

    Thứ tự chủ động: Tower → Soldier → Commander → Wall → HQ.
    """

    def select_target(self, titan, context: TargetContext):
        ct = context.current_target
        # Lock tower hiện tại chỉ khi cùng zone HOẶC là wall-tower (2 phía)
        if (_is_alive(ct) and _type_of(ct) == TOWER
                and (_distance(titan, ct) <= AGGRO_RANGE
                     or getattr(ct, '_wall_name', None))
                and (getattr(ct, '_wall_name', None)
                     or _same_zone(titan.x, titan.y, ct.x, ct.y))):
            return ct

        # Nearest tower trong cùng zone (hoặc wall-tower exempt zone filter)
        tower = _nearest(titan, [
            t for t in context.towers
            if _is_alive(t) and (getattr(t, '_wall_name', None)
                                 or _same_zone(titan.x, titan.y, t.x, t.y))
        ])
        if tower is not None:
            return tower

        soldier = _nearest(titan, context.visible_soldiers)
        if soldier is not None:
            return soldier

        commander = _nearest(titan, context.visible_commanders)
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
        prey = _nearest(titan, context.visible_soldiers + context.visible_commanders)
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
        prey = _nearest(titan, context.visible_soldiers)
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
        ct = context.current_target
        # Lock tower hiện tại chỉ khi cùng zone HOẶC là wall-tower (2 phía)
        if (_is_alive(ct) and _type_of(ct) == TOWER
                and (_distance(titan, ct) <= AGGRO_RANGE
                     or getattr(ct, '_wall_name', None))
                and (getattr(ct, '_wall_name', None)
                     or _same_zone(titan.x, titan.y, ct.x, ct.y))):
            return ct

        # Nearest tower trong cùng zone (hoặc wall-tower exempt zone filter)
        tower = _nearest(titan, [
            t for t in context.towers
            if _is_alive(t) and (getattr(t, '_wall_name', None)
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
    """Tạo bộ ưu tiên phù hợp cho `titan` dựa theo tên class."""
    cls = PRIORITY_BY_TITAN.get(type(titan).__name__, DefaultPriority)
    return cls()
