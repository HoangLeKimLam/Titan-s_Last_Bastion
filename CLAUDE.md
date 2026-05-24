# CLAUDE.md — Hướng dẫn cho Claude khi làm việc với dự án này

> Đây là dự án **Titan's Last Bastion** — một game tower defense theo phong cách Attack on Titan, viết bằng Python + Pygame, được sử dụng làm đồ án môn **Lập trình Hướng đối tượng (OOP)** tại UIT.

## 1. Bối cảnh dự án

- **Ngôn ngữ:** Python 3.10+ (sử dụng type hints, dataclasses, ABC).
- **Framework dự kiến:** Pygame (cho `draw()` và game loop).
- **Mục tiêu sư phạm:** Minh họa các nguyên tắc OOP — kế thừa, đa hình, abstraction, encapsulation — và các Design Pattern (Strategy, Observer/EventBus, Singleton, Decorator).
- **Ngôn ngữ docstring/comment:** Tiếng Việt (giữ nguyên — không dịch sang tiếng Anh).

## 2. Cấu trúc thư mục thực tế

```
d:\UIT\OOPPro\
├── AttackStrategy.py        # Strategy tấn công của Titan + NHÓM 6 (RockProjectile, HeatParticle)
├── Priority.py              # Hệ thống ưu tiên mục tiêu (Strategy Pattern) — 7 bộ + factory
├── Titan_AI.py              # Bộ não tự hành: WorldView + TitanAI (ABC) + 10 AI con + factory
├── Titan.py                 # Titan base + RegularTitan, ArmoredTitan, CrawlerTitan, AberrantTitan, Wolf, TowerHunter, SoldierHunter, Kamikaze
├── Boss.py                  # ColossalTitan, BeastTitan, FoundingTitan
├── Assets/                  # Toàn bộ asset PNG/GIF
│   ├── Boss/                # beast.png, clossal.png, founding.png
│   ├── Titan/               # regular{2,4,5,6,7}.png, wolf.png, towerhunter.png, soldierhunter.png
│   ├── Special/             # armored.png, kamikaze.png
│   ├── Rock/                # Rock Pile - Spritesheet.png
│   └── Explosion Kamikaze/  # explode.gif
├── CHECK/                   # Demo điều khiển tay — *check.py + _demo_dummies.py
├── CHECKAI/                  # Demo AI tự hành — *check_AI.py + _ai_app.py + _ai_dummies.py + _ai_bootstrap.py
└── Titan-s_Last_Bastion/
    └── core/
        ├── entity.py        # Lớp cha Entity (ABC) — id, x, y, is_alive, update(), draw()
        ├── interfaces.py    # IAttackable, IMovable, ISkillUser, IUpgradable, IProducible, ILootable
        ├── event_bus.py     # GameEventBus (Singleton Observer)
        ├── exceptions.py    # InsufficientResourceError, WallBreachError
        └── game_state.py    # ResourceBundle (dataclass), GameState (save/load JSON)
```

> Asset được load bằng `os.path.join(os.path.dirname(__file__), 'Assets', <folder>, <file>)` từ `Titan.py`/`Boss.py` (ở root). File trong `CHECK/` lùi 1 cấp (`dirname(dirname(__file__))`) để trỏ về root trước khi vào `Assets/`.

> Lưu ý: các file `Titan.py`, `Boss.py`, `AttackStrategy.py` ở root **import từ paths giả định** (`core.entity`, `characters.titans.attackstrategy`, `systems.world_query`, …). Cấu trúc package thực sự **chưa được dựng** — đây là code đang trong giai đoạn thiết kế/phác thảo.

## 3. Quy ước code (phải tuân thủ)

### Ngôn ngữ & style
- **Docstring tiếng Việt** — giữ tone giảng dạy hiện có. Khi thêm method mới, viết docstring giải thích "Tại sao", "Ai gọi", "Ví dụ" giống các file hiện tại.
- **PEP 8** — snake_case cho biến/hàm, PascalCase cho class.
- **Type hints bắt buộc** trên mọi signature mới: `def take_damage(self, amount: int, dtype: str) -> None:`.
- **Private attribute** dùng prefix `_` (ví dụ `self._hp`, `self._attack_strategy`).

