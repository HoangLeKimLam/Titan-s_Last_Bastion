# structures/wall/wall.py
import os
try:
    import pygame
    _PYGAME_OK = True
except ImportError:
    _PYGAME_OK = False

from core.entity import Entity
from core.interfaces import IAttackable
from core.event_bus import GameEventBus

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

    def __init__(self, x: float, y: float, max_hp: int = 10000,
                 section_type: str = 'wall_h'):
        super().__init__(x, y)
        self._hp          = max_hp
        self._max_hp      = max_hp
        self.section_type = section_type

    # ── combat ────────────────────────────────────────────────────────────────

    def take_damage(self, amount: int, dtype: str):
        self._hp -= amount
        if self._hp <= 0:
            self.is_alive = False
            GameEventBus.get_instance().publish(
                'wall_section_broken', {'section': self}
            )

    def get_hp_percent(self) -> float:
        return self._hp / self._max_hp

    def repair(self, amount: int):
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

    def update(self, dt: float): pass

    def draw(self, screen):
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
        section = self._find_nearest_section(pos)
        if section is not None:
            section.take_damage(amount, dtype)
            if not section.is_alive:
                GameEventBus.get_instance().publish(
                    'wall_breached', {'wall': self, 'section': section}
                )

    def is_destroyed(self) -> bool:
        return all(not s.is_alive for s in self._sections)

    def get_hp_percent(self) -> float:
        total     = sum(s._hp     for s in self._sections)
        total_max = sum(s._max_hp for s in self._sections)
        return total / total_max if total_max > 0 else 0.0

    def repair_all(self, amount: int):
        for s in self._sections:
            s.repair(amount)

    # ── update / draw ───────────────────────────────────────────────────────────

    def update(self, dt: float):
        for s in self._sections:
            s.update(dt)

    def draw(self, screen):
        # Y-sort: section có Y nhỏ hơn render trước → chantuong (Y lớn) đè lên wall_path
        for s in sorted(self._sections, key=lambda s: s.y):
            s.draw(screen)

    # ── internal ────────────────────────────────────────────────────────────────

    def _find_nearest_section(self, pos: tuple):
        if pos is None:
            return self._sections[0] if self._sections else None
        px, py = pos
        alive  = [s for s in self._sections if s.is_alive]
        if not alive:
            return None
        return min(alive, key=lambda s: (s.x - px)**2 + (s.y - py)**2)
