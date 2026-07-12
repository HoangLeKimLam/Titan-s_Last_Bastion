import pygame
import os
from core.entity import Entity

class SpriteSheet:
    """Bọc 1 ảnh sprite sheet (nhiều frame xếp lưới), cắt ra từng
    `pygame.Surface` con theo yêu cầu — hạ tầng dùng chung bởi
    `load_animation_strip()`/`load_spritesheet()` để nạp hiệu ứng VFX cho
    tháp/đạn/trạng thái (đóng băng, cháy...)."""

    def __init__(self, filename):
        """Nạp ảnh sheet từ `filename`. Lỗi tải (file thiếu/hỏng) → in cảnh
        báo rồi `raise SystemExit` — CỐ Ý crash cứng thay vì fallback im
        lặng, vì thiếu sprite VFX là lỗi asset cần phát hiện ngay lúc dev,
        không nên trôi tới runtime rồi vẽ sai/thiếu hiệu ứng."""
        try:
            self.sheet = pygame.image.load(filename).convert_alpha()
        except pygame.error as e:
            print(f"Unable to load spritesheet image: {filename}")
            raise SystemExit(e)

    def image_at(self, rectangle):
        """Loads image from x, y, x+offset, y+offset"""
        rect = pygame.Rect(rectangle)
        image = pygame.Surface(rect.size, pygame.SRCALPHA)
        image.blit(self.sheet, (0, 0), rect)
        return image

    def load_strip(self, rect, image_count):
        """Loads a strip of images and returns them as a list"""
        tups = [(rect[0] + rect[2] * x, rect[1], rect[2], rect[3])
                for x in range(image_count)]
        return [self.image_at(t) for t in tups]


class Animation:
    """Trình phát animation frame-based độc lập với entity — chỉ giữ danh
    sách frame + con trỏ thời gian thực (`current_frame` là FLOAT, không
    phải index nguyên, để nội suy tốc độ mượt bất kể dt dao động). Dùng
    làm khối xây dựng cho `TransientEffect`/`AttachedStatusVFX`."""

    def __init__(self, frames, fps=30, loop=True, loop_start_frame=0):
        """Tham số: frames — list Surface theo thứ tự phát; fps — tốc độ
        phát (frame/giây); loop — hết frame có quay lại từ đầu không;
        loop_start_frame — khi loop, quay về frame NÀY thay vì frame 0 (cho
        phép có đoạn "intro" chạy 1 lần rồi lặp phần thân, xem `update()`)."""
        self.frames = frames
        self.fps = fps
        self.loop = loop
        self.loop_start_frame = loop_start_frame
        self.current_frame = 0.0
        self.finished = False

    def update(self, dt):
        """Tiến `current_frame` theo `fps * dt` (thời gian thực, không phải
        cộng 1 mỗi lần gọi — animation chạy đúng tốc độ dù `update()` được
        gọi không đều). Vượt quá độ dài `frames`:
          - `loop=True`: tính phần dư `over` VƯỢT qua cuối, rồi MOD lại
            trong đoạn `[loop_start_frame, len(frames))` — cho phép lặp chỉ
            1 ĐOẠN của dải frame (bỏ qua phần "intro" ở lần lặp sau).
          - `loop=False`: kẹp ở frame cuối, đặt `finished=True` (caller —
            `TransientEffect.update()`/`AttachedStatusVFX.update()` — đọc
            cờ này để chuyển trạng thái hoặc tự huỷ).
        Đã `finished` → no-op (animation 1-lần đã dừng vĩnh viễn cho tới khi `reset()`).
        """
        if self.finished:
            return

        self.current_frame += self.fps * dt
        if self.current_frame >= len(self.frames):
            if self.loop:
                over = self.current_frame - len(self.frames)
                loop_len = len(self.frames) - self.loop_start_frame
                self.current_frame = self.loop_start_frame + (over % loop_len)
            else:
                self.current_frame = len(self.frames) - 1
                self.finished = True

    def get_current_frame(self):
        """Frame Surface tại vị trí hiện tại (làm tròn xuống — int hoá
        `current_frame` float). Kẹp an toàn ở frame cuối nếu vượt phạm vi
        (phòng sai số dấu phẩy động đẩy index vượt `len(frames)-1`)."""
        idx = int(self.current_frame)
        if idx >= len(self.frames):
            idx = len(self.frames) - 1
        return self.frames[idx]

    def reset(self):
        """Quay animation về frame 0, xoá cờ `finished` — dùng khi TÁI SỬ
        DỤNG cùng 1 Animation object cho nhiều lần phát (vd tháp bắn lặp
        lại hiệu ứng cùng loại nhiều lần thay vì tạo Animation mới mỗi lần)."""
        self.current_frame = 0.0
        self.finished = False


