# characters/soldiers/projectile.py
from __future__ import annotations

import math
import os

import pygame

from core.entity import Entity
from config import balance

_ARROW_PATH = os.path.join(os.path.dirname(__file__), "sprites", "Archer", "Arrow.png")


class Arrow(Entity):
    """Mũi tên bay THẲNG (không đạn đạo cong) — do ArcherSoldier bắn ra.

    Đặc điểm quan trọng: nhắm vị trí target LÚC BẮN (không dẫn trước như đá
    Beast), bay tới ĐÚNG điểm đó (`_impact`) rồi nổ, KHÔNG đuổi theo target di
    chuyển — nếu target chạy khỏi điểm bắn, mũi tên có thể trượt (chỉ trúng nếu
    lúc chạm điểm đó target vẫn còn ở gần trong `HIT_RADIUS*2`).
    """

    ENTITY_TYPE = "projectile"

    SPEED = balance.ARROW_SPEED
    HIT_RADIUS = balance.ARROW_HIT_RADIUS
    MAX_LIFETIME = balance.ARROW_MAX_LIFETIME

    _sprite_cache = None

    def __init__(self, x: float, y: float, target, damage: int,
                 *, shooter=None, headless: bool = False) -> None:
        """Tạo mũi tên bay từ (x,y) tới VỊ TRÍ HIỆN TẠI của `target`.

        Thuật toán: tính vector đơn vị hướng tới target LÚC TẠO, nhân `SPEED` →
        `_vx/_vy` CỐ ĐỊNH suốt đời mũi tên (không chỉnh hướng giữa chừng dù
        target di chuyển). Lưu điểm đích `_impact = (tx, ty)` — điểm CỐ ĐỊNH
        trong không gian, không phải "vị trí target". `_life = MAX_LIFETIME` (2s)
        — tự huỷ nếu bay quá lâu mà chưa tới (tránh mũi tên bay vô tận ra khỏi bản đồ).

        Tham số: target — entity nhắm (chỉ dùng lúc này để tính hướng + check
            trúng cuối); damage; shooter — ai bắn (để AI titan biết ai đánh mình);
            headless — bỏ qua nạp sprite khi test.
        Chỉ số: balance.ARROW_SPEED / _HIT_RADIUS / _MAX_LIFETIME.
        """
        super().__init__(x, y)
        self._target = target
        self._damage = int(damage)
        self._shooter = shooter
        self._headless = headless
        self._life = self.MAX_LIFETIME
        tx, ty = target.x, target.y
        dx, dy = tx - x, ty - y
        dist = math.hypot(dx, dy) or 1.0
        self._vx = dx / dist * self.SPEED
        self._vy = dy / dist * self.SPEED
        self._impact = (tx, ty)
        self._sprite = self._load_sprite() if not headless else None

    @classmethod
    def _load_sprite(cls):
        """Nạp sprite mũi tên 1 LẦN DUY NHẤT cho MỌI Arrow (class-level cache).

        `classmethod` + `_sprite_cache` là ATTRIBUTE CỦA CLASS: mọi mũi tên dùng
        chung 1 Surface đã scale 18×18, không nạp lại mỗi lần bắn (hàng trăm mũi
        tên mỗi trận). Lỗi/thiếu file → cache None (fallback vẽ chấm tròn ở `draw()`).
        """
        if cls._sprite_cache is not None:
            return cls._sprite_cache
        try:
            img = pygame.image.load(_ARROW_PATH)
            img = pygame.transform.scale(img, (18, 18))
            cls._sprite_cache = img
        except (pygame.error, FileNotFoundError):
            cls._sprite_cache = None
        return cls._sprite_cache

    def update(self, dt: float) -> None:
        """Bay 1 bước; TỚI ĐÍCH hoặc HẾT GIỜ thì kiểm tra trúng rồi tự huỷ.

        Thuật toán:
          1. Di chuyển theo `_vx/_vy` cố định (đường thẳng).
          2. Trừ `_life`.
          3. `reached` = đã tới trong `HIT_RADIUS` của điểm đích CỐ ĐỊNH `_impact`.
          4. `reached` HOẶC hết `_life` → KIỂM TRA TRÚNG: target còn sống VÀ hiện
             đang đứng trong `HIT_RADIUS × 2` của VỊ TRÍ HIỆN TẠI của mũi tên (không
             phải điểm impact gốc — cho phép sai số nhỏ nếu target xê dịch chút ít)
             → áp damage dtype='ranged', kèm `attacker=_shooter`. Rồi `is_alive=False`
             dù trúng hay trượt.

        Chỉ số: balance.ARROW_HIT_RADIUS.
        """
        if not self.is_alive:
            return
        self._life -= dt
        self.x += self._vx * dt
        self.y += self._vy * dt

        reached = math.hypot(self._impact[0] - self.x,
                             self._impact[1] - self.y) <= self.HIT_RADIUS
        if reached or self._life <= 0:
            tgt = self._target
            if (tgt is not None and getattr(tgt, "is_alive", False)
                    and math.hypot(tgt.x - self.x, tgt.y - self.y)
                    <= self.HIT_RADIUS * 2):
                tgt.take_damage(self._damage, "ranged", attacker=self._shooter)
            self.is_alive = False

    def draw(self, screen) -> None:
        """Vẽ mũi tên XOAY THEO HƯỚNG BAY (dùng `atan2(-vy, vx)` — trục Y đảo vì
        pygame Y hướng xuống). Không có sprite → chấm tròn vàng nhạt thay thế."""
        try:
            if self._sprite is not None:
                ang = math.degrees(math.atan2(-self._vy, self._vx))
                rot = pygame.transform.rotate(self._sprite, ang)
                screen.blit(rot, rot.get_rect(center=(int(self.x), int(self.y))))
            else:
                pygame.draw.circle(screen, (240, 230, 160),
                                   (int(self.x), int(self.y)), 3)
        except (AttributeError, pygame.error):
            pass
