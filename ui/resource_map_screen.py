"""
resource_map_screen.py — Overlay EXPEDITION MAP (view cho DispatchManager).

Chỉ là VIEW: không giữ game-state, mọi thao tác forward xuống DispatchManager
(dispatch / retreat). Mở ở Sảnh qua nút `feature` trên sidebar.

Bố cục:
    - Trái: nền = testv2/assets/map.png (cache scaled), CƠ SỞ CHÍNH ở CHÍNH GIỮA.
      Tự vẽ NODE quanh tâm theo (angle, distance) dùng ICON tài nguyên thật
      (core/resource/*.png) thay vì hình khối; mọi node cách tâm >= MIN_DISTANCE
      (vẽ 1 vòng "khoảng cách tới hạn" mờ để người chơi thấy).
    - Phải ("vùng chọn lựa"): nền giấy da (nine_slice 'paper') + ruy băng tiêu
      đề lớn (ribbon), cùng bộ dùng ở Shop/Inventory — chọn số lính 3 loại
      (+/- BỘI 5), gửi đội, và danh sách đội đang đi kèm icon tài nguyên +
      nút Retreat (rút chủ động, giữ đồ).

Thông báo gặp titan + minigame ping KHÔNG nằm ở đây — chúng vẽ ở tầng main-loop
(độc lập, hiện cả khi đóng tab). Toàn bộ text tiếng Anh.
"""
from __future__ import annotations

import math
import os

import pygame

from systems.dispatch_system import (
    MIN_DISTANCE, MAX_DISTANCE, SOLDIER_KINDS, SOLDIER_STEP,
    STATE_LOOTING,
)
from ui.nine_slice import draw_nine_slice, draw_ribbon_title

# Ảnh nền map (testv2/assets/map.png) — từ ui/ lên d:\OOP_project.
_ROOT = os.path.dirname(os.path.dirname(__file__))
_MAP_PNG = os.path.join(_ROOT, "testv2", "assets", "map.png")

# Icon tài nguyên (core/resource/{type}.png) — CÙNG bộ ảnh dùng cho droppped loot.
_ICON_DIR = os.path.join(_ROOT, "titans_last_bastion", "core", "resource")
_icon_cache: dict = {}   # (resource_type, size) -> Surface | None


def load_resource_icon(resource_type: str, size: int = 24):
    """Nạp + cache icon PNG cho 1 loại tài nguyên (None nếu không có file)."""
    key = (resource_type, size)
    if key in _icon_cache:
        return _icon_cache[key]
    surf = None
    path = os.path.join(_ICON_DIR, f"{resource_type}.png")
    try:
        raw = pygame.image.load(path).convert_alpha()
        surf = pygame.transform.smoothscale(raw, (size, size))
    except (pygame.error, FileNotFoundError):
        surf = None
    _icon_cache[key] = surf
    return surf


# Màu viền/nền dự phòng theo loại tài nguyên (khi icon không nạp được).
_RES_COLOR = {
    "wood":            (95, 190, 110),
    "stone":           (160, 160, 175),
    "ice_ore":         (140, 210, 235),
    "ore":             (200, 150, 90),
    "fire_ore":        (235, 110, 70),
    "serum":           (200, 120, 235),
    "water_ore":       (100, 170, 220),
    "electric_ore":    (230, 220, 90),
    "acid_ore":        (150, 220, 90),
    "wind_ore":        (190, 220, 210),
    "titan_pheromone": (230, 90, 150),
}
_KIND_ABBR = {"Warrior": "W", "Archer": "A", "Lancer": "L"}

# Bảng màu chữ cho nền giấy da (parchment) — tối, ấm, khớp shop/inventory.
_INK_DARK   = (55, 45, 35)
_INK_HEAD   = (80, 60, 30)
_INK_MUTED  = (120, 100, 78)
_INK_GOOD   = (60, 130, 70)
_INK_BAD    = (150, 60, 50)


