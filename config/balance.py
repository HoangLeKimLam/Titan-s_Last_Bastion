# -*- coding: utf-8 -*-
"""config/balance.py — MỌI chỉ số CÂN BẰNG GAMEPLAY của Titan's Last Bastion.

Chỉnh sức mạnh (HP, damage, tầm, tốc độ, cooldown, chi phí, tỉ lệ sản xuất,
độ khó wave, tỉ lệ loot…) Ở ĐÂY — các file khác chỉ THAM CHIẾU, không giữ số cứng.

KHÔNG chứa (giữ nguyên tại file gốc): kích thước màn hình, FPS, TILE, màu sắc,
đường dẫn asset, số frame/fps animation, footprint ô (tw/th).

Đây là module DỮ LIỆU thuần: chỉ import ResourceBundle (dataclass thuần ở core/,
không kéo theo pygame) để mô tả chi phí — không import module game nào khác nên
KHÔNG THỂ gây vòng lặp import. Cách dùng ở file khác:
    from config import balance
    ... = balance.REGULAR_TITAN_HP
"""
from core.game_state import ResourceBundle


# ═══════════════════════════════════════════════════════════════════════════
# TITAN THƯỜNG  (titans_last_bastion/characters/titans/titan.py)
# ═══════════════════════════════════════════════════════════════════════════

# ── Titan (base ABC) ──
TITAN_HP                    = 100
TITAN_SPEED                 = 60.0
TITAN_DAMAGE                = 20
TITAN_ATTACK_RANGE          = 60.0
TITAN_SOLDIER_ATTACK_RANGE  = 60.0
TITAN_ATTACK_COOLDOWN       = 1.5
TITAN_VISUAL_RANGE          = 250.0   # phát hiện soldier/commander trong tầm này
TITAN_COLLISION_RADIUS      = 50.0    # bán kính thân (giẫm đạp / get_rect)

# ── RegularTitan ──
REGULAR_TITAN_HP              = 1000
REGULAR_TITAN_SPEED          = 60.0
REGULAR_TITAN_DAMAGE         = 50
REGULAR_TITAN_ATTACK_RANGE   = 30.0
REGULAR_TITAN_ATTACK_COOLDOWN = 0.75
REGULAR_TITAN_HEAVY_HP_RATIO = 0.5    # <= tỉ lệ này thì chuyển "đòn nặng"

# ── ArmoredTitan ──
ARMORED_TITAN_HP               = 2500
ARMORED_TITAN_SPEED            = 60.0
ARMORED_TITAN_DAMAGE           = 150
ARMORED_TITAN_ATTACK_RANGE     = 40.0
ARMORED_TITAN_ATTACK_COOLDOWN  = 1.0
ARMORED_TITAN_ARMOR_REDUCTION  = 0.7   # giảm 70% damage 'normal'
ARMORED_TITAN_HITS_TO_BREAK    = 25    # số đòn để vỡ giáp
ARMORED_TITAN_DASH_SPEED_MULT  = 3.0
ARMORED_TITAN_DASH_MAX_DIST    = 300.0
ARMORED_TITAN_DASH_HIT_RADIUS  = 18.0
ARMORED_TITAN_RAM_HIT_RADIUS   = 55.0
ARMORED_TITAN_STAGGER_DURATION = 0.3
ARMORED_TITAN_RECOIL_DIST      = 100.0

# ── Wolf ──
WOLF_HP               = 1500
WOLF_SPEED            = 70.0
WOLF_DAMAGE           = 70
WOLF_ATTACK_RANGE     = 40.0
WOLF_ATTACK_COOLDOWN  = 0.5

# ── TowerHunter ──
TOWER_HUNTER_HP              = 1500
TOWER_HUNTER_SPEED          = 70.0
TOWER_HUNTER_DAMAGE         = 70
TOWER_HUNTER_ATTACK_RANGE   = 40.0
TOWER_HUNTER_ATTACK_COOLDOWN = 0.5

# ── SoldierHunter ──
SOLDIER_HUNTER_HP              = 1500
SOLDIER_HUNTER_SPEED          = 70.0
SOLDIER_HUNTER_DAMAGE         = 70
SOLDIER_HUNTER_ATTACK_RANGE   = 40.0
SOLDIER_HUNTER_ATTACK_COOLDOWN = 0.75

