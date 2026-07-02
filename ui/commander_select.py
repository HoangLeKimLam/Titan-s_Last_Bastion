"""
commander_select.py — Popup TRIỆU HỒI TƯỚNG (vòng lặp blocking).

Khi người chơi bấm "Vượt Ải" hoặc "Thao Trường Tự Do" ở Sảnh, game.py gọi
run_commander_select() để người chơi chọn tướng sẽ ra trận. Hàm trả về CLASS
của tướng được chọn, hoặc None nếu người chơi huỷ (ESC / nút Huỷ).

game.py truyền sẵn danh sách tướng (tên hiển thị + class) nên module này
KHÔNG cần import gì từ characters/ — giữ tách biệt hoàn toàn với logic game.
"""
import pygame


def run_commander_select(screen, clock, options, mode_label: str = ''):
    """Vòng lặp blocking chọn tướng.

    Args:
        screen, clock : đối tượng pygame hiện hành.
        options       : list[(display_name, commander_class)].
        mode_label    : nhãn chế độ ('VUOT AI...' / 'THAO TRUONG...').

    Returns:
        commander_class được chọn, hoặc None nếu huỷ.
    """
    W, H = screen.get_size()
    title_font = pygame.font.SysFont('consolas', 40, bold=True)
    name_font  = pygame.font.SysFont('consolas', 24, bold=True)
    info_font  = pygame.font.SysFont('consolas', 16)
    btn_font   = pygame.font.SysFont('consolas', 24, bold=True)

    n = max(1, len(options))
    cw, ch, gap = 300, 340, 30
    total_w = n * cw + (n - 1) * gap
    x0 = (W - total_w) // 2
    y0 = (H - ch) // 2 - 10
    cards = [
        (pygame.Rect(x0 + i * (cw + gap), y0, cw, ch), name, cls)
        for i, (name, cls) in enumerate(options)
    ]
    confirm_rect = pygame.Rect(W // 2 - 130, y0 + ch + 28, 260, 54)
    cancel_rect  = pygame.Rect(W // 2 - 130, y0 + ch + 92, 260, 38)

    selected = None
    while True:
        clock.tick(60)
        mpos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, _name, cls in cards:
                    if rect.collidepoint(event.pos):
                        selected = cls
                if cancel_rect.collidepoint(event.pos):
                    return None
                if selected is not None and confirm_rect.collidepoint(event.pos):
                    return selected

        # ── Draw ──────────────────────────────────────────────────────────
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((8, 10, 16, 236))
        screen.blit(overlay, (0, 0))

        title = title_font.render("TRIEU HOI TUONG", True, (235, 225, 190))
        screen.blit(title, title.get_rect(center=(W // 2, y0 - 64)))
        if mode_label:
            ml = info_font.render(mode_label, True, (150, 170, 200))
            screen.blit(ml, ml.get_rect(center=(W // 2, y0 - 28)))

        for rect, name, cls in cards:
            is_sel = (cls is selected)
            hover  = rect.collidepoint(mpos)
            bd = (250, 210, 120) if is_sel else ((150, 180, 220) if hover else (70, 90, 120))
            pygame.draw.rect(screen, (26, 32, 46), rect, border_radius=10)
            pygame.draw.rect(screen, bd, rect, 3 if is_sel else 2, border_radius=10)
            nm = name_font.render(str(name), True, (235, 235, 245))
            screen.blit(nm, nm.get_rect(center=(rect.centerx, rect.top + 44)))
            hint = info_font.render("Click de chon", True, (130, 140, 160))
            screen.blit(hint, hint.get_rect(center=(rect.centerx, rect.bottom - 32)))

        active = selected is not None
        pygame.draw.rect(screen, (40, 90, 50) if active else (40, 44, 50),
                         confirm_rect, border_radius=8)
        pygame.draw.rect(screen, (90, 200, 110) if active else (70, 75, 85),
                         confirm_rect, 2, border_radius=8)
        ct = btn_font.render("TRIEU HOI", True,
                             (200, 255, 210) if active else (120, 125, 135))
        screen.blit(ct, ct.get_rect(center=confirm_rect.center))

        pygame.draw.rect(screen, (60, 40, 40), cancel_rect, border_radius=8)
        pygame.draw.rect(screen, (160, 90, 90), cancel_rect, 1, border_radius=8)
        cct = info_font.render("Huy (ESC)", True, (210, 170, 170))
        screen.blit(cct, cct.get_rect(center=cancel_rect.center))

        pygame.display.flip()
