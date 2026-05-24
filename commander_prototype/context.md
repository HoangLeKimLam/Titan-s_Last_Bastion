# context.md — Titan's Last Bastion: Commander Prototype

Ghi lại toàn bộ quá trình xây dựng **commander_prototype** từ đầu đến hiện tại.

---

## 1. Bối cảnh dự án

- **Project chính**: `Titan-s_Last_Bastion/` — game Python/Pygame theo phong cách Attack on Titan, bài tập nhóm OOP (IT002).
- **Phần trách nhiệm của user**: Lính (Soldiers), Tướng (Commanders), Vũ khí (Weapons).
- **Mục tiêu prototype**: Xây dựng folder `commander_prototype/` độc lập để thử nghiệm 5 Tướng (Eren, Mikasa, Levi, Armin, Hange) mà không phụ thuộc vào phần code của các thành viên khác.

**Stack**: Python 3.13.7 + Pygame 2.6.1 (SDL 2.28.4), Windows 11.

---

## 2. Kiến trúc tổng thể

```
commander_prototype/
├── _core/               # Copy verbatim từ Titan-s_Last_Bastion/core/
│   ├── entity.py        # Entity(ABC) — lớp cha gốc
│   ├── interfaces.py    # IAttackable, IMovable, ISkillUser, IUpgradable, ...
│   ├── game_state.py    # ResourceBundle, GameState (save/load, defeat penalty)
│   ├── event_bus.py     # GameEventBus — Singleton Observer
│   └── exceptions.py   # InsufficientResourceError, WallBreachError
│
├── assets_config.py     # Sprite pack layout (strip vs folder mode, per-commander)
├── animation.py         # Unified loader + CommanderAnimator (state machine)
├── commander.py         # Abstract Commander(Entity, IAttackable, IMovable,
│                        #   ISkillUser, IUpgradable) — base của 5 tướng
├── eren.py              # ErenCommander — Màn 1 (Knight_player_1.4)
├── mikasa.py            # MikasaCommander — Màn 2 (Knight 2D Pixel Art)
├── armin.py             # ArminCommander — Màn 4 (Warrior pack)
├── soldier.py           # Soldier base + Archer/Lancer/Warrior (Sprint 18)
├── squad.py             # Squad / deploy_squad — cụm 10 lính hình tròn
├── projectile.py        # Arrow — tên bay của Archer
├── stubs.py             # WorldQuery (+structures), DummyTitan/LargeTitan
│                        #   (đánh trả + taunt-aware), ResourceManager, decorators
├── input_handler.py     # PlayerInputHandler (WASD, LMB, Q/R, E, SPACE)
├── main.py              # Pygame harness — game loop + camera + HUD + deploy
└── tests/
    ├── test_commander.py  # 75 unit tests (headless)
    └── test_soldier.py    # 15 unit tests (headless)
```

---

## 3. Quyết định thiết kế cốt lõi (đã chốt với nhóm)

| Quyết định | Lý do |
|---|---|
| Commander kế thừa thẳng Entity (KHÔNG qua Character) | Tài liệu có mô tả Character nhưng nhóm bỏ — tránh layer thừa |
| Thua 1 màn → commander_level -1 (tối thiểu 1) | Thay vì GameState.apply_defeat_penalty riêng, đặt ngay trong `Commander._on_defeat()` |
| Skill method (Q/E/R) đặt trên Commander base | Cả 3 tướng hiện tại dùng chung template; subclass override nếu cần |
| `TARGET_HEIGHT_PX = 100` trên Commander base | Chuẩn hóa chiều cao nhân vật khi render bất kể pack sprite có canvas size khác nhau |

---

## 4. Hệ thống Sprite / Animation

### Hai layout được hỗ trợ

**Strip mode** (Eren, Mikasa):
```python
{"file": "Idle_KG_1.png", "fps": 6, "loop": True}
# 1 PNG = dải N frame nằm ngang
```

**Folder mode** (Armin/Warrior):
```python
{"folder": "idle", "prefix": "Warrior_Idle_", "count": 6, "fps": 6, "loop": True}
# N file PNG riêng lẻ, một frame một file
```

### Character-bbox scaling (auto-normalize height)
- `load_clips()` đo IDLE frame 0 → lấy bbox character (non-transparent pixels).
- `scale = TARGET_HEIGHT_PX / idle_char_height`
- Crop vertical theo union envelope của toàn pack → attack/jump arms không bị xén.
- Kết quả: mọi commander đứng cao ~100px trên màn hình, feet chạm đất.

| Pack | Source frame | Idle char px | Scale | Final |
|---|---|---|---|---|
| Knight_player_1.4 (Eren) | 100×64 | 63 px | 1.587× | ~100px |
| Knight 2D Pixel Art (Mikasa) | 96×84 | 37 px | 2.703× | ~100px |
| Warrior (Armin) | 64–69×44 | 33 px | 3.030× | ~100px |

---

## 5. Commander Base Class (commander.py)

### Kế thừa
```python
class Commander(Entity, IAttackable, IMovable, ISkillUser, IUpgradable):
```

