"""eren.py — ErenCommander, Tướng Quân của Màn 1.

ErenCommander dùng sprite pack Knight_player_1.4 (100×64 mỗi frame).
Cả 3 skill (Q/E/R) đều dùng IMPLEMENTATION MẶC ĐỊNH ở Commander base
— Eren là "template ground-truth" cho cả 5 tướng. Các tướng khác có
thể override skill riêng nếu cần.

Constants Q_/E_/R_ kế thừa từ Commander (default Eren-flavoured).
Nếu muốn cân bằng riêng cho Eren, override tại đây.

Quyết định thiết kế đã chốt với nhóm (áp dụng ở commander.py):
    - KHÔNG có class Character trung gian: Commander kế thừa thẳng Entity.
    - Thua 1 màn → tụt 1 level (xử lý trong Commander.take_damage()).

Skill của Eren (Màn 1):
    Q — Slash Combo : dash tới Titan gần nhất + 3 nhát AoE 80px, 40 dmg/nhát.
    E — ODM Surge   : lao tới Titan gần nhất, gây choáng 1.5s.
    R — Titan Form  : bất tử 10s, đồng thời nổ AoE 150px gây 150 damage.
"""
from commander import Commander
from assets_config import EREN_SPRITE_FRAMES, FRAME_HEIGHT_EREN, FRAME_WIDTH_EREN


class ErenCommander(Commander):
    """Tướng Eren Yeager — mở khoá ở Màn 1."""

    # --- Định danh tướng -------------------------------------------------
    NAME = "Eren Yeager"
    STAGE = 1

    # --- Sprite pack ----------------------------------------------------
    SPRITE_FOLDER = "../Knight_player_1.4/Knight_player_1.4/Knight_player"
    SPRITE_FRAMES = EREN_SPRITE_FRAMES
    FRAME_WIDTH = FRAME_WIDTH_EREN
    FRAME_HEIGHT = FRAME_HEIGHT_EREN

    # --- Cooldowns (giây) -----------------------------------------------
    SKILL_COOLDOWNS = {"Q": 5.0, "E": 8.0, "R": 30.0}

    # Q_/E_/R_ constants inherit Commander defaults (40 dmg ×3, etc.)

    # --- Skill dispatch -------------------------------------------------
    def _activate_skill(self, skill_id: str) -> None:
        """Map skill_id → method. Skill methods live on Commander base.

        E (Grappling Swing) is NOT routed through use_skill — main.py drives it
        directly via begin_aim()/confirm_swing()/cancel_swing(). If E is ever
        dispatched here we just open the aim session as a safe fallback.
        """
        if skill_id == "Q":
            self._slash_combo()
        elif skill_id == "E":
            self.begin_aim()
        elif skill_id == "R":
            self._titan_form()
