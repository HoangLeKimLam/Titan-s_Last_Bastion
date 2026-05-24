"""_demo_dummies.py — Mock entities + spawn helper dùng chung cho mọi *check.py.

Cung cấp:
  • SoldierDummy   — lính 200 HP (xanh lá, vẽ circle r=14)
  • HeroDummy      — tướng (Levi/Mikasa/Erwin…) 600 HP (xanh-vàng circle r=18)
  • TowerDummy     — tháp 600 HP (xám hình chữ nhật 40×40)
  • spawn_world(W, H, titan_x, titan_y, min_dist=80, seed=None)
        → (soldiers: list[SoldierDummy], heroes: list[HeroDummy],
           towers: list[TowerDummy])

Quy ước phân phối:
  • 10 soldier: 5 con CỤM quanh 1 anchor random, 5 con random toàn map
  • 3 hero    : random toàn map (giữ khoảng cách min_dist với titan)
  • 3 tower   : random toàn map (giữ khoảng cách min_dist với titan)
  • Tất cả tránh chồng entity trong list đã spawn (min 36px giữa entity)

Method 3 class:
  • take_damage(amount, dtype)  — print log, giảm HP, hit_flash 0.4s
  • update(dt)                  — giảm hit_flash
  • draw_*(screen, font)        — helper render (gọi từ check.py)

Class HeroDummy có name (Levi, Mikasa, Erwin, …) để hiển thị tên.
"""
from __future__ import annotations

import random
from typing import Optional

import pygame


# Bộ tên hero (tham chiếu clossalcheck.py)
HERO_NAMES = ['Levi', 'Mikasa', 'Erwin', 'Armin', 'Jean', 'Sasha', 'Eren', 'Reiner']


class SoldierDummy:
    """Lính bộ binh — 200 HP, di chuyển 0 (đứng yên trong demo)."""

    entity_type = 'soldier'

    def __init__(self, x: float, y: float, hp: int = 200,
                 label: str = "Soldier") -> None:
        self.x = float(x)
        self.y = float(y)
        self._hp = hp
        self._max_hp = hp
        self.is_alive = True
        self._hit_flash = 0.0
        self._label = label
        # Vector pushback (NHÓM 6 — Beast rock land). Khởi tạo 0 để
        # `apply_pushback_tween` integrate được ngay frame đầu.
        self.pushback_vx = 0.0
        self.pushback_vy = 0.0

    def take_damage(self, amount: int, dtype: str) -> None:
        if amount > 0:
            self._hp = max(0, self._hp - amount)
            print(f"  [{self._label:9s}] take_damage({amount:>3}, '{dtype}')"
                  f"  → HP={self._hp}/{self._max_hp}")
        else:
            print(f"  [{self._label:9s}] take_damage(0, '{dtype}')")
        self._hit_flash = 0.4
        if self._hp <= 0:
            self.is_alive = False

    def update(self, dt: float) -> None:
        # Integrate vector pushback (Beast ném đá AOE) — phải gọi trước
        # khi vẽ frame này để vị trí lính cập nhật mượt qua từng tick.
        from AttackStrategy import RockProjectile
        RockProjectile.apply_pushback_tween(self, dt)
        if self._hit_flash > 0:
            self._hit_flash = max(0.0, self._hit_flash - dt)


class HeroDummy:
    """Tướng (Hero/Commander) — 600 HP, KHÔNG miễn nhiễm pushback nữa.

    Cập nhật: theo yêu cầu balance, commander BỊ pushback nhưng yếu hơn
    soldier (~50%, được Beast cấu hình qua `_DEFAULT_PUSHBACK_COMMANDER`).
    Hero vẫn miễn nhiễm stun (không có timer stun ở đây).
    """

    entity_type = 'commander'

    def __init__(self, x: float, y: float, name: str = "Hero",
                 hp: int = 600) -> None:
        self.x = float(x)
        self.y = float(y)
        self._hp = hp
        self._max_hp = hp
        self.is_alive = True
        self._hit_flash = 0.0
        self.name = name
        # Vector pushback — commander nhận pushback yếu hơn soldier.
        self.pushback_vx = 0.0
        self.pushback_vy = 0.0

    def take_damage(self, amount: int, dtype: str) -> None:
        if amount > 0:
            self._hp = max(0, self._hp - amount)
            print(f"  [Hero {self.name:7s}] take_damage({amount:>3}, '{dtype}')"
                  f"  → HP={self._hp}/{self._max_hp}")
        elif dtype == 'pushback':
            # Log dấu hiệu pushback (vector đã set qua attribute riêng).
            print(f"  [Hero {self.name:7s}] take_damage(0, 'pushback')")
        self._hit_flash = 0.4
        if self._hp <= 0:
            self.is_alive = False

    def update(self, dt: float) -> None:
        from AttackStrategy import RockProjectile
        RockProjectile.apply_pushback_tween(self, dt)
        if self._hit_flash > 0:
            self._hit_flash = max(0.0, self._hit_flash - dt)


