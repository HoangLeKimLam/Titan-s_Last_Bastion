# characters/soldiers/animation.py
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import pygame

from characters.soldiers.assets_config import NEXT_STATE_AFTER_ONESHOT, SPRITE_SCALE

logger = logging.getLogger(__name__)


@dataclass
class AnimationClip:
    """One animation = list of frames + fps + loop flag."""

    name: str
    frames: list = field(default_factory=list)
    fps: float = 8.0
    loop: bool = True

    @property
    def frame_duration(self) -> float:
        """Số giây MỖI FRAME phải hiện (nghịch đảo fps). fps<=0 → 1.0s (fallback an toàn)."""
        return 1.0 / self.fps if self.fps > 0 else 1.0


def _display_ready() -> bool:
    """True nếu pygame ĐÃ có display thật (không phải headless) — quyết định có
    dùng `convert_alpha()` an toàn hay không."""
    return pygame.display.get_init() and pygame.display.get_surface() is not None


def _maybe_convert(surface: "pygame.Surface") -> "pygame.Surface":
    """convert_alpha() only when a display is up — keeps headless tests safe."""
    if _display_ready():
        try:
            return surface.convert_alpha()
        except pygame.error:
            return surface
    return surface


# ---------------------------------------------------------------------------
# Raw-frame loading (mode-agnostic)
# ---------------------------------------------------------------------------

def _load_strip_frames(strip: "pygame.Surface",
                       frame_w: int, frame_h: int) -> list:
    """Slice a horizontal strip into individual frame Surfaces."""
    frames = []
    fh = min(frame_h, strip.get_height())
    n = strip.get_width() // frame_w
    for i in range(n):
        try:
            frames.append(
                strip.subsurface(pygame.Rect(i * frame_w, 0, frame_w, fh)).copy()
            )
        except ValueError:
            pass
    return frames


def _load_raw_frames(sprite_folder: str, spec: dict,
                     frame_w: int, frame_h: int) -> list:
    """Return raw (unscaled, uncropped) frame surfaces for one state spec.

    Dispatches on whether spec uses 'file' (strip mode) or 'folder' (per-frame).
    """
    if "folder" in spec:
        sub = os.path.join(sprite_folder, spec["folder"])
        if not os.path.isdir(sub):
            logger.warning("Sprite folder missing: %s", sub)
            return []
        prefix = spec.get("prefix", "")
        count = int(spec.get("count", 0))
        frames = []
        for i in range(1, count + 1):
            path = os.path.join(sub, f"{prefix}{i}.png")
            if not os.path.exists(path):
                logger.warning("Sprite frame missing: %s", path)
                continue
            try:
                frames.append(pygame.image.load(path))
            except pygame.error as exc:
                logger.warning("Failed to load %s: %s", path, exc)
        return frames

    if "file" in spec:
        path = os.path.join(sprite_folder, spec["file"])
        if not os.path.exists(path):
            logger.warning("Sprite strip missing: %s", path)
            return []
        try:
            strip = pygame.image.load(path)
        except pygame.error as exc:
            logger.warning("Failed to load %s: %s", path, exc)
            return []
        return _load_strip_frames(strip, frame_w, frame_h)

    return []


# ---------------------------------------------------------------------------
# Bbox helpers (vertical-only — works with variable frame widths)
# ---------------------------------------------------------------------------

def _vertical_extent(frame: "pygame.Surface"):
    """Return (top, bottom) y-range of non-transparent pixels, or None."""
    bbox = frame.get_bounding_rect(min_alpha=1)
    if bbox.height <= 0:
        return None
    return bbox.y, bbox.y + bbox.height


def _envelope_and_idle(raw_by_state: dict, idle_state: str = "idle"):
    """Compute (env_top, env_bottom, idle_top, idle_bottom) across pack."""
    env_top, env_bot = None, None
    idle_top, idle_bot = None, None
    for state, frames in raw_by_state.items():
        for f in frames:
            v = _vertical_extent(f)
            if v is None:
                continue
            t, b = v
            env_top = t if env_top is None else min(env_top, t)
            env_bot = b if env_bot is None else max(env_bot, b)
            if state == idle_state:
                idle_top = t if idle_top is None else min(idle_top, t)
                idle_bot = b if idle_bot is None else max(idle_bot, b)
    return env_top, env_bot, idle_top, idle_bot


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

