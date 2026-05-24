"""kamikazecheck.py — Demo Kamikaze Titan (clustering target → run → explode).

Phím điều khiển:
  WASD          — di chuyển Kamikaze manual (chỉ khi AUTO off)
  T             — toggle AUTO mode (kamikaze tự AI: detect → run → explode)
  E             — force trigger explosion ngay (pause 1.5s rồi nổ)
  H             — -50 HP kamikaze (test death-explode khi HP về 0)
  N             — spawn thêm 1 soldier random (test target re-pick)
  R             — respawn kamikaze + 10 soldier mới
  Q / ESC       — thoát

Mục đích kiểm tra:
  • Walk (rows 8-11, 9 frame) vs Run (rows 38-41, 8 frame)
  • Detect radius 300px (vòng tròn xám) — soldier vào → kamikaze bắt đầu chạy
  • Clustering target pick — kamikaze ưu tiên soldier có đông đồng đội nhất
  • Pause 1.5s + flash đỏ tăng dần khi target vào explode radius 80px
  • Explosion AoE: main 200, splash 100, knockback 60px
  • Death-explode: bấm H đủ 6 lần (-300 HP) → kamikaze chết → vẫn nổ
  • Explosion GIF từ `Explosion Kamikaze/explode.gif` (PIL tách frame)
"""
import sys
import os
import math
import random
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


# ── 2. Mock characters.titans (strategies + base Titan) ──────────────────────

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


# ── 3. Mock WorldQuery — find_in_radius('soldier') ───────────────────────────

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


# ── 4. Import Kamikaze thật ──────────────────────────────────────────────────

from Titan import Kamikaze  # noqa: E402


# ── 5. GIF loader qua PIL ────────────────────────────────────────────────────

def load_gif_frames(path: str) -> tuple:
    """Trả về (frames: list[Surface], durations: list[float]).

    Dùng PIL/Pillow để tách từng frame của GIF. Nếu thất bại trả ([], []).
    """
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        print("  [WARN] Pillow chưa cài — chạy: pip install Pillow")
        return [], []

    try:
        pil_img = Image.open(path)
    except Exception as e:
        print(f"  [WARN] Không mở được GIF: {e}")
        return [], []

    frames = []
    durations = []
    for frame in ImageSequence.Iterator(pil_img):
        rgba = frame.convert("RGBA")
        size = rgba.size
        data = rgba.tobytes()
        surf = pygame.image.fromstring(data, size, "RGBA")
        frames.append(surf)
        durations.append(frame.info.get('duration', 80) / 1000.0)
    return frames, durations


class ExplosionEffect:
    """Hiệu ứng nổ — play GIF 1 lượt rồi tự tắt."""

    def __init__(self, x: float, y: float,
                 frames: list, durations: list):
        self.x = float(x)
        self.y = float(y)
        self._frames    = frames
        self._durations = durations
        self._idx       = 0
        self._timer     = 0.0
        self.alive      = bool(frames)

    def update(self, dt: float) -> None:
        if not self.alive:
            return
        self._timer += dt
        # Tiến frame khi đủ duration
        while (self._idx < len(self._frames)
               and self._timer >= self._durations[self._idx]):
            self._timer -= self._durations[self._idx]
            self._idx += 1
        if self._idx >= len(self._frames):
            self.alive = False

    def draw(self, screen: pygame.Surface) -> None:
        if not self.alive or not self._frames:
            return
        idx = min(self._idx, len(self._frames) - 1)
        frame = self._frames[idx]
        rect = frame.get_rect(center=(int(self.x), int(self.y)))
        screen.blit(frame, rect)


# ── 6. Soldier dummy ─────────────────────────────────────────────────────────

