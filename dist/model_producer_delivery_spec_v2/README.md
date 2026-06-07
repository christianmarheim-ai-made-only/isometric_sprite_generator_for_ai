# Model Producer Delivery Spec — v2 (formal input requirements for the game_iso_v1 bake pipeline)

```yaml
producer_spec_version: model_producer_delivery_spec_v1
status: Accepted
effective_date: 2026-06-07
compatible_schema_versions:
  external_asset: external_asset_v2        # texture_mode REQUIRED; optional-compatible shim shipped as v1+texture_mode
  animation: anim_clips_v1
  hitbox: hitbox_v1
  preflight: producer_preflight_v1
  verification: verification_report_v1
supersedes:
  - docs/modeling_the_body.md
  - docs/texturing_the_body.md
  - docs/external_asset_contract.md
binding_scope:
  - model producer package handoff
  - producer self-verification before handoff
  - sprite-pipeline intake validation
```

## What this package is

The single authoritative, versioned contract a model-producer (an AI or a human) follows to deliver a 3D-model **package** that the `game_iso_v1` pipeline turns into a 16-direction sprite (color atlas + R8 hitmask + manifest) **with zero manual refinement**. The pipeline does exactly three things and gates between them: **verify input → bake → verify output**, all deterministic. The only place variation is allowed is *this* package; everything downstream is mechanical.

This is a small-margin dataset spec: most checks are **numbers**, not opinions. If you hit every number in `THRESHOLDS.md` and pass `self_verify_gate.md`, the bake is automatic and the sprite looks right in all 16 directions.

## Package contents

```
README.md                      <- you are here (metadata + contract status)
model_producer_delivery_spec.md  <- the full per-stage how-to (geometry/UV/texture/rig/anim/hitbox)
THRESHOLDS.md                  <- every numeric value you must hit (the load-bearing table)
self_verify_gate.md            <- the copy-paste commands you MUST pass before handoff
error_codes.md                 <- the canonical rejection codes
improvement_addendum.md        <- the consolidated v2 improvement snippets (versioning, waivers, calibration, ...)
schema/                        <- external_asset_v2 delta + the new sidecar schemas
examples/                      <- one manifest per archetype + provenance/preflight/verification/waiver examples
```

## The three rules that matter most (the rest is detail)

1. **Declare `texture_mode` and mean it.** `flat_region` = per-region solid colours, no UVs/atlas needed (honest, fully supported). `textured` = a real UV unwrap + a base-colour image **bound inside the glb** (`baseColorTexture`). A loose atlas next to a UV-less mesh is an **orphan** and is rejected at the front door — declaring `textured` without being *texture-capable* fails before any bake.
2. **Hit every number in `THRESHOLDS.md`.** Degenerate UVs, a flat/swatch atlas, a front that looks like the back, an off-vocab clip, a mis-scaled body — each is a coded, deterministic rejection.
3. **Run the self-verify gate and ship its reports.** `preflight_report.json` (you) and `verification_report.json` + `build_log.json` (the bake) must all agree `ok == true`. A package handed off without a passing preflight is incomplete.

## What changed from v1

- Promoted from *Proposed guidance* to an *Accepted, versioned, schema-backed contract* (no more validating against a private/stale schema copy — the authoritative schemas ship **in this ZIP**).
- Every fuzzy check is now numeric (atlas richness, front/back distinctness, UV overlap).
- Real textured vs `flat_region` vs **calibration** are first-class and separated; calibration debug textures are legal via an explicit, expiring waiver that can never claim `real_albedo: true`.
- Added `preflight_report.json` (producer-side) and a richer `verification_report.json` (bake-side) with the `preflight.ok == verification.ok == build_log.ok` agreement invariant.
- First-class per-archetype rules for `biped_v1`, `bird_v1`, `quadruped_v1`, `dragon_v1`, `ball_v1`.
