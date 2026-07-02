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

_BG = (16, 20, 28)
_SAVE_FILE = 'save.json'


def _save_exists() -> bool:
    """True nếu có file lưu để 'Continue'."""
    return os.path.exists(_SAVE_FILE)


def run_main_menu(screen, clock) -> str:
    """Vòng lặp blocking cho menu chính. Trả về 'new' | 'continue' | 'exit'."""
    W, H = screen.get_size()
    title_font = pygame.font.SysFont('consolas', 64, bold=True)
    sub_font   = pygame.font.SysFont('consolas', 20)
    btn_font   = pygame.font.SysFont('consolas', 28, bold=True)
    note_font  = pygame.font.SysFont('consolas', 16)

    has_save = _save_exists()
    # (label, action, enabled)
    items = [
        ('NEW GAME', 'new',      True),
        ('CONTINUE', 'continue', has_save),
        ('EXIT',     'exit',     True),
    ]
    bw, bh, gap = 360, 64, 20
    bx  = (W - bw) // 2
    by0 = H // 2 - 30
    # rects: (Rect, label, action, enabled)
    rects = [
        (pygame.Rect(bx, by0 + i * (bh + gap), bw, bh), label, action, enabled)
        for i, (label, action, enabled) in enumerate(items)
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
                for rect, _label, action, enabled in rects:
                    if enabled and rect.collidepoint(event.pos):
                        return action

        # ── Draw ──────────────────────────────────────────────────────────
        screen.fill(_BG)
        title = title_font.render("TITAN'S LAST BASTION", True, (235, 220, 180))
        screen.blit(title, title.get_rect(center=(W // 2, H // 2 - 170)))
        sub = sub_font.render("Phong tuyen cuoi cung", True, (140, 150, 170))
        screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 - 120)))

        for rect, label, action, enabled in rects:
            hover = enabled and rect.collidepoint(mpos)
            if not enabled:
                bg, fg, bd = (30, 34, 42), (90, 95, 105), (50, 55, 65)
            elif hover:
                bg, fg, bd = (55, 90, 140), (255, 255, 255), (120, 180, 240)
            else:
                bg, fg, bd = (30, 40, 58), (200, 215, 235), (70, 110, 160)
            pygame.draw.rect(screen, bg, rect, border_radius=8)
            pygame.draw.rect(screen, bd, rect, 2, border_radius=8)
            lbl = btn_font.render(label, True, fg)
            screen.blit(lbl, lbl.get_rect(center=rect.center))
            if not enabled and action == 'continue':
                note = note_font.render("(chua co file luu)", True, (110, 90, 90))
                screen.blit(note, note.get_rect(midleft=(rect.right + 16, rect.centery)))

        pygame.display.flip()