# ── Kamikaze ──
KAMIKAZE_HP               = 1000
KAMIKAZE_SPEED            = 80.0
KAMIKAZE_DAMAGE           = 50
KAMIKAZE_ATTACK_RANGE     = 60.0
KAMIKAZE_ATTACK_COOLDOWN  = 1.0
KAMIKAZE_DETECT_RADIUS    = 300.0
KAMIKAZE_EXPLODE_RADIUS   = 60.0
KAMIKAZE_CLUSTER_RADIUS   = 60.0
KAMIKAZE_RUN_SPEED_MULT   = 1.5
KAMIKAZE_PRE_EXPLODE_PAUSE = 1.0
KAMIKAZE_EXP_AOE_RADIUS   = 80.0
KAMIKAZE_EXP_KNOCKBACK    = 80.0


# ═══════════════════════════════════════════════════════════════════════════
# BOSS  (titans_last_bastion/characters/titans/boss.py)
# ═══════════════════════════════════════════════════════════════════════════

# ── ColossalTitan ──
COLOSSAL_HP              = 10000
COLOSSAL_SPEED           = 40.0
COLOSSAL_DAMAGE          = 150
COLOSSAL_ATTACK_RANGE    = 40.0
COLOSSAL_ATTACK_COOLDOWN = 2.0
COLOSSAL_STEAM_AOE            = 150
COLOSSAL_STEAM_R_IN          = 40
COLOSSAL_STEAM_R_OUT         = 140
COLOSSAL_STEAM_PARTICLE_COUNT = 200
COLOSSAL_STEAM_PARTICLE_AOE  = 50
COLOSSAL_STEAM_FIRE_DMG      = 100   # damage lính khi dính steam
COLOSSAL_STEAM_BURN_DMG      = 150   # damage tướng khi dính steam
COLOSSAL_STEAM_COOLDOWN      = 8.0
COLOSSAL_STEAM_ANIM_DUR      = 3.0
COLOSSAL_STOMP_AOE           = 160
COLOSSAL_STOMP_STUN_DUR      = 5.0
COLOSSAL_STOMP_DMG           = 300
COLOSSAL_JUMP_COOLDOWN       = 10.0
COLOSSAL_JUMP_ANIM_DUR       = 1.5

# ── BeastTitan ──
BEAST_HP              = 12000
BEAST_SPEED           = 50.0
BEAST_DAMAGE          = 175
BEAST_ATTACK_RANGE    = 350.0   # tầm ném đá
BEAST_ATTACK_COOLDOWN = 2.0
BEAST_ROCK_VELOCITY     = 580.0  # fallback nếu công thức adaptive fail
BEAST_ROCK_VELOCITY_MIN = 200.0
BEAST_ROCK_VELOCITY_MAX = 800.0
BEAST_ROCK_ANGLE_DEG    = 15.0
BEAST_ROCK_GRAVITY      = 600.0
BEAST_ROCK_DAMAGE       = 175    # MỌI mục tiêu trong AoE ăn cùng lượng này
BEAST_ROCK_TOWER_STUN   = 10.0    # đá trúng tháp → choáng 10s
BEAST_ROCK_AOE_RADIUS   = 100.0
BEAST_PUSHBACK_SOLDIER   = 100.0
BEAST_PUSHBACK_COMMANDER = 50.0

# ── FoundingTitan ──
FOUNDING_HP              = 15000
FOUNDING_SPEED           = 50.0
FOUNDING_DAMAGE          = 200
FOUNDING_ATTACK_RANGE    = 80.0
FOUNDING_ATTACK_COOLDOWN = 3.0
FOUNDING_P1_HP_RATIO        = 0.8    # > 0.8 = phase 1
FOUNDING_P3_HP_RATIO        = 0.3    # <= 0.3 = phase 3
FOUNDING_SUMMON_TOTAL       = 5
FOUNDING_SUMMON_RADIUS      = 180.0
FOUNDING_SUMMON_WAVE_COOLDOWN = 15.0
FOUNDING_HEAL_ON_SUMMON_PCT = 0.30   # hồi 30% (max_hp - hp) mỗi lần triệu hồi
FOUNDING_HEAL_DEBUFF_PCT      = 0.10
FOUNDING_HEAL_DEBUFF_DURATION = 5.0
FOUNDING_MINION_HP     = 500
FOUNDING_MINION_SPEED  = 40.0
FOUNDING_MINION_DAMAGE = 40


