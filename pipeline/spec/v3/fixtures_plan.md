# v3 self-test — FIXTURES plan

Drives the example `.json` files + `self_test.py` (authored separately). Every fixture below is
grounded in the real pipeline; the expected codes are the literal strings the enforcing code emits.

## Target & contract (locked — NOT the producer's to change)

- **game_iso_v1**: 2:1 dimetric, azimuth 45° / elevation 30°, 16 directions, forward **+X**, up **+Z**,
  tile 64×32, frame canvas 256 (`constants.CANVAS`), atlas page ≤ 4096 (`constants.MAX_PAGE_PX`).
- **Delivery contract = `external_asset_v2`** (`pipeline/schema/external_asset.schema.json`).
  Required keys: `asset_contract_version` (const `external_asset_v2`), `variant_id` (`^[a-z0-9_]+$`),
  `archetype` ∈ {biped,bird,quadruped,ball,dragon}, `files` (req `mesh`), **`texture_mode`** ∈
  {flat_region, textured}. `additionalProperties:false` at the top level and on `files`.

## Enforcement map (read from the real tools)

| Gate / behaviour | Enforcing tool | Code(s) emitted |
|---|---|---|
| `texture_capable` (real non-degenerate UVs + a bound `baseColorTexture`) | `glb_texture_probe.texture_capable` via `lint_external_asset.lint` | `texture_unbound`, `degenerate_uv` |
| degenerate UV = collapsed to a **POINT** or a **LINE** or a sliver | `glb_texture_probe` (`EPS_EXTENT=1e-3` per-axis, `EPS_AREA=1e-5` area) | `degenerate_uv` |
| flat_region must **not** bind a base-colour texture | `lint_external_asset.lint` (flat_region branch) | `flat_region_bound_texture` |
| orphan atlas (image present, none bound) | `glb_texture_probe` (`bound>0 and len(imgs)>0`) | `texture_unbound` |
| mode-aware escalation (ADR-0028): `degenerate_uv`/`region_fallback_torso` → ERROR for textured non-calibration | `build_log.write_build_log` (`texture_mode=="textured" and not calibration`) | escalated `degenerate_uv` / `region_fallback_torso` |
| `region_fallback_torso` (material matched no region keyword → silently torso) | `build_log` from `meta.region_fallback_materials` | `region_fallback_torso` (warn; ERROR when textured) |
| `base_color_linked` (node-driven base colour → silent-grey risk) | `build_log` from `meta.base_color_linked_materials` | `base_color_linked` (always warn) |
| `blank_frame` (a baked direction rendered empty) | `build_log._blank_frames` (hitmask crop `getbbox() is None`) | `blank_frame` (error) |
| `oversize_atlas_page` (pre-paging) | `build_log._packing` (`max(page)>MAX_PAGE_PX`) | `oversize_atlas_page` (error) |
| required clip present | `lint_external_asset.lint` (`CLIP_REQUIREMENTS`) + `error_codes` | `missing_required_clip` |

Note on **`missing_required_clip`**: `constants.CLIP_REQUIREMENTS["biped"]["required"]` is `["idle"]` — the
*lint gate* only hard-requires `idle`; `attack`/`hit`/`death` are the **combat-creature contract** (walk/run
recommended). The self-test asserts the combat contract directly: a combat delivery missing `attack` must be
rejected. The error string the linter produces for a missing *required* clip is literally prefixed
`missing_required_clip:` (see `lint_external_asset.py` line ~104). For the combat-`attack` case the self-test
checks against the same `missing_required_clip` code via the combat-contract checker; if it asserts purely at
the lint layer, it must drop `idle` from the manifest to trip the built-in gate (documented in the fixture note).

### Calibration colours (`calib_v1`, `calib_spec.CALIBRATION_COLORS`, EXACT sRGB 0..255)

