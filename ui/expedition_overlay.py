"""
expedition_overlay.py — Overlay TẦNG CAO cho hệ thống thám hiểm.

Ba lớp hiển thị, LUÔN vẽ ở tầng main-loop (độc lập với tab bản đồ — hiện cả
khi người chơi đã đóng tab thám hiểm):

    1. TITAN ALERT: banner giữa-trên màn (nền giấy da + ruy băng đỏ, cùng bộ
       nine_slice dùng ở Victory/Defeat/Shop), đếm ngược 10s, 2 nút
       [RETREAT] (bỏ đồ) / [FIGHT]. Hết giờ → DispatchManager tự auto-rút.
    2. PING COMBAT: vòng tròn + kim quay + vùng an toàn; SPACE lúc kim ở vùng
       an toàn = qua 1 lượt. Qua đủ N lượt = thắng; trượt 1 = thua.
    3. DEFEAT RESULT: banner ngắn (~3s, đóng sớm khi click/bấm phím) hiện sau
       khi thua 1 trận — cùng phong cách ruy băng đỏ như Victory/Defeat toàn
       màn (ui/combat_result.py), nhưng không chặn hẳn màn hình.

Chỉ là VIEW + input router: đọc trạng thái và gọi method của DispatchManager
(resolve_retreat / resolve_fight / combat_press / dismiss_result). Không giữ
game-state.

Vẽ vùng an toàn + kim bằng CÙNG công thức cos/sin (độ) như model để khớp tuyệt
đối với PingCombat._in_safe (không phụ thuộc hệ góc của pygame.draw.arc).
"""
from __future__ import annotations

import math

import pygame

from ui.nine_slice import draw_nine_slice, draw_ribbon_title, draw_button
from ui.resource_map_screen import load_resource_icon