# ═══════════════════════════════════════════════════════════════════════════
# CHIẾN LƯỢC TẤN CÔNG TITAN  (titans/attackstrategy.py) — hệ số nhân damage
# ═══════════════════════════════════════════════════════════════════════════
STRAT_MELEE_RUSH_MULT      = 1.5
STRAT_HEAVY_STRIKE_MULT    = 3.5
STRAT_INCURABLE_MULT       = 2.5   # antiheal (Wolf)
STRAT_ARMORED_RAM_MULT     = 20
STRAT_GROUND_SLAM_MULT     = 4.0   # đập đất + stun tháp
STRAT_EXPLOSION_MULT       = 4.0   # Kamikaze
STRAT_TOWER_HUNTER_MULT    = 3.0
STRAT_SOLDIER_HUNTER_MULT  = 3.0


# ═══════════════════════════════════════════════════════════════════════════
# AI TITAN  (titans/ai.py, titans/priority.py)
# ═══════════════════════════════════════════════════════════════════════════
AI_DEFAULT_ATTACK_RANGE = 60.0
AI_RUN_THRESHOLD        = 250.0   # khoảng cách > ngưỡng này thì chạy nước rút
AI_RUN_SPEED_MULT       = 1.5
AI_TELEGRAPH_DELAY      = 0.5     # 1s "ra đòn báo trước", hết thì check né
AI_KAMIKAZE_CMDR_EXPLODE_PAUSE = 1.0
PRIORITY_AGGRO_RANGE      = 360.0
PRIORITY_VIS_ROLL_COOLDOWN = 2.0


# ═══════════════════════════════════════════════════════════════════════════
# TƯỚNG  (characters/commanders/commander.py, mikasa.py, eren.py)
# ═══════════════════════════════════════════════════════════════════════════

# ── Commander (base) ──
COMMANDER_SKILL_COOLDOWNS   = {"Q": 5.0, "E": 8.0, "R": 30.0}
# Skill Q (slash combo)
COMMANDER_Q_RADIUS          = 80
COMMANDER_Q_HIT_COUNT       = 3
COMMANDER_Q_DAMAGE_PER_HIT  = 40
COMMANDER_Q_DASH_GAP        = 60
# Skill E (grappling swing)
COMMANDER_E_RANGE_PX          = 250
COMMANDER_E_MIN_RANGE_PX      = 60
COMMANDER_E_MAX_RANGE_PX      = 480
COMMANDER_E_BASE_CHARGES      = 6
COMMANDER_E_MAX_CHARGES       = 11
COMMANDER_E_BONUS_LIFETIME    = 6.0
COMMANDER_E_FLIGHT_DURATION   = 0.35
COMMANDER_E_AIM_TIMEOUT       = 3.0
COMMANDER_E_DOWNSWING_SLOWDOWN = 1.3
COMMANDER_E_TARGET_PAD_PX     = 24.0
# Stack damage đòn thường lên titan (125%/150%/200%/250%)
COMMANDER_TITAN_DMG_STACK_MULTS    = (1.25, 1.50, 2.00, 2.50)
COMMANDER_TITAN_STACK_RESET_WINDOW = 1.5
# Skill R (ult)
COMMANDER_R_DURATION = 10.0
COMMANDER_R_RADIUS   = 150
COMMANDER_R_DAMAGE   = 150
# Đòn đánh thường (LMB combo)
COMMANDER_BASIC_ATTACK_RADIUS            = 90
COMMANDER_BASIC_ATTACK_CONE_HALF_ANGLE_DEG = 28.0
COMMANDER_BASIC_ATTACK_MIN_LATERAL_PX    = 40.0
COMMANDER_BASIC_ATTACK_DAMAGES           = (25, 35, 60)
COMMANDER_COMBO_RESET_WINDOW             = 1.5
COMMANDER_COMBO_CANCEL_THRESHOLD         = 0.5
# Stat scaling
COMMANDER_BASE_HP       = 300
COMMANDER_HP_PER_LEVEL  = 40
COMMANDER_BASE_SPEED    = 150.0
COMMANDER_MAX_LEVEL     = 10
COMMANDER_DAMAGE_PCT_PER_LEVEL       = 0.15  # +15% dame mỗi cấp
COMMANDER_ATTACK_SPEED_PCT_PER_LEVEL = 0.05   # +5% tốc đánh mỗi cấp
COMMANDER_ANTI_HEAL_DURATION = 15.0           # Wolf antiheal chặn heal() (giây)
COMMANDER_UPGRADE_COSTS = {
    1: ResourceBundle(stone=30, wood=20),
    2: ResourceBundle(stone=50, wood=30, ore=5),
    3: ResourceBundle(stone=80, wood=40, ore=10),
    4: ResourceBundle(stone=120, wood=60, ore=20, fire_ore=2),
    5: ResourceBundle(stone=180, wood=90, ore=30, fire_ore=5),
}

