# characters/titans/attackstrategy.py
"""AttackStrategy.py — Toàn bộ "cách đánh" của Titan/Boss.

Vì sao có file này?
    Mỗi loại Titan có một "kiểu đánh" riêng (cận chiến, húc, AoE, ném đá…).
    Thay vì nhét `if/else` "tôi là loại nào → đánh ra sao" vào trong class
    Titan, ta tách phần đánh thành các **Strategy** riêng — đúng Pattern
    Strategy của GoF. Titan **HAS-A** một `_attack_strategy`; đổi cách đánh
    = đổi strategy (kể cả lúc runtime, vd ArmoredTitan vỡ giáp → switch
    sang HeavyStrikeStrategy).

Cấu trúc 1 Strategy chuẩn:
    • `_DEFAULT_DAMAGE_MULT` (class const) — hệ số nhân damage cơ bản
    • `_DEFAULT_DTYPE`       (class const) — string mô tả "loại sát thương"
    • `__init__(mult, dtype)` cho phép override khi cần (vd switch runtime)
    • `compute_damage(attacker)` (helper ABC) — trả `int(attacker._damage * mult)`
    • `execute(attacker, target)` — kích hoạt 1 đòn đánh

Cách damage được tính:
    damage_thật = int(attacker._damage * strategy._mult)
    target.take_damage(damage_thật, dtype=strategy._dtype)

Cách user cấu hình:
    Mỗi Titan/Boss chỉ cần khai báo `_damage` (giá trị gốc). Strategy lo
    phần nhân hệ số và dtype. Khi muốn đổi balance, sửa `_DEFAULT_DAMAGE_MULT`
    hoặc khởi tạo strategy với param khác — KHÔNG cần sửa class Titan.
"""
import math
import random

import pygame

from abc import ABC, abstractmethod
from core.interfaces import IAttackable


class TitanAttackStrategy(ABC):
    """ABC cho mọi chiến thuật tấn công của Titan.

    Vì sao có ABC này?
        Titan/Boss chỉ thấy interface chung `execute(attacker, target)`.
        Nhờ vậy code gọi đòn đánh không cần biết là Melee, Heavy hay
        Explosion — chỉ cần biết "có strategy thì gọi execute". Đây là
        điểm cốt lõi của Strategy Pattern: client (Titan) phụ thuộc
        ABSTRACTION (TitanAttackStrategy), không phụ thuộc concrete.

    Subclass cần khai báo (qua override class const):
        _DEFAULT_DAMAGE_MULT — hệ số nhân damage cơ bản (vd 2.0 cho heavy)
        _DEFAULT_DTYPE       — string mô tả loại sát thương (vd 'heavy')

    Subclass cần override:
        execute(attacker, target) — tung đòn cụ thể.

    Helper có sẵn (tránh duplicate logic):
        compute_damage(attacker) — trả `int(attacker._damage * self._mult)`.
    """

    # Default chung — subclass override để có hệ số riêng.
    _DEFAULT_DAMAGE_MULT: float = 1.0
    _DEFAULT_DTYPE:       str   = 'normal'

    def __init__(self, damage_mult: float = None, dtype: str = None) -> None:
        """Khởi tạo strategy.

        Tham số:
            damage_mult: ghi đè hệ số damage; None = dùng `_DEFAULT_DAMAGE_MULT`.
            dtype:       ghi đè loại sát thương; None = dùng `_DEFAULT_DTYPE`.

        Ví dụ:
            MeleeRushStrategy()                  → dùng default ×1.0 'normal'
            MeleeRushStrategy(damage_mult=2.0)   → berserk, ×2.0
        """
        self._mult  = self._DEFAULT_DAMAGE_MULT if damage_mult is None else damage_mult
        self._dtype = self._DEFAULT_DTYPE       if dtype       is None else dtype

    @abstractmethod
    def execute(self, attacker, target: IAttackable):
        """Thực hiện 1 đòn đánh.

        Tham số:
            attacker: Titan/Boss — con đang tấn công (truy cập `_damage`).
            target:   IAttackable — mục tiêu (Wall/Soldier/Tower/HQ/Commander).
        """
        ...

    # ── Helper dùng chung ────────────────────────────────────────

    def compute_damage(self, attacker) -> int:
        """Tính damage thực tế = `attacker._damage × _mult`.

        Trả int (làm tròn dưới) — vì `take_damage()` quy ước nhận int.
        Subclass dùng helper này để tránh duplicate phép nhân.
        """
        return int(getattr(attacker, '_damage', 0) * self._mult)


# ── NHÓM 1: Cận chiến ────────────────────────────────────────────

