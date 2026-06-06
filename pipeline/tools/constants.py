#!/usr/bin/env python3
"""Single source of truth for the pipeline's load-bearing constants.

These values were previously copy-pasted across the host bakers (`bake.py`), the Blender render
scripts (`blender_render.py`, `blender_render_anim.py`, `blender_preview.py`), the metric tools
(`hitbox_from_mesh.py`), and the atlas/logging tools (`shard_atlas.py`, `build_log.py`). A silent
drift between any two copies is a correctness bug: e.g. if `GROUND_BAND` or `EYE_FRACTION` drifts
between `bake.py` and `hitbox_from_mesh.py`, the text hitbox a producer sanity-checks no longer
matches the baked manifest; if `REGION_RGB` drifts between the render scripts, the R8 hit-mask
decodes to the wrong gameplay region. Importing from here makes that drift impossible.

PURE LITERALS + dependency-free pure helpers ONLY -- no numpy/PIL/Blender imports -- so this module
is safe to import from both host CPython and Blender's bundled interpreter (the Blender scripts
`sys.path.insert(0, TOOLS)` before importing, exactly as they already do for `render3d`).
"""
from __future__ import annotations

import math

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

# --- R8 HIT-region id <-> name + the name->region keyword table ------------------------------
#     This is the SINGLE source for resolving a material/group name to a body region. Both the
#     auto-rigger (rig_from_profile, which names the rigged-glb materials) and the bake
#     (mesh_io.region_for_name, which assigns the HIT region per face) resolve through THIS table,
#     so the material a part is given and the region the bake reads can never drift apart -- the
#     drift that would (e.g.) colour a dragon's `wing` as torso while the mask calls it arms.
REGION_NAMES = {1: "head", 2: "torso", 3: "arms", 4: "legs"}
REGION_NAME_TO_ID = {v: k for k, v in REGION_NAMES.items()}
REGION_KEYWORDS = [
    ("head", 1), ("skull", 1), ("face", 1), ("neck", 1), ("beak", 1),
    ("torso", 2), ("chest", 2), ("body", 2), ("spine", 2), ("hip", 2), ("pelvis", 2), ("waist", 2), ("tail", 2),
    ("arm", 3), ("hand", 3), ("shoulder", 3), ("elbow", 3), ("wrist", 3), ("wing", 3),
    ("leg", 4), ("foot", 4), ("feet", 4), ("thigh", 4), ("shin", 4), ("knee", 4), ("ankle", 4),
]


def region_for_name(name: str) -> int:
    """Body HIT region id for a material/group name; unmatched body faces default to torso (2)."""
    n = (name or "").lower()
    for kw, rid in REGION_KEYWORDS:
        if kw in n:
            return rid
    return 2


def material_region_name(part_name: str, region_id: int, index: int = 0) -> str:
    """Name a rigged part's material so the bake's region_for_name resolves it to `region_id`.

    region_for_name returns the FIRST keyword (in REGION_KEYWORDS order: head<torso<arms<legs) found
    anywhere in the name, so the encoding has three cases:
      1. the part's OWN keyword already resolves correctly      -> keep the name (keyword deliveries untouched)
      2. appending the canonical region keyword resolves it      -> `tentacle_3` declared legs -> `tentacle_3__legs`
      3. the part name carries a HIGHER-priority conflicting kw  -> drop it: `wing_L` (wing=arms) declared legs
         (e.g. wing -> arms outranks leg -> legs)                   can't keep "wing", so -> `legs__<index>`
    `index` only matters for case 3 (a keyword-free ordinal that keeps the names distinct)."""
    kw = REGION_NAMES[region_id]
    if region_for_name(part_name) == region_id:
        return part_name
    cand = f"{part_name}__{kw}"
    if region_for_name(cand) == region_id:
        return cand
    return f"{kw}__{index}"


# --- Forward-axis correction ----------------------------------------------------------------
#     game_iso_v1 fixes forward = +X = direction 0. A delivery declares geometry.forward; the bake
#     rotates the model about world +Z so the DECLARED forward lands on +X (so a +Y-authored model
#     bakes identically to a +X-authored one). forward_yaw is the SINGLE source the four render paths
#     (blender_render_anim, blender_render, render3d/bake numpy) share, so they cannot disagree.
#     Planar only (forward is a ground-plane heading; +Z/-Z are not valid forwards).
FORWARD_AXES = ("+x", "-x", "+y", "-y")
_FORWARD_VEC = {"+x": (1.0, 0.0), "-x": (-1.0, 0.0), "+y": (0.0, 1.0), "-y": (0.0, -1.0)}


def forward_yaw(forward: str) -> float:
    """Yaw (radians, CCW about +Z) that rotates the declared `forward` axis onto +X (direction 0).

    +x -> 0 (the no-op default); +y -> -pi/2; -y -> +pi/2; -x -> -pi (== +pi). Sign is the value that
    makes R_z(yaw) @ forward == +X; it is pinned empirically by test_forward_axis (a +Y-authored mesh
    baked with forward:"+y" must equal the +X-authored mesh baked with forward:"+x")."""
    fx, fy = _FORWARD_VEC.get((forward or "+x").lower(), (1.0, 0.0))
    return -math.atan2(fy, fx)


# --- Engine clip vocabulary -----------------------------------------------------------------
#     The engine renderer (slay_slayer_3 crates/client_bevy/src/render.rs) SELECTS animation clips by
#     these canonical names; a clip authored under any other name is never selected and silently falls
#     back to `idle` (the motion is baked but dead). The proven failure: a combatant authored with
#     move/shoot/hurt walks-as-idle and attacks with no swing. CLIP_SYNONYMS maps the common
#     off-vocabulary names -> the canonical clip, so the linter can say "rename move -> walk".
#     NOTE (cross-repo drift, deliberate follow-up): the pipeline's own ADR-044 canon + the grunt
#     fixture use `punch`, but render.rs selects `attack` -- so `punch` is off-vocab for the live engine.
ENGINE_CLIP_VOCAB = ("idle", "walk", "run", "attack", "hit", "jump", "fall", "crouch_idle", "crouch_walk")
CLIP_SYNONYMS = {
    "move": "walk", "stroll": "walk", "jog": "run", "sprint": "run", "dash": "run",
    "shoot": "attack", "fire": "attack", "swing": "attack", "slash": "attack", "stab": "attack",
    "cast": "attack", "punch": "attack", "melee": "attack", "strike": "attack", "jab": "attack",
    "hurt": "hit", "damage": "hit", "flinch": "hit", "stagger": "hit", "recoil": "hit",
    "hitreact": "hit", "hit_react": "hit",
    "die": "death", "dead": "death", "dying": "death", "ko": "death",
}


def offvocab_clip_renames(clip_names):
    """[(declared, canonical)] for each declared clip that is an off-vocabulary SYNONYM of a canonical
    engine clip, when that canonical name is NOT also declared. Empty = clean. Catches 'right motion,
    wrong name' (move->walk, shoot->attack, hurt->hit) -- bakes fine but the engine never selects it."""
    declared = {str(c).lower() for c in clip_names}
    out = []
    for c in clip_names:
        canon = CLIP_SYNONYMS.get(str(c).lower())
        if canon and canon not in declared:
            out.append((c, canon))
    return out


# --- Atlas paging ---------------------------------------------------------------------------
MAX_PAGE_PX = 4096    # a single atlas page must fit within MAX_PAGE_PX in each dimension
