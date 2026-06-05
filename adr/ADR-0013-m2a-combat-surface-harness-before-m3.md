# ADR-0013: Add M2A Combat-Surface Harness Before M3

- Status: Proposed
- Date: 2026-06-04
- Blocks: M3
- Related: ADR-0006 through ADR-0012

## Context

M2 proves the engine-facing seam with a placeholder. M3 uses a controlled real asset. The unresolved blockers around arms, shields, weapons, gear, sockets, markers, and effects should be closed before real art enters, otherwise the first real asset may expose policy disagreement rather than pipeline bugs.

## Decision

Add an explicit M2A gate between M2 and M3.

M2A test asset requirements:

```text
- arm crossing torso
- arm away from body
- shield covering torso
- short sword/spear crossing torso
- weapon tip extending outside body silhouette
- muzzle/staff tip equivalent
- fake pauldron regioned as arms
- backpack/quiver regioned as gear
- head_center socket
- weapon_grip + weapon_tip
- muzzle + muzzle_back
- shield_center
- marker-spawned effect test case
```

M2A machine gates:

```text
- all required sockets exist
- socket pairs are non-degenerate
- origin == anchor
- hitmask values are in palette
- arms, shield, weapon, and gear appear in at least one frame
- body world_metrics ignore equipment proxies
- boxes bound mask pixels and stay inside rect
- weapon pixel reports weapon, not torso
- shield pixel reports shield, not arms/torso
- arm-over-torso pixel reports arms
- marker references a valid socket
```

M2A human gates:

```text
- shield coverage visually blocks body
- arm guard pose reads as arm coverage
- weapon does not feel like a wall
- muzzle flash/flame spawns at expected pixel
- selection works on weapon, shield, gear, and body
- hit-test overlay works at scaled render sizes
```

## Consequences

### Positive

- Turns arms/weapons/equipment into explicit review cases.
- Prevents M3 from becoming a policy debugging session.
- Provides durable regression cases for future generator changes.

### Negative

- Adds one additional gate before real art.
- Requires a purpose-built placeholder beyond the M1/M2 arrow pilot.

## M1/M2 assumption

This bundled implementation stops before M2A. It creates a direction-only arrow pilot and a manifest validator. M2A should be implemented after these files are integrated and before M3.

## M3 review questions

- Is one M2A placeholder enough, or do melee and ranged variants need separate placeholders?
- Should M2A be required in CI for every contract change?
