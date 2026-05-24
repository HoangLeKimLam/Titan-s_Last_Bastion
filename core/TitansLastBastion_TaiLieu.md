# Titan's Last Bastion — Tài Liệu Tổng Hợp OOP

> **Học phần:** Lập Trình Hướng Đối Tượng (OOP) — Học kỳ 2, 2026  
> **Nhóm Trưởng:** Hoàng Lê Kim Lâm — MSSV: 25520974  
> **Thành Viên:** Võ Nguyễn Minh Long — MSSV: 25521057  
> **Thành Viên:** Đỗ Minh Nhật — MSSV: 25521305  
> **Lớp:** TTNT2025  

---

## I. Tổng Quan Game

**Thể loại:** 2D Top-down Tower Defense + Quản Lý Công Trình + Điều Khiển Tướng Trực Tiếp  
**Engine:** Python 3.x + Pygame  
**Quy mô:** ~2800 dòng · ~50 class · 7 Design Patterns · 5 màn + 1 tutorial

### Cơ chế cốt lõi

- Bản đồ: 3 vòng tường tròn đồng tâm — Wall Maria (ngoài), Wall Rose (giữa), Wall Sina (trong). Trụ sở HQ nằm ở tâm.
- **Persistent State:** Map KHÔNG reset giữa các màn. Tường bị phá, lính chết, công trình hỏng — giữ nguyên sang màn sau. Sửa chữa bằng tài nguyên.
- **Titan tấn công theo wave** từ bên ngoài mỗi màn.
- **Tướng Quân** điều khiển WASD + Q/E/R bên trong thành. Tab chuyển chế độ quản lý tháp/lính.
- **Điều kiện thua:** Khác nhau từng màn, tăng dần độ khắt khe từ màn 1 → 5.
- **Thua màn:** mất 20% tài nguyên + Tướng -1 level. Chơi lại ngay với nguyên trạng thiệt hại.

---

## II. Cấu Trúc Thư Mục

```
titans_last_bastion/
├── main.py                     # Entry point — khởi tạo Pygame, game loop chính
├── constants.py                # W, H, FPS, màu sắc, đường dẫn tài sản
├── save.json                   # Tự sinh khi chơi — lưu GameState serialized
│
├── core/                       # Nền tảng — KHÔNG import từ nơi khác
│   ├── entity.py               # Entity(ABC) — id, x, y, update(dt), draw(screen)
│   ├── interfaces.py           # IAttackable · IMovable · ISkillUser · IUpgradable · IProducible · ILootable
│   ├── game_state.py           # ResourceBundle (@dataclass) + GameState + save()/load()
│   ├── game_manager.py         # GameManager Singleton — phase · wave · win/lose
│   ├── event_bus.py            # GameEventBus Singleton — publish/subscribe Observer
│   └── exceptions.py           # InsufficientResourceError · WallBreachError
│
├── characters/
│   ├── titans/
│   │   ├── titan.py            # Titan(ABC) + RegularTitan + ArmoredTitan + CrawlerTitan + AberrantTitan (gộp 1 file)
│   │   ├── boss.py             # ColossalTitan · BeastTitan · FoundingTitan (3 phase)
│   │   └── attackstrategy.py   # WallPunchStrategy · ShoulderRamStrategy · HookClimbStrategy · AoeSlamStrategy
│   │
│   ├── commanders/
│   │   ├── commander.py        # Commander(ABC) — ISkillUser + IUpgradable
│   │   ├── eren.py             # ErenCommander — Q:SlashCombo · E:ODMSurge · R:TitanForm
│   │   ├── mikasa.py           # MikasaCommander — Q:BladeStorm · E:ArmorPierce · R:AckermanRage
│   │   ├── levi.py             # LeviCommander — Q:Counter · E:NapeLock · R:CaptainBuff
│   │   ├── armin.py            # ArminCommander — Q:FlashBomb · E:TacticalMine · R:FormationOrder
│   │   └── hange.py            # HangeCommander — Q:FreezeTrap · E:AcidSpray · R:TitanSerum
│   │
│   ├── soldiers/
│   │   ├── soldier.py          # Soldier(ABC) + GarrisonSoldier + ScoutSoldier + SpearmanSoldier + RiflemanSoldier + MedicSoldier (gộp 1 file)
│   │   └── attackstrategy.py   # MeleeAttackStrategy · ODMSwingStrategy · PiercingThrowStrategy · SuppressiveFireStrategy
│   │
│   └── weapons/
│       └── weapon.py           # Weapon(ABC) + Blade + ODMGear + Spear + SlowBullet (gộp 1 file)
│
├── structures/
│   ├── wall/
│   │   ├── wall.py             # Wall(Composite) + WallSection(Leaf)
│   │   └── wall_system.py      # Quản lý 3 vòng Maria / Rose / Sina
│   │
│   ├── towers/
│   │   ├── tower.py            # Tower(ABC) + CannonTower + BallistaTower + IceTower + FireTower + GasTrap + EMPTower (gộp 1 file)
│   │   └── attackstrategy.py   # NearestTargeting · StrongestTargeting · FastestTargeting
│   │
│   └── buildings/
│       ├── building.py         # Building(ABC) + Farm + StoneWorkshop + GasStorage + Forge + TrainingCamp + RepairStation (gộp 1 file)
│       └── resource_manager.py # ResourceManager Singleton — earn/spend/can_afford
│
├── systems/
│   ├── combat_system.py        # deal_damage(IAttackable) — đa hình
│   ├── wave_manager.py         # Spawn Titan theo config/wave_config.json
│   ├── soldier_ai.py           # SoldierStateMachine — idle/combat/retreat/reload
│   ├── dispatch_system.py      # DispatchManager Singleton — phái đoàn Scout ngoài thành
│   ├── world_query.py          # WorldQuery helpers — find_in_radius, find_nearest, replace_entity
│   └── input_handler.py        # PlayerInputHandler — đọc WASD, Q, E, R
│
├── patterns/
│   ├── factory.py              # TitanFactory · SoldierFactory · TowerFactory
│   └── decorator.py            # FrozenDecorator · StunnedDecorator · SlowedDecorator · BurnDecorator
│
├── config/
│   ├── wave_config.json        # Titan từng wave từng màn
│   ├── titan_stats.json        # HP / speed / damage theo màn
│   └── loot_tables.json        # Xác suất drop cho LootNode
│
└── assets/
    ├── sprites/                # PNG sprite sheet 64×64/frame
    ├── tiles/                  # Cainos tileset
    └── sounds/                 # SFX + BGM
```

