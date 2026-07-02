# CONTEXT.md — Auto-updated project state
_Last updated: 2026-04-24 (session 2)_

## What this project does
`map.py` renders a scrollable top-down RPG map using pygame, simulating `assets/Scene Overview.png`.
The map is defined as a char grid (`.`=void, `G`=grass, `P`=path, `S`=stone) in `RAW_MAP`.
Objects (trees, bushes, walls, props, stairs, arch) are listed in `OBJECTS` and Y-sorted for rendering.

## Current file: map.py
- **Screen**: 1024×768, TILE=32, FPS=60
- **Map size**: 58 cols × 48 rows
- **Camera**: scrollable with WASD/arrows

## Verified texture layout (2026-04-24)

### TX Tileset Wall.png (512×512) — contains BOTH building walls AND plain border wall tiles
| Block         | Rect (x,y,w,h)        | Content                          |
|---------------|-----------------------|----------------------------------|
| Block1 A      | (32,  32,  96, 128)   | Building wall with large window  |
| Block1 B      | (152, 32, 114, 128)   | Building wall with window        |
| Block2 left   | (32,  192, 128, 64)   | Plain stone band — outdoor use   |
| Block2 right  | (192, 192,  32, 64)   | Small plain stone accent         |
| Block3 A      | (32,  288,  64, 64)   | Plain stone — border wall_a ✓    |
| Block3 B      | (128, 288,  64, 64)   | Plain stone — border wall_b ✓    |
| Right section | (384, 64,   96, 96)   | Corner/door piece                |

### TX Struct.png (512×512) — stairs and arches ONLY
| Block     | Rect                  | Content                  |
|-----------|-----------------------|--------------------------|
| Stairs    | rows 288-479          | 4 stair variants (L/R×2) |
| Arch      | (408, 27, 80, 64)     | Small arch               |
| Arch 2    | (408, 128, 80, 64)    | Larger arch              |
| (rows 32-127, cols 32-288: building-interior wall sections, NOT for outdoor borders) |

### TX Tileset Grass.png (256×256)
16px tiles. Used for ground and as PATH underlay.

### TX Tileset Path.png (237×240)
Near-square single texture scaled to TILE×TILE as stone-path overlay on grass.

### TX Plant with Shadow.png (512×512)
- Trees: 3 variants at x=0,128,256; each 128×128 → scaled to 4×4 tiles
- Bushes: 3 variants y=128, x=32,160,288; each 96×64 → 2×2 tiles
- Shrubs: 6 variants y=192, spaced 64px; each 64×64 → 1.5×1.5 tiles

## Border wall sprites (wall_sheet = TX Tileset Wall.png)
```
wall_a → Rect(32,  288, 64, 64) from wall_sheet → screen 2×2 tiles (64×64px)
wall_b → Rect(128, 288, 64, 64) from wall_sheet → screen 2×2 tiles
wall_c → Rect(32,  192, 64, 64) from wall_sheet → screen 2×2 tiles
```
Placed every **2 columns** along top-edge tiles (stride=2 matching 2-tile sprite width).

## Rendering passes
```
Pass 1: Ground tiles (VOID skipped, GRASS/PATH/STONE drawn tile-by-tile)
Pass 2: Unified Y-sorted list (walls + objects):

  Sort key = base_row * 2       for wall faces  (drawn behind objects at same base)
  Sort key = base_row * 2 + 1   for objects     (drawn in front of walls at same base)

  base_row per kind:
    wall face  → ty + 1   (sprite bottom at (ty+1)*TILE)
    tree       → ty + 2   (4-tile sprite; feet 2 rows below map pos)
    bush       → ty + 1
    shrub      → ty + 1
    prop_*     → ty + 1
    arch       → ty + 1
    stair_l/r  → ty + 2
```

## Bugs fixed across sessions
1. Wrong texture for border walls (was struct_sheet, then corrected to wall_sheet Block3/Block2)
2. Sprite too tall: old h=224→7 tiles; now h=64→2 tiles
3. bake_wall_faces covered-set global across rows → now reset per row
4. bake_wall_faces stride was 3 cols → now 2 cols to match 2-tile-wide sprites
5. Layer ordering: walls in a dedicated pass before all objects → merged into Y-sort
6. Y-sort used map tile pos for all objects → now uses visual base_row per sprite type
   (trees sort 2 rows lower than their map pos, matching where their trunk meets the ground)
