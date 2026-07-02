#!/usr/bin/env python3
"""
Pixel Art Top-Down RPG Map – mô phỏng Scene_Overview.png
Sử dụng texture gốc từ Pixel Art Top Down - Basic asset pack.

Điều khiển:
  Arrow Keys / WASD  – cuộn bản đồ
  ESC / Q            – thoát
"""

import pygame
import sys
import os
import random

SCREEN_W, SCREEN_H = 1024, 768
TILE = 32
FPS  = 60

VOID  = 0
GRASS = 1
PATH  = 2
STONE = 3

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR  = os.path.join(BASE_DIR, "assets", "Texture")
TEX_GRASS  = os.path.join(ASSET_DIR, "TX Tileset Grass.png")
TEX_STONE  = os.path.join(ASSET_DIR, "TX Tileset Stone Ground.png")
TEX_WALL   = os.path.join(ASSET_DIR, "TX Tileset Wall.png")
TEX_PATH   = os.path.join(ASSET_DIR, "TX Tileset Path.png")
TEX_STRUCT = os.path.join(ASSET_DIR, "TX Struct.png")
TEX_PLANT  = os.path.join(ASSET_DIR, "Extra", "TX Plant with Shadow.png")
TEX_PROPS  = os.path.join(ASSET_DIR, "TX Props.png")

RAW_MAP = [
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGPPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGPPPPPGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGPPPGGGGGGGGPPPGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGPPPGGGGGGGGPPPGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGPPPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGPPPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGPPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGPPPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGPPPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "......GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG.........GGGGGGGGGGGG",
  "....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG.......GGGGGGGGGGGG",
  "....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG.......GGGGGGGGGGGG",
  "..GGGGGGGGGGGGGGGGGPPPPPPPPPPPGGGGGGGGGGGGGGG.....GGGGGGGGGGGG",
  "..GGGGGGGGGGGGGGGGGPPPPPPPPPPPGGGGGGGGGGGGGGG.....GGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGPPPPPPPGGGGGGGGGGGGGGGGG..GGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGPPPPPPPPGGGGGGGGGGGGGGGGGGGGG..GGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGPPPPPPPPPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGPPPPPPPPPPPPPPPGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGPPPPPPPGGGGGGGGGGGGGGGGGG..GGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGPPPPPPGGGGGGGGGGGGGGGGGGGGGG..GGGGGGGGGGGG",
  "..GGGGGGGGGGGGGGGGGGGGGPPPPPGGGGGGGGGGGGGGGGGGGG...GGGGGGGGGGG",
  "..GGGGGGGGGGGGGGGGGGGGGPPPPGGGGGGGGGGGGGGGGGGG...GGGGGGGGGGGGG",
  "..GGGGGGGGGGGGPPPPPPPPPPPPPPPPPGGGGGGGGGGGGGGGG...GGGGGGGGGGGG",
  "..GGGGGGGGGGGGPPPPPPPPPPPPPPPPPGGGGGGGGGGGGGGGG...GGGGGGGGGGGG",
  "....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG.....GGGGGGGGGGGG",
  "....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG.....GGGGGGGGGGGG",
  "....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG.....GGGGGGGGGGGG",
  "....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG......GGGGGGGGGGG",
  "....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG......GGGGGGGGGGG",
  "....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG......GGGGGGGGGGG",
  "......GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG........GGGGGGG",
  "......GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGS........GGGGGG",
  "......GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG........GGGGGGG",
  "......GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG........GGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
  "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
]

MAP_H = len(RAW_MAP)
MAP_W = max(len(r) for r in RAW_MAP)

def parse_map(raw):
    grid = []
    for row in raw:
        r = []
        for ch in row.ljust(MAP_W, '.'):
            if   ch == 'G' or ch == '.': r.append(GRASS)
            elif ch == 'P': r.append(PATH)
            elif ch == 'S': r.append(STONE)
            else:           r.append(VOID)
        grid.append(r)
    return grid

MAP_GRID = parse_map(RAW_MAP)

