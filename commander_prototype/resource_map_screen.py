"""resource_map_screen.py — full-screen strategic mini-map overlay (pygame).

Press M in `main.py` to toggle this overlay. It renders the symbolic mini-map
(a grid of cells) with each `ResourceZone` drawn as an icon, plus a side panel
(team pool, exploration level + upgrade button, active jobs with progress bars)
and a bottom action panel for the currently selected zone.

It owns NO game state — every click forwards intent to `MapState`
(`start_explore`, `start_mine`, `upgrade`). Mirrors the `TowerMenu` pattern:
`handle_event(event) -> bool` returns True when it consumes a click so main.py
suppresses the commander's basic-attack underneath. All rendered text is ASCII
(SysFont can't render Vietnamese diacritics reliably).
"""
from __future__ import annotations

import pygame

from resource_map import MapState, ZONE_RESOURCE

_KIND_COLOR: dict = {
    "forest": (90, 200, 120),
    "cave":   (150, 150, 170),
    "item":   (245, 220, 90),
}
_MINE_STEP: int = 10


class ResourceMapScreen:
    """Screen-space strategic map overlay driven by a `MapState`."""

    # Map grid panel (left) + side panel (right) + action bar (bottom).
    MAP_X, MAP_Y, MAP_W, MAP_H = 20, 56, 616, 416
    PANEL_X, PANEL_W = 648, 292
    ACTION_H = 92

    def __init__(self, map_state: MapState, screen_size: tuple = (960, 600)) -> None:
        self.map_state = map_state
        self._screen_w, self._screen_h = screen_size
        self._closed: bool = False
        self._selected = None            # selected ResourceZone (or None)
        self._mine_amount: int = _MINE_STEP
        self._build_rects()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return not self._closed

    def close(self) -> None:
        self._closed = True

    def handle_event(self, event) -> bool:
        """Consume LMB clicks while open. Returns True if the event was used."""
        if self._closed:
            return False
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        mpos = event.pos if hasattr(event, "pos") else pygame.mouse.get_pos()

        if self._close_rect.collidepoint(mpos):
            self.close()
            return True

        # Upgrade exploration ability.
        if self._upgrade_rect.collidepoint(mpos):
            self.map_state.upgrade()
            return True

        # Action buttons for the selected zone.
        z = self._selected
        if z is not None and z in self.map_state.zones:
            if (not z.is_item) and z.unlocked:
                if self._minus_rect.collidepoint(mpos):
                    self._mine_amount = max(1, self._mine_amount - _MINE_STEP)
                    return True
                if self._plus_rect.collidepoint(mpos):
                    cap = max(1, z.reserve)
                    self._mine_amount = min(cap, self._mine_amount + _MINE_STEP)
                    return True
                if self._action_rect.collidepoint(mpos):
                    amt = min(self._mine_amount, z.reserve)
                    self.map_state.start_mine(z, amt)
                    return True
            else:
                if self._action_rect.collidepoint(mpos):
                    self.map_state.start_explore(z)
                    return True

        # Select a zone by clicking its icon.
        for zone in self.map_state.zones:
            cx, cy = self._cell_center(zone)
            if (mpos[0] - cx) ** 2 + (mpos[1] - cy) ** 2 <= 26 * 26:
                self._selected = zone
                if (not zone.is_item) and zone.unlocked:
                    self._mine_amount = min(_MINE_STEP, max(1, zone.reserve))
                return True

        # Click on empty map area → deselect, but still consume (modal screen).
        self._selected = None
        return True

    def draw(self, screen) -> None:
        if self._closed:
            return
        try:
            self._draw(screen)
        except (AttributeError, pygame.error):
            pass

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_rects(self) -> None:
        self._map_rect = pygame.Rect(self.MAP_X, self.MAP_Y, self.MAP_W, self.MAP_H)
        self._panel_rect = pygame.Rect(self.PANEL_X, self.MAP_Y, self.PANEL_W,
                                       self.MAP_H + self.ACTION_H + 4)
        self._close_rect = pygame.Rect(self._screen_w - 30, 6, 24, 24)
        self._upgrade_rect = pygame.Rect(self.PANEL_X + 12, self.MAP_Y + 96,
                                         self.PANEL_W - 24, 30)
        # Bottom action bar.
        ay = self.MAP_Y + self.MAP_H + 4
        self._action_bar = pygame.Rect(self.MAP_X, ay, self.MAP_W, self.ACTION_H)
        self._minus_rect = pygame.Rect(self.MAP_X + 150, ay + 44, 30, 28)
        self._plus_rect = pygame.Rect(self.MAP_X + 250, ay + 44, 30, 28)
        self._action_rect = pygame.Rect(self.MAP_X + 320, ay + 40, 260, 36)

    def _cell_center(self, zone) -> tuple:
        cw = self.MAP_W / self.map_state.GRID_COLS
        ch = self.MAP_H / self.map_state.GRID_ROWS
        cx = self.MAP_X + (zone.gx + 0.5) * cw
        cy = self.MAP_Y + (zone.gy + 0.5) * ch
        return (int(cx), int(cy))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self, screen) -> None:
        overlay = pygame.Surface((self._screen_w, self._screen_h), pygame.SRCALPHA)
        overlay.fill((6, 10, 16, 220))
        screen.blit(overlay, (0, 0))

        title_font = pygame.font.SysFont("consolas", 20, bold=True)
        screen.blit(title_font.render("MINI-MAP  —  Thu thap tai nguyen", True,
                                      (235, 235, 235)), (self.MAP_X, 18))

        self._draw_grid(screen)
        for zone in self.map_state.zones:
            self._draw_zone(screen, zone)
        self._draw_side_panel(screen)
        self._draw_action_bar(screen)

        # Close button.
        pygame.draw.rect(screen, (90, 30, 30), self._close_rect)
        pygame.draw.rect(screen, (200, 80, 80), self._close_rect, 1)
        xf = pygame.font.SysFont("consolas", 16, bold=True)
        screen.blit(xf.render("x", True, (240, 240, 240)),
                    xf.render("x", True, (240, 240, 240)).get_rect(
                        center=self._close_rect.center))

    def _draw_grid(self, screen) -> None:
        pygame.draw.rect(screen, (26, 38, 30), self._map_rect)
        pygame.draw.rect(screen, (80, 110, 90), self._map_rect, 2)
        cw = self.MAP_W / self.map_state.GRID_COLS
        ch = self.MAP_H / self.map_state.GRID_ROWS
        for c in range(1, self.map_state.GRID_COLS):
            x = int(self.MAP_X + c * cw)
            pygame.draw.line(screen, (40, 56, 46), (x, self.MAP_Y),
                             (x, self.MAP_Y + self.MAP_H), 1)
        for r in range(1, self.map_state.GRID_ROWS):
            y = int(self.MAP_Y + r * ch)
            pygame.draw.line(screen, (40, 56, 46), (self.MAP_X, y),
                             (self.MAP_X + self.MAP_W, y), 1)

    def _draw_zone(self, screen, zone) -> None:
        cx, cy = self._cell_center(zone)
        small = pygame.font.SysFont("consolas", 11)
        locked = (not zone.is_item) and (not zone.unlocked)
        base_col = _KIND_COLOR.get(zone.kind, (200, 200, 200))
        col = tuple(c // 2 for c in base_col) if locked else base_col

        if zone.kind == "forest":
            pygame.draw.polygon(screen, col, [(cx, cy - 18), (cx - 15, cy + 10),
                                              (cx + 15, cy + 10)])
            pygame.draw.rect(screen, (110, 80, 50), (cx - 3, cy + 10, 6, 8))
        elif zone.kind == "cave":
            pygame.draw.circle(screen, col, (cx, cy + 4), 16)
            pygame.draw.rect(screen, (20, 20, 26), (cx - 7, cy + 4, 14, 14))
        else:  # item
            pygame.draw.polygon(screen, col, [(cx, cy - 16), (cx + 12, cy),
                                              (cx, cy + 16), (cx - 12, cy)])

        # Selection highlight.
        if zone is self._selected:
            pygame.draw.circle(screen, (255, 235, 120), (cx, cy), 28, 2)

        # Lock badge / reserve label.
        if locked:
            screen.blit(small.render("? LOCK", True, (210, 180, 90)),
                        small.render("? LOCK", True, (210, 180, 90)).get_rect(
                            center=(cx, cy + 26)))
        elif zone.kind in ZONE_RESOURCE:
            tag = f"{zone.reserve}" if zone.reserve > 0 else "het"
            screen.blit(small.render(tag, True, (220, 230, 220)),
                        small.render(tag, True, (220, 230, 220)).get_rect(
                            center=(cx, cy + 26)))
        else:
            screen.blit(small.render("ITEM", True, (245, 225, 120)),
                        small.render("ITEM", True, (245, 225, 120)).get_rect(
                            center=(cx, cy + 26)))

        # Active-job progress ring under the icon.
        job = self.map_state.job_for(zone)
        if job is not None:
            bar = pygame.Rect(cx - 22, cy + 32, 44, 5)
            pygame.draw.rect(screen, (40, 40, 48), bar)
            pygame.draw.rect(screen, (250, 210, 90),
                             (bar.left, bar.top, int(bar.width * job.progress), 5))

    def _draw_side_panel(self, screen) -> None:
        body = pygame.font.SysFont("consolas", 14)
        small = pygame.font.SysFont("consolas", 12)
        pygame.draw.rect(screen, (22, 26, 34), self._panel_rect)
        pygame.draw.rect(screen, (90, 110, 140), self._panel_rect, 2)
        px = self._panel_rect.left + 12
        py = self._panel_rect.top + 10

        ms = self.map_state
        screen.blit(body.render(f"Doi: {ms.teams_busy}/{ms.TEAMS_TOTAL} dang di",
                                True, (220, 230, 255)), (px, py))
        screen.blit(body.render(f"Kha nang tham hiem: Lv {ms.exploration_level}",
                                True, (220, 230, 255)), (px, py + 22))

        # Upgrade button.
        at_max = ms.exploration_level >= ms.MAX_EXPLORATION_LEVEL
        cost = ms.get_upgrade_cost()
        if at_max:
            label, col = "Tham hiem: MAX", (120, 130, 140)
        else:
            label = f"Nang cap [{self._fmt_bundle(cost)}]"
            col = (90, 180, 120)
        pygame.draw.rect(screen, (34, 44, 40), self._upgrade_rect)
        pygame.draw.rect(screen, col, self._upgrade_rect, 2)
        screen.blit(small.render(label, True, col),
                    small.render(label, True, col).get_rect(
                        center=self._upgrade_rect.center))

        # Active jobs list with progress bars.
        jy = self._upgrade_rect.bottom + 16
        screen.blit(body.render("Dang thuc hien:", True, (210, 210, 210)), (px, jy))
        jy += 22
        if not ms.jobs:
            screen.blit(small.render("(khong co)", True, (150, 150, 150)), (px, jy))
        for job in ms.jobs:
            kind = "Tham hiem" if job.kind == "explore" else f"Khai thac {job.amount}"
            screen.blit(small.render(f"{kind} - {job.zone.name}", True,
                                     (220, 220, 220)), (px, jy))
            bar = pygame.Rect(px, jy + 16, self._panel_rect.width - 24, 6)
            pygame.draw.rect(screen, (40, 40, 48), bar)
            pygame.draw.rect(screen, (250, 210, 90),
                             (bar.left, bar.top, int(bar.width * job.progress), 6))
            jy += 32

    def _draw_action_bar(self, screen) -> None:
        body = pygame.font.SysFont("consolas", 15)
        small = pygame.font.SysFont("consolas", 12)
        pygame.draw.rect(screen, (22, 26, 34), self._action_bar)
        pygame.draw.rect(screen, (90, 110, 140), self._action_bar, 2)
        ax = self._action_bar.left + 12
        ay = self._action_bar.top + 8

        z = self._selected
        if z is None or z not in self.map_state.zones:
            screen.blit(small.render("Chon mot khu tren ban do de thao tac.",
                                     True, (180, 180, 190)), (ax, ay + 28))
            return

        free = self.map_state.has_free_team()
        busy = self.map_state.job_for(z) is not None   # a job already on this zone
        screen.blit(body.render(z.name, True, (235, 235, 235)), (ax, ay))

        if (not z.is_item) and z.unlocked:
            # Mining quantity selector + dispatch button.
            screen.blit(small.render(f"Tru luong: {z.reserve}  |  So luong:",
                                     True, (210, 220, 210)), (ax, ay + 24))
            for rect, sign in ((self._minus_rect, "-"), (self._plus_rect, "+")):
                pygame.draw.rect(screen, (60, 64, 78), rect)
                pygame.draw.rect(screen, (150, 170, 150), rect, 1)
                screen.blit(body.render(sign, True, (235, 235, 235)),
                            body.render(sign, True, (235, 235, 235)).get_rect(
                                center=rect.center))
            amt = min(self._mine_amount, max(0, z.reserve))
            screen.blit(body.render(str(amt), True, (245, 245, 200)),
                        body.render(str(amt), True, (245, 245, 200)).get_rect(
                            center=(self._minus_rect.right + 35,
                                    self._minus_rect.centery)))
            secs = self.map_state.mine_time(amt)
            label = "Dang khai thac..." if busy else f"Khai thac {amt} ({secs:.1f}s)"
            self._draw_button(screen, self._action_rect, label,
                              enabled=free and z.reserve > 0 and not busy)
        else:
            # Explore (locked zone) / collect (item).
            verb = "Tham hiem & thu thap" if z.is_item else "Tham hiem mo khoa"
            secs = self.map_state.explore_time(z)
            screen.blit(small.render("Can cu 1 doi tham hiem.", True,
                                     (210, 220, 210)), (ax, ay + 24))
            label = "Dang tham hiem..." if busy else f"{verb} ({secs:.1f}s)"
            self._draw_button(screen, self._action_rect, label,
                              enabled=free and not busy)

    def _draw_button(self, screen, rect, label, *, enabled: bool) -> None:
        body = pygame.font.SysFont("consolas", 14, bold=True)
        col = (90, 180, 120) if enabled else (90, 96, 104)
        pygame.draw.rect(screen, (30, 40, 36), rect)
        pygame.draw.rect(screen, col, rect, 2)
        screen.blit(body.render(label, True, col),
                    body.render(label, True, col).get_rect(center=rect.center))

    @staticmethod
    def _fmt_bundle(bundle) -> str:
        parts = [f"{k}{v}" for k, v in bundle.to_dict().items() if v > 0]
        return " ".join(parts) if parts else "free"
