"""titancheck_AI.py — Demo AI tự hành của RegularTitan.

Chạy:  python titancheck_AI.py   (từ trong thư mục CHECKAI/)

RegularTitan KHÔNG do người chơi điều khiển. RegularAI (AI.py)
tự: chọn mục tiêu theo DefaultPriority → tiến tới → đánh thường. Khi
HP < 40% chính class RegularTitan đổi sang HeavyStrikeStrategy.

Quan sát:
  • Titan luôn hướng về HQ; gặp Wall chắn đường thì phá Wall.
  • Bấm K cho Tower/Soldier bắn titan → AI chuyển sang đánh kẻ tấn công.
  • HUD hiện State / Target / Reason của AI mỗi frame.
"""
import _ai_bootstrap  # noqa: F401  — PHẢI import đầu tiên
from _ai_app import AICheckApp
from Titan import RegularTitan


class RegularTitanAICheck(AICheckApp):
    """Demo AI cho RegularTitan — chỉ override phần đặc thù."""

    def create_titan(self):
        return RegularTitan(self.spawn_x, self.spawn_y, {
            'hp': 1000, 'speed': 70.0, 'damage': 20,
        })

    def title(self) -> str:
        return "RegularTitan AI  —  AI tự hành (SPACE/C/K/R/Q)"

    def describe_titan(self) -> list:
        heavy = getattr(self.titan, '_heavy_mode', False)
        return [f"Mode    : {'HEAVY (HP<40%)' if heavy else 'thường'}"]


if __name__ == '__main__':
    RegularTitanAICheck().run()
