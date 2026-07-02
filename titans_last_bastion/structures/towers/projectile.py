# structures/towers/projectile.py
from core.entity import Entity
import os
import pygame
import math
from structures.towers.visual_effects import load_animation_strip, load_spritesheet, TransientEffect


# ═══════════════════════════════════════════════════════
#  PROJECTILE BASE
# ═══════════════════════════════════════════════════════

class Projectile(Entity):
    """
    Đạn bay từ tháp đến mục tiêu, khi đến nơi gọi _on_hit().

    Bay theo đường thẳng với SPEED px/s.
    Nếu mục tiêu chết trước khi đến → tự hủy (is_alive = False).
    Class con override _on_hit() để định nghĩa hiệu ứng khi trúng.
    """

    SPEED = 400  # px/s — class con override nếu cần

    def __init__(self, x: float, y: float, target, damage: int, dtype: str,
                 shooter=None):
        super().__init__(x, y)
        self._target  = target
        self._damage  = damage
        self._dtype   = dtype
        self._shooter = shooter

    def update(self, dt: float):
        if not self._target.is_alive:
            self.is_alive = False
            return
        dx = self._target.x - self.x
        dy = self._target.y - self.y
        dist = (dx ** 2 + dy ** 2) ** 0.5
        step = self.SPEED * dt
        if dist <= step:
            self.x, self.y = self._target.x, self._target.y
            self._on_hit(self._target)
            self.is_alive = False
        else:
            self.x += dx / dist * step
            self.y += dy / dist * step
            self.angle = math.degrees(math.atan2(-dy, dx)) # Rotate based on trajectory

    def _notify_shooter(self, target) -> None:
        """Gọi notify_attacked trên titan bị bắn — dùng chung cho mọi subclass."""
        if self._shooter is not None:
            ai = getattr(target, '_ai', None)
            if ai is not None:
                ai.notify_attacked(self._shooter)

    def _on_hit(self, target):
        target.take_damage(self._damage, self._dtype)
        self._notify_shooter(target)

    def draw(self, screen): pass


# ═══════════════════════════════════════════════════════
#  PROJECTILE CỤ THỂ
# ═══════════════════════════════════════════════════════

class BasicProjectile(Projectile):
    """Đạn thường — chỉ gây damage normal. Sprite 1 frame xoay về phía target."""

    def __init__(self, x: float, y: float, target, damage: int, dtype: str = 'normal',
                 shooter=None):
        super().__init__(x, y, target, damage, dtype, shooter)
        self.angle = 0
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'base')
        try:
            self._sprite = pygame.image.load(os.path.join(base_dir, 'lv1.png')).convert_alpha()
        except Exception as e:
            print("BasicProjectile sprite error:", e)
            self._sprite = None

    def draw(self, screen):
        if self._sprite:
            rotated = pygame.transform.rotate(self._sprite, self.angle)
            rect = rotated.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(rotated, rect.topleft)
        else:
            pygame.draw.circle(screen, (200, 200, 50), (int(self.x), int(self.y)), 5)


