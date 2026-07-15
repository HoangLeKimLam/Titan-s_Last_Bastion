import os
import math
import pygame

from core.entity import Entity
from core.interfaces import IAttackable
from core.event_bus import GameEventBus
from systems.world_query import WorldQuery
from config import balance

_HERE = os.path.dirname(os.path.abspath(__file__))
TILE = 48  # Basic tile size for scaling

class Trap(Entity, IAttackable):
    """
    Base class for all Traps. Traps are placed on the ground, do not block
    Titan pathfinding, and trigger when Titans walk over them.

    Kiến trúc: `Trap` KHÔNG bị Titan coi là vật cản (không xuất hiện trong
    WorldQuery wall/collision query) — chỉ được các subclass TỰ QUÉT
    `WorldQuery.all()` mỗi frame trong `update()` để phát hiện titan đứng
    trong `get_rect()`/bán kính rồi CHỦ ĐỘNG gọi `t.take_damage(...)`. Đây
    là chiều NGƯỢC với combat thông thường (titan tấn công) — bẫy là bên
    chủ động tấn công titan.

    `COST_TUPLE = (gen_slot, spec_slot, amount)` — khai báo Ở SUBCLASS,
    dùng bởi hệ thống chế tạo (Forge/TrainingCamp trong `building.py`) để
    biết bẫy này tiêu tốn slot chế tạo chung (`gen_slot`) và slot loại
    riêng (`spec_slot`) bao nhiêu.
    """
    COST_TUPLE = None  # (gen_slot, spec_slot, amount)

    def __init__(self, x: float, y: float, tw: int, th: int, horizontal: bool = True):
        """Khởi tạo bẫy tại (x,y) với kích thước `tw`×`th` ô (đơn vị TILE=48px).

        Tham số: horizontal — hướng đặt bẫy (ảnh hưởng cách subclass chọn
        sprite ngang/dọc và cách tính vùng gây damage — xem `get_rect()`).
        HP mặc định 1/1 — MỌI subclass PHẢI override lại `_hp`/`_max_hp`
        đúng giá trị `balance.*_TRAP_HP` trong `__init__` của nó, nếu quên
        thì bẫy chết ngay từ 1 lượt trừ HP đầu tiên.
        """
        super().__init__(x, y)
        self.tw = tw
        self.th = th
        self.horizontal = horizontal
        self._hp = 1
        self._max_hp = 1
        self._sprite = None

    def take_damage(self, amount: int, dtype: str = ''):
        """Trừ `_hp` — bẫy KHÔNG bị Titan tấn công trực tiếp bình thường; đây
        là cơ chế "tự tiêu hao" HP bẫy dùng NỘI BỘ bởi mỗi lần gây damage
        thành công (xem `ThornTrap.update`/`PoisonTrap.update`: mỗi lượt
        trúng đòn titan trừ ngược lại vài điểm HP bẫy — bẫy "hao mòn" theo
        số lần dùng, không phải bị tấn công). `dtype` không dùng ở base class."""
        self._hp -= amount
        if self._hp <= 0:
            self.on_death()

    def on_death(self):
        """Bẫy hết HP/hết hạn → biến mất khỏi map, publish `'trap_destroyed'`
        (HUD/WorldQuery subscribe để dọn tham chiếu). Guard `is_alive` chặn
        publish LẶP LẠI nếu `take_damage` gọi nhiều lần sau khi đã chết."""
        if not self.is_alive:
            return
        self.is_alive = False
        GameEventBus.get_instance().publish('trap_destroyed', {'trap': self})

    def get_rect(self) -> pygame.Rect:
        """Vùng hình chữ nhật chiếm bởi bẫy (px) — dùng để test titan có đứng
        trong bẫy không (AABB-vs-circle clamp, xem các `update()` subclass)."""
        return pygame.Rect(self.x, self.y, self.tw * TILE, self.th * TILE)

    def get_center(self):
        """Toạ độ tâm hình học của bẫy (px) — dùng làm gốc tính khoảng cách
        cho các bẫy AoE tròn (Explode/Poison) hoặc gốc hướng đẩy (Suriken)."""
        return (self.x + self.tw * TILE / 2.0, self.y + self.th * TILE / 2.0)

    def update(self, dt: float):
        """No-op ở base class — MỌI logic kích hoạt/gây damage do subclass override."""
        pass

    def draw(self, surface: pygame.Surface):
        """Vẽ `_sprite` nếu có, KHÔNG thì vẽ khung magenta debug (báo hiệu
        thiếu sprite — không nên xuất hiện ở bản build thật)."""
        if self._sprite:
            surface.blit(self._sprite, (self.x, self.y))
        else:
            pygame.draw.rect(surface, (255, 0, 255), self.get_rect(), 2)


