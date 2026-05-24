"""
interfaces.py — 6 "hợp đồng" ABC cho Titan's Last Bastion.

Tại sao cần file này?
    Interface (ABC với @abstractmethod) là bản hợp đồng:
    "Class nào implement interface này BẮT BUỘC phải có những method đó."

    Lợi ích thực tế trong teamwork:
      - Long viết Tower.shoot(target: IAttackable) mà không cần biết
        target là Titan hay WallSection — chỉ cần biết nó có take_damage().
      - Nhật viết Titan mà không cần biết Tower trông như thế nào.
      - Python sẽ báo lỗi ngay khi class con quên implement method bắt buộc.

Quy tắc:
    Một class có thể implement nhiều interface cùng lúc:
        class Tower(Entity, IAttackable, IUpgradable): ...
        class Commander(Entity, IAttackable, IMovable, ISkillUser, IUpgradable): ...
"""

from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# IAttackable
# ---------------------------------------------------------------------------

class IAttackable(ABC):
    
    """
    Hợp đồng: "Tôi có thể bị tấn công và nhận damage."
    Kế thừa hơp đồng này với những cái có khả năng nhận sát thương
    Ai implement:
        Titan, Commander, Soldier, Tower, Building, WallSection

    Ai GỌI take_damage():
        - Tower.shoot()          → target.take_damage(dmg, 'normal')
        - TitanAttackStrategy    → target.take_damage(dmg, 'ram')
        - Commander skill        → target.take_damage(dmg, 'slash')
        - Decorator.take_damage  → ủy quyền xuống entity gốc

    Ví dụ sử dụng đa hình (đây là điểm mạnh nhất của interface):
    Ở file combatsystem.py, ta có def deal_damage() nhận target là IAttackable:
        def deal_damage(target: IAttackable, amount: int, dtype: str):
            target.take_damage(amount, dtype)
        # Gọi được với BẤT KỲ entity nào implement IAttackable:
        deal_damage(titan, 60, 'normal')
        deal_damage(wall_section, 200, 'ram')
        deal_damage(cannon_tower, 40, 'stomp')
    """

    @abstractmethod
    def take_damage(self, amount: int, dtype: str):
        """
        Nhận damage từ một nguồn tấn công.
        Quan tâm là có hàm take_damage() là được.
        Muốn thêm các hiệu ứng thì chỉ cần thêm mà thay đổi dtype thôi, không cần thêm method mới.
        Args:
            amount (int): Lượng damage thô trước khi tính giáp/buff.
            dtype  (str): Loại damage — xác định cách tính và hiệu ứng đi kèm giảm giáp.
                Ví dụ Các giá trị hợp lệ:
                'normal'     — bị ArmoredTitan chặn 60%
                'anti_armor' — xuyên giáp hoàn toàn
                'ice'        — apply FrozenDecorator slow 40%
                'fire'       — apply BurnDecorator DoT
                'odm'        — crit 15%, instant kill HP<30%
                'slash'      — damage thường từ Commander
                'ram'        — ×3 vào tường (ShoulderRamStrategy)
                'aoe'        — vùng rộng, không bị block
                'pierce'     — xuyên 3 Titan thẳng hàng
                'stomp'      — damage + stun tháp 160px

        Hướng dẫn code trong class con:
            1. Kiểm tra dtype để tính hệ số giảm giáp:
                   if dtype == 'anti_armor': multiplier = 1.0
                   elif dtype == 'normal' and self._armored: multiplier = 0.4
                   else: multiplier = 1.0
            2. Trừ HP: self._hp -= int(amount * multiplier)
            3. Nếu HP <= 0: gọi self.on_death()

        KHÔNG được làm:
            - KHÔNG tự set self._hp = 0 từ bên ngoài.
            - KHÔNG bỏ qua dtype (dù chưa dùng thì để comment TODO).
        """
        ...


# ---------------------------------------------------------------------------
# IMovable
# ---------------------------------------------------------------------------

