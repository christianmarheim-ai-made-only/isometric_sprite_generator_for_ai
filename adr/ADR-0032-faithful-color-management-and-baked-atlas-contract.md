# ADR-0032: Faithful color: pinned Standard/sRGB color management + baked-atlas contract

- Status: **Proposed**
- Date: 2026-06-07
- Blocks: every textured delivery (ogre, dragon, pirate_v2, red_ball) shipping a faithful baked `color_atlas`; the first real painted-texture bake (no longer flat placeholders)
- Related: ADR-0017 (atlas compression/streaming deferred-until-measured — this ADR records measured page sizes but keeps that deferral), ADR-0024 (runtime tint authored against the baked albedo — the faithful albedo is the *base* a tint multiplies), ADR-0028 (atlas richness gate — proposed; the non-flatness assertion lands there), ADR-0020 (metallic/specular — same Workbench-shading-determines-look prerequisite); grounding: `pipeline/tools/blender_render.py`, `pipeline/tools/blender_render_anim.py`, `pipeline/tools/blender_bake.py`, `pipeline/tools/bake.py`, `pipeline/tools/constants.py`, `pipeline/tools/build_log.py`. NOTE: engine ADR-026/028/029/030/031/032 are a SEPARATE (hit-region) numbering space in the engine repo — this ADR-0032 is the pipeline's.

## Context

A textured delivery can pass the whole pipeline and ship a `color_atlas` whose colors are **wrong** — washed, darkened, hue-shifted, or flat grey — with no gate firing. Two independent failure surfaces converge:

### 1. The color-management state is only half-pinned (host-config dependent)

Both production renderers pin exactly **one** of Blender's color-management knobs:

- `blender_render.py:37` — `scene.view_settings.view_transform = 'Standard'`
- `blender_render_anim.py:31` — `scene.view_settings.view_transform = 'Standard'`

Everything else is left at whatever the host Blender's startup config happens to be. Verified by grep across all three render/bake scripts: **the only color-management line is `view_transform`.** Not pinned: `view_settings.look` (a non-`None` look — e.g. a contrast look from a user config — silently re-grades every texel), `view_settings.exposure` and `view_settings.gamma` (a non-zero exposure / non-1 gamma scales/curves the output), `display_settings.display_device` (if not `sRGB`, the encode is wrong), and — critically — **the colorspace of the base-color image** is left at whatever the glTF importer assigned. A baseColorTexture imported as `Non-Color`/`Linear` bakes its texels **un-sRGB-encoded** (visibly dark/desaturated); the same atlas on a host where the importer tagged it `sRGB` bakes correctly. So *the same glb on two machines bakes two different atlases* — color fidelity is non-reproducible, and `view_transform='Standard'` alone does not save it.

`read_factory_settings(use_empty=True)` resets *data*, not all color-management view settings to a guaranteed baseline; relying on factory defaults is exactly the host-dependence this ADR removes.

### 2. The textured COLOR pass is STUDIO-lit — it adds light the albedo already contains

The color pass renders Workbench `light = 'STUDIO'` for both textured and untextured assets:

- `blender_render.py:147-148` — `color_type = 'TEXTURE' if has_tex else 'MATERIAL'`; `light = 'STUDIO'`
- `blender_render_anim.py:214-215` — same.

STUDIO applies Blender's built-in multi-light studio rig: a **direction-dependent** brightness gradient across the 16 yaws. For an **untextured** delivery (flat per-region base colors) that gradient is the *only* form — it's what makes the procedural humanoid read as 3D, and it is acceptable there. But the texturing contract this ADR governs **bakes value/AO into the albedo itself** (the known-good `humanoid_textured.glb` carries a real unwrap with painted shading in its baseColorTexture). STUDIO-lighting an already-shaded albedo **double-shades** it: the studio rig multiplies a second, direction-dependent value gradient on top of the painted one. Result: dir 00 and dir 08 of the *same* texel render at *different* brightness, and the authored color is not faithfully reproduced in any single direction.

