# CONTEXT.md — Bối cảnh & Thiết kế dự án Titan's Last Bastion

## 1. Tổng quan

**Titan's Last Bastion** là game *tower defense* lấy cảm hứng từ *Attack on Titan*. Người chơi đóng vai Tướng Quân trong thành Paradis, xây tháp – tường – công trình, huy động lính và Commander (Eren, Mikasa, Levi, Armin, Hange) để chống lại các đợt Titan tấn công xuyên qua các vòng tường (Maria → Rose → Sina), tiến tới đánh bại boss cuối là **Founding Titan**.

Dự án đồng thời là **đồ án môn Lập trình Hướng đối tượng** tại UIT, nhấn mạnh:
- Kế thừa & đa hình (Entity → Character/Structure → Titan/Tower/Soldier).
- Interfaces làm "hợp đồng" (IAttackable, IMovable, ISkillUser, IUpgradable, IProducible, ILootable).
- Design Patterns: **Strategy**, **Observer (EventBus)**, **Singleton**, **Decorator** (cho buff/debuff), **Factory** (cho wave spawn).

## 2. Gameplay (5 màn)

| Màn | Vòng tường | Threat chính | Cơ chế mở khoá |
|----:|-----------|--------------|----------------|
| 1 | Wall Maria | RegularTitan, AberrantTitan | Cơ bản: tháp + lính |
| 2 | Wall Maria | ArmoredTitan, CrawlerTitan | Anti-Armor Bolt, ODM Gear |
| 3 | Wall Rose  | **ColossalTitan** (boss) | Stun → cần FireTower/IceTower |
| 4 | Wall Rose  | **BeastTitan** (boss ném đá 350px) | Ballista tầm xa, EMPTower |
| 5 | Wall Sina  | **FoundingTitan** (3 phase, cần Serum) | Tất cả công nghệ |

Thua màn → mất 20% tài nguyên cơ bản, commander_level −1 (min 1) — xem `GameState.apply_defeat_penalty()`.

## 3. Kiến trúc lớp (đã có)

### Core layer — [Titan-s_Last_Bastion/core/](./Titan-s_Last_Bastion/core/)

```
Entity (ABC)
  ├── id, x, y, is_alive
  ├── update(dt)  [abstract]
  ├── draw(screen) [abstract]
  └── position → (x, y)
```

Interfaces ([interfaces.py](./Titan-s_Last_Bastion/core/interfaces.py)):
- **IAttackable** — `take_damage(amount, dtype)`. `dtype` chuẩn: `normal`, `anti_armor`, `ice`, `fire`, `odm`, `slash`, `ram`, `aoe`, `pierce`, `stomp`, `climb`, `rock`.
- **IMovable** — `move(destination)`.
- **ISkillUser** — `use_skill('Q'|'E'|'R')`, `get_cooldown(id)` (Commander).
- **IUpgradable** — `upgrade()`, `get_upgrade_cost()` (Tower, Building, Commander).
- **IProducible** — `produce() -> ResourceBundle` (Farm, StoneWorkshop, GasStorage, Forge, TrainingCamp, RepairStation).
- **ILootable** — `collect(collector)` (LootNode).

### Resource & State — [game_state.py](./Titan-s_Last_Bastion/core/game_state.py)

`ResourceBundle` — dataclass gom 8 loại tài nguyên:

| Tài nguyên | Dùng cho |
|------------|----------|
| wood       | Công trình cơ bản |
| stone      | Tháp, sửa tường |
| gas        | ODMGear, FireTower, GasStorage |
| food       | Train & duy trì lính |
| ore        | Forge, Ballista, EMPTower |
| crystal    | IceTower, upgrade cao cấp |
| serum      | Unlock Phase 3 FoundingTitan |
| anti_armor_bolt | Đạn Ballista xuyên giáp |

Toán tử: `+` (cộng kho), `*` (penalty thua màn, chỉ áp 4 loại cơ bản), `>=` (can_afford).

`GameState` — snapshot save/load JSON (`save.json`): current_level, stock, commander_level, walls_hp, towers, buildings, soldiers_alive.

### Event Bus — [event_bus.py](./Titan-s_Last_Bastion/core/event_bus.py)

Singleton. Các event chuẩn:

| Event | Publisher | Subscriber |
|-------|-----------|------------|
| `wall_breached` | WallSection | HUD, Camera, WaveManager, Audio |
| `titan_died` | Titan | ResourceManager, WaveManager |
| `soldier_died` | Soldier | ResourceManager, HUD |
| `building_destroyed` | Building | ResourceManager, HUD |
| `tower_destroyed` | Tower | HUD, lính rút lui |
| `wave_started` | WaveManager | HUD, Audio |
| `game_over` | GameManager | UI, Audio |

### Exceptions — [exceptions.py](./Titan-s_Last_Bastion/core/exceptions.py)

- `InsufficientResourceError(resource, required, available)` — raise trong `ResourceManager.spend()`.
- `WallBreachError(wall_name, section_id)` — optional, kèm event `wall_breached`.

## 4. Hệ thống Titan (đã có ở root)

### Titan base ([Titan.py](./Titan.py))

`Titan(Entity, IAttackable, IMovable)` — AI loop: tìm target → di chuyển → tấn công qua Strategy.

Ưu tiên target trong `_find_best_target()`:
1. HQ nếu đường thoáng.
2. WallSection cản đường.
3. Tower/Soldier đang đánh mình.
4. Fallback: HQ.

### Các Titan thường

| Class | Strategy ban đầu | Đặc trưng |
|-------|------------------|-----------|
| RegularTitan | MeleeRushStrategy | HP < 40% → switch sang HeavyStrikeStrategy; random visual variant `Assets/Titan/regular{2,4,5,6,7}.png` chọn lúc spawn; walk/run/attack animation đầy đủ |
| ArmoredTitan | ArmoredRamStrategy | Chặn 60% damage thường; **5 Ram va chạm HOẶC 5 anti_armor** → vỡ giáp → switch HeavyStrikeStrategy VĨNH VIỄN; sau vỡ mất Dash, đánh melee tại chỗ (rows 12-15) |
| CrawlerTitan | ClimbBypassStrategy | Leo qua tường, bypass tháp mặt đất |
| AberrantTitan | MeleeRushStrategy(mult=1.2) | Dash mỗi 4s — speed ×3 tạm thời |
| Wolf | Incurable | Thân nhỏ giống sói, cắn truyền `dtype='antiheal'` (damage ×0.8); sprite cố định `Assets/Titan/wolf.png`; không switch strategy |
| TowerHunter | TowerHunterStrategy | Công thành: ×1.5 damage nếu target là `Tower` (isinstance check); dtype='siege'; sprite cố định `Assets/Titan/towerhunter.png`; không switch strategy |
| SoldierHunter | SoldierHunterStrategy | Cleave AoE quanh ATTACKER (`radius = _attack_range`, mặc định 40px); trúng MỌI entity (soldier + commander + tower + wall + hq) với splash 50% main; sprite `Assets/Titan/soldierhunter.png` **kích thước đặc biệt** (walk/run 64×64, attack 192×192) |
| Kamikaze | Explosion | Suicide bomber: detect 300px → chạy 1.5× tốc về soldier (clustering pick) → vào 80px → pause 1.5s flash đỏ → nổ AoE (main 200 + splash 100 + knockback 60px). Chết trước nổ vẫn nổ. Sprite `Assets/Special/kamikaze.png` |

### Bosses ([Boss.py](./Boss.py))

| Class | Skill chính | Lưu ý |
|-------|-------------|-------|
| ColossalTitan | GroundSlamStrategy (radius=160, stun=3s) + Steam Burst mỗi 8s (annulus 80→140px, 24 particle × AoE 35px tại spawn point, 15 fire/burn + BurnDoT) + Jump Stomp mỗi 15s (AoE 160px, stun tháp 5s, dame 40) | Boss màn 3 |
| BeastTitan | Ném đá tầm 350px, arc parabol (v=250 px/s, góc 15°, g=600 px/s²); AoE 80px khi land (main=80, splash=40, dtype=rock); cooldown 2s; ngoài tầm → walk lại gần; cùng skill cho mọi target (Tower, Soldier, Commander, Wall, HQ) | Phá tháp từ xa, ưu tiên tower; sprite `Assets/Boss/beast.png` + rock `Assets/Rock/Rock Pile` row=9 col=5 (frame 85×85) |
| FoundingTitan | 3 phase HP-based: P1 (>60%, HeavyStrike range 80 cd 3s) / P2 (20-60%, auto-summon 10 minion vòng tròn 180px mỗi 10s + 2s pause animation) / P3 (≤20%, sticky **tắt summon** vĩnh viễn dù HP hồi lại) | Final boss; serum fragment + hồi 2%/s khi không có serum = **để mở**; sprite `Assets/Boss/founding.png` |

### Attack Strategies ([AttackStrategy.py](./AttackStrategy.py))

`TitanAttackStrategy` (ABC) — `execute(attacker, target)`.

