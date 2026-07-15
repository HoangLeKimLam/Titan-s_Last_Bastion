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
from config import balance


class TitanAttackStrategy(ABC):
    """ABC cho mọi chiến thuật tấn công của Titan."""

    _DEFAULT_DAMAGE_MULT: float = 1.0
    _DEFAULT_DTYPE:       str   = 'normal'

    def __init__(self, damage_mult: float = None, dtype: str = None) -> None:
        """Tạo strategy, cho phép ghi đè hệ số nhân damage và dtype.

        Ý tưởng: mỗi strategy có hằng mặc định ở class (`_DEFAULT_DAMAGE_MULT`,
        `_DEFAULT_DTYPE`). Nếu caller không truyền gì → lấy mặc định. Nhờ vậy
        cùng 1 class strategy có thể tái dùng với sức mạnh khác nhau mà không
        cần tạo class con mới.

        Tham số:
            damage_mult: hệ số nhân damage. None → dùng `_DEFAULT_DAMAGE_MULT`.
            dtype: loại damage ('normal'/'ram'/'antiheal'/...). None → mặc định.

        Liên kết: `_DEFAULT_DAMAGE_MULT` của mọi class con lấy từ
        `config/balance.py` (STRAT_*_MULT).
        Tác động khi sửa: đổi mult ở balance.py → đổi damage của MỌI titan đang
        dùng strategy đó (xem `titan.py` / `boss.py` gán `_attack_strategy`).
        """
        self._mult  = self._DEFAULT_DAMAGE_MULT if damage_mult is None else damage_mult
        self._dtype = self._DEFAULT_DTYPE       if dtype       is None else dtype

    @abstractmethod
    def execute(self, attacker, target: IAttackable):
        """Tung đòn đánh — MỌI strategy con BẮT BUỘC override.

        Ý tưởng: đây là "cú đánh thật sự". Class con quyết định đánh 1 mục tiêu
        hay AoE, có kèm stun/knockback/debuff hay không.

        Tham số:
            attacker: titan đang đánh (đọc `_damage`, `x`, `y` từ nó).
            target: mục tiêu chính (bất kỳ ai implement `IAttackable`).

        Liên kết: được gọi bởi `ai.py` (TitanAI._act_in_range → strat.execute()).
        Đòn damage cuối cùng luôn đi qua `target.take_damage(amount, dtype)`.
        """
        ...

    def compute_damage(self, attacker) -> int:
        """Quy đổi damage gốc của titan sang damage thật của đòn này.

        Thuật toán: `int(attacker._damage * self._mult)`.
        Đây là CÔNG THỨC DUY NHẤT tính damage cho mọi strategy — muốn đổi cách
        tính damage toàn game thì sửa ở đây.

        Trả về: int — damage đã nhân hệ số (chưa trừ giáp; giáp do phía
        `take_damage()` của mục tiêu tự xử lý theo `dtype`).

        Chỉ số cân bằng: `attacker._damage` ← balance.<TITAN>_DAMAGE;
        `self._mult` ← balance.STRAT_*_MULT.
        """
        return int(getattr(attacker, '_damage', 0) * self._mult)


# ── NHÓM 1: Cận chiến ────────────────────────────────────────────

class MeleeRushStrategy(TitanAttackStrategy):
    """Lao vào đánh cận chiến."""

    _DEFAULT_DAMAGE_MULT = balance.STRAT_MELEE_RUSH_MULT
    _DEFAULT_DTYPE       = 'normal'

    def execute(self, attacker, target: IAttackable):
        """Đánh thẳng 1 mục tiêu, damage 'normal' (đòn cơ bản nhất).

        Ai dùng: RegularTitan (titan.py) — đòn thường.
        Lưu ý: dtype='normal' nên bị ArmoredTitan chặn bớt (xem take_damage()).
        Chỉ số: balance.STRAT_MELEE_RUSH_MULT.
        """
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)


