import os
import math
import pygame

# ==============================================================================
# CẤU HÌNH ÂM THANH (DÀNH CHO USER CHỈNH SỬA)
# ==============================================================================

# 1. Âm lượng cơ bản (Base Volume) cho từng loại âm thanh (từ 0.0 đến 1.0)
SOUND_VOLUMES = {
    'backmu': 0.2,                          # Nhạc nền (BGM)
    'click2': 0.7,                          # UI Click
    'normal_tower': 0.5,                    # Tháp thường bắn
    'elec_tower': 0.5,                      # Sét chuyền (Chain Lightning)
    'zap(electro)_1': 0.5,                  # Bãi điện giật
    'ice_tower_1': 0.5,                     # Đạn băng trúng
    'water_tower_1': 0.5,                   # Đạn nước trúng
    'xoaynuoc': 0.7,                        # Xoáy nước
    'clossal_steam': 0.9,                   # Boss Colossal xả hơi nước
    'founding_summon_6_recommended': 0.9,   # Boss Founding gọi đệ
    'kazekage_explosion': 0.8,              # Kamikaze (Kazekage) nổ
    'wall_collapse_1': 0.8,                 # Tường/nhà sập
    'skillE': 0.6,                          # Tướng xài kỹ năng E (ODM gear)
    'eren_transform_titan': 0.9,            # Eren hóa Titan
    'eren_titan_punch': 0.7,                # Eren Titan đấm
    'mikasa_skillR': 0.8,                   # Mikasa chém lốc
    'swing_sword': 1.0,                     # Tướng chém kiếm thường
}

# 2. Cooldown (milli-giây) - Tránh ồn ào khi nhiều âm thanh giống nhau phát cùng lúc
# Ví dụ: 100 có nghĩa là nếu file 'zap' vừa kêu, phải 100ms sau nó mới được kêu tiếp.
SOUND_COOLDOWNS = {
    'normal_tower': 50,
    'elec_tower': 100,
    'zap(electro)_1': 100,
    'ice_tower_1': 50,
    'water_tower_1': 50,
    'xoaynuoc': 500,        # Xoáy nước kêu dài nên chặn lâu
    'swing_sword': 100,     # Lính/tướng chém kiếm
    'eren_titan_punch': 100,
    'click2': 50,
}

# 3. Thời lượng tối đa (milli-giây) - Nếu file quá dài, ép nó phải dừng lại sau X ms
# Ví dụ: 'wall_collapse_1' dài 5 giây, ta ép nó dừng ở 2500ms (2.5 giây).
SOUND_MAXTIME = {
    'wall_collapse_1': 2500,
    'skillE': 600,
}

# ==============================================================================

