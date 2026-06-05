# ADR-0012: Effects Are Renderable Sprite Variants, Not Runtime GIFs

- Status: Proposed
- Date: 2026-06-04
- Blocks: M3/M4 effects integration
- Related: ADR-0009 socket pairs, ADR-0010 markers, ADR-0014 validator/runtime contract

## Context

The plan needs flames, muzzle flashes, smoke, and other effects. GIFs are useful previews, but runtime playback should use the same atlas/manifest model as sprites so timing, anchors, batching, and scaling remain deterministic.

## Decision

Runtime effects are sprite variants with `variant_class: effect`.

An effect variant:

- has color atlas frames
- usually has no hitmask and no hitregions
- has an attach-point anchor, not necessarily ground contact
- can be directionless or use N directions
- is spawned by engine-owned marker handling

Examples:

```text
shoot frame 05 marker: fire @ muzzle
  -> spawn muzzle_flash_16dir at parent.muzzle
  -> spawn projectile at parent.muzzle

campfire_loop:
  -> ground anchored effect
  -> no owner hitmask
```

GIF export is allowed for preview only, not for runtime data.

## Consequences

### Positive

- Reuses atlas, manifest, frame timing, anchor, and direction-bin infrastructure.
- Keeps VFX attachment deterministic.
- Avoids runtime GIF decoding and palette/timing issues.

### Negative

- Effects need their own manifests and validation path.
- Socket-attached effects require marker/socket integration.

## Validation requirements

- `effect` variant class has no required hitregions.
- attach socket references resolve where effects are parent-spawned.
- direction count follows the same N ∈ {1,2,4,8,16} collapse rule.
- runtime loader treats missing hitmask as valid for effects only.

## M1/M2 assumption

The arrow pilot has a hitmask to test plumbing, but it is not an effect. Effect support is not implemented in this iteration.

## M3 review questions

- Which v1 effects are directionless vs directional?
- Should effect atlases share packing with character atlases?
- Should socket-attached effects inherit parent direction or use their own facing?
