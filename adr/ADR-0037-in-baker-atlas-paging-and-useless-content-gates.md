# ADR-0037: In-baker atlas paging + useless-content gates

Status: Accepted
Date: 2026-06-08
Related: docs/atlas_paging_contract.md (the multi-page format + loader invariants), ADR-0025/0036 (hit
regions), ADR-0028 (mode-aware severity). Vendored loader: `pipeline/bevy_reference/src/loader.rs`.

## Context

A character bakes `direction_count × Σ_state frames` cells into one color atlas + one hitmask atlas. A
realistic **combat** character has many states (idle/walk/run/attack/reload/hit/death/celebrate = 8), and
8 states × 16 directions overflows a single ≤`MAX_PAGE_PX` (4096) page: `pirate_duelist_v2` packs to
**2052×5062** → `oversize_atlas_page` (error) → **it cannot bake at all**. The atlas-paging *format* and
the *loader* already existed (multi-page `pages[]` + per-frame `page`, `shard_atlas.py` emitter, the
`bevy_reference` loader's `AtlasDef::page_list` + per-page rect validation), but paging only happened as a
manual **post-bake** `shard_atlas.py` step — the one-command bake (`bake_asset`) still produced a single
page and failed the gate. Two further gaps surfaced: the vendored engine **schema** was stale relative to
its own loader, and the gates couldn't tell when a bake was producing **useless** content.

## Decision

**1. In-baker paging (auto-shard when oversize).** After the bake, `bake_asset._page_if_oversize` checks
the single-page color atlas; if it exceeds `MAX_PAGE_PX` it re-packs **in place** into per-state pages
(`shard_atlas.shard`, `atlas_page_policy: per_state`) and removes the orphaned single-page PNGs. A
character that fits one page is returned **unchanged** (byte-identical → goldens/parity stable). A single
*state* that still overflows one page is a hard, explained failure (the greedy-within-state split remains
FUTURE per the contract §7).

**2. Sync the vendored engine schema to its loader.** `schema/engine/manifest.schema.json` *required*
`path`+`size` on each atlas, so it rejected the `pages[]` form **its own loader already parses**. The
atlas `color` def now accepts `anyOf[{path,size}, {pages}]` and the frame declares `page` — matching the
loader and `sprite_manifest.schema.json`, a strictly backward-compatible widening. (The engine team should
sync their *published* schema; their loader is already ahead of it.)

**3. Gate-1 validates paging.** `gate_engine_accept` resolves the page list (alias or `pages`) and mirrors
the loader's invariants: each frame's `rect` validated against `pages[frame.page].size`, page index in
range, `color.pages` length == `hitmask.pages` length, `mask_rect.w/h == rect.w/h`.

**4. build_log is paging-aware.** The colour-richness, region-presence (`region_missing`), artifact-hash,
and blank-frame checks resolve the atlas PNG(s) from the manifest (single `path` or every `pages[].path`)
instead of the fixed `color_atlas.png`/`hitmask_atlas.png`, so a sharded package is still fully gated
(region ids are unioned across pages).

**5. Useless-content gates — the process must KNOW it baked junk.**
- `flat_region_bound_texture` (input): a `flat_region` delivery that binds a base-colour texture is the
  "flat-via-degenerate-UV-texture" hack (looks textured, bakes ~one texel/material). `flat_region` uses
  material base colours, not a texture → rejected at the front door. (Only `pirate_duelist_v2` trips it;
  all 18 legit flat_region deliveries bind 0 textures.)
- `blank_frame` (output): a baked direction/state whose hitmask sub-rect is entirely background rendered
  NOTHING — an empty/failed frame is flagged, never silently shipped.

## Consequences

- An 8-state combat biped **bakes**: the overflow auto-shards into per-state pages (the engine can then
  lazy-load `idle` at spawn and stream the rest), passes Gate-1, and is fully gated.
- `oversize_atlas_page` becomes a **safety net** (a single page > `MAX_PAGE_PX` after sharding — only the
  unimplemented greedy-within-state case).
- No engine change required (the loader already supports pages); the vendored schema now matches it.
- The pirate is correctly **rejected** for its real defects (the redundant texture + atlas budget), and
  the clean version of the same model bakes + pages.

Tests: `test_atlas_paging.py` (auto-shard through the real `_page_if_oversize` path + Gate-1 paged accept
+ negative), `test_useless_content.py` (flat_region_bound_texture + blank_frame), plus the existing
`bevy_reference` paged loader tests. Full gate 40/40.
