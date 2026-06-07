# Model Producer Delivery Spec — Compiled Improvement Addendum

# Snippet 01 — Versioning and Contract Status

**Suggested location:** replace or extend the top metadata block.

```yaml
producer_spec_version: model_producer_delivery_spec_v1
status: Accepted
effective_date: 2026-06-07
compatible_schema_versions:
  external_asset: external_asset_v2
  animation: anim_clips_v1
  hitbox: hitbox_v1
  preflight: producer_preflight_v1
  verification: verification_report_v1
supersedes:
  - docs/modeling_the_body.md
  - docs/texturing_the_body.md
  - docs/external_asset_contract.md
binding_scope:
  - model producer package handoff
  - self-verification before handoff
  - sprite-pipeline intake validation
```

## Rule

Once this spec is accepted, a model package is complete only when it satisfies this versioned producer contract.

Older tutorial docs remain useful background, but conflicting rules in older docs lose to this producer spec.

## Rationale

Producer AIs and automated linters need one stable target. “Proposed” is fine during planning, but package generation should target a versioned, accepted, schema-backed contract.


---

# Snippet 02 — Canonical Package Tree

**Suggested location:** after section `1.1 The file set of a package`.

## Canonical folder layout

Every package should use this structure unless the asset is explicitly static and flat-region only.

```text
<variant>/
  <variant>.glb
  <variant>.asset.json
  <variant>_anim.json
  <variant>_hitbox.json
  <variant>_spell_orbits.json
  <variant>_basecolor.png              # only if sidecar texture is actually bound by GLB
  <variant>_materials.json             # optional producer metadata
  <variant>_sockets.json               # optional producer/runtime metadata
  <variant>_physical_metrics.json      # optional producer/runtime metadata
  preflight_report.json
  verification_report.json             # produced by bake/verify where available
  build_log.json                       # produced by bake where available
  contact_sheets/
    <variant>_color_sheet.png
    <variant>_hit_sheet.png
  source/
    README.md
    generator_or_source_notes.md
```

## Producer-authored vs bake-produced

Producer-authored files:

```text
<variant>.glb
<variant>.asset.json
<variant>_anim.json
<variant>_hitbox.json
<variant>_spell_orbits.json
preflight_report.json
```

Bake-produced files:

```text
verification_report.json
build_log.json
contact_sheets/*
```

A package may include bake-produced files if the producer ran the self-verify gate before handoff.


---

# Snippet 03 — Texture Richness Thresholds

**Suggested location:** section `3. Stage UV + TEXTURE`.

## Numeric atlas richness check

For `texture_mode: textured`, the base-color atlas must pass `atlas_colour_rich`.

A texture passes when all checks are true:

```yaml
atlas_colour_rich:
  quantized_unique_rgb_4bit_min: 64
  rgb_entropy_bits_min: 3.0
  largest_single_colour_fraction_max: 0.65
  non_background_pixel_fraction_min: 0.20
```

## Calibration exception

Calibration textures intentionally use clean flat debug colours. They must declare:

```json
{
  "texture_mode": "calibration_textured",
  "calibration_texture": true,
  "real_albedo": false,
  "debug_region_legend": "<variant>_debug_region_legend.json"
}
```

or, if schema keeps only two texture modes:

```json
{
  "texture_mode": "textured",
  "provenance": {
    "texture": {
      "calibration_texture": true,
      "real_albedo": false
    }
  }
}
```

## Rule

A calibration waiver may bypass `atlas_colour_rich`, but it must not set `real_albedo: true`.

## Rationale

This catches fake textured deliveries that bind a flat swatch grid or one-colour map while preserving the valid use case of high-contrast debug textures.


---

# Snippet 04 — Reject OBJ + Textured

**Suggested location:** section `1.2 The texture_mode declaration`.

## Rule

Reject this combination at linter/intake time:

```text
files.mesh endswith ".obj" AND texture_mode == "textured"
```

## Error code

```text
obj_textured_unsupported
```

## Message

```text
OBJ delivery is allowed only for static flat_region assets. 
A textured package must use GLB/GLTF with real UVs and a bound baseColorTexture.
```

## Rationale

OBJ support is useful for simple static flat-region assets, but textured acceptance requires glTF material binding and UV validation.


---

# Snippet 05 — UV Overlap and Mirroring

**Suggested location:** section `3. Stage UV + TEXTURE`.

## Rule

UV islands should be non-overlapping unless mirroring is intentional and declared.

```yaml
uv_overlap:
  different_region_overlap_ratio_max: 0.02
```

Intentional mirroring must be declared:

```json
{
  "provenance": {
    "texture": {
      "mirrored_uv_regions": [
        ["arm.L", "arm.R"],
        ["leg.L", "leg.R"]
      ]
    }
  }
}
```

