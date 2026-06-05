# ADR-0015: M1/M2 Uses a Direction-Only Arrow Pilot

- Status: Proposed
- Date: 2026-06-04
- Blocks: M1/M2 implementation scope
- Related: ADR-0014 validator/runtime contract

## Context

The immediate goal is to verify direction, yaw-bin, atlas, anchor, manifest, mask, and validator plumbing with the smallest possible asset. Weapon and equipment issues are intentionally not part of this first test run.

The master plan calls for M1 to confirm direction-0-is-East and the diagnostic pair where frame 02 points down and frame 10 points up. It also calls for M2 to prove lockfiles, schema, manifest, mask, anchor, sockets, metrics, and loader/validator behavior.

## Decision

For this iteration, M1/M2 uses a deterministic Python-generated arrow pilot:

- 16 directions
- one frame per direction
- `dir00 = +X / East`
- `dir02` projects straight down on screen
- `dir10` projects straight up on screen
- full 128x128 frame canvas
- anchor `[64,112]`
- no weapons/equipment/surface occlusion
- one simple foreground mask region for plumbing
- one color atlas and one hitmask atlas
- manifest + lockfiles + schema + validator

The arrow is generated with the same 2:1 isometric ground-plane projection convention used by `game_iso_v1`:

```text
screen_x = (world_x - world_y) * 32
screen_y = (world_x + world_y) * 16
```

This implementation is not the final Blender renderer. It is a low-cost harness to confirm engine-facing assumptions before Blender source assets are introduced.

## Consequences

### Positive

- No art/toolchain blocker for the first test run.
- Direction and coordinate bugs can be found immediately.
- Validator and manifest format can be reviewed with concrete files.

### Negative

- Does not prove Blender camera setup.
- Does not test real rig-derived masks, sockets, or body metrics.
- Does not test arms, weapons, shields, gear, effects, animation clips, or root motion.

## Validation requirements

- 16 frames are produced.
- atlas rects are 128x128 with 4px pad/extrusion.
- manifest yaw values equal `dir × 22.5°`.
- `dir02` screen vector is vertical down.
- `dir10` screen vector is vertical up.
- color alpha and hitmask agree on transparent pixels.
- mask values are allowed palette IDs.
- contract hash matches lockfiles.

## Review questions before M3

- Replace Python arrow generator with Blender headless capsule renderer.
- Add M2A combat-surface harness.
- Decide whether the Bevy plugin should live in the engine repo or this pipeline repo.