### Pattern bắt buộc
- **Tách `update(dt)` và `draw(screen)`** — không gọi lẫn nhau. `update` chỉ đụng logic, `draw` chỉ render.
- **Mọi entity kế thừa `Entity`** và gọi `super().__init__(x, y)` để có `id`, `x`, `y`, `is_alive`.
- **Đa hình qua interface** — hàm nhận `IAttackable` thay vì class cụ thể.
- **Strategy Pattern** — Titan HAS-A `_attack_strategy`, không tự code logic đánh. Đổi cách đánh = đổi strategy (kể cả runtime, ví dụ berserk).
- **Observer/EventBus** — không hardcode coupling. Dùng `GameEventBus.get_instance().publish(event, data)` cho các sự kiện như `titan_died`, `wall_breached`.
- **Singleton** — `GameEventBus`, `ResourceManager`, `WaveManager` đều lấy qua `get_instance()`, không khởi tạo trực tiếp.

### Immutability cho data
- `ResourceBundle` là dataclass — toán tử `+`, `*` luôn **trả về object mới**, không mutate `self`.
- Khi cần "cập nhật" stock: `self._stock = self._stock + loot` (không có `+=` in-place semantic).

### Exception
- Dùng exception custom trong `core/exceptions.py` thay vì `ValueError` chung chung.
- `ResourceManager.spend()` raise `InsufficientResourceError`, caller bắt rồi hiển thị HUD.

## 4. Việc Claude nên làm / không nên làm

### Nên
- Khi user yêu cầu thêm Titan/Tower/Strategy mới → tuân theo template hiện có (`class XxxStrategy(TitanAttackStrategy)` với `execute(self, attacker, target)`).
- Khi sửa method có `pass` ở cuối hoặc docstring "Hướng dẫn code" → triển khai theo đúng hướng dẫn trong docstring.
- Giữ docstring tiếng Việt khi sửa file.

### Không nên
- **Không tự ý refactor** cấu trúc package (chuyển `Titan.py` vào `characters/titans/`) trừ khi user yêu cầu — code hiện tại đang ở giai đoạn đặt nền móng.
- **Không xóa docstring dài** — chúng phục vụ mục đích giảng dạy.
- **Không thêm tính năng ngoài scope** (networking, AI nâng cao, save slot phức tạp) trừ khi user yêu cầu rõ.
- **Không dịch comment/docstring sang tiếng Anh.**

## 5. Modules còn thiếu (sẽ được tạo sau)

Các module được tham chiếu nhưng chưa tồn tại — nếu cần kiểm thử/đoán hành vi, đây là chữ ký dự kiến:

- `systems/world_query.py` — `WorldQuery.get_headquarters()`, `find_blocking_wall(self, hq)`, `find_nearest_attacker(self)`, `find_in_radius(cx, cy, radius, entity_type)`, `find_nearest(cx, cy, entity_type)`, `can_reach_direct(self, target)`.
- `systems/resource_manager.py` — Singleton, `get_stock()`, `spend(cost)`, `earn(bundle)`, `can_afford(cost)`.
- `systems/wave_manager.py` — Singleton, `spawn_minions(parent, count)`.
- `structures/towers/tower.py` — `Tower` class với `stun(duration)`.

Khi viết code mới có dùng các module này, **chỉ import** — không phải dựng cả module trừ khi user yêu cầu.

## 6. Lệnh thường dùng

```powershell
# Chạy game (khi main.py có)
python main.py

# Format / lint (theo rule global)
black .
ruff check .

# Test (khi tests/ có)
pytest --cov=. --cov-report=term-missing
```

## 7. Tham chiếu nhanh

- Chi tiết bối cảnh, gameplay, kế hoạch màn chơi → xem [CONTEXT.md](./CONTEXT.md).
- Diagram quan hệ class → xem docstring đầu mỗi file trong [Titan-s_Last_Bastion/core/](./Titan-s_Last_Bastion/core/).