class ExplosiveProjectile(Projectile):
    """
    Đạn nổ (BasicTower Lv2) — khi trúng:
        1. Damage mục tiêu chính + mọi titan trong explosion_radius (cùng damage, dtype 'fire')
        2. Spawn explosion VFX (lv2Explosion .png — 4 cols × 4 rows)
    """

    def __init__(self, x: float, y: float, target, damage: int,
                 explosion_radius: float, shooter=None):
        super().__init__(x, y, target, damage, 'fire', shooter)
        self._explosion_radius = explosion_radius
        self.angle = 0
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'base')
        try:
            self._sprite = pygame.image.load(os.path.join(base_dir, 'lv2.png')).convert_alpha()
        except Exception as e:
            print("ExplosiveProjectile sprite error:", e)
            self._sprite = None

    def draw(self, screen):
        if self._sprite:
            rotated = pygame.transform.rotate(self._sprite, self.angle)
            rect = rotated.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(rotated, rect.topleft)
        else:
            pygame.draw.circle(screen, (255, 120, 0), (int(self.x), int(self.y)), 7)

    def _on_hit(self, target):
        target.take_damage(self._damage, 'fire')
        self._notify_shooter(target)
        from systems.world_query import WorldQuery
        for t in WorldQuery.find_in_radius(
            cx=target.x, cy=target.y,
            radius=self._explosion_radius,
            entity_type='titan'
        ):
            if t is not target:
                t.take_damage(self._damage, 'fire')

        # Explosion VFX — size tương đương explosion_radius
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'base')
        try:
            expl_anim = load_spritesheet(
                os.path.join(base_dir, 'lv2Explosion .png'),
                cols=4, rows=4, fps=30, loop=False
            )
            # Scale VFX frame để khớp với explosion_radius
            r = int(self._explosion_radius)
            scaled_frames = []
            for f in expl_anim.frames:
                scaled_frames.append(pygame.transform.scale(f, (r * 2, r * 2)))
            expl_anim.frames = scaled_frames
            WorldQuery.spawn_entity(TransientEffect(target.x, target.y, expl_anim))
        except Exception as e:
            print("Explosion VFX error:", e)


class ElectricProjectile(Projectile):
    """
    Đạn điện — khi trúng:
        1. Damage mục tiêu chính (dtype 'electric')
        2. Chain lightning: titan trong chain_range nhận chain_damage
        3. Nếu spawn_field=True → spawn ElectricField tại vị trí trúng (Lv3)
    """

    def __init__(self, x: float, y: float, target, damage: int,
                 chain_damage: int, chain_range: float, spawn_field: bool = False, level: int = 1,
                 shooter=None):
        super().__init__(x, y, target, damage, 'electric', shooter)
        self._chain_damage = chain_damage
        self._chain_range  = chain_range
        self._spawn_field  = spawn_field
        self.level = level
        self.angle = 0
        
        # Load đạn bay (mô phỏng theo level)
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'elec')
        try:
            from structures.towers.visual_effects import load_animation_strip
            if self.level == 1:
                self.anim_loop = load_animation_strip(os.path.join(base_dir, 'lv1.png'), 5, fps=30, loop=True)
            else:
                self.anim_loop = load_animation_strip(os.path.join(base_dir, 'lv2.png'), 16, fps=30, loop=True, loop_start_frame=8)
        except:
            self.anim_loop = None

    def update(self, dt: float):
        super().update(dt)
        if self.anim_loop:
            self.anim_loop.update(dt)

    def draw(self, screen):
        import pygame
        if self.anim_loop:
            frame = self.anim_loop.get_current_frame()
            rotated_frame = pygame.transform.rotate(frame, self.angle)
            rect = rotated_frame.get_rect(center=(self.x, self.y))
            screen.blit(rotated_frame, rect.topleft)
        else:
            pygame.draw.line(screen, (0, 255, 255), (self.x-5, self.y-5), (self.x+5, self.y+5), 2)

    def _on_hit(self, target):
        target.take_damage(self._damage, 'electric')
        self._notify_shooter(target)
        self._spawn_hit_vfx(target.x, target.y)
        
        from systems.world_query import WorldQuery
        for t in WorldQuery.find_in_radius(
            cx=target.x, cy=target.y,
            radius=self._chain_range,
            entity_type='titan'
        ):
            if t is not target:
                t.take_damage(self._chain_damage, 'electric')
                self._spawn_hit_vfx(t.x, t.y)
                
        if self._spawn_field:
            WorldQuery.spawn_entity(
                ElectricField(target.x, target.y, self._chain_range, self._chain_damage)
            )
            
    def _spawn_hit_vfx(self, x, y):
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'elec')
        try:
            from structures.towers.visual_effects import load_animation_strip, TransientEffect
            hit_anim = load_animation_strip(os.path.join(base_dir, 'Thunder hit w blur.png'), 6, fps=30, loop=False)
            hit_effect = TransientEffect(x, y, hit_anim, angle=0)
            from systems.world_query import WorldQuery
            WorldQuery.spawn_entity(hit_effect)
        except:
            pass