| Strategy | Mô tả |
|----------|-------|
| MeleeRushStrategy(mult, dtype) | Cận chiến — đổi mult/dtype runtime |
| HeavyStrikeStrategy(mult=2.0) | Đòn nặng — dùng sau khi giáp vỡ |
| Incurable(mult=0.8, dtype='antiheal') | Cắn chặn hồi máu — target tự xử lý dtype, set cờ no_heal_timer |
| ArmoredRamStrategy(mult=3.0) | Húc với damage `ram` |
| ClimbBypassStrategy(offset=60) | Đánh + teleport sang bên kia tường |
| GroundSlamStrategy(radius, stun) | AoE damage `stomp` + stun tháp |
| Explosion(main, splash, radius, knockback) | AoE quanh attacker (không phải target); main + splash damage dtype='explode' + knockback ra xa attacker |
| TowerHunterStrategy(bonus=1.5, dtype='siege') | x1.5 damage nếu target là Tower (isinstance check) |
| SoldierHunterStrategy(splash_radius=attack_range, splash_mult=0.5) | Cleave 360° quanh ATTACKER: main ×1.0 lên target chính + splash 50% lên mọi entity (soldier/commander/tower/wall/hq) trong vùng |

Đặc trưng: **đổi strategy = đổi cách đánh, không sửa Titan**. Có thể switch runtime (berserk, vỡ giáp).

**NHÓM 6 — Projectile / Particle phụ trợ** (cùng file, không phải `TitanAttackStrategy`):

| Class | Mô tả |
|-------|-------|
| RockProjectile | Viên đá BeastTitan ném — bay parabol, AoE `rock` + knockback khi land |
| HeatParticle | Hạt hơi nóng ColossalTitan toả ra (skill Steam Burst) — vòng tròn xám mờ dần |

Hai class này là thực thể "phụ" sinh ra bởi đòn đánh tầm xa / AoE của boss. Chúng không có `execute()` nên không kế thừa `TitanAttackStrategy`, nhưng thuộc về "cách đánh" của boss nên gom chung tại `AttackStrategy.py`. `Boss.py` import ngược lại để spawn trong skill animation.

## 5. Modules dự kiến (chưa code)

| Module | Trách nhiệm |
|--------|-------------|
| `systems/world_query.py` | API tra cứu thế giới: tìm entity theo radius/type, đường đi đến HQ |
| `systems/resource_manager.py` | Singleton kho tài nguyên: earn/spend/can_afford |
| `systems/wave_manager.py` | Singleton wave spawning, đếm wave, spawn minions cho boss |
| `systems/dispatch_manager.py` | Scout đi thu loot bên ngoài thành |
| `structures/towers/tower.py` | Tower base + ArrowTower, CannonTower, FireTower, IceTower, Ballista, EMPTower |
| `structures/walls/wall_section.py` | Đoạn tường — IAttackable, publish `wall_breached` |
| `structures/buildings/*.py` | Farm, StoneWorkshop, GasStorage, Forge, TrainingCamp, RepairStation (IProducible) |
| `characters/commanders/*.py` | Eren, Mikasa, Levi, Armin, Hange (ISkillUser, IUpgradable) |
| `characters/soldiers/*.py` | Garrison, Scout, MP, ODMTrooper (state machine) |
| `decorators/effects.py` | FrozenDecorator, BurnDecorator (Decorator pattern lên IAttackable) |
| `ui/hud.py` | Subscribe events, vẽ thanh HP, cooldown bar, alert |
| `main.py` | Game loop Pygame: dt, update tất cả entity, draw, xử lý input |

## 6. Quy trình nâng cấp & combat

### Combat flow
```
Tower.shoot(target: IAttackable)
   └─> target.take_damage(amount, dtype)
         ├─ Nếu có Decorator (Frozen/Burn) → ủy quyền + apply effect
         ├─ Class con xử lý dtype (giáp, kháng)
         └─ Nếu HP ≤ 0 → on_death() → publish event
```

### Upgrade flow
```
UI bấm Upgrade → tower.get_upgrade_cost() → ResourceManager.spend(cost)
   ├─ Đủ:    tăng level, cập nhật stats
   └─ Thiếu: raise InsufficientResourceError → HUD show warning
```

### Wave flow
```
WaveManager.start_wave(n)
   ├─ publish('wave_started', {wave: n})
   ├─ Spawn list Titan từ wave config
   └─ Khi tất cả Titan chết hoặc HQ sập → kết thúc wave
```

## 7. Quyết định thiết kế quan trọng

1. **Strategy thay vì if/else trong Titan** — Titan không hỏi "tôi là loại gì để biết đánh ra sao", nó chỉ gọi `self._attack_strategy.execute(self, target)`. Thêm kiểu đánh mới = thêm class mới, không sửa Titan.

2. **EventBus thay vì cross-coupling** — WallSection không cần biết HUD, Audio, WaveManager. Nó chỉ publish; ai quan tâm thì subscribe.

3. **dtype string thay vì class hierarchy damage** — đơn giản hoá. `take_damage(amount, dtype)` để class con tự diễn giải. Trade-off: phải duy trì danh sách dtype hợp lệ làm "magic strings".

4. **ResourceBundle immutable** — toán tử trả object mới. Tránh bug do chia sẻ tham chiếu (loot chung 1 bundle cho nhiều scout).

5. **GameState là dataclass serializable** — save/load JSON dễ debug, dễ edit tay khi test.

6. **Tách `update(dt)` / `draw(screen)`** — chuẩn bị cho khả năng chạy logic không cần Pygame (unit test).

## 8. Trạng thái hiện tại (snapshot)

- ✅ Core layer hoàn chỉnh ở mức "skeleton có body": Entity, interfaces, EventBus, exceptions, ResourceBundle, GameState.
- ✅ Titan + Boss + AttackStrategy có code thực thi (không chỉ stub).
- ✅ ColossalTitan: Skill 1 Steam Burst (mở rộng) + Skill 2 Jump Stomp (mới) + HeatParticle + animation spritesheet rows 23-30 + WASD movement + direction-preserved skill animation.
- ✅ `check.py`: demo pygame độc lập với mock đầy đủ, phím SPACE/ENTER/T/Q, WASD di chuyển tốc độ 80 px/s.
- ✅ RegularTitan: random variant `Assets/Titan/regular{2,4,5,6,7}.png` lúc spawn + Walk/Run/Attack animation + HP < 40% → HeavyStrikeStrategy + `trigger_attack()` public.
- ✅ `titancheck.py`: demo pygame độc lập với mock đầy đủ, phím WASD/Shift/SPACE/H/R/Q.
- ✅ `Priority.py`: hệ thống ưu tiên mục tiêu (Strategy Pattern) — 7 bộ ưu tiên + factory (mục 20).
- ✅ `Titan_AI.py`: bộ não tự hành cho 10 loại Titan — `TitanAI` (ABC) + `WorldView` + 10 AI con (mục 21).
- ✅ `CHECKAI/`: 10 demo `[titan]check_AI.py` viết theo OOP — AI tự chạy, người xem quan sát.
- ❌ Tower, WallSection, Building, Commander, Soldier — **chưa có** (CHECKAI dùng entity giả `_ai_dummies.py`).
- ❌ Systems layer (WorldQuery, ResourceManager, WaveManager) — **chưa có** (đang được tham chiếu bằng `from systems.X import Y` dạng forward declaration).
- ❌ Pygame integration (main loop, asset loading) — **chưa có**, dù sprite PNG đã có sẵn ở `Assets/Boss/`, `Assets/Titan/`, `Assets/Special/`.
- ⚠️ Package layout chưa thống nhất: file ở root vs file trong `Titan-s_Last_Bastion/core/`.

## 9. Roadmap đề xuất

1. Thống nhất layout: đưa toàn bộ code vào `Titan-s_Last_Bastion/` theo cấu trúc `characters/`, `structures/`, `systems/`, `core/`, `ui/`.
2. Triển khai `systems/world_query.py` (mock đơn giản trước) để Titan/Boss chạy được unit test.
3. Triển khai `ResourceManager` + `WaveManager` Singleton.
4. Tower hierarchy + WallSection để có vòng combat tối thiểu.
5. Pygame loop ở `main.py`, load sprite từ thư mục PNG.
6. Commander + Skill system.
7. Decorator (Frozen/Burn) lên IAttackable.
8. UI/HUD subscribe EventBus.
9. Save/load tích hợp với menu chính.
10. Polish: animation, audio, balance.

## 10. ColossalTitan Skills — Skill 1 & 2 (mở rộng Boss màn 3)

> Trạng thái: **✅ đã triển khai** — `Boss.py` (ColossalTitan) + `check.py`

### Spritesheet ColossalTitan

- File: `Assets/Boss/clossal.png` (chú ý chính tả), mỗi frame **64 × 64 px**
- Walk rows : 8 (N), 9 (W), 10 (S), 11 (E) — **9 frame/hàng** (col 0–8), loop liên tục
- Steam rows: 26 (N), 23 (W), 24 (S), 25 (E) — **2 frame/hàng** (col 0–1), loop liên tục
- Idle rows : 26 (N), 23 (W), 24 (S), 25 (E) — dùng col 0 tĩnh (cùng hàng với steam)
- Jump rows : 26 (N), 27 (W), 28 (S), 29 (E) — **5 frame/hàng** (col 0–4), loop liên tục
- Hướng: 0=N, 1=W, 2=S, 3=E; mapping `_direction` → row dùng dict riêng cho từng trạng thái
- Khi không có target: giữ nguyên `_direction` cuối cùng
- Khi kích hoạt skill: **giữ nguyên `_direction` đang có**, không tính lại → skill animation đúng hướng đang đứng

### Skill 1 — Steam Burst (`_steam_burst()` — vành khuyên annulus)

