#!/usr/bin/env python3
"""Single source of truth for the pipeline's load-bearing constants.

These values were previously copy-pasted across the host bakers (`bake.py`), the Blender render
scripts (`blender_render.py`, `blender_render_anim.py`, `blender_preview.py`), the metric tools
(`hitbox_from_mesh.py`), and the atlas/logging tools (`shard_atlas.py`, `build_log.py`). A silent
drift between any two copies is a correctness bug: e.g. if `GROUND_BAND` or `EYE_FRACTION` drifts
between `bake.py` and `hitbox_from_mesh.py`, the text hitbox a producer sanity-checks no longer
matches the baked manifest; if `REGION_RGB` drifts between the render scripts, the R8 hit-mask
decodes to the wrong gameplay region. Importing from here makes that drift impossible.

PURE LITERALS ONLY -- no numpy/PIL/Blender imports -- so this module is safe to import from both
host CPython and Blender's bundled interpreter (the Blender scripts `sys.path.insert(0, TOOLS)`
before importing, exactly as they already do for `render3d`).
"""
from __future__ import annotations

# --- Frame / atlas geometry ------------------------------------------------------------------
CANVAS = 256          # logical frame canvas (px), the engine-facing render size
DIRS = 16             # direction_count (game_iso_v1 16-way)
PAD = 4               # atlas inter-frame padding (px), extruded to avoid bleed

# --- World-metric policy (must match across bake.py + hitbox_from_mesh.py) -------------------
GROUND_BAND = 0.15    # ground-contact verts: z <= zmin + GROUND_BAND * height (footprint radius)
EYE_FRACTION = 0.9    # eye_height_world = EYE_FRACTION * height_world

# --- R8 HIT-region -> art RGB (0..1 float; the Blender render scripts paint these so the baked
#     color == the region id; keys are the body palette {head,torso,arms,legs} = ids 1..4). ------
REGION_RGB = {
    1: (0.86, 0.22, 0.22),   # head
    2: (0.22, 0.70, 0.36),   # torso
    3: (0.27, 0.47, 0.95),   # arms
    4: (0.93, 0.79, 0.20),   # legs
}
PREVIEW_BG_RGB = (0.10, 0.10, 0.10)   # region id 0 (none/background) tint, preview only

# --- Atlas paging ---------------------------------------------------------------------------
MAX_PAGE_PX = 4096    # a single atlas page must fit within MAX_PAGE_PX in each dimension