class IceProjectile(Projectile):
    """
    Đạn băng — khi trúng:
        1. Damage mục tiêu chính (dtype 'ice') + apply_slow
        2. Nếu splash_radius > 0 → titan xung quanh cũng bị slow (Lv2+)
    """

    def __init__(self, x: float, y: float, target, damage: int,
                 slow_factor: float, slow_duration: float, splash_radius: float = 0,
                 shooter=None):
        super().__init__(x, y, target, damage, 'ice', shooter)
        self._slow_factor    = slow_factor
        self._slow_duration  = slow_duration
        self._splash_radius  = splash_radius
        self.angle = 0
        
        # Load animations
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'ice')
        self.anim_start = load_animation_strip(os.path.join(base_dir, 'Ice VFX 1 Start.png'), 3, fps=30, loop=False)
        self.anim_loop = load_animation_strip(os.path.join(base_dir, 'Ice VFX 1 Repeatable.png'), 10, fps=30, loop=True)
        self.state = "start"

    def update(self, dt: float):
        super().update(dt)
        if self.state == "start":
            self.anim_start.update(dt)
            if self.anim_start.finished:
                self.state = "loop"
        elif self.state == "loop":
            self.anim_loop.update(dt)

    def draw(self, screen):
        if self.state == "start":
            frame = self.anim_start.get_current_frame()
        else:
            frame = self.anim_loop.get_current_frame()
            
        rotated_frame = pygame.transform.rotate(frame, self.angle)
        rect = rotated_frame.get_rect(center=(self.x, self.y))
        screen.blit(rotated_frame, rect.topleft)

    def _apply_slow(self, t):
        if hasattr(t, 'apply_slow'):
            t.apply_slow(self._slow_factor, self._slow_duration)
            
        # Sinh ra hiệu ứng đóng băng dính dưới chân target
        try:
            base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'ice')
            from structures.towers.visual_effects import AttachedStatusVFX, load_animation_strip
            anim_start = load_animation_strip(os.path.join(base_dir, 'Ice VFX 2 Start.png'), 9, fps=30, loop=False)
            anim_active = load_animation_strip(os.path.join(base_dir, 'Ice VFX 2 Active.png'), 8, fps=30, loop=False)
            anim_end = load_animation_strip(os.path.join(base_dir, 'Ice VFX 2 Ending.png'), 18, fps=30, loop=False)
            
            slow_vfx = AttachedStatusVFX(t, anim_start, anim_active, anim_end, self._slow_duration, scale=2.4)
            from systems.world_query import WorldQuery
            WorldQuery.spawn_entity(slow_vfx)
        except Exception as e:
            print("Lỗi load ảnh VFX 2:", e)

    def _on_hit(self, target):
        target.take_damage(self._damage, 'ice')
        self._notify_shooter(target)
        self._apply_slow(target)
        if self._splash_radius > 0:
            from systems.world_query import WorldQuery
            for nearby in WorldQuery.find_in_radius(
                cx=target.x, cy=target.y,
                radius=self._splash_radius,
                entity_type='titan'
            ):
                if nearby is not target:
                    self._apply_slow(nearby)
        
        # Spawn hit effect
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'ice')
        hit_anim = load_animation_strip(os.path.join(base_dir, 'Ice VFX 1 Hit.png'), 8, fps=30, loop=False)
        hit_effect = TransientEffect(self.x, self.y, hit_anim, angle=self.angle)
        from systems.world_query import WorldQuery
        WorldQuery.spawn_entity(hit_effect)


