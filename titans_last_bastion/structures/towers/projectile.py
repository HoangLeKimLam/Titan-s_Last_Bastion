# structures/towers/projectile.py
from core.entity import Entity
from config import balance
import os
import pygame
import math
from systems.sound_system import SoundManager
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

    SPEED = balance.TOWER_PROJECTILE_SPEED  # px/s — class con override nếu cần

    def __init__(self, x: float, y: float, target, damage: int, dtype: str,
                 shooter=None):
        """Tạo đạn nhắm `target` — mang theo damage/dtype/shooter để `_on_hit()` dùng khi trúng.

        Tham số: shooter — tháp bắn ra đạn (dùng để báo AI titan biết bị đánh,
            và kiểm tra `_serum_buff` để áp debuff).
        """
        super().__init__(x, y)
        self._target  = target
        self._damage  = damage
        self._dtype   = dtype
        self._shooter = shooter

    def update(self, dt: float):
        """Bay THẲNG về VỊ TRÍ HIỆN TẠI của target MỖI FRAME (ĐUỔI THEO, khác Arrow của lính).

        Khác `characters/soldiers/projectile.py::Arrow` (nhắm điểm CỐ ĐỊNH lúc bắn):
        đạn tháp tính lại hướng bay MỖI FRAME theo vị trí MỚI NHẤT của target →
        đạn tháp LUÔN TRÚNG (trừ khi target chết giữa đường).

        Thuật toán: target chết → tự huỷ ngay. Còn sống → tính khoảng cách còn
        lại; đủ gần (`dist <= step`) → snap tới target, gọi `_on_hit()`, tự huỷ.
        Còn xa → tiến 1 bước theo hướng target, cập nhật `angle` (để `draw()` xoay
        sprite đúng hướng bay).

        Chỉ số: balance.TOWER_PROJECTILE_SPEED (hoặc override riêng từng loại đạn).
        """
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

    def _apply_serum_debuff(self, target) -> None:
        """Serum (item áp lên Tower, vĩnh viễn) — mọi đạn tháp đó bắn ra đều
        mang thêm hiệu ứng giảm % hồi máu của Founding. Gọi ngay sau lần
        take_damage() chính trong _on_hit() của MỌI subclass — mỗi loại đạn
        override _on_hit() hoàn toàn riêng (không gọi qua base), nên phải
        gọi helper này ở từng chỗ thay vì chỉ đặt 1 lần ở đây."""
        if getattr(self._shooter, '_serum_buff', False):
            _fn = getattr(target, 'apply_heal_debuff', None)
            if callable(_fn):
                _fn()

    def _eff_dtype(self, base: str) -> str:
        """Dtype thực tế dùng khi gây damage cho MỘT lần trúng đòn. Tháp bắn
        ra đạn này có buff `_anti_armor_buff` (item, vĩnh viễn) → luôn trả
        `'anti_armor'`, bất kể loại đạn gốc là gì — xuyên giáp hoàn toàn khi
        đánh ArmoredTitan (xem `Titan.take_damage`). Không có buff → trả
        nguyên `base` (dtype gốc của loại đạn: 'normal'/'fire'/'electric'/
        'ice'/'water'). Hiệu ứng phụ đi kèm loại đạn (slow, chain lightning,
        knockback, đốt) không đổi — chúng chạy qua method riêng
        (`apply_slow`, `ElectricField`,...) không đọc dtype, chỉ phép tính
        giáp trong `take_damage()` mới đọc giá trị này."""
        if getattr(self._shooter, '_anti_armor_buff', False):
            return 'anti_armor'
        return base

    def _on_hit(self, target):
        """HOOK mặc định — damage đơn, báo AI, áp serum. Mọi class con override
        HOÀN TOÀN để thêm hiệu ứng riêng (KHÔNG gọi `super()._on_hit()` — mỗi
        loại đạn tự viết lại cả 3 bước này, xem ghi chú `_apply_serum_debuff`)."""
        target.take_damage(self._damage, self._eff_dtype(self._dtype))
        self._notify_shooter(target)
        self._apply_serum_debuff(target)

    def draw(self, screen):
        """No-op — Projectile base KHÔNG có sprite riêng. Mọi class con override."""
        pass


