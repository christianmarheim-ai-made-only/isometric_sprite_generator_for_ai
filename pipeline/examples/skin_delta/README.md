# Texture-only SKIN DELTA

A **skin delta** is a production skin that re-uses a base model's body. It ships **only**:

1. a new **base-colour texture** (a power-of-two PNG), and
2. a small **`*.skin_delta.json`** descriptor pointing at a **base asset**.

Everything else — geometry, UVs, rig, anchors, world-metrics, and **region hitboxes** — is **cloned
from the base**. This is the "green dragon" case: it is geometrically the calibration dragon wearing a
different skin, so re-shipping (and re-validating) the whole model would be wasteful and error-prone.

## Why this exists / the guarantee

The pipeline must never let a "skin" silently smuggle a re-model. The guard proves the resolved variant
is **geometry + UV byte-identical** to the base (`geometry_fingerprint` = sha256 over every primitive's
POSITION + TEXCOORD_0 + NORMAL accessor bytes). If the swap touches geometry, the apply step hard-fails
(`skin_delta_geometry_changed`).

## Descriptor format

```json
{
  "skin_delta_version": "skin_delta_v1",
  "variant_id": "dragon_green_skin_v3",     // must DIFFER from base_asset_id
  "base_asset_id": "dragon_calibration_v3",
  "base_glb": "dragon_calibration_v3.glb",  // resolved under the base package dir
  "base_color": "dragon_green_basecolor.png", // resolved next to this descriptor; pow2 in {512,1024,2048,4096}
  "real_albedo": true,                       // a real painted skin (NOT a calibration/debug skin)
  "archetype": "dragon"
}
```

## Run it

```bash
# 1) GUARD — prove this is a clean texture-only change (no Blender needed)
python pipeline/tools/skin_delta.py validate  <descriptor.skin_delta.json> <base_pkg_dir>

# 2) RESOLVE — clone the base glb, swap in the new texture, clone the base's region hitboxes,
#    and synthesize a clean external_asset_v2 manifest (Blender)
python pipeline/tools/skin_delta.py apply     <descriptor.skin_delta.json> <base_pkg_dir> <out_dir>

# 3) BAKE — the resolved <out_dir>/<variant>.asset.json is an ordinary asset
python pipeline/tools/bake_asset.py <out_dir>/<variant_id>.asset.json --out <bake_dir>
```

`apply` writes into `<out_dir>`: `<variant>.glb` (base clone + new skin), `<variant>.asset.json`
(clean v2 manifest, `provenance.texture.skin_delta_of` = base), and `<variant>_hitbox.json` (the base's
authoritative `region_hitboxes`, asset_id rewritten — the regions a single-material art model declares
explicitly rather than via per-region materials).

## The guard's checks (all severity `error`, stage `input`)

| code | when |
|---|---|
| `skin_delta_invalid` | descriptor missing `variant_id` / `base_asset_id` |
| `skin_delta_self_reference` | `variant_id == base_asset_id` |
| `skin_delta_base_missing` | the base glb is not in the base package dir |
| `skin_delta_base_not_capable` | base has **no UVs** or **no bound base-colour texture** to swap |
| `skin_delta_texture_missing` | the replacement `base_color` PNG is absent |
| `skin_delta_texture_invalid` | not a PNG, or dims not power-of-two in {512,1024,2048,4096} |
| `skin_delta_real_albedo_conflict` | `real_albedo:true` **and** `calibration:true` together |
| `skin_delta_geometry_changed` | a shipped variant glb is **not** geometry+UV identical to the base |

## Region note (ADR-0028)

A single-material art model (one `Material_0` over the whole mesh) cannot produce a per-region render
mask, so the bake reports `region_fallback_torso`. For a textured non-calibration asset that normally
**escalates to an error**. But a skin delta clones the base's **explicit authoritative region map**
(`<variant>_hitbox.json` with `region_hitboxes`), so the regions are *declared, not silently defaulted* —
the gate keeps `region_fallback_torso` a visible **warn** and `ok` stays true. The pipeline recognises an
explicit region map (≥2 regions with valid min/max AABBs) via `bake_asset._has_explicit_regions`.

Tests: `pipeline/tools/test_skin_delta.py` (guard + fingerprint) and `pipeline/tools/test_bake_warnings.py`
(the explicit-region downgrade). Both run in the `build.py` gate.