class TransientEffect(Entity):
    """
    An entity that plays an animation at a specific location and dies when it finishes.
    """
    def __init__(self, x: float, y: float, animation: Animation, angle: float = 0):
        """Tạo hiệu ứng 1-lần tại (x,y) CỐ ĐỊNH (không đi theo target nào —
        khác `AttachedStatusVFX`). `animation` PHẢI có `loop=False` để
        `update()` phát hiện `finished` và tự huỷ entity; nếu truyền
        animation loop=True, hiệu ứng sẽ TỒN TẠI MÃI MÃI (rò rỉ entity).
        `angle` — góc xoay tĩnh áp lên mọi frame (vd hiệu ứng nổ hướng theo
        chiều đạn bay)."""
        super().__init__(x, y)
        self.animation = animation
        self.angle = angle

    def update(self, dt: float):
        """Tiến animation; animation báo `finished` (đã phát hết, không
        loop) → đánh dấu `is_alive=False` để WorldQuery dọn khỏi map."""
        self.animation.update(dt)
        if self.animation.finished:
            self.is_alive = False

    def draw(self, screen):
        """Vẽ frame hiện tại, xoay theo `angle` nếu khác 0, CĂN GIỮA tại
        (x,y) (không phải neo góc trên-trái — khác quy ước building/trap)."""
        frame = self.animation.get_current_frame()
        if self.angle != 0:
            frame = pygame.transform.rotate(frame, self.angle)
        rect = frame.get_rect(center=(self.x, self.y))
        screen.blit(frame, rect.topleft)

# --- Asset Loader Helper ---
_cache = {}

def load_animation_strip(path, num_frames, fps=30, loop=True, loop_start_frame=0):
    """Nạp 1 dải sprite NGANG (1 hàng, `num_frames` cột) từ `path`, cache
    theo key `(path, num_frames)` — gọi nhiều lần với cùng path/num_frames
    KHÔNG đọc lại đĩa/cắt lại ảnh, chỉ tái sử dụng list Surface đã cắt (bản
    thân frame Surface được CHIA SẺ giữa các Animation instance khác nhau —
    an toàn vì Animation không sửa nội dung Surface, chỉ đọc). Trả về 1
    `Animation` MỚI mỗi lần gọi (state phát — `current_frame`/`finished` —
    không chia sẻ, chỉ frame data chia sẻ)."""
    if (path, num_frames) not in _cache:
        sheet = SpriteSheet(path)
        w = sheet.sheet.get_width() // num_frames
        h = sheet.sheet.get_height()
        frames = sheet.load_strip((0, 0, w, h), num_frames)
        _cache[(path, num_frames)] = frames
    else:
        frames = _cache[(path, num_frames)]
    return Animation(frames, fps, loop, loop_start_frame)


def load_spritesheet(path, cols, rows, fps=30, loop=True, loop_start_frame=0):
    """Load tất cả frames từ một bảng sprite nhiều hàng (cols x rows)."""
    cache_key = (path, cols, rows)
    if cache_key not in _cache:
        sheet_obj = SpriteSheet(path)
        img = sheet_obj.sheet
        fw = img.get_width() // cols
        fh = img.get_height() // rows
        frames = []
        for row in range(rows):
            for col in range(cols):
                rect = (col * fw, row * fh, fw, fh)
                frames.append(sheet_obj.image_at(rect))
        _cache[cache_key] = frames
    else:
        frames = _cache[cache_key]
    return Animation(frames, fps, loop, loop_start_frame)



