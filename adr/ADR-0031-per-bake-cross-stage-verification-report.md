# ADR-0031: Per-bake cross-stage verification report + severity policy (verified-applied)

- Status: **Proposed**
- Date: 2026-06-07
- Blocks: trusting any baked package as correct without opening it in an engine; M3 controlled real variants (the hit data has to be *true*, not just present)
- Supersedes: none
- Related: **ADR-0030** (the per-archetype calibration golden — the oracle this report consumes), **ADR-0025** (per-region AABBs — this ADR *implements* them and gates them), **ADR-0028** (texture-fidelity gate — one stage of this report), ADR-0024 (effects bind to the `core`/torso-region centroid this report validates), ADR-0006 (topmost-surface region-mask semantics); grounding: `pipeline/tools/build_log.py` (ok/severity wiring), `pipeline/tools/blender_render_anim.py` (region pass, rest pose, per-frame render), `pipeline/tools/rig_from_profile.py:66-84` (nearest-bone bind, no validation), `pipeline/tools/constants.py` (`ENGINE_CLIP_VOCAB`/`CLIP_SYNONYMS`), `pipeline/schema/rig_profiles/biped_v1.json` (`region_by_bone`), `pipeline/tools/bake_batch.py` (FLAGGED summary, exit code)

## Context

We have proven — by parsing the delivered glbs and reading the atlases, not by inspecting renders — that a bake can ship **green-lit while being silently, structurally wrong**. The failure is not in any one stage; it is that *no stage proves its own output is correct*, and the few detectors we have are all non-fatal.

