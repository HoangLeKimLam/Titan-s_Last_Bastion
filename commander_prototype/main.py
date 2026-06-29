"""main.py — pygame test harness for the commander prototype.

Run from the prototype root:

    cd commander_prototype
    python main.py

Controls:
    WASD       — move ACTIVE commander
    LMB        — basic-attack combo (attack1 → attack2 → attack3 → wrap)
                 If the click lands on a Tower → opens its garrison menu instead.
    Q / R      — skills (Slash Combo dash / Titan Form invincibility)
    E          — Grappling Swing (đu dây):
                   1st E  → enter AIMING (vòng tròn vàng + mũi tên theo chuột).
                            Chuột càng XA = bay càng xa; càng GẦN = bay ngắn
                            (range clamp [E_MIN_RANGE_PX..E_MAX_RANGE_PX]).
                            Chỉ bay được khi mũi tên hướng vào CÔNG TRÌNH (tháp)
                            hoặc TITAN: mũi tên ĐẬM = bay được, NHẠT = chưa được.
                   2nd E  → launch swing theo hướng + khoảng cách chuột (nếu hợp lệ).
                   E while FLYING → redirect ngay sang mục tiêu con trỏ đang
                            chỉ vào (titan/công trình) mà KHÔNG cần dừng để ngắm.
                            Tốn 1 charge; con trỏ ở chỗ trống thì bỏ qua, bay tiếp.
                   Đu XUỐNG (điểm đáp nằm dưới) bay chậm hơn ~30%.
                   chain up to 6 swings per session (E_BASE_CHARGES=6);
                   LMB hit on a LargeTitan during a swing grants +1 bonus
                   charge (cap 11) that decays after 6s.
    SPACE      — cancel current E session (drops in place if mid-flight)
    1 / 2 / 3  — switch active commander (1=Eren, 2=Mikasa, 3=Armin)
                 Camera follows the active commander across the larger world.
    T          — spawn a DummyTitan at the mouse cursor
    B          — spawn a LargeTitan at the mouse cursor (bonus-eligible)
    M          — toggle the strategic MINI-MAP (resource collection):
                   send expedition teams to explore locked forests/caves or
                   collect random items; send mining teams (specify amount) to
                   opened zones; upgrade "Khả năng thám hiểm" to cut explore time.
                   Up to 3 teams run in parallel; gains feed ResourceManager.
    ESC        — close the mini-map if open, otherwise quit

Squads are spawned ONLY by Towers (auto-deploy when a titan enters a tower's
AGGRO_RADIUS). The old THÀNH (BASE_RECT) + HUD-deploy + RMB-select-titan flow
has been removed — soldiers are bound to the tower that spawned them and
retreat there to heal when no titan is in range.
"""
from __future__ import annotations

import logging
import random
import sys

import pygame

from _core.event_bus import GameEventBus
from armin import ArminCommander
from eren import ErenCommander
from input_handler import PlayerInputHandler
from mikasa import MikasaCommander
from resource_map import MapState
from resource_map_screen import ResourceMapScreen
from stubs import DummyTitan, LargeTitan, ResourceManager, WorldQuery
from tower import Tower
from tower_menu import TowerMenu

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

WIDTH, HEIGHT = 960, 600           # window (camera viewport) size
WORLD_WIDTH, WORLD_HEIGHT = 2880, 1800   # the playable map — larger than the window
FPS = 60

# Visual-only terrain — tall rectangles for swing-target reference.
# (x, y_top, w, h)  — drawn behind everything; no collision. Spread across the
# whole (bigger) world so there are grapple targets everywhere.
TERRAIN_RECTS: list = [
    (200,  300, 70, 380),
    (760,  180, 80, 460),
    (1340, 520, 70, 420),
    (1880, 240, 90, 500),
    (2480, 700, 70, 440),
    (520,  1180, 80, 420),
    (1620, 1240, 90, 400),
    (2300, 1300, 70, 380),
]


def spawn_initial_titans(n: int = 8) -> None:
    for _ in range(n):
        x = random.randint(120, WORLD_WIDTH - 120)
        y = random.randint(120, WORLD_HEIGHT - 120)
        WorldQuery.register(DummyTitan(x, y, hp=200))


# Two defensive towers on either side of world centre. Soldiers spawn only
# from these towers; each tower defines its own patrol zone (AGGRO_RADIUS).
TOWER_SPAWNS: list = [
    (int(WORLD_WIDTH * 0.35), int(WORLD_HEIGHT * 0.50)),
    (int(WORLD_WIDTH * 0.65), int(WORLD_HEIGHT * 0.50)),
]


