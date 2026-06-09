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
  `blocks_vision`), and terrain `tiling`. The world-builder authors recipes + briefs against THIS.
- `examples/` — one valid asset per kind (badlands: `ground_arid_v1`, `waystone_v1`, `mesa_wall_v1`,
  `seep_pool_v1`).
- `self_test.py` + `build_env.py` + `build_all.py`.

## Status + what's next (the handoff's priority order)

1. ✅ **Trimmed FLAT terrain/prop schema** (`env_asset_v1`) — unblocks the world-builder's recipes + briefs.
2. ⏳ **Tiered-terrain bake contract** (the paired pipeline ADR, the irreversible-mistake gate, ADR-053) —
   **gated on the engine** assigning a multi-level owner (`docs/handoff/multi-level-terrain/BRIEF.md` §0).
   The schema reserves a `tier` block so `env_asset_v2` extends cleanly (tier_height + edge_kind).
3. ⏳ **Prove the flat badlands look** — bake one `ground_arid` tile end-to-end through the gates (de-risk).
4. ⏳ **Harden the scenery gates** — seamless tiling (3×3 preview), the elevation guard, the static-prop
   hitmask. These become steps in `build_env.py`.

**GATED:** no world-asset *production* baking until the tiered contract + engine ADR land (a single sample
tile to prove look/feel is allowed). See `docs/map_content_pipeline_plan.md` for the full plan.
