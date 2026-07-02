# structures/towers/attackstrategy.py
from abc import ABC, abstractmethod


class TowerTargetingStrategy(ABC):
    """ABC cho chiến thuật chọn mục tiêu của tháp.

    Tower HAS-A strategy này.
    Đổi strategy → đổi cách nhắm mà không sửa class Tower.
    """

    @abstractmethod
    def select_target(self, tower, titans: list):
        """Chọn 1 Titan để tháp tấn công.
        Trả về Titan hoặc None nếu không có target.
        """
        ...


class NearestTargeting(TowerTargetingStrategy):
    """Nhắm Titan gần tháp nhất — mặc định CannonTower."""

    def select_target(self, tower, titans: list):
        if not titans:
            return None
        return min(
            titans,
            key=lambda t: (t.x - tower.x)**2 + (t.y - tower.y)**2
        )


class StrongestTargeting(TowerTargetingStrategy):
    """Nhắm Titan HP cao nhất — BallistaTower dùng."""

    def select_target(self, tower, titans: list):
        if not titans:
            return None
        return max(titans, key=lambda t: t._hp)


class FastestTargeting(TowerTargetingStrategy):
    """Nhắm Titan speed cao nhất — IceTower dùng để slow."""

    def select_target(self, tower, titans: list):
        if not titans:
            return None
        return max(titans, key=lambda t: t._speed)