Khác với phiên bản cũ (damage AoE 120 px quanh tâm Colossal), bản hiện tại **damage tỏa ra từ vành khuyên** quanh Colossal — phù hợp với khái niệm "hơi nước bốc lên quanh cơ thể", không phải "vụ nổ tại tâm".

| Thuộc tính | Giá trị |
|------------|---------|
| Cooldown   | 8 giây |
| Hình học spawn | Annulus: `_STEAM_R_IN=80` → `_STEAM_R_OUT=140` px |
| Số particle | `_STEAM_PARTICLE_COUNT=24` — chia đều quanh 360° + jitter ±π/N |
| AoE mỗi particle | `_STEAM_PARTICLE_AOE=35` px tại spawn point của particle đó |
| Lính (`soldier`) | 15 fire + `BurnDecorator` DoT 5 dmg/s × 5s + `dtype='pushback'` |
| Tướng (`commander`) | 15 burn + `BurnDecorator` DoT 5 dmg/s × 5s |
| Dedupe damage | Mỗi target chỉ ăn damage 1 lần dù bị nhiều particle phủ |
| Animation  | Rows 23–26 (ánh xạ W/S/E/N), **2 frame/hàng**, 6 FPS |
| Behaviour  | ColossalTitan **đứng yên 3 giây**; giữ nguyên `_direction` khi kích hoạt |

**Thuật toán spawn**: với `N=24`, mỗi particle có `angle = i × 2π/N + jitter`, `radius = uniform(R_in, R_out)`, spawn tại `(Colossal.x + cos·r, Colossal.y + sin·r)`. Damage được apply NGAY tại spawn point đó qua `WorldQuery.find_in_radius(sx, sy, 35, ...)`.

**Particle `HeatParticle`**: vòng tròn xám (160,160,160), spawn tại đúng vị trí truyền vào (không offset). Velocity ngẫu nhiên mọi hướng quanh spawn point, radius phình to, alpha mờ dần trong 0.8–1.8 giây.

**Hằng số `_STEAM_AOE = 120`** vẫn còn để backward-compat (demo có thể vẽ vòng tham chiếu), nhưng **không còn dùng cho damage logic**.

### Skill 2 — Jump Stomp (`_jump_stomp()`)

| Thuộc tính | Giá trị |
|------------|---------|
| Cooldown   | 15 giây |
| AoE radius | 160 px |
| Tháp (`tower`) | `tower.stun(5.0)` — choáng 5 giây |
| Lính (`soldier`) | 40 stomp damage tức thì |
| Tướng (`commander`) | 40 stomp damage tức thì |
| Animation  | Rows 26–29 (ánh xạ N/W/S/E), **5 frame/hàng**, 6 FPS |
| Behaviour  | ColossalTitan **đứng yên 1.5 giây**; giữ nguyên `_direction` khi kích hoạt |

### Di chuyển (WASD — demo `check.py`)

| Phím | Hướng | `_direction` |
|------|-------|--------------|
| W    | Bắc (lên) | 0 |
| A    | Tây (trái) | 1 |
| S    | Nam (xuống) | 2 |
| D    | Đông (phải) | 3 |

Tốc độ: **80 px/s**. Di chuyển bị khoá khi đang toả hơi hoặc nhảy.

### Các cờ animation trong `ColossalTitan.__init__`

```
_direction, _is_steaming, _steam_anim_timer,
_is_jumping, _jump_anim_timer, _is_moving,
_anim_col, _anim_timer, _heat_particles, _sprite_sheet
```

### File tham chiếu

- `Boss.py` — ColossalTitan (BeastTitan/FoundingTitan giữ nguyên)
- `patterns/decorator.py` — BurnDecorator (dùng như-là, không sửa)
- `check.py` — demo/test file độc lập với mock, không thuộc source chính

## 11. RegularTitan — Walk / Run / Attack + HeavyStrike threshold

> Trạng thái: **✅ đã triển khai** — `Titan.py` (RegularTitan) + `titancheck.py`

### Spritesheet RegularTitan

- File: `Assets/Titan/regular{N}.png` với `N ∈ {2, 4, 5, 6, 7}` — mỗi RegularTitan **bốc ngẫu nhiên 1 file lúc spawn** (giữ nguyên cả vòng đời). Truyền `config['variant']` để cố định trong test.
- Mỗi frame **64 × 64 px**.
- Ánh xạ hướng: `0=N → row1, 1=W → row2, 2=S → row3, 3=E → row4`.

| Trạng thái | Rows (N/W/S/E) | Frame/hàng | FPS |
|-----------|---------------|-----------|-----|
| Walk      | 8 / 9 / 10 / 11    | 9 | 6 |
| Run       | 37 / 38 / 39 / 40  | 8 | 6 |
| Attack    | 12 / 13 / 14 / 15  | 6 | 6 → 1.0s/đòn |
| Idle      | row Walk, col 0    | — | — |

### Logic chuyển strategy theo HP

| Ngưỡng HP | Hành động |
|-----------|-----------|
| `_hp / _max_hp < 0.4` (lần đầu) | `_heavy_mode = True`; `self._attack_strategy = HeavyStrikeStrategy()` |

> Thay thế hoàn toàn nhánh berserk 30% cũ. Không tăng `_speed` mặc định ở mức code; demo tự quyết tốc độ qua phím Shift.

### Public API mới trên RegularTitan

```python
titan.trigger_attack()      # kích hoạt animation tấn công 1 đòn (1.0s)
titan._is_running = True    # demo bật cờ chạy (Shift) — ảnh hưởng draw()
titan._is_moving  = True    # demo điều khiển di chuyển bên ngoài
titan._direction  = 0|1|2|3 # demo set hướng nhìn
```

### Các cờ animation trong `RegularTitan.__init__`

```
_variant, _direction, _is_moving, _is_running, _is_attacking,
_attack_anim_timer, _anim_col, _anim_timer,
_heavy_mode, _sprite_sheet
```

### Demo (`titancheck.py`)

| Phím         | Tác dụng |
|--------------|----------|
| WASD         | Di chuyển (Walk, 90 px/s) |
| Shift + WASD | Run (145 px/s) |
| SPACE        | Trigger Attack |
| H            | Gây 10% max HP damage (test ngưỡng 40%) |
| R            | Respawn với variant ngẫu nhiên mới |
| Q / ESC      | Thoát |

HUD hiển thị: variant, state (IDLE/WALK/RUN/ATTACK), direction, row, col, HP%, strategy hiện tại.

### File tham chiếu

- `Titan.py` — RegularTitan (các class còn lại giữ nguyên)
- `AttackStrategy.py` — MeleeRushStrategy, HeavyStrikeStrategy (không sửa)
- `titancheck.py` — demo/test độc lập với mock, không thuộc source chính

## 12. ArmoredTitan — Walk / Run / Dash (Ram skill) + Armor Break

ArmoredTitan có sprite **đơn** `Assets/Special/armored.png` (không random). Walk/Run dùng cùng layout với RegularTitan; skill Dash tái dùng Run frames với FPS gấp đôi.

### Spritesheet ArmoredTitan

| Trạng thái | Hàng (N/W/S/E) | Số frame | FPS |
|------------|----------------|----------|-----|
| Walk       | 8 / 9 / 10 / 11   | 9 | 6 |
| Run        | 37 / 38 / 39 / 40 | 8 | 6 |
| **Dash**   | tái dùng 37 / 38 / 39 / 40 | 8 | **12** (×2) |

Frame 64×64. Direction mapping: 0=N, 1=W, 2=S, 3=E (đồng nhất với RegularTitan).

### Skill — ArmoredRamStrategy (dash)

- **Trigger**: bên ngoài gọi `trigger_dash(dx, dy, run_speed)` với vector hướng + Run speed base.
- **Tốc độ**: `run_speed × 1.5`.
- **Khoảng dash tối đa**: `_DASH_MAX_DIST = 300.0 px`.
- **Dừng khi**: va chạm target HOẶC đi hết 300 px.
- **Va chạm**: caller phát hiện collision rồi gọi `end_dash_on_hit(target)` — method này tự gọi `_attack_strategy.execute(self, target)`.
- **Demo bước dash**: gọi `dash_step(dt, world_bounds)` mỗi frame để lấy `(new_x, new_y, finished)`.

### Armor break — 2 con đường, counter tích lũy cả vòng đời

`_HITS_TO_BREAK = 5`. Có 2 counter độc lập, **không reset**, đạt 5 hit thì vỡ giáp:

| Counter | Tăng khi | Damage trên đường đi |
|---------|----------|----------------------|
| `_ram_hits` | Dash va chạm target → `end_dash_on_hit()` được gọi | Theo ArmoredRamStrategy (×3.0) |
| `_antiarmor_hits` | `take_damage(amount, 'anti_armor')` được gọi | Full damage (xuyên giáp) |

Cái nào đạt 5 trước → `_break_armor(cause)` chạy:
- `_armor_intact = False` (vĩnh viễn)
- `_attack_strategy = HeavyStrikeStrategy()` (vĩnh viễn)
- `_break_cause = 'ram'` hoặc `'anti_armor'` (để HUD hiển thị)
- Hủy dash đang chạy nếu có

**Damage filter trong `take_damage()`**:
- Còn giáp + `dtype='anti_armor'`: full damage + đếm counter (vỡ ở hit thứ 5)
- Còn giáp + dtype khác: chặn 60% (giảm còn 40%)
- Giáp vỡ: full damage mọi dtype

### Post-break — đánh melee đứng tại chỗ

