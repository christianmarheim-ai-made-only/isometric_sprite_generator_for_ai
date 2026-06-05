# Production-readiness plan — decision-complete status

Reconciles **what the pipeline has** against **what production-ready needs**, item by item, with an
explicit decision on each: **TAKE-NOW (done this session)** or **DEFER (own file)**. Built from a
parallel multi-track review (animation, atlas/dedup, provenance, hardening, code-review, scaling)
cross-checked against the live tree and the engine contract (ADR-044 +
`../Claude/docs/pipeline/manifest.schema.json`).

**Headline:** the rigged-animation path is architecturally production-ready — the full ADR-044
clip vocabulary is authored, correctly named, playback-correct, and coverage-gated. The blocking
work was **two real correctness bugs** + **measured traceability/constant-drift holes**, all landed
this session. Scale/M2A work is deferred to two decision-complete files. Five questions need the
user.

---

## 1. TAKE-NOW — landed this session

| # | Item | What changed | Gate |
|---|---|---|---|
| **Clips** | Full 9-clip biped vocabulary | `combat_biped_anim.json` + `grunt.asset.json` now declare `idle/walk/crouch_idle/crouch_walk/jump/fall/hit/punch/death` (464 frames, 16 dir). `test_combat_bake` + `test_preview` assert the 9-state set. | `test_combat_bake`: 9 states, **16/16 distinct directions every state** (no 180° aliasing), regions {1,2,3,4}, log clean |
| **B1** | Blender `once`-clips never sampled their terminal/held pose | `blender_render_anim.py`: `denom = nf if loop else nf-1` so the last sprite frame **is** the authored terminal (the held corpse/settle). `blender_bake.py` now threads `playback` into the render spec (was dropped). | `test_combat_bake`, `test_rigged_anim` |
| **B2** | Gate-1 false-accepted `playback:"hold"` | `gate_engine_accept.py` enum → `loop\|once` only (matches the engine + every repo schema). Doc drift in `BEVY_LOADER_INTEGRATION.md` fixed. | `gate1_engine_accept`, `test_gates` |
| **T4** | Atlas size-ceiling contradiction (2048 vs 4096) | One enforced `MAX_PAGE_PX=4096`. `validate_debug_subset` (renamed from `validate_manifest`) uses it + fails gracefully on a paged manifest instead of KeyError-ing (it is the single-page debug-subset validator). `shard_atlas` promotes the oversize **WARN → hard `OversizePageError` + non-zero exit**. | `validate`, shard path |
| **T5** | 4-way magic-number drift (`REGION_COLOR`, ground-band `0.15`, eye `0.9`, `MAX_PAGE_PX`) | New `pipeline/tools/constants.py` is the single source; `bake.py`, the three Blender render scripts, `hitbox_from_mesh.py`, `shard_atlas.py`, `build_log.py` import it. Values byte-identical → references reproduce. | `test_references` (byte-identity), all Blender gates |
| **T6** | "Which hitmask came from which model?" had no spine | `build_log` now hashes output artifacts (`outputs.artifacts.{color,hitmask}_atlas`) + records the real `rig`; `bake_asset` stamps a self-describing `provenance` block into the shipped `manifest.json` (asset/mesh/clips sha, rig, `contract_hash`, `lockfile_hashes`, build-log pointer); `build_index.json` enriched with `batch_id` + `contract_hash` + per-variant build-log pointer + model→hitmask sha link. | `test_combat_bake` (log clean), batch run |
| **T1** | Shipped contract zip was stale (4-clip template) | Regenerated `dist/model_authoring_contract_v1.zip` (41 files) from live `pipeline/examples`. New `test_dist_drift` gate fails CI if the zip ever drifts from a fresh stage again. | `test_dist_drift` |
| **HK** | Housekeeping | gitignore `output/arrow_pilot/frames/`. | — |

**Provenance design note.** `lockfile_hashes` is carried in the manifest **`provenance`** block (via
the production stamp in `bake_asset`), **not** in core `_contract_fields`. This keeps the committed
numpy references (`humanoid_ref`, `humanoid_anim`) byte-reproducible — they bake through core
`bake.py`, which is unchanged — while every **shipped** package is fully traceable. The latent
`validate_manifest:84` lockfile-hash assertion is not reachable in the gates (that validator runs
only on the arrow pilot, which already writes the hashes).