# ═══════════════════════════════════════════════════════
#  PROJECTILE CỤ THỂ
# ═══════════════════════════════════════════════════════

class BasicProjectile(Projectile):
    """Đạn thường — chỉ gây damage normal. Sprite 1 frame xoay về phía target."""

    def __init__(self, x: float, y: float, target, damage: int, dtype: str = 'normal',
                 shooter=None):
        """Tạo đạn thường — nạp sprite `effect/base/lv1.png` (lỗi → None, fallback vẽ chấm)."""
        super().__init__(x, y, target, damage, dtype, shooter)
        self.angle = 0
        base_dir = os.path.join(os.path.dirname(__file__), 'effect', 'base')
        try:
            self._sprite = pygame.image.load(os.path.join(base_dir, 'lv1.png')).convert_alpha()
        except Exception as e:
            print("BasicProjectile sprite error:", e)
            self._sprite = None

    def draw(self, screen):
        """Vẽ sprite XOAY theo `angle` (đã tính trong `update()` từ hướng bay).
        Không có sprite → chấm tròn vàng thay thế."""
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
        """Tạo đạn nổ — nạp sprite `effect/base/lv2.png`, dtype CỐ ĐỊNH 'fire'."""
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
        """Vẽ sprite lv2 xoay theo hướng bay. Không có sprite → chấm cam thay thế."""
        if self._sprite:
            rotated = pygame.transform.rotate(self._sprite, self.angle)
            rect = rotated.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(rotated, rect.topleft)
        else:
            pygame.draw.circle(screen, (255, 120, 0), (int(self.x), int(self.y)), 7)

    def _on_hit(self, target):
        """Trúng: damage MỤC TIÊU CHÍNH + MỌI TITAN trong `_explosion_radius` (CÙNG damage), + VFX nổ.

        Thuật toán: damage/notify/serum cho mục tiêu chính TRƯỚC (giống base
        `_on_hit`), rồi quét thêm mọi titan KHÁC trong bán kính nổ — MỖI CON ăn
        CÙNG lượng `_damage` (không giảm theo khoảng cách, không phân biệt chính/phụ).
        Cuối cùng spawn hiệu ứng nổ (`lv2Explosion.png`, 4×4 sheet), SCALE THEO
        ĐÚNG `_explosion_radius` — vùng nổ VẼ RA khớp với vùng damage THẬT.

        Chỉ số: balance.BASIC_TOWER_EXPLOSION_RADIUS.
        """
        _dt = self._eff_dtype('fire')
        target.take_damage(self._damage, _dt)
        self._notify_shooter(target)
        self._apply_serum_debuff(target)
        from systems.world_query import WorldQuery
        for t in WorldQuery.find_in_radius(
            cx=target.x, cy=target.y,
            radius=self._explosion_radius,
            entity_type='titan'
        ):
            if t is not target:
                t.take_damage(self._damage, _dt)

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
        """Tạo đạn điện — animation bay KHÁC NHAU theo `level` (lv1: sheet 5 frame
        lặp; lv2+: sheet 16 frame, vòng lặp từ frame 8 — hiệu ứng "tích điện" trước
        khi vào loop ổn định)."""
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
        """Bay (uỷ quyền `super()`) + tiến animation bay đồng thời."""
        super().update(dt)
        if self.anim_loop:
            self.anim_loop.update(dt)

    def draw(self, screen):
        """Vẽ frame animation bay hiện tại (xoay theo hướng). Không có animation
        → vẽ 1 đoạn thẳng chéo màu cyan thay thế."""
        import pygame
        if self.anim_loop:
            frame = self.anim_loop.get_current_frame()
            rotated_frame = pygame.transform.rotate(frame, self.angle)
            rect = rotated_frame.get_rect(center=(self.x, self.y))
            screen.blit(rotated_frame, rect.topleft)
        else:
            pygame.draw.line(screen, (0, 255, 255), (self.x-5, self.y-5), (self.x+5, self.y+5), 2)

    def _on_hit(self, target):
        """Trúng: damage CHÍNH + CHAIN LIGHTNING (giật sang titan gần) + có thể SPAWN ĐIỆN TRƯỜNG.

        Thuật toán: damage/notify/serum cho mục tiêu chính, VFX tia chớp tại điểm
        trúng, rồi quét titan KHÁC trong `_chain_range` — MỖI CON ăn `_chain_damage`
        (KHÔNG PHẢI `_damage` gốc — chain luôn yếu hơn đòn chính) + VFX tia chớp
        riêng tại từng vị trí. `_spawn_field=True` (Lv2 tháp) → thêm spawn
        `ElectricField` (điện trường tồn tại lâu dài) tại điểm trúng.

        Chỉ số: balance.ELECTRIC_TOWER_CHAIN_DAMAGE (khởi tạo), balance.ELECTRIC_FIELD_DURATION.
        """
        SoundManager.get_instance().play('elec_tower', self.x, self.y)
        _dt = self._eff_dtype('electric')
        target.take_damage(self._damage, _dt)
        self._notify_shooter(target)
        self._apply_serum_debuff(target)
        self._spawn_hit_vfx(target.x, target.y)

        from systems.world_query import WorldQuery
        for t in WorldQuery.find_in_radius(
            cx=target.x, cy=target.y,
            radius=self._chain_range,
            entity_type='titan'
        ):
            if t is not target:
                t.take_damage(self._chain_damage, _dt)
                self._spawn_hit_vfx(t.x, t.y)
                
        if self._spawn_field:
            WorldQuery.spawn_entity(
                ElectricField(target.x, target.y, self._chain_range, self._chain_damage)
            )
            
    def _spawn_hit_vfx(self, x, y):
        """Spawn hiệu ứng tia chớp NHẤT THỜI (`TransientEffect`, tự huỷ khi hết
        animation, KHÔNG PHẢI ElectricField tồn tại lâu) tại (x,y). CHỈ ĐỒ HOẠ,
        lỗi → bỏ qua âm thầm."""
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
        """Tạo đạn băng — `slow_factor` ở đây là "PHẦN TỐC ĐỘ CÒN LẠI" (đã được
        `IceTower.shoot()` đổi dấu từ `1 - _slow_factor` của tháp). `splash_radius=0`
        (mặc định, Lv1) → không AoE slow, chỉ mục tiêu chính."""
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
        """Bay + máy trạng thái animation 2 pha: "start" (mồi lửa băng, chạy 1 lần)
        rồi TỰ CHUYỂN sang "loop" (lặp vô tận) khi `anim_start.finished`."""
        super().update(dt)
        if self.state == "start":
            self.anim_start.update(dt)
            if self.anim_start.finished:
                self.state = "loop"
        elif self.state == "loop":
            self.anim_loop.update(dt)

    def draw(self, screen):
        """Vẽ frame ĐÚNG PHA hiện tại (start hoặc loop), xoay theo hướng bay."""
        if self.state == "start":
            frame = self.anim_start.get_current_frame()
        else:
            frame = self.anim_loop.get_current_frame()
            
        rotated_frame = pygame.transform.rotate(frame, self.angle)
        rect = rotated_frame.get_rect(center=(self.x, self.y))
        screen.blit(rotated_frame, rect.topleft)

    def _apply_slow(self, t):
        """Áp `apply_slow()` lên `t` + spawn hiệu ứng ĐÓNG BĂNG DÍNH DƯỚI CHÂN (3 pha: bắt đầu → hoạt động → tan).

        `AttachedStatusVFX` (visual_effects.py) tự BÁM THEO vị trí `t` di chuyển
        trong suốt `_slow_duration` — khác `TransientEffect` (đứng yên tại điểm spawn).
        Lỗi nạp VFX → chỉ log, KHÔNG ảnh hưởng gameplay (slow vẫn áp dụng bình thường).
        """
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
        """Trúng: damage + SLOW mục tiêu chính, + slow LAN sang titan gần nếu có splash.

        Thuật toán: damage/notify/serum, rồi `_apply_slow(target)` (mục tiêu
        chính LUÔN bị slow). `_splash_radius > 0` (Lv2+) → quét titan KHÁC trong
        bán kính đó, MỖI CON cũng `_apply_slow()` (CÙNG `_slow_factor`/`_slow_duration`,
        không giảm nhẹ hơn mục tiêu chính — khác Explosion cleave của SoldierHunter).
        Cuối cùng spawn hiệu ứng chớp trúng (`Ice VFX 1 Hit.png`) tại vị trí đạn.
        """
        SoundManager.get_instance().play('ice_tower_1', self.x, self.y)
        target.take_damage(self._damage, self._eff_dtype('ice'))
        self._notify_shooter(target)
        self._apply_serum_debuff(target)
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
        """Tạo đạn nước — cắt sheet 5×5 (25 frame) về CHỈ 21 frame (bỏ 4 frame
        thừa cuối, hàng cuối sheet gốc chỉ có 1 frame hợp lệ), loop lặp từ frame 16."""
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
        """Bay + tiến animation cầu nước bay."""
        super().update(dt)
        if self._anim:
            self._anim.update(dt)

    def draw(self, screen):
        """Vẽ frame cầu nước xoay theo hướng. Không có animation → chấm xanh dương thay thế."""
        if self._anim:
            frame = self._anim.get_current_frame()
            rotated = pygame.transform.rotate(frame, self.angle)
            rect = rotated.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(rotated, rect.topleft)
        else:
            pygame.draw.circle(screen, (0, 100, 255), (int(self.x), int(self.y)), 7)

    def _knockback(self, t):
        """Đẩy `t` theo hướng NGƯỢC với vận tốc HIỆN TẠI của nó (đẩy lùi khỏi hướng đi).

        Thuật toán: đọc `_vx/_vy` (được `Titan._move_toward` cập nhật) — titan
        đang di chuyển thì đẩy NGƯỢC HƯỚNG ĐANG ĐI (như bị bắn giật lùi); titan
        đứng yên (`speed < 1.0`) thì fallback đẩy theo hướng TỪ ĐẠN TỚI titan
        (đẩy ra xa nguồn bắn). `kb_speed = push_force × 0.6 / kb_duration` — quy
        đổi lực đẩy tổng thành vận tốc tức thời cho `apply_knockback()`.
        """
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
        """Trúng: damage + VFX va chạm, RỒI RẼ NHÁNH theo cấp — LV1 knockback, LV2 xoáy nước.

        Thuật toán: damage/notify/serum, spawn VFX impact (luôn hiện, mọi cấp).
        `not _vortex_mode` (Lv1) → knockback mục tiêu chính + MỌI titan khác
        trong `_push_radius` (dùng `_knockback()` cho từng con), kèm VFX knockback
        riêng. `_vortex_mode` (Lv2) → BỎ QUA knockback, thay vào đó spawn 1
        `WaterVortex` tồn tại lâu dài tại điểm trúng — hút liên tục thay vì đẩy 1 lần.

        Chỉ số: balance.WATER_TOWER_PUSH_FORCE / _KB_DURATION.
        """
        SoundManager.get_instance().play('water_tower_1', self.x, self.y)
        target.take_damage(self._damage, self._eff_dtype('water'))
        self._notify_shooter(target)
        self._apply_serum_debuff(target)
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

    DURATION   = balance.ELECTRIC_FIELD_DURATION
    ZAP_PERIOD = balance.ELECTRIC_FIELD_ZAP_PERIOD

    def __init__(self, x: float, y: float, radius: float, damage: int):
        """Tạo điện trường tại (x,y) — tồn tại `DURATION` giây, giật MỌI titan
        trong `radius` mỗi `ZAP_PERIOD` giây.

        `_angle`/`_pulse` — bộ tích luỹ CHỈ dùng cho hiệu ứng xoay/nhấp nháy khi vẽ.
        """
        super().__init__(x, y)
        self._radius    = radius
        self._damage    = damage
        self._lifetime  = self.DURATION
        self._zap_timer = 0.0
        self._angle     = 0.0   # Rotation accumulator for arc animation
        self._pulse     = 0.0   # Pulse oscillation

    def update(self, dt: float):
        """Đếm ngược tuổi thọ (hết → tự huỷ), quay/nhấp nháy đồ hoạ, GIẬT ĐỊNH KỲ mọi titan trong vùng.

        Thuật toán: `_lifetime` hết → `is_alive=False`, thoát ngay. Còn sống →
        tăng `_angle`/`_pulse` (đồ hoạ). Đếm ngược `_zap_timer`; hết (mỗi
        `ZAP_PERIOD` giây) → quét MỌI titan trong `_radius`, MỖI CON ăn `_damage`
        (dtype='electric') + phát âm thanh + VFX tia chớp RIÊNG cho từng con.
        Đây là sát thương LIÊN TỤC — khác đòn 1-lần của các loại đạn khác.

        Chỉ số: balance.ELECTRIC_FIELD_DURATION / _ZAP_PERIOD.
        """
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
                SoundManager.get_instance().play('zap(electro)_1', self.x, self.y)
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
        """Vẽ vòng điện trường NHIỀU LỚP: quầng sáng nhấp nháy + viền + 4 tay chớp
        xoay thuận + 3 cung phụ xoay ngược, mờ dần theo `_lifetime` còn lại.
        CHỈ ĐỒ HOẠ — phức tạp nhưng không ảnh hưởng gameplay."""
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

    DURATION   = balance.WATER_VORTEX_DURATION
    PULL_SPEED = balance.WATER_VORTEX_PULL_SPEED
    SPIN_SPEED = balance.WATER_VORTEX_SPIN_SPEED
    MIN_DIST   = balance.WATER_VORTEX_MIN_DIST

    def __init__(self, x: float, y: float, radius: float):
        """Tạo xoáy nước tại (x,y) — 2 animation state ("startup" chạy trước rồi
        loop, "end" chạy 1 lần khi sắp hết đời). Phát âm thanh 'xoaynuoc' ngay
        lúc spawn. `_end_duration` tính từ số frame/fps của anim_end — dùng để
        biết CHÍNH XÁC lúc nào phải chuyển sang state "end" (xem `update()`)."""
        super().__init__(x, y)
        self._radius   = radius
        self._lifetime = self.DURATION
        self._state    = "startup"
        SoundManager.get_instance().play('xoaynuoc', self.x, self.y)

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
        """Đếm ngược tuổi thọ, TỰ CHUYỂN sang animation "end" ĐÚNG LÚC còn vừa đủ
        thời gian chạy hết nó, và HÚT MỌI titan trong bán kính theo xoắn ốc.

        Thuật toán:
          1. Hết `_lifetime` → tự huỷ ngay.
          2. **Thời điểm chuyển state tinh tế**: khi còn lại `_lifetime` VỪA ĐÚNG
             BẰNG `_end_duration` (thời lượng animation kết thúc), chuyển sang
             "end" — đảm bảo animation end CHẠY VỪA KHỚP tới đúng lúc vortex biến
             mất, không bị cắt cụt hay animation end chạy xong sớm mà vortex vẫn còn.
          3. Tiến animation theo state hiện tại. Animation "end" chạy XONG
             (`finished`) → tự huỷ NGAY (không cần đợi `_lifetime` về 0).
          4. MỌI FRAME (bất kể state): quét titan trong `_radius`, mỗi con
             `_apply_spiral()` — hút liên tục suốt vòng đời vortex, kể cả khi
             đang chạy animation "end".

        Chỉ số: balance.WATER_VORTEX_DURATION.
        """
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
        """Hút `titan` vào TÂM xoáy theo ĐƯỜNG XOẮN ỐC (không phải đường thẳng).

        Thuật toán: `(rx,ry)` = vector đơn vị hướng VÀO TÂM. `(tx,ty) = (-ry,rx)`
        = vector VUÔNG GÓC (tiếp tuyến) — công thức xoay 90°. Dịch chuyển titan
        theo TỔNG HỢP 2 lực: `PULL_SPEED` theo hướng vào tâm + `SPIN_SPEED` theo
        hướng tiếp tuyến → quỹ đạo xoắn ốc thay vì đi thẳng vào tâm.
        `dist < MIN_DIST` → bỏ qua (đã đủ gần tâm, tránh chia 0 / rung giật khi
        quá sát).

        Chỉ số: balance.WATER_VORTEX_PULL_SPEED / _SPIN_SPEED / _MIN_DIST.
        """
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
        """Vẽ vòng tròn xanh MỜ DẦN theo tuổi thọ (biểu diễn vùng ảnh hưởng) +
        animation xoáy nước ở tâm (startup hoặc end tuỳ state). CHỈ ĐỒ HOẠ."""
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