Sau khi vỡ giáp:
- **Dash bị khóa**: `trigger_dash()` luôn trả `False` khi `_armor_intact=False`.
- **Melee mới**: `trigger_attack()` kích hoạt animation đứng tại chỗ — 6 frame, rows 12-15 trong `Assets/Special/armored.png` (giả định layout chuẩn). 1 đòn = 1 s.
- Demo gọi `_attack_strategy.execute(self, target)` khi target trong tầm 60 px.

### Public API mới trên ArmoredTitan

| Method | Mô tả |
|--------|-------|
| `trigger_dash(dx, dy, run_speed)` | Bắt đầu dash; trả `False` nếu giáp đã vỡ hoặc đang busy |
| `dash_step(dt, world_bounds=None)` | Tính `(new_x, new_y, finished)` của bước dash kế tiếp |
| `end_dash_on_hit(target)` | Dừng dash + execute Strategy + `_ram_hits += 1`; trả `(broke, cause)` |
| `_break_armor(cause)` | Vỡ giáp + switch HeavyStrike + set `_break_cause`; idempotent |
| `trigger_attack()` | Melee post-break (CHỈ khi giáp vỡ); 6 frame × 1/6 s |
| `update_anim(dt)` | Cập nhật anim — ưu tiên Attack > Dash > Walk/Run > Idle |
| `_load_sprite()` + `draw(screen)` | Render sprite hoặc fallback |

### Demo (`armoredcheck.py`)

| Phím | Tác dụng |
|------|----------|
| WASD         | Di chuyển |
| Shift + WASD | Chạy (Run) |
| **SPACE + WASD** | Dash theo hướng đang giữ (skill Ram) |
| J            | Bắn anti_armor 100 dmg (test vỡ giáp → HeavyStrike) |
| H            | Normal 50 dmg (kiểm tra giáp chặn 60%) |
| R            | Respawn titan + dummy mới |
| Q / ESC      | Thoát |

Dummy target tĩnh ở bên phải — nếu dash va chạm trong bán kính 36 px → `ArmoredRamStrategy.execute()` được gọi. HUD: sprite status, state (IDLE/WALK/RUN/DASH), armor (INTACT/BROKEN), strategy.

### File tham chiếu

- `Titan.py` — class `ArmoredTitan` (mở rộng)
- `armoredcheck.py` — demo độc lập với mock

## 13. Wolf — Walk / Run / Attack + Incurable (chặn hồi máu)

Wolf là Titan thân nhỏ chuyên cắn truyền debuff antiheal. Luôn dùng `Incurable` strategy, **không** switch theo HP.

### Spritesheet Wolf

| Trạng thái | Hàng (N/W/S/E) | Số frame | FPS |
|------------|----------------|----------|-----|
| Walk       | 8 / 9 / 10 / 11   | 9 | 6 |
| Run        | 37 / 38 / 39 / 40 | 8 | 6 |
| Attack     | 12 / 13 / 14 / 15 | 6 | 6 (1.0 s/đòn) |

Sprite **cố định** `Assets/Titan/wolf.png` (không random variant). Frame 64×64. Mapping N=0, W=1, S=2, E=3.

### Strategy — Incurable

Định nghĩa trong [AttackStrategy.py](./AttackStrategy.py):

```python
class Incurable(TitanAttackStrategy):
    def __init__(self, damage_mult: float = 0.8, dtype: str = 'antiheal'):
        ...
    def execute(self, attacker, target):
        target.take_damage(
            amount=int(attacker._damage * self._damage_mult),
            dtype=self._dtype  # 'antiheal'
        )
```

- Damage thấp (×0.8) đổi lấy debuff.
- **Loose coupling**: Incurable không tự áp debuff. Chỉ truyền `dtype='antiheal'` — target tự xử lý (set cờ ngăn regen). Cho phép mỗi loại target phản ứng khác nhau.

### Public API mới trên Wolf

| Method | Mô tả |
|--------|-------|
| `trigger_attack()` | Kích hoạt animation cắn 1 đòn (6 frame × 1/6 s) |
| `update_anim(dt)` | Cập nhật frame; demo dùng thay cho `update()` |
| `_load_sprite()` + `draw(screen)` | Render `Assets/Titan/wolf.png` hoặc fallback xanh dương |

### Demo (`wolfcheck.py`)

| Phím | Tác dụng |
|------|----------|
| WASD         | Di chuyển |
| Shift + WASD | Chạy |
| SPACE        | Đòn cắn — nếu trong tầm 60 px của dummy, gọi `Incurable.execute()` |
| R            | Respawn Wolf + dummy |
| Q / ESC      | Thoát |

Dummy `HealingDummy`: HP 400, regen +5/s. Khi nhận `dtype='antiheal'` → `_no_heal_timer = 5.0 s` chặn regen, đếm ngược trên HUD; hết timer thì regen lại.

### File tham chiếu

- `Titan.py` — class `Wolf` (cuối file)
- `AttackStrategy.py` — class `Incurable` (trong NHÓM 1: Cận chiến)
- `wolfcheck.py` — demo độc lập với mock

## 14. TowerHunter — Walk / Run / Attack + bonus phá tháp (siege)

TowerHunter là Titan công thành — chuyên hạ Tower trước khi vào HQ. Luôn dùng `TowerHunterStrategy` cố định, **không** switch theo HP.

### Spritesheet TowerHunter

| Trạng thái | Hàng (N/W/S/E) | Số frame | FPS |
|------------|----------------|----------|-----|
| Walk       | 8 / 9 / 10 / 11   | 9 | 6 |
| Run        | 37 / 38 / 39 / 40 | 8 | 6 |
| Attack     | 12 / 13 / 14 / 15 | 6 | 6 (1.0 s/đòn) |

Sprite **cố định** `Assets/Titan/towerhunter.png` (không random variant). Frame 64×64. Mapping N=0, W=1, S=2, E=3.

### Strategy — TowerHunterStrategy

Định nghĩa trong [AttackStrategy.py](./AttackStrategy.py):

```python
class TowerHunterStrategy(TitanAttackStrategy):
    def __init__(self, tower_bonus_mult: float = 1.5, dtype: str = 'siege'):
        ...
    def execute(self, attacker, target):
        from structures.towers.tower import Tower
        mult = self._tower_bonus_mult if isinstance(target, Tower) else 1.0
        target.take_damage(
            amount=int(attacker._damage * mult),
            dtype=self._dtype  # 'siege'
        )
```

- **Bonus chỉ áp khi target là Tower** (isinstance check). Soldier/HQ/Wall đều nhận damage ×1.0.
- **dtype='siege'** — Tower nhận biết là damage công thành, có thể áp resistance/weakness riêng.
- Vẫn dùng `isinstance` (yêu cầu user) — Strategy có lazy import `from structures.towers.tower import Tower`, demo phải mock module này trước khi gọi `execute()`.

### Public API mới trên TowerHunter

| Method | Mô tả |
|--------|-------|
| `trigger_attack()` | Kích hoạt animation siege 1 đòn (6 frame × 1/6 s) |
| `update_anim(dt)` | Cập nhật frame; demo dùng thay cho `update()` |
| `_load_sprite()` + `draw(screen)` | Render `Assets/Titan/towerhunter.png` hoặc fallback tím |

### Demo (`towerhuntercheck.py`)

| Phím | Tác dụng |
|------|----------|
| WASD         | Di chuyển |
| Shift + WASD | Chạy |
| SPACE        | Đòn siege — execute lên dummy gần nhất nếu trong tầm 60 px |
| R            | Respawn titan + 2 dummy mới |
| Q / ESC      | Thoát |

**Hai dummy** để so sánh bonus:
- **TowerDummy** (subclass `_MockTower`, HP 600) — vẽ thành hình vuông đá xám với crenellation, nhận damage ×1.5
- **SoldierDummy** (class trần, HP 300) — hình tròn xanh lá, nhận damage ×1.0

Demo mock `structures.towers.tower.Tower = _MockTower` trước khi import Strategy, để `isinstance` check hoạt động. HUD hiển thị nearest target + công thức damage cho cả 2 loại.

### File tham chiếu

- `Titan.py` — class `TowerHunter` (cuối file)
- `AttackStrategy.py` — class `TowerHunterStrategy` (NHÓM 5: Mục tiêu đặc biệt) — đã sửa default mult=1.5, dtype='siege'
- `towerhuntercheck.py` — demo độc lập với mock (mock cả `structures.towers.tower`)

## 15. SoldierHunter — Walk / Run / Cleave (splash AoE = attack_range, đa loại)

SoldierHunter là Titan to xác cầm lưỡi hiểm — chuyên săn lính, gây cleave AoE quanh ATTACKER (vung 360° = `_attack_range`), trúng MỌI loại entity. Mặc định dùng `HeavyStrikeStrategy` và switch sang `SoldierHunterStrategy` khi target là `soldier` (xem `Titan.SoldierHunter.update`).

### Spritesheet SoldierHunter — kích thước ĐẶC BIỆT

`Assets/Titan/soldierhunter.png` có kích thước **1152 × 4224 px** với layout **hai vùng size khác nhau**:

| Vùng | Pixel rows | Frame size | Số cột | Mục đích |
|------|-----------|-----------|--------|----------|
| Top  | y ∈ [0, 3456)    | **64 × 64** | 18 | Walk/Run rows (chuẩn như các titan khác) |
| Bottom | y ∈ [3456, 4224) | **192 × 192** | 6 | 4 hàng attack — khung lớn 3× |

