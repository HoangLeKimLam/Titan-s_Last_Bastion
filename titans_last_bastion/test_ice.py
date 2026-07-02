import pygame
import sys
import os
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Mocks phải đặt TRƯỚC khi import tower ──────────────────────────────────

class MockWorldQuery:
    entities = []

    @classmethod
    def spawn_entity(cls, entity):
        cls.entities.append(entity)

    @classmethod
    def find_in_radius(cls, cx, cy, radius, entity_type):
        from core.entity import Entity
        return [e for e in cls.entities if hasattr(e, '_vx')]  # là MockTitan


class MockResourceManager:
    _inst = None
    @classmethod
    def get_instance(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst
    def can_afford(self, cost): return True
    def spend(self, cost): pass
    def earn(self, bundle): pass


class MockResourceBundle:
    """Chấp nhận mọi keyword — dùng để test upgrade mà không cần game_state thật."""
    def __init__(self, **kwargs): self._d = kwargs
    def __ge__(self, other): return True
    def __add__(self, other): return self
    def __mul__(self, scalar): return self


class MockEventBus:
    _inst = None
    @classmethod
    def get_instance(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst
    def publish(self, event, data): pass
    def subscribe(self, event, cb): pass


# systems.world_query
_wq = types.ModuleType('systems.world_query')
_wq.WorldQuery = MockWorldQuery
sys.modules.setdefault('systems', types.ModuleType('systems'))
sys.modules['systems.world_query'] = _wq

# structures.buildings.resource_manager — chỉ mock leaf, KHÔNG mock 'structures'
_rm = types.ModuleType('structures.buildings.resource_manager')
_rm.ResourceManager = MockResourceManager
sys.modules.setdefault('structures.buildings', types.ModuleType('structures.buildings'))
sys.modules['structures.buildings.resource_manager'] = _rm

# core.game_state → MockResourceBundle (tránh fail khi dùng ore field lạ)
import core.game_state as _gs
_gs.ResourceBundle = MockResourceBundle

# core.event_bus
import core.event_bus as _eb
_eb.GameEventBus = MockEventBus

# ── Import sau khi mock xong ────────────────────────────────────────────────

from core.entity import Entity
from structures.towers.visual_effects import load_spritesheet, TransientEffect


class MockTitan(Entity):
    def __init__(self, x, y):
        super().__init__(x, y)
        self.is_alive  = True
        self._vx       = -60.0
        self._vy       = 0.0
        self._kb_vx    = 0.0
        self._kb_vy    = 0.0
        self._kb_timer = 0.0
        self._kb_dur   = 0.0

    def update(self, dt):
        if self._kb_timer > 0:
            t = self._kb_timer / self._kb_dur if self._kb_dur > 0 else 0
            self.x += self._kb_vx * t * dt
            self.y += self._kb_vy * t * dt
            self._kb_timer -= dt
        else:
            self.x += self._vx * dt
            self.y += self._vy * dt

    def draw(self, screen):
        pygame.draw.circle(screen, (200, 0, 0), (int(self.x), int(self.y)), 20)

    def take_damage(self, dmg, dtype): pass
    def apply_slow(self, factor, dur): pass
    def apply_knockback(self, vx, vy, dur):
        self._kb_vx = vx; self._kb_vy = vy
        self._kb_timer = dur; self._kb_dur = dur


def _tower_stats(tower) -> list[str]:
    """Trả về danh sách dòng stats để hiển thị."""
    lines = [
        f"Level : {tower._level} / {tower.MAX_LEVEL}",
        f"Damage: {tower._damage}",
    ]
    if hasattr(tower, '_chain_damage'):
        lines.append(f"Chain dmg : {tower._chain_damage}")
        lines.append(f"Chain range: {tower._chain_range:.0f}px")
    if hasattr(tower, '_push_radius'):
        lines.append(f"Push radius: {tower._push_radius}px")
    if hasattr(tower, '_slow_duration'):
        lines.append(f"Slow dur : {tower._slow_duration:.1f}s")
        lines.append(f"Slow factor: {tower._slow_factor:.2f}")
        lines.append(f"Splash r   : {tower._splash_radius}px")
    if hasattr(tower, '_upgrade_ready'):
        if tower._upgrade_ready and tower._level < tower.MAX_LEVEL:
            lines.append(">> Sẵn sàng: cần fire_ore (U)")
        elif tower._level < tower.MAX_LEVEL:
            lines.append(f"Orb cần: {tower.ORB_FIELD}  (U để nạp)")
    else:
        if tower._level < tower.MAX_LEVEL:
            lines.append(f"Orb cần: {tower.ORB_FIELD}  (U để nạp)")
        else:
            lines.append("** MAX LEVEL **")
    return lines


def main():
    pygame.init()
    screen = pygame.display.set_mode((950, 600))
    pygame.display.set_caption("Test Towers — Upgrade Simulation")
    clock = pygame.time.Clock()

    from structures.towers.tower import BasicTower, ElectricTower, WaterTower, IceTower

    tower_pos = (200, 350)
    towers = [
        BasicTower(*tower_pos),
        ElectricTower(*tower_pos),
        WaterTower(*tower_pos),
        IceTower(*tower_pos),
    ]
    tower_names = ["Basic Tower", "Electric Tower", "Water Tower", "Ice Tower"]
    current_tower_idx = 0

    target  = MockTitan(680, 350)
    target2 = MockTitan(720, 390)
    MockWorldQuery.entities += [target, target2]

    font   = pygame.font.SysFont(None, 22)
    font_b = pygame.font.SysFont(None, 24)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if   event.key == pygame.K_1: current_tower_idx = 0
                elif event.key == pygame.K_2: current_tower_idx = 1
                elif event.key == pygame.K_3: current_tower_idx = 2
                elif event.key == pygame.K_4: current_tower_idx = 3
                elif event.key == pygame.K_ESCAPE: running = False
                elif event.key == pygame.K_u:
                    towers[current_tower_idx].apply_orb(1)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pygame.mouse.get_pos()
                target.x, target.y   = mx, my
                target.is_alive       = True
                target2.x, target2.y  = mx + 40, my + 40
                target2.is_alive      = True
                if not any(hasattr(e, '_vx') for e in MockWorldQuery.entities):
                    MockWorldQuery.entities += [target, target2]

        screen.fill((30, 30, 40))

        # Tower
        active = towers[current_tower_idx]
        active.update(dt)
        active.draw(screen)

        # Entities
        for e in MockWorldQuery.entities:
            e.update(dt)
            e.draw(screen)
        MockWorldQuery.entities = [e for e in MockWorldQuery.entities if e.is_alive]

        if not any(hasattr(e, '_vx') for e in MockWorldQuery.entities):
            target.is_alive = True; target.x, target.y = 680, 350
            target2.is_alive = True; target2.x, target2.y = 720, 390
            MockWorldQuery.entities += [target, target2]

        # ── UI panel bên phải ─────────────────────────────────────────
        panel_x = 700
        pygame.draw.line(screen, (60, 60, 80), (panel_x - 10, 0), (panel_x - 10, 600), 1)

        # Tên tower
        name_surf = font_b.render(f"[{current_tower_idx+1}] {tower_names[current_tower_idx]}", True, (255, 220, 80))
        screen.blit(name_surf, (panel_x, 10))

        # Stats
        for i, line in enumerate(_tower_stats(active)):
            col = (255, 180, 60) if ">>" in line or "MAX" in line else (200, 220, 255)
            screen.blit(font.render(line, True, col), (panel_x, 40 + i * 22))

        # Hướng dẫn
        hints = [
            "1-4 : chọn tháp",
            "U   : nạp 1 orb",
            "LClick: di chuyển titan",
        ]
        for i, h in enumerate(hints):
            screen.blit(font.render(h, True, (140, 140, 140)), (panel_x, 400 + i * 22))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