class IMovable(ABC):
    """
    Hợp đồng: "Tôi có thể di chuyển đến một tọa độ."

    Ai implement:
        Titan, Commander, Soldier

    Ai GỌI move():
        - Titan AI logic       → self.move(hq_position)
        - SoldierStateMachine  → soldier.move(tower_position)
        - PlayerInputHandler   → commander.move(new_pos)

    Ví dụ:
        titan.move((500, 300))       # Titan tiến về HQ
        scout.move(tower.position)   # Scout về tháp hồi phục
    """

    @abstractmethod
    def move(self, destination: tuple):
        """
        Di chuyển entity về phía destination trong 1 frame.

        Args:
            destination (tuple): Tọa độ đích (x, y) dạng pixel.

        Hướng dẫn code:
            1. Tính vector từ vị trí hiện tại đến destination.
            2. Normalize vector (chia cho độ dài).
            3. Nhân với self._speed * dt để có delta di chuyển.
            4. Cộng delta vào self.x, self.y.

            Ví dụ:
                dx = destination[0] - self.x
                dy = destination[1] - self.y
                dist = (dx**2 + dy**2) ** 0.5
                if dist > 0:
                    self.x += (dx / dist) * self._speed * dt
                    self.y += (dy / dist) * self._speed * dt

        Lưu ý: dt (delta time) nên được truyền vào update(dt) rồi
            move() gọi bên trong update() — không truyền dt qua move().
        """
        ...


# ---------------------------------------------------------------------------
# ISkillUser
# ---------------------------------------------------------------------------

class ISkillUser(ABC):
    """
    Hợp đồng: "Tôi có thể dùng skill và có cooldown."

    Ai implement:
        Commander (Eren, Mikasa, Levi, Armin, Hange)

    Ai GỌI:
        - PlayerInputHandler → commander.use_skill('Q') khi người chơi bấm Q
        - HUD                → commander.get_cooldown('R') để hiển thị cooldown bar

    Ví dụ:
        if input_handler.key_pressed('Q'):
            if commander.get_cooldown('Q') == 0.0:
                commander.use_skill('Q')
    """

    @abstractmethod
    def use_skill(self, skill_id: str):
        """
        Kích hoạt skill theo ID.

        Args:
            skill_id (str): Chỉ nhận 'Q', 'E', hoặc 'R'.

        Hướng dẫn code:
            1. Kiểm tra cooldown: if self._cooldowns[skill_id] > 0: return
            2. Gọi method skill tương ứng: self._activate_skill(skill_id)
            3. Đặt lại cooldown: self._cooldowns[skill_id] = SKILL_COOLDOWNS[skill_id]

        KHÔNG nhận giá trị skill_id ngoài 'Q', 'E', 'R' —
            raise ValueError nếu nhận giá trị khác.
        """
        ...

    @abstractmethod
    def get_cooldown(self, skill_id: str) -> float:
        """
        Trả về số giây cooldown còn lại của skill.

        Args:
            skill_id (str): 'Q', 'E', hoặc 'R'.

        Returns:
            float: Giây còn lại. 0.0 nếu skill đã sẵn sàng dùng.

        Hướng dẫn code:
            return max(0.0, self._cooldowns.get(skill_id, 0.0))

        Dùng ở đâu:
            - HUD vẽ cooldown bar: ratio = commander.get_cooldown('Q') / MAX_CD_Q
            - AI check trước khi dùng skill tự động.
        """
        ...


# ---------------------------------------------------------------------------
# IUpgradable
# ---------------------------------------------------------------------------