# ==============================================================================
# THORN TRAP
# ==============================================================================
class ThornTrap(Trap):
    """Bẫy gai — dải 5 ô, gây damage tick định kỳ cho MỌI titan chồng lên
    vùng bẫy. Không có trạng thái kích hoạt (luôn "bật"), chỉ tick theo
    `_TICK_RATE`. Sprite cache Ở CẤP CLASS (`_frames_h/_frames_v`) — nạp
    1 LẦN DUY NHẤT cho MỌI instance ThornTrap trên map."""
    COST_TUPLE = ('trap', 'thorn_trap', 1)

    _frames_h = None
    _frames_v = None

    def __init__(self, x: float, y: float, horizontal: bool = True):
        """Tạo bẫy gai dài 5 ô — `horizontal=True` → 5×1 ô (nằm ngang),
        ngược lại 1×5 ô (dọc). Nạp sprite lazy vào cache class-level lần
        instance ĐẦU TIÊN (kiểm tra `ThornTrap._frames_h is None`).
        Chỉ số cân bằng: `balance.THORN_TRAP_HP/DAMAGE/TICK_RATE`.
        """
        tw, th = (5, 1) if horizontal else (1, 5)
        super().__init__(x, y, tw, th, horizontal)
        self._hp = balance.THORN_TRAP_HP
        self._max_hp = balance.THORN_TRAP_HP
        self._damage = balance.THORN_TRAP_DAMAGE
        self._tick_timer = 0.0
        self._TICK_RATE = balance.THORN_TRAP_TICK_RATE  # deals damage every 1 second

        self._anim_timer = 0.0
        self._frame_idx = 0
        self._ANIM_FPS = 15.0

        if ThornTrap._frames_h is None:
            raw = pygame.image.load(os.path.join(_HERE, 'thorn_trap.png')).convert_alpha()
            frame_h = raw.get_height()
            frame_w = frame_h
            num_frames = raw.get_width() // frame_w
            ThornTrap._frames_h = []
            ThornTrap._frames_v = []
            for i in range(num_frames):
                rect = pygame.Rect(i * frame_w, 0, frame_w, frame_h)
                frame_surf = pygame.transform.smoothscale(raw.subsurface(rect), (TILE, TILE))
                ThornTrap._frames_h.append(frame_surf)
                ThornTrap._frames_v.append(pygame.transform.rotate(frame_surf, 90))

    def update(self, dt: float):
        """Mỗi frame: (1) chạy animation gai đung đưa liên tục (không phụ
        thuộc có titan hay không). (2) Cứ mỗi `_TICK_RATE` giây, quét TOÀN
        BỘ titan còn sống trong `WorldQuery.all()`, clamp tâm titan vào
        `get_rect()` (AABB-vs-circle) để test va chạm hình tròn bán kính
        `RADIUS` (mặc định 24 nếu titan không khai báo) với hình chữ nhật
        bẫy — titan trúng thì `take_damage(self._damage)`.

        Cơ chế "hao mòn theo lượt dùng": mỗi titan trúng đòn trong tick này
        làm BẪY (không phải titan) mất 10 HP (`self.take_damage(hit_count*10)`)
        — bẫy càng đánh trúng nhiều titan cùng lúc càng nhanh hỏng, mô
        phỏng gai bị gãy dần. Bẫy tự chết (`on_death`) khi HP ≤ 0.
        """
        if not self.is_alive: return

        self._anim_timer += dt
        if self._anim_timer >= 1.0 / self._ANIM_FPS:
            self._anim_timer -= 1.0 / self._ANIM_FPS
            if ThornTrap._frames_h:
                self._frame_idx = (self._frame_idx + 1) % len(ThornTrap._frames_h)

        self._tick_timer += dt
        if self._tick_timer >= self._TICK_RATE:
            self._tick_timer = 0.0
            rect = self.get_rect()
            hit_count = 0
            for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
                if not t.is_alive: continue
                tr = getattr(t, 'RADIUS', 24)
                cx = max(rect.left, min(t.x, rect.right))
                cy = max(rect.top, min(t.y, rect.bottom))
                if (t.x - cx)**2 + (t.y - cy)**2 <= tr**2:
                    t.take_damage(self._damage, dtype='physical', attacker=None)
                    hit_count += 1
            if hit_count > 0:
                self.take_damage(hit_count * 10)

    def draw(self, surface: pygame.Surface):
        """Vẽ frame hiện tại LẶP LẠI dọc theo chiều dài dải bẫy (5 ô, bước
        32px, không phải TILE=48 — cố ý chồng lấp nhẹ để lấp khoảng trống
        do offset -12px căn giữa mỗi sprite 48×48 quanh tâm ô 32px)."""
        frames = ThornTrap._frames_h if self.horizontal else ThornTrap._frames_v
        if frames:
            frame = frames[self._frame_idx]
            # Draw this frame 5 times
            length = self.tw if self.horizontal else self.th
            for i in range(length):
                if self.horizontal:
                    surface.blit(frame, (self.x + i * 32 - 12, self.y - 12))
                else:
                    surface.blit(frame, (self.x - 12, self.y + i * 32 - 12))
        else:
            pygame.draw.rect(surface, (255, 0, 255), self.get_rect(), 2)


