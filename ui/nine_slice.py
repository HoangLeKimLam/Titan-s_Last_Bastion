"""
nine_slice.py — Bộ vẽ panel/nút 9-slice dùng chung cho ui/*.py (THÊM MỚI, chỉ đồ họa).

4 style, mỗi style 1 sheet + 1 bộ rect cắt riêng (đo bằng quét alpha, xem memory
`ui-interface-asset-inventory`):
    'blue'   — BigBlueButton_Pressed.png — nút mang nghĩa TÍCH CỰC (proceed/confirm).
    'red'    — BigRedButton_Pressed.png  — nút mang nghĩa TIÊU CỰC (cancel/exit/end).
    'paper'  — RegularPaper.png          — nền panel giấy da cho màn thông báo/lựa chọn.
    'banner' — Banner.png                — biểu ngữ tiêu đề nhô đè mép trên panel giấy.

draw_nine_slice()/draw_button() vẽ panel giãn 9 mảnh (tự thu nhỏ góc nếu rect
nhỏ hơn khung gốc — tránh 2 góc đè nhau). draw_banner_title() vẽ banner tiêu đề
đè lên mép trên của 1 panel (kiểu bảng tên RPG cổ điển).

Hàm KHÔNG đụng logic game — chỉ pygame thuần, giống các file ui/ khác.
"""
import os
import pygame

_HERE   = os.path.dirname(os.path.abspath(__file__))
_UI_DIR = os.path.join(os.path.dirname(_HERE), 'testv2', 'assets', 'UI_interface')

_SHEETS = {
    'blue':   os.path.join(_UI_DIR, 'BigBlueButton_Pressed.png'),
    'red':    os.path.join(_UI_DIR, 'BigRedButton_Pressed.png'),
    'paper':  os.path.join(_UI_DIR, 'RegularPaper.png'),
    'banner': os.path.join(_UI_DIR, 'Banner.png'),
}

# Rect đã đo (quét alpha) trên sheet gốc — mỗi style 1 bộ vì kích thước khác nhau.
_CELLS = {
    'blue': {
        'tl': (14, 28, 50, 36),  'tm': (128, 28, 64, 36),  'tr': (256, 28, 50, 36),
        'ml': (14, 128, 50, 64), 'mm': (128, 128, 64, 64), 'mr': (256, 128, 50, 64),
        'bl': (14, 256, 50, 49), 'bm': (128, 256, 64, 49), 'br': (256, 256, 50, 49),
    },
    'red': {
        'tl': (14, 28, 50, 36),  'tm': (128, 28, 64, 36),  'tr': (256, 28, 50, 36),
        'ml': (14, 128, 50, 64), 'mm': (128, 128, 64, 64), 'mr': (256, 128, 50, 64),
        'bl': (14, 256, 50, 49), 'bm': (128, 256, 64, 49), 'br': (256, 256, 50, 49),
    },
    'paper': {
        'tl': (12, 20, 52, 44),  'tm': (128, 20, 64, 44),  'tr': (256, 20, 52, 44),
        'ml': (12, 128, 52, 64), 'mm': (128, 128, 64, 64), 'mr': (256, 128, 52, 64),
        'bl': (12, 256, 52, 45), 'bm': (128, 256, 64, 45), 'br': (256, 256, 52, 45),
    },
    'banner': {
        'tl': (28, 60, 100, 68),   'tm': (192, 60, 64, 68),   'tr': (320, 60, 84, 68),
        'ml': (28, 192, 100, 64), 'mm': (192, 192, 64, 64), 'mr': (320, 192, 84, 64),
        'bl': (28, 320, 100, 111), 'bm': (192, 320, 64, 111), 'br': (320, 320, 84, 111),
    },
}

_cache: dict = {}   # style -> {piece_name: Surface}, nạp 1 lần / style


def _pieces(style: str) -> dict:
    """Cắt 9 mảnh panel (4 góc + 4 cạnh + tâm, key tra `_CELLS[style]`) từ
    sprite sheet của `style`, cache theo style (cắt 1 lần/style). Dùng bởi
    `draw_nine_slice()` để ghép panel co giãn khớp mọi kích thước rect."""
    if style not in _cache:
        sheet = pygame.image.load(_SHEETS[style]).convert_alpha()
        _cache[style] = {name: sheet.subsurface(pygame.Rect(*r)).copy()
                         for name, r in _CELLS[style].items()}
    return _cache[style]