class ResourceMapScreen:
    """Overlay bản đồ thám hiểm, điều khiển 1 DispatchManager."""

    _bg_cache = None            # (w, h) -> Surface đã scale (dùng chung mọi instance)
    _bg_cache_key = None

    def __init__(self, dispatch_mgr, screen_size=(1024, 768)) -> None:
        """Bọc lấy `dispatch_mgr` (thuần logic, module này chỉ đọc/forward).
        Mọi Rect tương tác (`_close_rect`, `_pick_btns`, `_send_rect`,
        `_party_rows`) khởi tạo RỖNG — chỉ được TÍNH LẠI mỗi lần `_draw()`
        chạy, rồi `handle_event()` dùng lại (decoupling draw/event giống
        `ExpeditionOverlay`). `_selected`/`_pick` giữ state UI cục bộ (node
        đang chọn + số lính đang cấu hình gửi) — KHÔNG thuộc DispatchManager."""
        self.mgr = dispatch_mgr
        self._sw, self._sh = screen_size
        self._closed = False
        self._selected = None                       # ExpeditionZone đang chọn
        self._pick = {k: 0 for k in SOLDIER_KINDS}  # số lính đang chọn gửi
        # Rects tính lại mỗi lần layout (dùng chung draw + handle_event).
        self._close_rect = None
        self._pick_btns = {}                        # (kind, '-'|'+') -> Rect
        self._send_rect = None
        self._party_rows = []                       # [(Rect, party)]

    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        """True nếu overlay đang mở (chưa `close()`) — game.py dùng quyết
        định có vẽ/nhận input cho overlay này không."""
        return not self._closed

    def close(self) -> None:
        """Đóng overlay (nút X hoặc phím tắt game.py xử lý) — set cờ, KHÔNG
        reset `_selected`/`_pick` (mở lại vẫn giữ lựa chọn dở dang)."""
        self._closed = True

    # ------------------------------------------------------------------
    # Layout helpers (deterministic — dùng chung draw & handle_event)
    # ------------------------------------------------------------------
    def _map_rect(self) -> pygame.Rect:
        """Vùng bản đồ (VUÔNG, cạnh bằng min(chiều cao khả dụng, 60% chiều
        rộng màn hình)) — neo góc trái, căn giữa theo trục dọc. Tính TỪ
        `_sw`/`_sh` MỖI LẦN gọi (không cache) nên luôn khớp kích thước
        màn hình hiện tại, kể cả sau resize."""
        margin = 24
        side = min(self._sh - 2 * margin, int(self._sw * 0.60))
        return pygame.Rect(margin, (self._sh - side) // 2, side, side)

    def _panel_rect(self) -> pygame.Rect:
        """Vùng panel "vùng chọn lựa" (phải) — lấp đầy phần còn lại bên
        phải `_map_rect()`, cùng chiều cao với bản đồ."""
        m = self._map_rect()
        px = m.right + 20
        return pygame.Rect(px, m.top, self._sw - px - 24, m.height)

    def _center(self) -> tuple:
        """Tâm hình học của vùng bản đồ — gốc toạ độ cho MỌI node (angle,
        distance) quy đổi ra pixel qua `_node_pos`/`_radius_px`."""
        m = self._map_rect()
        return (m.centerx, m.centery)

    def _radius_px(self, distance: float) -> float:
        """Chiếu TUYỆT ĐỐI từ tâm: distance=0 -> radius=0 (đúng tâm), distance=
        MAX_DISTANCE -> radius=r_max (mép bản đồ). KHÔNG chuẩn hóa theo
        [MIN_DISTANCE, MAX_DISTANCE] (bug cũ: làm vòng MIN_DISTANCE luôn vẽ ở
        CÙNG 1 vị trí bất kể MIN_DISTANCE là bao nhiêu — sửa lại tăng
        MIN_DISTANCE sẽ tăng đúng kích thước vòng cấm)."""
        half = self._map_rect().width / 2
        r_max = 0.93 * half
        t = distance / max(1e-6, MAX_DISTANCE)
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        return t * r_max

    def _node_pos(self, zone) -> tuple:
        """Toạ độ pixel của `zone` trên bản đồ — toạ độ CỰC (angle, distance
        của zone) quy đổi sang toạ độ Descartes quanh `_center()`, bán kính
        qua `_radius_px()` (chiếu tuyệt đối, không chuẩn hoá theo dải)."""
        cx, cy = self._center()
        r = self._radius_px(zone.distance)
        return (int(cx + math.cos(zone.angle) * r),
                int(cy + math.sin(zone.angle) * r))

    # ------------------------------------------------------------------
    # Event
    # ------------------------------------------------------------------
    def handle_event(self, event) -> bool:
        """Nuốt click chuột trái khi mở. True nếu event được dùng."""
        if self._closed:
            return False
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        mp = event.pos if hasattr(event, "pos") else pygame.mouse.get_pos()

        if self._close_rect and self._close_rect.collidepoint(mp):
            self.close()
            return True

        # +/- bộ chọn lính (chỉ khi đang chọn 1 node).
        for (kind, sign), rect in self._pick_btns.items():
            if rect.collidepoint(mp):
                self._adjust_pick(kind, sign)
                return True

        # Gửi đội.
        if self._send_rect and self._send_rect.collidepoint(mp):
            if self._selected is not None and self.mgr.can_dispatch(self._pick):
                self.mgr.dispatch(self._selected, dict(self._pick))
                self._pick = {k: 0 for k in SOLDIER_KINDS}
            return True

        # Nút Retreat của từng đội.
        for rect, party in self._party_rows:
            if rect.collidepoint(mp):
                self.mgr.retreat(party)
                return True

        # Click node để chọn.
        for zone in self.mgr.zones:
            nx, ny = self._node_pos(zone)
            if (mp[0] - nx) ** 2 + (mp[1] - ny) ** 2 <= 24 * 24:
                self._selected = zone
                self._pick = {k: 0 for k in SOLDIER_KINDS}
                return True

        # Click vùng map trống → bỏ chọn; vẫn nuốt (overlay modal).
        if self._map_rect().collidepoint(mp) or self._panel_rect().collidepoint(mp):
            self._selected = None
            return True
        return True

    def _adjust_pick(self, kind: str, sign: str) -> None:
        """Bấm +/- trên bộ chọn quân số của loại `kind`. '+' tăng thêm
        `SOLDIER_STEP` (bội 5) nhưng KHÔNG VƯỢT số lính sẵn có ĐÃ LÀM TRÒN
        XUỐNG bội 5 gần nhất (`avail - avail % SOLDIER_STEP`) — đảm bảo
        lựa chọn LUÔN hợp lệ (bội 5, không vượt kho) mà không cần validate
        riêng ở `handle_event`. '-' giảm về 0 tối thiểu."""
        cur = self._pick.get(kind, 0)
        avail = self.mgr.available(kind)
        if sign == "+":
            cur = min(avail - avail % SOLDIER_STEP, cur + SOLDIER_STEP)
        else:
            cur = max(0, cur - SOLDIER_STEP)
        self._pick[kind] = cur

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, screen) -> None:
        """Điểm vào vẽ công khai — bọc `_draw()` trong try/except NGẦM
        `(pygame.error, AttributeError)` (lỗi vẽ không crash cả game),
        không vẽ gì nếu overlay đã đóng."""
        if self._closed:
            return
        try:
            self._draw(screen)
        except (pygame.error, AttributeError):
            pass

    def _draw(self, screen) -> None:
        """Vẽ toàn bộ overlay: nền mờ phủ màn hình → bản đồ (`_draw_map`)
        → panel bên phải (`_draw_panel`) → nút đóng (X). Thứ tự vẽ quyết
        định layer — panel/nút đè lên bản đồ nếu chồng lấn."""
        # Nền mờ toàn màn.
        ov = pygame.Surface((self._sw, self._sh), pygame.SRCALPHA)
        ov.fill((6, 9, 14, 232))
        screen.blit(ov, (0, 0))

        self._draw_map(screen)
        self._draw_panel(screen)

        # Nút đóng.
        self._close_rect = pygame.Rect(self._sw - 40, 12, 28, 28)
        pygame.draw.rect(screen, (90, 30, 30), self._close_rect)
        pygame.draw.rect(screen, (210, 90, 90), self._close_rect, 2)
        self._text(screen, "consolas", 18, "x", (240, 240, 240),
                   center=self._close_rect.center, bold=True)

    def _draw_map(self, screen) -> None:
        """Vẽ nền bản đồ (`map.png` scaled, cache theo kích thước qua
        `_get_bg`), vòng tròn "khoảng cách tới hạn" `MIN_DISTANCE` (vùng
        cấm quanh cơ sở — trực quan hoá lý do MỌI node đều cách xa tâm ít
        nhất chừng đó), biểu tượng CƠ SỞ ở tâm, rồi lặp vẽ TỪNG node
        (`_draw_node`) kèm số đội hiện đang đóng ở đó (đếm qua `id(zone)`
        vì `ExpeditionZone` là `@dataclass(eq=False)` — so sánh identity)."""
        rect = self._map_rect()
        bg = self._get_bg(rect.width, rect.height)
        if bg is not None:
            screen.blit(bg, rect.topleft)
        else:
            pygame.draw.rect(screen, (26, 34, 30), rect)
        pygame.draw.rect(screen, (120, 150, 120), rect, 2)
        self._text(screen, "consolas", 20, "EXPEDITION MAP", (235, 235, 235),
                   topleft=(rect.left + 8, rect.top + 6), bold=True)

        cx, cy = self._center()
        # Vòng "khoảng cách tới hạn" (MIN_DISTANCE) — vùng cấm quanh cơ sở.
        pygame.draw.circle(screen, (90, 120, 150), (cx, cy),
                           int(self._radius_px(MIN_DISTANCE)), 1)
        # Cơ sở chính ở giữa.
        pygame.draw.circle(screen, (250, 220, 120), (cx, cy), 16)
        pygame.draw.circle(screen, (120, 90, 30), (cx, cy), 16, 2)
        self._text(screen, "consolas", 12, "BASE", (30, 30, 30),
                   center=(cx, cy), bold=True)

        # Số đội đang ở mỗi node.
        parties_at = {}
        for p in self.mgr.parties:
            parties_at[id(p.zone)] = parties_at.get(id(p.zone), 0) + 1

        for zone in self.mgr.zones:
            self._draw_node(screen, zone, parties_at.get(id(zone), 0))

    def _draw_node(self, screen, zone, n_parties: int) -> None:
        """Vẽ 1 node: đường nối mờ từ cơ sở, viền vàng NẾU đang được chọn
        (`zone is self._selected` — so sánh identity), nền tròn tương phản
        + icon tài nguyên thật (fallback vòng tròn màu `_RES_COLOR` nếu icon
        thiếu), nhãn tên node, và badge số đội đang đóng tại đây (`n_parties`,
        chỉ vẽ nếu > 0)."""
        nx, ny = self._node_pos(zone)
        col = _RES_COLOR.get(zone.resource_type, (200, 200, 200))
        icon_size = 26 if zone.is_item else 30
        icon = load_resource_icon(zone.resource_type, icon_size)

        # Đường nối cơ sở → node (mờ).
        pygame.draw.line(screen, (70, 80, 95), self._center(), (nx, ny), 1)
        if zone is self._selected:
            pygame.draw.circle(screen, (255, 235, 120), (nx, ny), 22, 2)

        # Nền tròn phía sau icon (contrast against busy terrain) + icon thật.
        backdrop_r = icon_size // 2 + 5
        pygame.draw.circle(screen, (24, 26, 22), (nx, ny), backdrop_r)
        pygame.draw.circle(screen, col, (nx, ny), backdrop_r, 2)
        if icon is not None:
            screen.blit(icon, icon.get_rect(center=(nx, ny)))
        else:
            pygame.draw.circle(screen, col, (nx, ny), icon_size // 2)

        # Nhãn: chỉ tên node (icon đã truyền tải loại tài nguyên).
        self._text(screen, "consolas", 12, zone.name, (220, 225, 220),
                   center=(nx, ny + backdrop_r + 12))
        if n_parties > 0:
            badge = pygame.Rect(nx + backdrop_r - 6, ny - backdrop_r - 4, 18, 16)
            pygame.draw.rect(screen, (40, 60, 90), badge)
            pygame.draw.rect(screen, (120, 170, 220), badge, 1)
            self._text(screen, "consolas", 12, str(n_parties), (230, 235, 245),
                       center=badge.center, bold=True)

    def _draw_panel(self, screen) -> None:
        """Vẽ toàn bộ panel bên phải, 3 khối XẾP DỌC theo `py` tăng dần
        (layout thủ công, không dùng layout engine):

        1. BARRACKS: số lính idle/away theo loại (`available()`/`expedition_counts()`).
        2. Bộ chọn quân gửi đi — CHỈ vẽ nếu `_selected` khác None: icon+tên
           node đích, hàng +/- cho từng loại lính (Rect nút LƯU vào
           `_pick_btns` để `handle_event` dùng), nút SEND (màu xanh nếu
           `can_dispatch()` hợp lệ, xám nếu không — phản hồi trực quan
           không cần bấm thử). Không chọn node → hiện gợi ý "chọn 1 node".
        3. PARTIES OUT: danh sách đội đang thám hiểm, mỗi dòng kèm icon +
           thành phần quân (viết tắt `_KIND_ABBR`) + loot hiện có + trạng
           thái (nếu khác LOOTING) + nút Retreat — nút CHỈ enable (thêm vào
           `_party_rows` để nhận click) khi đội đang ở `STATE_LOOTING`
           (đang gặp titan/combat thì không cho rút qua panel này, phải xử
           lý qua `ExpeditionOverlay`).
        """
        rect = self._panel_rect()
        draw_nine_slice(screen, rect, style="paper")
        title_font = pygame.font.SysFont("consolas", 24, bold=True)
        banner = draw_ribbon_title(screen, rect, "EXPEDITION LOG", title_font,
                                   color="teal")

        px = rect.left + 32
        py = banner.bottom + 16
        inner_right = rect.right - 30

        # ── Kho trại (idle) từng loại + đang thám hiểm ──────────────────
        exp = self.mgr.expedition_counts()
        self._text(screen, "consolas", 15, "BARRACKS (ready / away)",
                   _INK_HEAD, topleft=(px, py), bold=True)
        py += 22
        for k in SOLDIER_KINDS:
            self._text(screen, "consolas", 13,
                       f"{k:8s} {self.mgr.available(k):3d} / {exp[k]:3d} away",
                       _INK_DARK, topleft=(px, py))
            py += 19
        py += 10
        pygame.draw.line(screen, (150, 130, 95), (px, py), (inner_right, py), 1)
        py += 12

        # ── Bộ chọn lính (khi đã chọn 1 node) ────────────────────────────
        self._pick_btns = {}
        self._send_rect = None
        if self._selected is not None:
            z = self._selected
            icon = load_resource_icon(z.resource_type, 20)
            head_y = py + 9
            if icon is not None:
                screen.blit(icon, icon.get_rect(midleft=(px, head_y)))
                text_x = px + 26
            else:
                text_x = px
            self._text(screen, "consolas", 14,
                       f"SEND PARTY -> {z.name} (dist {int(z.distance)})",
                       _INK_HEAD, topleft=(text_x, py), bold=True)
            py += 26
            for k in SOLDIER_KINDS:
                self._text(screen, "consolas", 13, f"{k:8s}",
                           _INK_DARK, topleft=(px, py + 3))
                minus = pygame.Rect(px + 88, py, 24, 22)
                plus = pygame.Rect(px + 176, py, 24, 22)
                for r, s in ((minus, "-"), (plus, "+")):
                    pygame.draw.rect(screen, (222, 200, 160), r, border_radius=3)
                    pygame.draw.rect(screen, (140, 105, 60), r, 1, border_radius=3)
                    self._text(screen, "consolas", 15, s, (70, 45, 20),
                               center=r.center, bold=True)
                    self._pick_btns[(k, s)] = r
                self._text(screen, "consolas", 14, str(self._pick[k]),
                           _INK_HEAD, center=(px + 150, py + 11), bold=True)
                py += 27
            # Nút Gửi.
            total = sum(self._pick.values())
            can = self.mgr.can_dispatch(self._pick)
            self._send_rect = pygame.Rect(px, py + 6, inner_right - px, 30)
            if can:
                bg, brdr, txt = (150, 190, 110), (70, 110, 45), (30, 55, 15)
            else:
                bg, brdr, txt = (198, 188, 168), (150, 140, 118), (130, 122, 105)
            pygame.draw.rect(screen, bg, self._send_rect, border_radius=4)
            pygame.draw.rect(screen, brdr, self._send_rect, 2, border_radius=4)
            self._text(screen, "consolas", 14, f"SEND ({total} soldiers)", txt,
                       center=self._send_rect.center, bold=True)
            py += 44
        else:
            self._text(screen, "consolas", 13,
                       "Select a node on the map to send a party.",
                       _INK_MUTED, topleft=(px, py))
            py += 24

        py += 6
        pygame.draw.line(screen, (150, 130, 95), (px, py), (inner_right, py), 1)
        py += 12

        # ── Danh sách đội đang đi + nút Retreat ──────────────────────────
        self._text(screen, "consolas", 15, "PARTIES OUT", _INK_HEAD,
                   topleft=(px, py), bold=True)
        py += 24
        self._party_rows = []
        if not self.mgr.parties:
            self._text(screen, "consolas", 13, "(none)", _INK_MUTED,
                       topleft=(px, py))
        for p in self.mgr.parties:
            icon = load_resource_icon(p.zone.resource_type, 18)
            comp = " ".join(f"{_KIND_ABBR[k]}{p.soldiers[k]}"
                            for k in SOLDIER_KINDS if p.soldiers[k] > 0)
            st = "" if p.state == STATE_LOOTING else f" [{p.state}]"
            row_x = px
            if icon is not None:
                screen.blit(icon, icon.get_rect(midleft=(px, py + 8)))
                row_x = px + 24
            self._text(screen, "consolas", 12,
                       f"{p.zone.name}: {comp} | loot {p.loot_amount()}{st}",
                       _INK_DARK, topleft=(row_x, py))
            btn = pygame.Rect(inner_right - 70, py - 2, 66, 20)
            enabled = p.state == STATE_LOOTING
            if enabled:
                bg, brdr, txt = (210, 175, 120), (150, 100, 55), (60, 35, 15)
            else:
                bg, brdr, txt = (200, 195, 180), (160, 155, 140), (140, 135, 122)
            pygame.draw.rect(screen, bg, btn, border_radius=3)
            pygame.draw.rect(screen, brdr, btn, 1, border_radius=3)
            self._text(screen, "consolas", 12, "Retreat", txt,
                       center=btn.center, bold=True)
            if enabled:
                self._party_rows.append((btn, p))
            py += 26

    # ------------------------------------------------------------------
    def _get_bg(self, w: int, h: int):
        """Nạp+scale `map.png` về `(w,h)`, cache CẤP CLASS theo key `(w,h)`
        (dùng chung mọi instance ResourceMapScreen — chỉ 1 background image
        active tại 1 thời điểm nên chia sẻ an toàn). Kích thước đổi (vd
        resize màn hình) → cache-miss, nạp lại. Lỗi tải → None (caller vẽ
        nền màu phẳng thay thế)."""
        key = (w, h)
        if ResourceMapScreen._bg_cache_key == key:
            return ResourceMapScreen._bg_cache
        surf = None
        try:
            raw = pygame.image.load(_MAP_PNG).convert_alpha()
            surf = pygame.transform.smoothscale(raw, (w, h))
        except (pygame.error, FileNotFoundError):
            surf = None
        ResourceMapScreen._bg_cache = surf
        ResourceMapScreen._bg_cache_key = key
        return surf

    @staticmethod
    def _text(screen, font_name, size, text, color, *, center=None,
              topleft=None, bold=False) -> None:
        """Vẽ 1 dòng text — neo bằng `center` HOẶC `topleft` (đúng 1 trong 2,
        caller quyết định qua đối số nào được truyền; `center` ưu tiên nếu
        cả 2 đều truyền, do kiểm tra `is not None` trước). Helper dùng lặp
        lại khắp overlay để tránh lặp code render font."""
        f = pygame.font.SysFont(font_name, size, bold=bold)
        surf = f.render(text, True, color)
        if center is not None:
            screen.blit(surf, surf.get_rect(center=center))
        else:
            screen.blit(surf, topleft)