Tính toán:
```
54 hàng top × 64 px = 3456 px (= y bắt đầu của vùng attack)
4  hàng bottom × 192 px = 768 px
Tổng cao = 3456 + 768 = 4224 px ✓
1152 px chia 18 cột × 64 = 1152 (top) ✓
1152 px chia 6 cột × 192  = 1152 (bottom) ✓
```

Hàng dùng (ánh xạ 0=N, 1=W, 2=S, 3=E):

| Trạng thái | Vị trí | Số frame | FPS |
|------------|--------|----------|-----|
| Walk (64×64)  | rows 8 / 9 / 10 / 11   | 9 | 6 |
| Run  (64×64)  | rows 37 / 38 / 39 / 40 | 8 | 6 |
| **Attack (192×192)** | pixel-y **3456 / 3648 / 3840 / 4032** | 6 | 6 (1.0 s/đòn) |

User gọi 4 hàng attack là "hàng 55, 56, 57, 58" (1-indexed, đếm theo vùng top 54 rows + thứ tự N/W/S/E). Trong code lưu trực tiếp pixel-y:

```python
_ATTACK_Y = {0: 3456, 1: 3648, 2: 3840, 3: 4032}
```

### Strategy — SoldierHunterStrategy (cập nhật NHÓM 5)

Định nghĩa trong [AttackStrategy.py](./AttackStrategy.py):

```python
class SoldierHunterStrategy(TitanAttackStrategy):
    _DEFAULT_DAMAGE_MULT = 3.0
    _DEFAULT_DTYPE       = 'soldier'
    _SPLASH_ENTITY_TYPES = ('soldier', 'commander', 'tower', 'wall', 'hq')

    def __init__(self, damage_mult=None, dtype=None,
                 splash_radius: float = 120.0,
                 splash_mult: float = 0.5,
                 splash_dtype: str = 'aoe'):
        ...
    def execute(self, attacker, target):
        base = self.compute_damage(attacker)
        target.take_damage(amount=base, dtype=self._dtype)
        # Cleave: quét MỌI loại entity trong _splash_radius quanh ATTACKER.
        splash_dmg = int(base * self._splash_mult)
        seen = {id(target)}
        for etype in self._SPLASH_ENTITY_TYPES:
            for e in WorldQuery.find_in_radius(
                    attacker.x, attacker.y, self._splash_radius, etype):
                if id(e) in seen: continue
                seen.add(id(e))
                e.take_damage(amount=splash_dmg, dtype=self._splash_dtype)
```

- **Target chính** → damage = `attacker._damage × 3.0`, dtype='soldier'.
- **Mọi entity trong vùng cleave quanh ATTACKER** (radius = `_splash_radius`,
  mặc định khi SoldierHunter khởi tạo = `self._attack_range` ≈ 40px) →
  damage ×0.5, dtype='aoe'. Bao gồm: soldier + commander + tower + wall + hq.
- Tự loại trừ target chính khỏi splash (`seen` set chứa `id(target)` từ đầu)
  → không trừ máu 2 lần.
- Loose coupling qua `WorldQuery.find_in_radius(cx, cy, radius, entity_type)` —
  world phải hỗ trợ đủ 5 entity_type. Loại nào chưa có → `find_in_radius`
  trả list rỗng → strategy bỏ qua, an toàn.

### Anchor / Draw đặc biệt

Cả walk/run (64×64) và attack (192×192) đều **căn giữa quanh `(titan.x, titan.y)`**. Khi đánh, frame 192 tỏa rộng 4 phía — vũ khí lưỡi hiểm vung quanh tâm. Va chạm và tầm đánh vẫn tính theo tâm titan, không phụ thuộc kích thước sprite frame.

### Public API mới trên SoldierHunter

| Method | Mô tả |
|--------|-------|
| `trigger_attack()` | Kích hoạt animation cleave (6 frame × 1/6 s) |
| `update_anim(dt)` | Cập nhật frame; demo dùng thay cho `update()` |
| `_get_frame(row, col)` | Trích frame 64×64 (walk/run) |
| `_get_attack_frame(col)` | Trích frame 192×192 (attack) tại direction hiện tại |
| `draw(screen)` | Tự chọn 64 hay 192 px tùy state |

### Demo (`soldierhuntercheck.py`)

| Phím | Tác dụng |
|------|----------|
| WASD         | Di chuyển |
| Shift + WASD | Chạy |
| SPACE        | Cleave (tầm 60 px → target gần nhất) — execute Strategy |
| R            | Respawn titan + 5 dummy mới |
| Q / ESC      | Thoát |

**Setup dummy**: 1 MAIN target (HP 250) ở giữa + 4 SoldierDummy quanh (N/S/W/E, mỗi cái HP 150, lệch 50 px). MockWorldQuery có `find_in_radius()` THẬT — duyệt list dummy đã đăng ký, trả về soldier trong bán kính. Khi SPACE đánh trúng MAIN, Strategy tự gọi find_in_radius quanh MAIN → 4 lính cận đều nhận splash 50%.

Hit feedback: dummy **flash đỏ** khi nhận `dtype='normal'`, **flash cam** khi nhận `dtype='aoe'`. HUD log đầy đủ: `[MAIN] take_damage(40, 'normal') [MAIN]` + `[north] take_damage(20, 'aoe') [SPLASH]` x4.

### File tham chiếu

- `Titan.py` — class `SoldierHunter` (cuối file)
- `AttackStrategy.py` — class `SoldierHunterStrategy` (NHÓM 5) — cleave quanh ATTACKER, trúng mọi entity_type, mặc định `splash_radius=120` (override = `attack_range` khi SoldierHunter khởi tạo)
- `soldierhuntercheck.py` — demo độc lập với mock (mock WorldQuery.find_in_radius bằng list dummy)

## 16. BeastTitan — Walk / Run / Throw Rock (parabolic arc + AoE)

BeastTitan là boss màn 4 — chuyên đứng xa **ném đá phá tháp** trước khi vào HQ. Khác hoàn toàn với Colossal/Founding ở chỗ có **projectile thật** (`RockProjectile`) bay theo cung parabol.

### Spritesheet BeastTitan — `Assets/Boss/beast.png` (frame 64×64, 0-indexed)

| Trạng thái | Hàng (N/W/S/E) | Số frame | FPS |
|------------|----------------|----------|-----|
| Walk       | 8 / 9 / 10 / 11    | 9 | 6 |
| Run        | 38 / 39 / 40 / 41  | 8 | 6 |
| Attack     | 12 / 13 / 14 / 15  | 6 | **24** (0.25 s/đòn — biến `_ATTACK_FPS` riêng) |

### Rock spritesheet — `Assets/Rock/Rock Pile - Spritesheet.png`

| Thuộc tính | Giá trị |
|------------|---------|
| Kích thước | 510 × 2550 |
| Layout     | 6 cột × 30 hàng → frame **85 × 85** |
| Frame chọn | row=9, col=5 (0-indexed) → pixel rect `(425, 765, 85, 85)` |

Frame đá được trích 1 lần lúc spawn beast, cache vào `_rock_frame`, share cho mọi `RockProjectile`.

### `RockProjectile` — class trong `AttackStrategy.py` (NHÓM 6)

Physics 2D top-down với "height offset" z:
- `vx = velocity × cos(angle) × dir_x`, `vy = velocity × cos(angle) × dir_y` (toward target)
- `vz = velocity × sin(angle)` (visual loft up); `vz -= gravity × dt`
- Vẽ rock tại `(x, y - z)` — z càng cao càng nhô lên màn hình
- Land khi `z ≤ 0` và `vz < 0` → áp damage AoE tại điểm rơi

| Tham số | Giá trị mặc định | Ý nghĩa |
|---------|------------------|---------|
| `velocity` | 250 px/s | tốc độ phóng ban đầu |
| `angle_deg` | 15° | góc chếch elevation |
| `gravity` | 600 px/s² | trọng lực kéo z xuống |
| `damage_main` | 80 | damage cho target chính (nếu trong AoE) |
| `damage_splash` | 40 | damage cho entity khác trong AoE |
| `aoe_radius` | 80 px | bán kính AoE quanh điểm rơi |
| dtype | `'rock'` | gửi vào `take_damage()` |

**Tradeoff vật lý**: với defaults, range thực tế chỉ ~52 px (do `t_flight ≈ 0.22 s × v_horizontal ≈ 241 px/s`). Nếu target xa hơn, đá rơi giữa đường — KHÔNG homing. User đã chấp nhận: trông tự nhiên hơn, không "rocket".

Visual phụ: rock có rotation spin (`_spin` độ/giây), và bóng đen elliptical tại ground projection để cue độ cao.

### Skill ném đá — `trigger_attack(target)`

| Bước | Mô tả |
|------|-------|
| 1. Trigger | `trigger_attack(target)` set `_is_attacking=True`, quay mặt về target, reset anim |
| 2. Animation | 6 frame × 1/24 s = 0.25 s total. `_anim_col` đếm 0→5 |
| 3. Release | Khi `_anim_col >= 3` (frame 3) và chưa release → spawn `RockProjectile` từ tay |
| 4. Tay (hand) | Vị trí spawn = `beast.center + 24 px` theo hướng đến target (2D vector); nâng lên 12 px |
| 5. Bay & land | Rock tự update; khi land → áp damage AoE qua `WorldQuery.find_in_radius` |
| 6. End | Animation chạy hết 0.25 s → `_is_attacking=False`, reset col |

