"""
hud_panels.py — Panel HUD trạng thái HQ: avatar + thanh máu chuyên nghiệp,
cố định góc TRÊN-TRÁI màn hình (THÊM MỚI, chỉ đồ họa).

Thay cho thanh máu HQ nổi trên map (cũ, ở structures/hq.py `draw()` — nay là
no-op). Panel này vẽ 1 lần/frame trong game.py, không phụ thuộc camera nên
luôn cố định vị trí bất kể người chơi cuộn map.

Hàm KHÔNG đụng logic game — chỉ đọc hq._hp/_max_hp để hiển thị, không sửa.
"""
import os
import pygame

_HERE   = os.path.dirname(os.path.abspath(__file__))
_UI_DIR = os.path.join(os.path.dirname(_HERE), 'testv2', 'assets', 'UI_interface')
_AVATAR_PATH = os.path.join(_UI_DIR, 'Avatars_06.png')

_avatar_cache: dict = {}   # size -> Surface, nạp 1 lần / kích thước


def _get_avatar(size: int) -> pygame.Surface:
    """Nạp+scale avatar HQ về `size`×`size`, cache theo kích thước (gọi
    nhiều lần cùng `size` không đọc lại đĩa). Lỗi tải (file thiếu/hỏng)
    → cache Surface TRONG SUỐT rỗng thay vì crash, `draw_hq_status()` vẫn
    vẽ được (chỉ thiếu ảnh avatar)."""
    if size not in _avatar_cache:
        try:
            raw = pygame.image.load(_AVATAR_PATH).convert_alpha()
            _avatar_cache[size] = pygame.transform.smoothscale(raw, (size, size))
        except Exception:
            _avatar_cache[size] = pygame.Surface((size, size), pygame.SRCALPHA)
    return _avatar_cache[size]


def draw_hq_status(screen, hq, margin: int = 12, avatar_size: int = 82,
                   bar_w: int = 230, bar_h: int = 28) -> pygame.Rect:
    """Vẽ avatar + thanh máu HQ chuyên nghiệp, cố định góc TRÊN-TRÁI.

    hq  : Headquarters instance (đọc _hp/_max_hp) — None thì bỏ qua, trả Rect rỗng.
    Trả về Rect tổng bao toàn khối (để game.py biết chừa chỗ cho phần tử khác).
    """
    if hq is None:
        return pygame.Rect(0, 0, 0, 0)

    avatar = _get_avatar(avatar_size)
    avatar_rect = pygame.Rect(margin, margin, avatar_size, avatar_size)

    bar_rect = pygame.Rect(avatar_rect.right + 10,
                           avatar_rect.centery - bar_h // 2 - 8,
                           bar_w, bar_h)

    # Nhãn phía trên thanh
    label_font = pygame.font.SysFont('consolas', 15, bold=True)
    lbl = label_font.render('HEADQUARTERS', True, (235, 220, 185))
    screen.blit(lbl, (bar_rect.left, bar_rect.top - 16))

    # Khung bar chuyên nghiệp: viền vàng nhạt ngoài, nền lõm tối, fill đỏ có
    # dải sáng phía trên (hiệu ứng bóng 3D), viền trong đen mảnh.
    _hp  = max(0, getattr(hq, '_hp', 0))
    _max = max(1, getattr(hq, '_max_hp', 1))
    ratio = min(1.0, _hp / _max)

    pygame.draw.rect(screen, (18, 12, 8), bar_rect.inflate(6, 6), border_radius=6)
    pygame.draw.rect(screen, (60, 15, 15), bar_rect, border_radius=4)
    fill_w = int((bar_rect.width - 4) * ratio)
    if fill_w > 0:
        fill_rect = pygame.Rect(bar_rect.x + 2, bar_rect.y + 2, fill_w, bar_rect.height - 4)
        col_hp = ((190, 45, 40) if ratio > 0.5 else
                 (205, 150, 40) if ratio > 0.25 else (210, 40, 35))
        pygame.draw.rect(screen, col_hp, fill_rect, border_radius=3)
        _hi = fill_rect.copy()
        _hi.height = max(2, fill_rect.height // 3)
        _hi_surf = pygame.Surface(_hi.size, pygame.SRCALPHA)
        _hi_surf.fill((255, 255, 255, 60))
        screen.blit(_hi_surf, _hi.topleft)
    pygame.draw.rect(screen, (205, 170, 100), bar_rect.inflate(6, 6), 2, border_radius=6)
    pygame.draw.rect(screen, (0, 0, 0), bar_rect, 1, border_radius=4)

    hp_font = pygame.font.SysFont('consolas', 15, bold=True)
    hp_txt = hp_font.render(f'{_hp:,} / {_max:,}', True, (255, 235, 220))
    screen.blit(hp_txt, hp_txt.get_rect(center=bar_rect.center))

    # Avatar: bóng đổ + khung viền vàng
    _shadow = pygame.Surface((avatar_size + 8, avatar_size + 8), pygame.SRCALPHA)
    pygame.draw.rect(_shadow, (0, 0, 0, 90), (4, 4, avatar_size, avatar_size), border_radius=8)
    screen.blit(_shadow, (avatar_rect.x - 2, avatar_rect.y - 2))
    pygame.draw.rect(screen, (30, 22, 14), avatar_rect.inflate(6, 6), border_radius=8)
    screen.blit(avatar, avatar_rect)
    pygame.draw.rect(screen, (205, 170, 100), avatar_rect.inflate(6, 6), 2, border_radius=8)

    return avatar_rect.unionall(
        [bar_rect, pygame.Rect(bar_rect.left, bar_rect.top - 18, bar_rect.width, 18)])