class MeleeRushStrategy(TitanAttackStrategy):
    """Lao vào đánh cận chiến.
    Nhóm dùng: Titan cơ bản (RegularTitan trạng thái thường), berserk mode.

    Ví dụ:
        MeleeRushStrategy()                 → damage thường ×1.0
        MeleeRushStrategy(damage_mult=2.0)  → switch runtime khi berserk
    """

    _DEFAULT_DAMAGE_MULT = 1.5
    _DEFAULT_DTYPE       = 'normal'

    def execute(self, attacker, target: IAttackable):
        target.take_damage(
            amount=self.compute_damage(attacker),
            dtype=self._dtype,
        )


class HeavyStrikeStrategy(TitanAttackStrategy):
    """Đòn đánh nặng — damage nhân lớn.
    Nhóm dùng: Titan dame to (FoundingTitan), ArmoredTitan sau khi giáp vỡ,
    RegularTitan khi HP < 40%.
    """

    _DEFAULT_DAMAGE_MULT = 3.0
    _DEFAULT_DTYPE       = 'heavy'

    def execute(self, attacker, target: IAttackable):
        target.take_damage(
            amount=self.compute_damage(attacker),
            dtype=self._dtype,
        )


class Incurable(TitanAttackStrategy):
    """Cắn chặn hồi máu — damage thấp đổi debuff `antiheal`.
    Nhóm dùng: Wolf — Titan thân nhỏ, cắn nhanh, ngăn target tự phục hồi.

    Cơ chế:
        • Damage = attacker._damage × 0.8 (thấp hơn melee thường)
        • dtype='antiheal' — bên target tự xử lý: thấy dtype này thì
          set một flag/timer ngăn regen trong vài giây tới.
        • KHÔNG tự áp debuff lên target — chỉ truyền dtype; target chịu
          trách nhiệm phản ứng (loose coupling qua dtype string).

    Ví dụ:
        Incurable()                  → ×0.8 chuẩn
        Incurable(damage_mult=1.0)   → buff nặng hơn cho boss-wolf
    """

    _DEFAULT_DAMAGE_MULT = 2.5
    _DEFAULT_DTYPE       = 'antiheal'

    def execute(self, attacker, target: IAttackable):
        target.take_damage(
            amount=self.compute_damage(attacker),
            dtype=self._dtype,
        )


# ── NHÓM 2: Giáp cứng ────────────────────────────────────────────

class ArmoredRamStrategy(TitanAttackStrategy):
    """Húc với giáp cứng — damage cao nhờ momentum.
    Nhóm dùng: ArmoredTitan trong lúc còn giáp (cơ chế dash → va chạm).

    Sau khi giáp vỡ → ArmoredTitan switch sang HeavyStrikeStrategy (runtime),
    tức là `_attack_strategy` được thay vĩnh viễn.

    Tham số `armor_reduction` chỉ dùng cho HUD/log (không trừ damage ở
    đây vì damage do strategy tạo ra là damage Ram nguyên đai).
    """

    _DEFAULT_DAMAGE_MULT = 6.7
    _DEFAULT_DTYPE       = 'ram'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 armor_reduction: float = 0.6) -> None:
        super().__init__(damage_mult, dtype)
        self._armor_reduction = armor_reduction   # giữ cho HUD/log

    def execute(self, attacker, target: IAttackable):
        target.take_damage(
            amount=self.compute_damage(attacker),
            dtype=self._dtype,
        )


# ── NHÓM 4: Nặng / AoE ───────────────────────────────────────────

class GroundSlamStrategy(TitanAttackStrategy):
    """Đập đất — damage + stun tháp trong bán kính.
    Nhóm dùng: ColossalTitan (đòn basic — damage target chính + stun tower
    quanh attacker).

    Damage = attacker._damage × _mult, dtype='stomp'.
    Sau khi gây damage target chính, quét tower trong `radius` quanh attacker
    và gọi `tower.stun(stun_duration)`.
    """

    _DEFAULT_DAMAGE_MULT = 1.0
    _DEFAULT_DTYPE       = 'stomp'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 radius: float = 160.0, stun_duration: float = 3.0) -> None:
        super().__init__(damage_mult, dtype)
        self._radius        = radius
        self._stun_duration = stun_duration

    def execute(self, attacker, target: IAttackable):
        target.take_damage(
            amount=self.compute_damage(attacker),
            dtype=self._dtype,
        )
        from systems.world_query import WorldQuery
        towers = WorldQuery.find_in_radius(
            attacker.x, attacker.y, self._radius, 'tower')
        for tower in towers:
            tower.stun(self._stun_duration)


