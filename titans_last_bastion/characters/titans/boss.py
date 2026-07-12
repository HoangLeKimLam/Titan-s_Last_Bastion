# characters/titans/boss.py
"""Boss.py — Toàn bộ tham số + thân xác (sprite/animation) của Boss.

Trách nhiệm: như `titan.py` nhưng cho 3 boss — ColossalTitan (Boss màn 3),
BeastTitan (Boss màn 4), FoundingTitan (Final Boss).

Mỗi Boss khai báo class constants:
    _DEFAULT_HP / _DEFAULT_SPEED / _DEFAULT_DAMAGE / _DEFAULT_ATTACK_RANGE
    / _DEFAULT_ATTACK_COOLDOWN — như Titan thường.
+ Tham số kỹ năng riêng (cooldown, AoE, damage, animation duration):
    Colossal: _STEAM_COOLDOWN, _JUMP_COOLDOWN, _STEAM_PARTICLE_COUNT, ...
    Beast   : _ROCK_VELOCITY, _ROCK_AOE_RADIUS, ... (range/cooldown gộp về _DEFAULT_*)
    Founding: _SUMMON_WAVE_COOLDOWN, _SUMMON_TOTAL, _P1_HP_RATIO, ...

Tất cả tham số có thể override qua `config` dict truyền vào `__init__`,
hoặc sửa trực tiếp class const để áp dụng toàn dự án.

Lưu ý chuyển đổi (khác bản gốc của Long):
    - Bỏ BurnDecorator (patterns/decorator.py chưa có) — _steam_burst()
      chỉ áp damage trực tiếp, không gắn DoT decorator.
    - ENTITY_TYPE = 'titan' kế thừa từ Titan base (đã khai báo ở titan.py).
    - Dùng WorldQuery class method; entity_type dùng chuỗi hằng (khớp
      ENTITY_TYPE class constant của mỗi class entity trong hệ thống).
"""
import os
import math
import random
import pygame
from systems.sound_system import SoundManager


from characters.titans.titan import Titan
from characters.titans.ai import make_ai_for
from config import balance
from characters.titans.attackstrategy import (
    GroundSlamStrategy,
    HeavyStrikeStrategy,
    RockProjectile,
    HeatParticle,
)

# RockProjectile và HeatParticle vẫn ở attackstrategy.py (Projectile / Particle
# phụ trợ). Boss.py import lại để dùng trong skill animation.


# ═══════════════════════════════════════════════════════
#  COLOSSAL TITAN — Boss màn 3 (Steam Burst + Jump Stomp)
# ═══════════════════════════════════════════════════════

