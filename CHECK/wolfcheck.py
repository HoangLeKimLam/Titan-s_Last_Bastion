"""wolfcheck.py — Demo trực quan Wolf Titan (walk/run/attack + antiheal debuff).

Phím điều khiển:
  WASD          — di chuyển Wolf (cập nhật hướng nhìn)
  Shift + WASD  — chạy (Run animation)
  SPACE         — đòn cắn (Incurable: damage ×0.8, dtype='antiheal')
                  Nếu trong tầm 60 px của dummy → áp lên dummy:
                    • damage thường
                    • đặt cờ no_heal_timer = 5.0 s (chặn regen)
  R             — respawn Wolf + dummy
  Q / ESC       — thoát

Dummy target:
  • HP 400, regen +5/s khi không bị antiheal
  • Khi nhận dtype='antiheal' → timer chặn heal 5 s
  • HUD hiển thị HEAL/BLOCKED và đếm ngược

Mục đích kiểm tra:
  • Walk (rows 8–11, 9 frame) vs Run (rows 37–40, 8 frame)
  • Attack (rows 12–15, 6 frame) loop 1 s
  • Sprite `wolf.png` fixed (không random)
  • Incurable.execute() truyền đúng dtype='antiheal'
  • Loose coupling: target tự xử lý dtype, không cần Strategy biết gì về heal
"""
import sys
import os
import math
import types

import pygame


# ── 1. Mock modules ──────────────────────────────────────────────────────────

def _mod(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


class _MockEntity:
    _next_id = 1

    def __init__(self, x: float, y: float):
        self.id = _MockEntity._next_id
        _MockEntity._next_id += 1
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen) -> None:
        pass


_mod('core')
_entity_mod = _mod('core.entity')
_entity_mod.Entity = _MockEntity


class _IAttackable:
    pass


class _IMovable:
    pass


_iface_mod = _mod('core.interfaces')
_iface_mod.IAttackable = _IAttackable
_iface_mod.IMovable    = _IMovable


