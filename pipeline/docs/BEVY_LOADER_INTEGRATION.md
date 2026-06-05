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

Every committed reference package (`pipeline/output/arrow_pilot` + `pipeline/reference/humanoid_{ref,anim,blender}`) emits `contract_hash` + `state_contract_version`.

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

## Multi-state + animation

The manifest may declare a top-level `animations` map and per-frame `state` + `frame_index`
(see `docs/multistate_sprite_contract.md`). A frame's full address is the triple
`(state, direction, frame_index)`:

```json
"default_state": "idle",
"animations": {
  "idle":   { "directions": 16, "fps": 1,  "frames": 1, "playback": "loop" },
  "walk":   { "directions": 16, "fps": 8,  "frames": 4, "playback": "loop" },
  "attack": { "directions": 16, "fps": 12, "frames": 3, "playback": "once" }
}
```

- `animations[state].directions` MUST equal top-level `direction_count`.
- Per `(state, direction)`, `frame_index` covers `0..frames-1` uniquely (no gaps/dupes); total
  `frames[]` length == Σ over states of `directions × frames`.
- `default_state` is shown when nothing is playing; omit → `idle` if present, else the first
  state in sorted key order.
- No `animations` block ⇒ a single implicit `idle` state (today's behavior). Fully backward-compatible.

Playback clock (per proxy, client-side; state stays derived at the client edge — no sim/Entity
changes): advance `frame_index` at `fps`; `loop` wraps, `once`/`hold` clamp to the terminal frame.
Map sim signals to a state (motion→walk, action→attack, else `default_state`). The reference
`bevy_reference/src/loader.rs` parses all states, validates coverage, builds the full
`(state,direction,frame_index)` atlas, and exposes the default state's frame 0 (the MIN);
`SpriteVariant::frame(state, dir, frame_index)` looks up any frame.

## Tight-crop sizing

Frames may be tight-cropped (transparent padding trimmed). Size + place from the LOGICAL
(untrimmed) frame, NOT the tight `rect` aspect (`docs/multistate_sprite_contract.md` section 3;
`FrameDef::screen_placement`):

```text
scale        = world_height * HEIGHT_SCREEN_SCALE / logical_frame_canvas.h   // HEIGHT_SCREEN_SCALE = 24
on_screen_w  = rect.w * scale
on_screen_h  = rect.h * scale
tight_offset = trim * scale          // [ox, oy] from the logical top-left
anchor_px    = anchor * scale        // anchor is in LOGICAL frame px; lands on the projected foot
```

`logical_frame_canvas` == `frame_canvas` for uncropped frames (`trim = [0,0]`). Sizing from the
tight `rect` aspect alone MIS-sizes a trimmed frame — always use the logical height for `scale`
and offset the tight region by `trim * scale`.

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
