# characters/soldiers/soldier.py
from __future__ import annotations

import math
import os

import pygame

from core.entity import Entity
from core.interfaces import IAttackable, IMovable
from characters.soldiers.animation import CommanderAnimator, load_clips
from characters.soldiers import assets_config as ac
from config import balance

_SPRITES_DIR = os.path.join(os.path.dirname(__file__), "sprites")


class Soldier(Entity, IAttackable, IMovable):
    """Lớp cha trừu tượng của mọi lính phe phòng thủ (Warrior/Archer/Lancer).

    Máy trạng thái `_state` (5 trạng thái, xem chi tiết ở `update()`):
        COMBAT  — đang săn titan / đánh nhau.
        RETREAT — không có titan trong tầm → về THÁP NHÀ để hồi máu.
        IDLE    — đã về tới tháp, đứng gác + hồi máu, chờ titan xuất hiện lại.
        MOVING  — đang được ĐIỀU CHUYỂN từ tháp A sang tháp B (transfer).
        DEAD    — is_alive=False (không phải giá trị `_state` thật, chỉ là quy ước).

    Class con (Warrior/Archer/Lancer) chỉ cần ghi đè các hằng
    BASE_HP/SPEED/ATTACK_*/BODY_COLOR — toàn bộ logic hành vi nằm ở đây.
    """

    ENTITY_TYPE: str = "soldier"
    FACTION: str = "ally"
    NAME: str = "Soldier"

    # --- Subclass sprite hooks ------------------------------------------
    SPRITE_FOLDER: str = ""
    SPRITE_FRAMES: dict = {}
    FRAME_SIZE: int = 192
    TARGET_HEIGHT_PX: int = 42

    # --- Subclass combat stats ------------------------------------------
    BASE_HP: int = balance.SOLDIER_BASE_HP
    DEFENSE: int = balance.SOLDIER_DEFENSE
    SPEED: float = balance.SOLDIER_SPEED
    ATTACK_DAMAGE: int = balance.SOLDIER_ATTACK_DAMAGE
    ATTACK_RANGE: float = balance.SOLDIER_ATTACK_RANGE
    ATTACK_COOLDOWN: float = balance.SOLDIER_ATTACK_COOLDOWN
    IS_RANGED: bool = False
    TAUNTS: bool = False

    HOME_VANISH_DIST_PX: float = 60.0

    # Hồi máu khi ở trong tháp (IDLE)
    HEAL_RATE: int  = balance.SOLDIER_HEAL_RATE    # HP hồi mỗi tick
    HEAL_TICK: float = balance.SOLDIER_HEAL_TICK # giây giữa mỗi tick

    BODY_COLOR: tuple = (90, 160, 220)
    BODY_RADIUS: int = 10

    # Bán kính VA CHẠM tường (KHÁC BODY_RADIUS dùng cho vẽ/đến đích).
    # Tường thật = collider 32px cách nhau 59/54px → có khe "hàng rào" 27/22px
    # GIỮA các collider. BODY_RADIUS=10 < 13.5 → lính lọt khe → XUYÊN TƯỜNG.
    # Đặt 18 (>13.5): chặn khe hàng rào (tường đặc) nhưng vẫn lọt lỗ THẬT
    # (1-tile vỡ: nửa-khe 37-42px > 18) → lính chỉ qua được CHỖ TƯỜNG ĐÃ VỠ.
    WALL_RADIUS: int = 18

    def __init__(self, x: float, y: float, *, target=None,
                 headless: bool = False,
                 home_pos: tuple | None = None,
                 home_radius: float = 600.0) -> None:
        """Khởi tạo lính tại (x,y), gắn THÁP NHÀ, áp buff trại lính, nạp animation.

        Tham số:
            target: titan nhắm sẵn (thường None — lính tự tìm qua `_acquire_nearest_titan`).
            headless: True khi test/CI không display.
            home_pos: vị trí THÁP NHÀ — lính RETREAT về đây khi hết titan. None →
                dùng chính (x,y) làm nhà.
            home_radius: bán kính phát hiện titan quanh nhà (mặc định 600px).

        **Áp buff trại lính NGAY LÚC SPAWN** (không phải lazy): quét
        `TrainingCamp` đầu tiên trong `WorldQuery`, nhân `hp_mult`/`dmg_mult` vào
        `_max_hp`/`_damage`. Bọc try/except NGẦM (`except: pass`) — WorldQuery
        chưa sẵn sàng lúc khởi tạo sớm thì lính vẫn tạo được với stat GỐC, không crash.

        State quan trọng khác:
            `_can_heal` — True mặc định; antiheal (Wolf) tắt VĨNH VIỄN tới khi chết.
            `_homeless` — True khi tháp chủ bị phá, lính không còn nơi về.
            `_zones` — vùng được phép phát hiện titan (gán từ tháp chủ).
            `_pf_gap_timer`/`_pf_cached_gap` — CACHE + THROTTLE tìm lỗ tường: chỉ
                gọi lại `WorldQuery.find_nearest_gap_center()` (đắt) mỗi 10 frame,
                dùng lại kết quả cache giữa các lần — tránh lag khi đông lính.

        Chỉ số: balance.SOLDIER_BASE_HP/_SPEED/_ATTACK_DAMAGE/_ATTACK_RANGE/
        _ATTACK_COOLDOWN, balance.SOLDIER_HEAL_RATE/_HEAL_TICK.
        """
        super().__init__(x, y)
        self._max_hp = int(self.BASE_HP)
        self._hp = int(self.BASE_HP)
        self._damage = int(self.ATTACK_DAMAGE)
        
        # Apply camp buffs
        try:
            from systems.world_query import WorldQuery
            from structures.buildings.building import TrainingCamp
            camps = [b for b in WorldQuery.get_all_buildings() if isinstance(b, TrainingCamp)]
            if camps:
                buffs = camps[0].get_soldier_buffs()
                self._max_hp = int(self.BASE_HP * buffs.get('hp_mult', 1.0))
                self._hp = self._max_hp
                self._damage = int(self.ATTACK_DAMAGE * buffs.get('dmg_mult', 1.0))
        except Exception:
            pass
            
        self._target = target
        self._atk_timer: float = 0.0
        self._headless = headless
        self._squad = None
        self._slot_offset: tuple = (0.0, 0.0)
        self._state: str = "COMBAT"  # COMBAT, RETREAT, IDLE, DEAD, MOVING
        self._home_pos: tuple = (
            (float(x), float(y)) if home_pos is None
            else (float(home_pos[0]), float(home_pos[1]))
        )
        self._home_radius: float = float(home_radius)
        self._transfer_target: object = None  # Tower đích (khi MOVING)
        self._heal_timer: float = 0.0         # tích lũy khi IDLE, reset khi ra chiến
        self._can_heal: bool = True           # False vĩnh viễn sau khi dính đòn
                                               # antiheal (Wolf) — cho tới khi chết
        self._original_home: tuple = self._home_pos  # Home gốc (Tower A)
        self._zones: tuple = ()  # Vùng cho phép phát hiện titan (theo tháp chủ)
        self._homeless: bool = False  # True khi tháp chủ bị phá (không nơi về)
        # ── Frame-throttle cho gap-search (chống kẹt tường) ──────────────────────
        # _pf_gap_timer đếm ngược từ 10; khi đến 0 mới chạy lại WorldQuery.find_nearest_gap_center.
        # _pf_cached_gap: kết quả cầu có gáp gần nhất từ lần tìm gần nhất (dùng lại giữa các frame).
        self._pf_gap_timer: int = 0
        self._pf_cached_gap: tuple | None = None

        clips = load_clips(
            self.SPRITE_FOLDER, self.SPRITE_FRAMES,
            frame_width=self.FRAME_SIZE, frame_height=self.FRAME_SIZE,
            target_character_height=self.TARGET_HEIGHT_PX,
            headless=headless,
        )
        self._animator = CommanderAnimator(clips, initial_state="idle")

    # --- read-only props -------------------------------------------------

    @property
    def hp(self) -> int:
        """HP hiện tại (đã tính buff trại lính, nếu có)."""
        return self._hp

    @property
    def max_hp(self) -> int:
        """HP tối đa (đã tính buff trại lính)."""
        return self._max_hp

    @property
    def is_taunting(self) -> bool:
        """True nếu lính này KÉO AGGRO titan (chỉ Warrior có `TAUNTS=True`) và còn sống."""
        return self.TAUNTS and self.is_alive

    # --- targeting -------------------------------------------------------

    def set_target(self, titan) -> None:
        """Gán mục tiêu THỦ CÔNG — dùng bởi caller ngoài (vd dispatch system);
        `update()` vẫn có thể tự đổi mục tiêu sau đó qua `_acquire_nearest_titan`."""
        self._target = titan

    def _acquire_nearest_titan(self) -> None:
        """Acquire the alive titan nearest to me, restricted to accessible zones.

        Vùng cơ bản: lấy thẳng từ _zones của tháp chủ (ổn định, không phụ
        thuộc vị trí lính hiện tại — tránh flicker khi đứng ở biên vùng).

        Mở rộng zone: nếu có lỗ hổng tường trong home_radius → cho phép nhận
        diện titan từ vùng kề bên (có thể đi qua lỗ để tới).
        """
        from systems.world_query import WorldQuery
        hx, hy = self._home_pos
        r  = self._home_radius
        candidates = WorldQuery.find_in_radius(
            cx=hx, cy=hy, radius=r, entity_type="titan"
        )

        # Vùng gốc: lấy thẳng từ tháp chủ (_zones được gán khi spawn/re-spawn)
        allowed: set = set(getattr(self, '_zones', ()))
        if not allowed:
            allowed = {WorldQuery.zone_of(hx, hy)}

        # Mở rộng nếu có lỗ hổng tường trong tầm → cho phép vùng kề (đi qua lỗ).
        # Thay vì mở khóa bừa bãi khi có bất kỳ lỗ hổng nào, ta dùng get_dead_wall_zone_pairs_near
        # để tìm ĐÍCH DANH bức tường nào bị vỡ. Dùng snapshot base_allowed để tránh cascade.
        dead_zone_pairs = WorldQuery.get_dead_wall_zone_pairs_near(hx, hy, r, min_sections=1)
        if dead_zone_pairs:
            base_allowed = set(allowed)
            for inner_z, outer_z in dead_zone_pairs:
                if inner_z in base_allowed or outer_z in base_allowed:
                    allowed.add(inner_z)
                    allowed.add(outer_z)

        best, best_d2 = None, float("inf")
        for e in candidates:
            if not getattr(e, "is_alive", False):
                continue
            if WorldQuery.zone_of(e.x, e.y) not in allowed:
                continue
            d2 = (e.x - self.x) ** 2 + (e.y - self.y) ** 2
            if d2 < best_d2:
                best, best_d2 = e, d2
        self._target = best


    def _target_outside_home_zone(self, target) -> bool:
        """True when our current target has wandered out of zone."""
        hx, hy = self._home_pos
        rh2 = self._home_radius * self._home_radius
        return (target.x - hx) ** 2 + (target.y - hy) ** 2 > rh2

    # --- IMovable --------------------------------------------------------

    def move(self, destination: tuple) -> None:
        """API `IMovable` — hiện tại CHỈ xoá mục tiêu hiện tại (KHÔNG dịch chuyển thật).

        Lính không có cơ chế "đi tới điểm tuỳ ý" như tướng — di chuyển của lính
        HOÀN TOÀN do máy trạng thái trong `update()` quyết định (đuổi titan / về
        nhà / transfer). Gọi `move()` chỉ có tác dụng buộc lính TÌM LẠI mục tiêu
        ở frame tiếp theo.
        """
        self._target = None

    # --- IAttackable -----------------------------------------------------

    def take_damage(self, amount: int, dtype: str = "phys") -> None:
        """Nhận damage — trừ giáp (`DEFENSE`), kích debuff antiheal nếu dtype khớp.

        Thuật toán:
          1. Đã chết → không làm gì.
          2. `dtype == 'antiheal'` (đòn Wolf) → `_can_heal = False` VĨNH VIỄN
             (không có gì đặt lại True — chỉ hết hiệu lực khi lính CHẾT và bị xoá,
             lần train mới tạo object mới với `_can_heal=True` từ đầu).
          3. `dealt = max(1, amount - DEFENSE)` — LUÔN ăn ít nhất 1 damage dù giáp
             cao tới đâu (không có "miễn nhiễm tuyệt đối").
          4. HP <= 0 → kẹp về 0, `is_alive = False`.

        Chỉ số: balance.SOLDIER_DEFENSE (base), riêng từng loại lính override.
        """
        if not self.is_alive:
            return
        if dtype == 'antiheal':
            self._can_heal = False   # vĩnh viễn — không tự hồi lại (Wolf)
        # Đòn tín hiệu thuần (đẩy lùi/pushback với amount<=0) KHÔNG gây damage.
        # Thiếu nhánh này thì `max(1, ...)` biến mọi tín hiệu 0-damage thành −1 HP,
        # bào dần lính giòn qua steam Colossal/knockback AoE (tướng dùng max(0,)
        # nên miễn nhiễm — lính phải khớp).
        if int(amount) <= 0:
            return
        dealt = max(1, int(amount) - self.DEFENSE)
        self._hp -= dealt
        if self._hp <= 0:
            self._hp = 0
            self.is_alive = False

    # --- Entity ----------------------------------------------------------

    def update(self, dt: float) -> None:
        """VÒNG UPDATE CHÍNH — máy trạng thái 4 nhánh (COMBAT ngầm định + 3 return sớm).

        Thuật toán, theo thứ tự:
          1. Chết → không làm gì.
          2. Đếm ngược `_pf_gap_timer` (throttle tìm lỗ tường).
          3. **Squad đánh thức**: squad chuyển sang COMBAT mà lính đang IDLE →
             đánh thức lính theo (`_state = "COMBAT"`).
          4. **`_state == "IDLE"`** (return sớm): thử tìm titan
             (`_acquire_nearest_titan`) — có → chuyển COMBAT, reset heal timer.
             Không có → HỒI MÁU theo tick (`HEAL_RATE` mỗi `HEAL_TICK` giây),
             CHỈ khi `_can_heal` (chưa dính antiheal). Rồi `return`.
          5. **`_state == "MOVING"`** (return sớm): `_move_to_tower()` (transfer
             giữa 2 tháp qua A*), rồi `return`.
          6. Còn lại coi như COMBAT (state có thể vẫn ghi "COMBAT" hoặc chuyển
             "RETREAT" ngay dưới):
             a. Áp pushback từ đá Beast (nếu có).
             b. Đếm ngược `_atk_timer`.
             c. Mục tiêu chết/mất/RA KHỎI VÙNG NHÀ → `_acquire_nearest_titan()`
                tìm lại.
             d. **KHÔNG có mục tiêu**: `_homeless` (tháp chủ đã bị phá) → đứng yên
                tại chỗ (KHÔNG RETREAT — không còn nhà để về), rồi `return`.
                Còn nhà → chuyển `_state = "RETREAT"`, gọi `_retreat_into_home()`, `return`.
             e. **CÓ mục tiêu**: tính `target_y` (với titan, cộng nửa chiều cao
                sprite để nhắm vào GIỮA THÂN thay vì chân — dùng `_DISPLAY_SIZE`
                hoặc `_FRAME_SIZE` tuỳ loại titan có).
                - Kiểm tra `same_zone` (cùng vùng tường) VÀ có đang "gần lỗ hổng"
                  hay không (cache `_pf_cached_gap`, coi là còn trong lỗ nếu cách
                  tâm lỗ < 48px).
                - **Khác vùng HOẶC đang thoát lỗ**: BẮT BUỘC tìm lỗ tường mà lách
                  qua (`gap_aim` + `follow_path` với `is_passing_gap=True`) — CỐ
                  Ý không đâm thẳng tường để tránh trượt vô tận dọc tường. Không
                  có lỗ → đành đi thẳng, chấp nhận có thể kẹt.
                - **Cùng vùng nhưng NGOÀI tầm đánh**: đi thẳng tới mục tiêu.
                - **Cùng vùng VÀ trong tầm**: hết cooldown → `_do_attack(target)`.

        Chỉ số: balance.SOLDIER_HEAL_RATE/_HEAL_TICK, balance.<TYPE>_ATTACK_RANGE/_ATTACK_COOLDOWN.
        Liên kết: `systems/pathmove.py::gap_aim/follow_path`, `WorldQuery.same_zone/find_nearest_gap_center`.
        """
        if not self.is_alive:
            return

        # Giảm gap search timer dùng để throttle gap search
        if self._pf_gap_timer > 0:
            self._pf_gap_timer -= 1

        # Nếu squad có state, kiểm tra xem squad chuyển COMBAT chưa
        if self._squad is not None:
            squad_state = getattr(self._squad, '_state', 'COMBAT')
            if squad_state == "COMBAT" and self._state == "IDLE":
                self._state = "COMBAT"  # ← Wake up!

        # Nếu lính ở trạng thái IDLE → hồi máu, đánh thức khi có titan
        if self._state == "IDLE":
            self._acquire_nearest_titan()
            if self._target is not None:
                self._state = "COMBAT"
                self._heal_timer = 0.0  # titan xuất hiện → reset heal
            else:
                # Hồi máu từng tick khi trong tháp — bỏ qua nếu dính antiheal
                if self._hp < self._max_hp and self._can_heal:
                    self._heal_timer += dt
                    if self._heal_timer >= self.HEAL_TICK:
                        self._heal_timer = 0.0
                        self._hp = min(self._max_hp, self._hp + self.HEAL_RATE)
                else:
                    self._heal_timer = 0.0
                self._animator.update(dt)
                return

        # MOVING state: di chuyển từ Tower A sang Tower B (transfer)
        if self._state == "MOVING":
            self._move_to_tower(dt)
            self._animator.update(dt)
            return

        # Rock AoE pushback tween từ BeastTitan
        if getattr(self, 'pushback_vx', 0.0) != 0.0 or getattr(self, 'pushback_vy', 0.0) != 0.0:
            from characters.titans.attackstrategy import RockProjectile
            RockProjectile.apply_pushback_tween(self, dt)
        if self._atk_timer > 0:
            self._atk_timer = max(0.0, self._atk_timer - dt)

        if (self._target is None
                or not getattr(self._target, "is_alive", False)
                or self._target_outside_home_zone(self._target)):
            self._acquire_nearest_titan()

        target = self._target
        if target is None:
            if self._homeless:
                # Mất tháp → không có nơi về, đứng yên tại chỗ chờ titan
                if self._animator.state != "idle":
                    self._animator.set_state("idle")
                self._animator.update(dt)
                return
            self._state = "RETREAT"  # ← Chuyển sang RETREAT
            self._retreat_into_home(dt)
            self._animator.update(dt)
            return

        if getattr(target, 'ENTITY_TYPE', '') == 'titan':
            if hasattr(target, '_DISPLAY_SIZE'):
                target_y = target.y + (target._DISPLAY_SIZE / 2.0)
            elif hasattr(target, '_FRAME_SIZE'):
                target_y = target.y + (target._FRAME_SIZE / 2.0)
            else:
                target_y = target.y + 45.0
        else:
            target_y = target.y

        dx = target.x - self.x
        dy = target_y - self.y
        dist = math.hypot(dx, dy)
        if abs(dx) > 0.5:
            self._animator.set_facing(dx > 0)

        from systems.world_query import WorldQuery
        same_zone = WorldQuery.same_zone(self.x, self.y, target.x, target.y, strict=True, strict_margin=24.0)

        # Lấy gap cached từ frame trước
        gap = self._pf_cached_gap
        is_near_gap = False
        if gap is not None:
            cx, cy, _ = gap
            # Nếu cách tâm lỗ dưới 48px, coi như vẫn đang chui lỗ (chưa thoát hẳn)
            is_near_gap = (self.x - cx) ** 2 + (self.y - cy) ** 2 < 2304.0

        # Muốn tấn công phải chung vùng (cùng zone) và đã thoát khỏi lỗ hổng hoàn toàn.
        if not same_zone or is_near_gap:
            # Khác vùng hoặc đang thoát lỗ: BẮT BUỘC tìm lỗ và lách qua, không cố đâm thẳng tường để tránh trượt (slide) vô tận.
            if not is_near_gap and getattr(self, '_pf_gap_timer', 0) <= 0:
                from systems.world_query import WorldQuery
                self._pf_cached_gap = WorldQuery.find_nearest_gap_center(
                    self.x, self.y, target.x, target_y, 3000.0, min_sections=1)
                self._pf_gap_timer = 10
            gap = self._pf_cached_gap
            if gap is not None:
                from systems.pathmove import gap_aim, follow_path
                aim_x, aim_y, is_in_hole = gap_aim(self.x, self.y, target.x, target_y, gap,
                                       self.WALL_RADIUS, align_tol=11.0)
                follow_path(self, aim_x, aim_y, self.SPEED, dt,
                            radius=8.0, collide_radius=0.0 if is_in_hole else 12.0,
                            is_passing_gap=True, gap_center=gap)
            else:
                # Không có lỗ, đi thẳng tới vách tường và trượt (chấp nhận kẹt)
                from systems.pathmove import follow_path
                follow_path(self, target.x, target_y, self.SPEED, dt,
                            radius=8.0, collide_radius=self.WALL_RADIUS)
            if self._animator.state != "walk":
                self._animator.set_state("walk")
        elif dist > self.ATTACK_RANGE:
            # Chung vùng nhưng xa ngoài tầm đánh -> đi thẳng tới mục tiêu
            from systems.pathmove import follow_path
            follow_path(self, target.x, target_y, self.SPEED, dt,
                        radius=8.0, collide_radius=self.WALL_RADIUS)
            if self._animator.state != "walk":
                self._animator.set_state("walk")
        else:
            # Chung vùng và trong tầm -> tấn công
            if self._atk_timer <= 0:
                self._do_attack(target)
                self._atk_timer = self.ATTACK_COOLDOWN

        self._animator.update(dt)

    def _retreat_into_home(self, dt: float) -> None:
        """Về tháp, NÉ TƯỜNG (đi qua lỗ vỡ, không xuyên tường). Tới sát tháp → IDLE."""
        hx, hy = self._home_pos
        d = math.hypot(hx - self.x, hy - self.y)
        if d > self.HOME_VANISH_DIST_PX:
            if abs(hx - self.x) > 0.5:
                self._animator.set_facing(hx > self.x)
            from systems.world_query import WorldQuery
            
            # Rescue: Nếu lính đã về gần tháp (d <= 120) và cọ sát vào tường,
            # coi như đã về tới đích, đứng gác tại chỗ (giữ nguyên logic gốc).
            if d <= 120.0 and WorldQuery.is_wall_blocked(self.x, self.y, self.WALL_RADIUS + 2.0):
                self._state = "IDLE"
                self._target = None
                self._heal_timer = 0.0
                self._animator.set_state("idle")
                return
                
            same_zone = WorldQuery.same_zone(self.x, self.y, hx, hy, strict=True, strict_margin=24.0)

            gap = self._pf_cached_gap
            is_near_gap = False
            if gap is not None:
                cx, cy, _ = gap
                is_near_gap = (self.x - cx) ** 2 + (self.y - cy) ** 2 < 2304.0

            if not same_zone or is_near_gap:
                if not is_near_gap and self._pf_gap_timer <= 0:
                    self._pf_cached_gap = WorldQuery.find_nearest_gap_center(
                        self.x, self.y, hx, hy, 3000.0, min_sections=1)
                    self._pf_gap_timer = 10
                gap = self._pf_cached_gap
                if gap is not None:
                    from systems.pathmove import gap_aim, follow_path
                    aim_x, aim_y, is_in_hole = gap_aim(self.x, self.y, hx, hy, gap,
                                           self.WALL_RADIUS, align_tol=11.0)
                    follow_path(self, aim_x, aim_y, self.SPEED, dt,
                                radius=self.BODY_RADIUS,
                                collide_radius=0.0 if is_in_hole else 12.0,
                                is_passing_gap=True, gap_center=gap)
                else:
                    from systems.pathmove import follow_path
                    follow_path(self, hx, hy, self.SPEED, dt,
                                radius=self.BODY_RADIUS,
                                collide_radius=self.WALL_RADIUS,
                                ignore_buffer=True)
                if self._animator.state != "walk":
                    self._animator.set_state("walk")
            else:
                from systems.pathmove import follow_path
                res = follow_path(self, hx, hy, self.SPEED, dt,
                                  radius=self.BODY_RADIUS,
                                  collide_radius=self.WALL_RADIUS,
                                  ignore_buffer=True)
                
                # Rescue: Nếu dường như đã về sát tháp nhưng vô tình kẹt cạnh tường
                if res == 'blocked' and d <= 120.0:
                    self._state = "IDLE"
                    self._target = None
                    self._heal_timer = 0.0
                    self._animator.set_state("idle")
                    return
                if self._animator.state != "walk":
                    self._animator.set_state("walk")
            return
        self._state = "IDLE"
        self._target = None
        self._heal_timer = 0.0
        self._animator.set_state("idle")

    def _move_to_tower(self, dt: float) -> None:
        """Di chuyển từ Tower A sang Tower B (transfer). Né tường, không chủ động attack."""
        if self._transfer_target is None:
            self._state = "IDLE"
            self._heal_timer = 0.0
            return

        tx = getattr(self._transfer_target, 'x', self.x)
        ty = getattr(self._transfer_target, 'y', self.y)
        # Tower dùng AGGRO_RADIUS; fallback home_radius / 600
        t_radius = getattr(self._transfer_target, 'AGGRO_RADIUS', None)
        if t_radius is None:
            t_radius = getattr(self._transfer_target, 'home_radius', 600.0)

        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)

        # Đã vào được phạm vi của Tower B → arrive
        # Dùng khoảng cố định 120px thay vì AGGRO_RADIUS (600px) để tránh
        # lính "arrive" ngay lập tức khi tháp A và tháp B ở gần nhau.
        if dist <= 120.0:
            self._home_pos = (float(tx), float(ty))
            self._home_radius = float(t_radius)
            self._transfer_target = None
            self._state = "COMBAT"
            self._target = None
            # Đánh thức squad sang COMBAT để cơ chế wake hoạt động về sau
            if self._squad is not None:
                self._squad._state = "COMBAT"
            return

        # Di chuyển tới Tower B theo A*
        if abs(dx) > 0.5:
            self._animator.set_facing(dx > 0)
            
        # Tìm đường bằng A* (chỉ tính 1 lần cho mỗi lệnh transfer)
        if getattr(self, '_pf_target_id', None) != id(self._transfer_target) or not hasattr(self, '_transfer_path'):
            from systems.pathfinding import AStarPathfinder
            from systems.world_query import WorldQuery
            self._transfer_path = AStarPathfinder.find_path(
                self.x, self.y, tx, ty,
                radius=self.BODY_RADIUS, buffer=12.0
            )
            self._pf_target_id = id(self._transfer_target)
            # Tháp nguồn nằm trên tường → wall section tại đó + 2 tile mỗi bên (192px)
            # bị bypass collision khi lính di chuyển, tránh lính bị kẹt do A* route
            # qua mặt tường đối diện (150px exception tạo path xuyên tường).
            # A* vẫn dùng chúng làm vật cản — chỉ bỏ cho follow_path vật lý.
            ox, oy = self._original_home
            self._transfer_wall_exclude = {
                w for w in getattr(WorldQuery, '_wall_refs', [])
                if (math.hypot(getattr(w, 'x', 0) - ox, getattr(w, 'y', 0) - oy) <= 192.0
                    or math.hypot(getattr(w, 'x', 0) - tx, getattr(w, 'y', 0) - ty) <= 192.0)
            }

        if self._transfer_path:
            wp_x, wp_y = self._transfer_path[0]
            # Nếu đã đến gần waypoint hiện tại, chuyển sang waypoint tiếp theo
            if math.hypot(wp_x - self.x, wp_y - self.y) < 60.0:
                self._transfer_path.pop(0)
                if self._transfer_path:
                    wp_x, wp_y = self._transfer_path[0]

            from systems.pathmove import follow_path
            dx_t, dy_t = tx - self.x, ty - self.y
            dist_t = math.hypot(dx_t, dy_t)
            is_last = len(self._transfer_path) <= 1

            follow_path(self, wp_x, wp_y, self.SPEED, dt,
                        radius=self.BODY_RADIUS,
                        collide_radius=self.WALL_RADIUS,
                        exclude=getattr(self, '_transfer_wall_exclude', None),
                        ignore_buffer=is_last and dist_t < 200.0)
                        
        if self._animator.state != "walk":
            self._animator.set_state("walk")

    def _do_attack(self, target) -> None:
        """Đánh CẬN CHIẾN mặc định — trúng NGAY, không có bay đạn. Archer override để bắn tên.

        Thuật toán: chuyển animation "attack" → `target.take_damage(_damage,
        'phys')` NGAY LẬP TỨC (không độ trễ bay đạn) → báo AI titan biết vừa bị
        đánh (`notify_attacked`) để nó có thể phản đòn.

        Tham số: target — titan đang đánh.
        Chỉ số: balance.<TYPE>_ATTACK_DAMAGE.
        """
        self._animator.set_state("attack")
        target.take_damage(self._damage, "phys")
        ai = getattr(target, '_ai', None)
        if ai is not None:
            ai.notify_attacked(self)

    def draw(self, screen) -> None:
        """Vẽ sprite lính + HP bar (chỉ hiện khi bị thương) + icon "đói"/"thiếu vũ khí".

        Không có frame → vẽ vòng tròn màu `BODY_COLOR` thay thế (fallback).
        HP bar chỉ vẽ khi `_hp < _max_hp` (lính đầy máu không cần thanh máu che khuất).
        CHỈ ĐỒ HOẠ.
        """
        frame = self._animator.current_frame()
        sprite_h = self.BODY_RADIUS * 2
        if frame is not None:
            rect = frame.get_rect(midbottom=(int(self.x), int(self.y)))
            screen.blit(frame, rect)
            sprite_h = frame.get_height()
        else:
            pygame.draw.circle(
                screen, self.BODY_COLOR,
                (int(self.x), int(self.y) - self.BODY_RADIUS), self.BODY_RADIUS)
            pygame.draw.circle(
                screen, (255, 255, 255),
                (int(self.x), int(self.y) - self.BODY_RADIUS), self.BODY_RADIUS, 1)
        bar_w = 26
        ratio = self._hp / self._max_hp if self._max_hp else 0.0
        bx = int(self.x) - bar_w // 2
        by = int(self.y) - sprite_h - 6
        try:
            pygame.draw.rect(screen, (120, 20, 20), (bx, by, bar_w, 4))
            pygame.draw.rect(screen, (60, 210, 90),
                             (bx, by, int(bar_w * ratio), 4))
            if self.is_taunting:
                pygame.draw.circle(screen, (230, 180, 70),
                                   (int(self.x), int(self.y) - self.BODY_RADIUS),
                                   self.BODY_RADIUS + 6, 1)
        except (AttributeError, pygame.error):
            pass