OBJECTS = [
    # ── Perimeter trees
   
    # ── Internal wall segments (row 9)
    (15,  9, "wall_a", 0),  (17,  9, "wall_b", 0),  (20,  9, "wall_c", 0),
    (22,  9, "wall_a", 0),  (24,  9, "wall_b", 0),
    # ── Internal wall segments (row 17)
    (13, 17, "wall_b", 0),  (15, 17, "wall_a", 0),  (18, 17, "wall_c", 0),
    (20, 17, "wall_a", 0),  (22, 17, "wall_b", 0),  (25, 17, "wall_c", 0),
    (27, 17, "wall_a", 0),
    # ── Internal wall segments (row 32)
    (12, 32, "wall_a", 0),  (14, 32, "wall_b", 0),  (17, 32, "wall_c", 0),
    (19, 32, "wall_a", 0),  (21, 32, "wall_b", 0),  (24, 32, "wall_c", 0),
    (26, 32, "wall_a", 0),  (28, 32, "wall_b", 0),
    # ── Arch / gateway (center bottom of grass area)
    (20, 36, "arch", 0),
    # ── Stairs
    ( 3, 26, "stair_l", 0),
    (41, 26, "stair_r", 0),
    # ── Props
    (23,  2, "prop_well",       0),
    (20, 15, "prop_barrel",     0),  (22, 15, "prop_barrel_alt", 0),
    (27, 15, "prop_crate",      0),  (29, 15, "prop_crate2",     0),
    (17, 26, "prop_barrel",     0),
    (24, 26, "prop_crate2",     0),
    (29, 26, "prop_crate",      0),
    (14, 31, "prop_vase",       0),
    (31, 31, "prop_vase2",      0),
    (23, 32, "prop_barrel_alt", 0),
    ( 8, 38, "prop_vase",       0),
    (11, 38, "prop_crate",      0),
    (20, 38, "prop_crate2",     0),
    (30, 38, "prop_barrel",     0),
    (36, 38, "prop_vase2",      0),
     (20,  0, "tree", 0),  (26,  0, "tree", 1),
    (14,  4, "tree", 2),  (30,  5, "tree", 0),
    ( 9,  9, "tree", 1),  (35,  9, "tree", 2),
    ( 6, 14, "tree", 0),  (39, 15, "tree", 1),
    ( 2, 21, "tree", 2),  (43, 21, "tree", 0),
    ( 0, 25, "tree", 1),  (44, 24, "tree", 2),
    ( 2, 30, "tree", 0),  (42, 30, "tree", 1),
    ( 4, 35, "tree", 2),  (38, 36, "tree", 0),
    ( 7, 36, "tree", 1),
    # ── Interior trees
    (12,  6, "tree", 2),  (21,  4, "tree", 0),  (29,  6, "tree", 1),
    (10, 12, "tree", 1),  (22, 10, "tree", 2),  (33, 12, "tree", 0),
    ( 8, 18, "tree", 0),  (37, 18, "tree", 2),
    (13, 24, "tree", 1),  (31, 25, "tree", 0),
    (10, 29, "tree", 2),  (36, 29, "tree", 1),
    (16, 28, "tree", 0),  (26, 28, "tree", 2),
    (20, 35, "tree", 1),  (29, 34, "tree", 0),
    # ── Bushes
    (17,  2, "bush", 1),  (25,  2, "bush", 2),
    (14,  8, "bush", 0),  (28,  7, "bush", 1),
    (18, 11, "bush", 2),  (25, 11, "bush", 0),
    ( 7, 20, "bush", 1),  (38, 20, "bush", 2),
    (15, 23, "bush", 0),  (21, 23, "bush", 1),  (31, 23, "bush", 2),
    ( 6, 32, "bush", 0),  (38, 32, "bush", 1),
    (14, 35, "bush", 2),  (24, 35, "bush", 0),  (33, 35, "bush", 1),
    ( 9, 36, "bush", 2),  (35, 36, "bush", 0),
    # ── Shrubs
    (23,  7, "shrub", 1),
    (16, 15, "shrub", 0),  (30, 14, "shrub", 2),
    (12, 19, "shrub", 3),  (34, 21, "shrub", 1),
    (11, 30, "shrub", 4),  (37, 30, "shrub", 0),
    (18, 36, "shrub", 2),  (28, 36, "shrub", 3),
    (22, 19, "shrub", 0),  (26, 26, "shrub", 1),
]