### Hằng số quan trọng
```python
TARGET_HEIGHT_PX = 100        # visual height (px) khi render
BASIC_ATTACK_RADIUS = 130     # cone depth của LMB attack
BASIC_ATTACK_CONE_HALF_ANGLE_DEG = 35.0  # ±35° (70° total)
BASIC_ATTACK_DAMAGES = (25, 35, 60)       # combo step damage
COMBO_RESET_WINDOW = 1.5      # giây không click → reset về attack1

E_RANGE_PX = 250              # default swing distance (mouse 1:1)
E_MIN_RANGE_PX = 60           # clamp dưới
E_MAX_RANGE_PX = 480          # clamp trên
E_BASE_CHARGES = 6            # số lần đu cơ bản mỗi session (Sprint 17: 3→6)
E_MAX_CHARGES = 11            # tổng tối đa (base + bonus); giữ headroom bonus +5
E_BONUS_LIFETIME = 6.0        # giây trước khi bonus charges hết hạn
E_FLIGHT_DURATION = 0.35      # giây một lần bay (đu ngang/lên)
E_AIM_TIMEOUT = 3.0           # tự hủy aim sau N giây không thao tác
E_DOWNSWING_SLOWDOWN = 1.3    # đu XUỐNG → duration ×1.3 (bay chậm hơn ~30%)
E_TARGET_PAD_PX = 20.0        # nới rộng bán kính bắt titan khi kiểm hướng nhắm

BASIC_ATTACK_MIN_LATERAL_PX = 55.0  # bề rộng ngang tối thiểu khi cận chiến (sát mặt)

# Titan-damage STACK (thay cho ×2.5 cũ): 4 đòn LMB liên tiếp trúng titan
TITAN_DMG_STACK_MULTS = (1.25, 1.50, 2.00, 2.50)  # 125/150/200/250% base
TITAN_STACK_RESET_WINDOW = 1.5  # giây không trúng → stack reset về 0

Q_RADIUS = 80; Q_HIT_COUNT = 3; Q_DAMAGE_PER_HIT = 40; Q_DASH_GAP = 60
R_DURATION = 10.0; R_RADIUS = 150; R_DAMAGE = 150
```

### Các method quan trọng
| Method | Mô tả |
|---|---|
| `basic_attack()` | 3-hit combo LMB, cone detection trước mặt, cancel-sớm trong nửa sau animation |
| `use_skill("Q")` | Dispatch `_slash_combo()` — dash tới titan gần nhất + 3-hit AoE |
| `use_skill("R")` | Dispatch `_titan_form()` — bất tử 10s + AoE nổ |
| `begin_aim()` | Bắt đầu E session → state=aiming, charges=3+bonus_pool |
| `set_aim_direction(vx,vy)` | Cập nhật hướng + range từ raw vector (magnitude → range) |
| `confirm_swing()` | Phóng theo hướng hiện tại, tiêu 1 charge |
| `cancel_swing()` | Hủy session (SPACE), set cooldown |
| `_grant_bonus_charge()` | LMB trúng LargeTitan trong session → +1 charge |
| `take_damage(amount, dtype)` | Nếu HP ≤ 0 → `_on_defeat()` (-1 level, revive full HP) |
| `upgrade()` | Tăng level, trừ ResourceManager |

---

## 6. Ba Tướng hiện có

### ErenCommander (Màn 1)
- **Sprite**: `Knight_player_1.4/` — 100×64, 11 states
- **Q — Slash Combo**: dash tới titan gần nhất, chơi `skill_q` (Attack_KG_3, 9 frame), AoE 3×40 damage bán kính 80px
- **E — Đu dây**: xem mục 7
- **R — Titan Form**: bất tử + AoE 150 damage bán kính 150px
- **LMB**: Attack_KG_1 → Attack_KG_2 → Attack_KG_4 (combo 25/35/60)

### MikasaCommander (Màn 2)
- **Sprite**: `Knight 2D Pixel Art/Sprites/with_outline/` — 96×84, `with_outline` variant
- Giống Eren về skill template. Sẽ override khi có skill riêng.

### ArminCommander (Màn 4)
- **Sprite**: `Warrior/Individual Sprite/` — individual PNGs (64–69×44)
- 4 animation đã map: `idle`, `Attack`, `Dash Attack` (→ skill_q), `Dash` (→ skill_e)
- Giống template Eren. Sẽ phát triển thêm khi thêm anim (Run, Hurt, Death...).

---

## 7. Skill E — Đu dây (Grappling Swing)

Thay thế hoàn toàn ODM Surge cũ.

### State machine
```
[IDLE] --(press E)--> [AIMING] --(press E)--> [FLYING] --+
  ^                      |                       |        |
  +-- cancel/timeout ----+    SPACE cancel        +-- charges > 0 --> back to AIMING
                                                   +-- charges == 0 --> back to IDLE + cooldown
```

