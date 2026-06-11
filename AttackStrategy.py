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

    _DEFAULT_DAMAGE_MULT = 3.5
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

    _DEFAULT_DAMAGE_MULT = 4.0
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
        trong AoE ăn `damage_splash` (theo `splash_ratio`).
      • Knockback: mỗi soldier bị đẩy ra xa khỏi attacker `knockback` px.
      • dtype='explode' để target/decorator có thể xử lý (vd particle effect).

    Cách tính damage (đã đồng nhất với pattern chung):
        main   = int(attacker._damage × _DEFAULT_DAMAGE_MULT)   # qua compute_damage
        splash = int(main × splash_ratio)

    Vì sao đổi sang dùng `compute_damage`?
        Trước đây Explosion truyền damage CỐ ĐỊNH (main=200, splash=100),
        bỏ qua `_damage` của attacker và `_DEFAULT_DAMAGE_MULT` — phá vỡ
        quy ước Strategy Pattern (mọi đòn đánh đều scale theo
        `attacker._damage × mult`). Giờ Kamikaze chỉnh `_DEFAULT_DAMAGE`
        ở class là toàn bộ Explosion scale theo, không cần đụng strategy.

    Tham số:
        splash_ratio  : tỷ lệ damage splash so với main (0.5 = splash bằng nửa)
        radius        : bán kính AoE quanh attacker
        knockback     : số px đẩy soldier ra xa khỏi attacker

    Nhóm dùng: Kamikaze. Sau khi execute, attacker (kamikaze) sẽ tự gọi
    on_death() vì đã 'phát nổ'.
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
        # Damage main scale theo attacker._damage × _mult (Strategy chuẩn).
        # Splash = main × splash_ratio để giữ tỷ lệ tương đối với main.
        damage_main   = self.compute_damage(attacker)
        damage_splash = int(damage_main * self._splash_ratio)

        nearby = WorldQuery.find_in_radius(
            attacker.x, attacker.y, self._radius, 'soldier')
        for s in nearby:
            if not getattr(s, 'is_alive', True):
                continue
            # Damage: target chính ×main, khác ×splash
            if s is target:
                s.take_damage(amount=damage_main, dtype=self._dtype)
            else:
                s.take_damage(amount=damage_splash, dtype=self._dtype)
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
            target.take_damage(
                amount=int(base * self._tower_bonus_mult),
                dtype=self._dtype,
            )
        else:
            target.take_damage(amount=base, dtype=self._dtype)


class SoldierHunterStrategy(TitanAttackStrategy):
    """Chuyên săn lính — cleave AoE quanh ATTACKER, trúng mọi loại entity.
    Nhóm dùng: SoldierHunter — Titan gây chaos hàng thủ, không quan tâm tường.

    Cập nhật (NHÓM 5):
        Trước đây splash chỉ quét quanh TARGET, chỉ trúng 'soldier'.
        Giờ chuyển thành CLEAVE quanh ATTACKER, trúng MỌI ENTITY trong
        bán kính `_splash_radius` (soldier + commander + tower + wall + HQ).
        Lý do: SoldierHunter cầm lưỡi liềm vung 360° — bất cứ gì đứng
        trong vùng vung lưỡi (ngang với attack_range) đều dính sát thương.

    Damage:
        • Target chính (mục tiêu được AI chọn) → damage = `attacker._damage
          × _mult`, dtype='soldier'.
        • Mọi entity (soldier/commander/tower/wall/hq) trong bán kính
          `_splash_radius` quanh ATTACKER → damage × `_splash_mult` (mặc
          định 0.5 = một nửa main), dtype='aoe'.
        • Tự loại trừ chính target khỏi splash → không trừ máu 2 lần.

    Vì sao dtype='soldier' (không phải 'normal')?
        • 'normal' được dành riêng cho đòn cơ bản của MeleeRushStrategy
          (RegularTitan) — quy ước: 1 strategy ⇄ 1 dtype phân biệt.
        • Lính có thể trang bị armor chống 'soldier' (kháng 30%) trong
          khi vẫn ăn đầy 'normal' từ Regular — cho phép balance riêng.

    `_splash_radius` mặc định 120 — set ≈ attack_range của SoldierHunter
    (xem `Titan.SoldierHunter._DEFAULT_ATTACK_RANGE`) để teammate thấy
    "vùng cleave = tầm đánh". Có thể override khi khởi tạo strategy.
    """

    _DEFAULT_DAMAGE_MULT = 3.0
    _DEFAULT_DTYPE       = 'soldier'

    # Danh sách entity_type bị quét trong cleave AoE — giữ ở class-level
    # để teammate biết chính xác phạm vi (và có thể override khi cần).
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

        # Cleave: quét MỌI loại entity trong bán kính quanh ATTACKER.
        # Dùng set để dedupe (1 entity có thể thuộc 2 pool nếu hệ thống
        # phân loại trùng — phòng hờ).
        from systems.world_query import WorldQuery
        splash_dmg = int(base * self._splash_mult)
        seen_ids: set = {id(target)}   # loại target khỏi splash từ đầu
        for etype in self._SPLASH_ENTITY_TYPES:
            for e in WorldQuery.find_in_radius(
                    attacker.x, attacker.y, self._splash_radius, etype):
                if id(e) in seen_ids:
                    continue
                seen_ids.add(id(e))
                e.take_damage(amount=splash_dmg, dtype=self._splash_dtype)


