# ADR-0018: Camera Elevation Is 30°; the Engine Applies `height_world × 24` Sizing (Not the Bake)

- Status: Proposed (height handling **engine-confirmed** against `crates/client_bevy/src/render.rs`)
- Date: 2026-06-05
- Supersedes: an earlier draft of this ADR that proposed pinning an explicit *in-bake* height pixel scale (anamorphic ×24). That approach was **wrong** and has been removed — see the Decision.
- Blocks: M3 height-bearing variants; the production-contract camera block
- Related: ADR-0014 (validator/runtime), ADR-0015 (arrow pilot), ADR-0007 (world metrics), ADR-0019 (foreshortening calibration)

## Context

`game_iso_v1` is a 2:1 dimetric isometric projection. Its **ground** projection
(`screen_x=(x−y)·32`, `screen_y=(x+y)·16`; tile 64×32) was verified in pixels by the
M1/M2 arrow pilot and matches the engine. This ADR settles the **vertical** axis: the
camera elevation, and **who applies** the world-height → screen-pixels scaling.

The "30° vs 26.565°" trap: a 2:1 *ground* tile requires `sin(elevation)=0.5 ⇒
elevation = 30°`. `arctan(0.5) ≈ 26.565°` is the on-screen tile-edge **slope** (a screen
result), **not** the camera elevation — a camera literally at 26.565° would render a
`≈2.236:1` ground, which is wrong.

## Decision

1. **Camera elevation is 30°** (azimuth 45°). 26.565° is the tile-edge screen angle, not
   the camera elevation; the camera is never set to 26.565°.
2. **The bake applies NO in-bake height scale / anamorphic ×24.** It renders the model
   through the 30° camera — which produces the correct height **foreshortening** (and
   therefore the frame's **aspect ratio** + internal vertical proportions) — and emits a
   correct `world_metrics.height_world`. The absolute pixel size of the baked frame is
   irrelevant to the engine.
3. **The engine applies the absolute on-screen size** (`render.rs::sprite_size`): drawn
   **height = `height_world × HEIGHT_SCREEN_SCALE (24)`**; drawn **width = height ×
   frame_aspect** (`rect.w / rect.h`). The engine resizes the baked frame to
   `height_world×24` px tall, preserving the frame's aspect.
4. **Consequence — cropping (see ADR-0019 / R5):** because the engine derives width from
   `rect.w/rect.h`, the **aspect of engine-consumed frames is load-bearing**. You may
   **not** tight-crop engine-consumed frames to varying aspects without an engine
   `logical_frame_canvas` sizing change — or animation scale (crouch/hurt/death) silently
   stretches.
5. The manifest records `camera_elevation_degrees: 30` + the ground scales; the validator
   and runtime assert `camera_elevation_degrees == 30` (and **reject 26.565**). There is
   **no** "height pixel scale" field the bake must hit.

## Consequences

### Positive
- The simplest correct rule: bake = 30° + `height_world`; the engine owns absolute size.
- Keeps the verified ground; no re-bake of flat assets; no anamorphic bake step.

### Negative
- The engine's rect-aspect sizing **constrains cropping** (point 4) — a real limitation R5 must respect.
- Requires the engine to carry `HEIGHT_SCREEN_SCALE` (24) as a known contract constant.

## Validation requirements
- `camera_elevation_degrees == 30` in the manifest (validator + runtime).
- Ground scales unchanged (`×32/×16`; tile 64×32); M1/M2 ground diagnostics still pass.
- Foreshortening/aspect calibration passes (ADR-0019) before any 3D height bake.

## M1/M2 assumption
The arrow pilot is flat (no height) and uses only the ground projection — unaffected.

## M3 review questions
- The rect-aspect-vs-tight-crop tension (point 4): does the engine gain a
  `logical_frame_canvas` sizing field, or do engine-consumed frames stay full-canvas?
- Does `height_world×24` interact with per-variant scale (large/small creatures)?