---

## III. Cây Kế Thừa Tổng Thể

```
Entity(ABC)
├── Character(ABC)
│   ├── Titan(ABC)                    ← IAttackable, IMovable
│   │   ├── RegularTitan
│   │   ├── ArmoredTitan
│   │   ├── CrawlerTitan
│   │   ├── AberrantTitan
│   │   ├── JawTitan
│   │   ├── CartTitan
│   │   ├── ColossalTitan             ← Boss màn 3
│   │   ├── BeastTitan                ← Boss màn 4
│   │   └── FoundingTitan             ← Final Boss 3 phase
│   │
│   ├── Commander(ABC)               ← IAttackable, IMovable, ISkillUser, IUpgradable
│   │   ├── ErenCommander
│   │   ├── MikasaCommander
│   │   ├── LeviCommander
│   │   ├── ArminCommander
│   │   └── HangeCommander
│   │
│   └── Soldier(ABC)                 ← IAttackable, IMovable
│       ├── GarrisonSoldier
│       ├── ScoutSoldier
│       ├── SpearmanSoldier
│       ├── RiflemanSoldier
│       └── MedicSoldier
│
└── Structure(ABC)
    ├── Tower(ABC)                   ← IAttackable, IUpgradable
    │   ├── CannonTower
    │   ├── BallistaTower
    │   ├── IceTower
    │   ├── FireTower
    │   ├── GasTrap
    │   └── EMPTower
    │
    ├── Building(ABC)                ← IAttackable, IUpgradable, IProducible
    │   ├── Farm
    │   ├── StoneWorkshop
    │   ├── GasStorage
    │   ├── Forge
    │   ├── TrainingCamp
    │   └── RepairStation
    │
    └── Wall                         ← IAttackable (Composite)
        └── WallSection              ← IAttackable (Leaf)

Weapon(ABC)
├── Blade
├── ODMGear
├── Spear
└── SlowBullet

LootNode(Entity)                     ← ILootable
```

---

## IV. 6 Interfaces — Bản Hợp Đồng

```python
# core/interfaces.py
from abc import ABC, abstractmethod


class IAttackable(ABC):
    """Bất cứ thứ gì có thể bị tấn công."""

    @abstractmethod
    def take_damage(self, amount: int, dtype: str):
        """
        amount: int — lượng damage
        dtype:  str — 'normal' | 'anti_armor' | 'ice' | 'fire' |
                      'odm' | 'slash' | 'aoe' | 'ram' | 'pierce' | 'stomp'
        Class con PHẢI kiểm tra giáp/buff trước khi trừ HP.
        """
        ...


class IMovable(ABC):
    """Bất cứ thứ gì có thể di chuyển."""

    @abstractmethod
    def move(self, destination: tuple):
        """Di chuyển đến tọa độ đích."""
        ...


class ISkillUser(ABC):
    """Bất cứ thứ gì có thể dùng skill."""

    @abstractmethod
    def use_skill(self, skill_id: str):
        """skill_id chỉ nhận: 'Q', 'E', hoặc 'R'."""
        ...

    @abstractmethod
    def get_cooldown(self, skill_id: str) -> float:
        """Trả về giây cooldown còn lại. 0.0 nếu sẵn sàng."""
        ...


class IUpgradable(ABC):
    """Bất cứ thứ gì có thể nâng cấp."""

    @abstractmethod
    def upgrade(self):
        """Nâng lên level tiếp theo. Tự kiểm tra tài nguyên."""
        ...

    @abstractmethod
    def get_upgrade_cost(self) -> "ResourceBundle":
        """Giá nâng lên level TIẾP THEO."""
        ...


class IProducible(ABC):
    """Bất cứ thứ gì có thể sản xuất tài nguyên."""

    @abstractmethod
    def produce(self) -> "ResourceBundle":
        """
        Tính và trả về lượng sản xuất 1 chu kỳ.
        KHÔNG tự cộng vào kho — update() sẽ làm việc đó.
        """
        ...


class ILootable(ABC):
    """Bất cứ thứ gì có thể được thu thập bởi Scout."""

    @abstractmethod
    def collect(self, collector) -> "ResourceBundle":
        """Scout đứng đủ thời gian → gọi collect()."""
        ...
```