class AttachedStatusVFX(Entity):
    """
    Hiệu ứng dính liền với một target (ví dụ: bị đóng băng, bị bốc cháy).
    Hiệu ứng sẽ đi theo x, y của target.
    Quản lý 3 trạng thái: start -> active (hold frame cuối) -> end.
    """
    def __init__(self, target, anim_start, anim_active, anim_end, total_duration, scale=1.0):
        """Tạo hiệu ứng dính vào `target` (vd titan bị đóng băng/cháy),
        theo chuỗi 3 pha: `anim_start` (bắt đầu, chạy 1 lần) → `anim_active`
        (giữ nguyên, LẶP LẠI HOẶC giữ frame cuối — PHẢI tự đặt `loop=False`
        ở nơi tạo animation này nếu muốn giữ nguyên 1 frame, class này
        không ép buộc) → `anim_end` (kết thúc, chạy 1 lần rồi tự huỷ).

        `total_duration` — TỔNG thời lượng hiệu ứng tính từ lúc tạo tới
        lúc bắt đầu pha 'end' được kích hoạt SỚM HƠN để `anim_end` VỪA ĐỦ
        chạy xong đúng lúc `total_duration` kết thúc (xem `end_duration`
        tính từ số frame/fps của `anim_end`, dùng ở `update()` để quyết
        định thời điểm chuyển 'active'→'end'). `scale` — hệ số phóng to
        frame khi vẽ (không ảnh hưởng hitbox, chỉ hiển thị).
        """
        super().__init__(target.x, target.y)
        self.target = target
        self.anim_start = anim_start
        self.anim_active = anim_active
        self.anim_end = anim_end
        self.scale = scale
        
        self.total_duration = total_duration
        self.elapsed = 0.0
        
        self.state = "start"
        
        # Tính thời gian cần để chạy xong anim_end
        self.end_duration = len(self.anim_end.frames) / self.anim_end.fps

    def update(self, dt: float):
        """State machine 3 pha 'start'→'active'→'end':

        Trước hết, target CHẾT → hiệu ứng biến mất NGAY LẬP TỨC (không chờ
        chạy hết `anim_end`) — tránh hiệu ứng "mồ côi" lơ lửng trên xác
        titan đã bị dọn khỏi map. Ngược lại, đồng bộ vị trí theo target
        MỖI FRAME (`self.x, self.y = target.x, target.y`) — đây là cơ chế
        "dính" duy nhất, không dùng parent-child transform nào khác.

        Tính `time_left` = thời gian còn lại tới `total_duration`; nếu
        đang ở 'start'/'active' MÀ thời gian còn lại ≤ `end_duration` (đủ
        đúng để `anim_end` chạy hết) → CHUYỂN NGAY sang 'end', BẤT KỂ
        'start'/'active' đã chạy xong animation của nó hay chưa (cắt
        ngang nếu cần, ưu tiên hiệu ứng kết thúc đúng lúc `total_duration`
        hơn là để 'active' chạy trọn).

        Trong mỗi pha, chỉ animation CỦA PHA ĐÓ được `update()`. 'start'
        xong (`anim_start.finished`) → tự chuyển 'active'. 'end' xong
        (`anim_end.finished`) → `is_alive=False` (kết thúc vòng đời).
        """
        if not self.target.is_alive:
            self.is_alive = False
            return

        self.x, self.y = self.target.x, self.target.y
        self.elapsed += dt

        # Nếu đã đến lúc chạy End
        time_left = self.total_duration - self.elapsed
        if self.state in ["start", "active"] and time_left <= self.end_duration:
            self.state = "end"

        if self.state == "start":
            self.anim_start.update(dt)
            if self.anim_start.finished:
                self.state = "active"
                
        elif self.state == "active":
            self.anim_active.update(dt)
            # Lưu ý: anim_active nên được thiết lập loop=False để dừng ở frame cuối
            
        elif self.state == "end":
            self.anim_end.update(dt)
            if self.anim_end.finished:
                self.is_alive = False

    def _foot_y(self) -> float:
        """Y tại CHÂN target — lệch xuống ~chân (anchor ở tâm thân), nhích lên xí."""
        t = self.target
        if hasattr(t, '_DISPLAY_SIZE'):
            off = t._DISPLAY_SIZE * 0.38
        elif hasattr(t, '_FRAME_SIZE'):
            off = t._FRAME_SIZE * 0.38
        else:
            off = 34.0
        return self.y + off

    def draw(self, screen):
        """Chọn frame theo pha hiện tại, scale nếu `scale != 1.0`, vẽ CĂN
        GIỮA THEO TRỤC X tại `self.x` nhưng theo Y tại `_foot_y()` (chân
        target, không phải tâm) — hiệu ứng trạng thái (băng/lửa) trông tự
        nhiên hơn khi bám dưới chân thay vì giữa thân titan."""
        frame = None
        if self.state == "start":
            frame = self.anim_start.get_current_frame()
        elif self.state == "active":
            frame = self.anim_active.get_current_frame()
        elif self.state == "end":
            frame = self.anim_end.get_current_frame()

        if frame:
            if self.scale != 1.0:
                w, h = frame.get_size()
                frame = pygame.transform.scale(frame, (int(w * self.scale), int(h * self.scale)))
            # Vẽ ngay dưới CHÂN target (lệch xuống theo nửa chiều cao sprite titan)
            rect = frame.get_rect(center=(self.x, self._foot_y()))
            screen.blit(frame, rect.topleft)
