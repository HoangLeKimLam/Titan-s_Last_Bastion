# structures/hq.py — Headquarters (HQ) — mục tiêu cuối cùng của Titan
"""Headquarters — trụ sở trung tâm, mục tiêu cuối cùng của mọi Titan.

Vị trí: trùng tâm castle sprite trên map (tile 85, 69).
Titan AI dùng WorldQuery.get_headquarters() để lấy object này làm target.

Đồ họa: castle_surf đã được render bởi Pass 2 của tile loop.
draw() ở đây chỉ vẽ thanh HP + label nổi lên trên castle.
"""
import pygame
from core.entity import Entity
from core.interfaces import IAttackable
from core.event_bus import GameEventBus
from config import balance


class Headquarters(Entity, IAttackable):
    """Trụ sở trung tâm — entity HQ với ENTITY_TYPE='hq'.

    Thuộc tính:
        ENTITY_TYPE = 'hq'          — nhận dạng bởi Priority + WorldQuery
        _hp / _max_hp               — thanh máu HQ
        is_alive                    — False khi HP ≤ 0 → game over

    draw() vẽ HP bar nổi phía trên vị trí castle; castle sprite
    được render bởi tile loop bên ngoài (không cần draw lại ở đây).
    """

    ENTITY_TYPE = 'hq'

    _DEFAULT_HP   = balance.HQ_HP
    _HP_BAR_W     = 200          # px — chiều rộng thanh HP
    _HP_BAR_H     = 12           # px
    _HP_BAR_Y_OFF = 210          # px phía trên anchor (self.y sau khi cam offset)

    _COL_BG       = (60,  20,  20)
    _COL_HP       = (220, 60,  60)
    _COL_BORDER   = (200, 200, 200)
    _COL_LABEL    = (255, 230, 100)

    _font = None

    def __init__(self, x: float, y: float,
                 max_hp: int = _DEFAULT_HP) -> None:
        """Khởi tạo HQ tại vị trí trùng tâm castle sprite (tile 85, 69), đầy máu.

        Tham số: max_hp — mặc định `balance.HQ_HP`; caller có thể override (vd
            load save game với HP HQ đã bị đánh trước đó).
        """
        super().__init__(x, y)
        self._max_hp = max_hp
        self._hp     = max_hp

    # ── IAttackable ──────────────────────────────────────────────

    def take_damage(self, amount: int, dtype: str = 'normal') -> None:
        """Titan (hoặc kỹ năng) gọi khi tấn công HQ."""
        if not self.is_alive:
            return
        self._hp = max(0, self._hp - amount)
        if self._hp <= 0:
            self.on_death()

    def on_death(self) -> None:
        """HQ bị phá HOÀN TOÀN → GAME OVER. Publish `'game_over'` (reason='hq_destroyed')
        cho UI/hệ thống subscribe hiển thị màn hình thua. Bọc try/except NGẦM —
        publish lỗi (event bus chưa sẵn sàng) không được chặn việc đánh dấu chết."""
        self.is_alive = False
        try:
            GameEventBus.get_instance().publish('game_over', {'reason': 'hq_destroyed'})
        except Exception:
            pass

    # ── Helpers ──────────────────────────────────────────────────

    @property
    def hp_ratio(self) -> float:
        """Tỉ lệ HP còn lại (0.0-1.0) — HUD dùng vẽ thanh máu HQ. max_hp=0 → 0.0 (an toàn)."""
        return self._hp / self._max_hp if self._max_hp > 0 else 0.0

    # ── Entity interface ─────────────────────────────────────────

    def update(self, dt: float) -> None:
        """No-op — HQ là mục tiêu TĨNH, không di chuyển, không có AI, không tự
        làm gì mỗi frame. Chỉ phản ứng thụ động qua `take_damage()`."""
        pass  # HQ không di chuyển, không có AI — chỉ nhận damage

    def draw(self, screen: pygame.Surface) -> None:
        """No-op (THÊM MỚI — chỉ đồ họa): thanh HP HQ không còn nổi trên map
        nữa, đã chuyển thành panel cố định (avatar + bar chuyên nghiệp) ở
        HUD — xem `ui/hud_panels.py:draw_hq_status()`, gọi 1 lần/frame trong
        game.py, đọc trực tiếp self._hp/_max_hp. castle sprite vẫn do tile
        loop vẽ như cũ, không đổi.
        """
        pass
