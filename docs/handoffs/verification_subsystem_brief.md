# Handoff: Verification subsystem (Epic B — per-bake detection + cross-stage verified-applied)

- For: the verification-subsystem implementation chat.
- Parent: [`../arcs/ARC-0001-textured-verified-skinned-models.md`](../arcs/ARC-0001-textured-verified-skinned-models.md).
- Implements: **ADR-0030** (calibration model + oracle) and **ADR-0031** (per-bake cross-stage verification report); consumes **ADR-0025** (per-region AABBs — this epic finally implements them) and **ADR-0028** (the texture-fidelity stage).
- Goal: every bake **proves** each stage was *applied* — modeling, skinning, animation, hitboxes — or fails. A deliberately-broken bake turns red; the calibration golden stays green every commit.

Read ARC §5 (the calibration keystone) and ADR-0030/0031 first. This brief is the ordered backlog. **Build the fixture + oracle first; every downstream stage asserts against it.**

---

## Design locks (from ADR-0030 — do not re-litigate)
- **Separate `CALIB_RGB`** palette = one distinct, maximally-separated colour **per deformable bone** (L/R hues far apart), painted into the **color pass only**. The canonical 4-id `REGION_RGB` *cannot* tell left-arm from right-arm — exactly the discrimination mis-skin detection needs.
- The **region/R8 pass stays canonical `REGION_RGB`** → hitmask + manifest + engine contract byte-unchanged; the two passes cross-check each other.
- **One calibration fixture PER ARCHETYPE** (biped/bird/quadruped/dragon/ball). One model can't exercise every skeleton.
- AA tolerance: classify by **colour-distance buckets**, not exact match; separation measured against the **alpha-key/transparent** bake background (critic C4 — *not* `PREVIEW_BG_RGB`, which is preview-only).
- Symmetric props (ball/orb) are **exempt** from front≠back / motion oracles.
- A **mutation harness** must prove every detector fires (non-vacuity), else the green golden is meaningless.

---

## B1 — calibration fixture + region↔color oracle (the spine) — ADR-0030

