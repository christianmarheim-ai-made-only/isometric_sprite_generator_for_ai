# game_iso_v1 Pipeline Gate / Error-Code Reference

> **Single source of truth:** `pipeline/tools/error_codes.py` (`CODES` table:
> `code -> (default_severity, stage, verification_check)`). This document is a
> faithful projection of that table plus the *when-it-fires* behaviour read from
> `build_log.py`, `lint_external_asset.py`, `glb_texture_probe.py`, `waivers.py`,
> and `constants.py`. If the code and this table ever disagree, **the code wins** —
> regenerate this doc, do not patch around it.
>
> The `verification_report.json` is a pure projection of `build_log.warnings`
> through this same table, so the two `ok` flags can never drift
> (`verification_build_log_disagree` exists to catch exactly that).

## Locked target (NOT the producer's to change)

`game_iso_v1`: 2:1 dimetric, azimuth 45° / elevation 30°, **16** directions,
forward **+X**, up **+Z**, tile **64×32**, frame canvas **256** (`CANVAS`), atlas
page **≤ 4096 px** per dimension (`MAX_PAGE_PX`).

## Delivery contract (`external_asset_v2`, `schema/external_asset.schema.json`)

- `asset_contract_version` const `external_asset_v2`; `texture_mode` is **REQUIRED**,
  `enum {flat_region, textured}`.
- `archetype` `enum {biped, bird, quadruped, ball, dragon}`.
- Absent legacy `texture_mode` would default to `flat_region` in the linter for
  back-compat, but the v2 schema *requires* it, so a v2 manifest cannot omit it.

## Severities

| severity | meaning |
|---|---|
| `error` | flips `build_log.ok = false` (and verification `ok=false`) — blocks delivery |
| `warn`  | recorded, does not fail `ok` |
| `info`  | provenance note (e.g. `auto_rigged`), never fails `ok` |
| `waived` | an `error` that a **valid** waiver downgraded; still appears, `ok` stays true |

**Stages:** `input | modeling | texture | skinning | animation | hitbox | bake | package`
(the `package` stage label exists in `STAGES`; every code in the table is filed
under one of the other seven — see the per-stage groupings below).

---

## Mode-aware escalation (read this first)

Two normally-`warn` codes become **`error`** when the delivery is
`texture_mode = textured` **and not** a `calibration` package
(`build_log.write_build_log`, the "Output fidelity gate", ADR-0028):

- **`degenerate_uv`** → `error`
- **`region_fallback_torso`** → `error` — *unless* `explicit_regions=True` (the asset
  ships an explicit authoritative `region_hitboxes` map, e.g. a single-material art
  model or a skin delta cloned from such a base). With an explicit region map the
  fallback is *declared, not silent*, so it stays a visible `warn` and a note is
  appended to the detail.

`flat_region` deliveries keep both as `warn` (unchanged). `calibration` packages
bypass escalation entirely (their flat debug colours are intentional). When a
textured non-calibration bake comes out flat across **every** colour page, an extra
**`atlas_colour_rich_low`** `error` is appended (needs unique≥64, entropy≥3.0,
largest≤0.65).

**New ADR-0037 gates:** `flat_region_bound_texture` (texture stage, the
flat-via-degenerate-UV-texture hack) and `blank_frame` (bake stage, a baked
direction/state that rendered empty). Both are `error` by default.

---

## input / package stage

