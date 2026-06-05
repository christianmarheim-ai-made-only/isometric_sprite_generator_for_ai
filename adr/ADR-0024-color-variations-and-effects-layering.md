# ADR-0024: Sprite Color Variations (Runtime Tint First) + Effects as Separate Layers (Never Baked Into the Unit)

- Status: Proposed
- Date: 2026-06-06
- Blocks: nothing today (uniform tint works now); the palette-mask recolor and the effect-overlay/particle paths are engine-coordinated (an effects/M2A milestone)
- Related: ADR-0012 (effects are renderable sprite variants, not runtime GIFs — this affirms + extends it), ADR-0011 (curated baked variants), ADR-0020 (metallic — shares the "engine has no sprite shader yet" prerequisite), ADR-0006 (R8 region mask, reused for a palette mask), ADR-0021 (M2A socket projection — the effect→unit sync hook); grounding: `docs/metallic_sprites_investigation.md`

## Context

Two adjacent asks:
1. **Color variations** — recolor ONE base creature (a grey ooze) into typed/zoned variants (pink, yellow) without modeling + baking a separate creature per color.
2. **Effects** — spell/shield/aura visuals: a runtime layer on top of the iso sprite, or "cached" by baking modified sprite variants (costlier upfront, claimed cheaper at runtime)?

**Engine reality** (verified in `metallic_sprites_investigation.md`): the engine is a **2D unlit Bevy `Sprite`** renderer. It already sets a **per-sprite `Sprite.color` tint** (a uniform RGBA multiply — `render.rs` uses it today for the player-blue vs neutral-tan placeholder) and draws **per-entity, depth-ordered** sprites. It has **no custom `Material2d`/WGSL shader** and no particle system.

The unifying principle this ADR adopts: **STATIC, per-unit visual identity is recolored/baked into the unit; DYNAMIC or SHARED visuals are a separate layer.** That single line answers both asks and resolves the "cache it vs layer it" tradeoff.

## Decision

### Part A — Color variations

1. **Default = runtime uniform tint. Works today, zero pipeline pixels.** Author recolorable
   creatures **greyscale / desaturated**; the game sets `Sprite.color` per zone/type and the existing
   per-sprite multiply recolors the whole sprite. One atlas serves every color; a "grey ooze → pink in
   zone A, yellow in zone B" is the *ideal* case for this. Authoring note: a multiply only
   colorizes/darkens (never brightens), so author the base **light, high-value grey** so tints read
   vivid.
2. **Pipeline extension = additive DATA, not pixels.** Add an optional `color_variants` (named variant
   → tint RGBA, optionally keyed to a zone/type id) block to the asset + manifest. Additive and
   engine-ignored until consumed — the `hitmask`/`normal` precedent. This is the whole pipeline change
   for the ooze case: emit the recolor *table*, never re-bake the atlas.
3. **Selective recolor = palette-index mask + a sprite shader (DEFERRED, engine-gated).** When uniform
   tint is too blunt (recolor only the body, keep eyes/teeth; or remap a palette non-multiplicatively),
   emit a per-pixel **palette-index mask** (clone the R8 region-mask emitter, ADR-0006) and recolor via
   a per-type LUT in the sprite shader. This needs the engine's **first `Material2d` + WGSL** — the
   *same* prerequisite as ADR-0020 (metallic). The pipeline side (emit the mask) is cheap and can land
   ahead; the engine side waits for that shader.
4. **Baked color variants = last resort.** Only when neither tint nor palette-mask suffices and a
   **small curated** set needs full hand-tuned control (e.g. a hero recolor with bespoke shading).
   Costs N× atlas VRAM / disk / bake time; apply ADR-0011's curated-cap discipline. Do **not** use for
   large or procedurally-typed sets — that is what tint (1) is for.

### Part B — Effects (spells, shields, auras): a separate layer, never baked into the unit

1. **Do NOT bake effects into the character sprite.** Baking multiplies
   `effect_state × unit_state × direction × frame` → combinatorial frame + VRAM explosion; it **freezes**
   the effect's motion into static frames; and it **destroys sharing** (one shield would re-bake onto
   every unit × every state × every direction). For anything dynamic or shared this is strictly worse
   **both** upfront (bake/VRAM) and at runtime (resident VRAM, cache pressure) — the "cheaper at
   runtime" intuition only counts draw calls and ignores the memory + flexibility blowup.
2. **Effects are a separate, depth-composited overlay entity** synced to the unit's anchor/socket. The
   engine already draws per-entity depth-ordered sprites, so an effect is just another entity layered
   over/under the unit — no new core render concept. This **affirms ADR-0012** (effects are renderable
   sprite variants, `variant_class: effect`) and confirms your instinct.
3. **Pre-rendered effect SHEETS vs live particles.** Per ADR-0012, art-directed iso effects are baked
   as their **own** sprite sheets (16-dir where orientation matters, animated) and played as an overlay
   — consistent pixel style, deterministic timing/anchoring, cheap to play, **no new engine tech**.
   Reserve a true **GPU particle system** for high-count stochastic effects (smoke, sparks, dust) a
   sheet can't capture; that is a separate additive engine system, layered the same way.
4. **The dividing line (resolves the tradeoff).** "Bake a modified sprite" is correct **only** for a
   STATIC, PERMANENT, per-unit visual change — and that is a **color variant (Part A)**, not an effect.
   Everything dynamic or shared (spells, shields, status auras, hit flashes) is a **layer (Part B)**.
   So the two halves of this ADR partition cleanly by one test: *is the visual a permanent identity of
   this unit, or a transient/shared overlay?*
