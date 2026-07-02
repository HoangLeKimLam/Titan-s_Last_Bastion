# characters/commanders/armin.py — ArminCommander, unlocked at Stage 4.
#
# Uses sprite pack: Warrior (Individual Sprite / folder mode, 69×44 frames).
# Folder structure under sprites/Armin/:
#   idle/          → Warrior_Idle_1.png … Warrior_Idle_6.png
#   Dash/          → Warrior_Dash_1.png … Warrior_Dash_7.png
#   Attack/        → Warrior_Attack_1.png … Warrior_Attack_12.png
#   Dash Attack/   → Warrior_Dash-Attack_1.png … Warrior_Dash-Attack_10.png
#
# State mapping (placeholder states reuse existing folders):
#   idle / walk(Dash) / attack1-3(Attack) / skill_q(Dash Attack) /
#   skill_e(Dash) / skill_r(Attack) / hurt/dying/win(idle)
import os
from characters.commanders.commander import Commander
from characters.commanders.assets_config import (
    ARMIN_SPRITE_FRAMES,
    FRAME_HEIGHT_ARMIN,
    FRAME_WIDTH_ARMIN,
)

_SPRITES_DIR = os.path.join(os.path.dirname(__file__), "sprites", "Armin")


class ArminCommander(Commander):
    """Tướng Armin Arlert — mở khoá ở Màn 4."""

    NAME = "Armin Arlert"
    STAGE = 4

    SPRITE_FOLDER = _SPRITES_DIR
    SPRITE_FRAMES = ARMIN_SPRITE_FRAMES
    FRAME_WIDTH = FRAME_WIDTH_ARMIN
    FRAME_HEIGHT = FRAME_HEIGHT_ARMIN

    SKILL_COOLDOWNS = {"Q": 5.0, "E": 8.0, "R": 30.0}

    def _activate_skill(self, skill_id: str) -> None:
        if skill_id == "Q":
            self._slash_combo()
        elif skill_id == "E":
            self.begin_aim()
        elif skill_id == "R":
            self._titan_form()
