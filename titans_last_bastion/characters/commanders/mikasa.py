# characters/commanders/mikasa.py — MikasaCommander, unlocked at Stage 1.
#
# Uses sprite pack: Knight_player_1.4 (100×64 frames per strip).
# All 3 skills use the default implementations from Commander base.
# Mikasa is the "template ground-truth" — other commanders may override skills.
import os
from characters.commanders.commander import Commander
from config import balance
from characters.commanders.assets_config import (
    MIKASA_SPRITE_FRAMES,
    FRAME_HEIGHT_MIKASA,
    FRAME_WIDTH_MIKASA,
)

_SPRITES_DIR = os.path.join(os.path.dirname(__file__), "sprites", "Mikasa")


class MikasaCommander(Commander):
    """Tướng Mikasa Ackerman — mở khoá ở Màn 1."""

    NAME = "Mikasa Ackerman"
    STAGE = 1

    SPRITE_FOLDER = _SPRITES_DIR
    SPRITE_FRAMES = MIKASA_SPRITE_FRAMES
    FRAME_WIDTH = FRAME_WIDTH_MIKASA
    FRAME_HEIGHT = FRAME_HEIGHT_MIKASA

    SKILL_COOLDOWNS = balance.MIKASA_SKILL_COOLDOWNS

    # Cấp yêu cầu để dùng skill — chỉnh ở đây nếu cần cân bằng lại.
    SKILL_UNLOCK_LEVEL = balance.MIKASA_SKILL_UNLOCK_LEVEL

    def _activate_skill(self, skill_id: str) -> None:
        """E is driven by main.py directly; routed here only as a safe fallback."""
        if skill_id == "Q":
            self._slash_combo()
        elif skill_id == "E":
            self.begin_aim()
        elif skill_id == "R":
            self._titan_form()