head = red `(216,38,38)`; torso = grey `(130,130,130)`; LEFT arm/wing = green `(42,196,64)`;
RIGHT arm/wing = blue `(40,90,224)`; legs = purple `(150,42,200)`; tail = orange `(240,138,30)`.
The `region_hitboxes` sidecar must cover each colour; the verification gate (`calib_color.py`) samples the
hitbox centre and checks it equals the expected colour, emitting `calib_region_color_mismatch` (error) on
disagreement. The colour spec + region-name folding live in `calib_spec.py`; `calib_oracle.py` is the
separate skinning/motion oracle.

### Immutable calibration metadata (reproduced EXACTLY; never re-modelled)

- `calib_biped_v1`: height 1.80 m, eye 1.62 m, footprint 0.40 m, mass 75 kg,
  regions [head, torso, arm_left, arm_right, legs].
- `calib_dragon_v1`: height 2.128, eye 1.638, footprint 1.55, mass 862 kg,
  regions [head, torso, arm_left, arm_right, legs, tail] (wings = arm_left/right).

---

## (a) POSITIVE fixture — one valid combat-creature delivery

### `pos_biped_flat_combat`

A **flat_region biped** combat creature that MUST lint clean (`lint_external_asset.lint` → `[]`) and bake
with `build_log.ok == true`.

**Ships:**

- `asset.json` (`external_asset_v2`):
  - `variant_id: "pos_biped_flat_combat"`, `archetype: "biped"`, `texture_mode: "flat_region"`
  - `rig: "biped_v1"` (resolves to `schema/rig_profiles/biped_v1.json` — a known profile)
  - `files.mesh: "pos_biped_flat_combat.glb"` (a rigged GLB; **no** bound `baseColorTexture` — flat_region
    shades by per-region **material base colour**)
  - `files.animation_clips: "pos_biped_flat_combat.clips.json"` (`anim_clips_v1`, `rig` matches the asset rig)
  - `animations`: the four required combat clips **plus** `idle` →
    `idle` (loop), `attack` (once), `hit` (once), `death` (once); walk/run recommended (include `walk` loop,
    `run` loop to model best practice). Every entry has `frames>=1`, `fps>0`, `playback∈{loop,once}`.
  - `geometry.forward: "+x"`, `geometry.up: "z"`, `geometry.unit: "meter"`
  - **FINISHED skin** for flat_region = a real **material `base_color_factor`** on every region material (no
    bound texture). `provenance.texture.real_albedo` is **absent/false** (flat_region must not claim
    `real_albedo:true` → else `flat_region_real_albedo`).
- `pos_biped_flat_combat_hitbox.json` — the **`region_hitboxes` sidecar** (`hitbox_v1`,
  `schema/hitbox_spec.schema.json`): `hitbox_spec_version:"hitbox_v1"`, `unit:"meter"`, `world_metrics`
  (height/footprint/eye), and `regions` keyed `head/torso/arms/legs` with ids 1–4 and `aabb_min`/`aabb_max`.

**Must pass:** schema valid; rig known; all declared files exist; clips well-formed and `clips.rig` == asset
`rig`; required clip(s) present; flat_region binds **zero** base-colour textures (no
`flat_region_bound_texture`); no `real_albedo:true`; sidecar schema-valid. Lint result: **`ASSET LINT OK`**.

---

## (b) NEGATIVE fixtures — one per failure mode (minimal asset, must fail with a SPECIFIC code)

Each is the smallest asset that trips exactly one gate. Codes are the literal strings the tools emit.

1. **`neg_uv_point`** — degenerate UV collapsed to a **POINT**.
   Ships: `texture_mode:"textured"` biped + a GLB whose every primitive's `TEXCOORD_0` is a single repeated
   `(u,v)` (UV bbox `w≈0` **and** `h≈0`, so `w<EPS_EXTENT` and `h<EPS_EXTENT`), plus a bound
   `baseColorTexture`. → **`degenerate_uv`** (from `glb_texture_probe.texture_capable`; the linter surfaces it
   as an input error because `texture_mode=textured`).

2. **`neg_uv_line`** — degenerate UV collapsed to a **LINE**.
   Ships: `texture_mode:"textured"` biped + a GLB whose UVs vary on one axis only (e.g. `v∈[0,0.8]`, `u≈const`
   → `w<EPS_EXTENT`, `h` fine, but it still samples a one-texel column; also caught by `w*h<EPS_AREA`), bound
   texture present. → **`degenerate_uv`**.

