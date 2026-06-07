# ADR-0030: Color-coded calibration model + region-color oracle (the e2e visual-regression basis)

- Status: **Proposed**
- Date: 2026-06-07
- Blocks: ADR-0031 (the skinning/animation/hitbox applied-verification report is built directly on this oracle); the "no automated e2e visual regression" gap on the hardening roadmap
- Related: ADR-0031 (the per-archetype verification report that *consumes* this oracle); ADR-0025 (the R8 region mask + per-region AABBs — the **other** pass this cross-checks); ADR-0006 (topmost-surface region-mask semantics); `REGION_RGB` / `region_for_name` in `pipeline/tools/constants.py:31-61`; the auto-rig story L2 (`rig_from_profile.py` flat-recolor + UV-strip) and the L4 "no gate" finding from the textured-delivery investigation. Grounding read: `pipeline/tools/gen_biped_fixture.py`, `pipeline/tools/blender_bake.py:73-88` (`_region_ids`), `pipeline/tools/blender_render_anim.py:206-225` (two-pass recolor + per-frame PNG emit), `pipeline/tools/make_contact_sheet.py`, `pipeline/schema/rig_profiles/biped_v1.json`.

## Context

The textured-delivery investigation proved the pipeline can **ship a bake that looks plausible but is structurally wrong, green-lit.** Four root-cause layers were verified by parsing the glbs and reading the atlases:

- **L0 — geometry-only + orphan atlas.** ogre/dragon/red_ball glbs carry 0 materials/textures/images and **zero UVs** (no `TEXCOORD_0`); their `*_texture_atlas.png` are sidecars bound to nothing.
- **L1 — degenerate UVs.** pirate_v2 binds 19 region materials to 1 embedded atlas, but every primitive's UVs collapse to a **single texel** (the centre of a swatch-grid tile) — one flat colour per part via a texture hack.
- **L2 — the auto-rigger erases input.** `rig_from_profile.py` **replaces** every part material with a flat per-region colour, **strips UVs/vertex-colours**, never reads the texture, and crashes on the pirate dict-shaped `materials.json`.
- **L4 — no gate.** `degenerate_uv` is a non-aborting WARN; `build_log.ok` only flips false on `severity=error`. So a textured-but-flat bake ships **green.**

The deeper problem under all four: **nothing in CI looks at the baked pixels and asserts the right thing is in the right place.** The region/R8 pass (ADR-0025, ADR-0006) checks *gameplay regions* — but it has only **4 ids** (`REGION_RGB`, `constants.py:31-36`), so an arm baked where a leg should be, or left/right limbs swapped, or a whole limb un-deformed by a clip, are all **invisible to it**: both limbs are `arms`, both legs are `legs`. The color pass, meanwhile, is checked by **eye** via contact sheets (`make_contact_sheet.py`) — not by machine.

We have the raw material for an automated check already in-tree:
- A **per-bone-skinned biped fixture** exists (`gen_biped_fixture.py`) — boxes, each box skinned 100% to one `biped_v1` bone, each tagged with a region material. It is the exact shape to model a calibration model on.
- The render path **already emits per-frame PNGs** for both passes (`blender_render_anim.py:206-225` `render_all`) and runs **color first, then recolors materials to region ids and re-renders** — a clean two-pass seam.
- The region decode is a **nearest-colour bucket** (`_region_ids`, `blender_bake.py:73-88`), anti-aliasing-tolerant by construction.

The missing piece is a **known-answer fixture**: a model where *every deformable part is a distinct, separable colour*, plus an **oracle** that reads the baked frames and asserts each part's colour is present, in the right place, at a plausible size — the automated e2e visual-regression substrate ADR-0031 needs.

## Decision

Adopt a canonical **color-coded calibration model** and a **region-color oracle**, as a dual-pass known-answer fixture committed with byte-stable goldens.

### D1 — A new `CALIB_RGB` palette, one maximally-separated colour per deformable bone

Add a palette `CALIB_RGB` to `constants.py`: a map **bone-name → RGB**, one entry per deformable bone of each rig archetype, with colours **maximally separated in RGB** and **L/R hues kept far apart** (e.g. `arm.L` warm / `arm.R` cool) so a left/right limb swap is detectable, not aliased. `CALIB_RGB` is a pure literal in the same dependency-free module as `REGION_RGB`, importable from both host CPython and Blender (the `constants.py` contract).