---

## V. ResourceBundle — Túi Tài Nguyên

```python
# core/game_state.py
from dataclasses import dataclass


@dataclass
class ResourceBundle:
    """Túi tài nguyên. Hỗ trợ +, *, >= để code gọn."""

    wood:            int = 0
    stone:           int = 0
    gas:             int = 0
    food:            int = 0
    ore:             int = 0
    crystal:         int = 0
    serum:           int = 0
    anti_armor_bolt: int = 0

    def __add__(self, other: "ResourceBundle") -> "ResourceBundle":
        """r1 + r2 — cộng 2 túi (khi loot về kho)."""
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

    def __mul__(self, factor: float) -> "ResourceBundle":
        """r * 0.8 — penalty mất 20% khi thua màn."""
        return ResourceBundle(
            wood  = int(self.wood  * factor),
            stone = int(self.stone * factor),
            gas   = int(self.gas   * factor),
            food  = int(self.food  * factor),
        )

    def __ge__(self, cost: "ResourceBundle") -> bool:
        """r >= cost — kiểm tra đủ tài nguyên để xây/upgrade."""
        return (
            self.wood            >= cost.wood
            and self.stone       >= cost.stone
            and self.gas         >= cost.gas
            and self.food        >= cost.food
            and self.ore         >= cost.ore
            and self.crystal     >= cost.crystal
            and self.serum       >= cost.serum
        )
```

---

## VI. GameEventBus — Observer Singleton

```python
# core/event_bus.py
from typing import Callable, Dict, List


class GameEventBus:
    """Singleton Observer — các class thông báo sự kiện mà không biết nhau."""

    _instance = None

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    @classmethod
    def get_instance(cls) -> "GameEventBus":
        if cls._instance is None:
            cls._instance = GameEventBus()
        return cls._instance

    def subscribe(self, event: str, callback: Callable):
        """Đăng ký lắng nghe. Gọi 1 lần khi khởi tạo hệ thống."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def publish(self, event: str, data=None):
        """Phát sự kiện đến tất cả subscriber."""
        for callback in self._listeners.get(event, []):
            callback(data)
```

### Events chuẩn

| Event | Ai publish | Ai subscribe |
|---|---|---|
| `'wall_breached'` | WallSection | HUD, Camera, WaveManager, Audio |
| `'titan_died'` | Titan.on_death() | ResourceManager, WaveManager |
| `'soldier_died'` | Soldier.on_death() | ResourceManager, HUD |
| `'building_destroyed'` | Building.take_damage() | ResourceManager, HUD |
| `'tower_destroyed'` | Tower.take_damage() | HUD, lính tại tháp rút lui |
| `'wave_started'` | WaveManager | HUD, Audio |
| `'game_over'` | GameManager | UI, Audio |

---

## VII. Titan & Boss

### Nguyên tắc AI Titan

- Titan **spawn là tiến ngay** — không đứng chờ.
- Mục tiêu cuối luôn là **HQ ở tâm**.
- Titan phá tường, hạ lính, phá tháp chỉ vì chúng **cản đường vào HQ**.
- **3 cấp độ:** Titan Quèn (nhiều) → Titan Trâu/Elite (thỉnh thoảng, mạnh 2–3×) → Boss cuối màn.

### Thứ tự ưu tiên mục tiêu

```
1. HQ — nếu đã vào được Sina
2. WallSection — đang cản đường vào HQ
3. Tower / Soldier — đang tấn công mình
4. Fallback: luôn tiến về HQ
```

### Titan cụ thể

| Class | File | Đặc điểm | Strategy |
|---|---|---|---|
| `RegularTitan` | titan.py | Đấm thẳng. Berserk HP<30%: speed×1.5 | `WallPunchStrategy` |
| `ArmoredTitan` | titan.py | Giáp chặn 60% damage thường. Override `take_damage()` | `ShoulderRamStrategy` |
| `CrawlerTitan` | titan.py | Leo tường bằng dây, bypass tháp mặt đất | `HookClimbStrategy` |
| `AberrantTitan` | titan.py | Zigzag, dash 4s/lần, khó nhắm | `WallPunchStrategy` |
| `JawTitan` | titan.py | Cắn tường giảm MaxHP vĩnh viễn | `JawBiteStrategy` |
| `CartTitan` | titan.py | Tìm lỗ hổng chui vào | `GapSeekStrategy` |
| `ColossalTitan` | boss.py | Boss M3 — FootStomp stun tháp 3s vùng 160px | `AoeSlamStrategy` |
| `BeastTitan` | boss.py | Boss M4 — RockVolley từ 350px phá tháp | riêng trong class |
| `FoundingTitan` | boss.py | Final Boss — 3 phase. Phase 3 cần Serum Fragment | riêng trong class |

