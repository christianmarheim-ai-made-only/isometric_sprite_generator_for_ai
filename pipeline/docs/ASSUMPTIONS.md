# M1/M2 Assumptions

These assumptions are safe for the arrow pilot but need review before M3.

## Direction and projection

- World yaw `0` is `+X / East`.
- World yaw increases counterclockwise toward `+Y`.
- Debug projection uses:

```text
screen_x = (world_x - world_y) * 32
screen_y = (world_x + world_y) * 16
```

- Therefore `dir02` (`45°`) points straight down, and `dir10` (`225°`) points straight up.
- This Python implementation is a low-cost direction harness, not the final Blender camera renderer.

## Asset scope

- The arrow pilot is a standalone debug variant.
- It is not a character, not an effect, and not a weapon/equipment surface test.
- The only required socket is `origin`.
- The hitmask uses a single foreground region (`torso`) to exercise mask plumbing.
- `world_metrics` are positive placeholders and have no gameplay meaning.

## Validation scope

- The Python validator is the full M1/M2 gate.
- The Bevy reference snippets are not a complete plugin.
- Runtime integration should assert at least `contract_hash`, `state_contract_version`, dense directions, rect validity, and `eye <= height` when eye height exists.

## Deferred before M3

Review and ratify:

- ADR-0006 visible topmost-surface hitmask semantics.
- ADR-0007 body-only world metrics.
- ADR-0008 source asset separation and hit proxies.
- ADR-0009 socket pairs.
- ADR-0010 marker/socket attack traces.
- ADR-0011 baked variants/no runtime equipment layering.
- ADR-0012 effects as renderables.
- ADR-0013 M2A combat-surface harness.
