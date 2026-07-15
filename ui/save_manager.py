"""
save_manager.py — Lưu và tải trạng thái game giữa các phiên (persistent state).

Những gì được lưu:
    - Tài nguyên (ResourceState) — DÙNG CHUNG danh sách field với ResourceBundle
      (lấy TỰ ĐỘNG qua `dataclasses.fields()`, KHÔNG hardcode list riêng — nếu
      ResourceBundle thêm/bớt field, save_manager.py tự đồng bộ theo).
    - Level hiện tại (ScreenManager.current_level).
    - Chỉ số tướng (_cmdr_saved_stats).
    - HP từng đoạn tường (all_sections).
    - HP + level công trình (buildings) — CẢ building xây thêm lúc chơi
      (không chỉ 11 building khởi tạo); building không khớp vị trí sẽ được
      TẠO MỚI khi load (xem game.py `_restore_extra_buildings`). Level được
      khôi phục bằng cách GỌI LẠI `_apply_level_bonus()` (nếu building có),
      không chỉ gán số `_level` — vì PRODUCTION_RATE là chỉ số TÍCH LŨY qua
      từng lần nâng cấp, gán thẳng `_level` không tự động cập nhật nó.
    - Tháp xây thêm trên tường (wall_towers): vị trí đoạn tường gắn, loại
      tháp, garrison, wave_order, HP/level (xem game.py `_restore_towers` —
      hidden_ids/blocked_ids dùng id() bộ nhớ nên KHÔNG serialize được,
      phải tính lại đúng công thức gốc lúc load).
    - Trại lính đang chờ (TrainingCamp._idle — lính train xong, chưa điều đi).
    - HP tướng thành (HQ).
    - **Bundle vũ khí — lưu TRỰC TIẾP bằng chính `ResourceBundle.to_dict()`/
      `from_dict()`** (không suy ra qua side-effect tái tạo building/tower):
      `weapon_stock` = ResourceManager.stock (tổng khả dụng), `weapon_used` =
      Forge._weapon_used (đã tiêu thụ). Vì đều là `ResourceBundle` thật nên
      tự động bao phủ MỌI field hiện có, không cần liệt kê tay.

File save: save.json (đang chơi, Continue luôn đọc file này) và
save_default.json (bản mẫu "game mới tinh", KHÔNG bao giờ bị ghi đè bởi tiến
trình chơi — chỉ tự sinh lại mỗi lần main() khởi tạo state mặc định). CẢ HAI
file luôn ghi qua CÙNG 1 hàm `save_game()` nên LUÔN cùng schema/field, không
bao giờ lệch nhau. New Game = copy save_default.json đè lên save.json, rồi
chạy CHUNG 1 đường load y hệt Continue.
"""
import json, os
from dataclasses import fields as _dc_fields

from core.game_state import ResourceBundle, MATERIAL_FIELDS

SAVE_PATH = 'save.json'
DEFAULT_SAVE_PATH = 'save_default.json'


def _bundle_field_names() -> list:
    """Tên TẤT CẢ field của ResourceBundle — lấy động, KHÔNG hardcode list
    riêng, để luôn đồng bộ nếu ResourceBundle đổi field trong tương lai."""
    return [f.name for f in _dc_fields(ResourceBundle)]


def save_exists() -> bool:
    """True nếu `save.json` đã tồn tại — main_menu.py dùng để quyết định
    hiện/ẩn nút "Continue" (chưa có save → chỉ "New Game")."""
    return os.path.exists(SAVE_PATH)


def copy_default_to_active() -> bool:
    """New Game: copy save_default.json đè lên save.json. Trả về True nếu
    thành công (False nếu chưa có save_default.json — chưa xảy ra bao giờ
    trong luồng thật vì game.py luôn ghi default trước khi vào menu)."""
    if not os.path.exists(DEFAULT_SAVE_PATH):
        return False
    try:
        with open(DEFAULT_SAVE_PATH, 'r', encoding='utf-8') as f:
            data = f.read()
        with open(SAVE_PATH, 'w', encoding='utf-8') as f:
            f.write(data)
        return True
    except Exception:
        return False


