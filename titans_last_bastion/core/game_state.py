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
    Túi chứa toàn bộ tài nguyên và vũ khí của game.

    Nguyên liệu cơ bản: wood, stone, gas, food, ore, serum
    Quặng đặc biệt: fire_ore, ice_ore, electric_ore, water_ore, wind_ore, acid_ore, anti_armor_ore
    Khác: titan_pheromone
    Vũ khí tháp: tower_weapon, basic_projectlie, ice_projectlie, electric_projectlie, water_projectlie
    Bẫy: trap, thorn_trap, explode_trap, bait_trap, poison_trap, smoke_trap
    Vũ khí lính: soldier_weapon, sword, spear, arrow, poison_arrow, heavy_arrow

    Toán tử hỗ trợ:
        +   : cộng 2 túi (loot, sản xuất)
        *   : nhân float — penalty chỉ áp lên wood/stone/gas/food
        >=  : kiểm tra đủ tài nguyên để chi tiêu (tất cả field)
    """
    # Thông số về nguyên liệu cơ bản
    wood:            int = 0
    stone:           int = 0
    gas:             int = 0
    food:            int = 0
    ore:             int = 0
    serum:           int = 0
    fire_ore:         int = 0
    ice_ore:         int = 0
    electric_ore:     int = 0
    water_ore:        int = 0
    wind_ore:         int = 0
    acid_ore:         int = 0
    anti_armor_ore:   int = 0
    titan_pheromone:     int = 0
    # Thông số về lượng vũ khí
    tower_weapon:    int = 0
    basic_projectlie:    int = 0
    ice_projectlie:    int = 0
    electric_projectlie:    int = 0
    water_projectlie:    int = 0
    trap:    int = 0
    thorn_trap:    int = 0
    explode_trap:    int = 0
    bait_trap:    int = 0
    poison_trap:    int = 0
    smoke_trap:    int = 0
    soldier_weapon:    int = 0
    sword:    int = 0
    spear:    int = 0
    arrow:    int =0
    poison_arrow:    int = 0
    heavy_arrow:    int = 0

    def __add__(self, other: "ResourceBundle") -> "ResourceBundle":
        return ResourceBundle(
            wood               = self.wood               + other.wood,
            stone              = self.stone              + other.stone,
            gas                = self.gas                + other.gas,
            food               = self.food               + other.food,
            ore                = self.ore                + other.ore,
            serum              = self.serum              + other.serum,
            fire_ore           = self.fire_ore           + other.fire_ore,
            ice_ore            = self.ice_ore            + other.ice_ore,
            electric_ore       = self.electric_ore       + other.electric_ore,
            water_ore          = self.water_ore          + other.water_ore,
            wind_ore           = self.wind_ore           + other.wind_ore,
            acid_ore           = self.acid_ore           + other.acid_ore,
            anti_armor_ore     = self.anti_armor_ore     + other.anti_armor_ore,
            titan_pheromone    = self.titan_pheromone    + other.titan_pheromone,
            tower_weapon       = self.tower_weapon       + other.tower_weapon,
            basic_projectlie   = self.basic_projectlie   + other.basic_projectlie,
            ice_projectlie     = self.ice_projectlie     + other.ice_projectlie,
            electric_projectlie= self.electric_projectlie+ other.electric_projectlie,
            water_projectlie   = self.water_projectlie   + other.water_projectlie,
            trap               = self.trap               + other.trap,
            thorn_trap         = self.thorn_trap         + other.thorn_trap,
            explode_trap       = self.explode_trap       + other.explode_trap,
            bait_trap          = self.bait_trap          + other.bait_trap,
            poison_trap        = self.poison_trap        + other.poison_trap,
            smoke_trap         = self.smoke_trap         + other.smoke_trap,
            soldier_weapon     = self.soldier_weapon     + other.soldier_weapon,
            sword              = self.sword              + other.sword,
            spear              = self.spear              + other.spear,
            arrow              = self.arrow              + other.arrow,
            poison_arrow       = self.poison_arrow       + other.poison_arrow,
            heavy_arrow        = self.heavy_arrow        + other.heavy_arrow,
        )


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
            wood               = int(self.wood  * factor),
            stone              = int(self.stone * factor),
            gas                = int(self.gas   * factor),
            food               = int(self.food  * factor),
            ore                = self.ore,
            serum              = self.serum,
            fire_ore           = self.fire_ore,
            ice_ore            = self.ice_ore,
            electric_ore       = self.electric_ore,
            water_ore          = self.water_ore,
            wind_ore           = self.wind_ore,
            acid_ore           = self.acid_ore,
            anti_armor_ore     = self.anti_armor_ore,
            titan_pheromone    = self.titan_pheromone,
            tower_weapon       = self.tower_weapon,
            basic_projectlie   = self.basic_projectlie,
            ice_projectlie     = self.ice_projectlie,
            electric_projectlie= self.electric_projectlie,
            water_projectlie   = self.water_projectlie,
            trap               = self.trap,
            thorn_trap         = self.thorn_trap,
            explode_trap       = self.explode_trap,
            bait_trap          = self.bait_trap,
            poison_trap        = self.poison_trap,
            smoke_trap         = self.smoke_trap,
            soldier_weapon     = self.soldier_weapon,
            sword              = self.sword,
            spear              = self.spear,
            arrow              = self.arrow,
            poison_arrow       = self.poison_arrow,
            heavy_arrow        = self.heavy_arrow,
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
        return (
            self.wood                >= cost.wood
            and self.stone           >= cost.stone
            and self.gas             >= cost.gas
            and self.food            >= cost.food
            and self.ore             >= cost.ore
            and self.serum           >= cost.serum
            and self.fire_ore        >= cost.fire_ore
            and self.ice_ore         >= cost.ice_ore
            and self.electric_ore    >= cost.electric_ore
            and self.water_ore       >= cost.water_ore
            and self.wind_ore        >= cost.wind_ore
            and self.acid_ore        >= cost.acid_ore
            and self.anti_armor_ore  >= cost.anti_armor_ore
            and self.titan_pheromone >= cost.titan_pheromone
            and self.tower_weapon    >= cost.tower_weapon
            and self.basic_projectlie    >= cost.basic_projectlie
            and self.ice_projectlie      >= cost.ice_projectlie
            and self.electric_projectlie >= cost.electric_projectlie
            and self.water_projectlie    >= cost.water_projectlie
            and self.trap            >= cost.trap
            and self.thorn_trap      >= cost.thorn_trap
            and self.explode_trap    >= cost.explode_trap
            and self.bait_trap       >= cost.bait_trap
            and self.poison_trap     >= cost.poison_trap
            and self.smoke_trap      >= cost.smoke_trap
            and self.soldier_weapon  >= cost.soldier_weapon
            and self.sword           >= cost.sword
            and self.spear           >= cost.spear
            and self.arrow           >= cost.arrow
            and self.poison_arrow    >= cost.poison_arrow
            and self.heavy_arrow     >= cost.heavy_arrow
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

    # --- Trạng thái màn hình / pha game (THÊM MỚI — không phá field cũ) -------
    # Các field dưới đây phục vụ hệ thống 3 màn hình (Menu → Sảnh → Chiến đấu).
    # Chúng có giá trị mặc định nên save.json cũ vẫn load được bình thường.
    game_mode:          str  = 'menu'   # 'menu' | 'lobby' | 'combat'
    selected_commander: str  = ''       # tên tướng đang chọn cho trận ('' = chưa)
    commander_xp:       int  = 0         # XP tướng — KHÔNG bao giờ reset
    hq_hp:              int  = 1000      # HP của HQ — KHÔNG bao giờ reset
    garrison_snapshot:  dict = field(default_factory=dict)  # {tower_id: {type: count}}

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
            # Field mới (3 màn hình) — thêm vào, không phá khoá cũ
            'game_mode':          self.game_mode,
            'selected_commander': self.selected_commander,
            'commander_xp':       self.commander_xp,
            'hq_hp':              self.hq_hp,
            'garrison_snapshot':  self.garrison_snapshot,
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
        # Field mới (3 màn hình) — .get() đảm bảo save cũ vẫn load được
        gs.game_mode          = data.get('game_mode', 'menu')
        gs.selected_commander = data.get('selected_commander', '')
        gs.commander_xp       = data.get('commander_xp', 0)
        gs.hq_hp              = data.get('hq_hp', 1000)
        gs.garrison_snapshot  = data.get('garrison_snapshot', {})
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