class HeavyStrikeStrategy(TitanAttackStrategy):
    """Đòn đánh nặng — damage nhân lớn."""

    _DEFAULT_DAMAGE_MULT = balance.STRAT_HEAVY_STRIKE_MULT
    _DEFAULT_DTYPE       = 'heavy'

    def execute(self, attacker, target: IAttackable):
        """Đòn nặng 1 mục tiêu — mult cao hơn MeleeRush nhiều.

        Ai dùng: RegularTitan khi HP tụt dưới `_HEAVY_HP_RATIO` (nổi khùng),
        ArmoredTitan SAU KHI VỠ GIÁP (đổi vĩnh viễn sang strategy này),
        TowerHunter/SoldierHunter khi target không đúng "khẩu vị".
        Chỉ số: balance.STRAT_HEAVY_STRIKE_MULT.
        """
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)


class Incurable(TitanAttackStrategy):
    """Cắn chặn hồi máu — damage thấp đổi debuff `antiheal`.

    dtype='antiheal' — target tự xử lý: thấy dtype này thì set cờ
    ngăn regen trong vài giây tới.
    """

    _DEFAULT_DAMAGE_MULT = balance.STRAT_INCURABLE_MULT
    _DEFAULT_DTYPE       = 'antiheal'

    def execute(self, attacker, target: IAttackable):
        """Cắn chặn hồi máu — damage vừa phải, đổi lấy debuff 'antiheal'.

        Thuật toán: KHÔNG tự áp debuff. Chỉ gửi dtype='antiheal'; phía nhận tự
        xử lý (đây là điểm mấu chốt, tránh strategy phải biết mọi loại target):
          - Soldier.take_damage → `_can_heal = False` VĨNH VIỄN (soldier.py).
          - Commander.take_damage → `_anti_heal_timer = ANTI_HEAL_DURATION`
            (commander.py), chặn `heal()` trong bấy nhiêu giây.

        Ai dùng: Wolf (titan.py).
        Chỉ số: balance.STRAT_INCURABLE_MULT, balance.COMMANDER_ANTI_HEAL_DURATION.
        """
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)


# ── NHÓM 2: Giáp cứng ────────────────────────────────────────────

class ArmoredRamStrategy(TitanAttackStrategy):
    """Húc với giáp cứng — damage cao nhờ momentum."""

    _DEFAULT_DAMAGE_MULT = balance.STRAT_ARMORED_RAM_MULT
    _DEFAULT_DTYPE       = 'ram'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 armor_reduction: float = 0.6) -> None:
        """Tạo đòn húc giáp.

        Tham số:
            armor_reduction: hệ số giáp của CHÍNH strategy (0.6). Lưu ý: giáp
                thực tế của ArmoredTitan nằm ở `ArmoredTitan.ARMOR_REDUCTION`
                (titan.py ← balance.ARMORED_TITAN_ARMOR_REDUCTION); field này
                hiện chỉ lưu, không dùng để tính damage.
        """
        super().__init__(damage_mult, dtype)
        self._armor_reduction = armor_reduction

    def execute(self, attacker, target: IAttackable):
        """Húc bằng momentum — dtype='ram', mult rất cao (phá tường cực mạnh).

        Ai dùng: ArmoredTitan lúc CÒN GIÁP (titan.py). Vỡ giáp → đổi sang
        HeavyStrikeStrategy.
        Tác động: dtype='ram' là đòn chuyên phá `WallSection` (wall.py).
        Chỉ số: balance.STRAT_ARMORED_RAM_MULT.
        """
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)


# ── NHÓM 4: Nặng / AoE ───────────────────────────────────────────

