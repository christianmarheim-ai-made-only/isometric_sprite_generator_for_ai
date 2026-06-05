# ADR-0016: AI Generation Enters Only Behind the Proven Seam

- Status: Proposed
- Date: 2026-06-04
- Blocks: M4
- Related: ADR-0008 source separation, ADR-0013 M2A harness

## Context

AI 3D generation is empirical. It may produce useful visuals, but topology, hands, weapons, rigging, and animation often need cleanup. The plan already mitigates this by proving the seam with placeholders and controlled input before generation enters.

## Decision

M4 may introduce AI only after M1, M2, M2A, and M3 controlled variants pass.

Default M4 path:

```text
AI concept / rough mesh
  -> manual cleanup and source separation
  -> standard rig / auto-rig with review
  -> manually authored or retargeted clips
  -> rig-bound hit proxies
  -> source validator
  -> Stage 4 export
  -> manifest validator
  -> human review
```

AI motion may be used as reference, but v1 production animation should prefer retargeted library clips or hand-keyed clips until AI motion passes the same source/manifest gates.

## Consequences

### Positive

- AI failures are attributable to generator/source quality, not contract ambiguity.
- The generator remains swappable.
- Cleanup cost becomes a measured production variable.

### Negative

- AI does not accelerate M1/M2.
- Some generated candidates will be rejected.
- Manual cleanup remains part of the pipeline.

## Validation requirements

- AI assets must pass the same source validator as hand-made assets.
- Cleanup time and rejection reason should be logged per candidate.
- No generated asset bypasses hit proxies or lockfile/hash validation.

## M1/M2 assumption

No AI generation is used in the bundled arrow pilot.

## M4 review questions

- Which AI mesh tools are allowed?
- What is the max cleanup time per candidate?
- What rejection rate is acceptable before changing generator strategy?
