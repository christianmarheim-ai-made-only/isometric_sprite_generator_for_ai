# Model Producer Delivery Spec — v3 (Combat Creature)

> **producer_spec_version = `model_producer_delivery_spec_v3`**
> **Status: Proposed**
> Audience: an AI or human **producing a 3D combat creature** for the `game_iso_v1` sprite pipeline.
>
> Sibling docs in this folder (read them — this README is the index, they are the detail):
> [`calibration_model.md`](calibration_model.md) · [`uv_format.md`](uv_format.md) · [`gate_reference.md`](gate_reference.md) · [`prompts/`](prompts/) · [`examples/`](examples/)

This document is **authoritative**. Where it and the code disagree, the code wins — every claim here is
traced to a real file under `pipeline/tools/` and `pipeline/schema/`, cited inline.

---

## 1. What this is — and the locked `game_iso_v1` contract (NOT yours to change)

You deliver a **3D model + a small manifest + sidecars**. The pipeline bakes it down to a 16-direction
2D sprite atlas the read-only game engine loads. You produce the model; the pipeline owns the camera, the
projection, the atlas, and the verification. You do **not** choose any of the following — they are fixed:

| Locked target (`game_iso_v1`) | Value | Source |
|---|---|---|
| Projection | 2:1 dimetric | locked |
| Camera azimuth / elevation | **45° / 30°** | locked |
| Directions baked | **16** (`DIRS`) | `constants.py` |
| Forward axis | **+X** = direction 0 | `constants.py` (`forward_yaw`) |
| Up axis | **+Z** | `constants.py` |
| Tile footprint | **64 × 32** px | locked |
| Frame canvas | **256** px (`CANVAS`) | `constants.py` |
| Atlas page cap | **≤ 4096** px per dimension (`MAX_PAGE_PX`) | `constants.py` |

You author in **metres, +Z up**, facing your declared forward. The baker rotates your declared
`geometry.forward` onto +X (a `+y`-authored model bakes identically to a `+x`-authored one — see
`forward_yaw()` in `constants.py`), so forward is a *live correction*, not a label. Get it right anyway.

**Do not "correct" the screen winding, the elevation, or the 16-way fan.** Those are the pipeline's.

---

## 2. Combat-creature delivery checklist — the exact files you ship

A combat creature is an **animated, rigged, region-tagged, finished-skin** delivery. The contract is
[`external_asset_v2`](../../schema/external_asset.schema.json) (`asset_contract_version: "external_asset_v2"`).
`texture_mode` is **REQUIRED**, `archetype` ∈ `{biped, bird, quadruped, ball, dragon}`.

Ship these files in one package directory (`<id>` = your `variant_id`, `^[a-z0-9_]+$`):

| File | Required | What it is |
|---|---|---|
| `<id>.glb` | ✅ | The mesh. **GLB**, rigged, with the animation clips embedded *(or* pair a clip-less rigged glb with `files.animation_clips`, below). `.obj` is **flat_region-only** and cannot be `textured`. |
| `<id>.asset.json` | ✅ | The `external_asset_v2` manifest — the front door. Declares `archetype`, `rig`, `texture_mode`, `files`, `animations`, `geometry`, `textures`. |
| `<id>_hitbox.json` | ✅ | The **`region_hitboxes` sidecar** (see §2.3). The authoritative per-region world AABB map. |
| `<id>_clips.json` *(or embedded)* | ✅ | An `anim_clips_v1` JSON ([`animation_clips.schema.json`](../../schema/animation_clips.schema.json)) referenced from `files.animation_clips`, **unless** the clips are already embedded in the glb. |
| base-colour PNG (+ optional normal/roughness/metallic) | ✅ for `textured` | The **finished skin**. Listed under `textures`. For `textured` the base colour must ALSO be bound *inside* the glb as `baseColorTexture` (§3). |

### 2.1 The required content (this is what makes it a *combat* creature)

1. **A rig.** Set `rig` to a known profile id (`pipeline/schema/rig_profiles/<rig>.json`); the linter
   rejects an unknown profile (`lint_external_asset.py`). For a humanoid that is `biped_v1`, whose bones
   (`root, hips, spine, chest, head, arm.L/R, forearm.L/R, hand.L/R, thigh.L/R, shin.L/R, foot.L/R`) you
   **must skin to exactly** so the shared animations apply (`schema/rig_profiles/biped_v1.json`). `archetype`
   must agree with the rig family or the bake fails `archetype_rig_mismatch`.