class GroundSlamStrategy(TitanAttackStrategy):
    """Đập đất: damage mục tiêu chính + CHOÁNG mọi tháp quanh attacker.

    Đây là strategy duy nhất (ngoài đá của Beast) gây stun tháp. Ai dùng:
    ColossalTitan — cả đòn thường lẫn skill Jump Stomp (boss.py).
    """

    _DEFAULT_DAMAGE_MULT = balance.STRAT_GROUND_SLAM_MULT
    _DEFAULT_DTYPE       = 'stomp'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 radius: float = 160.0, stun_duration: float = 3.0) -> None:
        """Tạo đòn đập đất.

        Tham số:
            radius: bán kính (px) quét tháp để gây choáng, quanh ATTACKER
                (không phải quanh target).
            stun_duration: số giây tháp ngừng bắn.

        Lưu ý: Colossal truyền giá trị riêng khi tạo strategy (boss.py dùng
        `_STOMP_AOE` / `_STOMP_STUN_DUR` ← balance.COLOSSAL_STOMP_*), nên 2 số
        mặc định ở đây chỉ là fallback.
        """
        super().__init__(damage_mult, dtype)
        self._radius        = radius
        self._stun_duration = stun_duration

    def execute(self, attacker, target: IAttackable):
        """Đánh target + stun toàn bộ tháp trong `_radius` quanh attacker.

        Thuật toán (2 bước):
          1. `target.take_damage(dmg, 'stomp')` — chỉ mục tiêu chính ăn damage.
          2. Hỏi `WorldQuery.find_in_radius(attacker.x, attacker.y, _radius,
             'tower')` → với MỌI tháp trả về, gọi `tower.stun(_stun_duration)`.
             Dùng `callable(getattr(...))` để an toàn nếu entity không có stun().

        Quan trọng: tháp trong vùng chỉ bị CHOÁNG, KHÔNG ăn damage.

        Liên kết: `WorldQuery` (systems/world_query.py) để quét vùng;
        `Tower.stun()` (towers/tower.py) — no-op nếu tháp có item anti_stun.
        Tác động khi sửa: tăng `_radius` → choáng nhiều tháp hơn mỗi đòn Colossal.
        Chỉ số: balance.STRAT_GROUND_SLAM_MULT, balance.COLOSSAL_STOMP_AOE,
        balance.COLOSSAL_STOMP_STUN_DUR.
        """
        target.take_damage(amount=self.compute_damage(attacker), dtype=self._dtype)
        from systems.world_query import WorldQuery
        towers = WorldQuery.find_in_radius(attacker.x, attacker.y, self._radius, 'tower')
        for tower in towers:
            if callable(getattr(tower, 'stun', None)):
                tower.stun(self._stun_duration)


