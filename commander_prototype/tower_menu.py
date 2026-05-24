"""tower_menu.py — screen-space overlay for editing a Tower's garrison/waves.

When the player LMB-clicks a Tower in the world, `main.py` opens a `TowerMenu`
pointing at that tower. The menu sits on the screen (not in world space) and
captures LMB clicks while it is open. It has two interactive sections:

    [ +/- ] count rows for each soldier type (Warrior, Lancer, Archer)
            — the +/− buttons call `Tower.adjust_garrison(...)`, which already
              clamps to `CAPACITY`.

    [ Wave 1 ] [ Wave 2 ] [ Wave 3 ]
            — three clickable badges that show the current type for that wave
              slot; clicking cycles W → L → A → W via `Tower.cycle_wave_slot`.

The menu is intentionally dumb: it never owns game state, only forwards user
intent to the tower. `handle_event(event)` returns True when it has consumed
the event (used by main.py to suppress basic-attack on that click). Clicking
outside the panel closes the menu and returns False.
"""
from __future__ import annotations

import pygame

from soldier import SOLDIER_TYPES
from tower import Tower


_ROW_TYPES: tuple = ("Warrior", "Lancer", "Archer")
_TYPE_COLORS: dict = {
    "Warrior": (210, 140, 80),
    "Lancer":  (110, 150, 235),
    "Archer":  (90, 200, 120),
}


