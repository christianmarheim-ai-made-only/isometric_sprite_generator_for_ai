# ADR-0010: Outgoing Weapon Damage Is Marker/Socket Driven, Not Pixel Driven

- Status: Proposed
- Date: 2026-06-04
- Blocks: M3 combat variants
- Related: ADR-0006 visible hit surfaces, ADR-0009 socket pairs

## Context

The visual weapon sprite is not a reliable physics object. Weapon pixels vary by frame, camera, scale, and visual style. The manifest should expose geometric facts, but not encode damage values or lifecycle rules.

## Decision

Outgoing attacks are engine-owned and use animation markers plus sockets/traces.

Examples:

```text
melee attack:
  marker melee_active_start @ weapon_tip
  marker melee_active_end   @ weapon_tip
  engine builds swept capsule/arc/cone in world space

ranged attack:
  marker fire @ muzzle
  engine spawns projectile at muzzle socket
  gameplay direction comes from facing/targeting rule
```

The weapon region in the hitmask is for incoming surface hits, selection, and debugging. It does not define outgoing damage volume.

Markers remain data-only: timing and socket references. They do not encode damage numbers, death, despawn, target rules, or state transitions.

## Consequences

### Positive

- Keeps combat simulation deterministic and engine-owned.
- Avoids pixel-perfect weapon collision problems.
- Makes muzzle flashes/projectiles visually align while preserving gameplay control.

### Negative

- Requires engine-side attack trace implementation.
- Requires reliable sockets and markers.
- Debugging needs overlays for markers, socket trails, and active windows.

## Validation requirements

- required markers exist for states that need them
- marker socket references resolve
- socket pair for associated equipment is non-degenerate
- debug overlay can show active attack window and socket trace

## M1/M2 assumption

The arrow pilot has no outgoing attack behavior. It exercises direction, atlas, mask, anchor, lockfile, and manifest validation only.

## M3 review questions

- What is the v1 melee trace primitive: swept capsule, arc, or cone?
- Are active windows frame-based only, or can they use subframe timing?
- Should ranged projectile spawn use socket screen position only for VFX or also world offset?