class TowerDummy:
    """Tháp — 800 HP, công trình cố định, không bị knockback."""

    def __init__(self, x: float, y: float, label: str = "Tower",
                 hp: int = 800) -> None:
        self.x = float(x)
        self.y = float(y)
        self._hp = hp
        self._max_hp = hp
        self.is_alive = True
        self._hit_flash = 0.0
        self._label = label
        self._stun_timer = 0.0

    def take_damage(self, amount: int, dtype: str) -> None:
        if dtype == 'pushback':
            # Tower không bị knockback
            return
        if amount > 0:
            self._hp = max(0, self._hp - amount)
            print(f"  [{self._label:9s}] take_damage({amount:>3}, '{dtype}')"
                  f"  → HP={self._hp}/{self._max_hp}")
        self._hit_flash = 0.4
        if self._hp <= 0:
            self.is_alive = False

    def stun(self, duration: float) -> None:
        self._stun_timer = max(self._stun_timer, duration)
        print(f"  [{self._label:9s}] STUNNED {duration:.1f}s")

    def update(self, dt: float) -> None:
        if self._hit_flash > 0:
            self._hit_flash = max(0.0, self._hit_flash - dt)
        if self._stun_timer > 0:
            self._stun_timer = max(0.0, self._stun_timer - dt)


# ─── Spawn helper ──────────────────────────────────────────────────────────────

def _ok_position(x: float, y: float, others: list,
                 min_dist: float = 36.0) -> bool:
    """True nếu (x, y) cách mọi entity trong `others` >= min_dist."""
    for e in others:
        dx = e.x - x
        dy = e.y - y
        if (dx * dx + dy * dy) ** 0.5 < min_dist:
            return False
    return True


def spawn_world(width: int, height: int,
                titan_x: float, titan_y: float,
                margin: int = 60,
                min_dist_to_titan: float = 120.0,
                seed: Optional[int] = None) -> tuple:
    """Spawn 10 soldier (5 cụm + 5 random) + 3 hero + 3 tower.

    Args:
      width, height: screen size
      titan_x, titan_y: vị trí titan (entity sẽ tránh)
      margin: pad từ biên màn hình
      min_dist_to_titan: khoảng cách tối thiểu so với titan
      seed: random seed (None = không seed)

    Returns:
      (soldiers, heroes, towers) — 3 list đã spawn
    """
    rng = random.Random(seed) if seed is not None else random

    soldiers: list = []
    heroes: list = []
    towers: list = []

    def _rand_pos_avoid_titan(others: list, attempts: int = 30) -> tuple:
        """Random vị trí, tránh titan và các entity khác. Trả (x, y)."""
        for _ in range(attempts):
            x = rng.uniform(margin, width - margin)
            y = rng.uniform(margin, height - margin)
            d_titan = ((x - titan_x) ** 2 + (y - titan_y) ** 2) ** 0.5
            if d_titan < min_dist_to_titan:
                continue
            if _ok_position(x, y, others):
                return x, y
        # Fallback: cứ random
        return (rng.uniform(margin, width - margin),
                rng.uniform(margin, height - margin))

    # ── 1. 5 soldier CỤM ───────────────────────────────────────────────────────
    import math as _m
    cluster_x, cluster_y = _rand_pos_avoid_titan(soldiers + heroes + towers)
    cluster_radius = 60.0
    for i in range(5):
        x = cluster_x
        y = cluster_y
        for _ in range(20):
            ang = rng.uniform(0, 2 * _m.pi)
            r   = rng.uniform(15, cluster_radius)
            x = cluster_x + r * _m.cos(ang)
            y = cluster_y + r * _m.sin(ang)
            x = max(margin, min(width - margin, x))
            y = max(margin, min(height - margin, y))
            if _ok_position(x, y, soldiers + heroes + towers,
                            min_dist=28.0):
                break
        soldiers.append(SoldierDummy(x, y, label=f"Sld_C{i+1}"))

    # ── 2. 5 soldier RANDOM toàn map ───────────────────────────────────────────
    for i in range(5):
        x, y = _rand_pos_avoid_titan(soldiers + heroes + towers)
        soldiers.append(SoldierDummy(x, y, label=f"Sld_R{i+1}"))

    # ── 3. 3 hero random ───────────────────────────────────────────────────────
    hero_names = rng.sample(HERO_NAMES, 3)
    for i in range(3):
        x, y = _rand_pos_avoid_titan(soldiers + heroes + towers)
        heroes.append(HeroDummy(x, y, name=hero_names[i]))

    # ── 4. 3 tower random ──────────────────────────────────────────────────────
    for i in range(3):
        x, y = _rand_pos_avoid_titan(soldiers + heroes + towers,
                                     attempts=40)
        towers.append(TowerDummy(x, y, label=f"Tower{i+1}"))

    return soldiers, heroes, towers