class WaterProjectile(Projectile):
    """
    Đạn nước — khi trúng:
        Lv1 (vortex_mode=False):
            Damage + knockback mục tiêu + AoE knockback trong push_radius
        Lv2 (vortex_mode=True):
            Damage + spawn WaterVortex tại vị trí trúng

    Sprite bay:
        WaterBall - Startup and Infinite.png — 6 cols × 5 rows (25 frames valid,
        hàng cuối chỉ 1 frame). Startup chạy frames 0-24, loop 6 frames cuối (19-24).

    Hit VFX:
        WaterBall - Impact.png          — 4 cols × 4 rows, play once (luôn xuất hiện)
        WaterBall - KnockBack.png       — 5 cols × 4 rows, play once (chỉ Lv1)
    """

    def __init__(self, x: float, y: float, target, damage: int,
                 push_radius: float, push_force: float, kb_duration: float,
                 vortex_mode: bool = False, shooter=None):
        super().__init__(x, y, target, damage, 'water', shooter)
        self._push_radius = push_radius
        self._push_force  = push_force
        self._kb_duration = kb_duration
        self._vortex_mode = vortex_mode
        self.angle = 0

        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'water')
        try:
            # 6×5 sheet nhưng hàng cuối chỉ 1 frame → trim về 25 frames
            anim = load_spritesheet(
                os.path.join(base_dir, 'WaterBall - Startup and Infinite.png'),
                cols=5, rows=5, fps=30, loop=True, loop_start_frame=16
            )
            anim.frames = anim.frames[:21]
            self._anim = anim
        except:
            self._anim = None

    def update(self, dt: float):
        super().update(dt)
        if self._anim:
            self._anim.update(dt)

    def draw(self, screen):
        if self._anim:
            frame = self._anim.get_current_frame()
            rotated = pygame.transform.rotate(frame, self.angle)
            rect = rotated.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(rotated, rect.topleft)
        else:
            pygame.draw.circle(screen, (0, 100, 255), (int(self.x), int(self.y)), 7)

    def _knockback(self, t):
        if not hasattr(t, 'apply_knockback'):
            return
        # Đẩy ngược hướng titan đang di chuyển (_vx/_vy)
        vx = getattr(t, '_vx', 0.0)
        vy = getattr(t, '_vy', 0.0)
        speed = (vx ** 2 + vy ** 2) ** 0.5
        if speed < 1.0:
            # Titan đứng yên → đẩy ngược hướng từ projectile đến titan
            dx = t.x - self.x
            dy = t.y - self.y
            d = (dx ** 2 + dy ** 2) ** 0.5 or 1.0
            vx, vy, speed = dx / d, dy / d, 1.0
        kb_speed = self._push_force * 0.6 / max(self._kb_duration, 0.01)
        t.apply_knockback(-vx / speed * kb_speed, -vy / speed * kb_speed, self._kb_duration)

    def _on_hit(self, target):
        target.take_damage(self._damage, 'water')
        self._notify_shooter(target)
        from systems.world_query import WorldQuery
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'water')

        # Impact VFX — luôn xuất hiện (4 cols × 4 rows)
        try:
            impact_anim = load_spritesheet(
                os.path.join(base_dir, 'WaterBall - Impact.png'),
                cols=4, rows=4, fps=30, loop=False
            )
            WorldQuery.spawn_entity(TransientEffect(target.x, target.y, impact_anim))
        except Exception as e:
            print("Impact VFX error:", e)

        if not self._vortex_mode:
            # Lv1: knockback
            self._knockback(target)
            for nearby in WorldQuery.find_in_radius(
                cx=target.x, cy=target.y,
                radius=self._push_radius,
                entity_type='titan'
            ):
                if nearby is not target:
                    self._knockback(nearby)
            # Knockback VFX (5 cols × 4 rows)
            try:
                kb_anim = load_spritesheet(
                    os.path.join(base_dir, 'knockback.png'),
                    cols=5, rows=4, fps=30, loop=False
                )
                WorldQuery.spawn_entity(TransientEffect(target.x, target.y, kb_anim))
            except Exception as e:
                print("KB VFX error:", e)
        else:
            # Lv2: spawn vortex
            WorldQuery.spawn_entity(WaterVortex(target.x, target.y, self._push_radius))


# ═══════════════════════════════════════════════════════
#  HIỆU ỨNG VÙNG (spawn bởi projectile khi trúng)
# ═══════════════════════════════════════════════════════

