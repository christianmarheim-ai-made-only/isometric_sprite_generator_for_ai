# Pirate PoC — full bake run RESULT

**Goal:** take the delivered `chr_pirate_duelist_v1` character package end-to-end through
`bake_asset.py` into a `game_iso_v1` sprite package, fixing the pipeline until a full run works, then
update the contract from what's confirmed.

## Result: SUCCESS ✅

A real external delivery bakes into a **standing, textured, animated, 16-direction, 8-state**
`game_iso_v1` package that passes Gate-1.

| Property | Value |
|---|---|
| States (8) | idle, move, run, shoot, reload, hurt, death, celebrate |
| Frames | **1040** (16 dirs × Σ 65 frames) |
| Direction distinctness | **16/16 per state** (no aliasing) |
| Hit regions | all four present (head/torso/arms/legs), **0 material→torso fallbacks** |
| Clip binding | **all 8 clips bound to the rig** (no `missing_clip_rest_pose`) |
| Texture | embedded base-color renders (per-material colors; see limitation 2) |
| Height (measured) | **2.015 m** (body 1.82 + tricorn hat; authored body-height excludes the hat) |
| Color atlas | 2052 × 5062, single page |
| Gate-1 | **PASS** (single-page) |
| Rig | `biped_v1` — validated end-to-end by a real delivered asset |

Reproduce: `python pipeline/tools/bake_asset.py creative/pirate/chr_pirate_duelist_v1.asset.json --out pipeline/output/pirate_poc`
Visual proof: `_poc_montage.png` (8 states × 16 directions), `_poc_hero.png` (full-res poses).
Full readiness analysis: `_bake_readiness.md`.

## Pipeline fixes made to get here

1. **Up-axis now honored on the Blender path** (the bug that made the pirate bake **lying down**).
   Blender's glTF importer always assumes Y-up; a `up:"z"`-authored glb was laid on its back. The
   bake now threads `geometry.up` (`bake_asset → bake_animated → blender_render_anim`) and applies a
   −90° X correction for `up:"z"`. `up:"y"` (grunt/sparrow/crow) is unchanged. *This closed a real
   contract gap — the doc had claimed glb up-axis was "inert".*
2. **Shard ceiling honors `MAX_PAGE_PX`.** `shelf_place` returns `content+PAD`, so per-state pages
   packed to `MAX_PAGE_PX` overshot by `PAD` (celebrate 4097, shoot 4099 → `OversizePageError`).
   `shard_atlas` now targets `MAX_PAGE_PX − PAD`, so pages land ≤ 4096.

## Delivered-artifact fixes (the delivery was built against a slightly older contract)

3. **`death` playback `hold` → `once`** in `chr_pirate_duelist_v1.asset.json` and `_anim.json`.
   `hold` was removed from the playback enum; `once` holds the terminal frame identically.
   *(The generator `generate_pirate_glb.py` still emits `hold` at lines 674/710 — fix before any
   regeneration so it stops re-introducing the invalid enum.)*

## Confirmed working (contract updates landed)

- `docs/external_asset_contract.md` — glb `up:"z"` is now honored (was documented as inert).
- `region_source: material_name` works on a real delivery — all 19 materials keyword-mapped to
  head/torso/arms/legs with zero fallbacks.
- `biped_v1` rig + 13-bone clip targets bind 1:1 against a real skinned glb.

## Known limitations / follow-ups (not blockers for this PoC)

1. **Single-page atlas (5062 px) exceeds the conservative `MAX_PAGE_PX=4096`** (but is under the
   ~8192 GPU cap, so it loads). A full 8-clip combat character at 256² does not fit a 4096 single
   page. `shard_atlas` produces a valid **paged** package, **but the engine schema rejects `pages[]`
   (Gate-1 fails on a sharded manifest)** — the engine consumes single-page only (paging = the
   deferred TASK-018). So today: ship single-page (engine-loadable up to GPU max). Production options
   when clip-count grows: TASK-018 paging consumption, a smaller canvas, or a curated clip set.
2. **Texture detail is flat** (`generate_pirate_glb.py:461-465` collapses each material's UVs to the
   tile centre) — colors are correct, fine painted detail is absent. Producer-side, optional.
3. **Clip vocabulary** (`move/run/shoot/reload/hurt/celebrate`) bakes fine; the bake never enforces
   the engine vocab. The engine state→clip selection mapping is a separate, documented concern.
