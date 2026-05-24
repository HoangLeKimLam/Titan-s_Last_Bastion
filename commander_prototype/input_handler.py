"""input_handler.py — translate keyboard input to commander actions.

WASD       → continuous movement direction (normalized vector)
Q / R      → edge-triggered skill activation (one fire per key press)
E          → NOT in SKILL_KEYS — handled directly by main.py event loop
              because it toggles between aim/confirm (begin_aim/confirm_swing).
SPACE      → edge-triggered (cancel E swing session)
LMB        → edge-triggered (basic-attack combo)

Keeping input handling here means Commander stays oblivious to keyboard
state — it only knows about move(destination), use_skill(skill_id), and
the new begin_aim/confirm_swing/cancel_swing trio for E.
"""
from __future__ import annotations

from typing import Optional

import pygame


class PlayerInputHandler:
    """Reads pygame key state each frame; edge-detects skill keys."""

    # E is handled outside this dict — see module docstring.
    SKILL_KEYS: dict = {
        pygame.K_q: "Q",
        pygame.K_r: "R",
    }

    def __init__(self) -> None:
        self._prev_skill_state: dict = {sid: False for sid in self.SKILL_KEYS.values()}
        self._prev_mouse_left: bool = False
        self._prev_space: bool = False

    def movement_vector(self) -> tuple:
        """Return a unit vector (dx, dy) from WASD, or (0, 0) if no key down."""
        keys = pygame.key.get_pressed()
        dx = (1 if keys[pygame.K_d] else 0) - (1 if keys[pygame.K_a] else 0)
        dy = (1 if keys[pygame.K_s] else 0) - (1 if keys[pygame.K_w] else 0)
        if dx == 0 and dy == 0:
            return (0.0, 0.0)
        length = (dx * dx + dy * dy) ** 0.5
        return (dx / length, dy / length)

    def triggered_skill(self) -> Optional[str]:
        """Return 'Q' / 'E' / 'R' on the first frame the key is pressed; else None."""
        keys = pygame.key.get_pressed()
        fired: Optional[str] = None
        for key, sid in self.SKILL_KEYS.items():
            pressed = bool(keys[key])
            was = self._prev_skill_state[sid]
            if pressed and not was and fired is None:
                fired = sid
            self._prev_skill_state[sid] = pressed
        return fired

    def mouse_left_clicked(self) -> bool:
        """True on the first frame the left mouse button is pressed."""
        pressed = bool(pygame.mouse.get_pressed()[0])
        was = self._prev_mouse_left
        self._prev_mouse_left = pressed
        return pressed and not was

    def mouse_position(self) -> tuple:
        """Current mouse cursor position (screen coords)."""
        return pygame.mouse.get_pos()

    def space_pressed(self) -> bool:
        """True on the first frame SPACE is pressed (edge-triggered)."""
        keys = pygame.key.get_pressed()
        pressed = bool(keys[pygame.K_SPACE])
        was = self._prev_space
        self._prev_space = pressed
        return pressed and not was
