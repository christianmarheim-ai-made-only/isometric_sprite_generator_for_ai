# Next-phase plan & roadmap status

Single source of truth for what's done, what's next, and the open decisions. Supersedes
`next_slices_plan.md §8` (now history-only). Produced from a 6-track investigation of the repo.

## 1. Where we stand

The pipeline is **contract-complete and green** through R7: `build.py --ci` is a ~20-step gate
covering numpy/OBJ bakes (single + multistate), Blender static + rigged-animated parity, schema
validation, and the cargo engine load-test. Work has landed **beyond** the R1–R7 plan: the rigged
combat-bake path, the external-asset authoring contract + linter + schemas, atlas paging, and the
model-authoring package (`dist/model_authoring_contract_v1.zip`, GO-reviewed).

- **Open in-repo:** only task #21 — `generate_arrow_pilot.py` still emits a debug-subset
  `manifest_version` + a small `frame_canvas` vs the 256² production target.
- **UNBLOCKED (engine ADR-044 landed, Arc 5):** the engine multi-state loader shipped — it plays our
  clips on a real-time frame timer, selected from disclosed entity state. Our multi-state packages
  now animate in-engine (not only in the reference loader). We aligned to it: clip vocabulary
  (`move`→`walk`; `idle/walk/crouch_idle/crouch_walk/jump/fall/hit` play now; `punch`/`death` load and
  play when ADR-040/041 land) and `playback ∈ {loop, once}` (`once` holds the last frame — `hold`
  removed). Still engine-side: R5B tight-crop (needs an engine `logical_frame_canvas` field) and
  atlas paging consumption (TASK-018, deferred — emit single-page for engine playback).
- **Next milestone:** M2A (weapons/equipment). Fully *reserved* in the contract, entirely unbuilt.

## 2. Housekeeping backlog (prioritized)

| # | Item | Why | Effort | Pri |
|---|---|---|---|---|
| H1 | Retire `next_slices_plan.md §8`; this doc is the tracker | stale §8 names a superseded Blender-blocked slice as "next" → mis-targets an autonomous loop | S | high |
| H2 | Close task #21: bump `manifest_version`→`sprite_manifest_v1` + `frame_canvas`→256², regen `contract_hash` + smoke/contract fixtures as one atomic change | only genuinely-open in-repo item; makes output read as production | S | high |
| H3 | **Gate the biped-combat bake** (`grunt.asset.json` + `combat_biped_anim.json`), Blender-skip like R7 | the rigged JSON-clip→biped path has **zero** end-to-end coverage; only the bird is gated → silent regression | S | high |
| H4 | **Gate the textured bake** (`humanoid_textured.glb` through `color_type='TEXTURE'`) asserting it differs from MATERIAL | the real-art texture path is never baked by any gate → silent Blender-shading regression | S | high |
| H5 | **DONE** — atlas ceiling reconciled to one `MAX_PAGE_PX=4096` (`constants.py`); `validate_manifest` uses it + fails gracefully on a `pages` manifest instead of KeyError; `shard_atlas` overflow WARN → hard `OversizePageError` + non-zero exit | real contradiction; oversize atlases emit on a WARN and continue; validate_manifest KeyErrors on a `pages` manifest | M | high |
| H6 | **DONE** — `pipeline/tools/constants.py` (`REGION_RGB`, `GROUND_BAND=0.15`, `EYE_FRACTION=0.9`, `CANVAS/DIRS=256/16`, `PAD=4`, `MAX_PAGE_PX`) imported across `bake.py`, the 3 Blender render scripts, `hitbox_from_mesh.py`, `shard_atlas.py`, `build_log.py`; references reproduce byte-identically | `REGION_COLOR` duplicated ×3; the 0.15/0.9 metric magic numbers appear ×6 as unguarded literals that **must** agree for metric parity | M | med |
| H7 | `manifest_version` enum in `sprite_manifest.schema.json` + a version↔fields↔loader compatibility table | 4 version strings validate as bare strings; the Rust loader hard-requires multistate fields, so a single-state `bake_v1` manifest is undeserializable by the reference loader | S | med |
| H8 | **PARTIAL** — paged-manifest KeyError fixed (graceful error → Gate-1) + 2048 literal dropped for `MAX_PAGE_PX` this session. Remaining: rename → `validate_debug_subset.py` **or** fully generalize = open decision **D-validate** (see `production_readiness_plan.md §3`) | it's wired in only for arrow_pilot yet reads as the system contract | M | med |
| H9 | `docs/state_vocabulary.md`: procedural `idle/walk/attack` (lockfile) vs rigged `idle/move/punch/death` (biped_v1) + which baker emits which | two "canonical" vocabularies; `walk`-vs-`move`/`attack`-vs-`punch` will bite engine state-machine wiring | S | med |
| H10 | **DONE** — `hitbox_from_mesh.py` now imports `GROUND_BAND`/`EYE_FRACTION` from `constants.py` (the same source `bake.py` uses), so metric parity is structural, not by-convention | both name 0.15/0.9 independently; nothing enforces lockstep → silent metric drift | S | med |
| H11 | **DONE** — gitignored `output/arrow_pilot/frames/` | tracked intermediates can go stale vs code | S | low |
| H12 | Pin a Blender version for committed fixtures + non-skipping checksum vs recorded `blender_version` | parity gates SKIP without Blender, so committed Blender fixtures are never re-verified on a no-Blender machine → cross-version drift undetectable | M | low |

