"""foundingcheck.py — Demo trực quan FoundingTitan (3 phase + summon vòng tròn).

Phím điều khiển:
  WASD          — di chuyển Founding manual (cập nhật hướng nhìn)
  SPACE         — LUÔN trigger attack animation (HeavyStrike); damage chỉ
                  áp khi dummy gần nhất trong tầm 80px
  N             — force trigger 1 đợt summon (chỉ chạy khi đang P2)
  1 / 2 / 3     — set HP = 90% / 50% / 15% (test phase transition)
  J             — +10% HP (test sticky lock — vào P3 rồi hồi vẫn không summon)
  R             — respawn founding + dummies (xóa hết minion)
  Q / ESC       — thoát

LƯU Ý: Founding KHÔNG có Run — chỉ Walk khi di chuyển.

Mục đích kiểm tra:
  • Phase 1 (HP > 60%): HeavyStrike (×2 damage) range 80px, cooldown 3s
  • Phase 2 (20% < HP ≤ 60%): tự động summon mỗi cycle
      - Animation rows 1-4 (N/W/S/E), 6 frame, 6 FPS = 1s
      - Hold col=5 trong 2s rồi spawn 10 minion (random 8 loại titan)
      - 10 minion chia ngẫu nhiên variant 1-8, đứng vòng tròn 180px
      - Hướng minion = hướng founding
      - Cooldown 10s trước đợt kế tiếp
  • Phase 3 (HP ≤ 20%): TẮT summon VĨNH VIỄN (sticky)
      - Bấm J để hồi HP > 20% — summon vẫn không bật lại
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


# ── 2. Mock characters.titans (Titan base + RegularTitan + strategies) ──────

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
_strat_mod.GroundSlamStrategy     = _atk_src.GroundSlamStrategy
_strat_mod.Explosion              = _atk_src.Explosion
# NHÓM 6 — Boss.py import lại RockProjectile/HeatParticle từ attackstrategy
_strat_mod.RockProjectile         = _atk_src.RockProjectile
_strat_mod.HeatParticle           = _atk_src.HeatParticle


import Titan as _titan_src  # noqa: E402
_titan_mod = _mod('characters.titans.titan')
_titan_mod.Titan         = _titan_src.Titan
# FoundingTitan._release_summon import cả 4 loại minion để spawn đa dạng
_titan_mod.RegularTitan  = _titan_src.RegularTitan
_titan_mod.Wolf          = _titan_src.Wolf
_titan_mod.TowerHunter   = _titan_src.TowerHunter
_titan_mod.SoldierHunter = _titan_src.SoldierHunter


# ── 3. Mock WorldQuery ───────────────────────────────────────────────────────

class _MockWorldQuery:
    soldiers:   list = []
    towers:     list = []
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
    def find_nearest_attacker(cls, _titan):
        """Lấy soldier/tower gần nhất (đại diện cho 'attacker')."""
        best, best_d = None, float('inf')
        for e in cls.soldiers + cls.towers:
            if not e.is_alive:
                continue
            d = ((e.x - _titan.x) ** 2 + (e.y - _titan.y) ** 2) ** 0.5
            if d < best_d:
                best_d, best = d, e
        return best

    @classmethod
    def find_nearest(cls, cx: float, cy: float, entity_type: str):
        pool = getattr(cls, entity_type + 's', [])
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


# ── 4. Mock patterns.decorator (Boss.py có thể import BurnDecorator) ────────

class _BurnDecorator:
    def __init__(self, entity, damage_per_sec: float, duration: float):
        pass


_mod('patterns')
_pd_mod = _mod('patterns.decorator')
_pd_mod.BurnDecorator = _BurnDecorator


# ── 5. Import FoundingTitan thật ─────────────────────────────────────────────

from Boss import FoundingTitan  # noqa: E402


# ── 6. Dummies ───────────────────────────────────────────────────────────────

class SoldierDummy:
    def __init__(self, x: float, y: float, hp: int = 200, label: str = "S"):
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
        print(f"  [{self._label:8s}] take_damage(amount={amount:>3}, dtype='{dtype}')  "
              f"→ HP={self._hp:>3}/{self._max_hp}")
        if self._hp <= 0:
            self.is_alive = False

    def update(self, dt: float) -> None:
        if self._hit_flash > 0:
            self._hit_flash = max(0.0, self._hit_flash - dt)


# ── 7. Pygame setup ──────────────────────────────────────────────────────────

pygame.init()
W, H   = 1280, 800
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "FoundingTitan Demo  (WASD=move  SPACE=attack  N=summon  1/2/3=HP  J=+10%HP  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font  = pygame.font.SysFont("Consolas", 15)
big   = pygame.font.SysFont("Consolas", 22, bold=True)


# ── 8. Spawn ─────────────────────────────────────────────────────────────────

FX, FY = W // 2, H // 2
WALK_SPEED = 70.0


def make_founding() -> FoundingTitan:
    f = FoundingTitan(float(FX), float(FY), {
        'hp': 2000,
        'speed': WALK_SPEED,
        'damage': 50,
    })
    f._load_sprite()
    sprite_ok = f._sprite_sheet is not None
    print(f"\n=== Spawn FoundingTitan  HP={f._hp}  damage={f._damage}  "
          f"sprite={'OK' if sprite_ok else 'MISSING'} ===")
    if not sprite_ok:
        print(f"  [WARN] Assets/Boss/founding.png không tải được → fallback hình tròn vàng")
    return f


def make_dummies() -> list:
    """2 soldier dummy để test P1 attack."""
    return [
        SoldierDummy(FX - 220, FY,       hp=400, label="Sol-L"),
        SoldierDummy(FX + 220, FY - 100, hp=400, label="Sol-R"),
    ]


founding = make_founding()
soldiers_local = make_dummies()


# ── 8b. Spawn 10 soldier + 3 hero + 3 tower (background) ─────────────────────
from _demo_dummies import (  # noqa: E402
    spawn_world, draw_all, update_all, draw_hero,
)

_extra_sol, heroes, towers = spawn_world(W, H, founding.x, founding.y)
soldiers = soldiers_local + _extra_sol
_MockWorldQuery.soldiers   = soldiers
_MockWorldQuery.commanders = heroes
_MockWorldQuery.towers     = towers
print(f"[Spawn] soldiers={len(soldiers)} ({len(soldiers_local)} setup + "
      f"{len(_extra_sol)} extra)  heroes={len(heroes)}  towers={len(towers)}")


DIR_NAMES   = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}
PHASE_COLOR = {1: (140, 220, 140), 2: (240, 200, 80), 3: (240, 100, 100)}
PHASE_LABEL = {1: "PHASE 1 (HP>60%)",
               2: "PHASE 2 (20-60%)  SUMMON",
               3: "PHASE 3 (≤20% sticky)"}


def _distance(a, b) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _target_name(e) -> str:
    """Tên hiển thị an toàn cho mọi loại target."""
    return getattr(e, '_label', None) or getattr(e, 'name', None) \
        or type(e).__name__


def _all_targets() -> list:
    """Gộp MỌI mục tiêu có thể đánh: soldier (local + extra) + hero + tower.

    Đọc động biến module-level → cập nhật đúng sau khi bấm R (respawn).
    """
    return list(soldiers) + list(heroes) + list(towers)


def _nearest_dummy() -> tuple:
    """Trả (target, dist) của mục tiêu còn sống gần nhất trong MỌI loại."""
    best, best_d = None, float('inf')
    for e in _all_targets():
        if not getattr(e, 'is_alive', False):
            continue
        d = _distance(founding, e)
        if d < best_d:
            best_d, best = d, e
    return best, best_d


# ── 9. Vòng lặp ──────────────────────────────────────────────────────────────

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
                # SPACE LUÔN trigger animation — damage chỉ áp nếu trong tầm
                target, dist = _nearest_dummy()
                started = founding.trigger_attack(target)
                if started and target is not None and dist <= founding._ATTACK_RANGE:
                    print(f"[ATTACK HIT P{founding._phase}]  "
                          f"HeavyStrike vào {_target_name(target)} @ {dist:.0f}px  "
                          f"(damage=2×{founding._damage}={2 * founding._damage})")
                # Ngoài tầm hoặc không có target: chỉ animation, không log

            elif event.key == pygame.K_n:
                started = founding.start_summon()
                if started:
                    print(f"[SUMMON start]  dir={DIR_NAMES[founding._direction]}  "
                          f"row={founding._SUMMON_ROWS[founding._direction]}  "
                          f"phase=P{founding._phase}")
                else:
                    reason = []
                    if founding._phase != 2:
                        reason.append(f"phase=P{founding._phase} (cần P2)")
                    if founding._summon_locked:
                        reason.append("SUMMON LOCKED (đã từng ≤20% HP)")
                    if founding._summon_cd_timer > 0:
                        reason.append(f"cd={founding._summon_cd_timer:.1f}s")
                    if founding._is_summoning or founding._is_attacking:
                        reason.append("busy")
                    print(f"[SUMMON miss]  {' | '.join(reason) or 'unknown'}")

            elif event.key == pygame.K_1:
                founding._hp = int(founding._max_hp * 0.90)
                print(f"[HP=90%]  {founding._hp}/{founding._max_hp}")

            elif event.key == pygame.K_2:
                founding._hp = int(founding._max_hp * 0.50)
                print(f"[HP=50%]  {founding._hp}/{founding._max_hp}")

            elif event.key == pygame.K_3:
                founding._hp = int(founding._max_hp * 0.15)
                print(f"[HP=15%]  {founding._hp}/{founding._max_hp}  "
                      f"→ summon LOCKED khi tick phase tiếp")

            elif event.key == pygame.K_j:
                heal = int(founding._max_hp * 0.10)
                founding._hp = min(founding._max_hp, founding._hp + heal)
                print(f"[HP +{heal}]  {founding._hp}/{founding._max_hp}  "
                      f"(summon_locked={founding._summon_locked})")

            elif event.key == pygame.K_r:
                founding = make_founding()
                soldiers_local = make_dummies()
                _extra_sol, heroes, towers = spawn_world(W, H, founding.x, founding.y)
                soldiers = soldiers_local + _extra_sol
                _MockWorldQuery.soldiers   = soldiers
                _MockWorldQuery.commanders = heroes
                _MockWorldQuery.towers     = towers
                print(f"[Respawn] soldiers={len(soldiers)}  "
                      f"heroes={len(heroes)}  towers={len(towers)}")

    # ── Manual movement (chặn khi đang summon/attack) ────────────────────────
    # Founding KHÔNG có Run — chỉ Walk tốc độ cố định
    if not founding._is_attacking and not founding._is_summoning:
        keys = pygame.key.get_pressed()
        speed = WALK_SPEED

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
            founding._direction = 1   # West  (A)
        elif dx > 0:
            founding._direction = 3   # East  (D)
        elif dy < 0:
            founding._direction = 0   # North (W)
        elif dy > 0:
            founding._direction = 2   # South (S)

        if dx != 0.0 and dy != 0.0:
            inv = 1.0 / math.sqrt(2.0)
            dx *= inv
            dy *= inv

        mx = dx * speed * dt
        my = dy * speed * dt
        founding._is_moving = (mx != 0.0 or my != 0.0)
        if founding._is_moving:
            founding.x = max(40.0, min(float(W - 40), founding.x + mx))
            founding.y = max(40.0, min(float(H - 40), founding.y + my))
    else:
        founding._is_moving = False

    # Animation + phase + summon timing
    founding.update_anim(dt)

    # Auto-summon: khi P2 và cooldown ready → start_summon
    if (founding._phase == 2 and not founding._summon_locked
            and not founding._is_summoning and not founding._is_attacking
            and founding._summon_cd_timer <= 0):
        founding.start_summon()

    # Update dummies (hit flash)
    for s in soldiers:
        s.update(dt)
    update_all(dt, [], heroes, towers)   # heroes + towers (soldiers đã update ở trên)

    # ── Draw ─────────────────────────────────────────────────────────────────
    screen.fill((24, 28, 34))
    for gx in range(0, W, 64):
        pygame.draw.line(screen, (40, 45, 52), (gx, 0), (gx, H))
    for gy in range(0, H, 64):
        pygame.draw.line(screen, (40, 45, 52), (0, gy), (W, gy))

    # Vòng tầm attack 80px (xanh) + vòng spawn 180px (cam)
    pygame.draw.circle(screen, (100, 180, 220),
                       (int(founding.x), int(founding.y)),
                       int(founding._ATTACK_RANGE), 1)
    pygame.draw.circle(screen, (220, 140, 60),
                       (int(founding.x), int(founding.y)),
                       int(founding._SUMMON_RADIUS), 1)

    # Background entities (heroes + towers) — vẽ trước dummies
    draw_all(screen, font, [], heroes, towers)

    # Soldier dummies (gồm cả local + extra — extra sẽ tự render kiểu local)
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
            lbl = font.render(f"{s._label} {s._hp}", True, (220, 220, 220))
            screen.blit(lbl, (bx, by - 14))

    # Summoned minions (vẽ fallback nếu sprite chưa load — đa số sẽ load OK)
    for m in founding._summoned_minions:
        m._load_sprite()
        m.draw(screen)
        if m._sprite_sheet is None:
            # Fallback: hình tròn nhỏ
            mx_t, my_t = int(m.x), int(m.y)
            pygame.draw.circle(screen, (180, 100, 100), (mx_t, my_t), 18)
            pygame.draw.circle(screen, (240, 200, 200), (mx_t, my_t), 18, 2)
            lbl = font.render(f"t{m._variant}", True, (255, 255, 255))
            screen.blit(lbl, (mx_t - 8, my_t - 6))

    # Founding (sprite or fallback)
    founding.draw(screen)
    if founding._sprite_sheet is None:
        fx_t, fy_t = int(founding.x), int(founding.y)
        pygame.draw.circle(screen, (220, 200, 80), (fx_t, fy_t), 34)
        pygame.draw.circle(screen, (255, 240, 160), (fx_t, fy_t), 34, 2)
        angle_map = {0: -math.pi / 2, 1: math.pi, 2: math.pi / 2, 3: 0.0}
        ang = angle_map[founding._direction]
        tip_x = fx_t + int(math.cos(ang) * 40)
        tip_y = fy_t + int(math.sin(ang) * 40)
        pygame.draw.line(screen, (255, 255, 255),
                         (fx_t, fy_t), (tip_x, tip_y), 3)

    # HP bar founding
    bar_w = 140
    hp_ratio = founding._hp / founding._max_hp if founding._max_hp > 0 else 0
    bx = int(founding.x - bar_w // 2)
    by = int(founding.y - 56)
    pygame.draw.rect(screen, (60, 0, 0), (bx, by, bar_w, 8))
    pygame.draw.rect(screen, PHASE_COLOR[founding._phase],
                     (bx, by, int(bar_w * hp_ratio), 8))
    pygame.draw.rect(screen, (200, 200, 200), (bx, by, bar_w, 8), 1)
    # Đánh dấu ngưỡng 60% và 20% trên thanh HP
    for pct, color in [(0.6, (200, 200, 80)), (0.2, (240, 80, 80))]:
        mx_h = bx + int(bar_w * pct)
        pygame.draw.line(screen, color, (mx_h, by - 2), (mx_h, by + 10), 1)

    # HUD
    if founding._is_summoning:
        if founding._summon_anim_timer > 0:
            state = f"SUMMON anim ({founding._anim_col + 1}/{founding._SUMMON_FRAMES})"
        else:
            state = f"SUMMON pause ({founding._summon_pause_timer:.1f}s)"
        row_info = f"row={founding._SUMMON_ROWS[founding._direction]}"
    elif founding._is_attacking:
        state = "ATTACK (HeavyStrike)"
        row_info = (f"row={founding._ATTACK_ROWS[founding._direction]}  "
                    f"col={founding._anim_col}/{founding._ATTACK_FRAMES - 1}")
    elif founding._is_moving:
        state, row_info = "WALK", f"row={founding._WALK_ROWS[founding._direction]}"
    else:
        state, row_info = "IDLE", f"row={founding._WALK_ROWS[founding._direction]}"

    attack_cd = (f"READY" if founding._attack_cd_timer <= 0
                 else f"{founding._attack_cd_timer:.1f}s")
    summon_cd = (f"READY" if founding._summon_cd_timer <= 0
                 else f"{founding._summon_cd_timer:.1f}s")

    hud = [
        f"sprite  : Assets/Boss/founding.png  [{'OK' if founding._sprite_sheet is not None else 'MISSING'}]",
        f"state   : {state}   dir={DIR_NAMES[founding._direction]}   {row_info}",
        f"hp      : {founding._hp}/{founding._max_hp}  "
        f"({hp_ratio*100:.0f}%)",
        f"phase   : {PHASE_LABEL[founding._phase]}  "
        f"locked={'YES' if founding._summon_locked else 'no'}",
        f"attack  : range={founding._ATTACK_RANGE:.0f}px  cd={attack_cd}  "
        f"damage=×2 HeavyStrike",
        f"summon  : radius={founding._SUMMON_RADIUS:.0f}px  total=10  "
        f"minion pool=8 loại (regular2/4/5/6/7, wolf, towerhunter, soldierhunter)  cd={summon_cd}",
        f"minions : {len(founding._summoned_minions)} đã spawn (lũy kế)",
        "",
        "WASD=move  SPACE=attack (luôn animate)  N=force summon",
        "1/2/3=set HP 90/50/15%  J=+10%HP  R=respawn  Q=quit",
    ]
    for i, line in enumerate(hud):
        color = (220, 220, 220)
        if i == 3:   # phase line
            color = PHASE_COLOR[founding._phase]
        surf = font.render(line, True, color)
        screen.blit(surf, (12, 12 + i * 18))

    pygame.display.flip()

pygame.quit()
sys.exit()
