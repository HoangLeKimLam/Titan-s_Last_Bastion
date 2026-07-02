"""
screen_manager.py — Quản lý PHA (phase) của game: Menu → Sảnh → Chiến đấu.

Tại sao cần file này?
    Game có 3 màn hình chính:
        - MENU   : màn hình chính (New Game / Continue / Exit)
        - LOBBY  : "Sảnh" — chính là map hiện tại ở chế độ xây dựng / farm,
                   KHÔNG có titan, KHÔNG có tướng. Hiện 2 nút chọn chế độ.
        - COMBAT : pha chiến đấu thực sự (có titan + tướng).

    ScreenManager CHỈ giữ trạng thái pha + chế độ chiến đấu + màn hiện tại.
    Nó KHÔNG đụng tới bất kỳ logic vận hành nào (titan, lính, tháp, pathfinding).
    Toàn bộ logic game cũ giữ nguyên — file này chỉ là một "công tắc" UI/flow.

Nguyên tắc:
    - CHỈ THÊM, không sửa logic game hiện có.
    - Mọi ràng buộc (chỉ xây tháp khi combat, khoá quân số, v.v.) được
      game.py kiểm tra qua các property is_lobby / is_combat của object này.

2 chế độ chiến đấu:
    - VƯỢT ẢI (vuot_ai)       : thử thách chính, 5 màn. Thua → phạt
                                (−20% tài nguyên cơ bản, tướng −1 cấp).
    - THAO TRƯỜNG (thao_truong): luyện tập. Không phạt, không lên màn.
"""

# --- Hằng số pha (phase) ---------------------------------------------------
PHASE_MENU   = 'menu'
PHASE_LOBBY  = 'lobby'
PHASE_COMBAT = 'combat'

# --- Hằng số chế độ chiến đấu ---------------------------------------------
MODE_VUOT_AI     = 'vuot_ai'
MODE_THAO_TRUONG = 'thao_truong'

# Số màn của chế độ Vượt Ải
MAX_LEVEL = 5


class ScreenManager:
    """Giữ trạng thái pha + chế độ chiến đấu + màn hiện tại.

    Đây là object thuần trạng thái (state holder). Không import gì từ
    systems/, characters/, structures/ để tránh phụ thuộc vòng và giữ
    core logic game độc lập hoàn toàn.
    """

    def __init__(self) -> None:
        self.phase: str        = PHASE_MENU
        self.combat_mode       = None   # None | MODE_VUOT_AI | MODE_THAO_TRUONG
        self.current_level: int = 1     # màn Vượt Ải hiện tại (1..MAX_LEVEL)

    # --- Truy vấn nhanh ----------------------------------------------------
    @property
    def is_menu(self) -> bool:
        return self.phase == PHASE_MENU

    @property
    def is_lobby(self) -> bool:
        return self.phase == PHASE_LOBBY

    @property
    def is_combat(self) -> bool:
        return self.phase == PHASE_COMBAT

    @property
    def is_vuot_ai(self) -> bool:
        return self.combat_mode == MODE_VUOT_AI

    @property
    def is_thao_truong(self) -> bool:
        return self.combat_mode == MODE_THAO_TRUONG

    # --- Chuyển pha --------------------------------------------------------
    def enter_lobby(self) -> None:
        """Vào Sảnh (từ menu hoặc sau khi kết thúc trận)."""
        self.phase = PHASE_LOBBY
        self.combat_mode = None

    def start_combat(self, mode: str) -> None:
        """Bắt đầu pha chiến đấu với chế độ `mode`."""
        self.phase = PHASE_COMBAT
        self.combat_mode = mode

    def end_combat(self) -> None:
        """Kết thúc trận → quay lại Sảnh (giữ nguyên hiện trạng map/HP)."""
        self.phase = PHASE_LOBBY
        self.combat_mode = None

    def advance_level(self) -> None:
        """Thắng Vượt Ải → mở màn tiếp theo (tối đa MAX_LEVEL)."""
        if self.current_level < MAX_LEVEL:
            self.current_level += 1

    # --- Hiển thị ----------------------------------------------------------
    def mode_label(self) -> str:
        """Nhãn ASCII hiển thị trên banner pha chiến đấu."""
        if self.combat_mode == MODE_VUOT_AI:
            return f'VUOT AI  -  Man {self.current_level}/{MAX_LEVEL}'
        if self.combat_mode == MODE_THAO_TRUONG:
            return 'THAO TRUONG TU DO'
        return ''
