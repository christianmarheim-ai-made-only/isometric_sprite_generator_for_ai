# ADR-0018: Vertical Projection Is Pinned by a Height Pixel Scale, Not Camera Elevation

- Status: Proposed
- Date: 2026-06-05
- Blocks: M3 height-bearing variants (anything taller than the ground plane); production contract camera block
- Related: ADR-0014 (validator/runtime contract), ADR-0015 (arrow pilot scope), ADR-0007 (world metrics), ADR-0019 (height-calibration probe)

## Context

The `game_iso_v1` camera elevation is **30°** (engine-confirmed). The ground
projection — `screen_x = (wx−wy)·32`, `screen_y = (wx+wy)·16`, `tile_px [64,32]` —
was verified in pixels by the M1/M2 arrow pilot (dir02 down, dir10 up, clockwise
winding) and corresponds to a 2:1 ground tile. None of that is in question.

The unresolved axis is **height**. For an orthographic iso camera (uniform scale
`s`, azimuth 45°, elevation θ) the per-axis screen scales are:

```
horizontal (wx−wy):  s/sqrt(2)            -> 32 px/unit   => s ≈ 45.25
depth      (wx+wy):  s/sqrt(2) · sin θ    -> 16 px/unit   => θ = 30°
height     (wz):     s · cos θ             -> ≈ 39 px/unit at 30°
```

But the engine places height with its own constant, `HEIGHT_SCREEN_SCALE = 24`
(`screen_y = −(wx+wy)·16 + height·24`, Bevy y-up). A single uniformly-scaled camera
at 30° therefore does **not** reproduce the engine's height: it yields ≈39 px per
world height-unit while the engine expects 24. Baking real 3D meshes with a naive
30° camera makes tall bodies ≈1.6× too tall, with error growing with height (eyes,
muzzles, health bars, projectile spawns, depth sorting / LOS silhouettes all drift).
Flat assets (`z ≈ 0`) are immune — which is why the arrow pilot is correct, nothing
shipped is wrong, and a flat probe cannot reveal this.

(The M1/M2 debug-subset contract encodes only the ground projection + `tile_px`; it
specifies no height factor. Vertical projection is currently unspecified in the
validated contract and must be pinned for production before any height-bearing bake.)

## Decision

> **⚠️ SUPERSEDED — see the Resolution section at the end of this ADR.** Decision
> point 1 below ("set the height scale explicitly in the bake" / anamorphic ×24) is
> **wrong**: the engine applies `×24` itself (`render.rs::sprite_size`). The bake must
> **not** apply a ×24/anamorphic squash — it bakes at **30°** (correct foreshortening)
> and emits `height_world`. (Current code is already correct; this note prevents a wrong
> re-implementation during R2–R6.)

1. The authoritative vertical spec is the **height pixel scale**
   `height_px_per_world_unit` = the engine's `HEIGHT_SCREEN_SCALE` (currently `24`).
   It is **set explicitly in the bake**, not left to fall out of the 30° camera
   (which gives ≈39). Mechanism: an anamorphic Z scale, a post-render vertical scale,
   or an engine-matched camera — whatever makes a world height `h` render to exactly
   `h · 24` px.
2. The camera elevation stays **30°** (engine-confirmed, ground verified). The
   manifest records `camera_elevation_degrees: 30`, the ground scales, and
   `height_px_per_world_unit`; the validator and runtime assert
   `height_px_per_world_unit` equals the engine constant (fail closed), so any drift
   is a field-by-field failure, not a visual surprise.
3. If the engine constant and the ground scales are ever found mutually inconsistent,
   it is resolved once, on the contract/engine side, by agreeing a single coherent
   (ground, height) system — never by silently re-scaling per asset.

## Consequences

### Positive

- Pins the quantity that actually drives 3D height correctness (height px/unit).
- Keeps the verified ground projection + confirmed 30° elevation intact — no re-bake of flat assets.
- Makes height mis-scaling a hard validator failure instead of silent visual drift.

### Negative

- The bake needs an explicit vertical-scale step, not just "set the camera angle."
- Requires the engine's `HEIGHT_SCREEN_SCALE` to be carried as a contract value.

## Validation requirements

- `height_px_per_world_unit` present in the production manifest and equal to the engine constant (validator + runtime assert).
- Ground scales unchanged (`×32 / ×16`, `tile_px [64,32]`); M1/M2 ground diagnostics still pass.
- A height-calibration probe (ADR-0019) passes before any height-bearing variant is baked.

## M1/M2 assumption

The arrow pilot is flat (no height) and uses only the ground projection, so it is unaffected and remains valid. No M1/M2 re-bake is required.

## M3 review questions

- Carry the engine `HEIGHT_SCREEN_SCALE` as a manifest/contract field.
- Choose the height-scale mechanism (anamorphic camera vs post-scale).
- Does the height factor interact with per-variant scale (large/small creatures)?

## Resolution (2026-06-05, from engine `render.rs`)

Confirmed against the authority (`crates/client_bevy/src/render.rs::sprite_size`):
the engine sets on-screen **height = `height_world × HEIGHT_SCREEN_SCALE` (24)** and
**width = height × frame_aspect** (`rect.w/rect.h`). So `×24` is applied **engine-side**,
not in the bake. This **supersedes Decision point 1's "set the height scale explicitly to
24 in the bake."** The corrected decision:

- The bake renders at azimuth 45° + **elevation 30°** (ground + correct height
  *foreshortening*, which fixes the frame's aspect and internal vertical proportions) and
  emits a correct `world_metrics.height_world`. It does **not** apply an in-bake `×24` /
  anamorphic squash.
- The engine owns absolute on-screen size (`height_world×24` tall, width = height ×
  frame-aspect). Elevation `30°` is still the one irreversible thing to get right (it bakes
  the foreshortening / aspect); `26.565°` remains the screen tile-edge angle, not the camera.
- Validator/runtime still assert `camera_elevation_degrees == 30` and valid `world_metrics`.
