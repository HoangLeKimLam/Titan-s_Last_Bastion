"""
wave_manager.py — Bộ sinh wave cho chế độ VƯỢT ẢI (THÊM MỚI).

Trách nhiệm DUY NHẤT: đọc cấu hình `config/levels/level_N.json` rồi tính ra
KẾ HOẠCH sinh titan cho từng wave (danh sách tên titan, chia cụm). File này
KHÔNG tự spawn, KHÔNG đụng pygame, KHÔNG import game.py — chỉ trả dữ liệu cho
game.py để game.py dùng đúng các helper sẵn có (WorldQuery.spawn_entity,
make_ai_for, tt_spawn_pos) mà spawn.

Thuật toán sinh titan giống Thao Trường Tự Do (rút thăm có trọng số tới khi cạn
ngân sách / đạt trần số lượng) nhưng ngân sách + trọng số lấy từ JSON theo từng
ải, nên Vượt Ải có thể sinh NHIỀU và KHÓ hơn Thao Trường.

Khóa tên titan PHẢI khớp registry `TT_TITANS` trong game.py:
    Regular · Wolf · Kamikaze · SoldierHunter · TowerHunter · Armored
Tên boss khớp `_VA_BOSS_CLASSES` trong game.py: Colossal · Beast · Founding
"""
import os
import json
import random
from typing import Optional


# Giá quy đổi mỗi loại titan (đồng bộ với TT_TITANS trong game.py). Để ở đây
# nhằm GIỮ wave_manager độc lập hoàn toàn — không phụ thuộc game.py.
TITAN_COSTS = {
    'Regular':       15,
    'Wolf':          20,
    'Kamikaze':      20,
    'SoldierHunter': 25,
    'TowerHunter':   25,
    'Armored':       45,
}

# Trọng số mặc định nếu JSON thiếu (an toàn fallback).
_DEFAULT_WEIGHTS = {
    'Regular': 50, 'Wolf': 25, 'Kamikaze': 15,
    'SoldierHunter': 7, 'TowerHunter': 3, 'Armored': 0,
}

_GROUP_MIN = 2     # số titan tối thiểu mỗi cụm spawn cùng lúc
_GROUP_MAX = 4     # số titan tối đa mỗi cụm


class VuotAiWaveManager:
    """Đọc JSON 1 ải → cấp phát kế hoạch từng wave cho game.py.

    Vòng đời:
        mgr = VuotAiWaveManager(config_dir)
        mgr.load_level(3)                 # nạp level_3.json
        while mgr.has_more_waves:
            plan = mgr.build_next_wave()  # dict mô tả wave kế tiếp
            ... game.py spawn theo plan ...
        reward = mgr.completion_reward
    """

    def __init__(self, config_dir: str) -> None:
        self._config_dir = config_dir
        self._cfg: dict = {}
        self._waves: list = []
        self._boss_wave: Optional[dict] = None
        self._level_weights: dict = {}
        self._idx = 0                      # số wave đã cấp phát (0-based con trỏ)

    # ── Nạp cấu hình ──────────────────────────────────────────────────────
    def load_level(self, level_num: int) -> bool:
        """Đọc level_<n>.json. Trả True nếu hợp lệ, False nếu lỗi/thiếu file."""
        path = os.path.join(self._config_dir, f'level_{level_num}.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            self._cfg = {}
            self._waves = []
            self._boss_wave = None
            self._idx = 0
            return False

        self._cfg = cfg
        self._waves = list(cfg.get('waves', []))
        self._boss_wave = cfg.get('boss_wave')        # None nếu ải không có boss
        self._level_weights = cfg.get('weights', dict(_DEFAULT_WEIGHTS))
        self._idx = 0
        return bool(self._waves) or self._boss_wave is not None

    # ── Truy vấn ──────────────────────────────────────────────────────────
    @property
    def total_waves(self) -> int:
        return len(self._waves) + (1 if self._boss_wave else 0)

    @property
    def has_more_waves(self) -> bool:
        return self._idx < self.total_waves

    @property
    def completion_reward(self) -> dict:
        return dict(self._cfg.get('completion_reward', {}))

    @property
    def difficulty(self) -> float:
        return float(self._cfg.get('difficulty', 1.0))

    # ── Cấp phát wave kế tiếp ─────────────────────────────────────────────
    def build_next_wave(self) -> Optional[dict]:
        """Trả kế hoạch wave kế tiếp, hoặc None nếu đã hết.

        Cấu trúc trả về:
            {
              'index':   int,            # wave thứ mấy (1-based)
              'is_boss': bool,
              'boss':    str | None,     # tên boss nếu là wave boss
              'groups':  [[tên,...], ..] # các cụm titan thường / lính hộ tống
              'reward':  dict | None,    # thưởng nhận khi dọn sạch wave này
            }
        """
        if not self.has_more_waves:
            return None

        # Wave boss luôn là wave cuối (sau toàn bộ wave thường)
        if self._boss_wave and self._idx == len(self._waves):
            bw = self._boss_wave
            weights = bw.get('weights', self._level_weights)
            budget = int(bw.get('escort_budget', 0))
            max_titans = int(bw.get('max_titans', 999))
            escorts = self._roll_titans(budget, weights, max_titans)
            self._idx += 1
            return {
                'index':   self._idx,
                'is_boss': True,
                'boss':    bw.get('boss'),
                'groups':  self._chunk(escorts),
                'reward':  bw.get('reward'),
            }

        # Wave thường
        w = self._waves[self._idx]
        weights = w.get('weights', self._level_weights)
        budget = int(w.get('budget', 0))
        max_titans = int(w.get('max_titans', 999))
        titans = self._roll_titans(budget, weights, max_titans)
        self._idx += 1
        return {
            'index':   self._idx,
            'is_boss': False,
            'boss':    None,
            'groups':  self._chunk(titans),
            'reward':  w.get('reward'),
        }

    # ── Nội bộ ────────────────────────────────────────────────────────────
    @staticmethod
    def _roll_titans(budget: int, weights: dict, max_titans: int) -> list:
        """Rút thăm có trọng số tới khi cạn ngân sách / đạt trần số lượng."""
        pool = {t: w for t, w in weights.items()
                if w > 0 and t in TITAN_COSTS}
        result: list = []
        while budget > 0 and len(result) < max_titans:
            cands = {t: w for t, w in pool.items() if TITAN_COSTS[t] <= budget}
            if not cands:
                break
            chosen = random.choices(list(cands.keys()),
                                    weights=list(cands.values()), k=1)[0]
            result.append(chosen)
            budget -= TITAN_COSTS[chosen]
        random.shuffle(result)
        return result

    @staticmethod
    def _chunk(titan_list: list) -> list:
        """Chia danh sách titan thành các cụm 2–4 con để spawn cùng lúc."""
        groups: list = []
        i = 0
        while i < len(titan_list):
            size = random.randint(_GROUP_MIN, _GROUP_MAX)
            groups.append(titan_list[i:i + size])
            i += size
        return groups