class TowerMenu:
    """Screen-space overlay editing a single Tower."""

    PANEL_W: int = 360
    PANEL_H: int = 260

    def __init__(self, tower: Tower, screen_size: tuple = (960, 600)) -> None:
        self.tower = tower
        self._screen_w, self._screen_h = screen_size
        self._closed: bool = False
        self._rebuild_rects()
        # Surface the aggro ring while the menu is open.
        self.tower._highlight_aggro = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return not self._closed

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.tower._highlight_aggro = False

    def handle_event(self, event) -> bool:
        """Return True if the event was consumed (suppress fall-through)."""
        if self._closed:
            return False
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        mpos = event.pos if hasattr(event, "pos") else pygame.mouse.get_pos()

        if not self._panel_rect.collidepoint(mpos):
            # Clicked outside → close, but still consume so the click doesn't
            # trigger a basic_attack underneath the (now invisible) panel.
            self.close()
            return True

        if self._close_rect.collidepoint(mpos):
            self.close()
            return True

        for t, (minus, plus) in self._row_rects.items():
            if minus.collidepoint(mpos):
                self.tower.adjust_garrison(t, -1)
                return True
            if plus.collidepoint(mpos):
                self.tower.adjust_garrison(t, +1)
                return True

        for i, rect in enumerate(self._wave_rects):
            if rect.collidepoint(mpos):
                self.tower.cycle_wave_slot(i)
                return True

        # Inside panel but on a non-interactive area — still consume so the
        # click doesn't pass through to basic_attack.
        return True

    def draw(self, screen) -> None:
        if self._closed:
            return
        try:
            self._draw_panel(screen)
        except (AttributeError, pygame.error):
            pass

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _rebuild_rects(self) -> None:
        px = (self._screen_w - self.PANEL_W) // 2
        py = (self._screen_h - self.PANEL_H) // 2
        self._panel_rect = pygame.Rect(px, py, self.PANEL_W, self.PANEL_H)
        self._close_rect = pygame.Rect(px + self.PANEL_W - 28, py + 6, 22, 22)

        # Count rows: 3 stacked rows for W/L/A.
        self._row_rects: dict = {}
        row_y0 = py + 50
        row_h = 36
        for i, t in enumerate(_ROW_TYPES):
            ry = row_y0 + i * row_h
            minus = pygame.Rect(px + 220, ry + 4, 28, 26)
            plus = pygame.Rect(px + 296, ry + 4, 28, 26)
            self._row_rects[t] = (minus, plus)

        # Wave slot badges (3 boxes) below the rows.
        wave_y = row_y0 + len(_ROW_TYPES) * row_h + 26
        gap = 12
        bw = (self.PANEL_W - 2 * 18 - 2 * gap) // 3
        self._wave_rects: list = []
        for i in range(3):
            wx = px + 18 + i * (bw + gap)
            self._wave_rects.append(pygame.Rect(wx, wave_y, bw, 36))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_panel(self, screen) -> None:
        # Backdrop (semi-transparent) so the world is still hinted at behind.
        overlay = pygame.Surface((self._screen_w, self._screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        screen.blit(overlay, (0, 0))

        pygame.draw.rect(screen, (28, 32, 40), self._panel_rect)
        pygame.draw.rect(screen, (140, 150, 175), self._panel_rect, 2)

        title_font = pygame.font.SysFont("consolas", 18, bold=True)
        body_font = pygame.font.SysFont("consolas", 15)
        small_font = pygame.font.SysFont("consolas", 12)

        # Title bar.
        title = title_font.render("Tower garrison", True, (235, 235, 235))
        screen.blit(title, (self._panel_rect.left + 14, self._panel_rect.top + 8))
        cap_txt = body_font.render(
            f"Total: {self.tower.total_garrison()}/{self.tower.CAPACITY}",
            True, (200, 220, 255),
        )
        screen.blit(cap_txt, (self._panel_rect.left + 14,
                              self._panel_rect.top + 30))

        # Close button.
        pygame.draw.rect(screen, (90, 30, 30), self._close_rect)
        pygame.draw.rect(screen, (200, 80, 80), self._close_rect, 1)
        x_label = body_font.render("x", True, (240, 240, 240))
        screen.blit(x_label, x_label.get_rect(center=self._close_rect.center))

        # Garrison rows.
        for t, (minus, plus) in self._row_rects.items():
            count = self.tower.garrison.get(t, 0)
            color = _TYPE_COLORS.get(t, (220, 220, 220))
            row_y = minus.top
            type_label = body_font.render(t, True, color)
            screen.blit(type_label, (self._panel_rect.left + 18, row_y + 4))
            count_label = body_font.render(str(count), True, (235, 235, 235))
            screen.blit(count_label,
                        count_label.get_rect(midleft=(self._panel_rect.left + 170,
                                                      row_y + 16)))
            for rect, sign in ((minus, "-"), (plus, "+")):
                pygame.draw.rect(screen, (60, 64, 78), rect)
                pygame.draw.rect(screen, color, rect, 1)
                lbl = body_font.render(sign, True, (235, 235, 235))
                screen.blit(lbl, lbl.get_rect(center=rect.center))

        # Wave row label.
        wave_label = body_font.render("Wave order (click to cycle):",
                                       True, (220, 220, 220))
        screen.blit(wave_label, (self._panel_rect.left + 14,
                                  self._wave_rects[0].top - 22))
        for i, rect in enumerate(self._wave_rects):
            t = self.tower.wave_order[i] if i < len(self.tower.wave_order) else "?"
            color = _TYPE_COLORS.get(t, (220, 220, 220))
            pygame.draw.rect(screen, (40, 44, 56), rect)
            pygame.draw.rect(screen, color, rect, 2)
            n_lbl = small_font.render(f"Wave {i + 1}", True, (200, 200, 200))
            screen.blit(n_lbl, (rect.left + 6, rect.top + 4))
            t_lbl = body_font.render(t, True, color)
            screen.blit(t_lbl, t_lbl.get_rect(center=(rect.centerx,
                                                     rect.centery + 6)))

        # Aggro hint at bottom of panel.
        hint = small_font.render(
            f"Aggro radius: {int(self.tower.AGGRO_RADIUS)} px  "
            f"|  Up to {self.tower.MAX_WAVES_PER_EVENT} waves / event",
            True, (180, 200, 230),
        )
        screen.blit(hint, (self._panel_rect.left + 14,
                          self._panel_rect.bottom - 22))


def open_menu_at(tower: Tower, screen_size: tuple) -> TowerMenu:
    """Helper used by main.py."""
    return TowerMenu(tower, screen_size=screen_size)
