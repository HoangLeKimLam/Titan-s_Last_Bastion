"""mikasa.py — MikasaCommander, Tướng Quân của Màn 2.

MikasaCommander dùng sprite pack "Knight 2D Pixel Art" (biến thể with_outline,
96×84 mỗi frame). Skill set kế thừa nguyên template Q/E/R từ Commander
base — sẽ cá biệt hoá cho Mikasa ở các sprint sau (chẳng hạn passive
counter-attack hay W "Family Vow" — phần đó nằm ngoài yêu cầu hiện tại).

Khác biệt so với Eren CHỈ ở 3 dòng:
    - SPRITE_FOLDER, SPRITE_FRAMES, FRAME_WIDTH/HEIGHT  → pack ảnh khác
    - NAME, STAGE                                       → định danh
    - _activate_skill                                   → vẫn dispatch 3 skill
"""
from commander import Commander
from assets_config import (
    FRAME_HEIGHT_MIKASA,
    FRAME_WIDTH_MIKASA,
    MIKASA_SPRITE_FRAMES,
)


class MikasaCommander(Commander):
    """Tướng Mikasa Ackerman — mở khoá ở Màn 2."""

    # --- Định danh tướng -------------------------------------------------
    NAME = "Mikasa Ackerman"
    STAGE = 2

    # --- Sprite pack ----------------------------------------------------
    SPRITE_FOLDER = "../Knight 2D Pixel Art/Sprites/with_outline"
    SPRITE_FRAMES = MIKASA_SPRITE_FRAMES
    FRAME_WIDTH = FRAME_WIDTH_MIKASA
    FRAME_HEIGHT = FRAME_HEIGHT_MIKASA

    # --- Cooldowns (giây) -----------------------------------------------
    SKILL_COOLDOWNS = {"Q": 5.0, "E": 8.0, "R": 30.0}

    # Q_/E_/R_ constants inherit Commander defaults. Sau này muốn Mikasa
    # damage cao hơn / cooldown ngắn hơn thì override trực tiếp ở đây.

    # --- Skill dispatch -------------------------------------------------
    def _activate_skill(self, skill_id: str) -> None:
        """Same dispatch as Eren — Mikasa reuses base Q/E/R for now."""
        if skill_id == "Q":
            self._slash_combo()
        elif skill_id == "E":
            self.begin_aim()  # E is normally driven directly by main.py
        elif skill_id == "R":
            self._titan_form()