# ─── Draw helpers ──────────────────────────────────────────────────────────────

def draw_soldier(screen, font, s: SoldierDummy) -> None:
    """Vẽ soldier — circle xanh lá r=14, có HP bar."""
    if not s.is_alive:
        return
    sx, sy = int(s.x), int(s.y)
    body = (240, 200, 80) if s._hit_flash > 0 else (100, 180, 110)
    pygame.draw.circle(screen, body, (sx, sy), 14)
    pygame.draw.circle(screen, (200, 240, 200), (sx, sy), 14, 2)
    # HP bar
    bar_w = 30
    ratio = s._hp / s._max_hp if s._max_hp > 0 else 0
    bx, by = sx - 15, sy - 24
    pygame.draw.rect(screen, (60, 0, 0), (bx, by, bar_w, 4))
    pygame.draw.rect(screen, (120, 220, 120),
                     (bx, by, int(bar_w * ratio), 4))


def draw_hero(screen, font, h: HeroDummy) -> None:
    """Vẽ hero — circle xanh-vàng r=18 với viền, tên + HP bar."""
    if not h.is_alive:
        return
    hx, hy = int(h.x), int(h.y)
    body = (240, 200, 80) if h._hit_flash > 0 else (60, 210, 90)
    pygame.draw.circle(screen, body, (hx, hy), 18)
    pygame.draw.circle(screen, (220, 220, 80), (hx, hy), 18, 3)
    # Name label
    lbl = font.render(h.name, True, (255, 255, 255))
    screen.blit(lbl, (hx - lbl.get_width() // 2, hy + 20))
    # HP bar
    bar_w = 40
    ratio = h._hp / h._max_hp if h._max_hp > 0 else 0
    bx, by = hx - 20, hy - 30
    pygame.draw.rect(screen, (60, 0, 0), (bx, by, bar_w, 5))
    pygame.draw.rect(screen, (80, 220, 80),
                     (bx, by, int(bar_w * ratio), 5))


def draw_tower(screen, font, t: TowerDummy) -> None:
    """Vẽ tower — hình vuông 40×40 xám, HP bar."""
    if not t.is_alive:
        return
    tx, ty = int(t.x), int(t.y)
    stunned = t._stun_timer > 0
    if t._hit_flash > 0:
        body = (240, 200, 80)
    elif stunned:
        body = (255, 200, 0)
    else:
        body = (130, 130, 150)
    rect = pygame.Rect(tx - 20, ty - 20, 40, 40)
    pygame.draw.rect(screen, body, rect, border_radius=4)
    pygame.draw.rect(screen, (220, 220, 240), rect, 2)
    # HP bar
    bar_w = 50
    ratio = t._hp / t._max_hp if t._max_hp > 0 else 0
    bx, by = tx - 25, ty - 32
    pygame.draw.rect(screen, (60, 0, 0), (bx, by, bar_w, 5))
    pygame.draw.rect(screen, (220, 180, 80),
                     (bx, by, int(bar_w * ratio), 5))
    # Label
    lbl = font.render(t._label, True, (220, 220, 220))
    screen.blit(lbl, (tx - lbl.get_width() // 2, ty + 22))


def draw_all(screen, font, soldiers: list, heroes: list, towers: list) -> None:
    """Vẽ toàn bộ: towers dưới, soldiers giữa, heroes trên cùng."""
    for t in towers:
        draw_tower(screen, font, t)
    for s in soldiers:
        draw_soldier(screen, font, s)
    for h in heroes:
        draw_hero(screen, font, h)


def update_all(dt: float, soldiers: list, heroes: list, towers: list) -> None:
    """Tick hit_flash + stun timer cho mọi entity."""
    for s in soldiers:
        s.update(dt)
    for h in heroes:
        h.update(dt)
    for t in towers:
        t.update(dt)
