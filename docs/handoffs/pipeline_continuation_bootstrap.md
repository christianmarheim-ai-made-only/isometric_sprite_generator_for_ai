# Pipeline continuation — bootstrap handoff

**Read this first.** It is the single orientation doc for a fresh chat continuing work on the
`isometric_sprite_generator_for_ai` pipeline. Snapshot: commit `8fe102e` (HEAD at hand-off),
gate green at **38/38**.

---

## 1. What this repo is

A deterministic **isometric sprite-generation pipeline**: a model producer delivers a 3D model
(`.glb`) + a small contract file (`<id>.asset.json`), and one command bakes it into a
`game_iso_v1` sprite package (color atlas + R8 hit-mask atlas + `manifest.json` + a verification
report). The pipeline is **gated**: input is linted, the bake runs, and the output is verified —
every stage speaks one error vocabulary so the two `ok` flags can never disagree.

It is **standalone**. It vendors everything it needs from the engine, so it builds in isolation:
- `pipeline/schema/manifest.schema.json` — the engine's manifest contract (vendored).
- `pipeline/bevy_reference/` — a small Rust crate that parses manifests with the **real** engine
  loader logic, run by `test_engine_load` (skips if `cargo` absent). This is how we prove the
  engine will accept our output without needing the engine repo.

## 2. The hard boundary (why this chat is pipeline-only)

The **game engine owns the manifest/asset contract** — it is the consumer. The engine is finished
and stable, and it is **not in this repo and must not be modified here**. We treat its contract as a
fixed external dependency: the vendored `manifest.schema.json` + `bevy_reference` loader are the
contract surface we must conform to. **This chat fixes the pipeline only** — it makes the bake
correct and the gate trustworthy; it does not change the engine or the locked contract.

## 3. The LOCKED contract — never alter

`game_iso_v1` (in `pipeline/tools/constants.py` + the schemas). Treat as immutable:

- 2:1 **dimetric**, azimuth **45°**, camera elevation **30°**, **16** directions.
- forward = **+X** = direction 0; up = **+Z**; tile **64×32 px**; frame canvas **256 px**;
  a single atlas page ≤ **4096 px** (`MAX_PAGE_PX`).
- R8 hit-mask palette is the fixed 4-body set: `{none:0, head:1, torso:2, arms:3, legs:4}`.
- Delivery contract = **`external_asset_v2`** (`pipeline/schema/external_asset.schema.json`,
  `additionalProperties:false`). `texture_mode` is REQUIRED ∈ `{flat_region, textured}`.

If you think the contract must change, that is an **engine-side** decision — write it up, don't do it.

## 4. Prove you're green (do this first)

```bash
python pipeline/tools/build.py --ci        # the whole gate; expect "BUILD PASS: 38/38"
```

- Pure-Python steps always run. **Blender-gated** steps (real bakes, parity, region e2e) and the
  **cargo** step (`test_engine_load`) **skip gracefully** (exit 0) when Blender/cargo are absent —
  the gate still reports green, just with fewer real bakes exercised.
- For real bakes you need **Blender** (set `$BLENDER` or have it on PATH) and Python **numpy + Pillow**.
- One command to bake a delivery: `python pipeline/tools/bake_asset.py <id>.asset.json --out <dir>`.

## 5. Working conventions (non-negotiable)

- **No Unicode in Python `print()`** — the Windows console is cp1252; `→`/`✓` crash it. Write
  reports to UTF-8 files and read them back if you need glyphs.
- **`.gitignore` new `pipeline/output/*` dirs BEFORE `git add -A`** — bakes are large + regenerable.
  Verify nothing under `pipeline/output/` or temp is staged before every commit.
- **Keep the gate green.** Run `python pipeline/tools/build.py --ci` before committing; it must stay
  at 38/38 (or higher as you add tests). New behavior ⇒ new test, registered in `build.py` `STEPS`.
- **Commit + push are pre-authorized** to `origin/main` (GitHub: `christianmarheim-ai-made-only/
  isometric_sprite_generator_for_ai`). End commit messages with the `Co-Authored-By` trailer.
- When you change anything in the **authoring contract** (`pipeline/schema/*`, `pipeline/examples/*`,
  the packaged docs), re-run `python pipeline/tools/package_authoring_contract.py` and commit the
  regenerated `dist/model_authoring_contract_v1.zip` — `test_dist_drift` enforces this.
- Don't "correct" the locked screen winding / projection (game_iso_v1 is intentional).

## 6. Architecture map (where things live)

Bake orchestration:
- `pipeline/tools/bake_asset.py` — the front door: lint → route → bake → Gate-1 → build-log + report.
- `pipeline/tools/blender_bake.py` — `bake_blender` (static glb) + `bake_animated` (rigged clips);
  packs atlases, maps the region pass → R8 ids, builds the manifest.
- `pipeline/tools/blender_render.py` — the in-Blender renderer (the EXACT game_iso_v1 ortho camera,
  16 dirs, color + region passes, world-AABB → screen `region_rects` projection).
- `pipeline/tools/rig_from_profile.py` — auto-rig an unrigged delivery from a rig profile.

Gate / verification (one vocabulary):
- `pipeline/tools/error_codes.py` — the SINGLE source of `(severity, stage, check)` per code.
- `pipeline/tools/lint_external_asset.py` — input gate (texture mode, clips, bones, …).
- `pipeline/tools/build_log.py` — assembles `build_log.json`; mode-aware escalation (ADR-0028),
  waivers, explicit-region downgrade.
- `pipeline/tools/verification_report.py` — projects warnings → `verification_report.json`
  (`ok` == build_log `ok` by construction).