def draw_nine_slice(screen, rect: pygame.Rect, style: str = 'blue') -> None:
    """Vẽ panel 9-slice khớp đúng `rect` (góc giữ tỉ lệ, cạnh/tâm giãn).

    Nếu rect nhỏ hơn tổng kích thước 4 góc gốc, tự thu nhỏ đều cả 4 góc theo
    cùng 1 tỉ lệ (giữ đối xứng) để 2 góc không đè lên nhau.
    """
    p = _pieces(style)
    tl, tm, tr = p['tl'], p['tm'], p['tr']
    ml, mm, mr = p['ml'], p['mm'], p['mr']
    bl, bm, br = p['bl'], p['bm'], p['br']

    cw_l0, ch_t0 = tl.get_size()
    cw_r0, _     = tr.get_size()
    _, ch_b0     = bl.get_size()

    scale = min(1.0,
               rect.width  / max(1, cw_l0 + cw_r0),
               rect.height / max(1, ch_t0 + ch_b0))
    cw_l = max(1, round(cw_l0 * scale)); cw_r = max(1, round(cw_r0 * scale))
    ch_t = max(1, round(ch_t0 * scale)); ch_b = max(1, round(ch_b0 * scale))

    if scale < 0.999:
        tl = pygame.transform.smoothscale(tl, (cw_l, ch_t))
        tr = pygame.transform.smoothscale(tr, (cw_r, ch_t))
        bl = pygame.transform.smoothscale(bl, (cw_l, ch_b))
        br = pygame.transform.smoothscale(br, (cw_r, ch_b))

    mid_w = max(1, rect.width  - cw_l - cw_r)
    mid_h = max(1, rect.height - ch_t - ch_b)
    x, y = rect.x, rect.y

    screen.blit(tl, (x, y))
    screen.blit(tr, (x + rect.width - cw_r, y))
    screen.blit(bl, (x, y + rect.height - ch_b))
    screen.blit(br, (x + rect.width - cw_r, y + rect.height - ch_b))
    screen.blit(pygame.transform.scale(tm, (mid_w, ch_t)), (x + cw_l, y))
    screen.blit(pygame.transform.scale(bm, (mid_w, ch_b)),
               (x + cw_l, y + rect.height - ch_b))
    screen.blit(pygame.transform.scale(ml, (cw_l, mid_h)), (x, y + ch_t))
    screen.blit(pygame.transform.scale(mr, (cw_r, mid_h)),
               (x + rect.width - cw_r, y + ch_t))
    screen.blit(pygame.transform.scale(mm, (mid_w, mid_h)), (x + cw_l, y + ch_t))


def draw_button(screen, rect: pygame.Rect, label: str, style: str = 'blue',
                font: pygame.font.Font = None, hover: bool = False,
                text_color=(250, 248, 240)) -> None:
    """Vẽ nút 9-slice + chữ căn giữa (có bóng đổ nhẹ cho dễ đọc).

    style : 'blue' (tích cực: proceed/confirm/next) | 'red' (tiêu cực: cancel/exit/end).
    hover : True → phủ lớp sáng mờ + chữ trắng sáng hơn (phản hồi hover).
    """
    draw_nine_slice(screen, rect, style)
    if hover:
        _hl = pygame.Surface(rect.size, pygame.SRCALPHA)
        _hl.fill((255, 255, 255, 35))
        screen.blit(_hl, rect.topleft)
    if font is None:
        font = pygame.font.SysFont('consolas', 20, bold=True)
    col = (255, 255, 255) if hover else text_color
    shadow = font.render(label, True, (20, 14, 10))
    screen.blit(shadow, shadow.get_rect(center=(rect.centerx + 2, rect.centery + 2)))
    lbl = font.render(label, True, col)
    screen.blit(lbl, lbl.get_rect(center=rect.center))


def draw_banner_title(screen, panel_rect: pygame.Rect, title: str, font,
                      text_color=(80, 60, 30), width_ratio: float = 0.62,
                      height: int = 70) -> pygame.Rect:
    """Vẽ banner tiêu đề (Banner.png) đè lên mép trên của `panel_rect`.

    Kiểu "bảng tên" RPG cổ điển: banner rộng = tỉ lệ `width_ratio` so với
    panel (tối thiểu đủ ôm chữ + đệm), tâm ngang trùng panel, tâm dọc đặt
    NGAY MÉP TRÊN panel (nửa banner nhô ra ngoài, nửa đè vào trong panel).

    Trả về Rect của banner (để caller đặt tiếp nội dung bên dưới nó).
    """
    lbl = font.render(title, True, text_color)
    bw = max(int(panel_rect.width * width_ratio), lbl.get_width() + 100)
    bw = min(bw, panel_rect.width + 80)
    brect = pygame.Rect(0, 0, bw, height)
    brect.centerx = panel_rect.centerx
    brect.centery = panel_rect.top

    draw_nine_slice(screen, brect, style='banner')
    shadow = font.render(title, True, (255, 250, 235))
    screen.blit(shadow, shadow.get_rect(center=(brect.centerx, brect.centery + 2)))
    dark = font.render(title, True, (30, 20, 10))
    screen.blit(dark, dark.get_rect(center=(brect.centerx - 1, brect.centery - 1)))
    screen.blit(lbl, lbl.get_rect(center=brect.center))
    return brect


# ── Ruy băng tiêu đề (BigRibbons.png) — 3-slice NGANG, 5 màu ──────────────────
_RIBBON_SHEET  = os.path.join(_UI_DIR, 'BigRibbons.png')
_RIBBON_ROW_Y  = {'teal': 20, 'red': 148, 'gold': 276, 'purple': 404, 'slate': 532}
_RIBBON_CELL_X = {'l': (30, 98), 'm': (192, 64), 'r': (320, 97)}   # (x, w)
_RIBBON_CELL_H = 103

