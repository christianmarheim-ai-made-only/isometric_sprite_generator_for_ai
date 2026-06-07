# ADR-0028: A textured delivery that bakes flat is a blocking failure (fidelity gates + severity)

- Status: Proposed
- Date: 2026-06-07
- Blocks: trusting any `textured`-declared delivery (today a textured-but-flat bake ships green-lit); the
  pipeline-hardening "textured fidelity" line item
- Related: ADR-0026 (`texture_mode` — this ADR defines the *gate* that makes the `textured` value mean
  something), ADR-0027 (UV/material preservation — supplies the inputs this gate inspects), ADR-0024
  (the build-log detector pattern this extends), ADR-0025 (per-region mask derived from one render pass —
  the same "one pass, two render paths must agree" parity concern), ADR-0031 (the per-bake verification
  report this fidelity verdict feeds into); engine consumes only `color_atlas.png` + R8 hitmask +
  `manifest.json` and is texture-capable but only as good as its input. Grounding:
  `pipeline/tools/build_log.py` (severity model + how `ok` is computed, ~140–172, `stamp_provenance`),
  `pipeline/tools/blender_render_anim.py:85–100` (`has_tex` + `degenerate_uv` detect),
  `pipeline/tools/blender_render.py:78–79,182` (`has_tex` ONLY — no degenerate detect),
  `pipeline/tools/intake_package.py` (`lint_package`, `textures.base_color` synthesis),
  `pipeline/tools/bake_batch.py` (FLAGGED summary + exit code).

## Context

A producer can deliver an asset that *declares* it is textured — it ships a `*_texture_atlas.png` and a
glb with texture-bound materials — and the pipeline will bake it **green** while every body part renders
a single flat colour. The detailed painted look the delivery implies never reaches a pixel, and **nothing
fails**. This is the worst failure class we have: a *silent* fidelity collapse that passes every existing
gate and ships.

### The verified gap (ground truth — parsed from the glbs + read from the atlases)

Four shapes of the same root failure, plus the known-good baseline:

- **L0 — geometry-only + orphan atlas** (`ogre`, `dragon`, `red_ball`): the glbs carry **0 materials, 0
  textures, 0 images, and ZERO UVs** (no `TEXCOORD_0`) on every part. Their `*_texture_atlas.png` are
  **orphan sidecars bound to nothing**. `materials.json` is a few flat per-region `base_color`s.
- **L1 — degenerate UVs** (`pirate_v2`): 1 mesh, 19 region-keyworded materials, **all 19 carry
  `baseColorTexture` bound to one embedded atlas** — but all 37 primitives have **degenerate UVs collapsed
  to a single point** (each pinned to the centre of its swatch-grid tile). Each material samples exactly
  **one texel** → one flat colour per part. A "flat colour via texture" hack that is textured on paper and
  flat in the frame.
- **Known-good baseline** (`humanoid_textured.glb`): 1 mesh, 4 region materials, `baseColorTexture` bound,
  **UVs spanning area 0.40–0.92** (a real unwrap). This is the shape a correct textured delivery must
  match, and the shape `test_texture_pass.py` already asserts against.
- The committed `*_texture_atlas.png` are **flat placeholders** (pirate = labelled swatch grid; dragon/ogre
  = noise/tiling fills), not painted art. Detailed painted atlases exist but are (a) not bound into any glb
  and (b) unusable because the models have no real UVs.

### Why it ships green today (the four enabling layers)