class ColossalTitan(Titan):
    """Boss màn 3 — to lớn, hai skill AoE: Steam Burst + Jump Stomp.

    Skill 1 — Steam Burst (`_steam_burst`):
        • Cooldown `_STEAM_COOLDOWN` giây
        • Vành khuyên annulus [`_STEAM_R_IN`, `_STEAM_R_OUT`] quanh Colossal
        • `_STEAM_PARTICLE_COUNT` particle chia đều quanh 360° + jitter
        • Mỗi particle: AoE `_STEAM_PARTICLE_AOE` tại spawn point
        • Lính: `_STEAM_FIRE_DMG` fire + pushback
        • Tướng: `_STEAM_BURN_DMG` damage dtype='burn'
        • Standing `_STEAM_ANIM_DUR` giây

    Skill 2 — Jump Stomp (`_jump_stomp`):
        • Cooldown `_JUMP_COOLDOWN` giây
        • AoE `_STOMP_AOE` quanh Colossal
        • Tháp: stun `_STOMP_STUN_DUR` giây
        • Lính / Tướng: `_STOMP_DMG` damage 'stomp'
        • Standing `_JUMP_ANIM_DUR` giây

    Đòn basic: GroundSlamStrategy — damage target chính + stun tower
    trong `radius=160`.

    Visual: `Assets/Boss/clossal.png` (chú ý spelling). Frame 64×64.
      Walk    : rows 8-11   — 9 frame
      Steam   : rows 23-26  — 2 frame (loop)
      Jump    : rows 26-29  — 5 frame (loop)
      Attack  : rows 12-15  — 6 frame (vung tay melee 0.25s)
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = balance.COLOSSAL_HP
    _DEFAULT_SPEED           = balance.COLOSSAL_SPEED     # to → đi chậm
    _DEFAULT_DAMAGE          = balance.COLOSSAL_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.COLOSSAL_ATTACK_RANGE    # GroundSlam có radius
    _DEFAULT_ATTACK_COOLDOWN = balance.COLOSSAL_ATTACK_COOLDOWN

    # ── Sprite mapping ───────────────────────────────────────────
    _STEAM_ROWS:  dict = {0: 26, 1: 23, 2: 24, 3: 25}
    _JUMP_ROWS:   dict = {0: 26, 1: 27, 2: 28, 3: 29}
    _WALK_ROWS:   dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _ATTACK_ROWS: dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _IDLE_ROWS:   dict = {0: 26, 1: 23, 2: 24, 3: 25}   # col 0 tĩnh
    _FRAME_SIZE    = 64
    _STEAM_FRAMES  = 2
    _STOMP_FRAMES  = 5
    _WALK_FRAMES   = 9
    _ATTACK_FRAMES = 6
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 24                  # nhanh — 0.25s/đòn vung tay

    # ── Skill 1: Steam Burst ─────────────────────────────────────
    _STEAM_AOE              = balance.COLOSSAL_STEAM_AOE        # tham chiếu HUD
    _STEAM_R_IN             = balance.COLOSSAL_STEAM_R_IN         # bán kính trong annulus
    _STEAM_R_OUT            = balance.COLOSSAL_STEAM_R_OUT        # bán kính ngoài annulus
    _STEAM_PARTICLE_COUNT   = balance.COLOSSAL_STEAM_PARTICLE_COUNT  # N particle chia đều quanh vòng
    _STEAM_PARTICLE_AOE     = balance.COLOSSAL_STEAM_PARTICLE_AOE  # bán kính damage tại mỗi spawn point
    _STEAM_FIRE_DMG         = balance.COLOSSAL_STEAM_FIRE_DMG   # damage lính khi bị steam
    _STEAM_BURN_DMG         = balance.COLOSSAL_STEAM_BURN_DMG   # damage tướng khi bị steam
    _STEAM_COOLDOWN         = balance.COLOSSAL_STEAM_COOLDOWN
    _STEAM_ANIM_DUR         = balance.COLOSSAL_STEAM_ANIM_DUR

    # ── Skill 2: Jump Stomp ──────────────────────────────────────
    _STOMP_AOE              = balance.COLOSSAL_STOMP_AOE
    _STOMP_STUN_DUR         = balance.COLOSSAL_STOMP_STUN_DUR
    _STOMP_DMG              = balance.COLOSSAL_STOMP_DMG
    _JUMP_COOLDOWN          = balance.COLOSSAL_JUMP_COOLDOWN
    _JUMP_ANIM_DUR          = balance.COLOSSAL_JUMP_ANIM_DUR

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo Colossal — boss màn 3, gắn sẵn GroundSlamStrategy + 2 skill timer.

        Ý tưởng: Colossal là "tháp canh biết đi" — chậm (SPEED 50), máu dày, và
        điều nguy hiểm nhất là nó VÔ HIỆU HOÁ THÁP: đòn thường đã stun tháp
        (GroundSlam), cộng thêm skill Jump Stomp stun mạnh hơn.

        Khởi tạo gì:
          - `_attack_strategy = GroundSlamStrategy(radius=160, stun_duration=3.0)`
            → đòn THƯỜNG cũng stun mọi tháp trong 160px.
          - 2 cặp timer/cooldown độc lập: `_steam_*` (Steam Burst) và `_jump_*`
            (Jump Stomp). Timer bắt đầu = 0.0 nghĩa là skill SẴN SÀNG NGAY frame
            đầu; AI có thể nạp lại cooldown sau nếu muốn trì hoãn.
          - `_heat_particles`: list hạt hơi nóng (thuần đồ hoạ).
          - `_world_x/_world_y`: vị trí world; cần vì `draw()` bị game loop trừ
            camera offset vào `self.x` (xem ghi chú bug ở BeastTitan).
          - Cụm cờ animation (`_is_steaming/_is_jumping/_is_attacking/_is_moving`)
            — chỉ 1 cờ được bật tại 1 thời điểm, `update()` xử lý theo thứ tự ưu tiên.

        Tham số:
            config: dict ghi đè stat (hp/speed/damage/...). None → dùng class const.

        Chỉ số: balance.COLOSSAL_* (HP/SPEED/DAMAGE/STEAM_*/STOMP_*/JUMP_*).
        Lưu ý: radius=160 và stun 3.0 truyền vào GroundSlam ở đây là số CỨNG,
        khác với `_STOMP_AOE`/`_STOMP_STUN_DUR` (dùng cho skill Jump Stomp).
        """
        super().__init__(x, y, config)
        self._attack_strategy = GroundSlamStrategy(
            radius=160, stun_duration=3.0)
        # Timer skill — bắt đầu = 0 (AI nạp sẵn cooldown sau).
        self._steam_timer    = 0.0
        self._steam_cooldown = self._STEAM_COOLDOWN
        self._jump_timer     = 0.0
        self._jump_cooldown  = self._JUMP_COOLDOWN

        # Particle system
        self._heat_particles: list = []
        self._world_x = x  # lưu vị trí world trước khi game loop offset
        self._world_y = y

        # Animation state
        self._direction         = 2
        self._is_steaming       = False
        self._steam_anim_timer  = 0.0
        self._is_jumping        = False
        self._jump_anim_timer   = 0.0
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._is_moving         = False
        self._anim_col          = 0
        self._anim_timer        = 0.0

        self._sprite_sheet = None

    # ── Sprite helpers ───────────────────────────────────────────

    def _load_sprite(self) -> None:
        """Nạp spritesheet `Assets/Boss/clossal.png` một lần (lazy load).

        Thuật toán: đã nạp (`_sprite_sheet is not None`) → thoát ngay, tránh đọc
        đĩa mỗi frame. Nạp LAZY (không nạp trong `__init__`) vì pygame cần có
        display trước khi `convert_alpha()` chạy được.

        Lỗi bất kỳ (thiếu file, chưa có display) → `_sprite_sheet = None`, game
        vẫn chạy, `draw()` sẽ vẽ hình thay thế. Không bao giờ crash vì thiếu ảnh.
        """
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Boss', 'clossal.png')
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt 1 ô (row, col) khỏi spritesheet → Surface mới có nền trong suốt.

        Thuật toán: sheet là lưới ô vuông `_FRAME_SIZE`×`_FRAME_SIZE` (64px).
        Ô cần lấy nằm ở pixel `(col*64, row*64)`. Tạo Surface rỗng cờ SRCALPHA
        (giữ được nền trong) rồi `blit` đúng vùng `region` vào.

        Quy ước row: hàng nào ứng với hướng/animation nào được khai ở các dict
        `_WALK_ROWS`, `_ATTACK_ROWS`, `_STEAM_ROWS`, `_JUMP_ROWS`.

        Trả về: pygame.Surface, hoặc None nếu chưa nạp được sheet.
        """
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    # ── Direction ────────────────────────────────────────────────

    def _compute_direction(self) -> int:
        """Xác định Colossal đang QUAY MẶT về hướng nào (0=N, 1=W, 2=S, 3=E).

        Thuật toán: lấy vector titan→target, rồi so `|dx|` với `|dy|`:
          - `|dx| >= |dy|` → lệch NGANG nhiều hơn → Đông (dx>=0) hoặc Tây.
          - ngược lại      → lệch DỌC nhiều hơn  → Nam (dy>=0) hoặc Bắc.
        Tức là chia mặt phẳng thành 4 góc phần tư chéo 45°.

        Không có target → giữ nguyên hướng cũ (`_direction`), tránh boss xoay
        loạn khi không có gì để đánh.

        Trả về: int 0-3, dùng để tra hàng sprite trong `_WALK_ROWS` v.v.
        """
        target = self._find_best_target()
        if target is None:
            return self._direction
        dx = target.x - self.x
        dy = target.y - self.y
        if abs(dx) >= abs(dy):
            return 3 if dx >= 0 else 1
        return 2 if dy >= 0 else 0

    # ── Update (chế độ manual — không có AI ngoài) ───────────────

    def update(self, dt: float) -> None:
        """Vòng update 1 frame của Colossal (chế độ MANUAL — khi không có AI ngoài).

        Thuật toán — máy trạng thái ưu tiên, ai bật trước thì "nuốt" cả frame:
          0. `dt_slowed = dt * _slow_factor` → mọi timer skill/animation bị ảnh
             hưởng bởi hiệu ứng LÀM CHẬM (IceTower). Nhưng particle hơi nóng dùng
             `dt` GỐC (hiệu ứng đồ hoạ không nên bị slow).
          1. Particle hơi nóng luôn cập nhật (kể cả đang làm việc khác); hạt nào
             `update()` trả False thì bị lọc khỏi list.
          2. `_is_steaming` → chỉ chạy animation phun hơi, đếm ngược
             `_steam_anim_timer`, rồi `return` (KHÔNG đi, KHÔNG đánh).
          3. `_is_attacking` → tương tự, chạy animation vung tay rồi `return`.
          4. `_is_jumping` → chạy animation nhảy rồi `return`.
             → 3 trạng thái trên loại trừ nhau và KHOÁ hành động khác.
          5. Rảnh → `super().update(dt)` (di chuyển + đánh thường của Titan base).
          6. Đếm ngược 2 timer skill; hết `_steam_timer` → `_steam_burst()`,
             hết `_jump_timer` → `_jump_stomp()`, rồi nạp lại cooldown.
          7. Nếu đang đi → chạy animation walk.

        Lưu ý: đây là AI "cây nhà lá vườn". Trong game THẬT, `ai.py`
        (`ColossalAI`) mới là bộ não; hàm này chủ yếu dùng cho demo/test.

        Chỉ số: balance.COLOSSAL_STEAM_COOLDOWN / _JUMP_COOLDOWN / _STEAM_ANIM_DUR.
        """
        dt_slowed = dt * self._slow_factor  # Apply slow to all timers
        # Particle hơi nóng luôn chạy.
        self._heat_particles = [
            p for p in self._heat_particles if p.update(dt)
        ]

        if self._is_steaming:
            self._steam_anim_timer -= dt_slowed
            self._anim_timer += dt_slowed
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % self._STEAM_FRAMES
            if self._steam_anim_timer <= 0:
                self._is_steaming = False
            return

        if self._is_attacking:
            self._attack_anim_timer -= dt_slowed
            self._anim_timer += dt_slowed
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES
            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
            return

        if self._is_jumping:
            self._jump_anim_timer -= dt_slowed
            self._anim_timer += dt_slowed
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % self._STOMP_FRAMES
            if self._jump_anim_timer <= 0:
                self._is_jumping = False
            return

        super().update(dt)

        self._steam_timer -= dt_slowed
        if self._steam_timer <= 0:
            self._steam_burst()
            self._steam_timer = self._steam_cooldown

        self._jump_timer -= dt_slowed
        if self._jump_timer <= 0:
            self._jump_stomp()
            self._jump_timer = self._jump_cooldown

        if self._is_moving:
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % self._WALK_FRAMES

    # ── Skill 1: Steam Burst ─────────────────────────────────────

    def _steam_burst(self) -> None:
        """SKILL 1 — phun hơi nóng theo VÀNH KHUYÊN (annulus) quanh Colossal.

        Hình học (mấu chốt): KHÔNG phải hình tròn đặc mà là VÀNH KHUYÊN —
        vùng giữa bán kính trong `_STEAM_R_IN` (40) và ngoài `_STEAM_R_OUT` (140).
        Nghĩa là ĐỨNG SÁT NÁCH Colossal (<40px) thì AN TOÀN, đứng vòng ngoài mới
        chết cháy. Đây là điểm gameplay quan trọng: người chơi né bằng cách áp sát.

        Thuật toán rải hạt:
          1. Chia đều 360° thành `N = _STEAM_PARTICLE_COUNT` (200) lát:
             `slice_angle = 2π/N`.
          2. Mỗi hạt i: `angle = i*slice_angle + jitter` với jitter ngẫu nhiên
             trong ±nửa lát → phủ đều nhưng không thẳng hàng như răng lược.
          3. `radius = random(_STEAM_R_IN, _STEAM_R_OUT)` → hạt nằm trong vành.
          4. Vị trí hạt = tâm + (cos·r, sin·r). Lưu `_rel_x/_rel_y` (offset TƯƠNG
             ĐỐI so với titan) và ép `vx=vy=0` → hạt ĐỨNG YÊN theo boss, không
             bay toả ra.

        Thuật toán damage (chạy CÙNG vòng lặp trên):
          5. Mỗi hạt quét `find_in_radius(_STEAM_PARTICLE_AOE = 50px)` quanh nó.
          6. DEDUPE bằng 2 set `damaged_soldiers` / `damaged_commanders`: 1 nạn
             nhân chỉ ăn damage ĐÚNG 1 LẦN, dù bị hàng chục hạt phủ chồng lên.
             Không có bước này thì lính đứng giữa vành sẽ ăn 200 lần damage → chết tức thì.
          7. Lính ăn `_STEAM_FIRE_DMG` (dtype='fire'); tướng ăn `_STEAM_BURN_DMG`
             (dtype='burn') — tướng ăn NẶNG hơn lính.
          8. Bật cờ `_is_steaming` + `_steam_anim_timer` → khoá boss trong lúc phun.

        Lưu ý: BurnDecorator đã bỏ — chỉ damage tức thời, KHÔNG có DoT cháy dai.

        Liên kết: `HeatParticle` (attackstrategy.py) chỉ là đồ hoạ, không gây damage;
        damage do CHÍNH hàm này tính.
        Chỉ số: balance.COLOSSAL_STEAM_R_IN/_R_OUT/_PARTICLE_COUNT/_PARTICLE_AOE/
        _FIRE_DMG/_BURN_DMG/_ANIM_DUR.
        """
        SoundManager.get_instance().play('clossal_steam', self.x, self.y)
        from systems.world_query import WorldQuery

        N = self._STEAM_PARTICLE_COUNT
        slice_angle = 2 * math.pi / N
        max_jitter  = slice_angle * 0.5
        aoe_r       = self._STEAM_PARTICLE_AOE

        damaged_soldiers   = set()
        damaged_commanders = set()

        spawn_x, spawn_y = self.x, self.y  # world position at spawn time
        for i in range(N):
            angle  = i * slice_angle + random.uniform(-max_jitter, max_jitter)
            radius = random.uniform(self._STEAM_R_IN, self._STEAM_R_OUT)
            # Relative offsets from spawn point
            rel_x = math.cos(angle) * radius
            rel_y = math.sin(angle) * radius

            p = HeatParticle(spawn_x + rel_x, spawn_y + rel_y)
            p.vx = 0.0  # steam particles stay in place, don't expand outward
            p.vy = 0.0
            p._rel_x = rel_x  # store relative offset so particles stay relative to titan
            p._rel_y = rel_y
            self._heat_particles.append(p)

            p_abs_x = spawn_x + rel_x
            p_abs_y = spawn_y + rel_y

            soldiers = WorldQuery.find_in_radius(
                cx=p_abs_x, cy=p_abs_y, radius=aoe_r, entity_type='soldier')
            for s in soldiers:
                if s in damaged_soldiers:
                    continue
                damaged_soldiers.add(s)
                s.take_damage(amount=self._STEAM_FIRE_DMG, dtype='fire')
                s.take_damage(amount=0, dtype='pushback')

            commanders = WorldQuery.find_in_radius(
                cx=p_abs_x, cy=p_abs_y, radius=aoe_r, entity_type='commander')
            for c in commanders:
                if c in damaged_commanders:
                    continue
                damaged_commanders.add(c)
                c.take_damage(amount=self._STEAM_BURN_DMG, dtype='burn')

        self._is_steaming      = True
        self._steam_anim_timer = self._STEAM_ANIM_DUR
        self._anim_col         = 0

    # ── Skill 2: Jump Stomp ──────────────────────────────────────

    def _jump_stomp(self) -> None:
        """SKILL 2 — nhảy tại chỗ rồi giậm đất: STUN tháp + damage lính/tướng.

        Khác Steam Burst ở 3 điểm cốt lõi:
          - Hình dạng: hình TRÒN ĐẶC bán kính `_STOMP_AOE` (160px) — KHÔNG có
            "vùng an toàn ở giữa". Áp sát boss KHÔNG cứu được bạn khỏi đòn này.
          - Đối tượng: trúng cả THÁP (bị choáng), lính và tướng.
          - Damage: lính và tướng ăn CÙNG `_STOMP_DMG` (300), không phân biệt.

        Thuật toán — 3 lần quét vùng độc lập quanh CHÍNH BOSS:
          1. 'tower'     → `t.stun(_STOMP_STUN_DUR)` (3.5s). Tháp KHÔNG ăn damage,
             chỉ ngừng bắn. (Nếu tháp có item anti_stun → `stun()` no-op, miễn nhiễm.)
          2. 'soldier'   → `take_damage(_STOMP_DMG, 'stomp')`.
          3. 'commander' → `take_damage(_STOMP_DMG, 'stomp')`.
          4. Bật `_is_jumping` + `_jump_anim_timer` → khoá boss trong lúc nhảy.

        KHÔNG dedupe như Steam Burst vì mỗi loại chỉ quét ĐÚNG 1 LẦN (không có
        200 hạt chồng lên nhau) → không thể trúng 2 lần.

        Liên kết: `Tower.stun()` (towers/tower.py) — đây là 1 trong 2 nguồn stun
        tháp (nguồn kia là đá của Beast).
        Chỉ số: balance.COLOSSAL_STOMP_AOE / _STOMP_STUN_DUR / _STOMP_DMG /
        _JUMP_COOLDOWN / _JUMP_ANIM_DUR.
        """
        from systems.world_query import WorldQuery

        towers = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self._STOMP_AOE, entity_type='tower')
        for t in towers:
            t.stun(self._STOMP_STUN_DUR)

        soldiers = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self._STOMP_AOE, entity_type='soldier')
        for s in soldiers:
            s.take_damage(amount=self._STOMP_DMG, dtype='stomp')

        commanders = WorldQuery.find_in_radius(
            cx=self.x, cy=self.y,
            radius=self._STOMP_AOE, entity_type='commander')
        for c in commanders:
            c.take_damage(amount=self._STOMP_DMG, dtype='stomp')

        self._is_jumping      = True
        self._jump_anim_timer = self._JUMP_ANIM_DUR
        self._anim_col        = 0

    # ── Attack animation (melee vung tay) ────────────────────────

    def trigger_attack(self, target=None) -> bool:
        """Kích hoạt animation vung tay melee — 0.25s.

        Vì sao Colossal có trigger_attack?
            Khi AI gọi đòn basic (GroundSlamStrategy) ở khoảng cách gần,
            người chơi cần thấy visual vung tay. Animation chỉ kéo dài 0.25s,
            KHÔNG chặn cooldown skill Steam/Stomp.
        """
        if self._is_attacking or self._is_steaming or self._is_jumping:
            return False
        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0
        if target is not None:
            dx = target.x - self.x
            dy = target.y - self.y
            if abs(dx) > abs(dy):
                self._direction = 3 if dx > 0 else 1
            else:
                self._direction = 2 if dy > 0 else 0
        return True

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ Colossal: chọn frame theo trạng thái → scale 2.5× → vẽ particle đè lên.

        Thuật toán:
          1. `_load_sprite()` (lazy, chỉ nạp lần đầu).
          2. Chọn HÀNG sprite theo cờ trạng thái, ưu tiên GIỐNG HỆT `update()`:
             steaming > jumping > attacking > moving > idle. Hướng lấy từ
             `_direction`, cột lấy từ `_anim_col`.
          3. Frame 64×64 được scale lên 160×160 (2.5×) và căn TÂM tại (x, y) —
             tức là (x,y) là TÂM boss, không phải góc trên-trái.
          4. Không có sprite → `super().draw()` (hình khối thay thế).
          5. Particle hơi nóng vẽ ĐÈ LÊN sprite. Mẹo quan trọng: particle lưu
             offset TƯƠNG ĐỐI (`_rel_x/_rel_y`), nên khi vẽ phải tạm gán
             `p.x = self.x + _rel_x`, vẽ xong TRẢ LẠI toạ độ world cũ. Nhờ vậy
             vành hơi nóng luôn bám quanh boss dù boss di chuyển/camera cuộn.
          6. Đang nhảy → vẽ thêm vòng tròn đỏ debug = đúng vùng `_STOMP_AOE`.

        CHỈ ĐỒ HOẠ — không đổi bất kỳ trạng thái logic nào (trừ việc mượn-rồi-trả
        p.x/p.y). Không gọi update() từ đây.
        """
        self._load_sprite()

        if self._is_steaming:
            frame = self._get_frame(self._STEAM_ROWS[self._direction], self._anim_col)
        elif self._is_jumping:
            frame = self._get_frame(self._JUMP_ROWS[self._direction], self._anim_col)
        elif self._is_attacking:
            frame = self._get_frame(self._ATTACK_ROWS[self._direction], self._anim_col)
        elif self._is_moving:
            frame = self._get_frame(self._WALK_ROWS[self._direction], self._anim_col)
        else:
            frame = self._get_frame(self._IDLE_ROWS[self._direction], 0)

        if frame is not None:
            ox = int(self.x - self._FRAME_SIZE // 2)
            oy = int(self.y - self._FRAME_SIZE // 2)
            scaled = pygame.transform.scale(frame, (160, 160))  # 2.5x scale
            rect = scaled.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(scaled, rect)
        else:
            super().draw(screen)

        # Vẽ particles hơi nóng lên trên sprite
        # Particles được spawn relative to titan, nên luôn ở vị trí: self.x + _rel_x
        for p in self._heat_particles:
            old_x, old_y = p.x, p.y
            # Render at titan's screen position + relative offset
            p.x = self.x + getattr(p, '_rel_x', 0.0)
            p.y = self.y + getattr(p, '_rel_y', 0.0)
            p.draw(screen)
            p.x, p.y = old_x, old_y  # restore world coords

        # DEBUG: vẽ vùng tác động Jump Stomp
        if self._is_jumping:
            pygame.draw.circle(screen, (255, 100, 100), (int(self.x), int(self.y)),
                             int(self._STOMP_AOE), 2)


# ═══════════════════════════════════════════════════════
#  BEAST TITAN — Boss màn 4 (Rock Throw + parabol AoE)
# ═══════════════════════════════════════════════════════

class BeastTitan(Titan):
    """Boss màn 4 — ném đá tầm xa, ưu tiên phá tháp trước khi tiến vào HQ.

    Skill ném đá (`trigger_attack(target)`):
      • Range: `_DEFAULT_ATTACK_RANGE` (ngoài tầm → walk lại gần)
      • Vật lý: velocity adaptive, angle `_ROCK_ANGLE_DEG`, gravity `_ROCK_GRAVITY`
      • Visual đá: spritesheet Rock Pile (frame 85×85 tại row=9, col=5)
      • Tay phát sinh: `_HAND_OFFSET` + `_HAND_LIFT` px
      • Release tại frame `_ROCK_RELEASE_FRAME`/6 (~0.125s)
      • Damage AoE `_ROCK_AOE_RADIUS` px khi rock land: main + splash, dtype='rock'
      • Cooldown `_DEFAULT_ATTACK_COOLDOWN` giây

    Adaptive velocity (`_release_rock`): tính v theo công thức parabol
    `v = sqrt(R · g / sin(2θ))` để đáp đúng target, clamp [`_ROCK_VELOCITY_MIN`,
    `_ROCK_VELOCITY_MAX`].

    Visual: `Assets/Boss/beast.png` (frame 64×64).
      Walk/Run/Attack — layout chuẩn rows 8-11 / 38-41 / 12-15.
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = balance.BEAST_HP
    _DEFAULT_SPEED           = balance.BEAST_SPEED
    _DEFAULT_DAMAGE          = balance.BEAST_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.BEAST_ATTACK_RANGE    # tầm ném đá (px)
    _DEFAULT_ATTACK_COOLDOWN = balance.BEAST_ATTACK_COOLDOWN

    # ── Sprite layout ────────────────────────────────────────────
    _SPRITE_FILE   = 'beast.png'
    _FRAME_SIZE    = 64
    _WALK_ROWS:    dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS:     dict = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS:  dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _ATTACK_FRAMES = 6
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 24

    # ── Skill ném đá ─────────────────────────────────────────────
    _ROCK_VELOCITY        = balance.BEAST_ROCK_VELOCITY    # fallback nếu công thức adaptive fail
    _ROCK_VELOCITY_MIN    = balance.BEAST_ROCK_VELOCITY_MIN
    _ROCK_VELOCITY_MAX    = balance.BEAST_ROCK_VELOCITY_MAX
    _ROCK_ANGLE_DEG       = balance.BEAST_ROCK_ANGLE_DEG
    _ROCK_GRAVITY         = balance.BEAST_ROCK_GRAVITY
    _ROCK_DAMAGE          = balance.BEAST_ROCK_DAMAGE      # MỌI mục tiêu trong AoE ăn cùng lượng này
    _ROCK_TOWER_STUN      = balance.BEAST_ROCK_TOWER_STUN      # đá trúng tháp → choáng 5s
    _ROCK_AOE_RADIUS      = balance.BEAST_ROCK_AOE_RADIUS
    _DEFAULT_PUSHBACK_SOLDIER   = balance.BEAST_PUSHBACK_SOLDIER
    _DEFAULT_PUSHBACK_COMMANDER = balance.BEAST_PUSHBACK_COMMANDER
    _ROCK_RELEASE_FRAME   = 3
    _HAND_OFFSET          = 24.0
    _HAND_LIFT            = 12.0

    # ── Rock sprite — sheet Rock Pile (510×2550) ─────────────────
    _ROCK_SHEET_FILE   = os.path.join('Assets', 'Rock', 'Rock Pile - Spritesheet.png')
    _ROCK_FRAME_SIZE   = 85
    _ROCK_FRAME_COL    = 5
    _ROCK_FRAME_ROW    = 9

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo Beast — boss màn 4, pháo binh tầm xa chuyên diệt tháp.

        Ý tưởng: Beast KHÔNG cận chiến. Nó đứng ngoài tầm bắn của tháp
        (ATTACK_RANGE 350px) và ném đá parabol vào tháp. Kết hợp `BeastPriority`
        (chủ động săn tháp) → nó gặm sạch phòng thủ trước khi tiến vào.

        Khởi tạo gì:
          - `THROW_RANGE`: ALIAS PUBLIC của `_attack_range`. Tồn tại vì `ai.py`
            và các file CHECK/ đọc `beast.THROW_RANGE`. Sửa `_attack_range` mà
            quên alias này → AI dùng tầm ném CŨ.
          - `_throw_timer` / `_throw_cooldown`: nhịp ném (lấy từ `_attack_cooldown`).
          - `_rocks`: list `RockProjectile` ĐANG BAY. Beast tự quản lý đá của
            mình (update + draw), không giao cho WorldQuery.
          - `_rock_released_this_attack`: cờ CHỐNG NÉM 2 LẦN trong 1 animation
            (xem `update_anim`).
          - `_attack_target`: nhớ mục tiêu lúc BẮT ĐẦU vung tay, vì đá chỉ thả ra
            ở giữa animation.
          - `_world_x/_world_y`: toạ độ world, cần cho `draw()` suy ra camera
            offset (xem ghi chú sửa lỗi trong `update_anim`).

        Chỉ số: balance.BEAST_HP/_SPEED/_DAMAGE/_ATTACK_RANGE/_ATTACK_COOLDOWN,
        balance.BEAST_ROCK_* (vận tốc/góc/trọng lực/damage/AoE/stun tháp).
        """
        super().__init__(x, y, config)
        # Alias public — AI.py + CHECK/CHECKAI đọc `beast.THROW_RANGE`.
        self.THROW_RANGE     = self._attack_range
        self._throw_timer    = 0.0
        self._throw_cooldown = self._attack_cooldown

        self._direction         = 2
        self._is_moving         = False
        self._is_running        = False
        self._is_attacking      = False
        self._attack_anim_timer = 0.0
        self._anim_col          = 0
        self._anim_timer        = 0.0

        self._rock_released_this_attack = False
        self._attack_target             = None

        self._sprite_sheet = None
        self._rock_frame   = None

        self._rocks: list = []
        self._world_x = x  # lưu vị trí world trước khi game loop offset
        self._world_y = y

    # ── Sprite helpers ───────────────────────────────────────────

    def _load_sprite(self) -> None:
        """Nạp lazy 2 ảnh: spritesheet Beast VÀ 1 frame viên đá.

        Thuật toán:
          1. Sheet Beast: `Assets/Boss/beast.png` → `_sprite_sheet`.
          2. Viên đá: mở sheet `Rock Pile - Spritesheet.png` (510×2550, ô 85px),
             CẮT ĐÚNG 1 Ô tại `(_ROCK_FRAME_COL=5, _ROCK_FRAME_ROW=9)` → giữ làm
             `_rock_frame` dùng lại cho MỌI viên đá. Chỉ cần 1 hình tĩnh vì đá
             được XOAY lúc vẽ (`_rot_angle`), không cần animation nhiều frame.
          3. Mỗi ảnh có try/except riêng → thiếu 1 cái không làm hỏng cái kia;
             thất bại → None, `draw()` tự fallback (vẽ vòng tròn xám).

        Lazy vì `convert_alpha()` đòi hỏi pygame display đã tồn tại.
        """
        if self._sprite_sheet is None:
            try:
                path = os.path.join(
                    os.path.dirname(__file__),
                    'Assets', 'Boss', self._SPRITE_FILE)
                self._sprite_sheet = pygame.image.load(path).convert_alpha()
            except Exception:
                self._sprite_sheet = None
        if self._rock_frame is None:
            try:
                path = os.path.join(
                    os.path.dirname(__file__),
                    self._ROCK_SHEET_FILE)
                sheet = pygame.image.load(path).convert_alpha()
                fs = self._ROCK_FRAME_SIZE
                region = pygame.Rect(
                    self._ROCK_FRAME_COL * fs,
                    self._ROCK_FRAME_ROW * fs,
                    fs, fs)
                self._rock_frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
                self._rock_frame.blit(sheet, (0, 0), region)
            except Exception:
                self._rock_frame = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt ô (row, col) khỏi spritesheet Beast → Surface nền trong suốt.

        Giống hệt `ColossalTitan._get_frame`: sheet là lưới ô `_FRAME_SIZE` (64px),
        ô cần lấy ở pixel `(col*64, row*64)`; dùng SRCALPHA để giữ nền trong.
        Trả về None nếu chưa nạp được sheet.
        """
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    # ── Public API cho demo/AI ───────────────────────────────────

    def trigger_attack(self, target) -> bool:
        """BẮT ĐẦU animation vung tay ném đá (đá CHƯA bay ra ở đây).

        Điểm cốt lõi — ném đá tách làm 2 pha:
          - Pha 1 (hàm này): bật cờ `_is_attacking`, NHỚ `_attack_target`, reset
            `_rock_released_this_attack = False`. Chưa tạo viên đá nào.
          - Pha 2 (`update_anim`): khi animation chạy tới frame
            `_ROCK_RELEASE_FRAME` (=3) mới thực sự sinh `RockProjectile`.
          Nhờ tách 2 pha, đá bay ra ĐÚNG LÚC tay boss vung tới — không phải lúc
          vừa bấm đánh.

        Thuật toán:
          1. Đang đánh dở (`_is_attacking`) → trả False (không chồng đòn).
          2. Target None/đã chết → trả False.
          3. Đặt `_attack_anim_timer = _ATTACK_FRAMES / _ATTACK_FPS` (=6/24=0.25s).
          4. Xoay mặt về target: so `|dx|` vs `|dy|` → chọn 1 trong 4 hướng.

        Tham số: target — entity sẽ bị nhắm (thường là Tower, do BeastPriority chọn).
        Trả về: bool — True = bắt đầu đánh; False = từ chối.
        Liên kết: gọi bởi `ai.py` (BeastAI) hoặc `update()` nội bộ.
        """
        if self._is_attacking:
            return False
        if target is None or not getattr(target, 'is_alive', True):
            return False

        self._is_attacking              = True
        self._attack_anim_timer         = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col                  = 0
        self._anim_timer                = 0.0
        self._rock_released_this_attack = False
        self._attack_target             = target

        dx = target.x - self.x
        dy = target.y - self.y
        if abs(dx) > abs(dy):
            self._direction = 3 if dx > 0 else 1
        else:
            self._direction = 2 if dy > 0 else 0
        return True

    def update_anim(self, dt: float) -> None:
        """Cập nhật animation + bay đá + THẢ ĐÁ đúng frame. AI gọi hàm này thay `update()`.

        Vì sao tách khỏi `update()`: trong game thật, bộ não là `BeastAI` (ai.py) —
        nó tự lo di chuyển/chọn mục tiêu, chỉ cần Beast lo phần THÂN XÁC
        (animation + đá). Gọi nhầm `update()` sẽ chạy CẢ AI nội bộ → 2 AI đánh nhau.

        Thuật toán:
          1. LÀM TƯƠI `_world_x/_world_y = self.x, self.y`.
             (SỬA LỖI: trước đây chỉ gán 1 lần trong `__init__` = vị trí SPAWN, nên
             `draw()` suy ra camera offset SAI đúng bằng quãng đường Beast đã đi
             → đá vẽ lệch dần. Vật lý/damage vẫn đúng, chỉ hình sai. Phải làm tươi
             ở pha UPDATE vì lúc này `self.x` còn là toạ độ WORLD; đến `draw()` thì
             game loop đã trừ camera offset vào rồi.)
          2. Cập nhật mọi viên đá đang bay; lọc bỏ viên đã nổ (`alive == False`).
             Lưu ý đá dùng `dt` GỐC (không bị slow) — vật lý đạn đạo không nên bị
             hiệu ứng làm chậm titan ảnh hưởng.
          3. Đang đánh (`_is_attacking`):
             - Chạy animation vung tay theo `_ATTACK_FPS`.
             - **THẢ ĐÁ**: khi `_anim_col >= _ROCK_RELEASE_FRAME` (3) VÀ chưa thả
               (`not _rock_released_this_attack`) → `_release_rock()` rồi bật cờ.
               Cờ này là thứ CHẶN NÉM NHIỀU VIÊN trong 1 lần vung tay.
             - Hết `_attack_anim_timer` → tắt cờ đánh, reset cột.
          4. Đang đi → chạy animation walk/run (`_RUN_FRAMES` nếu `_is_running`).
          5. Đứng yên → reset về frame 0.

        Chỉ số: balance.BEAST_ATTACK_COOLDOWN; `_ROCK_RELEASE_FRAME` là số animation
        (giữ trong file này, không nằm ở balance.py).
        """
        # SỬA LỖI ĐỒ HỌA: `_world_x/_world_y` trước đây chỉ được gán MỘT LẦN
        # trong __init__ (vị trí spawn) rồi không bao giờ cập nhật. draw() lại
        # dùng `_world_x - self.x` để suy ra offset camera → offset sai đúng
        # bằng quãng đường Beast đã đi từ điểm spawn, khiến đá vẽ lệch dần
        # (vật lý/damage vẫn đúng, chỉ hình bị lệch). Ở đây (pha update) `self.x`
        # vẫn là toạ độ WORLD — game loop chỉ offset sang toạ độ màn hình ngay
        # trước khi gọi draw() — nên làm tươi tại đây là đúng chỗ.
        self._world_x, self._world_y = self.x, self.y

        dt_slowed = dt * self._slow_factor  # Apply slow to all timers
        for r in self._rocks:
            r.update(dt)
        self._rocks = [r for r in self._rocks if r.alive]

        if self._is_attacking:
            self._attack_anim_timer -= dt_slowed
            self._anim_timer += dt_slowed
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES

            if (not self._rock_released_this_attack
                    and self._anim_col >= self._ROCK_RELEASE_FRAME):
                self._release_rock()
                self._rock_released_this_attack = True

            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
                self._anim_timer   = 0.0
        elif self._is_moving:
            frames = self._RUN_FRAMES if self._is_running else self._WALK_FRAMES
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % frames
        else:
            self._anim_col   = 0
            self._anim_timer = 0.0

    def _release_rock(self) -> None:
        """Sinh 1 `RockProjectile` từ TAY Beast, tự tính vận tốc để rơi TRÚNG target.

        Bước 1 — tìm điểm thả (tay boss), không phải tâm boss:
            Đi từ tâm boss về phía target `_HAND_OFFSET` (24px), rồi nhấc lên
            `_HAND_LIFT` (12px). Nhờ vậy đá bay ra từ tay chứ không "chui từ bụng".

        Bước 2 — VẬN TỐC THÍCH ỨNG (điểm hay nhất của hàm):
            Bài toán ném xiên: tầm xa `R = v²·sin(2θ)/g`.
            Đảo ngược để tìm v cần thiết cho đúng tầm R hiện tại:
                `v = sqrt(R · g / sin(2θ))`
            với θ = `_ROCK_ANGLE_DEG` (15°) cố định, g = `_ROCK_GRAVITY`.
            → Target gần thì ném nhẹ, target xa thì ném mạnh, LUÔN rơi trúng chỗ.
            Kẹp v trong [`_ROCK_VELOCITY_MIN`, `_ROCK_VELOCITY_MAX`].
            `sin(2θ) <= 0` hoặc R = 0 (chia 0) → dùng `_ROCK_VELOCITY` fallback.

        BOM HẸN GIỜ (đã biết): v bị kẹp trần 800 → tầm ném tối đa thực tế
            `R = v²·sin(2θ)/g = 533px`. Hiện `_DEFAULT_ATTACK_RANGE = 350` nên chưa
            lộ. Ai tăng tầm ném > 533 thì MỌI viên đá sẽ âm thầm rơi NGẮN.

        Bước 3 — truyền toàn bộ thông số damage/AoE/stun/pushback cho viên đá, kèm
            `beast_x/beast_y` để lúc nổ biết hướng "ra xa Beast" mà đẩy lùi.

        Hạn chế đã biết: nhắm vị trí target TẠI LÚC THẢ, KHÔNG dẫn trước → mục tiêu
        đang chạy có thể ra khỏi AoE.

        Chỉ số: balance.BEAST_ROCK_ANGLE_DEG / _GRAVITY / _VELOCITY_MIN / _MAX /
        _DAMAGE / _AOE_RADIUS / _TOWER_STUN, balance.BEAST_PUSHBACK_*.
        """
        target = self._attack_target
        if target is None:
            return
        dx = target.x - self.x
        dy = target.y - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0:
            hx = self.x + (dx / dist) * self._HAND_OFFSET
            hy = self.y + (dy / dist) * self._HAND_OFFSET
        else:
            hx, hy = self.x, self.y
        hy -= self._HAND_LIFT

        rdx = target.x - hx
        rdy = target.y - hy
        range_px = (rdx * rdx + rdy * rdy) ** 0.5

        angle_rad = math.radians(self._ROCK_ANGLE_DEG)
        sin_2theta = math.sin(2 * angle_rad)
        if sin_2theta > 0 and range_px > 0:
            v = math.sqrt(range_px * self._ROCK_GRAVITY / sin_2theta)
            velocity = max(self._ROCK_VELOCITY_MIN,
                           min(self._ROCK_VELOCITY_MAX, v))
        else:
            velocity = self._ROCK_VELOCITY

        rock = RockProjectile(
            start_x=hx, start_y=hy, target=target,
            velocity=velocity,
            angle_deg=self._ROCK_ANGLE_DEG,
            gravity=self._ROCK_GRAVITY,
            damage=self._ROCK_DAMAGE,
            aoe_radius=self._ROCK_AOE_RADIUS,
            pushback_soldier=self._DEFAULT_PUSHBACK_SOLDIER,
            pushback_commander=self._DEFAULT_PUSHBACK_COMMANDER,
            tower_stun_duration=self._ROCK_TOWER_STUN,
            beast_x=self.x,
            beast_y=self.y,
        )
        self._rocks.append(rock)

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ Beast + mọi viên đá đang bay (có bù camera offset thủ công).

        Thuật toán:
          1. Chọn hàng sprite: attacking > running > walking > (mặc định walk).
             Cột = `_anim_col` nếu đang đi/đánh, ngược lại 0 (đứng yên).
          2. Frame 64×64 scale lên 160×160 (2.5×), căn TÂM tại (x, y).
          3. **Bù camera cho đá** — chỗ tinh tế nhất:
             Game loop đã trừ camera offset vào `self.x` TRƯỚC khi gọi `draw()`,
             nên `self.x` giờ là toạ độ MÀN HÌNH. Nhưng `r.x` của đá vẫn là toạ độ
             WORLD. Suy ngược offset:
                 `cam_offset = _world_x - self.x`   (world - screen)
             rồi tạm dời đá `r.x -= cam_offset` để vẽ, xong TRẢ LẠI toạ độ world.
             Phải trả lại, nếu không vật lý đá sẽ bị dịch mỗi frame.
             (Đây chính là chỗ từng lỗi: `_world_x` không được làm tươi → offset sai.)

        CHỈ ĐỒ HOẠ — không đổi trạng thái logic (đá được mượn-rồi-trả nguyên vẹn).
        """
        self._load_sprite()

        if self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_moving and self._is_running:
            row = self._RUN_ROWS[self._direction]
        elif self._is_moving:
            row = self._WALK_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (self._is_moving or self._is_attacking) else 0
        frame = self._get_frame(row, col)
        if frame is not None:
            scaled = pygame.transform.scale(frame, (160, 160))  # 2.5x scale
            rect = scaled.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(scaled, rect)

        # Camera offset được áp dụng trước draw(): self.x/y != self._world_x/y
        # Rocks cần được offset tương tự
        cam_offset_x = self._world_x - self.x
        cam_offset_y = self._world_y - self.y
        for r in self._rocks:
            old_x, old_y = r.x, r.y
            r.x = old_x - cam_offset_x
            r.y = old_y - cam_offset_y
            r.draw(screen, self._rock_frame)
            r.x, r.y = old_x, old_y  # restore world coords

    # ── Update tự hành (chế độ manual) ───────────────────────────

    def update(self, dt: float) -> None:
        """AI NỘI BỘ của Beast (chế độ manual/demo) — săn tháp, giữ khoảng cách.

        CẢNH BÁO: trong game THẬT, `ai.py` (BeastAI) là bộ não; nó gọi
        `update_anim()` chứ KHÔNG gọi hàm này. Gọi cả 2 → 2 AI tranh nhau điều
        khiển, Beast sẽ giật/đi lung tung.

        Thuật toán:
          1. `update_anim(dt)` — luôn chạy (animation + đá bay + thả đá).
          2. Chết → thoát.
          3. Đang vung tay (`_is_attacking`) → đứng im, KHÔNG ra quyết định mới
             (không huỷ đòn giữa chừng).
          4. Đếm ngược `_throw_timer`.
          5. `_find_nearest_tower()`. Không có tháp nào → đứng yên (Beast này chỉ
             biết săn tháp; việc đi phá tường/HQ do AI thật lo).
          6. Trong tầm (`dist <= _attack_range` = 350px) → ĐỨNG YÊN và ném khi hết
             cooldown. Đây là hành vi "pháo binh": không xông vào, chỉ đứng bắn.
          7. Ngoài tầm → xoay mặt + `_move_toward()` đi lại gần.

        Chỉ số: balance.BEAST_ATTACK_RANGE (tầm ném), balance.BEAST_ATTACK_COOLDOWN
        (nhịp ném), balance.BEAST_SPEED.
        """
        self.update_anim(dt)
        if not self.is_alive:
            return
        if self._is_attacking:
            self._is_moving = False
            return

        self._throw_timer -= dt
        nearest_tower = self._find_nearest_tower()
        if nearest_tower is None:
            self._is_moving = False
            return

        dist = self._distance_to(nearest_tower)
        if dist <= self._attack_range:
            self._is_moving = False
            if self._throw_timer <= 0:
                if self.trigger_attack(nearest_tower):
                    self._throw_timer = self._throw_cooldown
        else:
            self._is_moving = True
            dx = nearest_tower.x - self.x
            dy = nearest_tower.y - self.y
            if abs(dx) > abs(dy):
                self._direction = 3 if dx > 0 else 1
            else:
                self._direction = 2 if dy > 0 else 0
            self._move_toward(nearest_tower, dt)

    def _rock_volley(self, tower):
        """ALIAS TƯƠNG THÍCH NGƯỢC — chỉ gọi thẳng `trigger_attack(tower)`.

        Tồn tại vì code/test cũ (thư mục CHECK/, CHECKAI/) còn gọi tên `_rock_volley`.
        Không có logic riêng. Code MỚI nên gọi thẳng `trigger_attack()`.
        Nếu chắc chắn không còn ai gọi → có thể xoá an toàn.
        """
        self.trigger_attack(tower)

    def _find_nearest_tower(self):
        """Tìm THÁP gần Beast nhất trên toàn bản đồ (không giới hạn tầm/vùng).

        Uỷ quyền cho `WorldQuery.find_nearest(entity_type='tower')`.
        Import lazy để tránh vòng lặp import (systems → characters).

        LƯU Ý: hàm này KHÔNG lọc vùng (zone) và KHÔNG giới hạn tầm nhìn — nó quét
        toàn bản đồ. Nó chỉ phục vụ AI NỘI BỘ (demo). AI thật dùng `BeastPriority`
        (priority.py) có lọc `visible_towers` + cùng vùng, chặt chẽ hơn nhiều.

        Trả về: entity Tower gần nhất, hoặc None nếu bản đồ không còn tháp.
        """
        from systems.world_query import WorldQuery
        return WorldQuery.find_nearest(
            cx=self.x, cy=self.y, entity_type='tower')


# ═══════════════════════════════════════════════════════
#  FOUNDING TITAN — Final Boss (3 Phase + Auto Summon)
# ═══════════════════════════════════════════════════════

class FoundingTitan(Titan):
    """Final Boss màn 5 — 3 phase HP-based, sticky summon-lock.

    Phase logic (`_check_phase`):
      • HP > `_P1_HP_RATIO` (80%) → Phase 1: HeavyStrike (range 40, cd 3s)
      • `_P3_HP_RATIO` (30%) < HP ≤ `_P1_HP_RATIO` → Phase 2: auto-summon
      • HP ≤ `_P3_HP_RATIO` → Phase 3: TẮT summon vĩnh viễn (sticky lock)

    Cờ sticky `_summon_locked` latches `True` khi HP chạm ≤ 30% lần đầu —
    one-way transition (dù HP có hồi lên > 30%, summon không bật lại).

    Summon spec (Phase 2):
      • Mỗi đợt `_SUMMON_TOTAL` minion, random từ `_MINION_POOL`
      • Vòng tròn bán kính `_SUMMON_RADIUS`
      • Animation 1s + hold col=5 `_SUMMON_PAUSE` giây → spawn
      • Cooldown `_SUMMON_WAVE_COOLDOWN` giây giữa đợt

    Visual: `Assets/Boss/founding.png` (frame 64×64).
      Walk/Attack/Summon — rows lần lượt 8-11 / 12-15 / 0-3.
      KHÔNG có Run (Founding chỉ Walk khi di chuyển).
    """

    # ── Tham số gameplay ─────────────────────────────────────────
    _DEFAULT_HP              = balance.FOUNDING_HP
    _DEFAULT_SPEED           = balance.FOUNDING_SPEED
    _DEFAULT_DAMAGE          = balance.FOUNDING_DAMAGE
    _DEFAULT_ATTACK_RANGE    = balance.FOUNDING_ATTACK_RANGE
    _DEFAULT_ATTACK_COOLDOWN = balance.FOUNDING_ATTACK_COOLDOWN

    # ── Sprite layout — KHÔNG có Run ─────────────────────────────
    _SPRITE_FILE   = 'founding.png'
    _FRAME_SIZE    = 64
    _WALK_ROWS:    dict = {0: 8,  1: 9,  2: 10, 3: 11}
    _ATTACK_ROWS:  dict = {0: 12, 1: 13, 2: 14, 3: 15}
    _SUMMON_ROWS:  dict = {0: 0,  1: 1,  2: 2,  3: 3}
    _WALK_FRAMES   = 9
    _ATTACK_FRAMES = 6
    _SUMMON_FRAMES = 6
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 10
    _SUMMON_FPS    = 6
    _SUMMON_PAUSE  = 2.0

    # ── Phase / HP thresholds ────────────────────────────────────
    _P1_HP_RATIO   = balance.FOUNDING_P1_HP_RATIO    # > 0.8 = P1
    _P3_HP_RATIO   = balance.FOUNDING_P3_HP_RATIO    # ≤ 0.3 = P3 (sticky)

    # ── Phase 2 summon ───────────────────────────────────────────
    _SUMMON_TOTAL         = balance.FOUNDING_SUMMON_TOTAL  # Reduced from 10 to reduce spawn lag spike
    _SUMMON_RADIUS        = balance.FOUNDING_SUMMON_RADIUS
    _SUMMON_WAVE_COOLDOWN = balance.FOUNDING_SUMMON_WAVE_COOLDOWN   # trước: 10.0 — giãn cách giữa các đợt triệu hồi

    # Skill hồi máu khi triệu hồi: mỗi đợt minion RA ĐỜI (lúc _release_summon
    # chạy, không phải lúc bắt đầu animation) hồi % LƯỢNG MÁU ĐÃ MẤT (không
    # phải % max_hp) — chỉnh số này để cân bằng.
    _HEAL_ON_SUMMON_PCT   = balance.FOUNDING_HEAL_ON_SUMMON_PCT   # hồi 30% (max_hp - hp) mỗi lần triệu hồi

    # Serum (item áp lên Tower) — đạn từ tháp có serum trúng Founding thì gọi
    # apply_heal_debuff(): trong _HEAL_DEBUFF_DURATION giây kế tiếp, tỉ lệ hồi
    # máu khi triệu hồi giảm còn _HEAL_DEBUFF_PCT (thay vì _HEAL_ON_SUMMON_PCT).
    # Mỗi lần trúng đạn serum CHỈ reset timer về lại _HEAL_DEBUFF_DURATION —
    # không cộng dồn thời lượng, không giảm % sâu hơn.
    _HEAL_DEBUFF_PCT      = balance.FOUNDING_HEAL_DEBUFF_PCT
    _HEAL_DEBUFF_DURATION = balance.FOUNDING_HEAL_DEBUFF_DURATION

    # Minion: chỉnh 3 số này để cân bằng độ trâu/tốc/damage của minion summon.
    _MINION_HP            = balance.FOUNDING_MINION_HP    # trước: 200
    _MINION_SPEED         = balance.FOUNDING_MINION_SPEED
    _MINION_DAMAGE        = balance.FOUNDING_MINION_DAMAGE

    # Pool: mỗi đợt random `_SUMMON_TOTAL` con từ 8 loại titan
    _MINION_POOL = (
        'regular2', 'regular4', 'regular5', 'regular6', 'regular7',
        'wolf', 'towerhunter', 'soldierhunter',
    )

    def __init__(self, x: float, y: float, config: dict = None) -> None:
        """Khởi tạo Founding — FINAL BOSS, 3 phase theo HP, triệu hồi + tự hồi máu.

        Ý tưởng thiết kế: máu cực dày (10000) và ở PHASE 2 nó vừa TRIỆU HỒI MINION
        vừa TỰ HỒI MÁU mỗi lần triệu hồi → nếu người chơi không đủ DPS, boss hồi
        nhanh hơn mất máu và trận đấu KHÔNG BAO GIỜ KẾT THÚC. Cách hoá giải: dùng
        item **serum** lên tháp → đạn tháp áp `apply_heal_debuff()` hạ tỉ lệ hồi từ
        30% xuống 10%.

        Khởi tạo gì:
          - `_attack_strategy = HeavyStrikeStrategy(damage_mult=2.0)` — ghi đè mult
            mặc định (3.5) xuống 2.0 vì `_damage` gốc của boss đã rất cao (200).
          - `_phase` (1/2/3) và `_summon_locked` — cờ STICKY: một khi HP tụt xuống
            phase 3, boss KHÔNG BAO GIỜ quay lại phase 2 dù có hồi máu lên lại
            (nếu không có cờ này, boss sẽ hồi máu → về P2 → triệu hồi → hồi tiếp…
            thành vòng lặp bất tử).
          - `_heal_debuff_timer` — >0 nghĩa là serum đang có hiệu lực.
          - Cụm cờ animation (KHÔNG có Run — Founding không chạy).
          - `_summon_released` — chống triệu hồi 2 lần trong 1 animation.
          - `_summoned_minions` — list minion do boss sinh ra, boss tự quản lý.

        Chỉ số: balance.FOUNDING_HP/_SPEED/_DAMAGE/_ATTACK_RANGE/_ATTACK_COOLDOWN,
        balance.FOUNDING_P1_HP_RATIO / _P3_HP_RATIO, _SUMMON_*, _HEAL_*, _MINION_*.
        """
        super().__init__(x, y, config)
        self._attack_strategy = HeavyStrikeStrategy(damage_mult=2.0)

        self._phase          = 1
        self._summon_locked  = False
        self._heal_debuff_timer = 0.0   # >0 = serum đang hiệu lực (xem apply_heal_debuff)

        # Animation state — KHÔNG có Run
        self._direction          = 2
        self._is_moving          = False
        self._is_attacking       = False
        self._is_summoning       = False
        self._summon_pause_timer = 0.0
        self._summon_released    = False
        self._anim_col           = 0
        self._anim_timer         = 0.0
        self._attack_anim_timer  = 0.0
        self._summon_anim_timer  = 0.0

        # Cooldown timers
        self._attack_cd_timer = 0.0
        self._summon_cd_timer = 0.0
        self._world_x = x  # lưu vị trí world trước khi game loop offset
        self._world_y = y

        self._sprite_sheet = None

        # Danh sách minion đã spawn
        self._summoned_minions: list = []

    # ── Sprite helpers ───────────────────────────────────────────

    def _load_sprite(self) -> None:
        """Nạp lazy spritesheet `Assets/Boss/founding.png` (1 lần duy nhất).

        Giống `ColossalTitan._load_sprite`: nạp lazy vì cần display trước khi
        `convert_alpha()`; lỗi → None, `draw()` tự fallback, không crash.
        """
        if self._sprite_sheet is not None:
            return
        try:
            path = os.path.join(
                os.path.dirname(__file__),
                'Assets', 'Boss', self._SPRITE_FILE)
            self._sprite_sheet = pygame.image.load(path).convert_alpha()
        except Exception:
            self._sprite_sheet = None

    def _get_frame(self, row: int, col: int = 0):
        """Cắt ô (row, col) khỏi spritesheet Founding → Surface nền trong suốt.

        Lưới ô vuông `_FRAME_SIZE` (64px); dùng SRCALPHA giữ nền trong.
        Hàng tra từ `_WALK_ROWS` / `_ATTACK_ROWS` / `_SUMMON_ROWS`.
        Trả về None nếu sheet chưa nạp được.
        """
        if self._sprite_sheet is None:
            return None
        fs = self._FRAME_SIZE
        region = pygame.Rect(col * fs, row * fs, fs, fs)
        frame = pygame.Surface((fs, fs), pygame.SRCALPHA)
        frame.blit(self._sprite_sheet, (0, 0), region)
        return frame

    # ── Phase logic ──────────────────────────────────────────────

    def _check_phase(self) -> None:
        """Tính lại `_phase` (1/2/3) theo tỉ lệ HP — với cơ chế KHOÁ MỘT CHIỀU.

        Bản đồ phase theo `ratio = hp / max_hp`:
            ratio > 0.8            → PHASE 1  (đánh thường)
            0.3 < ratio <= 0.8     → PHASE 2  (TRIỆU HỒI + tự hồi máu)
            ratio <= 0.3           → PHASE 3  (đánh thường, hết triệu hồi)

        CƠ CHẾ STICKY (quan trọng nhất): hễ `ratio <= _P3_HP_RATIO` MỘT LẦN thì
        `_summon_locked = True` VĨNH VIỄN. Sau đó dù boss có hồi máu vọt lên lại
        60% thì vẫn bị ép ở phase 3, KHÔNG được quay về phase 2 để triệu hồi nữa.

        Vì sao bắt buộc: nếu không có cờ khoá, chuỗi sẽ là
            P2 → triệu hồi → hồi 30% máu đã mất → ratio tăng → vẫn P2 → triệu hồi…
        boss BẤT TỬ. Cờ khoá đảm bảo trận đấu luôn kết thúc được.

        Chỉ số: balance.FOUNDING_P1_HP_RATIO (0.8), balance.FOUNDING_P3_HP_RATIO (0.3).
        Tác động khi sửa: hạ `_P3_HP_RATIO` → boss ở phase triệu hồi lâu hơn → khó hơn nhiều.
        """
        ratio = self._hp / self._max_hp if self._max_hp > 0 else 0
        if ratio <= self._P3_HP_RATIO:
            self._summon_locked = True

        if ratio > self._P1_HP_RATIO:
            self._phase = 1
        elif self._summon_locked:
            self._phase = 3
        elif ratio > self._P3_HP_RATIO:
            self._phase = 2
        else:
            self._phase = 3

    # ── Public API cho demo/AI ───────────────────────────────────

    # NOTE: bản cũ có `_act_in_range()` ở đây — CODE CHẾT và SAI: nó nằm trên
    # class Titan nhưng lại dùng `self.titan` / `self.target` / `self._attack_cd`
    # (thuộc tính của AI), gọi vào là AttributeError ngay. Bản thật nằm ở
    # `FoundingAI._act_in_range()` (ai.py). Đã xoá để tránh bẫy về sau.

    def trigger_attack(self) -> bool:
        """Đòn thường (phase 1 & 3) — vung tay HeavyStrike VÀ áp damage NGAY tại đây.

        KHÁC BIỆT SỐNG CÒN so với mọi titan khác: hàm này TỰ ÁP DAMAGE, không chỉ
        chạy animation. Đây từng là nguồn bug "boss đánh gấp đôi": `TitanAI._resolve_
        telegraph()` mặc định gọi CẢ `trigger_attack()` LẪN `strategy.execute()` →
        tướng ăn 2 lần damage. Vì thế `FoundingAI` PHẢI override `_resolve_telegraph()`
        để chỉ gọi `trigger_attack()`. Ai sửa AI nhớ giữ nguyên điều này.

        Không nhận tham số target — nó ĐỌC `self._ai_current_target` do `ai.py` gán
        trước khi gọi (AI đã kiểm tra tầm đánh rồi).

        Thuật toán:
          1. Từ chối nếu đang đánh/đang triệu hồi hoặc cooldown chưa hết → False.
          2. Bật cờ đánh, đặt `_attack_anim_timer` và nạp lại `_attack_cd_timer`.
          3. Xoay mặt về target (so |dx| vs |dy| → 1 trong 4 hướng).
          4. ÁP DAMAGE, phân nhánh theo loại mục tiêu:
             - Mục tiêu là TƯỜNG:
                 · `Wall` composite (có `_sections`) → `take_damage(..., pos=(x,y))`
                   — phải truyền vị trí để Wall biết ĐOẠN tường nào bị đánh.
                 · `WallSection` lẻ (không có `_sections`) → `take_damage()` thường.
             - Mục tiêu khác → `self._attack_strategy.execute(self, target)`.

        Trả về: bool — True = đã ra đòn; False = bị từ chối.
        Chỉ số: balance.FOUNDING_DAMAGE, balance.FOUNDING_ATTACK_COOLDOWN,
        balance.STRAT_HEAVY_STRIKE_MULT (nhưng bị ghi đè = 2.0 trong `__init__`).
        """
        if self._is_attacking or self._is_summoning:
            return False
        if self._attack_cd_timer > 0:
            return False

        self._is_attacking      = True
        self._attack_anim_timer = self._ATTACK_FRAMES / self._ATTACK_FPS
        self._anim_col          = 0
        self._anim_timer        = 0.0
        self._attack_cd_timer   = self._attack_cooldown

        # Get target from AI context (AI verified range via act() before calling this)
        target = getattr(self, '_ai_current_target', None)
        if target is not None:
            dx, dy = target.x - self.x, target.y - self.y
            if abs(dx) > abs(dy):
                self._direction = 3 if dx > 0 else 1
            else:
                self._direction = 2 if dy > 0 else 0

            # For walls, pass position if it's the composite Wall (not WallSection)
            if getattr(target, 'ENTITY_TYPE', None) == 'wall':
                dmg = self._attack_strategy.compute_damage(self)
                dtype = self._attack_strategy._dtype
                # Wall composite accepts pos; WallSection doesn't
                if hasattr(target, '_sections'):  # Wall composite has _sections
                    target.take_damage(amount=dmg, dtype=dtype, pos=(self.x, self.y))
                else:  # WallSection
                    target.take_damage(amount=dmg, dtype=dtype)
            else:
                self._attack_strategy.execute(self, target)

        return True

    def start_summon(self) -> bool:
        """BẮT ĐẦU animation triệu hồi (minion CHƯA ra đời ở đây) — chỉ phase 2.

        Tách 2 pha giống Beast ném đá:
          - Pha 1 (hàm này): bật `_is_summoning`, reset `_summon_released = False`.
          - Pha 2 (`update_anim` → `_release_summon`): hết animation + pause thì
            minion mới THỰC SỰ ra đời, VÀ boss mới hồi máu.
          Nhờ vậy người chơi có ~2s (`_SUMMON_PAUSE`) NHÌN THẤY boss đang gồng để
          kịp phản ứng (vd bắn đạn serum vào để hạ tỉ lệ hồi máu trước khi nó hồi).

        4 điều kiện từ chối (trả False):
          1. `_phase != 2` — chỉ phase 2 mới triệu hồi được.
          2. Đang đánh hoặc đang triệu hồi dở.
          3. `_summon_locked` — đã từng rơi xuống phase 3 → CẤM VĨNH VIỄN (chống
             vòng lặp bất tử, xem `_check_phase`).
          4. `_summon_cd_timer > 0` — chưa hết `_SUMMON_WAVE_COOLDOWN` (15s).

        Trả về: bool — True = bắt đầu triệu hồi.
        Chỉ số: balance.FOUNDING_SUMMON_WAVE_COOLDOWN.
        """
        SoundManager.get_instance().play('founding_summon_6_recommended', self.x, self.y)
        if self._phase != 2:
            return False
        if self._is_attacking or self._is_summoning or self._summon_locked:
            return False
        if self._summon_cd_timer > 0:
            return False

        self._is_summoning       = True
        self._summon_anim_timer  = self._SUMMON_FRAMES / self._SUMMON_FPS
        self._summon_pause_timer = 0.0
        self._summon_released    = False
        self._anim_col           = 0
        self._anim_timer         = 0.0
        return True

    def apply_heal_debuff(self) -> None:
        """SERUM trúng boss → hạ tỉ lệ hồi máu từ 30% xuống 10% trong 5 giây.

        Đây là API PUBLIC — "nút hoá giải" boss dành cho người chơi.

        Thuật toán: chỉ RESET timer về `_HEAL_DEBUFF_DURATION` (5.0s).
        **KHÔNG CỘNG DỒN** — trúng viên serum thứ 2 khi timer còn 2s thì timer về
        lại 5s, KHÔNG thành 7s. Và cũng KHÔNG hạ % sâu hơn 10%.
        Ý đồ: bắn nhiều serum chỉ giúp DUY TRÌ debuff, không giúp stack mạnh hơn.

        Ai gọi: `Projectile._apply_serum_debuff()` (structures/towers/projectile.py)
        — kích hoạt khi tháp bắn có `_serum_buff = True` (người chơi áp item serum
        lên tháp từ túi đồ trong game.py).
        Đếm ngược ở đâu: `update_anim()`.
        Chỉ số: balance.FOUNDING_HEAL_DEBUFF_DURATION / _HEAL_DEBUFF_PCT.
        """
        self._heal_debuff_timer = self._HEAL_DEBUFF_DURATION

    def _release_summon(self) -> None:
        """MINION RA ĐỜI + BOSS HỒI MÁU — trái tim của phase 2.

        ═══ 1. HỒI MÁU (chạy TRƯỚC khi spawn) ═══
        Công thức hồi theo **% MÁU ĐÃ MẤT**, KHÔNG phải % máu tối đa:
            `missing_hp = max_hp - hp`
            `hp += round(missing_hp × heal_pct)`, kẹp trần `max_hp`.
        Ví dụ: còn 4000/10000 (mất 6000) → hồi 30%×6000 = 1800 → lên 5800.
        Hệ quả (cố ý): boss càng gần chết, mỗi lần triệu hồi càng hồi NHIỀU máu
        tuyệt đối → càng khó kết liễu. Dùng %max_hp thì lượng hồi cố định, dễ hơn.

        `heal_pct` chọn theo debuff:
            `_heal_debuff_timer > 0` (đang dính SERUM) → `_HEAL_DEBUFF_PCT` (10%)
            ngược lại                                  → `_HEAL_ON_SUMMON_PCT` (30%)
        → Đây là cách người chơi hoá giải boss: áp item **serum** lên Tower, đạn
        tháp trúng boss sẽ gọi `apply_heal_debuff()`.

        ═══ 2. SPAWN MINION ═══
        Thuật toán rải vòng tròn + né tường:
          a. Chia đều 360° thành `_SUMMON_TOTAL` (6) lát → mỗi minion 1 góc.
          b. `SPAWN_RADIUS = max(_SUMMON_RADIUS + 150, 400)` — spawn XA hẳn boss,
             cố ý, để minion không đẻ ra là kẹt trong tường.
          c. NÉ TƯỜNG: mỗi vị trí thử tối đa 2 lần — nếu
             `WorldQuery.is_wall_blocked(mx, my, WALL_R=50)` thì đẩy bán kính ra
             thêm 100px rồi thử lại. Giới hạn 2 lần để không gây khựng lúc spawn.
             (WALL_R = 50 là bán kính va chạm thân minion → khe tường 1 ô 32px là
             KHÔNG lọt được; minion cần lỗ thủng rộng hơn.)
          d. Loại minion random từ `_MINION_POOL` (8 loại: 5 regular + wolf +
             towerhunter + soldierhunter).
          e. MỌI minion bị ép cùng `config = {hp, speed, damage}` yếu hơn hẳn bản
             gốc (vd RegularTitan gốc 1000HP/60dmg → minion chỉ dùng _MINION_*).

        Liên kết: `WorldQuery.is_wall_blocked()` (systems/world_query.py);
        `apply_heal_debuff()` gọi từ `structures/towers/projectile.py` (đạn serum).
        Chỉ số: balance.FOUNDING_HEAL_ON_SUMMON_PCT / _HEAL_DEBUFF_PCT /
        _SUMMON_TOTAL / _SUMMON_RADIUS / _MINION_HP / _MINION_SPEED / _MINION_DAMAGE.
        """
        from characters.titans.titan import (
            RegularTitan, Wolf, TowerHunter, SoldierHunter,
        )
        from systems.world_query import WorldQuery

        heal_pct = (self._HEAL_DEBUFF_PCT if self._heal_debuff_timer > 0
                   else self._HEAL_ON_SUMMON_PCT)
        missing_hp = self._max_hp - self._hp
        if missing_hp > 0:
            self._hp = min(self._max_hp,
                           self._hp + int(round(missing_hp * heal_pct)))

        config = {'hp': self._MINION_HP, 'speed': self._MINION_SPEED,
                 'damage': self._MINION_DAMAGE}  # Reduced speed to reduce AI/movement lag
        slice_angle = 2 * math.pi / self._SUMMON_TOTAL
        WALL_R = 50.0  # Minion collision radius
        SPAWN_RADIUS = max(self._SUMMON_RADIUS + 150.0, 400.0)  # Start far enough to avoid walls

        for idx in range(self._SUMMON_TOTAL):
            angle = idx * slice_angle
            mx = self.x + math.cos(angle) * SPAWN_RADIUS
            my = self.y + math.sin(angle) * SPAWN_RADIUS

            # Quick check: if still blocked, push farther (max 2 attempts to avoid lag)
            current_radius = SPAWN_RADIUS
            for attempt in range(2):
                if WorldQuery.is_wall_blocked(mx, my, WALL_R):
                    current_radius += 100.0  # Big push outward
                    mx = self.x + math.cos(angle) * current_radius
                    my = self.y + math.sin(angle) * current_radius
                else:
                    break

            kind = random.choice(self._MINION_POOL)
            if kind.startswith('regular'):
                minion = RegularTitan(mx, my, config)
                minion._variant = int(kind[len('regular'):])
            elif kind == 'wolf':
                minion = Wolf(mx, my, config)
            elif kind == 'towerhunter':
                minion = TowerHunter(mx, my, config)
            else:  # 'soldierhunter'
                minion = SoldierHunter(mx, my, config)

            minion._sprite_sheet = None
            minion._direction = self._direction
            self._summoned_minions.append(minion)
            # Minion AI: independent, not in FoundingAI._minion_ais (those are only for ticking)
            minion._ai = make_ai_for(minion, self.world)
            WorldQuery.spawn_entity(minion)

    # ── Update animation ─────────────────────────────────────────

    def update_anim(self, dt: float) -> None:
        """Đếm ngược mọi timer + chạy animation + KÍCH HOẠT triệu hồi đúng lúc.

        AI (`FoundingAI`) gọi hàm này mỗi frame thay cho `update()`.

        Thuật toán:
          1. Đếm ngược 3 timer (đều kẹp sàn 0, dùng `dt_slowed` — bị IceTower làm chậm):
             `_attack_cd_timer`, `_summon_cd_timer`, và `_heal_debuff_timer`
             (serum hết hạn ở đây → boss hồi máu lại 30%).
          2. `_check_phase()` — cập nhật phase theo HP MỖI FRAME (và có thể khoá
             vĩnh viễn phase 3).
          3. Đang ĐÁNH → chỉ chạy animation vung tay, xong thì tắt cờ, rồi `return`
             (khoá, không làm gì khác).
          4. Đang TRIỆU HỒI → máy trạng thái 2 giai đoạn:
             a. Còn `_summon_anim_timer` → chạy animation gồng. Lưu ý cột dừng lại
                ở frame CUỐI (`if _anim_col < _SUMMON_FRAMES-1`), KHÔNG lặp vòng —
                boss "giữ nguyên tư thế gồng".
                Hết animation → chuyển sang pha chờ: `_summon_pause_timer = _SUMMON_PAUSE` (2s).
             b. Hết pause → **`_release_summon()`** (minion ra đời + boss hồi máu),
                bật `_summon_released` chống gọi 2 lần, tắt cờ triệu hồi, và nạp
                `_summon_cd_timer = _SUMMON_WAVE_COOLDOWN` (15s).
             → 2s pause này là CỬA SỔ PHẢN ỨNG cho người chơi bắn serum vào boss
               trước khi nó kịp hồi máu.
             Lưu ý: animation summon dùng `dt` GỐC (không slow) — làm chậm boss
             KHÔNG kéo dài được thời gian gồng.
          5. Đang đi → animation walk. Đứng yên → reset frame.

        Chỉ số: balance.FOUNDING_SUMMON_WAVE_COOLDOWN, _HEAL_DEBUFF_DURATION,
        FOUNDING_ATTACK_COOLDOWN. (`_SUMMON_PAUSE` là số animation, nằm trong file này.)
        """
        dt_slowed = dt * self._slow_factor  # Apply slow to all timers
        if self._attack_cd_timer > 0:
            self._attack_cd_timer = max(0.0, self._attack_cd_timer - dt_slowed)
        if self._summon_cd_timer > 0:
            self._summon_cd_timer = max(0.0, self._summon_cd_timer - dt_slowed)
        if self._heal_debuff_timer > 0:
            self._heal_debuff_timer = max(0.0, self._heal_debuff_timer - dt_slowed)

        self._check_phase()

        if self._is_attacking:
            self._attack_anim_timer -= dt_slowed
            self._anim_timer += dt_slowed
            if self._anim_timer >= 1.0 / self._ATTACK_FPS:
                self._anim_timer -= 1.0 / self._ATTACK_FPS
                self._anim_col = (self._anim_col + 1) % self._ATTACK_FRAMES
            if self._attack_anim_timer <= 0:
                self._is_attacking = False
                self._anim_col     = 0
                self._anim_timer   = 0.0
            return

        if self._is_summoning:
            if self._summon_anim_timer > 0:
                self._summon_anim_timer -= dt
                self._anim_timer += dt
                if self._anim_timer >= 1.0 / self._SUMMON_FPS:
                    self._anim_timer -= 1.0 / self._SUMMON_FPS
                    if self._anim_col < self._SUMMON_FRAMES - 1:
                        self._anim_col += 1
                if (self._anim_col >= self._SUMMON_FRAMES - 1
                        and self._summon_anim_timer <= 0):
                    self._summon_anim_timer  = 0.0
                    self._summon_pause_timer = self._SUMMON_PAUSE
            else:
                self._summon_pause_timer -= dt
                if self._summon_pause_timer <= 0:
                    if not self._summon_released:
                        self._release_summon()
                        self._summon_released = True
                    self._is_summoning    = False
                    self._anim_col        = 0
                    self._anim_timer      = 0.0
                    self._summon_cd_timer = self._SUMMON_WAVE_COOLDOWN
            return

        if self._is_moving:
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._ANIM_FPS:
                self._anim_timer -= 1.0 / self._ANIM_FPS
                self._anim_col = (self._anim_col + 1) % self._WALK_FRAMES
        else:
            self._anim_col   = 0
            self._anim_timer = 0.0

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        """Vẽ minion TRƯỚC, rồi mới vẽ Founding đè lên (thứ tự lớp có chủ đích).

        Thuật toán:
          1. Duyệt `_summoned_minions` (bỏ qua con đã chết):
             - Gọi `_load_sprite()` của minion nếu có (nạp lazy giúp minion vừa
               spawn hiện ra ngay frame đầu, không bị 1 frame trống).
             - `m.draw(screen)` bọc try/except: 1 minion lỗi đồ hoạ KHÔNG được
               làm sập cả hàm draw của boss.
             - FALLBACK: minion không có sprite → vẽ vòng tròn đỏ (18px) để người
               chơi vẫn THẤY nó. Thà xấu còn hơn kẻ địch vô hình.
          2. Vẽ Founding SAU → luôn nổi trên đám minion (boss là tâm điểm, không
             bị minion che mặt).
          3. Chọn hàng sprite: summoning > attacking > moving > (mặc định walk).
             Cột = `_anim_col` nếu đang làm gì đó, ngược lại 0.
          4. Scale 64×64 → 160×160 (2.5×), căn TÂM tại (x, y).

        CHỈ ĐỒ HOẠ — không đổi trạng thái logic nào.
        """
        for m in self._summoned_minions:
            if not getattr(m, 'is_alive', True):
                continue
            load = getattr(m, '_load_sprite', None)
            if callable(load):
                load()
            try:
                m.draw(screen)
            except Exception:
                pass
            if getattr(m, '_sprite_sheet', None) is None:
                mx, my = int(m.x), int(m.y)
                pygame.draw.circle(screen, (180, 100, 100), (mx, my), 18)
                pygame.draw.circle(screen, (240, 200, 200), (mx, my), 18, 2)

        self._load_sprite()

        if self._is_summoning:
            row = self._SUMMON_ROWS[self._direction]
        elif self._is_attacking:
            row = self._ATTACK_ROWS[self._direction]
        elif self._is_moving:
            row = self._WALK_ROWS[self._direction]
        else:
            row = self._WALK_ROWS[self._direction]

        col = self._anim_col if (
            self._is_moving or self._is_attacking or self._is_summoning
        ) else 0
        frame = self._get_frame(row, col)
        if frame is not None:
            scaled = pygame.transform.scale(frame, (160, 160))  # 2.5x scale
            rect = scaled.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(scaled, rect)

    # ── AI gốc (chế độ manual) ───────────────────────────────────

    def update(self, dt: float) -> None:
        """AI NỘI BỘ của Founding (chế độ manual/demo) + DỌN XÁC minion.

        CẢNH BÁO: trong game THẬT, `FoundingAI` (ai.py) là bộ não và nó gọi
        `update_anim()`. Gọi cả hàm này nữa → 2 AI tranh nhau điều khiển.

        Thuật toán:
          1. `update_anim(dt)` — timer + animation + kích hoạt triệu hồi.
          2. **DỌN XÁC MINION** (quan trọng, kể cả khi AI thật đang chạy):
             minion chết bị `WorldQuery.remove_entity()` và lọc khỏi
             `_summoned_minions`. Không dọn → list phình mãi, `draw()` duyệt xác
             chết mỗi frame → rò rỉ bộ nhớ + tụt FPS.
             Lưu ý: minion là entity ĐỘC LẬP, tự được game loop update qua
             WorldQuery; boss chỉ THEO DÕI chứ không update hộ chúng.
          3. Chết → thoát.
          4. Đang triệu hồi → đứng im, không ra quyết định mới.
          5. PHASE 2 và hết cooldown → `start_summon()` rồi `return` NGAY (ưu tiên
             triệu hồi hơn đánh — đây là bản chất phase 2).
          6. Ngược lại (phase 1/3) → tìm `find_nearest_attacker()`:
             - Trong tầm + hết cooldown → `trigger_attack()`.
             - Ngoài tầm → đi lại gần.

        Chỉ số: balance.FOUNDING_ATTACK_RANGE / _ATTACK_COOLDOWN /
        _SUMMON_WAVE_COOLDOWN.
        """
        from systems.world_query import WorldQuery

        self.update_anim(dt)

        # Minions are independent — updated by game loop via WorldQuery.
        # Just cleanup dead ones from tracking list.
        dead_minions = [m for m in self._summoned_minions if not m.is_alive]
        for dead in dead_minions:
            WorldQuery.remove_entity(dead)
        self._summoned_minions = [m for m in self._summoned_minions if m.is_alive]

        if not self.is_alive:
            return

        # Allow attack targeting even if currently attacking (cooldown management)
        # Only skip minion spawning during attack
        if self._is_summoning:
            self._is_moving = False
            return

        if self._phase == 2 and self._summon_cd_timer <= 0:
            self.start_summon()
            return

        from systems.world_query import WorldQuery
        target = WorldQuery.find_nearest_attacker(self)
        if target is None:
            self._is_moving = False
            return
        dist = self._distance_to(target)
        if dist <= self._attack_range and self._attack_cd_timer <= 0:
            self._is_moving = False
            self.trigger_attack(target)
        elif dist > self._attack_range:
            self._is_moving = True
            self._move_toward(target, dt)

    # ── Backward-compat helpers ──────────────────────────────────

    def _summon_minions(self, count: int):
        """ALIAS TƯƠNG THÍCH NGƯỢC — chỉ gọi `start_summon()`.

        Tham số `count` bị BỎ QUA (`del count`): số minion mỗi đợt giờ do
        `_SUMMON_TOTAL` (← balance.FOUNDING_SUMMON_TOTAL) quyết định, không cho
        caller tự chọn nữa. Giữ tham số chỉ để chữ ký không vỡ với code cũ
        (thư mục CHECK/, CHECKAI/).

        Code MỚI nên gọi thẳng `start_summon()`. Muốn đổi số minion → sửa
        balance.FOUNDING_SUMMON_TOTAL.
        """
        del count
        self.start_summon()

    def _has_serum_fragment(self) -> bool:
        """STUB — luôn trả False. CODE CHẾT, hiện KHÔNG được dùng ở đâu.

        Ý định ban đầu: kiểm tra người chơi có "mảnh serum" để hạ tỉ lệ hồi máu
        của boss hay không.

        Thực tế cơ chế serum ĐÃ ĐƯỢC LÀM THEO CÁCH KHÁC và đang chạy tốt:
        người chơi áp item **serum** lên Tower (từ túi đồ trong game.py) → tháp
        có `_serum_buff = True` → đạn của nó gọi `apply_heal_debuff()` khi trúng
        boss → hồi máu tụt 30% → 10%.

        Vì vậy hàm này là tàn dư. Có thể xoá an toàn nếu chắc chắn không còn ai gọi.
        """
        return False
