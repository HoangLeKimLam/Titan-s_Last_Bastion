"""soldierhuntercheck_AI.py — Demo AI tự hành của SoldierHunter.

SoldierHunterAI (AI.py) tự hành theo SoldierHunterPriority —
"khắc tinh bộ binh": luôn ưu tiên săn Soldier. Đòn cleave có splash
AoE 60px quanh mục tiêu (SoldierHunterStrategy).

Quan sát:
  • Titan bỏ qua HQ/Wall, đi thẳng tới Soldier gần nhất.
  • Bấm SPACE thêm Soldier để xem AI đổi mục tiêu liên tục.
  • Hết Soldier → mới quay về HQ.
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Titan import SoldierHunter


class SoldierHunterAICheck(AICheckApp):
    """Demo AI cho SoldierHunter."""

    def create_titan(self):
        return SoldierHunter(self.spawn_x, self.spawn_y, {
            'hp': 1200, 'speed': 65.0, 'damage': 40,
        })

    def title(self) -> str:
        return "SoldierHunter AI  —  săn lính, cleave AoE 60px"

    def describe_titan(self) -> list:
        return ["Đặc thù : cleave splash 50% damage quanh target"]


if __name__ == '__main__':
    SoldierHunterAICheck().run()
