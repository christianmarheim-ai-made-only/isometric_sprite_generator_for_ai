# ADR-0021: M2A Equipment Layering — Execution Stance (Affirms ADR-0011)

- Status: Proposed — PARKED (recorded for later review; not scheduled, do NOT implement)
- Date: 2026-06-05
- Blocks: nothing (optional/deferred; gated until the first equipped character is needed)
- Related: ADR-0011 (v1 baked equipment variants — this affirms, does NOT supersede it), ADR-0006 (topmost-surface hitmask), ADR-0008 (source asset separation + hit proxies), ADR-0009 (orientable equipment sockets), ADR-0013 (M2A combat-surface harness), ADR-0017 (atlas/memory measurement), and the source investigation `docs/m2a_weapons_gear_review.md`

## Context

ADR-0011 already decided the high-level layering question for v1: equipment is shipped as **baked curated variants**, with **no runtime weapon/equipment layering** (Proposed). That decision stands. It does not, however, record the *execution-detail* calls the M2A review surfaced — why the baked-variant path is cheap, what bounds the variant explosion it warns about, which code is safe to build before the layering fork is committed, and which enforcement gates must stay closed until then.

This ADR captures those details so a future session can ratify them cold. It is a **PARK**: it adds the missing grounding to ADR-0011's stance, it does not re-open or re-decide ADR-0011, and it proposes no work now. Everything here remains gated until the first equipped character is actually needed. The full design matrix lives in `docs/m2a_weapons_gear_review.md`; this ADR records the recommended position, not a ratified one.

## Decision

All items below are **PARKED** (recommended position, proposed-but-not-ratified). They affirm ADR-0011 and do not supersede it.

1. **Affirm ADR-0011's baked-variants-first stance, with the review's grounding.** The baked path reuses the existing single-render z-buffered **topmost-surface occlusion pass for free**: gear modeled into the same scene as the body is rasterized in the one existing depth pass (`render3d.py::_rasterize`, one `zbuf`, `win = inside & (d > reg)`), so correct per-direction gear front/behind ordering — weapon in front of the torso for toward-camera directions, behind it for away-facing directions — **emerges from that one pass with zero extra code**. Record occlusion as **SOLVED / load-bearing**: it is a structural property of baking gear into the single render, never to be re-litigated by future M2A work.

2. **Add the curated-cap rule explicitly.** Bake only an **authored shortlist** of body+gear combinations (the combos the game actually ships) — **never the cartesian product** (N_body × N_weapon × N_shield × N_gear). This is the concrete mitigation for ADR-0011's variant-explosion negative; frame-dedup (≈38–40% byte-identical frames today) compresses each package further.

3. **The 3D→2D socket projection is the D1-independent first code.** Projecting `hand.L`/`hand.R`/`weapon_grip`/`weapon_tip`/`muzzle` bone positions through `render3d.py`'s **existing** camera basis into per-frame `sockets[]` entries (same transform `direction_tip`/`origin` already use: per-direction `rotate_z` → `project_raw` → the frame's `(s, ox, oy)` fit) is needed by **both** D1 forks identically and is **purely additive** (the manifest's per-frame `sockets` is `additionalProperties: true`; the engine ignores keys it does not consume). It is therefore safe to build **before any layering commitment**.

4. **Hold the two enforcement gates closed until M2A is scheduled.** Neither flip happens until M2A is actually scheduled (and, for layering-dependent placement, until D1 is decided):
   - `pipeline/tools/lint_source_asset.py` — move `DEFERRED_REGIONS = {"shield","weapon","gear"}` and `DEFERRED_SOCKETS = {"weapon_grip","weapon_tip","muzzle","muzzle_back","shield_center"}` into the allowed sets (linter policy only; the source schema already permits them).
   - `pipeline/tools/bake.py` — extend the body-only R8 palette in **both** emitters (`_bake_mesh_character`, `bake_character_anim`) to the already-reserved ids `shield:5, weapon:6, gear:7` (ideally via one shared `REGION_PALETTE` constant so the duplicated literals cannot drift; `sprite_contract.lock.json` already lists these ids).

Note: this entire decision remains gated until the first equipped character is needed.

## Consequences

### Positive

- ADR-0011 gains the missing rationale: occlusion is recorded as solved and load-bearing, so no future session re-derives the single most expensive thing the baked path already inherits for free.
- The curated-cap rule turns ADR-0011's open "variant count can grow quickly" negative into a bounded, enforceable policy.
- The socket projection is identified as safe, contract-additive first code — real M2A progress is possible before the D1 layering fork is committed.
- Holding the gates closed keeps the reserved contract (palette ids 5/6/7, region enum, socket grammar) fenced off until intentionally scheduled, so nothing leaks into earlier milestones by accident.

### Negative

- The curated cap must be actively enforced; an unbounded combo list silently reintroduces the variant explosion this ADR is meant to bound.
- Baked variants still multiply frames per shipped combination (states × directions × frame_index × curated combos); dedup compresses but does not eliminate this.
- The mask-semantics question for gear covering the torso (D4) is left open and coupled — equipped variants are not fully specified until it is resolved alongside the layering fork.

## Open questions

These are the calls left to a future review (decided **with** D1, not before it):

- **D1 itself stays the user's call.** This ADR affirms the recommendation (baked-variants-first); ratifying it as the *decision* — and confirming runtime overlay (Option B) is deferred to a later customization milestone — is still a future review's job.
- **D4 mask semantics when gear covers the torso** (`docs/m2a_weapons_gear_review.md §6`, ADR-0006): no-damage-there (single topmost mask) vs. a second under-gear body-region mask vs. engine-side per-region passthrough. Coupled to D1 — resolve in the same pass.
- What is the maximum curated-combo count acceptable before runtime layering becomes necessary (carried forward from ADR-0011)?
- Should the socket projection ship its self-consistency QA gate (projected `weapon_tip` tracks the modeled tip across all 16 directions) before or alongside the gate flips?
