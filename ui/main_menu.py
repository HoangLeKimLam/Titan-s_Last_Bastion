"""
main_menu.py — Màn hình MENU CHÍNH (vòng lặp blocking riêng).

Khi mới mở game, game.py gọi run_main_menu() MỘT LẦN trước khi vào game loop.
Hàm tự chạy vòng lặp riêng, vẽ menu và trả về lựa chọn của người chơi:
    'new'      → New Game
    'continue' → Continue (chỉ bật khi có file save.json)
    'exit'     → Exit / đóng cửa sổ

Hàm KHÔNG đụng tới logic game — chỉ pygame thuần.
"""
import os

import pygame

from ui.nine_slice import draw_button, draw_nine_slice, draw_ribbon_title

_BG = (16, 20, 28)
_SAVE_FILE = 'save.json'
_HERE     = os.path.dirname(os.path.abspath(__file__))
_BG_IMAGE = os.path.join(os.path.dirname(_HERE), 'testv2', 'assets', 'menu.png')


def _save_exists() -> bool:
    """True nếu có file lưu để 'Continue'."""
    return os.path.exists(_SAVE_FILE)


def _load_background(w: int, h: int) -> pygame.Surface:
    """Nạp menu.png, scale kiểu 'cover' (lấp đầy màn hình, cắt bớt dư ra,
    không méo hình) rồi cắt giữa đúng W×H. Fallback màu nền cũ nếu thiếu ảnh."""
    try:
        raw = pygame.image.load(_BG_IMAGE).convert()
    except Exception:
        surf = pygame.Surface((w, h))
        surf.fill(_BG)
        return surf
    iw, ih = raw.get_size()
    scale = max(w / iw, h / ih)
    sw, sh = round(iw * scale), round(ih * scale)
    scaled = pygame.transform.smoothscale(raw, (sw, sh))
    surf = pygame.Surface((w, h))
    surf.blit(scaled, ((w - sw) // 2, (h - sh) // 2))
    # Overlay tối dần lên phía trên (chỗ đặt tiêu đề) để chữ luôn rõ trên nền
    # ảnh sáng/rực màu — càng lên cao càng tối, phần dưới giữ nguyên độ sáng.
    _grad = pygame.Surface((w, h), pygame.SRCALPHA)
    for _gy in range(0, h, 4):
        _t = 1.0 - min(1.0, _gy / (h * 0.62))
        _a = int(150 * max(0.0, _t) ** 1.4)
        if _a > 0:
            pygame.draw.rect(_grad, (10, 12, 16, _a), (0, _gy, w, 4))
    surf.blit(_grad, (0, 0))
    return surf


def run_main_menu(screen, clock) -> str:
    """Vòng lặp blocking cho menu chính. Trả về 'new' | 'continue' | 'exit'."""
    W, H = screen.get_size()
    background = _load_background(W, H)
    title_font = pygame.font.SysFont('consolas', 64, bold=True)
    sub_font   = pygame.font.SysFont('consolas', 20)
    btn_font   = pygame.font.SysFont('consolas', 28, bold=True)
    note_font  = pygame.font.SysFont('consolas', 16)

    has_save = _save_exists()
    # (label, action, enabled, style) — style: 'blue' tich cuc | 'red' tieu cuc
    items = [
        ('NEW GAME', 'new',      True,     'blue'),
        ('CONTINUE', 'continue', has_save, 'blue'),
        ('EXIT',     'exit',     True,     'red'),
    ]
    bw, bh, gap = 360, 64, 20
    bx  = (W - bw) // 2
    by0 = H // 2 - 30
    # rects: (Rect, label, action, enabled, style)
    rects = [
        (pygame.Rect(bx, by0 + i * (bh + gap), bw, bh), label, action, enabled, style)
        for i, (label, action, enabled, style) in enumerate(items)
    ]

    while True:
        clock.tick(60)
        mpos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return 'exit'
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return 'exit'
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, _label, action, enabled, _style in rects:
                    if enabled and rect.collidepoint(event.pos):
                        return action

        # ── Draw ──────────────────────────────────────────────────────────
        screen.blit(background, (0, 0))

        title      = title_font.render("TITAN'S LAST BASTION", True, (250, 238, 205))
        title_sh   = title_font.render("TITAN'S LAST BASTION", True, (20, 14, 8))
        screen.blit(title_sh, title_sh.get_rect(center=(W // 2 + 3, H // 2 - 170 + 3)))
        screen.blit(title, title.get_rect(center=(W // 2, H // 2 - 170)))

        sub    = sub_font.render("The Last Line of Defense", True, (235, 220, 180))
        sub_sh = sub_font.render("The Last Line of Defense", True, (20, 14, 8))
        screen.blit(sub_sh, sub_sh.get_rect(center=(W // 2 + 2, H // 2 - 120 + 2)))
        screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 - 120)))

        for rect, label, action, enabled, style in rects:
            hover = enabled and rect.collidepoint(mpos)
            if not enabled:
                pygame.draw.rect(screen, (30, 34, 42), rect, border_radius=8)
                pygame.draw.rect(screen, (50, 55, 65), rect, 2, border_radius=8)
                lbl = btn_font.render(label, True, (90, 95, 105))
                screen.blit(lbl, lbl.get_rect(center=rect.center))
            else:
                draw_button(screen, rect, label, style=style, font=btn_font, hover=hover)
            if not enabled and action == 'continue':
                note    = note_font.render("(no save file)", True, (225, 210, 195))
                note_sh = note_font.render("(no save file)", True, (15, 10, 8))
                _npos = (rect.right + 16, rect.centery)
                screen.blit(note_sh, note_sh.get_rect(midleft=(_npos[0] + 1, _npos[1] + 1)))
                screen.blit(note, note.get_rect(midleft=_npos))

        pygame.display.flip()


def confirm_new_game(screen, clock) -> bool:
    """Hộp thoại xác nhận khi bấm NEW GAME nhưng ĐÃ có save (sẽ bị ghi đè).

    Chỉ gọi khi `_save_exists()` là True — nếu chưa từng có save thì New Game
    tiến hành thẳng, không cần hỏi. Trả về True nếu người chơi xác nhận muốn
    bắt đầu mới (đè save cũ), False nếu huỷ (giữ nguyên save, quay lại menu).
    """
    W, H = screen.get_size()
    title_font = pygame.font.SysFont('consolas', 26, bold=True)
    btn_font   = pygame.font.SysFont('consolas', 22, bold=True)
    body_font  = pygame.font.SysFont('consolas', 16)

    backdrop = screen.copy()

    bw, bh, gap = 320, 56, 18
    banner_half, gap_top, body_h, bottom_pad = 31, 26, 44, 22
    panel_w = bw * 2 + 60
    panel_h = banner_half + gap_top + body_h + bh + bottom_pad
    panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
    panel_rect.center = (W // 2, H // 2)

    body_y = panel_rect.top + banner_half + gap_top
    cancel_rect = pygame.Rect(0, 0, bw, bh)
    cancel_rect.top = body_y + body_h
    cancel_rect.left = panel_rect.centerx - bw - gap // 2
    confirm_rect = pygame.Rect(0, 0, bw, bh)
    confirm_rect.top = body_y + body_h
    confirm_rect.left = panel_rect.centerx + gap // 2

    while True:
        clock.tick(60)
        mpos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if cancel_rect.collidepoint(event.pos):
                    return False
                if confirm_rect.collidepoint(event.pos):
                    return True

        screen.blit(backdrop, (0, 0))
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((6, 8, 14, 200))
        screen.blit(overlay, (0, 0))

        draw_nine_slice(screen, panel_rect, style='paper')
        draw_ribbon_title(screen, panel_rect, 'START NEW GAME?', title_font,
                          color='red')

        line1 = body_font.render(
            'A saved game already exists.', True, (55, 45, 35))
        line2 = body_font.render(
            'Starting a new game will overwrite it.', True, (140, 60, 40))
        screen.blit(line1, line1.get_rect(center=(panel_rect.centerx, body_y + 12)))
        screen.blit(line2, line2.get_rect(center=(panel_rect.centerx, body_y + 32)))

        draw_button(screen, cancel_rect, 'CANCEL', style='blue', font=btn_font,
                   hover=cancel_rect.collidepoint(mpos))
        draw_button(screen, confirm_rect, 'NEW GAME', style='red', font=btn_font,
                   hover=confirm_rect.collidepoint(mpos))

        pygame.display.flip()