### 3. No gate catches a flat/wrong textured bake (it ships green-lit)

The committed `*_texture_atlas.png` are flat placeholders and the models have degenerate or absent UVs (the documented L0/L1/L2 root causes). The pipeline *detects* the degenerate-UV case but does not *block* it: `build_log.py:140-142` emits `degenerate_uv` at `severity: "warn"`, and `build_log.py:172` sets `ok` true unless some warning is `severity == "error"`. So a textured-but-flat bake is **green-lit**. (Contrast: `oversize_atlas_page` at `build_log.py:156` *is* a hard `error` — the precedent for promoting a fidelity check to a gate.)

### 4. The packer is already lossless — this ADR ratifies it as a contract, it does not change it

`bake.py:49-59` (`_extrude_paste`) pastes each frame 1:1 and edge-extrudes the PAD border with `Image.NEAREST` on 1-px crops (no resample of interior pixels, no premultiply, no alpha smear). `_pack`/`place_into` (`bake.py:62-114`) and the Blender bake path (`blender_bake.py:114-117`) compose with `Image.new(..., (0,0,0,0))` paste — no `alpha_composite`, no interior `resize`. So packing/cropping is **already** lossless. This ADR turns that property into a *named, gated contract* so a future packer change can't silently regress it.

### 5. Real textures grow pages — record sizes, keep the downscale deferral

Flat placeholders are tiny; **real painted atlases are large**. The dragon's `*_texture_atlas.png` is already **4096 px wide** — exactly `MAX_PAGE_PX` (`constants.py:136`). A faithful high-frequency texture is one resolution bump from overflowing a page. The actual downscale/compression *policy* stays DEFERRED-UNTIL-MEASURED per ADR-0017; this ADR's job is to **measure and record** page sizes every bake so the deferral is data-backed, and to lean on the existing `oversize_atlas_page` error gate as the hard ceiling.

## Decision

Pin the **full** Blender color-management state in every render script, force base-color images to **sRGB**, render the **textured** color pass **FLAT** (faithful albedo), assert the baked atlas is **sRGB 8-bit** and reproduces a known source texel **within tolerance**, ratify **lossless** packing, and **record** measured page sizes. Concretely:

### D1 — Pin the full color-management state (both render scripts, every pass)

Immediately after `read_factory_settings`, set **all** of, explicitly, in `blender_render.py` and `blender_render_anim.py`:

```text
scene.view_settings.view_transform   = 'Standard'   # (already set; keep)
scene.view_settings.look             = 'None'
scene.view_settings.exposure         = 0.0
scene.view_settings.gamma            = 1.0
scene.display_settings.display_device = 'sRGB'
```

These are a single pinned block, host-config-independent. The baked atlas no longer depends on the operator's Blender preferences.

### D2 — Force base-color images to the sRGB colorspace

After import, for every image feeding a material's **Base Color** (the `TEX_IMAGE` node images already enumerated for `has_tex` at `blender_render.py:78` / `blender_render_anim.py:85`), set `image.colorspace_settings.name = 'sRGB'`. (Non-color data maps — normal/roughness, when they exist — are out of scope here and must stay `Non-Color`; this ADR forces sRGB **only** on base-color feeders.) This makes authored texel colors decode correctly regardless of how the glTF importer tagged them.

### D3 — Textured color pass renders FLAT (faithful albedo), not STUDIO

Because the texturing contract bakes value/AO into the albedo, the **textured** color pass uses `shading.light = 'FLAT'` so the baked atlas reproduces the authored albedo without a second, direction-dependent light gradient. Precisely:

- `has_tex == True`  → color pass `light = 'FLAT'`.
- `has_tex == False` → color pass keeps `light = 'STUDIO'` (untextured per-region flat colors still need form; byte-identical to today for every untextured delivery).