| code | stage | default sev | when it fires | how a producer fixes it |
|---|---|---|---|---|
| `referenced_file_missing` | input | error | A path in `files`/`textures` does not exist relative to the manifest (`lint_external_asset.lint`). | Ship the referenced file, or correct the relative path in the manifest. |
| `package_manifest_mismatch` | input | error | The package manifest disagrees with the files actually present. | Re-sync the manifest with the delivered file set. |
| `texture_mode_missing` | input | error | `texture_mode` is not declared (schema requires it in v2). | Add `"texture_mode": "flat_region"` or `"textured"`. |
| `obj_textured_unsupported` | input | error | `texture_mode=textured` but `files.mesh` ends in `.obj` (`.obj` cannot carry real UVs + a bound `baseColorTexture`). | Deliver a GLB/GLTF with a real UV unwrap + bound `baseColorTexture`, or switch to `flat_region` (the only mode `.obj` supports). |
| `archetype_rig_mismatch` | input | error | The declared `archetype` is incompatible with the declared `rig`. | Pick the rig profile that matches the archetype (e.g. `biped` → `biped_v1`). |
| `preflight_missing` | input | error | The required preflight report is absent from the package. | Run preflight and include its report. |
| `preflight_not_ok` | input | error | The preflight report exists but did not pass. | Fix the issues preflight reported, re-run until OK. |
| `preflight_stale` | input | **warn** | The preflight report is older than the current inputs. | Re-run preflight against the current mesh/clips. |
| `flat_region_real_albedo` | input/texture* | error | A `flat_region` delivery sets `provenance.texture.real_albedo: true` (`lint_external_asset`). | Drop the `real_albedo:true` claim, or declare `texture_mode=textured` and ship a real painted texture. |
| `waiver_missing` | input | error | A waiver names no `code`, or has no `expires_at` (`waivers.validate`). | Give the waiver exactly one `code` and an ISO `expires_at`. |
| `waiver_expired` | input | error | `today >= expires_at` for a waiver (lexicographic ISO compare). | Renew with a future `expires_at`, or fix the underlying issue and drop the waiver. |
| `waiver_unknown_code` | input | error | Waiver `code` is unknown, or is a structural/non-waivable code (only `{atlas_colour_rich_low, degenerate_uv, front_back_indistinct}` may be waived). | Only waive a documented waivable code; fix structural codes for real. |
| `waiver_attempts_real_albedo_true` | input | error | A waiver sets `engine_real_albedo: true` (a waiver must never claim real albedo). | Remove `engine_real_albedo:true` from the waiver. |
| `skin_delta_invalid` | input | error | A texture-only skin-delta variant block is malformed. | Fix the skin-delta block to the documented shape. |
| `skin_delta_self_reference` | input | error | A skin delta references itself as its own base (not a distinct variant). | Point `base` at a different, real base variant. |
| `skin_delta_base_missing` | input | error | The skin delta's declared base variant is not present. | Include the base variant, or correct the base id. |
| `skin_delta_base_not_capable` | input | error | The base variant is not reskinnable (cannot accept a texture-only delta). | Choose a texture-capable base, or deliver the variant as a full asset. |
| `skin_delta_texture_missing` | input | error | The delta's replacement texture file is absent. | Ship the delta texture file. |
| `skin_delta_texture_invalid` | input | error | The delta's replacement texture is not a valid texture. | Replace with a valid image of the expected size/format. |
| `skin_delta_real_albedo_conflict` | input | error | The delta's `real_albedo` claim is incoherent with its base. | Make the delta's albedo claim match the base's mode. |
| `skin_delta_geometry_changed` | input | error | The delta's geometry/UVs differ from the base (a skin delta must be texture-only: geometry + UV identical). | Keep geometry + UVs identical to the base; only the texture may change. |

\* `flat_region_real_albedo` is filed `("error","texture",...)` in `error_codes.py`
but is raised by the **input-stage** linter; it is a texture-fidelity claim checked
at the front door.

---

## modeling stage

| code | stage | default sev | when it fires | how a producer fixes it |
|---|---|---|---|---|
| `forward_axis_mismatch` | modeling | error | The model's baked forward does not resolve to +X (declared `geometry.forward` inconsistent with the mesh). | Set `geometry.forward` to the model's true heading; the baker rotates it onto +X. |
| `ground_origin_mismatch` | modeling | error | The model's origin is not at the ground/footprint plane. | Re-author so the origin sits on the ground contact (feet on z=0). |
| `world_metrics_mismatch` | modeling | error | Authored `height_world` differs from the **measured** baked height by > 25% (`_metrics_mismatch`, tol 0.25) — wrong scale or orientation (e.g. baked lying down). | Fix the model scale/orientation, or correct the authored `world_metrics.height_world`. |
| `non_upright_biped` | modeling | **warn** | A `biped` silhouette is not portrait: median frame aspect > 1.0 **or** > 35% of frames landscape (`_non_upright`) — likely baked lying down / wrong up-axis. (Archetype-gated: only `biped`.) | Stand the model upright on +Z up; re-export so frames are taller than wide. |
| `front_back_indistinct` | modeling | error | The front and back silhouettes are indistinguishable (and the asset is not `front_back_distinctness_exempt`). | Add a distinguishing feature, or set `radial_symmetric` + `front_back_distinctness_exempt` for a truly symmetric prop. *(Waivable.)* |

---

## texture stage

