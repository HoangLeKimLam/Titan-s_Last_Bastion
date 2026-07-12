"""
vuot_ai.py — UI riêng cho chế độ VƯỢT ẢI (THÊM MỚI, pygame thuần).

Gồm 3 thành phần, KHÔNG đụng tới logic game:

    run_boss_intro()    : cutscene chặn ~2.2s khi boss xuất hiện — vẽ ĐÈ lên một
                          ảnh chụp (snapshot) khung hình đã canh camera vào boss,
                          thêm letterbox + thông báo + thanh đếm ngược. Vì là vòng
                          lặp chặn nên thế giới đóng băng và input bị khoá tự nhiên.
    draw_vuot_ai_hud()  : banner tiến độ wave (gọi mỗi frame trong pha chiến đấu).
    draw_boss_hp_bar()  : thanh máu boss ở giữa-dưới màn hình (gọi mỗi frame).

run_boss_intro() dùng CHUNG đối tượng `clock` với game loop và tick 60fps mỗi
frame, nên khi trả về không gây nhảy dt ở vòng lặp chính.
"""
import pygame

# Tên hiển thị đẹp cho từng boss (khoá khớp _VA_BOSS_CLASSES trong game.py).
_BOSS_DISPLAY = {
    'Colossal': 'COLOSSAL TITAN',
    'Beast':    'BEAST TITAN',
    'Founding': 'FOUNDING TITAN',
}

_INTRO_DURATION = 2.2   # giây


def boss_display_name(boss_key: str) -> str:
    """Tên hiển thị; fallback = chính khoá nếu chưa khai báo."""
    return _BOSS_DISPLAY.get(boss_key, str(boss_key).upper())