# ---------------------------------------------------------------------------
# Concrete soldier types
# ---------------------------------------------------------------------------

class ArcherSoldier(Soldier):
    """Ranged, high damage, fragile."""

    NAME = "Archer"
    SPRITE_FOLDER = os.path.join(_SPRITES_DIR, "Archer")
    SPRITE_FRAMES = ac.ARCHER_SPRITE_FRAMES
    FRAME_SIZE = ac.FRAME_SIZE_ARCHER
    TARGET_HEIGHT_PX = 30

    BASE_HP = balance.ARCHER_HP
    DEFENSE = balance.ARCHER_DEFENSE
    SPEED = balance.ARCHER_SPEED
    ATTACK_DAMAGE = balance.ARCHER_ATTACK_DAMAGE
    ATTACK_RANGE = balance.ARCHER_ATTACK_RANGE
    ATTACK_COOLDOWN = balance.ARCHER_ATTACK_COOLDOWN
    IS_RANGED = True
    BODY_COLOR = (90, 200, 120)

    def _do_attack(self, target) -> None:
        """Override TẦM XA — bắn mũi tên BAY tới thay vì trúng ngay (khác `Soldier._do_attack`).

        Spawn 1 `Arrow` (projectile.py) tại vị trí Archer (lệch lên 18px, mô
        phỏng cung nằm ở tay), giao cho `WorldQuery` quản lý bay + va chạm —
        damage THẬT SỰ xảy ra khi mũi tên TỚI đích (trong `Arrow.update()`), KHÔNG
        phải ngay lúc gọi hàm này.

        Chỉ số: balance.ARCHER_ATTACK_DAMAGE, balance.ARROW_SPEED.
        """
        from systems.world_query import WorldQuery
        from characters.soldiers.projectile import Arrow
        self._animator.set_state("attack")
        arrow = Arrow(self.x, self.y - 18, target, self._damage,
                      shooter=self, headless=self._headless)
        WorldQuery.spawn_entity(arrow)


