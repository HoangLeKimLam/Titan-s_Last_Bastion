"""foundingcheck_AI.py — Demo AI tự hành của FoundingTitan (Final Boss).

FoundingAI (AI.py) tự hành theo DefaultPriority, hành vi theo
3 phase do chính FoundingTitan quản (`_check_phase`):
  • P1 (HP>60%) / P3 (HP≤20%): áp sát đánh HeavyStrike — đứng yên
    vung tay trong 0.25s animation, không di chuyển giữa đòn.
  • P2 (20–60%): tự summon 10 minion mỗi đợt; giữa các đợt vẫn đánh.
    Mỗi minion được cấp AI riêng (RegularAI/WolfAI/TowerHunterAI/
    SoldierHunterAI) qua `make_ai_for` — minion KẾ THỪA đầy đủ
    class của nó (Walk/Run/Attack/AttackStrategy) và tự đi đánh
    Tower/Soldier/Commander/Wall/HQ trong WorldView của demo.
  • P3 sticky: vào P3 rồi thì tắt summon vĩnh viễn dù HP hồi lại.

Quan sát:
  • Bấm K nhiều lần hạ HP titan để xem chuyển phase + AI tự summon ở P2.
  • HUD báo Phase hiện tại + cooldown summon.
  • Minion summon hiện lên thành vòng tròn quanh Founding rồi tự tản
    ra đánh các entity phòng thủ.

Ghi chú: để dễ thấy chuyển phase, titan ở demo này HP thấp hơn game
thật (800) — bấm K vài lần là tụt phase.
"""
import _ai_bootstrap  # noqa: F401
from _ai_app import AICheckApp
from Boss import FoundingTitan


class FoundingTitanAICheck(AICheckApp):
    """Demo AI cho FoundingTitan — final boss 3 phase + summon."""

    def create_titan(self):
        # HP 800 (thấp hơn game thật) để bấm K vài lần là đổi phase.
        return FoundingTitan(self.spawn_x, self.spawn_y, {
            'hp': 800, 'speed': 50.0, 'damage': 50,
        })

    def title(self) -> str:
        return "FoundingTitan AI  —  Final Boss: 3 phase + summon"

    def describe_titan(self) -> list:
        t = self.titan
        phase  = getattr(t, '_phase', 1)
        locked = getattr(t, '_summon_locked', False)
        cd     = max(0.0, getattr(t, '_summon_cd_timer', 0.0))
        n      = len(getattr(t, '_summoned_minions', []))
        return [
            f"Phase   : P{phase}   "
            f"summon_locked={locked}   summon_cd={cd:.1f}s",
            f"Minions : đã summon {n} con (lũy kế)",
        ]


if __name__ == '__main__':
    FoundingTitanAICheck().run()
