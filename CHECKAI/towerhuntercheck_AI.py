"""towerhuntercheck_AI.py — Demo AI tự hành của TowerHunter.

TowerHunterAI (AI.py) tự hành theo TowerHunterPriority — "kẻ
công thành": luôn ưu tiên hạ Tower, khóa một Tower tới chết mới
chuyển sang Tower kế.

Quan sát:
  • Titan bỏ qua HQ/Wall, đi thẳng tới Tower gần nhất.
  • Đòn siege ×1.5 damage khi target là Tower (TowerHunterStrategy).
  • Hết Tower → mới quay về HQ.
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Titan import TowerHunter


class TowerHunterAICheck(AICheckApp):
    """Demo AI cho TowerHunter."""

    def create_titan(self):
        return TowerHunter(self.spawn_x, self.spawn_y, {
            'hp': 800, 'speed': 70.0, 'damage': 40,
        })

    def title(self) -> str:
        return "TowerHunter AI  —  săn tháp, khóa Tower tới chết"

    def describe_titan(self) -> list:
        return ["Đặc thù : siege ×1.5 damage khi target là Tower"]


if __name__ == '__main__':
    TowerHunterAICheck().run()