class Explosion(TitanAttackStrategy):
    """Phát nổ AoE quanh attacker — dành cho Kamikaze (suicide bomber).

    Khác các strategy khác:
      • Center damage là tại vị trí `attacker` (KHÔNG phải target).
      • Target chính (locked soldier) ăn `damage_main`, soldier khác
        trong AoE ăn `damage_splash`.
      • Knockback: mỗi soldier bị đẩy ra xa khỏi attacker `knockback` px.
      • dtype='explode' để target/decorator có thể xử lý (vd particle effect).

    Damage CỐ ĐỊNH (không nhân `attacker._damage`) — vì là damage AoE
    chuyên biệt, balance theo bộ skill, không scale theo damage base.
    Vẫn override _DEFAULT_DAMAGE_MULT = 0 để báo "không dùng compute_damage".

    Tham số:
        damage_main   : damage cho target chính (locked soldier)
        damage_splash : damage cho các soldier khác trong AoE
        radius        : bán kính AoE quanh attacker
        knockback     : số px đẩy soldier ra xa khỏi attacker

    Nhóm dùng: Kamikaze. Sau khi execute, attacker (kamikaze) sẽ tự gọi
    on_death() vì đã 'phát nổ'.
    """

    _DEFAULT_DAMAGE_MULT = 5.0   # không dùng compute_damage; damage cố định
    _DEFAULT_DTYPE       = 'explode'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 damage_main: int = 200, damage_splash: int = 100,
                 radius: float = 80.0, knockback: float = 60.0) -> None:
        super().__init__(damage_mult, dtype)
        self._damage_main   = damage_main
        self._damage_splash = damage_splash
        self._radius        = radius
        self._knockback     = knockback

    def execute(self, attacker, target: IAttackable):
        from systems.world_query import WorldQuery
        nearby = WorldQuery.find_in_radius(
            attacker.x, attacker.y, self._radius, 'soldier')
        for s in nearby:
            if not getattr(s, 'is_alive', True):
                continue
            # Damage: target chính ×main, khác ×splash
            if s is target:
                s.take_damage(amount=self._damage_main, dtype=self._dtype)
            else:
                s.take_damage(amount=self._damage_splash, dtype=self._dtype)
            # Knockback: push out theo vector (s - attacker) đã chuẩn hoá
            dx = s.x - attacker.x
            dy = s.y - attacker.y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > 0:
                s.x += (dx / dist) * self._knockback
                s.y += (dy / dist) * self._knockback


# ── NHÓM 5: Mục tiêu đặc biệt ────────────────────────────────────

class TowerHunterStrategy(TitanAttackStrategy):
    """Chuyên phá tháp — damage bonus khi tấn công Tower.
    Nhóm dùng: TowerHunter — Titan sinh ra để hạ hạ tầng phòng thủ.

    Damage:
        • Target là `Tower` (isinstance check)  → damage × `_mult × _tower_bonus_mult`
        • Target khác (Soldier/HQ/Wall/Commander) → damage × `_mult` (×1.0 nếu default)

    dtype `siege` để target nhận biết là damage công thành — tower có thể
    áp resistance/weakness riêng nếu cần.
    """

    _DEFAULT_DAMAGE_MULT = 1.0
    _DEFAULT_DTYPE       = 'siege'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 tower_bonus_mult: float = 1.5) -> None:
        super().__init__(damage_mult, dtype)
        self._tower_bonus_mult = tower_bonus_mult

    def execute(self, attacker, target: IAttackable):
        from structures.towers.tower import Tower
        base = self.compute_damage(attacker)
        if isinstance(target, Tower):
            target.take_damage(
                amount=int(base * self._tower_bonus_mult),
                dtype=self._dtype,
            )
        else:
            target.take_damage(amount=base, dtype=self._dtype)


class SoldierHunterStrategy(TitanAttackStrategy):
    """Chuyên săn lính — AoE quanh mục tiêu chính.
    Nhóm dùng: SoldierHunter — Titan gây chaos hàng thủ, không quan tâm tường.

    Damage:
        • Target chính → damage = `attacker._damage × _mult`, dtype='normal'
        • Mọi 'soldier' trong bán kính `splash_radius` quanh TARGET (KHÔNG quanh
          attacker) → damage × `splash_mult`, dtype='aoe'.
        • Tự loại trừ chính target khỏi splash để không trừ máu 2 lần.

    `splash_radius` mặc định 60 — phù hợp vũ khí lưỡi hiểm của
    SoldierHunter (frame 192×192).
    """

    _DEFAULT_DAMAGE_MULT = 1.0
    _DEFAULT_DTYPE       = 'normal'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 splash_radius: float = 60.0, splash_mult: float = 0.5,
                 splash_dtype: str = 'aoe') -> None:
        super().__init__(damage_mult, dtype)
        self._splash_radius = splash_radius
        self._splash_mult   = splash_mult
        self._splash_dtype  = splash_dtype

    def execute(self, attacker, target: IAttackable):
        base = self.compute_damage(attacker)
        target.take_damage(amount=base, dtype=self._dtype)
        from systems.world_query import WorldQuery
        splash = WorldQuery.find_in_radius(
            target.x, target.y, self._splash_radius, 'soldier')
        for s in splash:
            if s is not target:
                s.take_damage(
                    amount=int(base * self._splash_mult),
                    dtype=self._splash_dtype,
                )


