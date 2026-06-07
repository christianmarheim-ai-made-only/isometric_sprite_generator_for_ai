# Handoff: Pipeline hardening (Epic A — texture fidelity)

- For: the pipeline-hardening implementation chat.
- Parent: [`../arcs/ARC-0001-textured-verified-skinned-models.md`](../arcs/ARC-0001-textured-verified-skinned-models.md).
- Implements: **ADR-0026, ADR-0027, ADR-0028, ADR-0029, ADR-0032**.
- Goal: a textured/skinned delivery either bakes into a richly-textured sprite or **fails the bake loudly** — never ships flat green-lit.

Read the ARC §1 (the verified gap) and the five ADRs first; they carry the rationale and the exact predicates. This brief is the ordered backlog. Each story: `id` — what — touchpoint — gate. **Keep the slice order** (the gate before the preserve-fix hard-blocks in-flight deliveries).

---

## Slice 1 — `texture_mode` + the capability predicate (ADR-0026)
*Pure-additive, no bake-output change, ships green immediately. The keystone everything else gates against. Default `flat_region` keeps every existing asset valid.*

| id | what | touchpoint | gate |
|---|---|---|---|
| `declare-texture-mode` | add `texture_mode ∈ {flat_region, textured}` to both schemas (default `flat_region`) | `pipeline/schema/external_asset.schema.json`, `source_asset.schema.json` | `test_schemas.py` |
| `texture-capable` | implement `texture-capable(glb)` as a **standalone glTF-JSON reader** (no Blender): per-material UV bbox area ≥ 1e-4 **and** max-extent ≥ 1e-3 **and** islands in [0,1]; base colour **bound** (`baseColorTexture`→embedded image). Returns a structured record. Promote `_diag_glb_uvmesh.py` from print → checked predicate (+ the area term). | new `pipeline/tools/texture_capable.py` (from `_diag_glb_uvmesh.py`) | unit test on pirate(False)/humanoid_textured(True) |
| `gate-textured-requires-bound-tex-uv` + `kill-orphan-texture-atlas` | intake rejects `texture_mode:textured` + (not capable / orphan sidecar / degenerate) | `pipeline/tools/lint_external_asset.py`, `intake_package.py` | intake exit≠0 |
| `ar-materials-schema` | schema for `*_materials.json` accepting BOTH the LIST (`materials_v1`) and name-keyed DICT (`character_materials_v1`) shapes; validate at intake | new `pipeline/schema/materials.schema.json`, `intake_package.py:206+` | intake-lint |
| `doc-texture-mode-contract` | reconcile the docs; **rebase ADR-0026 Context** to the actual `external_asset.schema.json:37` text (critic C6 — keep the still-correct loose-path caveat) | `docs/texturing_the_body.md`, `docs/external_asset_contract.md` | docs-lint |
| `backfill-texture-mode-incoming` | stamp `texture_mode: flat_region` on cow/ball/ogre/dragon/pirate so re-bakes are gate-correct (`miss-flat-creatures-stay-valid`) | `creative/incoming/*/*.asset.json` | bake stays green |

---

## Slice 2 — auto-rig preserves textures + UVs (ADR-0027)
*Must land before the Slice-3 error gate, else good textured inputs hard-fail with no preserve path.*

| id | what | touchpoint | scope |
|---|---|---|---|
| `ar-materials-shape` | fix the crash: loader iterates `materials` as a LIST but the pirate ships a name-keyed DICT (`base_color_factor`) → AttributeError. Normalise both to `(name, region, colour)`. | `rig_from_profile.py:108-114` | S |
| `ar-preserve-tex` | gate the flat-replace + vertex-strip on `not is_textured(mesh)`; a part with a bound `TEX_IMAGE` + non-degenerate UVs keeps material/UV/image | `rig_from_profile.py:135-160` (`:151-152` clear, `:157-158` strip) | M |
| `ar-export-flags` | `export_materials='EXPORT'` (+ keep embedded image) at **both** export sites so the image survives the round-trip | `rig_from_profile.py:162`, `bake_anim_from_json.py:64-65` | S |
| `ar-prerig-policy` | document the routing: textured **ships pre-rigged**; auto-rig is the fallback that must preserve | `bake_asset.py:93-120`, docs | S |
| `tex-autorig-texture-guard` | FAIL the bake if input had a bound texture and the derived glb has none (no silent flatten) | `bake_asset.py:41-46` `_glb_has_armature`, `intake_package.py` | L |
| `ar-uv-repair` | opt-in, provenance-stamped: when UVs degenerate but the sidecar declares `atlas_tile.uv_rect_gltf`, rebuild flat UVs inside the rect → recovers the pirate's per-part colour with no art rework; mark `uv_repaired` | `rig_from_profile.py` (near `:142`), `pirate_duelist_v2_materials.json` | L |

---

## Slice 3 — the fidelity gate (ADR-0028)
*One shared detector, one trigger (`texture_mode==textured`), both render paths + intake + batch.*