class _MockBus:
    _inst = None

    @classmethod
    def get_instance(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def publish(self, event: str, data: dict) -> None:
        print(f"  [EventBus] publish('{event}', keys={list(data.keys())})")


_bus_mod = _mod('core.event_bus')
_bus_mod.GameEventBus = _MockBus


_mod('characters')
_mod('characters.titans')

# File này nằm trong CHECK/ — sys.path phải trỏ về parent (chứa Titan.py, AttackStrategy.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import AttackStrategy as _atk_src  # noqa: E402
_strat_mod = _mod('characters.titans.attackstrategy')
# Inject TẤT CẢ strategy mà Titan.py import (TowerHunter/SoldierHunter cũng được import)
_strat_mod.MeleeRushStrategy      = _atk_src.MeleeRushStrategy
_strat_mod.HeavyStrikeStrategy    = _atk_src.HeavyStrikeStrategy
_strat_mod.ArmoredRamStrategy     = _atk_src.ArmoredRamStrategy
_strat_mod.Incurable              = _atk_src.Incurable
_strat_mod.TowerHunterStrategy    = _atk_src.TowerHunterStrategy
_strat_mod.SoldierHunterStrategy  = _atk_src.SoldierHunterStrategy
_strat_mod.Explosion              = _atk_src.Explosion


class _MockWorldQuery:
    soldiers:   list = []
    commanders: list = []
    towers:     list = []

    @classmethod
    def get_headquarters(cls):
        return None

    @classmethod
    def can_reach_direct(cls, *_a, **_kw) -> bool:
        return False

    @classmethod
    def find_blocking_wall(cls, *_a, **_kw):
        return None

    @classmethod
    def find_nearest_attacker(cls, *_a, **_kw):
        return None

    @classmethod
    def find_nearest(cls, cx: float, cy: float, entity_type: str):
        pool = {'soldier':   cls.soldiers,
                'commander': cls.commanders,
                'tower':     cls.towers}.get(entity_type, [])
        best, best_d = None, float('inf')
        for e in pool:
            if not e.is_alive:
                continue
            d = ((e.x - cx) ** 2 + (e.y - cy) ** 2) ** 0.5
            if d < best_d:
                best_d, best = d, e
        return best

    @classmethod
    def find_in_radius(cls, cx: float, cy: float, radius: float,
                       entity_type: str) -> list:
        pool = {'soldier':   cls.soldiers,
                'commander': cls.commanders,
                'tower':     cls.towers}.get(entity_type, [])
        return [e for e in pool
                if e.is_alive
                and ((e.x - cx) ** 2 + (e.y - cy) ** 2) ** 0.5 <= radius]


_mod('systems')
_wq_mod = _mod('systems.world_query')
_wq_mod.WorldQuery = _MockWorldQuery


# ── 2. Import Wolf thật ──────────────────────────────────────────────────────

from Titan import Wolf  # noqa: E402


# ── 3. Dummy target có regen ─────────────────────────────────────────────────

class HealingDummy:
    """Dummy target tự hồi +5 HP/s, có thể bị antiheal chặn 5 s."""

    REGEN_PER_SEC   = 5.0
    NO_HEAL_SECONDS = 5.0

    def __init__(self, x: float, y: float, hp: int = 400):
        self.x = float(x)
        self.y = float(y)
        self._hp           = hp
        self._max_hp       = hp
        self._no_heal_timer = 0.0
        self._regen_accum   = 0.0
        self.is_alive      = True

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp = max(0, self._hp - amount)
        print(f"  [Dummy] take_damage(amount={amount}, dtype='{dtype}')  "
              f"→ HP={self._hp}/{self._max_hp}")
        if dtype == 'antiheal':
            self._no_heal_timer = self.NO_HEAL_SECONDS
            print(f"  [Dummy] HEAL BLOCKED for {self.NO_HEAL_SECONDS:.1f}s")
        if self._hp <= 0:
            self.is_alive = False

    def update(self, dt: float) -> None:
        if not self.is_alive:
            return
        # Cooldown timer của debuff antiheal
        if self._no_heal_timer > 0:
            self._no_heal_timer = max(0.0, self._no_heal_timer - dt)
            return
        # Regen tích lũy
        if self._hp < self._max_hp:
            self._regen_accum += self.REGEN_PER_SEC * dt
            if self._regen_accum >= 1.0:
                heal = int(self._regen_accum)
                self._regen_accum -= heal
                self._hp = min(self._max_hp, self._hp + heal)


# ── 4. Pygame setup ──────────────────────────────────────────────────────────

pygame.init()
W, H   = 1000, 720
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "Wolf Demo  (WASD=move  Shift=run  SPACE=bite(antiheal)  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font  = pygame.font.SysFont("Consolas", 15)
big   = pygame.font.SysFont("Consolas", 22, bold=True)


# ── 5. Spawn ─────────────────────────────────────────────────────────────────

CX, CY     = 200, H // 2
WALK_SPEED = 100.0
RUN_SPEED  = 160.0
BITE_RANGE = 60.0


def make_wolf() -> Wolf:
    w = Wolf(float(CX), float(CY), {
        'hp': 600,
        'speed': WALK_SPEED,
        'damage': 30,
    })
    w._load_sprite()
    sprite_ok = w._sprite_sheet is not None
    sprite_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.modules['Titan'].__file__)),
        'Assets', 'Titan', 'wolf.png',
    )
    print(f"\n=== Spawn Wolf  HP={w._hp}  damage={w._damage}  "
          f"strategy={type(w._attack_strategy).__name__}  "
          f"sprite={'OK' if sprite_ok else 'MISSING'} ===")
    if not sprite_ok:
        print(f"  [WARN] Sprite không tải được: {sprite_path}")
        print(f"  → Wolf sẽ hiển thị bằng hình tròn xanh dương")
    return w


def make_dummy() -> HealingDummy:
    return HealingDummy(W - 250, H // 2, hp=400)


wolf  = make_wolf()
dummy = make_dummy()


# ── 5b. Spawn 10 soldier + 3 hero + 3 tower (background) ─────────────────────
from _demo_dummies import spawn_world, draw_all, update_all  # noqa: E402

soldiers, heroes, towers = spawn_world(W, H, wolf.x, wolf.y)
_MockWorldQuery.soldiers   = soldiers
_MockWorldQuery.commanders = heroes
_MockWorldQuery.towers     = towers
print(f"[Spawn] soldiers={len(soldiers)}  heroes={len(heroes)}  towers={len(towers)}")


DIR_NAMES = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}


def _distance(a, b) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _target_name(e) -> str:
    """Tên hiển thị an toàn cho mọi loại target."""
    return getattr(e, '_label', None) or getattr(e, 'name', None) \
        or type(e).__name__


def _all_targets() -> list:
    """Gộp MỌI mục tiêu có thể đánh: dummy chính + soldier + hero + tower.

    Đọc động biến module-level → cập nhật đúng sau khi bấm R (respawn).
    """
    return [dummy] + list(soldiers) + list(heroes) + list(towers)