def save_game(res, all_sections, buildings, wall_towers, cmdr_saved_stats,
             current_level, *, training_idle=None, training_hungry=None,
             training_disarmed=None, hq_hp=None,
             weapon_stock=None, weapon_used=None, traps=None,
             chopped_trees=None, filepath=SAVE_PATH):
    """Ghi trạng thái hiện tại ra `filepath` (mặc định save.json).

    `wall_towers`   : list[(WallSection, Tower, hidden_ids, blocked_ids)] —
                      chỉ lấy (wall_section.x/y, tower) ra để serialize.
    `training_idle` : dict {soldier_type: count} — lính chờ ở TrainingCamp.
    `training_hungry`   : dict {soldier_type: count} — lính thiếu lương thực
                      (TrainingCamp._hungry — hệ thống Giẫm Đạp + Quyết Toán
                      Hậu Trận). Trước đây HOÀN TOÀN không lưu — lính đang
                      "đói" biến mất khỏi mọi bộ đếm sau Continue (không về
                      idle, không còn bị coi là đói — mất dấu hoàn toàn).
    `training_disarmed` : dict {soldier_type: count} — lính thiếu vũ khí
                      (TrainingCamp._disarmed_soldiers). Cùng vấn đề như trên.
    `hq_hp`         : int hoặc None — HP hiện tại của Headquarters.
    `weapon_stock`  : ResourceBundle hoặc None — ResourceManager.get_instance().stock
                      (tổng vũ khí/bẫy KHẢ DỤNG).
    `weapon_used`   : ResourceBundle hoặc None — Forge._weapon_used
                      (tổng vũ khí/bẫy ĐÃ TIÊU THỤ).
    `traps`         : list[Trap] hoặc None — bẫy đã đặt (ThornTrap/SurikenTrap/
                      PoisonTrap/ExplodeTrap/BaitTrap). Không nằm trong
                      `buildings` (đặt riêng qua registry, không qua
                      `buildings.append`) nên truyền tách biệt.
    `chopped_trees` : list[(tx, ty)] hoặc None — toạ độ tile các cây đã bị
                      chặt trong phiên chơi (game.py xoá cây khỏi `OBJECTS`
                      khi người chơi xác nhận chặt).

    LUÔN dùng hàm này cho CẢ save.json lẫn save_default.json (qua tham số
    `filepath`) — đảm bảo 2 file luôn cùng 1 schema, không lệch field.
    """
    data = {
        'current_level': int(current_level),
        'resources': {k: int(getattr(res, k, 0)) for k in _bundle_field_names()},
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
                # Tháp ĐẤT (Tower nằm trong buildings) phải lưu như tháp tường:
                # _damage là NGUỒN SỰ THẬT của cấp orb (level chỉ là chỉ báo dẫn
                # xuất), cùng garrison + wave_order. Building thường (Farm/Forge)
                # → getattr trả default (0/{}/[]) nên vô hại.
                'damage':     int(getattr(b, '_damage', 0)),
                'garrison':   dict(getattr(b, 'garrison', {})),
                'wave_order': list(getattr(b, 'wave_order', [])),
                # 3 item vĩnh viễn áp lên Tower (anti_stun/serum/anti_armor_ore) —
                # chỉ Tower đặt đất mới có 3 thuộc tính này, building thường
                # (Farm/Forge/...) luôn False do getattr fallback.
                'stun_immune':     bool(getattr(b, '_stun_immune', False)),
                'serum_buff':      bool(getattr(b, '_serum_buff', False)),
                'anti_armor_buff': bool(getattr(b, '_anti_armor_buff', False)),
            }
            for b in buildings
        ],
        'towers': [
            {
                'wall_x': int(ws.x), 'wall_y': int(ws.y),
                'type': tw.__class__.__name__,
                'hp': int(getattr(tw, '_hp', 0)),
                'max_hp': int(getattr(tw, '_max_hp', 300)),
                'level': int(getattr(tw, '_level', 1)),
                # Tower lên cấp qua _check_levelup() KHI `_damage` (sát thương
                # tích lũy qua "orb") vượt LV2_DMG_THRESHOLD — `_level` chỉ là
                # CHỈ BÁO dẫn xuất từ `_damage`, không phải nguồn sự thật. Phải
                # lưu THẲNG `_damage` — chỉ lưu `level` thôi thì sát thương
                # thật vẫn mất sau Continue dù badge hiển thị đúng cấp.
                'damage': int(getattr(tw, '_damage', 0)),
                'garrison': dict(getattr(tw, 'garrison', {})),
                'wave_order': list(getattr(tw, 'wave_order', [])),
                'alive': bool(getattr(tw, 'is_alive', True)),
                # 3 item vĩnh viễn áp lên Tower — xem ghi chú ở 'buildings' phía trên.
                'stun_immune':     bool(getattr(tw, '_stun_immune', False)),
                'serum_buff':      bool(getattr(tw, '_serum_buff', False)),
                'anti_armor_buff': bool(getattr(tw, '_anti_armor_buff', False)),
            }
            for (ws, tw, _hidden, _blocked) in wall_towers
        ],
        'traps': [
            {
                'x': int(t.x), 'y': int(t.y),
                'type': t.__class__.__name__,
                'hp': int(getattr(t, '_hp', 0)),
                'max_hp': int(getattr(t, '_max_hp', 1)),
                'horizontal': bool(getattr(t, 'horizontal', True)),
                'alive': bool(getattr(t, 'is_alive', True)),
            }
            for t in (traps or [])
        ],
        'training_idle': dict(training_idle) if training_idle else {},
        'training_hungry': dict(training_hungry) if training_hungry else {},
        'training_disarmed': dict(training_disarmed) if training_disarmed else {},
        'chopped_trees': [[int(tx), int(ty)] for tx, ty in (chopped_trees or [])],
        'hq_hp': int(hq_hp) if hq_hp is not None else None,
        'weapon_stock': weapon_stock.to_dict() if weapon_stock is not None else None,
        'weapon_used': weapon_used.to_dict() if weapon_used is not None else None,
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_game(filepath=SAVE_PATH):
    """Đọc `filepath`. Trả về dict hoặc None nếu không tồn tại / lỗi đọc."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _fast_forward_level(building, target_level: int) -> None:
    """Đưa building từ _level hiện tại (luôn =1 lúc vừa tạo) lên `target_level`
    bằng cách GỌI LẠI `_apply_level_bonus()` liên tiếp — thay vì gán thẳng
    `_level = target_level`.

    Lý do bắt buộc: PRODUCTION_RATE (và các chỉ số tương tự) là thuộc tính
    TÍCH LŨY — mỗi lần `_apply_level_bonus()` chạy thì `self.PRODUCTION_RATE
    += rate_bonus` rồi mới `_level += 1`. Nếu chỉ gán `_level` mà không gọi
    lại hàm này, PRODUCTION_RATE của building mới tạo (restore) vẫn ở mức cơ
    bản (level 1) dù `_level` hiển thị đúng — đúng bug "nâng cấp mất tác dụng
    sau khi Continue". `_apply_level_bonus()` không trừ tài nguyên (khác hẳn
    `upgrade()`) nên gọi lại an toàn, không tốn phí lần 2.
    """
    if not hasattr(building, '_apply_level_bonus'):
        return
    guard = 0
    while building._level < target_level and guard < 50:
        building._apply_level_bonus()
        guard += 1   # chặn vòng lặp vô hạn nếu logic building có lỗi lạ


def apply_save(data, res, all_sections, buildings, wall_towers, cmdr_saved_stats, sm,
               *, training_camps=None, hq=None, resource_manager=None, forge_cls=None):
    """
    Áp dụng dữ liệu save lên các object đã khởi tạo của game (phần CƠ BẢN —
    resources/level/commander/wall-hp/building-hp-level-hiện-có/trại-lính/HQ/
    bundle vũ khí).

    KHÔNG tạo building/tower mới ở đây (cần biết class-registry của game.py)
    — xem `game.py`: `_restore_extra_buildings()` / `_restore_towers()`, gọi
    NGAY TRƯỚC hàm này trong cùng 1 luồng load (building/tower xây thêm phải
    tồn tại TRƯỚC để vòng lặp training_camps ở dưới nhận diện đúng).

    Gọi MỘT LẦN, ngay sau khi game init xong và trước khi vào while True.
    """
    # ── Tài nguyên (generic — mọi field ResourceBundle hiện có) ──────────────
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

    # ── HP + level building ĐÃ CÓ (khớp vị trí) — building thiếu do
    # `_restore_extra_buildings` (game.py) đã tạo mới TRƯỚC bước này ──────────
    b_map = {(int(b.x), int(b.y)): b for b in buildings}
    for entry in data.get('buildings', []):
        b = b_map.get((entry['x'], entry['y']))
        if b is None:
            continue
        b._hp = int(entry.get('hp', getattr(b, '_hp', 0)))
        _fast_forward_level(b, int(entry.get('level', 1)))
        b.is_alive = bool(entry.get('alive', True)) and b._hp > 0
        # Khôi phục 3 item vĩnh viễn (anti_stun/serum/anti_armor_ore) — chỉ
        # có tác dụng nếu `b` thật sự là Tower (hasattr guard, building
        # thường không có 3 thuộc tính này nên bị bỏ qua an toàn).
        for _flag in ('_stun_immune', '_serum_buff', '_anti_armor_buff'):
            if hasattr(b, _flag):
                setattr(b, _flag, bool(entry.get(_flag[1:], False)))
        # Tháp đất khớp vị trí: khôi phục _damage/garrison/wave_order (level qua
        # _fast_forward_level là no-op với Tower). Dùng hasattr thay isinstance để
        # module save khỏi phụ thuộc import Tower.
        if hasattr(b, '_damage') and 'damage' in entry:
            b._damage = int(entry['damage'])
        if hasattr(b, 'garrison') and 'garrison' in entry:
            for _gk, _gv in entry['garrison'].items():
                if _gk in b.garrison:
                    b.garrison[_gk] = int(_gv)
        if hasattr(b, 'wave_order') and entry.get('wave_order'):
            b.wave_order = list(entry['wave_order'])

    # ── Sổ lính (idle / đói / thiếu vũ khí) ───────────────────────────────────
    # Các trại dùng CHUNG một sổ, nên save lưu TỔNG. Khi khôi phục, dồn hết vào
    # trại ĐẦU TIÊN và làm rỗng các trại còn lại.
    # SỬA LỖI: bản cũ gán CÙNG giá trị vào MỌI trại (`for camp in training_camps:
    # camp._idle[k] = v`) → có 2 trại là số lính bị NHÂN ĐÔI sau mỗi lần Continue.
    if training_camps:
        _first = training_camps[0]
        _rest = training_camps[1:]
        for _pool_name, _key in (('_idle', 'training_idle'),
                                 ('_hungry', 'training_hungry'),
                                 ('_disarmed_soldiers', 'training_disarmed')):
            _saved = data.get(_key, {})
            _pool = getattr(_first, _pool_name, None)
            if _pool is None:
                continue
            for k in _pool:
                _pool[k] = int(_saved.get(k, 0))
            for _c in _rest:
                _other = getattr(_c, _pool_name, None)
                if _other is not None:
                    for k in _other:
                        _other[k] = 0

    # ── HP HQ ─────────────────────────────────────────────────────────────────
    hq_hp = data.get('hq_hp')
    if hq_hp is not None and hq is not None:
        hq._hp = max(0, min(int(hq_hp), getattr(hq, '_max_hp', int(hq_hp))))
        hq.is_alive = hq._hp > 0

    # ── Bundle vũ khí — gán THẲNG (không cộng dồn qua side-effect) ───────────
    # LƯU Ý: phần SOLDIER của `weapon_used` (soldier_weapon + sword/arrow/spear)
    # nay được SUY RA từ số lính đang phục vụ, nên game.py gọi
    # `reconcile_soldiers()` ngay sau `apply_save()` để tính lại — giá trị khôi
    # phục ở đây chỉ là điểm khởi đầu và sẽ tự sửa nếu save cũ bị lệch. Phần
    # tháp (`tower_weapon`, `basic_projectlie`...) và bẫy (`trap`...) thì KHÔNG
    # suy ra được (không có "nguồn sự thật" nào để đếm lại) nên bắt buộc phải
    # khôi phục từ save như dưới đây.
    _wstock = data.get('weapon_stock')
    if _wstock is not None and resource_manager is not None:
        # `res` (ResourceState) mirror phần NGUYÊN LIỆU vào `_stock` — đã khôi phục
        # ở bước 'resources' phía trên. weapon_stock chỉ khôi phục phần VŨ KHÍ: copy
        # từng field KHÔNG phải nguyên liệu, GIỮ nguyên nguyên liệu (tránh replace cả
        # `_stock` làm mất nguyên liệu — và an toàn với save CŨ có material=0).
        _wb = ResourceBundle.from_dict(_wstock)
        for _f in _dc_fields(resource_manager._stock):
            if _f.name not in MATERIAL_FIELDS:
                setattr(resource_manager._stock, _f.name, getattr(_wb, _f.name))
    _wused = data.get('weapon_used')
    if _wused is not None and forge_cls is not None:
        forge_cls._weapon_used = ResourceBundle.from_dict(_wused)