def bake_tile_ids(grid):
    rng = random.Random(42)
    ids = []
    for ty in range(MAP_H):
        row = []
        for tx in range(MAP_W):
            cell = grid[ty][tx]
            if   cell == GRASS: row.append(rng.randint(0, 47))
            elif cell == PATH:  row.append(rng.randint(0, 47))
            elif cell == STONE: row.append(rng.randint(0, 47))
            else:               row.append(0)
        ids.append(row)
    return ids


def build_tile_cache(grass_sheet, path_sheet, stone_sheet):
    cache = {}
    ts = TILE
    gv = []
    for row in range(4):
        for col in range(8):
            gv.append(pygame.transform.scale(
                grass_sheet.subsurface(pygame.Rect(col*16+16, row*16, 16, 16)), (ts, ts)))
    for row in range(4, 8):
        for col in range(4):
            gv.append(pygame.transform.scale(
                grass_sheet.subsurface(pygame.Rect(col*16+16, row*16, 16, 16)), (ts, ts)))
    cache["grass"] = gv

    pv = []
    for row in range(6, 12):
        for col in range(8):
            pv.append(pygame.transform.scale(
                path_sheet, (ts, ts)))
    cache["path"] = pv

    sv = []
    for row in range(6):
        for col in range(8):
            sv.append(pygame.transform.scale(
                stone_sheet.subsurface(pygame.Rect(col*16, row*16, 16, 16)), (ts, ts)))
    cache["stone"] = sv
    return cache


