"""
commander_select.py — Popup TRIỆU HỒI TƯỚNG (vòng lặp blocking).

Khi người chơi bấm "Vượt Ải" hoặc "Thao Trường Tự Do" ở Sảnh, game.py gọi
run_commander_select() để người chơi chọn tướng sẽ ra trận. Hàm trả về CLASS
của tướng được chọn, hoặc None nếu người chơi huỷ (ESC / nút Huỷ).

game.py truyền sẵn danh sách tướng (tên hiển thị + class) nên module này
KHÔNG cần import gì từ characters/ — giữ tách biệt hoàn toàn với logic game.
"""
import pygame

from ui.nine_slice import draw_button, draw_nine_slice, draw_ribbon_title


def run_commander_select(screen, clock, options, mode_label: str = '', portraits=None):
    """Vòng lặp blocking chọn tướng.

    Args:
        screen, clock : đối tượng pygame hiện hành.
        options       : list[(display_name, commander_class)].
        mode_label    : nhãn chế độ ('VUOT AI...' / 'THAO TRUONG...').
        portraits     : dict[commander_class, pygame.Surface] tuỳ chọn — ảnh
                         đại diện (frame idle của tướng) hiển thị giữa mỗi
                         thẻ. Không truyền hoặc thiếu key cho class nào →
                         thẻ đó chỉ hiện tên (không vẽ ảnh).

    Returns:
        commander_class được chọn, hoặc None nếu huỷ.
    """
    portraits = portraits or {}
    W, H = screen.get_size()
    title_font = pygame.font.SysFont('consolas', 32, bold=True)
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

    # Panel giấy bao toàn bộ khu vực (banner + card + nút) — thẻ tướng vẫn giữ
    # màu navy riêng, chỉ thêm khung giấy da làm nền chung (kiểu cuộn da RPG).
    _pad_x, _pad_top, _pad_bottom = 44, 100, 36
    panel_rect = pygame.Rect(0, 0, total_w + _pad_x * 2,
                             _pad_top + ch + 130 + _pad_bottom)
    panel_rect.centerx = W // 2
    panel_rect.top = y0 - _pad_top

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

        draw_nine_slice(screen, panel_rect, style='paper')
        banner_rect = draw_ribbon_title(screen, panel_rect, "SUMMON COMMANDER",
                                        title_font, color='teal')
        if mode_label:
            ml = info_font.render(mode_label, True, (90, 78, 55))
            screen.blit(ml, ml.get_rect(center=(W // 2, banner_rect.bottom + 16)))

        for rect, name, cls in cards:
            is_sel = (cls is selected)
            hover  = rect.collidepoint(mpos)
            bd = (250, 210, 120) if is_sel else ((150, 180, 220) if hover else (70, 90, 120))
            pygame.draw.rect(screen, (26, 32, 46), rect, border_radius=10)
            pygame.draw.rect(screen, bd, rect, 3 if is_sel else 2, border_radius=10)
            nm = name_font.render(str(name), True, (235, 235, 245))
            screen.blit(nm, nm.get_rect(center=(rect.centerx, rect.top + 44)))
            _portrait = portraits.get(cls)
            if _portrait is not None:
                _pw, _ph = _portrait.get_size()
                if _pw > 0 and _ph > 0:
                    _box = 180
                    _pscale = min(_box / _pw, _box / _ph)
                    _sw, _sh = int(_pw * _pscale), int(_ph * _pscale)
                    _pscaled = pygame.transform.scale(_portrait, (_sw, _sh))
                    screen.blit(_pscaled, _pscaled.get_rect(
                        center=(rect.centerx, rect.top + 44 + 24 + _box // 2)))
            hint = info_font.render("Click to select", True, (130, 140, 160))
            screen.blit(hint, hint.get_rect(center=(rect.centerx, rect.bottom - 32)))

        active = selected is not None
        if active:
            draw_button(screen, confirm_rect, "SUMMON", style='blue', font=btn_font,
                       hover=confirm_rect.collidepoint(mpos))
        else:
            pygame.draw.rect(screen, (40, 44, 50), confirm_rect, border_radius=8)
            pygame.draw.rect(screen, (70, 75, 85), confirm_rect, 2, border_radius=8)
            ct = btn_font.render("SUMMON", True, (120, 125, 135))
            screen.blit(ct, ct.get_rect(center=confirm_rect.center))

        draw_button(screen, cancel_rect, "CANCEL (ESC)", style='red', font=info_font,
                   hover=cancel_rect.collidepoint(mpos))

        pygame.display.flip()