# ==============================================================================
# SURIKEN TRAP
# ==============================================================================
class SurikenTrap(Trap):
    """Bẫy phi tiêu — dải 5 ô, gây damage tick liên tục NHƯ ThornTrap, CỘNG
    THÊM kỹ năng chủ động "Wind Breath" (`trigger_wind_breath`) đẩy lùi
    titan theo 1 hướng cố định trong `_WIND_BREATH_DURATION` giây — dùng
    để đẩy titan RA XA khỏi HQ khi tình huống nguy cấp."""
    COST_TUPLE = ('trap', 'suriken_trap', 1)

    # Skill Wind Breath: tổng lực đẩy ≈ _WIND_PUSH_FORCE px trong suốt
    # _WIND_BREATH_DURATION giây (đẩy dt-scaled mỗi frame) — chỉnh 2 số này để
    # cân bằng. Trước: 1500 (quá mạnh, ~47 ô trong 1s).
    _WIND_PUSH_FORCE     = balance.SURIKEN_WIND_PUSH_FORCE
    _WIND_BREATH_DURATION = balance.SURIKEN_WIND_BREATH_DURATION

    _frames_h = None
    _frames_v = None
    _wind_frames = None

    def __init__(self, x: float, y: float, horizontal: bool = True):
        """Tạo bẫy phi tiêu dài 5 ô. Nạp 2 bộ sprite: phi tiêu (`_frames_h/v`)
        và hiệu ứng gió (`_wind_frames`, bọc try/except vì file "Wind Breath.png"
        có thể thiếu — không có thì hiệu ứng gió không hiển thị nhưng lực
        đẩy vẫn hoạt động). Chỉ số cân bằng: `balance.SURIKEN_TRAP_HP/DAMAGE/
        TICK_RATE/WIND_PUSH_FORCE/WIND_BREATH_DURATION`.
        """
        tw, th = (5, 1) if horizontal else (1, 5)
        super().__init__(x, y, tw, th, horizontal)
        self._hp = balance.SURIKEN_TRAP_HP
        self._max_hp = balance.SURIKEN_TRAP_HP
        self._damage = balance.SURIKEN_TRAP_DAMAGE
        self._tick_timer = 0.0
        self._TICK_RATE = balance.SURIKEN_TRAP_TICK_RATE
        
        self.wind_breath_active = False
        self._wind_breath_timer = 0.0
        self._wind_frame_idx = 0
        self._wind_anim_timer = 0.0
        self._push_dir = (1, 0)
        self._wind_angle = 0
        
        self._anim_timer = 0.0
        self._frame_idx = 0
        self._ANIM_FPS = 15.0

        if SurikenTrap._frames_h is None:
            raw = pygame.image.load(os.path.join(_HERE, 'suriken_trap', 'suriken_trap.png')).convert_alpha()
            frame_h = raw.get_height()
            frame_w = frame_h
            num_frames = raw.get_width() // frame_w
            SurikenTrap._frames_h = []
            SurikenTrap._frames_v = []
            for i in range(num_frames):
                rect = pygame.Rect(i * frame_w, 0, frame_w, frame_h)
                frame_surf = pygame.transform.smoothscale(raw.subsurface(rect), (TILE, TILE))
                SurikenTrap._frames_h.append(frame_surf)
                SurikenTrap._frames_v.append(pygame.transform.rotate(frame_surf, 90))
                
            try:
                wind = pygame.image.load(os.path.join(_HERE, 'suriken_trap', 'Wind Breath.png')).convert_alpha()
                SurikenTrap._wind_frames = []
                fw = 48
                fh = 32
                for i in range(12):
                    rect = pygame.Rect(i*fw, 0, fw, fh)
                    # Scale to 2.5x to make the effect larger
                    f = pygame.transform.smoothscale(wind.subsurface(rect), (int(fw * 1.3), int(fh * 1.3)))
                    SurikenTrap._wind_frames.append(f)
            except:
                pass

    def trigger_wind_breath(self, hq_pos):
        """Kích hoạt kỹ năng đẩy gió, chọn hướng đẩy TỰ ĐỘNG theo hình học.

        Thuật toán: tính vector từ HQ tới tâm bẫy (`vx,vy` chuẩn hoá) — đây
        là "hướng ra xa HQ". Bẫy chỉ đẩy được VUÔNG GÓC với trục dài của nó
        (2 lựa chọn: `px1,py1` hoặc hướng ngược `px2,py2`, cả 2 đều vuông
        góc với `tdx,tdy` — trục dài dải bẫy). Chọn hướng nào có tích vô
        hướng (`dot1`/`dot2`) LỚN HƠN với vector HQ→bẫy — tức là hướng đẩy
        GẦN VỚI "ra xa HQ" nhất trong 2 lựa chọn khả dĩ. `_wind_angle` tính
        từ hướng đẩy để xoay sprite hiệu ứng gió cho khớp.

        Tham số: hq_pos — toạ độ (x,y) hiện tại của HQ (bẫy không giữ tham
        chiếu HQ cố định, nhận mỗi lần kích hoạt để tính đúng hướng).
        """
        self.wind_breath_active = True
        self._wind_breath_timer = self._WIND_BREATH_DURATION
        self._wind_frame_idx = 0
        self._wind_anim_timer = 0.0
        
        cx, cy = self.get_center()
        hqx, hqy = hq_pos
        
        vx, vy = cx - hqx, cy - hqy
        length = math.hypot(vx, vy)
        if length > 0:
            vx, vy = vx/length, vy/length
        else:
            vx, vy = 1, 0
            
        tdx, tdy = (1, 0) if self.horizontal else (0, 1)
        px1, py1 = -tdy, tdx
        px2, py2 = tdy, -tdx
        
        dot1 = px1*vx + py1*vy
        dot2 = px2*vx + py2*vy
        
        if dot1 > dot2:
            self._push_dir = (px1, py1)
        else:
            self._push_dir = (px2, py2)
            
        self._wind_angle = math.degrees(math.atan2(-self._push_dir[1], self._push_dir[0]))

    def update(self, dt: float):
        """Mỗi frame: (1) tick damage định kỳ như ThornTrap (`_apply_damage`).
        (2) animation phi tiêu — chạy NHANH GẤP ĐÔI (+2 frame/tick thay vì +1)
        khi đang thổi gió, tạo cảm giác "gấp gáp" hơn lúc bình thường.
        (3) Nếu `wind_breath_active`: đếm ngược `_wind_breath_timer`, hết giờ
        thì tắt kỹ năng; còn hiệu lực thì với MỌI titan KHÔNG PHẢI boss
        (`is_boss` — boss miễn nhiễm gió) trong bán kính 200px, tính vector
        HQ-tới-titan chuẩn hoá và so `push_dot` (tích vô hướng với
        `_push_dir`) > 0.5 (~60° côn) — titan nằm trong côn hướng gió thổi
        thì bị đẩy `_WIND_PUSH_FORCE * dt` px theo `_push_dir` (dt-scaled,
        không phải xung lực tức thời — đẩy DẦN mỗi frame suốt thời lượng).
        """
        if not self.is_alive: return

        self._tick_timer += dt
        if self._tick_timer >= self._TICK_RATE:
            self._tick_timer -= self._TICK_RATE
            self._apply_damage()

        self._anim_timer += dt
        if self._anim_timer >= 1.0 / self._ANIM_FPS:
            self._anim_timer -= 1.0 / self._ANIM_FPS
            if self.wind_breath_active:
                self._frame_idx = (self._frame_idx + 2) % len(SurikenTrap._frames_h)
            else:
                self._frame_idx = (self._frame_idx + 1) % len(SurikenTrap._frames_h)
                
        if self.wind_breath_active:
            self._wind_breath_timer -= dt
            self._wind_anim_timer += dt
            if self._wind_anim_timer >= 1.0 / 15.0:
                self._wind_anim_timer -= 1.0 / 15.0
                self._wind_frame_idx += 1
                
            if self._wind_breath_timer <= 0:
                self.wind_breath_active = False
            else:
                cx, cy = self.get_center()
                for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
                    if not t.is_alive: continue
                    if getattr(t, 'is_boss', False): continue
                    
                    tcx, tcy = t.x, t.y
                    dist = math.hypot(tcx - cx, tcy - cy)
                    if dist <= 200:
                        tdx, tdy = tcx - cx, tcy - cy
                        tlen = math.hypot(tdx, tdy)
                        if tlen > 0:
                            tdx, tdy = tdx/tlen, tdy/tlen
                            px, py = self._push_dir
                            push_dot = tdx*px + tdy*py
                            if push_dot > 0.5:
                                push_force = self._WIND_PUSH_FORCE * dt
                                t.x += px * push_force
                                t.y += py * push_force

    def _apply_damage(self):
        """Gây `self._damage` cho MỌI titan có tâm nằm trong vùng bẫy MỞ RỘNG
        1 TILE mỗi phía (AABB đơn giản, KHÔNG dùng bán kính titan như
        ThornTrap — vùng test rộng hơn hình chữ nhật vẽ thật để bù việc
        không tính `RADIUS` titan)."""
        cx, cy = self.get_center()
        w = self.tw * TILE
        h = self.th * TILE

        for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
            if not t.is_alive: continue
            tx, ty = t.x, t.y
            if self.x - TILE <= tx <= self.x + w + TILE and self.y - TILE <= ty <= self.y + h + TILE:
                t.take_damage(self._damage, dtype='suriken', attacker=None)

    def draw(self, surface: pygame.Surface):
        """Vẽ dải phi tiêu (như ThornTrap). Nếu `wind_breath_active`, VẼ THÊM
        các frame hiệu ứng gió xoay theo `_wind_angle`, rải dọc dải bẫy với
        mật độ GẤP ĐÔI (bước 16px thay vì 32px) để tạo cảm giác luồng gió
        liên tục dày đặc, dịch theo `_push_dir * TILE` để bắt đầu từ MÉP
        NGOÀI bẫy (không chồng lên sprite phi tiêu)."""
        frames = SurikenTrap._frames_h if self.horizontal else SurikenTrap._frames_v
        if frames:
            frame = frames[self._frame_idx % len(frames)]
            for i in range(5):
                if self.horizontal:
                    surface.blit(frame, (self.x + i * 32 - 12, self.y - 12))
                else:
                    surface.blit(frame, (self.x - 12, self.y + i * 32 - 12))
        else:
            pygame.draw.rect(surface, (255, 0, 255), self.get_rect(), 2)

        if self.wind_breath_active and SurikenTrap._wind_frames:
            w_frame = SurikenTrap._wind_frames[self._wind_frame_idx % len(SurikenTrap._wind_frames)]
            r_frame = pygame.transform.rotate(w_frame, self._wind_angle)
            hw = r_frame.get_width() // 2
            hh = r_frame.get_height() // 2
            
            offset_x = self._push_dir[0] * TILE
            offset_y = self._push_dir[1] * TILE
            
            length = self.tw if self.horizontal else self.th
            # Vẽ gió dày đặc hơn: bước nhảy là 16px (nửa ô) thay vì 32px
            steps = length * 2
            for i in range(steps):
                if self.horizontal:
                    cx = self.x + i * 16 + 16
                    cy = self.y + (self.th * TILE) // 2
                else:
                    cx = self.x + (self.tw * TILE) // 2
                    cy = self.y + i * 16 + 16
                    
                surface.blit(r_frame, (cx + offset_x - hw, cy + offset_y - hh))


