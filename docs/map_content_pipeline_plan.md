# Big plan — generating all map/environment graphical material

Status: Plan (architecture decided; roadmap demo-driven). Date: 2026-06-08.
Grounded by a 3-way audit (reuse-seam audit + environment-asset taxonomy + architecture evaluation).

## 0. The decision (architecture)

**One shared CORE; two sibling consumers (Characters, Landscape); a cross-consumer test gate protecting the
core.** (Architecture eval scored a shared-core sibling split **7/10** vs in-place-in-the-character-pipeline 3
vs hard-fork 2.)

**Why not a fork (the earlier instinct): environment is not static.** A building with a swaying flag, a bird
flapping on a stone, water shimmer, a flickering torch — these are *animations*. A fork would **duplicate the
animation engine** (clip sampling, multi-frame atlas, paging) and guarantee drift. The animation machinery is
exactly the expensive, well-tested core both consumers must SHARE. So: **one core, two consumers** — Landscape
is NOT a "static subset of Characters"; it is a sibling that uses the *core* (including animation) with its own
contract.

```
                 core/   (generic bake: camera, atlas pack/page, manifest, Gate-1, hitmask, ANIM/clip sampling)
                 /   \                  *changing it requires BOTH suites below to be green*
        character/     env/ (landscape)
        rig, calib,     terrain, props, blocking features, water,
        combat clips     AMBIENT animation loops, the map/area format
   (siblings: neither imports the other; both import core; dependency is strictly one-way)
```

### Governance — the rule that protects the core (the user's rule)

- A change to **`core`** must keep **BOTH** the **character** suite **and** the **landscape** suite green
  (a combined `build_all.py` runs core + char + env). The shared foundation only moves when both things
  standing on it still stand.
- A **character-only** change needs core + character green (landscape can't be affected — it never imports
  character). A **landscape-only** change needs core + landscape green.
- **Dependency is strictly one-way:** `character → core`, `env → core`; never `character ↔ env`, never
  `core → either`. Enforce with a tiny boundary check (no `core` file imports a consumer; each consumer gate
  runs as its own CI job).
- **Today the generic core is physically tangled inside `pipeline/tools/` with the character layer.** Two
  ways to honour the rule: **(a) start now** — treat the generic functions (the seam below) as the *logical*
  core, document it, and run the cross-gate; no risky refactor. **(b) later** — physically extract
  `pipeline/core/`, verified by the existing green gates (a no-behaviour-change move). Recommend (a) now,
  (b) when it earns its keep.

### The shared-core seam both consumers reuse (don't widen it casually)

From the core (today inside `pipeline/tools/`), both Characters and Landscape reuse **as-is** (the audit
confirmed these are generic, not character-specific) — note `bake_animated`/clip sampling is core, so a
swaying flag bakes through the SAME path as a walking knight:
- `constants` — `CANVAS=256`, `DIRS=16`, `PAD=4`, `TILE_BASE=64×32`, `MAX_PAGE_PX=4096`, `forward_yaw()`.
- atlas packing — `bake._pack`, `shelf_place`, `place_into`; `shard_atlas.shard` (paging, ADR-0037).
- the camera render — `blender_render.py` (the exact game_iso_v1 ortho camera) + `bake_blender` (**static**
  props) **and `bake_animated` + `bake_anim_from_json` (the clip-sampling path a swaying flag / ambient critter
  reuses unchanged)**.
- Gate-1 — `gate_engine_accept.engine_accept` (the engine-acceptance contract).
- metrics/AABB — `measure_metrics.compute_world_metrics`, `blender_bake.region_aabbs`,
  `render3d.ground_screen_direction` / `compute_fit`.

Env **adds** (its own, never in tools/): env schemas (terrain/prop/feature/water), env gates (seamless-tile,
collision-intent, area-composition), the **map/area format + assembler**, the env **producer spec**, an env
**self-test**, and an env **gate runner** (`pipeline/env/build_env.py`).

## 1. What already exists — reuse, do not rebuild

- **`variant_class: terrain`** (ADR-053): flat z=0, `direction_count:1`, no world_metrics. Baked example
  `ground_arid_v1` (256×128, seamless-tiling verified via `preview_3x3.png`). The terrain path works today.
- **The collision/spatial layer is engine-side and generic** (ADR-019 `Collider = FootprintShape +
  VerticalSpan + CollisionChannels{blocks_movement, blocks_vision}`; ADR-024 static spatial index inserted
  once at load). Walls, water, mountains, props are all "a footprint + a tall span + channels."
- **Blocking features (ADR-054)** and **water (ADR-055)** are *specified* (footprint + tall VerticalSpan;
  water = `solid()` + an occluding band that makes ADR-033 height-aware LOS block sight for free). Map-load
  parser is declared but **not built** — that's our work.
- **Effect overlays (ADR-0024 Part B)** are separate depth-composited sprites synced to sockets — the
  template for any layered/animated environment effect.
- **A dev sandbox scene exists (`SPEC-PROP`)**: 20-unit grid, mountain-ringed boundary, AI off, deterministic
  — ready to drop real props/areas into for iteration.

## 2. The environment asset taxonomy

Demo set = **flat-with-obstacles**; the rest is noted but deferred.

