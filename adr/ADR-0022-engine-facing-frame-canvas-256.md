# ADR-0022: Lock 256×256 as the Engine-Facing Logical Frame Canvas

- Status: Proposed — PARKED (recorded for later review; not scheduled, do NOT implement)
- Date: 2026-06-05
- Blocks: nothing today; ratifying it unblocks the `manifest_version`/`contract_hash` bump (Task #21 / D-canvas), the one genuinely-open committed task
- Related: ADR-0015 (arrow-pilot direction-only scope), ADR-0017 (atlas format deferral), ADR-0018 (camera elevation vs height scale); `docs/production_readiness_plan.md` (§3 D-canvas row)

## Context

The pipeline emits a per-frame `frame_canvas` (and, on the multistate path, a
`logical_frame_canvas`) into every manifest. The engine is canvas-agnostic by design: it consumes
whatever `frame_canvas` the manifest declares (ADR-044 loader; no hardcoded engine-side canvas).
That means the canvas is a *contract value*, not engine code — it must be locked by agreement, not
discovered by the renderer.

Today there is a de-facto default that has never been formally ratified:

- `pipeline/tools/constants.py` — `CANVAS = 256`, commented "logical frame canvas (px), the
  engine-facing render size". This is the single source.
- `pipeline/tools/bake.py` — every entry point (`bake`, `bake_character`, `bake_mesh`,
  `bake_character_anim`) takes `canvas_px: int = 256` and the CLI `--canvas` defaults to `256`. All
  production packages (`humanoid_ref`, `humanoid_anim`, the grunt) emit `frame_canvas: [256, 256]`.
- `pipeline/tools/generate_arrow_pilot.py` — `CANVAS = (128, 128)`, emitting
  `frame_canvas: [128, 128]` under `manifest_version: "sprite_manifest_debug_subset_v1"`. This is a
  deliberate **debug subset**, not content: it verifies direction/atlas/anchor/mask plumbing without
  Blender or a real rig.

So 256² is already the production default in code; 128² is an intentionally-exempt debug variant. The
only thing missing is a recorded decision that says so, so the value can be treated as a frozen part
of the contract surface and a future session can ratify it cold.

The follow-through is purely mechanical but **engine-facing** (it touches the contract seam), so it
must not be done silently. Per `docs/production_readiness_plan.md` (D-canvas / Task #21): bump the
`manifest_version`, regen the `contract_hash`, and regenerate the smoke/contract fixtures + committed
reference packages — atomically, in one commit.

## Decision

> Proposed but **not ratified**. This is the recommended stance to ratify later, not an instruction
> to act now.

**Lock 256×256 as the engine-facing logical frame canvas for `game_iso_v1` production content.**
It is already the de-facto production default in `bake.py`/`constants.py`; this ADR makes that a
named contract guarantee rather than an accident of a default argument.

Scope of the lock:

```text
- LOCKED at [256, 256] : every production manifest (sprite_manifest_bake_v1,
                         sprite_manifest_multistate_v1) — frame_canvas and
                         logical_frame_canvas alike.
- EXEMPT  (stays 128²) : the arrow pilot (sprite_manifest_debug_subset_v1). It is a debug
                         variant, not shippable content; ADR-0015 already fences its scope.
```

The mechanical follow-through (to run **atomically in one commit**, only after engine sign-off):

1. Bump `manifest_version` (the production strings — `sprite_manifest_bake_v1` /
   `sprite_manifest_multistate_v1` — to the agreed next version; the debug-subset string is
   untouched).
2. Regenerate `contract_hash`.
3. Regenerate the smoke/contract fixtures and the committed reference packages
   (`humanoid_ref`, `humanoid_anim`, grunt) so byte-reproducibility (`test_references`) holds against
   the new version.

This is low-effort but contract-facing, so it stays parked until the engine team confirms 256² is the
contract canvas.

## Consequences

### Positive

- Turns the de-facto default into a named, reviewable contract constant — no silent drift if someone
  changes `constants.CANVAS`.
- Unblocks the single open committed task (#21 / D-canvas): the version/hash/fixture bump can be done
  cold in one atomic commit.
- The debug-subset exemption is recorded, so 128² in the arrow pilot reads as intentional, not a bug.
- No engine code change — the engine already honors the manifest's declared canvas.

### Negative

- Freezing 256² now is a commitment; a later need for a larger canvas (very tall creatures, higher
  detail) would mean another version bump + full reference regen.
- The `manifest_version` bump invalidates every committed reference and fixture in the same commit;
  if not done atomically, `test_references` / Gate-1 go red mid-tree.
- Locks one canvas for all variants — if a future variant class wants a different logical size, this
  ADR would have to be widened or superseded.

## Open questions

These are the calls left to the ratifying review (do not answer them here):

- Is **256²** confirmed by the engine team as the logical contract canvas?
- Does the **128² arrow-pilot debug subset stay exempt** (it is a debug variant, not content), or
  should it be normalized too?
- Which **`manifest_version` string** do we bump the production manifests to (and does the bump
  reset `contract_hash` only, or also a `frame_canvas`-specific contract field)?
- Should the lock be one canvas for all production variants, or per-`variant_class` (leaving room for
  a future oversize class without superseding this ADR)?
