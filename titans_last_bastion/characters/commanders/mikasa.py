# characters/commanders/mikasa.py — MikasaCommander, unlocked at Stage 2.
#
# Uses sprite pack: Knight 2D Pixel Art, with_outline variant (96×84 frames per strip).
# Skills inherit Commander defaults. Character-specific tuning goes here later.
import os
from characters.commanders.commander import Commander
from characters.commanders.assets_config import (
    FRAME_HEIGHT_MIKASA,
    FRAME_WIDTH_MIKASA,
    MIKASA_SPRITE_FRAMES,
)

_SPRITES_DIR = os.path.join(os.path.dirname(__file__), "sprites", "Mikasa")


class MikasaCommander(Commander):
    """Tướng Mikasa Ackerman — mở khoá ở Màn 2."""

    NAME = "Mikasa Ackerman"
    STAGE = 2

    SPRITE_FOLDER = _SPRITES_DIR
    SPRITE_FRAMES = MIKASA_SPRITE_FRAMES
    FRAME_WIDTH = FRAME_WIDTH_MIKASA
    FRAME_HEIGHT = FRAME_HEIGHT_MIKASA

    SKILL_COOLDOWNS = {"Q": 5.0, "E": 8.0, "R": 30.0}

    def _activate_skill(self, skill_id: str) -> None:
        if skill_id == "Q":
            self._slash_combo()
        elif skill_id == "E":
            self.begin_aim()
        elif skill_id == "R":
            self._titan_form()