| Asset kind | Bake path | Demo? | What it needs beyond a basic bake |
|---|---|---|---|
| **Ground terrain tile** | `variant_class:terrain`, dir 1, 256×128 | ✅ | seamless edge tiling; diamond alpha; elevation-correctness (30°) |
| **Blocking feature** (wall, rock, cliff-as-occluder, mountain) | static prop sprite (16-dir) + hitmask | ✅ | world_metrics → collider footprint+span; `blocks_movement`/`blocks_vision` intent; unbreakable |
| **Static prop / scenery** (tree, crate, bush) | static prop sprite (16-dir) + optional hitmask | ✅ | clear iso silhouette; height for occlusion; usually non-blocking |
| **Ambient animated prop** (swaying flag, flapping bird, torch flicker, foliage rustle) | **`bake_animated`** loop clip → multi-frame atlas (the SAME core path as a character) | ✅ | one looping ambient clip (no combat vocab idle/attack/hit/death, no rig profile required — bone or shape-key/vertex anim); directional (16-dir) OR radial (1-dir) per the prop; placed/composited like any feature |
| **Water / river** | terrain tile + a water collider (`solid()` + occluding band) | ✅ (one feature) | seamless water tile; authored occluder height so LOS blocks across it |
| **Visual effect overlay** | `variant_class:effect`, animated, directional/radial | ➖ if needed | anim frames; origin/socket policy; no collision |
| **Tile transitions / auto-tiling** (grass↔dirt edges) | edge-variant atlas cells | ❌ defer | Wang/blob tile indices + edge-pair selection — explodes the tileset |
| **Decals / overlays** | decal atlas + per-cell list | ❌ defer | small clipped sprites; a decal manager |
| **Lighting / time-of-day** | extra atlas pages OR runtime `Sprite.color` tint | ❌ defer | stable sun angle; combinatorial if undisciplined |

## 3. The map / area format

An area loads as **two layers** (this is what the env assembler emits and the engine consumes):

1. **Terrain tile grid** — a 2-D array of cells `{grid_x, grid_y}`, each `{ terrain_id: "ground_arid_v1",
   water?: true, decal_ids?: [...] (future) }`.
2. **Feature placement list** — declarative static props/features: `{ kind, grid_x, grid_y, facing,
   variant?, blocks_movement?, blocks_vision? }`. Colliders are spawned from this at load (ADR-054 pattern).

The assembler also emits a **preview compose** (lay the tiles + features into one image) so an area can be
eyeballed without the engine — the env analogue of `preview_3x3.png`.

## 4. The hard problems — and how the demo punts them

- **Auto-tiling/transitions** → DEFER. v1 = single uniform tile per terrain type, hard edges. The Wang/blob
  tileset + edge-pair selection is a future amendment (it explodes authoring + atlas packing).
- **Verticality** → DEFER (single-plane MVP, ADR-022). A "cliff/mountain" is a **2-D footprint + a tall
  VerticalSpan** (a visual occluder you can't stand on), NOT a walkable height. No ramps/stacked floors.
- **Water vision-blocking** → SOLVED cheaply: author an occluding-band span; ADR-033 LOS blocks for free.
- **Visual cohesion across unlit bakes** → the real discipline cost: lock azimuth 45° / elevation 30° + a
  tight art-direction doc + bake recipes (owned by the World Builder). Lighting variants stay single
  daylight bake for the demo.
- **Atlas budget** → a 4096 page ≈ ~100 terrain tiles OR ~25 16-dir props; paging (ADR-0037) already
  handles overflow. Keep a per-biome atlas budget; don't sprawl.

## 5. Roadmap (phased, demo-driven)

- **P0 — Package + seam + governance (1st).** Create `pipeline/env/` + the one-way boundary check + a
  trivial env self-test that bakes BOTH a **static prop** (`bake_blender`) AND a tiny **animated prop**
  (`bake_animated`, a 1-bone sway loop) through the reused core/Gate-1 — proving env reuses the *animation*
  path, not just static. `pipeline/env/build_env.py` is the separate env gate; add `build_all.py` (core +
  `build.py` char + `build_env.py`) as the gate any **core** change must pass. The character `build.py` is
  untouched.
- **P1 — Env contracts + gates.** Trimmed delivery schemas (terrain tile / prop / blocking feature / water)
  = `external_asset_v2` minus rig/clips/calib, plus collision-intent fields. Env gates: seamless-tile check
  (reuse the 3×3 preview), collision-intent presence, terrain elevation-correctness. The **env producer
  spec** (the character spec with the hard parts removed — the World Builder's briefs target this).
- **P2 — Map/area format + assembler.** The two-layer area schema (§3) + an assembler (grid + features →
  a loadable area manifest) + the preview compose. Validate one hand-authored area end-to-end.
- **P3 — Throughput + the demo biome.** Wire World Builder briefs → env producer → env bake; the asset
  index board. Bake the one demo biome's kit (ground tile + a handful of props/features + one water feature)
  and assemble the demo area(s).
- **P4 — Deferred (post-funding).** Auto-tiling, verticality, lighting/time variants, decals.

## 6. The three-chat division of labour

- **World Builder** (`docs/handoffs/world_builder_bootstrap.md`) — decides *what* areas/assets exist; writes
  briefs + area blockouts + recipes. Big calls = the user.
- **Env producer** — turns each brief into a glb to the trimmed env contract (the character Model Producer,
  with rig/clips/calib dropped).
- **Env pipeline (`pipeline/env/`)** — bakes the glbs + tiles (static AND ambient-animated) into iso
  sprites/tiles, runs the env gate, assembles areas. Reuses the **shared core** read-only (a sibling of the
  character pipeline, not a child of it).

## 7. Open decisions for the user (the big calls)

1. **Where does `pipeline/env/` live** — in this repo (recommended: shares the core directly, one CI), or a
   separate repo that vendors the seam?
2. **Demo biome + flat-with-obstacles confirm** — the World Builder's first task; it scopes the whole kit.
3. **How many demo areas** and what each showcases (movement / shield cover / LOS / water chokepoint).
4. **Draft the trimmed terrain/prop contract now**, or let the env chat define it at P1?