class Explosion(TitanAttackStrategy):
    """Phát nổ AoE quanh attacker — dành cho Kamikaze (suicide bomber).

    Titan vẫn AIM tới `target` như trước (quyết định lúc nào kích nổ — xem
    KamikazeAI), nhưng khi nổ thì KHÔNG còn phân biệt "mục tiêu chính" nữa:
    nổ theo VÙNG quanh vị trí attacker, mọi soldier/tower/wall/commander
    trong bán kính `_radius` ăn CÙNG 1 lượng damage như nhau — kể cả target
    ban đầu, nếu nó đã kịp chạy ra khỏi vùng nổ (né được) thì không dính,
    y hệt mọi entity khác. Knockback chỉ đẩy soldier ra xa.
    """

    _DEFAULT_DAMAGE_MULT = balance.STRAT_EXPLOSION_MULT
    _DEFAULT_DTYPE       = 'explode'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 radius: float = 80.0, knockback: float = 60.0) -> None:
        """Tạo đòn tự nổ.

        Tham số:
            radius: bán kính vùng nổ (px) quanh attacker.
            knockback: số px đẩy soldier ra xa tâm nổ (chỉ soldier bị đẩy).

        Kamikaze truyền giá trị thật từ `_EXP_AOE_RADIUS` / `_EXP_KNOCKBACK`
        (titan.py ← balance.KAMIKAZE_EXP_*).
        """
        super().__init__(damage_mult, dtype)
        self._radius    = radius
        self._knockback = knockback

    def execute(self, attacker, target: IAttackable):
        """Nổ theo VÙNG quanh attacker — mọi entity trong bán kính ăn CÙNG damage.

        Thuật toán:
          1. Tính damage 1 lần (`compute_damage`).
          2. Quét 4 loại entity ('soldier','commander','tower','wall') trong
             `_radius` quanh ATTACKER bằng `WorldQuery.find_in_radius`.
          3. Dùng set `seen` theo `id(e)` để 1 entity không ăn damage 2 lần
             (1 entity có thể xuất hiện ở nhiều lần quét).
          4. Bỏ qua entity đã chết (`is_alive`), rồi `take_damage(damage,'explode')`.
          5. Riêng 'soldier': đẩy ra xa tâm nổ `_knockback` px theo vector đơn vị
             (dx,dy)/dist.

        ĐIỂM QUAN TRỌNG: `target` (mục tiêu Kamikaze nhắm) KHÔNG được ưu tiên —
        nếu nó đã CHẠY RA KHỎI vùng nổ thì KHÔNG dính, y hệt mọi entity khác.
        Nghĩa là người chơi có thể NÉ được Kamikaze.

        Liên kết: gọi từ `Kamikaze._release_explosion()` (titan.py), có guard
        `_has_exploded` để không nổ 2 lần.
        Chỉ số: balance.STRAT_EXPLOSION_MULT, balance.KAMIKAZE_EXP_AOE_RADIUS,
        balance.KAMIKAZE_EXP_KNOCKBACK.
        """
        from systems.world_query import WorldQuery
        damage = self.compute_damage(attacker)

        # Nổ theo vùng: mọi entity còn sống trong bán kính, damage như nhau,
        # không phân biệt có phải target ban đầu hay không.
        # Bán kính "vỏ ngoài" của công trình lớn (khớp _get_target_radius ở
        # ai.py): tháp/HQ 40, tường 42. Kamikaze KÍCH NỔ theo RÌA mục tiêu
        # (`dist - t_rad <= _EXPLODE_RADIUS`) nên TÂM một công trình to có thể
        # cách xa hơn `_radius`; cộng vỏ ngoài vào bán kính quét = kiểm CHỒNG LẤN
        # hai đường tròn (vùng nổ ⊕ thân mục tiêu) → tháp/tường mà Kamikaze nhắm
        # mới thực sự dính nổ (trước đây đo tâm-đến-tâm nên tháp luôn hụt).
        _EDGE = {'tower': 40.0, 'hq': 40.0, 'wall': 42.0}
        seen = set()
        for etype in ('soldier', 'commander', 'tower', 'wall'):
            nearby = WorldQuery.find_in_radius(
                attacker.x, attacker.y, self._radius + _EDGE.get(etype, 0.0), etype)
            for e in nearby:
                if id(e) in seen:
                    continue
                if not getattr(e, 'is_alive', True):
                    continue
                seen.add(id(e))
                e.take_damage(amount=damage, dtype=self._dtype)
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

    _DEFAULT_DAMAGE_MULT = balance.STRAT_TOWER_HUNTER_MULT
    _DEFAULT_DTYPE       = 'siege'

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 tower_bonus_mult: float = 1.5) -> None:
        """Tạo đòn công thành.

        Tham số:
            tower_bonus_mult: nhân THÊM khi mục tiêu đúng là Tower (mặc định
                ×1.5). Tổng damage lên tháp = `_damage × _mult × 1.5`.
        """
        super().__init__(damage_mult, dtype)
        self._tower_bonus_mult = tower_bonus_mult

    def execute(self, attacker, target: IAttackable):
        """Đánh 1 mục tiêu; nếu mục tiêu là Tower thì nhân thêm bonus.

        Thuật toán: `isinstance(target, Tower)` → damage × `_tower_bonus_mult`;
        ngược lại damage thường. dtype='siege'.

        Vì sao import Tower BÊN TRONG hàm: tránh vòng lặp import
        (tower.py → soldier.py → ... ; còn attackstrategy nằm ở tầng characters).

        Ai dùng: TowerHunter (titan.py). Lưu ý AI của nó tự đổi strategy —
        nhắm tháp thì dùng class này, nhắm thứ khác thì HeavyStrikeStrategy.
        Chỉ số: balance.STRAT_TOWER_HUNTER_MULT.
        """
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

    _DEFAULT_DAMAGE_MULT = balance.STRAT_SOLDIER_HUNTER_MULT
    _DEFAULT_DTYPE       = 'soldier'

    _SPLASH_ENTITY_TYPES: tuple = ('soldier', 'commander', 'tower', 'wall', 'hq')

    def __init__(self, damage_mult: float = None, dtype: str = None,
                 splash_radius: float = 120.0, splash_mult: float = 0.5,
                 splash_dtype: str = 'aoe') -> None:
        """Tạo đòn cleave săn lính.

        Tham số:
            splash_radius: bán kính chém lan quanh ATTACKER (px).
            splash_mult: hệ số damage cho nạn nhân lan (0.5 = nửa damage chính).
            splash_dtype: dtype dùng cho damage lan ('aoe' — KHÔNG bị giáp chặn).
        """
        super().__init__(damage_mult, dtype)
        self._splash_radius = splash_radius
        self._splash_mult   = splash_mult
        self._splash_dtype  = splash_dtype

    def execute(self, attacker, target: IAttackable):
        """Đánh mục tiêu chính, rồi chém lan (nửa damage) ra mọi entity xung quanh.

        Thuật toán:
          1. Mục tiêu chính: damage đầy đủ, dtype='soldier'.
          2. `splash_dmg = int(base * _splash_mult)`.
          3. Quét `_SPLASH_ENTITY_TYPES` = soldier/commander/tower/wall/hq trong
             `_splash_radius` quanh ATTACKER.
          4. `seen_ids` khởi tạo = {id(target)} → mục tiêu chính KHÔNG bị đánh
             lần 2 bởi splash. Mỗi entity khác chỉ ăn splash đúng 1 lần.

        Nghĩa là đòn này trúng cả tường/HQ/tháp chứ không riêng lính — rất nguy
        hiểm khi lính đứng cụm.

        Ai dùng: SoldierHunter (titan.py) khi target là lính.
        Chỉ số: balance.STRAT_SOLDIER_HUNTER_MULT.
        """
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

    Khi land: AoE damage + pushback tween lên soldier/commander, và CHOÁNG
    mọi tháp trong vùng nổ (`tower_stun_duration` giây).
    Gọi `apply_pushback_tween(entity, dt)` trong update() của Soldier/Commander.

    Damage: MỌI mục tiêu trong bán kính AoE nhận CÙNG một lượng `damage` —
    không phân biệt mục tiêu chính hay lân cận (trước đây main 175 / splash 125).
    """

    _PUSHBACK_DECAY: float = 5.0

    def __init__(self, start_x: float, start_y: float, target,
                 velocity: float = 250.0, angle_deg: float = 15.0,
                 gravity: float = 600.0,
                 damage: int = 80,
                 aoe_radius: float = 80.0,
                 pushback_soldier: float = 100.0,
                 pushback_commander: float = 50.0,
                 tower_stun_duration: float = 5.0,
                 beast_x: float = None,
                 beast_y: float = None) -> None:
        """Tạo viên đá bay đạn đạo (parabol) từ tay Beast về phía target.

        Thuật toán khởi tạo vận tốc:
          1. Vector đơn vị (ux,uy) từ điểm ném → vị trí target TẠI THỜI ĐIỂM THẢ.
             (Nếu dist=0 → mặc định (0,1) để tránh chia 0.)
          2. Tách vận tốc: ngang `v*cos(angle)`, dọc-theo-trục-z `v*sin(angle)`.
             `vx,vy` là tốc độ TRÊN MẶT ĐẤT; `vz` là tốc độ BAY LÊN, `z` là độ cao.
          3. Mỗi frame `vz -= gravity*dt` → parabol. Chạm đất (z<=0, vz<0) → nổ.

        HỆ QUẢ CÂN BẰNG (bug tiềm ẩn đã biết): đá nhắm vị trí CŨ của target lúc
        thả, KHÔNG dẫn trước. Bay ~0.56s ở tầm 350px → mục tiêu chạy có thể ra
        khỏi AoE 100px.

        Tham số:
            target: entity nhắm tới (chỉ dùng để tính hướng lúc thả).
            velocity/angle_deg/gravity: thông số đạn đạo.
            damage: damage MỌI mục tiêu trong AoE (không phân biệt chính/lân cận).
            aoe_radius: bán kính nổ khi rơi.
            pushback_soldier / pushback_commander: lực đẩy tối đa (px).
            tower_stun_duration: số giây tháp bị choáng khi dính đá.
            beast_x/beast_y: vị trí Beast lúc ném — dùng để biết hướng "ra xa
                Beast" khi đẩy lùi (xem `_on_land`).

        Liên kết: tạo bởi `BeastTitan._release_rock()` (boss.py).
        Chỉ số: balance.BEAST_ROCK_* (velocity/gravity/damage/aoe/tower_stun) và
        balance.BEAST_PUSHBACK_SOLDIER / _COMMANDER.
        """
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

        self._damage             = damage
        self._aoe_radius         = aoe_radius
        self._pushback_soldier   = pushback_soldier
        self._pushback_commander = pushback_commander
        self._tower_stun_duration = tower_stun_duration

        self.alive   = True
        self._landed = False
        self._spin      = random.uniform(-180, 180)
        self._rot_angle = 0.0

    def update(self, dt: float) -> bool:
        """Tích phân 1 frame chuyển động parabol; nổ khi chạm đất.

        Thuật toán mỗi frame:
            x += vx*dt ; y += vy*dt        (di chuyển trên mặt đất)
            z += vz*dt ; vz -= gravity*dt  (bay lên rồi rơi xuống)
            _rot_angle += _spin*dt         (chỉ để vẽ đá xoay)
        Điều kiện chạm đất: `z <= 0 AND vz < 0` (phải đang RƠI, không phải vừa
        mới ném lên từ z=0) → set `alive=False` và gọi `_on_land()` (gây damage).

        Trả về: bool — True = còn bay; False = đã nổ/đã chết (caller xoá khỏi list).
        """
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
        """Nổ tại điểm rơi: damage AoE + choáng tháp + đẩy lùi lính/tướng.

        Thuật toán:
          1. Gom ứng viên: quét 'tower','soldier','commander','wall','hq' trong
             `_aoe_radius` quanh ĐIỂM RƠI. `type_map[id(e)] = etype` để nhớ loại.
          2. Nếu `_target` gốc còn sống mà KHÔNG nằm trong vùng → vẫn thêm vào
             (đảm bảo mục tiêu bị nhắm luôn ăn đòn dù lệch chút).
          3. Mỗi entity (lọc trùng bằng `seen`) ăn CÙNG `_damage`, dtype='rock'.
          4. Phân nhánh theo loại:
             - 'tower'     → gọi `stun(_tower_stun_duration)`, KHÔNG đẩy lùi.
             - 'soldier'   → lực đẩy tối đa `_pushback_soldier`.
             - 'commander' → lực đẩy tối đa `_pushback_commander`.
             - còn lại (wall/hq) → chỉ ăn damage.
          5. Lực đẩy có FALLOFF theo khoảng cách: `max_push * (1 - dist/aoe)` →
             đứng sát tâm bị đẩy mạnh nhất, ở rìa gần như không bị đẩy.
          6. Hướng đẩy: random 8 lần tìm hướng có tích vô hướng với vector
             "Beast → điểm rơi" >= 0, tức là đẩy RA XA Beast (không hút ngược
             vào Beast). Thất bại 8 lần → dùng thẳng hướng forward.
          7. Không dời entity ngay: cộng vào `pushback_vx/vy` để
             `apply_pushback_tween()` trượt mượt qua nhiều frame.

        Liên kết: `WorldQuery.find_in_radius`, `Tower.stun()`.
        Chỉ số: balance.BEAST_ROCK_DAMAGE / _AOE_RADIUS / _TOWER_STUN,
        balance.BEAST_PUSHBACK_SOLDIER / _COMMANDER.
        """
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
            # Mọi mục tiêu trong vùng nổ ăn CÙNG một lượng damage — không còn
            # phân biệt mục tiêu chính (175) với lân cận (125).
            e.take_damage(amount=self._damage, dtype='rock')

            etype = type_map.get(id(e))
            if etype == 'tower':
                # Đá trúng tháp → tháp CHOÁNG (ngừng bắn) trong `_tower_stun_duration` giây.
                stun = getattr(e, 'stun', None)
                if callable(stun):
                    stun(self._tower_stun_duration)
                continue
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
        """Trượt entity theo vector pushback, giảm dần theo hàm mũ (1 frame).

        Thuật toán:
            entity.x += vx*dt ; entity.y += vy*dt
            factor = exp(-_PUSHBACK_DECAY * dt)   (decay = 5.0)
            vx *= factor ; vy *= factor
            |vx|<1 và |vy|<1 → gán 0 (chốt lại, tránh trôi vô tận)
        Nhờ decay hàm mũ, cú đẩy mạnh lúc đầu rồi tắt mượt — thay vì "dịch chuyển
        tức thời" trông giật cục.

        static method vì nó thao tác trên entity BẤT KỲ (Soldier/Commander), không
        cần biết viên đá nào đã đẩy.

        PHẢI được gọi trong `update(dt)` của Soldier (soldier.py) và Commander
        (commander.py); nếu quên gọi → entity KHÔNG bao giờ bị đẩy dù đã dính đá.
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
        """Vẽ viên đá đang bay + bóng đổ dưới đất (chỉ đồ hoạ).

        Thuật toán:
          - Đá vẽ ở `(x, y - z)`: trừ `z` để đá TRÔNG NHƯ bay lên cao, dù toạ độ
            logic trên mặt đất vẫn là (x,y). Xoay theo `_rot_angle`.
          - Bóng vẽ ở đúng `(x, y)` (chân đá) với alpha `max(40, 120 - z)` → đá
            càng cao, bóng càng mờ; tạo cảm giác độ cao.
          - Không có sprite → vẽ vòng tròn xám thay thế (fallback).

        Tham số:
            rock_frame: 1 frame sprite đá, do `BeastTitan` cắt từ sheet và truyền
                vào (boss.py). Có thể None.

        Lưu ý: caller PHẢI trừ camera offset trước khi gọi, nếu không đá sẽ vẽ
        sai chỗ (đây từng là bug `_world_x` gán-một-lần trong boss.py).
        """
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
        """Sinh 1 hạt hơi nóng tại (cx, cy) với thông số NGẪU NHIÊN.

        Mọi thứ random để đám hạt trông tự nhiên, không "đồng phục":
            angle/speed  → hướng + tốc độ bay toả ra (vx, vy).
            _radius      → bán kính ban đầu (4-10 px).
            _max_r       → bán kính phình tối đa (15-35 px).
            _spawn_delay → 0-0.8s trễ mới hiện (hiệu ứng "tan dần từng hạt",
                           không bùng lên cùng lúc).
            _lifetime    → 1.5-4.5s, mỗi hạt tắt theo nhịp riêng.

        Đây là hạt THUẦN ĐỒ HOẠ — KHÔNG gây damage. Damage của Steam Burst do
        `ColossalTitan._steam_burst()` (boss.py) tự tính riêng.
        """
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
        """Tiến 1 frame: bay chậm dần, phình to, mờ dần.

        Thuật toán:
          1. Còn `_spawn_delay` → chưa hiện (alpha=0), chỉ đếm ngược. Return True.
          2. `_age += dt`; `t = age/lifetime` (0→1, kẹp ở 1).
          3. Bay: x += vx*dt; rồi `vx *= 0.93` mỗi frame → ma sát, hạt chậm dần.
          4. Phình: `_radius += (_max_r - _radius) * dt * 3` → tiệm cận `_max_r`
             (nhanh lúc đầu, chậm lúc sau — easing).
          5. Mờ: `alpha = 200 * (1-t)²` → ease-out, tắt êm chứ không tắt tuyến tính.

        Trả về: bool — True = còn sống; False = hết `_lifetime`, caller xoá hạt.
        """
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
        """Vẽ hạt: vòng tròn xám bán trong suốt.

        Vì sao phải tạo Surface riêng: `pygame.draw.circle` KHÔNG vẽ được alpha
        trực tiếp lên screen. Cách làm: tạo Surface nhỏ (2r × 2r) cờ SRCALPHA,
        vẽ vòng tròn màu (160,160,160, alpha) lên đó, rồi blit vào screen.

        Bỏ qua khi alpha<=0 (chưa spawn / đã tắt) hoặc bán kính < 1px.
        """
        if self._alpha <= 0 or self._radius < 1:
            return
        r = int(self._radius)
        surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (160, 160, 160, self._alpha), (r, r), r)
        screen.blit(surf, (int(self.x) - r, int(self.y) - r))
