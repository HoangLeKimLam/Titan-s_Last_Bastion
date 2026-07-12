"""
mode_select.py — Nút chọn chế độ hình thanh kiếm (Swords.png) + popup kiếm to
giữa màn hình (THÊM MỚI, chỉ đồ họa/UI — thay cho draw_lobby_overlay 2-nút cũ).

Luồng:
    draw_sword_button()      : nút nhỏ góc TRÊN-PHẢI, hình thanh kiếm — KHÔNG
                                khung/nền, chỉ hình kiếm (bấm vào → game.py mở
                                popup).
    draw_sword_mode_picker() : khi popup mở — kiếm TO nằm NGANG giữa màn hình
                                (mũi kiếm hướng PHẢI, giữ nguyên hướng gốc,
                                KHÔNG xoay). Chữ "MAIN CAMPAIGN" ở HÀNG phía
                                TRÊN thanh kiếm, "FREE TRAINING" ở HÀNG phía
                                DƯỚI. 2 vùng bấm chia theo NỬA TRÊN / NỬA DƯỚI
                                độ dày lưỡi kiếm (không chia theo chiều dài).
                                Đóng bằng ESC (game.py tự xử lý) hoặc bấm ra
                                ngoài kiếm.

Cắt Swords.png theo rect đã đo (quét màu, xem memory ui-interface-asset-inventory
cập nhật): mỗi hàng cao 128px, cột trái (23,105) = viên đá trang trí (đổi màu
theo hàng), cột giữa (192,64) + cột phải (320,97) = thanh/mũi kiếm màu kem
đồng nhất mọi hàng. Ghép ngang (trái+giữa giãn+phải) = 1 thanh kiếm nằm ngang.

Hàm KHÔNG đụng logic game — chỉ pygame thuần + trả Rect cho game.py xử lý click.
"""
import os
import pygame

_HERE   = os.path.dirname(os.path.abspath(__file__))
_UI_DIR = os.path.join(os.path.dirname(_HERE), 'testv2', 'assets', 'UI_interface')
_SWORD_SHEET = os.path.join(_UI_DIR, 'Swords.png')

_ROW_H  = 128
_COL_X  = {'l': (23, 105), 'm': (192, 64), 'r': (320, 97)}   # (x, w)
_ROW_Y  = {'teal': 0, 'red': 128, 'gold': 256, 'purple': 384, 'slate': 512}

_piece_cache: dict = {}   # color -> {'l'/'m'/'r': Surface}


def _pieces(color: str = 'slate') -> dict:
    """Cắt 3 mảnh thanh kiếm ('l'/'m'/'r' — trái/giữa/phải, xem `_COL_X`)
    từ hàng MÀU `color` của `Swords.png` (mỗi màu 1 hàng 128px cao, xem
    `_ROW_Y`). Cache theo `color` (mỗi màu cắt 1 lần). `_assemble_horizontal`
    ghép 3 mảnh này lại thành 1 thanh kiếm hoàn chỉnh dài tuỳ ý."""
    if color not in _piece_cache:
        sheet = pygame.image.load(_SWORD_SHEET).convert_alpha()
        y = _ROW_Y[color]
        _piece_cache[color] = {
            name: sheet.subsurface(pygame.Rect(x, y, w, _ROW_H)).copy()
            for name, (x, w) in _COL_X.items()
        }
    return _piece_cache[color]


def _assemble_horizontal(color: str, length: int, thickness: int) -> pygame.Surface:
    """Ghép trái+giữa(giãn)+phải thành 1 thanh kiếm NGANG dài `length`,
    dày `thickness` (scale đều theo `thickness` so với 128px gốc). Mũi kiếm
    (piece 'r') luôn ở đầu PHẢI — hướng gốc của asset, không xoay."""
    p = _pieces(color)
    scale = thickness / _ROW_H
    l0, m0, r0 = p['l'], p['m'], p['r']
    lw = max(1, round(l0.get_width() * scale))
    rw = max(1, round(r0.get_width() * scale))
    mid_w = max(1, length - lw - rw)

    l = pygame.transform.smoothscale(l0, (lw, thickness))
    r = pygame.transform.smoothscale(r0, (rw, thickness))
    m = pygame.transform.scale(m0, (mid_w, thickness))

    surf = pygame.Surface((length, thickness), pygame.SRCALPHA)
    surf.blit(l, (0, 0))
    surf.blit(m, (lw, 0))
    surf.blit(r, (lw + mid_w, 0))
    return surf


