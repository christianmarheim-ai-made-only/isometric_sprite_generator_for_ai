# ADR-0020: Metallic / Specular Sprite Materials — Baked-Static for v1; Dynamic Lit Parked

- Status: Proposed — PARKED (recorded for later review; not scheduled, do NOT implement)
- Date: 2026-06-05
- Blocks: nothing (optional/deferred). Phase C dynamic metal would block on the engine gaining a light-direction input it does not have today.
- Related: ADR-0006 (z-buffered topmost R8 pass the mask bake clones), ADR-0011 (baked variants, no runtime layering), ADR-0017 (defer-until-measured tone), ADR-044 (engine, sprite-animation-clips contract co-ownership); source investigation `docs/metallic_sprites_investigation.md`

## Context

Can `game_iso_v1` sprites show a metallic / specular / shiny look, and what does each path cost? The full grounded answer is in `docs/metallic_sprites_investigation.md`; this ADR distills its decisions so a future cold session can ratify without re-deriving.

The one load-bearing fact gating every option: **the engine is fully unlit today.** A whole-repo search found no `PointLight` / `DirectionalLight` / `AmbientLight` / `StandardMaterial` / `Material2d` / `AsBindGroup` / `normal_map` / `specular` / `metallic` / `fragment_shader` in any `.rs`, and **no `.wgsl` files anywhere**. The engine draws Bevy's built-in batched `Sprite` (a textured quad) under `Camera2d` with `Tonemapping::None`; the only per-sprite effect is a flat RGBA tint multiply — a tint, not lighting. There is no light, no normal, no per-fragment shading for a sprite to react to.

Consequence: anything **static** (shine frozen into the baked frames) extends nothing and ships today; anything **dynamic** (a glint that tracks a moving light) must *introduce* the engine's first `Material2d`, first WGSL shader, first multi-texture bind, **and a first light-direction input**, and forfeits Bevy sprite batching. That asymmetry is why the recommendation is sharply phased and most of it is parked.

The pipeline already owns the machinery the cheap paths reuse: the 16 baked directions naturally shift a baked highlight per facing, and the R8 hitmask bake (ADR-0006: z-buffered topmost pass + shelf packer + name→id authoring hook) is a near-exact template for a metalness mask.

## Decision

This ADR consolidates four coupled sub-decisions. Each records the **recommended (proposed-but-not-ratified)** position. **All four are PARKED** — recorded for a future review, not scheduled, do not implement now.

### D1 — Baked-static vs dynamic-lit metal  ·  Recommended: baked-static is the v1 path  ·  PARKED

