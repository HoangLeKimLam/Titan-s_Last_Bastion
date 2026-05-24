"""armoredcheck.py — Demo trực quan ArmoredTitan (walk/run/dash + armor break).

Phím điều khiển:
  WASD          — di chuyển Titan (cập nhật hướng nhìn)
  Shift + WASD  — chạy (Run animation, tốc độ ×1.6)
  SPACE + WASD  — DASH (Ram skill) theo hướng đang giữ
                  • tốc độ ×1.5 Run, đi đến khi va chạm hoặc 300 px
                  • va chạm dummy → ArmoredRamStrategy.execute()
  J             — bắn anti_armor 100 dmg vào titan (test giáp vỡ → HeavyStrike)
  H             — gây 50 normal dmg (kiểm tra giáp chặn 60%)
  R             — respawn titan + dummy mới
  Q / ESC       — thoát

Mục đích kiểm tra:
  • Walk (rows 8–11, 9 frame) vs Run (rows 37–40, 8 frame)
  • Dash (tái dùng Run rows, FPS ×2, speed ×1.5 so với Run)
  • Khi giáp còn: damage normal bị chặn 60%
  • Khi anti_armor → giáp vỡ → strategy switch sang HeavyStrikeStrategy
  • ArmoredRamStrategy.execute() gọi đúng khi dash va chạm dummy
"""
import sys
import os
import math
import types

import pygame


# ── 1. Mock modules trước khi import Titan ───────────────────────────────────

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
# Inject TẤT CẢ strategy mà Titan.py import (Wolf/TowerHunter/SoldierHunter cũng được import)
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


# ── 2. Import ArmoredTitan thật ──────────────────────────────────────────────

from Titan import ArmoredTitan  # noqa: E402
from AttackStrategy import HeavyStrikeStrategy  # noqa: E402


# ── 3. Dummy target để test va chạm dash + take_damage ───────────────────────

class DummyTarget:
    """Target tĩnh để test ArmoredRamStrategy.execute() và logger damage."""

    def __init__(self, x: float, y: float, hp: int = 500):
        self.x = float(x)
        self.y = float(y)
        self._hp     = hp
        self._max_hp = hp
        self.is_alive = True

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp -= amount
        print(f"  [Dummy] take_damage(amount={amount}, dtype='{dtype}')  "
              f"→ HP={max(0, self._hp)}/{self._max_hp}")
        if self._hp <= 0:
            self.is_alive = False


# ── 4. Pygame setup ──────────────────────────────────────────────────────────

pygame.init()
W, H   = 1000, 720
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "ArmoredTitan Demo  (WASD=move  Shift=run  SPACE+WASD=DASH  "
    "J=anti_armor  H=normal_dmg  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font  = pygame.font.SysFont("Consolas", 15)
big   = pygame.font.SysFont("Consolas", 22, bold=True)


# ── 5. Spawn ─────────────────────────────────────────────────────────────────

CX, CY     = 200, H // 2
WALK_SPEED = 90.0
RUN_SPEED  = 145.0


def make_titan() -> ArmoredTitan:
    t = ArmoredTitan(float(CX), float(CY), {
        'hp': 1000,
        'speed': WALK_SPEED,
        'damage': 25,
    })
    t._load_sprite()
    sprite_ok = t._sprite_sheet is not None
    sprite_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.modules['Titan'].__file__)),
        'Assets', 'Special', 'armored.png',
    )
    print(f"\n=== Spawn ArmoredTitan  HP={t._hp}  armor=INTACT  "
          f"sprite={'OK' if sprite_ok else 'MISSING'} ===")
    if not sprite_ok:
        print(f"  [WARN] Sprite không tải được: {sprite_path}")
        print(f"  → Titan sẽ hiển thị bằng hình tròn xám (giáp)")
    return t


def make_dummy() -> DummyTarget:
    return DummyTarget(W - 250, H // 2, hp=500)


titan = make_titan()
dummy = make_dummy()


# ── 5b. Spawn 10 soldier + 3 hero + 3 tower (background entities) ────────────
from _demo_dummies import spawn_world, draw_all, update_all  # noqa: E402

soldiers, heroes, towers = spawn_world(W, H, titan.x, titan.y)
_MockWorldQuery.soldiers   = soldiers
_MockWorldQuery.commanders = heroes
_MockWorldQuery.towers     = towers
print(f"[Spawn] soldiers={len(soldiers)}  heroes={len(heroes)}  towers={len(towers)}")


# ── 6. Helpers ───────────────────────────────────────────────────────────────

DIR_NAMES = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}