### FoundingTitan — 3 Phase

| Phase | Điều kiện | Hành vi |
|---|---|---|
| Phase 1 | HP > 60% | TremorCharge liên tục |
| Phase 2 | HP 20–60% | Summon 8 minion |
| Phase 3 | HP < 20% + có Serum | Lõi lộ ra, focus 10s để thắng |

### Attack Strategy Titan

```python
# characters/titans/attackstrategy.py

class TitanAttackStrategy(ABC):
    @abstractmethod
    def execute(self, attacker, target: IAttackable):
        ...

class WallPunchStrategy(TitanAttackStrategy):
    def execute(self, attacker, target):
        target.take_damage(amount=attacker._damage, dtype='normal')

class ShoulderRamStrategy(TitanAttackStrategy):
    def execute(self, attacker, target):
        target.take_damage(amount=attacker._damage * 3, dtype='ram')

class HookClimbStrategy(TitanAttackStrategy):
    def execute(self, attacker, target):
        target.take_damage(amount=attacker._damage, dtype='climb')
        attacker.x = target.x + 60    # bypass tường

class AoeSlamStrategy(TitanAttackStrategy):
    STOMP_RADIUS  = 160
    STUN_DURATION = 3.0

    def execute(self, attacker, target):
        target.take_damage(amount=attacker._damage, dtype='stomp')
        towers = WorldQuery.find_in_radius(
            cx=attacker.x, cy=attacker.y,
            radius=self.STOMP_RADIUS, entity_type='tower'
        )
        for tower in towers:
            tower.stun(self.STUN_DURATION)
```

---

## VIII. Lính — Soldier

### Cơ chế đóng quân tại tháp

```
Train tại TrainingCamp
    → điều phối đến tháp cụ thể
        → chiến đấu trong tầm nhất định quanh tháp
            → HP < 30% hoặc hết vũ khí → retreat về tháp
                → hồi máu + nạp vũ khí
                    → quay lại chiến đấu
```

Trên đường về có tỉ lệ bị Titan tấn công.

### 5 Loại Lính

| Class | HP | Tầm | Vũ Khí | Đặc điểm |
|---|---|---|---|---|
| `GarrisonSoldier` | 120 | 60px | Blade | Shield Block khi HP<50% — chặn 1 đòn |
| `ScoutSoldier` | 80 | 220px | ODMGear | ду dây đến gáy Titan, 15% crit instant kill |
| `SpearmanSoldier` | 95 | 180px | Spear | Xuyên 3 Titan thẳng hàng |
| `RiflemanSoldier` | 70 | 250px | SlowBullet | Slow target 30% trong 3s |
| `MedicSoldier` | 65 | — | — | Hồi 15HP/s cho lính trong 100px, không tấn công |

### SoldierStateMachine

```
IDLE → COMBAT → RETREAT → RELOAD → COMBAT
                  ↑                    ↓
               HP<30% hoặc hết vũ khí   Đủ máu + đủ đạn
```

### Attack Strategy Lính

```python
# characters/soldiers/attackstrategy.py

class SoldierAttackStrategy(ABC):
    @abstractmethod
    def execute(self, soldier, target: IAttackable):
        ...

class MeleeAttackStrategy(SoldierAttackStrategy):
    """GarrisonSoldier dùng."""
    def execute(self, soldier, target):
        soldier._weapon.use(target)

class ODMSwingStrategy(SoldierAttackStrategy):
    """ScoutSoldier dùng — kiểm tra gas trước."""
    def execute(self, soldier, target):
        if soldier._weapon.has_ammo():
            soldier._weapon.use(target)

class PiercingThrowStrategy(SoldierAttackStrategy):
    """SpearmanSoldier — xuyên qua hàng Titan."""
    def execute(self, soldier, target):
        soldier._weapon.use(target)
        # Logic xuyên thêm 2 Titan phía sau

class SuppressiveFireStrategy(SoldierAttackStrategy):
    """RiflemanSoldier — 5 phát liên tiếp."""
    def execute(self, soldier, target):
        for _ in range(5):
            if soldier._weapon.has_ammo():
                soldier._weapon.use(target)
```

---

## IX. Tướng Quân — Commander

### Cơ chế

- Chỉ hoạt động **bên trong thành** trong pha chiến đấu.
- **WASD** di chuyển. **Q/E/R** dùng skill. **Tab** chuyển chế độ quản lý.
- **HAS-A** PlayerInputHandler (đọc bàn phím).
- Thua màn: -1 level (min lv1). Level 1–10, mỗi level +5% stats.

### 5 Tướng Quân

| Tướng | Màn | Q | E | R |
|---|---|---|---|---|
| ErenCommander | 1 | Slash Combo AoE 80px — 3 nhát × 40dmg | ODM Surge — lao tới, stun 1.5s | Titan Form 10s bất tử + AoE 150px |
| MikasaCommander | 2 | Blade Storm 360° | Armor Pierce — xuyên giáp hoàn toàn | Ackerman Rage speed×2, cooldown=0 trong 8s |
| LeviCommander | 3 | Counter — reflect 200% dmg nhận 1.5s | Nape Lock — 25% instant kill | Captain Buff — Garrison +50% atk 15s |
| ArminCommander | 4 | Flash Bomb — Titan mù 4s bỏ target | Tactical Mine — bẫy stun AoE 3s | Formation Order — lính DPS×3 trong 10s |
| HangeCommander | 5 | Freeze Trap — đóng băng 5s | Acid Spray — tan giáp + DoT 8s | Titan Serum — Titan quay đánh đồng loại 12s |