# ── MikasaCommander ──
MIKASA_SKILL_COOLDOWNS    = {"Q": 5.0, "E": 5.0, "R": 30.0}
MIKASA_SKILL_UNLOCK_LEVEL = {"Q": 5, "R": 10}

# ── ErenCommander ──
EREN_SKILL_COOLDOWNS    = {"Q": 3.0, "E": 6.0, "R": 40.0}
EREN_SKILL_UNLOCK_LEVEL = {"Q": 3, "R": 5, "E": 10}
# Titan form (Eren hoá titan)
EREN_TITAN_MAX_HP       = 2000
EREN_TITAN_Q_DASH_SPEED = 800.0
EREN_TITAN_Q_DASH_DUR   = 0.4
EREN_TITAN_Q_DAMAGE     = 50
EREN_TITAN_Q_RADIUS     = 60.0
EREN_TITAN_E_RAGE_DUR    = 8.0
EREN_TITAN_E_RAGE_DRAIN  = 40    # HP drained per second
EREN_TITAN_E_AURA_RADIUS = 100.0
EREN_TITAN_E_AURA_DAMAGE = 30    # damage per tick (0.5s)


# ═══════════════════════════════════════════════════════════════════════════
# LÍNH  (characters/soldiers/soldier.py, projectile.py)
# ═══════════════════════════════════════════════════════════════════════════

# ── Soldier (base) ──
SOLDIER_BASE_HP         = 60
SOLDIER_DEFENSE         = 0
SOLDIER_SPEED           = 90.0
SOLDIER_ATTACK_DAMAGE   = 15
SOLDIER_ATTACK_RANGE    = 42.0
SOLDIER_ATTACK_COOLDOWN = 1.0
SOLDIER_HEAL_RATE = 5     # HP hồi mỗi tick khi ở trong tháp (IDLE)
SOLDIER_HEAL_TICK = 2.0   # giây giữa mỗi tick

# ── ArcherSoldier (ranged, dame cao, giòn) ──
ARCHER_HP              = 40
ARCHER_DEFENSE         = 0
ARCHER_SPEED           = 70.0
ARCHER_ATTACK_DAMAGE   = 30
ARCHER_ATTACK_RANGE    = 220.0
ARCHER_ATTACK_COOLDOWN = 1.0

# ── LancerSoldier (nhanh, thủ vừa) ──
LANCER_HP              = 75
LANCER_DEFENSE         = 3
LANCER_SPEED           = 135.0
LANCER_ATTACK_DAMAGE   = 30
LANCER_ATTACK_RANGE    = 44.0
LANCER_ATTACK_COOLDOWN = 0.6

# ── WarriorSoldier (trâu, chậm, dame thấp, TAUNTS) ──
WARRIOR_HP              = 200
WARRIOR_DEFENSE        = 8
WARRIOR_SPEED          = 48.0
WARRIOR_ATTACK_DAMAGE  = 10
WARRIOR_ATTACK_RANGE   = 38.0
WARRIOR_ATTACK_COOLDOWN = 1.0

# ── Arrow (đạn Archer) ──
ARROW_SPEED        = 520.0
ARROW_HIT_RADIUS   = 26.0
ARROW_MAX_LIFETIME = 2.0


# ═══════════════════════════════════════════════════════════════════════════
# CÔNG TRÌNH & PHÒNG THỦ  (structures/)
# ═══════════════════════════════════════════════════════════════════════════

# ── HQ (structures/hq.py) ──
HQ_HP = 5000

# ── Wall (structures/wall/wall.py) — HP mỗi đoạn tường ──
WALL_SECTION_HP = 10000

# ── Bẫy (structures/trap/trap.py) ──
THORN_TRAP_HP        = 500
THORN_TRAP_DAMAGE    = 20
THORN_TRAP_TICK_RATE = 1.0
SURIKEN_TRAP_HP        = 800
SURIKEN_TRAP_DAMAGE    = 30
SURIKEN_TRAP_TICK_RATE = 0.5
SURIKEN_WIND_PUSH_FORCE      = 600.0   # tổng lực đẩy Wind Breath (px)
SURIKEN_WIND_BREATH_DURATION = 1.0
POISON_TRAP_HP          = 300
POISON_TRAP_TICK_RATE   = 1.0
POISON_TRAP_TICK_DAMAGE = 10     # damage mỗi 0.5s khi đang nhiễm độc
EXPLODE_TRAP_RADIUS = 150.0
EXPLODE_TRAP_DAMAGE = 300
BAIT_TRAP_PHEROMONE_RADIUS = 400.0
BAIT_TRAP_DURATION         = 15.0


