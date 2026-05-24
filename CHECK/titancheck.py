"""titancheck.py — Demo trực quan RegularTitan (walk/run/attack + HP threshold).

Phím điều khiển:
  WASD          — di chuyển Titan (cập nhật hướng nhìn)
  Shift + WASD  — chạy (Run animation, tốc độ ×1.6)
  SPACE         — kích hoạt animation Attack (loop 6 frame, 1 giây)
  H             — gây 10% max HP damage (test ngưỡng HP < 40% → HeavyStrike)
  B             — toggle berserk/normal (chuyển đổi HeavyStrike ↔ MeleeRush)
  R             — respawn với variant ngẫu nhiên mới (titan2/4/5/6/7)
  Q / ESC       — thoát

Mục đích: kiểm tra:
  • Random sprite variant lúc spawn
  • Hàng spritesheet đúng cho từng hướng N/W/S/E
  • Walk (rows 8–11, 9 frame) vs Run (rows 37–40, 8 frame)
  • Attack (rows 12–15, 6 frame) loop 1 giây
  • Khi HP tụt dưới 40% → strategy chuyển sang HeavyStrikeStrategy (in log)
  • B key: toggle berserk thủ công
"""
import sys
import os
import types

import pygame


# ── 1. Tạo mock modules trước khi import Titan ───────────────────────────────

def _mod(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


# core.entity — Entity base
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


_core_mod   = _mod('core')
_entity_mod = _mod('core.entity')
_entity_mod.Entity = _MockEntity


# core.interfaces — IAttackable, IMovable (chỉ cần là class trống)
class _IAttackable:
    pass


class _IMovable:
    pass


_iface_mod = _mod('core.interfaces')
_iface_mod.IAttackable = _IAttackable
_iface_mod.IMovable    = _IMovable


# core.event_bus — Singleton giả
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


# characters.titans.attackstrategy — import 4 strategy thật từ AttackStrategy.py
_chars_mod  = _mod('characters')
_titans_mod = _mod('characters.titans')

# File này nằm trong Check/ — sys.path phải trỏ về parent (chứa Titan.py, AttackStrategy.py)
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


# systems.world_query — hỗ trợ soldier/hero/tower pool cho demo
class _MockWorldQuery:
    soldiers: list = []
    commanders: list = []   # mapping 'commander' → hero
    towers: list = []

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


_sys_mod = _mod('systems')
_wq_mod  = _mod('systems.world_query')
_wq_mod.WorldQuery = _MockWorldQuery


# ── 2. Import RegularTitan thật ──────────────────────────────────────────────

from Titan import RegularTitan  # noqa: E402
from AttackStrategy import MeleeRushStrategy, HeavyStrikeStrategy  # noqa: E402


# ── 3. Pygame setup ──────────────────────────────────────────────────────────

pygame.init()
W, H   = 960, 680
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "RegularTitan Demo  (WASD=move  Shift=run  SPACE=attack  H=-10%HP  B=berserk  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font  = pygame.font.SysFont("Consolas", 15)


# ── 4. Spawn titan ───────────────────────────────────────────────────────────

CX, CY     = W // 2, H // 2
WALK_SPEED = 90.0
RUN_SPEED  = 145.0


def make_titan() -> RegularTitan:
    t = RegularTitan(float(CX), float(CY), {
        'hp': 1000,
        'speed': WALK_SPEED,
        'damage': 20,
    })
    # Thử load sprite ngay để biết path có đúng không
    t._load_sprite()
    sprite_ok = t._sprite_sheet is not None
    sprite_path = os.path.join(
        os.path.dirname(os.path.abspath(
            sys.modules['Titan'].__file__ if 'Titan' in sys.modules else __file__
        )),
        'Assets', 'Titan', f'regular{t._variant}.png',
    )
    print(f"\n=== Spawn RegularTitan  variant=regular{t._variant}.png  "
          f"HP={t._hp}  sprite={'OK' if sprite_ok else 'MISSING'} ===")
    if not sprite_ok:
        print(f"  [WARN] Sprite không tải được: {sprite_path}")
        print(f"  → Titan sẽ hiển thị bằng hình tròn thay thế")
    return t


titan = make_titan()


# ── 4b. Spawn entities (10 soldier + 3 hero + 3 tower) ───────────────────────
from _demo_dummies import spawn_world, draw_all, update_all  # noqa: E402

soldiers, heroes, towers = spawn_world(W, H, titan.x, titan.y)
_MockWorldQuery.soldiers   = soldiers
_MockWorldQuery.commanders = heroes
_MockWorldQuery.towers     = towers
print(f"[Spawn] soldiers={len(soldiers)}  heroes={len(heroes)}  towers={len(towers)}")


# ── 5. Vòng lặp chính ────────────────────────────────────────────────────────

DIR_NAMES = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}