### Khung skill Commander

```python
# characters/commanders/levi.py

class LeviCommander(Commander):

    SKILL_COOLDOWNS = {
        'Q': 6.0,
        'E': 10.0,
        'R': 25.0,
    }

    def _activate_skill(self, skill_id: str):
        if   skill_id == 'Q': self._counter()
        elif skill_id == 'E': self._nape_lock()
        elif skill_id == 'R': self._captain_buff()

    def _counter(self):
        """Q — reflect 200% damage nhận trong 1.5s tiếp theo."""
        self._counter_active = True
        self._counter_timer  = 1.5

    def _nape_lock(self):
        """E — 25% instant kill Titan gần nhất trong 100px."""
        import random
        target = WorldQuery.find_nearest(
            cx=self.x, cy=self.y,
            entity_type='titan', max_range=100
        )
        if target is not None:
            if random.random() < 0.25:
                target.take_damage(amount=target._hp, dtype='slash')
            else:
                target.take_damage(amount=80, dtype='slash')

    def _captain_buff(self):
        """R — Garrison trong 200px +50% atk trong 15 giây."""
        soldiers = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=200, entity_type='soldier'
        )
        for s in soldiers:
            if hasattr(s, '_weapon') and s._weapon is not None:
                s._weapon._damage = int(s._weapon._damage * 1.5)
                s._buff_timer     = 15.0
```

---

## X. Vũ Khí — Weapon

```python
# characters/weapons/weapon.py

class Weapon(ABC):
    """Cha của mọi vũ khí. Lính HAS-A weapon này."""

    def __init__(self, max_ammo: int):
        self._ammo     = max_ammo
        self._max_ammo = max_ammo

    def has_ammo(self) -> bool:
        return self._ammo > 0

    def reload(self):
        """Gọi khi lính về tháp."""
        self._ammo = self._max_ammo

    def get_ammo_percent(self) -> float:
        return self._ammo / self._max_ammo

    @abstractmethod
    def use(self, target) -> int:
        """Dùng vũ khí. Trả về damage. Tự trừ ammo."""
        ...
```

| Class | Ammo | Damage | dtype | Đặc điểm |
|---|---|---|---|---|
| `Blade` | ∞ | 20 | `'normal'` | Cận chiến, không hết |
| `ODMGear` | 100 gas | 45 | `'odm'` | 5 gas/lần ду. 15% crit instant kill |
| `Spear` | 10 | 30 | `'pierce'` | Xuyên 3 Titan thẳng hàng |
| `SlowBullet` | 30 | 18 | `'normal'` | Apply SlowedDecorator slow 30% / 3s |

---

## XI. Tường — Wall Composite Pattern

```python
# structures/wall/wall.py

class WallSection(Entity, IAttackable):
    """Leaf — 1 đoạn tường nhỏ. Có HP riêng."""

    def take_damage(self, amount: int, dtype: str):
        self._hp -= amount
        if self._hp <= 0:
            self.is_alive = False
            GameEventBus.get_instance().publish(
                'wall_breached',
                {'wall': self._parent, 'section': self}
            )


class Wall(Entity, IAttackable):
    """Composite — chứa nhiều WallSection.

    Gọi wall.take_damage(100, pos=(x,y)) →
    Wall tự tìm section gần pos nhất → trừ HP section đó.
    """

    def take_damage(self, amount: int, dtype: str = 'normal', pos: tuple = None):
        section = self._find_nearest_section(pos)
        if section is not None:
            section.take_damage(amount, dtype)

    def is_destroyed(self) -> bool:
        return all(not s.is_alive for s in self._sections)

    def get_hp_percent(self) -> float:
        total     = sum(s._hp     for s in self._sections)
        total_max = sum(s._max_hp for s in self._sections)
        return total / total_max if total_max > 0 else 0.0

    def repair_all(self, amount: int):
        """RepairStation gọi mỗi wave."""
        for s in self._sections:
            s.repair(amount)
```

### 3 vòng tường

| Tường | Vị trí | Ý nghĩa khi bị phá |
|---|---|---|
| Wall Maria | Ngoài cùng | Titan vào vùng giữa |
| Wall Rose | Giữa | Titan vào vùng nội thành |
| Wall Sina | Trong cùng | Titan tấn công HQ và công trình |

---

## XII. Tháp — Tower

### Tower Base

```python
# structures/towers/tower.py

class Tower(Entity, IAttackable, IUpgradable):
    """HAS-A TowerTargetingStrategy."""

    def update(self, dt: float):
        if self._stun_timer > 0:
            self._stun_timer -= dt
            return             # stun → không bắn
        self._shoot_timer -= dt
        if self._shoot_timer <= 0:
            target = self._pick_target()
            if target is not None:
                self.shoot(target)
                self._shoot_timer = self._cooldown

    def shoot(self, target: IAttackable):
        """Class con override để thêm hiệu ứng."""
        target.take_damage(amount=self._damage, dtype='normal')

    def stun(self, duration: float):
        """ColossalTitan FootStomp gọi."""
        self._stun_timer = duration
```

