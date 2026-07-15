import os
import math
import pygame
from core.event_bus import GameEventBus
from systems.world_query import WorldQuery
from characters.commanders.commander import Commander
from config import balance
from characters.commanders.assets_config import (
    FRAME_HEIGHT_EREN,
    FRAME_WIDTH_EREN,
    EREN_SPRITE_FRAMES,
)
import logging
logger = logging.getLogger(__name__)

_SPRITES_DIR = os.path.join(os.path.dirname(__file__), "sprites", "Eren")


class ErenCommander(Commander):
    """Tướng Eren Yeager — mở khoá ở Màn 2. Có khả năng hoá Titan."""

    NAME = "Eren Yeager"
    STAGE = 2

    SPRITE_FOLDER = _SPRITES_DIR
    SPRITE_FRAMES = EREN_SPRITE_FRAMES
    FRAME_WIDTH = FRAME_WIDTH_EREN
    FRAME_HEIGHT = FRAME_HEIGHT_EREN

    SKILL_COOLDOWNS = balance.EREN_SKILL_COOLDOWNS

    # Cấp yêu cầu để dùng skill — chỉnh ở đây nếu cần cân bằng lại.
    # "E" chỉ áp dụng cho E TRONG dạng titan (titan cuồng nộ, _titan_e_rage) —
    # E ở dạng người (móc câu/lướt, begin_aim) đi đường khác, KHÔNG qua
    # use_skill() nên không bị khoá bởi mốc này.
    SKILL_UNLOCK_LEVEL = balance.EREN_SKILL_UNLOCK_LEVEL

    # Titan Form Config
    TITAN_MAX_HP = balance.EREN_TITAN_MAX_HP
    TITAN_Q_DASH_SPEED = balance.EREN_TITAN_Q_DASH_SPEED
    TITAN_Q_DASH_DUR = balance.EREN_TITAN_Q_DASH_DUR
    TITAN_Q_DAMAGE = balance.EREN_TITAN_Q_DAMAGE
    TITAN_Q_RADIUS = balance.EREN_TITAN_Q_RADIUS
    
    TITAN_E_RAGE_DUR = balance.EREN_TITAN_E_RAGE_DUR
    TITAN_E_RAGE_DRAIN = balance.EREN_TITAN_E_RAGE_DRAIN  # HP drained per second
    TITAN_E_AURA_RADIUS = balance.EREN_TITAN_E_AURA_RADIUS
    TITAN_E_AURA_DAMAGE = balance.EREN_TITAN_E_AURA_DAMAGE # damage per tick (0.5s)
    
    # Sprite layout for LPC
    _WALK_ROWS   = {0: 8,  1: 9,  2: 10, 3: 11}
    _RUN_ROWS    = {0: 38, 1: 39, 2: 40, 3: 41}
    _ATTACK_ROWS = {0: 12, 1: 13, 2: 14, 3: 15}
    _WALK_FRAMES   = 9
    _RUN_FRAMES    = 8
    _ATTACK_FRAMES = 6
    _FRAME_SIZE    = 64
    _ANIM_FPS      = 10
    _ATTACK_FPS    = 18
    _DISPLAY_SIZE  = 120   # Titan display size
    
    def __init__(self, x: float, y: float, level: int = 1, xp: int = 0, *, headless: bool = False) -> None:
        """Khởi tạo Eren — thêm state DẠNG NGƯỜI + DẠNG TITAN (2 "thân xác" song song.

        Eren là tướng DUY NHẤT có khả năng biến hình. Ngoài state của Commander
        base, class này quản lý CẢ MỘT BỘ state riêng cho dạng titan (đánh dấu
        tiền tố `_titan_*`): HP riêng (`_titan_hp`), animation riêng (walk/attack
        4 hướng, KHÔNG dùng chung `_animator` của dạng người), và cờ nổi khùng
        `is_enraged` (đổi sprite sang bản giận dữ).

        `_q_aiming` — skill Q dạng người dùng cơ chế "GIỮ PHÍM để ngắm, THẢ để lướt".
        `_kb_*` — knockback riêng (trùng tên với base nhưng đây LÀ override, không
        phải field mới — Commander base không có sẵn field này).

        Gọi `_load_titan_sprites()` ngay trong `__init__` (KHÔNG lazy như hầu hết
        chỗ khác trong game) vì Eren luôn cần cả 2 bộ sprite từ đầu.

        Chỉ số: balance.EREN_TITAN_MAX_HP.
        """
        super().__init__(x, y, level, xp, headless=headless)
        self.is_in_titan_form = False
        self._titan_hp = 0
        self.is_enraged = False
        
        self._kb_timer = 0.0
        self._kb_vx = 0.0
        self._kb_vy = 0.0
        
        self._q_aiming = False
        
        self._titan_sheet = None
        self._titan_angry_sheet = None
        
        self._titan_direction = 2
        self._titan_is_moving = False
        self._titan_is_attacking = False
        self._titan_anim_col = 0
        self._titan_anim_timer = 0.0
        self._titan_attack_anim_timer = 0.0
        self._titan_q_timer = 0.0
        self._titan_q_vx = 0.0
        self._titan_q_vy = 0.0
        
        self._titan_e_timer = 0.0
        self._titan_e_aura_tick = 0.0
        
        self._load_titan_sprites()
        
    def _load_titan_sprites(self) -> None:
        """Nạp 3 spritesheet dạng titan: bình thường, GIẬN DỮ, và hiệu ứng Thunderstrike.

        Thuật toán:
          1. `eren.png` → `_titan_sheet` (dạng titan thường).
          2. `angry_eren.png` → `_titan_angry_sheet` (dùng khi `is_enraged`,
             skill E "cuồng nộ" — xem `_titan_e_rage`).
          3. `Thunderstrike w blur.png` — sheet 13 frame 64×64, CẮT RIÊNG TỪNG Ô
             rồi scale lên 256×256 ngay lúc nạp (không scale mỗi frame draw) →
             `_thunder_frames`. Đây là hiệu ứng sét đánh khi vào dạng titan.
          4. File Thunderstrike không tồn tại → `_thunder_frames = []` (bỏ qua
             hiệu ứng, không crash).
          5. Lỗi bất kỳ (thiếu file eren.png/angry_eren.png) → log lỗi, để None
             (draw() titan form sẽ không vẽ được, nhưng game không crash).

        Không giống hầu hết `_load_sprite()` khác trong hệ thống, hàm này KHÔNG
        lazy — được gọi ngay trong `__init__`.
        """
        try:
            path_normal = os.path.join(self.SPRITE_FOLDER, 'eren.png')
            self._titan_sheet = pygame.image.load(path_normal).convert_alpha()
            path_angry = os.path.join(self.SPRITE_FOLDER, 'angry_eren.png')
            self._titan_angry_sheet = pygame.image.load(path_angry).convert_alpha()
            
            # Load Thunderstrike
            thunder_path = os.path.join(self.SPRITE_FOLDER, 'Thunderstrike w blur.png')
            self._thunder_frames = []
            if os.path.exists(thunder_path):
                thunder_sheet = pygame.image.load(thunder_path).convert_alpha()
                for i in range(13):
                    rect = pygame.Rect(i * 64, 0, 64, 64)
                    surf = thunder_sheet.subsurface(rect)
                    surf = pygame.transform.scale(surf, (256, 256))
                    self._thunder_frames.append(surf)
                    
        except Exception as e:
            logger.error("ErenCommander failed to load titan sprites: %s", e)
            self._thunder_frames = []
            
        self._thunder_anim_idx = -1
        self._thunder_anim_timer = 0.0
        self._THUNDER_FPS = 10.0
            
    def _get_titan_frame(self, row: int, col: int = 0):
        """Cắt ô (row, col) khỏi ĐÚNG SHEET theo trạng thái (bình thường hay giận dữ).

        Thuật toán: `sheet = _titan_angry_sheet if is_enraged else _titan_sheet`
        — chọn sheet TRƯỚC khi cắt, nên caller không cần biết Eren đang giận hay
        không, chỉ cần gọi hàm này. Cắt xong scale thẳng lên `_DISPLAY_SIZE` (120px).

        Bọc `ValueError` (subsurface ngoài biên sheet, vd row/col sai) → trả None
        thay vì crash.
        """
        sheet = self._titan_angry_sheet if self.is_enraged else self._titan_sheet
        if sheet is None:
            return None
        rect = pygame.Rect(col * self._FRAME_SIZE, row * self._FRAME_SIZE,
                           self._FRAME_SIZE, self._FRAME_SIZE)
        try:
            surface = sheet.subsurface(rect)
            return pygame.transform.scale(surface, (self._DISPLAY_SIZE, self._DISPLAY_SIZE))
        except ValueError:
            return None
            
    def _titan_update_anim(self, dt: float) -> None:
        """Máy trạng thái animation RIÊNG cho dạng titan: đánh > đi > đứng yên.

        Độc lập hoàn toàn với `_animator` của dạng người — dạng titan tự quản lý
        `_titan_anim_col`/`_titan_anim_timer` bằng tay (không dùng
        `CommanderAnimator`). Cấu trúc giống mẫu chung của titan.py (đánh xong tự
        tắt cờ + reset cột).
        """
        if self._titan_is_attacking:
            self._titan_attack_anim_timer += dt
            if self._titan_attack_anim_timer >= 1.0 / self._ATTACK_FPS:
                self._titan_attack_anim_timer = 0.0
                self._titan_anim_col += 1
                if self._titan_anim_col >= self._ATTACK_FRAMES:
                    self._titan_anim_col = 0
                    self._titan_is_attacking = False
        else:
            if self._titan_is_moving:
                self._titan_anim_timer += dt
                if self._titan_anim_timer >= 1.0 / self._ANIM_FPS:
                    self._titan_anim_timer = 0.0
                    self._titan_anim_col = (self._titan_anim_col + 1) % self._WALK_FRAMES
            else:
                self._titan_anim_col = 0
                self._titan_anim_timer = 0.0

    def update(self, dt: float) -> None:
        """Vòng update ĐẶC BIỆT của Eren — chạy dạng NGƯỜI hay dạng TITAN tuỳ `is_in_titan_form`.

        Đây là override PHỨC TẠP NHẤT trong toàn hệ thống commander, vì nó phải
        lo CẢ 2 "thân xác" trong cùng 1 hàm.

        Thuật toán, theo thứ tự (chạy MỌI LÚC bất kể dạng nào):
          1. Animation hiệu ứng Thunderstrike (đồ hoạ, không phụ thuộc dạng).
          2. **Q dạng "giữ để ngắm"**: đang `_q_aiming` mà NGƯỜI CHƠI VỪA NHẢ phím
             Q → `_execute_q_dash()` NGAY (không cần đợi frame update tiếp theo —
             đọc bàn phím trực tiếp qua `pygame.key.get_pressed()`).
          3. **Q đang lướt Ở DẠNG NGƯỜI** (`_titan_q_timer > 0` và không phải dạng
             titan): dịch chuyển theo `_titan_q_vx/vy`, kiểm tra tường (kẹt tường
             → dừng lướt ngay), gây damage NHẸ (`TITAN_Q_DAMAGE // 2`, bán kính
             CHỈ BẰNG NỬA `TITAN_Q_RADIUS`) cho titan trên đường — Q dạng người
             yếu hơn Q dạng titan nhưng vẫn gây sát thương dọc đường lướt.

          4. **KHÔNG ở dạng titan** → `super().update(dt)` (vòng update chuẩn của
             Commander) rồi `return` NGAY — phần còn lại của hàm CHỈ dành cho dạng titan.

          5. ═══ TỪ ĐÂY LÀ LOGIC DẠNG TITAN — KHÔNG gọi `super().update()` ═══
             a. Đã chết (`not is_alive`) → `_exit_titan_form()`, thoát.
             b. Tự tay đếm ngược cooldown skill + `_combo_anim_left` +
                `_inv_timer` (vì bước 4 đã bỏ qua `super().update()`, nên các
                timer chung của Commander base KHÔNG được tick tự động — Eren
                dạng titan phải TỰ LÀM LẠI việc này).
             c. Nhớ vị trí frame trước (`_last_titan_x/y`) để tính hướng di chuyển
                sau khi mọi thứ (kể cả input WASD từ game.py) đã áp dụng.
             d. **Q dạng titan đang lướt** (`_titan_q_timer > 0`): dịch chuyển theo
                vận tốc lướt, gây damage ĐẦY ĐỦ `TITAN_Q_DAMAGE` (×2 nếu
                `is_enraged`) cho MỌI titan trong `TITAN_Q_RADIUS` DỌC ĐƯỜNG lướt
                (không chỉ điểm cuối). Hết lướt → `_find_safe_landing()` đẩy ra
                nếu đáp trúng trong tường (giống cơ chế đu dây ODM của người).
             e. Không lướt mà đang bị knockback (`_kb_timer > 0`) → trôi theo
                vận tốc knockback.
             f. Không cả 2 → có `_move_target` → đi bộ tới đó (tốc độ ×1.5 nếu
                `is_enraged`), kiểm tra tường mỗi bước.
             g. Suy ra HƯỚNG NHÌN + cờ `_titan_is_moving` từ ĐỘ DỊCH CHUYỂN thật
                (so `old_x/y` với vị trí mới) — không suy từ input, vì vị trí có
                thể bị game.py ghi đè trực tiếp qua WASD.
             h. **NỔI KHÙNG** (`is_enraged`, do skill E kích hoạt): đếm ngược
                `_titan_e_timer`; TỰ TRỪ MÁU liên tục (`TITAN_E_RAGE_DRAIN` mỗi
                giây — cái giá của sức mạnh); cứ 0.5s giật 1 nhịp damage AoE
                (`TITAN_E_AURA_DAMAGE`) quanh bán kính `TITAN_E_AURA_RADIUS`.
                Hết timer → tự tắt khùng.
             i. `_titan_hp <= 0` (do tự trừ máu enrage HOẶC bị đánh) →
                `_exit_titan_form()`, thoát.
             j. `_titan_update_anim(dt)` — chạy animation dạng titan.

        Chỉ số: balance.EREN_TITAN_Q_DASH_SPEED/_DAMAGE/_RADIUS, balance.EREN_TITAN_E_RAGE_DUR/
        _RAGE_DRAIN/_AURA_RADIUS/_AURA_DAMAGE.
        """
        # Xử lý Thunder animation
        if getattr(self, '_thunder_anim_idx', -1) >= 0:
            self._thunder_anim_timer += dt
            if self._thunder_anim_timer >= 1.0 / getattr(self, '_THUNDER_FPS', 10.0):
                self._thunder_anim_timer = 0.0
                self._thunder_anim_idx += 1
                if self._thunder_anim_idx >= len(self._thunder_frames):
                    self._thunder_anim_idx = -1
                    
        # Xử lý logic nhả phím Q (Hold to aim)
        if getattr(self, '_q_aiming', False):
            keys = pygame.key.get_pressed()
            if not keys[pygame.K_q]:
                self._execute_q_dash()
                
        # Dạng người cũng cần lướt Q (nếu timer > 0)
        if getattr(self, '_titan_q_timer', 0) > 0 and not self.is_in_titan_form:
            self._titan_q_timer -= dt
            nx = self.x + getattr(self, '_titan_q_vx', 0) * dt
            ny = self.y + getattr(self, '_titan_q_vy', 0) * dt
            if not WorldQuery.is_wall_blocked(nx, ny, radius=20.0, extend_down=48.0):
                self.x, self.y = nx, ny
            else:
                self._titan_q_timer = 0  # Dạng người lướt kẹt tường thì dừng lại
            
            # Gây sát thương nhẹ cho bầy Titan trên đường lướt
            for titan in WorldQuery.find_in_radius(cx=self.x, cy=self.y,
                                                   radius=self.TITAN_Q_RADIUS * 0.5,
                                                   entity_type="titan"):
                titan.take_damage(amount=self.TITAN_Q_DAMAGE // 2, dtype="slash", attacker=self)
                
            if self._titan_q_timer <= 0:
                self._titan_q_timer = 0
                if self._animator.state == "skill_q":
                    self._animator.set_state("idle")
                    
        if not self.is_in_titan_form:
            super().update(dt)
            return
            
        # TITAN FORM UPDATE
        if not self.is_alive:
            self._exit_titan_form()
            return
            
        # Update cooldowns manually (since we skip super().update(dt))
        for key in list(self._skill_cd.keys()):
            if self._skill_cd[key] > 0:
                self._skill_cd[key] = max(0.0, self._skill_cd[key] - dt)
                
        # Also update generic entity cooldowns (combo_anim, invincibility)
        if self._combo_anim_left > 0:
            self._combo_anim_left -= dt
        if self._inv_timer > 0:
            self._inv_timer -= dt
            if self._inv_timer <= 0:
                self._invincible = False

        # Suy giảm stack-damage & combo Ở DẠNG TITAN — super().update() bị bỏ qua
        # nên phải tick tay (giống Commander.update); thiếu thì stack giữ mãi tới
        # 2.5× và combo đông cứng dù ngừng đánh → đòn đấm phồng damage vô thời hạn.
        if self._combo_reset_left > 0:
            self._combo_reset_left = max(0.0, self._combo_reset_left - dt)
            if self._combo_reset_left == 0:
                self._combo_step = 0
        if self._titan_stack_timer > 0:
            self._titan_stack_timer = max(0.0, self._titan_stack_timer - dt)
            if self._titan_stack_timer == 0.0:
                self._titan_stack = 0
        
        # Lấy toạ độ từ frame trước (vì game.py có thể đã thay đổi x, y qua WASD)
        old_x = getattr(self, '_last_titan_x', self.x)
        old_y = getattr(self, '_last_titan_y', self.y)
        self._titan_is_moving = False
        
        if getattr(self, '_titan_q_timer', 0) > 0:
            # Dashing
            self._titan_q_timer -= dt
            self.x += self._titan_q_vx * dt
            self.y += self._titan_q_vy * dt
            
            # Deal damage to enemies in path
            for titan in WorldQuery.find_in_radius(cx=self.x, cy=self.y,
                                                   radius=self.TITAN_Q_RADIUS,
                                                   entity_type="titan"):
                dmg = self.TITAN_Q_DAMAGE * (2 if self.is_enraged else 1)
                titan.take_damage(amount=dmg, dtype="strike", attacker=self)
                
            if self._titan_q_timer <= 0:
                self._titan_q_timer = 0
                self._titan_is_attacking = False
                # Trượt ra khỏi tường nếu điểm đáp nằm bên trong tường (giống đu dây ODM)
                self.x, self.y = self._find_safe_landing(self.x, self.y)
                
        elif self._kb_timer > 0:
            self._kb_timer -= dt
            self.x += self._kb_vx * dt
            self.y += self._kb_vy * dt
        elif self._move_target is not None:
            dx_tgt = self._move_target[0] - self.x
            dy_tgt = self._move_target[1] - self.y
            dist = math.hypot(dx_tgt, dy_tgt)
            speed = self._speed * (1.5 if self.is_enraged else 1.0)
            step = speed * dt
            
            if dist <= step:
                nx, ny = self._move_target[0], self._move_target[1]
                if not WorldQuery.is_wall_blocked(nx, ny, radius=20.0, extend_down=48.0):
                    self.x, self.y = nx, ny
                    self._move_target = None
                else:
                    self._move_target = None
            else:
                nx = self.x + (dx_tgt / dist) * step
                ny = self.y + (dy_tgt / dist) * step
                if not WorldQuery.is_wall_blocked(nx, ny, radius=20.0, extend_down=48.0):
                    self.x = nx
                    self.y = ny
                else:
                    self._move_target = None
                
        # Direction and movement detection
        dx = self.x - old_x
        dy = self.y - old_y
        if abs(dx) > 0.01 or abs(dy) > 0.01:
            self._titan_is_moving = True
            if abs(dx) > abs(dy):
                self._titan_direction = 1 if dx < 0 else 3
            else:
                self._titan_direction = 0 if dy < 0 else 2
                
        # Lưu lại cho frame sau
        self._last_titan_x = self.x
        self._last_titan_y = self.y
                
        # Handle Enrage
        if self.is_enraged:
            self._titan_e_timer -= dt
            self._titan_e_aura_tick += dt
            self._titan_hp -= self.TITAN_E_RAGE_DRAIN * dt
            
            if self._titan_e_aura_tick >= 0.5:
                self._titan_e_aura_tick = 0.0
                for titan in WorldQuery.find_in_radius(cx=self.x, cy=self.y,
                                                       radius=self.TITAN_E_AURA_RADIUS,
                                                       entity_type="titan"):
                    titan.take_damage(amount=self.TITAN_E_AURA_DAMAGE, dtype="magic", attacker=self)
            
            if self._titan_e_timer <= 0:
                self.is_enraged = False
                
        if self._titan_hp <= 0:
            self._exit_titan_form()
            return
            
        self._titan_update_anim(dt)
        

    def draw(self, screen) -> None:
        """Vẽ dạng NGƯỜI (uỷ quyền cho base) HOẶC dạng TITAN (vẽ hoàn toàn riêng).

        Không phải titan → `super().draw()` rồi thoát NGAY — mọi thứ dưới đây
        CHỈ chạy cho dạng titan.

        Thứ tự vẽ dạng titan (dưới lên trên):
          1. Frame titan (attack hoặc walk theo `_titan_direction`), scale sẵn
             `_DISPLAY_SIZE`, neo LỆCH lên trên (y - DISPLAY_SIZE + 20, không phải
             midbottom) vì sprite titan cao hơn nhiều so với dạng người.
          2. HP bar RIÊNG cho dạng titan (đỏ, tỉ lệ `_titan_hp/TITAN_MAX_HP`) —
             KHÁC HP bar dạng người.
          3. Thanh hồi đòn — TÁI DÙNG `_draw_recovery_bar()` của Commander base
             (dạng titan cũng có combo "gồng đòn" giống dạng người, vì
             `basic_attack()` nhánh titan gọi `super().basic_attack()`).
          4. Hiệu ứng Thunderstrike (nếu đang chạy animation sét).
          5. **Đang giữ Q để ngắm** (`_q_aiming`): vẽ tia đỏ từ tướng tới chuột +
             vòng tròn ở điểm đáp — cho người chơi thấy trước sẽ lướt bao xa.
             Tầm lướt = `TITAN_Q_DASH_SPEED × TITAN_Q_DASH_DUR`; DẠNG NGƯỜI lướt
             chỉ bằng NỬA tầm titan (`×0.5`).
          6. Đang trong combo animation → vẽ vùng đánh (`_draw_attack_cone`).

        CHỈ ĐỒ HOẠ — không đổi logic.
        """
        if not self.is_in_titan_form:
            super().draw(screen)
            return

        if self._titan_is_attacking:
            row = self._ATTACK_ROWS.get(self._titan_direction, 14)
        else:
            row = self._WALK_ROWS.get(self._titan_direction, 10)
            
        frame = self._get_titan_frame(row, self._titan_anim_col)
        if frame:
            sx = int(self.x - self._DISPLAY_SIZE // 2)
            sy = int(self.y - self._DISPLAY_SIZE + 20)
            screen.blit(frame, (sx, sy))
            
        # Draw Titan HP Bar
        bar_w = 80
        ratio = max(0.0, min(1.0, self._titan_hp / self.TITAN_MAX_HP))
        bx = int(self.x - bar_w // 2)
        by = int(self.y - self._DISPLAY_SIZE + 10)
        pygame.draw.rect(screen, (80, 20, 20), (bx, by, bar_w, 8))
        pygame.draw.rect(screen, (220, 40, 40), (bx, by, int(bar_w * ratio), 8))

        # Thanh hồi đòn (mảnh, trắng) — dạng titan cũng có gồng đòn giống dạng
        # người (basic_attack() nhánh titan chỉ đổi tạm BASIC_ATTACK_* rồi gọi
        # super().basic_attack(), dùng chung _attack_recovery_gate()).
        self._draw_recovery_bar(screen, bx, by - 6, bar_w)

        # Draw Thunderstrike effect
        if getattr(self, '_thunder_anim_idx', -1) >= 0 and getattr(self, '_thunder_frames', []):
            idx = self._thunder_anim_idx
            if idx < len(self._thunder_frames):
                frame = self._thunder_frames[idx]
                fx = int(self.x - 128)
                fy = int(self.y - 256 + 40)  # +40 to anchor near feet
                
                # Vẽ phần gốc của vụ nổ sét
                screen.blit(frame, (fx, fy))
        
        # Vẽ tia aim nếu đang giữ Q
        if getattr(self, '_q_aiming', False):
            mx, my = pygame.mouse.get_pos()
            cx = int(self.x)
            cy = int(self.y)
            
            # Tính khoảng cách lướt
            range_len = self.TITAN_Q_DASH_SPEED * self.TITAN_Q_DASH_DUR
            if not self.is_in_titan_form:
                range_len *= 0.5  # Dạng người lướt ngắn hơn (50%)
                cy -= 40
            else:
                cy -= self._DISPLAY_SIZE // 2 - 20
                
            dx = mx - cx
            dy = my - cy
            dist = math.hypot(dx, dy)
            if dist > 0:
                end_x = cx + (dx/dist) * range_len
                end_y = cy + (dy/dist) * range_len
                pygame.draw.line(screen, (255, 100, 100), (cx, cy), (int(end_x), int(end_y)), 3)
                pygame.draw.circle(screen, (255, 50, 50), (int(end_x), int(end_y)), int(self.TITAN_Q_RADIUS), 1)

        if self._combo_anim_left > 0:
            self._draw_attack_cone(screen)

    def _draw_attack_cone(self, screen) -> None:
        """Vẽ vùng đánh — dạng người dùng hình tam giác của base; dạng titan dùng NỬA HÌNH TRÒN (180°).

        Không phải titan → `super()._draw_attack_cone()`. Dạng titan: vẽ cung 180°
        (16 đoạn thẳng nối thành polygon xấp xỉ nửa hình tròn) bán kính
        `TITAN_Q_RADIUS × 1.5`, hướng theo `_titan_direction` (0=Bắc/1=Tây/2=Nam/3=Đông
        → góc -90°/180°/90°/0°). Vùng RỘNG HƠN HẲN dạng người — đấm titan là đòn diện rộng.
        CHỈ ĐỒ HOẠ.
        """
        if not self.is_in_titan_form:
            super()._draw_attack_cone(screen)
            return

        import math
        import pygame
        # Titan form 180 degrees (half = 90)
        half = math.radians(90)
        r = int(self.TITAN_Q_RADIUS * 1.5)
        
        ox = int(self.x)
        oy = int(self.y - self._DISPLAY_SIZE // 2 + 20)
        
        # Determine base angle from direction (0: UP, 1: LEFT, 2: DOWN, 3: RIGHT)
        if self._titan_direction == 0:
            base_angle = -math.pi / 2
        elif self._titan_direction == 1:
            base_angle = math.pi
        elif self._titan_direction == 2:
            base_angle = math.pi / 2
        else:
            base_angle = 0
            
        points = [(ox, oy)]
        # Draw an arc by calculating points along the curve
        segments = 16
        start_ang = base_angle - half
        end_ang = base_angle + half
        for i in range(segments + 1):
            ang = start_ang + (end_ang - start_ang) * (i / segments)
            px = ox + int(r * math.cos(ang))
            py = oy + int(r * math.sin(ang))
            points.append((px, py))
            
        try:
            pygame.draw.polygon(screen, (255, 100, 100), points, 2)
        except pygame.error:
            pass

    def _in_attack_cone(self, tx: float, ty: float, body_radius: float = 0.0) -> bool:
        """Kiểm tra va chạm THẬT của đòn đấm — bản 180° khớp với vùng vẽ ở dạng titan.

        Không phải titan → uỷ quyền cho `super()`. Dạng titan:
          1. Loại xa ngay nếu khoảng cách trừ `body_radius` vượt `BASIC_ATTACK_RADIUS`.
          2. Tính góc thật `atan2(dy,dx)`, so lệch góc với `base_angle` (theo
             hướng nhìn) — `diff` chuẩn hoá về [-π, π] bằng công thức modulo.
          3. `|diff| <= half_angle_rad` (90°, tức NỬA VÒNG TRÒN) → trúng.
          4. **Trường hợp đặc biệt point-blank**: dù lệch góc, nếu khoảng cách
             (trừ body_radius) <= `BASIC_ATTACK_MIN_LATERAL_PX` → VẪN trúng — đứng
             quá sát tướng thì luôn dính đòn bất kể hướng, không có "góc chết" khi
             kề vai sát cánh.

        Trả về: bool — True = mục tiêu (tx,ty) nằm trong vùng đánh.
        """
        if not self.is_in_titan_form:
            return super()._in_attack_cone(tx, ty, body_radius)

        import math
        dx = tx - self.x
        oy = self.y - self._DISPLAY_SIZE / 2 + 20
        dy = ty - oy
        
        dist = math.hypot(dx, dy)
        if dist - body_radius > self.BASIC_ATTACK_RADIUS:
            return False
            
        if self._titan_direction == 0:
            base_angle = -math.pi / 2
        elif self._titan_direction == 1:
            base_angle = math.pi
        elif self._titan_direction == 2:
            base_angle = math.pi / 2
        else:
            base_angle = 0
            
        angle = math.atan2(dy, dx)
        diff = (angle - base_angle + math.pi) % (2 * math.pi) - math.pi
        
        half_angle_rad = math.radians(self.BASIC_ATTACK_CONE_HALF_ANGLE_DEG)
        if abs(diff) <= half_angle_rad:
            return True
            
        if dist <= body_radius + self.BASIC_ATTACK_MIN_LATERAL_PX:
            return True
            
        return False

    def basic_attack(self) -> None:
        """Đòn đấm thường — dạng titan MƯỢN hẳn combo logic của Commander base
        bằng cách TẠM GHI ĐÈ 3 hằng class rồi gọi `super()`.

        Kỹ thuật (không phải kiến trúc "sạch" nhưng hiệu quả, TRÁNH TRÙNG LẶP code):
          1. Lưu 3 giá trị GỐC: `BASIC_ATTACK_CONE_HALF_ANGLE_DEG`, `_RADIUS`, `_DAMAGES`.
          2. GHI ĐÈ TẠM THỜI thành số của DẠNG TITAN: góc 90° (nửa vòng tròn),
             bán kính `TITAN_Q_RADIUS × 1.5`, damage `(80, 80, 120)` (số cứng,
             không nằm trong balance.py).
          3. Gọi `super().basic_attack()` — chạy TOÀN BỘ logic combo/stack/cooldown
             gốc của Commander, nhưng với 3 con số vừa ghi đè.
          4. TRẢ LẠI 3 giá trị gốc ngay sau đó — vì đây là ATTRIBUTE CẤP CLASS,
             không trả lại sẽ làm rò rỉ số dạng titan sang MỌI lần gọi tiếp theo
             (kể cả dạng người) — cực kỳ quan trọng để không có bug.
          5. So `_combo_step` trước/sau: đổi khác nghĩa là đòn ĐÃ THỰC SỰ ra (không
             bị `_attack_recovery_gate()` chặn) → mới bật animation đấm dạng titan
             + phát âm thanh (base không biết gì về animation dạng titan riêng).

        Không phải dạng titan → gọi thẳng `super().basic_attack()`, không có mẹo gì.
        """
        if self.is_in_titan_form:
            old_angle = self.BASIC_ATTACK_CONE_HALF_ANGLE_DEG
            old_radius = self.BASIC_ATTACK_RADIUS
            old_damages = self.BASIC_ATTACK_DAMAGES
            
            # Titan form: nửa hình tròn (180 độ -> half angle = 90)
            self.BASIC_ATTACK_CONE_HALF_ANGLE_DEG = 90.0
            self.BASIC_ATTACK_RADIUS = int(self.TITAN_Q_RADIUS * 1.5)
            self.BASIC_ATTACK_DAMAGES = (80, 80, 120)
            
            old_step = self._combo_step
            super().basic_attack()
            
            self.BASIC_ATTACK_CONE_HALF_ANGLE_DEG = old_angle
            self.BASIC_ATTACK_RADIUS = old_radius
            self.BASIC_ATTACK_DAMAGES = old_damages
            
            # Chỉ kích hoạt animation chém của Titan nếu đòn đánh thực sự được tung ra
            if self._combo_step != old_step:
                self._titan_is_attacking = True
                from systems.sound_system import SoundManager
                SoundManager.get_instance().play('eren_titan_punch', self.x, self.y)
                self._titan_anim_col = 0
                self._titan_attack_anim_timer = 0.0
        else:
            super().basic_attack()

    def _activate_skill(self, skill_id: str) -> None:
        """Dispatch Q/E/R — Ý NGHĨA KHÁC HẲN nhau tuỳ đang ở dạng NGƯỜI hay TITAN.

        DẠNG NGƯỜI:
            Q → bật `_q_aiming` (bắt đầu ngắm lướt, thực thi khi nhả phím — xem
                `update()`). Chỉ bật nếu Q hết cooldown.
            E → `begin_aim()` (kế thừa từ Commander base — móc câu/lướt ODM, HOÀN
                TOÀN KHÔNG liên quan tới `_titan_e_rage`. `SKILL_UNLOCK_LEVEL['E']`
                CHỈ áp cho E-trong-dạng-titan, nên móc câu này KHÔNG bao giờ bị khoá).
            R → `_enter_titan_form()` — BIẾN HÌNH.

        DẠNG TITAN:
            Q → giống hệt dạng người (lướt nắm đấm), nhưng tốc độ/tầm khác (xem
                `_execute_q_dash`).
            E → `_titan_e_rage()` — NỔI KHÙNG (tự trừ máu đổi lấy sức mạnh AoE).
            R → `_exit_titan_form()` — THOÁT dạng titan, KHÔNG phải kích hoạt gì thêm.

        Đây chính là điểm mấu chốt khiến `SKILL_UNLOCK_LEVEL['E']` PHẢI ghi rõ
        "chỉ áp cho E-trong-dạng-titan" trong docstring của class Eren.
        """
        if not self.is_in_titan_form:
            if skill_id == "Q":
                if self._skill_cd.get("Q", 0.0) <= 0:
                    self._q_aiming = True
            elif skill_id == "E":
                self.begin_aim()
            elif skill_id == "R":
                self._enter_titan_form()
        else:
            if skill_id == "Q":
                if self._skill_cd.get("Q", 0.0) <= 0:
                    self._q_aiming = True
            elif skill_id == "E":
                self._titan_e_rage()
            elif skill_id == "R":
                self._exit_titan_form()

    def use_skill(self, skill_id: str) -> None:
        """Ghi đè cho R (biến hình Titan): cooldown CHỈ tính từ lúc THOÁT form.

        Lớp cha luôn nạp cd sau `_activate_skill` → vừa vào form là R đã cd 40s,
        bấm R để thoát lại bị chính cd-gate của `use_skill` chặn → KẸT dạng Titan
        tới khi cd hết hoặc _titan_hp cạn. Ở đây tách 2 chiều:
          • Vào form: gate bằng cd (chống biến hình lại quá nhanh sau thoát), KHÔNG nạp cd.
          • Thoát form: LUÔN cho phép, nạp cd (bắt đầu đếm TỪ LÚC THOÁT).
        Q/E và mọi skill khác giữ nguyên hành vi lớp cha.
        """
        if skill_id == 'R':
            if not self.is_skill_unlocked('R'):
                return
            if not self.is_in_titan_form:
                if self._skill_cd.get('R', 0.0) > 0:
                    return
                self._activate_skill('R')        # vào form — KHÔNG nạp cd ở đây
            else:
                self._activate_skill('R')        # thoát form
                self._skill_cd['R'] = float(self.SKILL_COOLDOWNS['R'])
            return
        super().use_skill(skill_id)
                
    def _enter_titan_form(self) -> None:
        """BIẾN HÌNH sang dạng titan — nạp đầy `_titan_hp`, KHÔNG tốn cooldown ở đây.

        ⚠️ Lưu ý: hàm này KHÔNG tự đặt `_skill_cd['R']` — cooldown R được đặt ở
        `_exit_titan_form()` (lúc THOÁT), nghĩa là bạn có thể giữ dạng titan bao
        lâu tuỳ ý (chỉ giới hạn bởi `_titan_hp` tự cạn hoặc bị đánh chết), và
        cooldown chỉ tính từ lúc THOÁT ra.

        Thuật toán: kiểm tra cooldown R (chặn biến hình lặp lại quá nhanh sau lần
        thoát trước) → phát âm thanh biến hình → bật `is_in_titan_form` + nạp đầy
        `_titan_hp = TITAN_MAX_HP` + tắt `is_enraged` (biến hình mới luôn tỉnh táo)
        + kích animation Thunderstrike + publish event `'commander_titan_form'`
        (state='enter', HUD/hệ thống khác có thể subscribe để phản ứng).

        Chỉ số: balance.EREN_TITAN_MAX_HP.
        """
        if self._skill_cd.get("R", 0.0) > 0:
            return
        from systems.sound_system import SoundManager
        SoundManager.get_instance().play('eren_transform_titan', self.x, self.y)
        self.is_in_titan_form = True
        self._titan_hp = self.TITAN_MAX_HP
        self.is_enraged = False
        self._thunder_anim_idx = 0
        self._thunder_anim_timer = 0.0
        self._animator.set_state("skill_r")
        GameEventBus.get_instance().publish("commander_titan_form", {"name": self.NAME, "state": "enter"})
        
    def _exit_titan_form(self) -> None:
        """THOÁT dạng titan — về dạng người, ĐẶT COOLDOWN R (mới đặt ở đây, không phải lúc vào).

        Gọi từ: `_activate_skill('R')` khi người chơi CHỦ ĐỘNG thoát, HOẶC tự động
        khi `_titan_hp <= 0` (dạng titan "chết" — không phải Eren chết thật, chỉ
        buộc về dạng người), HOẶC khi tướng chết hẳn (`update()` gọi khi
        `not is_alive`).

        Reset: tắt `is_in_titan_form`/`is_enraged`, xoá knockback/move_target dở
        dang (tránh mang state dạng titan sang dạng người), nạp
        `_skill_cd['R'] = SKILL_COOLDOWNS['R']` (30s mặc định), publish event
        `'commander_titan_form'` (state='exit').
        """
        self.is_in_titan_form = False
        self.is_enraged = False
        self._kb_timer = 0.0
        self._move_target = None
        self._skill_cd["R"] = float(self.SKILL_COOLDOWNS.get("R", 30.0))
        GameEventBus.get_instance().publish("commander_titan_form", {"name": self.NAME, "state": "exit"})
        
    def _execute_q_dash(self) -> None:
        """THỰC THI cú lướt Q — nhắm THEO VỊ TRÍ CHUỘT THẬT (đã bù camera), lướt xuyên titan.

        Thuật toán:
          1. Tắt `_q_aiming`, nạp cooldown Q ngay (dù có lướt được hay không —
             chống spam nếu người chơi bấm Q rồi nhả liền, không di chuột).
          2. Lấy vị trí chuột SCREEN, cộng `_camera_offset` để ra toạ độ WORLD
             thật — nếu bỏ bước bù camera, lướt sẽ nhắm sai khi camera đã cuộn.
          3. Tính vector hướng, tốc độ = `TITAN_Q_DASH_SPEED`; DẠNG NGƯỜI lướt
             chỉ bằng NỬA tốc độ (`×0.5`) — chậm và ngắn hơn dạng titan.
          4. Đặt `_titan_q_vx/vy` (vận tốc lướt, `update()` sẽ tiêu thụ dần theo
             `_titan_q_timer = TITAN_Q_DASH_DUR`), bật `_titan_is_attacking`
             (dùng chung cho cả 2 dạng — damage dọc đường lướt xử lý trong `update()`).
          5. Xoá `_move_target` — lướt Q GHI ĐÈ mọi ý định di chuyển bằng chuột trước đó.
          6. Chỉ đổi `_animator` sang "skill_q" ở DẠNG NGƯỜI (dạng titan dùng
             `_titan_anim_col` riêng, không qua `_animator`).

        Chỉ số: balance.EREN_TITAN_Q_DASH_SPEED / _DASH_DUR, balance.EREN_SKILL_COOLDOWNS['Q'].
        """
        self._q_aiming = False
        self._skill_cd["Q"] = float(self.SKILL_COOLDOWNS.get("Q", 5.0))
        
        mx, my = pygame.mouse.get_pos()
        cam_x, cam_y = getattr(self, '_camera_offset', (0, 0))
        target_x = mx + cam_x
        target_y = my + cam_y
        
        dx = target_x - self.x
        dy = target_y - self.y
             
        dist = math.hypot(dx, dy)
        speed = self.TITAN_Q_DASH_SPEED
        if not self.is_in_titan_form:
            speed *= 0.5  # Dạng người lướt chậm hơn và ngắn hơn
            
        if dist > 0:
            self._titan_q_vx = (dx / dist) * speed
            self._titan_q_vy = (dy / dist) * speed
        else:
            self._titan_q_vx = speed
            self._titan_q_vy = 0
            
        self._titan_q_timer = self.TITAN_Q_DASH_DUR
        self._titan_is_attacking = True
        self._titan_anim_col = 0
        self._move_target = None
        
        if not self.is_in_titan_form:
            self._animator.set_state("skill_q")
        
    def _titan_e_rage(self) -> None:
        """SKILL E DẠNG TITAN — nổi khùng: đổi MÁU của chính mình lấy AoE damage liên tục.

        Kích hoạt xong, TOÀN BỘ hiệu ứng (tự trừ máu, giật damage AoE mỗi 0.5s,
        đổi sang sprite `_titan_angry_sheet`, tự tắt khi hết giờ) được xử lý trong
        `update()` — hàm này CHỈ bật cờ và đặt timer.

        Điều kiện từ chối: còn cooldown HOẶC đang khùng sẵn rồi.
        Thành công: nạp cooldown, bật `is_enraged`, đặt `_titan_e_timer = TITAN_E_RAGE_DUR`.

        Chỉ số: balance.EREN_TITAN_E_RAGE_DUR / _RAGE_DRAIN / _AURA_RADIUS / _AURA_DAMAGE,
        balance.EREN_SKILL_COOLDOWNS['E'].
        """
        if self._skill_cd.get("E", 0.0) > 0 or self.is_enraged:
            return
        self._skill_cd["E"] = float(self.SKILL_COOLDOWNS.get("E", 8.0))
        self.is_enraged = True
        self._titan_e_timer = self.TITAN_E_RAGE_DUR
        
    def take_damage(self, amount: int, dtype: str) -> None:
        """Nhận damage — DẠNG TITAN trừ vào `_titan_hp` RIÊNG, KHÔNG ảnh hưởng HP người thật.

        Đây là điểm mấu chốt: HP dạng titan (`_titan_hp`) và HP dạng người
        (`self._hp` của Commander base) là 2 THANH MÁU HOÀN TOÀN ĐỘC LẬP.

        Dạng titan: trừ `_titan_hp`; hết máu → `_exit_titan_form()` — Eren BỊ ÉP
        VỀ DẠNG NGƯỜI (với `self._hp` gốc VẪN NGUYÊN, không hề bị đụng tới), tức
        là "chết dạng titan" chỉ là mất buff tạm thời, không phải chết thật.
        Ngược lại, tướng CHỈ thực sự thua trận khi `self._hp` (dạng người) về 0
        — qua `super().take_damage()` khi KHÔNG ở dạng titan (dạng titan hoàn
        toàn MIỄN NHIỄM với cơ chế `_on_defeat`/antiheal của base, vì nhánh
        `super()` không được gọi).

        Dạng người: uỷ quyền hoàn toàn cho `Commander.take_damage()` (base) —
        antiheal, bất tử, animation "hurt" như bình thường.

        Chỉ số: balance.EREN_TITAN_MAX_HP.
        """
        if self.is_in_titan_form:
            self._titan_hp -= max(0, int(amount))
            if self._titan_hp <= 0:
                self._exit_titan_form()
        else:
            super().take_damage(amount, dtype)
