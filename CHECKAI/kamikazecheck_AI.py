"""kamikazecheck_AI.py — Demo AI tự hành của Kamikaze.

KamikazeAI (AI.py) tự hành theo KamikazePriority — "bom tự sát":
  • Phát hiện Soldier trong 300px → lao vào cụm đông nhất (clustering).
  • Vào 80px → pause 1.5s → nổ AoE.
  • Không còn lính → đi về HQ theo Priority.

KamikazeAI tái dùng `Kamikaze.ai_tick()` có sẵn để xử lý clustering +
di chuyển + kích nổ — minh họa "AI tái dùng hành vi của class titan".

Quan sát:
  • Titan chạy thẳng vào cụm lính rồi tự nổ (HUD state → SKILL/DEAD).
  • Bấm SPACE thêm lính để xem clustering chọn cụm mới.
"""
import os

import _ai_bootstrap  # noqa: F401
import pygame
from _ai_app import AICheckApp
from Titan import Kamikaze

try:
    from PIL import Image as _PILImage
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


def _load_gif_frames(path: str) -> list[pygame.Surface]:
    """Load animated GIF thành danh sách pygame.Surface (RGBA).

    Dùng Pillow để đọc từng frame, chuyển sang RGBA, rồi tạo Surface.
    Nếu Pillow chưa cài → trả list rỗng (không crash, chỉ không vẽ).
    """
    if not _PIL_OK:
        return []
    frames: list[pygame.Surface] = []
    try:
        gif = _PILImage.open(path)
        for i in range(gif.n_frames):
            gif.seek(i)
            rgba = gif.convert('RGBA')
            w, h = rgba.size
            raw  = rgba.tobytes()
            surf = pygame.image.fromstring(raw, (w, h), 'RGBA').convert_alpha()
            frames.append(surf)
    except Exception:
        pass
    return frames


# ── Đường dẫn GIF ────────────────────────────────────────────────
_GIF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),   # lùi về root
    'Assets', 'Explosion Kamikaze', 'explode.gif',
)

# Tốc độ phát animation nổ — 12 frame / 0.6s ≈ 20 FPS
_EXPLODE_FPS  = 20.0
_EXPLODE_LOOP = False   # phát 1 lần rồi đứng frame cuối


class KamikazeAICheck(AICheckApp):
    """Demo AI cho Kamikaze — dùng layout chung (4 Wall bao HQ).

    Clustering vẫn quan sát được vì layout chung đã có 3 Soldier + 1 Commander.
    Bấm SPACE để thêm Soldier ngẫu nhiên, dễ thấy Kamikaze chọn cụm đông.

    Thêm: khi Kamikaze nổ, phát GIF explode.gif tại tâm vụ nổ.
    """

    def __init__(self) -> None:
        # Khởi tạo state explosion TRƯỚC super().__init__() vì super gọi
        # _build_scene() → _update() có thể chạy trước khi ta set attribute.
        self._explode_frames: list[pygame.Surface] = []
        self._explode_frame_idx: float = 0.0
        self._explode_playing: bool    = False
        self._explode_x: float         = 0.0
        self._explode_y: float         = 0.0

        super().__init__()

        # Load GIF frames sau khi pygame đã init (pygame.image cần display).
        self._explode_frames = _load_gif_frames(_GIF_PATH)

    def create_titan(self):
        return Kamikaze(self.spawn_x, self.spawn_y, {
            'hp': 300, 'speed': 80.0, 'damage': 50,
        })

    def title(self) -> str:
        return "Kamikaze AI  —  lao vào cụm lính rồi tự nổ"

    def describe_titan(self) -> list:
        t = self.titan
        exploded = getattr(t, '_has_exploded', False)
        pausing  = getattr(t, '_is_pausing', False)
        if exploded:
            phase = 'ĐÃ NỔ'
        elif pausing:
            phase = 'PAUSE trước nổ'
        else:
            phase = 'đang săn lính'
        return [f"Phase   : {phase}"]

    # ── Override để chèn explosion GIF ──────────────────────────────

    def _build_scene(self) -> None:
        """Reset cả trạng thái explosion GIF khi respawn."""
        super()._build_scene()
        self._explode_frame_idx = 0.0
        self._explode_playing   = False

    def _update(self, dt: float) -> None:
        """Thêm tick explosion GIF vào sau update chuẩn."""
        # Phát hiện thời điểm titan vừa nổ → bắt đầu phát GIF.
        just_exploded = (
            not self._explode_playing
            and getattr(self.titan, '_has_exploded', False)
        )
        if just_exploded and self._explode_frames:
            self._explode_playing   = True
            self._explode_frame_idx = 0.0
            self._explode_x         = self.titan.x
            self._explode_y         = self.titan.y

        # Tick frame index.
        if self._explode_playing:
            self._explode_frame_idx += _EXPLODE_FPS * dt
            max_idx = len(self._explode_frames) - 1
            if self._explode_frame_idx > max_idx:
                if _EXPLODE_LOOP:
                    self._explode_frame_idx %= len(self._explode_frames)
                else:
                    self._explode_frame_idx = float(max_idx)  # đứng frame cuối

        super()._update(dt)

    def _draw_titan(self) -> None:
        """Vẽ titan bình thường; khi đã nổ thì vẽ GIF explosion thay thế."""
        super()._draw_titan()   # HP bar ẩn tự động trong _ai_app.py

        if self._explode_playing and self._explode_frames:
            idx  = int(self._explode_frame_idx)
            idx  = max(0, min(idx, len(self._explode_frames) - 1))
            surf = self._explode_frames[idx]
            w, h = surf.get_size()
            # Scale lên cho dễ thấy (80x48 → 160x96).
            scaled = pygame.transform.scale(surf, (w * 2, h * 2))
            sw, sh = scaled.get_size()
            bx = int(self._explode_x - sw // 2)
            by = int(self._explode_y - sh // 2)
            self.screen.blit(scaled, (bx, by))


if __name__ == '__main__':
    KamikazeAICheck().run()