### 6 Loại Tháp

| Class | Damage | Range | Skill | Cần tài nguyên |
|---|---|---|---|---|
| `CannonTower` | 60 AoE | 200px | Stun Shell — stun 2s, cd 15s | 50 stone + 20 wood |
| `BallistaTower` | 80 xuyên | 280px | Anti-Armor Bolt xuyên giáp | 40 stone + 30 ore |
| `IceTower` | 20 | 180px | Blizzard AoE đóng băng 4s | 60 stone + 20 crystal |
| `FireTower` | DoT | 200px | Inferno 300px | 45 stone + 25 gas |
| `GasTrap` | AoE | passive | Smoke Screen — Titan mất target 8s | 30 gas + 20 wood |
| `EMPTower` | — | 200px | EMP Burst — disable tháp bị Beast 5s | 50 ore + 30 stone |

### Tower Targeting Strategy

```python
# structures/towers/attackstrategy.py

class TowerTargetingStrategy(ABC):
    @abstractmethod
    def select_target(self, tower, titans: list):
        """Chọn 1 Titan để tháp tấn công."""
        ...

class NearestTargeting(TowerTargetingStrategy):
    """Titan gần tháp nhất — CannonTower mặc định."""
    def select_target(self, tower, titans):
        return min(titans, key=lambda t: (t.x-tower.x)**2 + (t.y-tower.y)**2)

class StrongestTargeting(TowerTargetingStrategy):
    """Titan HP cao nhất — BallistaTower."""
    def select_target(self, tower, titans):
        return max(titans, key=lambda t: t._hp)

class FastestTargeting(TowerTargetingStrategy):
    """Titan nhanh nhất — IceTower."""
    def select_target(self, tower, titans):
        return max(titans, key=lambda t: t._speed)
```

---

## XIII. Công Trình — Building

### Cơ chế sản xuất tài nguyên

- Tự sản xuất theo timer khi game đang chạy.
- **Tắt game = dừng sản xuất** — không tính offline.
- Thu hoạch trong pha chuẩn bị.
- Bị Titan phá nếu chúng lọt vào Sina.

### 6 Công Trình (từ đề xuất)

| Class | Chu kỳ | Sản xuất | Vai trò |
|---|---|---|---|
| `Farm` | 60s | 10 food | Nuôi lính — mất Farm = không train được |
| `StoneWorkshop` | 90s | 8 stone | Xây tháp, sửa tường đá |
| `GasStorage` | 75s | 15 gas | Gas cho Scout ODMGear và FireTower |
| `Forge` | — | Anti-Armor Bolt | Đúc đạn từ Đá + Ore. Cần Ballista xuyên giáp |
| `TrainingCamp` | theo loại | Lính mới | Tuyển Garrison và Scout, tốn lương thực |
| `RepairStation` | 1/wave | Sửa 50 HP/section | Tự sửa tường chậm — giảm áp lực thủ công |

### Building Base

```python
# structures/buildings/building.py

class Building(Entity, IAttackable, IUpgradable, IProducible):

    CYCLE_TIME      = 60.0    # giây — class con override
    PRODUCTION_RATE = 0       # class con override

    def update(self, dt: float):
        if not self.is_alive:
            return
        self._timer += dt
        if self._timer >= self.CYCLE_TIME:
            self._timer  = 0.0
            self._stock += self.produce()

    def produce(self) -> ResourceBundle:
        """IProducible — class con override."""
        return ResourceBundle()

    def harvest(self) -> ResourceBundle:
        """Lấy _stock ra, reset về 0."""
        out         = self._stock
        self._stock = ResourceBundle()
        return out
```

---

## XIV. ResourceManager — Singleton

```python
# structures/buildings/resource_manager.py

class ResourceManager:
    """Kho tài nguyên duy nhất. Mọi class gọi get_instance()."""

    _instance = None

    @classmethod
    def get_instance(cls) -> "ResourceManager":
        if cls._instance is None:
            cls._instance = ResourceManager()
        return cls._instance

    def earn(self, bundle: ResourceBundle):
        self._stock += bundle

    def spend(self, cost: ResourceBundle) -> bool:
        if not self.can_afford(cost):
            return False
        # trừ từng loại
        return True

    def can_afford(self, cost: ResourceBundle) -> bool:
        return self._stock >= cost

    def get_stock(self) -> ResourceBundle:
        return self._stock

    def apply_defeat_penalty(self):
        """Thua màn → mất 20% tài nguyên."""
        self._stock = self._stock * 0.8
```

---

## XV. Hệ Thống Phái Đoàn — Dispatch System

```
Pha chuẩn bị → bản đồ ngoài thành hiện ra
    → Kéo thả Scout vào điểm tài nguyên muốn thu thập
        → Bấm "Phái đi"
            → Scout tự đi và trở về (không điều khiển trực tiếp)
                → Sự kiện ngẫu nhiên: "Đội gặp Titan!"
                    → Chọn trong 5 giây:
                        [Chiến đấu] — 50% cơ hội thắng
                        [Rút lui]   — mất 50% đồ đã kiếm, bảo toàn lính
```

