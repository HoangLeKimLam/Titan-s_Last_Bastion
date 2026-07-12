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
        """Tạo cả 3 vòng tường Maria (ngoài) / Rose (giữa) / Sina (trong) cùng lúc.

        Tham số: mỗi `*_positions` là list điểm section (xem `Wall.__init__`),
        do `game.py` tính sẵn từ layout bản đồ khi khởi tạo level. Object
        này là điểm truy cập DUY NHẤT tới cả 3 vòng tường — WorldQuery/AI
        titan/HUD đều đi qua `get_wall()`/`all_walls()`, không giữ tham chiếu
        `Wall` trực tiếp.
        """
        self._walls = {
            'maria': Wall('maria', maria_positions),
            'rose':  Wall('rose',  rose_positions),
            'sina':  Wall('sina',  sina_positions),
        }

    def get_wall(self, name: str) -> Wall:
        """Lấy 1 vòng tường theo tên ('maria'/'rose'/'sina'). KeyError nếu sai tên."""
        return self._walls[name]

    def all_walls(self) -> list:
        """Trả về list cả 3 `Wall` — dùng khi cần lặp qua TẤT CẢ (vd tính tổng HP, vẽ toàn bộ)."""
        return list(self._walls.values())

    def update(self, dt: float):
        """Uỷ quyền update cho cả 3 vòng tường (mỗi `Wall.update` hiện là no-op)."""
        for w in self._walls.values():
            w.update(dt)

    def draw(self, screen):
        """Vẽ cả 3 vòng tường — THỨ TỰ dict (maria→rose→sina), KHÔNG y-sort
        giữa các vòng (chỉ y-sort NỘI BỘ từng vòng, xem `Wall.draw`); vì 3 vòng
        không chồng lấn nhau trên bản đồ nên thứ tự giữa chúng không quan trọng."""
        for w in self._walls.values():
            w.draw(screen)