class ExpeditionOverlay:
    """Router hiển thị/điều khiển cho encounter + combat của 1 DispatchManager."""

    def __init__(self, dispatch_mgr, screen_size=(1024, 768)) -> None:
        """Bọc lấy `dispatch_mgr` (thuần logic — module này chỉ ĐỌC trạng
        thái của nó và gọi method public để phản ứng input). `screen_size`
        khởi tạo tạm, `game.py` gọi `set_screen_size()` cập nhật khi
        resize/fullscreen thay đổi."""
        self.mgr = dispatch_mgr
        self._sw, self._sh = screen_size
        self._retreat_rect = None
        self._fight_rect = None

    def set_screen_size(self, w: int, h: int) -> None:
        """Cập nhật kích thước màn hình dùng để CĂN GIỮA mọi panel/overlay
        — gọi mỗi khi cửa sổ đổi kích thước."""
        self._sw, self._sh = w, h

    @property
    def is_active(self) -> bool:
        """True khi có alert/combat/defeat-banner đang hiện → game.py nuốt input khác."""
        return (self.mgr.active_combat is not None
                or self.mgr.current_encounter is not None
                or self.mgr.last_result is not None)

    # ------------------------------------------------------------------
    # Event
    # ------------------------------------------------------------------
    def handle_event(self, event) -> bool:
        """Router input MODAL — trả True nếu overlay đã "nuốt" sự kiện này
        (game.py PHẢI bỏ qua xử lý input khác khi True, tránh click xuyên
        qua overlay xuống UI bên dưới). Định tuyến theo trạng thái ưu tiên
        cao nhất trước:
          - Combat active: CHỈ nhận SPACE (đấm nút), mọi input khác vẫn bị
            NUỐT (modal cứng — không cho click/phím nào lọt qua).
          - Alert (gặp titan) đang mở: click vào `_retreat_rect`/`_fight_rect`
            gọi method tương ứng của manager; MỌI click khác trong lúc này
            cũng bị nuốt (modal).
          - Banner defeat: bất kỳ click/phím nào đóng sớm banner.
        Không có gì active (`is_active` False) → return False ngay, để input
        chảy xuống các hệ thống khác bình thường.
        """
        if not self.is_active:
            return False
        # Combat: chỉ nhận SPACE; nuốt mọi input khác (modal).
        if self.mgr.active_combat is not None:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                self.mgr.combat_press()
                return True
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                return True
            return False
        # Alert: click 2 nút.
        if self.mgr.current_encounter is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mp = event.pos if hasattr(event, "pos") else pygame.mouse.get_pos()
                if self._retreat_rect and self._retreat_rect.collidepoint(mp):
                    self.mgr.resolve_retreat()
                    return True
                if self._fight_rect and self._fight_rect.collidepoint(mp):
                    self.mgr.resolve_fight()
                    return True
                return True                  # nuốt mọi click khi alert mở
            return False
        # Defeat banner: bất kỳ click/phím nào đóng sớm.
        if self.mgr.last_result is not None:
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.mgr.dismiss_result()
                return True
            return False
        return False

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, screen) -> None:
        """Vẽ ĐÚNG 1 trong 3 lớp theo thứ tự ưu tiên (combat > alert >
        defeat-banner — khớp thứ tự kiểm tra trong `is_active`/`handle_event`),
        không active gì thì không vẽ gì. Bọc try/except NGẦM `(pygame.error,
        AttributeError)` — lỗi vẽ (vd font hệ thống thiếu) không được làm
        crash cả vòng lặp game, chỉ bỏ qua frame vẽ overlay đó."""
        try:
            if self.mgr.active_combat is not None:
                self._draw_combat(screen, self.mgr.active_combat)
            elif self.mgr.current_encounter is not None:
                self._draw_alert(screen, self.mgr.current_encounter)
            elif self.mgr.last_result is not None:
                self._draw_result(screen, self.mgr.last_result)
        except (pygame.error, AttributeError):
            pass

    def _draw_alert(self, screen, enc) -> None:
        """Vẽ banner "TITAN SIGHTED!" cho `enc` — panel 9-slice phong cách
        giấy da + ruy băng đỏ, hiện tên zone/khoảng cách/loot đang giữ, thời
        gian còn lại đếm ngược, số lượt combat DỰ KIẾN (`_combat_preview`,
        tính trước để người chơi cân nhắc trước khi bấm FIGHT), và 2 nút
        RETREAT/FIGHT — Rect của 2 nút được LƯU vào `self._retreat_rect`/
        `_fight_rect` để `handle_event()` dùng test click ở frame kế tiếp
        (decoupling: draw tính rect, event dùng lại — không tính 2 lần)."""
        self._retreat_rect = None
        self._fight_rect = None
        party = enc.party
        rounds, _, _ = _combat_preview(enc.difficulty)

        panel = pygame.Rect(0, 0, 620, 190)
        panel.centerx = self._sw // 2
        panel.top = int(self._sh * 0.08)
        draw_nine_slice(screen, panel, style="paper")
        title_font = pygame.font.SysFont("consolas", 24, bold=True)
        banner = draw_ribbon_title(screen, panel, "TITAN SIGHTED!", title_font,
                                   color="red")

        line1 = (f"Party at {party.zone.name} (distance {int(party.distance)}) "
                f"| loot held: {party.loot_amount()}")
        self._icon_text_row(screen, party.zone.resource_type, 22, line1,
                            (55, 45, 35), center=(panel.centerx, banner.bottom + 22))
        self._text(screen, 15,
                   f"Time left: {max(0.0, enc.timer):.0f}s   "
                   f"(fight: {rounds} rounds, 1 miss = defeat)",
                   (140, 60, 40), center=(panel.centerx, banner.bottom + 46))

        self._retreat_rect = pygame.Rect(0, 0, 230, 40)
        self._retreat_rect.midleft = (panel.left + 40, panel.bottom - 34)
        self._fight_rect = pygame.Rect(0, 0, 230, 40)
        self._fight_rect.midright = (panel.right - 40, panel.bottom - 34)
        mp = pygame.mouse.get_pos()
        btn_font = pygame.font.SysFont("consolas", 16, bold=True)
        draw_button(screen, self._retreat_rect, "RETREAT (abandon loot)",
                   style="red", font=btn_font,
                   hover=self._retreat_rect.collidepoint(mp))
        draw_button(screen, self._fight_rect, "FIGHT", style="blue", font=btn_font,
                   hover=self._fight_rect.collidepoint(mp))

    def _draw_result(self, screen, result: dict) -> None:
        """Vẽ banner "DEFEATED" ngắn (~3s tự đóng, hoặc đóng sớm qua
        `handle_event`) — hiện tên zone, danh sách lính đã MẤT (lọc `v > 0`
        khỏi `result['lost_soldiers']`), và lượng loot đã mất. `result` là
        dict snapshot từ `DispatchManager.last_result` (đã chốt tại thời
        điểm thua, không đọc lại state động)."""
        panel = pygame.Rect(0, 0, 480, 130)
        panel.centerx = self._sw // 2
        panel.top = int(self._sh * 0.10)
        draw_nine_slice(screen, panel, style="paper")
        title_font = pygame.font.SysFont("consolas", 24, bold=True)
        banner = draw_ribbon_title(screen, panel, "DEFEATED", title_font,
                                   color="red")

        lost_troops = ", ".join(f"{k} x{v}" for k, v in
                                result.get("lost_soldiers", {}).items() if v > 0)
        self._text(screen, 14,
                   f"Party at {result.get('zone_name', '?')} was wiped out.",
                   (55, 45, 35), center=(panel.centerx, banner.bottom + 20))
        line2 = f"Lost: {lost_troops or 'none'}  |  loot lost: {result.get('lost_loot', 0)}"
        self._icon_text_row(screen, result.get("resource_type", ""), 20, line2,
                            (140, 60, 40), center=(panel.centerx, banner.bottom + 44))

    def _draw_combat(self, screen, pc) -> None:
        """Vẽ minigame ping-combat: nền mờ modal phủ toàn màn hình, vòng
        tròn bán kính `R` (20% chiều nhỏ nhất màn hình), cung "vùng an
        toàn" tô XANH (polyline từng đoạn 2° dọc theo `pc.safe_start` →
        `pc.safe_start + pc.safe_arc` — CÙNG CÔNG THỨC cos/sin ĐỘ như
        `PingCombat._in_safe()` để vùng vẽ khớp TUYỆT ĐỐI với vùng logic,
        không lệch do khác quy ước góc của `pygame.draw.arc`), và kim quay
        (`pc.angle`) vẽ như 1 đường thẳng từ tâm ra viền + đầu kim tròn."""
        # Nền mờ (modal).
        ov = pygame.Surface((self._sw, self._sh), pygame.SRCALPHA)
        ov.fill((6, 8, 12, 200))
        screen.blit(ov, (0, 0))

        cx, cy = self._sw // 2, self._sh // 2
        R = int(min(self._sw, self._sh) * 0.20)

        pygame.draw.circle(screen, (58, 64, 78), (cx, cy), R, 3)
        # Vùng an toàn — polyline dày theo cùng công thức cos/sin (độ).
        pts = []
        a = pc.safe_start
        end = pc.safe_start + pc.safe_arc
        while a <= end:
            rad = math.radians(a)
            pts.append((cx + math.cos(rad) * R, cy + math.sin(rad) * R))
            a += 2.0
        if len(pts) >= 2:
            pygame.draw.lines(screen, (80, 225, 130), False, pts, 10)

        # Kim.
        rad = math.radians(pc.angle)
        tip = (cx + math.cos(rad) * R, cy + math.sin(rad) * R)
        pygame.draw.line(screen, (250, 230, 120), (cx, cy), tip, 4)
        pygame.draw.circle(screen, (250, 230, 120), (int(tip[0]), int(tip[1])), 7)
        pygame.draw.circle(screen, (200, 205, 215), (cx, cy), 6)

        self._text(screen, 24, "TITAN COMBAT", (240, 240, 245),
                   center=(cx, cy - R - 54), bold=True)
        self._text(screen, 18,
                   f"Round {pc.rounds_done + 1}/{pc.rounds_total}",
                   (250, 220, 150), center=(cx, cy - R - 26), bold=True)
        self._text(screen, 16, "Press SPACE when the needle is in the GREEN zone",
                   (200, 210, 220), center=(cx, cy + R + 30))

    # ------------------------------------------------------------------
    def _icon_text_row(self, screen, resource_type, icon_size, text, color,
                       *, center) -> None:
        """Vẽ [icon] + text như 1 khối NGANG cân giữa tại `center` (đo chữ
        trước để icon KHÔNG đè lên chữ, dù text dài ngắn khác nhau)."""
        f = pygame.font.SysFont("consolas", 15)
        text_surf = f.render(text, True, color)
        icon = load_resource_icon(resource_type, icon_size)
        gap = 8
        icon_w = icon.get_width() if icon is not None else 0
        total_w = icon_w + (gap if icon is not None else 0) + text_surf.get_width()
        x = center[0] - total_w // 2
        y = center[1]
        if icon is not None:
            screen.blit(icon, icon.get_rect(midleft=(x, y)))
            x += icon_w + gap
        screen.blit(text_surf, text_surf.get_rect(midleft=(x, y)))

    def _text(self, screen, size, text, color, *, center, bold=False) -> None:
        """Vẽ 1 dòng text đơn giản (không đổ bóng, không icon), CĂN GIỮA
        tại `center` — helper dùng lặp lại khắp overlay cho label/mô tả."""
        f = pygame.font.SysFont("consolas", size, bold=bold)
        surf = f.render(text, True, color)
        screen.blit(surf, surf.get_rect(center=center))


def _combat_preview(difficulty: float) -> tuple:
    """Số lượt/vùng/tốc dự kiến (để hiện ở banner) — dùng chung công thức model."""
    from systems.dispatch_system import combat_params
    return combat_params(difficulty)