Cooldown `_THROW_COOLDOWN=2.0` giây giữa các lần throw (timer `_throw_timer`).

### AI gốc `update(dt)` — auto behavior

1. `update_anim(dt)` — animation + rocks trong flight luôn chạy
2. Nếu `_is_attacking` → chỉ đứng yên đánh, không AI tiếp
3. Tìm `_find_nearest_tower()` qua WorldQuery
4. Nếu không có tower → idle
5. Nếu dist ≤ 350 và `_throw_timer ≤ 0` → `trigger_attack(tower)`
6. Nếu dist > 350 → walk lại gần (`_is_moving=True`, cập nhật hướng, `_move_toward`)

### Demo (`beastcheck.py`)

| Phím | Tác dụng |
|------|----------|
| WASD         | Di chuyển manual |
| Shift + WASD | Chạy (Run) |
| SPACE        | Ném đá thủ công vào tower gần nhất (nếu trong tầm) |
| **T**        | Toggle AUTO mode — beast tự chạy AI gốc (`update`) |
| R            | Respawn beast + 3 tower + 1 soldier |
| Q / ESC      | Thoát |

Setup dummies (đo từ beast spawn):
- **T@150** (đông): trong tầm — ăn full damage
- **T@280** (đông-nam): trong tầm
- **T@450** (đông-bắc): NGOÀI tầm 350 — AUTO mode → beast walk lại gần
- **Soldier** (bắc, 200 px): không phải Tower → không bị nhắm. Có thể ăn splash 40 nếu rock rơi gần.

HUD: state, row/col, cooldown timer, physics constants, rocks in flight count, AUTO/MANUAL.

Console log: `[THROW]` khi trigger, `[T@150] take_damage(80, 'rock')` khi land trúng, splash damage cho entity khác trong AoE.

### File tham chiếu

- `AttackStrategy.py` — class `RockProjectile` (NHÓM 6, sau `HeatParticle`); `Boss.py` import lại
- `Boss.py` — class `BeastTitan` (viết lại hoàn toàn)
- `beastcheck.py` — demo độc lập với mock WorldQuery (find_nearest + find_in_radius), mock patterns.decorator.BurnDecorator

## 17. FoundingTitan — 3 Phase HP-based + Auto Summon Ring (Final Boss)

FoundingTitan là final boss màn 5 — chia 3 phase theo % HP, có cơ chế **summon vòng tròn** ở Phase 2 và **sticky lock** ở Phase 3 (mất summon vĩnh viễn).

### Spritesheet FoundingTitan — `Assets/Boss/founding.png` (frame 64×64, 0-indexed)

| Trạng thái | Hàng (N/W/S/E) | Số frame | FPS |
|------------|----------------|----------|-----|
| Walk    | 8 / 9 / 10 / 11    | 9 | 6 |
| Attack (P1/P3) | 12 / 13 / 14 / 15 | 6 | 6 (1 s/đòn) |
| **Summon (P2)** | (mapping user tự chỉnh trong `_SUMMON_ROWS`) | **6** | **6 (1 s anim)** |

**LƯU Ý**: FoundingTitan **KHÔNG có Run** — đã bỏ `_RUN_ROWS`, `_RUN_FRAMES`, `_is_running` hoàn toàn. Khi di chuyển chỉ Walk tốc độ cố định.

Summon animation đặc biệt: chạy 6 frame trong 1 s → **HOLD col=5 (frame cuối) trong 2 s** → spawn 10 minion → cooldown 10 s → lặp.

### 3 Phase logic

| Phase | Điều kiện HP | Hành vi |
|-------|--------------|---------|
| **P1** | HP > 60% | HeavyStrikeStrategy (damage ×2.0), range 80 px, cooldown 3 s |
| **P2** | 20% < HP ≤ 60% | Auto-summon liên tục, **vẫn dùng** HeavyStrike khi không bận |
| **P3** | HP ≤ 20% **HOẶC** đã từng ≤ 20% | **TẮT summon vĩnh viễn** (sticky), chỉ HeavyStrike |

**Cờ sticky `_summon_locked`**: latches `True` ngay khi HP chạm `≤20%` lần đầu. Sau đó dù HP có hồi lên > 20% (ví dụ player chưa lấy serum, founding tự hồi 2%/s — chưa implement), summon vẫn không bật lại. Đây là one-way transition.

### Phase 2 — Summon spec

```python
_SUMMON_TOTAL          = 10           # tổng minion/đợt
_SUMMON_RADIUS         = 180.0        # px — bán kính vòng tròn quanh founding
_SUMMON_WAVE_COOLDOWN  = 10.0         # giây sau pause trước đợt kế
_SUMMON_PAUSE          = 2.0          # giữ col=5 trước khi spawn
_MINION_POOL = (                      # 8 loại titan ứng 8 sprite Assets/Titan
    'regular2', 'regular4', 'regular5', 'regular6', 'regular7',
    'wolf', 'towerhunter', 'soldierhunter',
)
```

Cycle 1 đợt summon:
1. `start_summon()` → set `_is_summoning=True`, anim_col=0
2. Animation chạy 1 s (6 frame × 1/6 s = 1 s) đến col=5
3. **Hold col=5 trong 2 s** (`_summon_pause_timer`)
4. Khi pause hết → `_release_summon()`:
   - Spawn đúng 10 minion; mỗi con `random.choice(_MINION_POOL)` độc lập
   - Tên-loại được ánh xạ sang đúng CLASS: `regular{N}`→RegularTitan(variant=N),
     `wolf`→Wolf, `towerhunter`→TowerHunter, `soldierhunter`→SoldierHunter.
     Minion vì thế kế thừa đầy đủ strategy + khả năng tấn công riêng của loại.
   - Mỗi minion tại `(founding.x + cos(i × 36°) × 180, founding.y + sin(i × 36°) × 180)`
   - `minion._direction = founding._direction`; push vào `_summoned_minions`
5. Set `_summon_cd_timer = 10 s`
6. AI tự gọi `start_summon()` lại khi cd ≤ 0 + phase==2

### Public API FoundingTitan

| Method | Mô tả |
|--------|-------|
| `trigger_attack(target=None)` | P1/P3 HeavyStrike. **LUÔN chạy animation** (kể cả target=None hoặc ngoài tầm). Damage CHỈ áp khi target alive + dist ≤ 80px |
| `start_summon()` | P2 only — kích hoạt summon animation; trả False nếu phase≠2 hoặc locked |
| `_release_summon()` | Internal — spawn 10 minion (random 8 loại titan) vòng tròn quanh founding |
| `_check_phase()` | Update `_phase` + `_summon_locked` theo HP hiện tại |
| `update_anim(dt)` | Animation + pause/release/cooldown — gọi từ demo |
| `update(dt)` | AI gốc: auto-summon ở P2, attack target gần nhất ở P1/P3 |
| `draw(screen)` | Render frame theo state (idle/walk/run/attack/summon) |

### Demo (`foundingcheck.py`)

| Phím | Tác dụng |
|------|----------|
| WASD         | Di chuyển manual (không có Run) |
| SPACE        | **Luôn** trigger animation HeavyStrike; damage chỉ khi dummy gần nhất ≤ 80px (không log khi miss) |
| **N**        | Force trigger 1 đợt summon (yêu cầu phase==2 + cd ready + chưa locked) |
| **1 / 2 / 3** | Set HP về 90% / 50% / 15% — test phase transition |
| **J**        | +10% HP — test sticky lock (vào P3 rồi hồi vẫn không summon) |
| R            | Respawn founding + dummies (clear minions) |
| Q / ESC      | Thoát |

**HUD trực quan**:
- Vòng tầm attack 80px (xanh) + vòng spawn 180px (cam) quanh founding
- HP bar với 2 vạch ngưỡng 60% (vàng) và 20% (đỏ)
- Phase label đổi màu theo phase (P1 xanh / P2 vàng / P3 đỏ) + `locked` flag
- Cooldown timers (attack + summon)
- Số minion đã spawn (lũy kế trong demo, không tự cleanup)

**Test flow điển hình**:
1. Bấm `2` → HP 50% → vào P2 → founding tự summon 10 minion sau 1s anim + 2s pause
2. Đợi 10s → đợt summon kế tiếp
3. Bấm `3` → HP 15% → vào P3, summon LOCKED
4. Bấm `J` 3 lần → HP về > 60% → vẫn không summon (sticky)
5. Bấm SPACE gần dummy → HeavyStrike damage = 50 × 2 = 100

### Điều chưa implement (để mở)

- **Serum Fragment resource**: hệ thống tài nguyên `stock.serum` — chờ user thiết kế nguồn drop
- **Hồi 2%/s khi không có serum + ở P3**: stub `_has_serum_fragment() → False`, logic hồi chưa có
- **Phase 3 skill độc nhất**: chỉ có HeavyStrike như P1, chưa có skill riêng cho P3 (vd "Lõi lộ ra, focus 10s")

### File tham chiếu

- `Boss.py` — class `FoundingTitan` (viết lại hoàn toàn từ stub cũ); import thêm `HeavyStrikeStrategy`
- `foundingcheck.py` — demo độc lập với mock đầy đủ (Titan base + RegularTitan + WorldQuery + BurnDecorator)

## 18. Kamikaze — Suicide Bomber (Clustering Target + Death-Explode)

