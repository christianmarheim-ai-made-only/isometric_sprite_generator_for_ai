# ADR-0018: Vertical Projection Is Pinned by a Height Pixel Scale, Not Camera Elevation

- Status: Proposed
- Date: 2026-06-05
- Blocks: M3 height-bearing variants (anything taller than the ground plane); production contract camera block
- Related: ADR-0014 (validator/runtime contract), ADR-0015 (arrow pilot scope), ADR-0007 (world metrics), ADR-0019 (height-calibration probe)

## Context

Review flagged `camera.camera_elevation_degrees: 30` (in the production contract) as the classic "30° vs 26.57°" isometric trap, and proposed re-baking real art at `arctan(0.5) ≈ 26.565°`. Getting this wrong silently mis-scales the height of every 3D character — the "looks right, subtly wrong" failure this pipeline exists to catch — and would force a full re-bake.

The two angles are not interchangeable; conflating them *is* the trap:

- **30°** is the *camera elevation* that renders a **2:1 ground tile** (`sin 30° = 0.5` halves the depth axis). It is consistent with the LOCKED ground projection `screen_x=(wx−wy)·32`, `screen_y=(wx+wy)·16` and `tile_px [64,32]`, and that ground projection was **verified in pixels** by the M1/M2 arrow pilot (dir02 down, dir10 up, clockwise winding).
- **26.565°** (`arctan 0.5`) is the *slope of the 2:1 line in screen space* ("2 across, 1 down"). It is a screen measurement, **not** a camera elevation.

Setting the camera *elevation* to 26.565° would foreshorten the **ground** by `sin 26.565° = 0.447`, rendering ground tiles at ≈2.24:1 and **breaking the already-verified `×32/×16` ground**. So "bake at 26.57°" is the conflation in reverse and is not the fix.

The real defect is on the **height** axis. For an orthographic iso camera the per-axis screen scales are (uniform scale `s`, azimuth 45°, elevation θ):

```
horizontal (wx−wy):  s/sqrt(2)            -> locked 32 px/unit   => s ≈ 45.25
depth      (wx+wy):  s/sqrt(2) · sin θ    -> locked 16 px/unit   => θ ≈ 30°
height     (wz):     s · cos θ             -> falls out ≈ 39 px/unit at 30°
```

But the engine places height with its own factor, `height_world · 24` px. Ground (32/16) and height (24) **over-constrain a single uniformly-scaled camera** — no one elevation yields both a 2:1 ground tile and 24 px/height. At 30° the bake emits ≈39 px per world height-unit while the engine expects 24: tall sprites ≈1.6× too tall, error growing with height (eyes, muzzles, health bars, projectile spawns, depth sorting all drift). Flat assets (`z ≈ 0`) are immune — which is why the arrow pilot is correct and nothing shipped is wrong.

Note: the M1/M2 **debug-subset** contract (`sprite_contract.lock.json`) encodes only the ground projection + `tile_px`; it specifies **no** camera elevation and **no** height factor. Vertical projection is therefore currently *unspecified* in the validated contract and must be pinned for production before any height-bearing bake.

## Decision

1. The authoritative vertical spec is the **height pixel scale** `height_px_per_world_unit` (the engine's factor — currently `24`), **not** the camera elevation. The elevation is a *derived* value chosen to reproduce the locked ground scales (`30°` for the 2:1 ground tile). The camera elevation must **not** be set to `26.565°` — that is the screen 2:1 slope, not an elevation, and using it breaks the verified ground.
2. Because a uniform-scale camera cannot satisfy ground (32/16) and height (24) simultaneously, the bake **sets the height scale explicitly** (anamorphic Z scale, a post-render vertical scale, or an engine-matched camera) so rendered height equals `height_px_per_world_unit` exactly. The pipeline pins the number; it does not let it fall out of the elevation.
3. The production contract and manifest record `camera_elevation_degrees`, the ground scales, and `height_px_per_world_unit`; the validator and runtime assert `height_px_per_world_unit` equals the engine-pinned factor (fail closed), so any future drift is a field-by-field failure, not a visual surprise.
4. If the engine factor and the locked ground scales are ever found mutually inconsistent, it is resolved **once, on the contract/engine side**, by agreeing a single coherent (ground, height) system — never by silently changing the bake angle per asset.

## Consequences

### Positive

- Removes the 30/26.57 ambiguity by pinning the quantity that actually matters (height px/unit).
- Keeps the verified ground projection intact — no elevation change, no re-bake of flat assets.
- Makes height mis-scaling a hard validator failure instead of silent visual drift.

### Negative

- The bake needs an explicit non-uniform vertical scale step, not just "set the camera angle."
- Requires the engine team to confirm and lock the height factor (the "·24") as a contract value.

## Validation requirements

- `height_px_per_world_unit` present in the production manifest and equal to the engine-pinned factor (validator + runtime assert).
- Ground scales unchanged (`×32 / ×16`, `tile_px [64,32]`); M1/M2 ground diagnostics still pass.
- A height-calibration probe (ADR-0019) passes before any height-bearing variant is baked.

## M1/M2 assumption

The arrow pilot is flat (no height) and uses only the ground projection, so it is unaffected and remains valid. No M1/M2 re-bake is required.

## M3 review questions

- Confirm the engine's exact height factor and its units; agree the single coherent (ground, height) system.
- Choose the height-scale mechanism (anamorphic camera vs post-scale).
- Does the height factor interact with per-variant scale (large/small creatures)?
