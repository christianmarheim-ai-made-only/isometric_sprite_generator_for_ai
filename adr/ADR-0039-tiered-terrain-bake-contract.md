# ADR-0039: Tiered-terrain bake contract (the pipeline half of the walkable-height-tiers program)

Status: **Proposed** — paired pipeline ADR. **Gated:** ratifies + is implemented only alongside the engine
ADR-022/053 successor, which is itself **blocked on the engine assigning a multi-level owner** (handoff
`docs/handoff/multi-level-terrain/BRIEF.md` §0). **No tiered terrain art bakes until this contract + the
extended Gate-3 exist** (ADR-053's irreversible-mistake rule).
Date: 2026-06-10.
Related: ADR-0018 (camera elevation 30°; *bake owns foreshortening, engine owns `height_world×24` sizing*),
ADR-0019 (the foreshortening/aspect calibration probe = Gate-3), ADR-0006/0053 (flat z=0 terrain tile),
ADR-0054 (blocking feature = ADR-019 collider), `pipeline/env/` (`env_asset_v1`, the FLAT contract this
extends). Engine: BRIEF §4.1/§4.2/§4.3/§4.5; ADR-003 (height → screen-Y), ADR-022 (the MVP this supersedes).

## Context

The demo needs **walkable tactical height-tiers** — a single-surface heightfield (one walkable height per
`(x,y)`, no overhangs). The headline *pipeline* risk is the **tiered-terrain bake contract**, which ADR-053
calls *"the one irreversible mistake in this pipeline"*: terrain baked at the wrong elevation will not align
with the engine's faked-Z, and is unfixable without re-baking the whole world.

The decisive fact (ADR-0018, already ratified): **the bake does NOT apply a height scale.** It renders model
geometry through the locked **30°** `game_iso_v1` camera and owns only the **foreshortening** (frame aspect +
internal proportions). The **engine** applies the absolute height→pixels sizing (`height_world ×
HEIGHT_SCREEN_SCALE`, **24**) and *places* the sprite. Gate-3 (ADR-0019) is therefore a **foreshortening
calibration probe**, not a pixel-height check — *a wrong elevation surfaces as wrong foreshortening*, the
irreversible mistake. This split is what makes tiers cheap; the contract below leans on it.

## Decision (pipeline side)

1. **The flat-top tile is height-agnostic — there is NO per-tier flat-top bake.** A tier-`N` walkable
   surface is the **existing** `env_asset_v1` `terrain` tile, **placed by the engine** at the tier's screen-Y
   offset (`tier_index × tier_height_world × 24`, ADR-0018/ADR-003). One tile sprite, `N` placements. The
   pipeline never bakes elevation into the flat top → no combinatorial tile explosion, and the flat badlands
   look (priority #3) is already the right tile.

2. **The genuinely-new baked artifacts are the VERTICAL tier geometry only:**
   - **`cliff_face`** — the wall that fills the vertical gap between a high tile and the ground/low tier
     (height = the tier delta). In `env` terms a cliff face **is a `blocking_feature`** whose footprint is the
     tier edge and whose `occluder_height_world` = the tier delta (its *collider* is derived from the height
     field, BRIEF §4.5; its *art* is baked).
   - **`ramp` / `stair`** — the walkable connector between tiers (sloped / stepped geometry).
   These bake through the **same locked 30° camera** — the bake owns their foreshortening; the engine owns
   their `×24` placement. Nothing new in the renderer: a cliff face / ramp is just static vertical geometry
   through the existing static bake path.

3. **`env_asset_v2` = `env_asset_v1` + a `tier` block** (fills the reserved slot):
   ```jsonc
   "tier": {
     "edge_kind": "flat_top | cliff_face | ramp | stair",
     "tier_height_world": 2.0,        // the vertical extent (m); cliff_face/ramp/stair only
     "orientation": "+x | -x | +y | -y" // which cell edge this piece faces (cliff_face/ramp/stair)
   }
   ```
   `flat_top` routes to the existing `terrain` bake; `cliff_face` routes to `blocking_feature`; `ramp`/`stair`
   route to the static prop/feature bake. v2 stays a clean superset of v1 (a v1 asset is a v2 asset with no
   `tier`).

4. **Gate-3 EXTENDS to tier geometry — this is THE gate, ruled before any tiered art bakes.** The ADR-0019
   foreshortening probe gains a **tier calibration object** (a `1×1×tier_height_world` pole + a reference
   cliff/ramp wedge) rendered through the production 30° path. A tiered bake passes **only if**: (a)
   `camera_elevation_degrees == 30` (reject 26.565); **and** (b) the tier-height geometry foreshortens to the
   30° orthographic **prediction within tolerance** (the proportions a `tier_height`-tall vertical face must
   show at 30°). A failure here is the irreversible mistake caught *before* production. This lands as a step
   in `pipeline/env/build_env.py` (`env_elevation_guard`).

5. **The shared constants the engine must co-ratify (the paired-ADR seam — lock these together):**
   - `camera_elevation_degrees == 30` (already locked, both sides).
   - `HEIGHT_SCREEN_SCALE == 24` — the engine's `height_world → px`; the pipeline's foreshortening probe is
     validated to be *consistent* with it (the single number a tier's screen-Y offset is built from).
   - `tier_height_world` (⚑ PM: ~**2.0 m** primary cliff unit) and **max tiers** (⚑ 3–4) — BRIEF §6.
   - **The anchor convention for a `cliff_face`/`ramp`/`stair` piece** — *where the engine pins it relative to
     the cell + tier*. This is the **one genuinely-new placement contract**, and it must be co-designed with
     the engine's height-occlusion depth-sort work (BRIEF §4.3, the one invariant that bends).

## Consequences

- Tiered terrain = **existing flat-top tile (engine-elevated) + baked cliff-face/ramp/stair vertical pieces.**
  No new renderer, no per-tier flat-top art, consistent with ADR-0018's bake/engine split.
- The irreversible-mistake surface is **bounded to one thing** — the foreshortening of vertical tier geometry
  vs the engine's `×24` placement — and Gate-3's probe rules it before any production bake.
- `env_asset_v2` extends `env_asset_v1` with no breakage; the world-builder's *flat* briefs (priority #1) stay
  valid and gain a `tier` block when this lands.

## Open questions (engine + PM co-design — do NOT bake tiered art until these close)

- **⚑ `tier_height_world` (~2.0 m) + max tiers (3–4)** — PM sign-off (BRIEF §6).
- **The cliff-face fork (biggest):** does the engine want the cliff face as a **baked sprite** (pipeline
  produces cliff-face art — richer look) **or derived from the height delta at render time** (no cliff-face
  sprite; the engine draws the gap)? This decides whether the pipeline bakes cliff-face *art* at all.
  *Recommend:* pipeline bakes cliff-face **art** (visual richness for the badlands mesas); engine derives the
  **collider** from the height delta. Confirm with the engine chair.
- **The `cliff_face`/`ramp` anchor + occlusion convention** — co-design with the depth-sort successor (§4.3).
- **Ramp/stair as baked geometry vs a tile variant**, and step-up nav thresholds — ride the pathfinding ADR
  (BRIEF §4.4), not load-bearing for the bake.

## Status / next

Proposed; the pipeline side is **decision-complete pending the engine's #5 constants + the cliff-face fork**.
The moment those close, implementation is small: the `tier` block in `env_asset_v2`, route `cliff_face/ramp`
to the static bake, and the `env_elevation_guard` tier probe in `build_env.py`. Until then: **flat scenery
production proceeds (priority #1/#3); tiered art is gated.**