# ==============================================================================
# POISON TRAP
# ==============================================================================
class PoisonTrap(Trap):
    """Bẫy độc — 2×2 ô, state machine 'idle'/'poisoning'. KHÁC Thorn/Suriken
    (luôn tick): bẫy độc CHỈ gây damage sau khi bị titan GIẪM TRÚNG 1 lần
    (chuyển 'idle'→'poisoning'), rồi phát nổ animation độc + tick damage
    lặp lại trong suốt animation, tự quay về 'idle' khi animation hết."""
    COST_TUPLE = ('trap', 'poison_trap', 1)
    _frames = None

    def __init__(self, x: float, y: float, horizontal: bool = True):
        """Tạo bẫy độc 2×2 ô (`horizontal` không có tác dụng — bẫy vuông,
        tham số giữ để đồng nhất chữ ký với các Trap khác). Nạp 21 frame
        animation (frame 0-7: idle lặp, frame 8-20: hiệu ứng độc 1 lần).
        Chỉ số cân bằng: `balance.POISON_TRAP_HP/TICK_RATE/TICK_DAMAGE`.
        """
        super().__init__(x, y, tw=2, th=2, horizontal=True)
        self._hp = balance.POISON_TRAP_HP
        self._max_hp = balance.POISON_TRAP_HP
        self._tick_timer = 0.0
        self._TICK_RATE = balance.POISON_TRAP_TICK_RATE
        
        self.state = 'idle'
        self._anim_timer = 0.0
        self._frame_idx = 0
        self._ANIM_FPS = 15.0
        
        if PoisonTrap._frames is None:
            raw = pygame.image.load(os.path.join(_HERE, 'poison_trap', 'poison_trap.png')).convert_alpha()
            frame_h = 64
            frame_w = 96
            num_frames = 21
            PoisonTrap._frames = []
            for i in range(num_frames):
                rect = pygame.Rect(i * frame_w, 0, frame_w, frame_h)
                frame_surf = pygame.transform.smoothscale(raw.subsurface(rect), (2 * TILE, 2 * TILE))
                PoisonTrap._frames.append(frame_surf)

    def update(self, dt: float):
        """State machine 2 trạng thái:

        'idle': animation lặp frame 0-7 liên tục; MỖI frame quét titan giẫm
            trúng (AABB-vs-circle như ThornTrap) → chuyển 'poisoning',
            `_frame_idx=8` (bắt đầu đúng đoạn hiệu ứng độc trong sprite sheet).
        'poisoning': animation chạy MỘT LẦN từ frame 8→20 rồi tự quay lại
            'idle' (`_frame_idx=0`). Trong suốt trạng thái này, cứ 0.5s
            (hardcode, KHÔNG dùng `_TICK_RATE`) quét lại titan trong vùng
            bẫy, gây `balance.POISON_TRAP_TICK_DAMAGE` cho MỖI titan trúng
            — nghĩa là 1 lượt kích hoạt có thể tick NHIỀU LẦN nếu titan
            đứng lại trong bẫy đủ lâu (animation dài hơn 0.5s).
        Mỗi lượt tick trúng titan làm bẫy mất 5 HP/titan (hao mòn theo lượt
        dùng, giống ThornTrap nhưng hệ số 5 thay vì 10).
        """
        if not self.is_alive: return

        self._anim_timer += dt
        if self._anim_timer >= 1.0 / self._ANIM_FPS:
            self._anim_timer -= 1.0 / self._ANIM_FPS
            if self.state == 'idle':
                self._frame_idx = (self._frame_idx + 1) % 8
            elif self.state == 'poisoning':
                self._frame_idx += 1
                if self._frame_idx >= 21:
                    self.state = 'idle'
                    self._frame_idx = 0

        if self.state == 'idle':
            rect = self.get_rect()
            for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
                if not t.is_alive: continue
                tr = getattr(t, 'RADIUS', 24)
                cx = max(rect.left, min(t.x, rect.right))
                cy = max(rect.top, min(t.y, rect.bottom))
                if (t.x - cx)**2 + (t.y - cy)**2 <= tr**2:
                    self.state = 'poisoning'
                    self._frame_idx = 8
                    self._tick_timer = 0.0   # reset nhịp mỗi lần kích hoạt MỚI —
                    break                    # không thì tick độc đầu của lượt sau nổ sớm/tức thì
                    
        if self.state == 'poisoning':
            self._tick_timer += dt
            if self._tick_timer >= 0.5:
                self._tick_timer = 0.0
                rect = self.get_rect()
                hit_count = 0
                for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
                    if not t.is_alive: continue
                    tr = getattr(t, 'RADIUS', 24)
                    cx = max(rect.left, min(t.x, rect.right))
                    cy = max(rect.top, min(t.y, rect.bottom))
                    if (t.x - cx)**2 + (t.y - cy)**2 <= tr**2:
                        t.take_damage(balance.POISON_TRAP_TICK_DAMAGE, dtype='poison', attacker=None)
                        hit_count += 1
                if hit_count > 0:
                    self.take_damage(hit_count * 5)
                    
    def draw(self, surface: pygame.Surface):
        """Vẽ frame hiện tại, dịch (-16,-24)px so với (x,y) vì sprite 96×64
        LỚN HƠN vùng hitbox 2×2 ô (96×96) — offset để hiệu ứng độc lan toả
        trông tự nhiên, không bị cắt cụt ở mép hitbox."""
        if PoisonTrap._frames:
            frame = PoisonTrap._frames[self._frame_idx]
            # Kéo hình ảnh lên trên và sang trái
            surface.blit(frame, (self.x - 16, self.y - 24))
        else:
            pygame.draw.rect(surface, (255, 0, 255), self.get_rect(), 2)


