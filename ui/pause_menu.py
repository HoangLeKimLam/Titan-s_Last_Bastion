"""
pause_menu.py — Hộp thoại TẠM DỪNG khi bấm ESC (vòng lặp blocking).

Dùng cho 2 ngữ cảnh:
    - Pha Chiến đấu : "Choi tiep" / "Bo cuoc"   (bỏ cuộc → về Sảnh)
    - Pha Sảnh      : "Choi tiep" / "Tro ve menu"

Hàm vẽ overlay mờ ĐÈ lên khung hình hiện tại (cảm giác pause thật) và trả về:
    'resume' → chơi tiếp
    'leave'  → rời đi (game.py tự quyết: combat=bỏ cuộc về sảnh, lobby=về menu)

Hàm KHÔNG đụng tới logic game — chỉ pygame thuần.
"""
import pygame


def run_pause_menu(screen, clock, title: str, resume_label: str,
                   leave_label: str) -> str:
    """Vòng lặp blocking hộp thoại tạm dừng. Trả về 'resume' | 'leave'."""
    W, H = screen.get_size()
    title_font = pygame.font.SysFont('consolas', 42, bold=True)
    btn_font   = pygame.font.SysFont('consolas', 26, bold=True)
    hint_font  = pygame.font.SysFont('consolas', 15)

    # Chụp lại khung hình hiện tại để làm nền mờ phía sau
    backdrop = screen.copy()

    bw, bh, gap = 320, 60, 22
    cx = W // 2
    y0 = H // 2 - 10
    resume_rect = pygame.Rect(cx - bw // 2, y0, bw, bh)
    leave_rect  = pygame.Rect(cx - bw // 2, y0 + bh + gap, bw, bh)

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

        t = title_font.render(title, True, (235, 225, 190))
        screen.blit(t, t.get_rect(center=(cx, y0 - 80)))

        for rect, label, base, hov, bd in [
            (resume_rect, resume_label, (34, 56, 40), (54, 90, 60), (90, 190, 110)),
            (leave_rect,  leave_label,  (60, 36, 36), (95, 52, 52), (210, 120, 120)),
        ]:
            hover = rect.collidepoint(mpos)
            pygame.draw.rect(screen, hov if hover else base, rect, border_radius=8)
            pygame.draw.rect(screen, bd, rect, 2, border_radius=8)
            lbl = btn_font.render(label, True, (235, 240, 245))
            screen.blit(lbl, lbl.get_rect(center=rect.center))

        hint = hint_font.render("ESC = choi tiep", True, (140, 150, 170))
        screen.blit(hint, hint.get_rect(center=(cx, leave_rect.bottom + 28)))

        pygame.display.flip()
