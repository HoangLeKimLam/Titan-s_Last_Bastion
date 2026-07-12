# structures/wall/wall.py
import os
try:
    import pygame
    from systems.sound_system import SoundManager
    _PYGAME_OK = True
except ImportError:
    _PYGAME_OK = False

from core.entity import Entity
from core.interfaces import IAttackable
from core.event_bus import GameEventBus
from config import balance

_HERE = os.path.dirname(os.path.abspath(__file__))

_SPRITE_FILES = {
    'wall_h':     'wall.png',
    'wall_Y':     'wall_Y.png',
    'corner_ul':  'corner_up_left.png',
    'corner_ur':  'corner_up_right.png',
    'corner_dl':  'corner_down_left.png',
    'corner_dr':  'corner_down_right.png',
}

# Shared cache: section_type → pygame.Surface (loaded once)
_sprite_cache: dict = {}


def _get_sprite(section_type: str):
    """Nạp lazy sprite ĐÚNG LOẠI ĐOẠN TƯỜNG, cache CHUNG cho MỌI WallSection cùng loại.

    Module-level cache (`_sprite_cache`) — MỌI đoạn tường `wall_h` trên bản đồ
    dùng CHUNG 1 Surface đã nạp, không nạp lại từng section. Loại không có trong
    `_SPRITE_FILES` hoặc file thiếu → cache None (WallSection.draw() bỏ qua).
    `not _PYGAME_OK` (import pygame thất bại — hiếm) → luôn trả None.
    """
    if not _PYGAME_OK:
        return None
    if section_type not in _sprite_cache:
        fname = _SPRITE_FILES.get(section_type)
        path  = os.path.join(_HERE, fname) if fname else None
        if path and os.path.exists(path):
            _sprite_cache[section_type] = pygame.image.load(path).convert_alpha()
        else:
            _sprite_cache[section_type] = None
    return _sprite_cache[section_type]


class WallSection(Entity, IAttackable):
    """Leaf — 1 đoạn tường nhỏ. Có HP riêng.

    section_type:
        'wall_h'    — cạnh ngang (trục X): wall.png
        'wall_path' — cạnh dọc lớp trên (sàn đi bộ): wall_path.png
        'chantuong' — cạnh dọc lớp dưới (mặt đá): chantuong.png
        'corner_ul' / 'corner_ur' / 'corner_dl' / 'corner_dr' — 4 góc
    """

    ENTITY_TYPE = 'wall'

    def __init__(self, x: float, y: float, max_hp: int = balance.WALL_SECTION_HP,
                 section_type: str = 'wall_h'):
        """Tạo 1 đoạn tường (Leaf trong Composite Pattern) đầy máu tại (x,y).

        Tham số: max_hp — mặc định `balance.WALL_SECTION_HP`; section_type —
            quyết định sprite nào được vẽ (xem `_SPRITE_FILES`).
        """
        super().__init__(x, y)
        self._hp          = max_hp
        self._max_hp      = max_hp
        self.section_type = section_type

    # ── combat ────────────────────────────────────────────────────────────────

    def take_damage(self, amount: int, dtype: str):
        """Nhận damage — hết HP thì SẬP: phát âm thanh + publish event.

        Guard `is_alive` đầu hàm — CHẶN DAMAGE TIẾP TỤC vào đoạn tường đã sập
        (không thì titan giẫm liên tục qua `check_trampling()` sẽ phát âm thanh
        + publish `'wall_section_broken'` LẶP LẠI mỗi lần chạm, dù tường đã chết).
        `dtype` hiện KHÔNG được dùng để tính giáp/hệ số (tường không có giáp
        riêng — hệ số theo dtype như ×3 lên tường nằm ở `AttackStrategy` bên gọi).
        """
        if not self.is_alive:
            return
        self._hp -= amount
        if self._hp <= 0:
            SoundManager.get_instance().play('wall_collapse_1', self.x, self.y)
            self.is_alive = False
            GameEventBus.get_instance().publish(
                'wall_section_broken', {'section': self}
            )

    def get_hp_percent(self) -> float:
        """Tỉ lệ HP còn lại (0.0-1.0) của đoạn tường này."""
        return self._hp / self._max_hp

    def repair(self, amount: int):
        """Hồi HP — nếu đoạn tường ĐÃ SẬP mà hồi lại được thì SỐNG LẠI + báo WorldQuery cập nhật lỗ hổng.

        Thuật toán: ghi nhớ trạng thái chết TRƯỚC khi hồi (`was_dead`). Hồi HP
        (kẹp trần `_max_hp`). HP > 0 → `is_alive = True`. Nếu VỪA SỐNG LẠI
        (`was_dead`), đánh dấu `WorldQuery._dead_clusters_dirty = True` —
        CỤM LỖ HỔNG (dùng bởi titan để tìm đường xuyên tường) đã thay đổi, cần
        tính lại; không đánh dấu thì titan vẫn tưởng còn lỗ ở chỗ vừa được vá.
        """
        was_dead = not self.is_alive
        self._hp = min(self._max_hp, self._hp + amount)
        if self._hp > 0:
            self.is_alive = True
            # Tường sống lại → cụm lỗ hổng thay đổi, báo cho WorldQuery cập nhật
            if was_dead:
                try:
                    from systems.world_query import WorldQuery
                    WorldQuery._dead_clusters_dirty = True
                except ImportError:
                    pass

    # ── update / draw ──────────────────────────────────────────────────────────

    def update(self, dt: float):
        """No-op — tường không có logic per-frame, chỉ phản ứng thụ động qua `take_damage()`/`repair()`."""
        pass

    def draw(self, screen):
        """Vẽ sprite ĐÚNG LOẠI (qua cache `_get_sprite`) tại (x,y). Đoạn tường
        đã sập (`not is_alive`) → KHÔNG vẽ gì (biến mất khỏi bản đồ)."""
        if not _PYGAME_OK or not self.is_alive:
            return
        surf = _get_sprite(self.section_type)
        if surf is not None:
            screen.blit(surf, (int(self.x), int(self.y)))


