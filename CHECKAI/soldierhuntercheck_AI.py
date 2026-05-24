"""soldierhuntercheck_AI.py — Demo AI tự hành của SoldierHunter.

SoldierHunterAI (AI.py) tự hành theo SoldierHunterPriority —
"khắc tinh bộ binh": luôn ưu tiên săn Soldier.

Cleave AoE (NHÓM 5 — cập nhật):
  • Tâm cleave = vị trí ATTACKER (không phải target).
  • Bán kính = `_attack_range` của SoldierHunter (mặc định 40px),
    truyền vào `SoldierHunterStrategy(splash_radius=…)` khi __init__.
  • Quét MỌI loại entity: soldier + commander + tower + wall + HQ.
  • Damage: target chính = 100% × `attacker._damage × _DEFAULT_DAMAGE_MULT`
    (dtype='soldier'); các entity còn lại trong vùng = 50% (dtype='aoe').
  • Target chính tự loại khỏi splash → không trừ máu 2 lần.

Quan sát:
  • Titan bỏ qua HQ/Wall, đi thẳng tới Soldier gần nhất.
  • Khi vung đòn cleave, mọi đơn vị/công trình đứng kẹp quanh
    SoldierHunter đều ăn splash 50%.
  • Bấm SPACE thêm Soldier để xem AI đổi mục tiêu liên tục.
  • Hết Soldier → mới quay về HQ.
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Titan import SoldierHunter


class SoldierHunterAICheck(AICheckApp):
    """Demo AI cho SoldierHunter — cleave AoE đa loại quanh attacker."""

    def create_titan(self):
        return SoldierHunter(self.spawn_x, self.spawn_y, {
            'hp': 1200, 'speed': 65.0, 'damage': 40,
        })

    def title(self) -> str:
        return "SoldierHunter AI  —  cleave AoE = attack_range, trúng mọi entity"

    def describe_titan(self) -> list:
        t = self.titan
        rng = getattr(t, '_attack_range', 40.0)
        return [
            f"Cleave  : radius={rng:.0f}px quanh ATTACKER (= attack_range)",
            "Splash  : 50% main, quét soldier + commander + tower + wall + hq",
        ]


if __name__ == '__main__':
    SoldierHunterAICheck().run()
