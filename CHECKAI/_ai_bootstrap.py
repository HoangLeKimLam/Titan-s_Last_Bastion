"""_ai_bootstrap.py — Dựng môi trường import cho các demo AI (CHECKAI/).

Vì sao cần file này?
    Titan.py / Boss.py import từ các package GIẢ ĐỊNH chưa được dựng:
        core.entity, core.interfaces, core.event_bus,
        characters.titans.titan, characters.titans.attackstrategy,
        systems.world_query, patterns.decorator ...
    Mỗi demo muốn `import Titan` đều phải mock đống module đó trước.
    Thay vì chép khối mock dài vào 10 file check_AI, ta gom 1 lần ở
    đây. File check_AI chỉ cần `import _ai_bootstrap` là xong.

Cách dùng:
    import _ai_bootstrap            # PHẢI import TRƯỚC mọi import khác
    from Titan import RegularTitan  # giờ import được
    from AI import make_ai_for, SimpleWorldView

Triết lý OOP:
    File này đóng vai "Composition Root" — nơi lắp ráp phụ thuộc. Nó
    không chứa logic game, chỉ dựng môi trường. Tách riêng giúp 10
    demo gọn và nhất quán.
"""
import os
import sys
import types


# ── Đăng ký module giả ───────────────────────────────────────────

def _new_module(name: str) -> types.ModuleType:
    """Tạo & đăng ký một module rỗng vào sys.modules (idempotent)."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ── core.entity — lớp Entity gốc ─────────────────────────────────

class _MockEntity:
    """Bản Entity tối giản: id, x, y, is_alive + update/draw rỗng.

    Đủ cho Titan/Boss kế thừa trong môi trường demo.
    """

    _next_id = 1

    def __init__(self, x: float, y: float) -> None:
        self.id = _MockEntity._next_id
        _MockEntity._next_id += 1
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen) -> None:
        pass


# ── core.event_bus — GameEventBus Singleton giả ──────────────────

class _MockEventBus:
    """EventBus giả: publish chỉ in log gọn, đủ để Titan.on_death chạy."""

    _instance = None

    @classmethod
    def get_instance(cls) -> '_MockEventBus':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def publish(self, event: str, data: dict) -> None:
        print(f"  [EventBus] {event}")

    def subscribe(self, *args, **kwargs) -> None:
        pass


# ── systems.world_query — WorldQuery giả ─────────────────────────

class _MockWorldQuery:
    """WorldQuery giả — chỉ trả rỗng.

    AI trong CHECKAI KHÔNG dùng WorldQuery (nó dùng WorldView). Mock
    này chỉ để các strategy/skill có lazy-import WorldQuery không vỡ
    khi chưa kịp gán dữ liệu thật. Demo có thể gán đè 3 list này.
    """

    soldiers:   list = []
    towers:     list = []
    commanders: list = []
    walls:      list = []
    hq:         object = None

    @classmethod
    def _pool_for(cls, entity_type: str) -> list:
        """Trả về pool entity tương ứng với entity_type. HQ trả [hq] hoặc []."""
        if entity_type == 'hq':
            return [cls.hq] if cls.hq is not None else []
        return {
            'soldier':   cls.soldiers,
            'tower':     cls.towers,
            'commander': cls.commanders,
            'wall':      cls.walls,
        }.get(entity_type, [])

    @classmethod
    def find_in_radius(cls, cx: float, cy: float,
                       radius: float, entity_type: str) -> list:
        pool = cls._pool_for(entity_type)
        r2 = radius * radius
        out = []
        for e in pool:
            if not getattr(e, 'is_alive', False):
                continue
            dx = e.x - cx
            dy = e.y - cy
            if dx * dx + dy * dy <= r2:
                out.append(e)
        return out

    @classmethod
    def find_nearest(cls, cx: float, cy: float,
                     entity_type: str):
        pool = cls._pool_for(entity_type)
        best, best_d = None, float('inf')
        for e in pool:
            if not getattr(e, 'is_alive', False):
                continue
            d = ((e.x - cx) ** 2 + (e.y - cy) ** 2) ** 0.5
            if d < best_d:
                best_d, best = d, e
        return best

    @classmethod
    def get_headquarters(cls):
        return None

    @classmethod
    def can_reach_direct(cls, *args, **kwargs) -> bool:
        return True

    @classmethod
    def find_blocking_wall(cls, *args, **kwargs):
        return None

    @classmethod
    def find_nearest_attacker(cls, *args, **kwargs):
        return None


# ── patterns.decorator — BurnDecorator giả ───────────────────────

class _MockBurnDecorator:
    """BurnDecorator giả — nuốt mọi tham số, không làm gì.

    Một số skill (Steam Burst của Colossal) tạo BurnDecorator. Bản
    giả này đủ để skill chạy không lỗi trong demo.
    """

    def __init__(self, *args, **kwargs) -> None:
        pass

    def update(self, *args, **kwargs) -> None:
        pass


def install() -> None:
    """Lắp toàn bộ module giả vào sys.modules.

    Gọi MỘT LẦN, TRƯỚC khi import Titan/Boss. An toàn khi gọi lại
    (idempotent) nhờ _new_module kiểm tra sẵn.
    """
    # Đưa thư mục gốc dự án (chứa Titan.py, Boss.py, AttackStrategy.py,
    # Priority.py, AI.py) vào sys.path. File này ở CHECKAI/ nên
    # lùi 1 cấp.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    # core.*
    _new_module('core')
    _new_module('core.entity').Entity = _MockEntity
    iface = _new_module('core.interfaces')
    iface.IAttackable = type('IAttackable', (), {})
    iface.IMovable    = type('IMovable', (), {})
    iface.ISkillUser  = type('ISkillUser', (), {})
    _new_module('core.event_bus').GameEventBus = _MockEventBus
    exc = _new_module('core.exceptions')
    exc.InsufficientResourceError = type(
        'InsufficientResourceError', (Exception,), {})
    exc.WallBreachError = type('WallBreachError', (Exception,), {})

    # systems.*
    _new_module('systems')
    _new_module('systems.world_query').WorldQuery = _MockWorldQuery

    # patterns.*
    _new_module('patterns')
    _new_module('patterns.decorator').BurnDecorator = _MockBurnDecorator

    # structures.towers.tower — TowerHunterStrategy lazy-import `Tower`
    # rồi dùng isinstance(target, Tower) để áp bonus ×1.5. Ta trỏ tên
    # `Tower` về chính TowerDummy của CHECKAI, nhờ vậy isinstance đúng
    # và bonus siege hoạt động trong demo.
    _new_module('structures')
    _new_module('structures.towers')
    from _ai_dummies import TowerDummy as _TowerDummy
    _new_module('structures.towers.tower').Tower = _TowerDummy

    # characters.* — strategy module phản chiếu AttackStrategy.py thật.
    _new_module('characters')
    _new_module('characters.titans')
    import AttackStrategy as _atk  # noqa: E402  (sau khi sys.path đã có root)
    strat = _new_module('characters.titans.attackstrategy')
    for _name in dir(_atk):
        if not _name.startswith('_'):
            setattr(strat, _name, getattr(_atk, _name))
    # characters.titans.titan — phản chiếu Titan.py thật. Phải import
    # SAU khi strategy module + core đã sẵn sàng.
    import Titan as _titan  # noqa: E402
    tmod = _new_module('characters.titans.titan')
    for _name in dir(_titan):
        if not _name.startswith('_'):
            setattr(tmod, _name, getattr(_titan, _name))


# Tự động lắp khi file được import — demo chỉ cần `import _ai_bootstrap`.
install()