**Fallback if STUDIO is retained for textured assets** (explicit opt-out, not silent): the studio light **MUST** be pinned to a fixed, recorded studio-light id/preset, AND a `studio_cross_direction_consistency` assertion MUST hold — the mean luminance of a fixed un-occluded albedo region varies across the 16 directions by no more than a recorded tolerance. Choosing STUDIO without both is forbidden.

### D4 — The baked color_atlas is sRGB, 8-bit, and texel-faithful within tolerance

- `color_atlas.png` is encoded **8-bit sRGB** (`RGBA`, matching `blender_bake.py:129` `RGBA` / `_pack` mode `"RGBA"`).
- For a fixture whose source carries a **known reference texel** (a solid swatch of known sRGB value, sampled away from any edge-extrude border and any AA seam), the corresponding atlas pixel matches the expected sRGB-encoded value within a recorded per-channel tolerance (proposed `<= 2/255`, allowing only round-trip rounding). This is the load-bearing fidelity check: it fails on a wrong `display_device`, a non-`None` look, a non-sRGB base-color colorspace, or STUDIO double-shading.

### D5 — Packing/cropping is lossless (ratify the existing NEAREST edge-extrude)

The atlas packer MUST NOT resample interior frame pixels, premultiply alpha, or alpha-composite frames over a non-transparent ground. Interior pixels are placed 1:1; the PAD border is **NEAREST** edge-extrude only (the current `_extrude_paste`, `bake.py:49-59`). A frame's interior color pixels appear byte-identical in the atlas.

### D6 — Record measured page sizes; downscale stays deferred (ADR-0017)

Every bake records `color_atlas` page dimensions (W×H px) in the build log / provenance. The existing `oversize_atlas_page` **error** gate (`build_log.py:156`, ceiling `MAX_PAGE_PX = 4096`, `constants.py:136`) is the hard limit. No automatic downscale/compression is added — that policy stays DEFERRED-UNTIL-MEASURED per ADR-0017; this ADR only guarantees the measurement exists so the deferral is revisited on data, not vibes.

### D7 — A flat-when-it-should-be-textured bake fails the gate (companion to ADR-0028)

When a delivery declares `texture_mode == textured` (ADR-0026), a bake whose atlas is effectively a single flat color per region MUST NOT ship green-lit. **The trigger is the declared mode, not `has_tex`** — a `flat_region` asset with an incidental bound texture is unaffected, so this ADR and ADR-0028 can never give the same input opposite verdicts. (Note D3 above — rendering the color pass FLAT — *does* key on `has_tex`; that is a render decision, separate from this gate trigger.) The richness/non-flatness assertion itself lands in **ADR-0028 (atlas richness gate)**; this ADR's contribution is the **severity promotion**: `degenerate_uv` (and an equivalent "textured-but-flat atlas" finding) MUST be `severity: "error"` for a `textured`-declared delivery, so `build_log.ok` (`build_log.py:172`) flips false. The faithful-color contract is only meaningful if a flat bake is a hard failure, not a warning.

## Consequences

### Positive
- **Reproducible color:** the same glb bakes the same atlas on any host; color fidelity no longer depends on the operator's Blender config (look/exposure/gamma/display-device/importer colorspace are all pinned).
- **Faithful albedo:** FLAT textured rendering stops the double-shading; one texel reads the same brightness in all 16 directions, and authored color survives the bake.
- **Machine-checkable fidelity:** D4's known-texel tolerance is a single CI assertion that catches every D1/D2/D3 regression at once.
- **Lossless packing becomes a contract,** not an accident — a future packer change that resamples or premultiplies now trips a gate.
- **The flat-placeholder trap closes:** a textured-but-flat bake is a hard failure (D7 + ADR-0028), not a green-lit warning.
- **Page growth is visible:** real textures' page sizes are recorded every bake, feeding the ADR-0017 downscale revisit with measured data.