- **L2 — the auto-rig strips fidelity.** `rig_from_profile.py` **replaces every part material with a flat
  per-region colour, strips UVs / vertex-colours, and never reads the texture** (and crashes on the
  pirate's dict-shaped `materials.json`). So even a delivery that *did* have a real unwrap can be flattened
  upstream of the renderer.
- **L3 — render is texture-capable but only as good as its input.** The Workbench color pass selects
  `TEXTURE` iff `has_tex` (`blender_render.py:147`, `blender_render_anim.py:214`). Given degenerate UVs or
  an orphan atlas it faithfully renders the flat result. Render is not the bug; the input is.
- **L4 — no gate, wrong severity.** `degenerate_uv` is emitted as a **non-aborting `severity: "warn"`**
  (`build_log.py:141`). `ok` flips false **only** on `severity == "error"` (`build_log.py:172`,
  `gate1_ok and not any(w["severity"] == "error" ...)`). `bake_batch` exits non-zero only when a bake
  fails, an intake fails, or some log is `not ok` (`bake_batch.py:189`). So a textured-but-flat bake is
  `ok: true`, lands in **FLAGGED (baked, but review)** at worst, and the batch exits **0**.
- **Render-path drift.** `blender_render_anim.py` detects `degenerate_uv_materials` **and**
  `base_color_linked_materials` (lines 89–100, 107–138; emitted in meta at 234–235). `blender_render.py`
  detects **`has_tex` only** (lines 78–79, emitted at 182) — **no degenerate-UV detection at all**. The same
  delivery therefore produces different diagnostics depending on whether it took the animated or the static
  path. A flat pirate that happens to bake through the static path emits *no* degenerate signal whatsoever.

The net: a textured *claim* is unverified. There is no single place that asks "did this textured delivery
actually bake with texture detail?" and refuses to ship when the answer is no.

`flat_region` deliveries (ogre/dragon as they stand) are **legitimate** — a flat per-region look is their
declared intent. The bug is **only** the mismatch between a `textured` *claim* and a flat *result*. Any
fix must preserve flat-region behaviour untouched.

## Decision

Introduce **one shared fidelity detector** and **one blocking gate**, wired so a textured-but-flat bake
fails loudly at both the intake door and the build log, and so the static and animated render paths emit
**identical** texture diagnostics.

### 1. One shared fidelity detector (kill the render-path drift)

Factor the texture-fidelity probe into a single function (e.g. `mesh_io.texture_fidelity(obj)` or a shared
helper imported by both renderers) that returns one diagnostic dict from one inspection of the imported
mesh:

```text
{ has_tex: bool,                       # any material binds a non-null TEX_IMAGE  (existing logic)
  degenerate_uv_materials: [name,...], # materials whose UV span < 1e-4 in u and v (existing anim logic)
  base_color_linked_materials: [...],  # Base Color driven by a node graph (existing anim logic)
  atlas_color_richness: int }          # distinct quantized colours sampled across the BAKED color frames
```

- `has_tex`, `degenerate_uv_materials`, `base_color_linked_materials` are the **existing**
  `blender_render_anim.py:85–138` logic, lifted verbatim so **both** `blender_render.py` and
  `blender_render_anim.py` call it. The static path **gains** degenerate-UV + base-color-linked detection it
  lacks today; neither path keeps a private copy.
- `atlas_color_richness` is the count of distinct quantized colours in the baked `color_atlas.png`
  (silhouette pixels only, alpha > 0), reusing the **existing** quantize-and-count technique
  `test_texture_pass.py:54` already applies (its `> 30` distinct-colours assertion is the precedent and the
  source of the documented floor). This is the back-stop that catches an **orphan-atlas** delivery whose UVs
  are *not* degenerate but whose bound atlas is a flat fill: UVs look fine, the frame is still one colour.
- Both renderers emit the **same keys** in their `*_meta.json`. `bake_asset.py:151–154` already loads
  whichever meta exists into `meta` and threads it to `write_build_log(..., meta=meta)`
  (`bake_asset.py:160–163`), so no new plumbing is needed — only key parity.

### 2. The blocking gate (severity = error when a textured claim bakes flat)

In `build_log.py`, when the asset's `texture_mode` is `textured` (per ADR-0026), emit a **`severity:
"error"`** warning — which flips `ok` false via the existing `build_log.py:172` rule — if **any** of:

```text
not has_tex                                  # textured declared, nothing bound (L0 orphan-atlas: ogre/dragon/ball)
degenerate_uv_materials is non-empty         # textured but renders flat per-material (L1: pirate)
atlas_color_richness < TEXTURED_RICHNESS_FLOOR   # bound + non-degenerate, but the baked frame is flat (orphan/flat-fill atlas)
```

Concretely a new detector `_textured_flat(manifest, meta, texture_mode)` returns
`{"code": "textured_bakes_flat", "severity": "error", "detail": "<which condition + offending materials>"}`
appended alongside the existing detectors at `build_log.py:158–163`. `TEXTURED_RICHNESS_FLOOR` is a single
documented constant in `constants.py` (initial value `30`, matching the `test_texture_pass.py:54`
precedent), referenced — never re-literalled — by both this gate and the test.

- `texture_mode == flat_region` (or absent/legacy) → **the gate does not fire**. `degenerate_uv` /
  `base_color_linked` remain `severity: "warn"` as today for the non-textured paths. **Ogre/dragon stay
  valid** until their art is fixed. This is a strict superset of today's behaviour for flat-region assets:
  no flat-region bake changes verdict.

### 3. Intake refuses to batch a structurally-doomed textured package

`lint_package` (`intake_package.py:206`) gains a **textured-fidelity error** so a delivery that *cannot
possibly* bake with detail is rejected **before** a batch wastes time on it (the same "fail before bake"
spirit as the existing missing-file / archetype / rig / region checks):

- If `texture_mode == textured` and the package binds **no** base-color texture **or** ships an **orphan
  atlas** (a `*_texture_atlas.png` exists but the glb has no UVs / no `baseColorTexture` binding it) →
  `r.err(...)`. This is the static, file/glb-shape-level subset checkable without Blender (the
  degenerate-UV and color-richness conditions require the bake and live in the build-log gate, §2). Note
  `texture_mode` is synthesized into the asset.json next to the existing `textures.base_color`
  (`intake_package.py:158–160`) per ADR-0026.

### 4. Per-asset opt-out waiver (deliberately-flat textured asset)

A delivery may *intend* a flat look while still declaring `textured` (e.g. a stylized swatch aesthetic). It
opts out with an **explicit** per-asset note — `texture_fidelity_waiver: "<reason>"` in the source_asset /
asset.json. When present, `textured_bakes_flat` is **downgraded to `severity: "warn"`** (recorded, visible
in FLAGGED, but `ok` stays true) and the waiver string is copied verbatim into the build log so the
deliberate exception is auditable and greppable. Absent the waiver, a flat textured bake **fails**. Silence
is never consent.

### 5. Batch surfacing

No new exit logic is required: a `severity: "error"` makes the per-variant log `ok: false`, which
`bake_batch.py:189` already turns into a non-zero exit, and `bake_batch.py:171–176` already prints it under
**FLAGGED** with a `[FAIL]` mark. The gate rides the existing severity → `ok` → exit-code chain end to end.

## Consequences

### Positive

- The exact silent failures that motivated this ADR now **fail the batch**: the flat pirate (degenerate
  UVs), the orphan-atlas ogre/dragon/ball (no binding / flat-fill atlas) go from `ok: true` to `[FAIL]`.
- **One** texture-fidelity probe → the static/animated diagnostic **drift is eliminated** by construction;
  the static path stops being a blind spot.
- `flat_region` deliveries are **provably unaffected** (the gate is `texture_mode == textured`-only) — no
  re-bake, no verdict change for any current flat asset.
- The colour-richness floor catches the case **neither** existing detector does: a bound, non-degenerate
  texture whose *atlas* is a flat fill (UVs pass, frame is still one colour).
- Reuses machinery already in the tree (the `has_tex`/degenerate logic, the `test_texture_pass.py`
  quantized-colour count, the severity→`ok`→exit chain) — additive, not a rebuild.
- A deliberately-flat textured asset still has a sanctioned, **explicit and audited** path (the waiver).

### Negative

- A floor (`TEXTURED_RICHNESS_FLOOR`) is a tunable threshold: too high risks a false-fail on a legitimately
  low-palette-but-real texture; too low lets a near-flat bake through. Mitigated by anchoring it to the
  documented `test_texture_pass.py` precedent and the waiver escape hatch; record the chosen value and any
  revisit in the build log.
- `atlas_color_richness` requires sampling the baked color frames (a cheap post-bake numpy pass), so the
  full verdict is a **build-log** gate, not an intake-only gate; intake catches only the static
  no-binding/orphan subset (§3).
- Lifting the detector into a shared helper touches both render entry points and the build log; until both
  paths import it, parity is only as good as the refactor (covered by an acceptance test below).
- Fixing the **upstream** L2 cause (the auto-rig stripping UVs/textures and crashing on the pirate
  `materials.json`) is **out of scope** here and tracked by ADR-0027; this ADR gates the *symptom* so a
  stripped bake can no longer ship green, which is the safety net regardless of the L2 fix timeline.

## Alternatives considered

- **Leave `degenerate_uv` a warning; rely on the reviewer.** *Rejected* — this is the status quo that ships
  the flat pirate green. The whole point is that a *silent* fidelity collapse must not depend on a human
  noticing a warning among many.
- **Per-renderer detectors (keep two copies, just add one to the static path).** *Rejected* — two copies
  drift again the next time one is touched (exactly how the static path fell behind). One shared detector is
  the only durable parity guarantee, mirroring ADR-0025's "one render pass, one source of truth."
- **Degenerate-UV check only (no colour-richness floor).** *Rejected* — it misses the orphan-atlas L0 case
  entirely (UVs are absent or fine; the *atlas* is the flat thing). The richness floor is the back-stop that
  closes that hole.
- **Block ALL flat-looking bakes regardless of `texture_mode`.** *Rejected* — it would fail the legitimate
  flat-region ogre/dragon. The contract distinction is a *claim mismatch* (textured-declared, flat-baked),
  not flatness per se.
- **Hard-fail textured-flat with no waiver.** *Rejected* — a deliberately-stylized flat-textured asset is a
  legitimate (if rare) intent; an explicit, audited waiver is safer than forcing such assets to mis-declare
  `flat_region`.

## Acceptance criteria (each assertable by a CI test)

```text
1. shared-detector parity: blender_render.py and blender_render_anim.py emit IDENTICAL texture-diagnostic
   keys (has_tex, degenerate_uv_materials, base_color_linked_materials, atlas_color_richness) in *_meta.json
   for the same input glb. (Today the static meta lacks degenerate_uv_materials entirely — this test fails
   pre-change, passes post-change.)
2. degenerate-UV -> FAIL when textured: baking the pirate_v2 package with texture_mode=textured yields a
   build_log warning code "textured_bakes_flat" at severity "error" and ok == false.
3. orphan-atlas -> FAIL when textured: a glb with no UVs / no baseColorTexture but texture_mode=textured and
   a *_texture_atlas.png sidecar is REJECTED by lint_package (r.ok == false) AND, if forced to bake, yields
   ok == false (not has_tex branch).
4. flat-fill atlas -> FAIL when textured: a bound, non-degenerate-UV mesh whose baked color_atlas has
   distinct-colour count < TEXTURED_RICHNESS_FLOOR yields "textured_bakes_flat" severity "error", ok false.
5. known-good textured passes: humanoid_textured.glb (UV span ~0.40-0.92, real unwrap) bakes with
   texture_mode=textured, atlas_color_richness >= TEXTURED_RICHNESS_FLOOR, NO textured_bakes_flat warning,
   ok == true.
6. flat_region untouched: an asset with texture_mode=flat_region (ogre/dragon shape) bakes with ok == true
   regardless of has_tex/degenerate UVs; degenerate_uv stays severity "warn"; verdict is byte-identical to
   pre-change for every committed flat-region reference.
7. waiver downgrades, never silences: the same flat textured asset WITH texture_fidelity_waiver set has
   textured_bakes_flat present at severity "warn", ok == true, and the waiver string copied verbatim into
   build_log.json; WITHOUT the waiver the identical asset is severity "error", ok == false.
8. batch exit code: a batch containing one textured-flat (un-waived) package exits non-zero and lists that
   variant under FLAGGED with a [FAIL] mark.
9. floor is a named constant: TEXTURED_RICHNESS_FLOOR is defined once in constants.py and referenced by both
   the build_log gate and test_texture_pass.py (no duplicated literal; grep proves a single definition).
```

## Implementer work-list

Consolidates these backlog stories (named so implementers can find the granular tickets):
**`miss-shared-fidelity-detector`** (§1), **`tex-renderside-warn-parity`** (§1, AC-1),
**`gate-claims-flat-detector`** (§2), **`gate-degenerate-uv-blocking`** / **`tex-degenerate-uv-gate`** (§2,
AC-2), **`ar-flat-gate`** (§2 — gate the auto-rig-flattened output; the upstream L2 fix is ADR-0027),
**`intake-texture-uv-gate`** (§3, AC-3), **`batch-flag-textured-flat`** (§5, AC-8).

1. Extract `texture_fidelity(obj) -> dict` into a shared module (`mesh_io.py`) by lifting
   `blender_render_anim.py:85–138` verbatim; add `atlas_color_richness` (quantize-and-count over the baked
   `color_atlas.png` silhouette pixels, reusing the `test_texture_pass.py:54` technique). Call it from BOTH
   `blender_render.py` (replacing the bare `has_tex` at lines 78–79/182) and `blender_render_anim.py`; emit
   identical meta keys from both. (AC-1)
2. Add `TEXTURED_RICHNESS_FLOOR = 30` to `constants.py` with a comment citing `test_texture_pass.py`; make
   that test import the constant instead of its literal `30`. (AC-9)
3. Add `_textured_flat(manifest, meta, texture_mode, waiver)` to `build_log.py`, appended at the
   detector site (~158–163); `severity: "error"` (or `"warn"` if waiver present), wiring through the
   existing `ok` rule at line 172. Read `texture_mode` + `texture_fidelity_waiver` from the asset; thread
   them into the `write_build_log(...)` call at `bake_asset.py:160–163`. (AC-2, AC-4, AC-7)
4. In `intake_package.py:lint_package`, add the static textured-fidelity error: `texture_mode == textured`
   with no binding / orphan atlas → `r.err(...)`. Synthesize `texture_mode` (+ optional
   `texture_fidelity_waiver`) into the asset.json next to `textures.base_color` (lines 158–160) per
   ADR-0026. (AC-3)
5. Tests: AC-1 through AC-9 above. Reuse `pirate_v2` (degenerate UVs), an orphan-atlas fixture
   (ogre/ball shape), and `humanoid_textured.glb` (known-good) as the three corners; add a flat-fill-atlas
   fixture for AC-4 and a waiver fixture for AC-7.
6. Doc: add `textured_bakes_flat` + the waiver to `docs/build_log_warnings.md`, and record the chosen
   `TEXTURED_RICHNESS_FLOOR` and its revisit threshold.

(Files verified by reading: `build_log.py` severity/`ok` at 141–142 & 172, detector site 134–163,
`stamp_provenance` 208–230; `blender_render_anim.py` 85–138 detect + 234–235 emit; `blender_render.py`
78–79 & 182 `has_tex`-only; `intake_package.py` 158–160 texture synth + 206–310 gate; `bake_batch.py`
171–176 FLAGGED + 189 exit; `bake_asset.py` 150–163 meta load + `write_build_log` call;
`test_texture_pass.py:54` the `>30` colour-richness precedent.)