**Nguyên tắc khoảng cách:**
- Điểm gần = ít đồ, an toàn, Titan yếu và ít.
- Điểm xa = nhiều đồ ngon, Titan nhiều.

**Lính chết trong phái đoàn:** mất vĩnh viễn — phải train lại tại TrainingCamp.  
**Nút rút lui:** có thể bấm bất kỳ lúc nào để về sớm.

---

## XVI. Decorator Pattern — Trạng Thái Tạm Thời

```python
# patterns/decorator.py

class FrozenDecorator:
    """Bọc quanh Titan bị đóng băng. Tháo sau khi hết duration."""

    def __init__(self, entity, slow_amount: float, duration: float):
        self._entity     = entity
        self._remaining  = duration
        self._orig_speed = entity._speed
        entity._speed    = entity._speed * (1 - slow_amount)
        # Delegate thuộc tính public
        self.x        = entity.x
        self.y        = entity.y
        self.id       = entity.id
        self.is_alive = entity.is_alive

    def update(self, dt: float):
        self._remaining -= dt
        if self._remaining <= 0:
            self._entity._speed = self._orig_speed
            return self._entity    # trả về entity gốc
        self._entity.update(dt)
        self.x        = self._entity.x
        self.y        = self._entity.y
        self.is_alive = self._entity.is_alive
        return self

    def take_damage(self, amount: int, dtype: str):
        self._entity.take_damage(amount, dtype)
        self.is_alive = self._entity.is_alive


class StunnedDecorator:
    """Titan bị choáng — đứng im, không tấn công."""

    def __init__(self, entity, duration: float):
        self._entity    = entity
        self._remaining = duration
        self.x        = entity.x
        self.y        = entity.y
        self.id       = entity.id
        self.is_alive = entity.is_alive

    def update(self, dt: float):
        self._remaining -= dt
        if self._remaining <= 0:
            return self._entity    # hết choáng
        # KHÔNG gọi entity.update() → Titan không di chuyển
        return self

    def take_damage(self, amount: int, dtype: str):
        self._entity.take_damage(amount, dtype)
        self.is_alive = self._entity.is_alive
```

---

## XVII. Factory Pattern

```python
# patterns/factory.py

class TitanFactory:
    @staticmethod
    def create(titan_type: str, x: float, y: float, config: dict):
        mapping = {
            'regular':  RegularTitan,
            'armored':  ArmoredTitan,
            'crawler':  CrawlerTitan,
            'aberrant': AberrantTitan,
            'colossal': ColossalTitan,
            'beast':    BeastTitan,
            'founding': FoundingTitan,
        }
        cls = mapping.get(titan_type)
        if cls is None:
            raise ValueError(f"Titan type không tồn tại: {titan_type}")
        return cls(x=x, y=y, config=config)


class SoldierFactory:
    @staticmethod
    def create(soldier_type: str, x: float, y: float):
        mapping = {
            'garrison': GarrisonSoldier,
            'scout':    ScoutSoldier,
            'spearman': SpearmanSoldier,
            'rifleman': RiflemanSoldier,
            'medic':    MedicSoldier,
        }
        cls = mapping.get(soldier_type)
        if cls is None:
            raise ValueError(f"Soldier type không tồn tại: {soldier_type}")
        return cls(x=x, y=y)
```

---

## XVIII. Mối Quan Hệ Giữa Các Class

### Kế thừa (IS-A)

| Từ | Đến | Con nhận thêm gì |
|---|---|---|
| Entity | Character | _hp, _speed, take_damage(), move() |
| Character | Titan | _target, _attack_strategy, AI logic |
| Character | Commander | _level, _skill_cd, use_skill() |
| Character | Soldier | _state machine, assign_to_tower() |
| Entity | Tower | _stun_timer, targeting strategy, shoot() |
| Entity | Building | _timer, _stock, produce(), harvest() |

### Composition HAS-A

| Ai chứa | Chứa gì | Lý do không dùng kế thừa |
|---|---|---|
| Commander | PlayerInputHandler | Commander không phải bàn phím |
| ScoutSoldier | ODMGear (Weapon) | Lính CÓ thiết bị, không PHẢI thiết bị |
| GarrisonSoldier | Blade (Weapon) | Vũ khí tự quản lý ammo/reload |
| Titan | TitanAttackStrategy | Đổi cách đánh runtime không sửa class |
| Tower | TowerTargetingStrategy | Đổi chiến lược nhắm runtime |
| Wall | WallSection[] | Composite Pattern |

### Observer

| Publisher | Event | Subscriber |
|---|---|---|
| WallSection | `wall_breached` | HUD, Camera, WaveManager, Audio |
| Titan | `titan_died` | ResourceManager (+thưởng), WaveManager |
| Soldier | `soldier_died` | ResourceManager, HUD |
| Building | `building_destroyed` | ResourceManager, HUD |

---

## XIX. 7 Design Patterns Áp Dụng