2. **The required + recommended clips.** The *hard* gate (`CLIP_REQUIREMENTS` in `constants.py`,
   enforced by `lint_external_asset.py` → `missing_required_clip`) requires **`idle`** for every archetype.
   A combat creature, however, **must ship the combat set**: **`idle` + `attack` + `hit` + `death`**, with
   **`walk` / `run` recommended**. The engine renderer selects clips by a fixed vocabulary
   (`ENGINE_CLIP_VOCAB`); a clip named off-vocabulary (e.g. `move`, `shoot`, `hurt`, `die`) bakes fine but
   the engine **never selects it and silently falls back to `idle`**. The linter warns and tells you the
   rename (`offvocab_clip_renames`): `move→walk`, `shoot/swing/slash/cast/punch→attack`, `hurt/flinch→hit`,
   `die/ko→death`. Use the canonical names.

3. **A finished skin.** Not a placeholder. For `textured`, a real painted base-colour texture with a real
   UV unwrap. For `flat_region`, a real per-region material `base_color_factor` (a real albedo colour —
   `flat_region` must NOT claim `real_albedo:true`, see `flat_region_real_albedo`).

4. **A `region_hitboxes` sidecar** covering head / torso / arms / legs (+ tail for dragons). This is the
   authoritative region map; it both keeps a single-material art model from being read as a *silent*
   torso fallback **and** is baked into the per-pixel hit-mask (ADR-0036).

### 2.2 `animations` block (manifest)

Each entry is `state → {frames, fps, playback}` with `playback ∈ {loop, once}` (`once` holds the last
frame — death/hit hold their final pose). The pipeline samples each named glb clip into
`frames × 16 directions` (`external_asset.schema.json`). Example combat states:

```json
"animations": {
  "idle":   { "frames": 1, "fps": 1,  "playback": "loop" },
  "walk":   { "frames": 6, "fps": 10, "playback": "loop" },
  "attack": { "frames": 4, "fps": 12, "playback": "once" },
  "hit":    { "frames": 2, "fps": 12, "playback": "once" },
  "death":  { "frames": 6, "fps": 10, "playback": "once" }
}
```

### 2.3 The `region_hitboxes` sidecar (`<id>_hitbox.json`)

This is the **calibration / skin-delta dialect** the bake actually reads for explicit regions
(`bake_asset._explicit_region_path`): a top-level `region_hitboxes` object, each region carrying world-space
`min` / `max` arrays. **≥ 2 regions with valid `min`/`max` are required** or the file is ignored:

```json
{
  "asset_id": "<id>",
  "region_hitboxes": {
    "head":  { "min": [..,..,..], "max": [..,..,..] },
    "torso": { "min": [..,..,..], "max": [..,..,..] },
    "arm_left":  { "min": [..,..,..], "max": [..,..,..] },
    "arm_right": { "min": [..,..,..], "max": [..,..,..] },
    "legs":  { "min": [..,..,..], "max": [..,..,..] }
  }
}
```

> Note: the *verification-only* `hitbox_v1` schema (`schema/hitbox_spec.schema.json`) uses the longer
> `regions`/`aabb_min`/`aabb_max` form for a coarse capsule sanity-check. The **bake-consumed authoritative**
> sidecar is the `region_hitboxes` `min`/`max` form above. See [`examples/`](examples/).

Body regions collapse to the engine's 4-id palette `1=head, 2=torso, 3=arms, 4=legs`
(`REGION_NAMES`/`REGION_KEYWORDS` in `constants.py`); a dragon's wings + forelegs → arms, hindlegs → legs,
tail + trunk → torso.

---

## 3. `flat_region` vs `textured` — when, and the one hard rule

`texture_mode` is REQUIRED, in `{flat_region, textured}` (`external_asset.schema.json`). Both are
first-class, fully-supported deliveries — pick by how the skin is authored, not by "quality":

| | `flat_region` | `textured` |
|---|---|---|
| Skin source | per-region **material base colour** | a **real UV unwrap + painted `baseColorTexture` bound in the glb** |
| UVs / atlas | none needed | **required**, real |
| Mesh format | `.glb` or `.obj` | **`.glb`/`.gltf` only** (`obj_textured_unsupported`) |
| Pre-bake gate | must NOT bind a texture (below) | `glb_texture_probe.texture_capable` must pass before any bake |

**The hard rule (ADR-0037): a `flat_region` delivery must NOT bind a base-colour texture.** Binding a
texture under degenerate UVs (the "flat-via-degenerate-UV-texture" hack — it *looks* textured but bakes
~one texel per material) is rejected at the front door as **`flat_region_bound_texture`** (error,
`lint_external_asset.py`). If you have a real painted skin, declare `texture_mode: textured` with a real
UV unwrap instead. Conversely, declaring `textured` without real UVs + a bound texture fails
`texture_capable` up front (`texture_unbound` / `degenerate_uv`).

