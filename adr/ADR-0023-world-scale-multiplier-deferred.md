# ADR-0023: Per-Variant `world_scale_multiplier` Is Deferred; Measured Height Is Sufficient

- Status: Proposed — PARKED (recorded for later review; not scheduled, do NOT implement)
- Date: 2026-06-05
- Blocks: nothing (optional/deferred — pure art-direction exaggeration, no correctness gap)
- Related: ADR-0018 (amends/closes its open "per-variant scale" question), ADR-0007 (body world metrics exclude equipment), ADR-0017 (defer-until-measured precedent); source investigation `docs/scaling_investigation.md §6` (D6 stub)

## Context

ADR-0018 settled the on-screen sizing chain: the bake renders through the 30° camera
and emits a measured `world_metrics.height_world`; the **engine** owns absolute size via
`render.rs::sprite_size` — drawn **height = `height_world × HEIGHT_SCREEN_SCALE (24)`**,
drawn **width = height × frame_aspect**. That chain is **physically faithful**: a
creature's on-screen size is derived from its literal measured height in world metres.
There is **no correctness gap** to fix.

ADR-0018's M3 review left one question open: *does `height_world × 24` interact with a
per-variant scale for large/small creatures?* `scaling_investigation.md §6` (the D6 stub)
records the same question and explicitly declines to decide it: the only thing on the
table is an **optional art-direction exaggeration** — rendering a creature bigger or
smaller than its literal measured metres for readability (e.g. an M4 roster wanting a
dragon to *read* larger than its true height). This ADR closes that question for now and
parks the exaggeration mechanism so a future session can ratify it cold.

## Decision

**(Recommended, proposed-but-not-ratified.)** Do **not** add a per-variant
`world_scale_multiplier` now.

1. **Measured height is sufficient.** The faithful path —
   `height_world × HEIGHT_SCREEN_SCALE (24)`, width from `frame_aspect` — already
   produces correct relative sizing for every variant from its measured metres. ADR-0018's
   open "per-variant scale" question is closed as **"measured height is sufficient"**: this
   is exaggeration, not correctness, and nothing in the current roster requires it.
2. **Reserve the field name, build nothing.** If exaggeration is ever pursued, the
   mechanism is an **additive manifest field** `world_scale_multiplier`, **default `1.0`**,
   **engine-ignored by default** — the faithful `height_world × 24` path is unchanged. It is
   consulted **only** by an opt-in art-direction pass that elects to multiply drawn size by
   it. Because the default is `1.0` and the engine may ignore it, deferring costs **zero**:
   no re-bake, no engine change, no manifest migration.
3. **Bake-time vs engine-read is left open** (see Open questions). Both remain viable
   precisely because nothing is built — a future session picks the cheaper of (a) a pure
   bake-time scale that bakes a larger/smaller frame with no engine change, or (b) a
   manifest field the engine reads. Recording the field name now does not commit to either.

This follows the ADR-0017 precedent: defer optional work until a real driver (an M4 roster
variant that demonstrably needs exaggeration) exists, rather than building speculative
machinery.

## Consequences

### Positive

- Keeps the sizing contract minimal: one rule (`height_world × 24`, width from aspect), no
  per-variant knobs to validate, document, or get wrong.
- Zero deferral cost: a `1.0` default that the engine may ignore means turning exaggeration
  on later is purely additive — no migration, no re-bake of existing variants.
- Closes ADR-0018's last open sizing question without expanding M3 scope.

### Negative

- No art-direction lever today: a creature reads at exactly its measured height, so a
  variant that should *feel* bigger/smaller than its literal metres cannot be tuned yet.
- The bake-time-vs-engine-read choice (Open questions) is deferred, not resolved — a future
  art pass must still make that call before any exaggeration ships.

## Open questions

- Does any **planned** creature need exaggeration beyond its measured height — i.e. is there
  a concrete M4-roster variant (e.g. a dragon) that must read larger/smaller than its
  literal `height_world`? Until one exists, this ADR stays parked.
- If exaggeration is pursued: **manifest field the engine reads** (`world_scale_multiplier`,
  default `1.0`) **vs. a pure bake-time scale** (bake a larger/smaller frame, no engine
  change). The faithful path is unchanged either way; the choice is about where the
  multiplier lives.
- Interaction with ADR-0018 point 4 (rect-aspect sizing): a bake-time scale changes frame
  pixels but not aspect, so it is cropping-safe; an engine-read multiplier scales drawn size
  only — confirm neither path reintroduces the crop/stretch tension before ratifying.
