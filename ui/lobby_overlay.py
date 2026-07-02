"""
lobby_overlay.py — Overlay vẽ ĐÈ lên map ở pha Sảnh và pha Chiến đấu.

Khác với 3 màn hình blocking (menu / chọn tướng / kết quả), 2 hàm ở đây được
gọi MỖI FRAME trong game loop của game.py để vẽ nút lên trên map đang chạy:

    draw_lobby_overlay()    : pha Sảnh — 2 nút "Vượt Ải" / "Thao Trường Tự Do".
    draw_combat_controls()  : pha Chiến đấu — banner chế độ + nút "Kết thúc trận".

Mỗi hàm trả về dict các pygame.Rect để game.py kiểm tra click ở frame kế tiếp
(đúng theo cách codebase hiện tại dựng rect khi draw rồi xử lý click sau).
Hàm KHÔNG đụng tới logic game.
"""
import pygame


def draw_lobby_overlay(screen, level: int) -> dict:
    """Vẽ 2 nút chọn chế độ ở Sảnh. Trả về {'vuot_ai': Rect, 'thao_truong': Rect}."""
    W = screen.get_width()
    title_font = pygame.font.SysFont('consolas', 22, bold=True)
    sub_font   = pygame.font.SysFont('consolas', 14)

    bw, bh, gap = 260, 56, 24
    total = bw * 2 + gap
    x0 = (W - total) // 2
    y  = 16
    mpos = pygame.mouse.get_pos()

    # Banner nền
    banner = pygame.Surface((total + 40, bh + 46), pygame.SRCALPHA)
    banner.fill((10, 14, 22, 185))
    screen.blit(banner, (x0 - 20, y - 8))
    lbl = sub_font.render("SANH CHUAN BI  -  Chon che do chien dau", True, (150, 165, 190))
    screen.blit(lbl, (x0, y - 4))
    y += 18

    va = pygame.Rect(x0, y, bw, bh)
    tt = pygame.Rect(x0 + bw + gap, y, bw, bh)
    specs = [
        (va, "VUOT AI", f"Thu thach chinh - Man {level}/5", (60, 40, 40), (120, 70, 70)),
        (tt, "THAO TRUONG TU DO", "Luyen tap - khong phat", (40, 55, 40), (70, 110, 70)),
    ]
    for rect, label, sub, base, hov in specs:
        hover = rect.collidepoint(mpos)
        pygame.draw.rect(screen, hov if hover else base, rect, border_radius=8)
        pygame.draw.rect(screen, (210, 180, 120) if hover else (120, 120, 130),
                         rect, 2, border_radius=8)
        t = title_font.render(label, True, (240, 225, 200))
        screen.blit(t, t.get_rect(center=(rect.centerx, rect.centery - 8)))
        s = sub_font.render(sub, True, (190, 190, 200))
        screen.blit(s, s.get_rect(center=(rect.centerx, rect.centery + 16)))

    return {'vuot_ai': va, 'thao_truong': tt}