### Range theo chuột + bắt buộc nhắm trúng mục tiêu (Sprint 12)
- **Tầm phóng (distance)**: co/giãn theo khoảng cách chuột → nhân vật, clamp `[60, 480]` px
  (thu phóng bằng chuột). Vòng nét mảnh ngoài hiển thị max-range.
- **Điều kiện bay (validity) — ĐIỂM ĐÁP (Sprint 14)**: chỉ phóng được khi **điểm đáp**
  (đầu mũi tên = vị trí con trỏ chuột = `origin + aim_dir * aim_range`) **nằm TRÊN**
  một **công trình** (tháp) hoặc **titan** (nhỏ/lớn), trong sai số `E_TARGET_PAD_PX`.
  `set_aim_direction()` → `_aim_endpoint_on_target()` set `_e_aim_valid`.
  Lưu ý: **range vẫn theo chuột** (thu phóng), nhưng phải zoom sao cho con trỏ nằm
  ĐÚNG trên mục tiêu mới bay được.
- **Vì sao đổi (Sprint 14 fix)**: bản ray-cast (Sprint 12/13) bị false-positive khi
  một tháp/titan **tình cờ nằm dọc theo đường ngắm** dù con trỏ trỏ vào chỗ trống
  (vd: ngắm qua tháp giữa để tới chỗ trống vẫn "CAN FLY"). Kiểm theo điểm đáp = "bay
  tới đúng chỗ con trỏ" nên chỉ valid khi con trỏ thực sự nằm trên mục tiêu.
- **Mũi tên**: NHẠT (xám-vàng, mảnh) khi chưa hợp lệ; ĐẬM (vàng sáng, dày + đầu mũi to)
  khi hợp lệ — báo "bay được". `confirm_swing()` no-op nếu chưa hợp lệ (không tốn charge).
- HUD aiming hiển thị `[CAN FLY]` / `[aim a target]`.

### Đu xuống chậm hơn (Sprint 10)
- Khi điểm đáp nằm DƯỚI nhân vật (`target.y > start.y`) → `_e_flight_dur =
  E_FLIGHT_DURATION × E_DOWNSWING_SLOWDOWN` (×1.3 ≈ chậm 30%), cảm giác "rơi có kiểm soát".
- Đu ngang/lên giữ nguyên `E_FLIGHT_DURATION`.

### Đu tiếp giữa không trung — redirect 1 phím + preview khi bay (Sprint 15-16)
- **Preview khi bay (Sprint 16)**: trong lúc `flying`, giao diện ngắm (vòng tròn tầm +
  mũi tên, đậm/nhạt theo lock) vẫn hiển thị và bám chuột (`update_flight_aim()` mỗi frame
  trong `main.py`), để người chơi **thấy và chọn** mục tiêu kế tiếp ngay giữa lúc bay.
- `redirect_flight(vx, vy)`: đang `flying` bấm **E** → **đổi hướng ngay** sang mục tiêu
  con trỏ đang chỉ vào, KHÔNG cần dừng lại để ngắm. Phóng cú bay mới từ vị trí hiện tại.
  Có thể bấm liên tục để **nhảy qua lại nhiều mục tiêu khác nhau** (titan/công trình)
  trong cùng một lượt E.
- Chỉ redirect khi **điểm đáp** (theo con trỏ) nằm trên titan/công trình hợp lệ; nếu con trỏ
  ở chỗ trống thì bỏ qua, vẫn bay tiếp đường cũ.
- Mỗi lần redirect tốn **1 charge** (như một cú bay mới); hết charge thì không redirect được.
- Dùng chung `_compute_aim()` (aim+range+validity) và `_launch_flight()` giữa
  `set_aim_direction`/`update_flight_aim`/`confirm_swing`/`redirect_flight`.

### Bonus charges (vẫn giữ — chỉ đổi phần damage)
- Trong một session E, LMB trúng **LargeTitan** (IS_LARGE=True) → +1 charge (cap 8).
- Bonus charges expire sau `E_BONUS_LIFETIME = 6.0s`. Vòng timer vàng quanh đầu hiển thị TTL.
- **Lưu ý**: damage không còn ×2.5 — đã thay bằng cơ chế stack (mục 8).

### LargeTitan
- `LargeTitan(DummyTitan)`: `IS_LARGE=True`, HP=600, size scale 1.8×.
- Spawn bằng phím **B** ở vị trí chuột. Là grapple anchor hợp lệ cho chiêu E.

---

## 8. Basic Attack — 3-hit Combo

- **LMB** click → lần lượt: `attack1 → attack2 → attack3 → wrap lại attack1`.
- Mỗi bộ 3 lần: 25 / 35 / 60 damage.
- **Cancel sớm**: click trong nửa sau animation chain ngay sang đòn tiếp.
- **Reset 1.5s**: không click 1.5 giây → combo reset về attack1.
- **Hit zone**: hình nón 70° trước mặt, depth 130px. Titan đứng sau lưng không bị đánh.
- **Cận chiến / sát mặt (Sprint 12)**: bề rộng ngang của nón không nhỏ hơn
  `BASIC_ATTACK_MIN_LATERAL_PX = 55`, nên địch đứng **sát ngay cạnh** (kể cả lệch trục
  hoặc `forward ≈ 0`, tức gần như chồng lên nhân vật) vẫn bị đánh trúng. Địch ở **phía sau**
  hướng mặt (`forward < 0`) vẫn miss như cũ. (Fix lỗi "đứng sát địch nhưng không gây sát thương".)

