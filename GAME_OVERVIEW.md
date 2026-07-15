# TITAN'S LAST BASTION — Tài liệu hệ thống & Gameplay đầy đủ

> **Tài liệu này mô tả GAME Ở TRẠNG THÁI HIỆN TẠI CỦA CODE.** Mọi con số, cơ chế,
> luồng xử lý đều được đọc trực tiếp từ source. Đây là tài liệu tham chiếu chính
> cho bất kỳ ai (người hoặc AI) cần hiểu game — không cần đọc các file md cũ.
>
> **Engine:** Python 3.13 + pygame 2.6.1
> **Thể loại:** Tower Defense + Resource Management, 2D top-down
> **Điểm vào:** `game.py` → `main()`

---

## MỤC LỤC

1. [Ý tưởng cốt lõi & Mục tiêu game](#1-ý-tưởng-cốt-lõi--mục-tiêu-game)
2. [Bản đồ thế giới & Hệ thống Vùng (Zone)](#2-bản-đồ-thế-giới--hệ-thống-vùng-zone)
3. [FULL FLOW GAMEPLAY — từ lúc bấm chơi](#3-full-flow-gameplay--từ-lúc-bấm-chơi)
4. [Hai chế độ chơi](#4-hai-chế-độ-chơi)
5. [Hệ thống Tài nguyên & Kinh tế](#5-hệ-thống-tài-nguyên--kinh-tế)
6. [Hệ thống Công trình (Building)](#6-hệ-thống-công-trình-building)
7. [Hệ thống Lính (Soldier) & Điều lính](#7-hệ-thống-lính-soldier--điều-lính)
8. [Hệ thống Tháp (Tower)](#8-hệ-thống-tháp-tower)
9. [Hệ thống Bẫy (Trap)](#9-hệ-thống-bẫy-trap)
10. [Hệ thống Tường (Wall) & HQ](#10-hệ-thống-tường-wall--hq)
11. [Hệ thống Tướng (Commander)](#11-hệ-thống-tướng-commander)
12. [Hệ thống Titan & AI](#12-hệ-thống-titan--ai)
13. [Cơ chế Thám hiểm (Expedition / Dispatch)](#13-cơ-chế-thám-hiểm-expedition--dispatch)
14. [Cơ chế Hậu trận (Post-Combat Settlement)](#14-cơ-chế-hậu-trận-post-combat-settlement)
15. [Hệ thống Item đặc biệt](#15-hệ-thống-item-đặc-biệt)
16. [Save / Load](#16-save--load)
17. [Vòng lặp COMBAT chi tiết — mỗi frame làm gì](#17-vòng-lặp-combat-chi-tiết--mỗi-frame-làm-gì)
18. [UI / HUD / Điều khiển đầy đủ](#18-ui--hud--điều-khiển-đầy-đủ)
19. [Bảng tra cứu nhanh — mọi con số quan trọng](#19-bảng-tra-cứu-nhanh--mọi-con-số-quan-trọng)
20. [MÔ TẢ TỪNG FILE — Mục đích & Bản chất](#20-mô-tả-từng-file--mục-đích--bản-chất)
21. [PHÂN CÔNG — LONG: Hệ thống Titan](#21-phân-công--long-hệ-thống-titan)
22. [PHÂN CÔNG — NHẬT: Hệ thống Commander & Soldier](#22-phân-công--nhật-hệ-thống-commander--soldier)

---

## 1. Ý tưởng cốt lõi & Mục tiêu game

Người chơi là **chỉ huy phòng thủ của pháo đài loài người cuối cùng**. Titan tấn
công từ ngoài rìa bản đồ vào trong. Người chơi phải:

- **Xây dựng kinh tế** (Farm, Workshop, Forge, Training Camp) để có tài nguyên.
- **Xây dựng phòng thủ** (Tháp, Bẫy) trên 3 vòng tường.
- **Huấn luyện lính** và điều lính đóng quân trong tháp.
- **Trực tiếp điều khiển 1 vị Tướng** (Mikasa hoặc Eren) tham chiến bằng WASD + kỹ năng.
- **Sống sót qua các đợt Titan** để bảo vệ **HQ (Trụ sở, HP = 5000)** ở trung tâm.

**Điều kiện THUA:** HQ bị phá (HP về 0).
**Điều kiện THẮNG (Vượt Ải):** Dọn sạch toàn bộ wave của ải hiện tại.

Mục tiêu tối thượng: **vượt hết 5 ải**, trong đó ải 3/4/5 có Boss (Colossal / Beast / Founding).

---

## 2. Bản đồ thế giới & Hệ thống Vùng (Zone)

**Kích thước:** `MAP_W = 170` × `MAP_H = 136` tile, mỗi tile `TILE = 32px`
→ thế giới thật `5440 × 4352 px`. Màn hình `1024×768`, camera cuộn được.

### 3 vòng tường đồng tâm (từ ngoài vào trong)

```
┌─────────────────── FIELD (ngoài cùng, titan spawn ở đây) ────────────────┐
│  ┌──────────────── MARIA (vòng ngoài) ────────────────────────────────┐  │
│  │   ┌──────────── ROSE (vòng giữa) ─────────────────────────────┐    │  │
│  │   │    ┌─────── SINA (vòng trong) ──────────────────┐         │    │  │
│  │   │    │            [ HQ - HP 5000 ]                │         │    │  │
│  │   │    └────────────────────────────────────────────┘         │    │  │
│  │   └───────────────────────────────────────────────────────────┘    │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

- `MARIA_BOX = (14, 13, 156, 123)` (toạ độ tile)
- Mỗi vòng tường gồm nhiều `WallSection` (mỗi đoạn HP = **10.000**).
- `WorldQuery.zone_of(x, y)` trả về `'sina' | 'rose' | 'maria' | 'field'`.

### Luật xây dựng theo vùng (`game.py::_zone_build_allowed`)

| Loại | Field | Maria | Rose | Sina |
|---|:---:|:---:|:---:|:---:|
| **Tháp** (đặt đất) | ❌ | ✅ | ✅ | ✅ |
| **Bẫy** | ✅ | ✅ | ✅ | ✅ |
| **Building** (Farm/Forge/Workshop) | ❌ | ❌ | ✅ | ✅ |
| **Tháp gắn tường** | Đi nhánh snap riêng — đặt được ở MỌI đoạn tường |

→ **Bẫy là loại DUY NHẤT xây được ngoài Field.**

---

## 3. FULL FLOW GAMEPLAY — từ lúc bấm chơi

### Bước 1 — MAIN MENU (`ui/main_menu.py`)

Chạy `python game.py` → `main()` → `run_main_menu()`.
3 lựa chọn: **New Game** / **Continue** (chỉ hiện nếu có `save.json`) / **Exit**.

- **New Game** → hiện hộp xác nhận (`confirm_new_game`) → copy `save_default.json`
  đè lên `save.json` → load như bình thường.
- **Continue** → load thẳng `save.json`.

> **Điểm mấu chốt kiến trúc:** New Game và Continue chạy **CHUNG 1 đường load**.
> New Game chỉ khác ở chỗ ghi đè file save trước. Không có 2 nhánh code khác nhau.

### Bước 2 — Khởi tạo thế giới

`main()` dựng: bản đồ tile → 3 vòng tường (`WallSystem`) → HQ → 11 công trình
khởi đầu + 1 TrainingCamp (bất tử, `is_starter=True`) → `WorldQuery.register_zones()`
→ `DispatchManager.configure()` → load save (`_restore_extra_buildings` →
`_restore_towers` → `_restore_traps` → `_restore_chopped_trees` → `_apply_save`
→ `reconcile_soldiers()`).

### Bước 3 — PHA SẢNH (LOBBY) — `ScreenManager.phase = 'lobby'`

Đây là pha **hoà bình**: KHÔNG có titan, KHÔNG có tướng trên map.
Người chơi tự do làm mọi việc chuẩn bị:

| Hành động | Cách làm |
|---|---|
| **Xây công trình/tháp/bẫy** | Mở Shop (icon sidebar) → chọn thẻ → click bản đồ |
| **Nâng cấp công trình** | Click công trình → panel → nút UPGRADE |
| **Huấn luyện lính** | Click TrainingCamp → tab TRAIN → chọn loại lính |
| **Điều lính vào tháp** | Click tháp → tab GARRISON |
| **Chế vũ khí/đạn/bẫy** | Click Forge → tab CRAFT |
| **Sửa tường** | Click HQ (Castle) → tab Tường → nút Repair |
| **Đi thám hiểm** | Icon sidebar → mở Bản đồ Thám hiểm |
| **Chặt cây** | Click vào cây → popup "Chặt / Không chặt" → rơi ra gỗ |
| **Zoom map** | Lăn chuột (chỉ ở Sảnh) |
| **Áp item lên tháp** | Túi đồ → chọn item → "Apply to Tower" → click tháp |

### Bước 4 — Chọn chế độ & Triệu hồi tướng

Bấm **nút hình thanh kiếm** (góc trên phải) → popup kiếm to hiện 2 vùng:
- Nửa **TRÊN** = `MAIN CAMPAIGN` (Vượt Ải)
- Nửa **DƯỚI** = `FREE TRAINING` (Thao Trường)

Chọn xong → `run_commander_select()` → màn chọn tướng (hiện **ảnh idle** của
Mikasa/Eren) → bấm SUMMON.

Tướng được tạo tại `(hq.x + TILE, hq.y)` với **level/XP khôi phục từ
`_cmdr_saved_stats`** (tướng giữ cấp qua các trận).

### Bước 5 — PHA CHIẾN ĐẤU (COMBAT)

`sm.start_combat(mode)` → mọi thứ chuyển sang combat:
- `dispatch_mgr.retreat_all()` — **rút hết đội thám hiểm về** (giữ đồ, lính về trại).
- Garrison count trong tháp → chuyển thành **entity squad thật** (`_reserve_squads`).
- Zoom bị khoá về 1.0.
- **KHÔNG xây được building thường nữa** — nhưng **VẪN xây được Tháp và Bẫy**.
- Titan bắt đầu spawn theo wave.

**Điều khiển trong Combat:**

| Phím | Tác dụng |
|---|---|
| `WASD` | Di chuyển Tướng (khi ở commander mode) |
| `TAB` | Bật/tắt commander mode (điều khiển tướng ↔ chế độ quản lý) |
| `Chuột trái` | Đánh thường (combo 3 đòn) khi ở commander mode |
| `Q` / `E` / `R` | Kỹ năng tướng |
| `ESC` | Thoát chế độ / Pause menu |
| `K` | Bảng spawn titan thủ công (debug, chỉ combat) |

**Tướng chết:** không thua ngay — `_respawn_timer = 30s`, sau đó có thể respawn
(bấm TAB). Ở **Vượt Ải** tướng chết bị **trừ 1 cấp**; ở **Thao Trường** thì KHÔNG
(cờ `_level_penalty_on_defeat`).

### Bước 6 — Kết thúc trận & Quyết toán → quay lại SẢNH

Xem chi tiết ở [mục 14](#14-cơ-chế-hậu-trận-post-combat-settlement).

### Vòng lặp tổng

```
MENU → SẢNH ⇄ (chọn chế độ → chọn tướng) → COMBAT → quyết toán → SẢNH → ...
                    ↑                                                  │
                    └──────────── (thắng Vượt Ải → level+1) ───────────┘
```

---

## 4. Hai chế độ chơi

### A. VƯỢT ẢI (`MODE_VUOT_AI`) — thử thách chính

- **5 ải**, mỗi ải là 1 file `config/levels/level_N.json`.
- Quản lý bởi `VuotAiWaveManager` (`systems/wave_manager.py`).
- Mỗi ải có: `difficulty`, danh sách `waves` (mỗi wave có `budget` + `max_titans`
  + `reward`), và có thể có `boss_wave` (luôn là wave CUỐI).

| Ải | Difficulty | Boss | Escort budget |
|---|---|---|---|
| 1 | 1.0 | — | — |
| 2 | 1.15 | — | — |
| 3 | 1.3 | **Colossal** | 760 |
| 4 | 1.5 | **Beast** | 920 |
| 5 | 1.7 | **Founding** | 1120 |

**Thuật toán sinh titan mỗi wave** (`_roll_titans`):
Rút thăm CÓ TRỌNG SỐ từ `weights` cho tới khi **cạn `budget`** hoặc **đạt
`max_titans`**. Giá quy đổi (`WAVE_TITAN_COSTS`):
`Regular=15, Wolf=20, Kamikaze=20, SoldierHunter=25, TowerHunter=25, Armored=45`.
Sau đó `_chunk()` chia thành các **cụm 2–4 con** spawn cùng lúc.

**Thắng** → `sm.advance_level()` (mở ải sau) + nhận `completion_reward`.
**Thua** (HQ vỡ) → **PHẠT: −20% tài nguyên cơ bản + Tướng −1 cấp** (sàn cấp 1).
Chơi lại ngay, tường/công trình **giữ nguyên hư hại**.

Boss wave có màn **intro riêng** (`ui/vuot_ai.py::run_boss_intro`) và **thanh máu
boss** trên HUD.

### B. THAO TRƯỜNG TỰ DO (`MODE_THAO_TRUONG`) — luyện tập

- **Không phạt, không lên ải.** Chỉ để luyện tập/test.
- Người chơi **tự chọn wave bắt đầu**, rồi bấm "Wave tiếp theo" thủ công.
- Titan sinh bởi logic `TT_*` ngay trong `game.py` (không dùng `wave_manager`).
- Ngân sách: `TT_BUDGET_BASE=300 + 80×wave`, trần `2000`, tối đa `150` titan/wave.
- Loại titan mở khoá dần theo wave (`TT_TITAN_UNLOCK_LEVEL`):
  Regular/Wolf từ w1 · Kamikaze/SoldierHunter từ w2 · TowerHunter từ w3 · **Armored từ w4**.
- Trọng số theo 4 tier (`TT_WEIGHTS`), bão hoà sau wave 20.
- Spawn ở 4 hướng (N/S/E/W), cách tường `8` tile, né vùng góc (`TT_CORNER_MARGIN=16`).

---

## 5. Hệ thống Tài nguyên & Kinh tế

### Các loại tài nguyên (`ResourceBundle` — `core/game_state.py`)

**Cơ bản:** `wood`, `stone`, `food`, `ore`
**Đặc biệt:** `anti_stun`, `serum`, `titan_pheromone`
**Quặng:** `fire_ore`, `ice_ore`, `electric_ore`, `water_ore`, `wind_ore`, `acid_ore`, `anti_armor_ore`
**Slot vũ khí:** `tower_weapon`, `soldier_weapon`, `trap` (slot chung) + `basic_projectlie`,
`ice_projectlie`, `electric_projectlie`, `water_projectlie`, `sword`, `spear`, `arrow`,
`thorn_trap`, `suriken_trap`, ... (slot cụ thể)

### ⚠️ FOOD KHÔNG PHẢI LÀ KHO — FOOD LÀ **TỐC ĐỘ (rate)**

Đây là điểm dễ hiểu nhầm nhất của game:

- `Farm.produce()` trả về **túi RỖNG** — Farm KHÔNG tích food vào kho.
- Food chỉ tồn tại dưới dạng **food/s** = `total_food_production_rate()` =
  tổng `PRODUCTION_RATE / CYCLE_TIME` của mọi Farm còn sống.
- Food/s dùng để **giới hạn số lính nuôi được** (upkeep), KHÔNG phải để mua đồ.

**Bất biến kinh tế (2 điều kiện phải luôn đúng):**
```
tổng upkeep lính  ≤  tổng food/s
tổng weapon_used  ≤  tổng weapon_stock
```

### Cơ chế "lính thiếu" (hungry / disarmed)

Nếu vi phạm bất biến (vd Farm bị phá → food/s tụt), lính bị **ĐÌNH CHỈ**:
- `_hungry` — lính đói (thiếu food)
- `_disarmed_soldiers` — lính thiếu vũ khí

Lính "thiếu" **KHÔNG ăn, KHÔNG giữ vũ khí, KHÔNG tham chiến**.
Muốn giải phóng → **xây/nâng cấp Farm hoặc Forge**.
**Đang có lính thiếu thì BỊ CHẶN huấn luyện lính mới.**

### `reconcile_soldiers()` — thuật toán A rồi B

Hàm trung tâm của kinh tế (`structures/buildings/building.py`):

- **Thuật toán A (`_push_deficit`)** — đẩy lính idle vào "thiếu" cho tới khi bù đủ
  thâm hụt. Chia đều cho 3 loại lính, dừng ngay khi VỪA VƯỢT target.
- **Thuật toán B (`_pull_back`)** — kéo lính "thiếu" về idle bằng phần dư. Chỉ thêm
  lính khi CẢ food LẪN weapon đều còn đủ.

Gọi khi: xây/nâng cấp Farm · xây/nâng cấp Forge · `upgrade_limit` · lính thám hiểm
chết · **cuối trận** · sau khi load save · Forge/Farm bị phá. **KHÔNG gọi giữa trận.**

> **Thiết kế quan trọng:** upkeep và phần soldier của `weapon_used` đều được **SUY RA
> (derive)** từ số lính đang phục vụ, KHÔNG phải bộ đếm cộng/trừ thủ công. Nhờ vậy
> lính chết trong combat/thám hiểm tự động đúng, không rò rỉ.

### Loot khi giết titan (`systems/loot_system.py`)

Titan chết → theo `LOOT_TABLE` rơi vật phẩm ra đất (`DroppedLoot`), **click chuột để nhặt**.

| Titan | Loot |
|---|---|
| RegularTitan | ore 60%, anti_stun 20% |
| **ArmoredTitan** | **anti_armor_ore 50%**, stone 80%, serum 10% |
| ColossalTitan | fire_ore 80%, serum 50%, pheromone 20% |
| BeastTitan | pheromone 100%, acid_ore 50%, wood 80% |
| FoundingTitan | serum 100%, pheromone 100%, electric_ore 80% |

**XP cho Tướng** (cùng file): Regular 25 · Armored 50 · Beast 80 · Colossal 100 · **Founding 200**.

---

## 6. Hệ thống Công trình (Building)

File: `structures/buildings/building.py`

| Công trình | Sản xuất | Max Lv | Ghi chú |
|---|---|:---:|---|
| **Farm** | food/s (rate 300 / cycle 60s) | 3 | Nuôi lính. KHÔNG tích kho. |
| **StoneWorkshop** | 8 stone / 60s | 3 | Tích kho thật |
| **WoodWorkshop** | 15 wood / 60s | 2 | Tích kho thật |
| **Forge** | — (cycle 999) | 3 | Cấp **slot vũ khí**, chế tạo đạn/bẫy/vũ khí |
| **TrainingCamp** | — | 3 | Huấn luyện lính. **Là công trình khởi đầu duy nhất, bất tử** |
| **RepairStation** | — | — | Sửa tường 50 HP/section mỗi cycle |

- Mọi building có **HP = 300**. Titan vào Sina **giẫm đạp** (`check_trampling`) phá được.
- `is_starter = True` → **BẤT TỬ** (11 building khởi đầu).
- Nâng cấp qua `_apply_level_bonus()` (tăng `PRODUCTION_RATE` tích luỹ).

**Shop chỉ hiện building/tháp/bẫy** (`_SHOP_BUILDING_ITEMS` lọc từ `BUILDING_DEFS`,
loại bỏ mọi decoration không phải 3 nhóm này). Chi phí xây mỗi loại lấy từ
`balance.BUILD_COSTS` — hiện đặt mặc định **0 cho mọi thứ** (xây miễn phí), chỉ
dùng 3 tài nguyên gỗ/đá/quặng làm trục chi phí, đã sẵn cấu hình tập trung để
chỉnh số sau này.

**Forge — 2 trục nâng cấp độc lập:**
1. `upgrade()` — nâng CẤP Xưởng (1→2→3), cộng **slot tổng** (tower_weapon/soldier_weapon/trap).
2. `upgrade_limit()` — tăng từng **loại vũ khí lẻ** (sword/arrow/spear...).

**TrainingCamp:**
- 3 loại lính: `Warrior` (10s, upkeep 1.0) · `Archer` (12s, upkeep 0.8) · `Lancer` (20s, upkeep 2.0)
- **Lancer bị KHOÁ tới khi trại đạt cấp 3.**
- Nâng cấp trại → **buff HỒI TỐ** cho TOÀN BỘ lính đang sống: `+15% HP/DMG mỗi cấp`.

---

## 7. Hệ thống Lính (Soldier) & Điều lính

File: `characters/soldiers/soldier.py`, `squad.py`, `projectile.py`, `animation.py`

### 3 loại lính

| Loại | HP | DEF | Speed | DMG | Range | CD | Đặc điểm |
|---|---:|---:|---:|---:|---:|---:|---|
| **Warrior** | 200 | 8 | 48 | 10 | 38 | 1.0s | Trâu, chậm, **TAUNTS** (kéo aggro) |
| **Archer** | 40 | 0 | 70 | 30 | **220** | 1.0s | Tầm xa, giòn. Bắn `Arrow` |
| **Lancer** | 75 | 3 | **135** | 30 | 44 | 0.6s | Nhanh. Mở khoá ở trại Lv3 |

- `SQUAD_SIZE = 10` lính / squad.
- Lính hồi máu khi IDLE trong tháp: `5 HP / 2s`.
- `WALL_RADIUS = 18` (khác `BODY_RADIUS=10`) — chặn lính lọt khe tường, nhưng vẫn
  chui được **lỗ tường ĐÃ VỠ**.

### Máy trạng thái lính (`Soldier.update()`)

```
        ┌──── có titan trong tầm ────┐
        ↓                            │
    [COMBAT] ──── không còn titan ──→ [RETREAT] ──── về tới tháp ──→ [IDLE]
        ↑                                                              │
        └────────────── titan xuất hiện lại ───────────────────────────┘

    [MOVING] — đang được TRANSFER từ tháp A sang tháp B (dùng A*)
```

- **IDLE**: đứng gác cạnh tháp, hồi máu. Tìm thấy titan → COMBAT.
- **COMBAT**: đuổi/đánh titan. Nếu titan **khác vùng tường** → BẮT BUỘC tìm **lỗ
  tường vỡ** mà lách qua (`gap_aim` + `follow_path`), cố ý không đâm thẳng tường.
- **RETREAT**: về tháp nhà.
- `_homeless` (tháp chủ bị phá) → **đứng yên tại chỗ**, không retreat (không còn nhà).

### Cơ chế ĐIỀU LÍNH — Garrison & Dispatch (`Tower._update_squad_dispatch`)

Đây là **bộ não** của phòng thủ. Tháp TỰ ĐỘNG thả lính:

```
   [idle] ──(có titan trong AGGRO_RADIUS=600 + có quân)──→ [active]
      ↑                                                        │
      │                                                        │ thả từng ĐỢT (wave)
      │                                                        │ tối đa 3 đợt/sự kiện
      │                                                        │ mỗi đợt cách 2.0s
      └────────(nghỉ EVENT_COOLDOWN=5s)──── [cooldown] ←───────┘
```

- **Sức chứa tháp:** `CAPACITY = 8` squad.
- **`wave_order`** — 3 slot loại lính LUÂN PHIÊN mỗi đợt (mặc định Warrior→Lancer→Archer).
- **WIPE-TRIGGERS-NEXT-WAVE:** squad hiện tại chết sạch → **bỏ qua thời gian chờ**,
  thả đợt tiếp theo NGAY.
- **`_reserve_squads`** — squad đã rút về tháp: **entity vẫn được GIỮ NGUYÊN** (không
  xoá, không tạo lại) → khi có titan mới, đúng những entity cũ tái xuất hiện.
- **Transfer:** người chơi chuyển squad từ tháp A → tháp B thủ công (dùng A* pathfinding).

---

## 8. Hệ thống Tháp (Tower)

File: `structures/towers/tower.py`, `projectile.py`, `attackstrategy.py`, `visual_effects.py`

### 4 loại tháp

| Tháp | HP | DMG | Range | CD | Orb (quặng) | Max Lv | Hiệu ứng |
|---|---:|---:|---:|---:|---|:---:|---|
| **BasicTower** | 2000 | 100 | 300 | 2.0s | `ore` (→`fire_ore` giai đoạn 2) | 2 | Lv2: **đạn nổ AoE** (r=80) |
| **ElectricTower** | 2000 | 50 | 400 | 1.5s | `electric_ore` | 2 | **Chain lightning**; Lv2: **điện trường** tồn tại 5s |
| **WaterTower** | 3000 | 75 | 300 | 1.5s | `water_ore` | 2 | Lv1: **knockback**; Lv2: **xoáy nước** hút titan |
| **IceTower** | 3000 | 75 | 400 | 1.5s | `ice_ore` | **3** | **Làm chậm**; Lv2: slow AoE; Lv3: slow cực mạnh (0.97) |

### Cơ chế nâng cấp tháp — "ORB"

**KHÔNG phải nâng cấp theo cấp trực tiếp.** Cơ chế:
1. Bấm UPGRADE → tiêu **quặng riêng của tháp** (`ORB_FIELD`) → `apply_orb()`.
2. Mỗi orb **cộng dồn stat** (damage/duration/radius).
3. Khi stat **vượt ngưỡng** (`LV2_DMG_THRESHOLD = 300`) → **TỰ ĐỘNG lên cấp**.
4. Đạt `MAX_LEVEL` → `can_apply_orb()` = False.

→ `_level` chỉ là **CHỈ BÁO dẫn xuất** từ `_damage`, không phải nguồn sự thật.
(Chi phí orb mỗi lần bấm: `balance.TOWER_ORB_COST`.)

### Strategy Pattern — chọn mục tiêu

`TowerTargetingStrategy`: `NearestTargeting` (mặc định) / `StrongestTargeting` / `FastestTargeting`.

### Tháp gắn tường vs Tháp đặt đất

- **Tháp gắn tường:** snap vào `WallSection`, thay thế đồ hoạ tường. Đặt được ở **mọi
  đoạn tường**. Quản lý trong list `wall_towers`.
- **Tháp đặt đất:** qua `BuildingRegistry`, chỉ trong Maria/Rose/Sina.

### Tháp bị choáng (stun)

Nguồn: **Colossal** (GroundSlam 3s + Jump Stomp 5s) và **đá Beast** (10s).
Tháp choáng → **ngừng bắn + ngừng điều lính**. Có **viền hổ phách nhấp nháy**.
(Item `anti_stun` → miễn nhiễm hoàn toàn.)

---

## 9. Hệ thống Bẫy (Trap)

File: `structures/trap/trap.py`

| Bẫy | Kích thước | HP | Cơ chế |
|---|---|---:|---|
| **ThornTrap** | 5×1 | 500 | Tick 20 dmg/1s cho mọi titan trên bẫy. Hao mòn 10 HP/titan trúng |
| **SurikenTrap** | 5×1 | 800 | Tick 30 dmg/0.5s + **kỹ năng WIND BREATH** (chủ động, tốn `wind_ore`): đẩy titan lùi 600px trong 1s. Gây slow 0.3× |
| **PoisonTrap** | 2×2 | 300 | Giẫm trúng → nhiễm độc, tick 10 dmg/0.5s |
| **ExplodeTrap** | 1×1 | 1 | **1 lần dùng**: giẫm → đếm ngược → **NỔ 300 dmg, r=150** → tự huỷ |
| **BaitTrap** | 3×2 | ∞ | **Không gây damage.** Phát pheromone r=400 **DỤ titan** tới thay vì tới HQ. Hết 15s tự huỷ |

- Bẫy **KHÔNG cản đường titan** — titan đi xuyên qua, bẫy tự quét & tấn công titan.
- Bẫy **là vật tiêu hao 1 lần** — đặt xuống là tiêu luôn, **không hoàn vũ khí** khi chết.
- Bẫy là loại **DUY NHẤT xây được ở Field**.

---

## 10. Hệ thống Tường (Wall) & HQ

File: `structures/wall/wall.py`, `wall_system.py`, `structures/hq.py`

**Composite Pattern:**
```
WallSystem  →  Wall (maria/rose/sina)  →  WallSection (leaf, HP=10.000 mỗi đoạn)
```

- `Wall.take_damage(amount, pos)` — **uỷ quyền xuống ĐÚNG 1 section gần `pos` nhất**.
- Section sập → publish `'wall_breached'` → **tạo LỖ HỔNG** trên bản đồ.
- **Lỗ hổng là cơ chế cốt lõi:** titan và lính đều phải **tìm lỗ mà chui qua**
  (`WorldQuery.find_nearest_gap_center` + `pathmove.gap_aim`).
- Sửa tường (`repair`) → nếu đoạn đã sập được hồi lại → **SỐNG LẠI** + đánh dấu
  `WorldQuery._dead_clusters_dirty = True` (báo pathfinding tính lại).

**HQ (Headquarters):** HP 5000, `ENTITY_TYPE='hq'`, nằm giữa Sina. Vỡ → **`game_over`**.
Vùng castle còn là **vùng HỒI MÁU cho Tướng** (20 HP/1s).

---

## 11. Hệ thống Tướng (Commander)

File: `characters/commanders/commander.py`, `mikasa.py`, `eren.py`

### Chỉ số chung

- `BASE_HP = 300`, `+40 HP mỗi cấp`, `MAX_LEVEL = 10`, `BASE_SPEED = 150`
- `+15% damage mỗi cấp`, `+5% tốc đánh mỗi cấp`
- XP lên cấp: `100 × level`. Lên cấp → **HỒI ĐẦY MÁU**.
- Chết: **−1 cấp** (chỉ Vượt Ải), hồi sinh sau 30s.

### Đánh thường (LMB) — Combo 3 đòn

- Damage: `(25, 35, 60)` — đòn 3 mạnh nhất.
- **Hình nón 56°**, bán kính 90px.
- **Cơ chế "gồng đòn" (recovery gate):** click hụt lúc đang vung = **0 damage**,
  không tính combo (nhị phân, không có chip damage). Có **thanh hồi đòn màu trắng**.
- **STACK DAMAGE lên titan:** đánh liên tiếp → `125% → 150% → 200% → 250%`.
  Ngừng 1.5s → reset.

### Kỹ năng chung

| Skill | Cơ chế |
|---|---|
| **Q** | Slash combo — 3 hit × 40 dmg, r=80 |
| **E** | **Grappling Swing (ODM)** — máy trạng thái `idle → aiming → flying`. Bay tới tháp/titan. 6 charge cơ bản (max 11) |
| **R** | Ult — 10s, r=150, 150 dmg |

### MIKASA
- CD: `Q=5s, E=5s, R=30s`. Mở khoá: `Q ở Lv5`, `R ở Lv10`.
- Thuần cận chiến + ODM.

### EREN — **KIẾN TRÚC 2 DẠNG (dual-form)**
- CD: `Q=3s, E=6s, R=40s`. Mở khoá: `Q Lv3`, `R Lv5`, `E Lv10`.
- **`R` = HOÁ TITAN** (`_enter_titan_form`).

> **Cực kỳ quan trọng:** dạng titan có **HP HOÀN TOÀN RIÊNG** (`_titan_hp = 2000`).
> Damage vào dạng titan **CHỈ trừ `_titan_hp`, KHÔNG đụng `self._hp`** (HP người).
> Hết `_titan_hp` → thoát về dạng người với HP người nguyên vẹn.

Ở dạng titan, **Q/E/R mang ý nghĩa HOÀN TOÀN KHÁC**:
- `Q` = Dash (800 px/s, 0.4s, 50 dmg r=60)
- `E` = **Cuồng nộ** (8s, tự trừ 40 HP/s, aura 30 dmg/0.5s r=100)
- Đánh thường dạng titan: nón **180°** (rộng hơn hẳn dạng người)

---

## 12. Hệ thống Titan & AI

*(Chi tiết đầy đủ ở [mục 21 — phân công Long](#21-phân-công--long-hệ-thống-titan))*

**6 titan thường:** RegularTitan, ArmoredTitan, Wolf, TowerHunter, SoldierHunter, Kamikaze
**3 Boss:** ColossalTitan, BeastTitan, FoundingTitan

Kiến trúc 4 tầng: **Titan (data/animation)** ← **AI (quyết định)** ← **Priority
(chọn mục tiêu)** + **AttackStrategy (cách gây damage)**.

---

## 13. Cơ chế Thám hiểm (Expedition / Dispatch)

File: `systems/dispatch_system.py` + `ui/resource_map_screen.py` + `ui/expedition_overlay.py`

**CHỈ HOẠT ĐỘNG Ở SẢNH.** Vào Combat → tự động rút hết đội về.

### Luồng

1. Mở **Bản đồ Thám hiểm** (icon sidebar) → thấy **CĂN CỨ ở tâm** + các **node** xung quanh.
2. Node càng **XA** → tài nguyên càng **QUÝ** (nhưng càng **NGUY HIỂM**).
   - Mọi node cách tâm ≥ `MIN_DISTANCE = 350` ("khoảng cách tới hạn", vẽ vòng tròn mờ).
   - **6 node cố định — CHỈ gỗ/đá cơ bản**, rải đều 8 hướng quanh CĂN CỨ, luôn sẵn
     có ngay từ đầu game (`seed_default_zones`): Near Forest (wood) · Stone Quarry
     (stone) · Old Grove (wood) · Rock Outcrop (stone) · Timber Camp (wood) ·
     Granite Ridge (stone). Mọi tài nguyên khác (quặng, item đặc biệt) KHÔNG có
     trong bộ node cố định — chỉ ra từ Item Cache.
   - **"Item Cache"** — node ngẫu nhiên, tối đa `MAX_ITEMS = 3` node cùng lúc, spawn
     thêm mỗi `ITEM_SPAWN_INTERVAL = 20s` nếu số node chưa đủ. Tài nguyên rút thăm
     **CÓ TRỌNG SỐ** theo 5 bậc hiếm (`ITEM_RESOURCE_WEIGHTS`): `ore` dễ ra nhất
     (trọng số 100) → `acid_ore`/`wind_ore` vừa (50) → `ice_ore`/`water_ore`/
     `electric_ore` hơi hiếm (20) → `anti_armor_ore`/`anti_stun` hiếm (8) →
     `serum` siêu hiếm (2).
   - **Item Cache tự hết hạn:** node CHƯA từng gửi đội tự biến mất sau
     `ITEM_LIFETIME = 180s` (3 phút). Node ĐANG có đội thám hiểm thì miễn hết hạn
     (hoạt động bình thường) và KHÔNG tính vào giới hạn `MAX_ITEMS`. Node đã TỪNG
     được gửi đội — dù thắng, thua hay bị rút lui — biến mất NGAY khi đội cuối
     cùng rời đi (không chờ thêm, không hết hạn tự nhiên nữa).
3. Chọn node → chọn số lính (**bội số 5**) từ 3 loại → **SEND**.
   → Lính bị **TRỪ KHỎI KHO TRẠI** (`TrainingCamp._idle`) ngay lập tức
   → tháp không dùng được lính đang đi thám hiểm.
4. **Loot VÔ HẠN theo thời gian:** `rate = zone.base_loot_rate × (số lính / 15)`.
   → càng đông lính, loot càng nhanh.

### Rủi ro — Gặp Titan

Mỗi giây, mỗi đội roll xác suất:
```
λ = 0.03 × (số lính / 15) × (khoảng cách / 400)
```
→ **Đông lính VÀ đi xa = dễ gặp titan.** (Đánh đổi với tốc độ loot!)

Gặp titan → vào **HÀNG ĐỢI FIFO**. **Trong lúc xử lý 1 vụ, MỌI đội khác PAUSE**
(không loot, không roll). Overlay hiện banner đếm ngược **10 giây**, 2 lựa chọn:

- **RETREAT** → **BỎ ĐỒ** (loot = 0), lính về trại an toàn.
- **FIGHT** → mở **minigame PING**.
- **Hết 10s không chọn** → tự động rút, bỏ đồ.

### Minigame PING (`PingCombat`)

Kim quay quanh vòng tròn, có **vùng an toàn màu xanh**. Bấm `SPACE` khi kim ở trong
vùng an toàn = qua 1 lượt.

- **Qua đủ N lượt = THẮNG** → giữ đồ, loot tiếp, **miễn nhiễm titan 6s**.
- **TRƯỢT 1 lượt = THUA NGAY** → **MẤT TOÀN BỘ LÍNH + MẤT TOÀN BỘ ĐỒ**.
  (Lính coi như **CHẾT** → callback `_on_soldiers_lost` → `reconcile_soldiers()`.)

**Độ khó** `D = 0.5×(distance/620) + 0.5×(1 − lính/60)`, kẹp [0,1].
→ **Đi XA và ÍT lính = KHÓ NHẤT.**
`D` quyết định: số lượt (2→6), độ rộng vùng an toàn (100°→30°), tốc kim (160→340 °/s).

**Rút chủ động** (từ tab tiến độ) → **GIỮ ĐỒ**, lính về trại.

---

## 14. Cơ chế Hậu trận (Post-Combat Settlement)

Chạy tại `game.py` khi `_end_combat_won is not None`. Thứ tự **8 bước**:

1. **Lưu cấp/XP tướng** vào `_cmdr_saved_stats` → gỡ tướng khỏi map.
2. **Dọn sạch mọi titan** khỏi map, clear `titan_ais`.
3. **Phạt / tiến độ theo chế độ:**
   - Vượt Ải + THẮNG → `advance_level()` + nhận `completion_reward`.
   - Vượt Ải + THUA → **×0.8 tài nguyên cơ bản** + **Tướng −1 cấp** (XP về 0).
   - Thao Trường → không gì cả.
4. **`sm.end_combat()`** → về Sảnh. **HỒI SINH HQ** nếu bị phá (nếu không, lần sau
   vào combat sẽ thua tức thì mãi mãi). **Tường GIỮ NGUYÊN hư hại.**
5. **Trả lính về trại:**
   - Lính tự do trên map còn sống → `return_expedition()` về `TrainingCamp._idle`.
   - Lính trong garrison/reserve của tháp → trả hết về trại. Clear garrison.
   - **Lính chết thì biến mất luôn** (không trả về).
6. **Xoá tháp bị `_disarmed`** (hết đạn) khỏi map + registry.
7. **`reconcile_soldiers()`** — quyết toán Food & Weapon (thuật toán A rồi B).
   Vì upkeep/weapon_used đều SUY RA từ số lính thật → lính chết tự động không còn tính.
8. **`_save_game()`** — lưu toàn bộ.

→ Cuối cùng hiện màn hình **VICTORY / DEFEAT** (`ui/combat_result.py`).

---

## 15. Hệ thống Item đặc biệt

3 item áp **VĨNH VIỄN** lên Tháp. Luồng dùng giống hệt nhau:
**Túi đồ → chọn item → "Apply to Tower" → vào chế độ GHOST (icon bám chuột) →
click 1 tháp để áp → ESC mới thoát** (click được nhiều tháp liên tiếp).

| Item | Cờ trên Tower | Tác dụng | Viền hiển thị |
|---|---|---|---|
| **anti_stun** | `_stun_immune` | `Tower.stun()` thành **no-op hoàn toàn** — miễn nhiễm MỌI nguồn choáng | Vàng nhạt (+2px) |
| **serum** | `_serum_buff` | Mọi đạn tháp mang thêm **debuff giảm hồi máu Founding** (30% → 10%) | Tím (+8px, ngoài cùng) |
| **anti_armor_ore** | `_anti_armor_buff` | Mọi đạn tháp dùng **`dtype='anti_armor'`** → **XUYÊN GIÁP hoàn toàn** ArmoredTitan | **Đỏ (+1px, trong cùng)** |

**Về `anti_armor`:** `ArmoredTitan.take_damage()` giảm **70% mọi damage KHÔNG PHẢI
`anti_armor`**. Với `anti_armor` → ăn **100% damage** + cộng `_antiarmor_hits`;
đủ 25 đòn → **VỠ GIÁP VĨNH VIỄN**.
Cách phá giáp còn lại: để Armored **tự húc tường** đủ 25 lần (`_ram_hits`).

---

## 16. Save / Load

File: `ui/save_manager.py`. 2 file: `save.json` (đang chơi) và `save_default.json`
(bản mẫu "game mới tinh", tự sinh lại mỗi lần `main()` khởi tạo).

**CẢ 2 file ghi qua CÙNG 1 hàm `save_game()`** → luôn cùng schema.

**Nội dung save:** `current_level` · `resources` (mọi field ResourceBundle, lấy động
qua `dataclasses.fields()`) · `commander_stats` (cấp/XP từng tướng) · `wall_sections`
(HP từng đoạn) · `buildings` (HP + level) · `towers` (loại, HP, **`_damage`** — vì
`_level` chỉ là chỉ báo dẫn xuất!, garrison, wave_order, **3 cờ buff vĩnh viễn**
`stun_immune`/`serum_buff`/`anti_armor_buff` — lưu cho cả tháp gắn tường lẫn tháp
đặt đất) · `traps` · `training_idle`
/ `training_hungry` / `training_disarmed` · `hq_hp` · `weapon_stock` / `weapon_used`
(ResourceBundle thật) · **`chopped_trees`** (toạ độ cây đã chặt).

**Lưu khi:** đóng cửa sổ ở Sảnh · Back to Menu · **kết thúc mỗi trận**.

> **Lưu ý kiến trúc:** `OBJECTS` (cây/prop) là **list module-level**. Đầu mỗi lần
> `main()` chạy, nó được **reset về `_ORIGINAL_OBJECTS`** rồi mới xoá lại đúng
> những cây trong `chopped_trees` của save — nếu không, cây chặt ở phiên trước sẽ
> mất vĩnh viễn kể cả khi New Game.

---

## 17. Vòng lặp COMBAT chi tiết — mỗi frame làm gì

Đây là thứ tự **CHÍNH XÁC** các việc xảy ra trong 1 frame combat (`game.py::main()`):

```
┌─ 1. dt = clock.tick(60) / 1000        (frame time, game chạy 60 FPS)
│
├─ 2. effective_zoom = zoom nếu Sảnh, ép 1.0 nếu Combat
│
├─ 3. XỬ LÝ INPUT (for event in pygame.event.get())
│     Thứ tự ưu tiên click chuột trái (RẤT QUAN TRỌNG — cái trên "nuốt" cái dưới):
│       a) pending_tower_buff  → đang ghost áp item lên tháp (modal, ESC mới thoát)
│       b) _chop_target        → popup chặt cây (modal)
│       c) minimap click       → lia camera
│       d) spawn panel         → bảng debug spawn titan (phím K)
│       e) sidebar icon        → shop / túi đồ / thám hiểm
│       f) sword button        → chọn chế độ (chỉ Sảnh)
│       g) shop / inventory / castle menu / tower menu
│       h) click bản đồ        → nhặt loot → cứu lính kẹt → chọn tháp/building/bẫy
│                              → click cây (CHỈ Ở SẢNH)
│
├─ 4. SINH TITAN THEO WAVE
│     Vượt Ải:   _va_pending → mỗi _va_group_timer hết → spawn 1 CỤM (2-4 con)
│     Thao Trường: _tt_pending tương tự (người chơi tự bấm "Wave tiếp theo")
│     Mỗi titan: cls(x,y) → WorldQuery.spawn_entity() → titan_ais.append(make_ai_for())
│
├─ 5. UPDATE LOGIC (theo thứ tự)
│     a) WorldQuery._ensure_frame_cache()   ← DỰNG CACHE 1 LẦN/FRAME (tối ưu cốt lõi)
│     b) for ai in titan_ais: ai.update(dt)     ← AI titan: sense → decide → act
│     c) for e in WorldQuery.all(): e.update(dt) ← mọi entity (lính, đạn, VFX, loot)
│     d) for bldg in buildings: bldg.update(dt)  ← sản xuất + check_trampling()
│     e) for tower: tower.update(dt)             ← bắn + _update_squad_dispatch()
│     f) for trap: trap.update(dt)               ← tự quét & tấn công titan
│     g) commander.update(dt) + WASD movement
│     h) Hồi máu tướng nếu đứng trong _CASTLE_HEAL_RECT (20 HP/1s)
│     i) dispatch_mgr.update(dt)                 ← CHỈ Ở SẢNH
│
├─ 6. KIỂM TRA KẾT THÚC TRẬN
│     HQ chết        → _end_combat_won = False
│     Hết sạch wave  → _end_combat_won = True
│     → nếu != None  → CHẠY QUYẾT TOÁN HẬU TRẬN (mục 14) → về Sảnh
│
├─ 7. RENDER (3 pass)
│     Pass 1: ground tiles (grass/path/stone)
│     Pass 2: Y-SORT CHUNG — gom TẤT CẢ vào render_items rồi sort theo _entity_sort_y():
│               • walls (sort theo section y + priority)
│               • objects (cây/prop/castle)
│               • buildings   (callable closure)
│               • wall towers (callable closure)
│               • entities: titan/lính/tướng/đạn/VFX/loot (callable closure)
│             → sort(key=item[0]) → vẽ theo thứ tự → AI Ở DƯỚI ĐÈ LÊN AI Ở TRÊN
│     Pass 3: corner_down (luôn vẽ sau cùng)
│
├─ 8. VẼ OVERLAY / HUD (không bị Y-sort, luôn trên cùng)
│     viền tháp (stun/anti_stun/serum/anti_armor) → ghost build → HUD tướng
│     → HUD HQ → sidebar → shop/inventory/menu → minimap → popup chặt cây
│     → bản đồ thám hiểm + overlay gặp titan (chỉ Sảnh) → FPS
│
├─ 9. WorldQuery.purge_dead()      ← DỌN entity chết. PHẢI chạy đúng 1 lần/frame
│
└─ 10. pygame.display.flip()
```

### Tối ưu hiệu năng cốt lõi — Frame Cache

`WorldQuery._ensure_frame_cache()` phân loại **TOÀN BỘ entity theo `ENTITY_TYPE`
ĐÚNG 1 LẦN/FRAME** vào `_f_hq / _f_walls / _f_towers / _f_soldiers / _f_commanders`.

**Tại sao bắt buộc:** mỗi titan cần biết "ai đang ở đâu" để chọn mục tiêu. Nếu mỗi
titan tự quét lại toàn bộ entity → **O(số_titan × số_entity)** mỗi frame → với 150
titan (Thao Trường wave cao) là **lag chết**. Cache 1 lần → mọi titan **dùng chung**.

Ngoài ra `WorldQuery` còn cache: **spatial hash tường** (tra tường theo ô lưới) và
**cụm lỗ hổng** (`_dead_clusters`, chỉ tính lại khi `_dead_clusters_dirty`).

### Titan spawn ở đâu?

`tt_spawn_pos(direction)` — spawn ở 4 hướng N/S/E/W, **cách tường 8 tile**, toạ độ
dọc cạnh **random trong phần GIỮA** tường (né `TT_CORNER_MARGIN = 16` tile mỗi đầu).
→ Cố ý **né vùng GÓC** vì titan hay bị kẹt gặm tường tại góc.

---

## 18. UI / HUD / Điều khiển đầy đủ

### Bàn phím

| Phím | Pha | Tác dụng |
|---|---|---|
| `WASD` / `←↑→↓` | Cả 2 | Cuộn camera (khi KHÔNG ở commander mode) |
| `WASD` | Combat | **Di chuyển Tướng** (khi ở commander mode) |
| `TAB` | Combat | **Bật/tắt commander mode**. Tướng chết → respawn (sau 30s) |
| `Chuột trái` | Combat | Đánh thường (commander mode) / chọn đối tượng |
| `Chuột phải` | Cả 2 | Chọn công trình để xem panel |
| `Q` | Combat | Skill Q (commander mode) — **ESC nếu KHÔNG ở commander mode** |
| `E` | Combat | Skill E — giữ để **nhắm ODM**, nhả để bay |
| `R` | Combat | Skill R (Eren: **HOÁ TITAN**) |
| `ESC` | Cả 2 | Thoát chế độ hiện tại theo thứ tự ưu tiên → Pause menu |
| `K` | Combat | Bảng spawn titan thủ công (debug) |
| `SPACE` | Sảnh | Bấm trong **minigame PING** (thám hiểm) |
| Lăn chuột | Sảnh | Zoom map / cuộn shop (khi shop mở) |

**Thứ tự ưu tiên của `ESC`** (cái nào đang mở thì đóng cái đó trước):
`sword popup → commander mode → transfer mode → pending_tower_buff → chop popup
→ (build/shop/inventory/selected/castle menu) → Pause Menu`

### HUD & Panel

| Thành phần | Vị trí | Nội dung |
|---|---|---|
| **HQ Status** | Trên-trái | Avatar + thanh máu HQ (5000) |
| **HUD Tướng** | Trên-trái (dưới HQ) | HP, XP bar, Level, cooldown Q/E/R (hiện **"LvN"** nếu chưa mở khoá), icon antiheal |
| **Banner wave** | Trên-giữa | Vượt Ải: `Level X/5 — Wave Y/Z`, số titan còn sống |
| **Thanh máu Boss** | Trên-giữa | Chỉ khi boss còn sống |
| **Minimap radar** | Trên-phải | Chấm titan (đỏ) / boss / tướng / tường (màu theo HP%). **Click để lia cam** |
| **Sidebar icon** | Phải (giữa) | Shop · Túi đồ · Bản đồ Thám hiểm |
| **Nút kiếm** | Trên-phải | Chọn chế độ (chỉ Sảnh) |
| **FPS** | Trên-phải | Xanh >50 / Vàng >30 / Đỏ |
| **Status message** | Dưới-giữa | Thông báo tạm thời (2s) |

### Panel khi click đối tượng

| Click vào | Panel hiện ra |
|---|---|
| **Tháp** | 2 tab: `GARRISON` (điều lính vào/ra, transfer) + `SQUADS`. Nút **UPGRADE** |
| **TrainingCamp** | 3 tab: `TRAIN` (huấn luyện) + `ROSTER` (danh sách lính, chỉ số, **mục "LÍNH THIẾU"**) + upgrade |
| **Forge** | 3 tab: cấp độ + `LIMITS` (giới hạn vũ khí) + **`CRAFT`** (chế đạn/bẫy/vũ khí) |
| **Farm/Workshop** | Panel đơn giản + nút UPGRADE |
| **SurikenTrap** | Nút **WIND BREATH** (tốn 1 `wind_ore`) |
| **HQ (Castle)** | 2 tab: `Tường` (sửa chữa) + `Tướng` (xem/chọn tướng) |
| **Cây** (chỉ Sảnh) | Popup **"Chặt / Không chặt"** |

---

## 19. Bảng tra cứu nhanh — mọi con số quan trọng

### Titan
| | HP | Speed | DMG | Range | CD |
|---|---:|---:|---:|---:|---:|
| Regular | 1000 | 60 | 50 | 30 | 0.75 |
| Armored | 2500 | 60 | 150 | 40 | 1.0 |
| Wolf | 1500 | 70 | 70 | 40 | 0.5 |
| TowerHunter | 1500 | 70 | 70 | 40 | 0.5 |
| SoldierHunter | 1500 | 70 | 70 | 40 | 0.75 |
| Kamikaze | 1000 | 80 | 50 | 60 | 1.0 |
| **Colossal** | **10000** | 40 | 150 | 40 | 2.0 |
| **Beast** | **12000** | 50 | 175 | **350** | 2.0 |
| **Founding** | **15000** | 50 | 200 | 80 | 3.0 |
| Founding Minion | 500 | 40 | 40 | — | — |

### Phòng thủ
| | Giá trị |
|---|---|
| **HQ** | 5000 HP |
| **WallSection** | 10.000 HP mỗi đoạn |
| BasicTower / ElectricTower | 2000 HP |
| WaterTower / IceTower | 3000 HP |
| Tower CAPACITY | 8 squad |
| Tower AGGRO_RADIUS | 600 px |
| Building (thường) | 300 HP |

### Lính
| | HP | DEF | Speed | DMG | Range | CD | Upkeep | Train |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Warrior | 200 | 8 | 48 | 10 | 38 | 1.0 | 1.0 | 10s |
| Archer | 40 | 0 | 70 | 30 | 220 | 1.0 | 0.8 | 12s |
| Lancer | 75 | 3 | 135 | 30 | 44 | 0.6 | 2.0 | 20s |

### Tướng
| | Giá trị |
|---|---|
| BASE_HP / mỗi cấp | 300 / +40 |
| MAX_LEVEL | 10 |
| XP lên cấp | `100 × level` |
| Damage / cấp | +15% |
| Tốc đánh / cấp | +5% |
| Combo damage | 25 / 35 / 60 |
| Stack lên titan | 125% → 150% → 200% → 250% |
| Eren titan HP | 2000 (RIÊNG) |
| Respawn | 30s |

### Ngưỡng quan trọng
| | Giá trị |
|---|---|
| Vỡ giáp Armored | **25 đòn** (`_ram_hits` HOẶC `_antiarmor_hits`) |
| Armor reduction | **70%** |
| Titan VISUAL_RANGE | 250 px |
| Titan AGGRO_RANGE (priority) | 360 px |
| Chạy nước rút | > 250 px → tốc ×1.5 |
| Telegraph delay | 0.5s (né được!) |
| Founding phase 3 | HP ≤ 30% (**KHOÁ MỘT CHIỀU**) |
| Founding hồi máu | 30% × (máu ĐÃ MẤT) |
| Serum debuff | 30% → **10%**, trong 5s |
| Tower LV2 threshold | damage ≥ 300 |
| Defeat penalty | ×0.8 tài nguyên + Tướng −1 cấp |

---

## 20. MÔ TẢ TỪNG FILE — Mục đích & Bản chất

### `game.py` (~6.100 dòng) — ĐIỂM VÀO & VÒNG LẶP CHÍNH
**Bản chất:** God-file chứa toàn bộ vòng lặp game, render pipeline, xử lý input, UI panel.
- `main()` — khởi tạo + vòng lặp `while True`.
- `WorldQueryView` — cầu nối giữa `WorldQuery` và AI titan (dựng `TargetContext`).
- `ResourceState` — kho tài nguyên **của UI** (song song với `ResourceManager`).
- `BuildingRegistry` — sổ chiếm-ô lưới (nguồn sự thật "ô nào có gì").
- `BUILDING_DEFS` — catalogue mọi thứ đặt được (shop đọc từ đây).
- `_build_blocked_tiles()`, `_kind_tile_offset()`, `_obj_blit_pos()` — hình học đặt đồ.
- `_entity_sort_y()` — **khoá Y-sort** cho toàn bộ render (quyết định ai đè lên ai).
- Render 3 pass: ground tiles → Y-sort chung (walls/objects/buildings/entities) → corner_down.

### `config/` — CẤU HÌNH
| File | Mục đích |
|---|---|
| `balance.py` | **MỌI chỉ số cân bằng gameplay.** Chỉnh sức mạnh ở đây, không ở file khác. Module dữ liệu thuần (chỉ import `ResourceBundle`) → không thể gây vòng lặp import |
| `levels/level_N.json` | Kịch bản wave từng ải Vượt Ải |

### `titans_last_bastion/core/` — NỀN TẢNG (chỉ import stdlib)
| File | Mục đích |
|---|---|
| `entity.py` | `Entity(ABC)` — cha của MỌI vật thể. Có `x, y, is_alive`, `update()`, `draw()` |
| `interfaces.py` | `IAttackable`, `IMovable`, `ISkillUser`, `IUpgradable`, `IProducible`, `ILootable` |
| `game_state.py` | `ResourceBundle` (dataclass, hỗ trợ `+`, `*`, `>=`) — schema tài nguyên |
| `event_bus.py` | `GameEventBus` (Singleton, Observer) — `subscribe`/`publish` |
| `exceptions.py` | `InsufficientResourceError`, `WallBreachError` |

### `titans_last_bastion/systems/` — HỆ THỐNG
| File | Mục đích |
|---|---|
| **`world_query.py`** | **TRÁI TIM.** Sổ đăng ký MỌI entity + truy vấn không gian. Cache theo frame, spatial hash tường, A* grid, **hệ thống zone**, phát hiện lỗ hổng tường |
| `wave_manager.py` | `VuotAiWaveManager` — đọc JSON ải → sinh kế hoạch wave |
| `screen_manager.py` | `ScreenManager` — giữ pha (menu/lobby/combat) + chế độ + màn hiện tại |
| `dispatch_system.py` | Toàn bộ logic Thám hiểm (thuần logic, KHÔNG import pygame) |
| `loot_system.py` | `LOOT_TABLE`, `DroppedLoot`, cấp XP cho tướng |
| `pathmove.py` | **Steering O(1)/frame** — né tường bằng lách góc. Dùng bởi titan & lính |
| `pathfinding.py` | **A* trên lưới 64px** — chỉ dùng khi lính chuyển tháp cự ly xa |
| `sound_system.py` | `SoundManager` (Singleton) — âm thanh **không gian** (pan trái/phải + xa/gần) |

### `titans_last_bastion/characters/` — NHÂN VẬT
*(chi tiết ở mục 21 & 22)*

### `titans_last_bastion/structures/` — CÔNG TRÌNH
| File | Mục đích |
|---|---|
| `hq.py` | `Headquarters` — mục tiêu cuối. Vỡ = thua |
| `wall/wall.py` | `Wall` (Composite) + `WallSection` (Leaf) |
| `wall/wall_system.py` | `WallSystem` — quản lý 3 vòng tường |
| `towers/tower.py` | `Tower` + 4 loại. Chứa **máy trạng thái điều lính** |
| `towers/projectile.py` | 5 loại đạn + `ElectricField`, `WaterVortex` |
| `towers/attackstrategy.py` | Strategy chọn mục tiêu của tháp |
| `towers/visual_effects.py` | `Animation`, `TransientEffect`, `AttachedStatusVFX` |
| `trap/trap.py` | 5 loại bẫy |
| `buildings/building.py` | 6 công trình + **TOÀN BỘ thuật toán kinh tế** (`reconcile_soldiers`) |
| `buildings/resource_manager.py` | `ResourceManager` (Singleton) — kho tài nguyên THẬT |

### `ui/` — GIAO DIỆN (đều là pygame thuần, không giữ game-state)
| File | Mục đích |
|---|---|
| `main_menu.py` | Menu chính (New/Continue/Exit) |
| `commander_select.py` | Màn chọn tướng (có ảnh idle) |
| `mode_select.py` | Nút kiếm chọn Vượt Ải / Thao Trường |
| `combat_result.py` | Màn VICTORY / DEFEAT |
| `pause_menu.py` | Menu tạm dừng |
| `lobby_overlay.py` | Minimap radar, controls, chọn wave Thao Trường |
| `hud_panels.py` | Panel HP HQ (góc trên trái) |
| `icon_sidebar.py` | Sidebar icon (shop/túi đồ/thám hiểm) |
| `vuot_ai.py` | Intro boss, HUD tiến độ wave, thanh máu boss |
| `resource_map_screen.py` | Bản đồ Thám hiểm |
| `expedition_overlay.py` | Banner gặp titan + minigame PING |
| `nine_slice.py` | Hạ tầng vẽ panel/nút/ruy băng RPG |
| `save_manager.py` | Save/Load JSON |

---

## 21. PHÂN CÔNG — LONG: Hệ thống Titan

> Long ơi, đây là **toàn bộ** mảng của bạn. Đọc kỹ phần này là hiểu hết titan.

### 21.1 — 5 FILE CỦA BẠN

```
titans_last_bastion/characters/titans/
├── titan.py           (1.930 dòng) — 6 titan thường: data, sprite, animation, damage
├── boss.py            (1.664 dòng) — 3 boss: Colossal, Beast, Founding
├── ai.py              (2.669 dòng) — TOÀN BỘ AI: nhận thức → quyết định → hành động
├── priority.py          (732 dòng) — CHỌN MỤC TIÊU (Strategy Pattern)
└── attackstrategy.py    (768 dòng) — CÁCH GÂY DAMAGE (Strategy Pattern) + RockProjectile
```

### 21.2 — KIẾN TRÚC 4 TẦNG (cực quan trọng)

Một titan hoạt động nhờ **4 object riêng biệt** phối hợp:

```
   ┌─────────────────────────────────────────────────────────────┐
   │  Titan  (titan.py / boss.py)                                │
   │  → DATA + SPRITE + ANIMATION + take_damage()                │
   │  → KHÔNG tự quyết định gì cả. Chỉ là "thân xác".            │
   └────────────────────────┬────────────────────────────────────┘
                            │ được điều khiển bởi
                            ↓
   ┌─────────────────────────────────────────────────────────────┐
   │  TitanAI  (ai.py)  ← "BỘ NÃO"                               │
   │  Mỗi frame chạy 3 bước:                                     │
   │     sense()  → dựng TargetContext (ai đang ở đâu)           │
   │     decide() → chọn mục tiêu  ─────┐                        │
   │     act()    → di chuyển / đánh    │                        │
   └────────────────────────────────────┼────────────────────────┘
                                        │ uỷ quyền cho
                    ┌───────────────────┴──────────────────┐
                    ↓                                      ↓
   ┌──────────────────────────────┐    ┌──────────────────────────────┐
   │ TargetPriorityStrategy       │    │ TitanAttackStrategy          │
   │ (priority.py)                │    │ (attackstrategy.py)          │
   │ → CHỌN AI ĐỂ ĐÁNH            │    │ → GÂY DAMAGE NHƯ THẾ NÀO     │
   └──────────────────────────────┘    └──────────────────────────────┘
```

**Tại sao tách 4 tầng?** Để đổi hành vi titan mà **không sửa class Titan**.
Ví dụ: muốn 1 con Regular biết săn tháp → chỉ cần gán cho nó `TowerHunterPriority`.

### 21.3 — 6 TITAN THƯỜNG (`titan.py`)

| Titan | HP | Speed | DMG | Range | CD | Cơ chế ĐẶC BIỆT |
|---|---:|---:|---:|---:|---:|---|
| **RegularTitan** | 1000 | 60 | 50 | 30 | 0.75s | **ENRAGE:** HP ≤ 50% → đổi sang `HeavyStrikeStrategy` (×3.5 dmg) |
| **ArmoredTitan** | **2500** | 60 | 150 | 40 | 1.0s | **GIÁP + DASH** (xem dưới) |
| **Wolf** | 1500 | 70 | 70 | 40 | 0.5s | Dùng `Incurable` — **dtype `antiheal`** (×2.5 dmg + CHẶN HỒI MÁU) |
| **TowerHunter** | 1500 | 70 | 70 | 40 | 0.5s | Chuyên **săn tháp** (×3 dmg lên tháp) |
| **SoldierHunter** | 1500 | 70 | 70 | 40 | 0.75s | Chuyên **săn lính** (×3, có cleave). Sprite sheet **2 kích thước frame khác nhau** (192px & 64px) |
| **Kamikaze** | 1000 | 80 | 50 | 60 | 1.0s | **TỰ NỔ** (xem dưới) |

#### ArmoredTitan — cơ chế phức tạp nhất

**GIÁP:**
- `ARMOR_REDUCTION = 0.7` → **giảm 70% MỌI damage** không phải `anti_armor`.
- `dtype='anti_armor'` → ăn **100% damage** + `_antiarmor_hits += 1`.
- **VỠ GIÁP** khi: `_ram_hits >= 25` **HOẶC** `_antiarmor_hits >= 25`.
- `_break_armor()` → đổi strategy về thường, **đẩy titan RA KHỎI tường** (chống kẹt).
- Vỡ giáp là **VĨNH VIỄN** — sau đó `ArmoredAI._transform_to_regular()`.

**CHU KỲ DASH (máy trạng thái trong `update_dash_cycle()`):**
```
   [idle] → trigger_dash() → [dashing] (tốc ×3, tối đa 300px)
                                  │
                       chạm tường (≤55px)
                                  ↓
                          end_dash_on_hit()
                          → damage 'ram' (×20!)
                          → _ram_hits += 1  ← MỖI LẦN HÚC TRÚNG = +1
                                  ↓
                            [stagger] (0.3s)
                                  ↓
                            [recoil] (lùi 100px)
                                  ↓
                               [idle]
```
> **Trả lời câu hỏi hay gặp:** Đúng, **1 lần húc trúng = mất đúng 1 lần trong 25**.
> `end_dash_on_hit()` tắt `_is_dashing` ngay đầu hàm nên không thể đếm 2 lần cho 1 cú húc.

#### Kamikaze — 2 đường AI riêng biệt (dễ nhầm!)

- `KamikazeAI` (trong `ai.py`) — đường CHÍNH, dùng trong game.
- `Kamikaze.ai_tick()` (trong `titan.py`) — đường AI thủ công đơn giản hơn, **TÁCH BIỆT**.

Cơ chế: phát hiện mồi trong `DETECT_RADIUS=300` → **chọn cụm ĐÔNG NHẤT** (thuật toán
O(n²) `_pick_clustering_target`) → lao tới (tốc ×1.5) → vào `EXPLODE_RADIUS=60` →
**dừng 1s** (báo trước) → **NỔ** (`Explosion` ×4 dmg, AoE 80, knockback 80).
**Chết kiểu gì cũng NỔ** (`on_death` cũng gọi `_release_explosion`).

### 21.4 — 3 BOSS (`boss.py`)

#### ColossalTitan — HP 10.000, "kẻ khống chế tháp"
| Skill | Cơ chế |
|---|---|
| **Đòn thường** | `GroundSlamStrategy` — ×4 dmg, **STUN tháp 3s** trong r=160 |
| **Steam Burst** (CD 8s) | Xả hơi hình **vành khuyên** (r_in=40 → r_out=140), 200 particle. **100 dmg lính / 150 dmg tướng** |
| **Jump Stomp** (CD 10s) | Nhảy đập đất: **300 dmg**, r=160, **STUN tháp 5s** |

#### BeastTitan — HP 12.000, "pháo binh tầm xa"
- **Đòn thường = NÉM ĐÁ** (`RockProjectile`), tầm **350px**.
- **Đá bay theo QUỸ ĐẠO ĐẠN ĐẠO thật** — công thức adaptive: `v = √(R·g / sin2θ)`,
  `θ=15°`, `g=600`. Vận tốc kẹp `[200, 800]`.
- Đá trúng: **175 dmg cho MỌI mục tiêu trong AoE r=100** (không giảm theo khoảng cách).
- **Đá trúng tháp → STUN 10 giây.**
- Đẩy lùi: lính 100px, tướng 50px.
- ⚠️ **BOM HẸN GIỜ CÓ SẴN:** `v` bị kẹp trần 800 → tầm ném tối đa thật là
  `R = v²·sin2θ/g = 533px`. Hiện `ATTACK_RANGE=350` nên chưa lộ. **Ai tăng tầm >533
  thì MỌI viên đá sẽ rơi ngắn im lặng, không báo lỗi.**
- ⚠️ **Đá KHÔNG có lead prediction** — nhắm vị trí mục tiêu **lúc thả**. Bay ~0.56s
  → mục tiêu di chuyển có thể thoát AoE.

#### FoundingTitan — HP 15.000, "boss cuối"
**3 PHA theo HP:**
- Phase 1: HP > 80%
- Phase 2: 30% < HP ≤ 80%
- Phase 3: HP ≤ 30% — **KHOÁ MỘT CHIỀU (sticky)**: đã vào phase 3 thì **không bao
  giờ quay lại** dù được hồi máu. (Nếu không khoá → **vòng lặp bất tử**!)

**TRIỆU HỒI MINION** (CD 15s): gọi **5 minion** (HP 500, speed 40, dmg 40) trong r=180.
Spawn **né tường**.

**HỒI MÁU KHI TRIỆU HỒI** — công thức đặc biệt:
```
hồi = 30% × (max_hp − hp_hiện_tại)     ← 30% của LƯỢNG MÁU ĐÃ MẤT, không phải 30% max_hp
```
VD: còn 4000/15000 (mất 11000) → hồi 3300 → thành 7300.

**COUNTER: item `serum`** → `apply_heal_debuff()` → hồi chỉ còn **10%** trong 5s
(reset chứ **không cộng dồn**).

⚠️ **BẪY CODE:** `FoundingTitan.trigger_attack()` **TỰ áp damage** (khác mọi titan
khác — chúng chỉ chạy animation). Nên `FoundingAI` **PHẢI override `_resolve_telegraph()`**
để chỉ gọi `trig()`, không gọi `strat.execute()` — nếu không **commander ăn GẤP ĐÔI damage**.

### 21.5 — AI (`ai.py`) — vòng đời mỗi frame

```python
TitanAI.update(dt):
    1. _tick_telegraph(dt)   # đang "ra đòn báo trước" → chờ, có thể né được
    2. context = sense()     # dựng TargetContext qua WorldView
    3. target  = decide(context)   # uỷ quyền cho Priority
    4. act(dt, context)      # di chuyển tới target / đánh nếu trong tầm
```

**Telegraph (báo trước đòn):** `_TELEGRAPH_DELAY = 0.5s`. Titan "giơ tay" trước, hết
0.5s mới **kiểm tra lại tầm** → **người chơi NÉ ĐƯỢC**.

⚠️ **BẪY:** AI nào **override `update()` mà KHÔNG gọi `super()`** thì **PHẢI tự gọi
`_tick_telegraph(dt)`**, nếu không → `_telegraph_timer` không bao giờ giảm →
**titan ĐỨNG ĐƠ VĨNH VIỄN**. (Đã xảy ra với `FoundingAI` trước đây.)
Các AI override `update()`: `RegularAI`, `ArmoredAI`, `KamikazeAI`, `ColossalAI`,
`BeastAI`, `FoundingAI`.

**Di chuyển (`_move`)**: dùng `pathmove.follow_path()` (steering O(1), lách góc).
Nếu bị tường chặn → tìm **lỗ hổng** qua `WorldQuery.find_nearest_gap_center()` →
`_gap_aim()` (2 pha: căn giữa lỗ trước, rồi mới xuyên qua). Không có lỗ → **PHÁ TƯỜNG**.

**Chạy nước rút:** khoảng cách > `_RUN_THRESHOLD=250` → tốc **×1.5**.

**Bản đồ AI ↔ Titan** (`make_ai_for()`):
| Titan | AI |
|---|---|
| RegularTitan | `RegularAI` |
| ArmoredTitan | `ArmoredAI` |
| Wolf | `WolfAI` |
| TowerHunter | `TowerHunterAI` |
| SoldierHunter | `SoldierHunterAI` |
| Kamikaze | `KamikazeAI` |
| ColossalTitan | `ColossalAI` |
| BeastTitan | `BeastAI` |
| FoundingTitan | `FoundingAI` |
| (khác) | `DefaultAI` |

### 21.6 — PRIORITY (`priority.py`) — chọn mục tiêu

`TargetContext` (dataclass) chứa: `hq`, `walls`, `towers`, `soldiers`, `commanders`,
`visible_*` (trong `VISUAL_RANGE=250`), `blocking_wall`, `can_reach_hq`, `attackers`.

**Luật chung mọi Priority:**
1. **`_locked_reactive_target`** — ai đánh mình thì đánh lại (khoá mục tiêu).
2. **`_same_zone` filter** — CHỈ đánh mục tiêu **CÙNG VÙNG TƯỜNG** (`_same_zone_only`).
   → Titan ngoài Maria **không đánh xuyên tường** vào lính trong Sina.
3. **`_maybe_visible_target`** — roll ngẫu nhiên (CD `2.0s`) xem có bị mục tiêu
   nhìn thấy làm phân tâm không. `AGGRO_RANGE = 360`.
4. Không có gì → **đi tới HQ** (`_path_target`), bị tường chặn → **đánh tường**.

| Priority | Ưu tiên |
|---|---|
| `DefaultPriority` | Lính/tướng gần → HQ |
| `ArmoredPriority` | **TƯỜNG** (chuyên húc tường) |
| `BeastPriority` | **THÁP** (từ xa, ném đá) |
| `KamikazePriority` | **CỤM ĐÔNG NHẤT** |
| `SoldierHunterPriority` | **LÍNH** |
| `TowerHunterPriority` | **THÁP** |
| `WolfPriority` | **TƯỚNG/LÍNH** (antiheal) |

### 21.7 — ATTACK STRATEGY (`attackstrategy.py`) — hệ số damage

| Strategy | ×Mult | dtype | Dùng bởi |
|---|---:|---|---|
| `MeleeRushStrategy` | 1.5 | normal | Titan thường |
| `HeavyStrikeStrategy` | **3.5** | heavy | Regular **enrage** |
| `Incurable` | 2.5 | **antiheal** | **Wolf** |
| `ArmoredRamStrategy` | **20** | **ram** (×3 lên tường) | Armored dash |
| `GroundSlamStrategy` | 4.0 | stomp (+stun tháp) | Colossal |
| `Explosion` | 4.0 | aoe | Kamikaze |
| `TowerHunterStrategy` | 3.0 | — | TowerHunter |
| `SoldierHunterStrategy` | 3.0 | — | SoldierHunter |

### 21.8 — MỌI FILE LIÊN QUAN TỚI TITAN (import chéo)

**Titan IMPORT (phụ thuộc vào):**
```
core/entity.py          → Entity (cha)
core/interfaces.py      → IAttackable, IMovable
core/event_bus.py       → publish 'titan_died'
config/balance.py       → MỌI chỉ số
systems/world_query.py  → tìm mục tiêu, kiểm tra tường, tìm lỗ hổng
systems/pathmove.py     → follow_path, gap_aim (di chuyển né tường)
systems/sound_system.py → âm thanh
structures/towers/tower.py → gọi tower.stun() (Colossal, Beast)
```

**File IMPORT TITAN (dùng titan):**
```
game.py                       → tạo titan, gọi make_ai_for(), vòng lặp update/draw
systems/wave_manager.py       → tên titan trong JSON (KHÔNG import class)
systems/loot_system.py        → LOOT_TABLE + xp_table theo TÊN CLASS titan
characters/titans/__init__.py → export
structures/towers/projectile.py → gọi titan.take_damage(), apply_slow(), apply_knockback()
structures/trap/trap.py       → gọi titan.take_damage(), gán titan.bait_target
characters/soldiers/soldier.py → tìm & đánh titan
characters/commanders/*.py    → đánh titan
```

**Điểm nối quan trọng bạn PHẢI biết:**
- `WorldQuery.spawn_entity(titan)` — **BẮT BUỘC** gọi sau khi tạo, không thì titan
  không tồn tại trong thế giới.
- `titan._ai` — tham chiếu ngược từ titan về AI của nó (dùng bởi `notify_attacked`).
- `titan.bait_target` — do `BaitTrap` gán, AI đọc để đổi mục tiêu.
- Mọi damage vào titan đi qua **`Titan.take_damage(amount, dtype, attacker)`**.
- `dtype` **thực sự có tác dụng** chỉ với: `'anti_armor'` (xuyên giáp), `'suriken'`
  (slow 0.3× trong 2s), `'antiheal'` (chặn hồi máu). Các dtype khác (`fire`/`ice`/
  `electric`/`water`) **hiện KHÔNG có hiệu ứng gắn với chuỗi dtype** — hiệu ứng của
  chúng (slow/chain/knockback) được áp qua **hàm riêng** (`apply_slow()`, ...).

---

## 22. PHÂN CÔNG — NHẬT: Hệ thống Commander & Soldier

> Nhật ơi, đây là **toàn bộ** mảng của bạn.

### 22.1 — FILE CỦA BẠN

```
titans_last_bastion/characters/commanders/
├── commander.py       (1.135 dòng) — Commander(ABC): HP/XP/combo/skill/E-ODM
├── mikasa.py             (41 dòng) — Mikasa (đơn giản, chỉ override hằng số)
├── eren.py              (807 dòng) — Eren + TOÀN BỘ dạng Titan
└── assets_config.py      (46 dòng) — Bố cục sprite sheet

titans_last_bastion/characters/soldiers/
├── soldier.py           (706 dòng) — Soldier(ABC) + Warrior/Archer/Lancer
├── squad.py             (109 dòng) — Squad (10 lính) + đội hình
├── projectile.py        (122 dòng) — Arrow (đạn Archer)
├── animation.py         (361 dòng) — CommanderAnimator + load_clips (DÙNG CHUNG cả 2!)
└── assets_config.py      (37 dòng) — Bố cục sprite lính
```

> ⚠️ **Lưu ý:** `animation.py` nằm trong thư mục `soldiers/` **nhưng được DÙNG BỞI CẢ
> COMMANDER**. `Commander.__init__` gọi `load_clips()` + `CommanderAnimator` từ đây.
> Đây là hạ tầng animation dùng chung, không phải chỉ của lính.

### 22.2 — COMMANDER — quy trình xử lý

#### Vòng đời
```
Sảnh: chọn tướng (run_commander_select)
   ↓ tạo với level/xp từ _cmdr_saved_stats
Combat: WorldQuery.spawn_entity(commander)
   ↓ TAB bật commander_mode → WASD + LMB + QER
Giết titan → loot_system cấp XP → gain_xp() → lên cấp → HỒI ĐẦY MÁU
   ↓
Chết → _on_defeat() → −1 cấp (chỉ Vượt Ải) → respawn sau 30s
   ↓
Cuối trận → lưu level/xp vào _cmdr_saved_stats → gỡ khỏi map
```

#### Máy trạng thái animation
`idle / walk / attack1 / attack2 / attack3 / skill_q / skill_e / skill_r / hurt / dying / win`
→ `CommanderAnimator.set_state()`. Animation **one-shot tự chuyển về idle**.

#### Đánh thường (`basic_attack()`) — chi tiết
1. **Gate hồi đòn** (`_attack_recovery_gate()`): đang trong nửa đầu animation vung →
   click bị **NUỐT** (0 dmg, không tính combo). Vẽ **thanh trắng** báo tiến độ.
2. Combo `attack1 → attack2 → attack3` → damage `(25, 35, 60)`.
3. Nhân hệ số cấp: `× (1 + 0.15 × (level−1))`.
4. Quét **hình nón 56°**, bán kính 90px (`_in_attack_cone`).
5. Trúng titan → **stack damage** `125% → 150% → 200% → 250%` (reset sau 1.5s không đánh).

#### Skill E — Grappling Swing (ODM) — phức tạp nhất
Máy trạng thái: `idle → aiming → flying → (aiming | idle)`
- Giữ `E` → vào **aiming**, hiện mũi tên nhắm.
- **Chỉ hợp lệ khi mũi tên chạm THÁP hoặc TITAN** (`E_TARGET_PAD_PX = 24`).
- Nhả → **flying** (0.35s bay tới).
- **6 charge cơ bản** (tối đa 11, charge thưởng hết hạn sau 6s).
- Bay xuống dốc chậm hơn 30% (`E_DOWNSWING_SLOWDOWN`).

#### EREN — dạng TITAN (điểm khó nhất)

> **KIẾN TRÚC 2 DẠNG HOÀN TOÀN TÁCH BIỆT:**
> - Dạng người: dùng `self._animator`, `self._hp` (kế thừa Commander)
> - Dạng titan: dùng `self._titan_*` (sprite riêng) và **`self._titan_hp` (2000) RIÊNG BIỆT**
> - **Damage vào dạng titan CHỈ trừ `_titan_hp`, KHÔNG BAO GIỜ đụng `self._hp`.**
> - Hết `_titan_hp` → `_exit_titan_form()` → về dạng người, **HP người nguyên vẹn**.

`R` = biến hình. Ở dạng titan, **Q/E/R đổi hoàn toàn ý nghĩa**:
- `Q` = Dash 800px/s, 0.4s, 50 dmg r=60
- `E` = **Cuồng nộ**: 8s, **TỰ TRỪ 40 HP/s**, aura 30 dmg mỗi 0.5s r=100
- Đánh thường: nón **180°** (thay vì 56°)

**Kỹ thuật đáng chú ý trong `basic_attack()` của Eren:** tạm thời **ghi đè 3 hằng số
class** (`BASIC_ATTACK_CONE_HALF_ANGLE_DEG`/`_RADIUS`/`_DAMAGES`) → gọi `super().basic_attack()`
→ **khôi phục lại**. Nhờ vậy tái dùng 100% cơ chế gate/combo/stack của lớp cha.

⚠️ `ErenCommander.draw()` nhánh titan **KHÔNG gọi `super().draw()`** → phải tự vẽ
thanh hồi đòn thủ công.

#### Đòn `antiheal` (Wolf) — counter tướng
`take_damage(dtype='antiheal')` → `_anti_heal_timer = 15s` → **`heal()` bị CHẶN HOÀN
TOÀN** trong 15s (kể cả vùng castle). HUD hiện **icon trái tim gạch chéo**.
- Với **lính**: `_can_heal = False` **VĨNH VIỄN** (nhưng vô hại vì cuối trận lính quy
  về số lượng trong trại, lần train sau là object mới).

### 22.3 — SOLDIER — quy trình xử lý

#### Vòng đời lính
```
TrainingCamp.start_training() → vào _queue (đếm ngược train_time)
   ↓ xong
_spawn_soldier() → vào TrainingCamp._idle  ← LÍNH LÀ *SỐ ĐẾM*, CHƯA CÓ ENTITY!
   ↓ người chơi điều vào tháp (garrison)
Tower.garrison / _garrison_sizes  ← VẪN LÀ SỐ ĐẾM
   ↓ vào Combat
deploy_squad() → TẠO ENTITY THẬT (10 lính/squad) → WorldQuery.spawn_entity()
   ↓ đánh nhau
Sống → về tháp → _reserve_squads (entity ĐƯỢC GIỮ NGUYÊN, chỉ ẩn khỏi map)
Chết → is_alive=False → biến mất
   ↓ cuối trận
Lính sống → return_expedition() về TrainingCamp._idle (lại thành SỐ ĐẾM)
Lính chết → biến mất luôn → reconcile_soldiers() tự động tính lại upkeep
```

> **Điểm mấu chốt:** lính tồn tại ở **2 dạng**: **SỐ ĐẾM** (trong trại/garrison) và
> **ENTITY THẬT** (trên bản đồ khi combat). Hiểu điều này là hiểu toàn bộ hệ thống lính.

#### Điều kiện huấn luyện (`start_training`)
1. Không được có **BẤT KỲ lính "thiếu"** nào (ở bất kỳ trại nào) → chặn ngay.
2. Lancer cần **trại Lv3**.
3. `upkeep hiện tại + train_cost hàng đợi + train_cost mới < tổng food/s`.
4. Forge phải `equip()` được vũ khí (giữ chỗ slot).

#### Máy trạng thái lính (chi tiết ở [mục 7](#7-hệ-thống-lính-soldier--điều-lính))

**Điểm khó nhất — di chuyển qua tường:**
- Lính có `WALL_RADIUS = 18` (khác `BODY_RADIUS = 10`).
- Tường thật = collider 32px cách nhau **59/54px** → có **khe hở 27/22px** giữa các collider!
- Nếu dùng `BODY_RADIUS=10` (< 13.5) → **lính lọt khe = XUYÊN TƯỜNG** (bug).
- Đặt `18` (> 13.5) → chặn khe, nhưng vẫn lọt **lỗ THẬT** (1 tile vỡ: nửa-khe 37-42px > 18).
- → **Lính chỉ qua được chỗ tường ĐÃ VỠ.** ✅

**Lính dùng 2 hệ di chuyển:**
| Khi nào | Dùng gì |
|---|---|
| Đuổi titan, né tường (mỗi frame) | `pathmove.follow_path()` — steering O(1), **buffer-layer** (6 mức độ sâu) |
| Chuyển tháp cự ly xa (transfer) | `pathfinding.AStarPathfinder` — A* lưới 64px |

#### Squad (`squad.py`)
- `SQUAD_SIZE = 10`. `formation_offsets()` xếp đội hình.
- `Squad.set_state()` → **đánh thức đồng loạt** cả squad (lính IDLE nghe theo squad).
- `deploy_squad()` — tạo + đăng ký toàn bộ squad vào world.

#### Arrow (`projectile.py`)
Đạn Archer: `speed=520`, `hit_radius=26`, `lifetime=2s`.
⚠️ **KHÁC đạn tháp:** Arrow nhắm **điểm CỐ ĐỊNH lúc bắn** (có thể trượt).
Đạn tháp (`towers/projectile.py`) **đuổi theo mục tiêu mỗi frame** (luôn trúng).

### 22.4 — MỌI FILE LIÊN QUAN (import chéo)

**Commander/Soldier IMPORT:**
```
core/entity.py, interfaces.py, event_bus.py, game_state.py
config/balance.py                        → mọi chỉ số
characters/soldiers/animation.py         → CommanderAnimator, load_clips (CẢ 2 DÙNG!)
systems/world_query.py                   → tìm titan, tìm tháp, kiểm tra zone
systems/pathmove.py                      → follow_path, gap_aim  (soldier)
systems/pathfinding.py                   → AStarPathfinder      (soldier transfer)
systems/sound_system.py                  → âm thanh
characters/soldiers/projectile.py        → Arrow (Archer)
```

**File IMPORT Commander/Soldier:**
```
game.py                        → tạo tướng, WASD/QER, HUD, respawn, _cmdr_saved_stats
ui/commander_select.py         → chọn tướng (nhận class + ảnh idle)
structures/towers/tower.py     → import SOLDIER_TYPES; điều lính (garrison/dispatch)
structures/buildings/building.py → TrainingCamp huấn luyện; reconcile_soldiers()
systems/dispatch_system.py     → lính đi thám hiểm (qua adapter _ExpeditionBarracks)
systems/loot_system.py         → cấp XP cho commander (gain_xp)
characters/titans/*            → titan tìm & đánh lính/tướng
```

**Điểm nối quan trọng bạn PHẢI biết:**
- `Commander._camera_offset` — biến **CẤP CLASS**, `game.py` set trước khi vẽ (để vẽ
  cone tấn công đúng vị trí mà không cần truyền tham số).
- `commander._level_penalty_on_defeat` — `game.py` set = `not sm.is_thao_truong`.
- `_cmdr_saved_stats` (dict trong `game.py`) — **nơi lưu cấp/XP tướng giữa các trận**.
- `soldier._homeless` — tháp chủ bị phá → lính đứng yên.
- `soldier.NAME` — dùng làm **key** khi trả lính về trại (`return_expedition(NAME, 1)`).
- `TrainingCamp._idle / ._hungry / ._disarmed_soldiers` — **3 pool đếm số lính**.
- **MỌI trại dùng CHUNG 1 SỔ** — các hàm module-level trong `building.py` luôn thao
  tác qua TẤT CẢ trại như 1 pool duy nhất.

---

## PHỤ LỤC — Design Patterns đang dùng

| Pattern | Nơi dùng |
|---|---|
| **Singleton** | `WorldQuery`, `GameEventBus`, `ResourceManager`, `DispatchManager`, `SoundManager` |
| **Strategy** | `TitanAttackStrategy`, `TargetPriorityStrategy`, `TowerTargetingStrategy` |
| **Composite** | `Wall` (composite) + `WallSection` (leaf) |
| **Observer** | `GameEventBus` — `wall_breached`, `titan_died`, `tower_destroyed`, `game_over`... |
| **State Machine** | Soldier (5 state), Tower dispatch (3 state), Armored dash (4 state), Founding (3 phase), Commander E (3 state) |
| **Template Method** | `TitanAI.update()` → hook `_on_decide()`, `_act_in_range()` |
| **Adapter** | `_ExpeditionBarracks` (nối `TrainingCamp` ↔ `DispatchManager`) |
| **Callback injection** | `DispatchManager` `on_loot` / `on_soldiers_lost` (giữ thuần logic, không import ngược `game.py`) |

---

## PHỤ LỤC — Quy tắc kiến trúc (BẮT BUỘC tuân thủ)

```
core/        → CHỈ import stdlib. KHÔNG BAO GIỜ import systems/characters/structures.
config/      → chỉ import core (ResourceBundle). Là leaf → không thể gây vòng lặp.
characters/  → import được core, systems, config
structures/  → import được core, systems, config, characters
systems/     → import được core, config (dispatch_system KHÔNG import pygame)
ui/          → pygame thuần, KHÔNG giữ game-state, nhận dữ liệu qua tham số/callback
game.py      → import được tất cả
```

**Chỉnh cân bằng:** LUÔN sửa ở `config/balance.py`. **KHÔNG** viết số cứng ở file khác.