ATTACK_RANGE = 60.0   # tầm đánh melee của RegularTitan


def _distance(a, b) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _target_name(e) -> str:
    """Tên hiển thị an toàn cho mọi loại target."""
    return getattr(e, '_label', None) or getattr(e, 'name', None) \
        or type(e).__name__


def _all_targets() -> list:
    """Gộp MỌI mục tiêu có thể đánh: soldier + hero + tower.

    Đọc động biến module-level → cập nhật đúng sau khi bấm R (respawn).
    """
    return list(soldiers) + list(heroes) + list(towers)


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
running = True

while running:
    dt = min(clock.tick(60) / 1000.0, 0.05)  # clamp dt tránh lag spike

    # ── Input ────────────────────────────────────────────────────────────────
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

            elif event.key == pygame.K_SPACE:
                titan.trigger_attack()
                # Đánh mục tiêu gần nhất trong MỌI loại (soldier/hero/
                # tower). RegularTitan dùng MeleeRushStrategy — mọi
                # loại đều nhận damage qua execute().
                target, dist = _find_nearest_alive(titan, _all_targets())
                if target is not None and dist <= ATTACK_RANGE:
                    print(f"[ATTACK]  dir={DIR_NAMES[titan._direction]}  "
                          f"row={titan._ATTACK_ROWS[titan._direction]}  "
                          f"target={_target_name(target)}  "
                          f"strategy={type(titan._attack_strategy).__name__}")
                    titan._attack_strategy.execute(titan, target)
                elif target is not None:
                    print(f"[ATTACK miss]  nearest={_target_name(target)} "
                          f"dist={dist:.0f} > {ATTACK_RANGE:.0f}")
                else:
                    print(f"[ATTACK miss]  hết mục tiêu")

            elif event.key == pygame.K_h:
                dmg = int(titan._max_hp * 0.10)
                titan._hp = max(0, titan._hp - dmg)
                print(f"[HP -{dmg}]  HP={titan._hp}/{titan._max_hp}  "
                      f"({titan._hp / titan._max_hp * 100:.0f}%)")

            elif event.key == pygame.K_b:
                # Toggle berserk: normal ↔ heavy
                if not titan._heavy_mode:
                    titan._heavy_mode      = True
                    titan._attack_strategy = HeavyStrikeStrategy()
                    print(f"[BERSERK ON]   → HeavyStrikeStrategy  "
                          f"(damage ×{titan._attack_strategy._damage_mult})")
                else:
                    titan._heavy_mode      = False
                    titan._attack_strategy = MeleeRushStrategy()
                    print(f"[BERSERK OFF]  → MeleeRushStrategy")

            elif event.key == pygame.K_r:
                titan = make_titan()
                soldiers, heroes, towers = spawn_world(W, H, titan.x, titan.y)
                _MockWorldQuery.soldiers   = soldiers
                _MockWorldQuery.commanders = heroes
                _MockWorldQuery.towers     = towers
                print(f"[Respawn] soldiers={len(soldiers)}  "
                      f"heroes={len(heroes)}  towers={len(towers)}")

    # ── Movement (chặn khi đang đánh) ────────────────────────────────────────
    if not titan._is_attacking:
        keys = pygame.key.get_pressed()
        titan._is_running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        speed = RUN_SPEED if titan._is_running else WALK_SPEED

        dx = dy = 0.0
        if keys[pygame.K_w]:
            dy -= speed * dt
        if keys[pygame.K_s]:
            dy += speed * dt
        if keys[pygame.K_a]:
            dx -= speed * dt
        if keys[pygame.K_d]:
            dx += speed * dt

        # Hướng nhìn: ưu tiên trục ngang (A/D) hơn trục dọc (W/S).
        #   W+D → D, A+W → A. Khi A+D (hoặc W+S) triệt tiêu nhau → giữ
        #   hướng cũ, không đổi.
        if dx < 0:
            titan._direction = 1   # West  (A)
        elif dx > 0:
            titan._direction = 3   # East  (D)
        elif dy < 0:
            titan._direction = 0   # North (W)
        elif dy > 0:
            titan._direction = 2   # South (S)

        titan._is_moving = (dx != 0.0 or dy != 0.0)
        if titan._is_moving:
            titan.x = max(32.0, min(float(W - 32), titan.x + dx))
            titan.y = max(32.0, min(float(H - 32), titan.y + dy))
    else:
        titan._is_moving = False

    # ── Animation state (không gọi titan.update() vì mock WorldQuery không có target) ──
    if titan._is_attacking:
        titan._attack_anim_timer -= dt
        titan._anim_timer += dt
        if titan._anim_timer >= 1.0 / titan._ATTACK_FPS:
            titan._anim_timer -= 1.0 / titan._ATTACK_FPS
            titan._anim_col = (titan._anim_col + 1) % titan._ATTACK_FRAMES
        if titan._attack_anim_timer <= 0:
            titan._is_attacking = False
            titan._anim_col     = 0
            titan._anim_timer   = 0.0
    elif titan._is_moving:
        frames = titan._RUN_FRAMES if titan._is_running else titan._WALK_FRAMES
        titan._anim_timer += dt
        if titan._anim_timer >= 1.0 / titan._ANIM_FPS:
            titan._anim_timer -= 1.0 / titan._ANIM_FPS
            titan._anim_col = (titan._anim_col + 1) % frames
    else:
        titan._anim_col   = 0
        titan._anim_timer = 0.0

    # ── HP threshold: tự động chuyển HeavyStrike khi máu < 40% ──────────────
    if titan._max_hp > 0 and (titan._hp / titan._max_hp) < titan._HEAVY_HP_RATIO \
            and not titan._heavy_mode:
        titan._heavy_mode      = True
        titan._attack_strategy = HeavyStrikeStrategy()
        print(f"[AUTO HEAVY]  HP {titan._hp}/{titan._max_hp} < 40% "
              f"→ switch HeavyStrikeStrategy")

    # ── Draw ─────────────────────────────────────────────────────────────────
    screen.fill((28, 32, 38))

    # Lưới mỏng
    for gx in range(0, W, 64):
        pygame.draw.line(screen, (45, 50, 58), (gx, 0), (gx, H))
    for gy in range(0, H, 64):
        pygame.draw.line(screen, (45, 50, 58), (0, gy), (W, gy))

    # Update + Vẽ entities (soldier/hero/tower) DƯỚI titan
    update_all(dt, soldiers, heroes, towers)
    draw_all(screen, font, soldiers, heroes, towers)

    # Vẽ Titan (sprite hoặc fallback hình tròn nếu sprite thiếu)
    titan.draw(screen)
    if titan._sprite_sheet is None:
        color = (255, 160, 0) if titan._heavy_mode else (200, 80, 80)
        cx_t, cy_t = int(titan.x), int(titan.y)
        pygame.draw.circle(screen, color, (cx_t, cy_t), 28)
        pygame.draw.circle(screen, (255, 255, 255), (cx_t, cy_t), 28, 2)
        # Chỉ hướng nhìn bằng tam giác nhỏ
        import math
        angle_map = {0: -math.pi / 2, 1: math.pi, 2: math.pi / 2, 3: 0.0}
        ang = angle_map[titan._direction]
        tip_x = cx_t + int(math.cos(ang) * 34)
        tip_y = cy_t + int(math.sin(ang) * 34)
        pygame.draw.line(screen, (255, 255, 255), (cx_t, cy_t), (tip_x, tip_y), 3)

    # HP bar
    bar_w    = 80
    hp_ratio = titan._hp / titan._max_hp if titan._max_hp > 0 else 0
    bx = int(titan.x - bar_w // 2)
    by = int(titan.y - 48)
    pygame.draw.rect(screen, (60, 0, 0),   (bx, by, bar_w, 6))
    bar_color = (220, 40, 40) if hp_ratio >= 0.4 else (255, 180, 0)
    pygame.draw.rect(screen, bar_color,    (bx, by, int(bar_w * hp_ratio), 6))
    pygame.draw.rect(screen, (200, 200, 200), (bx, by, bar_w, 6), 1)

    # Trạng thái HUD
    if titan._is_attacking:
        state = "ATTACK"
        row   = titan._ATTACK_ROWS[titan._direction]
    elif titan._is_moving and titan._is_running:
        state = "RUN"
        row   = titan._RUN_ROWS[titan._direction]
    elif titan._is_moving:
        state = "WALK"
        row   = titan._WALK_ROWS[titan._direction]
    else:
        state = "IDLE"
        row   = titan._WALK_ROWS[titan._direction]

    strategy_name = type(titan._attack_strategy).__name__
    sprite_status = "OK" if titan._sprite_sheet is not None else "MISSING (vẽ hình tròn)"

    hud_lines = [
        f"variant : titan{titan._variant}.png  [{sprite_status}]",
        f"state   : {state}   dir={DIR_NAMES[titan._direction]}   row={row}   col={titan._anim_col}",
        f"hp      : {titan._hp}/{titan._max_hp}  ({hp_ratio*100:.0f}%)",
        f"strategy: {strategy_name}{'  [BERSERK/HEAVY]' if titan._heavy_mode else ''}",
        "",
        "WASD=move  Shift=run  SPACE=attack  H=-10%HP  B=berserk  R=respawn  Q=quit",
    ]
    for i, line in enumerate(hud_lines):
        surf = font.render(line, True, (220, 220, 220))
        screen.blit(surf, (12, 12 + i * 18))

    pygame.display.flip()

pygame.quit()
sys.exit()