Baked-static is the v1 path: bake the shine into the color atlas (it is already an authoring affordance — `texturing_the_body.md` step 5, "bake light/form into base color"; optionally flip Workbench's specular-highlight toggle on the existing studio-lit color pass) and/or tune source ramps for a pixel-art metal banding. It **works today, with zero engine change and zero contract change** (the existing flat sprite path plays whatever color atlas it is handed), and the 16 baked directions already shift the highlight per facing so it reads as a consistent material.

Dynamic-lit metal is **deferred** because the engine is fully unlit (verified above): dynamic metal would be the engine's first custom shader + first material + first multi-texture bind + a light direction it does not have, and would forfeit sprite batching. For a stylized iso game, baked is almost certainly sufficient; treat dynamic as a later, light-rig-gated upgrade.

### D2 — Is a single global "sun" light direction acceptable?  ·  Recommended: yes, if dynamic is ever pursued  ·  PARKED

Any dynamic metal needs *some* light input, and the engine has none. For a fixed-camera iso game, a single global "sun" vector (fixed or slowly orbiting) is likely all the dynamic path needs, and is far cheaper than per-light shading. This is the prerequisite for any Tier-6 work and must be confirmed before it. Parked until/unless dynamic metal is on the table.

### D3 — Stylized matcap vs physically-based (Blinn-Phong)  ·  Recommended: matcap, if dynamic  ·  PARKED

If dynamic is pursued, prefer **matcap** (`N.xy` lookup into a painted chrome sphere) over physically-based Blinn-Phong. Both share the one hard prerequisite — a per-direction normal-map atlas — but matcap needs **no light uniform** and only a trivial shader, gives swap-a-sphere art control, and reads as stylized chrome. Blinn-Phong is higher fidelity but needs the D2 light input, a heavier shader, and carries per-pixel shimmer/crawl risk on low-res sprites. Defer physically-lit Blinn-Phong until a real light rig exists; its cost lands before its payoff can. Parked.

### D4 — Emit the R8 metalness mask now, ahead of consumption?  ·  Recommended: yes IF metal is on the roadmap  ·  PARKED

Emit an R8 `atlases.metalness` mask (which pixels are metal / how rough) by **cloning the existing hitmask bake** — same R8 format, same z-buffered topmost pass (ADR-0006), same shelf packer, same name→id authoring hook; it reuses `mask_rect` (color + mask already share placements), so no new per-frame rect. Like `hitmask`, the engine ignores it until ready, so emitting it is **non-breaking in both directions** and unblocks every later selective-shine path (so the shine lights the sword, not the cloth) at near-zero cost. Recommended **yes** if metal is on the roadmap at all — but **still PARKED** per the user; not scheduled.

### Contract note (additive consumer, allow-listed producer)

Two schema files, both additive-friendly; precedent is `atlases.hitmask` (an already-defined optional companion atlas the engine does not consume yet).

- **Engine CONSUMER schema** (`C:\Code\Claude\docs\pipeline\manifest.schema.json`): `additionalProperties: true` on `atlases` (and root / `camera` / `color` / `frames[]`). New `atlases.normal` / `atlases.metalness` are **non-breaking**; serde silently drops unknown fields (`AtlasesDef` declares only `color`). The pipeline can emit them today and the engine ignores them.
- **Pipeline PRODUCER schema** (`pipeline/schema/sprite_manifest.schema.json`): `atlases` is **closed** — `additionalProperties: false` (line 72), `required: ["color","hitmask"]`. A new `normal` / `metalness` key fails validation here until added to `atlases.properties` — **one allow-list line per new atlas** (clone the `hitmask_atlas` $def). This is the single non-additive edit; everything else (paging, per-frame rects, top-level, world_metrics) is open.

Per ADR-044 contract co-ownership: emitting an *unconsumed* atlas (the D4 mask) needs no further ADR — it is the hitmask pattern. Introducing a *consumed* atlas (a lit normal, or a metalness that is actually lit) is a cross-repo amendment and would warrant its own ADR mirroring ADR-044.

## Consequences

### Positive

- A real metal read ships **today** with zero coordination: pure-pipeline baked shine (D1), no engine or contract change. For a stylized/pixel target this is plausibly the ceiling, not just the floor.
- The D4 metalness mask is the best "reuse what we already ship" story — it clones the proven hitmask bake and, being unconsumed, is non-breaking both ways. It unblocks every later selective-shine path (rim sheen, screen-space sweep, matcap-confined spec) at near-zero cost and without committing the engine to anything.
- Parking the whole menu now means a future session can ratify cold: the costs, the phasing, and the exact contract edits are recorded, not re-derived.
- The consumer schema being additive (`additionalProperties: true`) means the expensive coordination is deferred, not blocked — the pipeline can always emit ahead of engine readiness.

### Negative

- Baked-static shine does not track a moving light; per-direction-only. A glint that responds to a unit turn or a game light is out of scope for v1.
- Workbench specular is a single hardcoded studio shine, not PBR — it reads "plasticky," and the Principled `metallic`/`roughness` inputs are still dropped (only base color is read). Convincing brushed metal needs hand-tuned ramps, not the toggle.
- Dynamic metal (Tier 6), if ever pursued, is the engine's first `Material2d` + first WGSL + multi-texture bind + light input, **forfeits sprite batching**, and per-pixel relit speculars can shimmer/crawl on low-res sprites and fight the studio shading already baked into color ("double-lit"). Cost lands before payoff while there is no light rig.
- The producer schema requires one non-additive allow-list line per new atlas — small, but a real coordinated edit, not free.

## Open questions

Calls left to a future review (none blocked on more investigation):

- **Where do production normals come from?** The cheapest *correct* normals live in the numpy software probe (`render3d.py`: per-face normals already computed at line 152, z-buffer at 77/101-104, ~30-40 lines to emit on the existing R8 write pattern). The Blender art path exposes **no clean normal AOV from Workbench**; a production normal atlas likely needs a *new EEVEE/Cycles AOV pass*. Reconciling "numpy owns normals" with "Blender owns the art" is an **open** pipeline question, not solved.
- **Is baked-static actually sufficient for the art target?** (D1) If the target leans stylized/pixel, yes; confirm before paying any shader cost.
- **Is a single global light direction acceptable?** (D2) Must be confirmed before any Tier-6 work — it sets the engine-side scope.
- **Matcap or Blinn-Phong, if dynamic?** (D3) A shader/art-direction choice, not a pipeline one (both need the normal atlas).
- **Emit the metalness mask now?** (D4) Cheap and non-breaking, but parked per the user — does a future session ratify emitting ahead of consumption?
- **Per-direction normal correctness** — does the highlight track the body correctly through the 16 baked views? The main fidelity risk in any dynamic path; genuinely open.
- **First-material cost is an estimate.** `client_bevy/Cargo.toml:18-20` notes a trimmed 2D feature set previously failed to draw sprites — a flag that the custom-material path may surface Bevy-version friction.