Constraints, machine-checkable:
- **Pairwise minimum distance.** For every pair of calib colours, squared RGB distance ≥ a fixed `CALIB_MIN_DIST2` chosen so that **no calib colour ever buckets to the wrong bone** under the `_region_ids`-style nearest-colour decode after 8× AA (`render_aa='8'`).
- **Disjoint from `REGION_RGB` is NOT required** (different pass), but **disjoint from background** (`PREVIEW_BG_RGB`, transparent) IS — every calib colour must be > `CALIB_MIN_DIST2` from `(0,0,0)`/bg so alpha-thresholding cannot eat a part.
- One colour **per deformable bone**, not per region — this is the whole point: `arm.L` and `arm.R` are different colours though both are region `arms`.

### D2 — `CALIB_RGB` is painted into the COLOR pass ONLY; the REGION/R8 pass is byte-unchanged

The calibration colours are applied **only** in the color render pass. The second pass still recolors materials to the canonical 4-id `REGION_RGB` and re-renders exactly as today (`blender_render_anim.py:218-225`). Therefore:
- the **hitmask atlas, the manifest region palette, and the engine contract are BYTE-UNCHANGED** — the engine consumes the same 4-id R8 mask it always did;
- the **two passes cross-check each other**: a calib part of colour `C_bone` (color pass) must fall inside the silhouette of its region id `R(bone)` (region pass). `region_by_bone` (`biped_v1.json:24-31`) gives the bone→region map for that cross-check.

This is a **fixture-only authoring path**: real deliveries are untouched; the calib colours live on the calibration fixtures alone.

### D3 — A `calib_oracle.py` reads baked frames and asserts known colours by distance bucket

`calib_oracle.py` ingests the baked color frames **either** pre-pack (per-frame PNGs from `render_all`) **or** post-pack (crop each frame out of `color_atlas.png` via the manifest `rect`/`trim`, the same reconstruction `make_contact_sheet.py:_reconstruct_color` already does). For each declared `(state, frame, direction)` it asserts, **per expected part**:

1. **PRESENCE** — the part's known colour is present: ≥ `MIN_PART_PIXELS` pixels fall in `C_bone`'s colour bucket (squared-distance ≤ `CALIB_BUCKET2`, **not** exact match — AA-tolerant, mirroring `_region_ids`).
2. **SILHOUETTE BAND** — the part's pixel centroid lies inside its **expected screen band** for that direction (e.g. head in the upper band, feet in the lower; left/right limbs on the expected screen side for front-facing directions). Bands are authored per archetype as fractional canvas boxes and stored in the golden.
3. **PLAUSIBLE COVERAGE** — the part's pixel count sits within `[lo, hi]` of its golden coverage for that frame (catches a collapsed/exploded/missing limb), with tolerance for AA and pose.

All thresholds are **named constants**, all comparisons are **bucketed by colour distance**, never exact RGB equality.

### D4 — Commit the fixture + a reference oracle readout as versioned, byte-stable goldens

Per archetype, commit: the calibration **fixture glb** (or its deterministic generator + a checksum, following the Blender-golden pin already in CI), and a **reference oracle readout** — the per-`(state,frame,direction)` per-part {present, centroid-band, coverage} record the oracle produces on a known-good bake. CI re-runs the oracle and asserts the readout **matches the golden within tolerance**, and that the readout is **byte-stable across two runs** (determinism).

### D5 — A NEGATIVE / mutation harness proves the oracle FIRES

