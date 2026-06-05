# ADR-0006: Hitmask Semantics Are Visible Topmost Gameplay Surface

- Status: Proposed
- Date: 2026-06-04
- Blocks: M3 controlled real variants
- Supersedes: none
- Related: ADR-0001 through ADR-0004 hit-region decisions, ADR-0013 M2A combat-surface harness

## Context

The locked contract already establishes a mask-primary hit-region design: the pipeline emits an R8 region-ID mask, boxes are broad-phase, and the engine owns gameplay meaning. The unresolved blocker is what a pixel means when an arm, shield, held weapon, or gear visually covers another body part.

Without a single semantic rule, the exporter, validator, debug overlay, and gameplay code can silently disagree. For example, a shield pixel over the torso could be treated as torso by damage code, shield by selection code, or body by collision code.

## Decision

The v1 hitmask represents the **topmost visible gameplay surface**, not hidden anatomy.

For any frame pixel:

- visible arm over torso emits `arms`
- visible shield over torso emits `shield`
- visible weapon over torso emits `weapon`
- visible gear/backpack/quiver over torso emits `gear`
- visible torso emits `torso`
- transparent/non-gameplay background emits `none`

Any nonzero region may select the owning entity. Region-to-damage interpretation remains engine-owned.

Recommended v1 default gameplay interpretation:

| Region | Selection | Damage default | Body behind blocked? |
|---|---:|---|---:|
| `head` | yes | high/lethal/head damage | yes |
| `torso` | yes | normal body damage | yes |
| `arms` | yes | reduced or non-lethal damage | yes |
| `legs` | yes | reduced/mobility damage later | yes |
| `shield` | yes | shield/block interaction | yes |
| `weapon` | yes | no body damage by default | yes visually; not metric collision |
| `gear` | yes | no body damage by default or future passthrough | yes visually; not metric collision |

## Consequences

### Positive

- The mask answers the same question as the player sees: "what surface did I click or hit?"
- Shield coverage, arm guard poses, and weapon silhouettes become visible and debuggable.
- The exporter can use one z-buffered surface pass for mask production.
- Engine selection can be simple: any nonzero region selects the owner.

### Negative

- A weapon held over the torso blocks torso damage in v1 unless gameplay adds passthrough rules later.
- Large visual gear can hide body regions if designers allow it.
- Very large weapons or capes can make hit behavior feel too defensive unless controlled by asset rules.

## Validation requirements

Before M3, the M2A harness must contain frames where:

- arm covers torso and samples as `arms`
- shield covers torso and samples as `shield`
- weapon crosses body and samples as `weapon`
- gear covers body and samples as `gear`
- visible torso still samples as `torso`

The validator must ensure all mask values are in the allowed palette and boxes bound each region's mask pixels.

## M1/M2 assumption

The included arrow pilot is direction-only. It uses a single simple foreground region to validate mask plumbing, but it does not test combat-surface occlusion.

## M3 review questions

- Do projectiles/clicks need a second body-damage mask that ignores weapons/gear?
- Should `gear` ever pass through to hidden body parts?
- Are large capes/backpacks allowed in v1, or are they postponed until a second mask exists?
