# Producer Prompt Library — Combat Creature (v3)

A per-stage library of **ready-to-run prompts** a producer AI follows to build ONE combat creature
for the `game_iso_v1` target. Run the stages in order, 0 → 9. Each `stage_N_<slug>.md` is a complete
prompt: the work, the exact constraints, the **gate(s)** that stage must pass, and a crisp
**done-when**. Don't skip a gate — every gate name below is a real code/check in the live pipeline
(`pipeline/tools/error_codes.py`), not a slogan.

## The locked target — `game_iso_v1` (NOT yours to change)

| Property | Value | Source |
|---|---|---|
| Projection | 2:1 dimetric, azimuth **45°**, elevation **30°** | locked camera |
| Directions | **16** (`DIRS`), forward **+X** = direction 0, up **+Z** | `constants.py` |
| Tile / canvas | tile 64×32, frame canvas **256** (`CANVAS`) | `constants.py` |
| Atlas page cap | **≤ 4096 px** per dimension (`MAX_PAGE_PX`) | `constants.py` |

You author a model in metres, +Z up, facing +X. The baker spins it into 16 frames and packs the
atlas. You never set the camera, the canvas, or the page size.

## The delivery contract — `external_asset_v2`

The single front door is `pipeline/schema/external_asset.schema.json`. Two fields gate everything:

- **`texture_mode`** — REQUIRED, one of `{flat_region, textured}`.
  - `flat_region` = per-region **material `base_color_factor`**, **NO** bound texture, no UVs needed.
  - `textured` = a **real UV unwrap** + a **`baseColorTexture` bound in the glb**.
- **`archetype`** — one of `{biped, bird, quadruped, ball, dragon}`. Selects the shared rig + clip
  library. A combat creature is normally `biped` or `dragon`.

## What a COMBAT creature MUST ship

1. a **rig** (`biped_v1`, `dragon_v1`, …) the mesh is skinned to;
2. the required clips **idle + attack + hit + death** (walk/run recommended);
3. a **finished skin** — a real painted albedo (`textured`) **or** material `base_color_factor`
   (`flat_region`); never a flat-grey or swatch placeholder;
4. a **`region_hitboxes` sidecar** named `<variant_id>_hitbox.json`.

## The gates, by stage (all real codes)

| Stage | File | Gate(s) it must clear |
|---|---|---|
| 0 | `stage_0_brief.md` | `texture_mode_declared`, `archetype_matches_rig` |
| 1 | `stage_1_blockout.md` | `forward_axis`, `ground_origin`, `scale`, `upright` |
| 2 | `stage_2_regions.md` | region keyword resolution (no silent `region_fallback_torso`) |
| 3 | `stage_3_uv.md` | `degenerate_uv`, `uv_overlap`, `has_bound_tex` (textured) |
| 4 | `stage_4_skin.md` | `flat_region_no_bound_texture`, `flat_region_no_real_albedo`, `base_color_source`, `atlas_colour_rich` |
| 5 | `stage_5_rig.md` | `required_bones_present`, `all_parts_weighted`, `max_4_influences` |
| 6 | `stage_6_clips.md` | `required_clips_present`, `clip_vocab`, `loop_continuity` |
| 7 | `stage_7_hitboxes.md` | `regions_present`, `no_region_fallback`, calibration-colour agreement |
| 8 | `stage_8_selfcheck.md` | `texture_capable` + full `lint_external_asset` (front-door) |
| 9 | `stage_9_package.md` | `no_blank_frames`, `atlas_page_size`, `ok_agreement` (bake `ok=true`) |

## Mode-aware escalation (read before you start) — ADR-0028

For a **`textured`, non-calibration** delivery the diagnostic warnings become **ERRORS** (they flip
`build_log.ok` to false):

- `degenerate_uv` (UVs collapsed to a point/line — a fake "texture") → **error**;
- `region_fallback_torso` (a material matched no region keyword → silently defaulted to torso) →
  **error**, *unless* you ship an explicit authoritative `region_hitboxes` map (≥2 regions with valid
  `min`/`max`), which is exactly the Stage 7 sidecar;
- the colour atlas must be **rich** (`atlas_colour_rich`), not a baked-flat swatch.

`flat_region` keeps these as warnings. **Calibration** packages bypass escalation (their debug
colours are intentional). Don't try to dodge a gate with the **flat-via-degenerate-UV-texture hack**:
ADR-0037 `flat_region_bound_texture` rejects a `flat_region` delivery that binds a base-colour texture.

## Calibration colours — `calib_v1` (only when building a calibration/oracle model)

If (and only if) you build a calibration model, paint each region the **EXACT** sRGB and reproduce the
**immutable** world metrics. A calibration model is never re-modelled.

| Region | Colour | sRGB 0..255 |
|---|---|---|
| head | red | 216, 38, 38 |
| torso | grey | 130, 130, 130 |
| arm/wing LEFT | green | 42, 196, 64 |
| arm/wing RIGHT | blue | 40, 90, 224 |
| legs | purple | 150, 42, 200 |
| tail | orange | 240, 138, 30 |

| Calib model | height | eye | footprint r | mass | regions |
|---|---|---|---|---|---|
| `calib_biped_v1` | 1.80 m | 1.62 m | 0.40 m | 75 kg | head, torso, arm_left, arm_right, legs |
| `calib_dragon_v1` | 2.128 m | 1.638 m | 1.55 m | 862 kg | head, torso, arm_left, arm_right, legs, tail |

`calib_color.py` verifies that each hitbox region's centre samples the expected colour — proving the
texture, the UVs, and the hitbox all agree. Folding rules (anatomy name → colour key) live in
`pipeline/tools/calib_spec.py` (`wing_left` → `arm_left`, `jaw`/`horn` → `head`, …).

## Tools you'll run

- `pipeline/tools/glb_texture_probe.py` — `texture_capable(glb)`; the textured front-door probe.
- `pipeline/tools/lint_external_asset.py` — the full manifest linter (Stage 8).
- `pipeline/tools/bake_asset.py` — production bake + `build_log.json` (Stage 9).
- `pipeline/tools/calib_oracle.py` — proves skin + anim are VERIFIED-APPLIED (clip motion).
- `pipeline/tools/hitbox_from_mesh.py` — derive a hitbox sanity-check from geometry.

Read those files for exact behaviour. Do not invent gate names.
