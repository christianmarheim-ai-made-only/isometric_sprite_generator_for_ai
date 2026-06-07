# external_asset_v2 Delta Notes

This is not a full JSON schema. It is a concise implementation checklist for updating `external_asset.schema.json`.

## Required additions

```yaml
required:
  - texture_mode
```

## New / expanded fields

```yaml
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
  texture:
    texture_mode: string
    has_bound_tex: boolean
    real_albedo: boolean
    basecolor_sha256: string
    embedded_image_count: integer
    sidecar_image_count: integer
    uv_coverage_ratio: number
    degenerate_uv_materials: array
    uv_repaired: boolean
    flat_fallback: boolean
    calibration_texture: boolean
    waiver_id: string | null

waivers:
  array of waiver objects
```

## Required linter behavior

- `texture_mode` missing => error.
- `texture_mode: textured` and `.obj` mesh => error.
- `texture_mode: textured` and no bound baseColorTexture => error.
- `texture_mode: textured` and degenerate UVs => error.
- `texture_mode: textured` and low atlas richness => error unless calibration/waiver.
- `texture_mode: flat_region` and `real_albedo: true` => error.