class LancerSoldier(Soldier):
    """Fast, medium defense, damage below the archer."""

    NAME = "Lancer"
    SPRITE_FOLDER = os.path.join(_SPRITES_DIR, "Lancer")
    SPRITE_FRAMES = ac.LANCER_SPRITE_FRAMES
    FRAME_SIZE = ac.FRAME_SIZE_LANCER
    TARGET_HEIGHT_PX = 44

    BASE_HP = balance.LANCER_HP
    DEFENSE = balance.LANCER_DEFENSE
    SPEED = balance.LANCER_SPEED
    ATTACK_DAMAGE = balance.LANCER_ATTACK_DAMAGE
    ATTACK_RANGE = balance.LANCER_ATTACK_RANGE
    ATTACK_COOLDOWN = balance.LANCER_ATTACK_COOLDOWN
    BODY_COLOR = (110, 150, 235)


class WarriorSoldier(Soldier):
    """Tanky, slow, low damage — TAUNTS to pull titan aggro."""

    NAME = "Warrior"
    SPRITE_FOLDER = os.path.join(_SPRITES_DIR, "Warrior")
    SPRITE_FRAMES = ac.WARRIOR_SOLDIER_SPRITE_FRAMES
    FRAME_SIZE = ac.FRAME_SIZE_WARRIOR_SOLDIER
    TARGET_HEIGHT_PX = 36

    BASE_HP = balance.WARRIOR_HP
    DEFENSE = balance.WARRIOR_DEFENSE
    SPEED = balance.WARRIOR_SPEED
    ATTACK_DAMAGE = balance.WARRIOR_ATTACK_DAMAGE
    ATTACK_RANGE = balance.WARRIOR_ATTACK_RANGE
    ATTACK_COOLDOWN = balance.WARRIOR_ATTACK_COOLDOWN
    TAUNTS = True
    BODY_COLOR = (210, 140, 80)


SOLDIER_TYPES: dict = {
    "Archer": ArcherSoldier,
    "Lancer": LancerSoldier,
    "Warrior": WarriorSoldier,
}
