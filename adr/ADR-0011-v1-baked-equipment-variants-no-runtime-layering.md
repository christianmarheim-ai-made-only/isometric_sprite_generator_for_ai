# ADR-0011: v1 Uses Baked Equipment Variants; No Runtime Weapon Layering

- Status: Proposed
- Date: 2026-06-04
- Blocks: M3 scope if game design expects runtime swapping
- Related: ADR-0008 source asset separation, ADR-0017 atlas/memory measurement

## Context

The plan explicitly avoids over-building: v1 uses baked curated variants and no layering. Runtime weapon swapping would require separate overlays, synchronized sockets, per-direction equipment atlases, occlusion rules, and much more review surface.

## Decision

v1 does not support runtime visual weapon/equipment layering.

A body + weapon + shield + gear combination is a baked variant:

```text
soldier_sword_shield
soldier_spear
soldier_bow
soldier_torch
```

The engine consumes the baked variant manifest and does not compose weapons at runtime in v1.

## Consequences

### Positive

- Keeps the first pipeline ratifiable.
- Avoids body/weapon occlusion ordering problems.
- Keeps variant review explicit and capped.

### Negative

- Variant count can grow quickly.
- Character customization is limited in v1.
- The curated variant cap must be enforced.

## Validation requirements

- `sprite_variants.lock.json` lists baked variant IDs.
- M4 scale-up enforces the curated cap.
- Manifest records `equipment_baked: true` for character/equipment variants.

## M1/M2 assumption

The arrow pilot is a standalone debug variant with no equipment. This ADR is included for M3 review.

## M3 review questions

- Does v1 game design require visible weapon changes at runtime?
- What is the maximum number of baked variants acceptable before layering becomes necessary?
- Are cosmetic-only variants allowed to share gameplay identifiers?