Kamikaze là titan "tự sát" — chạy đến cụm soldier rồi phát nổ. Định nghĩa trong `Titan.py` (KHÔNG ở Boss.py vì không phải boss).

### Spritesheet Kamikaze — `Assets/Special/kamikaze.png` (frame 64×64, 0-indexed)

| Trạng thái | Hàng (N/W/S/E) | Số frame | FPS |
|------------|----------------|----------|-----|
| Walk | 8 / 9 / 10 / 11    | 9 | 6 |
| Run  | 38 / 39 / 40 / 41  | 8 | 6 |
| Attack | **KHÔNG có** — không vẽ animation tấn công, chỉ pause + render GIF nổ |

### Strategy — `Explosion` (NHÓM 4, file `AttackStrategy.py`)

```python
class Explosion(TitanAttackStrategy):
    def __init__(self, damage_main=200, damage_splash=100,
                 radius=80, knockback=60):
        ...
    def execute(self, attacker, target):
        # Center damage = vị trí attacker (KHÔNG phải target)
        from systems.world_query import WorldQuery
        nearby = WorldQuery.find_in_radius(attacker.x, attacker.y, radius, 'soldier')
        for s in nearby:
            if s is target: s.take_damage(damage_main, 'explode')
            else:           s.take_damage(damage_splash, 'explode')
            # Knockback: đẩy soldier ra xa attacker
            ...
```

dtype='explode' để target/decorator có thể xử lý riêng (vd particle effect đặc biệt).

### Hành vi 3 giai đoạn

1. **Idle/Walk**: không có soldier trong `_DETECT_RADIUS = 300 px` → walk tốc độ `_speed`. Không lock target.
2. **Run** (locked): có soldier trong detect radius → pick target qua **clustering** (`_pick_clustering_target`):
   - Mỗi candidate s, đếm `count = số soldier trong _CLUSTER_RADIUS = 60 px quanh s`
   - Pick s có count max; tiebreaker = gần kamikaze nhất
   - Chạy tốc độ `_speed × _RUN_SPEED_MULT (1.5)` về target
   - Cập nhật `_direction` theo vector di chuyển
3. **Pause + Explode**: target vào `_EXPLODE_RADIUS = 80 px` → `trigger_explosion()`:
   - `_is_pausing = True`, `_pause_timer = 1.5 s`
   - Sprite đứng yên frame 0 (walk row hiện tại)
   - Flash đỏ overlay: `intensity` tăng dần 0→1, nháy với tần số `6 + 14×intensity` Hz
   - Khi `_pause_timer ≤ 0` → `_release_explosion()`:
     - `Explosion.execute(self, _target)` → damage + knockback
     - `_has_exploded = True`, `is_alive = False`

### Death-explode (chết trước nổ vẫn nổ)

Override `on_death()`: nếu HP về 0 mà `_has_exploded == False` → gọi `_release_explosion()` trước khi `super().on_death()`. Damage tại vị trí chết — target có thể là None nếu chưa từng lock.

### Target re-pick

Trong `ai_tick(dt)`:
- Nếu `_target is None` hoặc `_target.is_alive == False` hoặc `distance(target) > _DETECT_RADIUS` → gọi `_refind_target()`
- `_refind_target()` query `WorldQuery.find_in_radius(self, 300, 'soldier')` rồi pick clustering
- Nếu không còn soldier trong detect radius → `_target = None` → quay về walk thường (không run)

### Public API

| Method | Mô tả |
|--------|-------|
| `ai_tick(dt)` | Tick AI: refresh target, di chuyển, kiểm tra explode trigger. KHÔNG cập nhật animation. |
| `update_anim(dt)` | Animation Walk/Run + pause + flash. Caller phải gọi riêng |
| `trigger_explosion()` | Force chuyển pause + explode. Trả False nếu đang pause/đã nổ |
| `_release_explosion()` | Internal — execute Strategy + set `_has_exploded` + die |
| `_pick_clustering_target(candidates)` | Clustering pick (public-able để test) |
| `on_death()` | Override — death-explode |
| `draw(screen)` | Render sprite + flash overlay khi pause |

### Demo (`kamikazecheck.py`)

| Phím | Tác dụng |
|------|----------|
| WASD         | Di chuyển manual (chỉ khi AUTO off, walk speed) |
| **T**        | Toggle AUTO mode — kamikaze tự AI |
| **E**        | Force trigger explosion ngay (pause 1.5 s) |
| **H**        | -50 HP (test death-explode: 6 lần = 300 HP về 0) |
| N            | Spawn thêm 1 soldier random — test target re-pick |
| R            | Respawn kamikaze + 10 soldier mới |
| Q / ESC      | Thoát |

Setup: 10 soldier random scatter trong nửa phải màn hình, mỗi con HP 150.

**GIF explosion**: load `Assets/Explosion Kamikaze/explode.gif` qua **PIL/Pillow** (`pip install Pillow`). Tách từng frame thành `pygame.Surface`, play 1 lượt khi `_has_exploded` chuyển True. Nếu PIL chưa cài hoặc GIF lỗi → fallback im lặng (chỉ in log `[BOOM]`).

**Visual cues HUD**:
- Vòng xám 300px = detect radius
- Vòng đỏ 80px = explode radius
- Vòng vàng 60px quanh target hiện tại = cluster radius (chỉ vẽ khi có target)
- Target hiện tại được tô khoanh đỏ dày
- Trong pause: kamikaze flash đỏ pulse + sprite static frame 0

### File tham chiếu

- `AttackStrategy.py` — class `Explosion` (NHÓM 4, sau `GroundSlamStrategy`)
- `Titan.py` — class `Kamikaze` (cuối file); import thêm `Explosion` + `import math`
- `kamikazecheck.py` — demo độc lập với mock WorldQuery + GIF loader qua PIL

## 19. Beast Rock — Knockback rule + Demo entity layout chuẩn

### Pushback rule (Beast rock) — cập nhật

`RockProjectile._on_land()` (AttackStrategy.py) khi đá rơi:

| Loại entity     | Main damage | Splash (AoE 100px) | Pushback MAX (tại tâm) | Hướng                                  |
|-----------------|-------------|--------------------|------------------------|----------------------------------------|
| Soldier         | 175         | 125                | **100 px**             | Random nửa mặt phẳng đối diện Beast    |
| Commander       | 175         | 125                | **50 px** (~50% lính)  | Random nửa mặt phẳng đối diện Beast    |
| Tower / Wall / HQ | 175       | 125                | **KHÔNG** (cố định)    | —                                      |

- `BeastTitan._DEFAULT_PUSHBACK_SOLDIER = 100.0`, `_DEFAULT_PUSHBACK_COMMANDER = 50.0` — 2 hằng số tách biệt thay cho `_ROCK_KNOCKBACK` cũ.
- `RockProjectile.__init__(..., pushback_soldier, pushback_commander, beast_x, beast_y)`. `beast_x/y` để loại hướng pushback về phía Beast.
- **Falloff tuyến tính** theo khoảng cách: `push = max × (1 - dist / aoe_radius)`.
- **Hướng**: rejection sampling random angle, loại hướng có `dot(dir, beast→điểm rơi) < 0`. Beast ở W của điểm rơi → soldier/commander chỉ bị đẩy về E/N/S, không bao giờ về W.
- **Cơ chế tween** (không teleport): set `entity.pushback_vx/vy`, entity tự decay trong `update()` qua `RockProjectile.apply_pushback_tween(self, dt)`. Decay rate `_PUSHBACK_DECAY = 5/s` ⇒ ~0.6–1s là dứt.
- `take_damage(0, 'pushback')` vẫn là tín hiệu phụ cho HUD/log, **không còn được dùng làm cờ miễn nhiễm**. Tower/Wall/HQ tự bị bỏ qua trong `_on_land` (không vào nhánh push), không cần chặn dtype.

### `_demo_dummies.py` — Helper entity chuẩn cho mọi `*check.py`

File `_demo_dummies.py` cung cấp pattern phân phối đồng nhất:

- **`SoldierDummy(x, y, hp=200, label)`** — circle xanh r=14, có HP bar
- **`HeroDummy(x, y, name, hp=600)`** — circle xanh-vàng r=18, viền dày, hiển thị tên (Levi/Mikasa/Erwin/Armin/Jean/Sasha/Eren/Reiner). `entity_type='commander'`, có `pushback_vx/vy` + integrate tween trong `update()` (nhận pushback ~50% soldier).
- **`TowerDummy(x, y, label, hp=800)`** — square 40×40 xám, HP bar, có `stun(duration)`. Không bao giờ bị Beast đẩy (loại trong `_on_land`).

**`spawn_world(W, H, titan_x, titan_y, seed=None) → (soldiers, heroes, towers)`** sinh:
- **10 soldier**: 5 **CỤM** quanh 1 anchor random (radius 60px) + 5 **RANDOM** toàn map
- **3 hero**: random toàn map (tên duy nhất chọn từ pool 8 names)
- **3 tower**: random toàn map
- Tất cả: cách titan ≥ 120px (min_dist_to_titan), cách nhau ≥ 36px

**Helper render**: `draw_all(screen, font, soldiers, heroes, towers)` và `update_all(dt, ...)`.

### Áp dụng cho 9 file `*check.py`

