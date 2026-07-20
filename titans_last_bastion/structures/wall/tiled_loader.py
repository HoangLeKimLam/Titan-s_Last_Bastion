# -*- coding: utf-8 -*-
"""Đọc `mapdata/walls.tmx` (Tiled) và trả về `(maria_pos, rose_pos, sina_pos)`
— CÙNG FORMAT với `build_ring()` (list các tuple `(x, y, section_type)`), để
`WallSystem` dùng làm nguồn tường thay cho `build_ring()` mà không cần đổi
gì ở `Wall`/`WallSection`.

1 FILE DUY NHẤT, 1 LƯỚI DUY NHẤT (37×27px — bằng 1/2 lưới gốc của wall_Y,
chọn vì đây là kích thước mịn nhất mà cả wall_h/wall_Y/corners đều snap vào
KHÔNG mất mảnh nào, đã verify bằng script) cho cả 3 layer `wall_h`/`wall_Y`/
`corners` — không còn cần quy đổi toạ độ giữa nhiều file như thiết kế cũ.

Vì `WallSystem` cần 3 list riêng theo tên vòng (`Wall.name` dùng cho
`get_wall('maria')`), loader PHÂN LẠI mỗi mảnh tường vào vòng có biên
(MARIA_BOX/ROSE_BOX/SINA_BOX, tính ra pixel) gần nhất — 3 vòng cách nhau
hàng chục tile nên việc phân này không có vùng mập mờ.
"""
import os
import xml.etree.ElementTree as ET

_MAPDATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'mapdata')


def _read_origin(root) -> tuple:
    origin_x = origin_y = None
    for prop in root.find('properties').findall('property'):
        if prop.get('name') == 'origin_x':
            origin_x = float(prop.get('value'))
        elif prop.get('name') == 'origin_y':
            origin_y = float(prop.get('value'))
    return origin_x, origin_y


def _read_gid_tile_info(root) -> dict:
    """Trả về `{gid: (section_type, image_height)}` đọc từ MỌI tileset trong
    file — cần `image_height` để bù lệch neo (xem `_TOP_LEFT_Y_CORRECTION`)."""
    info = {}
    for ts in root.findall('tileset'):
        firstgid = int(ts.get('firstgid'))
        for tile in ts.findall('tile'):
            props = tile.find('properties')
            if props is None:
                continue
            stype = None
            for p in props.findall('property'):
                if p.get('name') == 'section_type':
                    stype = p.get('value')
            image = tile.find('image')
            img_h = float(image.get('height')) if image is not None else None
            if stype is not None:
                info[firstgid + int(tile.get('id'))] = (stype, img_h)
    return info


def _load_layer_by_gid(root, layer_name: str) -> list:
    """Đọc 1 Tile Layer — loại (`section_type`) của MỖI Ô được tra theo
    CHÍNH GID của ô đó (tileset nào định nghĩa gid này), KHÔNG dựa vào tên
    layer chứa nó. Nhờ vậy, nếu ai đó lỡ đặt nhầm tile corner vào layer
    `wall_h` (hoặc ngược lại) trong Tiled, game vẫn nhận đúng loại thật của
    tile đó — không cần layer phải "sạch" đúng loại mới load được.

    QUAN TRỌNG — neo Tiled: Tiled luôn neo tile theo GÓC DƯỚI-TRÁI của ô lưới
    (xem TMX Map Format doc: "Larger tiles will extend at the top and right
    (anchored to the bottom left)"), KHÔNG PHẢI trên-trái. Trục X không đổi
    (mép trái luôn khớp dù neo trên hay dưới), nhưng trục Y phải cộng thêm
    `(step_y - image_height)` để ra đúng góc TRÊN-TRÁI thật — thứ mà
    `WallSection`/`build_ring()` dùng làm `(x, y)` khi vẽ.
    """
    origin_x, origin_y = _read_origin(root)
    step_x = float(root.get('tilewidth'))
    step_y = float(root.get('tileheight'))
    gid_info = _read_gid_tile_info(root)

    layer = next((lyr for lyr in root.findall('layer') if lyr.get('name') == layer_name), None)
    if layer is None:
        return []
    cols = int(layer.get('width'))
    csv_text = layer.find('data').text
    gids = [int(v) for v in csv_text.replace('\n', '').split(',') if v.strip() != '']

    out = []
    for idx, gid in enumerate(gids):
        if gid == 0:
            continue
        info = gid_info.get(gid)
        if info is None:
            # gid không khớp tileset nào hiện có (VD lỡ tay làm lệch firstgid
            # trong Tiled) -> bỏ qua đúng 1 ô lỗi, không crash cả game.
            print(f'[tiled_loader] CANH BAO: gid={gid} khong khop tileset nao '
                  f'(layer "{layer_name}") - da bo qua 1 o.')
            continue
        stype, img_h = info
        y_correction = step_y - (img_h if img_h is not None else step_y)
        col, row = idx % cols, idx // cols
        out.append((origin_x + col * step_x,
                     origin_y + row * step_y + y_correction,
                     stype))
    return out


def _rect_from_box(box: tuple, tile: int) -> tuple:
    left_t, top_t, right_t, bot_t = box
    return (left_t * tile, top_t * tile, right_t * tile, bot_t * tile)


def _dist_to_rect_boundary(x: float, y: float, rect: tuple) -> float:
    l, t, r, b = rect

    def seg_dist(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        u = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        return ((px - (x1 + u * dx)) ** 2 + (py - (y1 + u * dy)) ** 2) ** 0.5

    edges = [(l, t, r, t), (l, b, r, b), (l, t, l, b), (r, t, r, b)]
    return min(seg_dist(x, y, *e) for e in edges)


def load_walls_from_tiled(maria_box: tuple, rose_box: tuple, sina_box: tuple,
                           tile: int) -> tuple:
    """Trả về `(maria_pos, rose_pos, sina_pos)` đọc từ `mapdata/walls.tmx`.

    Ném `FileNotFoundError` nếu file .tmx chưa tồn tại — gọi nơi có fallback
    về `build_ring()` để không crash khi chưa tạo map bằng Tiled.
    """
    path = os.path.join(_MAPDATA_DIR, 'walls.tmx')
    root = ET.parse(path).getroot()

    all_pos = []
    for layer_name in ('wall_h', 'wall_Y', 'corners'):
        all_pos.extend(_load_layer_by_gid(root, layer_name))

    rects = {
        'maria': _rect_from_box(maria_box, tile),
        'rose': _rect_from_box(rose_box, tile),
        'sina': _rect_from_box(sina_box, tile),
    }
    buckets = {'maria': [], 'rose': [], 'sina': []}
    for (x, y, stype) in all_pos:
        best_name = min(rects, key=lambda name: _dist_to_rect_boundary(x, y, rects[name]))
        buckets[best_name].append((x, y, stype))

    return buckets['maria'], buckets['rose'], buckets['sina']
