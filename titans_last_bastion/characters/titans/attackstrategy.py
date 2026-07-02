# characters/titans/attackstrategy.py
"""Toàn bộ "cách đánh" của Titan/Boss — Strategy Pattern.

Mỗi Strategy = 1 kiểu đánh. Titan HAS-A một `_attack_strategy`;
đổi cách đánh = đổi strategy (kể cả lúc runtime).

Cách damage được tính:
    damage_thật = int(attacker._damage × strategy._mult)
    target.take_damage(damage_thật, dtype=strategy._dtype)
"""
import math
import random

import pygame

from abc import ABC, abstractmethod
from core.interfaces import IAttackable


class TitanAttackStrategy(ABC):
    """ABC cho mọi chiến thuật tấn công của Titan."""

    _DEFAULT_DAMAGE_MULT: float = 1.0
    _DEFAULT_DTYPE:       str   = 'normal'

    def __init__(self, damage_mult: float = None, dtype: str = None) -> None:
        self._mult  = self._DEFAULT_DAMAGE_MULT if damage_mult is None else damage_mult
        self._dtype = self._DEFAULT_DTYPE       if dtype       is None else dtype

    @abstractmethod
    def execute(self, attacker, target: IAttackable):
        ...

    def compute_damage(self, attacker) -> int:
        return int(getattr(attacker, '_damage', 0) * self._mult)


# ── NHÓM 1: Cận chiến ────────────────────────────────────────────

class MeleeRushStrategy(TitanAttackStrategy):
    """Lao vào đánh cận chiến."""

    _DEFAULT_DAMAGE_MULT = 1.5
    _DEFAULT_DTYPE       = 'normal'

    def execute(self, attacker, target: IAttackable):
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)


class HeavyStrikeStrategy(TitanAttackStrategy):
    """Đòn đánh nặng — damage nhân lớn."""

    _DEFAULT_DAMAGE_MULT = 3.5
    _DEFAULT_DTYPE       = 'heavy'

    def execute(self, attacker, target: IAttackable):
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)


class Incurable(TitanAttackStrategy):
    """Cắn chặn hồi máu — damage thấp đổi debuff `antiheal`.

    dtype='antiheal' — target tự xử lý: thấy dtype này thì set cờ
    ngăn regen trong vài giây tới.
    """

    _DEFAULT_DAMAGE_MULT = 2.5
    _DEFAULT_DTYPE       = 'antiheal'

    def execute(self, attacker, target: IAttackable):
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)


# ── NHÓM 2: Giáp cứng ────────────────────────────────────────────

class ArmoredRamStrategy(TitanAttackStrategy):
    """Húc với giáp cứng — damage cao nhờ momentum."""

    _DEFAULT_DAMAGE_MULT = 6.7
    _DEFAULT_DTYPE       = 'ram'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 armor_reduction: float = 0.6) -> None:
        super().__init__(damage_mult, dtype)
        self._armor_reduction = armor_reduction

    def execute(self, attacker, target: IAttackable):
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)


# ── NHÓM 4: Nặng / AoE ───────────────────────────────────────────

class GroundSlamStrategy(TitanAttackStrategy):
    """Đập đất — damage + stun tháp trong bán kính."""

    _DEFAULT_DAMAGE_MULT = 4.0
    _DEFAULT_DTYPE       = 'stomp'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 radius: float = 160.0, stun_duration: float = 3.0) -> None:
        super().__init__(damage_mult, dtype)
        self._radius        = radius
        self._stun_duration = stun_duration

    def execute(self, attacker, target: IAttackable):
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)
        from systems.world_query import WorldQuery
        towers = WorldQuery.find_in_radius(attacker.x, attacker.y, self._radius, 'tower')
        for tower in towers:
            if callable(getattr(tower, 'stun', None)):
                tower.stun(self._stun_duration)


