# ADR-0017: Atlas Compression and Streaming Are Deferred Until Measured

- Status: Proposed
- Date: 2026-06-04
- Blocks: M4/M5 only
- Related: baked variant cap, atlas packing, runtime loader

## Context

The plan intentionally keeps v1 runtime format simple: decoded RGBA8 color and R8 masks, no BC7/KTX2/Basis compression until real assets exist and memory/draw-call behavior is measured. Premature compression work can obscure correctness bugs.

## Decision

M1 through M4 use uncompressed PNG source artifacts and decoded runtime RGBA8/R8. Compression/streaming is postponed to M5 unless M4 measurement proves an earlier hard memory blocker.

Atlas rules remain:

```text
- no rotated packing
- 4px padding + 4px extrusion
- base atlas <= 2048x2048 for production contract
- group commonly co-visible frames for batching after measurement
```

M5 may introduce KTX2/DDS/BC7/Basis/UASTC runtime packages if:

- masks remain bit-exact
- visual parity is reviewed against RGBA8 baseline
- fallback path exists
- memory budget is updated from measurements, not assumptions

## Consequences

### Positive

- Correctness and direction calibration stay easier to debug.
- Masks remain exact in early tests.
- Compression work is driven by real data.

### Negative

- Early working-set memory is larger.
- M4 scale tests may require fewer variants before compression is implemented.

## Validation requirements

- M4 records resident VRAM/texture working set in a representative scene.
- M5 compares compressed output against RGBA8 baseline.
- R8 hitmasks must remain exact.

## M1/M2 assumption

The arrow pilot emits a small uncompressed color atlas and R8 hitmask atlas. Compression is intentionally absent.

## M4/M5 review questions

- Which GPU formats are supported by the target platforms?
- Should color atlases and hitmask atlases have different streaming policies?
- What measured VRAM threshold triggers M5?