## 3. Production logging (per-batch build log)

**Goal:** a durable record per bake so a later-noticed error is troubleshootable and a fix is
*verifiable by diff*. AI-inspectable + human-viewable.

- **`pipeline/tools/build_log.py`** (~120 lines, no new deps): a `BuildLog` recorder with
  `start/end_stage` context managers, `file_sha256`, `git_commit` (cached, tolerant of no-git),
  `packing_efficiency`. Reuses the `validate_manifest` `{checks,warnings,errors}` vocabulary.
- **Two artifacts:** (1) per-bake `output/<variant>/build_log.json` (`sprite_build_log_v1`, sorted
  keys, rounded floats — the diffable record); (2) per-batch `output/<batch>/build_index.json` +
  a one-screen human summary table from `produce_verify_set.py`.
- **Schema** (all fields already computed somewhere): `inputs` (asset + mesh/clip **sha256**),
  `params` (canvas/directions/states/fps/playback/default_state from the manifest), `environment`
  (git commit+dirty, **blender_version**, `contract_hash`, lockfile hashes), `stages[]` (render/pack/
  emit/blender ms), `outputs` (frame_count, atlas/page sizes, **packing_efficiency**), `gates`
  (gate-1 reasons, direction-distinctness, camera-parity worst-err), and **`warnings[]` with an enum
  code**.
- **The key win — surface the two currently-SILENT warnings at their source:**
  `region_fallback_torso` (a mis-named material silently defaults to torso) and
  `missing_clip_rest_pose` (a declared clip absent from the glb silently renders the rest pose).
  These are exactly the "baked green but looks wrong" failures with zero evidence today. The only
  in-Blender change is emitting `region_fallback_count`/`missing_clips` into the `*_meta.json`.
- **Verify-a-fix workflow:** re-bake, `git diff` the two `build_log.json` — a fix flips a gate
  `false→true` or drops a warning code. Keep volatile fields (timestamp, wall_ms) separable.
- **Caveat:** `test_references.py` asserts committed manifest == fresh bake byte-for-byte, so for
  committed reference packages the log must be gitignored (or volatile fields excluded) before it
  becomes a gate.

## 4. Atlas optimization — investigation result

**The shelf packer is already 75–80% efficient** (humanoid_anim 80%, sparrow 75.5%), so a new
MaxRects/guillotine packer is **low value**. The #1 waste is **duplicate frames**: **38–40% of
frames are byte-identical** (humanoid_anim 48/128, sparrow 32/80), caused deterministically by the
procedural posing collapsing walk-zero-crossings / attack-frame-0 / idle to the exact rest pose.

- **Highest value / lowest risk = frame dedup in the baker.** No contract/loader/schema change:
  the contract requires the `(state,direction,frame_index)` **address** be unique, not the pixels —
  two frame entries may legally point at the same `rect`. Color+mask already share one placement,
  so dedup is free for the hitmask. **Expected −32% to −40% atlas area, zero visual/engine change.**
- **Measure first (throwaway spikes, not committed):** Spike 1 — content-hash dedup in
  `bake_character_anim`/`place_into`, report before/after on real packages. Spike 2 — dedup yield
  **single-page vs per-state-paged** (cross-state rest-pose dups can't cross page boundaries, so
  paging reduces yield; this decides dedup-before-shard).
- **Retired dead-ends (proven):** new packer, rotation (ADR-0017 bars it), bilateral-mirror dedup
  (the 45°/30° camera breaks L/R symmetry — verified), shared color+mask layout (already done),
  hitmask bit-depth (already R8). Note the dedup win is **runtime VRAM/texture-region**, not
  download size (PNG already compresses the transparent padding).

## 5. Weapons/gear (M2A) — readiness

**Verdict: a low-risk *extension*, not a rebuild.** The equipment surface is reserved end-to-end
(palette IDs shield 5 / weapon 6 / gear 7, source-schema region enum + sockets, `HIT_`/`SOCKET_`
grammar, `biped_v1` `hand.L/hand.R`, Rust manifest types). **Occlusion is already solved
structurally** — the R8 mask is a single z-buffered topmost-visible-surface pass, so equipment
modeled into the same render gets correct per-direction front/behind ordering **for free**.

- **Only active blockers:** two enforcement points — `lint_source_asset.py`
  `DEFERRED_REGIONS/DEFERRED_SOCKETS`, and the bakers' hardcoded `{none,head,torso,arms,legs}`
  palette.
