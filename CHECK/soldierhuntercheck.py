"""soldierhuntercheck.py — Demo trực quan SoldierHunter (walk/run/attack 192×192 + splash).

Phím điều khiển:
  WASD          — di chuyển SoldierHunter
  Shift + WASD  — chạy (Run animation)
  SPACE         — đòn lưỡi hiểm (range 60 px → execute lên target gần nhất)
                  • Strategy gọi WorldQuery.find_in_radius(target.x, target.y, 60, 'soldier')
                  • Target chính: damage ×1.0  dtype='normal'
                  • Soldiers trong splash 60 px quanh target: damage ×0.5  dtype='aoe'
  R             — respawn titan + 5 dummy mới
  Q / ESC       — thoát

Mục đích kiểm tra:
  • Walk/Run (frame 64×64, rows 8-11, 37-40)
  • Attack (frame 192×192 — kích thước đặc biệt, anchor center)
  • SoldierHunterStrategy.execute() truyền dtype đúng:
      - main target: 'normal' ×1.0
      - splashed:    'aoe'    ×0.5
  • WorldQuery mock trả về danh sách soldier trong radius
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
_strat_mod.MeleeRushStrategy      = _atk_src.MeleeRushStrategy
_strat_mod.HeavyStrikeStrategy    = _atk_src.HeavyStrikeStrategy
_strat_mod.ArmoredRamStrategy     = _atk_src.ArmoredRamStrategy
_strat_mod.Incurable              = _atk_src.Incurable
_strat_mod.TowerHunterStrategy    = _atk_src.TowerHunterStrategy
_strat_mod.SoldierHunterStrategy  = _atk_src.SoldierHunterStrategy
_strat_mod.Explosion              = _atk_src.Explosion


# WorldQuery với find_in_radius thật — sẽ được dummies đăng ký vào sau
class _MockWorldQuery:
    soldiers:   list = []   # demo sẽ assign list dummy soldiers vào đây
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
                       entity_type: str):
        """Trả về list entity còn sống trong bán kính `radius` quanh (cx, cy)."""
        pool = {'soldier':   cls.soldiers,
                'commander': cls.commanders,
                'tower':     cls.towers}.get(entity_type, [])
        out = []
        for s in pool:
            if not s.is_alive:
                continue
            d = ((s.x - cx) ** 2 + (s.y - cy) ** 2) ** 0.5
            if d <= radius:
                out.append(s)
        return out


_mod('systems')
_wq_mod = _mod('systems.world_query')
_wq_mod.WorldQuery = _MockWorldQuery


# ── 2. Import SoldierHunter thật ─────────────────────────────────────────────

from Titan import SoldierHunter  # noqa: E402


# ── 3. Soldier dummy ─────────────────────────────────────────────────────────

class SoldierDummy:
    """Dummy lính — nhận damage và lưu lại dtype của đòn cuối để vẽ HUD."""

    def __init__(self, x: float, y: float, hp: int = 200, label: str = ""):
        self.x = float(x)
        self.y = float(y)
        self._hp     = hp
        self._max_hp = hp
        self.is_alive = True
        self._label  = label
        self._last_dtype = ""        # 'normal' hoặc 'aoe' — để tô màu hit feedback
        self._hit_flash  = 0.0       # giây còn lại của hiệu ứng nháy

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp = max(0, self._hp - amount)
        self._last_dtype = dtype
        self._hit_flash  = 0.35
        tag = "MAIN" if dtype == 'normal' else "SPLASH"
        print(f"  [{self._label:8s}] take_damage(amount={amount:>3}, dtype='{dtype}')  "
              f"→ HP={self._hp:>3}/{self._max_hp}  [{tag}]")
        if self._hp <= 0:
            self.is_alive = False

    def update(self, dt: float) -> None:
        if self._hit_flash > 0:
            self._hit_flash = max(0.0, self._hit_flash - dt)


# ── 4. Pygame setup ──────────────────────────────────────────────────────────

pygame.init()
W, H   = 1100, 760
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "SoldierHunter Demo  (WASD=move  Shift=run  SPACE=cleave (splash 60px)  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font  = pygame.font.SysFont("Consolas", 15)
big   = pygame.font.SysFont("Consolas", 20, bold=True)


# ── 5. Spawn ─────────────────────────────────────────────────────────────────

CX, CY        = 250, H // 2
WALK_SPEED    = 90.0
RUN_SPEED     = 145.0
ATTACK_RANGE  = 60.0
SPLASH_RADIUS = 60.0


def make_titan() -> SoldierHunter:
    t = SoldierHunter(float(CX), float(CY), {
        'hp': 1200,
        'speed': WALK_SPEED,
        'damage': 40,
    })
    t._load_sprite()
    sprite_ok = t._sprite_sheet is not None
    sprite_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.modules['Titan'].__file__)),
        'Assets', 'Titan', 'soldierhunter.png',
    )
    print(f"\n=== Spawn SoldierHunter  HP={t._hp}  damage={t._damage}  "
          f"strategy={type(t._attack_strategy).__name__}  "
          f"splash={t._attack_strategy._splash_radius:.0f}px  "
          f"sprite={'OK' if sprite_ok else 'MISSING'} ===")
    if not sprite_ok:
        print(f"  [WARN] Sprite không tải được: {sprite_path}")
        print(f"  → Titan sẽ hiển thị bằng hình tròn vàng")
    return t


def make_dummies() -> list:
    """1 main target ở giữa + 4 lính xung quanh."""
    cx, cy = W - 320, H // 2
    main    = SoldierDummy(cx,      cy,      hp=250, label="MAIN")
    north   = SoldierDummy(cx,      cy - 50, hp=150, label="north")
    south   = SoldierDummy(cx,      cy + 50, hp=150, label="south")
    west    = SoldierDummy(cx - 50, cy,      hp=150, label="west")
    east    = SoldierDummy(cx + 50, cy,      hp=150, label="east")
    return [main, north, south, west, east]


titan   = make_titan()
dummies = make_dummies()


# ── 5b. Spawn 10 soldier (5 cụm + 5 random) + 3 hero + 3 tower ───────────────
from _demo_dummies import spawn_world, draw_all, update_all  # noqa: E402

_extra_sol, heroes, towers = spawn_world(W, H, titan.x, titan.y)

# 5 con dummies local (có _last_dtype) + 10 extra _demo_dummies soldier
_MockWorldQuery.soldiers   = dummies + _extra_sol
_MockWorldQuery.commanders = heroes
_MockWorldQuery.towers     = towers
print(f"[Spawn] soldiers={len(dummies) + len(_extra_sol)} "
      f"(5 main test + 10 extra)  heroes={len(heroes)}  towers={len(towers)}")


DIR_NAMES = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}


def _distance(a, b) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _find_nearest_alive(titan, dummies) -> tuple:
    best = None
    best_d = float('inf')
    for d in dummies:
        if not d.is_alive:
            continue
        dist = _distance(titan, d)
        if dist < best_d:
            best_d = dist
            best = d
    return best, best_d


def _target_name(e) -> str:
    """Tên hiển thị an toàn cho mọi loại target (dummy/soldier/hero/tower)."""
    return getattr(e, '_label', None) or getattr(e, 'name', None) \
        or type(e).__name__


def _all_targets() -> list:
    """Gộp MỌI mục tiêu có thể đánh: dummy + soldier + hero + tower.

    Đọc động các biến module-level nên luôn cập nhật sau khi bấm R
    (respawn). Yêu cầu: titan phải tấn công được cả 4 loại.
    """
    return list(dummies) + list(_extra_sol) + list(heroes) + list(towers)


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
                titan.trigger_attack()
                # Đánh mục tiêu gần nhất trong MỌI loại (dummy/soldier/
                # hero/tower). SoldierHunterStrategy vẫn giữ splash AoE
                # 60px quanh target qua WorldQuery — hiệu ứng đặc thù
                # không đổi, chỉ mở rộng tập mục tiêu chính.
                target, dist = _find_nearest_alive(titan, _all_targets())
                if target is not None and dist <= ATTACK_RANGE:
                    print(f"[CLEAVE]  dir={DIR_NAMES[titan._direction]}  "
                          f"target={_target_name(target)}  "
                          f"splash_radius={SPLASH_RADIUS:.0f}px  "
                          f"strategy={type(titan._attack_strategy).__name__}")
                    titan._attack_strategy.execute(titan, target)
                elif target is not None:
                    print(f"[CLEAVE miss]  nearest={_target_name(target)} "
                          f"dist={dist:.0f} > {ATTACK_RANGE:.0f}")
                else:
                    print(f"[CLEAVE miss]  hết mục tiêu")

            elif event.key == pygame.K_r:
                titan   = make_titan()
                dummies = make_dummies()
                _extra_sol, heroes, towers = spawn_world(W, H, titan.x, titan.y)
                _MockWorldQuery.soldiers   = dummies + _extra_sol
                _MockWorldQuery.commanders = heroes
                _MockWorldQuery.towers     = towers
                print(f"[Respawn] soldiers={len(dummies) + len(_extra_sol)}  "
                      f"heroes={len(heroes)}  towers={len(towers)}")

    # Movement (chặn khi đang đánh)
    if not titan._is_attacking:
        keys = pygame.key.get_pressed()
        titan._is_running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        speed = RUN_SPEED if titan._is_running else WALK_SPEED

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
            titan._direction = 1   # West  (A)
        elif dx > 0:
            titan._direction = 3   # East  (D)
        elif dy < 0:
            titan._direction = 0   # North (W)
        elif dy > 0:
            titan._direction = 2   # South (S)

        if dx != 0.0 and dy != 0.0:
            inv = 1.0 / math.sqrt(2.0)
            dx *= inv
            dy *= inv

        mx = dx * speed * dt
        my = dy * speed * dt
        titan._is_moving = (mx != 0.0 or my != 0.0)
        if titan._is_moving:
            titan.x = max(32.0, min(float(W - 32), titan.x + mx))
            titan.y = max(32.0, min(float(H - 32), titan.y + my))
    else:
        titan._is_moving = False

    titan.update_anim(dt)
    for d in dummies:
        d.update(dt)
    # Update + draw extra entities sẽ làm sau khi vẽ grid
    update_all(dt, _extra_sol, heroes, towers)

    # ── Draw ─────────────────────────────────────────────────────────────────
    screen.fill((28, 32, 38))

    for gx in range(0, W, 64):
        pygame.draw.line(screen, (45, 50, 58), (gx, 0), (gx, H))
    for gy in range(0, H, 64):
        pygame.draw.line(screen, (45, 50, 58), (0, gy), (W, gy))

    # Draw 10 extra soldier + 3 hero + 3 tower (background)
    draw_all(screen, font, _extra_sol, heroes, towers)

    # Vẽ splash preview quanh target gần nhất (mờ)
    near, ndist = _find_nearest_alive(titan, dummies)
    if near is not None and ndist <= ATTACK_RANGE:
        pygame.draw.circle(screen, (100, 200, 100),
                           (int(near.x), int(near.y)),
                           int(SPLASH_RADIUS), 1)

    # Dummies
    for d in dummies:
        if not d.is_alive:
            dead = font.render(f"{d._label} dead", True, (255, 80, 80))
            screen.blit(dead, (int(d.x - 28), int(d.y - 8)))
            continue
        # Màu flash theo dtype
        if d._hit_flash > 0:
            if d._last_dtype == 'normal':
                body = (240, 80, 80)        # đỏ — main hit
            else:
                body = (240, 180, 80)        # cam — splash AoE
        else:
            body = (100, 180, 110) if d._label != "MAIN" else (80, 200, 200)
        r = 22 if d._label != "MAIN" else 26
        pygame.draw.circle(screen, body, (int(d.x), int(d.y)), r)
        pygame.draw.circle(screen, (220, 220, 220), (int(d.x), int(d.y)), r, 2)

        # HP bar
        ratio = d._hp / d._max_hp if d._max_hp > 0 else 0
        bx = int(d.x - 30)
        by = int(d.y - r - 12)
        pygame.draw.rect(screen, (60, 0, 0), (bx, by, 60, 5))
        pygame.draw.rect(screen, (120, 220, 120), (bx, by, int(60 * ratio), 5))
        pygame.draw.rect(screen, (200, 200, 200), (bx, by, 60, 5), 1)
        lbl = font.render(f"{d._label} {d._hp}", True, (220, 220, 220))
        screen.blit(lbl, (bx, by - 14))

    # Titan
    titan.draw(screen)
    if titan._sprite_sheet is None:
        cx_t, cy_t = int(titan.x), int(titan.y)
        # Frame to khi attack, nhỏ khi walk/idle
        radius = 56 if titan._is_attacking else 30
        color = (240, 200, 80) if titan._is_attacking else (200, 160, 60)
        pygame.draw.circle(screen, color, (cx_t, cy_t), radius)
        pygame.draw.circle(screen, (255, 240, 200), (cx_t, cy_t), radius, 2)
        angle_map = {0: -math.pi / 2, 1: math.pi, 2: math.pi / 2, 3: 0.0}
        ang = angle_map[titan._direction]
        tip_x = cx_t + int(math.cos(ang) * (radius + 8))
        tip_y = cy_t + int(math.sin(ang) * (radius + 8))
        pygame.draw.line(screen, (255, 255, 255), (cx_t, cy_t), (tip_x, tip_y), 3)

    # Vòng tầm cleave
    pygame.draw.circle(screen, (200, 200, 100),
                       (int(titan.x), int(titan.y)), int(ATTACK_RANGE), 1)

    # HP bar titan
    bar_w = 80
    hp_ratio = titan._hp / titan._max_hp if titan._max_hp > 0 else 0
    bx = int(titan.x - bar_w // 2)
    by = int(titan.y - 56)
    pygame.draw.rect(screen, (60, 0, 0),  (bx, by, bar_w, 6))
    pygame.draw.rect(screen, (220, 40, 40), (bx, by, int(bar_w * hp_ratio), 6))
    pygame.draw.rect(screen, (200, 200, 200), (bx, by, bar_w, 6), 1)

    # HUD
    if titan._is_attacking:
        state = "CLEAVE"
        row_info = f"attack_y={titan._ATTACK_Y[titan._direction]}  frame=192×192"
    elif titan._is_moving and titan._is_running:
        state = "RUN"
        row_info = f"row={titan._RUN_ROWS[titan._direction]}  frame=64×64"
    elif titan._is_moving:
        state = "WALK"
        row_info = f"row={titan._WALK_ROWS[titan._direction]}  frame=64×64"
    else:
        state = "IDLE"
        row_info = f"row={titan._WALK_ROWS[titan._direction]}  frame=64×64"

    sprite_status = "OK" if titan._sprite_sheet is not None else "MISSING (fallback)"
    expected_main   = titan._damage
    expected_splash = int(titan._damage * titan._attack_strategy._splash_mult)

    hud = [
        f"sprite  : Assets/Titan/soldierhunter.png (1152×4224)  [{sprite_status}]",
        f"state   : {state}   dir={DIR_NAMES[titan._direction]}   "
        f"col={titan._anim_col}   {row_info}",
        f"hp      : {titan._hp}/{titan._max_hp}  ({hp_ratio*100:.0f}%)",
        f"damage  : main={expected_main}  splash={expected_splash} "
        f"(×{titan._attack_strategy._splash_mult:.1f})",
        f"strategy: {type(titan._attack_strategy).__name__}  "
        f"splash_radius={titan._attack_strategy._splash_radius:.0f}px",
        "",
        "WASD=move  Shift=run  SPACE=cleave (tầm 60px → target gần nhất)",
        "R=respawn  Q=quit",
    ]
    for i, line in enumerate(hud):
        surf = font.render(line, True, (220, 220, 220))
        screen.blit(surf, (12, 12 + i * 18))

    pygame.display.flip()

pygame.quit()
sys.exit()