| code | stage | default sev | when it fires | how a producer fixes it |
|---|---|---|---|---|
| `texture_unbound` | texture | error | `texture_mode=textured` but the GLB has no bound `baseColorTexture`/image, **or** no UVs anywhere (`texture_capable`). | Bind a `baseColorTexture` image in the GLB and give every part a real UV unwrap. |
| `degenerate_uv` | texture | **warn** → **error** (textured, non-calib) | A material's UVs are collapsed to a POINT, a LINE, or a sliver (bbox W or H < 1e-3, or area < 1e-5; `glb_texture_probe`). Textured renders flat per-material. | Properly UV-unwrap each part so islands have real 2D area. *(Waivable for a declared-flat debug asset.)* |
| `orphan_texture` | texture | error | A texture/atlas is shipped but is not bound/used by the mesh. | Bind the texture as `baseColorTexture`, or remove the orphan file. |
| `atlas_colour_rich_low` | texture | error | A **textured** non-calibration colour atlas baked flat across **every** page (needs unique≥64, entropy≥3.0, largest≤0.65; appended in `build_log`). | Deliver a real painted texture with genuine colour variation. *(Waivable for a calibration/debug texture.)* |
| `uv_overlap_undeclared` | texture | error | UV islands overlap without being declared (undeclared shared-texel layout). | Declare the intended overlap, or lay out non-overlapping islands. |
| `base_color_linked` | texture | **warn** (never escalates) | A material's Base Color is driven by a node graph (e.g. vertex-colour Mix from a glTF re-import) rather than the Principled default — silent-flat-grey risk; colour was recovered from the upstream constant. | Bake/flatten the base colour to a constant Principled `base_color_factor` and verify the rendered colour. |
| `flat_region_real_albedo` | texture | error | *(See input stage — raised by the linter for a `flat_region` package claiming `real_albedo:true`.)* | Drop the claim or switch to `textured`. |
| `flat_region_bound_texture` | texture | error | **(ADR-0037)** A `flat_region` delivery binds ≥1 base-colour texture — the "flat-via-degenerate-UV-texture" hack (looks textured, bakes ~one texel per part when UVs are degenerate). Raised by `lint_external_asset` via `texture_capable`. | Drop the bound texture (use per-region material base colours), **or** declare `texture_mode=textured` with a real UV unwrap. |

---

## skinning stage

| code | stage | default sev | when it fires | how a producer fixes it |
|---|---|---|---|---|
| `missing_required_bone` | skinning | error | A `*_skin_binding.json` part binds a bone not present in the declared rig profile (`lint_external_asset` static check), or a required bone is otherwise absent. | Bind every part to a real bone name from `schema/rig_profiles/<rig>.json`. |
| `unweighted_part` | skinning | error | A mesh part has no skin weights (would not animate). | Weight every part to the rig. |
| `too_many_influences` | skinning | error | A vertex has more than 4 bone influences (engine cap). | Limit/normalize to ≤ 4 influences per vertex. |
| `auto_rigged` | skinning | **info** | The delivery had no armature and the pipeline auto-rigged it (`rig_from_profile`); the baked glb is pipeline-derived, not the delivered mesh. | None required — provenance note. Ship your own rig if you need explicit control. |

---

## animation stage

| code | stage | default sev | when it fires | how a producer fixes it |
|---|---|---|---|---|
| `missing_required_clip` | animation | error | An **animated** delivery does not declare its archetype's required clip(s). All listed archetypes require `idle` (`CLIP_REQUIREMENTS`). Off-vocab synonyms count as their canonical name. | Declare the required clip(s). **Combat creatures** should additionally ship `attack`, `hit`, `death` (and the recommended `walk`/`run`). |
| `missing_clip_rest_pose` | animation | **warn** (→ error for a required clip) | A declared state's clip is absent from the glb, so the renderer baked the **rest pose** instead of the animation (`build_log`, from `*_meta.json`). | Embed the named clip into the glb (e.g. via `bake_anim_from_json.py`) so it actually animates. |
| `offvocab_clip` | animation | **warn** | A clip is named off the engine vocabulary (`move`/`shoot`/`hurt`/…). It bakes fine but the renderer never selects it and falls back to `idle` (`offvocab_clip_renames`). | Rename to the canonical engine name (`move`→`walk`, `shoot`/`swing`→`attack`, `hurt`→`hit`, …). |
| `loop_discontinuity` | animation | **warn** | A looping clip's first and last poses do not match (visible seam on wrap). | Make the loop's end pose meet its start pose. |

---

## hitbox stage