# ═══════════════════════════════════════════════════════════════════════════
# CÔNG TRÌNH SẢN XUẤT  (structures/buildings/building.py)
# ═══════════════════════════════════════════════════════════════════════════

# ── Building (base) ──
BUILDING_CYCLE_TIME        = 60.0
BUILDING_PRODUCTION_RATE   = 0
BUILDING_UPGRADE_RATE_MULT = 1.2   # base upgrade() nhân production rate

# ── Farm (food/s = rate/cycle) ──
FARM_CYCLE_TIME      = 60.0
FARM_PRODUCTION_RATE = 300
FARM_MAX_LEVEL       = 3
FARM_LEVEL_UPGRADE = {
    1: {'cost': ResourceBundle(wood=50,  stone=30),  'rate_bonus': 180},
    2: {'cost': ResourceBundle(wood=100, stone=60),  'rate_bonus': 520},
}

# ── StoneWorkshop ──
STONE_WS_CYCLE_TIME      = 60.0
STONE_WS_PRODUCTION_RATE = 8
STONE_WS_MAX_LEVEL       = 3
STONE_WS_LEVEL_UPGRADE = {
    1: {'cost': ResourceBundle(wood=60),           'rate_bonus': 4},
    2: {'cost': ResourceBundle(wood=120, ore=10),  'rate_bonus': 8},
}

# ── WoodWorkshop ──
WOOD_WS_CYCLE_TIME      = 60.0
WOOD_WS_PRODUCTION_RATE = 15
WOOD_WS_MAX_LEVEL       = 2
WOOD_WS_LEVEL_UPGRADE = {
    1: {'cost': ResourceBundle(stone=40), 'rate_bonus': 8},
}

# ── Forge (chế vũ khí — CYCLE 999 = không tự sản xuất) ──
FORGE_CYCLE_TIME      = 999
FORGE_PRODUCTION_RATE = 0
FORGE_MAX_LEVEL       = 3
FORGE_LEVEL_UPGRADE = {
    1: {'cost':  ResourceBundle(wood=100, stone=60,  ore=20),
        'bonus': ResourceBundle(tower_weapon=50, soldier_weapon=50, trap=20)},
    2: {'cost':  ResourceBundle(wood=200, stone=120, ore=50),
        'bonus': ResourceBundle(tower_weapon=100, soldier_weapon=100, trap=40)},
}
# Giới hạn vũ khí Forge cấp: KHỞI ĐẦU (chung + cụ thể cơ bản), phần CHUNG được
# track để trừ khi Forge vỡ, và XÂY THÊM (chỉ chung, nửa khởi đầu).
FORGE_INITIAL_LIMITS = ResourceBundle(
    tower_weapon=200, soldier_weapon=100, trap=50,
    basic_projectlie=100, thorn_trap=20, sword=50, spear=50, arrow=40,
)
FORGE_INITIAL_GENERAL = ResourceBundle(tower_weapon=200, soldier_weapon=100, trap=50)
FORGE_BUILD_LIMITS    = ResourceBundle(tower_weapon=100, soldier_weapon=50, trap=25)

# ── TrainingCamp ──
TRAININGCAMP_MAX_LEVEL = 3
TRAININGCAMP_SOLDIER_STATS = {
    'Warrior': {'train_time': 10.0, 'upkeep': 1.0, 'train_cost': 2.0},
    'Archer':  {'train_time': 12.0, 'upkeep': 0.8, 'train_cost': 1.5},
    'Lancer':  {'train_time': 20.0, 'upkeep': 2.0, 'train_cost': 4.0},
}
TRAININGCAMP_WEAPON_COST = {
    'Warrior': ('soldier_weapon', 'sword',  1),
    'Archer':  ('soldier_weapon', 'arrow',  10),
    'Lancer':  ('soldier_weapon', 'spear',  1),
}
TRAININGCAMP_LEVEL_UPGRADE = {
    1: {'cost': ResourceBundle(wood=80,  stone=50)},
    2: {'cost': ResourceBundle(wood=160, stone=100, ore=20)},
}

