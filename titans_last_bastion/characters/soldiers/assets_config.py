# characters/soldiers/assets_config.py
from __future__ import annotations

# Shared
SPRITE_SCALE: int = 2
NEXT_STATE_AFTER_ONESHOT: str = "idle"

# ===========================================================================
# SOLDIER packs (Archer / Lancer / Warrior)
# All three are horizontal STRIP sheets with SQUARE frames.
# Soldier state machine uses: idle / walk / attack (+ guard for Warrior).
# ===========================================================================

# --- Archer — 192×192 frames -----------------------------------------------
FRAME_SIZE_ARCHER: int = 192
ARCHER_SPRITE_FRAMES: dict = {
    "idle":   {"file": "Archer_Idle.png",  "fps": 6,  "loop": True},
    "walk":   {"file": "Archer_Run.png",   "fps": 12, "loop": True},
    "attack": {"file": "Archer_Shoot.png", "fps": 16, "loop": False},
}

# --- Lancer — 320×320 frames ------------------------------------------------
FRAME_SIZE_LANCER: int = 320
LANCER_SPRITE_FRAMES: dict = {
    "idle":   {"file": "Lancer_Idle.png",         "fps": 10, "loop": True},
    "walk":   {"file": "Lancer_Run.png",           "fps": 14, "loop": True},
    "attack": {"file": "Lancer_Right_Attack.png",  "fps": 14, "loop": False},
}

# --- Warrior soldier — 192×192 frames --------------------------------------
FRAME_SIZE_WARRIOR_SOLDIER: int = 192
WARRIOR_SOLDIER_SPRITE_FRAMES: dict = {
    "idle":   {"file": "Warrior_Idle.png",    "fps": 8,  "loop": True},
    "walk":   {"file": "Warrior_Run.png",     "fps": 12, "loop": True},
    "attack": {"file": "Warrior_Attack1.png", "fps": 16, "loop": False},
    "guard":  {"file": "Warrior_Guard.png",   "fps": 8,  "loop": True},
}