class ElectricField(Entity):
    """
    Điện trường tồn tại DURATION giây (spawn bởi ElectricProjectile Lv3).
    Mỗi ZAP_PERIOD giây giật tất cả titan trong radius.
    """

    DURATION   = 5.0
    ZAP_PERIOD = 0.5

    def __init__(self, x: float, y: float, radius: float, damage: int):
        super().__init__(x, y)
        self._radius    = radius
        self._damage    = damage
        self._lifetime  = self.DURATION
        self._zap_timer = 0.0
        self._angle     = 0.0   # Rotation accumulator for arc animation
        self._pulse     = 0.0   # Pulse oscillation

    def update(self, dt: float):
        self._lifetime -= dt
        if self._lifetime <= 0:
            self.is_alive = False
            return
        self._angle += dt * 120   # Rotate 120 degrees/sec
        self._pulse += dt * 6     # Pulse oscillation
        self._zap_timer -= dt
        if self._zap_timer <= 0:
            self._zap_timer = self.ZAP_PERIOD
            from systems.world_query import WorldQuery
            for titan in WorldQuery.find_in_radius(
                cx=self.x, cy=self.y,
                radius=self._radius,
                entity_type='titan'
            ):
                titan.take_damage(self._damage, 'electric')
                # Spawn zap VFX
                from structures.towers.visual_effects import load_animation_strip, TransientEffect
                base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'elec')
                try:
                    hit_anim = load_animation_strip(os.path.join(base_dir, 'Thunder hit w blur.png'), 6, fps=30, loop=False)
                    WorldQuery.spawn_entity(TransientEffect(titan.x, titan.y, hit_anim))
                except:
                    pass

    def draw(self, screen):
        import math
        r = self._radius
        life_ratio = self._lifetime / self.DURATION
        alpha = int(life_ratio * 220)
        pulse = (math.sin(self._pulse) + 1) / 2  # 0.0 ~ 1.0

        size = int(r * 2 + 20)
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        cx, cy = size // 2, size // 2

        # === Layer 1: Pulsing inner glow ===
        inner_r = int(r * 0.6 + r * 0.1 * pulse)
        inner_alpha = max(0, int((alpha - 100) * 0.6))
        pygame.draw.circle(surface, (180, 130, 0, inner_alpha), (cx, cy), inner_r)

        # === Layer 2: Mid-ring glow ===
        pygame.draw.circle(surface, (255, 200, 0, max(0, alpha - 60)), (cx, cy), int(r * 0.85), 3)

        # === Layer 3: Outer boundary ring ===
        pygame.draw.circle(surface, (255, 240, 80, alpha), (cx, cy), r, 2)

        # === Layer 4: 4 rotating lightning arc arms ===
        base_angle_rad = math.radians(self._angle)
        num_arms = 4
        for i in range(num_arms):
            arm_angle = base_angle_rad + (2 * math.pi / num_arms) * i
            mid_r = r * 0.5
            tip_r = r * 0.9
            zag_offset = math.pi / 8

            mx = cx + math.cos(arm_angle + zag_offset) * mid_r
            my = cy + math.sin(arm_angle + zag_offset) * mid_r
            ex = cx + math.cos(arm_angle) * tip_r
            ey = cy + math.sin(arm_angle) * tip_r

            bolt_alpha = max(0, alpha - 20)
            pygame.draw.line(surface, (255, 220, 50, bolt_alpha), (cx, cy), (int(mx), int(my)), 2)
            pygame.draw.line(surface, (255, 255, 150, bolt_alpha), (int(mx), int(my)), (int(ex), int(ey)), 1)

            tip_glow = max(0, alpha - 40)
            pygame.draw.circle(surface, (255, 255, 255, tip_glow), (int(ex), int(ey)), 3)

        # === Layer 5: 3 counter-rotating secondary arcs ===
        base_angle_rad2 = math.radians(-self._angle * 0.7)
        for i in range(3):
            arm_angle = base_angle_rad2 + (2 * math.pi / 3) * i
            ex = cx + math.cos(arm_angle) * (r * 0.75)
            ey = cy + math.sin(arm_angle) * (r * 0.75)
            sec_alpha = max(0, int(alpha * 0.6))
            pygame.draw.line(surface, (255, 200, 0, sec_alpha), (cx, cy), (int(ex), int(ey)), 1)

        screen.blit(surface, (self.x - cx, self.y - cy))


