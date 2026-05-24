"""check.py — Demo trực quan ColossalTitan Skill 1 (Steam Burst) & Skill 2 (Jump Stomp).

Phím điều khiển:
  WASD   — di chuyển ColossalTitan (80 px/s), cập nhật hướng nhìn
  SPACE  — kích hoạt Steam Burst ngay lập tức
  ENTER  — kích hoạt Jump Stomp ngay lập tức
  T      — bật/tắt tự động cooldown (để titan tự trigger)
  Q      — thoát
"""
import sys
import os
import math
import random
import types

import pygame

# ── 1. Tạo mock modules trước khi import Boss ─────────────────────────────────

def _mod(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


# ── BurnDecorator giả (tự đăng ký lên entity._decorators) ───────────────────

class MockBurnDecorator:
    def __init__(self, entity, damage_per_sec: float, duration: float):
        self.entity        = entity
        self.dps           = damage_per_sec
        self.duration      = duration
        self._elapsed      = 0.0
        self._tick_timer   = 0.0
        self.active        = True
        if hasattr(entity, '_decorators'):
            entity._decorators.append(self)
        print(f"  [Burn] ← {entity.label}  {damage_per_sec} dmg/s × {duration}s")

    def update(self, dt: float) -> None:
        if not self.active:
            return
        self._elapsed    += dt
        self._tick_timer += dt
        if self._tick_timer >= 1.0:
            self._tick_timer -= 1.0
            self.entity.take_damage(int(self.dps), 'burn_dot')
        if self._elapsed >= self.duration:
            self.active = False
            print(f"  [Burn] expired on {self.entity.label}")


_pat     = _mod('patterns')
_pat_dec = _mod('patterns.decorator')
_pat_dec.BurnDecorator = MockBurnDecorator


# ── Mock Entity (soldier / commander / tower) ─────────────────────────────────

class MockEntity:
    def __init__(self, x: float, y: float, label: str):
        self.x          = x
        self.y          = y
        self.label      = label
        self.is_alive   = True
        self._hp        = 200
        self._decorators: list = []
        self._stun_timer = 0.0

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp = max(0, self._hp - amount)
        tag = f"[{self.label}]"
        print(f"{tag:<22} take_damage({amount:>3}, '{dtype}')  HP→{self._hp}")
        if dtype == 'pushback':
            print(f"{'':22} ↩  PUSHBACK!")

    def stun(self, duration: float) -> None:
        self._stun_timer = duration
        print(f"[{self.label:<20}] STUNNED {duration}s!")

    def update(self, dt: float) -> None:
        if self._stun_timer > 0:
            self._stun_timer = max(0.0, self._stun_timer - dt)
        for d in self._decorators:
            d.update(dt)
        self._decorators = [d for d in self._decorators if d.active]


# ── WorldQuery giả ────────────────────────────────────────────────────────────

class MockWorldQuery:
    soldiers:   list = []
    commanders: list = []
    towers:     list = []

    @classmethod
    def find_in_radius(cls, cx: float, cy: float,
                       radius: float, entity_type: str) -> list:
        mapping = {
            'soldier':   cls.soldiers,
            'commander': cls.commanders,
            'tower':     cls.towers,
        }
        return [
            e for e in mapping.get(entity_type, [])
            if math.hypot(e.x - cx, e.y - cy) <= radius
        ]

    @classmethod
    def find_nearest(cls, cx: float, cy: float, entity_type: str):
        src = {'soldier': cls.soldiers,
               'commander': cls.commanders,
               'tower': cls.towers}.get(entity_type, [])
        return min(src, key=lambda e: math.hypot(e.x - cx, e.y - cy),
                   default=None)


_sys_mod = _mod('systems')
_wq_mod  = _mod('systems.world_query')
_wq_mod.WorldQuery = MockWorldQuery

_rm_mod = _mod('systems.resource_manager')

class _MockRM:
    @classmethod
    def get_instance(cls):
        return cls()
    def get_stock(self):
        class _Stock:
            serum = 0
        return _Stock()

_rm_mod.ResourceManager = _MockRM

_wm_mod = _mod('systems.wave_manager')

class _MockWM:
    @classmethod
    def get_instance(cls):
        return cls()
    def spawn_minions(self, **_kw) -> None:
        pass

_wm_mod.WaveManager = _MockWM


# ── Titan / GroundSlamStrategy giả ───────────────────────────────────────────

class _MockTitan:
    def __init__(self, x: float, y: float, config: dict):
        self.x          = x
        self.y          = y
        self.is_alive   = True
        self._hp        = config.get('hp', 2000)
        self._max_hp    = self._hp
        self._attack_strategy = None

    def _find_best_target(self):
        # Titan quay về phía HQ giả (dưới-phải màn hình)
        class _FakeTarget:
            x = 750
            y = 550
        return _FakeTarget()

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen: pygame.Surface) -> None:
        pass

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp -= amount