| code | stage | default sev | when it fires | how a producer fixes it |
|---|---|---|---|---|
| `region_fallback_torso` | hitbox | **warn** → **error** (textured, non-calib, unless `explicit_regions`) | A material name matched no region keyword, so the bake silently defaulted that part to torso (id 2) (`build_log`, from `*_meta.json`). | Name the material with a region keyword (head/torso/arm/leg/wing/tail/…), **or** ship an explicit authoritative `region_hitboxes` map so the regions are declared, not defaulted. |
| `region_missing` | hitbox | error | The baked R8 hitmask has **no** body region at all (all background). | Ensure parts carry region materials so the hitmask decodes 1..4; ship a valid `<id>_hitbox.json`. |
| `calib_region_color_mismatch` | hitbox | error | **Calibration models only** (`calib_color.py`): a region hitbox's centre samples a colour that is closer to a DIFFERENT calibration colour than the one the region must be (e.g. the head samples blue, not red). The texture, the UVs, or the hitbox disagree. | Paint each region its exact calib_v1 colour (head=red, torso=grey, L arm/wing=green, R=blue, legs=purple, tail=orange) and make the `region_hitboxes` box cover that colour. |

---

## bake stage

| code | stage | default sev | when it fires | how a producer fixes it |
|---|---|---|---|---|
| `blank_frame` | bake | error | **(ADR-0037)** A baked direction/state rendered **entirely empty** — its hitmask sub-rect is all background (`_blank_frames`, getbbox()==None). The process must know it baked junk. | Fix the missing geometry / clip / camera so every baked direction renders a silhouette; re-bake. |
| `oversize_atlas_page` | bake | error | An atlas page exceeds `MAX_PAGE_PX` (4096) in a dimension (`_packing`). Note: the baker auto-shards 8+ state characters into per-state ≤4096 pages (ADR-0037), so this fires only when a *single* page is still too big. | Reduce frame/state count or canvas so each page fits ≤4096; rely on per-state paging. |
| `verification_build_log_disagree` | bake | error | The `verification_report.json` `ok` and the `build_log.json` `ok` disagree — a projection bug between the two. | Internal consistency failure — regenerate both from the same `error_codes` table (should never happen by construction). |

---

## Calibration colours (`calib_v1`, `calib_spec.py`) — reference for region/hitbox gates

Exact sRGB (0..255). The `region_hitboxes` sidecar must cover each colour; `calib_color.py`
verifies each hitbox **centre samples the expected colour**, proving texture + UVs + hitbox agree.

| region (canonical key) | colour | sRGB |
|---|---|---|
| head | red | (216, 38, 38) |
| torso | grey | (130, 130, 130) |
| arm_left (left arm/wing) | green | (42, 196, 64) |
| arm_right (right arm/wing) | blue | (40, 90, 224) |
| legs | purple | (150, 42, 200) |
| tail | orange | (240, 138, 30) |

**Hard-coded, immutable calibration models** (reproduce these numbers exactly — a
calibration model is never re-modelled):

| model | height_world | eye_height_world | footprint_radius_world | mass | regions |
|---|---|---|---|---|---|
| `calib_biped_v1` | 1.80 m | 1.62 m | 0.40 m | 75 kg | head, torso, arm_left, arm_right, legs |
| `calib_dragon_v1` | 2.128 m | 1.638 m | 1.55 m | 862 kg | head, torso, arm_left, arm_right, legs, tail (wings = arm_left/right) |

---

## Combat-creature delivery checklist (focus)

A combat creature MUST ship, and each maps to the gate that catches its absence:

1. **A rig** (e.g. `biped_v1`) — else `archetype_rig_mismatch` / `auto_rigged` (the
   pipeline rigs it for you, with a provenance warning).
2. **Required clips** `idle` (gated) + the combat set `attack` + `hit` + `death`
   (`walk`/`run` recommended) — `missing_required_clip` / `offvocab_clip` /
   `missing_clip_rest_pose`.
3. **A finished skin** — a real painted texture for `textured` (else
   `atlas_colour_rich_low` / `degenerate_uv`/`texture_unbound` escalate to errors),
   or material `base_color_factor` for `flat_region` (no bound texture, or
   `flat_region_bound_texture` fires).
4. **A `region_hitboxes` sidecar** (`<id>_hitbox.json`) — else `region_missing`, and
   a keyword-less material trips `region_fallback_torso` (an error for textured
   combatants unless the map is explicit).

---

## Waivers (`waivers.py`)

A waiver downgrades **exactly one** `error`-code to `waived` (ok stays true), must
carry an ISO `expires_at`, must not claim real albedo, and may only target a code in
the allowlist `{atlas_colour_rich_low, degenerate_uv, front_back_indistinct}`. A
waived check still appears in `build_log.warnings` and the verification report, so the
downgrade is always auditable. Malformed/expired/over-broad waivers instead raise the
`waiver_*` errors listed in the input stage.