## Calibration rule

Calibration models must not mirror left/right regions unless the colors remain distinguishable after bake.

For example, a calibration biped cannot mirror:

```text
left arm = green
right arm = yellow
```

onto the same UV area.

## Rationale

Mirroring can be valid for production art, but it is dangerous for calibration assets because it can hide left/right mapping errors.


---

# Snippet 06 — Required Texture Provenance Block

**Suggested location:** section `8. The asset manifest`.

## Required block for textured packages

For `texture_mode: textured`, the manifest must include:

```json
{
  "provenance": {
    "texture": {
      "texture_mode": "textured",
      "has_bound_tex": true,
      "real_albedo": true,
      "basecolor_sha256": "<sha256>",
      "embedded_image_count": 1,
      "sidecar_image_count": 0,
      "uv_coverage_ratio": 0.73,
      "degenerate_uv_materials": [],
      "uv_repaired": false,
      "flat_fallback": false,
      "calibration_texture": false,
      "waiver_id": null
    }
  }
}
```

## Field meanings

- `has_bound_tex`: true only when the GLB material has a real `baseColorTexture` binding.
- `real_albedo`: true only for actual painted art, not calibration/debug colours.
- `basecolor_sha256`: hash of the embedded or sidecar base-color image.
- `uv_coverage_ratio`: fraction of UV area covered by non-degenerate islands.
- `degenerate_uv_materials`: names of materials with collapsed UV area.
- `uv_repaired`: true only if an automated UV repair path modified the package.
- `flat_fallback`: true if the asset baked as flat despite claiming textured.
- `calibration_texture`: true only for debug/oracle assets.

## Rule

`texture_mode: textured` with `has_bound_tex: false` is invalid.

`real_albedo: true` with `calibration_texture: true` is invalid.

`flat_fallback: true` requires a waiver.


---

# Snippet 07 — Waiver Policy

**Suggested location:** after the self-verify gate or in a new `Waivers` section.

## Waiver block

```json
{
  "waivers": [
    {
      "waiver_id": "WAIVE_TEXTURE_RICHNESS_0001",
      "code": "atlas_colour_rich_low",
      "reason": "Calibration texture intentionally uses flat debug colours.",
      "approved_by": "pipeline-owner",
      "created_at": "2026-06-07",
      "expires_at": "2026-07-01",
      "engine_real_albedo": false
    }
  ]
}
```

## Rules

- A waiver downgrades exactly one named check.
- A waiver must not set `real_albedo: true`.
- A waiver must expire.
- A waived check still appears in `verification_report.json`.
- A package with an expired waiver is invalid.
- Waivers are acceptable for calibration/debug assets, not for hiding broken production art.

## Recommended error codes

```text
waiver_missing
waiver_expired
waiver_unknown_code
waiver_attempts_real_albedo_true
```


---

# Snippet 08 — Per-Archetype Clip Requirements

**Suggested location:** section `6. Stage ANIMATION`.

## Canonical clip requirements

### `biped_v1`

```yaml
required:
  - idle
recommended:
  - walk
  - run
  - attack
  - hit
optional:
  - jump
  - fall
  - crouch_idle
  - crouch_walk
  - death
```

### `bird_v1`

```yaml
required:
  - idle
recommended:
  - fly
  - hit
optional:
  - attack
  - death
```

### `quadruped_v1`

```yaml
required:
  - idle
recommended:
  - walk
  - run
  - hit
optional:
  - attack
  - death
```

### `dragon_v1`

```yaml
required:
  - idle
recommended:
  - walk
  - run
  - attack
  - hit
  - fly
optional:
  - jump
  - fall
  - death
```

### `ball_v1`

```yaml
required:
  - idle
recommended:
  - roll
  - hit
optional:
  - attack
  - death
```

## Vocabulary note

If the engine vocabulary does not yet include `death`, then either:

1. add `death` to the engine vocabulary, or
2. remove `death` from load-bearing verification gates.

Do not gate on clips the engine cannot select.


---

# Snippet 09 — Calibration Package Rules

**Suggested location:** new section after `The gold-standard worked examples`.

## Calibration packages

A calibration package exists to prove model orientation, UV placement, skinning, animation, and hit-region alignment.

Calibration packages must include:

```text
<variant>.glb
<variant>.asset.json
<variant>_anim.json
<variant>_hitbox.json
<variant>_debug_region_legend.json
<variant>_skin_binding.json
<variant>_texture_regions.json
preflight_report.json
```

## Required states

Every calibration fixture should include:

```text
idle
one movement clip:
  biped/quadruped/dragon: walk or run
  bird: fly
  ball: roll
hit
calibration_pose
```

