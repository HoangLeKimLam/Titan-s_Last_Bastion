"""
combat_result.py — Màn hình KẾT QUẢ TRẬN (vòng lặp blocking).

Khi một trận kết thúc (thắng do bấm "Kết thúc trận" với HQ còn sống, hoặc
thua do HQ bị phá), game.py gọi run_combat_result() để hiển thị kết quả +
các dòng thông tin (phạt / lên màn). Hàm trả về khi người chơi bấm "VE SANH".

Hàm KHÔNG đụng tới logic game — chỉ pygame thuần.
"""
import pygame


def run_combat_result(screen, clock, won: bool, lines=None) -> None:
    """Vòng lặp blocking hiển thị kết quả trận.

    Args:
        won   : True = thắng, False = thua.
        lines : list[str] các dòng thông tin phụ (phạt, lên màn...).
    """
    W, H = screen.get_size()
    title_font = pygame.font.SysFont('consolas', 56, bold=True)
    info_font  = pygame.font.SysFont('consolas', 22)
    btn_font   = pygame.font.SysFont('consolas', 26, bold=True)
    lines = lines or []

    btn_rect = pygame.Rect(W // 2 - 150, H // 2 + 130, 300, 56)

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

        if won:
            t = title_font.render("CHIEN THANG", True, (235, 215, 130))
        else:
            t = title_font.render("THAT BAI", True, (220, 110, 110))
        screen.blit(t, t.get_rect(center=(W // 2, H // 2 - 120)))

        for i, ln in enumerate(lines):
            li = info_font.render(str(ln), True, (180, 195, 215))
            screen.blit(li, li.get_rect(center=(W // 2, H // 2 - 40 + i * 32)))

        hover = btn_rect.collidepoint(mpos)
        pygame.draw.rect(screen, (50, 80, 120) if hover else (34, 48, 70),
                         btn_rect, border_radius=8)
        pygame.draw.rect(screen, (120, 170, 230) if hover else (70, 100, 150),
                         btn_rect, 2, border_radius=8)
        bl = btn_font.render("VE SANH", True, (225, 235, 250))
        screen.blit(bl, bl.get_rect(center=btn_rect.center))

        pygame.display.flip()
