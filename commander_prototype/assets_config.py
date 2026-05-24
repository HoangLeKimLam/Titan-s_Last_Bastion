"""assets_config.py — sprite pack layouts (one block per commander).

Each commander's sprite pack has its own frame width/height and its own
state→file mapping. The Commander subclass sets:

    SPRITE_FOLDER, SPRITE_FRAMES, FRAME_WIDTH, FRAME_HEIGHT

…and `animation.load_clips()` reads those off the subclass.

Currently supported packs:
    EREN_SPRITE_FRAMES    — Knight_player_1.4   (100×64 frames per strip)
    MIKASA_SPRITE_FRAMES  — Knight 2D Pixel Art (96×84 frames per strip,
                            "with_outline" variant)

Animation state names (must stay consistent across all packs so
commander.py's state machine works):
    idle / walk
    attack1 / attack2 / attack3  — LMB 3-hit combo
    skill_q / skill_e / skill_r  — Q / E / R skill animations
    hurt / dying / win

After a one-shot finishes, animator falls back to NEXT_STATE_AFTER_ONESHOT
(except "dying", which holds on the last frame).
"""
from __future__ import annotations

# Shared
SPRITE_SCALE: int = 2
NEXT_STATE_AFTER_ONESHOT: str = "idle"

# --- Eren (Knight_player_1.4) ----------------------------------------------
FRAME_WIDTH_EREN: int = 100
FRAME_HEIGHT_EREN: int = 64

EREN_SPRITE_FRAMES: dict = {
    "idle":    {"file": "Idle_KG_1.png",     "fps": 6,  "loop": True},
    "walk":    {"file": "Walking_KG_1.png",  "fps": 12, "loop": True},
    "attack1": {"file": "Attack_KG_1.png",   "fps": 14, "loop": False},
    "attack2": {"file": "Attack_KG_2.png",   "fps": 14, "loop": False},
    "attack3": {"file": "Attack_KG_4.png",   "fps": 14, "loop": False},
    "skill_q": {"file": "Attack_KG_3.png",   "fps": 14, "loop": False},
    "skill_e": {"file": "Dashing_KG_1.png",  "fps": 12, "loop": False},
    "skill_r": {"file": "Power_Up_KG_1.png", "fps": 14, "loop": False},
    "hurt":    {"file": "Hurt_KG_1.png",     "fps": 10, "loop": False},
    "dying":   {"file": "Dying_KG_1.png",    "fps": 6,  "loop": False},
    "win":     {"file": "knight_win.png",    "fps": 6,  "loop": False},
}

# --- Armin (Warrior pack, individual-file mode) ---------------------------
# Each PNG is ONE frame (not a strip). Frame width varies per animation
# (64 for Idle/Attack, 69 for Dash/Dash-Attack). For now we only wire the
# 4 animations the user asked for; the other states reuse Idle / Attack /
# Dash as placeholders so the game still has SOMETHING to render in those
# states. Replace later when more animations land.
FRAME_WIDTH_ARMIN: int = 69     # max source frame width
FRAME_HEIGHT_ARMIN: int = 44    # all Warrior frames are 44 tall

ARMIN_SPRITE_FRAMES: dict = {
    "idle":    {"folder": "idle",        "prefix": "Warrior_Idle_",
                "count": 6,  "fps": 6,  "loop": True},
    "walk":    {"folder": "Dash",        "prefix": "Warrior_Dash_",
                "count": 7,  "fps": 12, "loop": True},
    "attack1": {"folder": "Attack",      "prefix": "Warrior_Attack_",
                "count": 12, "fps": 20, "loop": False},
    "attack2": {"folder": "Attack",      "prefix": "Warrior_Attack_",
                "count": 12, "fps": 20, "loop": False},
    "attack3": {"folder": "Attack",      "prefix": "Warrior_Attack_",
                "count": 12, "fps": 20, "loop": False},
    "skill_q": {"folder": "Dash Attack", "prefix": "Warrior_Dash-Attack_",
                "count": 10, "fps": 18, "loop": False},
    "skill_e": {"folder": "Dash",        "prefix": "Warrior_Dash_",
                "count": 7,  "fps": 14, "loop": False},
    "skill_r": {"folder": "Attack",      "prefix": "Warrior_Attack_",
                "count": 12, "fps": 14, "loop": False},
    "hurt":    {"folder": "idle",        "prefix": "Warrior_Idle_",
                "count": 6,  "fps": 10, "loop": False},
    "dying":   {"folder": "idle",        "prefix": "Warrior_Idle_",
                "count": 6,  "fps": 6,  "loop": False},
    "win":     {"folder": "idle",        "prefix": "Warrior_Idle_",
                "count": 6,  "fps": 6,  "loop": True},
}