- **Implementation order (once green-lit):** (1) build the ADR-0013 synthetic placeholder first
  (body + box sword off `hand.R` + plate shield over torso + backpack) as the durable regression
  fixture; (2) flip the two gates + extend the palette to 5/6/7 + add the `HIT_`-proxy/keyword path;
  (3) add **3D socket → 2D projection** (project `hand.*`/`weapon_grip`/`weapon_tip`/`muzzle` world
  positions through the same camera into the per-frame sockets map — today's sockets are facing-only
  aids, this is net-new renderer code); (4) default to ADR-0011 baked variants; (5) defer markers +
  the second body-damage mask.

See §7 for the design decisions that gate M2A.

## 6. Model previewer — recommended V1

**A headless-Blender "source preview sheet", not a web viewer** (reuses the parity-trusted Blender
path, zero deps, emits AI-readable PNGs+JSON, leaves the locked iso render untouched). The previewer
*inverts* the iso renderer: fix the object, use a few **free non-iso** angles.

- **`pipeline/tools/blender_preview.py`** (in Blender): reuses `blender_render`'s import+normalize +
  material/region maps verbatim; per stage at a few labelled diagnostic angles emits
  `mesh_<angle>.png` (flat silhouette/topology), `tex_<angle>.png` (texture sanity),
  **`region_<angle>.png`** (flat region pass — the cheapest, highest-value check: catches mis-named
  materials *before* they bake into a wrong hitmask), and for rigged assets `bind_*` +
  `<clip>_k{0,mid,last}_*` (rig/key-pose sanity). Plus `preview_meta.json` (angles, has_tex,
  material→region map, unmatched-material warnings) so an AI reads what was shown.
- **`pipeline/tools/preview_source.py`** (CPython): takes a `*.asset.json`, runs the above,
  composites one labelled `source_preview.png` (rows = mesh / texture / rig+key-poses / region) ×
  (cols = angles), and **appends the baked contact sheet as the final "sprite" row**.
- **Use:** the first thing to open when a sprite looks wrong — walk mesh → texture → rig → region →
  sprite to localize the failing stage (model vs texture vs rig vs anim vs conversion). Wire its
  INDEX into the verify_set ledger next to `build_index.json`. Defer an interactive
  three.js/`<model-viewer>` orbit to a human-only v2 fed by the same normalized glb.

## 7. Recommended sequence

1. **H1** — retire §8, this doc is the tracker.
2. **build_log.py** + surface the two silent warnings — the substrate every later fix-verification leans on.
3. **H2** — close task #21 (version + canvas) atomically.
4. **H3 + H4** — the two silent-regression gates (biped-combat bake, textured bake).
5. **Atlas dedup spikes** (measure), then implement dedup only — no new packer.
6. **H5** — reconcile the atlas ceiling + add a `shard_atlas` gate.
7. **H6 + H10** — shared constants module + hitbox parity gate.
8. **Model previewer v1** (`blender_preview.py` + `preview_source.py`), wired into the ledger.
9. **M2A scope decision** on §7's questions (runtime-layering fork first) → then the ADR-0013 placeholder + gate flips.

## 8. Open decisions (need your call)

- **D1 — Runtime-layering fork (gates ALL of M2A):** baked variants (one package per body+gear
  combo — cheapest, reuses single-render occlusion, but variant explosion needs a curated cap) **vs**
  a runtime equipment-overlay (separate atlas + synced hardpoints + per-direction z-order flags)?
- **D2 — `frame_canvas` target:** confirm 256² is the engine-facing logical canvas and that bumping
  it only needs a `contract_hash` regen (not a fixture rewrite beyond arrow-pilot smoke).
- **D3 — Engine coordination (external):** ✅ multi-state loader LANDED (ADR-044) — packages play
  in-engine. STILL OPEN: will the engine add a `logical_frame_canvas` field to unblock R5B tight-crop
  (else engine-consumed frames stay full-canvas), and TASK-018 atlas paging consumption (deferred —
  single-page only for engine playback today)?
- **D4 — Mask semantics (ADR-0006):** when gear covers the torso, accept no-damage-there (single
  topmost mask), emit a **second body-damage mask**, or per-region passthrough engine-side?
- **D5 — `manifest_version` convergence:** collapse the 4 strings into one schema with optional
  multistate fields (+ a single-state path in the Rust loader), or keep them distinct? (Today a
  single-state `bake_v1` manifest appears undeserializable by the reference loader — confirm
  intentional vs latent.)
- **D6 — Per-variant scale (ADR-0018 open):** does `height_world × 24` need a per-variant multiplier
  for large/small creatures before an M4 roster?
- **D7 — Golden-fixture policy:** are `output/verify_set` + `reference/` Blender packages
  authoritative goldens (→ Blender pin + non-skipping checksum) or convenience samples (→ trim from
  git, gitignore regenerable frames)?
