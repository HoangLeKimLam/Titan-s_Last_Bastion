"""
game_state.py — Túi tài nguyên và trạng thái toàn cục của game.

Tại sao cần file này?
    ResourceBundle gom 8 loại tài nguyên vào 1 object duy nhất.
    Thay vì truyền 8 tham số riêng lẻ:
        spend(wood=50, stone=20, gas=0, food=0, ...)   ← rối
    Ta chỉ cần:
        spend(ResourceBundle(wood=50, stone=20))        ← gọn

    GameState lưu TOÀN BỘ trạng thái có thể serialize ra file JSON
    (save.json) và load lại — đảm bảo Persistent State giữa các màn.

Ai dùng file này:
    - ResourceManager  → lưu kho dưới dạng ResourceBundle
    - GameManager      → lưu/load GameState
    - Building.produce → trả về ResourceBundle
    - IUpgradable      → get_upgrade_cost() trả về ResourceBundle
"""

from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# ResourceBundle
# ---------------------------------------------------------------------------

@dataclass
class ResourceBundle:
    """
    Túi chứa 8 loại tài nguyên của game.

    Attributes:
        wood            (int): Gỗ — xây công trình cơ bản.
        stone           (int): Đá — xây tháp, sửa tường.
        gas             (int): Gas — ODMGear, FireTower, GasStorage.
        food            (int): Lương thực — train lính, duy trì quân.
        ore             (int): Quặng — Forge, BallistaTower, EMPTower.
        crystal         (int): Tinh thể — IceTower, nâng cấp cao cấp.
        serum           (int): Serum — mở khoá Phase 3 FoundingTitan.
        anti_armor_bolt (int): Đạn xuyên giáp — Forge sản xuất cho Ballista.

    Cách khởi tạo:
        cost  = ResourceBundle(stone=50, wood=20)      # chỉ khai báo cần thiết
        empty = ResourceBundle()                        # tất cả = 0
        loot  = ResourceBundle(wood=10, gas=5, ore=3)

    Toán tử hỗ trợ:
        +   : cộng 2 túi (khi loot hoặc sản xuất vào kho)
        *   : nhân với float (penalty mất 20% khi thua màn)
        >=  : kiểm tra đủ tài nguyên để chi tiêu
    """

    wood:            int = 0
    stone:           int = 0
    gas:             int = 0
    food:            int = 0
    ore:             int = 0
    crystal:         int = 0
    serum:           int = 0
    anti_armor_bolt: int = 0

    def __add__(self, other: "ResourceBundle") -> "ResourceBundle":
        return ResourceBundle(
            wood            = self.wood            + other.wood,
            stone           = self.stone           + other.stone,
            gas             = self.gas             + other.gas,
            food            = self.food            + other.food,
            ore             = self.ore             + other.ore,
            crystal         = self.crystal         + other.crystal,
            serum           = self.serum           + other.serum,
            anti_armor_bolt = self.anti_armor_bolt + other.anti_armor_bolt,
        )
        """
        Cộng 2 túi tài nguyên, trả về túi mới.

        Args:
            other (ResourceBundle): Túi cộng thêm.

        Returns:
            ResourceBundle: Túi mới = self + other (không sửa self).

        Dùng khi nào:
            - Loot về kho: self._stock = self._stock + loot_bundle
            - Building.update: self._stock += self.produce()

        Hướng dẫn code:
            return ResourceBundle(
                wood            = self.wood            + other.wood,
                stone           = self.stone           + other.stone,
                gas             = self.gas             + other.gas,
                food            = self.food            + other.food,
                ore             = self.ore             + other.ore,
                crystal         = self.crystal         + other.crystal,
                serum           = self.serum           + other.serum,
                anti_armor_bolt = self.anti_armor_bolt + other.anti_armor_bolt,
            )

        Ví dụ:
            stock = ResourceBundle(wood=100, stone=50)
            loot  = ResourceBundle(wood=20,  gas=10)
            new   = stock + loot
            # new.wood == 120, new.stone == 50, new.gas == 10
        """
        pass

    def __mul__(self, factor: float) -> "ResourceBundle":
        """
        Nhân toàn bộ tài nguyên với một hệ số float.

        Args:
            factor (float): Hệ số nhân, vd. 0.8 (mất 20%).

        Returns:
            ResourceBundle: Túi mới với giá trị đã nhân (làm tròn int).

        Dùng khi nào:
            - Penalty thua màn: self._stock = self._stock * 0.8

        Lưu ý:
            Chỉ nhân 4 loại tài nguyên cơ bản (wood, stone, gas, food).
            ore, crystal, serum, anti_armor_bolt KHÔNG bị penalty.

        Hướng dẫn code:
            return ResourceBundle(
                wood  = int(self.wood  * factor),
                stone = int(self.stone * factor),
                gas   = int(self.gas   * factor),
                food  = int(self.food  * factor),
                ore             = self.ore,
                crystal         = self.crystal,
                serum           = self.serum,
                anti_armor_bolt = self.anti_armor_bolt,
            )

        Ví dụ:
            stock   = ResourceBundle(wood=100, stone=80, ore=10)
            penalty = stock * 0.8
            # penalty.wood == 80, penalty.stone == 64, penalty.ore == 10 (giữ nguyên)
        """
        return ResourceBundle(
            wood  = int(self.wood  * factor),
            stone = int(self.stone * factor),
            gas   = int(self.gas   * factor),
            food  = int(self.food  * factor),
            ore             = self.ore,
            crystal         = self.crystal,
            serum           = self.serum,
            anti_armor_bolt = self.anti_armor_bolt,
        )
        

    def __ge__(self, cost: "ResourceBundle") -> bool:
        """
        Kiểm tra self có đủ tất cả loại tài nguyên so với cost không.

        Args:
            cost (ResourceBundle): Mức yêu cầu cần đủ.

        Returns:
            bool: True nếu self >= cost ở mọi loại tài nguyên.

        Dùng khi nào:
            - ResourceManager.can_afford(cost): return self._stock >= cost
            - IUpgradable: kiểm tra trước khi upgrade

        Hướng dẫn code:
            return (
                self.wood            >= cost.wood
                and self.stone       >= cost.stone
                and self.gas         >= cost.gas
                and self.food        >= cost.food
                and self.ore         >= cost.ore
                and self.crystal     >= cost.crystal
                and self.serum       >= cost.serum
                and self.anti_armor_bolt >= cost.anti_armor_bolt
            )

        Ví dụ:
            stock = ResourceBundle(wood=100, stone=50)
            cost  = ResourceBundle(stone=50, wood=20)
            stock >= cost   # True
            cost  >= stock  # False (cost.wood=20 < stock.wood=100... wait)
            # Ý đúng: kiểm tra xem STOCK có ĐỦ để trả COST không
        """
        return (self.wood            >= cost.wood
                and self.stone       >= cost.stone
                and self.gas         >= cost.gas
                and self.food        >= cost.food
                and self.ore         >= cost.ore
                and self.crystal     >= cost.crystal
                and self.serum       >= cost.serum
                and self.anti_armor_bolt >= cost.anti_armor_bolt
                )

    def to_dict(self) -> dict:
        """
        Chuyển ResourceBundle thành dict để serialize ra JSON.

        Returns:
            dict: {'wood': 100, 'stone': 50, ...}

        Hướng dẫn code:
            return asdict(self)   # dataclasses.asdict tự làm việc này

        Dùng khi nào:
            - GameState.save() → json.dump(state.to_dict(), file)
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ResourceBundle":
        """
        Tạo ResourceBundle từ dict đọc được từ JSON.

        Args:
            data (dict): {'wood': 100, 'stone': 50, ...}

        Returns:
            ResourceBundle: Object được khôi phục.

        Hướng dẫn code:
            return cls(**data)

        Dùng khi nào:
            - GameState.load() → bundle = ResourceBundle.from_dict(raw['stock'])
        """
        return cls(**data)


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    """
    Snapshot toàn bộ trạng thái game có thể lưu/load.

    Attributes:
        current_level     (int):  Màn hiện tại (1–5).
        stock             (ResourceBundle): Kho tài nguyên hiện tại.
        commander_level   (int):  Level Tướng Quân (1–10).
        walls_hp          (dict): {wall_id: {section_id: hp}} — HP từng đoạn tường.
        towers            (list): Danh sách dict mô tả tháp đã đặt.
        buildings         (list): Danh sách dict mô tả công trình.
        soldiers_alive    (int):  Số lính còn sống.

    Dùng khi nào:
        - Thắng màn  → GameManager gọi save() để ghi save.json
        - Mở game    → GameManager gọi load() để đọc save.json
        - Thua màn   → apply_defeat_penalty() rồi save() ngay
    """

    current_level:   int            = 1
    stock:           ResourceBundle = field(default_factory=ResourceBundle)
    commander_level: int            = 1
    walls_hp:        dict           = field(default_factory=dict)
    towers:          list           = field(default_factory=list)
    buildings:       list           = field(default_factory=list)
    soldiers_alive:  int            = 0

    def save(self, filepath: str = "save.json"):
        """
        Serialize GameState ra file JSON.

        Args:
            filepath (str): Đường dẫn file, mặc định 'save.json' ở root.

        Hướng dẫn code:
            import json
            data = {
                'current_level':   self.current_level,
                'stock':           self.stock.to_dict(),
                'commander_level': self.commander_level,
                'walls_hp':        self.walls_hp,
                'towers':          self.towers,
                'buildings':       self.buildings,
                'soldiers_alive':  self.soldiers_alive,
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        Ví dụ:
            game_state.save()             # ghi vào save.json
            game_state.save('slot2.json') # ghi vào slot khác
        """
        import json
        data = {
            'current_level':   self.current_level,
            'stock':           self.stock.to_dict(),
            'commander_level': self.commander_level,
            'walls_hp':        self.walls_hp,
            'towers':          self.towers,
            'buildings':       self.buildings,
            'soldiers_alive':  self.soldiers_alive,
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str = "save.json") -> "GameState":
        """
        Đọc file JSON và khôi phục GameState.

        Args:
            filepath (str): Đường dẫn file save.

        Returns:
            GameState: Object được khôi phục từ file.

        Hướng dẫn code:
            import json, os
            if not os.path.exists(filepath):
                return cls()   # Không có file → trả về GameState mặc định (màn 1)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            gs = cls()
            gs.current_level   = data.get('current_level', 1)
            gs.stock           = ResourceBundle.from_dict(data.get('stock', {}))
            gs.commander_level = data.get('commander_level', 1)
            gs.walls_hp        = data.get('walls_hp', {})
            gs.towers          = data.get('towers', [])
            gs.buildings       = data.get('buildings', [])
            gs.soldiers_alive  = data.get('soldiers_alive', 0)
            return gs

        Ví dụ:
            state = GameState.load()
            print(state.current_level)   # 3 (đang ở màn 3)
        """
        import json, os
        if not os.path.exists(filepath):
            return cls()   # Không có file → trả về GameState mặc
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        gs = cls()
        gs.current_level   = data.get('current_level', 1)
        gs.stock           = ResourceBundle.from_dict(data.get('stock', {}))
        gs.commander_level = data.get('commander_level', 1)
        gs.walls_hp        = data.get('walls_hp', {})
        gs.towers          = data.get('towers', [])
        gs.buildings       = data.get('buildings', [])
        gs.soldiers_alive  = data.get('soldiers_alive', 0)
        return gs

    def apply_defeat_penalty(self):
        """
        Áp dụng hình phạt thua màn: mất 20% tài nguyên cơ bản,
        commander_level giảm 1 (tối thiểu 1).

        Hướng dẫn code:
            self.stock = self.stock * 0.8
            self.commander_level = max(1, self.commander_level - 1)

        Dùng khi nào:
            GameManager phát hiện lose condition → gọi method này
            → rồi gọi self.save() để lưu trạng thái mới.

        Ví dụ:
            game_state.apply_defeat_penalty()
            game_state.save()
            # Game reload màn hiện tại với trạng thái đã bị penalty
        """
        self.stock = self.stock * 0.8
        self.commander_level = max(1, self.commander_level - 1)