def load_clips(sprite_folder: str, sprite_frames: dict, *,
               frame_width: int = 100, frame_height: int = 64,
               target_character_height: int = None,
               scale: float = None, headless: bool = False) -> dict:
    """Nạp TOÀN BỘ animation của 1 nhân vật (mọi state trong `sprite_frames`),
    tự tính SCALE để mọi bộ sprite khác nhau kích thước ĐỀU CAO BẰNG NHAU lúc đứng yên.

    Đây là loader DÙNG CHUNG cho cả Commander (Mikasa/Eren) VÀ Soldier
    (Warrior/Archer/Lancer) — mỗi bộ sprite gốc có kích thước khung khác nhau
    (100×64, 96×84, 192×192...), nhưng người chơi cần MỌI nhân vật hiển thị ở
    TỈ LỆ TƯƠNG ĐỐI hợp lý trên màn hình.

    Thuật toán (5 bước):
      1. Nạp RAW frame cho mọi state (`_load_raw_frames`) — chưa crop, chưa scale.
      2. Tính "envelope" (`_envelope_and_idle`): vùng pixel KHÔNG TRONG SUỐT bao
         trùm MỌI frame của MỌI state (dùng để crop margin trong suốt thừa), và
         RIÊNG chiều cao NHÂN VẬT LÚC ĐỨNG YÊN (chỉ từ state "idle").
      3. **Tự tính scale** (nếu `target_character_height` được truyền và chưa có
         `scale` cứng): `scale = target_height / idle_height` — vd nhân vật idle
         cao 64px thật trong ảnh, muốn hiển thị 42px trên màn hình → scale ≈0.66.
         Đây LÀ LÝ DO mọi commander/soldier trông cân đối dù ảnh gốc khác cỡ.
         Không truyền gì → dùng `SPRITE_SCALE` mặc định từ assets_config.py.
      4. Với mỗi frame: CROP theo envelope (bỏ margin trong suốt thừa TRÊN/DƯỚI,
         giữ NGUYÊN chiều rộng — envelope chỉ tính theo trục dọc), rồi SCALE đều.
      5. `_maybe_convert()` mỗi frame (convert_alpha nếu có display thật).

    `headless=True` HOẶC `sprite_folder` rỗng → BỎ QUA MỌI I/O ĐĨA, trả clip với
    `frames=[]` cho MỌI state — để `set_state()` không bao giờ KeyError dù chạy
    test không có display/asset.

    Tham số:
        sprite_folder: thư mục chứa file ảnh của nhân vật.
        sprite_frames: dict {state: {'file'/'folder':..., 'fps':..., 'loop':...}}.
        frame_width/frame_height: kích thước 1 frame TRONG sheet gốc (chế độ strip).
        target_character_height: chiều cao MONG MUỐN khi hiển thị (px). None → dùng `scale`.
        scale: hệ số scale CỐ ĐỊNH, ghi đè tự tính. None → tự tính hoặc SPRITE_SCALE.
        headless: bỏ qua I/O đĩa (test/CI).

    Trả về: dict {state_name: AnimationClip}.
    """
    if headless or not sprite_folder:
        return {
            state: AnimationClip(
                name=state, frames=[],
                fps=float(spec.get("fps", 8)),
                loop=bool(spec.get("loop", True)),
            )
            for state, spec in sprite_frames.items()
        }

    # 1) Load raw frames per state
    raw_by_state = {
        state: _load_raw_frames(sprite_folder, spec, frame_width, frame_height)
        for state, spec in sprite_frames.items()
    }

    # 2) Compute envelope (for crop) + idle char height (for scale)
    env_top, env_bot, idle_top, idle_bot = _envelope_and_idle(raw_by_state)

    if (scale is None and target_character_height is not None
            and idle_top is not None and idle_bot > idle_top):
        idle_h = idle_bot - idle_top
        scale = target_character_height / idle_h
        logger.info(
            "Pack '%s': idle char height=%d  envelope_y=%d..%d  "
            "scale=%.3f → idle renders at %d px",
            os.path.basename(sprite_folder),
            idle_h, env_top or 0, env_bot or 0, scale,
            int(round(idle_h * scale)),
        )
    if scale is None:
        scale = SPRITE_SCALE

    # 3) Build final clips: vertical-crop to envelope, then uniform scale.
    clips = {}
    for state, spec in sprite_frames.items():
        out_frames = []
        for f in raw_by_state[state]:
            fw, fh = f.get_size()
            cropped = f
            if env_top is not None and env_bot is not None:
                top = max(0, env_top)
                bot = min(fh, env_bot)
                if bot > top and (top > 0 or bot < fh):
                    try:
                        cropped = f.subsurface(
                            pygame.Rect(0, top, fw, bot - top)
                        ).copy()
                    except ValueError:
                        cropped = f
            if scale != 1.0:
                w, h = cropped.get_size()
                cropped = pygame.transform.scale(
                    cropped, (int(round(w * scale)), int(round(h * scale)))
                )
            out_frames.append(_maybe_convert(cropped))
        clips[state] = AnimationClip(
            name=state,
            frames=out_frames,
            fps=float(spec.get("fps", 8)),
            loop=bool(spec.get("loop", True)),
        )
    return clips


# ---------------------------------------------------------------------------
# Animator
# ---------------------------------------------------------------------------

