"""
icon_sidebar.py — Sidebar dọc 3 icon, áp sát cạnh PHẢI màn hình, ngay dưới nút
kiếm chọn chế độ (THÊM MỚI, chỉ đồ họa/UI).

Icon từ trên xuống (to, để thưa, KHÔNG khung/viền riêng từng ô — chỉ có nền
dải chung mượn cạnh trái Banner.png):
    Icon_05 (kiếm chéo) — CHƯA CÓ chức năng (placeholder, hiển thị mờ hơn).
    Icon_03 (đồng xu)   — mở/đóng Shop (thay nút BUILD cũ).
    Icon_02 (khúc gỗ)   — mở/đóng Túi đồ (thay nút BAG cũ).

Nền dải dùng draw_left_edge_strip() (cột trái Banner.png, xem nine_slice.py).

Hàm KHÔNG đụng logic game — chỉ vẽ + trả Rect cho game.py xử lý click
(game.py tự quyết định show_shop/show_inventory dựa trên Rect trả về, y hệt
cách btn_bag/btn_shop cũ hoạt động — chỉ đổi đồ họa/vị trí, không đổi state).
"""
import os
import pygame

from ui.nine_slice import draw_left_edge_strip

_HERE   = os.path.dirname(os.path.abspath(__file__))
_UI_DIR = os.path.join(os.path.dirname(_HERE), 'testv2', 'assets', 'UI_interface')

_ICON_PATHS = {
    'feature':  os.path.join(_UI_DIR, 'Icon_05.png'),
    'shop':     os.path.join(_UI_DIR, 'Icon_03.png'),
    'inventory':os.path.join(_UI_DIR, 'Icon_02.png'),
}

_icon_cache: dict = {}


def _get_icon(key: str, size: int) -> pygame.Surface:
    """Nạp+scale icon (tra đường dẫn qua `_ICON_PATHS[key]`) về `size`×`size`,
    cache theo `(key, size)`. Lỗi tải → Surface trong suốt rỗng (không crash)."""
    cache_key = (key, size)
    if cache_key not in _icon_cache:
        try:
            raw = pygame.image.load(_ICON_PATHS[key]).convert_alpha()
            _icon_cache[cache_key] = pygame.transform.smoothscale(raw, (size, size))
        except Exception:
            _icon_cache[cache_key] = pygame.Surface((size, size), pygame.SRCALPHA)
    return _icon_cache[cache_key]


def draw_icon_sidebar(screen, top_y: int = None, active_shop: bool = False,
                      active_inventory: bool = False, margin: int = 10,
                      icon_size: int = 76, gap: int = 26,
                      pad: int = 18) -> dict:
    """Vẽ sidebar 3 icon dọc, áp cạnh phải. Icon to, để thưa, KHÔNG khung/viền
    riêng từng ô — chỉ nền dải chung (Banner.png).

    `top_y` : None (mặc định) → tự CĂN GIỮA theo chiều dọc màn hình (tránh đè
              lên minimap ở góc trên-phải khi combat). Truyền số cụ thể để
              ghim vị trí cố định thay vì căn giữa.

    Trả {'feature': Rect, 'shop': Rect, 'inventory': Rect} để game.py bắt click.
    """
    W, H = screen.get_size()
    strip_w = icon_size + pad * 2
    strip_h = pad * 2 + icon_size * 3 + gap * 2
    if top_y is None:
        top_y = (H - strip_h) // 2   # THÊM MỚI: căn giữa cạnh phải màn hình
    strip_rect = pygame.Rect(W - strip_w - margin, top_y, strip_w, strip_h)

    draw_left_edge_strip(screen, strip_rect, style='banner')

    mpos = pygame.mouse.get_pos()
    rects = {}
    specs = [
        ('feature',   False),          # chưa có chức năng
        ('shop',      active_shop),
        ('inventory', active_inventory),
    ]
    _y = strip_rect.top + pad
    for key, active in specs:
        icon = _get_icon(key, icon_size).copy()
        r = pygame.Rect(strip_rect.centerx - icon_size // 2, _y, icon_size, icon_size)
        rects[key] = r

        hover = r.collidepoint(mpos)
        is_placeholder = (key == 'feature')

        if is_placeholder:
            icon.set_alpha(110)          # mờ hơn = chưa dùng được
        elif active:
            # alpha=0 trong add-tuple: KHÔNG đụng vùng trong suốt quanh icon,
            # chỉ cộng nhẹ RGB vào phần đã có màu (tránh lỗi "trắng xoá / hiện
            # khung ma" do BLEND_RGBA_ADD cộng full RGB bất kể alpha nếu alpha>0).
            icon.fill((90, 90, 90, 0), special_flags=pygame.BLEND_RGBA_ADD)
        elif hover:
            icon.fill((55, 55, 55, 0), special_flags=pygame.BLEND_RGBA_ADD)

        screen.blit(icon, r.topleft)

        # Chấm nhỏ báo trạng thái active (thay cho khung) — không phải "khung"
        # bao quanh, chỉ 1 dấu chấm nhỏ dưới icon.
        if active:
            pygame.draw.circle(screen, (235, 200, 110),
                               (r.centerx, r.bottom + 8), 4)

        _y += icon_size + gap

    return rects
