# characters/soldiers/squad.py
from __future__ import annotations

import math

from characters.soldiers.soldier import SOLDIER_TYPES

SQUAD_SIZE: int = 10
SQUAD_SPACING: float = 52.0


def formation_offsets(n: int, spacing: float = SQUAD_SPACING) -> list:
    """Return n (dx, dy) offsets packed as a filled hex-ring cluster.
    Neighbours sit ~`spacing` apart so sprites spread out instead of stacking."""
    offsets = [(0.0, 0.0)]
    ring = 1
    while len(offsets) < n:
        radius = ring * spacing
        slots = max(1, int(round(2 * math.pi * ring)))
        phase = ring * 0.5
        for i in range(slots):
            if len(offsets) >= n:
                break
            ang = (2 * math.pi * i) / slots + phase
            offsets.append((math.cos(ang) * radius, math.sin(ang) * radius))
        ring += 1
    return offsets[:n]


class Squad:
    """A deployed cluster of same-type soldiers bound to one spawn anchor."""

    def __init__(self, soldier_type: str, base_pos: tuple, target=None,
                 *, size: int = SQUAD_SIZE, headless: bool = False,
                 home_pos: tuple | None = None,
                 home_radius: float = 600.0,
                 no_formation: bool = False) -> None:
        """Tạo `size` lính CÙNG LOẠI, rải theo đội hình hex quanh `base_pos`.

        Tham số:
            soldier_type: khoá tra `SOLDIER_TYPES` ('Warrior'/'Archer'/'Lancer').
                Sai khoá → `ValueError` ngay (lỗi cấu hình, nên raise sớm).
            base_pos: điểm SPAWN (tâm đội hình).
            home_pos: THÁP NHÀ chung cho cả squad — None → dùng `base_pos`.
            no_formation: True → mọi lính chồng CÙNG 1 điểm (offset (0,0)) thay
                vì rải theo `formation_offsets()` — dùng khi cần spawn gọn/test.

        Mỗi lính được gắn NGƯỢC `soldier._squad = self` — cơ chế 2 chiều để
        `Soldier.update()` đọc được `squad._state` (đánh thức khi squad chuyển COMBAT).

        Chỉ số: SQUAD_SIZE (10), SQUAD_SPACING (52px).
        """
        if soldier_type not in SOLDIER_TYPES:
            raise ValueError(f"Unknown soldier type: {soldier_type!r}")
        self.soldier_type = soldier_type
        cls = SOLDIER_TYPES[soldier_type]
        bx, by = base_pos
        home = base_pos if home_pos is None else home_pos
        self.home_pos: tuple = (float(home[0]), float(home[1]))
        self.home_radius: float = float(home_radius)
        self.members: list = []
        self._state: str = "COMBAT"  # COMBAT, RETREAT, IDLE

        offsets = [(0.0, 0.0)] * size if no_formation else formation_offsets(size)
        for dx, dy in offsets:
            soldier = cls(
                bx + dx, by + dy, target=target, headless=headless,
                home_pos=self.home_pos, home_radius=self.home_radius,
            )
            soldier._squad = self
            soldier._slot_offset = (dx, dy)
            self.members.append(soldier)

    def register_all(self, world) -> None:
        """Register every member with the given WorldQuery registry."""
        for s in self.members:
            world.register(s)

    @property
    def alive_members(self) -> list:
        """List lính còn sống trong squad — dùng để đếm quân số thật/kiểm tra sạch quân."""
        return [s for s in self.members if s.is_alive]

    @property
    def is_alive(self) -> bool:
        """True while at least one member is alive. Used by Tower for wipe-detection."""
        return any(s.is_alive for s in self.members)

    def set_state(self, state: str) -> None:
        """Broadcast state change to all squad members."""
        self._state = state
        for member in self.members:
            if member.is_alive:
                member._state = state


def deploy_squad(soldier_type: str, base_pos: tuple, target, world,
                 *, size: int = SQUAD_SIZE, headless: bool = False,
                 home_pos: tuple | None = None,
                 home_radius: float = 600.0) -> Squad:
    """Create a Squad and register all members in `world`. Returns the Squad.

    `home_pos` / `home_radius` define the patrol zone — soldiers only chase
    titans inside it and retreat to that anchor when idle.
    """
    squad = Squad(soldier_type, base_pos, target, size=size, headless=headless,
                  home_pos=home_pos, home_radius=home_radius)
    squad.register_all(world)
    return squad