_ribbon_cache: dict = {}   # color -> {'l'/'m'/'r': Surface}, nạp 1 lần / màu


def _ribbon_pieces(color: str) -> dict:
    """Cắt 3 mảnh ruy băng ('l'/'m'/'r') từ hàng `color` của `BigRibbons.png`
    (xem `_RIBBON_ROW_Y`/`_RIBBON_CELL_X`), cache theo màu. Dùng bởi
    `draw_ribbon_title()` để ghép ruy băng tiêu đề dài tuỳ chỉnh."""
    if color not in _ribbon_cache:
        sheet = pygame.image.load(_RIBBON_SHEET).convert_alpha()
        y = _RIBBON_ROW_Y[color]
        _ribbon_cache[color] = {
            name: sheet.subsurface(pygame.Rect(x, y, w, _RIBBON_CELL_H)).copy()
            for name, (x, w) in _RIBBON_CELL_X.items()
        }
    return _ribbon_cache[color]


def draw_ribbon_title(screen, panel_rect: pygame.Rect, title: str, font,
                      color: str = 'teal', text_color=(255, 255, 255),
                      width_ratio: float = 0.62, height: int = 62) -> pygame.Rect:
    """Vẽ ruy băng tiêu đề (BigRibbons.png) đè lên mép trên của `panel_rect`.

    color : 'teal' | 'red' | 'gold' | 'purple' | 'slate' — 5 màu có sẵn trên sheet.
    Ruy băng chỉ giãn NGANG (3-slice: trái đuôi cờ | giữa giãn | phải đuôi cờ),
    cao cố định theo `height` (giữ tỉ lệ đuôi cờ, không méo).

    Trả về Rect của ruy băng (để caller đặt tiếp nội dung bên dưới nó).
    """
    p = _ribbon_pieces(color)
    l0, m0, r0 = p['l'], p['m'], p['r']
    scale = height / l0.get_height()
    lw, rw = max(1, round(l0.get_width() * scale)), max(1, round(r0.get_width() * scale))

    lbl = font.render(title, True, text_color)
    bw = max(int(panel_rect.width * width_ratio), lbl.get_width() + lw + rw + 20)
    bw = min(bw, panel_rect.width + 80)

    brect = pygame.Rect(0, 0, bw, height)
    brect.centerx = panel_rect.centerx
    brect.centery = panel_rect.top

    l = pygame.transform.smoothscale(l0, (lw, height))
    r = pygame.transform.smoothscale(r0, (rw, height))
    mid_w = max(1, bw - lw - rw)
    m = pygame.transform.scale(m0, (mid_w, height))

    screen.blit(l, (brect.x, brect.y))
    screen.blit(m, (brect.x + lw, brect.y))
    screen.blit(r, (brect.x + bw - rw, brect.y))

    shadow = font.render(title, True, (15, 15, 15))
    screen.blit(shadow, shadow.get_rect(center=(brect.centerx + 2, brect.centery + 2)))
    screen.blit(lbl, lbl.get_rect(center=brect.center))
    return brect


def draw_left_edge_strip(screen, rect: pygame.Rect, style: str = 'banner') -> None:
    """Vẽ dải nền DỌC dùng CỘT TRÁI (tl/ml/bl) của 1 style làm 3-slice đứng
    (mảnh trên cố định, giữa giãn, mảnh dưới cố định) — dùng làm nền sidebar
    icon dọc cạnh phải màn hình (mượn nghệ thuật góc trái Banner.png, vốn có
    chi tiết dây/nếp gấp, đẹp làm dải viền dọc độc lập).

    Tự thu nhỏ 2 đầu nếu `rect` thấp hơn tổng chiều cao gốc (giống draw_nine_slice).
    """
    p = _pieces(style)
    tl0, ml0, bl0 = p['tl'], p['ml'], p['bl']
    w0 = tl0.get_width()

    scale_w = rect.width / max(1, w0)
    cap_t0, cap_b0 = tl0.get_height(), bl0.get_height()
    scale_h = min(1.0, rect.height / max(1, (cap_t0 + cap_b0) * scale_w))
    scale = scale_w * scale_h

    cap_t = max(1, round(cap_t0 * scale))
    cap_b = max(1, round(cap_b0 * scale))
    mid_h = max(1, rect.height - cap_t - cap_b)

    tl = pygame.transform.smoothscale(tl0, (rect.width, cap_t))
    bl = pygame.transform.smoothscale(bl0, (rect.width, cap_b))
    ml = pygame.transform.scale(ml0, (rect.width, mid_h))

    screen.blit(tl, (rect.x, rect.y))
    screen.blit(ml, (rect.x, rect.y + cap_t))
    screen.blit(bl, (rect.x, rect.y + cap_t + mid_h))