### Negative
- **Untextured deliveries are unchanged; textured ones change look** (STUDIO→FLAT) — every existing textured fixture's golden atlas must be re-baked and its golden checksum updated once.
- **FLAT pushes all shading into authoring:** the texture art must now carry value/AO itself; a flat-albedo asset with no painted shading will look flat (correctly — that's the contract, but it shifts burden onto the texture author / the sprite-bake step).
- **A new fixture is required** (a known-reference-texel swatch asset) plus a small golden image, and a CI test to assert D4.
- **D7 will fail current deliveries** (ogre/dragon/ball/pirate) until they ship real UVs + painted atlases — intended (that's the gap), but it means those stay red until the upstream texturing work lands.

## Alternatives considered

- **Pin only `view_transform='Standard'` (today's state).** *Rejected* — verified insufficient: look/exposure/gamma/display-device and the importer's base-color colorspace all still leak host config into the atlas. The same glb bakes differently per machine.
- **Keep STUDIO for the textured pass without pinning/asserting.** *Rejected* — double-shades the already-shaded albedo and bakes a direction-dependent brightness gradient, so no single direction reproduces the authored color. Retained *only* as the explicit, fully-pinned-and-asserted D3 fallback, never as a silent default.
- **Bake in a wide/linear gamut or higher bit depth for "quality."** *Rejected for v1* — the engine consumes an 8-bit sRGB `color_atlas`; a wider pipeline adds an encode step (a new smear/precision surface) for fidelity the consumer can't use. 8-bit sRGB end-to-end keeps the round-trip lossless and the tolerance tight.
- **Add automatic downscale/compression now to absorb big textures.** *Rejected* — violates ADR-0017's deferred-until-measured policy; we record sizes and lean on the existing `oversize_atlas_page` error instead, and revisit when the data demands it.
- **Leave `degenerate_uv` a warning and rely on human review.** *Rejected* — it is precisely what let flat placeholders ship green-lit; a fidelity contract with no gate is decoration.

## Acceptance criteria (each a CI-assertable check)

```text
COLOR-MGMT STATE (D1) — assert on the rendered scene / its recorded meta:
  view_settings.view_transform == 'Standard'
  view_settings.look           == 'None'
  view_settings.exposure       == 0.0
  view_settings.gamma          == 1.0
  display_settings.display_device == 'sRGB'
  (in BOTH blender_render.py and blender_render_anim.py)

BASE-COLOR COLORSPACE (D2):
  every TEX_IMAGE image feeding a material Base Color has colorspace_settings.name == 'sRGB';
  any normal/roughness (non-color) maps remain 'Non-Color'.

TEXTURED PASS IS FLAT (D3):
  has_tex == True  -> the color pass recorded light == 'FLAT';
  has_tex == False -> the color pass recorded light == 'STUDIO' (untextured unchanged).
  Fallback branch (if STUDIO kept for textured): a fixed studio-light id is recorded AND
    studio_cross_direction_consistency holds (per-direction mean albedo luminance of a fixed
    region varies <= recorded tolerance across all 16 dirs).

ATLAS FIDELITY (D4):
  color_atlas.png decodes as 8-bit sRGB RGBA;
  for the known-texel fixture, atlas pixel == expected sRGB value within <= 2/255 per channel
    (sampled off any edge-extrude border and AA seam).

LOSSLESS PACK (D5):
  a frame's interior color pixels are byte-identical in the atlas (no resample/premultiply/composite);
  the PAD border is NEAREST edge-extrude only (interior never resized).

PAGE-SIZE RECORD + CEILING (D6):
  the build log/provenance records color_atlas W,H for the bake;
  every page W,H <= MAX_PAGE_PX (4096); oversize_atlas_page remains severity 'error'.
  (No downscale asserted — deferred per ADR-0017; the recorded sizes are the only requirement here.)

FLAT-WHEN-TEXTURED IS A HARD FAILURE (D7, with ADR-0028):
  texture_mode == textured AND (degenerate_uv OR atlas-effectively-flat) -> build_log.ok == False
    (severity 'error', not 'warn').   # trigger keys on DECLARED mode, not has_tex (defers to ADR-0028)
```

## Implementer work-list

Consolidates these backlog stories — implementers grepping for them land here:
**tex-srgb-faithful** (D1+D2), **tex-studio-light-faithful** (D3), **tex-pack-no-resample** (D5), **miss-atlas-srgb-bitdepth-contract** (D4), **miss-atlas-memory-downscale** (D6).

1. In **`blender_render.py`** and **`blender_render_anim.py`**, replace the single `view_transform` line with the full pinned block (D1): `view_transform='Standard'`, `look='None'`, `exposure=0.0`, `gamma=1.0`, `display_settings.display_device='sRGB'`. (`blender_render.py:37`, `blender_render_anim.py:31`.)
2. In both scripts, after import, set `image.colorspace_settings.name='sRGB'` on every base-color `TEX_IMAGE` image (reuse the `has_tex` node walk at `blender_render.py:78` / `blender_render_anim.py:85`); leave non-color maps untouched (D2).
3. In both scripts, gate the color-pass light on `has_tex`: `FLAT` when textured, `STUDIO` when not (`blender_render.py:147-148`, `blender_render_anim.py:214-215`) (D3). If the STUDIO fallback is taken instead, pin a fixed studio-light id and emit per-direction mean-luminance into meta for the consistency assertion.
4. Record the chosen color-pass `light`, the pinned color-management values, and the base-color image colorspaces into `blender_meta.json` / `anim_meta.json` so D1/D2/D3 are CI-assertable from meta without re-opening Blender.
5. Add a **known-reference-texel fixture** (a solid-swatch textured asset with a real, non-degenerate UV island) + a golden, and a `test_texture_pass`-adjacent CI test asserting D4 (atlas pixel within `<=2/255` of expected sRGB).
6. Add a CI test ratifying D5 against `_extrude_paste`/`_pack` (`bake.py:49-114`): interior pixels byte-identical, border NEAREST-extruded only.
7. Record `color_atlas` page W×H in `build_log.py` provenance (D6); confirm `oversize_atlas_page` stays `severity:'error'` at the `MAX_PAGE_PX=4096` ceiling (`build_log.py:156`, `constants.py:136`). Do **not** add downscale (ADR-0017).
8. Promote `degenerate_uv` (and the ADR-0028 atlas-flat finding) to `severity:'error'` when `texture_mode=='textured'` (ADR-0028's trigger — **not** `has_tex`, so a `flat_region` asset with an incidental bound texture is unaffected) (`build_log.py:140-142`, gate at `:172`) so a flat textured bake flips `ok` false (D7).
9. Re-bake every existing **textured** golden (STUDIO→FLAT changes their pixels) and update the golden checksums; verify untextured goldens are byte-identical (unchanged).

---

Verified touchpoints (read, not assumed): `pipeline/tools/blender_render.py:37,78,147-148`; `pipeline/tools/blender_render_anim.py:31,85,214-215`; `pipeline/tools/blender_bake.py:40-41,110-117,129`; `pipeline/tools/bake.py:49-114`; `pipeline/tools/constants.py:136`; `pipeline/tools/build_log.py:140-142,156,172`. Confirmed gap: only `view_transform='Standard'` is pinned today (grep across all three scripts); `look`/`exposure`/`gamma`/`display_device`/base-color colorspace are host-default. `degenerate_uv` is `severity:'warn'` and `ok` flips false only on `severity=='error'`, so a textured-but-flat bake ships green. ADR-0017 and ADR-0024/0025 exist on disk and were used for house format; ADR-0028 is referenced as the proposed sibling richness gate (not yet on disk).
