# structures/buildings/resource_manager.py
from dataclasses import fields as dc_fields
from core.game_state import ResourceBundle


class ResourceManager:
    """Singleton — kho tài nguyên duy nhất của game.

    Mọi class cần tài nguyên đều gọi ResourceManager.get_instance().
    Không ai được cộng/trừ tài nguyên trực tiếp ngoài class này.
    """

    _instance = None

    def __init__(self):
        self._stock = ResourceBundle()

    @classmethod
    def get_instance(cls) -> "ResourceManager":
        if cls._instance is None:
            cls._instance = ResourceManager()
        return cls._instance

    def earn(self, bundle: ResourceBundle):
        """Cộng tài nguyên vào kho (loot, harvest, thưởng)."""
        self._stock += bundle

    def spend(self, cost: ResourceBundle) -> bool:
        """Trừ tài nguyên. Trả về False nếu không đủ."""
        if not self.can_afford(cost):
            return False
        for f in dc_fields(self._stock):
            setattr(self._stock, f.name,
                    getattr(self._stock, f.name) - getattr(cost, f.name))
        return True

    def can_afford(self, cost: ResourceBundle) -> bool:
        """Kiểm tra đủ tài nguyên không."""
        return self._stock >= cost

    def get_stock(self) -> ResourceBundle:
        """Trả về kho hiện tại. HUD dùng để hiển thị."""
        return self._stock

    def apply_defeat_penalty(self):
        """Thua màn → mất 20% tài nguyên."""
        self._stock = self._stock * 0.8