### The verified gap (ground truth, four root-cause layers)
- **L0 — geometry-only + orphan atlas.** The ogre and dragon glbs carry 0 materials, 0 textures, 0 images, and **zero UVs** (no `TEXCOORD_0`) on every part; `red_ball` is 1 mesh, 0 UVs, 0 binding. Their `*_texture_atlas.png` are orphan sidecars bound to nothing. `materials.json` is a few flat per-region base colours.
- **L1 — degenerate UVs.** `pirate_v2` has 19 region-keyworded materials, all 19 carrying a `baseColorTexture` bound to one embedded atlas — but all 37 primitives have **UVs collapsed to a single point** (each pinned to the centre of its swatch-grid tile), so each material samples exactly one texel: one flat colour per part. A flat-colour-via-texture hack, not a real unwrap. (Contrast the known-good `humanoid_textured.glb`: 4 region materials, bound `baseColorTexture`, UVs spanning area 0.40–0.92 — a real unwrap. That is the shape a correct textured delivery must match.)
- **L2 — the auto-rigger destroys input fidelity and mis-binds.** `rig_from_profile.py` **replaces every part material with a flat per-region colour** (`rig_from_profile.py:142-160`), **strips UVs/vertex-colours**, never reads the texture, binds each part 100% to its **nearest bone by centroid with no validation** (`rig_from_profile.py:66-84` — `nearest_bone(cen)`, no check against the profile's `region_by_bone`), and **crashes on the pirate's dict-shaped `materials.json`**.
- **L3 — render is capable but only as good as its input.** `blender_render_anim.py` selects `TEXTURE` shading iff `has_tex` (`:214`), so a real unwrap *would* render; but fed L0–L2 input it faithfully renders flat.
- **L4 — no gate.** `degenerate_uv` is a **non-aborting WARN** (`build_log.py:140-142`), and `build_log` `ok` only flips false on a `severity == "error"` warning (`build_log.py:172`). The renderer's region pass, rest pose, and per-frame poses (`blender_render_anim.py:175-225`) emit no per-stage truth claims at all. So a textured-but-flat bake — or a mis-bound limb, or a rest-stuck clip, or an empty region mask — ships with `ok: true`.

### Why "it baked" is not "it is correct"
Today's detectors check a handful of *symptoms* (`region_fallback_torso`, `missing_clip_rest_pose`, `degenerate_uv`, `world_metrics_mismatch`, `non_upright_biped`) and only two of them flip `ok`. There is no claim that:
- the *intended* bone moves for the clip (walk → legs, attack → arms), or that the clip moves **at all** vs the rest pose;
- the part bound to the bone the rig profile **intends** (`region_by_bone`), not just the nearest centroid;
- the R8 mask is non-empty for every **declared** region and actually **overlaps that region's known calibration colour**;
- the per-region AABBs ADR-0025 promised **exist**, bound their region, and **track the limb across frames**;
- the regions **tile the silhouette** with no inter-limb gaps a projectile could thread (ADR-0028).

The pieces to check all this now exist: `region_by_bone` is in `biped_v1.json` (currently inert), the region RGB palette is canonical (`constants.REGION_RGB`), the clip vocabulary is canonical (`constants.ENGINE_CLIP_VOCAB`/`CLIP_SYNONYMS`), and ADR-0030 gives a per-archetype calibration oracle with known colour blocks. What is missing is a **report that aggregates per-stage checks with a severity that can fail the build**, plus a **regression net** proving each check actually fires.

## Decision

**Every bake emits a structured `verification_report.json`** aggregating per-stage checks. Each check has a `stage`, a stable `code`, a `severity`, a boolean `pass`, and a human `detail`. The report is the single artifact that answers "is this bake *correct*", not merely "did it run". The build log's `ok` and the batch FLAGGED summary are driven by it.

### Stages and their load-bearing checks

**MODELING** (world-frame sanity, from `blender_render_anim.py` metrics + the region pass)
- `world_metrics` — measured `height_world` within tolerance of authored (subsumes today's `world_metrics_mismatch`).
- `upright` — biped silhouette is portrait, not baked lying down (subsumes `non_upright_biped`).
- `frontback_distinct` — heading **N** differs from heading **N+8** (front ≠ back); a flat/symmetric-by-accident bake that spins into 16 *aliased* frames is caught. Symmetric props are exempt (see waivers).
- `regions_tile_silhouette` — the per-part region render **partitions the solid silhouette with no inter-limb gaps** (ADR-0028); every silhouette pixel owns a region id, no holes.

**SKINNING** (closes the L2 mis-bind, from a rest vs moved-frame diff)
- `all_parts_bound` — no static part; every part-mesh is skinned (no part renders identically under a moved bone).
- `bound_to_intended_bone` — each part binds to the bone its region **intends** per the rig profile's `region_by_bone`, catching the **unvalidated nearest-bone-by-centroid** mis-bind in `rig_from_profile.py:71-72`.
- `bind_deforms` — the bind is live: a part's **calibration colour block (ADR-0030)** actually **displaces** between the rest pose and a moved frame.

**ANIMATION** (closes the rest-stuck / wrong-region-moves failures, from per-frame vs rest diffs)
- `clip_not_rest_stuck` — animated frames **differ from the rest pose** (no dead clip; subsumes `missing_clip_rest_pose` and promotes it to load-bearing).
- `clip_intent` — the **right region moves for the clip intent** (walk/run → legs, attack → arms, idle → small overall motion), resolved through `CLIP_SYNONYMS`.
- `loop_seam` — for `playback: loop`, last frame ≈ first frame (continuity).
- `frame_motion` — per-frame motion is non-degenerate (no two consecutive frames identical inside a multi-frame clip).
- `clip_vocab_coverage` — declared clips map onto `ENGINE_CLIP_VOCAB` (off-vocab synonyms flagged), **including resolving the death gap** (`death` declared and bakeable where the archetype requires it).

**HITBOX** (finally **implements** ADR-0025's per-region AABBs and gates them, from the R8 mask + the ADR-0030 oracle)
- `declared_regions_present` — the R8 mask is **non-empty for every DECLARED region** (a declared `legs` that produced zero mask pixels is a collapse).
- `mask_colour_oracle_aligned` — mask region **R overlaps the known calibration colour pixels** for R (ADR-0030): the mask is labelled with the region whose paint actually sits there, catching a label/paint swap.
- `region_aabbs_emitted_and_bound` — per-frame per-region AABBs **exist** (implementing ADR-0025), each **bounds exactly its region's mask pixels**, and **tracks the limb across frames** (the AABB moves with the moving region).
- `occlusion` — the **nearest part owns the pixel** (arm-over-torso resolves to arm), per the region-pass z-buffer (ADR-0006).

### Severity policy
- **Load-bearing checks flip `build_log.ok` to false.** Today everything is a WARN so a broken bake ships; under this ADR, a failed load-bearing check (an `error`-severity entry) fails the bake and the batch (`bake_batch.py:189` already exits non-zero on `not ok`).
- **Severities:** `error` (fails the build), `warn` (review, does not fail), `info` (provenance). The L0/L1/L2 failures above become `error`.
- **Per-asset waiver allowlist.** A named asset may waive a specific check `code` (with a recorded reason) — e.g. a deliberately-flat placeholder, or the cow's hugging `pelvis_ring` opt-out pattern from ADR-0024. A waiver downgrades that one check for that one asset, recorded in the report.
- **Symmetric props are exempt** from `frontback_distinct` and from clip `frame_motion`/`clip_intent` (a barrel has no front, no walk).

### Surfacing
- Results are summarized into `build_log` `warnings[]` **codes** (the existing channel, `build_log.py:134-163`) so `ok` and the per-variant log carry them.
- The batch **FLAGGED** summary (`bake_batch.py:171-189`) lists each variant's failing/waived check codes, so a reviewer sees at a glance which bakes are correct, which need a look, and which failed.

### Regression net
- The **per-archetype calibration golden (ADR-0030) is baked every commit** as the regression net; its known colour blocks are the oracle the SKINNING/HITBOX checks consume.
- A **mutation harness** proves each detector fires: a deliberately broken input (unbind a part, freeze a clip to rest, zero out a region's mask, swap two region colours, collapse the UVs, scramble the bone bind) must turn the corresponding check `pass: false`. A check that cannot be made to fail is not a check.

## Consequences

### Positive
- **"Baked" finally implies "correct".** The four verified failure layers (orphan atlas, degenerate UVs, mis-bind/strip, no-gate) each map to a load-bearing check that fails the build.
- **One report, one source of truth** for all stages; the engine/consumer never has to re-derive trust from renders.
- **ADR-0025's per-region AABBs become real** — emitted, bounded, and gated — instead of proposed-but-absent.
- **Detectors are themselves tested** (mutation harness), so the gate cannot silently rot into always-green.
- Reuses existing channels: the `build_log` warning codes, `ok`, and the batch FLAGGED summary — no new surfacing concept.

### Negative
- Adds bake cost: a rest-vs-moved diff pass, per-region AABB derivation, and the per-commit calibration golden bake.
- The waiver allowlist is a maintenance surface; an over-broad waiver can re-hide a real failure (mitigated: waivers are per-asset, per-code, reason-required, and visible in the report).
- Promoting today's WARNs (`degenerate_uv`, `missing_clip_rest_pose`) to `error` will **fail existing deliveries that currently pass** — intended, but it gates work until those are fixed or waived.
- Screen-space caveat (inherited from ADR-0025): `occlusion` and the AABBs are screen-space; iso depth ignores height (ADR-0018). This report validates *labelling/coverage*, not world-height reconciliation, which stays a consumer concern.

## Alternatives considered
- **Keep the symptom-WARN model, just add more WARNs.** Rejected — the proven failure is precisely that WARNs don't fail the build (`build_log.py:172`); more non-fatal detectors ship the same broken bake greener.
- **One monolithic `ok`/`not-ok` per bake, no per-stage report.** Rejected — loses the diagnosis (which stage, which region, which clip) the FLAGGED summary needs, and can't carry per-check waivers.
- **Validate by eyeballing renders / engine load-test only.** Rejected — not machine-checkable, doesn't scale to batch, and is exactly what let the flat/mis-bound bakes through.
- **Per-stage gates as independent scripts, no aggregated artifact.** Rejected — no single durable record to diff across commits (the build-log discipline), and no shared severity/waiver policy.
- **Trust the oracle (ADR-0030) alone without a mutation harness.** Rejected — an undetected-failing detector is indistinguishable from a passing bake; the harness is what proves each detector has teeth.

## Acceptance criteria (each is a CI-assertable check)

```text
Every production bake writes verification_report.json (schema verification_report_v1) with one entry
  per check: {stage, code, severity, pass, detail}; stages cover MODELING, SKINNING, ANIMATION, HITBOX.
build_log.ok is false whenever any verification entry has severity=error and pass=false; a fixture
  with a forced error-check asserts ok flips false (regression vs today's warn-only behaviour).
MODELING: a glb baked lying down fails `upright`; a front/back-aliased (flat) glb fails
  `frontback_distinct`; a region render leaving an inter-limb hole fails `regions_tile_silhouette`.
SKINNING: a part whose centroid is nearest the wrong bone fails `bound_to_intended_bone` against
  biped_v1.json region_by_bone; an unskinned part fails `all_parts_bound`; a part that does not
  displace between rest and a moved frame fails `bind_deforms`.
ANIMATION: a clip that renders identically to the rest pose fails `clip_not_rest_stuck`; a walk whose
  legs do not move fails `clip_intent`; a loop whose last frame != first fails `loop_seam`; an
  off-vocab clip (move/shoot/hurt) is flagged by `clip_vocab_coverage`; a missing required `death`
  fails coverage for the archetypes that declare it.
HITBOX: a declared region with zero mask pixels fails `declared_regions_present`; a region whose mask
  does not overlap its ADR-0030 calibration colour fails `mask_colour_oracle_aligned`; a frame missing
  per-region AABBs, or an AABB not bounding its region's mask pixels, or an AABB that does not move
  with a moving region, fails `region_aabbs_emitted_and_bound`; an arm-over-torso pixel owned by torso
  fails `occlusion`.
The degenerate-UV (pirate L1) and geometry-only/orphan-atlas (ogre/dragon/ball L0) inputs each produce
  at least one severity=error entry (textured-but-flat / orphan-binding) and ok=false unless waived.
A per-asset waiver for code C downgrades exactly check C for exactly that asset, records a reason, and
  is listed in verification_report.json; it does not affect any other asset or check.
Symmetric props are exempt from frontback_distinct and clip motion checks (assert a prop fixture is
  not failed by them).
The ADR-0030 per-archetype calibration golden is baked in CI on every commit and all its verification
  checks pass (the regression net is green by construction).
A mutation harness mutates one input per case (unbind a part, freeze a clip to rest, zero a region's
  mask, swap two region colours, collapse UVs, mis-bind a bone) and asserts the corresponding check
  flips pass=false; a check with no mutation that fails it is itself a CI failure.
The batch FLAGGED summary lists each variant's failing and waived check codes (bake_batch.py).
```

## Implementer work-list (granular backlog story-ids)

1. **Emit the report.** Add a `verification_report.py` that runs the stage checks against the renderer's `anim_meta.json` + the R8 mask + the ADR-0030 oracle, and writes `verification_report.json`; wire its entries into `build_log.write_build_log` so `ok` consumes load-bearing failures (replaces the warn-only path at `build_log.py:172`). *(Epic-B B5: verify-runner, severity-policy, surface-batch.)*
2. **SKINNING checks.** Make `region_by_bone` (`biped_v1.json`) authoritative for the bind; validate `nearest_bone` against it in/after `rig_from_profile.py:71-84`; add the rest-vs-moved displacement diff. *(Epic-B B2: all-bound, misbind-intended-bone, deform-live, skin-report.)*
3. **ANIMATION checks.** Rest-vs-frame and frame-vs-frame diffs in/after `blender_render_anim.py:206-225`; clip-intent region mapping via `CLIP_SYNONYMS`; loop-seam; vocab coverage incl. the death gap. *(Epic-B B3: dead-clip, intent-oracle, loop-seam, frame-degenerate, vocab-coverage, motion-metrics; b-vocab-death-reconcile.)*
4. **HITBOX checks + AABBs.** Derive per-frame per-region AABBs from the mask and emit them in the manifest (implements ADR-0025); declared-regions-present; colour-oracle/mask alignment; AABB-bounds/track; silhouette coverage gap; region-collapse; occlusion; schema for the region boxes; region-severity wiring. *(Epic-B B4: emit-region-aabbs, declared-regions-present, colour-oracle-mask-alignment, aabb-bounds/tracks, silhouette-coverage-gap, catch-region-collapse, region-severity-wiring, schema-region-boxes, occlusion; b-occlusion-gate.)*
5. **MODELING checks.** Model-metrics/upright (promote `build_log.py:86-123` into the report), front/back distinctness, region-coverage tiling. *(Epic-B B5: model-metrics/upright/frontback/region-coverage.)*
6. **Severity + waivers.** Severity policy table; per-asset, per-code waiver allowlist with recorded reasons; symmetric-prop exemptions.
7. **Regression net.** Bake the ADR-0030 per-archetype golden in CI every commit; build the **mutation harness** with one mutation per check; assert each detector fires.
8. **Surface.** Extend the batch FLAGGED summary (`bake_batch.py:171-189`) to print failing/waived check codes per variant; keep exit non-zero on any unwaived `error` (`bake_batch.py:189`).
