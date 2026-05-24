"""_ai_dummies.py — Entity giả cho các demo kiểm thử AI (CHECKAI/).

Vì sao có file này?
    AI cần "nhìn thấy" thế giới: HQ, tường, tháp, lính, tướng.
    Các class thật (HQ, WallSection, Tower, Soldier, Commander) chưa
    được dựng trong dự án. File này cung cấp bản GIẢ tối giản — đủ
    thuộc tính để AI + Priority + WorldView hoạt động và để vẽ lên
    màn hình demo.

Thiết kế OOP:
    TargetEntity (ABC)        — lớp cha mọi mục tiêu: x, y, hp, is_alive,
                                entity_type, take_damage(), draw().
      ├─ Headquarters         — đại bản doanh (entity_type='hq').
      ├─ WallDummy            — đoạn tường (entity_type='wall').
      ├─ TowerDummy           — tháp phòng thủ (entity_type='tower'),
                                có thể bắn titan + bị stun.
      ├─ SoldierDummy         — lính (entity_type='soldier'), bắn titan.
      └─ CommanderDummy       — tướng (entity_type='commander'), bắn titan.

Quy ước bắt buộc cho Priority/WorldView:
    Mọi entity có `entity_type` ∈ {'hq','wall','tower','soldier',
    'commander'} và `is_alive`. Đây là hợp đồng dữ liệu — Priority chỉ
    đọc `entity_type`, không phụ thuộc class cụ thể.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pygame


# ═════════════════════════════════════════════════════════════════
#  TargetEntity — lớp cha trừu tượng của mọi mục tiêu
# ═════════════════════════════════════════════════════════════════

class TargetEntity(ABC):
    """Lớp cha cho mọi entity mà Titan có thể nhắm/đánh.

    Gom các thuộc tính + hành vi chung một chỗ (DRY): vị trí, máu,
    cờ sống/chết, hiệu ứng nháy khi trúng đòn. Class con chỉ cần khai
    `entity_type`, màu sắc và cách vẽ.
    """

    #: Loại entity — class con BẮT BUỘC ghi đè bằng 1 trong các hằng
    #: số {'hq','wall','tower','soldier','commander'}.
    entity_type: str = ''

    def __init__(self, x: float, y: float, hp: int,
                 label: str = '') -> None:
        self.x          = float(x)
        self.y          = float(y)
        self._hp        = int(hp)
        self._max_hp    = int(hp)
        self.is_alive   = True
        self._label     = label or type(self).__name__
        self._hit_flash = 0.0     # giây nháy đỏ còn lại khi trúng đòn
        # Vector pushback (NHÓM 6 — Beast rock land). Khởi tạo 0 cho mọi
        # entity (kể cả HQ/Wall/Tower) để `apply_pushback_tween` integrate
        # an toàn — riêng những entity Beast KHÔNG đẩy (tower/wall/hq)
        # thì vector này không bao giờ được set khác 0.
        self.pushback_vx = 0.0
        self.pushback_vy = 0.0

    # ── Nhận damage ──────────────────────────────────────────────

    def take_damage(self, amount: int, dtype: str = 'normal') -> None:
        """Nhận sát thương từ Titan.

        `amount == 0` (vd dtype='pushback') chỉ là tín hiệu phụ —
        không trừ máu. `amount > 0` trừ máu, có thể giết entity.
        """
        if amount > 0:
            self._hp = max(0, self._hp - amount)
            self._hit_flash = 0.35
            if self._hp <= 0:
                self.is_alive = False

    # ── Cập nhật mỗi frame ───────────────────────────────────────

    def update(self, dt: float) -> None:
        """Giảm timer nháy đỏ + integrate vector pushback (nếu có).

        Class con override để thêm hành vi (vd Tower bắn titan) nhưng
        BẮT BUỘC gọi `super().update(dt)` để pushback tween chạy.
        """
        # Tween pushback — gọi đầu update để vị trí cập nhật trước khi
        # vẽ frame này. Lazy import tránh vòng tròn import giữa
        # _ai_dummies và AttackStrategy.
        from AttackStrategy import RockProjectile
        RockProjectile.apply_pushback_tween(self, dt)
        if self._hit_flash > 0.0:
            self._hit_flash = max(0.0, self._hit_flash - dt)

    # ── Vẽ ───────────────────────────────────────────────────────

    @abstractmethod
    def draw(self, screen: pygame.Surface, font) -> None:
        """Vẽ entity lên màn hình. Class con tự quyết hình dạng."""
        ...

    # ── Helper chung cho class con ───────────────────────────────

    def _hp_ratio(self) -> float:
        """Tỉ lệ máu 0..1 — dùng vẽ thanh HP."""
        return self._hp / self._max_hp if self._max_hp > 0 else 0.0

    def _draw_hp_bar(self, screen: pygame.Surface,
                     width: int, y_offset: int,
                     color: tuple) -> None:
        """Vẽ thanh HP phía trên entity."""
        bx = int(self.x - width / 2)
        by = int(self.y - y_offset)
        pygame.draw.rect(screen, (60, 0, 0), (bx, by, width, 5))
        pygame.draw.rect(screen, color,
                         (bx, by, int(width * self._hp_ratio()), 5))

    def _draw_label(self, screen: pygame.Surface, font,
                    y_offset: int) -> None:
        """Vẽ nhãn tên dưới entity."""
        lbl = font.render(self._label, True, (220, 220, 220))
        screen.blit(lbl, (int(self.x - lbl.get_width() / 2),
                          int(self.y + y_offset)))

    def _body_color(self, base: tuple,
                    flash: tuple = (250, 220, 90)) -> tuple:
        """Màu thân — nháy `flash` khi vừa trúng đòn, còn lại `base`."""
        return flash if self._hit_flash > 0.0 else base


# ═════════════════════════════════════════════════════════════════
#  AttackerEntity — entity biết bắn trả Titan
# ═════════════════════════════════════════════════════════════════

class AttackerEntity(TargetEntity):
    """Lớp con trung gian: entity vừa là mục tiêu, vừa BIẾT BẮN titan.

    Tower / Soldier / Commander đều bắn Titan từ xa. Logic "bắn theo
    nhịp cooldown, báo cho AI của titan biết mình đang tấn công" giống
    nhau → gom vào đây để 3 class con khỏi lặp.

    Vì sao báo cho AI?
        Luật Priority "chỉ đánh Tower/Soldier khi bị chúng tấn công"
        cần biết AI titan đang bị ai bắn. Khi bắn, ta gọi
        `titan_ai.notify_attacked(self)` để AI ghi nhận.
    """

    def __init__(self, x: float, y: float, hp: int,
                 attack_range: float, attack_damage: int,
                 attack_cooldown: float, label: str = '') -> None:
        super().__init__(x, y, hp, label)
        self._atk_range    = attack_range
        self._atk_damage   = attack_damage
        self._atk_cooldown = attack_cooldown
        self._atk_timer    = 0.0

    def try_shoot(self, titan, titan_ai, dt: float) -> bool:
        """Bắn `titan` nếu nó trong tầm và đã hồi đòn.

        Tham số:
            titan: con Titan mục tiêu.
            titan_ai: TitanAI điều khiển titan — để báo notify_attacked.
            dt: delta time.

        Trả về True nếu vừa bắn ở frame này.
        """
        self._atk_timer = max(0.0, self._atk_timer - dt)
        if not self.is_alive or titan is None \
                or not getattr(titan, 'is_alive', False):
            return False
        dx = titan.x - self.x
        dy = titan.y - self.y
        if (dx * dx + dy * dy) ** 0.5 > self._atk_range:
            return False
        if self._atk_timer > 0.0:
            return False
        # Trong tầm + đã hồi → bắn.
        titan.take_damage(self._atk_damage, 'normal')
        if titan_ai is not None:
            titan_ai.notify_attacked(self)
        self._atk_timer = self._atk_cooldown
        return True


# ═════════════════════════════════════════════════════════════════
#  Headquarters — đại bản doanh
# ═════════════════════════════════════════════════════════════════

class Headquarters(TargetEntity):
    """HQ — mục tiêu cuối cùng của mọi Titan (entity_type='hq').

    Không bắn trả. Máu lớn. Vẽ hình vuông lớn màu vàng nhạt.
    """

    entity_type = 'hq'

    def __init__(self, x: float, y: float, hp: int = 5000) -> None:
        super().__init__(x, y, hp, label='HQ')

    def draw(self, screen: pygame.Surface, font) -> None:
        if not self.is_alive:
            return
        body = self._body_color((210, 190, 110))
        rect = pygame.Rect(int(self.x - 38), int(self.y - 38), 76, 76)
        pygame.draw.rect(screen, body, rect, border_radius=6)
        pygame.draw.rect(screen, (250, 240, 180), rect, 3)
        self._draw_hp_bar(screen, 80, 52, (230, 210, 90))
        self._draw_label(screen, font, 42)


# ═════════════════════════════════════════════════════════════════
#  WallDummy — đoạn tường thành
# ═════════════════════════════════════════════════════════════════

class WallDummy(TargetEntity):
    """Đoạn tường (entity_type='wall').

    Cản đường Titan vào HQ. Không bắn trả. Vẽ hình chữ nhật xám đậm.

    Tham số `vertical=True`: vẽ tường dọc (44×88px) thay vì ngang
    (88×44px) — dùng cho cạnh trái/phải khi bao vây HQ.
    """

    entity_type = 'wall'

    def __init__(self, x: float, y: float, hp: int = 1200,
                 label: str = 'Wall', vertical: bool = False) -> None:
        super().__init__(x, y, hp, label=label)
        self._vertical = vertical

    def draw(self, screen: pygame.Surface, font) -> None:
        if not self.is_alive:
            return
        body = self._body_color((110, 105, 120))
        if self._vertical:
            # Tường dọc: 44 rộng × 88 cao
            rect = pygame.Rect(int(self.x - 22), int(self.y - 44), 44, 88)
            pygame.draw.rect(screen, body, rect, border_radius=3)
            pygame.draw.rect(screen, (170, 170, 190), rect, 2)
            for gy in range(-33, 44, 22):
                pygame.draw.line(screen, (80, 78, 92),
                                 (int(self.x - 22), int(self.y + gy)),
                                 (int(self.x + 22), int(self.y + gy)), 1)
            self._draw_hp_bar(screen, 48, 58, (180, 180, 200))
            self._draw_label(screen, font, 50)
        else:
            # Tường ngang: 88 rộng × 44 cao (mặc định)
            rect = pygame.Rect(int(self.x - 44), int(self.y - 22), 88, 44)
            pygame.draw.rect(screen, body, rect, border_radius=3)
            pygame.draw.rect(screen, (170, 170, 190), rect, 2)
            for gx in range(-33, 44, 22):
                pygame.draw.line(screen, (80, 78, 92),
                                 (int(self.x + gx), int(self.y - 22)),
                                 (int(self.x + gx), int(self.y + 22)), 1)
            self._draw_hp_bar(screen, 92, 36, (180, 180, 200))
            self._draw_label(screen, font, 26)


# ═════════════════════════════════════════════════════════════════
#  TowerDummy — tháp phòng thủ
# ═════════════════════════════════════════════════════════════════

class TowerDummy(AttackerEntity):
    """Tháp phòng thủ (entity_type='tower').

    Bắn Titan trong tầm. Có thể bị ColossalTitan stun (`stun()`),
    khi đó ngừng bắn. Vẽ hình vuông xám có lỗ châu mai.
    """

    entity_type = 'tower'

    def __init__(self, x: float, y: float, hp: int = 800,
                 label: str = 'Tower') -> None:
        super().__init__(x, y, hp,
                         attack_range=220.0, attack_damage=12,
                         attack_cooldown=1.2, label=label)
        self._stun_timer = 0.0

    def stun(self, duration: float) -> None:
        """Bị choáng `duration` giây — ngừng bắn trong thời gian đó."""
        self._stun_timer = max(self._stun_timer, duration)

    def try_shoot(self, titan, titan_ai, dt: float) -> bool:
        """Bắn — nhưng bị khóa khi đang bị stun."""
        if self._stun_timer > 0.0:
            return False
        return super().try_shoot(titan, titan_ai, dt)

    def update(self, dt: float) -> None:
        super().update(dt)
        if self._stun_timer > 0.0:
            self._stun_timer = max(0.0, self._stun_timer - dt)

    def draw(self, screen: pygame.Surface, font) -> None:
        if not self.is_alive:
            return
        stunned = self._stun_timer > 0.0
        if self._hit_flash > 0.0:
            body = (250, 220, 90)
        elif stunned:
            body = (255, 200, 0)
        else:
            body = (125, 130, 155)
        rect = pygame.Rect(int(self.x - 22), int(self.y - 22), 44, 44)
        pygame.draw.rect(screen, body, rect, border_radius=4)
        pygame.draw.rect(screen, (210, 215, 240), rect, 2)
        # Lỗ châu mai trên đỉnh tháp.
        for cx in (-14, 0, 14):
            pygame.draw.rect(screen, (210, 215, 240),
                             (int(self.x + cx - 4), int(self.y - 28), 8, 8))
        self._draw_hp_bar(screen, 52, 38, (220, 180, 80))
        self._draw_label(screen, font, 26)


# ═════════════════════════════════════════════════════════════════
#  SoldierDummy — lính bộ binh
# ═════════════════════════════════════════════════════════════════

class SoldierDummy(AttackerEntity):
    """Lính (entity_type='soldier').

    Bắn Titan tầm gần. Máu thấp. Vẽ vòng tròn xanh lá nhỏ.
    """

    entity_type = 'soldier'

    def __init__(self, x: float, y: float, hp: int = 200,
                 label: str = 'Soldier') -> None:
        super().__init__(x, y, hp,
                         attack_range=140.0, attack_damage=6,
                         attack_cooldown=0.8, label=label)

    def draw(self, screen: pygame.Surface, font) -> None:
        if not self.is_alive:
            return
        body = self._body_color((100, 185, 110))
        pygame.draw.circle(screen, body,
                           (int(self.x), int(self.y)), 13)
        pygame.draw.circle(screen, (200, 240, 200),
                           (int(self.x), int(self.y)), 13, 2)
        self._draw_hp_bar(screen, 30, 24, (120, 220, 120))


# ═════════════════════════════════════════════════════════════════
#  CommanderDummy — tướng quân
# ═════════════════════════════════════════════════════════════════

class CommanderDummy(AttackerEntity):
    """Tướng (entity_type='commander').

    Bắn Titan mạnh hơn lính. Vẽ vòng tròn xanh lớn có viền vàng + tên.

    Pushback (NHÓM 6 — Beast):
        Cập nhật balance: Commander **BỊ pushback nhưng yếu hơn soldier**
        (~50%), được Beast cấu hình qua `_DEFAULT_PUSHBACK_COMMANDER`.
        Trước đây Commander miễn nhiễm hoàn toàn — không còn đúng nữa.
    """

    entity_type = 'commander'

    def __init__(self, x: float, y: float, name: str = 'Levi',
                 hp: int = 600) -> None:
        super().__init__(x, y, hp,
                         attack_range=170.0, attack_damage=14,
                         attack_cooldown=1.0, label=name)
        self.name = name

    def draw(self, screen: pygame.Surface, font) -> None:
        if not self.is_alive:
            return
        body = self._body_color((60, 210, 95))
        pygame.draw.circle(screen, body,
                           (int(self.x), int(self.y)), 17)
        pygame.draw.circle(screen, (225, 220, 90),
                           (int(self.x), int(self.y)), 17, 3)
        self._draw_hp_bar(screen, 40, 30, (80, 220, 80))
        self._draw_label(screen, font, 21)
