"""witchcheck_AI.py — Demo AI tự hành của Witch.

WitchAI (AI.py) tự hành theo WitchPriority:
  • Còn Soldier/Commander/Tower → đứng yên cast Cursed x10 toàn map.
  • Hết lực lượng phòng thủ → mới đi về Wall/HQ và cast fallback cận chiến.

Quan sát:
  • Witch giữ frame summon cuối 2 giây rồi gọi sét.
  • `thunder.jpg` skip frame trắng, mask nền và vẽ tia sét tại mỗi target.
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Titan import Witch


class WitchAICheck(AICheckApp):
    """Demo AI cho Witch — caster đứng xa, Cursed toàn map."""

    def create_titan(self):
        return Witch(self.spawn_x, self.spawn_y, {
            'hp': 1200, 'speed': 55.0, 'damage': 45,
        })

    def title(self) -> str:
        return "Witch AI  —  Cursed x10 toàn map"

    def describe_titan(self) -> list:
        t = self.titan
        cd = max(0.0, getattr(t, '_cast_cd_timer', 0.0))
        casting = getattr(t, '_is_casting', False)
        bolts = getattr(t, '_last_bolt_count', 0)
        return [
            f"Cursed : cooldown={cd:.1f}s   casting={casting}",
            f"Bolts  : lần cast gần nhất = {bolts}",
        ]


if __name__ == '__main__':
    WitchAICheck().run()