| id | what | touchpoint |
|---|---|---|
| `b1-calib-palette` | `CALIB_RGB: {bone→rgb}` + `CALIB_PART_REGION: {bone→region_id}` + pure helpers `calib_part_for_color`/`calib_region_for_color`; assert min pairwise distance ≥ floor; round-trip | `constants.py` (next to `REGION_RGB`); `rig_profiles/biped_v1.json` bone set |
| `b1-fixture-glb` + `b-calib-archetype-coverage` | `gen_calibration_fixture.py` — per-bone-skinned body, each bone its own region-keyworded material = `CALIB_RGB[bone]`; **one fixture per archetype** | model on `gen_biped_fixture.py` |
| `b1-dual-pass` | color pass paints `CALIB_RGB`; region pass stays `REGION_RGB` (golden-compare the mask is byte-unchanged) | `blender_render_anim.py:206-221` |
| `b1-oracle-core` | `calib_oracle.py` — read baked frames (pre-pack PNGs or post-pack via manifest) → which known colour is where | `make_contact_sheet.py` reconstruct pattern |
| `b1-aa-tolerance` | colour-distance buckets; survive STUDIO/AA + the nearest-colour `_region_ids` bucket | `blender_bake.py:73-88` |
| `b1-silhouette-band` | each region's known colour sits in its expected vertical band | — |
| `b1-plausibility` | each part's known colour present with a sane pixel area | — |
| `b1-commit-reference` | commit fixture + reference oracle readout as **byte-stable goldens** | `pipeline/reference/` |
| `b1-oracle-self-test` + `b-mutation-harness` | deliberately mis-bind a limb / kill a clip / swap a colour ⇒ oracle FIRES | new `test_calib_mutation.py` |
| `b1-oracle-report` | surface oracle readout in `build_log` codes + batch summary | `build_log.py`, `bake_batch.py` |
| `b-oracle-determinism` | stable across machines/Blender versions (tolerance + quantize) | — |
| `b-oracle-perf-budget` | per-frame oracle read within a stated budget (don't slow every bake) | — |

---

## B2 — skinning verified-applied — ADR-0031
*The auto-rig binds each part 100% to its **nearest bone by centroid** with **no validation** (`rig_from_profile.py:67-84`) — the named mis-skin failure.*

| id | what | severity |
|---|---|---|
| `b2-all-bound` | every part-mesh is bound — **no static/unskinned part** | error |
| `b2-collapsed-part` | detect parts collapsed to origin / zero bind area | error |
| `b2-misbind-intended-bone` | catch nearest-bone mis-bind against the intended bone via the profile's `region_by_bone` | error |
| `b2-deform-live` | the bind **deforms** — a part's `CALIB` colour block displaces between rest and a moved frame | error |
| `b2-autorig-wrong` | detect the "auto_rigged but bound wrong" case | warn→error |
| `b2-skin-report-code/surface/verify` | skin warning codes in `build_log`; surface the `rig_from_profile` skin report on **success** (today discarded); add to verify-set/contact-sheet | — |

---

## B3 — animation verified-applied — ADR-0031

| id | what | severity |
|---|---|---|
| `anim-motion-metrics` | emit per-region per-frame motion metrics from the animation render pass | — |
| `anim-dead-clip` | fail a clip whose frames are identical to its rest pose (`missing_clip_rest_pose` is adjacent) | error |
| `anim-intent-oracle` | the **right** region moved for the clip's intent (walk/run→legs, attack→arms, idle→small) via the colour oracle | error |
| `anim-bone-applied` | each declared moving bone actually displaced its skinned part (skin/anim cross-check) | error |
| `anim-loop-seam-perbake` | loop continuity (last≈first) for every looping clip, every bake | error |
| `anim-frame-degenerate` | flag per-frame zero/duplicate motion within a multi-frame clip | warn |
| `anim-hitbox-colour-xcheck` | the per-region mask overlaps the `CALIB` colour blocks (skin↔hitbox cross-check) | error |
| `anim-vocab-coverage` + `b-vocab-death-reconcile` | clip-vocab presence/coverage; **resolve the `death` gap** — add it to `ENGINE_CLIP_VOCAB` or stop gating it (ARC PREREQ; today `death` is only a synonym target) | gate |

---

## B4 — hitbox / region-mask verified-applied — ADR-0031 (implements ADR-0025)

| id | what | severity |
|---|---|---|
| `emit-region-aabbs` | derive per-region screen-space AABBs **from** the R8 mask, per frame → manifest (**this implements ADR-0025**) | — |
| `declared-regions-present` | the R8 mask is non-empty for every **declared** region | error |
| `colour-oracle-mask-alignment` | mask region R **overlaps** R's known `CALIB` colour pixels (mask↔silhouette proof) | error |
| `aabb-bounds-its-region` + `aabb-tracks-motion` | each AABB bounds exactly its region's pixels **and** tracks the limb across animation frames | error |
| `silhouette-coverage-gap` | regions **tile** the body — no large unclassified holes (ADR-0028 partition-no-gaps) | error |
| `catch-region-collapse` | everything → one region (region_fallback_torso writ large) = **BLOCKING** | error |
| `region-severity-wiring` | promote `ok=false` to include region-class severities | — |
| `schema-region-boxes` | manifest schema permits + requires per-frame per-region AABBs | `test_schemas.py` |
| `contact-sheet-region-overlay` | colour-pass vs mask side-by-side for human verify | `make_contact_sheet.py` |
| `region-decode-ambiguity-guard` | flag ambiguous / non-palette region-pass pixels in `_region_ids` | `blender_bake.py:73-88` |
| `b-occlusion-gate` | nearest part owns the pixel (arm-over-torso) — the roadmap occlusion gap | error |
| `hit-verify-ci-suite` | CI drives the full B4 suite over the calibration fixture + a known-bad fixture | CI |

---

## B5 — modeling checks + the unified harness + CI — ADR-0031

| id | what | severity |
|---|---|---|
| `model-metrics` | scale / world-metrics (already error-gating) → promote into the unified report; **pin the `±25%` tolerance to the actual constant** (critic) | error |
| `model-upright` | upright/orientation as a first-class per-bake detector | error |
| `model-frontback` | front≠back aliasing == heading N ≠ N+8, as a **numeric** per-bake detector (cite `test_direction_distinctness.py`) | error |
| `model-region-coverage` | regions cover the silhouette (no body pixel region-0, no inter-limb gaps) | error |
| `verify-runner` | one structured `verification_report.json` per bake aggregating MODELING/SKINNING/ANIMATION/HITBOX + evidence | — |
| `severity-policy` | load-bearing checks flip `build_log.ok=false`; per-asset waiver allowlist; symmetric-prop exemption | `build_log.py:172` |
| `surface-batch` | surface results in `build_log` codes + the batch FLAGGED summary | `bake_batch.py` |
| `ci-calibration-golden` | bake the per-archetype calibration fixture **every commit** and assert the full skin+anim+hitbox chain (the regression net) | CI |
| `b-epic` | compose the calibration fixture with Epic-A auto-rig texture/UV preservation (shared fixture, no duplication) | — |

**Done:** the calibration fixtures (per archetype) bake green every commit; the mutation harness shows each detector fires; a `verification_report.json` is emitted with severities driving `ok`; ADR-0025's per-region AABBs are live and gated.