def draw_combat_controls(screen, mode_label: str) -> dict:
    """Vẽ banner chế độ + nút 'Kết thúc trận'. Trả về {'end': Rect}."""
    W = screen.get_width()
    title_font = pygame.font.SysFont('consolas', 18, bold=True)

    bw, bh = 190, 40
    banner_w = 380
    x0 = (W - banner_w) // 2
    y  = 12

    banner = pygame.Surface((banner_w, 30), pygame.SRCALPHA)
    banner.fill((20, 12, 12, 185))
    screen.blit(banner, (x0, y))
    t = title_font.render(mode_label, True, (240, 200, 160))
    screen.blit(t, t.get_rect(center=(x0 + banner_w // 2, y + 15)))

    end_rect = pygame.Rect(W - bw - 16, y, bw, bh)
    hover = end_rect.collidepoint(pygame.mouse.get_pos())
    pygame.draw.rect(screen, (90, 50, 50) if hover else (60, 36, 36),
                     end_rect, border_radius=6)
    pygame.draw.rect(screen, (210, 120, 120) if hover else (140, 80, 80),
                     end_rect, 2, border_radius=6)
    el = title_font.render("KET THUC TRAN", True, (255, 210, 200))
    screen.blit(el, el.get_rect(center=end_rect.center))

    return {'end': end_rect}


def draw_thao_truong_wave_select(screen, wave_chosen: int,
                                 wave_min: int, wave_max: int) -> dict:
    """Overlay chọn wave bắt đầu cho Thao Trường Tự Do.

    Trả về {'dec': Rect, 'inc': Rect, 'confirm': Rect}. Không đụng logic game.
    """
    W, H = screen.get_width(), screen.get_height()
    title_font = pygame.font.SysFont('consolas', 22, bold=True)
    body_font  = pygame.font.SysFont('consolas', 16)
    num_font   = pygame.font.SysFont('consolas', 30, bold=True)
    mpos = pygame.mouse.get_pos()

    pw, ph = 420, 230
    px = (W - pw) // 2
    py = (H - ph) // 2

    panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
    panel.fill((14, 20, 16, 235))
    screen.blit(panel, (px, py))
    pygame.draw.rect(screen, (90, 150, 90), (px, py, pw, ph), 2, border_radius=10)

    t = title_font.render("THAO TRUONG TU DO", True, (200, 235, 200))
    screen.blit(t, t.get_rect(center=(px + pw // 2, py + 30)))
    s = body_font.render("Chon Wave bat dau:", True, (170, 200, 175))
    screen.blit(s, s.get_rect(center=(px + pw // 2, py + 70)))

    # Nút giảm / số / nút tăng
    cy = py + 120
    dec = pygame.Rect(px + 90, cy - 24, 48, 48)
    inc = pygame.Rect(px + pw - 90 - 48, cy - 24, 48, 48)
    for rect, label in ((dec, "-"), (inc, "+")):
        hover = rect.collidepoint(mpos)
        pygame.draw.rect(screen, (50, 90, 55) if hover else (35, 60, 40),
                         rect, border_radius=8)
        pygame.draw.rect(screen, (120, 200, 120) if hover else (80, 130, 85),
                         rect, 2, border_radius=8)
        gl = num_font.render(label, True, (210, 240, 210))
        screen.blit(gl, gl.get_rect(center=rect.center))

    nl = num_font.render(str(wave_chosen), True, (255, 240, 180))
    screen.blit(nl, nl.get_rect(center=(px + pw // 2, cy)))
    rng = body_font.render(f"(toi da: {wave_min}..{wave_max})", True, (130, 160, 135))
    screen.blit(rng, rng.get_rect(center=(px + pw // 2, cy + 36)))

    # Nút xác nhận
    confirm = pygame.Rect(px + (pw - 200) // 2, py + ph - 50, 200, 36)
    hover = confirm.collidepoint(mpos)
    pygame.draw.rect(screen, (50, 110, 60) if hover else (38, 80, 46),
                     confirm, border_radius=8)
    pygame.draw.rect(screen, (120, 220, 130) if hover else (80, 150, 90),
                     confirm, 2, border_radius=8)
    cl = title_font.render("XAC NHAN", True, (220, 250, 220))
    screen.blit(cl, cl.get_rect(center=confirm.center))

    return {'dec': dec, 'inc': inc, 'confirm': confirm}


def draw_thao_truong_controls(screen, wave: int, titan_alive: int,
                              wave_active: bool) -> dict:
    """Banner Thao Trường + nút 'Wave tiếp theo' / 'Kết thúc luyện tập'.

    Trả về {'next': Rect, 'end': Rect}. Hai nút mờ khi wave đang diễn ra.
    """
    W = screen.get_width()
    title_font = pygame.font.SysFont('consolas', 18, bold=True)
    info_font  = pygame.font.SysFont('consolas', 14)

    banner_w = 380
    x0 = (W - banner_w) // 2
    y  = 12
    banner = pygame.Surface((banner_w, 30), pygame.SRCALPHA)
    banner.fill((12, 20, 14, 190))
    screen.blit(banner, (x0, y))
    t = title_font.render(f"THAO TRUONG  -  Wave {wave}", True, (200, 240, 200))
    screen.blit(t, t.get_rect(center=(x0 + banner_w // 2, y + 15)))
    inf = info_font.render(f"Titan song: {titan_alive}", True,
                           (255, 180, 120) if titan_alive else (140, 170, 145))
    screen.blit(inf, (x0 + 8, y + 34))

    mpos = pygame.mouse.get_pos()
    bw, bh = 190, 40

    # Nút "Wave tiếp theo" (mờ khi wave đang chạy)
    next_rect = pygame.Rect(16, y, bw, bh)
    _draw_tt_button(screen, next_rect, "WAVE TIEP THEO", title_font,
                    enabled=not wave_active, mpos=mpos,
                    base=(36, 60, 40), hov=(50, 95, 56),
                    border=(90, 160, 95), txt=(210, 250, 210))

    # Nút "Kết thúc luyện tập" (mờ khi wave đang chạy)
    end_rect = pygame.Rect(W - bw - 16, y, bw, bh)
    _draw_tt_button(screen, end_rect, "KET THUC TRAIN", title_font,
                    enabled=not wave_active, mpos=mpos,
                    base=(60, 36, 36), hov=(90, 50, 50),
                    border=(140, 80, 80), txt=(255, 210, 200))

    return {'next': next_rect, 'end': end_rect}


def _draw_tt_button(screen, rect, label, font, enabled, mpos,
                    base, hov, border, txt) -> None:
    """Vẽ 1 nút Thao Trường có trạng thái bật/mờ."""
    if not enabled:
        pygame.draw.rect(screen, (40, 44, 42), rect, border_radius=6)
        pygame.draw.rect(screen, (70, 75, 72), rect, 2, border_radius=6)
        l = font.render(label, True, (110, 115, 112))
        screen.blit(l, l.get_rect(center=rect.center))
        return
    hover = rect.collidepoint(mpos)
    pygame.draw.rect(screen, hov if hover else base, rect, border_radius=6)
    pygame.draw.rect(screen, border, rect, 2, border_radius=6)
    l = font.render(label, True, txt)
    screen.blit(l, l.get_rect(center=rect.center))


def draw_combat_minimap(screen, maria_box_px, all_sections,
                        titan_dots, boss_dots, hq_pos, cmdr_pos=None) -> None:
    """
    Vẽ minimap radar góc trên phải trong pha chiến đấu.

    maria_box_px : (x0, y0, x1, y1) — bounding box MARIA tính bằng pixel
    all_sections : danh sách WallSection (có .x, .y, ._hp, ._max_hp, .is_alive)
    titan_dots   : [(x, y), ...] — chấm cam nhỏ
    boss_dots    : [(x, y), ...] — chấm đỏ to hơn
    hq_pos       : (x, y) | None — chấm vàng
    cmdr_pos     : (x, y) | None — chấm xanh lá
    """
    W = screen.get_width()
    MM_W, MM_H = 190, 148
    MM_X = W - MM_W - 8
    MM_Y = 56          # bên dưới banner chiến đấu (y=12, h=40, gap=4)

    # ── Nền mờ ───────────────────────────────────────────────────────────────
    _bg = pygame.Surface((MM_W, MM_H), pygame.SRCALPHA)
    _bg.fill((6, 10, 6, 210))
    screen.blit(_bg, (MM_X, MM_Y))
    pygame.draw.rect(screen, (55, 100, 50), (MM_X, MM_Y, MM_W, MM_H), 1)

    # ── Nhãn ─────────────────────────────────────────────────────────────────
    _lf = pygame.font.SysFont('consolas', 11, bold=True)
    _lbl = _lf.render('RADAR', True, (90, 180, 70))
    screen.blit(_lbl, (MM_X + 4, MM_Y + 2))
    _cnt_lbl = _lf.render(
        f'T:{len(titan_dots)}  B:{len(boss_dots)}', True, (160, 120, 80))
    screen.blit(_cnt_lbl, (MM_X + MM_W - _cnt_lbl.get_width() - 4, MM_Y + 2))

    # ── Tỉ lệ bản đồ ─────────────────────────────────────────────────────────
    mx0, my0, mx1, my1 = maria_box_px
    _cw = MM_W - 4            # content width (2px padding each side)
    _ch = MM_H - 16           # content height (14px label + 2px bottom)
    _scale = min(_cw / max(mx1 - mx0, 1), _ch / max(my1 - my0, 1))
    _ox = MM_X + 2 + (_cw - (mx1 - mx0) * _scale) / 2
    _oy = MM_Y + 14 + (_ch - (my1 - my0) * _scale) / 2

    def _mm(wx, wy):
        return (int(_ox + (wx - mx0) * _scale),
                int(_oy + (wy - my0) * _scale))

    def _in(px, py, r=0):
        return (MM_X - r <= px <= MM_X + MM_W + r and
                MM_Y - r <= py <= MM_Y + MM_H + r)

    # ── Đoạn tường — chấm nhỏ màu theo HP% ──────────────────────────────────
    for _s in all_sections:
        if not _s.is_alive:
            continue
        _pct = _s._hp / max(_s._max_hp, 1)
        _sc = ((50, 180, 55) if _pct > 0.66 else
               (200, 175, 40) if _pct > 0.33 else (195, 50, 40))
        _px, _py = _mm(_s.x, _s.y)
        if _in(_px, _py):
            pygame.draw.rect(screen, _sc, (_px, _py, 2, 2))

    # ── HQ — chấm vàng ───────────────────────────────────────────────────────
    if hq_pos:
        _hx, _hy = _mm(*hq_pos)
        if _in(_hx, _hy, 4):
            pygame.draw.circle(screen, (255, 200, 60), (_hx, _hy), 5)
            pygame.draw.circle(screen, (255, 240, 140), (_hx, _hy), 5, 1)

    # ── Tướng — chấm xanh lá ─────────────────────────────────────────────────
    if cmdr_pos:
        _cx, _cy = _mm(*cmdr_pos)
        if _in(_cx, _cy, 3):
            pygame.draw.circle(screen, (60, 230, 100), (_cx, _cy), 4)
            pygame.draw.circle(screen, (160, 255, 180), (_cx, _cy), 4, 1)

    # ── Titan — chấm cam ─────────────────────────────────────────────────────
    for _tx, _ty in titan_dots:
        _dx, _dy = _mm(_tx, _ty)
        if _in(_dx, _dy, 3):
            pygame.draw.circle(screen, (255, 130, 25), (_dx, _dy), 3)

    # ── Boss — chấm đỏ to hơn với vòng ngoài ─────────────────────────────────
    for _bx, _by in boss_dots:
        _dx, _dy = _mm(_bx, _by)
        if _in(_dx, _dy, 6):
            pygame.draw.circle(screen, (210, 30, 30), (_dx, _dy), 6)
            pygame.draw.circle(screen, (255, 90, 70), (_dx, _dy), 6, 1)

    return {
        'rect':  pygame.Rect(MM_X, MM_Y, MM_W, MM_H),
        'ox':    _ox,   'oy':    _oy,
        'scale': _scale,
        'mx0':   mx0,   'my0':   my0,
    }
