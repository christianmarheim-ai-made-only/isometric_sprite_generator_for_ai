# ADR-0019: Height-Calibration Probe and Gate Before Height-Bearing Bakes

- Status: Proposed
- Date: 2026-06-05
- Blocks: M2A combat surfaces; M3 height-bearing variants
- Related: ADR-0018 (height pixel scale), ADR-0015 (arrow direction probe), ADR-0013 (M2A harness), ADR-0014 (validator/runtime)

## Context

ADR-0018 pins vertical projection by an explicit height pixel scale rather than the camera elevation. That number must be **verified against the running engine before** real character variants are baked — otherwise a wrong height scale is found only after the catalogue exists, forcing the full re-bake the "30 vs 26.57" flag warns about. M1 set the pattern: a tiny deterministic probe proves one engine-facing assumption in pixels (the arrow proved direction + ground projection). Height needs the same.

## Decision

Add a **height-calibration probe** — the vertical analogue of the arrow direction probe — and gate height-bearing bakes on it.

- The probe is a known-height vertical reference (e.g., posts of exactly 1.00 m and 2.00 m at the origin), rendered through the production bake path.
- **Machine gate:** each reference's rendered pixel height equals `height_world · height_px_per_world_unit` within a tight tolerance (e.g., ±1 px), and the base sits on the anchor (origin == anchor, ground contact).
- **Human gate:** the probe overlaid at its engine-computed screen position lines up at top and bottom (a debug sheet, like the arrow sheet).
- **No height-bearing variant (M2A or M3) is baked until this probe passes** against the engine's pinned factor. Flat/probe assets are exempt.
- The probe's measured factor is written to its manifest and is the value ADR-0018's validator/runtime checks assert against.

## Consequences

### Positive

- Catches a wrong height scale on one 5-minute asset instead of the whole roster.
- Turns ADR-0018's "·24" from an assumption into a measured, regression-tested fact.
- Reuses the proven probe → atlas → manifest → validator path.

### Negative

- One more gate before real art.
- Needs the engine to expose (or confirm) where it expects the top of a known-height unit on screen.

## Validation requirements

- Probe manifest validates; `height_px_per_world_unit` recorded.
- Rendered reference heights match `height_world · factor` within tolerance.
- Anchor/base alignment holds (origin == anchor, ground contact).
- Gate wired into the M2A/M3 pre-bake checks (CI).

## M1/M2 assumption

Not part of M1/M2 (flat arrow). The probe is added at M2A, before the first height-bearing asset.

## M3 review questions

- Reference heights and tolerance (±1 px? sub-pixel?).
- Should the probe also calibrate eye height (ADR-0007) for muzzle/projectile alignment?
- Merge the height probe with the arrow direction probe into one calibration asset?
