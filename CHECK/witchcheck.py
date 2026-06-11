"""witchcheck.py — Demo thủ công cho Witch + Cursed.

Phím:
  WASD          — di chuyển Witch manual (khi AUTO off)
  SPACE         — cast Cursed x10 toàn map
  T             — toggle AUTO mode (Witch tự đứng cast khi còn phòng thủ)
  N             — spawn thêm 1 Soldier
  R             — respawn Witch + world
  Q / ESC       — thoát
"""
import os
import random
import sys
import types

import pygame


# CHECK/ → root để import Titan.py, AttackStrategy.py.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _mod(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


class _MockEntity:
    _next_id = 1

    def __init__(self, x: float, y: float) -> None:
        self.id = _MockEntity._next_id
        _MockEntity._next_id += 1
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen) -> None:
        pass


class _MockBus:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def publish(self, event: str, data: dict = None) -> None:
        print(f"[EventBus] {event}")

    def subscribe(self, *_args, **_kwargs) -> None:
        pass


class _MockWorldQuery:
    soldiers: list = []
    commanders: list = []
    towers: list = []

    @classmethod
    def _pool_for(cls, entity_type: str) -> list:
        return {
            'soldier': cls.soldiers,
            'commander': cls.commanders,
            'tower': cls.towers,
        }.get(entity_type, [])

    @classmethod
    def find_in_radius(cls, cx: float, cy: float,
                       radius: float, entity_type: str) -> list:
        pool = cls._pool_for(entity_type)
        r2 = radius * radius
        out = []
        for e in pool:
            if not getattr(e, 'is_alive', False):
                continue
            dx = e.x - cx
            dy = e.y - cy
            if dx * dx + dy * dy <= r2:
                out.append(e)
        return out

    @classmethod
    def find_nearest(cls, cx: float, cy: float, entity_type: str):
        pool = cls._pool_for(entity_type)
        alive = [e for e in pool if getattr(e, 'is_alive', False)]
        if not alive:
            return None
        return min(alive, key=lambda e: (e.x - cx) ** 2 + (e.y - cy) ** 2)

    @classmethod
    def get_headquarters(cls):
        return None

    @classmethod
    def can_reach_direct(cls, *_args, **_kwargs) -> bool:
        return True

    @classmethod
    def find_blocking_wall(cls, *_args, **_kwargs):
        return None

    @classmethod
    def find_nearest_attacker(cls, *_args, **_kwargs):
        return None


# core.* mocks
_mod('core')
_mod('core.entity').Entity = _MockEntity
iface = _mod('core.interfaces')
iface.IAttackable = type('IAttackable', (), {})
iface.IMovable = type('IMovable', (), {})
_mod('core.event_bus').GameEventBus = _MockBus

# systems.* mocks
_mod('systems')
_mod('systems.world_query').WorldQuery = _MockWorldQuery

# characters.titans.attackstrategy mirrors AttackStrategy.py thật.
_mod('characters')
_mod('characters.titans')
import AttackStrategy as _atk_src  # noqa: E402
strat_mod = _mod('characters.titans.attackstrategy')
for _name in dir(_atk_src):
    if not _name.startswith('_'):
        setattr(strat_mod, _name, getattr(_atk_src, _name))

from Titan import Witch  # noqa: E402
from _demo_dummies import spawn_world, draw_all, update_all, SoldierDummy  # noqa: E402


W, H = 1040, 720
FPS = 60


def make_witch() -> Witch:
    return Witch(150.0, H / 2, {
        'hp': 1200, 'speed': 55.0, 'damage': 45,
    })


def sync_world() -> None:
    _MockWorldQuery.soldiers = soldiers
    _MockWorldQuery.commanders = heroes
    _MockWorldQuery.towers = towers


pygame.init()
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "Witch Demo  (WASD=move  SPACE=Cursed  T=auto  N=+soldier  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font = pygame.font.SysFont('Consolas', 15)

witch = make_witch()
soldiers, heroes, towers = spawn_world(W, H, witch.x, witch.y)
sync_world()
auto_mode = False
running = True


while running:
    dt = min(clock.tick(FPS) / 1000.0, 0.05)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False
            elif event.key == pygame.K_SPACE:
                if witch.trigger_attack(None):
                    print("[CAST] Witch bắt đầu Cursed")
            elif event.key == pygame.K_t:
                auto_mode = not auto_mode
                print(f"[AUTO {'ON' if auto_mode else 'OFF'}]")
            elif event.key == pygame.K_n:
                s = SoldierDummy(
                    random.uniform(260, W - 80),
                    random.uniform(80, H - 80),
                    label=f"Sld+{len(soldiers) + 1}",
                )
                soldiers.append(s)
                sync_world()
            elif event.key == pygame.K_r:
                witch = make_witch()
                soldiers, heroes, towers = spawn_world(W, H, witch.x, witch.y)
                sync_world()

    keys = pygame.key.get_pressed()

    if auto_mode:
        witch.update(dt)
    else:
        witch._is_moving = False
        if not getattr(witch, '_is_casting', False):
            dx = dy = 0.0
            if keys[pygame.K_w]:
                dy -= 1.0
            if keys[pygame.K_s]:
                dy += 1.0
            if keys[pygame.K_a]:
                dx -= 1.0
            if keys[pygame.K_d]:
                dx += 1.0
            mag = (dx * dx + dy * dy) ** 0.5
            if mag > 0:
                witch._is_moving = True
                witch.x += (dx / mag) * witch._speed * dt
                witch.y += (dy / mag) * witch._speed * dt
                if abs(dx) >= abs(dy):
                    witch._direction = 3 if dx > 0 else 1
                else:
                    witch._direction = 2 if dy > 0 else 0
        witch.update_anim(dt)

    update_all(dt, soldiers, heroes, towers)

    screen.fill((24, 25, 32))
    for gx in range(0, W, 80):
        pygame.draw.line(screen, (38, 40, 48), (gx, 0), (gx, H))
    for gy in range(0, H, 80):
        pygame.draw.line(screen, (38, 40, 48), (0, gy), (W, gy))

    draw_all(screen, font, soldiers, heroes, towers)
    witch.draw(screen)

    hp = getattr(witch, '_hp', 0)
    max_hp = getattr(witch, '_max_hp', 1) or 1
    cd = max(0.0, getattr(witch, '_cast_cd_timer', 0.0))
    lines = [
        f"Witch HP={hp}/{max_hp}  mode={'AUTO' if auto_mode else 'MANUAL'}",
        f"Cursed cd={cd:.1f}s  casting={getattr(witch, '_is_casting', False)}  "
        f"last_bolts={getattr(witch, '_last_bolt_count', 0)}",
        f"Targets: soldiers={sum(s.is_alive for s in soldiers)}  "
        f"heroes={sum(h.is_alive for h in heroes)}  "
        f"towers={sum(t.is_alive for t in towers)}",
        "WASD=move  SPACE=Cursed  T=auto  N=+soldier  R=respawn  Q=quit",
    ]
    panel = pygame.Surface((W, 100), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 170))
    screen.blit(panel, (0, 0))
    for i, text in enumerate(lines):
        surf = font.render(text, True, (235, 235, 235))
        screen.blit(surf, (12, 10 + i * 22))

    pygame.display.flip()

pygame.quit()