# ── NHÓM 6: Projectile / Particle phụ trợ ────────────────────────
#
# RockProjectile và HeatParticle là các thực thể "phụ" sinh ra bởi đòn
# đánh tầm xa / AoE của boss:
#   • RockProjectile — viên đá BeastTitan ném (đòn ném đá tầm xa).
#   • HeatParticle   — hạt hơi nóng ColossalTitan toả ra (skill Steam Burst).
# Chúng không phải `TitanAttackStrategy` (không có `execute`), nhưng thuộc
# về "cách đánh" của boss nên được gom chung tại đây. Boss.py import ngược
# lại 2 class này để spawn trong skill animation.

class RockProjectile:
    """Viên đá ném — bay parabol từ tay beast về hướng target.

    Physics (2D top-down với 'height offset' z):
      • Horizontal: velocity × cos(angle) theo hướng đến target lúc spawn
      • Vertical loft: velocity × sin(angle) đẩy z lên, gravity kéo xuống
      • Visual: rock vẽ tại (x, y - z) — z càng lớn càng nhô lên màn hình
      • Land khi z trở về 0 (sau khi đã lên cao xuống thấp)

    Khi land: AoE damage_main lên target chính + damage_splash lên các entity
    khác trong bán kính `aoe_radius`, dtype='rock'.
    """

    def __init__(self, start_x: float, start_y: float, target,
                 velocity: float = 250.0, angle_deg: float = 15.0,
                 gravity: float = 600.0,
                 damage_main: int = 80, damage_splash: int = 40,
                 aoe_radius: float = 80.0,
                 knockback_dist: float = 40.0) -> None:
        self.x = float(start_x)
        self.y = float(start_y)
        self._target = target

        # Hướng tới target tại thời điểm spawn
        dx = target.x - start_x
        dy = target.y - start_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0:
            ux, uy = dx / dist, dy / dist
        else:
            ux, uy = 0.0, 1.0   # fallback: south

        angle_rad        = math.radians(angle_deg)
        horizontal_speed = velocity * math.cos(angle_rad)
        self.vx = ux * horizontal_speed
        self.vy = uy * horizontal_speed

        # Vertical loft (z = chiều cao 'nhô lên' khỏi mặt đất)
        self.z  = 0.0
        self.vz = velocity * math.sin(angle_rad)
        self._gravity = gravity

        self._damage_main    = damage_main
        self._damage_splash  = damage_splash
        self._aoe_radius     = aoe_radius
        self._knockback_dist = knockback_dist

        self.alive   = True
        self._landed = False
        # Rotation visual để rock quay nhẹ khi bay
        self._spin       = random.uniform(-180, 180)   # độ/giây
        self._rot_angle  = 0.0

    def update(self, dt: float) -> bool:
        """Cập nhật vị trí + height. Trả False khi đá đã land."""
        if not self.alive:
            return False

        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z += self.vz * dt
        self.vz -= self._gravity * dt
        self._rot_angle += self._spin * dt

        # Land khi z < 0 sau khi đã đi xuống
        if self.z <= 0 and self.vz < 0:
            self.z = 0.0
            self._landed = True
            self.alive   = False
            self._on_land()
            return False
        return True

    def _on_land(self) -> None:
        """Áp damage AoE tại điểm rơi.

        Quy ước:
          • Tower/Soldier/Commander/Wall/HQ trong AoE đều dính damage.
          • Target chính (`self._target`) nhận `damage_main`, các entity
            khác trong AoE nhận `damage_splash`.
          • KNOCKBACK: chỉ áp dụng cho 'soldier'. Tower/Wall/HQ (công
            trình cố định) và Commander (hero) không bị đẩy lùi.
          • Knockback magnitude = `_knockback_dist`, đẩy ra xa khỏi điểm rơi.
        """
        from systems.world_query import WorldQuery

        # Map entity → entity_type để biết ai là soldier (cho knockback)
        type_map: dict = {}
        candidates = []
        for etype in ('tower', 'soldier', 'commander', 'wall', 'hq'):
            hits = WorldQuery.find_in_radius(
                cx=self.x, cy=self.y,
                radius=self._aoe_radius, entity_type=etype,
            )
            for e in hits:
                type_map[id(e)] = etype
            candidates.extend(hits)

        # Đảm bảo target chính luôn dính (kể cả khi WorldQuery không
        # phân loại được nó — vd dummy custom).
        if (self._target is not None
                and getattr(self._target, 'is_alive', False)
                and id(self._target) not in type_map):
            candidates.append(self._target)

        seen = set()
        for e in candidates:
            if id(e) in seen:
                continue
            seen.add(id(e))
            if e is self._target:
                e.take_damage(amount=self._damage_main, dtype='rock')
            else:
                e.take_damage(amount=self._damage_splash, dtype='rock')

            # Knockback chỉ cho soldier
            if type_map.get(id(e)) == 'soldier':
                dx = e.x - self.x
                dy = e.y - self.y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > 0:
                    push = self._knockback_dist
                    e.x += (dx / dist) * push
                    e.y += (dy / dist) * push
                else:
                    e.x += self._knockback_dist
                # Đánh dấu pushback dtype phụ (caller có thể nhận biết)
                try:
                    e.take_damage(amount=0, dtype='pushback')
                except Exception:
                    pass

    def draw(self, screen: pygame.Surface, rock_frame: pygame.Surface) -> None:
        """Vẽ rock tại (x, y - z) với rotation; fallback hình tròn nếu sprite None."""
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
        # Bóng nhỏ tại ground projection (z=0) — visual cue cho độ cao
        shadow_alpha = max(40, 120 - int(self.z))
        shadow_surf = pygame.Surface((20, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (0, 0, 0, shadow_alpha), (0, 0, 20, 8))
        screen.blit(shadow_surf, (int(self.x) - 10, int(self.y) - 4))


class HeatParticle:
    """Hạt hiệu ứng hơi nóng — vòng tròn xám mờ dần và phình to.

    Spawn TẠI ĐÚNG vị trí (cx, cy) — caller chịu trách nhiệm tính điểm
    spawn trên vành khuyên quanh Colossal. Particle sau đó tự bay ngẫu
    nhiên mọi hướng quanh spawn point.

    Cơ chế "tan dần từng hạt":
      • `_spawn_delay` random 0–0.8s: hạt chưa xuất hiện cho tới khi
        delay hết → hạt hiện ra rải rác trong ~0.8s đầu, không cùng lúc.
      • `_lifetime` random 1.5–4.5s: chênh lệch tuổi giữa hạt sống ngắn
        nhất và dài nhất tới 3s → mắt thấy rõ "từng hạt tắt".
      • `_alpha` theo curve ease-out `(1-t)²`: đậm lâu, nhạt nhanh ở cuối
        đời, cảm giác fade-out tự nhiên thay vì tuyến tính.
    """

    def __init__(self, cx: float, cy: float) -> None:
        self.x = float(cx)
        self.y = float(cy)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(20, 70)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self._radius   = random.uniform(4, 10)
        self._max_r    = random.uniform(15, 35)
        self._alpha    = 0       # ẩn cho tới khi qua spawn_delay
        # Stagger spawn: mỗi hạt xuất hiện sau 0–0.8s ngẫu nhiên.
        self._spawn_delay = random.uniform(0.0, 0.8)
        # Lifetime trải rộng (1.5–4.5s) → mỗi hạt tan theo nhịp riêng.
        self._lifetime = random.uniform(1.5, 4.5)
        self._age      = 0.0

    def update(self, dt: float) -> bool:
        """Cập nhật vị trí, kích thước, độ mờ. Trả False khi hạt hết tuổi.

        Trong giai đoạn `_spawn_delay` đầu: hạt chưa "tồn tại visual"
        (alpha = 0, không di chuyển). Sau đó mới bắt đầu già + fade.
        """
        # Chưa qua spawn delay → đứng yên, ẩn.
        if self._spawn_delay > 0.0:
            self._spawn_delay -= dt
            self._alpha = 0
            return True   # vẫn alive, chờ tới lượt xuất hiện

        self._age += dt
        t = min(self._age / self._lifetime, 1.0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.93
        self.vy *= 0.93
        self._radius += (self._max_r - self._radius) * dt * 3
        # Ease-out: alpha rớt chậm ở đầu, nhanh ở cuối → fade-out tự nhiên.
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