class IUpgradable(ABC):
    """
    Hợp đồng: "Tôi có thể được nâng cấp và có giá upgrade."

    Ai implement:
        Tower, Building, Commander

    Ai GỌI:
        - UI/Player     → tower.upgrade() khi người chơi bấm nút Upgrade
        - HUD           → tower.get_upgrade_cost() để hiển thị giá

    Ví dụ:
        cost = cannon_tower.get_upgrade_cost()
        if resource_manager.can_afford(cost):
            cannon_tower.upgrade()
        else:
            hud.show_warning("Không đủ tài nguyên!")
    """

    @abstractmethod
    def upgrade(self):
        """
        Nâng cấp lên level tiếp theo.

        Hướng dẫn code:
            1. Lấy cost: cost = self.get_upgrade_cost()
            2. Gọi ResourceManager.spend(cost) — nếu không đủ sẽ raise
               InsufficientResourceError (để caller bắt).
            3. Tăng self._level += 1
            4. Cập nhật stats theo level mới (damage, range, HP…).

        KHÔNG tự kiểm tra tài nguyên bằng if/else —
            để ResourceManager raise exception, caller xử lý.
        """
        ...

    @abstractmethod
    def get_upgrade_cost(self) -> "ResourceBundle":
        """
        Trả về giá để nâng lên level TIẾP THEO (không phải level hiện tại).

        Returns:
            ResourceBundle: Chi phí tài nguyên để upgrade.

        Hướng dẫn code:
            Dùng lookup table theo level:
                UPGRADE_COSTS = {
                    1: ResourceBundle(stone=50, wood=20),
                    2: ResourceBundle(stone=80, ore=15),
                }
                return UPGRADE_COSTS.get(self._level, ResourceBundle())

        Dùng ở đâu:
            - UI hiển thị nút upgrade kèm giá.
            - AI quyết định có nên upgrade không.
        """
        ...


# ---------------------------------------------------------------------------
# IProducible
# ---------------------------------------------------------------------------

class IProducible(ABC):
    """
    Hợp đồng: "Tôi sản xuất tài nguyên theo chu kỳ."

    Ai implement:
        Farm, StoneWorkshop, GasStorage, Forge, TrainingCamp, RepairStation

    Ai GỌI:
        - Building.update() → gọi self.produce() mỗi khi hết chu kỳ
          rồi cộng vào self._stock (KHÔNG tự cộng trong produce())

    Ví dụ flow:
        # Trong Building.update(dt):
        self._timer += dt
        if self._timer >= self.CYCLE_TIME:
            self._timer = 0.0
            self._stock += self.produce()   # ← produce() chỉ TRẢ VỀ, không cộng
    """

    @abstractmethod
    def produce(self) -> "ResourceBundle":
        """
        Tính và trả về lượng tài nguyên sản xuất trong 1 chu kỳ.

        Returns:
            ResourceBundle: Lượng tài nguyên tạo ra.

        QUAN TRỌNG:
            KHÔNG tự cộng vào kho bên trong method này.
            Building.update() sẽ cộng vào self._stock sau khi nhận kết quả.

        Hướng dẫn code (ví dụ Farm):
            def produce(self) -> ResourceBundle:
                return ResourceBundle(food=10 * self._level)

        Hướng dẫn code (ví dụ StoneWorkshop):
            def produce(self) -> ResourceBundle:
                return ResourceBundle(stone=8 * self._level)
        """
        ...


# ---------------------------------------------------------------------------
# ILootable
# ---------------------------------------------------------------------------

class ILootable(ABC):
    """
    Hợp đồng: "Tôi có thể được thu thập bởi Scout trong Dispatch System."

    Ai implement:
        LootNode (điểm tài nguyên ngoài thành)

    Ai GỌI:
        - DispatchManager → loot_node.collect(scout) khi Scout đứng đủ thời gian

    Ví dụ:
        # Trong DispatchManager khi Scout đến điểm:
        if scout.time_at_node >= loot_node.collect_time:
            bundle = loot_node.collect(scout)
            resource_manager.earn(bundle)
    """

    @abstractmethod
    def collect(self, collector) -> "ResourceBundle":
        """
        Scout đứng đủ thời gian → gọi collect() để lấy tài nguyên.

        Args:
            collector: Scout đang thu thập (dùng để tính bonus nếu có).

        Returns:
            ResourceBundle: Tài nguyên thu được. Trả về ResourceBundle()
                rỗng nếu node đã hết hoặc bị Titan phá.

        Hướng dẫn code:
            1. Kiểm tra self._remaining > 0.
            2. Tính lượng loot (có thể random theo loot_tables.json).
            3. Trừ self._remaining.
            4. Nếu self._remaining <= 0: self.is_alive = False (node cạn kiệt).
            5. return ResourceBundle(wood=amount).
        """
        ...
