"""_ai_app.py — Khung demo dùng chung cho mọi [titan]check_AI.py.

Vì sao có file này?
    10 demo AI đều cần: cửa sổ pygame, game loop, spawn HQ/Wall/Tower/
    Soldier/Commander, để AI tự chạy, vẽ HUD trạng thái AI. Nếu chép
    code đó vào 10 file thì lặp khủng khiếp và khó bảo trì.

    AICheckApp gom toàn bộ khung đó. Mỗi demo chỉ là một class con
    nhỏ override 2 method: `create_titan()` và `title()`.

Triết lý OOP — Template Method Pattern:
    AICheckApp.run() định nghĩa "bộ xương" vòng demo (cố định). Các
    "lỗ trống" (tạo titan loại gì, tiêu đề cửa sổ) do class con điền.
    Thêm demo cho titan mới = thêm 1 class con ~10 dòng.

Người dùng KHÔNG điều khiển titan — titan tự hành bằng AI. Người dùng
chỉ tác động lên thế giới:
    SPACE  — thêm 1 Soldier ngẫu nhiên (test đổi ưu tiên mục tiêu)
    C      — thêm 1 Commander ngẫu nhiên
    K      — Soldier/Commander đồng loạt bắn titan 1 loạt (ép titan
             "bị tấn công" để xem AI phản ứng theo Priority)
    R      — respawn lại toàn bộ
    Q/ESC  — thoát
"""
from __future__ import annotations

import random

import pygame

import _ai_bootstrap  # noqa: F401  — PHẢI import trước Titan/AI
from AI import (
    make_ai_for, SimpleWorldView,
    STATE_DEAD,
)
from _ai_dummies import (
    Headquarters, WallDummy, TowerDummy, SoldierDummy, CommanderDummy,
)


# ── Hằng số bố cục màn hình ──────────────────────────────────────

SCREEN_W = 1040
SCREEN_H = 720
FPS      = 60

_DIR_NAMES = {0: 'N', 1: 'W', 2: 'S', 3: 'E'}
_COMMANDER_NAMES = ['Levi', 'Mikasa', 'Erwin', 'Armin', 'Jean', 'Sasha']