def _wasd_vector(keys) -> tuple:
    dx = dy = 0.0
    if keys[pygame.K_w]:
        dy -= 1.0
    if keys[pygame.K_s]:
        dy += 1.0
    if keys[pygame.K_a]:
        dx -= 1.0
    if keys[pygame.K_d]:
        dx += 1.0
    return dx, dy


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


# ── 7. Vòng lặp chính ────────────────────────────────────────────────────────

running = True

while running:
    dt = min(clock.tick(60) / 1000.0, 0.05)
    keys = pygame.key.get_pressed()

    # ── Input ────────────────────────────────────────────────────────────────
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

            elif event.key == pygame.K_SPACE:
                # Phân nhánh theo trạng thái giáp:
                #   • Giáp còn → trigger_dash (cần WASD chọn hướng)
                #   • Giáp vỡ → trigger_attack (melee đứng tại chỗ, range 60px)
                if titan._armor_intact:
                    dx, dy = _wasd_vector(keys)
                    if dx == 0.0 and dy == 0.0:
                        print("[DASH miss] Phải giữ WASD khi bấm SPACE để chọn hướng")
                    else:
                        started = titan.trigger_dash(dx, dy, RUN_SPEED)
                        if started:
                            print(f"[DASH start] dir=({dx:+.0f},{dy:+.0f})  "
                                  f"speed={titan._dash_speed:.0f} px/s  "
                                  f"max_dist={titan._DASH_MAX_DIST:.0f}px  "
                                  f"ram_hits={titan._ram_hits}/{titan._HITS_TO_BREAK}")
                else:
                    # Melee post-break — đánh mục tiêu gần nhất trong MỌI
                    # loại (dummy/soldier/hero/tower), tầm 60px.
                    started = titan.trigger_attack()
                    if started:
                        target, dist = _find_nearest_alive(
                            titan, _all_targets())
                        if target is not None and dist <= 60.0:
                            print(f"[MELEE]  HeavyStrikeStrategy.execute()  "
                                  f"target={_target_name(target)}  "
                                  f"damage_base={titan._damage} ×2.0 = "
                                  f"{int(titan._damage * 2.0)}")
                            titan._attack_strategy.execute(titan, target)
                        elif target is not None:
                            print(f"[MELEE miss]  "
                                  f"nearest={_target_name(target)} "
                                  f"dist={dist:.0f} > 60px")
                        else:
                            print(f"[MELEE miss]  hết mục tiêu")

            elif event.key == pygame.K_j:
                # Anti-armor bolt: 100 dmg, dtype='anti_armor'
                was_intact = titan._armor_intact
                titan.take_damage(100, 'anti_armor')
                if was_intact and not titan._armor_intact:
                    print(f"[ARMOR BROKEN by anti_armor]  "
                          f"antiarmor_hits={titan._antiarmor_hits}/{titan._HITS_TO_BREAK}  "
                          f"HP={titan._hp}/{titan._max_hp}  "
                          f"strategy → {type(titan._attack_strategy).__name__}")
                else:
                    print(f"[ANTI_ARMOR -100]  HP={titan._hp}/{titan._max_hp}  "
                          f"antiarmor_hits={titan._antiarmor_hits}/{titan._HITS_TO_BREAK}")

            elif event.key == pygame.K_h:
                # Normal damage 50 — bị chặn 60% nếu giáp còn
                hp_before = titan._hp
                titan.take_damage(50, 'normal')
                actual = hp_before - titan._hp
                shield = "GIÁP CHẶN 60%" if titan._armor_intact else "GIÁP VỠ - full damage"
                print(f"[NORMAL -50 → -{actual}]  HP={titan._hp}/{titan._max_hp}  ({shield})")

            elif event.key == pygame.K_r:
                titan = make_titan()
                dummy = make_dummy()
                soldiers, heroes, towers = spawn_world(W, H, titan.x, titan.y)
                _MockWorldQuery.soldiers   = soldiers
                _MockWorldQuery.commanders = heroes
                _MockWorldQuery.towers     = towers
                print(f"[Respawn] soldiers={len(soldiers)}  "
                      f"heroes={len(heroes)}  towers={len(towers)}")

    # ── Movement (chặn khi đang dash) ────────────────────────────────────────
    if titan._is_dashing:
        # Bước dash kế tiếp + check collision với dummy
        new_x, new_y, finished = titan.dash_step(
            dt, world_bounds=(32.0, 32.0, float(W - 32), float(H - 32))
        )
        titan.x = new_x
        titan.y = new_y

        # Kiểm tra va chạm với MỌI loại (dummy/soldier/hero/tower) →
        # con gần nhất trong _DASH_HIT_RADIUS sẽ ăn ArmoredRamStrategy.
        hit_target, hit_dist = _find_nearest_alive(titan, _all_targets())
        if hit_target is not None and hit_dist < titan._DASH_HIT_RADIUS:
            mult = getattr(titan._attack_strategy, '_damage_mult', '?')
            print(f"[DASH HIT]  ArmoredRamStrategy.execute()  "
                  f"target={_target_name(hit_target)}  "
                  f"damage_base={titan._damage}  ×{mult}  "
                  f"ram_hits={titan._ram_hits + 1}/{titan._HITS_TO_BREAK}")
            broke, cause = titan.end_dash_on_hit(hit_target)
            if broke:
                print(f"[ARMOR BROKEN by {cause}]  "
                      f"ram_hits={titan._ram_hits}/{titan._HITS_TO_BREAK}  "
                      f"strategy → {type(titan._attack_strategy).__name__}  "
                      f"(Dash khóa, dùng SPACE để melee)")

        titan._is_moving = False
    else:
        # Walk / Run thông thường
        titan._is_running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        speed = RUN_SPEED if titan._is_running else WALK_SPEED

        dx, dy = _wasd_vector(keys)
        if dx != 0.0 and dy != 0.0:
            inv = 1.0 / math.sqrt(2.0)
            dx *= inv
            dy *= inv
        mx = dx * speed * dt
        my = dy * speed * dt

        if mx != 0.0 or my != 0.0:
            titan._is_moving = True
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
            titan.x = max(32.0, min(float(W - 32), titan.x + mx))
            titan.y = max(32.0, min(float(H - 32), titan.y + my))
        else:
            titan._is_moving = False

    # ── Animation ────────────────────────────────────────────────────────────
    titan.update_anim(dt)

    # ── Draw ─────────────────────────────────────────────────────────────────
    screen.fill((28, 32, 38))

    # Lưới
    for gx in range(0, W, 64):
        pygame.draw.line(screen, (45, 50, 58), (gx, 0), (gx, H))
    for gy in range(0, H, 64):
        pygame.draw.line(screen, (45, 50, 58), (0, gy), (W, gy))

    # Update + Draw background entities (10 soldier + 3 hero + 3 tower)
    update_all(dt, soldiers, heroes, towers)
    draw_all(screen, font, soldiers, heroes, towers)

    # Dummy target
    if dummy.is_alive:
        dr = 36
        pygame.draw.circle(screen, (80, 100, 140), (int(dummy.x), int(dummy.y)), dr)
        pygame.draw.circle(screen, (180, 200, 240), (int(dummy.x), int(dummy.y)), dr, 2)
        # HP bar dummy
        ratio = dummy._hp / dummy._max_hp if dummy._max_hp > 0 else 0
        bx = int(dummy.x - 40)
        by = int(dummy.y - dr - 12)
        pygame.draw.rect(screen, (60, 0, 0), (bx, by, 80, 6))
        pygame.draw.rect(screen, (80, 180, 240), (bx, by, int(80 * ratio), 6))
        pygame.draw.rect(screen, (200, 200, 200), (bx, by, 80, 6), 1)
        label = font.render(f"DUMMY {dummy._hp}/{dummy._max_hp}", True, (220, 220, 220))
        screen.blit(label, (bx - 4, by - 16))
    else:
        dead = big.render("DUMMY DEAD", True, (255, 80, 80))
        screen.blit(dead, (int(dummy.x - 70), int(dummy.y - 12)))

    # Titan
    titan.draw(screen)
    if titan._sprite_sheet is None:
        # Fallback hình tròn — xám = giáp còn, cam = giáp vỡ
        color = (160, 160, 170) if titan._armor_intact else (220, 140, 60)
        cx_t, cy_t = int(titan.x), int(titan.y)
        pygame.draw.circle(screen, color, (cx_t, cy_t), 30)
        pygame.draw.circle(screen, (255, 255, 255), (cx_t, cy_t), 30, 2)
        angle_map = {0: -math.pi / 2, 1: math.pi, 2: math.pi / 2, 3: 0.0}
        ang = angle_map[titan._direction]
        tip_x = cx_t + int(math.cos(ang) * 36)
        tip_y = cy_t + int(math.sin(ang) * 36)
        pygame.draw.line(screen, (255, 255, 255), (cx_t, cy_t), (tip_x, tip_y), 3)

    # Hiển thị vệt dash khi đang dash (cho thấy hướng + còn lại bao nhiêu)
    if titan._is_dashing:
        remaining = titan._dash_dist_remaining
        ex = titan.x + titan._dash_dx * remaining
        ey = titan.y + titan._dash_dy * remaining
        pygame.draw.line(screen, (255, 200, 80),
                         (int(titan.x), int(titan.y)),
                         (int(ex), int(ey)), 2)

    # HP bar titan
    bar_w = 80
    hp_ratio = titan._hp / titan._max_hp if titan._max_hp > 0 else 0
    bx = int(titan.x - bar_w // 2)
    by = int(titan.y - 50)
    pygame.draw.rect(screen, (60, 0, 0),  (bx, by, bar_w, 6))
    pygame.draw.rect(screen, (220, 40, 40), (bx, by, int(bar_w * hp_ratio), 6))
    pygame.draw.rect(screen, (200, 200, 200), (bx, by, bar_w, 6), 1)
    # Armor indicator
    armor_text = "ARMOR" if titan._armor_intact else "BROKEN"
    armor_col  = (160, 200, 240) if titan._armor_intact else (255, 140, 60)
    armor_surf = font.render(armor_text, True, armor_col)
    screen.blit(armor_surf, (bx, by - 16))

    # HUD
    if titan._is_attacking:
        state = "MELEE"
        row   = titan._ATTACK_ROWS[titan._direction]
    elif titan._is_dashing:
        state = "DASH"
        row   = titan._DASH_ROWS[titan._direction]
    elif titan._is_moving and titan._is_running:
        state = "RUN"
        row   = titan._RUN_ROWS[titan._direction]
    elif titan._is_moving:
        state = "WALK"
        row   = titan._WALK_ROWS[titan._direction]
    else:
        state = "IDLE"
        row   = titan._WALK_ROWS[titan._direction]

    sprite_status = "OK" if titan._sprite_sheet is not None else "MISSING (fallback)"
    strategy_name = type(titan._attack_strategy).__name__

    if titan._armor_intact:
        armor_line  = (f"armor   : INTACT (chặn 60% normal)  "
                       f"ram_hits={titan._ram_hits}/{titan._HITS_TO_BREAK}  "
                       f"antiarmor_hits={titan._antiarmor_hits}/{titan._HITS_TO_BREAK}")
        attack_hint = "SPACE+WASD=DASH (cần 5 hit để vỡ giáp)"
    else:
        armor_line  = (f"armor   : BROKEN by {titan._break_cause}  "
                       f"(full damage, Dash khóa, dùng melee)")
        attack_hint = "SPACE=MELEE (đứng tại chỗ, range 60px → HeavyStrike ×2)"

    hud = [
        f"sprite  : Assets/Special/armored.png  [{sprite_status}]",
        f"state   : {state}   dir={DIR_NAMES[titan._direction]}   "
        f"row={row}   col={titan._anim_col}",
        f"hp      : {titan._hp}/{titan._max_hp}  ({hp_ratio*100:.0f}%)",
        armor_line,
        f"strategy: {strategy_name}",
        "",
        f"WASD=move  Shift=run  {attack_hint}",
        "J=anti_armor (-100, cần 5 hit)  H=normal_dmg (-50)  R=respawn  Q=quit",
    ]
    for i, line in enumerate(hud):
        surf = font.render(line, True, (220, 220, 220))
        screen.blit(surf, (12, 12 + i * 18))

    pygame.display.flip()

pygame.quit()
sys.exit()