class SoldierDummy:
    def __init__(self, x: float, y: float, hp: int = 150, label: str = "S"):
        self.x = float(x)
        self.y = float(y)
        self._hp     = hp
        self._max_hp = hp
        self.is_alive = True
        self._label  = label
        self._hit_flash = 0.0

    def take_damage(self, amount: int, dtype: str) -> None:
        self._hp = max(0, self._hp - amount)
        self._hit_flash = 0.45
        tag = "MAIN" if amount >= 200 else "SPLASH"
        print(f"  [{self._label:4s}] take_damage(amount={amount:>3}, dtype='{dtype}')  "
              f"→ HP={self._hp:>3}/{self._max_hp}  [{tag}]")
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
    "Kamikaze Demo  (WASD=move  T=auto  E=explode  H=-50HP  N=add soldier  R=respawn  Q=quit)"
)
clock = pygame.time.Clock()
font  = pygame.font.SysFont("Consolas", 15)
big   = pygame.font.SysFont("Consolas", 22, bold=True)


# ── 8. Load GIF + spawn ──────────────────────────────────────────────────────

KAM_X, KAM_Y = 120, H // 2
WALK_SPEED   = 70.0

# File này nằm trong CHECK/ — lùi 1 cấp ra root rồi vào Assets/
EXPLOSION_GIF = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'Assets', 'Explosion Kamikaze', 'explode.gif',
)
gif_frames, gif_durations = load_gif_frames(EXPLOSION_GIF)
print(f"\n=== GIF loaded: {len(gif_frames)} frames "
      f"(total {sum(gif_durations):.2f}s) ===")
if not gif_frames:
    print(f"  [WARN] Không load được GIF — fallback hình tròn đỏ scale up")


def make_kamikaze() -> Kamikaze:
    k = Kamikaze(float(KAM_X), float(KAM_Y), {
        'hp': 300,
        'speed': WALK_SPEED,
        'damage': 50,
    })
    k._load_sprite()
    sprite_ok = k._sprite_sheet is not None
    print(f"\n=== Spawn Kamikaze  HP={k._hp}  walk={WALK_SPEED}  "
          f"run={WALK_SPEED * k._RUN_SPEED_MULT:.0f}  "
          f"sprite={'OK' if sprite_ok else 'MISSING'} ===")
    if not sprite_ok:
        print(f"  [WARN] Assets/Special/kamikaze.png không load được "
              f"→ fallback hình tròn vàng")
    return k


def make_soldiers(n: int = 10) -> list:
    """N soldier random scatter trong nửa phải màn hình."""
    out = []
    for i in range(n):
        sx = random.randint(W // 2 - 100, W - 80)
        sy = random.randint(80, H - 80)
        out.append(SoldierDummy(sx, sy, hp=150, label=f"S{i:02d}"))
    return out


kamikaze = make_kamikaze()


# ── 8b. Spawn 10 soldier (5 cụm + 5 random) + 3 hero + 3 tower ───────────────
from _demo_dummies import spawn_world, draw_all, update_all  # noqa: E402

soldiers, heroes, towers = spawn_world(W, H, kamikaze.x, kamikaze.y)
_MockWorldQuery.soldiers   = soldiers
_MockWorldQuery.commanders = heroes
_MockWorldQuery.towers     = towers
print(f"[Spawn] soldiers={len(soldiers)} (5 cum + 5 random)  "
      f"heroes={len(heroes)}  towers={len(towers)}")

# Effect list (1 hoặc nhiều explosion)
effects: list = []


DIR_NAMES = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}
auto_mode = True
running   = True
prev_alive = True   # để bắt event "vừa chết" → spawn effect


def _spawn_explosion(x: float, y: float) -> None:
    """Spawn explosion effect (GIF hoặc fallback)."""
    if gif_frames:
        effects.append(ExplosionEffect(x, y, gif_frames, gif_durations))
    print(f"  [BOOM]  explosion @ ({x:.0f}, {y:.0f})")


# ── 9. Vòng lặp ──────────────────────────────────────────────────────────────