### Cơ chế STACK tăng sát thương lên titan (Sprint 10 — thay cho ×2.5)
- Mỗi đòn LMB **trúng titan** cộng 1 stack. Đòn liên tiếp thứ 1/2/3/4 gây
  **125% / 150% / 200% / 250%** sát thương gốc (`base × TITAN_DMG_STACK_MULTS`).
- Đòn thứ 5 trở đi **giữ mức 250%** (stack cap = 4).
- Không trúng titan trong `TITAN_STACK_RESET_WINDOW = 1.5s` → stack reset về 0
  (đòn kế tiếp lại tính từ 125%).
- Stack độc lập với bộ đếm combo (25/35/60): combo chọn `base`, stack chọn hệ số.
- Chỉ áp dụng cho LMB; **Q/R giữ damage cố định** (không bị stack).
- HUD hiển thị `Titan stack xN (…% next)`.

---

## 9. Input Controls

| Phím | Chức năng |
|---|---|
| WASD | Di chuyển (disabled trong lúc E flying) |
| LMB | Basic attack 3-hit combo |
| Q | Slash Combo (dash + AoE) |
| R | Titan Form (invincibility + AoE) |
| E (lần 1) | Bắt đầu aim (vòng tròn co/giãn theo chuột; mũi tên đậm=bay được, nhạt=chưa) |
| E (lần 2) | Phóng theo hướng + khoảng cách chuột (chỉ khi nhắm trúng công trình/titan) |
| E (khi đang bay) | Đổi hướng ngay sang mục tiêu con trỏ chỉ vào (không cần dừng ngắm), tốn 1 charge |
| SPACE | Hủy E session (drop tại chỗ) |
| RMB (chuột phải) | Chọn titan làm mục tiêu cho lính (vòng vàng) |
| Nút HUD Archer/Lancer/Warrior | Gửi 1 cụm 10 lính loại đó tới titan đã chọn |
| 1 / 2 / 3 | Đổi tướng: Eren / Mikasa / Armin |
| T | Spawn DummyTitan tại vị trí chuột |
| B | Spawn LargeTitan tại vị trí chuột |
| ESC | Thoát |

---

## 10. Terrain

**Map lớn + camera đi theo nhân vật (Sprint 17)**:
- World: `WORLD_WIDTH×WORLD_HEIGHT = 2880×1800`; cửa sổ (viewport) vẫn `960×600`.
- **Camera** căn giữa nhân vật active: `cam = clamp(active.pos - viewport/2, 0, world-viewport)`
  (`_compute_camera`). Vẽ toàn bộ world lên `world_surf` rồi blit đúng vùng viewport ra screen.
  Toạ độ chuột đổi sang world (`_mouse_world_pos`) cho aim chiêu E và spawn T/B.
- **8 tháp** (`TERRAIN_RECTS`) rải khắp world — visual, không collision di chuyển, nhưng
  **được đăng ký làm grapple target** (`WorldQuery.register_structure`) để chiêu E kiểm tra
  điểm đáp hợp lệ. Titan khởi tạo (8 con) cũng rải khắp world.

---

## 11. Sprite Packs và Assets

| Pack | Vị trí | Nhân vật |
|---|---|---|
| Knight_player_1.4 | `../Knight_player_1.4/Knight_player_1.4/Knight_player/` | Eren |
| Knight 2D Pixel Art | `../Knight 2D Pixel Art/Sprites/with_outline/` | Mikasa |
| Warrior (Individual Sprite) | `../Warrior/Individual Sprite/` | Armin |
| Archer (strip 192²) | `../Archer/` | Lính Archer |
| Lancer (strip 320²) | `../Lancer/` | Lính Lancer |
| Warrior (strip 192²) | `../Warrior/` (Warrior_Idle/Run/Attack1/Guard) | Lính Warrior |

**Lưu ý bản quyền (Knight_player_1.4)**: credit `@Jump_Button` khi dùng thương mại. KHÔNG dùng để training AI/ML, NFT, blockchain.

---

## 12. Tests

**121 tests** — tất cả headless (không cần pygame display) — 75 commander + 25 soldier + 21 tower:

