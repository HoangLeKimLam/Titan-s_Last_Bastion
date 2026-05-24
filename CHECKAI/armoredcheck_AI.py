"""armoredcheck_AI.py — Demo AI tự hành của ArmoredTitan.

ArmoredAI (AI.py) tự hành theo ArmoredPriority — "cỗ máy phá
thành":
  • Ưu tiên Wall hơn cả HQ; với Wall còn ngoài tầm → kích Dash (Ram)
    lao húc, tích lũy `_ram_hits`.
  • Sau 5 hit (Ram hoặc anti_armor) → giáp vỡ, Dash bị khóa, AI
    chuyển sang melee đứng tại chỗ.

Quan sát:
  • Titan dash húc Wall; HUD báo armor INTACT/BROKEN.
  • Bấm K để Tower/Soldier/Commander bắn → AI quay sang đánh chúng.
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Titan import ArmoredTitan


class ArmoredTitanAICheck(AICheckApp):
    """Demo AI cho ArmoredTitan."""

    def create_titan(self):
        return ArmoredTitan(self.spawn_x, self.spawn_y, {
            'hp': 1000, 'speed': 100.0, 'damage': 100,
        })

    def title(self) -> str:
        return "ArmoredTitan AI  —  dash phá Wall, melee sau khi vỡ giáp"

    def describe_titan(self) -> list:
        t = self.titan
        armor = 'INTACT' if getattr(t, '_armor_intact', True) else 'BROKEN'
        ram = getattr(t, '_ram_hits', 0)
        aa  = getattr(t, '_antiarmor_hits', 0)
        return [f"Armor   : {armor}   ram_hits={ram}  antiarmor_hits={aa}"]


if __name__ == '__main__':
    ArmoredTitanAICheck().run()
