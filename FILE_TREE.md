# FILE_TREE.md — Những file THỰC SỰ cần để chạy game

> Repo có nhiều thư mục backup/test lẫn lộn. File này liệt kê **chỉ** những gì
> game cần khi chạy. Mọi thứ ở mục "KHÔNG CẦN" có thể bỏ qua an toàn.
> Entry point: `python game.py`

---

## 1. CODE — chạy game

```
d:\OOP_project\
├── game.py                     ← ENTRY POINT (chạy file này)
│
├── config/                     ← CẤU HÌNH
│   ├── __init__.py
│   ├── balance.py              ← ★ MỌI CHỈ SỐ CÂN BẰNG (chỉnh sức mạnh Ở ĐÂY)
│   └── levels/
│       ├── level_1.json … level_5.json   ← kịch bản wave từng ải (Vượt Ải)
│
├── ui/                         ← 13 file giao diện (import bởi game.py)
│   ├── main_menu.py            ├── commander_select.py
│   ├── combat_result.py        ├── lobby_overlay.py
│   ├── pause_menu.py           ├── hud_panels.py
│   ├── mode_select.py          ├── icon_sidebar.py
│   ├── resource_map_screen.py  ├── expedition_overlay.py
│   ├── nine_slice.py           ├── save_manager.py
│   └── vuot_ai.py
│
└── titans_last_bastion/        ← LÕI GAME (được thêm vào sys.path)
    ├── core/                   (nền tảng — chỉ import stdlib)
    │   ├── entity.py           ├── interfaces.py
    │   ├── event_bus.py        ├── game_state.py      (ResourceBundle)
    │   └── exceptions.py
    │
    ├── characters/
    │   ├── titans/
    │   │   ├── titan.py         (6 titan thường)
    │   │   ├── boss.py          (Colossal / Beast / Founding)
    │   │   ├── ai.py            (bộ não titan)
    │   │   ├── attackstrategy.py(cách đánh — Strategy)
    │   │   └── priority.py      (chọn mục tiêu)
    │   ├── commanders/
    │   │   ├── commander.py     (base) ├── mikasa.py ├── eren.py
    │   │   └── assets_config.py (layout sprite)
    │   └── soldiers/
    │       ├── soldier.py       (Archer / Lancer / Warrior)
    │       ├── squad.py         ├── projectile.py (mũi tên)
    │       ├── animation.py     └── assets_config.py
    │
    ├── structures/
    │   ├── hq.py                (Headquarters)
    │   ├── towers/
    │   │   ├── tower.py         (Basic / Electric / Water / Ice)
    │   │   ├── projectile.py    (đạn + ElectricField + WaterVortex)
    │   │   ├── attackstrategy.py(cách nhắm mục tiêu)
    │   │   └── visual_effects.py
    │   ├── buildings/
    │   │   ├── building.py      (Farm / Stone / Wood / Forge / TrainingCamp / RepairStation)
    │   │   └── resource_manager.py (kho tài nguyên — Singleton)
    │   ├── wall/
    │   │   ├── wall.py          (WallSection)
    │   │   └── wall_system.py   (3 vòng Maria/Rose/Sina)
    │   └── trap/
    │       └── trap.py          (Thorn / Suriken / Poison / Explode / Bait)
    │
    └── systems/
        ├── world_query.py       (truy vấn không gian — trung tâm)
        ├── wave_manager.py      (sinh titan theo wave — Vượt Ải)
        ├── screen_manager.py    (Menu → Sảnh → Combat)
        ├── dispatch_system.py   (điều quân thám hiểm)
        ├── loot_system.py       (rơi đồ)
        ├── pathfinding.py       ├── pathmove.py
        └── sound_system.py
```

## 2. ĐỒ HOẠ / ÂM THANH / DATA (được code trỏ tới thật)

```
testv2/assets/Texture/          ← tile + struct + castle (TEX_* trong game.py)
    ├── TX Tileset Grass.png · TX Tileset Path.png · TX Tileset Stone Ground.png
    ├── TX Struct.png · Picture1.png (castle)
    └── Extra/  (TX Plant with Shadow.png · TX Props with Shadow.png · Tree4.png)
testv2/assets/UI_interface/     ← con trỏ + panel UI (Cursor_01.png, …)

titans_last_bastion/**/sprites/ ← sprite nhân vật/công trình
    ├── characters/titans/sprites/      (regular, wolf, beast, founding, …)
    ├── characters/commanders/sprites/  (Mikasa/, Eren/)   [Armin/ = thừa, đã gỡ khỏi code]
    ├── characters/soldiers/sprites/    (Archer/, Lancer/, Warrior/)
    ├── structures/towers/effect/       (base/ elec/ water/ ice/)
    ├── structures/buildings/*.png      (Farm.png, Forge_*.png, …)
    ├── structures/wall/*.png           (wall.png, corner_*.png, …)
    └── structures/trap/                (thorn/suriken/poison/explode/bait)

titans_last_bastion/sfx/        ← âm thanh (.wav/.mp3) — SoundManager.init_sounds()

map_layout.json                 ← bố cục map
save.json                       ← save hiện tại (tự sinh)
save_default.json               ← save mặc định (tự ghi lại mỗi lần chạy)
```

## 3. KHÔNG CẦN ĐỂ CHẠY GAME (backup / test / rác)

```
Titan-s_Last_Bastion/       ← bản sao lưu TOÀN BỘ project (cũ)
nhật/                       ← backup của thành viên
long/                       ← backup của thành viên
testv2/map.py               ← demo map cũ (assets bên trong VẪN CẦN, chỉ file .py này là thừa)

test_buildings_visual.py · test_wall_visual.py · test_demo_map.py
_check_sprites.py · _check_props.py · _check_props2.py · tempCodeRunnerFile.py
titans_last_bastion/test_ice.py

.omc/  ·  .vscode/  ·  __pycache__/
```

---

## Ghi chú
- **Chỉnh sức mạnh:** chỉ sửa `config/balance.py`. Không cần đụng file nào khác.
- **Thiết kế wave từng ải:** sửa `config/levels/level_N.json`.
- `core/` là tầng nền: chỉ import stdlib, không phụ thuộc `systems/`, `characters/`, `structures/`.