| File | Cách dùng |
|------|-----------|
| `titancheck.py`        | Spawn 10/3/3 background; R=respawn cả entities |
| `armoredcheck.py`      | Giữ `DummyTarget` chính + thêm 10/3/3 background |
| `wolfcheck.py`         | Giữ `HealingDummy` chính + thêm 10/3/3 background |
| `towerhuntercheck.py`  | Hybrid: extra tower kế thừa cả `TowerDummy` (visual) + `_MockTower` (isinstance), giữ TowerDummy/SoldierDummy chính |
| `soldierhuntercheck.py`| Giữ 5 SoldierDummy local (test cleave AoE) + thêm 10 extra soldier + 3 hero + 3 tower |
| `beastcheck.py`        | Giữ 3 tower setup + 1 soldier local + thêm 3 tower extra + 10 soldier + 3 hero |
| `foundingcheck.py`     | Giữ 2 SoldierDummy local (test attack range) + 10 extra soldier + 3 hero + 3 tower |
| `kamikazecheck.py`     | Thay 10 soldier random cũ bằng 10 spawn_world (5 cụm + 5 random) + 3 hero + 3 tower; N key spawn thêm bằng `SoldierDummy` |
| `clossalcheck.py`      | Thay 4/2/3 cũ bằng 10/3/3 từ spawn_world, convert sang `MockEntity` để tương thích HUD cũ |

**Convention**: tất cả `_MockWorldQuery` đều có method `find_in_radius(cx, cy, radius, entity_type)` và `find_nearest(cx, cy, entity_type)` hỗ trợ 3 entity_type chuẩn: `'soldier'`, `'commander'` (hero), `'tower'`.

## 20. Priority — Hệ thống ưu tiên mục tiêu của Titan

> Trạng thái: **✅ đã triển khai** — `Priority.py` (root) + `CHECK/prioritycheck.py`

Mỗi loại Titan có "khẩu vị" mục tiêu khác nhau. Thay vì nhét `if/else`
"tôi là loại gì → đánh ai" vào class Titan, phần "chọn mục tiêu" được
tách thành **Strategy Pattern** riêng — y hệt cách `AttackStrategy.py`
tách "đánh thế nào".

### Cấu trúc `Priority.py`

| Thành phần | Vai trò |
|------------|---------|
| `TargetContext` (dataclass) | Ảnh chụp thế giới Titan "nhìn thấy": `hq, walls, towers, soldiers, commanders, blocking_wall, can_reach_hq, attackers, current_target` |
| `TargetPriorityStrategy` (ABC) | `select_target(titan, context) → entity\|None`. Kèm khối dùng lại `_locked_reactive_target()` (khóa mục tiêu) + `_path_target()` (đường tới HQ) |
| `DefaultPriority` | Luật chung: HQ → Wall cản → Tower/Soldier (khi bị đánh) → fallback HQ |
| `ArmoredPriority` | HQ (khi đường thông) → Wall (chỉ khi chặn đường vào HQ; AI tự kích `ArmoredRamStrategy` dash) → Tower/Soldier/Commander (phản ứng) |
| `BeastPriority` | Tower (chủ động, khóa tới chết) → Soldier (chủ động) → Commander (chủ động) → Wall (khi còn chặn HQ) → HQ |
| `KamikazePriority` | Soldier/Commander (chủ động) → HQ → Wall → Tower (phản ứng) |
| `SoldierHunterPriority` | Soldier (chủ động) → HQ → Wall → Tower/Commander (phản ứng) |
| `TowerHunterPriority` | Tower (chủ động, khóa) → HQ → Wall → Soldier/Commander (phản ứng) |
| `WolfPriority` | HQ → Wall → Commander → Tower/Soldier — đảo vị trí Commander lên trên |
| `make_priority_for(titan)` | Factory: tên class Titan → bộ Priority phù hợp (mặc định `DefaultPriority`) |

### Khái niệm cốt lõi

- **entity_type**: mọi mục tiêu có thuộc tính string `entity_type` ∈
  `{'hq','wall','tower','soldier','commander'}`. Priority chỉ đọc
  string này — không phụ thuộc class Tower/WallSection cụ thể.
- **Mục tiêu CHỦ ĐỘNG vs PHẢN ỨNG**: loại "phản ứng" (`_reactive_types`)
  chỉ bị đánh khi chúng tấn công Titan trước; loại "chủ động" thì Titan
  tự đi tìm để đánh.
- **Khóa mục tiêu (lock)**: khi đã quay sang đánh một Tower/Soldier,
  Titan đánh tới chết mới đổi — qua `current_target`.

`CHECK/prioritycheck.py` test độc lập 41 case (không cần pygame).

## 21. Titan_AI — Bộ não tự hành của Titan + CHECKAI

> Trạng thái: **✅ đã triển khai** — `Titan_AI.py` (root) + `CHECKAI/`

Titan **không do người chơi điều khiển** — chúng phải tự quyết định.
`Titan_AI.py` là tầng "bộ não": mỗi frame **điều phối** 3 thành phần
có sẵn (Priority chọn mục tiêu, di chuyển, AttackStrategy đánh).

> Mỗi Titan = thân xác (`Titan.py`/`Boss.py`) + khẩu vị (`Priority.py`)
> + đòn đánh (`AttackStrategy.py`) + bộ não (`Titan_AI.py`).

### Kiến trúc `Titan_AI.py`

| Thành phần | Vai trò |
|------------|---------|
| `WorldView` (ABC) | "Giác quan": AI nhìn thế giới qua đây. `build_context(titan) → TargetContext` |
| `SimpleWorldView` | Bản cụ thể dựng từ list entity; tự tính `blocking_wall` bằng hình học |
| `TitanAI` (ABC) | Vòng AI chung mỗi frame: **sense → decide → act**. HAS-A titan, world, priority |
| `DefaultAI` / `RegularAI` / `ArmoredAI` / `AberrantAI` / `WolfAI` / `TowerHunterAI` / `SoldierHunterAI` / `KamikazeAI` / `ColossalAI` / `BeastAI` / `FoundingAI` | 10 AI con — mỗi loại Titan một bộ não riêng |
| `make_ai_for(titan, world)` | Factory: tên class Titan → AI phù hợp |

**Composition, KHÔNG kế thừa Titan**: `ai = make_ai_for(titan, world)`
rồi gọi `ai.update(dt)` mỗi frame. Titan_AI **không sửa** `Titan.py`/
`Boss.py` — chỉ gọi API công khai của chúng (`trigger_attack`,
`trigger_dash`, `_steam_burst`, `start_summon`...).

### Hành vi đặc thù mỗi AI

- **RegularAI** — tiến HQ, đánh thường; class tự đổi HeavyStrike khi HP<40%.
- **ArmoredAI** — còn giáp + mục tiêu Wall → kích Dash húc; giáp vỡ → melee.
- **AberrantAI** — tự quản nhịp dash: tốc độ ×3 trong 0.6s mỗi 4s.
- **WolfAI** — cắn nhanh; WolfPriority ưu tiên Commander khi bị đánh.
- **TowerHunterAI / SoldierHunterAI** — săn Tower / Soldier theo Priority.
- **KamikazeAI** — lao vào Soldier/Commander gần nhất (run ×1.5) → vào
  80px → `trigger_explosion()`. Tự điều phối, không gọi `ai_tick()` gốc
  để giữ một nguồn giác quan duy nhất (WorldView).
- **ColossalAI** — đọc cooldown của titan, tung Jump Stomp / Steam Burst.
- **BeastAI** — ném đá vào Tower trong `THROW_RANGE`; ngoài tầm → đi lại gần.
- **FoundingAI** — theo 3 phase; P2 tự `start_summon()` mỗi đợt.

### CHECKAI/ — demo kiểm thử AI (lấy CHECKAI làm root)

Viết theo **OOP** đầy đủ (Template Method Pattern). Titan **tự hành** —
người dùng chỉ tác động lên thế giới.

| File | Vai trò |
|------|---------|
| `_ai_bootstrap.py` | "Composition Root" — mock các module giả định (`core.*`, `systems.*`, `characters.*`, `structures.*`, `patterns.*`) để `import Titan/Boss` chạy được. Import 1 dòng là xong |
| `_ai_dummies.py` | Entity giả OOP: `TargetEntity` (ABC) → `Headquarters`, `WallDummy` (`vertical=True` cho tường trái/phải), `TowerDummy`, `SoldierDummy`, `CommanderDummy`. `AttackerEntity` (con trung gian) cho Tower/Soldier/Commander biết bắn trả |
| `_ai_app.py` | `AICheckApp` — base class khung demo dùng chung: pygame, game loop, spawn entity, HUD. `spawn_world_layout()` mặc định đặt HQ ở giữa-phải màn hình, bao quanh bởi 4 `WallDummy` (trên/dưới/trái/phải, cách tâm HQ ~100px). Class con chỉ override `create_titan()` + `title()` |
| `[titan]check_AI.py` (×10) | Mỗi file 1 class con `AICheckApp` ~20-35 dòng — cho RegularTitan, ArmoredTitan, AberrantTitan, Wolf, TowerHunter, SoldierHunter, Kamikaze, ColossalTitan, BeastTitan, FoundingTitan |

Phím điều khiển CHECKAI (tác động THẾ GIỚI, không điều khiển titan):
`SPACE`=+Soldier, `C`=+Commander, `K`=volley bắn titan, `R`=respawn,
`Q`/`ESC`=thoát. HUD hiện State / Target / Reason của AI mỗi frame.

> CrawlerTitan **chưa làm AI** ở đợt này — class `CrawlerTitan` +
> `ClimbBypassStrategy` còn ở dạng khung sơ khai. Sẽ bổ sung sau.