def _find_nearest_alive(origin, candidates) -> tuple:
    """Trả (target, dist) của entity còn sống gần nhất, hoặc (None, inf)."""
    best, best_d = None, float('inf')
    for e in candidates:
        if not getattr(e, 'is_alive', False):
            continue
        d = _distance(origin, e)
        if d < best_d:
            best_d, best = d, e
    return best, best_d


# ── 6. Vòng lặp ──────────────────────────────────────────────────────────────

running = True

while running:
    dt = min(clock.tick(60) / 1000.0, 0.05)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

            elif event.key == pygame.K_SPACE:
                wolf.trigger_attack()
                # Cắn mục tiêu gần nhất trong MỌI loại (dummy/soldier/
                # hero/tower). Incurable.execute() vẫn truyền dtype
                # 'antiheal' — mọi loại target đều nhận được đòn cắn.
                target, dist = _find_nearest_alive(wolf, _all_targets())
                if target is not None and dist <= BITE_RANGE:
                    print(f"[BITE]  dir={DIR_NAMES[wolf._direction]}  "
                          f"target={_target_name(target)}  "
                          f"row={wolf._ATTACK_ROWS[wolf._direction]}  "
                          f"strategy={type(wolf._attack_strategy).__name__}")
                    wolf._attack_strategy.execute(wolf, target)
                elif target is not None:
                    print(f"[BITE miss]  nearest={_target_name(target)} "
                          f"dist={dist:.0f} > {BITE_RANGE:.0f}")
                else:
                    print(f"[BITE miss]  hết mục tiêu")

            elif event.key == pygame.K_r:
                wolf  = make_wolf()
                dummy = make_dummy()
                soldiers, heroes, towers = spawn_world(W, H, wolf.x, wolf.y)
                _MockWorldQuery.soldiers   = soldiers
                _MockWorldQuery.commanders = heroes
                _MockWorldQuery.towers     = towers
                print(f"[Respawn] soldiers={len(soldiers)}  "
                      f"heroes={len(heroes)}  towers={len(towers)}")

    # Movement (chặn khi đang cắn)
    if not wolf._is_attacking:
        keys = pygame.key.get_pressed()
        wolf._is_running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        speed = RUN_SPEED if wolf._is_running else WALK_SPEED

        dx = dy = 0.0
        if keys[pygame.K_w]:
            dy -= 1.0
        if keys[pygame.K_s]:
            dy += 1.0
        if keys[pygame.K_a]:
            dx -= 1.0
        if keys[pygame.K_d]:
            dx += 1.0

        # Hướng nhìn: ưu tiên trục ngang (A/D) hơn trục dọc (W/S).
        #   W+D → D, A+W → A. A+D (hoặc W+S) triệt tiêu → giữ hướng cũ.
        if dx < 0:
            wolf._direction = 1   # West  (A)
        elif dx > 0:
            wolf._direction = 3   # East  (D)
        elif dy < 0:
            wolf._direction = 0   # North (W)
        elif dy > 0:
            wolf._direction = 2   # South (S)

        if dx != 0.0 and dy != 0.0:
            inv = 1.0 / math.sqrt(2.0)
            dx *= inv
            dy *= inv

        mx = dx * speed * dt
        my = dy * speed * dt
        wolf._is_moving = (mx != 0.0 or my != 0.0)
        if wolf._is_moving:
            wolf.x = max(32.0, min(float(W - 32), wolf.x + mx))
            wolf.y = max(32.0, min(float(H - 32), wolf.y + my))
    else:
        wolf._is_moving = False

    # Animation + dummy regen
    wolf.update_anim(dt)
    dummy.update(dt)

    # ── Draw ─────────────────────────────────────────────────────────────────
    screen.fill((28, 32, 38))

    for gx in range(0, W, 64):
        pygame.draw.line(screen, (45, 50, 58), (gx, 0), (gx, H))
    for gy in range(0, H, 64):
        pygame.draw.line(screen, (45, 50, 58), (0, gy), (W, gy))

    # Update + Draw background entities (10 soldier + 3 hero + 3 tower)
    update_all(dt, soldiers, heroes, towers)
    draw_all(screen, font, soldiers, heroes, towers)

    # Dummy
    if dummy.is_alive:
        dr = 36
        # Màu thay đổi theo trạng thái heal
        if dummy._no_heal_timer > 0:
            body = (180, 80, 80)    # đỏ — đang bị chặn heal
            ring = (255, 180, 80)
        else:
            body = (80, 140, 80)    # xanh — đang heal
            ring = (180, 240, 180)
        pygame.draw.circle(screen, body, (int(dummy.x), int(dummy.y)), dr)
        pygame.draw.circle(screen, ring, (int(dummy.x), int(dummy.y)), dr, 2)

        # HP bar dummy
        ratio = dummy._hp / dummy._max_hp if dummy._max_hp > 0 else 0
        bx = int(dummy.x - 50)
        by = int(dummy.y - dr - 16)
        pygame.draw.rect(screen, (60, 0, 0), (bx, by, 100, 6))
        pygame.draw.rect(screen, (60, 200, 100), (bx, by, int(100 * ratio), 6))
        pygame.draw.rect(screen, (200, 200, 200), (bx, by, 100, 6), 1)
        lbl = font.render(f"DUMMY {dummy._hp}/{dummy._max_hp}", True, (220, 220, 220))
        screen.blit(lbl, (bx, by - 16))
        if dummy._no_heal_timer > 0:
            tlbl = font.render(
                f"HEAL BLOCKED {dummy._no_heal_timer:.1f}s",
                True, (255, 180, 80))
            screen.blit(tlbl, (bx, by - 32))
        else:
            tlbl = font.render("REGEN +5/s", True, (160, 240, 160))
            screen.blit(tlbl, (bx, by - 32))
    else:
        dead = big.render("DUMMY DEAD", True, (255, 80, 80))
        screen.blit(dead, (int(dummy.x - 70), int(dummy.y - 12)))

    # Wolf
    wolf.draw(screen)
    if wolf._sprite_sheet is None:
        cx_t, cy_t = int(wolf.x), int(wolf.y)
        pygame.draw.circle(screen, (80, 120, 200), (cx_t, cy_t), 26)
        pygame.draw.circle(screen, (200, 220, 255), (cx_t, cy_t), 26, 2)
        angle_map = {0: -math.pi / 2, 1: math.pi, 2: math.pi / 2, 3: 0.0}
        ang = angle_map[wolf._direction]
        tip_x = cx_t + int(math.cos(ang) * 32)
        tip_y = cy_t + int(math.sin(ang) * 32)
        pygame.draw.line(screen, (255, 255, 255), (cx_t, cy_t), (tip_x, tip_y), 3)

    # Vòng tầm cắn (mờ)
    pygame.draw.circle(screen, (120, 120, 160),
                       (int(wolf.x), int(wolf.y)), int(BITE_RANGE), 1)

    # HP bar wolf
    bar_w = 80
    hp_ratio = wolf._hp / wolf._max_hp if wolf._max_hp > 0 else 0
    bx = int(wolf.x - bar_w // 2)
    by = int(wolf.y - 48)
    pygame.draw.rect(screen, (60, 0, 0),  (bx, by, bar_w, 6))
    pygame.draw.rect(screen, (220, 40, 40), (bx, by, int(bar_w * hp_ratio), 6))
    pygame.draw.rect(screen, (200, 200, 200), (bx, by, bar_w, 6), 1)

    # HUD
    if wolf._is_attacking:
        state = "BITE"
        row   = wolf._ATTACK_ROWS[wolf._direction]
    elif wolf._is_moving and wolf._is_running:
        state = "RUN"
        row   = wolf._RUN_ROWS[wolf._direction]
    elif wolf._is_moving:
        state = "WALK"
        row   = wolf._WALK_ROWS[wolf._direction]
    else:
        state = "IDLE"
        row   = wolf._WALK_ROWS[wolf._direction]

    sprite_status = "OK" if wolf._sprite_sheet is not None else "MISSING (fallback)"

    hud = [
        f"sprite  : Assets/Titan/wolf.png  [{sprite_status}]",
        f"state   : {state}   dir={DIR_NAMES[wolf._direction]}   "
        f"row={row}   col={wolf._anim_col}",
        f"hp      : {wolf._hp}/{wolf._max_hp}  ({hp_ratio*100:.0f}%)",
        f"damage  : {wolf._damage}  ×0.8 = {int(wolf._damage * 0.8)} (Incurable)",
        f"strategy: {type(wolf._attack_strategy).__name__}",
        "",
        "WASD=move  Shift=run  SPACE=bite (cắn antiheal, tầm 60px)",
        "R=respawn  Q=quit",
    ]
    for i, line in enumerate(hud):
        surf = font.render(line, True, (220, 220, 220))
        screen.blit(surf, (12, 12 + i * 18))

    pygame.display.flip()

pygame.quit()
sys.exit()