class WaterVortex(Entity):
    """
    Xoáy nước tồn tại DURATION giây (spawn bởi WaterProjectile Lv2).

    Animation:
        startup — Vortex - Startup.png: 4 cols × 3 rows = 12 frames,
                  chạy frames 0-3 một lần rồi loop 8 frames cuối (4-11)
        end     — Vortex - End.png: 3 cols × 3 rows = 9 frames, play once

    Draw:
        - Vòng tròn xanh bán trong suốt thể hiện vùng ảnh hưởng
        - Animation vortex ở tâm

    Physics:
        - Titan trong radius bị hút vào tâm theo hình xoắn ốc mỗi frame
    """

    DURATION   = 3.0
    PULL_SPEED = 40
    SPIN_SPEED = 60
    MIN_DIST   = 10

    def __init__(self, x: float, y: float, radius: float):
        super().__init__(x, y)
        self._radius   = radius
        self._lifetime = self.DURATION
        self._state    = "startup"

        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'water')
        try:
            # 4 cols × 3 rows: chạy 4 frame đầu một lần, rồi loop 8 frame cuối
            self._anim_startup = load_spritesheet(
                os.path.join(base_dir, 'vortex Startup and Infinite.png'),
                cols=4, rows=3, fps=30, loop=True, loop_start_frame=4
            )
            # 3 cols × 3 rows: play once
            self._anim_end = load_spritesheet(
                os.path.join(base_dir, 'vortex end.png'),
                cols=3, rows=3, fps=30, loop=False
            )
            self._end_duration = len(self._anim_end.frames) / self._anim_end.fps
        except Exception as e:
            print("Vortex VFX error:", e)
            self._anim_startup = None
            self._anim_end     = None
            self._end_duration = 0.3

    def update(self, dt: float):
        self._lifetime -= dt
        if self._lifetime <= 0:
            self.is_alive = False
            return

        # Chuyển sang end khi vừa đủ thời gian chạy anim_end
        if self._state == "startup" and self._lifetime <= self._end_duration:
            self._state = "end"
            if self._anim_end:
                self._anim_end.reset()

        if self._state == "startup" and self._anim_startup:
            self._anim_startup.update(dt)
        elif self._state == "end" and self._anim_end:
            self._anim_end.update(dt)
            if self._anim_end.finished:
                self.is_alive = False
                return

        from systems.world_query import WorldQuery
        for titan in WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self._radius,
            entity_type='titan'
        ):
            self._apply_spiral(titan, dt)

    def _apply_spiral(self, titan, dt: float):
        dx = self.x - titan.x
        dy = self.y - titan.y
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist < self.MIN_DIST:
            return
        rx, ry = dx / dist, dy / dist
        tx, ty = -ry, rx
        titan.x += (rx * self.PULL_SPEED + tx * self.SPIN_SPEED) * dt
        titan.y += (ry * self.PULL_SPEED + ty * self.SPIN_SPEED) * dt

    def draw(self, screen):
        r = int(self._radius)
        life_ratio = max(0.0, self._lifetime / self.DURATION)

        # Vòng tròn xanh thể hiện vùng ảnh hưởng — fade out dần
        circle_alpha = int(life_ratio * 150)
        surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        cx, cy = r + 2, r + 2
        pygame.draw.circle(surf, (30, 140, 255, max(0, circle_alpha // 2)), (cx, cy), r)
        pygame.draw.circle(surf, (80, 200, 255, circle_alpha), (cx, cy), r, 2)
        screen.blit(surf, (int(self.x) - cx, int(self.y) - cy))

        # Animation vortex ở tâm
        frame = None
        if self._state == "startup" and self._anim_startup:
            frame = self._anim_startup.get_current_frame()
        elif self._state == "end" and self._anim_end:
            frame = self._anim_end.get_current_frame()
        if frame:
            rect = frame.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(frame, rect.topleft)
