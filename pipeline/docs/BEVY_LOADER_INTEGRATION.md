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

Use world yaw (not screen angle). Binning is ROUND-to-nearest, matching the engine
`sprite.rs::direction_index` and the locked contract (`sprite_contract.lock.json`
`facing.runtime_binning`):

```rust
let dir = direction_index(world_angle_radians, n); // round(yaw / (TAU/n)) mod n
```

`n` is the variant's `direction_count`. Frame `i` renders at yaw `i * TAU/n` — the bin
CENTER, never a lower edge. `direction_bin16` is the `n == 16` case; `collapse_bin16`
re-bins a 16-index to a coarser `n`, but prefer `direction_index` on the continuous
facing when you have it.

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