class SoundManager:
    """Singleton phát âm thanh KHÔNG GIAN (positional/2D-panned) + nhạc nền.

    Cơ chế không gian: mọi âm thanh gọi qua `play(sound_id, x, y)` được tính
    LẠI âm lượng + cân bằng trái/phải (pan) MỖI LẦN PHÁT dựa trên khoảng
    cách/hướng tới tâm camera hiện tại (`update()` cập nhật tâm mỗi frame)
    — mô phỏng "nghe gần to, xa nhỏ, lệch trái/phải theo vị trí trên màn
    hình" mà không cần audio engine 3D thật. Singleton qua `__new__` (không
    phải `get_instance()` factory như các Singleton khác trong game — cả
    2 cách gọi `SoundManager()` VÀ `SoundManager.get_instance()` đều trả
    cùng 1 instance nhờ `__new__` chặn tạo instance thứ 2).
    """
    _instance = None

    def __new__(cls):
        """Chặn tạo instance thứ 2 — LUÔN trả `_instance` đã có (tạo lần
        đầu nếu chưa). `_initialized=False` gắn NGAY TRONG `__new__` (không
        phải `__init__`) để `__init__` (chạy MỖI LẦN gọi `SoundManager()`,
        kể cả khi `__new__` trả instance cũ) có thể tự phát hiện "đã init
        rồi" và bỏ qua, tránh reset `self.sounds` mỗi lần gọi constructor."""
        if cls._instance is None:
            cls._instance = super(SoundManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Chỉ chạy logic khởi tạo THẬT SỰ 1 LẦN DUY NHẤT (guard
        `_initialized`) — mọi lần gọi `SoundManager()` sau đó là no-op,
        giữ nguyên `self.sounds`/state cũ. `max_distance` khởi tạo tạm
        1000px, được `update()` tính lại chính xác theo kích thước màn
        hình thật ngay khi vòng lặp game bắt đầu gọi."""
        if self._initialized:
            return
        self._initialized = True
        
        self.sounds = {}
        self.cam_center_x = 0.0
        self.cam_center_y = 0.0
        self.screen_w = 1280.0
        self.screen_h = 720.0
        self.max_distance = 1000.0  # Sẽ được cập nhật động trong update()
        
        self._cooldown_timers = {}

    def init_sounds(self, base_dir: str):
        """Khởi tạo mixer và load toàn bộ âm thanh."""
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.set_num_channels(32)
        
        sfx_dir = os.path.join(base_dir, 'sfx')
        if not os.path.exists(sfx_dir):
            print("SoundManager: Khong tim thay thu muc sfx:", sfx_dir)
            return

        for f in os.listdir(sfx_dir):
            if f.endswith('.wav') or f.endswith('.mp3'):
                path = os.path.join(sfx_dir, f)
                name = os.path.splitext(f)[0]
                
                if name == 'backmu':
                    try:
                        pygame.mixer.music.load(path)
                        pygame.mixer.music.set_volume(SOUND_VOLUMES.get(name, 0.3))
                        pygame.mixer.music.play(-1) # Loop forever
                    except Exception as e:
                        print(f"SoundManager: Loi load BGM {f}: {e}")
                else:
                    try:
                        sound = pygame.mixer.Sound(path)
                        sound.set_volume(SOUND_VOLUMES.get(name, 0.7))
                        self.sounds[name] = sound
                    except Exception as e:
                        print(f"SoundManager: Loi load sound {f}: {e}")

    def update(self, cam_x: float, cam_y: float, screen_w: int, screen_h: int):
        """Cập nhật tọa độ tâm camera mỗi frame."""
        self.screen_w = float(screen_w)
        self.screen_h = float(screen_h)
        self.cam_center_x = cam_x + self.screen_w / 2.0
        self.cam_center_y = cam_y + self.screen_h / 2.0
        
        # Bán kính màn hình * 1.3 (Âm thanh mất dần khi ra khỏi mép màn hình)
        screen_radius = math.hypot(self.screen_w / 2.0, self.screen_h / 2.0)
        self.max_distance = screen_radius * 1.3

    def play(self, sound_id: str, x: float = None, y: float = None):
        """Phát âm thanh tại tọa độ (x, y). Nếu x, y = None thì phát full 2 tai."""
        if sound_id not in self.sounds:
            return

        now = pygame.time.get_ticks()
        limit = SOUND_COOLDOWNS.get(sound_id, 0)
        last_played = self._cooldown_timers.get(sound_id, 0)
        
        if now - last_played < limit:
            return
            
        self._cooldown_timers[sound_id] = now

        sound = self.sounds[sound_id]
        channel = pygame.mixer.find_channel(force=False)
        
        if channel is None:
            return # Full channel

        base_vol = SOUND_VOLUMES.get(sound_id, 0.7)
        maxtime = SOUND_MAXTIME.get(sound_id, 0)

        # Global/UI sound
        if x is None or y is None:
            channel.set_volume(base_vol, base_vol)
            channel.play(sound, maxtime=maxtime)
            return

        # Spatial sound
        dx = x - self.cam_center_x
        dy = y - self.cam_center_y
        dist = math.hypot(dx, dy)

        if dist > self.max_distance:
            return  # Culling

        # Attenuation
        atten = max(0.0, 1.0 - (dist / self.max_distance))
        
        # Panning
        pan = max(-1.0, min(1.0, dx / (self.screen_w / 2.0)))
        
        vol = atten * base_vol
        
        if pan < 0:
            left_vol = vol
            right_vol = vol * (1.0 - abs(pan))
        else:
            left_vol = vol * (1.0 - abs(pan))
            right_vol = vol

        channel.set_volume(left_vol, right_vol)
        channel.play(sound, maxtime=maxtime)

    @classmethod
    def get_instance(cls):
        """Trả instance Singleton — tương đương gọi `SoundManager()` trực
        tiếp (nhờ `__new__` chặn tạo instance thứ 2), giữ để đồng nhất
        API `get_instance()` với các Singleton khác trong game
        (ResourceManager, GameEventBus...)."""
        return cls()