# ── RepairStation ──
REPAIR_STATION_AMOUNT = 50   # HP sửa tường mỗi cycle


# ═══════════════════════════════════════════════════════════════════════════
# THÁP  (structures/towers/tower.py, projectile.py)
# ═══════════════════════════════════════════════════════════════════════════

# ── Tower (base) ──
TOWER_MAX_LEVEL         = 2
TOWER_DMG_PER_ORB       = 50
TOWER_LV2_DMG_THRESHOLD = 300
TOWER_CAPACITY            = 8       # max squad chứa
TOWER_AGGRO_RADIUS        = 600   # titan vào bán kính → mở event
TOWER_WAVE_COOLDOWN       = 2.0
TOWER_EVENT_COOLDOWN      = 5.0
TOWER_MAX_WAVES_PER_EVENT = 3

# ── BasicTower ──
BASIC_TOWER_HP       = 2000
BASIC_TOWER_DAMAGE   = 100
BASIC_TOWER_RANGE    = 300
BASIC_TOWER_COOLDOWN = 2.0
BASIC_TOWER_MAX_LEVEL         = 2
BASIC_TOWER_DMG_PER_ORB       = 50
BASIC_TOWER_LV2_DMG_THRESHOLD = 300
BASIC_TOWER_EXPLOSION_RADIUS  = 80

# ── ElectricTower ──
ELECTRIC_TOWER_HP       = 2000
ELECTRIC_TOWER_DAMAGE   = 50
ELECTRIC_TOWER_RANGE    = 400
ELECTRIC_TOWER_COOLDOWN = 1.5
ELECTRIC_TOWER_MAX_LEVEL            = 2
ELECTRIC_TOWER_DMG_PER_ORB          = 50
ELECTRIC_TOWER_CHAIN_DMG_PER_ORB    = 10
ELECTRIC_TOWER_CHAIN_RADIUS_PER_ORB = 7
ELECTRIC_TOWER_LV2_DMG_THRESHOLD    = 300
ELECTRIC_TOWER_CHAIN_DAMAGE = 20   # self._chain_damage khởi tạo
ELECTRIC_TOWER_CHAIN_RANGE  = 50   # self._chain_range khởi tạo

# ── WaterTower ──
WATER_TOWER_HP       = 3000
WATER_TOWER_DAMAGE   = 75
WATER_TOWER_RANGE    = 300
WATER_TOWER_COOLDOWN = 1.5
WATER_TOWER_MAX_LEVEL         = 2
WATER_TOWER_DMG_PER_ORB       = 40
WATER_TOWER_RADIUS_PER_ORB    = 10
WATER_TOWER_LV2_DMG_THRESHOLD = 300
WATER_TOWER_PUSH_FORCE  = 60
WATER_TOWER_KB_DURATION = 0.3
WATER_TOWER_PUSH_RADIUS = 70   # self._push_radius khởi tạo

# ── IceTower ──
ICE_TOWER_HP       = 3000
ICE_TOWER_DAMAGE   = 75
ICE_TOWER_RANGE    = 400
ICE_TOWER_COOLDOWN = 1.5
ICE_TOWER_MAX_LEVEL              = 3
ICE_TOWER_DURATION_PER_ORB       = 0.5
ICE_TOWER_LV2_DURATION_THRESHOLD = 4.0
ICE_TOWER_SLOW_FACTOR_PER_ORB    = 0.05
ICE_TOWER_SPLASH_RADIUS_PER_ORB  = 8
ICE_TOWER_LV3_FACTOR_THRESHOLD   = 0.75
ICE_TOWER_SLOW_DURATION   = 2.0   # self._slow_duration khởi tạo
ICE_TOWER_SLOW_FACTOR     = 0.4   # self._slow_factor khởi tạo
ICE_TOWER_SPLASH_RADIUS   = 80    # self._splash_radius khởi tạo
ICE_TOWER_LV3_SLOW_FACTOR = 0.97  # boost khi lên Lv3

# ── Projectile (đạn tháp) ──
TOWER_PROJECTILE_SPEED    = 400   # base Projectile.SPEED
ELECTRIC_FIELD_DURATION   = 5.0
ELECTRIC_FIELD_ZAP_PERIOD = 0.5
WATER_VORTEX_DURATION   = 3.0
WATER_VORTEX_PULL_SPEED = 40
WATER_VORTEX_SPIN_SPEED = 60
WATER_VORTEX_MIN_DIST   = 10