class Explosion(TitanAttackStrategy):
    """Phát nổ AoE quanh attacker — dành cho Kamikaze (suicide bomber).

    Center damage tại vị trí `attacker`. Target chính ăn `damage_main`,
    soldier khác trong AoE ăn `damage_splash`. Knockback đẩy soldier ra xa.
    """

    _DEFAULT_DAMAGE_MULT = 6.7
    _DEFAULT_DTYPE       = 'explode'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 splash_ratio: float = 0.5,
                 radius: float = 80.0, knockback: float = 60.0) -> None:
        super().__init__(damage_mult, dtype)
        self._splash_ratio = splash_ratio
        self._radius       = radius
        self._knockback    = knockback

    def execute(self, attacker, target: IAttackable):
        from systems.world_query import WorldQuery
        damage_main   = self.compute_damage(attacker)
        damage_splash = int(damage_main * self._splash_ratio)

        # Damage target chính
        if target is not None:
            target.take_damage(amount=damage_main, dtype=self._dtype)

        # Damage splash: mọi entity type gần đó (soldier, commander, tower)
        seen = {id(target)} if target else set()
        for etype in ('soldier', 'commander', 'tower'):
            nearby = WorldQuery.find_in_radius(
                attacker.x, attacker.y, self._radius, etype)
            for e in nearby:
                if id(e) in seen:
                    continue
                if not getattr(e, 'is_alive', True):
                    continue
                seen.add(id(e))
                e.take_damage(amount=damage_splash, dtype=self._dtype)
                # Knockback cho soldiers
                if etype == 'soldier':
                    dx = e.x - attacker.x
                    dy = e.y - attacker.y
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist > 0:
                        e.x += (dx / dist) * self._knockback
                        e.y += (dy / dist) * self._knockback


# ── NHÓM 5: Mục tiêu đặc biệt ────────────────────────────────────

class TowerHunterStrategy(TitanAttackStrategy):
    """Chuyên phá tháp — damage bonus khi tấn công Tower.

    Dùng isinstance check với Tower để bonus ×1.5.
    """

    _DEFAULT_DAMAGE_MULT = 3.0
    _DEFAULT_DTYPE       = 'siege'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 tower_bonus_mult: float = 1.5) -> None:
        super().__init__(damage_mult, dtype)
        self._tower_bonus_mult = tower_bonus_mult

    def execute(self, attacker, target: IAttackable):
        from structures.towers.tower import Tower
        base = self.compute_damage(attacker)
        if isinstance(target, Tower):
            target.take_damage(amount=int(base * self._tower_bonus_mult), dtype=self._dtype)
        else:
            target.take_damage(amount=base, dtype=self._dtype)


class SoldierHunterStrategy(TitanAttackStrategy):
    """Chuyên săn lính — cleave AoE quanh ATTACKER, trúng mọi loại entity.

    Target chính: damage × _mult, dtype='soldier'.
    Mọi entity trong bán kính `_splash_radius` quanh ATTACKER: damage × _splash_mult, dtype='aoe'.
    """

    _DEFAULT_DAMAGE_MULT = 3.0
    _DEFAULT_DTYPE       = 'soldier'

    _SPLASH_ENTITY_TYPES: tuple = ('soldier', 'commander', 'tower', 'wall', 'hq')

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 splash_radius: float = 120.0, splash_mult: float = 0.5,
                 splash_dtype: str = 'aoe') -> None:
        super().__init__(damage_mult, dtype)
        self._splash_radius = splash_radius
        self._splash_mult   = splash_mult
        self._splash_dtype  = splash_dtype

    def execute(self, attacker, target: IAttackable):
        base = self.compute_damage(attacker)
        target.take_damage(amount=base, dtype=self._dtype)

        from systems.world_query import WorldQuery
        splash_dmg = int(base * self._splash_mult)
        seen_ids: set = {id(target)}
        for etype in self._SPLASH_ENTITY_TYPES:
            for e in WorldQuery.find_in_radius(
                    attacker.x, attacker.y, self._splash_radius, etype):
                if id(e) in seen_ids:
                    continue
                seen_ids.add(id(e))
                e.take_damage(amount=splash_dmg, dtype=self._splash_dtype)


# ── NHÓM 6: Projectile / Particle phụ trợ ────────────────────────

