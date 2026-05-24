"""clossalcheck_AI.py — Demo AI tự hành của ColossalTitan (Boss màn 3).

ColossalAI (AI.py) tự hành theo DefaultPriority — tiến về HQ —
nhưng tung 2 kỹ năng AoE theo cooldown do chính ColossalTitan quản:
  • Jump Stomp (mỗi 15s) — AoE 160px, stun Tower 5s.
  • Steam Burst (mỗi 8s) — vành khuyên hơi nóng, đốt Soldier/Commander.

AI chỉ ĐỌC cooldown của titan rồi gọi `_jump_stomp()` / `_steam_burst()`
đúng lúc — không tự đếm giờ.

Quan sát:
  • HUD báo "Jump Stomp" / "Steam Burst" khi skill kích hoạt.
  • Tower quanh titan bị stun (đổi màu vàng) sau Jump Stomp.
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Boss import ColossalTitan


class ColossalTitanAICheck(AICheckApp):
    """Demo AI cho ColossalTitan — boss 2 kỹ năng AoE theo cooldown."""

    def create_titan(self):
        return ColossalTitan(self.spawn_x, self.spawn_y, {
            'hp': 2000, 'speed': 55.0, 'damage': 60,
        })

    def title(self) -> str:
        return "ColossalTitan AI  —  Boss M3: Steam Burst + Jump Stomp"

    def describe_titan(self) -> list:
        t = self.titan
        st = max(0.0, getattr(t, '_steam_timer', 0.0))
        jt = max(0.0, getattr(t, '_jump_timer', 0.0))
        return [f"Skill CD: Steam={st:.1f}s   Jump={jt:.1f}s"]


if __name__ == '__main__':
    ColossalTitanAICheck().run()