| Nhóm | Số test |
|---|---|
| Identity & stats | 3 |
| take_damage / defeat | 5 |
| Skills & cooldowns | 4 |
| Movement | 1 |
| Q — Slash Combo | 6 |
| Basic attack (LMB combo) + cone + cận chiến | ~11 |
| E — Grappling Swing (range chuột + nhắm trúng mục tiêu) | 10 |
| E — range scaling theo chuột | 4 |
| E — down-swing slower | 1 |
| E — mid-flight re-aim | 2 |
| E — bonus charges | 4 |
| Titan-damage STACK (125/150/200/250%) | 5 |
| Mikasa | 4 |
| Armin | 3 |
| Upgrades | 2 |
| LargeTitan | 1 |
| **Soldier** (stats/def/attack/arrow/taunt/titan-retaliation/squad/retarget/regroup/home-zone/retreat/**vanish-into-tower**) | 25 |
| **Tower** (capacity/wave-order/aggro-trigger/3-wave-cap/cooldown/menu/**home-binding/wipe-redeploy**) | 21 |

> Lưu ý: chạy headless cần `pygame` + `pytest`. Trên máy dev (Windows) đã có sẵn;
> nếu chạy nơi khác, cài vào venv: `pip install pygame pytest` rồi
> `SDL_VIDEODRIVER=dummy python -m pytest tests/ -q`.

Chạy: `cd commander_prototype && python -m pytest tests/ -q`

---

## 12B. Hệ thống Lính (Soldiers — Sprint 18)

Lính bộ binh đồng minh, deploy theo cụm để đánh titan.

### File
- `soldier.py` — `Soldier(Entity, IAttackable, IMovable)` base + `ArcherSoldier` /
  `LancerSoldier` / `WarriorSoldier`; `SOLDIER_TYPES` registry. Dùng `load_clips`
  strip-mode (idle/walk/attack, +guard cho warrior), scale nhỏ ~40–48px.
- `squad.py` — `Squad` / `deploy_squad()`: spawn `SQUAD_SIZE=10` lính CÙNG loại
  thành **cụm filled hex nhiều vòng** (`formation_offsets`, `SQUAD_SPACING=52` → các con
  cách nhau ~50px, không đè texture) quanh thành, đăng ký vào `WorldQuery`.
- `projectile.py` — `Arrow`: tên bay thẳng của Archer, gây dame khi tới nơi.

### Stat (3 vai trò)
| Loại | HP | Def | Speed | Dmg | Range | CD | Đặc biệt |
|---|---|---|---|---|---|---|---|
| Archer  | 40  | 0 | 70  | 30 | 220 | 1.0 | bắn `Arrow`, mỏng manh |
| Lancer  | 75  | 3 | 135 | 18 | 44  | 0.6 | nhanh nhất |
| Warrior | 170 | 8 | 48  | 10 | 38  | 1.0 | **taunt** kéo aggro titan |

Dame nhận = `max(1, incoming − DEFENSE)`.

### AI lính (`Soldier.update`)
1. Mất target/target chết → `find_nearest` titan (đánh tiếp con gần nhất).
2. Ngoài tầm → đi thẳng tới titan (chưa có collision). Trong tầm → đánh theo CD
   (melee gây dame trực tiếp; Archer spawn `Arrow`).
3. **Hết titan (hết tấn công) → regroup** (`_regroup`): mỗi lính đi về slot
   `_slot_offset` của mình quanh `Squad.regroup_center()` (anchor = centroid cached
   khi vào idle, reset khi tái giao chiến) → cụm **tản ra như lúc mới xuất thành**
   thay vì chồng đống tại chỗ titan vừa chết.

### Titan đánh trả (`stubs.py`)
- `AGGRO_RADIUS / ATK_DAMAGE / ATK_RANGE / ATK_COOLDOWN`. `_pick_soldier_target()`:
  trong tầm aggro **ưu tiên Warrior đang taunt** (`is_taunting`), không có thì gần nhất.
  Không có lính → **giữ hành vi cũ** (đứng yên / đi tới `_target`) nên commander tests không đổi.
- `LargeTitan` aggro/dame/tầm lớn hơn.

### Thành (base) + thao tác (`main.py`)
- `BASE_RECT` — vùng "THÀNH" nhỏ gần tâm world, lính spawn từ đây.
- **RMB** click titan → `selected_titan` (vẽ vòng vàng quanh titan). Titan chết → bỏ chọn.
- 3 **nút HUD** (góc dưới phải) `Archer/Lancer/Warrior`: LMB nút (khi đã chọn titan)
  → `deploy_squad` 10 lính loại đó tới titan. LMB ngoài nút = đánh thường của tướng (không đụng).
- Lính/Arrow là `Entity` → vòng update/draw + camera (`world_surf`) lo sẵn.

---

## 12C. Tháp phòng thủ (Tower — Sprint 19)

Lớp phòng thủ TỰ ĐỘNG đặt cạnh THÀNH. Người chơi nạp/chỉnh garrison qua menu;
khi titan vào tầm tháp tự xuất quân theo lượt.

### File
- `tower.py` — `Tower(Entity)`: hằng số `CAPACITY=8`, `AGGRO_RADIUS=600`,
  `WAVE_COOLDOWN=3.0s`, `EVENT_COOLDOWN=8.0s`, `MAX_WAVES_PER_EVENT=3`.
  State machine `idle → active → cooldown → idle`. Thân chữ nhật xám + nóc tam
  giác đỏ, nhãn `n/8` phía trên; ring vàng khi active; dashed aggro circle khi
  menu mở (`_highlight_aggro`).
- `tower_menu.py` — `TowerMenu`: panel ~360×260 screen-space ở giữa màn hình.
  Hàng `+/-` cho W/L/A (gọi `Tower.adjust_garrison`, từ chối nếu vượt 8); 3 ô
  Wave 1/2/3 (click → `Tower.cycle_wave_slot`); click ngoài = đóng.
- `tests/test_tower.py` — 17 unit tests headless.

### Cơ chế
- Mỗi tháp **giữ cố định 8 cụm tổng** (mặc định `Warrior:4, Lancer:2, Archer:2`);
  ng/chơi rebalance qua menu, miễn tổng ≤ 8.
- `wave_order` = list 3 loại lính (mặc định `[Warrior, Lancer, Archer]`).
- Khi `find_nearest("titan")` cho ≤ `AGGRO_RADIUS` và còn garrison → vào `active`,
  bắn ngay lượt 1; sau đó mỗi `WAVE_COOLDOWN` (3s) ra 1 cụm 10 lính loại
  `wave_order[index]`; bỏ qua loại rỗng (cycle qua các slot khác trong order).
- Sau 3 lượt — hoặc hết garrison / titan rời tầm — vào `cooldown` 8s rồi mới
  lại nhận sự kiện kế.
- Cụm spawn dùng `squad.deploy_squad` y như nút HUD (10 lính, mỗi lính regroup
  như cũ khi rảnh).

### Tích hợp `main.py`
- `TOWER_SPAWNS` = 2 vị trí cố định (cánh trái/phải BASE_RECT, `0.35/0.65 × WORLD_WIDTH`).
- Tháp đăng ký vào `WorldQuery.register` (cho update/draw + `find_nearest`) và
  `register_structure(tower.bounds())` (cho chiêu E neo).
- Event loop: nếu menu mở → menu xử lý LMB trước (close on outside-click).
  Nếu menu đóng và LMB rơi vào `Tower.bounds()` → mở `TowerMenu`, `lmb_consumed`
  = True (chặn `basic_attack`). Nút HUD deploy cũ vẫn hoạt động song song.
- HUD thêm dòng `Towers (2): n/8[idl], n/8[act] ...` để liếc nhanh trạng thái.

### Phạm vi
- Tháp đứng yên, **không có HP** (titan không phá được tháp) — đơn giản hoá.
- Menu chỉ chỉnh garrison/wave_order; AGGRO_RADIUS/cooldown để hằng.

---

## 12D. Patrol-zone & Retreat-into-tower (Sprint 20 + 21)

Lính giờ **gắn chặt vào tháp đã spawn ra chúng** — không lang thang khắp map,
và khi hết việc thì **đi vào thành rồi biến mất**.

### Hành vi mới (`soldier.py`)
- Mỗi `Soldier` lưu `_home_pos` (toạ độ tháp mẹ) + `_home_radius` (mặc định
  600 = `Tower.AGGRO_RADIUS`). `_acquire_nearest_titan` quét `WorldQuery` rồi
  **lọc bỏ titan ngoài bán kính home** trước khi chọn gần-nhất-tới-lính →
  lính chỉ đánh titan trong vùng tháp.
- Nếu titan đang đuổi đi ra ngoài vùng (vd bị dẫn dụ chạy qua tháp khác) →
  `_target_outside_home_zone` trả True, lính drop target ngay tick kế.
- Khi không còn titan trong vùng → gọi `_retreat_into_home(dt)`: đi về
  `_home_pos + _slot_offset`. Khi cách home ≤ `HOME_VANISH_DIST_PX=6px` thì
  **`is_alive = False`** — lính "đi vào thành" và bị main-loop cull pass
  xoá khỏi `WorldQuery`. Không còn hồi máu trên bản đồ; thay vào đó lính
  rút trọn vào trong tháp.

### Hành vi mới (`tower.py`)
- Tháp truyền `home_pos=(self.x, self.y)` + `home_radius=AGGRO_RADIUS` qua
  `deploy_squad` để buộc cụm lính mới với tháp.
- **Wipe-triggers-next-wave**: Tháp giữ `_active_squad` (Squad vừa deploy).
  Trong `update`, nếu `_active_squad.is_alive == False` và còn waves chưa
  dùng → set `_wave_timer = 0`, lượt kế xả NGAY (bỏ qua `WAVE_COOLDOWN`).
  Vẫn tính vào cap **3 lượt / sự kiện**; sau cap thì cooldown bình thường.

### Hành vi mới (`squad.py`)
- `Squad.__init__` + `deploy_squad` nhận `home_pos` / `home_radius`, truyền
  thẳng xuống mỗi `Soldier` khi khởi tạo. Squad lưu `home_pos`/`home_radius`
  để tham chiếu, và `Squad.is_alive` (đã có) dùng cho wipe-detect ở tháp.

### Loại bỏ (`main.py`)
- **Gỡ HẲN** `BASE_RECT` ("THÀNH"), 3 nút HUD deploy thủ công, cờ
  `selected_titan` và xử lý RMB-select-titan, `deploy_squad` import.
  Soldiers giờ **CHỈ** ra trận từ Tower → game vòng lặp đơn giản hơn.

---

## 13. Lịch sử thay đổi chính

| Sprint | Nội dung |
|---|---|
| 1 | Setup `_core/` (verbatim copy), `stubs.py`, `animation.py` strip mode, `commander.py` base, `eren.py` — prototype chạy được đầu tiên |
| 2 | Fix sprite-strip bug (blitting cả strip → 4 Erens) — slicing 100×64 frame |
| 3 | Thêm LMB 3-hit combo + cone hit zone (hình nón 70°, depth 130px) |
| 4 | Q rework: dash tới titan gần nhất + play `skill_q` (Attack_KG_3) |
| 5 | Mikasa (Knight 2D Pixel Art, 96×84, with_outline), key 1/2 switch |
| 6 | Character size normalization — dual-bbox scaling (idle char height target 168, sau giảm 40% → 100px) |
| 7 | Armin (Warrior pack, individual-file mode, 64–69×44), key 3 |
| 8 | Skill E rework: Đu dây (aim circle + 3 chain swings + bonus charges + ×2.5 damage) |
| 9 | E range scaling theo chuột (phạm vi phóng co giãn live) |
| 10 | E rework: (a) chỉ đu được khi tia nhắm trúng **công trình** (tháp) hoặc **titan** (nhỏ/lớn) — bám mục tiêu gần nhất; (b) đu **xuống** chậm hơn ×1.3; (c) bấm E khi đang bay để **đu sang công trình khác** giữa chừng. Damage titan đổi sang **stack 125/150/200/250%** (4 đòn LMB liên tiếp, cap 250%, reset 1.5s) — bỏ ×2.5. Tháp terrain đăng ký làm grapple anchor (`WorldQuery.register_structure`). |
| 11 | **Gỡ** ràng buộc grapple của Sprint 10 theo yêu cầu: chiêu E lại **đu được mọi hướng**, tầm phóng **co/giãn theo chuột** (clamp [60,480]). Xoá ray-cast (`_find_grapple_target`/`_ray_*`), `_e_aim_valid`, structure registry. **Giữ nguyên** đu-xuống chậm ×1.3, interrupt giữa không trung, và stack damage 125/150/200/250%. |
| 12 | E rework lần 2: **giữ thu phóng tầm bằng chuột** NHƯNG chỉ bay được khi **hướng nhắm** trúng công trình/titan (ray-cast `_aim_hits_target`, range vẫn theo chuột — không snap mục tiêu). Mũi tên **nhạt khi chưa hợp lệ / đậm khi bay được**. Khôi phục structure registry + đăng ký tháp ở `main.py`. Fix **tầm đánh thường**: thêm `BASIC_ATTACK_MIN_LATERAL_PX=55` để địch đứng sát/lệch trục/sát mặt vẫn trúng (địch sau lưng vẫn miss). |
| 13 | Fix bug validity E false-positive: bản Sprint 12 dùng `c<=0 → return 0` (origin nằm trong padded circle/rect) khiến khi đứng SÁT titan/tháp thì **mọi hướng** đều valid → bay lung tung. Đổi `_ray_circle_t` sang kiểm **GÓC** (lệch tâm ≤ góc-mục-tiêu + slack, cap 40°) và `_ray_rect_t` yêu cầu entry phía trước. Giờ phải chĩa đúng vào mục tiêu mới bay. |
| 14 | Đổi validity sang **ĐIỂM ĐÁP**: chỉ bay khi đầu mũi tên (con trỏ chuột = origin+dir*range) NẰM TRÊN công trình/titan (`_aim_endpoint_on_target`, sai số `E_TARGET_PAD_PX=24`). Bỏ ray-cast (`_ray_circle_t`/`_ray_rect_t`, hằng số góc) vì còn false-positive khi mục tiêu **tình cờ nằm dọc đường ngắm** nhưng con trỏ ở chỗ trống. "Bay tới đúng chỗ con trỏ". |
| 15 | Redirect giữa lúc bay bằng **1 phím**: đang `flying` bấm E → `redirect_flight()` đổi hướng ngay sang mục tiêu con trỏ chỉ vào (KHÔNG cần dừng để ngắm), phóng cú bay mới từ vị trí hiện tại, tốn 1 charge; con trỏ ở chỗ trống thì bỏ qua. Tách `_launch_flight()` dùng chung với `confirm_swing()`; thay cho `interrupt_flight_to_aim` (dừng-rồi-ngắm). |
| 16 | **Preview khi bay** để chuyển đổi đa dạng mục tiêu: lúc `flying` vẫn hiện overlay ngắm bám chuột (`update_flight_aim` mỗi frame + `draw` overlay cho cả trạng thái flying), HUD báo `CAN FLY`/`aim a target`. Nhờ đó bấm E nhảy qua lại nhiều titan/công trình ngay giữa lúc bay. Tách `_compute_aim()` dùng chung. |
| 17 | Tăng `E_BASE_CHARGES` 3→6 (giữ bonus: `E_MAX_CHARGES` 8→11 để headroom bonus vẫn +5). **Map lớn hơn** `2880×1800` với 8 tháp + 8 titan rải khắp, và **camera đi theo nhân vật** active (`_compute_camera` clamp biên, vẽ qua `world_surf` rồi blit viewport; chuột đổi sang world cho aim/spawn). Tests headless không đổi (75 pass). |
| 18 | **Hệ thống Lính** (`soldier.py`/`squad.py`/`projectile.py`): 3 loại Archer/Lancer/Warrior (assets strip), deploy cụm 10 con hình tròn từ **thành** (`BASE_RECT`). RMB chọn titan + nút HUD chọn loại → lính xuất phát, tìm titan gần nhất, đánh liên tục. Titan **đánh trả** + Warrior **taunt** kéo aggro (`stubs.py`). 15 test mới → tổng **90 pass**. Sau đó cải tiến: cụm spawn theo **filled hex cluster** thay vì 1 vòng tròn (spacing ~50px, không đè texture), và **regroup** về formation khi hết titan (`_regroup` + `Squad.regroup_center()` cached centroid → 18 test soldier, tổng **93 pass**). |
| 19 | **Tháp phòng thủ** (`tower.py` / `tower_menu.py`): `Tower(Entity)` đặt 2 chiếc cạnh THÀNH (vị trí cố định trên world), giữ **garrison cố định 8 cụm** chia theo W/L/A. LMB tháp mở **menu** chỉnh garrison + thứ tự loại của 3 lượt. Khi có titan trong `AGGRO_RADIUS=600px` → tháp **tự xuất 1 cụm 10 lính / lượt** theo `WAVE_COOLDOWN=3s`, tối đa **3 lượt / sự kiện**, sau đó nghỉ `EVENT_COOLDOWN=8s`. Bỏ qua slot rỗng; kết thúc sự kiện sớm nếu hết garrison hoặc titan rời tầm. Tháp cũng register làm grapple anchor (chiêu E neo được). HUD báo trạng thái tháp. 17 test mới → tổng **110 pass**. |
| 20 | **Patrol-zone / Retreat / Heal / Wipe-redeploy**: lính bị **buộc** vào tháp đã spawn — `Soldier._home_pos` + `_home_radius` (mặc định 600px). `_acquire_nearest_titan` lọc bỏ titan ngoài vùng → lính KHÔNG truy kích titan ngoài tầm tháp; titan bị dẫn dụ ra ngoài cũng bị drop. Hết titan trong vùng → `_retreat_and_heal` đi về `home + slot_offset`, đến nơi thì idle và **hồi `HEAL_RATE=10% max HP/s`** (full HP sau ~10s; dùng `_heal_acc` để cộng dồn fractional). Tháp track `_active_squad`; nếu cụm bị wipe sạch mà titan còn trong aggro và còn waves → **xả lượt kế NGAY** (set `_wave_timer=0`, vẫn tính vào cap 3 lượt). **Bỏ hẳn** BASE_RECT + 3 nút HUD deploy + RMB-select-titan trong `main.py` — lính giờ chỉ ra từ tháp. 11 test mới (+7 soldier, +4 tower) → tổng **121 pass**. |
| 21 | **Vanish-into-tower** ("đi vào thành"): bỏ cơ chế hồi-máu-tại-chỗ ở Sprint 20. Khi lính rút về tới home slot (`_home_pos + _slot_offset`, sai số `HOME_VANISH_DIST_PX=6px`) thì **set `is_alive=False`** → main loop cull pass tự gỡ khỏi WorldQuery. Đọc trực quan như lính bước vào tháp rồi biến mất. Đổi tên `_retreat_and_heal` → `_retreat_into_home`; xoá `HEAL_RATE`/`HOME_HEAL_DIST_PX`/`_heal_acc`. Thay 4 test "heal" cũ bằng 4 test "vanish/walk-toward-home/no-vanish-while-walking" → vẫn **121 pass**. |

---

## 14. Chạy game

```bash
cd d:/python/it002/project5/commander_prototype
python main.py
```

---

## 15. Việc còn lại (backlog)

- [ ] Mikasa skills riêng (counter-attack, ODM blade)
- [ ] Armin skills riêng (thunder spear, strategic boost)
- [ ] Tướng 3 (Levi) + Tướng 5 (Hange)
- [ ] Warrior pack: thêm Run, Hurt, Death animations cho Armin
- [ ] Terrain collision (hiện chỉ visual)
- [ ] Sound effects
- [ ] HUD damage numbers floating
- [ ] Tích hợp vào game chính (`Titan-s_Last_Bastion/`)
- [x] Hệ thống Lính Archer/Lancer/Warrior + thành + deploy + titan đánh trả (Sprint 18)
- [ ] Lính: pathfinding tránh vật cản, formation khi di chuyển, giới hạn/tài nguyên số cụm
- [ ] Công trình "thành" thật (HP, có thể bị titan phá) thay cho `BASE_RECT` tượng trưng