3. **`neg_texture_unbound`** — orphan / unbound texture.
   Ships: `texture_mode:"textured"` biped + a GLB with **real, non-degenerate UVs** but **no material binds a
   `baseColorTexture`** (image may sit orphaned in the file, or be absent). `texture_capable` returns
   `bound==0` → reason. → **`texture_unbound`**.
   (Schema-distinct sibling `orphan_texture` exists in `error_codes.py` but `texture_capable` reports the
   unbound case as `texture_unbound`; the fixture asserts `texture_unbound`.)

4. **`neg_flat_region_bound_texture`** — the flat-via-texture hack.
   Ships: `texture_mode:"flat_region"` biped whose GLB **binds a base-colour texture** (often paired with
   degenerate per-material UVs). The flat_region branch of `lint_external_asset.lint` sees `bound>0`. →
   **`flat_region_bound_texture`**.

5. **`neg_base_color_linked`** — node-driven base colour (silent-grey risk).
   Ships: `texture_mode:"flat_region"` biped whose material Base Color is driven by a **node graph** (e.g. a
   vertex-colour Mix from a glTF re-import), not the Principled constant. Surfaced at bake via
   `meta.base_color_linked_materials` → `build_log` warning. → **`base_color_linked`** (severity **warn** —
   `error_codes` comment "never error (real grey-bug only)"; the self-test asserts the code is *present as a
   warning*, not that `ok` flips).

6. **`neg_region_fallback_torso`** — textured single-material, no region keywords.
   Ships: `texture_mode:"textured"` (non-calibration) single-material art biped whose one material name
   matches **no** region keyword → bake silently defaults it to torso (`meta.region_fallback_materials`).
   Under ADR-0028 escalation (`texture_mode=="textured" and not calibration` **and** no explicit region map)
   `build_log` flips its severity to **error**. → **`region_fallback_torso`** (escalated to error; `ok=false`).

7. **`neg_missing_attack`** — combat creature missing the `attack` clip.
   Ships: biped flat_region combat delivery with `idle`+`hit`+`death` but **no `attack`** (and no
   attack-synonym: not swing/slash/cast/punch/strike/…). Fails the combat-contract clip check. →
   **`missing_required_clip`** (code prefix the linter emits; see the note above — to trip the *built-in*
   lint gate at the bare-`idle` layer the fixture also omits `idle`, recorded in the fixture note).

8. **`neg_oversize_atlas_page`** — pre-paging oversize page.
   Ships: a manifest whose colour atlas single page (or a `pages[]` entry) has
   `max(size) > MAX_PAGE_PX (4096)` — i.e. a character baked *before* the in-baker per-state sharding
   (ADR-0037) ran. `build_log._packing` returns `over=True`. → **`oversize_atlas_page`** (error).
   (Fixture is a `manifest.json` + (optional) atlas stub, since this gate fires in `build_log`, not the
   front-door linter.)

9. **`neg_blank_frame`** — a baked direction that rendered empty.
   Ships: a manifest + a hitmask atlas PNG where one frame's `mask_rect` crop is **all background**
   (`getbbox() is None`). `build_log._blank_frames` lists it. → **`blank_frame`** (error).

---

## Coverage summary

Positive (1): `pos_biped_flat_combat`.
Negative (9), one per failure mode, with the literal expected code:

| Fixture | Expected code |
|---|---|
| `neg_uv_point` | `degenerate_uv` |
| `neg_uv_line` | `degenerate_uv` |
| `neg_texture_unbound` | `texture_unbound` |
| `neg_flat_region_bound_texture` | `flat_region_bound_texture` |
| `neg_base_color_linked` | `base_color_linked` (warn) |
| `neg_region_fallback_torso` | `region_fallback_torso` (escalated → error, textured) |
| `neg_missing_attack` | `missing_required_clip` |
| `neg_oversize_atlas_page` | `oversize_atlas_page` |
| `neg_blank_frame` | `blank_frame` |
