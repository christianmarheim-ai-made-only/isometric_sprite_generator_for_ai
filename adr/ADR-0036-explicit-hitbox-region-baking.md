# ADR-0036: Bake per-region hit data from the explicit hitbox map (single-material models)

Status: Accepted
Date: 2026-06-07
Related: ADR-0025 (hit-region output / per-region AABBs), ADR-0028 (mode-aware severity / region_fallback escalation), ADR-0035 (model origin = ground-footprint anchor), skin_delta (texture-only variants)

## Context

The R8 hit-mask and its per-region AABBs are derived from the **render** region pass, which colours each
face by its material's name (`region_for_name`). A **single-material** art model — one `Material_0` over
the whole mesh, e.g. `dragon_calibration_v3` and every skin delta cloned from it — therefore renders an
**all-torso** region pass: the baked hit-mask has exactly one body id (`hit_regions_present == [2]`), even
though the model ships an explicit authoritative region map (`<id>_hitbox.json` with `region_hitboxes`)
declaring many regions (head, wing, tail, foreleg, …).

ADR-0028 stopped this from *failing the gate* (an explicit region map means the fallback is declared, not
silent → `region_fallback_torso` stays a warn). But the baked **manifest** was still torso-only: the
authoritative regions travelled in the sidecar, unused by the bake. The engine's per-pixel region mask —
the thing it samples for "which part was hit" — was wrong for the whole class of single-material creatures.

## Decision

When an asset ships an explicit authoritative region map (`files.hitbox` or the `<variant>_hitbox.json`
sibling, ≥2 valid `region_hitboxes`), the static bake **projects** each region's world-space AABB into
screen space and uses it to recover per-region hit data:

1. **Projection (in Blender, `blender_render.py`).** Each region AABB's 8 corners are put through the
   EXACT same transform the mesh uses — `Rz(yaw_i) @ (corner − shift)` then the ortho `probe()` — for all
   16 directions. The result is pixel-aligned to the rendered region pass *by construction* (same camera,
   same per-frame `shift`, same projection), not by a re-derived camera. Each region's screen bounding box
   + its body id (`region_for_name(name)`, which collapses creature-specific names like `wing`→arms,
   `foreleg`→legs into the engine's fixed 4-body palette) is written to `blender_meta.region_rects`.

2. **Re-label (`region_paint.relabel_region_ids`).** For a frame whose rendered region pass is DEGENERATE
   (≤1 body id — the single-material case), the silhouette is re-labelled from the projected boxes:
   largest box first so the smallest (most specific) wins on overlap. Only silhouette pixels are touched;
   the background and the silhouette **shape** are preserved exactly. A frame that already rendered >1
   region (a normal multi-material model) is never re-labelled — the render wins.

3. **Emit.** The re-labelled mask packs into `hitmask_atlas.png` (now multi-id) and each frame gets
   `region_aabbs` (the existing ADR-0025 field, tight boxes of the re-labelled mask).

This is **gated**: with no region map projected, nothing changes — `blender_meta.json` has no
`region_rects`, the mask is not re-labelled, and `region_aabbs` is not added, so a normal bake is
byte-identical (Blender goldens + render parity stay green).

## Consequences

- A single-material creature (and every skin delta off it) now bakes a multi-region hit-mask:
  `dragon_green_skin_v3` goes from `hit_regions_present [2]` → `[1,2,3,4]`, head on the +X (front) side.
- The recovered mask is **coarse** (AABB-derived, collapsed to the 4-body palette). It is strictly better
  than all-torso; the exact per-region world AABBs remain in the sidecar for any finer use. Smallest-box-
  wins is a heuristic for overlap, documented as approximate.
- The fix is general: any hand-authored-hitbox model benefits, not just dragons. It does NOT change the
  engine contract (the hit-mask palette stays the fixed 4-body `{none,head,torso,arms,legs}`).
- **Axis trap (learned here):** a glb authored height-along-+Z imports into Blender lying down (glTF is
  Y-up); the region AABBs must be in the SAME frame the glb imports into. Correctly-exported glbs (Blender
  export → upright Z-up import) and Z-up `region_hitboxes` agree; the e2e fixture authors height along +Y
  to match.

Tests: `test_region_paint.py` (pure relabel) + `test_region_bake_e2e.py` (Blender: single-material box +
explicit hitbox → multi-region mask, head above legs). Both in `build.py`.