# ═══════════════════════════════════════════════════════════════════════════
# WAVE / ĐỘ KHÓ  (systems/wave_manager.py, game.py TT_*)
# ═══════════════════════════════════════════════════════════════════════════

# ── Vượt Ải (systems/wave_manager.py) ──
WAVE_TITAN_COSTS = {
    'Regular': 15, 'Wolf': 20, 'Kamikaze': 20,
    'SoldierHunter': 25, 'TowerHunter': 25, 'Armored': 45,
}
WAVE_DEFAULT_WEIGHTS = {
    'Regular': 50, 'Wolf': 25, 'Kamikaze': 15,
    'SoldierHunter': 7, 'TowerHunter': 3, 'Armored': 0,
}
WAVE_GROUP_MIN = 2
WAVE_GROUP_MAX = 4

# ── Thao Trường Tự Do (game.py TT_*) ──
TT_TITAN_COSTS = {
    'Regular': 15, 'Wolf': 20, 'Kamikaze': 20,
    'SoldierHunter': 25, 'TowerHunter': 25, 'Armored': 45,
}
TT_TITAN_UNLOCK_LEVEL = {
    'Regular': 1, 'Wolf': 1, 'Kamikaze': 2,
    'SoldierHunter': 2, 'TowerHunter': 3, 'Armored': 4,
}
TT_WEIGHTS = {
    'tier1': {'Regular': 55, 'Wolf': 25, 'Kamikaze': 15, 'SoldierHunter': 5,  'TowerHunter': 0,  'Armored': 0},
    'tier2': {'Regular': 35, 'Wolf': 25, 'Kamikaze': 20, 'SoldierHunter': 10, 'TowerHunter': 10, 'Armored': 0},
    'tier3': {'Regular': 20, 'Wolf': 20, 'Kamikaze': 20, 'SoldierHunter': 18, 'TowerHunter': 15, 'Armored': 7},
    'tier4': {'Regular': 15, 'Wolf': 18, 'Kamikaze': 18, 'SoldierHunter': 20, 'TowerHunter': 17, 'Armored': 12},
}
TT_BUDGET_BASE     = 300    # ngân sách wave 0
TT_BUDGET_PER_WAVE = 80     # ngân sách thêm mỗi wave
TT_BUDGET_CAP      = 2000   # trần ngân sách
TT_MAX_TITANS      = 150    # số titan tối đa / wave
TT_WAVE_CAP        = 20     # sau wave 20 độ khó bão hoà
TT_SPAWN_OFFSET    = 8      # số tile cách tường khi spawn
TT_CORNER_MARGIN   = 16     # né vùng GÓC khi spawn


# ═══════════════════════════════════════════════════════════════════════════
# LOOT  (systems/loot_system.py)
# ═══════════════════════════════════════════════════════════════════════════
LOOT_TABLE = {
    'Titan': [('ore', 0.5), ('wood', 0.4), ('stone', 0.4)],
    'RegularTitan': [('ore', 0.6), ('anti_stun', 0.2)],
    'ArmoredTitan': [('anti_armor_ore', 0.5), ('stone', 0.8), ('serum', 0.1)],
    'ColossalTitan': [('fire_ore', 0.8), ('serum', 0.5), ('titan_pheromone', 0.2)],
    'BeastTitan': [('titan_pheromone', 1.0), ('acid_ore', 0.5), ('wood', 0.8)],
    'FoundingTitan': [('serum', 1.0), ('titan_pheromone', 1.0), ('electric_ore', 0.8)],
}


# ═══════════════════════════════════════════════════════════════════════════
# KINH TẾ / TOÀN CỤC  (game.py, structures/buildings/resource_manager.py)
# ═══════════════════════════════════════════════════════════════════════════
COMMANDER_CASTLE_HEAL_RATE = 20     # HP hồi mỗi tick khi tướng đứng trong castle
COMMANDER_CASTLE_HEAL_TICK = 1.0    # giây giữa mỗi tick
DEFEAT_PENALTY_KEEP_RATIO  = 0.8    # thua → giữ 80% tài nguyên (mất 20%)


# ═══════════════════════════════════════════════════════════════════════════
# CHI PHÍ VŨ KHÍ & CHẾ TẠO  (game.py)
# ═══════════════════════════════════════════════════════════════════════════