def _tower_under_world_point(wx: float, wy: float, towers: list):
    """Return the tower whose `bounds()` rect contains world point (wx, wy)."""
    for tower in towers:
        if not getattr(tower, "is_alive", True):
            continue
        if tower.bounds().collidepoint(int(wx), int(wy)):
            return tower
    return None


def _draw_active_marker(screen, commander, font) -> None:
    """Yellow downward-arrow above the active commander's head."""
    cx = int(commander.x)
    top_y = int(commander.y) - 150
    pygame.draw.polygon(
        screen, (255, 220, 60),
        [(cx - 10, top_y), (cx + 10, top_y), (cx, top_y + 12)],
    )
    label = font.render("ACTIVE", True, (255, 220, 60))
    screen.blit(label, label.get_rect(midbottom=(cx, top_y - 2)))


def _draw_terrain(screen) -> None:
    """Tall stone-coloured rectangles — visual swing targets, no collision."""
    for x, y, w, h in TERRAIN_RECTS:
        pygame.draw.rect(screen, (60, 55, 50), (x, y, w, h))
        pygame.draw.rect(screen, (95, 88, 78), (x, y, w, h), 2)
        # Light cap so it reads as a "tower"
        pygame.draw.rect(screen, (110, 100, 88), (x - 4, y - 8, w + 8, 10))


def _compute_camera(commander) -> tuple:
    """Top-left world coords of the viewport so the active commander is centred,
    clamped to the world bounds (no scrolling past the edges)."""
    cam_x = commander.x - WIDTH / 2
    cam_y = commander.y - HEIGHT / 2
    cam_x = max(0.0, min(float(WORLD_WIDTH - WIDTH), cam_x))
    cam_y = max(0.0, min(float(WORLD_HEIGHT - HEIGHT), cam_y))
    return (cam_x, cam_y)


def _mouse_world_pos(cam: tuple) -> tuple:
    """Mouse cursor position translated from screen space into world space."""
    mx, my = pygame.mouse.get_pos()
    return (mx + cam[0], my + cam[1])


def _mouse_aim_vector(commander, cam: tuple) -> tuple:
    """Raw (dx, dy) from commander to the mouse (in WORLD space) — magnitude =
    swing distance. Commander.set_aim_direction extracts direction (normalized)
    + range (clamped) from it, so the cursor scales the swing distance.
    """
    wx, wy = _mouse_world_pos(cam)
    dx = wx - commander.x
    dy = (wy - 40) - commander.y  # aim from head area, not feet
    if dx == 0 and dy == 0:
        return (1.0, 0.0)
    return (dx, dy)


