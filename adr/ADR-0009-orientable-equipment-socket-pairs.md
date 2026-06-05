# ADR-0009: Orientable Equipment Uses Socket Pairs

- Status: Proposed
- Date: 2026-06-04
- Blocks: M3 weapon users
- Related: ADR-0010 outgoing weapon traces, ADR-0012 effects

## Context

The contract currently keeps sockets positional and frame-local. A single point is enough for simple attachment, but not enough to orient muzzle flashes, weapon trails, projectiles, torches, or slash effects.

Adding full transforms to every socket is more contract surface than v1 needs.

## Decision

Sockets remain positional-only in v1, but orientable equipment must emit socket pairs so the engine can derive a 2D frame-local vector.

Required socket groups:

```text
base character:
  origin
  head_center
  hand_l
  hand_r

melee weapon:
  weapon_grip
  weapon_tip

ranged weapon:
  weapon_grip
  muzzle
  muzzle_back

shield:
  shield_center

two-handed weapon:
  hand_l
  hand_r
  weapon_grip
  weapon_tip or muzzle/muzzle_back
```

Derived vectors:

```text
weapon_vector = weapon_tip - weapon_grip
muzzle_vector = muzzle - muzzle_back
```

Gameplay direction may still use world facing or target vector; socket pairs primarily solve visual alignment.

## Consequences

### Positive

- Keeps v1 socket schema simple.
- Enables visually aligned muzzle flashes, flame effects, weapon trails, and debug overlays.
- Avoids Blender transform compatibility problems across tools.

### Negative

- Socket pairs can become degenerate if authored poorly.
- Roll/twist around the vector is not represented.
- Some complex weapons may need full transforms later.

## Validation requirements

- required sockets exist for equipment class
- paired sockets are non-degenerate in each frame that uses them
- marker socket references resolve
- debug overlay can draw weapon/muzzle vectors

## M1/M2 assumption

The arrow pilot has no weapon equipment sockets. It emits `origin` only.

## M3 review questions

- Do melee trails need multiple weapon-tip samples or only active-window frame samples?
- Should socket coordinates be interpolated between frames for high-speed effects?
- Are full socket transforms needed for thrown objects or rotating VFX?
