# ADR-0033: Creature-traits seam for uncommon archetypes (cars, horses, eyeless blobs, energy-creatures)

- Status: **Proposed** (seam to BAKE IN NOW — behaviour-preserving, contract-additive)
- Date: 2026-06-07
- Owner: sprite-pipeline
- Related: ADR-0026 (texture_mode), ADR-0030/0031 (calibration + verification), ADR-0024 (effects/colour layering), review snippets 10/11 (radial/flat-region), ARC-0001. Engine repo (C:/Code/Claude) is read-only.
- Note: pipeline ADR numbering; distinct from the engine repo's own ADR space.

## Context

The pipeline today silently assumes a **forward-facing, four-region, opaque biped-ish body**: `forward +X` is required and a front≠back gate fires for every archetype; HIT regions are the fixed set `head/torso/arms/legs` from `constants.REGION_RGB`/`REGION_KEYWORDS`; a material that matches no region keyword falls back to `torso` and warns. That is correct for biped/bird/quadruped/dragon, but it bakes in assumptions that will fight the next wave of creatures the game wants:

- **vehicles** (car, motorbike, skateboard, steampunk airship) — directional but with wheel/rotor/hull "regions" that are not head/torso/arms/legs;
- **horses / mounts** — quadruped variants, but also future ride targets (see ADR-0034);
- **a blob-monster with NO eyes and NO inherent direction** — radially symmetric, so the front≠back gate is a *false positive* (its 16 directions are legitimately near-identical);
- **energy-creatures** — semi-transparent / additive / emissive, no stable opaque silhouette, possibly eyes in multiple directions or none.

We do not want to build any of these now. We want the contract + gates to have **room** so that onboarding one later is *data* (a manifest row + a rig profile + maybe a region-set), not new code or a gate rewrite. The latent ball front/back false-positive (a radial prop failing a directional gate) is the canary: it's already wrong today.

## Decision

Introduce an **archetype → traits** indirection now, behaviour-preserving (the 5 current archetypes reproduce today's exact output), and widen the two gates that hard-code biped assumptions. Nothing renders differently; the seam is contract/data only.

### D1. `archetype_traits.json` (5 current rows = today's behaviour exactly)
A committed table keyed by archetype, each row declaring:
- `has_direction` (bool) — false ⇒ skip the forward-axis requirement and the front≠back gate;
- `is_radial` (bool) — true ⇒ exempt from front≠back (paired with `front_back_distinctness_exempt`);
- `region_set` (string) — which HIT-region vocabulary applies (default `body4`);
- `material_class` / `silhouette_model` / `marker_optional` — reserved (see D4).

Onboarding a car/horse/blob/energy = **one row + one rig profile + (maybe) one region-set entry** — all data.

### D2. `REGION_SETS` registry (replaces the single `REGION_RGB`/`REGION_KEYWORDS` pair)
`constants.REGION_SETS = {"body4": {...today...}, ...}` with `region_for_name(name, region_set="body4")`. The **`body4` default keeps every existing call site byte-identical**. Each set carries its own `fallback_severity`, so `region_fallback_*` is fatal only where a fallback is a real bug (fixes the backwards "a car wheel is rejected as torso"). The engine-facing R8 id mapping stays `{none,head,torso,arms,legs}` for `body4`; a new region set that needs new engine ids is an engine-team contract item (out of scope, engine read-only).

### D3. Wire `has_direction`/`is_radial` into the two gates
- forward-axis requirement skipped when `!has_direction`;
- front≠back distinctness (ADR-0031 MODELING / review snippet 10) exempt when `is_radial` OR `front_back_distinctness_exempt`.
This consumes the otherwise-orphaned snippet-10 flags and **fixes the latent ball false-positive today** — a no-op for the 4 directional archetypes.

### D4. Reserve material/manifest fields (declared, NOT rendered)
Add OPTIONAL, defaulted-to-today fields so the engine-facing contract is pinned now for energy-creatures, exactly as ADR-0026 reserved normal/roughness/metallic:
- `material_class` (default `opaque`), `emissive` (default false), `blend_mode ∈ {normal, additive}` (default `normal`), `silhouette_model ∈ {rigid, fluid}` (default `rigid`).
These are **recorded, not rendered** — the Workbench RGBA cutout renderer stays opaque. A future ADR with its own goldens turns on emissive/additive rendering.

### D5. Reserve mounting grammar (held closed; full design in ADR-0034)
Document `seat/saddle/deck/helm/hitch` as the reserved socket vocabulary and reserve an OPTIONAL `mount_role`/`provides_seat`/`consumes_seat` — but emit nothing and gate nothing until ADR-0034 is scheduled. Sockets are already free-string with `additionalProperties:true`, so this needs no schema change; it just constrains any future socket-projection emitter to be **generic over socket names** (so e.g. the cow's existing `back_socket` carries through for free).

## Consequences
- **+** A new uncommon creature is onboarded as data (row + rig + region-set), not code.
- **+** Fixes the radial-prop front/back false positive today; makes `region_fallback` precise per body plan.
- **+** Pins the energy-creature / mounting contract surface now (cheap, reversible) without committing the renderer.
- **−** One more set of files that must agree (archetype enum ↔ traits ↔ region-sets ↔ rig profiles ↔ spec) — mitigated by a mutual-consistency test (the same single-source discipline ARC-0001 already mandates).
- **−** Until a real vehicle/blob/energy package arrives, the non-`body4` region sets and the emissive/fluid fields are *recorded only* — explicitly deferred.

## Acceptance criteria (when built)
```text
archetype_traits.json has exactly the 5 current archetypes; each maps to a region_set that exists.
region_for_name(name) == region_for_name(name, "body4") for every existing call (pure refactor; goldens unchanged).
A radial prop (ball) with is_radial/front_back_distinctness_exempt is NOT failed by the front!=back gate.
A non-directional archetype with no `forward` declared does NOT raise forward_axis_mismatch.
A test asserts archetype enum <-> archetype_traits.json <-> REGION_SETS keys <-> rig profiles are mutually consistent.
Reserved fields (material_class/emissive/blend_mode/silhouette_model, mount_role) validate but change no rendered pixel.
```

## Deferred (NOT in this ADR)
Any actual new archetype rows (vehicle/blob/energy) + their rigs/palettes; emissive/additive/transparent RENDERING; `silhouette_model: fluid` gate relaxations (need a fluid-silhouette stability metric); non-planar/multi-axis forward and multi-eye direction markers; all of mounting (ADR-0034).