- `pipeline/tools/calib_oracle.py` — calibration colour-oracle (ADR-0030/0031).

Regions / hitboxes:
- `pipeline/tools/constants.py` — `REGION_RGB`, `REGION_KEYWORDS`, `region_for_name`,
  `CLIP_REQUIREMENTS`, `forward_yaw`, canvas/dirs. **The drift-proof source of truth.**
- `pipeline/tools/region_paint.py` + the projection in `blender_render.py` — ADR-0036 explicit-hitbox
  region baking (project world AABBs → relabel a degenerate single-material mask).
- `pipeline/tools/skin_delta.py` — texture-only variant process + guard (the green-dragon case).

Contract + scaffolding:
- `pipeline/schema/` — `external_asset.schema.json`, `sprite_manifest.schema.json`, `hitbox_spec…`,
  `rig_profiles/{biped,bird,quadruped,dragon,ball}_v1.json`, vendored `manifest.schema.json`.
- `pipeline/tools/intake_package.py` — synthesize an `.asset.json` from a delivery + gate it.
- `pipeline/tools/build.py` — the gate runner (the STEPS list = every test).

## 7. Producer-facing contract + the docs that matter

A delivery is a model + an `.asset.json` (+ optional `<id>_hitbox.json`, animation clips, textures).
The producer-facing docs (read in this order for a new creature):
1. `docs/external_asset_contract.md` — the front-door contract + the two region-assignment paths.
2. `docs/modeling_the_body.md` — scale / forward / origin / region anatomy mapping.
3. `docs/generating_hitbox_data.md` — world-metrics math + the per-region AABB format + the tool.
4. `docs/generated_package_intake.md` — "Preparing for new creatures" (add archetype + rig profile).
5. `docs/handoffs/model_producer_delivery_spec.md` + `…_spec_v3_plan.md` — the full producer spec
   + the v3 roadmap (stages, invalidation matrix, prompt-library design).
6. `adr/INDEX.md` — all design decisions; ADR-0025 (hit regions), 0028 (mode-aware severity),
   0030/0031 (calibration oracle), 0035 (origin/anchor), 0036 (explicit-hitbox region baking).

## 8. Current state (what's hardened)

- Full gated pipeline (input → bake → output verify) across texture / skin / anim / hitbox stages.
- FLAT-textured faithful render; `external_asset_v2`; mode-aware escalation + waivers; calibration
  colour-oracle; per-region AABBs (ADR-0025); model-origin/anchor contract (ADR-0035).
- **Skin deltas** (`skin_delta.py`): texture-only variants cloned from a base, with a guard proving
  geometry+UV identity; clones the base's region hitbox sidecar.
- **Explicit-hitbox region baking** (ADR-0036): a single-material model + its `region_hitboxes` now
  bakes a multi-region hit-mask (dragon went `hit_regions_present [2] → [1,2,3,4]`).
- 38-step gate green; recent commits: `8fe102e` (region baking), `068186b` (skin delta), `b8127f6`
  (Epic B oracle/waivers/AABBs), `c3ad372` (v2 migration).

## 9. Open threads (where to take it)

Known gaps + deferred items, roughly prioritized — confirm scope with the user as new deliveries arrive:

1. **Region vocabulary reconciliation.** Two systems coexist: the fixed **4-body** R8 mask
   (`head/torso/arms/legs`) vs. a **rich named** AABB sidecar (the v3 dragon ships 10:
   eye/mouth/horn/wing/tail/foreleg/hindleg/…). ADR-0036 bakes a *coarse* collapse of the rich set
   into the 4 ids; deciding whether the engine wants richer per-region data is an engine-contract
   conversation. The exact named AABBs live in `<id>_hitbox.json`.
2. **Missing producer guides** (proposed, not yet written): `docs/authoring_hitboxes_nonstandard.md`
   (the dragon walkthrough: material-name vs `hit_proxy_objects` vs explicit sidecar) and
   `docs/adding_a_creature_archetype.md` (the ordered checklist: enum → rig profile →
   `CLIP_REQUIREMENTS` → upright/radial gate → tests → intake-validate) + a `rig_profile_template.json`.
3. **ADR-0033 creature-traits seam is Proposed, not built** — `archetype_traits.json`,
   `REGION_SETS`, `has_direction`/`is_radial`. Needed before non-upright / radial / custom-region
   creatures are first-class. `_non_upright` is still hard-coded biped-only (`build_log.py`).
4. **Static-bake up-axis correction.** A Z-up glb that is exported wrong imports into Blender lying
   down; the static path has no auto-correction (the animated path does). Add the correction + a
   negative fixture ("Z-up-wrong glb → orientation gate fires"). (The dragon was fixed by hand.)
5. **Per-archetype calibration goldens + a negative/mutation harness in CI** — needs committed
   per-archetype calibration fixtures (bake every commit; mutate inputs to prove the gate bites).
6. **New-creature intake hardening** — as new models arrive, tighten `intake_package.py` /
   `lint_external_asset.py` so the gated process catches each new failure mode it surfaces.

## 10. First moves in the new chat

1. Extract the zip; `cd` into the repo; run `python pipeline/tools/build.py --ci` → expect 38/38.
2. Skim `adr/INDEX.md` + this doc's §6–§7. Read `external_asset_contract.md` end-to-end.
3. If a new model delivery is in hand: drop it in, run `bake_asset.py` (or `intake_package.py`),
   read the verification report, and fix whatever the gate (rightly) refuses — adding a test for
   each new failure mode. If the gate is wrong, fix the gate + its test. Keep 38/38 green; commit+push.
