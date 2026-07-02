# structures/wall/wall_system.py
from structures.wall.wall import Wall


class WallSystem:
    """Quản lý 3 vòng tường Maria / Rose / Sina.

    Dùng:
        ws = WallSystem(maria_positions, rose_positions, sina_positions)
        ws.get_wall('maria').take_damage(100, pos=(x, y))
    """

    WALL_NAMES = ('maria', 'rose', 'sina')

    def __init__(self,
                 maria_positions: list,
                 rose_positions: list,
                 sina_positions: list):
        self._walls = {
            'maria': Wall('maria', maria_positions),
            'rose':  Wall('rose',  rose_positions),
            'sina':  Wall('sina',  sina_positions),
        }

    def get_wall(self, name: str) -> Wall:
        return self._walls[name]

    def all_walls(self) -> list:
        return list(self._walls.values())

    def update(self, dt: float):
        for w in self._walls.values():
            w.update(dt)

    def draw(self, screen):
        for w in self._walls.values():
            w.draw(screen)