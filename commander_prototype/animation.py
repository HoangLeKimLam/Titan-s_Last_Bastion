"""animation.py — sprite loader + per-commander state-machine animator.

Two source layouts are supported per state:

    STRIP  mode (Eren, Mikasa):
        {"file": "Idle_KG_1.png", "fps": 6, "loop": True}
        — one PNG containing N frames laid horizontally, each `frame_width`
          wide × `frame_height` tall.

    FOLDER mode (Warrior/Armin):
        {"folder": "idle", "prefix": "Warrior_Idle_", "count": 6,
         "fps": 6, "loop": True}
        — N individual PNGs in `sprite_folder/<folder>/<prefix><i>.png`
          where i = 1..count. Each PNG IS one frame; widths may vary
          between files (e.g. Attack 64 vs Dash 69).

Character-size normalisation:
    All packs share a `target_character_height` (default 168 px). The loader
    inspects the IDLE animation's character bounding box, computes
    `scale = target / idle_char_height`, and applies that same scale to
    every frame in the pack. So Eren (idle char 61 px) and Warrior (idle
    char 33 px) both render at ~168 px standing height.

    Frames are vertically cropped to the pack's VERTICAL envelope (union
    of bbox.y..bbox.y+bbox.height across every frame in every clip) so
    raised-arm attack frames aren't clipped. Per-frame widths are
    preserved so packs with variable frame widths still render correctly.

Headless mode (used by tests) skips disk I/O entirely; clips are created
with empty frame lists so set_state() / clip_duration() stay safe.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import pygame

from assets_config import NEXT_STATE_AFTER_ONESHOT, SPRITE_SCALE

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
        return 1.0 / self.fps if self.fps > 0 else 1.0


def _display_ready() -> bool:
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
    """Compute (env_top, env_bottom, idle_top, idle_bottom) across pack.

    env_*  = union across every frame in every clip — used to crop padding
    idle_* = union within idle clip only — used to compute uniform scale
    """
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
    """Load every state in `sprite_frames`; return dict[state, AnimationClip].

    If `target_character_height` is set, scale is computed automatically from
    the IDLE character's bbox so every pack ends up at the same standing
    height. Each frame is vertically cropped to the pack's envelope so
    attack/jump silhouettes that extend past idle aren't clipped.

    `headless=True` skips all disk I/O — clips are created with empty frame
    lists so set_state() never KeyErrors.
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
    #    Per-frame width is preserved (handles Warrior's 64-vs-69 variance).
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
    """State-machine animator owned by a Commander (HAS-A composition)."""

    def __init__(self, clips: dict, initial_state: str = "idle"):
        self._clips = clips
        self._state = initial_state
        self._frame_index = 0
        self._timer = 0.0
        self._facing_right = True

    @property
    def state(self) -> str:
        return self._state

    @property
    def facing_right(self) -> bool:
        return self._facing_right

    def set_facing(self, facing_right: bool) -> None:
        self._facing_right = bool(facing_right)

    def clip_duration(self, state: str) -> float:
        clip = self._clips.get(state)
        if clip is None or not clip.frames or clip.fps <= 0:
            return 0.0
        return len(clip.frames) / clip.fps

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        if state not in self._clips:
            logger.warning("Unknown animation state: %s", state)
            return
        self._state = state
        self._frame_index = 0
        self._timer = 0.0

    def update(self, dt: float) -> None:
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
        clip = self._clips.get(self._state)
        if clip is None or not clip.frames:
            return None
        idx = min(self._frame_index, len(clip.frames) - 1)
        frame = clip.frames[idx]
        if not self._facing_right:
            frame = pygame.transform.flip(frame, True, False)
        return frame