class RockProjectile:
    """Viên đá ném — bay parabol từ tay beast về hướng target.

    Khi land: AoE damage + pushback tween lên soldier/commander.
    Gọi `apply_pushback_tween(entity, dt)` trong update() của Soldier/Commander.
    """

    _PUSHBACK_DECAY: float = 5.0

    def __init__(self, start_x: float, start_y: float, target,
                 velocity: float = 250.0, angle_deg: float = 15.0,
                 gravity: float = 600.0,
                 damage_main: int = 80, damage_splash: int = 40,
                 aoe_radius: float = 80.0,
                 pushback_soldier: float = 100.0,
                 pushback_commander: float = 50.0,
                 beast_x: float = None,
                 beast_y: float = None) -> None:
        self.x = float(start_x)
        self.y = float(start_y)
        self._target = target
        self._beast_x = float(beast_x) if beast_x is not None else float(start_x)
        self._beast_y = float(beast_y) if beast_y is not None else float(start_y)

        dx = target.x - start_x
        dy = target.y - start_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0:
            ux, uy = dx / dist, dy / dist
        else:
            ux, uy = 0.0, 1.0

        angle_rad        = math.radians(angle_deg)
        horizontal_speed = velocity * math.cos(angle_rad)
        self.vx = ux * horizontal_speed
        self.vy = uy * horizontal_speed

        self.z  = 0.0
        self.vz = velocity * math.sin(angle_rad)
        self._gravity = gravity

        self._damage_main        = damage_main
        self._damage_splash      = damage_splash
        self._aoe_radius         = aoe_radius
        self._pushback_soldier   = pushback_soldier
        self._pushback_commander = pushback_commander

        self.alive   = True
        self._landed = False
        self._spin      = random.uniform(-180, 180)
        self._rot_angle = 0.0

    def update(self, dt: float) -> bool:
        if not self.alive:
            return False

        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z += self.vz * dt
        self.vz -= self._gravity * dt
        self._rot_angle += self._spin * dt

        if self.z <= 0 and self.vz < 0:
            self.z = 0.0
            self._landed = True
            self.alive   = False
            self._on_land()
            return False
        return True

    def _on_land(self) -> None:
        """Áp damage AoE + pushback tween tại điểm rơi."""
        from systems.world_query import WorldQuery

        type_map: dict = {}
        candidates = []
        for etype in ('tower', 'soldier', 'commander', 'wall', 'hq'):
            hits = WorldQuery.find_in_radius(
                cx=self.x, cy=self.y, radius=self._aoe_radius, entity_type=etype)
            for e in hits:
                type_map[id(e)] = etype
            candidates.extend(hits)

        if (self._target is not None
                and getattr(self._target, 'is_alive', False)
                and id(self._target) not in type_map):
            candidates.append(self._target)
            # Dùng ENTITY_TYPE (uppercase) để đồng bộ với hệ thống chính
            type_map[id(self._target)] = getattr(
                self._target, 'ENTITY_TYPE', 'soldier')

        bdx = self.x - self._beast_x
        bdy = self.y - self._beast_y
        bdist = (bdx * bdx + bdy * bdy) ** 0.5
        if bdist > 0:
            forward_x, forward_y = bdx / bdist, bdy / bdist
        else:
            forward_x, forward_y = None, None

        seen = set()
        for e in candidates:
            if id(e) in seen:
                continue
            seen.add(id(e))
            if e is self._target:
                e.take_damage(amount=self._damage_main, dtype='rock')
            else:
                e.take_damage(amount=self._damage_splash, dtype='rock')

            etype = type_map.get(id(e))
            if etype == 'soldier':
                max_push = self._pushback_soldier
            elif etype == 'commander':
                max_push = self._pushback_commander
            else:
                continue

            dx = e.x - self.x
            dy = e.y - self.y
            dist = (dx * dx + dy * dy) ** 0.5
            falloff = max(0.0, 1.0 - dist / self._aoe_radius) if self._aoe_radius > 0 else 1.0
            push_dist = max_push * falloff
            if push_dist <= 0:
                continue

            for _ in range(8):
                theta = random.uniform(0, 2 * math.pi)
                dir_x = math.cos(theta)
                dir_y = math.sin(theta)
                if forward_x is None:
                    break
                if dir_x * forward_x + dir_y * forward_y >= 0.0:
                    break
            else:
                dir_x, dir_y = forward_x, forward_y

            decay = self._PUSHBACK_DECAY
            vx_push = dir_x * push_dist * decay
            vy_push = dir_y * push_dist * decay
            e.pushback_vx = getattr(e, 'pushback_vx', 0.0) + vx_push
            e.pushback_vy = getattr(e, 'pushback_vy', 0.0) + vy_push
            try:
                e.take_damage(amount=0, dtype='pushback')
            except Exception:
                pass

    @staticmethod
    def apply_pushback_tween(entity, dt: float) -> None:
        """Tích phân vector pushback của entity qua 1 frame.

        Gọi trong `update(dt)` của Soldier/Commander:
            RockProjectile.apply_pushback_tween(self, dt)
        """
        vx = getattr(entity, 'pushback_vx', 0.0)
        vy = getattr(entity, 'pushback_vy', 0.0)
        if vx == 0.0 and vy == 0.0:
            return
        entity.x += vx * dt
        entity.y += vy * dt
        factor = math.exp(-RockProjectile._PUSHBACK_DECAY * dt)
        vx *= factor
        vy *= factor
        if abs(vx) < 1.0 and abs(vy) < 1.0:
            vx = 0.0
            vy = 0.0
        entity.pushback_vx = vx
        entity.pushback_vy = vy

    def draw(self, screen: pygame.Surface, rock_frame: pygame.Surface) -> None:
        if not self.alive:
            return
        draw_x = int(self.x)
        draw_y = int(self.y - self.z)
        if rock_frame is not None:
            rotated = pygame.transform.rotate(rock_frame, self._rot_angle)
            rect = rotated.get_rect(center=(draw_x, draw_y))
            screen.blit(rotated, rect)
        else:
            pygame.draw.circle(screen, (110, 90, 70), (draw_x, draw_y), 8)
            pygame.draw.circle(screen, (60, 50, 40), (draw_x, draw_y), 8, 2)
        shadow_alpha = max(40, 120 - int(self.z))
        shadow_surf = pygame.Surface((20, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (0, 0, 0, shadow_alpha), (0, 0, 20, 8))
        screen.blit(shadow_surf, (int(self.x) - 10, int(self.y) - 4))


class HeatParticle:
    """Hạt hiệu ứng hơi nóng — vòng tròn xám mờ dần và phình to.

    Cơ chế "tan dần từng hạt": `_spawn_delay` random → stagger xuất hiện;
    `_lifetime` random → mỗi hạt tan theo nhịp riêng; alpha ease-out `(1-t)²`.
    """

    def __init__(self, cx: float, cy: float) -> None:
        self.x = float(cx)
        self.y = float(cy)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(20, 70)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self._radius      = random.uniform(4, 10)
        self._max_r       = random.uniform(15, 35)
        self._alpha       = 0
        self._spawn_delay = random.uniform(0.0, 0.8)
        self._lifetime    = random.uniform(1.5, 4.5)
        self._age         = 0.0

    def update(self, dt: float) -> bool:
        if self._spawn_delay > 0.0:
            self._spawn_delay -= dt
            self._alpha = 0
            return True

        self._age += dt
        t = min(self._age / self._lifetime, 1.0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.93
        self.vy *= 0.93
        self._radius += (self._max_r - self._radius) * dt * 3
        fade = (1.0 - t) ** 2
        self._alpha = int(200 * fade)
        return self._age < self._lifetime

    def draw(self, screen: pygame.Surface) -> None:
        if self._alpha <= 0 or self._radius < 1:
            return
        r = int(self._radius)
        surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (160, 160, 160, self._alpha), (r, r), r)
        screen.blit(surf, (int(self.x) - r, int(self.y) - r))
