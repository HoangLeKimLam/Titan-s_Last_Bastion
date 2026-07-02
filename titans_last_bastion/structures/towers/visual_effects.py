import pygame
import os
from core.entity import Entity

class SpriteSheet:
    def __init__(self, filename):
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
    def __init__(self, frames, fps=30, loop=True, loop_start_frame=0):
        self.frames = frames
        self.fps = fps
        self.loop = loop
        self.loop_start_frame = loop_start_frame
        self.current_frame = 0.0
        self.finished = False

    def update(self, dt):
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
        idx = int(self.current_frame)
        if idx >= len(self.frames):
            idx = len(self.frames) - 1
        return self.frames[idx]

    def reset(self):
        self.current_frame = 0.0
        self.finished = False


class TransientEffect(Entity):
    """
    An entity that plays an animation at a specific location and dies when it finishes.
    """
    def __init__(self, x: float, y: float, animation: Animation, angle: float = 0):
        super().__init__(x, y)
        self.animation = animation
        self.angle = angle

    def update(self, dt: float):
        self.animation.update(dt)
        if self.animation.finished:
            self.is_alive = False

    def draw(self, screen):
        frame = self.animation.get_current_frame()
        if self.angle != 0:
            frame = pygame.transform.rotate(frame, self.angle)
        rect = frame.get_rect(center=(self.x, self.y))
        screen.blit(frame, rect.topleft)

# --- Asset Loader Helper ---
_cache = {}

def load_animation_strip(path, num_frames, fps=30, loop=True, loop_start_frame=0):
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
