# ADR-0027: Auto-rig preserves textures and UVs; textured models ship pre-rigged

- Status: **Proposed**
- Date: 2026-06-07
- Blocks: any textured creature delivery (pirate_v2 today; every future painted-atlas asset). Until this lands, the auto-rig path **silently flattens** every textured model to per-region flat colour, and the build still ships green.
- Related: ADR-0026 (`texture_mode` — the manifest field, enum **exactly `{flat_region, textured}`**; note **`uv_repaired` is NOT a `texture_mode` value** — it is a separate provenance bool recorded by ADR-0029), ADR-0028 (the **gate** that makes a flatten an *error*, not a warn), ADR-0029 (the `uv_repaired` provenance stamp); pipeline ADR-0024 (color variations — runtime tint over a *correctly textured* base; this ADR keeps the base correct), pipeline ADR-0025 (region mask/AABBs — the region pass must keep working when materials/UVs are preserved); engine ADR-0NN hit-regions are a **different** numbering space (do not collide). Grounding read for this ADR: `pipeline/tools/rig_from_profile.py`, `pipeline/tools/bake_asset.py`, `pipeline/tools/bake_anim_from_json.py`, `pipeline/tools/blender_render_anim.py`, `pipeline/tools/build_log.py`.

## Context

A producer delivered a textured pirate (`chr_pirate_duelist_v2`). It baked **green** (Gate-1 passed, build log `ok: true`) yet the sprite shows **no painted detail** — every part is one flat colour. Parsing the deliveries against the pipeline gives the ground truth (verified, not re-investigated here):

