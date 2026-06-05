# ADR-0007: World Metrics Are Body Metrics; Held Equipment Is Excluded

- Status: Proposed
- Date: 2026-06-04
- Blocks: M3 controlled real variants
- Related: ADR-0005 world metrics, ADR-0006 hitmask semantics, ADR-0008 hit proxies

## Context

The contract requires `height_world` and `footprint_radius_world`, with optional `eye_height_world`, for collision, FOW/LOS, and other engine-side systems. The plan left weapon/gear inclusion open. A literal visual-bound measurement can make spears, bows, shields, backpacks, or torch flames act like collision/occlusion walls.

## Decision

`world_metrics` are measured from body metric proxies only.

Include in body metrics:

- torso, head, limbs, and feet
- worn armor/clothing that closely follows the body silhouette
- semantic body proxy geometry approved for collision/LOS scale

Exclude from body metrics:

- held weapons
- shields
- backpacks, quivers, capes, loose gear
- flames, muzzle flashes, spell VFX, particles
- temporary animation extension poses

`eye_height_world` is derived from a head/eye socket or head bone. If the source has no head/eye socket, omit it and let the engine apply its default rule.

Optional future metadata may report full visual bounds separately:

```json
{
  "world_metrics": {
    "height_world": 1.82,
    "footprint_radius_world": 0.32,
    "eye_height_world": 1.62
  },
  "visual_bounds_world": {
    "height_world": 2.05,
    "radius_world": 1.15
  },
  "equipment_bounds_world": {
    "held_weapon_radius_world": 1.05,
    "shield_radius_world": 0.45
  }
}
```

The engine must use `world_metrics`, not `visual_bounds_world`, for body collision, FOW, and LOS defaults.

## Consequences

### Positive

- Prevents pikes, shields, capes, and backpacks from becoming walls.
- Keeps character collision stable across equipment variants.
- Allows shield/weapon visual coverage through hitmask without polluting movement/FOW metrics.

### Negative

- A large shield may visually extend beyond the body footprint but not affect pathing.
- If future gameplay needs shield-as-cover, that requires a separate engine rule or equipment bounds, not body metrics.

## Validation requirements

- `height_world > 0`
- `footprint_radius_world > 0`
- if present, `eye_height_world <= height_world`
- provenance records body metric proxy source
- source validator rejects held equipment included in body metric proxy

## M1/M2 assumption

The arrow pilot emits tiny positive placeholder metrics only to exercise manifest plumbing. They are not meaningful gameplay metrics.

## M3 review questions

- Should tower shields add a separate cover/occluder profile?
- Should capes/backpacks be disallowed until visual-vs-body bounds are exposed in the engine?
- Should shield bounds become optional equipment metadata for targeting/cover previews?
