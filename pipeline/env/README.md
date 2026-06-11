# `pipeline/env/` — the world-scenery pipeline (sibling of the character pipeline)

The world-scenery track: baking the demo world's **terrain tiles, static props, blocking features, and
water** into `game_iso_v1` iso sprites/tiles. It is a **sibling** of the character pipeline, not a child of
it — both stand on the same shared core.

## The rule (governance)

```
                 pipeline/tools/  (shared CORE: game_iso_v1 camera, atlas pack/page, manifest,
                 /            \    Gate-1, R8 hitmask, clip sampling)  ← changing it must keep BOTH gates green
        character (build.py)   env (build_env.py)        ← run both via build_all.py
```

- **Dependency is one-way:** `pipeline/env` imports `pipeline/tools` read-only; **`pipeline/tools` must
  never import `pipeline/env`** (enforced by `self_test.py`).
- **Separate gates:** `build_env.py` is the scenery gate; the character `build.py` is untouched. A change
  to the shared core must pass **`build_all.py`** (character + scenery). A scenery-only change need only
  pass `build_env.py`.

## What's here (P0 / priority #1 of the World-Builder handoff)

- `schema/env_asset.schema.json` — **`env_asset_v1`**, the trimmed delivery contract (FLAT): the character
  `external_asset_v2` minus rig/clips/archetype/calibration, plus `kind` (terrain | prop | blocking_feature
  | water), a `collision` block (an ADR-019 collider: footprint + occluder height + `blocks_movement` /
  `blocks_vision`), terrain `tiling`, and — for **structures** — a multi-volume `collision_volumes` block
  (see below). The world-builder authors recipes + briefs against THIS.
- `collision_volumes.py` — derives + validates the additive **`collision_volumes`** structure block (the
  engine contract). `examples/` has one valid asset per kind plus the structure example `wall_window_v1`
  (+ its `wall_window_v1_hitbox.json` region-AABB sidecar).
- `self_test.py` + `test_collision_volumes.py` + `build_env.py` + `build_all.py`.

## Structure colliders — `collision_volumes` (a wall with a window)

A simple feature (a boulder, a mesa) ships ONE `collision` block. A **structure** — a wall with a window,
where different parts have different sight/movement/projectile behaviour — ships `collision_volumes`: a list
of per-part colliders. This is the engine contract
[`docs/handoff/sprite-scenery-contracts/CONTRACT-scenery-structure-metadata.md`], emitted **additively** (the
engine loader ignores unknown manifest fields by construction — Gate-1 stays green), so the model bakes today
and never needs re-baking when the (currently owed) engine consumers land.

**The split — the bake MEASURES geometry, the modeler AUTHORS semantics:**

| | comes from | fields |
|---|---|---|
| **GEOMETRY** (derived) | each region's world AABB in the `files.hitbox` **region_hitboxes sidecar** | `footprint` (aabb offset + half-extents), `span_world` `[bottom, top]` |
| **SEMANTICS** (authored, in the asset's `collision_volumes[]`) | the modeler — *they* know what is glass | `vision` (opaque\|transparent), `passable`, `material_class`, `projectile_response` (default + per-class), `damage_variant_role` |

So a `collision_volumes` asset **requires** `files.hitbox` + `region_source: explicit_region_hitboxes`, and
each authored `region` MUST name a sidecar entry — the bake measures that box (direction-invariant, intact
pose, one set per model), it never invents geometry. Volumes are emitted at the manifest top level; each
`transparent` region also emits a per-frame `window_<n>_center` socket (the projected px aperture centre,
reused from the core's named `region_rects` — nothing re-projected). `world_metrics` stays (sizing/eye
source); `collision_volumes` only supersedes the single-cylinder collider mapping. The block carries CLASS
names and measured FACTS — **never** gameplay numbers (HP/damage/resistances); the engine owns class→body
(the ADR-034 guard). The bake validates the emitted block against the contract §6 rules and fails on a bad
one (`collision_volumes.validate_volumes`).

## Status + what's next (the handoff's priority order)

1. ✅ **Trimmed FLAT terrain/prop schema** (`env_asset_v1`) — unblocks the world-builder's recipes + briefs.
2. ⏳ **Tiered-terrain bake contract** (the paired pipeline ADR, the irreversible-mistake gate, ADR-053) —
   **gated on the engine** assigning a multi-level owner (`docs/handoff/multi-level-terrain/BRIEF.md` §0).
   The schema reserves a `tier` block so `env_asset_v2` extends cleanly (tier_height + edge_kind).
3. ✅ **Prove the flat badlands look** — `ground_arid` bakes end-to-end (seamless, elevation 30, Gate-1).
4. ✅ **Harden the scenery gates** — seamless tiling (3×3 preview), the elevation guard, the static-prop
   hitmask are steps in `build_env.py`.
5. ✅ **Structure `collision_volumes`** — the additive multi-volume block bakes today (geometry measured
   from the region_hitboxes sidecar, semantics authored, §6-validated, window sockets, Gate-1 still green).
   Follow-up that needs a **core** change (both gates): make the R8 hitmask carry structure part ids so the
   palette self-describes per-pixel (today the volumes carry their own `region` tags; the engine reads no
   hitmask yet, so this is not on the no-re-bake critical path).

**GATED:** no world-asset *production* baking until the tiered contract + engine ADR land (a single sample
tile to prove look/feel is allowed). See `docs/map_content_pipeline_plan.md` for the full plan.