**Input-side reality (4 deliveries + 1 known-good baseline):**
- **ogre, dragon, red_ball glbs — GEOMETRY-ONLY.** Zero materials, zero textures, zero images, and **no `TEXCOORD_0`** on any primitive. Their committed `*_texture_atlas.png` are **orphan sidecars** bound to nothing. `materials.json` is a few flat per-region `base_color`s. (Root-cause layer **L0**.)
- **pirate_v2 glb — degenerate UVs (L1).** 1 mesh, 19 region-keyworded materials, **all 19 carry `baseColorTexture`** bound to 1 embedded atlas — but **all 37 primitives have UVs collapsed to a single point** (each pinned to the centre of that material's swatch-grid tile). So each material samples **exactly one texel** → one flat colour per part. A "flat colour via texture" hack, not a real unwrap.
- **Known-good baseline `humanoid_textured.glb`** — 1 mesh, 4 region materials, `baseColorTexture` bound, UVs spanning area **0.40–0.92** (a real unwrap). This is the shape a correct textured delivery must match.
- The committed `*_texture_atlas.png` are **flat placeholders** (pirate = labelled swatch grid; dragon/ogre = noise/tiling fills), **not painted art**. Detailed painted atlases exist but are (a) bound into no glb and (b) unusable because the models have no real UVs.

**Pipeline-side reality (the failure that ships it green):**
- **L2 — `rig_from_profile.py` destroys textures unconditionally.** For *every* part it builds a **fresh single-Principled material** from a flat per-region sidecar colour (`:142–153`), **clears** the imported material (`:151–152` `m.data.materials.clear()`), and **strips all vertex-colour attributes** (`:157–158`). It **never reads** the bound `baseColorTexture` and **never inspects UVs**. So even the pirate's one-texel-per-part hack — its only source of per-part colour — is thrown away and re-derived from the sidecar.
- **L2 (crash) — the `materials.json` shape mismatch.** `:111–114` iterates `json.load(...).get("materials", [])` as a **LIST of dicts** (`for mm in ...: mm.get("region")`). The textured pirate ships a **name-keyed DICT** of `{material_name: {base_color_factor: ...}}` with **no top-level `materials` list** — so the richest deliveries either get an **empty colour table** (the `.get("materials", [])` default) or **`AttributeError`** when a dict value is iterated as a material record. The shape that carries the most colour intent is exactly the one the loop can't read.
- **L2 (export) — no material/image flags.** `rig_from_profile.py:162` exports with `export_scene.gltf(..., export_format='GLB', use_selection=False)` — **no `export_materials`, no embedded-image directive**. Whatever survived in memory is at the mercy of exporter defaults.
- **L2 (re-export) — same gap downstream.** `bake_anim_from_json.py:64–65` re-exports with `export_animations`/`export_skins` but **no `export_materials` / embedded-image flag** — a second round-trip that can drop a bound image.
- **L3 — the renderer is texture-capable but only as good as its input.** `blender_render_anim.py:85–86` detects `has_tex` (any material with a `TEX_IMAGE` node carrying an `image`) and `:214` selects `shading.color_type = 'TEXTURE' if has_tex else 'MATERIAL'`. If the texture survived, the bake would render it. It never survives auto-rig.
- **L4 — no gate; the flatten ships green.** `blender_render_anim.py:89–100` detects `degenerate_uv` (a material whose loops all sample ~one UV point). It flows to `build_log.py:140–142` as **`severity: "warn"`**. And `build_log.py:172` sets `"ok": gate1_ok and not any(w["severity"] == "error" ...)` — **only an `error` flips `ok` false**. A textured-but-flat bake is therefore green-lit. (`bake_asset.py:99` is where the trap is sprung: auto-rig fires whenever `not _glb_has_armature(mesh_path)`, and `_glb_has_armature` at `:41–48` checks **only `skins`** — a *textured-but-unrigged* glb has no skin, so it is routed straight into the flattening rig step with no texture guard.)

The net: a correct textured input is indistinguishable, in the shipped package, from a flat one. The pipeline is texture-capable end-to-end **except** that its own auto-rig step is a texture-destroyer, and its gate can't tell.

## Decision

**Auto-rig MUST preserve a part-mesh's existing UVs and bound base-colour texture when present; the flat-per-region replacement is a FALLBACK applied ONLY to genuinely un-textured parts. Textured deliveries SHOULD ship PRE-RIGGED; a textured-but-unrigged model that gets auto-rigged keeps its texture OR the bake FAILS — never silently flatten.**

Precisely, and machine-checkably:

1. **Per-part preserve-vs-flatten branch in `rig_from_profile.py`.** Before any material replacement, classify each part-mesh. A part is **textured** iff it has at least one material with a `TEX_IMAGE` node bound to a non-null `image` **and** a non-degenerate active UV layer for that material's loops (UV bbox extent ≥ `1e-4` on at least one axis — the same threshold as the `degenerate_uv` detector, so the two agree). For a **textured** part: **add the vertex group + armature modifier only** (`:78–83`) and leave **material, UV layer, and image untouched** — do **not** clear materials, do **not** strip `color_attributes`. The flat-per-region material build + `color_attributes` strip (`:142–158`) runs **only** for parts that are **not** textured.

2. **Fix the `materials.json` shape crash (accept LIST or name-keyed DICT).** The sidecar loader (`:111–114`) MUST accept **both** the list shape (`{"materials": [{"name","region","base_color"}, ...]}`) **and** the name-keyed dict shape (`{"<material_name>": {"base_color_factor": [...], "region": ...}}`) the textured pirate ships, normalising to the same `region_id -> base_color` table. Reading a name-keyed-dict `materials.json` MUST NOT raise.

3. **Thread explicit glTF export flags through every round-trip.** Both `rig_from_profile.py:162` **and** `bake_anim_from_json.py:64–65` MUST export with `export_materials='EXPORT'` and keep the embedded image (textures packed into the GLB). A bound `baseColorTexture` present on the input MUST be present on each derived glb the next stage consumes.

4. **Pre-rig policy + auto-rig texture guard.** Textured deliveries **SHOULD** ship pre-rigged: `bake_asset.bake_asset` routes **around** auto-rig when the glb already declares a skin (existing `_glb_has_armature` check at `:99`, unchanged for the rigged case). For a model that **is** auto-rigged: if the **input** glb had a bound base-colour texture (≥1 `baseColorTexture`) and the **derived rigged glb** has **none**, the bake **MUST FAIL** (a hard error, not a warn). A textured input may never silently become a flat package.

5. **Optional, provenance-stamped UV repair (recovers the pirate without art rework).** When a part's UVs are degenerate **but** its sidecar declares `atlas_tile.uv_rect_gltf` for that material, `rig_from_profile.py` MAY rebuild **flat-but-correct** UVs from the declared rect (each loop placed inside the declared tile) so the part samples its intended swatch instead of one arbitrary texel. A package built with any repaired UV MUST be stamped **`uv_repaired`** in provenance (per ADR-0029). UV repair is **opt-in** and never silently changes a delivery that didn't ask for it.

This ADR consolidates and supersedes the granular backlog stories: **ar-preserve-tex** (1), **ar-materials-shape** (2), **ar-export-flags** (3), **ar-prerig-policy** + **tex-autorig-texture-guard** (4), **ar-uv-repair** (5).

## Consequences

### Positive
- **Textured deliveries finally bake textured.** The known-good `humanoid_textured.glb` shape round-trips through auto-rig with its unwrap + atlas intact; the renderer's existing `TEXTURE` branch (`blender_render_anim.py:214`) does the rest.
- **The richest deliveries stop crashing/emptying.** The name-keyed-dict `materials.json` is read, not skipped or fatal.
- **No more silent flatten.** A textured input that loses its texture is a **build failure** (4), surfaced loudly, not a green package with a buried `warn`.
- **Pirate recoverable with zero art rework.** Declared-rect UV repair (5) restores its intended per-part swatch colour, stamped honestly as `uv_repaired`.
- **Un-textured deliveries are unaffected.** ogre/dragon/ball (geometry-only, L0) still take the flat-per-region fallback exactly as today — same output, same path, byte-compatible.

### Negative
- **`rig_from_profile.py` grows a branch** (preserve vs flatten) and two input-shape readers; more surface, more tests. Mitigated by the per-part classifier being a small, single-thresholded predicate shared with the existing `degenerate_uv` detector (no drift).
- **A previously-green class of package now fails the bake** (textured-in, flat-out). This is intended, but it converts silent debt into visible breakage that producers must fix (deliver pre-rigged, or a real unwrap, or declare `uv_rect_gltf` for repair).
- **UV repair is a flat approximation**, not a true unwrap — it recovers per-part colour, not painted gradients within a part. It is explicitly marked `uv_repaired` so no one mistakes it for art (ADR-0029).
- **Cross-file coupling:** the export-flag fix must land in **both** re-export sites (3) or a texture still dies on the second round-trip; the gate (ADR-0028) is the backstop that catches a missed site.

## Alternatives considered

- **Leave auto-rig as-is; require every producer to ship pre-rigged + a real unwrap.** *Rejected as the sole fix.* Pre-rig is the right **policy** (Decision 4) but cannot be the only mechanism: an unrigged textured delivery would still hit auto-rig, and today that flattens silently. The texture guard (4) makes the policy enforceable instead of advisory.
- **Make `degenerate_uv` a fatal error and stop there.** *Insufficient.* That gates **degenerate** UVs (the pirate) but not the **clobber** path — a model with a *real* unwrap (the baseline) would still have its material cleared and image stripped by `rig_from_profile.py:151–158`, and `degenerate_uv` would never fire because by render time there's no texture left to test. The preserve branch (1) must come first; the gate (ADR-0028) is complementary, not a substitute.
- **Always run UV repair when UVs are degenerate.** *Rejected.* Repair fabricates UVs; doing it implicitly would mask genuine producer errors and silently alter deliveries. It is opt-in and provenance-stamped (5 / ADR-0029).
- **Bake textures by writing per-region colour into a generated atlas (keep flat-only forever).** *Rejected.* That permanently forecloses real painted art (the existing detailed atlases) and contradicts the renderer already being texture-capable. The cost of preserving is small; the cost of foreclosing is the whole textured roadmap.

## Acceptance criteria (each is a CI-assertable check)

```text
PRESERVE (ar-preserve-tex)
1. Rigging the known-good humanoid_textured.glb yields a rigged glb that still declares >=1
   baseColorTexture bound to a packed image, and >=1 material with a non-degenerate UV layer
   (active-UV bbox extent >= 1e-4 on >=1 axis) -- assert by parsing the derived glb's glTF JSON.
2. For that same rigged glb, NO material was replaced by a flat-per-region Principled and NO
   color_attributes were stripped on a textured part (the preserved material name == the input
   material name for every textured part).
3. Rigging a geometry-only input (ogre/dragon/ball shape: 0 textures, no TEXCOORD_0) takes the
   flat-per-region fallback EXACTLY as before -- output materials/colours byte-identical to the
   pre-ADR baseline (golden compare).

MATERIALS SHAPE (ar-materials-shape)
4. Loading a name-keyed-dict materials.json ({ "<name>": {"base_color_factor":[...]}}) returns a
   non-empty region_id->base_color table and raises no AttributeError.
5. Loading the legacy list-shaped materials.json ({"materials":[...]}) yields the same normalised
   table it does today (no regression).

EXPORT FLAGS (ar-export-flags)
6. rig_from_profile and bake_anim_from_json each export with export_materials='EXPORT' and an
   embedded image; a baseColorTexture present on the input is present on each derived glb
   (parse glTF JSON of both round-trips: rigged.glb AND animated.glb).

PRE-RIG POLICY + GUARD (ar-prerig-policy / tex-autorig-texture-guard)
7. A glb that already declares a skin is NOT auto-rigged (bake_asset routes around rig_from_profile).
8. Auto-rigging a textured-but-unrigged glb that ENDS UP with no bound texture FAILS the bake
   (non-zero exit / raised SystemExit) -- it does NOT produce a package with ok:true.
9. The end-to-end bake of a textured delivery sets has_tex=True in meta AND the rendered body of the
   torso frame contains >1 distinct non-background colour (texture detail present, not flat).

UV REPAIR (ar-uv-repair)
10. With UV repair ON and a sidecar declaring atlas_tile.uv_rect_gltf, a degenerate-UV part's loops
    fall inside the declared rect (rebuilt UVs), and the package provenance is stamped uv_repaired.
11. With UV repair OFF (default), a delivery's UVs are unchanged and provenance is NOT stamped
    uv_repaired.
```

## Implementer work-list

1. **`rig_from_profile.py` — per-part classify + branch (ar-preserve-tex).** Add a `_is_textured(mesh)` predicate (≥1 material with a `TEX_IMAGE` node + bound `image`, and a non-degenerate active UV layer for that material's loops, threshold `1e-4` shared with the `degenerate_uv` detector). Gate the material-replace + `color_attributes` strip (`:142–158`) on `not _is_textured(m)`; for textured parts run only the skin/armature add (`:78–83`).
2. **`rig_from_profile.py` — `materials.json` shape normaliser (ar-materials-shape).** Replace the `:111–114` list assumption with a loader that accepts a list **or** a name-keyed dict (`base_color` / `base_color_factor`), normalising to `region_id -> base_color`.
3. **`rig_from_profile.py:162` + `bake_anim_from_json.py:64–65` — export flags (ar-export-flags).** Add `export_materials='EXPORT'` and keep embedded images on both exports.
4. **`bake_asset.py` — texture guard around auto-rig (tex-autorig-texture-guard / ar-prerig-policy).** After `rig_from_profile` produces `rigged` (`:115–119`), if the **input** mesh had a bound base-colour texture and the **derived** rigged glb has none, `raise SystemExit(...)`. Confirm the pre-rig route (skin present → skip, `:99`) is unchanged.
5. **`rig_from_profile.py` — opt-in UV repair (ar-uv-repair).** Behind a flag: when a part's UVs are degenerate and its sidecar carries `atlas_tile.uv_rect_gltf`, rebuild flat UVs inside the rect; record `uv_repaired` for ADR-0029 to stamp.
6. **Tests.** Add `test_auto_rig_preserves_texture.py` (criteria 1–3, 6–9), extend the `materials.json` loader test (4–5), and a `test_uv_repair.py` (10–11). Wire into the pre-commit CI gate alongside `test_texture_pass.py` / `test_bake_warnings.py`. Note: the **green-ships** half (a flat textured bake must FAIL, not warn) is owned by **ADR-0028**; this ADR's guard (4) is the narrower "auto-rig dropped a texture → fail" check.
