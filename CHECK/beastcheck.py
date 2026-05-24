"""beastcheck.py — Demo trực quan BeastTitan (walk/run/throw + arc rock physics).

Phím điều khiển:
  WASD          — di chuyển Beast manual (cập nhật hướng nhìn)
  Shift + WASD  — chạy (Run animation)
  SPACE         — ném đá thủ công vào tower gần nhất (nếu trong tầm 350px)
  T             — toggle AUTO mode (beast tự ném theo cooldown, tự walk khi xa)
  R             — respawn beast + 3 tower + 1 soldier
  Q / ESC       — thoát

Setup dummy (đo từ beast spawn point):
  • Tower 1: 150 px (đông)           — trong tầm
  • Tower 2: 280 px (đông-nam)       — trong tầm
  • Tower 3: 450 px (đông-bắc)       — NGOÀI tầm 350 (AUTO mode → walk lại gần)
  • Soldier: 200 px (bắc)            — không được ưu tiên (không phải Tower)

Mục đích kiểm tra:
  • Walk (rows 8-11, 9 frame) vs Run (rows 38-41, 8 frame)
  • Attack (rows 12-15, 6 frame, 24 FPS = 0.25 s/đòn)
  • Rock release tại frame 3/6 của animation (~0.125 s sau trigger)
  • Rock visual = Rock Pile sheet row 9 col 5 (frame 85×85)
  • Physics: vận tốc 250 px/s + góc 15° + gravity 600 px/s² → arc parabol
  • Damage AoE 80 px: main 80, splash 40 (dtype='rock')
  • AUTO mode: walk lại gần khi tower xa hơn 350 px
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


# ── 2. Mock characters.titans (Titan base + tất cả strategy mà Titan.py import)

_mod('characters')
_mod('characters.titans')

# File này nằm trong CHECK/ — sys.path phải trỏ về parent (chứa Boss.py, AttackStrategy.py)
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
_strat_mod.GroundSlamStrategy     = _atk_src.GroundSlamStrategy
# NHÓM 6 — Boss.py import lại RockProjectile/HeatParticle từ attackstrategy
_strat_mod.RockProjectile         = _atk_src.RockProjectile
_strat_mod.HeatParticle           = _atk_src.HeatParticle


# Import class Titan thật để Boss.py có thể `from characters.titans.titan import Titan`
import Titan as _titan_src  # noqa: E402
_titan_mod = _mod('characters.titans.titan')
_titan_mod.Titan = _titan_src.Titan


# ── 3. Mock WorldQuery — find_nearest('tower') + find_in_radius(...) ─────────

class _MockWorldQuery:
    """Đăng ký list tower/soldier/commander từ demo qua class-attribute."""
    towers:     list = []
    soldiers:   list = []
    commanders: list = []

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
        pool = getattr(cls, entity_type + 's', [])
        best = None
        best_d = float('inf')
        for e in pool:
            if not e.is_alive:
                continue
            d = ((e.x - cx) ** 2 + (e.y - cy) ** 2) ** 0.5
            if d < best_d:
                best_d = d
                best = e
        return best

    @classmethod
    def find_in_radius(cls, cx: float, cy: float, radius: float,
                       entity_type: str):
        pool = getattr(cls, entity_type + 's', [])
        out = []
        for e in pool:
            if not e.is_alive:
                continue
            d = ((e.x - cx) ** 2 + (e.y - cy) ** 2) ** 0.5
            if d <= radius:
                out.append(e)
        return out


_mod('systems')
_wq_mod = _mod('systems.world_query')
_wq_mod.WorldQuery = _MockWorldQuery


# ── 4. Mock patterns.decorator (Boss.py import BurnDecorator trong steam_burst)

class _BurnDecorator:
    def __init__(self, entity, damage_per_sec: float, duration: float):
        pass


_mod('patterns')
_pd_mod = _mod('patterns.decorator')
_pd_mod.BurnDecorator = _BurnDecorator


# ── 5. Import BeastTitan thật ────────────────────────────────────────────────

from Boss import BeastTitan  # noqa: E402


# ── 6. Dummies ───────────────────────────────────────────────────────────────

class TowerDummy:
    def __init__(self, x: float, y: float, label: str, hp: int = 600):
        self.x = float(x)
        self.y = float(y)
        self._hp     = hp
        self._max_hp = hp
        self.is_alive = True
        self._label  = label
        self._hit_flash = 0.0

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp = max(0, self._hp - amount)
        self._hit_flash = 0.4
        print(f"  [{self._label:7s}] take_damage(amount={amount:>3}, dtype='{dtype}')  "
              f"→ HP={self._hp:>3}/{self._max_hp}")
        if self._hp <= 0:
            self.is_alive = False

    def update(self, dt: float) -> None:
        if self._hit_flash > 0:
            self._hit_flash = max(0.0, self._hit_flash - dt)


class SoldierDummy:
    def __init__(self, x: float, y: float, hp: int = 200):
        self.x = float(x)
        self.y = float(y)
        self._hp     = hp
        self._max_hp = hp
        self.is_alive = True
        self._hit_flash = 0.0

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp = max(0, self._hp - amount)
        self._hit_flash = 0.4
        print(f"  [Soldier] take_damage(amount={amount:>3}, dtype='{dtype}')  "
              f"→ HP={self._hp:>3}/{self._max_hp}")
        if self._hp <= 0:
            self.is_alive = False

    def update(self, dt: float) -> None:
        if self._hit_flash > 0:
            self._hit_flash = max(0.0, self._hit_flash - dt)


# ── 7. Pygame setup ──────────────────────────────────────────────────────────

pygame.init()
W, H   = 1200, 760
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "BeastTitan Demo  (WASD=move  Shift=run  SPACE=throw  T=auto  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font  = pygame.font.SysFont("Consolas", 15)
big   = pygame.font.SysFont("Consolas", 20, bold=True)


# ── 8. Spawn ─────────────────────────────────────────────────────────────────

BEAST_X, BEAST_Y = 220, H // 2
WALK_SPEED = 80.0
RUN_SPEED  = 130.0


def make_beast() -> BeastTitan:
    b = BeastTitan(float(BEAST_X), float(BEAST_Y), {
        'hp': 1500,
        'speed': WALK_SPEED,
        'damage': 80,
    })
    b._load_sprite()
    sprite_ok = b._sprite_sheet is not None
    rock_ok   = b._rock_frame is not None
    print(f"\n=== Spawn BeastTitan  HP={b._hp}  THROW_RANGE={b.THROW_RANGE:.0f}px  "
          f"beast_sprite={'OK' if sprite_ok else 'MISSING'}  "
          f"rock_sprite={'OK' if rock_ok else 'MISSING'} ===")
    if not sprite_ok:
        print(f"  [WARN] Assets/Boss/beast.png không tải được → fallback hình tròn nâu")
    if not rock_ok:
        print(f"  [WARN] Rock Pile sheet không tải được → fallback hình tròn xám")
    return b


def make_dummies() -> tuple:
    """3 tower ở các khoảng cách + 1 soldier."""
    # Tính vị trí tower theo (dist, angle) so với beast
    def at(dist: float, angle_deg: float, label: str = "", soldier=False):
        rad = math.radians(angle_deg)
        x = BEAST_X + math.cos(rad) * dist
        y = BEAST_Y + math.sin(rad) * dist
        if soldier:
            return SoldierDummy(x, y)
        return TowerDummy(x, y, label)

    t1 = at(150, 0,    label="T@150")   # đông, trong tầm
    t2 = at(280, 30,   label="T@280")   # đông-nam, trong tầm
    t3 = at(450, -25,  label="T@450")   # đông-bắc, NGOÀI tầm
    sol = at(200, -90, soldier=True)    # bắc, soldier
    return [t1, t2, t3], [sol]


beast = make_beast()
towers_local, soldiers_local = make_dummies()


# ── 8b. Spawn 10 soldier + 3 hero + 3 tower từ _demo_dummies (background) ────
from _demo_dummies import spawn_world, draw_all, update_all  # noqa: E402

_extra_sol, heroes, _extra_tw = spawn_world(W, H, beast.x, beast.y)

# Pool gộp: 3 tower setup + 3 tower extra + 1 soldier local + 10 soldier extra
towers = towers_local + _extra_tw
soldiers = soldiers_local + _extra_sol
_MockWorldQuery.towers     = towers
_MockWorldQuery.soldiers   = soldiers
_MockWorldQuery.commanders = heroes
print(f"[Spawn] towers={len(towers)} ({len(towers_local)} setup + "
      f"{len(_extra_tw)} extra)  soldiers={len(soldiers)} "
      f"({len(soldiers_local)} setup + {len(_extra_sol)} extra)  "
      f"heroes={len(heroes)}")


DIR_NAMES = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}


def _distance(a, b) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _find_nearest_tower_alive() -> tuple:
    best, best_d = None, float('inf')
    for t in towers:
        if not t.is_alive:
            continue
        d = _distance(beast, t)
        if d < best_d:
            best_d, best = d, t
    return best, best_d


def _target_name(e) -> str:
    """Tên hiển thị an toàn cho mọi loại target."""
    return getattr(e, '_label', None) or getattr(e, 'name', None) \
        or type(e).__name__


def _all_targets() -> list:
    """Gộp MỌI mục tiêu có thể đánh: tower + soldier + hero.

    Đọc động biến module-level → cập nhật đúng sau khi bấm R (respawn).
    """
    return list(towers) + list(soldiers) + list(heroes)


def _find_nearest_any() -> tuple:
    """Trả (target, dist) của mục tiêu còn sống gần nhất trong MỌI loại."""
    best, best_d = None, float('inf')
    for e in _all_targets():
        if not getattr(e, 'is_alive', False):
            continue
        d = _distance(beast, e)
        if d < best_d:
            best_d, best = d, e
    return best, best_d


# ── 9. Vòng lặp ──────────────────────────────────────────────────────────────

auto_mode = False
running   = True

while running:
    dt = min(clock.tick(60) / 1000.0, 0.05)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

            elif event.key == pygame.K_SPACE:
                # Ném đá vào mục tiêu gần nhất trong MỌI loại (tower/
                # soldier/hero). RockProjectile khi rơi AoE đủ cả 3 loại
                # quanh điểm rơi — hiệu ứng đặc thù giữ nguyên.
                target, dist = _find_nearest_any()
                if target is None:
                    print(f"[THROW miss]  hết mục tiêu")
                elif dist > beast.THROW_RANGE:
                    print(f"[THROW miss]  mục tiêu gần nhất @ {dist:.0f}px > "
                          f"{beast.THROW_RANGE:.0f}px")
                else:
                    started = beast.trigger_attack(target)
                    if started:
                        beast._throw_timer = beast._throw_cooldown
                        print(f"[THROW]  target={_target_name(target)} "
                              f"@ {dist:.0f}px  "
                              f"dir={DIR_NAMES[beast._direction]}  "
                              f"release tại frame {beast._ROCK_RELEASE_FRAME}/6")

            elif event.key == pygame.K_t:
                auto_mode = not auto_mode
                print(f"[AUTO mode {'ON' if auto_mode else 'OFF'}]")

            elif event.key == pygame.K_r:
                beast = make_beast()
                towers_local, soldiers_local = make_dummies()
                _extra_sol, heroes, _extra_tw = spawn_world(W, H, beast.x, beast.y)
                towers   = towers_local + _extra_tw
                soldiers = soldiers_local + _extra_sol
                _MockWorldQuery.towers     = towers
                _MockWorldQuery.soldiers   = soldiers
                _MockWorldQuery.commanders = heroes
                print(f"[Respawn] towers={len(towers)}  "
                      f"soldiers={len(soldiers)}  heroes={len(heroes)}")
                auto_mode = False

    # ── AUTO mode: BeastTitan.update tự xử lý AI ─────────────────────────────
    if auto_mode:
        beast.update(dt)
    else:
        # Manual mode: WASD move, không tự attack
        if not beast._is_attacking:
            keys = pygame.key.get_pressed()
            beast._is_running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
            speed = RUN_SPEED if beast._is_running else WALK_SPEED

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
                beast._direction = 1   # West  (A)
            elif dx > 0:
                beast._direction = 3   # East  (D)
            elif dy < 0:
                beast._direction = 0   # North (W)
            elif dy > 0:
                beast._direction = 2   # South (S)

            if dx != 0.0 and dy != 0.0:
                inv = 1.0 / math.sqrt(2.0)
                dx *= inv
                dy *= inv

            mx = dx * speed * dt
            my = dy * speed * dt
            beast._is_moving = (mx != 0.0 or my != 0.0)
            if beast._is_moving:
                beast.x = max(40.0, min(float(W - 40), beast.x + mx))
                beast.y = max(40.0, min(float(H - 40), beast.y + my))
        else:
            beast._is_moving = False

        beast.update_anim(dt)
        # Cooldown timer cũng phải tick trong manual mode
        if beast._throw_timer > 0:
            beast._throw_timer = max(0.0, beast._throw_timer - dt)

    # Update dummies (hit flash)
    for t in towers:
        t.update(dt)
    for s in soldiers:
        s.update(dt)
    for h in heroes:
        h.update(dt)

    # ── Draw ─────────────────────────────────────────────────────────────────
    screen.fill((28, 32, 38))
    for gx in range(0, W, 64):
        pygame.draw.line(screen, (45, 50, 58), (gx, 0), (gx, H))
    for gy in range(0, H, 64):
        pygame.draw.line(screen, (45, 50, 58), (0, gy), (W, gy))

    # Vòng tầm ném 350px
    pygame.draw.circle(screen, (220, 140, 60),
                       (int(beast.x), int(beast.y)),
                       int(beast.THROW_RANGE), 1)

    # Towers
    for t in towers:
        if t.is_alive:
            tx, ty = int(t.x), int(t.y)
            rect = pygame.Rect(tx - 30, ty - 36, 60, 72)
            body = (240, 200, 80) if t._hit_flash > 0 else (130, 130, 150)
            pygame.draw.rect(screen, body, rect)
            pygame.draw.rect(screen, (220, 220, 240), rect, 2)
            # Crenellation
            for cx in range(tx - 28, tx + 28, 12):
                pygame.draw.rect(screen, body, (cx, ty - 46, 8, 10))
                pygame.draw.rect(screen, (220, 220, 240), (cx, ty - 46, 8, 10), 1)
            # HP bar
            ratio = t._hp / t._max_hp if t._max_hp > 0 else 0
            bx, by = tx - 40, ty - 60
            pygame.draw.rect(screen, (60, 0, 0), (bx, by, 80, 5))
            pygame.draw.rect(screen, (240, 200, 80),
                             (bx, by, int(80 * ratio), 5))
            pygame.draw.rect(screen, (200, 200, 200), (bx, by, 80, 5), 1)
            lbl = font.render(f"{t._label} {t._hp}", True, (220, 220, 220))
            screen.blit(lbl, (bx, by - 14))
            # Khoảng cách hiện tại
            d = _distance(beast, t)
            color_d = (140, 220, 140) if d <= beast.THROW_RANGE else (240, 140, 140)
            dlbl = font.render(f"{d:.0f}px", True, color_d)
            screen.blit(dlbl, (bx, by + 8))
        else:
            dead = big.render(f"{t._label} DEAD", True, (255, 80, 80))
            screen.blit(dead, (int(t.x - 60), int(t.y - 12)))

    # Soldier
    for s in soldiers:
        if s.is_alive:
            sx, sy = int(s.x), int(s.y)
            body = (240, 200, 80) if s._hit_flash > 0 else (100, 180, 110)
            pygame.draw.circle(screen, body, (sx, sy), 22)
            pygame.draw.circle(screen, (200, 240, 200), (sx, sy), 22, 2)
            ratio = s._hp / s._max_hp if s._max_hp > 0 else 0
            bx, by = sx - 30, sy - 38
            pygame.draw.rect(screen, (60, 0, 0), (bx, by, 60, 5))
            pygame.draw.rect(screen, (120, 220, 120),
                             (bx, by, int(60 * ratio), 5))
            pygame.draw.rect(screen, (200, 200, 200), (bx, by, 60, 5), 1)
            lbl = font.render(f"Soldier {s._hp}", True, (220, 220, 220))
            screen.blit(lbl, (bx, by - 14))
        else:
            dead = big.render("SOLDIER DEAD", True, (255, 80, 80))
            screen.blit(dead, (int(s.x - 80), int(s.y - 12)))

    # Heroes (commander) — vẽ bằng helper từ _demo_dummies
    from _demo_dummies import draw_hero  # noqa: E402
    for h in heroes:
        draw_hero(screen, font, h)

    # Beast (sprite or fallback)
    beast.draw(screen)
    if beast._sprite_sheet is None:
        bx_t, by_t = int(beast.x), int(beast.y)
        pygame.draw.circle(screen, (140, 80, 40), (bx_t, by_t), 32)
        pygame.draw.circle(screen, (220, 180, 120), (bx_t, by_t), 32, 2)
        angle_map = {0: -math.pi / 2, 1: math.pi, 2: math.pi / 2, 3: 0.0}
        ang = angle_map[beast._direction]
        tip_x = bx_t + int(math.cos(ang) * 38)
        tip_y = by_t + int(math.sin(ang) * 38)
        pygame.draw.line(screen, (255, 255, 255),
                         (bx_t, by_t), (tip_x, tip_y), 3)

    # HUD
    nearest, ndist = _find_nearest_tower_alive()
    if nearest is not None:
        in_range = ndist <= beast.THROW_RANGE
        nearest_str = (f"{nearest._label} @ {ndist:.0f}px "
                       f"({'IN RANGE' if in_range else 'OUT OF RANGE'})")
    else:
        nearest_str = "—"

    if beast._is_attacking:
        state = "THROW"
        row_info = (f"row={beast._ATTACK_ROWS[beast._direction]}  "
                    f"col={beast._anim_col}/{beast._ATTACK_FRAMES - 1}  "
                    f"(release@{beast._ROCK_RELEASE_FRAME})")
    elif beast._is_moving and beast._is_running:
        state, row_info = "RUN", f"row={beast._RUN_ROWS[beast._direction]}"
    elif beast._is_moving:
        state, row_info = "WALK", f"row={beast._WALK_ROWS[beast._direction]}"
    else:
        state, row_info = "IDLE", f"row={beast._WALK_ROWS[beast._direction]}"

    cd = max(0.0, beast._throw_timer)
    cd_str = "READY" if cd <= 0 else f"cooldown {cd:.1f}s"

    hud = [
        f"sprite  : Assets/Boss/beast.png  rock: Assets/Rock Pile (row=9, col=5, 85×85)",
        f"state   : {state}   dir={DIR_NAMES[beast._direction]}   {row_info}",
        f"hp      : {beast._hp}/{beast._max_hp}",
        f"throw   : {cd_str}   range={beast.THROW_RANGE:.0f}px",
        f"physics : v={beast._ROCK_VELOCITY:.0f}px/s  angle={beast._ROCK_ANGLE_DEG:.0f}°  "
        f"g={beast._ROCK_GRAVITY:.0f}px/s²  AoE={beast._ROCK_AOE_RADIUS:.0f}px",
        f"damage  : main={beast._ROCK_DAMAGE_MAIN}  splash={beast._ROCK_DAMAGE_SPLASH}  "
        f"(dtype='rock')",
        f"nearest : {nearest_str}",
        f"rocks   : {len(beast._rocks)} in flight",
        f"mode    : {'AUTO' if auto_mode else 'MANUAL'}",
        "",
        "WASD=move  Shift=run  SPACE=throw  T=auto  R=respawn  Q=quit",
    ]
    for i, line in enumerate(hud):
        surf = font.render(line, True, (220, 220, 220))
        screen.blit(surf, (12, 12 + i * 18))

    pygame.display.flip()

pygame.quit()
sys.exit()