## Required metadata

```json
{
  "calibration": {
    "enabled": true,
    "palette": "CALIB_RGB",
    "debug_region_legend": "<variant>_debug_region_legend.json",
    "skin_binding": "<variant>_skin_binding.json",
    "texture_regions": "<variant>_texture_regions.json",
    "real_albedo": false
  }
}
```

## Rules

- Calibration color pass uses `CALIB_RGB`.
- Region/HIT pass still uses canonical `REGION_RGB`.
- One fixture per rig archetype is required.
- Symmetric/radial props may be exempt from front/back distinctness.
- Calibration textures may bypass richness only through the calibration exception.


---

# Snippet 10 — Front/Back Distinctness Metric

**Suggested location:** section `2. Stage GEOMETRY`.

## Metric

```text
front_back_distinctness_score =
  mean_abs_rgb_difference(
    color_sheet.direction_N,
    color_sheet.direction_N_plus_8,
    silhouette_union_mask
  )
```

## Pass threshold

```yaml
front_back_distinctness:
  mean_abs_rgb_difference_min: 8.0
  edge_ssim_max: 0.92
```

A non-radial body passes when either:

```text
mean_abs_rgb_difference >= 8.0
```

or:

```text
edge_ssim <= 0.92
```

## Exemptions

```json
{
  "radial_symmetric": true,
  "front_back_distinctness_exempt": true
}
```

Valid examples:

```text
ball_v1
orb_v1
radial explosion core
```

## Rationale

This turns “front and back must be visually distinct” into a testable requirement instead of an eyeball-only guideline.


---

# Snippet 11 — Flat Region Clarifications

**Suggested location:** section `1.2 The texture_mode declaration`.

## Rules for `flat_region`

```text
flat_region packages MAY omit UVs.
flat_region packages SHOULD NOT include a texture atlas unless it is a debug/calibration artifact.
flat_region packages MUST use region-keyworded material names.
flat_region packages MUST use non-default, non-grey material base colors.
flat_region packages MUST NOT claim real_albedo: true.
```

## Rule for sidecar images

A sidecar image in a `flat_region` package is treated as documentation/debug reference only unless it is bound in the GLB material.

## Rationale

Flat-region is a legal delivery mode. Producers should not add fake UVs, fake atlases, or orphan images just to make the package appear more complete.


---

# Snippet 12 — Required Producer Preflight Report

**Suggested location:** after section `1.4 Delivery contract — pass/fail checklist`.

## Required file

Every delivered package must include:

```text
preflight_report.json
```

## Purpose

The producer preflight report records the checks the producer ran before handoff. It is not a substitute for the receiving pipeline’s verification; it proves the package was not handed off blindly.

## Required shape

```json
{
  "preflight_report_version": "producer_preflight_v1",
  "producer_spec_version": "model_producer_delivery_spec_v1",
  "asset_id": "example_variant",
  "texture_mode": "textured",
  "ok": true,
  "tool_versions": {
    "blender": "4.2.0",
    "pipeline_commit": "unknown"
  },
  "checks": {
    "geometry": { "status": "pass" },
    "texture": { "status": "pass" },
    "rig_skin": { "status": "pass" },
    "animation": { "status": "pass" },
    "hitbox": { "status": "pass" },
    "bake": { "status": "pass" }
  },
  "artifacts": {
    "color_sheet": "contact_sheets/example_variant_color_sheet.png",
    "hit_sheet": "contact_sheets/example_variant_hit_sheet.png",
    "build_log": "build_log.json",
    "verification_report": "verification_report.json"
  }
}
```

## Rules

- Missing `preflight_report.json` means incomplete package.
- `preflight_report.ok == false` means not deliverable.
- A receiving pipeline may rerun all checks and reject stale or inconsistent reports.


---

# Snippet 13 — Add Manifest Examples for Every Archetype

**Suggested location:** appendix or examples section.

## Required examples

The spec should include one minimal manifest for each:

```text
biped_v1
bird_v1
quadruped_v1
dragon_v1
ball_v1
```

## Minimal dragon example

```json
{
  "asset_contract_version": "external_asset_v2",
  "variant_id": "calibration_dragon_v1",
  "archetype": "dragon",
  "texture_mode": "textured",
  "files": {
    "mesh": "calibration_dragon_v1.glb",
    "animation_clips": "calibration_dragon_v1_anim.json"
  },
  "geometry": {
    "up": "z",
    "forward": "+x",
    "unit": "meter"
  },
  "rig": "dragon_v1",
  "region_source": "material_name",
  "animations": {
    "idle": { "clip": "idle", "frames": 4, "fps": 6, "playback": "loop" },
    "walk": { "clip": "walk", "frames": 8, "fps": 10, "playback": "loop" },
    "hit": { "clip": "hit", "frames": 8, "fps": 12, "playback": "once" }
  },
  "world_metrics": {
    "height_world": 8.95,
    "footprint_radius_world": 4.35,
    "eye_height_world": 6.30
  }
}
```

