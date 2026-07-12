"""
pause_menu.py — Hộp thoại TẠM DỪNG khi bấm ESC (vòng lặp blocking).

Dùng cho 2 ngữ cảnh:
    - Pha Chiến đấu : "Resume" / "Abandon Battle"   (bỏ cuộc → về Sảnh)
    - Pha Sảnh      : "Resume" / "Back to Menu"

Hàm vẽ overlay mờ ĐÈ lên khung hình hiện tại (cảm giác pause thật), bên trong
là 1 panel giấy (RegularPaper) + banner tiêu đề (Banner) đè mép trên, rồi trả về:
    'resume' → chơi tiếp
    'leave'  → rời đi (game.py tự quyết: combat=bỏ cuộc về sảnh, lobby=về menu)

Hàm KHÔNG đụng tới logic game — chỉ pygame thuần.
"""
import pygame

from ui.nine_slice import draw_button, draw_nine_slice, draw_ribbon_title


def run_pause_menu(screen, clock, title: str, resume_label: str,
                   leave_label: str) -> str:
    """Vòng lặp blocking hộp thoại tạm dừng. Trả về 'resume' | 'leave'."""
    W, H = screen.get_size()
    title_font = pygame.font.SysFont('consolas', 30, bold=True)
    btn_font   = pygame.font.SysFont('consolas', 24, bold=True)
    hint_font  = pygame.font.SysFont('consolas', 15)

    # Chụp lại khung hình hiện tại để làm nền mờ phía sau
    backdrop = screen.copy()

    bw, bh, gap = 300, 58, 20
    banner_half, gap_top, bottom_pad = 31, 26, 24
    panel_w = bw + 80
    panel_h = banner_half + gap_top + bh + gap + bh + bottom_pad
    panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
    panel_rect.center = (W // 2, H // 2)

    cx = panel_rect.centerx
    resume_rect = pygame.Rect(0, 0, bw, bh)
    resume_rect.centerx = cx
    resume_rect.top = panel_rect.top + banner_half + gap_top
    leave_rect = pygame.Rect(0, 0, bw, bh)
    leave_rect.centerx = cx
    leave_rect.top = resume_rect.bottom + gap

    while True:
        clock.tick(60)
        mpos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return 'resume'
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return 'resume'          # ESC lần nữa = chơi tiếp
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return 'resume'
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if resume_rect.collidepoint(event.pos):
                    return 'resume'
                if leave_rect.collidepoint(event.pos):
                    return 'leave'

        # ── Draw ──────────────────────────────────────────────────────────
        screen.blit(backdrop, (0, 0))
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((6, 8, 14, 200))
        screen.blit(overlay, (0, 0))

        draw_nine_slice(screen, panel_rect, style='paper')
        draw_ribbon_title(screen, panel_rect, title, title_font, color='teal')

        for rect, label, style in [
            (resume_rect, resume_label, 'blue'),
            (leave_rect,  leave_label,  'red'),
        ]:
            draw_button(screen, rect, label, style=style, font=btn_font,
                       hover=rect.collidepoint(mpos))

        hint = hint_font.render("ESC = resume", True, (140, 150, 170))
        screen.blit(hint, hint.get_rect(center=(cx, panel_rect.bottom + 24)))

        pygame.display.flip()