def draw_sword_button(screen, margin: int = 10, width: int = 176,
                      thickness: int = 62, color: str = 'slate') -> pygame.Rect:
    """Vẽ nút hình thanh kiếm góc TRÊN-PHẢI — KHÔNG khung/nền, chỉ hình kiếm
    (to hơn bản cũ). Hover → sáng nhẹ ngay trên hình (không viền/hộp riêng).
    Trả Rect (bounding box của hình) để game.py bắt click.
    """
    W = screen.get_width()
    bar = _assemble_horizontal(color, width, thickness)
    rect = pygame.Rect(W - width - margin, margin, width, thickness)

    if rect.collidepoint(pygame.mouse.get_pos()):
        bar = bar.copy()
        # alpha=0 trong add-tuple: không đụng vùng trong suốt quanh lưỡi kiếm
        # (tránh lỗi hiện khung/hộp ma khi hover — xem ghi chú trong icon_sidebar.py)
        bar.fill((55, 55, 55, 0), special_flags=pygame.BLEND_RGBA_ADD)

    screen.blit(bar, rect.topleft)
    return rect


def draw_sword_mode_picker(screen, current_level: int, max_level: int,
                           color: str = 'slate') -> dict:
    """Vẽ kiếm TO nằm NGANG giữa màn hình (popup chọn chế độ) — mũi kiếm
    hướng PHẢI (không xoay). "MAIN CAMPAIGN" là 1 hàng chữ phía TRÊN thanh
    kiếm; "FREE TRAINING" là 1 hàng chữ phía DƯỚI. Vùng bấm chia theo nửa
    TRÊN / nửa DƯỚI của chính độ dày thanh kiếm (khớp hàng chữ tương ứng).

    Trả {'upper': Rect, 'lower': Rect, 'sword': Rect}.
    """
    W, H = screen.get_size()

    _dim = pygame.Surface((W, H), pygame.SRCALPHA)
    _dim.fill((0, 0, 0, 165))
    screen.blit(_dim, (0, 0))

    length = min(860, W - 100)
    thickness = 260
    bar = _assemble_horizontal(color, length, thickness)
    sword_rect = bar.get_rect(center=(W // 2, H // 2))

    _sh = pygame.Surface((sword_rect.width + 16, sword_rect.height + 16), pygame.SRCALPHA)
    pygame.draw.rect(_sh, (0, 0, 0, 110),
                     (8, 8, sword_rect.width, sword_rect.height), border_radius=10)
    screen.blit(_sh, (sword_rect.x - 8, sword_rect.y - 8))
    screen.blit(bar, sword_rect.topleft)

    # 2 vùng bấm = nửa TRÊN / nửa DƯỚI của chính thanh kiếm (không chia dọc)
    upper = pygame.Rect(sword_rect.x, sword_rect.y, sword_rect.width, sword_rect.height // 2)
    lower = pygame.Rect(sword_rect.x, sword_rect.centery,
                        sword_rect.width, sword_rect.height - sword_rect.height // 2)

    title_font = pygame.font.SysFont('consolas', 34, bold=True)
    sub_font   = pygame.font.SysFont('consolas', 17)
    mpos = pygame.mouse.get_pos()

    for zone in (upper, lower):
        if zone.collidepoint(mpos):
            _hl = pygame.Surface(zone.size, pygame.SRCALPHA)
            _hl.fill((255, 255, 255, 35))
            screen.blit(_hl, zone.topleft)

    def _draw_row(label: str, sub: str, title_y: int, sub_y: int, hover: bool) -> None:
        """Vẽ 1 dòng nhãn (title + sub) với đổ bóng (text đen lệch (+2,+2)px
        vẽ TRƯỚC, text màu vẽ ĐÈ LÊN) — màu title đổi TRẮNG SÁNG khi `hover`
        để phản hồi con trỏ đang ở đúng nửa kiếm này."""
        col = (255, 255, 255) if hover else (240, 230, 210)
        t = title_font.render(label, True, col)
        t_shadow = title_font.render(label, True, (10, 8, 5))
        screen.blit(t_shadow, t_shadow.get_rect(center=(W // 2 + 2, title_y + 2)))
        screen.blit(t, t.get_rect(center=(W // 2, title_y)))
        s = sub_font.render(sub, True, (225, 218, 200))
        s_shadow = sub_font.render(sub, True, (10, 8, 5))
        screen.blit(s_shadow, s_shadow.get_rect(center=(W // 2 + 1, sub_y + 1)))
        screen.blit(s, s.get_rect(center=(W // 2, sub_y)))

    # Hàng chữ TRÊN thanh kiếm — MAIN CAMPAIGN
    _draw_row("MAIN CAMPAIGN", f"Main Challenge - Level {current_level}/{max_level}",
             title_y=sword_rect.top - 54, sub_y=sword_rect.top - 22,
             hover=upper.collidepoint(mpos))
    # Hàng chữ DƯỚI thanh kiếm — FREE TRAINING
    _draw_row("FREE TRAINING", "Training - No Penalty",
             title_y=sword_rect.bottom + 30, sub_y=sword_rect.bottom + 62,
             hover=lower.collidepoint(mpos))

    hint_font = pygame.font.SysFont('consolas', 14)
    hint = hint_font.render("ESC to cancel", True, (170, 175, 190))
    screen.blit(hint, hint.get_rect(center=(W // 2, sword_rect.bottom + 100)))

    return {'upper': upper, 'lower': lower, 'sword': sword_rect}