class _MockGSS:
    def __init__(self, radius: float, stun_duration: float):
        pass
    def execute(self, attacker, target) -> None:
        pass


class _MockHSS:
    """Mock HeavyStrikeStrategy — chỉ cần để Boss.py import được."""
    def __init__(self, damage_mult: float = 2.0,
                 cooldown: float = 3.0,
                 range_px: float = 80.0) -> None:
        self._damage_mult = damage_mult
    def execute(self, attacker, target) -> None:
        pass


_chars_mod  = _mod('characters')
_titans_mod = _mod('characters.titans')
_titan_mod  = _mod('characters.titans.titan')
_titan_mod.Titan = _MockTitan

_strat_mod  = _mod('characters.titans.attackstrategy')
_strat_mod.GroundSlamStrategy  = _MockGSS
_strat_mod.HeavyStrikeStrategy = _MockHSS
# NHÓM 6 — Boss.py import lại RockProjectile/HeatParticle từ attackstrategy.
# Lấy bản THẬT từ AttackStrategy.py. AttackStrategy.py có `from core.interfaces
# import IAttackable` ở top-level nên cần mock tối thiểu `core` trước khi import.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_mod('core')
_core_iface = _mod('core.interfaces')
_core_iface.IAttackable = type('IAttackable', (), {})
import AttackStrategy as _atk_src  # noqa: E402
_strat_mod.RockProjectile  = _atk_src.RockProjectile
_strat_mod.HeatParticle    = _atk_src.HeatParticle


# ── 2. Import ColossalTitan từ Boss.py thật ───────────────────────────────────

# File này nằm trong Check/ — sys.path phải trỏ về parent (chứa Boss.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Boss import ColossalTitan, HeatParticle  # noqa: E402


# ── 3. Pygame setup ───────────────────────────────────────────────────────────

pygame.init()
W, H   = 960, 680
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(
    "ColossalTitan — Demo  (WASD=Move  SPACE=Steam  ENTER=Jump  T=Auto  Q=Quit)"
)
clock  = pygame.time.Clock()
font   = pygame.font.SysFont("Consolas", 15)
big    = pygame.font.SysFont("Consolas", 22, bold=True)


# ── 4. Entities ───────────────────────────────────────────────────────────────

CX, CY = W // 2, H // 2

colossal = ColossalTitan(float(CX), float(CY), {'hp': 2000})

# ── Spawn 10 soldier (5 cụm + 5 random) + 3 hero + 3 tower ───────────────────
import sys as _sys  # noqa: E402
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _demo_dummies import (  # noqa: E402
    spawn_world, draw_all as _draw_all, update_all as _update_all,
)

_d_soldiers, _d_heroes, _d_towers = spawn_world(W, H, CX, CY)

# Convert sang MockEntity để tương thích với HUD/draw cũ (giữ behavior)
MockWorldQuery.soldiers = []
for i, s in enumerate(_d_soldiers):
    m = MockEntity(s.x, s.y, f"Sld{i+1}")
    MockWorldQuery.soldiers.append(m)
MockWorldQuery.commanders = []
for h in _d_heroes:
    m = MockEntity(h.x, h.y, h.name)
    MockWorldQuery.commanders.append(m)
MockWorldQuery.towers = []
for i, t in enumerate(_d_towers):
    m = MockEntity(t.x, t.y, f"Tower{i+1}")
    MockWorldQuery.towers.append(m)
print(f"[Spawn] soldiers={len(MockWorldQuery.soldiers)}  "
      f"heroes={len(MockWorldQuery.commanders)}  "
      f"towers={len(MockWorldQuery.towers)}")

auto_mode = False   # T キー でトグル — 自動でcooldown進行


# ── 5. Draw helpers ───────────────────────────────────────────────────────────

def draw_aoe_ring(cx: int, cy: int, radius: int, color: tuple, label: str) -> None:
    pygame.draw.circle(screen, color, (cx, cy), radius, 1)
    lbl = font.render(label, True, color)
    screen.blit(lbl, (cx + radius + 4, cy - 8))