# ==============================================================================
# EXPLODE TRAP
# ==============================================================================
class ExplodeTrap(Trap):
    """Bẫy nổ — 1×1 ô, 1-LẦN-DÙNG-DUY-NHẤT. State machine 4 trạng thái tuần
    tự: 'idle' (chờ) → 'pre_explode' (đếm ngược) → 'explode' (nổ, gây
    damage AoE) → 'post_explode' (tàn dư) → tự huỷ (`take_damage(_hp)`).
    KHÔNG quay lại 'idle' — khác Poison (tuần hoàn được)."""
    COST_TUPLE = ('trap', 'explode_trap', 1)
    _frames_idle = None
    _frames_pre = None
    _frames_exp = None
    _frames_post = None

    def __init__(self, x: float, y: float, horizontal: bool = True):
        """Tạo bẫy nổ 1×1 ô. Nạp 4 dải sprite riêng biệt (idle/pre_explode/
        explode/post_explode — 4 file PNG khác nhau, KHÔNG chung 1 sheet
        như các Trap khác) qua `_load_strip()`. Chỉ số cân bằng:
        `balance.EXPLODE_TRAP_RADIUS/DAMAGE` (HP giữ mặc định 1 từ base
        `Trap.__init__` — bẫy nổ chỉ cần 1 lần kích hoạt là tự huỷ, HP
        không có ý nghĩa "hao mòn" như 3 loại bẫy kia).
        """
        super().__init__(x, y, tw=1, th=1, horizontal=True)
        self.explosion_radius = balance.EXPLODE_TRAP_RADIUS
        self.explosion_damage = balance.EXPLODE_TRAP_DAMAGE

        self.state = 'idle'
        self._anim_timer = 0.0
        self._frame_idx = 0
        self._ANIM_FPS = 10.0

        if ExplodeTrap._frames_idle is None:
            ExplodeTrap._frames_idle = self._load_strip('idle.png', 48)
            ExplodeTrap._frames_pre = self._load_strip('pre_explode.png', 48)
            ExplodeTrap._frames_exp = self._load_strip('explode.png', 48)
            ExplodeTrap._frames_post = self._load_strip('post_explode.png', 48)

    def _load_strip(self, filename, frame_w):
        """Nạp 1 dải sprite từ `explode_trap/<filename>`, cắt theo `frame_w`
        px/frame (chiều cao = nguyên ảnh), scale mỗi frame lên 1.5×TILE để
        hiệu ứng nổ trông to hơn hitbox 1 ô thật (kịch tính hơn)."""
        raw = pygame.image.load(os.path.join(_HERE, 'explode_trap', filename)).convert_alpha()
        num_frames = raw.get_width() // frame_w
        frames = []
        for i in range(num_frames):
            rect = pygame.Rect(i * frame_w, 0, frame_w, raw.get_height())
            frame_surf = pygame.transform.smoothscale(raw.subsurface(rect), (int(TILE * 1.5), int(TILE * 1.5)))
            frames.append(frame_surf)
        return frames

    def update(self, dt: float):
        """Chạy animation frame-by-frame; khi hết dải frame của trạng thái
        HIỆN TẠI thì CHUYỂN SANG trạng thái kế tiếp trong chuỗi idle→
        pre_explode→explode→post_explode→(tự huỷ), reset `_frame_idx=0`
        mỗi lần chuyển (trừ 'idle' tự lặp vô hạn bằng `%=`).

        Điểm mấu chốt: damage AoE chỉ được gây ĐÚNG 1 LẦN — tại thời điểm
        chuyển từ 'explode'→'post_explode' (không phải mỗi frame trong lúc
        'explode'), quét MỌI titan trong `explosion_radius` quanh tâm bẫy
        (khoảng cách tròn thật, không phải AABB) và gây `explosion_damage`
        1 lần/titan. 'idle'→'pre_explode' được kích hoạt khi có titan giẫm
        trúng hitbox (AABB-vs-circle như ThornTrap). Hết 'post_explode' →
        `self.take_damage(self._hp)` ép chết ngay (tự huỷ vĩnh viễn).
        """
        if not self.is_alive: return

        self._anim_timer += dt
        if self._anim_timer >= 1.0 / self._ANIM_FPS:
            self._anim_timer -= 1.0 / self._ANIM_FPS
            self._frame_idx += 1
            
            if self.state == 'idle':
                self._frame_idx %= len(ExplodeTrap._frames_idle)
            elif self.state == 'pre_explode':
                if self._frame_idx >= len(ExplodeTrap._frames_pre):
                    self.state = 'explode'
                    self._frame_idx = 0
            elif self.state == 'explode':
                if self._frame_idx >= len(ExplodeTrap._frames_exp):
                    self.state = 'post_explode'
                    self._frame_idx = 0
                    # Do damage exactly once when moving to post_explode or during explode
                    cx, cy = self.get_center()
                    for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
                        if not t.is_alive: continue
                        if math.hypot(t.x - cx, t.y - cy) <= self.explosion_radius:
                            t.take_damage(self.explosion_damage, dtype='fire', attacker=None)
            elif self.state == 'post_explode':
                if self._frame_idx >= len(ExplodeTrap._frames_post):
                    self.take_damage(self._hp) # Die
                    return

        if self.state == 'idle':
            rect = self.get_rect()
            for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
                if not t.is_alive: continue
                tr = getattr(t, 'RADIUS', 24)
                cx = max(rect.left, min(t.x, rect.right))
                cy = max(rect.top, min(t.y, rect.bottom))
                if (t.x - cx)**2 + (t.y - cy)**2 <= tr**2:
                    self.state = 'pre_explode'
                    self._frame_idx = 0
                    break

    def draw(self, surface: pygame.Surface):
        """Chọn dải sprite theo `state` hiện tại, vẽ frame `_frame_idx` (nếu
        còn trong phạm vi — tránh IndexError khi `update()` vừa tăng
        `_frame_idx` vượt độ dài trước khi chuyển state ở frame kế)."""
        frames = None
        if self.state == 'idle': frames = ExplodeTrap._frames_idle
        elif self.state == 'pre_explode': frames = ExplodeTrap._frames_pre
        elif self.state == 'explode': frames = ExplodeTrap._frames_exp
        elif self.state == 'post_explode': frames = ExplodeTrap._frames_post

        if frames and self._frame_idx < len(frames):
            frame = frames[self._frame_idx]
            surface.blit(frame, (self.x - 12, self.y - 12))
        else:
            pygame.draw.rect(surface, (255, 0, 255), self.get_rect(), 2)