def run_boss_intro(screen, clock, bg_snapshot, boss_key: str,
                   subtitle: str = "BOSS APPROACHING") -> None:
    """Cutscene chặn khi boss xuất hiện.

    Args:
        bg_snapshot : Surface ảnh chụp khung hình (đã canh camera vào boss).
        boss_key    : khoá boss ('Colossal' | 'Beast' | 'Founding').
        subtitle    : dòng phụ phía trên tên boss.
    """
    W, H = screen.get_size()
    name = boss_display_name(boss_key)

    font_title = pygame.font.SysFont("georgia", 30, bold=True)
    font_sub   = pygame.font.SysFont("georgia", 14)

    timer = _INTRO_DURATION
    while timer > 0:
        clock.tick(60)
        timer -= 1.0 / 60.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            # Cho phép bỏ qua nhanh bằng phím — vẫn khoá điều khiển nhân vật.
            if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                return

        # ── Nền: ảnh chụp khung hình đã canh vào boss ──────────────────────
        screen.blit(bg_snapshot, (0, 0))

        # Tối nhẹ toàn cảnh cho cảm giác điện ảnh
        vig = pygame.Surface((W, H), pygame.SRCALPHA)
        vig.fill((0, 0, 0, 90))
        screen.blit(vig, (0, 0))

        # Letterbox trên/dưới
        bar = max(44, H // 12)
        pygame.draw.rect(screen, (0, 0, 0), (0, 0, W, bar))
        pygame.draw.rect(screen, (0, 0, 0), (0, H - bar, W, bar))

        # Thanh đếm ngược dưới letterbox trên
        frac = max(0.0, timer / _INTRO_DURATION)
        pygame.draw.rect(screen, (60, 35, 0), (0, bar, W, 4))
        pygame.draw.rect(screen, (210, 155, 50), (0, bar, int(W * frac), 4))

        # ── Thông báo giữa màn ─────────────────────────────────────────────
        progress = 1.0 - frac
        fade_in  = min(1.0, progress / 0.15)
        fade_out = min(1.0, timer / 0.4)
        alpha    = int(min(fade_in, fade_out) * 230)

        band_h = 58
        band_y = H // 2 - band_h // 2 - 10
        band = pygame.Surface((W, band_h), pygame.SRCALPHA)
        band.fill((0, 0, 0, 120))
        band.set_alpha(alpha)
        screen.blit(band, (0, band_y))

        line = pygame.Surface((W, 1), pygame.SRCALPHA)
        line.fill((180, 130, 60, alpha))
        screen.blit(line, (0, band_y))
        screen.blit(line, (0, band_y + band_h - 1))

        sub = font_sub.render(f"— {subtitle} —", True, (180, 130, 60))
        sub.set_alpha(alpha)
        screen.blit(sub, (W // 2 - sub.get_width() // 2, band_y + 8))

        title = font_title.render(name, True, (240, 220, 185))
        title.set_alpha(alpha)
        screen.blit(title, (W // 2 - title.get_width() // 2, band_y + 24))

        pygame.display.flip()


def draw_vuot_ai_hud(screen, level: int, max_level: int, wave: int, total: int,
                     titan_alive: int, is_boss_wave: bool) -> None:
    """Banner tiến độ Vượt Ải, canh giữa theo chiều ngang phía trên màn hình
    (không nút, chỉ hiển thị) — trước đây ở góc trên-trái, đè lên HUD tướng.

    Vượt Ải KHÔNG có nút 'Wave tiếp theo' / 'Kết thúc trận': wave tự ra sau
    thời gian nghỉ; chỉ kết thúc khi THẮNG (dọn hết wave) hoặc THUA (HQ vỡ).
    """
    title_font = pygame.font.SysFont('consolas', 16, bold=True)
    info_font  = pygame.font.SysFont('consolas', 13)

    W, _H = screen.get_size()
    pw, ph = 232, 76
    px, py = (W - pw) // 2, 12
    panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
    panel.fill((18, 12, 22, 195))
    screen.blit(panel, (px, py))
    border = (210, 90, 80) if is_boss_wave else (120, 110, 150)
    pygame.draw.rect(screen, border, (px, py, pw, ph), 2, border_radius=8)

    tlbl = f"VUOT AI  -  Man {level}/{max_level}"
    screen.blit(title_font.render(tlbl, True, (240, 220, 200)), (px + 10, py + 7))

    wlbl = f"Wave {max(wave, 0)}/{total}"
    screen.blit(info_font.render(wlbl, True, (200, 205, 225)), (px + 10, py + 31))

    if is_boss_wave:
        bl = info_font.render(">> BOSS WAVE <<", True, (255, 110, 90))
        screen.blit(bl, (px + 10, py + 52))
    else:
        col = (255, 180, 120) if titan_alive else (150, 200, 150)
        il = info_font.render(f"Titan con song: {titan_alive}", True, col)
        screen.blit(il, (px + 10, py + 52))


def draw_boss_hp_bar(screen, boss_key: str, hp: float, max_hp: float) -> None:
    """Thanh máu boss ở giữa-dưới màn hình."""
    if max_hp <= 0:
        return
    W, H = screen.get_size()
    name = boss_display_name(boss_key)
    frac = max(0.0, min(1.0, hp / max_hp))

    bar_w = int(W * 0.52)
    bar_h = 26
    bar_x = (W - bar_w) // 2
    bar_y = H - 72

    name_font = pygame.font.SysFont('georgia', 16, bold=True)
    hp_font   = pygame.font.SysFont('consolas', 14, bold=True)

    # Nền
    pygame.draw.rect(screen, (16, 6, 6),
                     (bar_x - 3, bar_y - 3, bar_w + 6, bar_h + 6), border_radius=8)
    # Fill đỏ + lớp sáng
    fill_w = int(bar_w * frac)
    if fill_w > 0:
        pygame.draw.rect(screen, (170, 26, 26),
                         (bar_x, bar_y, fill_w, bar_h), border_radius=6)
        pygame.draw.rect(screen, (228, 70, 55),
                         (bar_x, bar_y, fill_w, max(3, bar_h // 3)), border_radius=6)
    # Viền vàng
    pygame.draw.rect(screen, (205, 145, 55),
                     (bar_x - 3, bar_y - 3, bar_w + 6, bar_h + 6), 2, border_radius=8)

    # Tên boss phía trên thanh
    nlbl = name_font.render(name, True, (240, 210, 175))
    screen.blit(nlbl, (bar_x, bar_y - 22))
    # Số HP giữa thanh
    hlbl = hp_font.render(f"{int(max(hp, 0)):,} / {int(max_hp):,}", True, (255, 220, 185))
    screen.blit(hlbl, (bar_x + bar_w // 2 - hlbl.get_width() // 2, bar_y + 5))