def draw_soldier(e: MockEntity) -> None:
    stunned = e._stun_timer > 0
    color   = (255, 220, 0) if stunned else (60, 130, 220)
    pygame.draw.circle(screen, color, (int(e.x), int(e.y)), 14)
    lbl = font.render(e.label.split('_')[0], True, (255, 255, 255))
    screen.blit(lbl, (int(e.x) - lbl.get_width() // 2, int(e.y) + 16))
    bar_w = 32
    hp_f  = max(e._hp, 0) / 200
    pygame.draw.rect(screen, (80, 0, 0),   (int(e.x) - 16, int(e.y) - 22, bar_w, 5))
    pygame.draw.rect(screen, (0, 200, 80), (int(e.x) - 16, int(e.y) - 22, int(bar_w * hp_f), 5))
    if any(d.active for d in e._decorators):
        pygame.draw.circle(screen, (255, 120, 0), (int(e.x) + 12, int(e.y) - 12), 5)


def draw_commander(e: MockEntity) -> None:
    stunned = e._stun_timer > 0
    color   = (255, 220, 0) if stunned else (60, 210, 90)
    pygame.draw.circle(screen, color, (int(e.x), int(e.y)), 18)
    pygame.draw.circle(screen, (200, 200, 50), (int(e.x), int(e.y)), 18, 2)
    lbl = font.render(e.label, True, (255, 255, 255))
    screen.blit(lbl, (int(e.x) - lbl.get_width() // 2, int(e.y) + 20))
    bar_w = 40
    hp_f  = max(e._hp, 0) / 200
    pygame.draw.rect(screen, (80, 0, 0),   (int(e.x) - 20, int(e.y) - 26, bar_w, 5))
    pygame.draw.rect(screen, (0, 200, 80), (int(e.x) - 20, int(e.y) - 26, int(bar_w * hp_f), 5))
    if any(d.active for d in e._decorators):
        pygame.draw.circle(screen, (255, 120, 0), (int(e.x) + 16, int(e.y) - 16), 5)


def draw_tower(e: MockEntity) -> None:
    stunned = e._stun_timer > 0
    color   = (255, 200, 0) if stunned else (90, 90, 90)
    rect    = pygame.Rect(int(e.x) - 20, int(e.y) - 20, 40, 40)
    pygame.draw.rect(screen, color, rect, border_radius=4)
    lbl = font.render(e.label.split('_')[0], True, (255, 255, 255))
    screen.blit(lbl, (int(e.x) - lbl.get_width() // 2, int(e.y) + 22))
    if stunned:
        stun_lbl = font.render(f"stun {e._stun_timer:.1f}s", True, (255, 220, 0))
        screen.blit(stun_lbl, (int(e.x) - stun_lbl.get_width() // 2, int(e.y) - 36))


def draw_hud() -> None:
    dir_names = {0: "North", 1: "West", 2: "South", 3: "East"}
    lines = [
        "─── ColossalTitan HUD ───",
        f"  Steam timer : {colossal._steam_timer:5.1f}s  (cooldown 8s)",
        f"  Jump  timer : {colossal._jump_timer:5.1f}s  (cooldown 15s)",
        f"  Steaming    : {colossal._is_steaming}",
        f"  Jumping     : {colossal._is_jumping}",
        f"  Moving      : {colossal._is_moving}",
        f"  Direction   : {dir_names.get(colossal._direction, '?')}",
        f"  Pos         : ({colossal.x:.0f}, {colossal.y:.0f})",
        f"  Particles   : {len(colossal._heat_particles)}",
        f"  Auto-mode   : {'ON' if auto_mode else 'OFF'}",
        "",
        "─── Controls ───",
        "  WASD   Move (80 px/s)",
        "  SPACE  Steam Burst",
        "  ENTER  Jump Stomp",
        "  T      Toggle auto",
        "  Q      Quit",
        "",
        "─── Legend ───",
        "  ● Blue   = Soldier",
        "  ● Green  = Commander",
        "  ■ Gray   = Tower",
        "  ● Orange = Burn DoT",
        "  ■ Yellow = Stunned",
    ]
    for i, line in enumerate(lines):
        color = (200, 200, 200) if not line.startswith("─") else (140, 200, 255)
        surf  = font.render(line, True, color)
        screen.blit(surf, (8, 8 + i * 19))


def draw_skill_overlay() -> None:
    if colossal._is_steaming:
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (255, 140, 0, 22), overlay.get_rect())
        screen.blit(overlay, (0, 0))
        msg = big.render("★  STEAM BURST  ★", True, (255, 180, 60))
        screen.blit(msg, (CX - msg.get_width() // 2, 16))
    elif colossal._is_jumping:
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (160, 60, 255, 22), overlay.get_rect())
        screen.blit(overlay, (0, 0))
        msg = big.render("★  JUMP STOMP  ★", True, (200, 120, 255))
        screen.blit(msg, (CX - msg.get_width() // 2, 16))


# ── 6. Game loop ──────────────────────────────────────────────────────────────

running = True
while running:
    dt = clock.tick(60) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                running = False

            elif event.key == pygame.K_SPACE:
                print("\n=== [Manual] STEAM BURST ===")
                colossal._steam_burst()
                colossal._steam_timer = colossal._steam_cooldown

            elif event.key == pygame.K_RETURN:
                print("\n=== [Manual] JUMP STOMP ===")
                colossal._jump_stomp()
                colossal._jump_timer = colossal._jump_cooldown

            elif event.key == pygame.K_t:
                auto_mode = not auto_mode
                print(f"[Auto-mode] {'ON' if auto_mode else 'OFF'}")

    # ── WASD — di chuyển ColossalTitan (80 px/s) ────────────────────────────
    # Bỏ qua di chuyển khi đang tung skill (titan đứng yên)
    if not (colossal._is_steaming or colossal._is_jumping):
        keys = pygame.key.get_pressed()
        dx_move = dy_move = 0.0
        if keys[pygame.K_w]:
            dy_move -= 80.0 * dt
        if keys[pygame.K_s]:
            dy_move += 80.0 * dt
        if keys[pygame.K_a]:
            dx_move -= 80.0 * dt
        if keys[pygame.K_d]:
            dx_move += 80.0 * dt

        # Hướng nhìn: ưu tiên trục ngang (A/D) hơn trục dọc (W/S).
        #   W+D → D, A+W → A. A+D (hoặc W+S) triệt tiêu → giữ hướng cũ.
        if dx_move < 0:
            colossal._direction = 1   # West  (A)
        elif dx_move > 0:
            colossal._direction = 3   # East  (D)
        elif dy_move < 0:
            colossal._direction = 0   # North (W)
        elif dy_move > 0:
            colossal._direction = 2   # South (S)
        colossal._is_moving = (dx_move != 0.0 or dy_move != 0.0)
        if colossal._is_moving:
            colossal.x = max(32.0, min(float(W - 32), colossal.x + dx_move))
            colossal.y = max(32.0, min(float(H - 32), colossal.y + dy_move))
    else:
        colossal._is_moving = False

    # ── Cập nhật ColossalTitan ───────────────────────────────────────────────
    if auto_mode:
        colossal.update(dt)
    else:
        # Cập nhật particles và animation kể cả khi không auto
        colossal._heat_particles = [
            p for p in colossal._heat_particles if p.update(dt)
        ]
        colossal._anim_timer += dt
        if colossal._anim_timer >= 1.0 / colossal._ANIM_FPS:
            colossal._anim_timer -= 1.0 / colossal._ANIM_FPS
            if colossal._is_steaming:
                colossal._anim_col = (colossal._anim_col + 1) % ColossalTitan._STEAM_FRAMES
            elif colossal._is_jumping:
                colossal._anim_col = (colossal._anim_col + 1) % ColossalTitan._STOMP_FRAMES
            elif colossal._is_moving:
                colossal._anim_col = (colossal._anim_col + 1) % ColossalTitan._WALK_FRAMES
        if colossal._is_steaming:
            colossal._steam_anim_timer -= dt
            if colossal._steam_anim_timer <= 0:
                colossal._is_steaming = False
        if colossal._is_jumping:
            colossal._jump_anim_timer -= dt
            if colossal._jump_anim_timer <= 0:
                colossal._is_jumping = False

    # Cập nhật entities (burn DoT, stun timer)
    for e in (MockWorldQuery.soldiers
              + MockWorldQuery.commanders
              + MockWorldQuery.towers):
        e.update(dt)

    # ── Vẽ ──────────────────────────────────────────────────────────────────
    screen.fill((28, 28, 38))

    # AoE rings — theo vị trí hiện tại của titan
    tx, ty = int(colossal.x), int(colossal.y)
    # Steam Burst: vành khuyên annulus thay vì vòng tròn đặc
    draw_aoe_ring(tx, ty, ColossalTitan._STEAM_R_IN,  (200, 100, 30),
                  f"R_in {ColossalTitan._STEAM_R_IN}px")
    draw_aoe_ring(tx, ty, ColossalTitan._STEAM_R_OUT, (200, 140, 50),
                  f"R_out {ColossalTitan._STEAM_R_OUT}px")
    draw_aoe_ring(tx, ty, ColossalTitan._STOMP_AOE,   (120, 60, 200), "Stomp 160px")

    # Entities
    for e in MockWorldQuery.towers:
        draw_tower(e)
    for e in MockWorldQuery.soldiers:
        draw_soldier(e)
    for e in MockWorldQuery.commanders:
        draw_commander(e)

    # ColossalTitan — sprite PNG (luôn hiển thị) + particles
    titan_lbl = big.render("Colossal", True, (255, 110, 110))
    screen.blit(titan_lbl, (tx - titan_lbl.get_width() // 2, ty - 58))
    colossal.draw(screen)   # spritesheet frame luôn được vẽ + particles

    # Skill overlay
    draw_skill_overlay()

    # HUD
    draw_hud()

    pygame.display.flip()

pygame.quit()
sys.exit(0)