# ==============================================================================
# BAIT TRAP
# ==============================================================================
class BaitTrap(Trap):
    """Bẫy mồi nhử — 3×2 ô, KHÔNG gây damage. Khi kích hoạt, phát "pheromone"
    dụ MỌI titan (không phải boss? — thực ra không lọc boss ở đây, khác
    Suriken) trong bán kính vào CÙNG ZONE bản đồ đi tới đây thay vì tới HQ,
    câu giờ cho phòng tuyến. Máu vô hạn (chỉ chết khi hết `duration`)."""
    COST_TUPLE = ('trap', 'bait_trap', 1)
    _frames = None

    def __init__(self, x: float, y: float, horizontal: bool = True):
        """Tạo bẫy mồi 3×2 ô. `horizontal` không dùng (bẫy không có 2 hướng
        đặt như Thorn/Suriken). Nạp 29 frame (0-2: idle lặp, 3-28: hiệu
        ứng pheromone khi active). Chỉ số cân bằng:
        `balance.BAIT_TRAP_PHEROMONE_RADIUS/DURATION`.
        """
        super().__init__(x, y, tw=3, th=2, horizontal=True)
        self.pheromone_radius = balance.BAIT_TRAP_PHEROMONE_RADIUS
        self.duration = balance.BAIT_TRAP_DURATION
        self.active = False
        self._zone_id = None

        self._anim_timer = 0.0
        self._frame_idx = 0
        self._ANIM_FPS = 10.0

        if BaitTrap._frames is None:
            raw = pygame.image.load(os.path.join(_HERE, 'bait_trap.png')).convert_alpha()
            frame_h = 64
            frame_w = 144
            num_frames = 29
            BaitTrap._frames = []
            for i in range(num_frames):
                rect = pygame.Rect(i * frame_w, 0, frame_w, frame_h)
                frame_surf = pygame.transform.smoothscale(raw.subsurface(rect), (3 * TILE, 2 * TILE))
                BaitTrap._frames.append(frame_surf)

    def get_zone_id(self):
        """Lấy (và cache) ID vùng bản đồ (zone) chứa bẫy — dùng bởi
        `update()` để chỉ dụ titan CÙNG ZONE (qua `WorldQuery.same_zone`),
        tránh titan ở khu vực khác "xuyên tường" bị hút vô lý. Cache 1 lần
        vì vị trí bẫy không đổi sau khi đặt. `hasattr` guard vì
        `same_zone_query` là API tuỳ chọn của WorldQuery (có thể chưa
        implement ở bản đồ đơn giản không chia zone)."""
        if self._zone_id is None:
            # We assume WorldQuery has get_zone(x, y) or similar.
            self._zone_id = WorldQuery.same_zone_query(self.x, self.y) if hasattr(WorldQuery, 'same_zone_query') else None
        return self._zone_id

    def take_damage(self, amount: int, dtype: str = 'physical'):
        """Override CHẶN damage thường — bẫy mồi "bất tử" trước titan.
        CHỈ chấp nhận damage nếu `amount >= 999999` (giá trị đặc biệt dùng
        làm "lệnh ép chết" nội bộ bởi chính `update()` khi hết `duration`,
        xem dưới) — cơ chế "khoá bằng ngưỡng số" thay vì thêm cờ riêng."""
        # Bẫy mồi nhử không nhận sát thương từ Titan, máu vô hạn.
        # Chỉ có thể chết khi bị ép chết bằng code đặc biệt (hết thời gian).
        if amount >= 999999:
            super().take_damage(amount, dtype)

    def update(self, dt: float):
        """State: `active` False→True khi có titan giẫm trúng hitbox (AABB-
        vs-circle như ThornTrap), bắt đầu đếm ngược `duration`.

        Khi `active`: animation chạy 1 LẦN từ frame 3→28 rồi GIỮ NGUYÊN ở
        frame cuối (không có nhánh reset — khác các Trap khác, hiệu ứng
        pheromone "đọng lại" suốt thời gian hiệu lực). `duration -= dt`;
        hết giờ → tự huỷ qua `take_damage(999999)` (né override chặn ở
        trên bằng đúng ngưỡng nó cho phép).

        Thuật toán dụ titan: với mỗi titan còn sống, KHÔNG PHẢI ĐANG bị
        chính bẫy này dụ rồi (`t.bait_target == self` → bỏ qua, tránh gán
        lại lãng phí), nếu khoảng cách tới tâm bẫy ≤ `pheromone_radius` VÀ
        cùng zone bản đồ (nếu `WorldQuery.same_zone` tồn tại — guard
        `hasattr` như trên) thì gán `t.bait_target = self`. Việc titan có
        THỰC SỰ đi tới bẫy hay không do AI titan (`ai.py`) tự đọc thuộc
        tính `bait_target` và ưu tiên nó làm mục tiêu di chuyển — file này
        chỉ "gắn nhãn", không tự điều khiển titan di chuyển.
        """
        if not self.is_alive: return

        self._anim_timer += dt
        if self._anim_timer >= 1.0 / self._ANIM_FPS:
            self._anim_timer -= 1.0 / self._ANIM_FPS
            if not self.active:
                self._frame_idx = (self._frame_idx + 1) % 3
            else:
                self._frame_idx += 1
                if self._frame_idx >= 29:
                    self._frame_idx = 3

        if not self.active:
            rect = self.get_rect()
            for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
                if not t.is_alive: continue
                tr = getattr(t, 'RADIUS', 24)
                cx = max(rect.left, min(t.x, rect.right))
                cy = max(rect.top, min(t.y, rect.bottom))
                if (t.x - cx)**2 + (t.y - cy)**2 <= tr**2:
                    self.active = True
                    self._frame_idx = 3
                    break
        else:
            self.duration -= dt
            if self.duration <= 0:
                self.take_damage(999999)
                return
                
            cx, cy = self.get_center()
            for t in [t for t in WorldQuery.all() if getattr(t, 'ENTITY_TYPE', None) == 'titan']:
                if not t.is_alive: continue
                if getattr(t, 'bait_target', None) == self:
                    continue
                
                if math.hypot(t.x - cx, t.y - cy) <= self.pheromone_radius:
                    if hasattr(WorldQuery, 'same_zone'):
                        if WorldQuery.same_zone(cx, cy, t.x, t.y):
                            t.bait_target = self
                    else:
                        t.bait_target = self

    def draw(self, surface: pygame.Surface):
        """Vẽ sprite bẫy (offset -24,-32px bù kích thước sprite lớn hơn
        hitbox 3×2 ô). Nếu `active`, vẽ THÊM viền tròn hồng bán kính
        `pheromone_radius` (chỉ viền, không tô) để người chơi thấy rõ vùng
        hiệu lực dụ titan."""
        if BaitTrap._frames:
            frame = BaitTrap._frames[self._frame_idx]
            # Kéo hình ảnh lên trên và sang trái
            surface.blit(frame, (self.x - 24, self.y - 32))
        else:
            pygame.draw.rect(surface, (255, 0, 255), self.get_rect(), 2)

        if self.active:
            pygame.draw.circle(surface, (255, 100, 200), self.get_center(), int(self.pheromone_radius), 1)
