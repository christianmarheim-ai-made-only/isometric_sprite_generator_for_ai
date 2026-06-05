# Region Assignment Policy (C2)

How hitmask region IDs are decided and where they come from. **Body-only this
iteration** — `shield`/`weapon`/`gear` are reserved but not authored (see
`docs/next_slices_plan.md` §6). Builds on ADR-0006 (topmost-visible surface) and
ADR-0008 (hit proxies).

## Authoritative source

- **M3+ authoritative hitmask source is `HIT_` proxy geometry**, not the visual
  mesh. The exporter rasterizes the topmost visible `HIT_` proxy per pixel into
  the R8 mask.
- Visual-mesh (`VIS_`) vertex/material tags may drive **debug** overlays but are
  **not authoritative** unless explicitly marked authoritative in the source
  descriptor. This keeps messy AI-generated visual topology out of the gameplay
  surface.
- The arrow pilot (M1/M2) is the one documented exception: it has no `HIT_`
  proxy and paints a single `torso` region directly to exercise plumbing
  (ADR-0015).

## Region vocabulary and palette

The mask is single-channel R8, discrete region IDs, no antialiasing. Palette
(from `sprite_contract.lock.json`):

| Region | ID | This iteration |
|---|---:|---|
| `none` | 0 | active (background) |
| `head` | 1 | active |
| `torso` | 2 | active |
| `arms` | 3 | active |
| `legs` | 4 | active |
| `shield` | 5 | reserved (deferred) |
| `weapon` | 6 | reserved (deferred) |
| `gear` | 7 | reserved (deferred) |

Reserved IDs keep their numbers fixed, so adding equipment later does not
renumber the contract. The validator rejects any mask value outside this palette.

## Semantics: topmost visible gameplay surface

A mask pixel is the **topmost visible gameplay surface** at that pixel, not
hidden anatomy (ADR-0006). For body-only assets that is whichever of
head/torso/arms/legs is visually frontmost. (When equipment returns, a visible
shield over the torso emits `shield`, a held weapon emits `weapon`, etc.)

- Fully transparent color (alpha < 8/255) ⇒ `none` (0). Enforced by the
  validator's alpha→mask-0 rule.
- Selection: any nonzero region selects the owning entity. Region→damage
  interpretation is engine-owned — the pipeline emits geometry, not gameplay
  rules (ADR-0010).

## Proxy → region mapping

- `HIT_<region>[_<side>]` maps to its region ID: `HIT_head→1`, `HIT_torso→2`,
  `HIT_arm_l`/`HIT_arm_r→3`, `HIT_leg_l`/`HIT_leg_r→4`.
- Left/right sides collapse to the same region ID — sidedness is geometry, not a
  separate region.
- Overlapping proxies resolve by visible depth (topmost wins), consistent with
  the topmost-surface rule.

## Boxes (broad phase)

Per-frame `boxes[region]` is the tight AABB that **bounds** that region's mask
pixels — broad-phase only; the mask is the precise test. The validator checks
each box contains its region's pixels and lies inside the frame rect.

## Deferred (this iteration)

`shield`/`weapon`/`gear` regions, and equipment-over-body occlusion cases, are
not authored now (ADR-0009/0010/0011 remain Proposed). The M2A combat-surface
harness (ADR-0013) exercises them before M3 real variants.
