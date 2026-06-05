# ADR-0019: Foreshortening/Aspect Calibration Probe Before Height-Bearing Bakes

- Status: Proposed
- Date: 2026-06-05
- Supersedes: an earlier draft that framed the gate as a *pixel-height* (`height_world×24`) equality check. That absolute sizing is an **engine** concern (`render.rs::sprite_size`), **not** a bake gate — see the Decision.
- Blocks: M2A combat surfaces; M3 height-bearing variants
- Related: ADR-0018 (elevation/sizing), ADR-0015 (arrow direction probe), ADR-0013, ADR-0014

## Context

The flat arrow probe proved the ground/direction convention but is elevation-immune
(no height), so it **cannot** reveal whether the bake's 30° height **foreshortening** is
correct. Per ADR-0018 the engine applies the absolute `height_world×24` sizing; the bake
owns the 30° foreshortening (which sets the frame **aspect** + internal proportions). A
wrong elevation shows up as a wrong foreshortening/aspect, and is the one irreversible
mistake (it forces a re-bake), so it must be gated before any real 3D bake.

## Decision

Add a **foreshortening/aspect calibration probe** — a known-proportion 3D object (e.g. a
`1×1×H` box / pole, plus a cube) rendered through the production 30° bake path.

- **Bake-side gate (this IS a bake gate):** the rendered object's **aspect / internal
  proportions** match the 30° orthographic projection prediction within tolerance. This is
  what catches a wrong elevation.
- This is **NOT** a "rendered pixel height == `height_world×24`" check — that absolute
  sizing is applied by the **engine** (`render.rs::sprite_size`) and is verified by an
  **engine** test, not a bake gate.
- No height-bearing variant (M2A/M3) is baked until this passes. Flat/probe assets exempt.

## Consequences

### Positive
- Catches a wrong elevation on one tiny object, not the whole roster.
- Reuses the R1 renderer + the probe → atlas → manifest → validator path.
- No confusion with engine-side absolute sizing.

### Negative
- One more gate before real art; needs a known-proportion reference object.

## Validation requirements
- The calibration object's rendered **aspect** matches the 30° projection within tolerance.
- `camera_elevation_degrees == 30` (ADR-0018); 26.565 rejected.
- Anchor / ground-contact correct.

## M1/M2 assumption
Not part of M1/M2 (flat arrow). Added at M2A / R3, before the first height-bearing asset.

## M3 review questions
- Reference object(s) + tolerance (aspect-implied extents to ±1 px?).
- Should this merge with the direction probe into one calibration asset?