class AICheckApp:
    """Khung demo AI — lớp cha cho mọi [titan]check_AI.py.

    Vòng đời:
        app = SomeTitanAICheck()   # class con
        app.run()                  # mở cửa sổ, chạy tới khi thoát

    Class con BẮT BUỘC override:
        • create_titan() -> Titan   — tạo instance titan cần demo.
        • title() -> str            — tiêu đề cửa sổ.
    Class con CÓ THỂ override:
        • describe_titan() -> list[str]  — vài dòng HUD mô tả titan.
        • spawn_world_layout()           — bố trí entity ban đầu.
    """

    # ── Phần class con override ──────────────────────────────────

    def create_titan(self):
        """Tạo & trả về instance Titan cần demo. BẮT BUỘC override."""
        raise NotImplementedError

    def title(self) -> str:
        """Tiêu đề cửa sổ. BẮT BUỘC override."""
        raise NotImplementedError

    def describe_titan(self) -> list:
        """Vài dòng mô tả titan cho HUD. Mặc định: rỗng."""
        return []

    # ── Khởi tạo ─────────────────────────────────────────────────

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(self.title())
        self.clock = pygame.time.Clock()
        self.font  = pygame.font.SysFont('Consolas', 14)
        self.big   = pygame.font.SysFont('Consolas', 20, bold=True)
        self.running = True

        # Vị trí titan spawn — mép trái, giữa chiều cao.
        self.spawn_x = 150.0
        self.spawn_y = SCREEN_H / 2

        self._build_scene()

    # ── Dựng / dựng lại sân khấu ─────────────────────────────────

    def _build_scene(self) -> None:
        """Tạo titan + entity + WorldView + AI. Gọi lúc đầu và khi R."""
        self.titan = self.create_titan()
        # Nạp sprite nếu titan hỗ trợ (an toàn nếu không có).
        load = getattr(self.titan, '_load_sprite', None)
        if callable(load):
            load()

        self.hq, self.walls, self.towers, \
            self.soldiers, self.commanders = self.spawn_world_layout()

        # WorldView: giác quan của AI, dựng từ các entity vừa spawn.
        self.world = SimpleWorldView(
            hq=self.hq, walls=self.walls, towers=self.towers,
            soldiers=self.soldiers, commanders=self.commanders,
        )
        # Bộ não AI — factory tự chọn AI + Priority theo loại titan.
        self.ai = make_ai_for(self.titan, self.world)

        # Đồng bộ danh sách cho WorldQuery giả (vài skill lazy-import nó).
        _ai_bootstrap._MockWorldQuery.soldiers   = self.soldiers
        _ai_bootstrap._MockWorldQuery.towers     = self.towers
        _ai_bootstrap._MockWorldQuery.commanders = self.commanders
        _ai_bootstrap._MockWorldQuery.walls      = self.walls
        _ai_bootstrap._MockWorldQuery.hq         = self.hq

        self._frame = 0
        print(f"\n=== {type(self.titan).__name__} AI demo ===")
        print(f"    AI = {type(self.ai).__name__}  "
              f"Priority = {type(self.ai.priority).__name__}")

    def spawn_world_layout(self) -> tuple:
        """Bố trí entity ban đầu. Class con override nếu muốn khác.

        Mặc định: HQ nằm bên phải màn hình, được bao vây hoàn toàn bởi
        4 WallDummy (trên/dưới/trái/phải), mỗi Wall cách HQ ~100px.
        Tower + Soldier + Commander đặt bên ngoài vòng Wall để mô phỏng
        lực lượng phòng thủ thực tế.

        Bố cục (nhìn từ trên):

            Titan  →→→  [Tower-1]   [Wall-T]
                                  [Wall-L] [HQ] [Wall-R]
                        [Tower-2]   [Wall-B]

        Trả: (hq, walls, towers, soldiers, commanders)
        """
        cx = SCREEN_W - 200   # tâm HQ — cách mép phải 200px
        cy = SCREEN_H / 2
        gap = 100             # khoảng cách tâm HQ → tâm Wall (~100px)

        hq = Headquarters(cx, cy)

        # 4 Wall bao vây HQ: trên, dưới, trái (dọc), phải (dọc)
        walls = [
            WallDummy(cx,        cy - gap, label='Wall-T'),           # trên (ngang)
            WallDummy(cx,        cy + gap, label='Wall-B'),           # dưới (ngang)
            WallDummy(cx - gap,  cy,       label='Wall-L', vertical=True),  # trái (dọc)
            WallDummy(cx + gap,  cy,       label='Wall-R', vertical=True),  # phải (dọc)
        ]

        # Tower bên ngoài vòng Wall, góc trên-trái và dưới-trái
        towers = [
            TowerDummy(cx - 200, cy - 160, label='Tower-1'),
            TowerDummy(cx - 200, cy + 160, label='Tower-2'),
        ]

        # Soldier rải từ giữa màn hình ra
        soldiers = [
            SoldierDummy(cx - 340, cy - 60,  label='Sld-1'),
            SoldierDummy(cx - 290, cy + 50,  label='Sld-2'),
            SoldierDummy(cx - 380, cy + 130, label='Sld-3'),
        ]

        commanders = [
            CommanderDummy(cx - 310, cy - 160, name='Levi'),
        ]
        return hq, walls, towers, soldiers, commanders

    # ── Vòng lặp chính (Template Method) ─────────────────────────

    def run(self) -> None:
        """Mở cửa sổ và chạy demo tới khi người dùng thoát."""
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self._frame += 1
            self._handle_input()
            self._update(dt)
            self._draw()
        pygame.quit()

    # ── Input ────────────────────────────────────────────────────

    def _handle_input(self) -> None:
        """Người dùng chỉ tác động lên THẾ GIỚI — không điều khiển titan."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    self._spawn_soldier()
                elif event.key == pygame.K_c:
                    self._spawn_commander()
                elif event.key == pygame.K_k:
                    self._volley_attack()
                elif event.key == pygame.K_r:
                    self._build_scene()

    def _spawn_soldier(self) -> None:
        """Thêm 1 Soldier ngẫu nhiên — test AI đổi ưu tiên sang lính."""
        x = random.uniform(SCREEN_W * 0.35, SCREEN_W * 0.75)
        y = random.uniform(80, SCREEN_H - 80)
        s = SoldierDummy(x, y, label=f'Sld+{len(self.soldiers) + 1}')
        self.soldiers.append(s)
        print(f"  [+] Soldier @ ({x:.0f},{y:.0f})")

    def _spawn_commander(self) -> None:
        """Thêm 1 Commander ngẫu nhiên — test ưu tiên với tướng."""
        x = random.uniform(SCREEN_W * 0.35, SCREEN_W * 0.75)
        y = random.uniform(80, SCREEN_H - 80)
        name = random.choice(_COMMANDER_NAMES)
        self.commanders.append(CommanderDummy(x, y, name=name))
        print(f"  [+] Commander {name} @ ({x:.0f},{y:.0f})")

    def _volley_attack(self) -> None:
        """Mọi Soldier/Commander gần titan bắn 1 loạt — ép titan 'bị
        tấn công' để quan sát AI chuyển mục tiêu theo Priority."""
        n = 0
        for e in list(self.soldiers) + list(self.commanders):
            if not e.is_alive:
                continue
            d = ((e.x - self.titan.x) ** 2
                 + (e.y - self.titan.y) ** 2) ** 0.5
            if d <= 320:
                self.titan.take_damage(8, 'normal')
                self.ai.notify_attacked(e)
                n += 1
        print(f"  [K] {n} entity bắn titan 1 loạt")

    # ── Update ───────────────────────────────────────────────────

    def _update(self, dt: float) -> None:
        """Cập nhật AI titan + để các entity tấn công bắn trả."""
        # 1. AI titan tự hành.
        self.ai.update(dt)

        # 2. Các entity biết bắn (Tower/Soldier/Commander) bắn trả.
        for e in self.towers + self.soldiers + self.commanders:
            shoot = getattr(e, 'try_shoot', None)
            if callable(shoot):
                shoot(self.titan, self.ai, dt)

        # 3. Tick mọi entity (nháy đỏ, stun timer...).
        for e in self._all_entities():
            e.update(dt)

    def _all_entities(self) -> list:
        """Mọi entity còn trong scene (kể cả đã chết để vẽ mờ)."""
        out = []
        if self.hq is not None:
            out.append(self.hq)
        out += self.walls + self.towers + self.soldiers + self.commanders
        return out

    # ── Draw ─────────────────────────────────────────────────────

    def _draw(self) -> None:
        """Vẽ 1 khung hình: nền lưới → entity → titan → HUD."""
        screen = self.screen
        screen.fill((26, 28, 34))
        # Lưới nền cho dễ ước lượng khoảng cách.
        for gx in range(0, SCREEN_W, 80):
            pygame.draw.line(screen, (38, 40, 48), (gx, 0), (gx, SCREEN_H))
        for gy in range(0, SCREEN_H, 80):
            pygame.draw.line(screen, (38, 40, 48), (0, gy), (SCREEN_W, gy))

        # Đường nối titan → mục tiêu AI đang chọn (trực quan hóa quyết định).
        if self.ai.target is not None and self.ai.target.is_alive:
            pygame.draw.line(
                screen, (200, 90, 90),
                (int(self.titan.x), int(self.titan.y)),
                (int(self.ai.target.x), int(self.ai.target.y)), 2)

        # Entity.
        for e in self._all_entities():
            e.draw(screen, self.font)

        # Titan — dùng draw() riêng nếu có, fallback hình tròn.
        self._draw_titan()

        # HUD.
        self._draw_hud()
        pygame.display.flip()

    def _draw_titan(self) -> None:
        """Vẽ titan: ưu tiên draw() riêng của nó; fallback hình tròn đỏ."""
        titan = self.titan
        drawn = False
        draw_fn = getattr(titan, 'draw', None)
        if callable(draw_fn):
            try:
                draw_fn(self.screen)
                drawn = True
            except Exception:
                drawn = False
        if not drawn:
            color = (200, 70, 70) if titan.is_alive else (90, 60, 60)
            pygame.draw.circle(self.screen, color,
                               (int(titan.x), int(titan.y)), 22)
            pygame.draw.circle(self.screen, (250, 180, 180),
                               (int(titan.x), int(titan.y)), 22, 2)

        # Ẩn HP bar khi titan chết hoặc đã nổ (Kamikaze) — sprite biến mất
        # thì thanh HP cũng biến mất, không còn lơ lửng giữa map.
        if not getattr(titan, 'is_alive', False):
            return
        if getattr(titan, '_has_exploded', False):
            return

        # Thanh HP titan (luôn vẽ đè để thấy rõ).
        hp     = getattr(titan, '_hp', 0)
        max_hp = getattr(titan, '_max_hp', 1) or 1
        ratio  = max(0.0, hp / max_hp)
        bx, by = int(titan.x - 28), int(titan.y - 44)
        pygame.draw.rect(self.screen, (60, 0, 0), (bx, by, 56, 6))
        pygame.draw.rect(self.screen, (230, 80, 80),
                         (bx, by, int(56 * ratio), 6))

    def _draw_hud(self) -> None:
        """Vẽ bảng HUD: trạng thái AI, mục tiêu, lý do quyết định."""
        titan = self.titan
        ai    = self.ai
        hp     = getattr(titan, '_hp', 0)
        max_hp = getattr(titan, '_max_hp', 1) or 1

        target_name = '—'
        if ai.target is not None:
            target_name = (getattr(ai.target, '_label', None)
                           or getattr(ai.target, 'name', None)
                           or getattr(ai.target, 'entity_type', '?'))

        lines = [
            f"Titan   : {type(titan).__name__}   "
            f"HP={hp}/{max_hp} ({hp / max_hp * 100:.0f}%)",
            f"AI      : {type(ai).__name__}   "
            f"Priority={type(ai.priority).__name__}",
            f"State   : {ai.state.upper()}   "
            f"dir={_DIR_NAMES.get(getattr(titan, '_direction', 2), '?')}",
            f"Target  : {target_name}",
            f"Reason  : {ai.last_reason}",
            f"World   : HQ={'O' if (self.hq and self.hq.is_alive) else 'X'}  "
            f"walls={sum(w.is_alive for w in self.walls)}  "
            f"towers={sum(t.is_alive for t in self.towers)}  "
            f"soldiers={sum(s.is_alive for s in self.soldiers)}  "
            f"cmds={sum(c.is_alive for c in self.commanders)}",
        ]
        lines += self.describe_titan()
        lines += [
            "",
            "SPACE=+Soldier  C=+Commander  K=volley bắn titan  "
            "R=respawn  Q=thoát",
        ]

        # Khung nền HUD.
        panel = pygame.Surface((SCREEN_W, 22 * len(lines) + 16),
                               pygame.SRCALPHA)
        panel.fill((0, 0, 0, 165))
        self.screen.blit(panel, (0, 0))
        for i, text in enumerate(lines):
            surf = self.font.render(text, True, (235, 235, 235))
            self.screen.blit(surf, (12, 10 + i * 22))

        # Nhãn lớn khi titan chết.
        if ai.state == STATE_DEAD:
            label = self.big.render("TITAN ĐÃ CHẾT — bấm R để respawn",
                                    True, (255, 160, 160))
            self.screen.blit(
                label,
                (SCREEN_W // 2 - label.get_width() // 2, SCREEN_H - 60))
