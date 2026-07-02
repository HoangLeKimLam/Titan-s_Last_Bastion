"""
save_manager.py — Lưu và tải trạng thái game giữa các phiên (persistent state).

Những gì được lưu:
    - Tài nguyên (ResourceState)
    - Level hiện tại (ScreenManager.current_level)
    - Chỉ số tướng (_cmdr_saved_stats)
    - HP từng đoạn tường (all_sections)
    - HP + level công trình (buildings)
    - HP + level tháp tường (wall_towers) — lưu vào file;
      KHÔNG khôi phục tháp khi load (tháp được đặt động, cần build lại thủ công)

File save: save.json ở thư mục gốc project.
"""
import json, os

SAVE_PATH = 'save.json'

_RES_FIELDS = [
    'wood', 'stone', 'gas', 'food', 'ore', 'serum',
    'fire_ore', 'ice_ore', 'electric_ore', 'water_ore', 'wind_ore', 'acid_ore',
    'anti_armor_ore', 'titan_pheromone',
    'tower_weapon', 'basic_projectlie', 'ice_projectlie', 'electric_projectlie',
    'water_projectlie',
    'trap', 'thorn_trap', 'explode_trap', 'bait_trap', 'poison_trap', 'smoke_trap',
    'soldier_weapon', 'sword', 'spear', 'arrow', 'poison_arrow', 'heavy_arrow',
]


def save_exists() -> bool:
    return os.path.exists(SAVE_PATH)


def save_game(res, all_sections, buildings, wall_towers, cmdr_saved_stats, current_level):
    """Ghi trạng thái hiện tại ra save.json."""
    data = {
        'current_level': int(current_level),
        'resources': {k: int(getattr(res, k, 0)) for k in _RES_FIELDS},
        'commander_stats': dict(cmdr_saved_stats),
        'wall_sections': [
            {
                'x': int(s.x), 'y': int(s.y),
                'hp': int(getattr(s, '_hp', 0)),
                'max_hp': int(getattr(s, '_max_hp', 1000)),
                'alive': bool(getattr(s, 'is_alive', True)),
            }
            for s in all_sections
        ],
        'buildings': [
            {
                'x': int(b.x), 'y': int(b.y),
                'type': b.__class__.__name__,
                'hp': int(getattr(b, '_hp', 0)),
                'level': int(getattr(b, '_level', 1)),
                'alive': bool(getattr(b, 'is_alive', True)),
            }
            for b in buildings
        ],
    }
    with open(SAVE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_game():
    """Đọc save.json. Trả về dict hoặc None nếu không tồn tại / lỗi đọc."""
    if not os.path.exists(SAVE_PATH):
        return None
    try:
        with open(SAVE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def apply_save(data, res, all_sections, buildings, wall_towers, cmdr_saved_stats, sm):
    """
    Áp dụng dữ liệu từ save.json lên các object đã khởi tạo của game.

    Gọi MỘT LẦN, ngay sau khi game init xong và trước khi vào while True.
    Các object (res, all_sections, buildings) phải đã được tạo đầy đủ.
    """
    # ── Tài nguyên ────────────────────────────────────────────────────────────
    for k, v in data.get('resources', {}).items():
        if hasattr(res, k):
            setattr(res, k, int(v))

    # ── Level hiện tại ────────────────────────────────────────────────────────
    sm.current_level = int(data.get('current_level', 1))

    # ── Chỉ số tướng ─────────────────────────────────────────────────────────
    cmdr_saved_stats.clear()
    cmdr_saved_stats.update(data.get('commander_stats', {}))

    # ── HP tường — khớp theo vị trí pixel (x, y) ─────────────────────────────
    ws_map = {(int(s.x), int(s.y)): s for s in all_sections}
    for entry in data.get('wall_sections', []):
        s = ws_map.get((entry['x'], entry['y']))
        if s is None:
            continue
        s._hp = int(entry.get('hp', getattr(s, '_hp', 0)))
        s._max_hp = int(entry.get('max_hp', getattr(s, '_max_hp', 1000)))
        alive = bool(entry.get('alive', True)) and s._hp > 0
        s.is_alive = alive

    # ── HP + level công trình — khớp theo vị trí ─────────────────────────────
    b_map = {(int(b.x), int(b.y)): b for b in buildings}
    for entry in data.get('buildings', []):
        b = b_map.get((entry['x'], entry['y']))
        if b is None:
            continue
        b._hp = int(entry.get('hp', getattr(b, '_hp', 0)))
        if hasattr(b, '_level'):
            b._level = int(entry.get('level', 1))
        b.is_alive = bool(entry.get('alive', True)) and b._hp > 0