5. **Binding an overlay to the unit: a per-creature `core` anchor + automatic depth occlusion.**
   Orbiting / enveloping effects (an orb circling the body, a shield bubble, a status ring) pivot on a
   **`core` / centre anchor recorded per creature** — distinct from the foot/ground anchor the sprite
   is *placed* by. Its **height (z) is per-creature**: a long-legged creature's core sits high (the orb
   floats up around the torso), a stubby creature's sits low (the orb hugs the ground) — pivot on the
   foot anchor instead and the effect circles the *feet*. Author it as an explicit anchor, or derive it
   from the torso-region centroid the hitbox already carries. The effect is then a separate
   depth-sorted entity at `core_xy + horizontal_offset(t)`, and **front/behind occlusion is FREE**: the
   engine's per-entity ground-depth sort (`x+y`) draws the effect *behind* the character on the far
   side — the opaque silhouette hides it — and *in front* on the near side, with **no per-pixel depth
   buffer**. **Caveat:** the depth key ignores height (ADR-0018), so the front/behind separation comes
   from the effect's **horizontal** motion; a purely **vertical** effect (rising straight up through
   the body) produces no depth separation and cannot be occluded this way. Same anchor machinery as a
   held weapon (ADR-0021 socket projection) — a hand-cast spell and a held sword both bind to a
   per-creature point at a per-creature height.
6. **Many effects at once, many instances, and changing counts all scale for FREE — by multiplying
   entities, never by baking.** Three runtime-composition dynamics, each with zero pipeline cost:
   - **Multiple DISTINCT effects simultaneously** (a ring around the legs **and** a trio of fireballs
     at the shoulders) = multiple overlay entities, each bound to a **different named anchor**. The
     socket set a creature already exposes (shoulders, belt/pelvis, hands, back…) provides those
     locations — `core` (B.5) generalizes to *any named socket can host an effect*, each at its own
     per-creature height. Every entity depth-sorts independently, so each occludes correctly on its own.
   - **Multiple INSTANCES of one effect** (the trio) = the engine spawns **one** baked fireball sheet
     **N times** around the anchor, driven by a **SINGLE shared orbit clock** with instances at evenly
     spaced phase offsets (`i · 360°/N`). They rotate as one **rigid, evenly-spaced constellation** —
     they must **not** drift into a line or bunch up, which independent per-orb timers would eventually
     do (and look silly). On a count change (throw one), the survivors **re-space evenly** across the
     new N−1. The pipeline bakes a single sheet; count, spacing, and the shared phase are runtime. Each
     instance is its own depth-sorted entity → some in front of the shoulder, some behind, correctly.
   - **Dynamic count** (throw one → N−1) = pure runtime **spawn/despawn** of effect entities — gameplay
     state, **not baked data**, zero contract impact. (Effect entities batch on the shared effect
     atlas, so the cost is *sprites, not bakes*.)
   **DISCRETE vs CONTINUOUS occlusion:** discrete orbs (fireballs, each a separate entity) wrap
   front/behind for free (B.5). A **continuous loop** (a ring) is a single card at one depth and
   **cannot** wrap — near arc over the legs, far arc behind — under per-entity sort. Render it as a
   **front-arc + back-arc pair** (two entities depth-offset around the anchor) to wrap correctly, or
   accept a whole-ring-at-one-depth for cheap. This is the one place effect multiplicity meets the
   height-ignores-depth caveat (B.5).

## Consequences

### Positive
- Ooze recoloring **ships today** via `Sprite.color` + greyscale authoring; the only pipeline work is
  an additive `color_variants` table, never re-baked pixels.
- Effects stay **shared, dynamic, and memory-cheap**; the combinatorial unit×effect×state explosion is
  avoided entirely.
- Both paths reuse machinery we already have (per-sprite tint, depth-ordered entities, the region-mask
  emitter, ADR-0012's effect renderables) — no speculative engine rebuild.
- **Arbitrary simultaneous effects, multi-instance sets, and changing counts** (a ring + a depleting
  trio of fireballs) cost only entities + spawn/despawn (B.6) — never a re-bake, a new atlas, or a
  contract change.

### Negative
- Uniform tint **cannot selectively recolor** (whole-sprite multiply only); selective recolor is gated
  on the engine's first sprite shader (shared with ADR-0020).
- Layered effects cost **extra draw calls** and need an **effect→unit sync contract** (which socket /
  anchor + depth offset the overlay binds to).
- A true particle system, if wanted, is **net-new engine tech**.

## Open questions

- Does the tint / `color_variants` data live in the **manifest** (pipeline emits it) or purely
  game-side? (additive either way; emitting it keeps the recolor reproducible + reviewable.)
- **Effect→unit binding — resolved to a per-creature `core` anchor (see Part B.5).** Residual: is
  `core` an explicitly authored anchor or derived from the torso-region centroid, and is it **static**
  (rest-pose) or **per-frame**? A static rest-pose `core` is enough for a coarse orbit/aura; a
  hand-tracked effect needs the per-frame socket (ADR-0021).
- **Selective recolor mask:** a dedicated palette-index mask, or reuse the 4-region R8 hitmask? (4
  regions is likely too coarse for arbitrary recolor zones — probably a separate small index mask.)
- Greyscale-authoring convention: do we add a pipeline check/warning that a creature declared
  `recolorable` is actually low-saturation (so tints read), mirroring the build-log detector pattern?
- **Which sockets are effect-bindable**, and do they carry per-anchor orbit defaults (radius, plane,
  instance spacing) as emitted data or purely game-side? (additive either way; B.6.)
- **Continuous-loop effects** (rings/auras that wrap the body) need a front-arc/back-arc split
  convention engine-side (B.6) — define it when the first wrapping effect ships; discrete-orb sets
  (fireballs) need nothing.