class CommanderAnimator:
    """State-machine animator owned by a Soldier or Commander (HAS-A composition)."""

    def __init__(self, clips: dict, initial_state: str = "idle"):
        """Gắn animator với bộ `clips` đã nạp (từ `load_clips`), bắt đầu ở `initial_state`.

        Tham số: clips — dict {state: AnimationClip}; initial_state — state đầu.
        """
        self._clips = clips
        self._state = initial_state
        self._frame_index = 0
        self._timer = 0.0
        self._facing_right = True

    @property
    def state(self) -> str:
        """Tên state animation hiện tại (vd 'idle', 'attack1', 'walk')."""
        return self._state

    @property
    def facing_right(self) -> bool:
        """True nếu nhân vật đang QUAY MẶT sang phải — `current_frame()` tự lật
        ảnh trái/phải dựa trên cờ này (KHÔNG cần 2 bộ sprite riêng theo hướng)."""
        return self._facing_right

    def set_facing(self, facing_right: bool) -> None:
        """Đặt hướng quay mặt — gọi mỗi khi nhân vật di chuyển ngang có ý nghĩa."""
        self._facing_right = bool(facing_right)

    def clip_duration(self, state: str) -> float:
        """Tổng thời lượng (giây) của 1 clip = số frame / fps.

        State không tồn tại, không có frame, hoặc fps<=0 → trả 0.0 (an toàn,
        không chia 0). Dùng bởi caller để biết animation "gồng đòn" kéo dài bao lâu
        (vd `Commander.basic_attack()` đặt `_combo_anim_total` từ giá trị này).
        """
        clip = self._clips.get(state)
        if clip is None or not clip.frames or clip.fps <= 0:
            return 0.0
        return len(clip.frames) / clip.fps

    def set_state(self, state: str) -> None:
        """Chuyển sang animation state MỚI — reset frame về 0, bỏ qua nếu ĐANG Ở state đó.

        Thuật toán:
          1. `state == _state` hiện tại → không làm gì (tránh giật animation khi
             gọi `set_state("walk")` liên tục mỗi frame trong khi đang walk).
          2. `state` không tồn tại trong `_clips` → log warning, KHÔNG đổi state
             (an toàn hơn crash — animation cũ tiếp tục chạy).
          3. Đổi state hợp lệ → reset `_frame_index`/`_timer` về 0 (animation mới
             LUÔN bắt đầu từ frame đầu).
        """
        if state == self._state:
            return
        if state not in self._clips:
            logger.warning("Unknown animation state: %s", state)
            return
        self._state = state
        self._frame_index = 0
        self._timer = 0.0

    def update(self, dt: float) -> None:
        """Tiến animation 1 frame theo thời gian thật, tự chuyển state khi hết animation MỘT LẦN.

        Thuật toán:
          1. Clip hiện tại không tồn tại/không có frame → không làm gì.
          2. Tích luỹ `_timer += dt`; vòng `while _timer >= frame_duration` (WHILE
             để bù frame nếu dt lớn do lag, giống `ai.py::_step_col`) → tăng
             `_frame_index`.
          3. Hết frame (`_frame_index >= len(frames)`):
             - `clip.loop == True` → quay về frame 0 (lặp vô tận, vd "idle"/"walk").
             - `loop == False` (animation MỘT LẦN, vd "attack"/"hurt"): giữ ở
               FRAME CUỐI, rồi TỰ ĐỘNG chuyển sang `NEXT_STATE_AFTER_ONESHOT`
               (thường là "idle") — TRỪ KHI đang ở state "dying" (chết thì đứng
               yên ở frame chết cuối cùng, không tự quay lại "idle").

        Chỉ số fps/loop: khai trong `sprite_frames` (assets_config.py) của mỗi nhân vật.
        """
        clip = self._clips.get(self._state)
        if clip is None or not clip.frames:
            return
        self._timer += dt
        while self._timer >= clip.frame_duration:
            self._timer -= clip.frame_duration
            self._frame_index += 1
            if self._frame_index >= len(clip.frames):
                if clip.loop:
                    self._frame_index = 0
                else:
                    self._frame_index = len(clip.frames) - 1
                    if self._state != "dying":
                        self.set_state(NEXT_STATE_AFTER_ONESHOT)
                    return

    def current_frame(self) -> Optional["pygame.Surface"]:
        """Trả Surface của frame HIỆN TẠI, tự LẬT ẢNH nếu đang quay mặt trái.

        `idx` kẹp trần `len(frames)-1` (phòng frame_index vượt do timing hiếm
        gặp). `facing_right=False` → `pygame.transform.flip(frame, True, False)`
        MỖI LẦN GỌI (không cache lật sẵn) — đơn giản, chấp nhận chi phí lật lại
        mỗi frame vẽ.

        Trả về: Surface, hoặc None nếu state không có frame nào (caller tự fallback vẽ hình khác).
        """
        clip = self._clips.get(self._state)
        if clip is None or not clip.frames:
            return None
        idx = min(self._frame_index, len(clip.frames) - 1)
        frame = clip.frames[idx]
        if not self._facing_right:
            frame = pygame.transform.flip(frame, True, False)
        return frame