`degenerate_uv` is detected by `glb_texture_probe.py`: a per-material UV bbox collapsed to a **point**
(both extents `< 1e-3`), a **line** (one extent tiny), or a **sliver** (area `< 1e-5`).

> Full UV requirements, island layout, power-of-two texture sizes, and the bound-texture probe live in
> [`uv_format.md`](uv_format.md). Calibration colours + the immutable calibration-model numbers live in
> [`calibration_model.md`](calibration_model.md).

### Skin variants

A texture-only variant of an existing base ships as a **skin delta** (`skin_delta.py`): a new
power-of-two PNG + a descriptor pointing at the base. Geometry + UVs + rig + hitboxes are cloned and
proven byte-identical to the base (`geometry_fingerprint`); a smuggled re-model hard-fails
`skin_delta_geometry_changed`. See [`examples/`](examples/) and `pipeline/examples/skin_delta/`.

### Calibration models are special and immutable

A **calibration** package is a debug/oracle delivery that paints each region an EXACT colour and is
**never re-modelled**. The colours (`calib_v1`, `calib_spec.CALIBRATION_COLORS`, sRGB 0..255) are:

| region | colour | sRGB |
|---|---|---|
| head | red | `216,38,38` |
| torso | grey | `130,130,130` |
| arm/wing **left** | green | `42,196,64` |
| arm/wing **right** | blue | `40,90,224` |
| legs | purple | `150,42,200` |
| tail | orange | `240,138,30` |

The `region_hitboxes` must cover each colour's region. The hard-coded, versioned calibration models
(`calib_spec.CALIBRATION_MODELS`) are reproduced **exactly**:

- **`calib_biped_v1`**: height 1.80 m, eye 1.62 m, footprint 0.40 m, mass 75 kg, regions
  `[head, torso, arm_left, arm_right, legs]` (no tail).
- **`calib_dragon_v1`**: height 2.128 m, eye 1.638 m, footprint 1.55 m, mass 862 kg, regions
  `[head, torso, arm_left, arm_right, legs, tail]` (wings = arm_left/right).

Calibration colours and numbers, and how the oracle verifies them, are detailed in
[`calibration_model.md`](calibration_model.md).

---

## 4. How the pipeline will judge your delivery

Your package runs through a **front-door lint → bake → build-log gate**. The single vocabulary of
checks lives in `pipeline/tools/error_codes.py`; the full table with every severity and trigger is in
[`gate_reference.md`](gate_reference.md). The short version:

1. **Front door** (`lint_external_asset.py`, no Blender): schema; files exist; `rig` is a known profile;
   required clips present (`missing_required_clip`); off-vocab clip warnings; `texture_mode` gate
   (`texture_capable` for `textured`; `flat_region_bound_texture` for `flat_region`). Exit 0 = clean.

2. **Bake** (`bake_asset.py`): orients to +X, samples 16 directions × your clips, projects your
   `region_hitboxes` into the R8 hit-mask, packs the atlas (auto-sharding into per-state pages ≤ 4096 px
   for 8+ state combat characters — ADR-0037), and writes `build_log.json`.

3. **Build-log gate** (`build_log.py`) — the `ok` flag. Key escalations for a **textured non-calibration**
   delivery (ADR-0028): `degenerate_uv` and `region_fallback_torso` become **errors**; a flat/swatch atlas
   is `atlas_colour_rich_low`; a baked-empty direction is `blank_frame`; an oversize page is
   `oversize_atlas_page`. `flat_region` keeps the diagnostics as warnings. An **explicit `region_hitboxes`
   map** keeps `region_fallback_torso` a *warn* (regions are declared, not silently defaulted).

4. **Calibration colour↔hitbox gate** (`calib_color.py`, calibration packages only): projects each region
   hitbox's centre through the bake's per-direction projection, samples the baked colour atlas there, and
   requires it to match the region's expected calibration colour (head=red, torso=grey, L arm/wing=green,
   R=blue, legs=purple, tail=orange). A mismatch (`calib_region_color_mismatch`, error) means the texture,
   UVs, or hitbox disagree. The colour spec + folding live in `calib_spec.py`.
5. **Calibration motion oracle** (`calib_oracle.py`, calibration packages only): proves skinning + animation
   actually took — some region must move across a clip (no dead/rest-pose-baked clips), the intent region
   must be the top mover (walk→legs, attack→arms), and its AABB must travel.

A delivery **passes** when the front-door lint exits 0 **and** `build_log.json` `ok` is `true`. Read
[`gate_reference.md`](gate_reference.md) before you ship.
