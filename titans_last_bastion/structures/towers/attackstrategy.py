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
        """Chọn titan GẦN THÁP NHẤT (so bình phương khoảng cách, không tính căn).
        Rỗng → None."""
        if not titans:
            return None
        return min(
            titans,
            key=lambda t: (t.x - tower.x)**2 + (t.y - tower.y)**2
        )


class StrongestTargeting(TowerTargetingStrategy):
    """Nhắm Titan HP cao nhất — BallistaTower dùng."""

    def select_target(self, tower, titans: list):
        """Chọn titan HP HIỆN TẠI CAO NHẤT (ưu tiên tập trung hoả lực vào con
        trâu nhất trước). Rỗng → None. Hiện KHÔNG có tháp nào dùng strategy này
        theo mặc định (đăng ký thủ công qua `set_targeting()` nếu cần)."""
        if not titans:
            return None
        return max(titans, key=lambda t: t._hp)


class FastestTargeting(TowerTargetingStrategy):
    """Nhắm Titan speed cao nhất — IceTower dùng để slow."""

    def select_target(self, tower, titans: list):
        """Chọn titan TỐC ĐỘ CAO NHẤT — ưu tiên hạ trước những con chạy nhanh
        khó bắt kịp (thường ghép với tháp Ice để làm chậm con nguy hiểm nhất
        trước khi nó vượt qua tuyến phòng thủ). Rỗng → None."""
        if not titans:
            return None
        return max(titans, key=lambda t: t._speed)