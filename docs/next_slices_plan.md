# Sprite Pipeline — Implementation Plan: Next Slices

_Prepared 2026-06-05. This file is the source of truth for the self-paced build loop._

## Scope guard (this iteration)

**Weapons and equipment are OUT.** Body-only character work and pipeline
hardening only. Weapon/shield/gear regions, weapon/muzzle/shield sockets,
fire/strike markers, runtime equipment layering, and ranged states are deferred
— see [§6](#6-deferred--weapons--equipment). They remain captured in
ADR-0009/0010/0011 (Proposed) and are not implemented now.

## How the loop uses this document

Each iteration:
1. Read this file. Find the first slice in [§4](#4-execution-order) whose status
   in [§8](#8-status-tracker) is not `done`.
2. If it is `blocked:blender`, do the code/doc parts that do not need Blender,
   mark it `partial:blender`, and continue to the next unblocked slice.
3. Implement that slice per its spec in [§7](#7-slice-specs). Keep changes
   minimal and localized. Honour every invariant in [§2](#2-contract-invariants).
4. Run the slice's verification gate. Update [§8](#8-status-tracker).
5. Commit (`<slice-id>: <summary>`) and push to origin.

## 1. Where we are

- M1/M2 direction-only arrow pilot: built, reviewed, green.
- Fix pass landed (commit `f7e2750`): `contract_hash` narrowed to
  `sprite_contract.lock.json`; `Image.NEAREST` mask extrusion; validator bounds
  anchor/sockets/boxes against the per-frame rect.
- Gates green: `smoke_test` PASS/PASS, `validate_manifest` 203 checks `ok:true`,
  `test_contract_hash` + `test_mask_discrete` pass.
- Repo clean and pushed (`main` == `origin/main`).

## 2. Contract invariants

Carried unchanged into every slice. A change to any is a silent-bug regression
and a hard stop:

- Forward = +X (East). Up = +Z. 1 unit = 1 meter.
- Origin = ground footprint center.
- World yaw bins are `N x 22.5deg` CCW from +X.
- Screen appearance is derived from `game_iso_v1`
  (`screen_x=(wx-wy)*32`, `screen_y=(wx+wy)*16`, `screen_y` down), never
  hand-picked. Consequence: world-CCW reads clockwise on screen; dir02 down,
  dir10 up. Do not "fix" this.
- Manifest/atlas/hitmask must validate against the lockfiles.
- `contract_hash` mismatch is a hard failure.
- State/frame counts come from `sprite_states.lock.json`, not prose.
- Effects are separate renderables (`variant_class: effect`), not character states.
- No bulk AI roster generation before M3 passes.

## 3. Slice map

**Track P — pipeline**

| Slice | Goal | Blender? |
|---|---|---|
| P0 | Verify existing arrow bundle (docs) | no |
| P1 | Harness hardening (build cmd, fixtures, CI output) | no |
| P2 | Blender-authored arrow probe | **yes** (.blend + render) |
| P3 | Source-asset descriptor schema | no |
| P4 | Source linter v1 (probe-level) | no |
| P5 | Source linter v2 (humanoid) | code now / fixtures need rig |

**Track C — content/source prep**

| Slice | Goal | Blender? |
|---|---|---|
| C0 | Source layout + naming conventions | no |
| C1 | Canonical rig template | **yes** (.blend) |
| C2 | Region policy (body regions) | no |
| C3 | Socket/marker policy — base sockets only; weapon parts deferred | no |
| C4 | World-metrics policy (body-only) | no |
| C5 | Texture/style guide + palette | no |
| C6 | Reference character B0–B4 (no ranged) | **yes** (.blend + clips) |
| C7 | Effects test assets (weapon-free) | partly (renderable frames) |
| C8 | Authoring checklist | no |
| C9 | Gen→conform recipe (HOLD scale) | no |

## 4. Execution order

Dependency-ordered worklist for the loop. `[B]` = needs Blender for its art
artifact; do the code/doc parts now and flag the art for a human/headless step.

1. **P0** — review + runbook docs
2. **P1** — harness hardening
3. **C0** — naming conventions
4. **C2** — region policy (body regions)
5. **C4** — world-metrics policy (body-only)
6. **P3** — `source_asset.schema.json` + body-only examples
7. **P4** — source linter v1 + probe fixtures
8. **P2** `[B]` — write `export_blender_probe.py` + descriptor now; `.blend`/render by human
9. **C5** — style guide + `palette.json` + swatch
10. **C1** `[B]` — `skeleton_spec.md` now; `rig_template.blend` by human
11. **P5** — humanoid linter code now; rig-dependent fixtures when C1 lands
12. **C6** `[B]` — descriptor/linter conformance now; `.blend` B0–B4 by human
13. **C7** — effect descriptors + (renderable) effect frames
14. **C8** — authoring checklist (md + machine json)
15. **C9** — gen→conform recipe; **HOLD** roster-scale AI until M3 passes

Key cross-dependencies: P3 before P2's descriptor and P4. C0 before P2/C1
naming. C1 rig + P5 before C6 animation conformance.

## 5. External dependencies

The loop runs headless Python; it **cannot** open Blender or produce `.blend`
files or renders. For `[B]` slices it will:
- write all schemas, linters, export tooling, descriptors, policies, and docs;
- generate placeholder/fixture data where possible;
- mark the `.blend`/render deliverable `blocked:blender` in §8 and describe
  exactly what a human (or a future headless-Blender/MCP step) must produce.

If a headless Blender becomes available, these unblock without plan changes.

## 6. Deferred — weapons & equipment

Explicitly **not** built this iteration (kept body-only):

- Regions: `shield`, `weapon`, `gear` — reserved in the palette, not exercised.
- Sockets: `weapon_grip`, `weapon_tip`, `muzzle`, `muzzle_back`, `shield_center`.
- Markers: `fire`, `strike` (weapon-referencing).
- States: B5 ranged. B4 is **fist** attack only (body-only).
- Runtime equipment layering (ADR-0011).

These stay Proposed in ADR-0009/0010/0011 and re-enter after the M3 base passes.

## 7. Slice specs

### P0 — Verify existing arrow bundle  (immediate next)

Goal: formal record that the M1/M2 seam is proven.
Deliverables:
- `docs/runbook.md` — consolidated run steps (generate → validate → smoke →
  tests → debug-sheet human check). May fold in `pipeline/docs/M1_M2_RUNBOOK.md`.
- `docs/m1_arrow_pilot_review.md` — what was verified (facing math vs rendered
  pixels; discrete masks {0,2}; hash gate fails closed; validator coverage; Rust
  loader anchor-flip + scale + asserts) and the fix pass before/after hash.

Machine gate: validator passes valid manifest; corrupted hash fails; (P1
fixtures fail). Human gate: dir02 down, dir10 up, clockwise spin, stable anchor
(`debug_sheet.png` — already confirmed).

### P1 — Harness hardening

Goal: one reproducible, CI-friendly command; stable diffable outputs; fixtures.
Deliverables:
- `pipeline/tools/build.py` — single entrypoint: generate `--clean` → validate
  `--report` → smoke_test → test_contract_hash → test_mask_discrete; aggregate
  nonzero exit on any failure; `--ci` prints a one-line PASS/FAIL summary.
- Stable `validation_report.json`: store the manifest path **repo-relative**
  (not absolute), so the report is reproducible and diffable. (Fixes the current
  absolute `C:\...` path.)
- `pipeline/tests/fixtures/valid/` + `pipeline/tests/fixtures/invalid/*`:
  invalid cases — corrupted `contract_hash`, out-of-palette mask value, anchor
  outside rect, missing required socket, wrong frame count, `mask_rect` != rect,
  transparent pixel with nonzero mask. Each is a manifest variant over a copied
  output dir (extends the smoke-test pattern).
- `pipeline/tools/test_fixtures.py` — asserts valid passes; every invalid fails
  nonzero **and** reports the expected error substring.

Machine gate: valid fixture passes; all invalid fixtures fail nonzero;
`build.py --ci` exits 0 on green.

### C0 — Source layout + naming

Deliverables: `docs/naming_conventions.md`; example trees. Prefixes: `VIS_`,
`HIT_`, `METRIC_`, `SOCKET_`, `ARMATURE_`. Region suffix grammar
(`HIT_torso`, `HIT_head`, …) restricted to body regions this iteration.

### C2 — Region policy (body)

Deliverable: `docs/region_assignment_policy.md`. M3+ authoritative hitmask
source = hit-proxy geometry; visual-mesh tags are debug-only unless marked
authoritative. Active regions this iteration: `none, head, torso, arms, legs`.
`shield, weapon, gear` reserved (see §6).

### C4 — Metrics policy (body)

Deliverable: `docs/world_metrics_policy.md` (+ optional measurement-script stub).
Body metrics exclude held weapons/shield/gear/backpack/cape/VFX. Visual bounds
may include them separately. `eye_height_world` emitted only when a head/eye
bone exists; `eye_height_world <= height_world`.

### P3 — Source-asset descriptor schema

Deliverable: `pipeline/schema/source_asset.schema.json` + examples
(`pipeline/schema/examples/source_asset.probe.json`, `.character.json`,
`.effect.json`). Required fields: `asset_id, variant_class, source_format,
forward_axis, up_axis, units, origin_policy, visual_objects, hit_proxy_objects,
metric_proxy_objects, sockets, clips_states`. Schema may *allow* weapon socket
names (forward-compat) but examples use body-only sockets.

### P4 — Source linter v1

Deliverable: `pipeline/tools/lint_source_asset.py` + valid/broken arrow_probe
fixtures. Checks: descriptor schema valid; source file exists; required objects
exist; required sockets exist; allowed (body) region names only;
forward/up/unit declarations match contract; origin exists; `min_z` within
tolerance. No skeleton/animation checks yet.

### P2 — Blender arrow probe  `[B]`

Deliverables (code now): `pipeline/tools/export_blender_probe.py` (reads a
`.blend` via Blender `bpy`, renders 16 dirs through the game_iso_v1 camera,
writes frames → atlas/hitmask → manifest using the existing packing/validator
path); `source_assets/arrow_probe/source_asset.json` (probe descriptor, P3-valid).
Blocked-on-Blender: `arrow_probe.blend`, the render, `output/arrow_probe_blender/*`.
Rules: `variant_class=probe`, forward +X, up +Z, origin=anchor, 16 dirs, idle
only, no humanoid skeleton. Machine gate: exported manifest validates; yaw
values match lockfile; mask palette valid; `contract_hash` matches. Human gate:
matches the Python arrow's direction behavior.

### C5 — Style guide + palette

Deliverables: `docs/style_guide.md`; `pipeline/style/palette.json`; swatch PNG
(generatable headless with PIL). Acceptance: readable 256px + 128px previews,
silhouette preview, straight alpha.

### C1 — Rig template  `[B]`

Deliverables: `docs/skeleton_spec.md` (default skeleton: root, pelvis,
spine_01/02, neck, head, eye, clavicle/upper_arm/forearm/hand L+R,
thigh/shin/foot/toe L+R). Blocked-on-Blender: `source_assets/rig_template.blend`.
Review item: project-native vs Mixamo-compatible bone names.

### P5 — Source linter v2 (humanoid)

Deliverable (code now): extend the linter with skeleton checks, humanoid
body-socket checks (origin, head_center, hand_l, hand_r — weapon sockets
deferred), metric-proxy checks, clip/marker checks, root XY-drift check.
Rig-dependent fixtures land once C1's `.blend` exists.

### C6 — Reference character (staged, body-only)  `[B]`

Sub-slices: B0 static standing, B1 idle, B2 walk, B3 hurt/death/resurrect,
B4 fist attack. (B5 ranged deferred — §6.) Each sub-slice must pass the linter
level that exists when it lands. Loop produces descriptors + conformance now;
`.blend` + clips are blocked-on-Blender.

### C7 — Effects test assets (weapon-free)

Deliverables: directional debug flash (a weapon-free rename of the
"muzzle/debug flash"), directionless spark, directionless ground puff. Rules:
`variant_class=effect`, anchor=emission point, no hitregions, `direction_count=1`
unless visually directional. Effect frames can be generated headless with PIL.

### C8 — Authoring checklist

Deliverables: `docs/content_checklist.md` +
`pipeline/tools/content_checklist.machine.json` (machine-checkable subset).

### C9 — Gen→conform recipe

Deliverables: `docs/gen_to_conform_recipe.md` + cleanup-budget estimate.
**HOLD:** no roster-scale AI generation before the M3 base passes.

## 8. Status tracker

_Updated by each loop iteration._

| Slice | Status | Notes |
|---|---|---|
| P0 | done | runbook.md + m1_arrow_pilot_review.md |
| P1 | done | build.py + test_fixtures + repo-relative report path |
| C0 | done | naming_conventions.md |
| C2 | done | region_assignment_policy.md |
| C4 | next | body-only metrics |
| P3 | todo | schema + body examples |
| P4 | todo | linter v1 + fixtures |
| P2 | todo · blocked:blender (.blend/render) | tooling+descriptor doable now |
| C5 | todo | headless PIL OK |
| C1 | todo · blocked:blender (.blend) | skeleton_spec doable now |
| P5 | todo | code now; fixtures need C1 |
| C6 | todo · blocked:blender (.blend) | descriptors/conformance now |
| C7 | todo | weapon-free; PIL OK |
| C8 | todo | |
| C9 | todo · HOLD scale | recipe only |

Legend: `done` · `next` · `todo` · `partial:blender` · `blocked:blender` · `HOLD`.