while running:
    dt = min(clock.tick(60) / 1000.0, 0.05)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

            elif event.key == pygame.K_t:
                auto_mode = not auto_mode
                print(f"[AUTO {'ON' if auto_mode else 'OFF'}]")

            elif event.key == pygame.K_e:
                if kamikaze.trigger_explosion():
                    print(f"[FORCE EXPLODE]  pause {kamikaze._PRE_EXPLODE_PAUSE}s "
                          f"target={'None' if kamikaze._target is None else kamikaze._target._label}")
                else:
                    print(f"[EXPLODE skip]  đang pause hoặc đã nổ")

            elif event.key == pygame.K_h:
                if kamikaze.is_alive:
                    before = kamikaze._hp
                    kamikaze.take_damage(50, 'normal')
                    print(f"[HP -50]  {before} → {kamikaze._hp}  "
                          f"alive={kamikaze.is_alive}  exploded={kamikaze._has_exploded}")

            elif event.key == pygame.K_n:
                sx = random.randint(W // 2 - 100, W - 80)
                sy = random.randint(80, H - 80)
                lbl = f"S_add{len(soldiers):02d}"
                from _demo_dummies import SoldierDummy as _DSol  # noqa: E402
                new_s = _DSol(sx, sy, hp=150, label=lbl)
                soldiers.append(new_s)
                _MockWorldQuery.soldiers = soldiers
                print(f"[ADD]  {lbl} @ ({sx}, {sy})")

            elif event.key == pygame.K_r:
                kamikaze = make_kamikaze()
                soldiers, heroes, towers = spawn_world(W, H, kamikaze.x, kamikaze.y)
                _MockWorldQuery.soldiers   = soldiers
                _MockWorldQuery.commanders = heroes
                _MockWorldQuery.towers     = towers
                print(f"[Respawn] soldiers={len(soldiers)}  "
                      f"heroes={len(heroes)}  towers={len(towers)}")
                effects.clear()
                prev_alive = True

    # ── Manual movement (khi AUTO off và không pausing/exploded) ─────────────
    if (not auto_mode and not kamikaze._is_pausing
            and not kamikaze._has_exploded and kamikaze.is_alive):
        keys = pygame.key.get_pressed()
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
            kamikaze._direction = 1   # West  (A)
        elif dx > 0:
            kamikaze._direction = 3   # East  (D)
        elif dy < 0:
            kamikaze._direction = 0   # North (W)
        elif dy > 0:
            kamikaze._direction = 2   # South (S)

        if dx != 0.0 and dy != 0.0:
            inv = 1.0 / math.sqrt(2.0)
            dx *= inv
            dy *= inv

        speed = WALK_SPEED   # manual = walk only (kiểm tra animation Walk)
        mx = dx * speed * dt
        my = dy * speed * dt
        kamikaze._is_moving  = (mx != 0.0 or my != 0.0)
        kamikaze._is_running = False
        if kamikaze._is_moving:
            kamikaze.x = max(40.0, min(float(W - 40), kamikaze.x + mx))
            kamikaze.y = max(40.0, min(float(H - 40), kamikaze.y + my))

    # ── AUTO AI tick ─────────────────────────────────────────────────────────
    if auto_mode and kamikaze.is_alive and not kamikaze._has_exploded:
        kamikaze.ai_tick(dt)

    kamikaze.update_anim(dt)

    # Đã nổ vừa rồi → spawn effect 1 lần
    if kamikaze._has_exploded and prev_alive:
        _spawn_explosion(kamikaze.x, kamikaze.y)
        # Explosion strategy (source) chỉ AoE lên 'soldier'. Bổ sung tại
        # đây: áp damage_splash cho tower + commander trong bán kính nổ
        # để Kamikaze "nổ trúng mọi loại" — không sửa AttackStrategy.py.
        _ex = kamikaze._attack_strategy
        _splash = getattr(_ex, '_damage_splash', 100)
        _radius = getattr(_ex, '_radius', kamikaze._EXPLODE_RADIUS)
        for _e in list(towers) + list(heroes):
            if not getattr(_e, 'is_alive', False):
                continue
            _dx = _e.x - kamikaze.x
            _dy = _e.y - kamikaze.y
            if (_dx * _dx + _dy * _dy) ** 0.5 <= _radius:
                _e.take_damage(_splash, 'explode')
        prev_alive = False

    # Update soldiers + effects
    for s in soldiers:
        s.update(dt)
    update_all(dt, [], heroes, towers)
    for ef in effects:
        ef.update(dt)
    effects = [ef for ef in effects if ef.alive]

    # ── Draw ─────────────────────────────────────────────────────────────────
    screen.fill((28, 30, 36))
    for gx in range(0, W, 64):
        pygame.draw.line(screen, (42, 46, 54), (gx, 0), (gx, H))
    for gy in range(0, H, 64):
        pygame.draw.line(screen, (42, 46, 54), (0, gy), (W, gy))

    # Vòng detect (xám) + vòng explode (đỏ) quanh kamikaze nếu chưa nổ
    if not kamikaze._has_exploded:
        pygame.draw.circle(screen, (130, 130, 140),
                           (int(kamikaze.x), int(kamikaze.y)),
                           int(kamikaze._DETECT_RADIUS), 1)
        pygame.draw.circle(screen, (220, 80, 60),
                           (int(kamikaze.x), int(kamikaze.y)),
                           int(kamikaze._EXPLODE_RADIUS), 1)

    # Heroes + Towers (background) — vẽ TRƯỚC soldiers
    draw_all(screen, font, [], heroes, towers)

    # Soldiers
    for s in soldiers:
        if s.is_alive:
            sx, sy = int(s.x), int(s.y)
            body = (240, 200, 80) if s._hit_flash > 0 else (100, 180, 110)
            # Tô đậm hơn nếu là target hiện tại của kamikaze
            if s is kamikaze._target:
                pygame.draw.circle(screen, (255, 80, 80), (sx, sy), 26, 3)
            pygame.draw.circle(screen, body, (sx, sy), 20)
            pygame.draw.circle(screen, (200, 240, 200), (sx, sy), 20, 2)
            # HP bar
            ratio = s._hp / s._max_hp if s._max_hp > 0 else 0
            bx, by = sx - 22, sy - 32
            pygame.draw.rect(screen, (60, 0, 0), (bx, by, 44, 4))
            pygame.draw.rect(screen, (120, 220, 120),
                             (bx, by, int(44 * ratio), 4))
            lbl = font.render(s._label, True, (220, 220, 220))
            screen.blit(lbl, (bx, by - 14))
        else:
            dead = font.render(f"{s._label}✗", True, (255, 80, 80))
            screen.blit(dead, (int(s.x - 12), int(s.y - 8)))

    # Vòng cluster radius quanh target hiện tại (mờ)
    if kamikaze._target is not None and kamikaze._target.is_alive:
        pygame.draw.circle(screen, (200, 180, 80),
                           (int(kamikaze._target.x), int(kamikaze._target.y)),
                           int(kamikaze._CLUSTER_RADIUS), 1)

    # Kamikaze (sprite or fallback)
    if kamikaze.is_alive or not kamikaze._has_exploded:
        kamikaze.draw(screen)
        if kamikaze._sprite_sheet is None and not kamikaze._has_exploded:
            kx_t, ky_t = int(kamikaze.x), int(kamikaze.y)
            color = (240, 200, 80)
            if kamikaze._is_pausing:
                # Pulse red dựa trên flash_intensity
                t = kamikaze._flash_intensity
                red = int(240 + 15 * t)
                color = (min(255, red), int(200 * (1 - t)), int(80 * (1 - t)))
            pygame.draw.circle(screen, color, (kx_t, ky_t), 26)
            pygame.draw.circle(screen, (255, 240, 200), (kx_t, ky_t), 26, 2)
            angle_map = {0: -math.pi / 2, 1: math.pi, 2: math.pi / 2, 3: 0.0}
            ang = angle_map[kamikaze._direction]
            tip_x = kx_t + int(math.cos(ang) * 32)
            tip_y = ky_t + int(math.sin(ang) * 32)
            pygame.draw.line(screen, (255, 255, 255),
                             (kx_t, ky_t), (tip_x, tip_y), 3)

    # Vẽ explosion effects
    for ef in effects:
        ef.draw(screen)
    # Fallback effect nếu không có GIF (vòng đỏ lớn dần + fade)
    if not gif_frames:
        # Tạm: nếu đã nổ trong < 0.5s, vẽ vòng tròn
        pass

    # HP bar kamikaze (chỉ khi còn sống)
    if kamikaze.is_alive:
        bar_w = 80
        hp_ratio = kamikaze._hp / kamikaze._max_hp if kamikaze._max_hp > 0 else 0
        bx = int(kamikaze.x - bar_w // 2)
        by = int(kamikaze.y - 48)
        pygame.draw.rect(screen, (60, 0, 0), (bx, by, bar_w, 6))
        pygame.draw.rect(screen, (220, 40, 40),
                         (bx, by, int(bar_w * hp_ratio), 6))
        pygame.draw.rect(screen, (200, 200, 200), (bx, by, bar_w, 6), 1)

    # HUD
    if kamikaze._has_exploded:
        state = "EXPLODED"
    elif kamikaze._is_pausing:
        state = f"PAUSE ({kamikaze._pause_timer:.2f}s) flash={kamikaze._flash_intensity:.2f}"
    elif kamikaze._is_moving and kamikaze._is_running:
        state = "RUN"
    elif kamikaze._is_moving:
        state = "WALK"
    else:
        state = "IDLE"

    target_label = "—"
    if kamikaze._target is not None and kamikaze._target.is_alive:
        d = ((kamikaze.x - kamikaze._target.x) ** 2
             + (kamikaze.y - kamikaze._target.y) ** 2) ** 0.5
        target_label = f"{kamikaze._target._label} @ {d:.0f}px"

    alive_soldiers = sum(1 for s in soldiers if s.is_alive)
    hud = [
        f"sprite     : Assets/Special/kamikaze.png  "
        f"[{'OK' if kamikaze._sprite_sheet is not None else 'MISSING'}]",
        f"GIF        : {len(gif_frames)} frames  "
        f"[{'OK' if gif_frames else 'MISSING — fallback flash'}]",
        f"state      : {state}   dir={DIR_NAMES[kamikaze._direction]}   "
        f"col={kamikaze._anim_col}",
        f"hp         : {kamikaze._hp if kamikaze.is_alive else 0}/{kamikaze._max_hp}  "
        f"alive={kamikaze.is_alive}  exploded={kamikaze._has_exploded}",
        f"target     : {target_label}",
        f"detect     : {kamikaze._DETECT_RADIUS:.0f}px  "
        f"explode={kamikaze._EXPLODE_RADIUS:.0f}px  "
        f"cluster={kamikaze._CLUSTER_RADIUS:.0f}px",
        f"explosion  : main={kamikaze._EXP_DAMAGE_MAIN}  "
        f"splash={kamikaze._EXP_DAMAGE_SPLASH}  "
        f"AoE={kamikaze._EXP_AOE_RADIUS:.0f}px  "
        f"knockback={kamikaze._EXP_KNOCKBACK:.0f}px",
        f"soldiers   : {alive_soldiers}/{len(soldiers)} alive",
        f"mode       : {'AUTO' if auto_mode else 'MANUAL'}",
        "",
        "WASD=move (MANUAL)  T=toggle AUTO  E=force explode",
        "H=-50HP (death-explode)  N=add soldier  R=respawn  Q=quit",
    ]
    for i, line in enumerate(hud):
        surf = font.render(line, True, (220, 220, 220))
        screen.blit(surf, (12, 12 + i * 18))

    pygame.display.flip()

pygame.quit()
sys.exit()