# Chi phí vũ khí để ĐẶT tháp / bẫy — (gen_slot, spec_slot, amount)
TOWER_WEAPON_COST = {
    'BasicTower':    ('tower_weapon', 'basic_projectlie',    10),
    'ElectricTower': ('tower_weapon', 'electric_projectlie', 10),
    'WaterTower':    ('tower_weapon', 'water_projectlie',    10),
    'IceTower':      ('tower_weapon', 'ice_projectlie',      10),
}
TRAP_WEAPON_COST = {
    'ThornTrap':   ('trap', 'thorn_trap',   1),
    'SurikenTrap': ('trap', 'suriken_trap', 1),
    'PoisonTrap':  ('trap', 'poison_trap',  1),
    'ExplodeTrap': ('trap', 'explode_trap', 1),
    'BaitTrap':    ('trap', 'bait_trap',    1),
}

# Chi phí XÂY (gỗ/đá/quặng) từng loại building/tower/trap trong shop. Mặc
# định 0 (chưa cân bằng) — chỉnh trực tiếp các số ở đây, không cần sửa game.py.
BUILD_COSTS = {
    'WoodWorkshop':  {'wood': 0, 'stone': 0, 'ore': 0},
    'Farm':          {'wood': 0, 'stone': 0, 'ore': 0},
    'Forge':         {'wood': 0, 'stone': 0, 'ore': 0},
    'StoneWorkshop': {'wood': 0, 'stone': 0, 'ore': 0},
    'BasicTower':    {'wood': 0, 'stone': 0, 'ore': 0},
    'ElectricTower': {'wood': 0, 'stone': 0, 'ore': 0},
    'WaterTower':    {'wood': 0, 'stone': 0, 'ore': 0},
    'IceTower':      {'wood': 0, 'stone': 0, 'ore': 0},
    'ThornTrap':     {'wood': 0, 'stone': 0, 'ore': 0},
    'SurikenTrap':   {'wood': 0, 'stone': 0, 'ore': 0},
    'PoisonTrap':    {'wood': 0, 'stone': 0, 'ore': 0},
    'ExplodeTrap':   {'wood': 0, 'stone': 0, 'ore': 0},
    'BaitTrap':      {'wood': 0, 'stone': 0, 'ore': 0},
}

# Số lượng quặng (loại ORB_FIELD riêng từng tháp: ore/electric_ore/water_ore/
# ice_ore) tiêu tốn MỖI LẦN bấm nút UPGRADE trong menu tháp (apply_orb) —
# đây là chi phí CHO MỖI ĐƠN VỊ orb nạp vào, không phải tổng chi phí lên
# hẳn 1 cấp (mỗi orb cộng dồn damage tới khi đủ ngưỡng LV2_DMG_THRESHOLD
# thì tự động lên cấp).
TOWER_ORB_COST = {
    'BasicTower':    1,
    'ElectricTower': 1,
    'WaterTower':    1,
    'IceTower':      1,
}

# Công thức CHẾ TẠO — (key, ore_key, color, label, ore_cost, amount_gain)
# ore_cost / amount_gain là 2 số cân bằng; color/label chỉ để hiển thị.
PROJ_CRAFT_DEFS = [
    ('basic_projectlie',     'ore',           (200, 200, 200), 'Dan Thuong', 5, 20),
    ('ice_projectlie',       'ice_ore',        ( 80, 200, 240), 'Dan Bang',   5, 20),
    ('electric_projectlie',  'electric_ore',   (240, 220,  40), 'Dan Dien',   5, 20),
    ('water_projectlie',     'water_ore',      ( 60, 140, 220), 'Dan Nuoc',   5, 20),
]
TRAP_CRAFT_DEFS = [
    ('thorn_trap',    'ore',          (150, 150, 150), 'Bay Gai',      5, 5),
    ('suriken_trap',  'wind_ore',     (100, 200, 200), 'Bay Phi Tieu', 5, 5),
    ('poison_trap',   'acid_ore',     ( 80, 200,  80), 'Bay Doc',      5, 3),
    ('explode_trap',  'fire_ore',     (240, 100,  40), 'Bay No',       5, 3),
    ('bait_trap',     'titan_pheromone', (240, 200,  40), 'Bay Moi Nhu',  5, 2),
]
WEAPON_CRAFT_DEFS = [
    ('sword',         'ore',          (200, 200, 200), 'Kiem',         5, 10),
    ('spear',         'ore',          (200, 200, 200), 'Giao',         5, 10),
    ('arrow',         'wood',         (150, 100,  50), 'Cung Ten',     5, 15),
]

# Cấp trại tối thiểu để mở khoá loại lính
TC_LOCKED_LV = {'Lancer': 3}
