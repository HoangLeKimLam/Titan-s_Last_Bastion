"""
combat_result.py — Màn hình KẾT QUẢ TRẬN (vòng lặp blocking).

Khi một trận kết thúc (thắng do bấm "Kết thúc trận" với HQ còn sống, hoặc
thua do HQ bị phá), game.py gọi run_combat_result() để hiển thị kết quả +
các dòng thông tin (phạt / lên màn). Hàm trả về khi người chơi bấm "VE SANH".

Hàm KHÔNG đụng tới logic game — chỉ pygame thuần.
"""
import pygame

from ui.nine_slice import draw_button, draw_nine_slice, draw_ribbon_title


def run_combat_result(screen, clock, won: bool, lines=None) -> None:
    """Vòng lặp blocking hiển thị kết quả trận.

    Args:
        won   : True = thắng, False = thua.
        lines : list[str] các dòng thông tin phụ (phạt, lên màn...).
    """
    W, H = screen.get_size()
    title_font = pygame.font.SysFont('consolas', 32, bold=True)
    info_font  = pygame.font.SysFont('consolas', 20)
    btn_font   = pygame.font.SysFont('consolas', 22, bold=True)
    lines = lines or []

    # Panel giấy cao theo số dòng nội dung; banner tiêu đề đè mép trên panel.
    panel_w = 640
    panel_h = max(260, 171 + len(lines) * 32)
    panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
    panel_rect.center = (W // 2, H // 2)

    btn_rect = pygame.Rect(0, 0, 280, 54)
    btn_rect.centerx = panel_rect.centerx
    btn_rect.bottom = panel_rect.bottom - 26

    while True:
        clock.tick(60)
        mpos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_SPACE):
                return
            if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                    and btn_rect.collidepoint(event.pos)):
                return

        # ── Draw ──────────────────────────────────────────────────────────
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((6, 8, 14, 240))
        screen.blit(overlay, (0, 0))

        draw_nine_slice(screen, panel_rect, style='paper')
        banner_rect = draw_ribbon_title(screen, panel_rect,
                                        "VICTORY" if won else "DEFEAT",
                                        title_font, color='gold' if won else 'red')

        for i, ln in enumerate(lines):
            li = info_font.render(str(ln), True, (55, 45, 35))
            screen.blit(li, li.get_rect(
                center=(panel_rect.centerx, banner_rect.bottom + 28 + i * 32)))

        draw_button(screen, btn_rect, "BACK TO LOBBY", style='blue', font=btn_font,
                   hover=btn_rect.collidepoint(mpos))

        pygame.display.flip()