| Pattern | Áp dụng ở đâu | Lợi ích |
|---|---|---|
| **Factory** | TitanFactory, SoldierFactory, TowerFactory | Thêm loại mới = 1 class + 1 dòng trong dict |
| **Strategy** | TitanAttackStrategy, TowerTargetingStrategy, SoldierAttackStrategy | Đổi hành vi runtime không sửa class gốc |
| **Observer** | GameEventBus publish/subscribe | Class không biết nhau, loose coupling |
| **State** | SoldierStateMachine (idle/combat/retreat/reload) | AI rõ ràng, thêm state không đụng code cũ |
| **Singleton** | GameManager, ResourceManager, GameEventBus, DispatchManager | Chỉ 1 bản, tránh mâu thuẫn |
| **Composite** | Wall + WallSection | Gọi lệnh trên Wall, tự phân phối xuống Section |
| **Decorator** | FrozenDecorator, StunnedDecorator, SlowedDecorator | Thêm trạng thái tạm thời không sửa class |

---

## XX. Quy Ước Bắt Buộc — Cả Nhóm

### Đặt tên

| Loại | Quy tắc | ✅ Đúng | ❌ Sai |
|---|---|---|---|
| Class | PascalCase | `RegularTitan` | `regularTitan` |
| Method | snake_case | `take_damage()` | `takeDamage()` |
| Thuộc tính public | snake_case | `odm_gear` | `odmGear` |
| Thuộc tính private | `_snake_case` | `_hp` | `hp`, `__hp` |
| Hằng số | `UPPER_SNAKE_CASE` | `MAX_HP = 200` | `maxHp = 200` |
| File | `snake_case.py` | `regular_titan.py` | `RegularTitan.py` |

### Method bắt buộc

| Method | Có trong | Quy tắc |
|---|---|---|
| `update(dt: float)` | Mọi Entity | dt ≈ 0.016s. KHÔNG gọi draw(). |
| `draw(screen)` | Mọi Entity | Tách hoàn toàn khỏi update(). |
| `take_damage(amount: int, dtype: str)` | Mọi IAttackable | Kiểm tra giáp trước. Gọi on_death() nếu HP≤0. |
| `on_death()` | Titan, Soldier, Building | is_alive=False + emit event. KHÔNG gọi thẳng. |
| `use_skill(skill_id: str)` | Commander + ISkillUser | Chỉ nhận 'Q', 'E', 'R'. Tự kiểm tra cooldown. |
| `get_cooldown(skill_id) → float` | Commander + ISkillUser | Trả về 0.0 nếu sẵn sàng. |
| `upgrade()` | Tower, Building, Commander | Tự gọi ResourceManager.spend() bên trong. |
| `get_upgrade_cost() → ResourceBundle` | Tower, Building, Commander | Giá level TIẾP THEO từ level hiện tại. |
| `produce() → ResourceBundle` | Mọi Building | Trả về, KHÔNG tự cộng vào _stock. |
| `harvest() → ResourceBundle` | Mọi Building | Lấy _stock ra, reset về 0. |

### dtype values

| dtype | Gây ra bởi | Ảnh hưởng |
|---|---|---|
| `'normal'` | Cannon, Garrison, Regular attack | Bị ArmoredTitan chặn 60% |
| `'anti_armor'` | Ballista + Anti-Armor Bolt | Xuyên giáp hoàn toàn, giáp vỡ |
| `'ice'` | IceTower, Freeze Trap | Apply FrozenDecorator slow 40% |
| `'fire'` | FireTower, Inferno | Apply BurnDecorator DoT |
| `'odm'` | Scout, Commander ODM | Crit 15%, instant kill HP<30% |
| `'slash'` | Commander skill | Damage thường |
| `'ram'` | ArmoredTitan ShoulderRam | Damage × 3 vào tường |
| `'aoe'` | TitanForm, Blizzard | Vùng rộng, không block |
| `'pierce'` | Spearman | Xuyên 3 Titan thẳng hàng |
| `'stomp'` | ColossalTitan FootStomp | Damage + stun tháp 160px |

### Private rule

| ❌ KHÔNG được | ✅ Phải làm |
|---|---|
| `titan._hp = 0` | `titan.take_damage(titan._hp, 'kill')` |
| `building._stock += bundle` | Để `building.update()` tự cộng |
| `scout.odm_gear._ammo -= 5` | `weapon.use(target)` tự trừ |
| `tower._level = 5` | `tower.upgrade()` × 4 lần |
| `rm._stock.wood = 999` | `rm.earn(ResourceBundle(wood=999))` |

---

## XXI. Tham Khảo

| Tựa game | Điểm tham khảo |
|---|---|
| Clash of Clans | Xây công trình sản xuất, quản lý tài nguyên, upgrade, thủ thành |
| Kingdom Rush | Tower Defense đặt tháp chặn enemy theo lane |
| Attack on Titan Tribute Game | Bối cảnh AoT, cơ chế Titan, tường vòng tròn |
| Darkest Dungeon | Thiệt hại không tự hồi giữa các màn — persistent damage |

---

*Tài liệu tổng hợp từ: Bản Đề Xuất Đồ Án (PDF) + TitansLastBastion_Final.html*  
*Cập nhật lần cuối theo GDD v4.1*
