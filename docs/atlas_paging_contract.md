# game_iso_v1 — atlas paging (multi-atlas) contract

**Status:** specified + reference-loader-verified + emitter-implemented. **Strictly additive and
backward-compatible:** every single-page manifest loads byte-for-byte unchanged. Extends the output
manifest (`docs/multistate_sprite_contract.md`); does not change camera/sizing/anchoring.

## 1. Why (the budget)

The pipeline packs one color atlas + one hitmask atlas per model. A model is `direction_count ×
Σ_state frames` cells, and the single-page shelf packer is capped (legacy 2048²). That overflows:

- The committed 3-state reference (`idle 1 + walk 4 + attack 3 = 8 frames/dir × 16 = 128 frames`)
  already fills the color atlas to ~2041×1576. **One more 4-frame action overflows 2048²** at 256 px.
- Higher resolution makes it worse: at 512 px logical canvas, even 3 states overflow.

So a single model is split across **atlas pages**. Per-page budget (no rotation, PAD=4):
`per_row = floor((page_w − PAD) / (tight_w + PAD))`, `rows = floor((page_h − PAD) / (tight_h + PAD))`,
`capacity = per_row × rows`. With the measured median tight frame (~92×215) and **`max_page_px =
4096`**: a 256 px-canvas character holds ~756 frames/page (so ≤3-state characters stay single-page
after the cap is raised to 4096); paging materializes for 8+ state characters or 512 px+ canvases.

## 2. The format (additive)

`atlases.color` and `atlases.hitmask` each accept **either** the single-page alias **or** a `pages`
array; each frame gains an optional integer **`page`** (default `0`). `rect` / `mask_rect` are
**local to the frame's page**.

```jsonc
"atlases": {
  "color":   { "format": "...", "sampling": "linear",
               "pages": [ {"path":"color.idle.png","size":[1408,904]},
                          {"path":"color.walk.png","size":[2008,1812]} ] },
  "hitmask": { "format": "PNG_R8_UINT_linear_no_antialias", "sampling": "nearest",
               "palette": {"none":0,"head":1,"torso":2,"arms":3,"legs":4},
               "pages": [ {"path":"mask.idle.png","size":[1408,904]},
                          {"path":"mask.walk.png","size":[2008,1812]} ] }
},
"atlas_page_policy": "per_state",          // "single" | "per_state" | "greedy" (how pages were sharded)
"frames": [
  { "state":"walk","direction":2,"frame_index":1,"page":1,
    "rect":[480,670,92,204],"mask_rect":[480,670,92,204], "...": "trim/anchor/sockets as before" }
]
```

- **Single-page alias (unchanged):** `"color": {"path":"color_atlas.png","size":[w,h]}` and frames
  with no `page` field. The loader synthesizes `pages = [{path,size}]` and every frame is page 0.

## 3. Invariants (loader-enforced)

1. `atlases.color.pages` and `atlases.hitmask.pages` MUST be the **same length**; for each frame,
   color and hitmask share the **same `page`** index.
2. `mask_rect.w/h` MUST equal `rect.w/h` (positions may differ; the engine rejects a size mismatch).
3. `0 ≤ page < pages.len()`; default `0`. Each frame's `rect [x,y,w,h]` is validated against
   `pages[page].size` (NOT a single global atlas size).
4. Every page dimension `> 0`.

State coverage (`(state, direction, frame_index)` complete + unique) and all sizing/anchoring are
**unchanged** — paging only chooses *which texture* a resolved frame samples.

## 4. Paging policy

- **`per_state` (default, recommended).** One page per state: all directions × that state's frames
  on it, so `page` == the state's ordinal. This lets the engine **lazy/partial-load by state** (load
  `idle` at spawn, stream `walk`/`attack` on first transition, evict unused states) and gives one
  draw batch per active state.
- **greedy-within-state fallback.** If a single state's frames exceed one page (e.g. a 60-frame
  death at 512 px), split that state across consecutive pages and record the span as
  `animations[state].pages = [start, end]` so load-by-state still works.
- **`greedy`.** Pure bin-packing ignoring state — reserved for one-shot effect sets; flagged
  `atlas_page_policy: "greedy"`. Avoid for characters (frames of every state scatter across pages,
  making pages un-evictable).

## 5. Page size

`max_page_px = 4096` per page (default; well under the conservative 8192 GPU 2D limit, so portable).
Recommended cap of **≤ 32 pages per variant** as a runaway guard. Keep PAD=4 + 4 px extrusion per
page, no rotation (ADR-0017).

## 6. Reference implementation

- **Loader:** `pipeline/bevy_reference/src/loader.rs` parses the page list (alias or `pages`),
  validates each frame's `rect` against its page, enforces invariants 1–4, and exposes
  `SpriteVariant.pages` + `FrameDef.page`. Tests in `tests/engine_load.rs`
  (`multi_atlas_paged_manifest_loads`, `paged_rect_exceeding_its_page_is_rejected`,
  `single_page_alias_still_loads`, `sharded_real_package_loads`).
- **Emitter:** `python pipeline/tools/shard_atlas.py PACKAGE_DIR --out OUT_DIR` re-packs a baked
  single-page package into per-state pages.
- **Examples:** `pipeline/examples/atlas_paging/manifest.example.json` (small, hand-authored) and
  `humanoid_anim_paged.manifest.json` (the real 3-state reference sharded to 3 pages). Both validate
  against `pipeline/schema/sprite_manifest.schema.json` and load through the reference loader.

## 7. Status of pipeline emission

The baker emits **single-page** packages today; `shard_atlas.py` converts to multi-page on demand.
Folding per-state paging into `bake_character_anim`/`bake_animated` directly (so large characters
page during the bake, not as a post-step) is a follow-up — the manifest/loader contract above does
not change when it lands.