# --- Mikasa (Knight 2D Pixel Art, with_outline variant) --------------------
FRAME_WIDTH_MIKASA: int = 96
FRAME_HEIGHT_MIKASA: int = 84

# This pack has no dedicated DASH or POWER_UP strips, so Mikasa reuses
# JUMP / DEFEND for E (gap-close) and R (defensive form). Tweak any time.
MIKASA_SPRITE_FRAMES: dict = {
    "idle":    {"file": "IDLE.png",     "fps": 8,  "loop": True},
    "walk":    {"file": "WALK.png",     "fps": 12, "loop": True},
    "attack1": {"file": "ATTACK 1.png", "fps": 14, "loop": False},
    "attack2": {"file": "ATTACK 2.png", "fps": 14, "loop": False},
    "attack3": {"file": "ATTACK 3.png", "fps": 14, "loop": False},
    "skill_q": {"file": "ATTACK 3.png", "fps": 14, "loop": False},
    "skill_e": {"file": "JUMP.png",     "fps": 12, "loop": False},
    "skill_r": {"file": "DEFEND.png",   "fps": 10, "loop": False},
    "hurt":    {"file": "HURT.png",     "fps": 10, "loop": False},
    "dying":   {"file": "DEATH.png",    "fps": 8,  "loop": False},
    "win":     {"file": "IDLE.png",     "fps": 6,  "loop": True},
}

# ===========================================================================
# SOLDIER packs (Archer / Lancer / Warrior) — drawn small, in squads of ~10.
# All three are horizontal STRIP sheets with SQUARE frames, so
# FRAME_WIDTH == FRAME_HEIGHT and animation.load_clips() slices by frame width.
# Soldier state machine only needs: idle / walk / attack (+ guard for Warrior).
# ===========================================================================

# --- Archer (../Archer) — 192×192 frames ----------------------------------
FRAME_SIZE_ARCHER: int = 192
ARCHER_SPRITE_FRAMES: dict = {
    "idle":   {"file": "Archer_Idle.png",  "fps": 6,  "loop": True},   # 6
    "walk":   {"file": "Archer_Run.png",   "fps": 12, "loop": True},   # 4
    "attack": {"file": "Archer_Shoot.png", "fps": 16, "loop": False},  # 8
}

# --- Lancer (../Lancer) — 320×320 frames ----------------------------------
FRAME_SIZE_LANCER: int = 320
LANCER_SPRITE_FRAMES: dict = {
    "idle":   {"file": "Lancer_Idle.png",         "fps": 10, "loop": True},   # 12
    "walk":   {"file": "Lancer_Run.png",          "fps": 14, "loop": True},   # 6
    "attack": {"file": "Lancer_Right_Attack.png", "fps": 14, "loop": False},  # 3
}

# --- Warrior soldier (../Warrior) — 192×192 frames ------------------------
# NOTE: this is the root Warrior strip pack (Warrior_Idle.png, …), distinct
# from whatever folder-mode pack a Commander might use.
FRAME_SIZE_WARRIOR_SOLDIER: int = 192
WARRIOR_SOLDIER_SPRITE_FRAMES: dict = {
    "idle":   {"file": "Warrior_Idle.png",    "fps": 8,  "loop": True},   # 8
    "walk":   {"file": "Warrior_Run.png",     "fps": 12, "loop": True},   # 6
    "attack": {"file": "Warrior_Attack1.png", "fps": 16, "loop": False},  # 4
    "guard":  {"file": "Warrior_Guard.png",   "fps": 8,  "loop": True},   # 6  (taunt pose)
}
