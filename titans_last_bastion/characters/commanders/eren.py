# characters/commanders/eren.py — ErenCommander, unlocked at Stage 1.
#
# Uses sprite pack: Knight_player_1.4 (100×64 frames per strip).
# All 3 skills use the default implementations from Commander base.
# Eren is the "template ground-truth" — other commanders may override skills.
import os
from characters.commanders.commander import Commander
from characters.commanders.assets_config import (
    EREN_SPRITE_FRAMES,
    FRAME_HEIGHT_EREN,
    FRAME_WIDTH_EREN,
)

_SPRITES_DIR = os.path.join(os.path.dirname(__file__), "sprites", "Eren")


class ErenCommander(Commander):
    """Tướng Eren Yeager — mở khoá ở Màn 1."""

    NAME = "Eren Yeager"
    STAGE = 1

    SPRITE_FOLDER = _SPRITES_DIR
    SPRITE_FRAMES = EREN_SPRITE_FRAMES
    FRAME_WIDTH = FRAME_WIDTH_EREN
    FRAME_HEIGHT = FRAME_HEIGHT_EREN

    SKILL_COOLDOWNS = {"Q": 5.0, "E": 8.0, "R": 30.0}

    def _activate_skill(self, skill_id: str) -> None:
        """E is driven by main.py directly; routed here only as a safe fallback."""
        if skill_id == "Q":
            self._slash_combo()
        elif skill_id == "E":
            self.begin_aim()
        elif skill_id == "R":
            self._titan_form()
