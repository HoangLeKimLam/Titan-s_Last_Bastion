# characters/commanders/assets_config.py
# Sprite pack layouts for each commander.
# animation.load_clips() reads SPRITE_FRAMES, FRAME_WIDTH, FRAME_HEIGHT off each subclass.
#
# State names must match commander.py's state machine exactly:
#   idle / walk
#   attack1 / attack2 / attack3   — LMB 3-hit combo
#   skill_q / skill_e / skill_r   — Q / E / R skill animations
#   hurt / dying / win
from __future__ import annotations

# --- Mikasa (Knight_player_1.4 pack, 100×64 frames per strip) ---------------
FRAME_WIDTH_MIKASA: int = 100
FRAME_HEIGHT_MIKASA: int = 64

MIKASA_SPRITE_FRAMES: dict = {
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

# --- Eren (Knight 2D Pixel Art, with_outline variant, 96×84 frames) ------
FRAME_WIDTH_EREN: int = 96
FRAME_HEIGHT_EREN: int = 84

EREN_SPRITE_FRAMES: dict = {
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