class Cursed(TitanAttackStrategy):
    """Triệu hồi 10 tia sét toàn map — đòn đặc trưng của Witch.

    Nhóm dùng: Witch. Khác melee/projectile:
      • Không cần khoảng cách tới target chính khi còn lực lượng phòng thủ.
      • Quét toàn map qua WorldQuery, ưu tiên soldier + commander + tower.
      • Ưu tiên mỗi target ăn 1 tia trước; nếu thiếu target thì cho phép
        đánh trùng để vẫn đủ 10 tia.
      • Khi không còn nhóm phòng thủ, fallback đánh target được truyền vào
        đúng 1 tia để Witch vẫn phá Wall/HQ ở cận chiến.
    """

    _DEFAULT_DAMAGE_MULT = 1.0
    _DEFAULT_DTYPE       = 'cursed'
    _TARGET_TYPES: tuple = ('soldier', 'commander', 'tower')

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 bolt_count: int = 10,
                 search_radius: float = 1_000_000.0) -> None:
        super().__init__(damage_mult, dtype)
        self._bolt_count    = int(bolt_count)
        self._search_radius = float(search_radius)

    def _alive_unique_defenders(self, attacker) -> list:
        """Lấy danh sách soldier/commander/tower còn sống trong toàn map."""
        from systems.world_query import WorldQuery
        out = []
        seen = set()
        for etype in self._TARGET_TYPES:
            for entity in WorldQuery.find_in_radius(
                    attacker.x, attacker.y, self._search_radius, etype):
                if not getattr(entity, 'is_alive', False):
                    continue
                marker = id(entity)
                if marker in seen:
                    continue
                seen.add(marker)
                out.append(entity)
        return out

    def pick_targets(self, attacker, fallback_target=None) -> list:
        """Chọn target cho từng tia sét.

        Trả danh sách có thể chứa trùng object. Caller dùng danh sách này
        để vừa apply damage vừa spawn visual đúng vị trí.
        """
        defenders = self._alive_unique_defenders(attacker)
        if defenders:
            selected = defenders[:]
            random.shuffle(selected)
            selected = selected[:self._bolt_count]
            while len(selected) < self._bolt_count:
                selected.append(random.choice(defenders))
            return selected

        if fallback_target is not None and getattr(fallback_target, 'is_alive', True):
            return [fallback_target]
        return []

    def execute(self, attacker, target: IAttackable = None):
        damage = self.compute_damage(attacker)
        struck = self.pick_targets(attacker, target)
        for entity in struck:
            entity.take_damage(amount=damage, dtype=self._dtype)
        return struck


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

    Pushback: soldier + commander trong AoE bị đẩy tween (vector vận tốc
    `pushback_vx/vy` set lên entity, entity tự decay trong update). Xem
    `apply_pushback_tween()` để integrate vào game loop của soldier/commander.
    """

    # Hệ số decay của vector pushback — đơn vị "1/giây".
    # Mỗi frame: vx *= exp(-decay × dt). Decay=5 ⇒ ~99% giảm sau 0.92s,
    # tổng quãng đường đẩy ≈ v0 / decay = push_dist. Tăng decay → đẩy
    # nhanh và dứt khoát; giảm → đẩy chậm dài hơi.
    _PUSHBACK_DECAY: float = 5.0

    def __init__(self, start_x: float, start_y: float, target,
                 velocity: float = 250.0, angle_deg: float = 15.0,
                 gravity: float = 600.0,
                 damage_main: int = 80, damage_splash: int = 40,
                 aoe_radius: float = 80.0,
                 pushback_soldier: float = 100.0,
                 pushback_commander: float = 50.0,
                 beast_x: float | None = None,
                 beast_y: float | None = None) -> None:
        self.x = float(start_x)
        self.y = float(start_y)
        self._target = target
        # Vị trí Beast (nguồn ném đá) — dùng để loại trừ hướng pushback về phía Beast.
        # Nếu không truyền (fallback), dùng chính start_x/y (vị trí tay beast lúc release).
        self._beast_x = float(beast_x) if beast_x is not None else float(start_x)
        self._beast_y = float(beast_y) if beast_y is not None else float(start_y)

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

        self._damage_main        = damage_main
        self._damage_splash      = damage_splash
        self._aoe_radius         = aoe_radius
        # Pushback (đẩy lùi) tách riêng theo loại mục tiêu:
        #   • _pushback_soldier   — soldier bị đẩy mạnh (trung bình 100px ở tâm)
        #   • _pushback_commander — commander bị đẩy ÍT hơn (~50% soldier) vì hero nặng
        # Giá trị là MAX distance (khi target nằm ngay tâm điểm rơi); falloff
        # tuyến tính theo khoảng cách: gần tâm → đẩy xa, rìa AoE → đẩy ít.
        self._pushback_soldier   = pushback_soldier
        self._pushback_commander = pushback_commander

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
        """Áp damage AoE + pushback tại điểm rơi.

        Quy ước:
          • Tower/Soldier/Commander/Wall/HQ trong AoE đều dính damage.
          • Target chính (`self._target`) nhận `damage_main`, các entity
            khác trong AoE nhận `damage_splash`.

        Pushback (NHÓM 6 — Beast):
          • Chỉ áp dụng cho **soldier** (mạnh) và **commander** (yếu hơn,
            ~50% soldier vì hero "nặng"). Tower/Wall/HQ không bị đẩy.
          • Hướng đẩy: **random trong nửa mặt phẳng đối diện Beast** —
            không bao giờ đẩy về phía Beast. Ví dụ Beast ở W của điểm
            rơi → random hướng E/N/S, chặn W.
          • Độ mạnh: **falloff tuyến tính** theo khoảng cách từ tâm điểm
            rơi đá: `push = max_push × (1 - dist / aoe_radius)`. Càng
            gần tâm → đẩy càng xa.
          • Cơ chế: **tween qua nhiều frame** — set vector vận tốc
            `pushback_vx/vy` lên entity; entity sẽ tự decay trong update.
            Giây quy đổi: vector ban đầu = push_dist × `_PUSHBACK_DECAY`
            (decay 5/giây → toàn bộ đoạn đẩy hoàn tất trong ~0.6s).
        """
        from systems.world_query import WorldQuery

        # Map entity → entity_type để biết loại nào cho pushback
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
        # phân loại được nó — vd dummy custom không thuộc pool).
        # BUG FIX: cũng phải gán entity_type cho target chính để pushback
        # nhận diện được. Đọc qua attribute `entity_type` của target
        # (duck-type); nếu không có thì coi như 'soldier' (mục tiêu mặc
        # định của Beast — boss này ném đá nhắm vào lính + commander).
        if (self._target is not None
                and getattr(self._target, 'is_alive', False)
                and id(self._target) not in type_map):
            candidates.append(self._target)
            type_map[id(self._target)] = getattr(self._target, 'entity_type', 'soldier')

        # Vector từ Beast → điểm rơi (dùng để xác định "nửa mặt phẳng
        # đối diện Beast"). Nếu beast trùng điểm rơi (degenerate) thì
        # cho phép random toàn vòng tròn.
        bdx = self.x - self._beast_x
        bdy = self.y - self._beast_y
        bdist = (bdx * bdx + bdy * bdy) ** 0.5
        if bdist > 0:
            forward_x, forward_y = bdx / bdist, bdy / bdist
        else:
            forward_x, forward_y = None, None   # fallback: random toàn vòng

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
                continue   # tower/wall/hq không bị đẩy

            # Falloff tuyến tính theo khoảng cách tới tâm điểm rơi
            dx = e.x - self.x
            dy = e.y - self.y
            dist = (dx * dx + dy * dy) ** 0.5
            falloff = max(0.0, 1.0 - dist / self._aoe_radius) if self._aoe_radius > 0 else 1.0
            push_dist = max_push * falloff
            if push_dist <= 0:
                continue

            # Random hướng trong nửa mặt phẳng đối diện Beast.
            # Cách làm: rejection sampling — random angle [0, 2π], chấp
            # nhận nếu dot(dir, forward) >= 0 (cùng phía 'xa Beast'),
            # vì forward chỉ từ Beast → điểm rơi (tức hướng "xa Beast").
            for _ in range(8):
                theta = random.uniform(0, 2 * math.pi)
                dir_x = math.cos(theta)
                dir_y = math.sin(theta)
                if forward_x is None:
                    break   # degenerate: chấp nhận mọi hướng
                if dir_x * forward_x + dir_y * forward_y >= 0.0:
                    break
            else:
                # Fallback sau 8 lần fail: dùng đúng forward
                dir_x, dir_y = forward_x, forward_y

            # Set vector pushback (tween) — entity tự decay trong update().
            # vận tốc khởi tạo = push_dist × _PUSHBACK_DECAY → toàn đoạn
            # đẩy hoàn tất trong ~1/decay giây.
            decay = self._PUSHBACK_DECAY
            vx_push = dir_x * push_dist * decay
            vy_push = dir_y * push_dist * decay
            # Cộng dồn vào pushback hiện tại (nếu entity bị nhiều rock cùng lúc)
            e.pushback_vx = getattr(e, 'pushback_vx', 0.0) + vx_push
            e.pushback_vy = getattr(e, 'pushback_vy', 0.0) + vy_push
            # Đánh dấu để caller (HUD/log) biết entity vừa bị pushback
            try:
                e.take_damage(amount=0, dtype='pushback')
            except Exception:
                pass

    @staticmethod
    def apply_pushback_tween(entity, dt: float) -> None:
        """Tích phân vector pushback của entity qua 1 frame (tween).

        Cách dùng: trong `update(dt)` của Soldier/Commander, gọi
        `RockProjectile.apply_pushback_tween(self, dt)` ngay đầu hàm.
        Hàm sẽ:
          1. Đọc `entity.pushback_vx/vy` (mặc định 0 nếu chưa có).
          2. Dịch entity theo vector × dt (di chuyển thực sự).
          3. Decay vector theo `exp(-_PUSHBACK_DECAY × dt)` — vector
             tiến tới 0, nên pushback sẽ tự kết thúc sau ~0.6–1s.
          4. Khi |v| < 1px/s → snap về 0 cho gọn.

        An toàn với entity chưa có 2 attribute này (init lazy).
        """
        vx = getattr(entity, 'pushback_vx', 0.0)
        vy = getattr(entity, 'pushback_vy', 0.0)
        if vx == 0.0 and vy == 0.0:
            return
        entity.x += vx * dt
        entity.y += vy * dt
        # Exponential decay — ổn định với dt biến thiên (60fps vs 30fps).
        factor = math.exp(-RockProjectile._PUSHBACK_DECAY * dt)
        vx *= factor
        vy *= factor
        # Snap về 0 khi đủ nhỏ để tránh "trôi vĩnh viễn"
        if abs(vx) < 1.0 and abs(vy) < 1.0:
            vx = 0.0
            vy = 0.0
        entity.pushback_vx = vx
        entity.pushback_vy = vy

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