## Rationale

Most drift happens in non-biped assets. Examples for quadruped, dragon, and ball prevent producers from inventing incompatible companion manifests.


---

# Snippet 14 — Instant Rejection Rules

**Suggested location:** near `Anti-patterns` or `Self-verify gate`.

## Instant rejection

Reject a package immediately when any of these are true:

```text
textured + no bound baseColorTexture in GLB
textured + any degenerate UV material
textured + atlas listed but unused by materials
textured + atlas_colour_rich fails without waiver/calibration exception
textured + OBJ mesh
any package + region_fallback_torso warning
any package + declared clip missing
any package + mesh not facing declared forward
any package + min_z significantly below/above 0
any package + referenced file missing
any package + package manifest and actual files disagree
```

## Recommended error codes

```text
texture_unbound
degenerate_uv
orphan_texture
atlas_colour_rich_low
obj_textured_unsupported
region_fallback_torso
missing_clip_rest_pose
forward_axis_mismatch
ground_origin_mismatch
referenced_file_missing
package_manifest_mismatch
```


---

# Snippet 15 — Sidecar Texture Binding Proof

**Suggested location:** section `1.3 What bound means`.

## Rule

A sidecar texture is acceptable only when the GLB material references it and the manifest proves which materials bind it.

```json
{
  "textures": {
    "base_color": {
      "path": "variant_basecolor.png",
      "sha256": "<sha256>",
      "bound_materials": [
        "head_skin",
        "torso_body",
        "arms_wing_L",
        "legs_hind_R"
      ]
    }
  }
}
```

## Validation

The linter/verifier must check:

```text
file exists
sha256 matches
GLB material references the image
all listed materials exist
all textured region materials are listed
```

## Rule

A listed sidecar PNG that is not referenced by the GLB is an orphan and must be rejected for `texture_mode: textured`.


---

# Snippet 16 — Schema Delta Summary

**Suggested location:** implementation appendix.

## `external_asset_v2` required additions

```yaml
required:
  - texture_mode

properties:
  texture_mode:
    enum:
      - flat_region
      - textured

  archetype:
    enum:
      - biped
      - bird
      - quadruped
      - dragon
      - ball

  provenance:
    type: object
    properties:
      texture:
        $ref: "#/$defs/texture_provenance"

  waivers:
    type: array
    items:
      $ref: "#/$defs/waiver"
```

## New sidecar schemas

```text
producer_preflight_v1
verification_report_v1
debug_region_legend_v1
skin_binding_v1
texture_regions_v1
spell_orbit_points_v1
```

## Linter updates

```text
texture_mode required
textured + OBJ rejected
textured requires bound baseColorTexture
textured requires non-degenerate UVs
textured requires atlas_colour_rich unless waived/calibration
archetype must match rig profile
all declared clips must exist or be paired through animation_clips
```


---

# Snippet 17 — Verification Report Shape

**Suggested location:** verification / self-verify section.

## Required file

```text
verification_report.json
```

## Required shape

```json
{
  "verification_report_version": "verification_report_v1",
  "asset_id": "example_variant",
  "ok": true,
  "texture_mode": "textured",
  "stages": {
    "modeling": {
      "ok": true,
      "checks": {
        "scale": "pass",
        "up_axis": "pass",
        "forward_axis": "pass",
        "ground_origin": "pass",
        "front_back_distinctness": "pass"
      }
    },
    "texture": {
      "ok": true,
      "checks": {
        "has_bound_tex": "pass",
        "degenerate_uv": "pass",
        "atlas_colour_rich": "pass",
        "orphan_texture": "pass"
      }
    },
    "skinning": {
      "ok": true,
      "checks": {
        "required_bones_present": "pass",
        "all_parts_weighted": "pass",
        "max_4_influences": "pass"
      }
    },
    "animation": {
      "ok": true,
      "checks": {
        "clip_vocab": "pass",
        "declared_clips_exist": "pass",
        "loop_continuity": "pass",
        "intended_regions_move": "pass"
      }
    },
    "hitbox": {
      "ok": true,
      "checks": {
        "regions_present": "pass",
        "no_region_fallback": "pass",
        "mask_tiles_silhouette": "pass",
        "aabbs_match_masks": "pass"
      }
    }
  },
  "errors": [],
  "warnings": [],
  "waivers": []
}
```

## Rule

`verification_report.ok` must be false if any load-bearing check fails.

`build_log.ok` and `verification_report.ok` must agree.


---
