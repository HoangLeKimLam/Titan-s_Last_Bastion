"""wolfcheck_AI.py — Demo AI tự hành của Wolf.

WolfAI (AI.py) tự hành theo WolfPriority. Wolf cắn nhanh, truyền
debuff 'antiheal'. Khẩu vị Wolf: khi bị tấn công, ưu tiên Commander
hơn Tower/Soldier.

Quan sát:
  • Wolf lao về HQ, gặp Wall thì phá.
  • Bấm K khi có cả Commander lẫn Tower bắn → AI quay sang Commander
    trước (đặc trưng WolfPriority).
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Titan import Wolf


class WolfAICheck(AICheckApp):
    """Demo AI cho Wolf — khẩu vị ưu tiên tướng khi bị tấn công."""

    def create_titan(self):
        return Wolf(self.spawn_x, self.spawn_y, {
            'hp': 600, 'speed': 95.0, 'damage': 30,
        })

    def title(self) -> str:
        return "Wolf AI  —  cắn nhanh, ưu tiên Commander khi bị đánh"

    def describe_titan(self) -> list:
        strat = type(getattr(self.titan, '_attack_strategy', None)).__name__
        return [f"Strategy: {strat} (truyền dtype='antiheal')"]


if __name__ == '__main__':
    WolfAICheck().run()
