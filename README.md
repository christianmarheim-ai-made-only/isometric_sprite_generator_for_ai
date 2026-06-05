# Isometric Sprite Generator (`game_iso_v1`)

A headless pipeline that bakes a 3D model into **16-direction isometric sprite sheets
+ a machine-readable manifest** for a Bevy/Vulkan isometric game (format
**`game_iso_v1`**). Core discipline: **avoid silent contract bugs** — output that looks
right but is subtly wrong (a half-bin rotation, a flipped axis, a wrong camera angle, a
blended mask value).

## Status

- **M1/M2 arrow pilot + hardening** — done: deterministic 16-direction probe, validator,
  fixtures, lockfile `contract_hash` gate, source-asset schema + linter, policies.
- **R1 — headless 3D renderer** — done: `pipeline/tools/render3d.py`, a numpy
  orthographic rasterizer whose camera matches the engine's ground projection to
  floating-point precision.
- **R2–R6** — spec-resolved in **[docs/build_plan_R1_R6_review.md](docs/build_plan_R1_R6_review.md)**,
  the **authoritative forward plan**: engine-shaped manifest + bake orchestrator (R2),
  acceptance gates + calibration (R3), real-mesh + hit-proxy R8 hitmask + metrics (R4),
  animation/crop + full manifest convergence (R5), first reference character end-to-end +
  engine load-test (R6).

One green build gate (`build.py --ci`, all steps green):

```bash
pip install -r requirements.txt
python pipeline/tools/build.py --ci
```

## The engine contract (pinned)

`game_iso_v1`: camera **azimuth 45°, elevation 30°** (`sin30° = 0.5` → a 2:1 ground tile;
`arctan(0.5) ≈ 26.565°` is the on-screen *tile-edge* angle, **not** the camera elevation),
**1 unit = 1 m**, forward **+X**, up **+Z**, origin = ground footprint center. The engine
sizes sprites by **`height_world × 24`** (`render.rs::sprite_size`), so the bake supplies
the **30° foreshortening + `height_world`**, **not** an in-bake ×24. The manifest's
top-level must carry a `camera` block (`camera.id == "game_iso_v1"`), `frames[]` with
per-frame `rect` + `anchor`, and (for non-probe variants) `world_metrics`. Full pinned
contract + locked conventions: **[docs/build_plan_R1_R6_review.md §0](docs/build_plan_R1_R6_review.md)**
and **[docs/engine_reference_alignment.md](docs/engine_reference_alignment.md)**.

## Layout

```text
adr/                       ADR-0006..0019 (design decisions; weapons/AI/compression deferred)
docs/                      plans + policies — build_plan_R1_R6_review.md is authoritative for R2-R6
pipeline/
  tools/                   generators, render3d (R1), validator, source linter, build.py gate, tests
  schema/                  manifest + source-asset JSON schemas (+ examples)
  lockfiles/               sprite_contract / sprite_states / sprite_variants
  style/                   palette + readability previews
  output/arrow_pilot/      the committed M1/M2 golden baseline (regenerable)
  bevy_reference/          reference-only Rust snippets (the real engine is the authority)
source_assets/             source-asset descriptors (e.g. arrow_probe)
```

## Scope (this iteration)

**Body-only.** Weapons, equipment, AI generation, and compression are deferred
(ADR-0009/0010/0011/0016/0017). The pipeline runs **fully headless** on procedural
meshes; real art (Blender / glTF / AI) plugs into the **R4** mesh-input and **R5**
animation seams without pipeline changes.
