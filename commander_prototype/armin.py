"""armin.py — ArminCommander, Tướng Quân của Màn 4.

ArminCommander dùng asset pack "Warrior" (Individual Sprite — mỗi PNG là
một frame riêng, không phải sprite strip). User chỉ yêu cầu triển khai
4 animation hiện tại: Attack, Dash Attack, Idle, Dash.

Mapping:
    idle      → idle/  (6 frames, the canonical standing pose)
    walk      → Dash/  (no walk anim in this set — use Dash as placeholder)
    attack1/2/3 → Attack/ (LMB combo all play the same 12-frame attack)
    skill_q   → Dash Attack/  (Q = dash slash — fits naturally)
    skill_e   → Dash/         (E = ODM Surge — Dash animation)
    skill_r   → Attack/       (no power-up anim — Attack as placeholder)
    hurt/dying/win → idle/    (placeholders until those anims land)

Character normalisation: idle character bbox = 33 px tall in source;
TARGET_HEIGHT_PX=168 ⇒ scale ≈ 5.09 ⇒ idle renders at ~168 px tall, same
as Eren and Mikasa.
"""
from commander import Commander
from assets_config import (
    ARMIN_SPRITE_FRAMES,
    FRAME_HEIGHT_ARMIN,
    FRAME_WIDTH_ARMIN,
)


class ArminCommander(Commander):
    """Tướng Armin Arlert — mở khoá ở Màn 4."""

    # --- Định danh tướng -------------------------------------------------
    NAME = "Armin Arlert"
    STAGE = 4

    # --- Sprite pack ----------------------------------------------------
    SPRITE_FOLDER = "../Warrior/Individual Sprite"
    SPRITE_FRAMES = ARMIN_SPRITE_FRAMES
    FRAME_WIDTH = FRAME_WIDTH_ARMIN
    FRAME_HEIGHT = FRAME_HEIGHT_ARMIN

    # --- Cooldowns (giây) -----------------------------------------------
    SKILL_COOLDOWNS = {"Q": 5.0, "E": 8.0, "R": 30.0}

    # Q_/E_/R_ tuning inherits Commander defaults.

    # --- Skill dispatch -------------------------------------------------
    def _activate_skill(self, skill_id: str) -> None:
        """Same template as Eren/Mikasa — Armin reuses base Q/E/R for now."""
        if skill_id == "Q":
            self._slash_combo()
        elif skill_id == "E":
            self.begin_aim()  # E is normally driven directly by main.py
        elif skill_id == "R":
            self._titan_form()
