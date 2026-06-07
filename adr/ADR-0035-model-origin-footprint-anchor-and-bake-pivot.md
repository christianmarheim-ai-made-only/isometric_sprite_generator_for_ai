# ADR-0035: Model origin, footprint anchor, bake pivot, and the coordinate/anchor contract

- Status: **Proposed** (hard gate for the v3 producer spec)
- Date: 2026-06-07
- Owner: sprite-pipeline (+ engine/sim alignment)
- Related: ADR-0018 (camera elevation 30° vs the 26.565° on-screen tile angle — the 2:1 dimetric resolution), ADR-0019 (height calibration), ADR-0022 (256² logical frame canvas), ADR-0030/0031 (calibration model + verification), the LOCKED game_iso_v1 contract. Engine repo (C:/Code/Claude) read-only.
- Driver: an independent review of the v2 producer spec ("the rotation pivot for sprite baking must not be guessed from mesh bounds") + the open "what is *center*" question.

## Context

The pipeline bakes 16 per-direction sprites by rotating a model about a vertical axis. **Which axis** has been implicit — and a model has many plausible "centers" (mesh-bounds centre, visual mass, footprint, feet, rig root, sprite anchor pixel). If the bake guesses the pivot from mesh bounds, an asymmetric body (a dragon with a long tail, a humanoid holding a spear, wings, a cape) **orbits around its visual mass** and the sprite "swims" between directions — and every downstream system that assumes a stable ground point (depth sort, selection ring, shadow, hitbox, collider) is subtly wrong. This is the same silent class of bug as a wrong camera elevation: not obvious frame-by-frame, but everything "feels off."

The sim already separates **footprint (x,y)** from **height (z)** and uses a continuous facing angle with **0 = +X**. The model/bake contract must mirror that, and it must be **machine-checked**, not inferred.

## Decision

### D1. The canonical model-space convention (RATIFIES game_iso_v1; now explicit + gated)
For every delivered model:
- **`(0,0,0)` is the ground-footprint anchor** — where the entity exists in sim space.
- **Ground plane = `Z = 0`; `+Z` is up (height); `+X` is forward = direction 0.**
- **The bake rotates the MODEL about the vertical `+Z` axis through `(0,0,0)`** under a **fixed camera** (not camera-around-model) — easier to validate and keeps the projected origin stable.
- **The sprite anchor = the projected `(0,0,0)`** in every baked frame; the projected-origin pixel is **identical across all 16 directions** (per-frame `rect`/`trim` may differ — the body silhouette changes — but the **anchor does not drift**).
- **The mesh-bounds centre MUST NOT be used as the pivot** unless it is exactly the footprint anchor.
- Camera: azimuth 45° / elevation 30° (ADR-0018; the 26.565° figure is the *on-screen* 2:1 tile-edge angle, NOT the camera elevation — do not conflate); ortho; tile 64×32; logical canvas 256² (ADR-0022).

### D2. The contract is *footprint at origin*, NOT *mesh centred at origin*
Require **the footprint anchor at the origin**; do **not** require the mesh be centred on the origin. Tails, weapons, wings, capes, horns, snouts, and asymmetric poses legitimately extend away from the anchor — they do not move it. (This is the distinction the reviewer flagged: a dragon/spear-unit/tentacle-monster is valid and asymmetric.)

### D3. Root-bone + in-place animation
- The rig **root bone sits at the model origin** with neutral rotation/scale.
- **Animations are in-place** (no root motion) for MVP baking: net horizontal (x,y) root/bone translation per clip ≈ 0 (within ~1% of footprint radius). The sim moves entities; animation must not secretly translate them. Root-motion clips are **rejected** for now.

### D4. Required manifest metadata (`model_space` + optional `anchors`)
The asset manifest declares (machine-checkable, not prose):
```json
"model_space": {
  "up_axis": "Z", "forward_axis": "+X",
  "origin_semantics": "ground_footprint_center",
  "rotation_pivot": [0.0, 0.0, 0.0], "rotation_axis": "+Z",
  "sprite_anchor": "projected_origin"
}
```
Optional, for advanced cases (default = origin): `"anchors": { "footprint_anchor": [...], "root_bone_anchor": [...], "shadow_anchor": [...], "collider_anchor": [...] }`. A future `collider.center_offset_xy` may offset the *collider*, but the **bake pivot stays the footprint anchor**. The baked manifest already emits per-frame `anchor` + `sprite_anchor_px`; this declares the *intent* the bake verifies against.

## Acceptance / preflight gates (machine-checked)
```text
origin on ground plane:            min meaningful contact z  ~= 0  (|min_z| <= tol)
footprint centred:                 footprint centroid x,y    ~= 0
forward marker points +X:          declared forward resolves to +X (facing oracle / +X marker)
rotation_pivot metadata == [0,0,0] and rotation_axis == "+Z"
anchor stability:                  projected-origin pixel identical across all 16 directions (no drift)
in-place:                          per-clip net horizontal root/bone translation <= 1% footprint_radius
mesh-bounds-center != pivot check: if |bounds_center_xy| > tol, the asset MUST declare footprint anchor
                                   explicitly (so a tail-heavy body is not silently pivoted on its tail)
```
**Calibration models** additionally carry visible markers the oracle reads: a footprint cross/ring at the anchor, a `+X` forward arrow, a ground-contact marker, and distinct left/right markers — to catch "looks fine but rotates wrong / mirrored" failures.

## Consequences
- **+** Asymmetric bodies (dragon/spear/cape/wings) bake without swimming; depth, shadow, selection ring, hitbox, and collider all read off one stable ground point that mirrors the sim.
- **+** Turns "center" from tribal knowledge into a declared, gated contract field — the same machine-checkable move the project already applies to facing and fog.
- **−** Existing assets must declare `model_space` (additive; default convention = today's behaviour, so the migration is a backfill, not a re-author).
- **−** Root-motion is banned for MVP — a future ADR can add an explicit opt-in root-motion mode with its own sim contract.

## Note
Most of D1 already follows from the LOCKED game_iso_v1 + ADR-0018/0022; the **new** commitments are: the explicit *footprint-anchor-at-origin / never-bounds-center* pivot rule, the `model_space` metadata, the anchor-stability + in-place + bounds-center gates, and the calibration markers. This ADR is the coordinate/anchor half of the "decide the basics now" list; the remaining contract decisions (direction numbering detail, region-naming grammar, texture authority, socket names, collider/visual classification, variant compatibility) are tracked in `docs/handoffs/model_producer_spec_v3_plan.md`.
