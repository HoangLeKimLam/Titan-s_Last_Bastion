"""beastcheck_AI.py — Demo AI tự hành của BeastTitan (Boss màn 4).

BeastAI (AI.py) tự hành theo BeastPriority — "thợ săn tháp":
  • Thứ tự chủ động: Tower → Soldier → Commander → Wall → HQ.
  • Mục tiêu trong THROW_RANGE (350px) + đã hồi → ném đá (RockProjectile),
    cùng skill cho mọi loại target (Tower, Soldier, Commander, Wall, HQ).
  • Ngoài tầm → đi bộ lại gần.
  • Cooldown ném 2.0s (giảm từ 5.0s).

Quan sát:
  • Beast dọn sạch Tower trước, rồi quét Soldier, rồi Commander.
  • Hết lực lượng phòng thủ → đập Wall mở đường vào HQ.
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Boss import BeastTitan


class BeastTitanAICheck(AICheckApp):
    """Demo AI cho BeastTitan — boss ném đá tầm xa.

    Layout dùng chung của AICheckApp (4 Wall bao quanh HQ + Tower/Soldier/
    Commander bố trí ngoài vòng Wall) — đồng nhất với các demo khác.
    """

    def create_titan(self):
        return BeastTitan(self.spawn_x, self.spawn_y, {
            'hp': 1500, 'speed': 55.0, 'damage': 80,
        })

    def title(self) -> str:
        return "BeastTitan AI  —  Boss M4: ném đá tầm xa, săn tháp"

    def describe_titan(self) -> list:
        t = self.titan
        cd = max(0.0, getattr(t, '_throw_timer', 0.0))
        rng = getattr(t, 'THROW_RANGE', 350.0)
        return [f"Throw   : range={rng:.0f}px   cooldown={cd:.1f}s"]


if __name__ == '__main__':
    BeastTitanAICheck().run()