class Wall(Entity, IAttackable):
    """Composite — chứa nhiều WallSection.

    positions: list of (x, y) or (x, y, section_type)
    Gọi wall.take_damage(100, pos=(x,y)) →
    Wall tự tìm section gần pos nhất → trừ HP section đó.
    """

    def __init__(self, name: str, positions: list):
        """Tạo 1 VÒNG TƯỜNG (Maria/Rose/Sina) — COMPOSITE gồm nhiều `WallSection`.

        Tham số:
            name: tên vòng tường ('maria'/'rose'/'sina').
            positions: list điểm — mỗi phần tử `(x, y)` HOẶC `(x, y, section_type)`.
                Thiếu `section_type` → mặc định 'wall_h'.

        `Wall` bản thân KHÔNG có HP riêng (dù kế thừa `IAttackable`) — mọi damage
        được UỶ QUYỀN xuống ĐÚNG 1 section cụ thể (xem `take_damage`).
        """
        super().__init__(x=0, y=0)
        self.name = name
        self._sections: list[WallSection] = []
        for entry in positions:
            if len(entry) == 3:
                px, py, stype = entry
            else:
                px, py = entry
                stype  = 'wall_h'
            self._sections.append(WallSection(px, py, section_type=stype))

    # ── combat ─────────────────────────────────────────────────────────────────

    def take_damage(self, amount: int, dtype: str = 'normal',
                    pos: tuple = None):
        """UỶ QUYỀN damage xuống ĐÚNG 1 section gần `pos` nhất — đây là "cầu nối" Composite→Leaf.

        Thuật toán: `_find_nearest_section(pos)` tìm section mục tiêu, đẩy
        damage xuống nó. Section đó VỪA SẬP (không còn `is_alive`) →
        publish `'wall_breached'` (kèm cả `wall` composite lẫn `section` cụ thể)
        — HUD/Camera/WaveManager/Audio subscribe để phản ứng (cảnh báo, âm thanh sập tường).

        Tham số: pos — toạ độ NƠI TRÚNG ĐÒN (thường x,y của titan đang húc). None
            → fallback section ĐẦU TIÊN trong list (dùng khi không rõ vị trí cụ thể).
        """
        section = self._find_nearest_section(pos)
        if section is not None:
            section.take_damage(amount, dtype)
            if not section.is_alive:
                GameEventBus.get_instance().publish(
                    'wall_breached', {'wall': self, 'section': section}
                )

    def is_destroyed(self) -> bool:
        """True nếu TOÀN BỘ section trong vòng tường đã sập (không còn đoạn nào sống)."""
        return all(not s.is_alive for s in self._sections)

    def get_hp_percent(self) -> float:
        """Tỉ lệ HP TỔNG (cộng dồn mọi section) — HUD dùng vẽ thanh máu cả vòng
        tường, KHÁC `WallSection.get_hp_percent()` (chỉ 1 đoạn)."""
        total     = sum(s._hp     for s in self._sections)
        total_max = sum(s._max_hp for s in self._sections)
        return total / total_max if total_max > 0 else 0.0

    def repair_all(self, amount: int):
        """Hồi `amount` HP cho MỌI section trong vòng tường (kể cả đoạn đã sập
        — có thể làm chúng SỐNG LẠI, xem `WallSection.repair`). Dùng bởi
        RepairStation (building.py) và Castle Menu (sửa tường thủ công)."""
        for s in self._sections:
            s.repair(amount)

    # ── update / draw ───────────────────────────────────────────────────────────

    def update(self, dt: float):
        """Uỷ quyền update cho TỪNG section (hiện là no-op, chỉ để đúng interface)."""
        for s in self._sections:
            s.update(dt)

    def draw(self, screen):
        """Vẽ MỌI section, SẮP XẾP THEO Y (Y nhỏ vẽ trước) để lớp đúng thứ tự:
        đoạn `chantuong` (Y lớn hơn, mặt đá phía dưới) ĐÈ LÊN đoạn `wall_path`
        (sàn đi bộ phía trên) — mô phỏng chiều sâu top-down."""
        # Y-sort: section có Y nhỏ hơn render trước → chantuong (Y lớn) đè lên wall_path
        for s in sorted(self._sections, key=lambda s: s.y):
            s.draw(screen)

    # ── internal ────────────────────────────────────────────────────────────────

    def _find_nearest_section(self, pos: tuple):
        """Tìm section CÒN SỐNG gần `pos` nhất (so bình phương khoảng cách).

        `pos is None` → trả section ĐẦU TIÊN trong list (bất kể sống/chết) —
        fallback đơn giản khi không biết vị trí cụ thể. Không còn section nào
        sống → None.
        """
        if pos is None:
            return self._sections[0] if self._sections else None
        px, py = pos
        alive  = [s for s in self._sections if s.is_alive]
        if not alive:
            return None
        return min(alive, key=lambda s: (s.x - px)**2 + (s.y - py)**2)
