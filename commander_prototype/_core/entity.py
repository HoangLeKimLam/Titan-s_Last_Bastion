"""
entity.py — Lớp cha gốc của mọi đối tượng trong game.

Tại sao cần file này?
    Mọi thứ trong game — Titan, Tower, Soldier, Building, WallSection —
    đều CÓ vị trí (x, y), CÓ id duy nhất, và CẦN được update mỗi frame
    và draw lên màn hình.

    Thay vì mỗi class tự khai báo lại x, y, id, ta đặt ở Entity một lần.
    Tất cả class con kế thừa miễn phí.

Ai kế thừa Entity:
    Character(Entity) → Titan, Commander, Soldier
    Structure(Entity) → Tower, Building, Wall
    LootNode(Entity)

Quy tắc bắt buộc:
    - update(dt) và draw(screen) là 2 method TÁCH BIỆT hoàn toàn.
    - KHÔNG gọi draw() bên trong update().
    - KHÔNG gọi update() bên trong draw().
    - dt (delta time) ≈ 0.016 giây (tương đương 60 FPS).
"""

from abc import ABC, abstractmethod

#ABC ở đay mang nghĩa "Abstract Base Class" — lớp cha trừu tượng, không thể khởi tạo trực tiếp. Chỉ để kế thừa để xài.
#abstractmethod là đánh dấu method phải được override trong class con. Nếu class con không định nghĩa update() hoặc draw(), sẽ bị lỗi.
class Entity(ABC):
    """
    Lớp cha trừu tượng cho mọi đối tượng tồn tại trong thế giới game.

    Attributes:
        id       (str):   ID duy nhất, tự sinh từ _id_counter. Dùng để phân biệt
                          2 entity cùng loại, tra cứu trong WorldQuery.
        x        (float): Tọa độ ngang tính bằng pixel (0 = trái màn hình).
        y        (float): Tọa độ dọc tính bằng pixel (0 = trên màn hình).
        is_alive (bool):  True = đang tồn tại. False = cần xóa khỏi danh sách.
                          Game loop kiểm tra is_alive để remove entity chết.

    Class attribute:
        _id_counter (int): Bộ đếm tăng dần, dùng để tạo id duy nhất.
                           Mỗi lần Entity.__init__() chạy, counter tăng 1.
    """

    _id_counter: int = 0

    def __init__(self, x: float, y: float):
        """
        Khởi tạo entity tại vị trí (x, y).

        Args:
            x (float): Tọa độ ngang ban đầu (pixel).
            y (float): Tọa độ dọc ban đầu (pixel).

            Entity._id_counter += 1
            self.id       = f"entity_{Entity._id_counter}"
            self.x        = x
            self.y        = y
            self.is_alive = True

        Lưu ý:
            Class con gọi super().__init__(x, y) để tự động có id, x, y, is_alive.
            Ví dụ trong Titan.__init__:
                def __init__(self, x, y, config):
                    super().__init__(x, y)   # ← bắt buộc
                    self._hp = config['hp']
                    ...
        """
        Entity._id_counter += 1
        self.id=f"entity_{Entity._id_counter}"
        self.x=x
        self.y=y
        self.is_alive=True

    @abstractmethod
    def update(self, dt: float):
        """
        Các class con đều phải có method này 
        Cập nhật trạng thái logic của entity mỗi frame.

        Args:
            dt (float): Thời gian (giây) từ frame trước đến frame này.
                        Ở 60 FPS thì dt ≈ 0.016.
                        Dùng dt để tính toán không phụ thuộc FPS:
                            self.x += self._speed * dt   ✅ đúng
                            self.x += self._speed        ❌ sai — phụ thuộc FPS

        Những gì nên làm trong update():
            - Di chuyển (cập nhật x, y)
            - Giảm cooldown / timer
            - Kiểm tra trạng thái (stun, freeze…)
            - Quyết định AI (Titan chọn mục tiêu, Soldier đổi state)
            - Spawn projectile / gọi take_damage
        Ví dụ class con:
            def update(self, dt: float):
                self._shoot_timer -= dt
                if self._shoot_timer <= 0:
                    self.shoot(self._pick_target())
                    self._shoot_timer = self._cooldown
        """
        ...

    @abstractmethod
    def draw(self, screen):
        """
        Các class con đều phải có method này
        Vẽ entity lên màn hình Pygame.

        Args:
            screen: pygame.Surface — bề mặt màn hình chính.
                    Nhận từ main.py và truyền xuống qua game loop.

        Những gì nên làm trong draw():
            - screen.blit(self._sprite, (self.x, self.y))
            - Vẽ thanh HP nếu cần
            - Vẽ hiệu ứng (vòng tròn range, icon skill…)

        KHÔNG làm trong draw():
            - KHÔNG thay đổi bất kỳ thuộc tính logic nào (x, y, _hp…)
            - KHÔNG gọi update()

        Ví dụ class con:
            def draw(self, screen):
                screen.blit(self._sprite, (int(self.x), int(self.y)))
                # Vẽ HP bar phía trên
                bar_w = 40
                ratio = self._hp / self._max_hp
                pygame.draw.rect(screen, (255,0,0), (self.x, self.y-8, bar_w, 5))
                pygame.draw.rect(screen, (0,255,0), (self.x, self.y-8, int(bar_w*ratio), 5))
        """
        ...

    @property
    def position(self) -> tuple:
        """
        Trả về tọa độ hiện tại dưới dạng tuple (x, y).

        Returns:
            tuple: (x, y) — tiện dùng khi truyền vào move() hoặc WorldQuery.


            return (self.x, self.y)

        Ví dụ:
            scout.move(tower.position)        # Scout di chuyển về tháp
            WorldQuery.find_in_radius(*hq.position, 200, 'titan')
        """
        return (self.x, self.y)

    def __repr__(self) -> str:
        """
        Chuỗi đại diện khi print(entity) hoặc debug.

        Returns:
            str: vd. "RegularTitan(id=entity_5, x=320.0, y=180.0)"

            return f"{self.__class__.__name__}(id={self.id}, x={self.x:.1f}, y={self.y:.1f})"
        """
        return f"{self.__class__.__name__}(id={self.id}, x={self.x:.1f}, y={self.y:.1f})"