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

    _DEFAULT_HP   = 5000
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
        self.is_alive = False
        try:
            GameEventBus.get_instance().publish('game_over', {'reason': 'hq_destroyed'})
        except Exception:
            pass

    # ── Helpers ──────────────────────────────────────────────────

    @property
    def hp_ratio(self) -> float:
        return self._hp / self._max_hp if self._max_hp > 0 else 0.0

    # ── Entity interface ─────────────────────────────────────────

    def update(self, dt: float) -> None:
        pass  # HQ không di chuyển, không có AI — chỉ nhận damage

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ HP bar + label "HQ" phía trên castle sprite.

        Khi được gọi từ Pass 2.6, self.x/self.y đã là toạ độ màn hình
        (world coords đã trừ cam_x/cam_y bởi render loop).
        """
        sx = int(self.x)
        sy = int(self.y)

        bar_x = sx - self._HP_BAR_W // 2
        bar_y = sy - self._HP_BAR_Y_OFF

        # Background
        pygame.draw.rect(screen, self._COL_BG,
                         (bar_x, bar_y, self._HP_BAR_W, self._HP_BAR_H))
        # HP fill
        fill_w = int(self._HP_BAR_W * self.hp_ratio)
        if fill_w > 0:
            pygame.draw.rect(screen, self._COL_HP,
                             (bar_x, bar_y, fill_w, self._HP_BAR_H))
        # Border
        pygame.draw.rect(screen, self._COL_BORDER,
                         (bar_x, bar_y, self._HP_BAR_W, self._HP_BAR_H), 1)

        # Label "HQ  HP/MAX"
        if Headquarters._font is None:
            try:
                Headquarters._font = pygame.font.SysFont('consolas', 11)
            except Exception:
                return
        txt = Headquarters._font.render(
            f'HQ  {self._hp}/{self._max_hp}', True, self._COL_LABEL)
        screen.blit(txt, (bar_x, bar_y - txt.get_height() - 2))
