# cow_brown_farm_v1

This package contains a generated mesh, texture atlas, source-asset descriptor, animation raw data, hitbox data, physical metrics, sockets, and spell-orbit metadata.

## Contract status
- `*.source_asset.json`, `*_anim.json`, and `*_hitbox.json` are validated against the provided schemas.
- A schema-valid `external_asset_v1` manifest is **not** included for this asset because the current `external_asset_v1` contract only supports archetypes `biped` and `bird`.
- The package therefore ships a custom rig profile (if needed) under `schema_extensions/` and uses `*.package_manifest.json` as the entry point.

## Additional metadata included
- height and eye height
- physical mass/weight
- pelvis spell-orbit ring height and radius
- shoulder spell-orbit ring height and radius