def build_sprites(struct_sheet, plant_sheet, props_sheet, wall_sheet):
    sp = {}
    ts = TILE

    # Border wall faces from TX Tileset Wall (plain stone sections, no windows)
    # Block3 (rows 288-351): two 64×64 plain-stone variants
    # Block2 (rows 192-255): 128×64 band — take left 64px for a third variant
    for name, (rx, ry, rw, rh) in [
        ("wall_a", (32,  288, 64, 64)),
        ("wall_b", (128, 288, 64, 64)),
        ("wall_c", (32,  192, 64, 64)),
    ]:
        try:
            raw = wall_sheet.subsurface(pygame.Rect(rx, ry, rw, rh))
            sp[name] = pygame.transform.scale(raw, (ts * 2, ts * 2))
        except Exception:
            pass

    # Arch (verified: rows 27-90, cols 408-487)
    try:
        sp["arch"] = pygame.transform.scale(
            struct_sheet.subsurface(pygame.Rect(408, 27, 80, 64)), (ts * 3, ts * 2))
    except Exception:
        pass

    # Stairs
    try:
        sp["stair_l"] = pygame.transform.scale(
            struct_sheet.subsurface(pygame.Rect(32, 288, 140, 176)), (ts*5, ts*4))
        sp["stair_r"] = pygame.transform.scale(
            struct_sheet.subsurface(pygame.Rect(192, 288, 140, 176)), (ts*5, ts*4))
    except Exception:
        pass

    # Trees: 3 variants, each 128x128 in source
    for i, x in enumerate([0,0, 256]):
        try:
            sp[f"tree_{i}"] = pygame.transform.scale(
                plant_sheet.subsurface(pygame.Rect(x, 0, 128, 128)), (ts*4, ts*4))
        except Exception:
            pass

    # Bushes: 3 variants at y=128, each ~96px wide centered every 128px
    for i, x in enumerate([32, 150, 278]):
        try:
            sp[f"bush_{i}"] = pygame.transform.scale(
                plant_sheet.subsurface(pygame.Rect(x, 256, 64, 64)), (ts*2, ts*2))
        except Exception:
            pass

    # Shrubs: y=192, 6 variants spaced 64px
    for i in range(6):
        try:
            sp[f"shrub_{i}"] = pygame.transform.scale(
                plant_sheet.subsurface(pygame.Rect(i*64, 192, 64, 64)),
                (ts+ts//2, ts+ts//2))
        except Exception:
            pass

    # Props
    prop_defs = {
        "prop_barrel":     (7, 0),
        "prop_barrel_alt": (5, 2.5),
        "prop_crate":      (3, 0),
        "prop_crate2":     (3, 0),
        "prop_vase":       (6, 2.9),
        "prop_vase2":      (7, 2),
        "prop_well":       (6, 4),
    }
    for key, (col, row) in prop_defs.items():
        try:
            sp[key] = pygame.transform.scale(
                props_sheet.subsurface(pygame.Rect(col*64-32, row*64, 96, 80)),
                (ts*2, ts*2))
        except Exception:
            pass

    # TX Tileset Wall building interiors
    try:
        sp["bldg_window"] = pygame.transform.scale(
            wall_sheet.subsurface(pygame.Rect(32, 32, 96, 128)), (ts*3, ts*4))
    except Exception:
        pass
    try:
        sp["bldg_solid"] = pygame.transform.scale(
            wall_sheet.subsurface(pygame.Rect(160, 32, 160, 128)), (ts*5, ts*4))
    except Exception:
        pass

    return sp


def is_top_edge(tx, ty):
    if MAP_GRID[ty][tx] == VOID:
        return False
    above = MAP_GRID[ty-1][tx] if ty > 0 else VOID
    return above == VOID


def bake_wall_faces():
    """Build list of (tx, ty, variant_idx) for top-edge border walls."""
    faces = []
    for ty in range(MAP_H):
        covered = set()          # reset per row so each row gets its own segments
        for tx in range(MAP_W):
            if not is_top_edge(tx, ty) or tx in covered:
                continue
            vi = (tx // 2 + ty // 3) % 3
            faces.append((tx, ty, vi))
            covered.add(tx + 1)      # sprites are 2 tiles wide → skip only 1 col
    return faces


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Top-Down RPG Map  –  Scene Overview")
    clock = pygame.time.Clock()

    grass_sheet  = pygame.image.load(TEX_GRASS).convert_alpha()
    path_sheet   = pygame.image.load(TEX_PATH).convert_alpha()
    stone_sheet  = pygame.image.load(TEX_STONE).convert_alpha()
    wall_sheet   = pygame.image.load(TEX_WALL).convert_alpha()
    struct_sheet = pygame.image.load(TEX_STRUCT).convert_alpha()
    plant_sheet  = pygame.image.load(TEX_PLANT).convert_alpha()
    props_sheet  = pygame.image.load(TEX_PROPS).convert_alpha()

    tile_cache = build_tile_cache(grass_sheet,path_sheet, stone_sheet)
    sprites    = build_sprites(struct_sheet, plant_sheet, props_sheet, wall_sheet)
    tile_ids   = bake_tile_ids(MAP_GRID)
    wall_faces = bake_wall_faces()

    wf_names = ["wall_a", "wall_b", "wall_c"]

    rng_path = random.Random(77)
    path_base = [[rng_path.randint(0, 31) for _ in range(MAP_W)] for _ in range(MAP_H)]

    sorted_objects = sorted(OBJECTS, key=lambda o: (o[1], o[0]))

    world_w = MAP_W * TILE
    world_h = MAP_H * TILE
    cam_x = max(0, world_w // 2 - SCREEN_W // 2)
    cam_y = max(0, world_h // 2 - SCREEN_H // 2 - TILE * 4)
    CAM_SPEED = 8

    font = pygame.font.SysFont("monospace", 13)
    BG   = (28, 28, 32)

    running = True
    while running:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: cam_x -= CAM_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: cam_x += CAM_SPEED
        if keys[pygame.K_UP]    or keys[pygame.K_w]: cam_y -= CAM_SPEED
        if keys[pygame.K_DOWN]  or keys[pygame.K_s]: cam_y += CAM_SPEED
        cam_x = max(0, min(cam_x, max(0, world_w - SCREEN_W)))
        cam_y = max(0, min(cam_y, max(0, world_h - SCREEN_H)))

        col0 = max(0, cam_x // TILE)
        col1 = min(MAP_W, col0 + SCREEN_W // TILE + 3)
        row0 = max(0, cam_y // TILE)
        row1 = min(MAP_H, row0 + SCREEN_H // TILE + 4)

        screen.fill(BG)

        gv = tile_cache["grass"]
        pv = tile_cache["path"]
        sv = tile_cache["stone"]

        # PASS 1: Ground
        for ty in range(row0, row1):
            for tx in range(col0, col1):
                cell = MAP_GRID[ty][tx]
                if cell == VOID:
                    continue
                px = tx * TILE - cam_x
                py = ty * TILE - cam_y
                tid = tile_ids[ty][tx]
                if cell == GRASS:
                    screen.blit(gv[tid % len(gv)], (px, py))
                elif cell == PATH:
                    screen.blit(gv[path_base[ty][tx] % len(gv)], (px, py))
                    screen.blit(pv[tid % len(pv)], (px, py))
                elif cell == STONE:
                    screen.blit(sv[tid % len(sv)], (px, py))

        # PASS 2+3: Unified Y-sorted (walls + objects together)
        # Sort key: (ty*2) for wall faces → behind objects at same row
        #           (ty*2+1) for objects  → in front of walls at same row
        render_items = []

        # Wall faces: visual base is bottom of tile ty → base_row = ty+1
        for (tx, ty, vi) in wall_faces:
            if not (col0-2 <= tx <= col1+2 and row0-6 <= ty <= row1+1):
                continue
            spr = sprites.get(wf_names[vi % 3])
            if spr is None:
                continue
            px = tx * TILE - cam_x
            py = ty * TILE - cam_y
            render_items.append(((ty + 1) * 2, px, py - spr.get_height() + TILE, spr))

        for (tx, ty, kind, variant) in sorted_objects:
            if not (row0-8 <= ty <= row1+2 and col0-5 <= tx <= col1+5):
                continue
            gy = min(max(ty, 0), MAP_H-1)
            gx = min(max(tx, 0), MAP_W-1)
            if MAP_GRID[gy][gx] == VOID:
                continue
            px = tx * TILE - cam_x
            py = ty * TILE - cam_y
            spr = None
            bx, by = px, py
            base_row = ty + 1   # default visual base: one tile below map pos

            if kind == "tree":
                spr = sprites.get(f"tree_{variant % 3}")
                if spr:
                    sw, sh = spr.get_size()
                    bx = px - sw//2 + TILE//2
                    by = py - sh + TILE*2
                    base_row = ty + 2   # 4-tile-tall sprite; feet 2 rows below map pos
            elif kind == "bush":
                spr = sprites.get(f"bush_{variant % 3}")
                if spr:
                    bx = px - TILE//4
                    by = py - TILE//2
            elif kind == "shrub":
                spr = sprites.get(f"shrub_{variant % 6}")
                if spr:
                    by = py - TILE//4
            elif kind == "arch":
                spr = sprites.get("arch")
                if spr:
                    bx = px - spr.get_width()//2 + TILE//2
                    by = py - spr.get_height() + TILE
            elif kind == "stair_l":
                spr = sprites.get("stair_l")
                if spr:
                    bx = px - TILE
                    by = py - spr.get_height() + TILE*2
                    base_row = ty + 2
            elif kind == "stair_r":
                spr = sprites.get("stair_r")
                if spr:
                    bx = px - TILE*3
                    by = py - spr.get_height() + TILE*2
                    base_row = ty + 2
            elif kind.startswith("prop_"):
                spr = sprites.get(kind)
                if spr:
                    by = py - TILE

            if spr is not None:
                render_items.append((base_row * 2 + 1, bx, by, spr))

        render_items.sort(key=lambda item: item[0])
        for (_, bx, by, spr) in render_items:
            screen.blit(spr, (bx, by))

        # HUD
        hint = "WASD / ↑↓←→: cuộn bản đồ   ESC: thoát"
        sh = font.render(hint, True, (0, 0, 0))
        lb = font.render(hint, True, (210, 210, 210))
        screen.blit(sh, (11, SCREEN_H-23))
        screen.blit(lb, (10, SCREEN_H-24))

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
