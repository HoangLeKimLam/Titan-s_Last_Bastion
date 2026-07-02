# CLAUDE.md — Top-Down RPG Map Simulator

## Project Overview
A pygame simulation of a pixel-art top-down RPG map using the "Pixel Art Top Down - Basic" asset pack.
Single file: `map.py`. Assets live in `assets/Texture/`.

## Context Update Rule
**At the start of every session or command**, read the current state of `map.py` and update `CONTEXT.md`
with any changes to: texture rects, layer rendering strategy, object list, or known bugs.
Use the Write tool to overwrite `CONTEXT.md` completely with the latest understanding.

## Asset Layout (verified pixel coordinates)

### TX Struct.png (512×512) — outdoor walls, arches, stairs
| Sprite     | Rect (x, y, w, h)    | Notes                        |
|------------|----------------------|------------------------------|
| wall_a     | (32,  32, 64, 96)    | Plain stone, variant A       |
| wall_b     | (128, 32, 65, 96)    | Plain stone, variant B       |
| wall_c     | (224, 32, 65, 96)    | Stone with grass/vegetation  |
| arch small | (408, 27, 80, 64)    | Small stone arch             |
| arch large | (408, 128, 80, 64)   | Larger stone arch            |
| stairs     | rows 288-479         | 4 stair variants (L/R ×2)   |

### TX Tileset Wall.png (512×512) — building interiors only
Contains building walls with windows. **Do NOT use for border/outdoor walls.**
Used only for `bldg_window` and `bldg_solid` props.

### TX Tileset Grass.png (256×256)
16px tiles, 8 cols × 16 rows. First 4 rows skip col 0 (blank).

### TX Tileset Stone Ground.png (256×256)
16px tiles, 8 cols × 6 rows from (0,0).

### TX Tileset Path.png (237×240)
Near-square single-texture file — scaled to TILE×TILE as a repeating overlay.

### TX Plant with Shadow.png (512×512)
- Trees: 3 variants at x=0, 128, 256; each 128×128
- Bushes: 3 variants at x=32, 160, 288; y=128; each 96×64
- Shrubs: 6 variants at y=192, spaced 64px; each 64×64

## Rendering Layer Order (correct)
```
PASS 1 – Ground tiles (GRASS, PATH, STONE)
PASS 2 – Unified Y-sorted pass:
          sort key = (ty * 2)     for border wall faces  ← behind objects same row
          sort key = (ty * 2 + 1) for all objects        ← in front of walls same row
```

## Known Fixed Bugs
- **Wrong texture for border walls**: was using `wall_sheet` (building windows), must use `struct_sheet`
- **Wall sprites too tall**: old rects gave 6-7 tile height; correct is 3 tiles (96px screen)
- **bake_wall_faces covered set**: `covered` must reset per row, not persist across rows
- **Layer order**: wall faces were in a separate PASS 2 before objects; merged into Y-sort

## Controls
- WASD / Arrow keys — scroll map
- ESC / Q — quit
