"""
event_bus.py — Hệ thống sự kiện Observer dùng chung toàn game.

Tại sao cần file này?
    Không dùng EventBus: WallSection phải biết HUD, WaveManager, Audio
    để thông báo "tôi bị phá". Mỗi class biết nhau → coupling chặt → sửa
    1 class phải sửa 5 class khác.

    Dùng EventBus: WallSection chỉ gọi publish('wall_breached', data).
    HUD, WaveManager, Audio tự subscribe. Không ai biết ai — loose coupling.

Sự kiện chuẩn trong game:
    'wall_breached'       — WallSection publish  → HUD, Camera, WaveManager, Audio subscribe
    'titan_died'          — Titan publish         → ResourceManager (+thưởng), WaveManager
    'soldier_died'        — Soldier publish       → ResourceManager, HUD
    'building_destroyed'  — Building publish      → ResourceManager, HUD
    'tower_destroyed'     — Tower publish         → HUD, lính rút lui
    'wave_started'        — WaveManager publish   → HUD, Audio
    'game_over'           — GameManager publish   → UI, Audio

Pattern: Singleton — chỉ tồn tại 1 instance duy nhất trong toàn bộ game.
"""

from typing import Callable, Dict, List, Any


class GameEventBus:
    """
    Singleton Observer — trung tâm phát/nhận sự kiện toàn game.

    Attributes (private):
        _instance  (GameEventBus): Instance duy nhất (class attribute).
        _listeners (dict):         {event_name: [callback1, callback2, ...]}

    Cách lấy instance:
        bus = GameEventBus.get_instance()   # ← LUÔN dùng cách này
        # KHÔNG gọi GameEventBus() trực tiếp
    """

    _instance: "GameEventBus" = None

    def __init__(self):
        """
        Khởi tạo dict listeners rỗng.

        CẢNH BÁO: KHÔNG gọi trực tiếp từ bên ngoài.
            Luôn dùng GameEventBus.get_instance().

        Hướng dẫn code:
            self._listeners: Dict[str, List[Callable]] = {}
        """
        self._listeners = {}

    @classmethod
    def get_instance(cls) -> "GameEventBus":
        """
        Trả về instance duy nhất, tạo mới nếu chưa có (Singleton pattern).

        Returns:
            GameEventBus: Instance toàn cục.

        Hướng dẫn code:
            if cls._instance is None:
                cls._instance = GameEventBus()
            return cls._instance

        Ví dụ — lấy bus ở bất kỳ đâu:
            bus = GameEventBus.get_instance()
            bus.publish('titan_died', {'titan_id': self.id, 'reward': 50})
        """
        if cls._instance is None:
            cls._instance = GameEventBus()
        return cls._instance

    def subscribe(self, event: str, callback: Callable):
        """
        Đăng ký lắng nghe một sự kiện.

        Args:
            event    (str):      Tên sự kiện, vd. 'wall_breached'.
            callback (Callable): Hàm sẽ được gọi khi sự kiện xảy ra.
                                 Signature: callback(data: Any) → None

        Hướng dẫn code:
            if event not in self._listeners:
                self._listeners[event] = []
            self._listeners[event].append(callback)

        Gọi subscribe() ở đâu:
            Gọi 1 lần khi khởi tạo hệ thống — thường trong __init__ hoặc
            trong hàm setup() của HUD, WaveManager, ResourceManager.

        Ví dụ — HUD đăng ký nghe wall_breached:
            class HUD:
                def __init__(self):
                    bus = GameEventBus.get_instance()
                    bus.subscribe('wall_breached', self.on_wall_breached)
                    bus.subscribe('titan_died',    self.on_titan_died)

                def on_wall_breached(self, data):
                    wall_name = data['wall']
                    self.show_alert(f"{wall_name} đã bị phá!")

        Ví dụ — ResourceManager đăng ký nhận thưởng khi Titan chết:
            bus.subscribe('titan_died', resource_manager.on_titan_died)
            # resource_manager.on_titan_died(data):
            #     self.earn(ResourceBundle(wood=data['reward']))
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        pass

    def publish(self, event: str, data: Any = None):
        """
        Phát sự kiện đến tất cả subscriber đã đăng ký.

        Args:
            event (str): Tên sự kiện.
            data  (Any): Dữ liệu đính kèm — thường là dict, có thể None.

        Hướng dẫn code:
            for callback in self._listeners.get(event, []):
                callback(data)

        Lưu ý:
            Nếu event chưa có subscriber nào → không làm gì (không raise lỗi).
            Dùng .get(event, []) để tránh KeyError.

        Ví dụ — WallSection gọi khi bị phá:
            GameEventBus.get_instance().publish(
                'wall_breached',
                {
                    'wall':    'Wall Maria',
                    'section': self.id,
                    'pos':     (self.x, self.y),
                }
            )

        Ví dụ — Titan gọi khi chết:
            GameEventBus.get_instance().publish(
                'titan_died',
                {
                    'titan_id': self.id,
                    'titan_type': self.__class__.__name__,
                    'reward':   self._loot_reward,
                    'pos':      (self.x, self.y),
                }
            )

        Ví dụ — WaveManager gọi khi wave bắt đầu:
            GameEventBus.get_instance().publish(
                'wave_started',
                {'wave_number': self._current_wave}
            )
        """
        for callback in self._listeners.get(event, []):
            callback(data)

    def unsubscribe(self, event: str, callback: Callable):
        """
        Huỷ đăng ký lắng nghe một sự kiện (dùng khi entity bị destroy).

        Args:
            event    (str):      Tên sự kiện.
            callback (Callable): Hàm đã đăng ký trước đó cần gỡ ra.

        Hướng dẫn code:
            if event in self._listeners:
                try:
                    self._listeners[event].remove(callback)
                except ValueError:
                    pass   # Không có trong list → bỏ qua

        Dùng khi nào:
            Khi Tower hoặc Building bị destroy — gỡ callback của nó khỏi bus
            để tránh gọi callback trên object đã chết.

        Ví dụ:
            class Tower:
                def on_death(self):
                    bus = GameEventBus.get_instance()
                    bus.unsubscribe('wave_started', self.on_wave_started)
                    self.is_alive = False
        """
        if event in self._listeners:
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass

    def clear(self):
        """
        Xoá toàn bộ listeners — dùng khi reset game hoặc load màn mới.

        Hướng dẫn code:
            self._listeners.clear()

        Dùng khi nào:
            GameManager.reset_level() → bus.clear() để tránh callback cũ
            từ màn trước vẫn bị gọi ở màn mới.

        Ví dụ:
            GameEventBus.get_instance().clear()
            # Sau đó các hệ thống subscribe lại từ đầu
        """
        self._listeners.clear()