def main() -> int:
    pygame.init()
    pygame.display.set_caption("Commander Prototype — Eren + Mikasa + Armin")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    # Off-screen surface the whole world is drawn onto; the camera blits a
    # viewport-sized sub-rect of it to the screen each frame.
    world_surf = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)
    small_font = pygame.font.SysFont("consolas", 12)

    # HUD event log
    log_lines: list = []

    def on_titan_died(data) -> None:
        log_lines.append(f"Titan {data['titan_id']} died")

    def on_commander_defeated(data) -> None:
        log_lines.append(
            f"{data['name']} defeated: lv {data['old_level']} → {data['new_level']}"
        )

    def on_e_session_started(data) -> None:
        log_lines.append(
            f"{data['name']} E session: {data['charges']} charges "
            f"({data['bonus_in_session']} bonus)"
        )

    def on_bonus_added(data) -> None:
        log_lines.append(
            f"{data['name']} +1 bonus charge → {data['charges']} total"
        )

    bus = GameEventBus.get_instance()
    bus.subscribe("titan_died", on_titan_died)
    bus.subscribe("commander_defeated", on_commander_defeated)
    bus.subscribe("e_session_started", on_e_session_started)
    bus.subscribe("e_charge_bonus_added", on_bonus_added)

    cy0 = WORLD_HEIGHT // 2
    eren = ErenCommander(x=WORLD_WIDTH // 2 - 160, y=cy0)
    mikasa = MikasaCommander(x=WORLD_WIDTH // 2, y=cy0)
    armin = ArminCommander(x=WORLD_WIDTH // 2 + 160, y=cy0)
    switch_keys = {
        pygame.K_1: eren,
        pygame.K_2: mikasa,
        pygame.K_3: armin,
    }
    active = eren
    WorldQuery.register(eren)
    WorldQuery.register(mikasa)
    WorldQuery.register(armin)
    # Register the terrain towers as grapple targets (công trình) so the E
    # aim can validate against them.
    for rect in TERRAIN_RECTS:
        WorldQuery.register_structure(rect)
    # Defensive towers — registered in WorldQuery so their `update(dt)` fires
    # from the main loop, and their bounds become grapple anchors as well.
    towers: list = [Tower(x, y, headless=False) for (x, y) in TOWER_SPAWNS]
    for tower in towers:
        WorldQuery.register(tower)
        WorldQuery.register_structure(tower.bounds())
    spawn_initial_titans(3)

    # Mini-map dispatch/collection meta-layer (press M to open the strategic map).
    map_state = MapState()
    map_state.seed_default_zones()
    map_screen: ResourceMapScreen | None = None

    inputs = PlayerInputHandler()
    active_menu: TowerMenu | None = None
    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0
        cam = _compute_camera(active)   # follow the active commander
        lmb_consumed = False            # menu/tower-click consumed this frame
        map_open = map_screen is not None and map_screen.is_open

        for event in pygame.event.get():
            # Strategic mini-map (if open) eats LMB clicks first.
            if map_open and map_screen is not None:
                if map_screen.handle_event(event):
                    lmb_consumed = True
                    continue
            # Tower menu (if open) eats LMB first; outside-click closes the menu.
            if active_menu is not None and active_menu.is_open:
                if active_menu.handle_event(event):
                    lmb_consumed = True
                    if not active_menu.is_open:
                        active_menu = None
                    continue
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_m:
                    # Toggle the strategic mini-map.
                    if map_open and map_screen is not None:
                        map_screen.close()
                        map_screen = None
                        map_open = False
                    else:
                        map_screen = ResourceMapScreen(map_state, (WIDTH, HEIGHT))
                        map_open = True
                elif event.key == pygame.K_ESCAPE:
                    # ESC closes the map if open; otherwise quits.
                    if map_open and map_screen is not None:
                        map_screen.close()
                        map_screen = None
                        map_open = False
                    else:
                        running = False
                elif map_open:
                    # While the strategic map is focused, suppress tactical keys.
                    pass
                elif event.key in switch_keys:
                    active = switch_keys[event.key]
                    log_lines.append(f"Switched to {active.NAME}")
                elif event.key == pygame.K_t:
                    wx, wy = _mouse_world_pos(cam)
                    WorldQuery.register(DummyTitan(wx, wy, hp=200))
                elif event.key == pygame.K_b:
                    wx, wy = _mouse_world_pos(cam)
                    WorldQuery.register(LargeTitan(wx, wy))
                    log_lines.append(f"Spawned LargeTitan at ({int(wx)},{int(wy)})")
                elif event.key == pygame.K_e:
                    # E is special:
                    #   idle    → begin_aim
                    #   aiming  → confirm_swing (only fires if locked on anchor)
                    #   flying  → interrupt mid-air and re-aim at another công trình
                    if active._e_state == "idle":
                        active.begin_aim()
                    elif active._e_state == "aiming":
                        active.confirm_swing(_mouse_aim_vector(active, cam))
                    elif active._e_state == "flying":
                        # Redirect mid-air toward the cursor (no stop-to-aim)
                        active.redirect_flight(*_mouse_aim_vector(active, cam))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # LMB on a tower opens its garrison menu and suppresses the
                # basic_attack that would otherwise fire below.
                wx, wy = _mouse_world_pos(cam)
                twr = _tower_under_world_point(wx, wy, towers)
                if twr is not None:
                    active_menu = TowerMenu(twr, screen_size=(WIDTH, HEIGHT))
                    lmb_consumed = True

        # The map may have been toggled during the event loop — refresh the
        # focus flag so tactical input is gated on the CURRENT state, not the
        # value sampled at the top of the frame.
        map_open = map_screen is not None and map_screen.is_open

        # --- Input applies to the ACTIVE commander (suspended while the
        #     strategic mini-map is focused) ---
        if not map_open:
            # Movement disabled during E flight (commander is in lerp control)
            if active._e_state != "flying":
                vx, vy = inputs.movement_vector()
                if vx or vy:
                    active.move((active.x + vx * 6, active.y + vy * 6))

            # Q / R remain edge-triggered via PlayerInputHandler.
            # E is handled in the event loop above (needs aim toggle).
            skill = inputs.triggered_skill()
            if skill is not None:
                active.use_skill(skill)

            if inputs.mouse_left_clicked() and not lmb_consumed:
                active.basic_attack()
            if inputs.space_pressed():
                active.cancel_swing()

            # Live aim direction + range follow the mouse during AIMING/FLYING.
            if active._e_state == "aiming":
                ax, ay = _mouse_aim_vector(active, cam)
                active.set_aim_direction(ax, ay)  # magnitude → swing range
            elif active._e_state == "flying":
                ax, ay = _mouse_aim_vector(active, cam)
                active.update_flight_aim(ax, ay)
        else:
            # Drain the polled edge-trigger states so they don't fire on the
            # frame the map closes.
            inputs.movement_vector()
            inputs.triggered_skill()
            inputs.mouse_left_clicked()
            inputs.space_pressed()

        # --- Update meta + world + cull dead entities ---
        map_state.update(dt)
        for entity in WorldQuery.all():
            entity.update(dt)
        for entity in WorldQuery.all():
            if not getattr(entity, "is_alive", True):
                WorldQuery.unregister(entity)

        # --- Draw (world space onto world_surf, then blit camera viewport) ---
        cam_rect = pygame.Rect(int(cam[0]), int(cam[1]), WIDTH, HEIGHT)
        world_surf.fill((30, 30, 36), cam_rect)   # clear only the visible region
        _draw_terrain(world_surf)
        for entity in WorldQuery.all():
            entity.draw(world_surf)
        _draw_active_marker(world_surf, active, small_font)
        screen.blit(world_surf, (0, 0), cam_rect)

        e_state = active._e_state
        e_ch = active._e_charges
        e_pool = active._e_bonus_pool + active._e_bonus_count_in_session
        e_ttl = active._e_bonus_timer if e_pool > 0 else 0.0
        if e_state in ("aiming", "flying"):
            e_lock = "CAN FLY" if active._e_aim_valid else "aim a target"
        else:
            e_lock = "-"
        stack = active.titan_stack
        # Multiplier the NEXT connecting hit will use (index capped at last).
        next_idx = min(stack, len(active.TITAN_DMG_STACK_MULTS) - 1)
        stack_pct = int(active.TITAN_DMG_STACK_MULTS[next_idx] * 100)
        soldier_count = sum(
            1 for e in WorldQuery.all()
            if getattr(e, "ENTITY_TYPE", None) == "soldier" and e.is_alive
        )
        tower_summary = ", ".join(
            f"{t.total_garrison()}/{Tower.CAPACITY}[{t.state[:3]}]"
            for t in towers
        )
        stock = ResourceManager.get_instance().stock
        hud_lines = [
            f"FPS: {clock.get_fps():.0f}    Active: [{active.NAME}]",
            f"Lv {active.level}  HP {active.hp}/{active.max_hp}",
            f"CD  Q={active.get_cooldown('Q'):.1f}  "
            f"E={active.get_cooldown('E'):.1f}  "
            f"R={active.get_cooldown('R'):.1f}",
            f"E: {e_state:6s} [{e_lock}]  charges={e_ch}/{active.E_MAX_CHARGES}  "
            f"bonus_pool={e_pool}  ttl={e_ttl:.1f}s",
            f"Combo next: attack{active.combo_step + 1}  base 25/35/60  "
            f"| Titan stack x{stack} ({stack_pct}% next)",
            f"Soldiers alive: {soldier_count}",
            f"Towers ({len(towers)}): {tower_summary}   (LMB tháp → menu)",
            f"Stock: wood={stock.wood} stone={stock.stone} gas={stock.gas} "
            f"ore={stock.ore}  |  Map[M]: doi {map_state.teams_busy}/"
            f"{map_state.TEAMS_TOTAL} expl Lv{map_state.exploration_level}",
            "WASD=move  LMB=atk/tower-menu  Q/R=skill  E=swing  SPACE=cancel  "
            "1/2/3=switch  T=titan  B=LargeTitan  M=map  ESC=quit",
        ]
        for i, line in enumerate(hud_lines):
            screen.blit(font.render(line, True, (230, 230, 230)),
                        (10, 10 + i * 18))

        for i, line in enumerate(log_lines[-4:]):
            screen.blit(font.render(line, True, (200, 200, 120)),
                        (10, HEIGHT - 80 + i * 18))

        # Tower menu overlay (screen-space) — drawn last so it sits above HUD.
        if active_menu is not None:
            if active_menu.is_open:
                active_menu.draw(screen)
            else:
                active_menu = None

        # Strategic mini-map overlay — drawn above everything when open.
        if map_screen is not None:
            if map_screen.is_open:
                map_screen.draw(screen)
            else:
                map_screen = None

        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
