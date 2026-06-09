# Big plan — generating all map/environment graphical material

Status: Plan (architecture decided; roadmap demo-driven). Date: 2026-06-08.
Grounded by a 3-way audit (reuse-seam audit + environment-asset taxonomy + architecture evaluation).

## 0. The decision (architecture)

**Build a SIBLING extension package — `pipeline/env/` — that IMPORTS the character pipeline as a read-only
library and NEVER modifies it.** (Architecture eval: sibling **7/10** vs in-place 3/10 vs hard-fork 2/10.)

Why, in one line: the character pipeline is hardened (42/42) and *too sensitive to touch*, while environment
assets are a **strict subset** of what it already does (static; no rig, no clips, no calibration, no combat
regions). So we reuse the proven core and add an env-only layer beside it that **physically cannot break the
character gate** (separate files, separate CI gate).

The boundary (the one rule that makes this safe):

```
pipeline/env/   ──imports──▶   pipeline/tools/        (ONE-WAY. env may read tools; tools must never import env)
     │                              │
  env-only: schemas, gates,     the proven core (unchanged):
  map format, producer spec,    camera, atlas pack/page, manifest, Gate-1, hitmask
  env self-test + env gate
```

Enforce it with a tiny boundary check (an env self-test assertion: no file under `pipeline/tools/` imports
`env`, and the env gate runs as a **separate** CI job from `build.py`). A broken env bake then turns the env
gate red and leaves the character 42/42 green.

### The stable seam env imports (don't widen it casually)

From `pipeline/tools/`, env reuses **as-is** (the audit confirmed these are generic, not character-specific):
- `constants` — `CANVAS=256`, `DIRS=16`, `PAD=4`, `TILE_BASE=64×32`, `MAX_PAGE_PX=4096`, `forward_yaw()`.
- atlas packing — `bake._pack`, `shelf_place`, `place_into`; `shard_atlas.shard` (paging, ADR-0037).
- the camera render — `blender_render.py` (the exact game_iso_v1 ortho camera) + `bake_blender` (the **static**
  bake path — props are already bakeable through it).
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

- **P0 — Package + seam (1st).** Create `pipeline/env/` + the one-way boundary check + a trivial env
  self-test that bakes a **static prop** through the reused `bake_blender`/Gate-1 (proves import-only reuse).
  `pipeline/env/build_env.py` is the separate env gate. The character `build.py` is untouched.
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
- **Env pipeline (`pipeline/env/`)** — bakes the glbs + tiles into iso sprites/tiles, runs the env gate,
  assembles areas. Reuses the character core read-only.

## 7. Open decisions for the user (the big calls)

1. **Where does `pipeline/env/` live** — in this repo (recommended: shares the core directly, one CI), or a
   separate repo that vendors the seam?
2. **Demo biome + flat-with-obstacles confirm** — the World Builder's first task; it scopes the whole kit.
3. **How many demo areas** and what each showcases (movement / shield cover / LOS / water chokepoint).
4. **Draft the trimmed terrain/prop contract now**, or let the env chat define it at P1?
