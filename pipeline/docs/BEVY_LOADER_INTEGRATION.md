# Bevy Loader Integration Notes

The files under `pipeline/bevy_reference/src/` are reference snippets, not a full Bevy plugin. They avoid pinning a specific Bevy version because sprite APIs churn.

## Runtime critical assertions

When loading a sprite manifest, the engine should fail closed if:

- `contract_hash` does not match the engine's contract lockfile (`sprite_contract.lock.json` only; state and variant compatibility are checked separately via `state_contract_version` and the per-variant cross-check, so growing the variant roster does not change this hash).
- `state_contract_version` does not match the engine's pinned state contract.
- requested state/direction/frame is missing.
- a rect lies outside the atlas.
- hitmask rect dimensions differ from color rect dimensions.
- `eye_height_world > height_world` if eye height exists.

## Direction bin

Use world yaw, not screen angle:

```rust
let bin16 = direction_bin16(world_angle_radians);
```

Reduced direction counts collapse from 16 by integer division:

```rust
let dir_n = collapse_bin16(bin16, n);
```

## Anchor conversion

Manifest frame coordinates are top-left origin and +Y down. Bevy custom sprite anchors are center-origin normalized and Y-up.

```text
bevy_anchor.x = anchor.x / frame_width  - 0.5
bevy_anchor.y = 0.5 - anchor.y / frame_height
```

## Hit-test conversion

The scaled render case must include scale:

```text
frame_pixel = screen_offset / render_scale + anchor
```

Where `screen_offset` is measured from the rendered anchor position in screen pixels. The resulting frame pixel is top-left origin, +Y down.
