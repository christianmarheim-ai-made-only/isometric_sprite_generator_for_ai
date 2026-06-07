# ADR-0029: Texture/UV provenance in the baked manifest

- Status: Proposed
- Date: 2026-06-07
- Blocks: nothing today (a flat bake still ships); unblocks the **engine per-sprite tint decision** — the engine cannot currently tell a real-albedo sprite from a flat-region-colour one, so `proxy_color` washes a textured sprite. The engine tint fix that *reads* this block is tracked in the engine handoff (out of this repo's scope).
- Related: ADR-0026 (`texture_mode` — the render-side texture/material switch this block records the *outcome* of), ADR-0024 (runtime tint vs baked identity — the engine tint decision this feeds), ADR-0025 (additive per-frame manifest fields + a derived-from-source consistency gate — same pattern), ADR-0011/0012 (curated/effect variants); engine tint follow-up (cross-repo handoff). Grounding: `docs/pipeline_hardening_roadmap.md` ("textured but flat" findings), the orphan-atlas / degenerate-UV gap parsed from the delivered glbs.

## Context

A textured-looking bake can ship **green-lit and flat**. Tracing four real deliveries against the known-good baseline showed the manifest records **nothing** about whether a sprite carries real painted albedo or a single flat colour per body part — and the one signal that exists (`degenerate_uv`) is a non-aborting warning that never fails the build.

### What the pipeline detects today (but does not record reproducibly)
- `blender_render_anim.py:85` computes **`has_tex`** = any material has a bound `TEX_IMAGE` node with an image, and at `:214` sets Workbench `color_type = 'TEXTURE' if has_tex else 'MATERIAL'`. So the render *is* texture-capable — but only as good as the input.
- `blender_render_anim.py:87-100` computes **`degenerate_uv_materials`**: materials whose faces all sample ~one UV point (the bound atlas collapses to a single flat swatch — "textured but renders flat"). For `pirate_duelist_v2` this lists **18 of 19 materials** (`anim_meta.json:314-333`) — a fully "textured" sprite that samples one texel per part.
- These land in `anim_meta.json` (`:227-238`), are read into `meta` by `bake_asset.py:150-155`, and `build_log.py:140-142` turns `degenerate_uv` into a `severity:"warn"`. **`ok` only flips false on `severity=="error"`** (`build_log.py:172`). A textured-but-flat bake is therefore **green-lit**.

### What the shipped manifest records today
- `stamp_provenance` (`build_log.py:208-230`) stamps a `sprite_provenance_v1` block: `asset` / `mesh` / `clips` / `rig` / `contract_hash` / `lockfile_hashes` / `build_log`. It answers "which model+clips+rig made this" — but says **nothing** about texture fidelity, the base-colour texture identity, or UV coverage. The engine reads `manifest.json` alone and has no field that distinguishes real albedo from flat region colour.

### The verified gap (ground truth — do not re-investigate)
- **Orphan atlas + geometry-only** (ogre, dragon, red_ball): glbs carry **0 materials/textures/images and zero UVs**; their `*_texture_atlas.png` are sidecars bound to nothing. `has_tex` is correctly `False` here, so they bake MATERIAL-mode flat — but nothing in the manifest *states* "no texture, flat by design."
- **Degenerate UVs** (pirate_v2): 19 region materials, all 19 carry `baseColorTexture` bound to one embedded atlas, but all 37 primitives have UVs collapsed to a point → one flat colour per part. `has_tex` is `True`; the sprite looks textured and ships flat.
- **Known-good baseline** (`humanoid_textured.glb`): 4 region materials, `baseColorTexture` bound, **UVs spanning area 0.40–0.92** (a real unwrap). This is the shape a correct textured delivery must match — and the only one the engine should tint as real albedo.

So the manifest cannot answer the one question the engine needs: **does this sprite carry real albedo, or a flat region colour?** That single bool drives whether the engine applies `proxy_color`/tint (ADR-0024) or leaves the baked pixels alone.

## Decision

Record texture/UV **provenance** in the baked `manifest.json`, additively, and add a gate that asserts the recorded block matches what was actually baked.

1. **Extend the `sprite_provenance_v1` block** (stamped by `stamp_provenance`, `build_log.py:208-230`) with a `texture` sub-block. It is **additive only** — the engine manifest schema is `additionalProperties: true` (`sprite_manifest.schema.json:179`), so this is the `hitmask`/`color_variants` precedent, engine-ignored until consumed. The sub-block records, reproducibly:
   - **`textured`** (bool) — the authoritative engine-facing flag, sourced from the renderer's `has_tex` (`blender_render_anim.py:85`). `true` iff at least one material had a bound base-colour image *and* drove the TEXTURE-mode pass.
   - **`texture_mode`** (string) — the render mode actually used (`"texture"` / `"material"`), the recorded outcome of ADR-0026's switch (`color_type` at `blender_render_anim.py:214`). Must be `"texture"` iff `textured` is `true`.
   - **`base_color_textures`** (array) — for each bound base-colour image, its **sha256** (and pixel dims). Empty iff `textured` is `false`. These are the hashes the engine/reviewer uses to confirm *which* painted atlas (not the orphan sidecar) actually fed the bake.
   - **`uv_coverage`** — a UV identity/coverage summary over textured materials: `min`/`median`/`max` of per-material UV bounding-box area (the same area the degenerate-UV probe at `blender_render_anim.py:96-99` already computes), plus `degenerate_count` and `degenerate_materials` (carried straight from `degenerate_uv_materials`). A real unwrap reads ~0.40–0.92; a degenerate one reads ~0.0.
   - **`flat_fallback`** (bool) — `true` iff the sprite renders one flat colour per part **despite or instead of** a texture: either `textured` is `false` (geometry-only / orphan atlas — ogre/dragon/ball) **or** every textured material is degenerate (pirate). This is the single field that means "do **not** treat these pixels as real albedo."
   - **`uv_repaired`** (bool) — `true` iff the pipeline regenerated/repaired UVs before baking (reserved; `false` today — no repair path exists yet, the auto-rig *strips* UVs).
2. **`textured` is the engine's albedo signal; `flat_fallback` is its inverse-with-reason.** The engine's per-sprite tint decision (ADR-0024) reads `textured && !flat_fallback` to mean "real albedo — do not wash with `proxy_color`." A `flat_fallback` sprite keeps the existing tint behaviour. (The engine-side wiring is the handoff item; this ADR only guarantees the field is present and correct.)
3. **Derive every recorded value from the bake, never restate it.** `texture` is computed once, in the renderer/assembler, from `has_tex` + the UV probe + the bound-image hashes — the same numbers the build-log warnings already use. The manifest block and the `build_log.json` warnings are then **two views of one source**, so they cannot disagree.
4. **Add a provenance-consistency gate** (Gate, alongside Gate-1 engine-accept) that re-derives the texture facts from the baked artifacts and asserts they match the recorded block. Crucially, the gate makes `flat_fallback` **non-silent**: a green build log may still carry `flat_fallback:true`, but the gate guarantees the manifest *says so truthfully*, so a downstream policy can choose to fail or flag it. (Whether `flat_fallback` on a delivery *declared* textured is itself an error is an authoring-policy decision deferred to ADR-0026 / the source linter; this ADR makes it **visible and machine-checkable**, which it is not today.)

## Consequences

### Positive
- The engine gains the **one field it needs** to stop washing real-albedo sprites with `proxy_color` — `textured && !flat_fallback` is a single, additive read.
- A **textured-but-flat** bake (pirate) is no longer indistinguishable from a real unwrap in the shipped manifest: `flat_fallback:true` + `degenerate_count:18` states it explicitly and reproducibly.
- **Reproducible texture identity**: `base_color_textures[].sha256` lets a reviewer prove the *painted* atlas (not the orphan sidecar) fed the bake — end-to-end with the existing `mesh.sha256`.
- Pure **additive** change (schema is `additionalProperties:true`); no engine schema bump, no re-bake of existing packages required to stay valid.
- One source of truth: the consistency gate means the manifest block can never silently drift from the build-log warnings or the rendered pixels.

### Negative
- Adds a manifest sub-block, a small computation in the assembler, and one CI gate (more surface to maintain).
- `flat_fallback` is **diagnostic, not corrective** — it records that a sprite is flat; it does not repair UVs or re-bind atlases (`uv_repaired` is reserved). The L2 auto-rig root cause (strips UVs, replaces materials) is out of scope here.
- The engine benefit is **dormant** until the engine reads the field (handoff item) — this ADR makes the seam correct, not the tint live.
- Texture hashing reads the bound image bytes per bake (negligible; same cost class as the existing `mesh`/`hitmask` sha256).

## Alternatives considered

- **Leave it as a build-log warning only (status quo).** Rejected: `degenerate_uv` is a `severity:"warn"` that never flips `ok` (`build_log.py:172`), and the **engine reads `manifest.json`, not `build_log.json`** — so the warning is invisible to the consumer that needs it. The signal must live in the manifest.
- **A bare `textured` bool, nothing else.** Rejected: it cannot distinguish geometry-only (ogre) from textured-but-degenerate (pirate) — both want "don't treat as albedo," but only the texture-hash + UV-coverage detail lets a reviewer see *why* and verify the right atlas was used. `flat_fallback` needs `uv_coverage` to be computable.
- **A new top-level `texture` manifest object (not under `provenance`).** Rejected for cohesion: it belongs with the other "how this package was made" facts already in `sprite_provenance_v1`; nesting keeps one provenance read and one stamping site (`stamp_provenance`).
- **Gate that hard-fails any `flat_fallback`.** Rejected *here* (recorded for the reviewer): some deliveries (a genuinely flat-coloured ball) are *correctly* flat, so a blanket fail is wrong. The gate asserts **consistency** (the record matches reality); the authoring policy of *whether flat-when-declared-textured is an error* is deferred to ADR-0026 / the linter.

## Acceptance criteria (each is a CI-assertable check)

```text
1. A baked manifest.json carries provenance.texture with keys:
   textured(bool), texture_mode(str), base_color_textures(array),
   uv_coverage(obj), flat_fallback(bool), uv_repaired(bool).
2. provenance.texture.textured == the renderer's has_tex for that bake
   (re-derived from the glb's bound base-colour images; they must agree).
3. texture_mode == "texture" IFF textured == true; else "material".
4. textured == false  =>  base_color_textures == []  AND  flat_fallback == true.
5. Each base_color_textures[].sha256 equals the sha256 of an image actually
   bound as a base-colour texture in the baked mesh (no orphan-sidecar hash).
6. uv_coverage.degenerate_materials == anim_meta.degenerate_uv_materials, and
   degenerate_count == len(that list) (manifest block == build-log source).
7. flat_fallback == true  IFF  (textured == false) OR (every textured material
   is degenerate, i.e. degenerate_count == textured-material count).
8. For the known-good baseline (humanoid_textured.glb): textured == true,
   flat_fallback == false, uv_coverage.median area in [0.40, 0.92].
9. For pirate_duelist_v2: textured == true, flat_fallback == true,
   degenerate_count == 18.
10. For a geometry-only/orphan-atlas delivery (ogre/dragon/red_ball):
    textured == false, flat_fallback == true, base_color_textures == [].
11. The block is additive: the manifest still validates against
    sprite_manifest.schema.json (additionalProperties:true) unchanged.
12. The provenance-consistency gate runs in CI and fails if any of 2–7 is
    violated for any baked package (the record must match the bake).
```

## Implementer work-list

Consolidates backlog stories **`tex-manifest-provenance`**, **`texture-uv-provenance`**, **`w5-texture-provenance-contract`**, and **`gate-texture-provenance-consistency`** into one delivery.

1. In `blender_render_anim.py` (around the `has_tex` / `degenerate_uv` block, `:85-100`), additionally collect: each bound base-colour image's file/bytes (for hashing) and the per-material UV bbox-area list already computed at `:96-99`. Emit these into `anim_meta.json` (`:227-238`) as `base_color_images` + `uv_areas` alongside the existing `degenerate_uv_materials` / `has_tex`.
2. In `build_log.py`, extend `stamp_provenance` (`:208-230`) to assemble the `texture` sub-block (textured, texture_mode, base_color_textures[sha256+dims], uv_coverage, flat_fallback, uv_repaired) from the `meta` it already receives, and nest it under the `sprite_provenance_v1` block.
3. Thread the `meta` (anim/blender) into `stamp_provenance` at the `bake_asset.py:165` call site (it already loads `meta` at `:150-155` for `write_build_log`); pass the same dict so the manifest block and the log warnings share one source.
4. Add the **provenance-consistency gate** (new check next to `engine_accept` in `bake_asset.py:144`, and a standalone CI test): re-derive textured / texture_mode / hashes / uv_coverage / flat_fallback from the baked artifacts and assert they equal `manifest.provenance.texture` (acceptance 2–7).
5. Add fixtures/asserts for the three reference shapes — baseline (real unwrap), pirate_v2 (degenerate), and an orphan-atlas/geometry-only delivery — mirroring `test_bake_warnings.py` (which already exercises `degenerate_uv_materials`).
6. (Reserved) leave `uv_repaired` wired to `false`; flip it when a UV-repair path lands. Cross-reference ADR-0026 for `texture_mode` and the engine handoff for the tint consumer.

---

Returned files (all absolute): the ADR is grounded in `C:/Code/isometric_sprite_generator_for_ai/pipeline/tools/build_log.py` (stamp_provenance 208-230; degenerate→warn 140-142; ok-flip 172), `C:/Code/isometric_sprite_generator_for_ai/pipeline/tools/blender_render_anim.py` (has_tex 85, degenerate_uv 87-100, color_type 214, meta emit 227-238), `C:/Code/isometric_sprite_generator_for_ai/pipeline/tools/bake_asset.py` (meta load 150-155, stamp call 165), and `C:/Code/isometric_sprite_generator_for_ai/pipeline/schema/sprite_manifest.schema.json` (additionalProperties:true, 179). Note for the orchestrator: ADR-0026 (`texture_mode`) is referenced as a sibling but does **not yet exist** in the repo — the Related line treats it as a forward reference, consistent with the task brief.