---

## 2. DEFER — own files (decision-complete; a cold session can execute)

| Item | File | Why deferred |
|---|---|---|
| **Frame-dedup + atlas paging + batch throughput** | [`scaling_investigation.md`](scaling_investigation.md) | Engine consumes **single-page** atlases only (TASK-018 deferred). Dedup is a VRAM/scale optimization, not a runtime blocker; turning it on couples to a reference-golden regen. The **spike is done** (measured below) and recorded; implementation waits. |
| **Weapons / gear / equipment (M2A)** | [`m2a_weapons_gear_review.md`](m2a_weapons_gear_review.md) | Every code path is gated on decision **D1** (baked-variants vs runtime-overlay). Contract surface already reserved. Recommendation: baked-variants-first + curated cap. The 3D→2D socket projection is the one D1-independent piece safe to build first. |

### Dedup spike result (measured this session — recorded, not implemented)

| Package | frames | unique | duplicates | recoverable atlas area |
|---|---|---|---|---|
| grunt (full 9-clip) | 464 | 368 | 96 (21%) | ~20% |
| humanoid_anim (3-state) | 128 | 80 | 48 (38%) | ~32% |

**Decision recorded:** dedup runs in the single-page baker **before** `shard_atlas` (cross-state
rest-pose duplicates can't collapse across a per-state page boundary). Joint `(color,region)`
content-hash; only the `(state,direction,frame_index)` address must be unique, not the pixels — so
frames may legally share a rect. Mechanism + exact helper signature + regen cost are in the file.

---

## 3. DECISIONS — parked as ADRs (0020–0023) or resolved

| ID | Question | Status |
|---|---|---|
| **D-canvas** (Task #21) | Lock **256²** as the engine-facing logical frame canvas? | **Parked → ADR-0022** — needs a 30-sec engine sign-off, then bump `manifest_version` + regen `contract_hash`/fixtures atomically |
| **D1** | M2A layering: baked-variants vs runtime-overlay? | **Parked → ADR-0021** (affirms ADR-0011: baked-first + curated cap); gated to the first equipped character |
| **D-metallic** | Metallic/specular sprites (4 sub-decisions) | **Parked → ADR-0020** — baked-static is the v1 path; dynamic-lit is gated on the engine gaining a light rig |
| **D6** | Optional art-direction `world_scale_multiplier`? | **Parked → ADR-0023** — deferred; measured `height_world × 24` is already faithful |
| **D-validate scope** | Rename `validate_manifest.py`? | **DONE** — renamed → `validate_debug_subset.py` (+ function + importers + build step) |
| **D-blender-fixture** | Pin Blender + non-skipping checksum? | **DONE** — `reference/blender_goldens.lock.json` + `test_blender_goldens.py` (non-skipping, warns on local-version mismatch) |

---

## 4. Harden-next (not blocking)

- **Loop-seam + anchor-drift gate** — **DONE** (`test_loop_seam.py`, non-skipping on
  `reference/humanoid_anim`): per `loop` clip, the frame N-1→0 wrap delta must be within 2× the
  largest in-clip step, the per-frame anchor must be constant, and the silhouette centroid must
  stay within 20% of the canvas across the clip. Still open to fold in: the `hit` once-clip
  recoil-then-settle monotonicity check.
- **Reverse provenance index** — `provenance_index.json = {sha: {variant, kind, build_log}}` over
  every input+output sha; pure assembly now that T6 emits output hashes. (Still open.)

---

## 5. Verification

Full gate: `python pipeline/tools/build.py --ci` (**26 steps** incl. the cargo engine load-test and
the Blender bakes; Blender steps skip where Blender is absent, but `test_loop_seam` and
`test_blender_goldens` are **non-skipping** so they verify committed goldens even on a no-Blender
box). Reference byte-reproducibility and Gate-1 acceptance hold across all three committed references
after the constants refactor.