| id | what | touchpoint | severity |
|---|---|---|---|
| `miss-shared-fidelity-detector` + `tex-renderside-warn-parity` | lift ONE `texture_fidelity()` (has_tex, degenerate_uv, atlas-richness) into **both** renderers — the static path has **no** degenerate detection today | `blender_render.py:78-79`, `blender_render_anim.py:85-100` | — |
| `animmeta-emit-hastex` | emit `has_tex` + degenerate list from the animated path meta | `blender_render_anim.py:234-236` | — |
| `ar-flat-gate` / `gate-degenerate-uv-blocking` | `texture_mode==textured` **AND** (not has_tex / any degenerate / atlas-flat) ⇒ `severity:error` ⇒ `ok=false` | `build_log.py:140-142,172` | **error** |
| `gate-claims-flat-detector` / `w5-richness-srgb-gate` | atlas colour-richness floor (distinct quantized colours). **Pin `>` vs `>=` and one constant name** (critic C2; current `test_texture_pass.py:54` uses `>30`) | `test_texture_pass.py:53-56`, `build_log.py` | **error** |
| `intake-texture-uv-gate` | reject `textured`+not-capable at intake (no-Blender, pre-batch) | `intake_package.py`, `lint_external_asset.py` | error |
| `batch-flag-textured-flat` | batch FLAGGED summary marks textured-flat as FAIL + non-zero exit | `bake_batch.py` | error |
| `tex-multimaterial-fixture` | committed multi-mesh, multi-material, textured fixture (real-delivery shape) via a `gen_*` script | `gen_texture_starter.py` | — |
| `tex-twopass-region-gate` | assert the R8 region pass stays discrete (≤5 unique ids) even when the color pass is TEXTURE-shaded | `blender_render_anim.py:206-225`, `blender_bake.py:73-88` | gate |
| `tex-join-preserves-uv` | the multi-mesh JOIN preserves UVs/material-slots/images (active-UV-layer assumption) | `blender_render_anim.py:43-51` | gate |
| `tex-orient-correction-safe` | textured +Y/Z-up bakes equivalent to +X/+Z (no UV mirror/winding flip) | `test_forward_axis.py` (extend) | gate |

---

## Slice 4 — texture/UV provenance (ADR-0029)

| id | what | touchpoint |
|---|---|---|
| `tex-manifest-provenance` / `texture-uv-provenance` | provenance.texture: **rename raw bool `has_bound_tex`** (== has_tex) + derive **`real_albedo = has_tex && !flat_fallback`** (critic C3/C11 — the engine-facing field), per-image sha256, UV coverage, `uv_repaired`/`flat_fallback`/`texture_mode` | `build_log.py:208-230` `stamp_provenance`, `blender_bake.py` |
| `gate-texture-provenance-consistency` | assert the recorded block matches the bake | `build_log.py` + a gate test |
| `w5-texture-provenance-contract` | optional fields in `sprite_manifest.schema.json` + `source_asset.schema.json` | `test_schemas.py` |

---

## Slice 7 — faithful color + atlas contract (ADR-0032)
*Parallel to Slices 4–6.*

| id | what | touchpoint |
|---|---|---|
| `tex-srgb-faithful` | pin full color-mgmt (`Standard`/`look None`/exposure 0/gamma 1/display sRGB) + force base-color images to sRGB | `blender_render.py:30-37`, `blender_render_anim.py:29-31` |
| `tex-studio-light-faithful` | render the textured color pass **FLAT** (AO baked into albedo); if STUDIO kept, pin the light + assert cross-direction brightness | `blender_render*.py` light gate |
| `tex-pack-no-resample` | lossless pack assertion (NEAREST extrude, no resample/premultiply) | `bake.py:49-114` |
| `miss-atlas-srgb-bitdepth-contract` | atlas decodes sRGB-8; known-texel fixture within ≤2/255 | new `test_texture_color_fidelity.py` |
| `miss-atlas-memory-downscale` | record page W×H every bake vs `MAX_PAGE_PX=4096` (dragon atlas already 4096 wide); downscale stays deferred (ADR-0017) | `build_log.py`, `constants.py:136` |

---

## Cross-slice goldens + re-process

| id | what |
|---|---|
| `tex-nonskip-golden` / `w5-textured-golden` | commit a real-textured reference package + a **non-skipping** richness/discreteness gate (covers the no-Blender CI box) |
| `w5-pirate-proof-chain` | re-UV + re-bake `pirate_duelist_v2` (it is pre-rigged + texture-bound; only blocker is the UVs) → assert `degenerate_uv==[]` + atlas richness ≫ flat. The end-to-end proof. |
| `w5-rebake-revendor` | once textured deliveries arrive, re-bake ogre/dragon/pirate + re-vendor to the engine → see [`engine_team_brief.md`](engine_team_brief.md) |

**Done:** the four broken shapes (geometry-only, degenerate-UV, auto-rig-flattened, orphan-atlas) each turn the build red; `humanoid_textured.glb` stays green; the pirate proof-of-chain bakes textured.
