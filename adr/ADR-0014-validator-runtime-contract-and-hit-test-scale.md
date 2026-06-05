# ADR-0014: Validator and Runtime Must Assert Contract, State Version, Coordinates, and Scale

- Status: Proposed
- Date: 2026-06-04
- Blocks: M2
- Related: M2 Stage-0 harness, Bevy loader integration

## Context

The plan identifies silent coordinate/format/hit-test bugs as a risk. Review findings also called out lockfile cross-checks, state contract pinning, boxes validation, hit-test Y orientation, and a scale term for screen-to-frame conversion.

## Decision

The Python validator is the full CI/pre-commit gate. The runtime loader asserts a critical subset so stale or mismatched assets fail closed.

The manifest must include:

- `contract_hash`
- `state_contract_version`
- `variant_id`
- `variant_class`
- state/frame/direction metadata
- atlas image paths and rects
- frame-local anchors/sockets with origin top-left, +Y down

Validator requirements:

```text
- recompute contract_hash from lockfiles
- assert manifest contract_hash matches lockfiles
- assert state_contract_version matches sprite_states.lock.json
- assert manifest states match sprite_variants.lock.json supported_states
- assert frame and direction counts match state lockfile
- assert required sockets are present for variant class/state
- assert marker socket references resolve
- assert image files exist and have expected modes
- assert color/mask rect sizes match
- assert mask values are in palette
- assert boxes bound region pixels and are inside rect
- assert anchor and sockets are inside frame canvas
- assert world metrics are positive and eye <= height when present
- assert diagnostic directions for M1/M2 arrow pilot
```

Runtime critical subset:

```text
- contract_hash match
- state_contract_version match
- dense directions/frames for requested state
- atlas rect dimensions valid
- eye_height_world <= height_world
- mask dimensions equal sprite rect for hitmask variants
```

Hit-test conversion must use +Y-down frame coordinates and include scale:

```text
frame_pixel = screen_offset / render_scale + anchor
```

Bevy anchor conversion must flip Y from frame-local top-left to Bevy's y-up anchor coordinate.

## Consequences

### Positive

- Reduces silent asset drift.
- Keeps CI strict while keeping runtime checks cheap.
- Makes scaled rendering hit-tests explicit.

### Negative

- Validator is intentionally coupled to the lockfile schema.
- Runtime loader must be updated when the manifest contract changes.

## M1/M2 assumption

The bundled Python validator implements this ADR for the arrow pilot subset. The Bevy reference module includes direction, anchor, and hit-test formulas but is not a full Bevy plugin.

## M3 review questions

- Which runtime errors should panic/fail load vs return recoverable errors?
- Should region boxes be derived at load instead of stored in manifest?
- Should image hashes be required in runtime manifests?