Ship a mutation harness that takes a calibration fixture and applies deliberate defects, then asserts the oracle **fails** on each:
- **mis-bind a limb** (skin `arm.L`'s verts to `arm.R`'s bone) → silhouette-band assertion fires;
- **kill a clip** (drop a deforming clip so a limb never moves) → coverage/centroid drift across frames fires;
- **swap a colour** (paint `arm.L` with `arm.R`'s calib colour) → presence/side assertion fires.
A green oracle on a mutated fixture is itself a CI **failure** (the oracle must be proven non-vacuous).

### D6 — One calibration fixture PER RIG ARCHETYPE; symmetric props are exempt from directional/motion oracles

One model cannot exercise all skeletons. Provide **one calibration fixture per rig archetype**: biped, bird, quadruped, dragon, ball. Each exercises its own bone set. **Symmetric props (ball)** have no front/back and no deforming limbs, so the ball fixture is **exempt** from the silhouette-band (front-vs-back) and motion/coverage-drift oracles; it runs only presence + total-coverage.

## Consequences

### Positive
- The pipeline gains its **first automated e2e visual check on baked pixels** — the L2/L4 failures (auto-rig flattening, no-gate flat bake) become **red in CI**, where today they ship green.
- **Zero engine-contract impact**: the R8/region pass and manifest palette are byte-unchanged (D2); the calib colours never touch a real delivery.
- The **two passes cross-check** (calib-color ↔ region-id), turning a previously by-eye contact-sheet review (`make_contact_sheet.py`) into a machine assertion.
- Distinct per-bone colours catch failures the 4-id region pass **structurally cannot**: L/R swaps, single-limb mis-binds, a limb that never deforms.
- The mutation harness (D5) guarantees the oracle is **non-vacuous** — it can never silently rot into an always-green no-op.
- Reuses existing machinery: the per-bone-skinned fixture (`gen_biped_fixture.py`), the two-pass render (`blender_render_anim.py`), the nearest-colour bucket (`_region_ids`), the frame reconstruction (`make_contact_sheet.py`).

### Negative
- **N fixtures to build and maintain** (one per archetype) plus their goldens; archetype skeletons that don't exist yet (bird) gate their fixture.
- The calib **color authoring path diverges from real deliveries** — it must be kept fixture-only and explicitly tagged, or it risks leaking a non-shippable palette into a real bake.
- Silhouette-band thresholds are **pose- and direction-sensitive**; bands and coverage ranges need tolerance tuning, and a re-tuned golden is a reviewable diff.
- Adds CI runtime (an extra bake + oracle per archetype + the mutation runs).

## Alternatives considered

- **Extend `REGION_RGB` to per-bone ids instead of a separate palette.** *Rejected* — it would change the R8 mask, the manifest palette, and the engine contract (ADR-0025/0006), which are LOCKED at 4 ids. The whole value of D2 is that the calib colours live in the **color** pass and leave the contract byte-unchanged.
- **Keep verifying by eye via contact sheets.** *Rejected* — `make_contact_sheet.py` is a human aid; it caught nothing in the textured-delivery failures because no human gate is in CI. The oracle reuses its reconstruction but makes the assertion automatic.
- **Exact-RGB-match oracle.** *Rejected* — 8× AA and Workbench shading perturb edge pixels; exact match would false-fail constantly. Colour-distance buckets (mirroring `_region_ids`, `blender_bake.py:73-88`) are AA-tolerant by design.
- **One universal calibration model for all rigs.** *Rejected* — a single skeleton cannot exercise biped + bird + quadruped + dragon + ball bone sets (D6). Per-archetype fixtures are mandatory; the ball's exemptions fall out of its symmetry.
- **Trust a non-aborting WARN to flag flat bakes (status quo).** *Rejected* — that is exactly the L4 gap: `degenerate_uv` WARNs, `build_log.ok` stays true, and the bad bake ships green.

## Acceptance criteria (each assertable by a CI test)

```text
PALETTE
  A1  CALIB_RGB exists in constants.py as a pure literal; importable under host CPython
      AND Blender's interpreter (no numpy/PIL/bpy import at module load).
  A2  Every pair of CALIB_RGB colours has squared RGB distance >= CALIB_MIN_DIST2.
  A3  Each L/R bone pair (arm.L/arm.R, thigh.L/thigh.R, ...) has distinct, far-apart hues
      (pair distance >= CALIB_MIN_DIST2, asserted explicitly for every L/R pair).
  A4  Every CALIB_RGB colour is > CALIB_MIN_DIST2 from background/transparent so alpha-thresholding
      cannot delete a part.
  A5  CALIB_RGB has exactly one entry per deformable bone of its archetype's rig profile
      (key set == rig profile deformable-bone set; no extras, no omissions).

CONTRACT INVARIANCE
  A6  A calibration bake's hitmask_atlas.png and manifest region palette are BYTE-IDENTICAL to a
      bake of the same fixture with the canonical REGION_RGB color pass (calib touches color pass only).
  A7  For every part, its calib-colour pixels (color pass) fall inside the silhouette of its region id
      R(bone) (region pass), per region_by_bone -- the two passes agree.

ORACLE CORE
  A8  calib_oracle.py runs on both pre-pack per-frame PNGs and post-pack manifest crops and
      produces the SAME per-part readout for both ingestion paths.
  A9  Presence: for each expected part in each (state,frame,direction), >= MIN_PART_PIXELS pixels
      bucket to C_bone (distance <= CALIB_BUCKET2); exact RGB match is never required.
  A10 Silhouette band: each part's centroid lies in its expected fractional-canvas band for that
      direction (L/R parts on the expected screen side for front directions).
  A11 Plausible coverage: each part's pixel count is within its golden [lo,hi] for that frame.

GOLDENS / DETERMINISM
  A12 A committed reference oracle readout exists per archetype; CI reproduces it within tolerance.
  A13 Two consecutive oracle runs on the same bake produce a BYTE-IDENTICAL readout (determinism).

MUTATION (oracle must fire)
  A14 Mis-binding a limb to the wrong bone makes the oracle FAIL (band/side assertion).
  A15 Killing a deforming clip makes the oracle FAIL (coverage/centroid-drift assertion).
  A16 Swapping a part's calib colour makes the oracle FAIL (presence/side assertion).
  A17 A green oracle result on ANY mutated fixture is itself a CI failure (non-vacuity guard).

ARCHETYPE COVERAGE / EXEMPTIONS
  A18 Exactly one calibration fixture per supported rig archetype (biped/bird/quadruped/dragon/ball),
      each committed as a glb or a deterministic generator + checksum.
  A19 The ball (symmetric prop) fixture is exempt from front-vs-back silhouette-band and
      motion/coverage-drift oracles; it asserts presence + total coverage only, and CI records the
      exemption rather than silently skipping.
```

## Implementer work-list

Granular backlog stories consolidated by this ADR (Epic-B):

1. **`b1-calib-palette`** — add `CALIB_RGB` + `CALIB_MIN_DIST2`/`CALIB_BUCKET2`/`MIN_PART_PIXELS` to `constants.py` as pure literals (A1–A5); unit-test pairwise + L/R + bg distances.
2. **`b1-fixture-glb`** — generalize `gen_biped_fixture.py` into a calibration-fixture generator that paints `CALIB_RGB` per bone in the color pass; produce the biped calib fixture first (A18).
3. **`b1-dual-pass`** — wire the color pass to use `CALIB_RGB` for calib fixtures while the region pass still recolors to `REGION_RGB` (`blender_render_anim.py:218-225`); assert contract invariance (A6, A7).
4. **`b1-oracle-core`** — write `calib_oracle.py` with both ingestion paths (per-frame PNG; manifest crop reusing `make_contact_sheet.py` reconstruction) (A8).
5. **`b1-aa-tolerance`** — implement the colour-distance bucket decode (mirror `_region_ids`, `blender_bake.py:73-88`); presence by bucket, never exact match (A9).
6. **`b1-silhouette-band`** — per-archetype fractional-canvas band tables + the centroid-in-band + L/R-side check (A10).
7. **`b1-plausibility`** — golden per-part coverage `[lo,hi]` ranges + the coverage assertion (A11).
8. **`b1-commit-reference`** — commit fixtures (glb or generator+checksum) and reference oracle readouts as goldens (A12, A18).
9. **`b1-oracle-self-test`** + **`b-mutation-harness`** — the mis-bind / kill-clip / swap-colour mutators and the non-vacuity guard (A14–A17).
10. **`b1-oracle-report`** — a human-readable oracle report (pass/fail per part per frame) alongside the machine readout, for review parity with the contact sheets.
11. **`b-oracle-determinism`** — the two-run byte-identical readout test (A13).
12. **`b-calib-archetype-coverage`** — extend fixtures + palettes + bands to bird/quadruped/dragon/ball; gate archetypes whose skeleton does not yet exist (A18).
13. **`b-symmetric-prop-exemption`** — encode and CI-record the ball's exemption from directional/motion oracles (A19).

This oracle is the automated e2e visual-regression substrate; **ADR-0031** (skinning/animation/hitbox applied-verification) is built directly on top of it.
