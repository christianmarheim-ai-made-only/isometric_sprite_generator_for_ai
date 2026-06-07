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

So a single model is split across **atlas pages**. The shelf packer wraps rows at a fixed page
**width** and grows the page **height** to fit (it has no height cap). The single-page baker packs at
**2048** wide (legacy); the paged emitter `shard_atlas.py` packs each page at **4096** wide. Rows (no
rotation, PAD=4): `per_row = floor((page_w − PAD)/(tight_w + PAD))` — at 4096 wide and the measured
~92 px tight width, ~42 per row, so a 96-frame state (16 dirs × 6 frames) at ~215 px tall packs to
roughly **4096 × 650**. Paging is worth it once a single-page (2048-wide) bake would grow
uncomfortably tall — large multi-action characters, or 512 px+ canvases (3 states already overflow
2048² at 512 px).

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
- **greedy-within-state fallback (FUTURE — not yet implemented).** When a single state's frames would
  exceed one max page, the plan is to split that state across consecutive pages and record the span as
  `animations[state].pages = [start, end]` so load-by-state still works. **Today** `shard_atlas.py`
  emits exactly one page per state and the loader reads only the per-FRAME `page` (not the per-state
  span); a state that overflows currently produces one over-tall page (and `shard_atlas.py` warns).
  See §7.
- **`greedy`.** Pure bin-packing ignoring state — reserved for one-shot effect sets; flagged
  `atlas_page_policy: "greedy"`. Avoid for characters (frames of every state scatter across pages,
  making pages un-evictable).

## 5. Page size

`shard_atlas.py` packs each page **4096 px wide** (well under the conservative 8192 GPU 2D limit, so
portable); page **height grows to fit** the state's frames (the shelf packer has no height cap, so a
very large single state yields a tall page — `shard_atlas.py` warns if a page exceeds 4096 in either
dimension, the trigger for the FUTURE greedy-within-state split, §4/§7). Recommended cap of **≤ 32
pages per variant** as a runaway guard. PAD=4 + 4 px extrusion per page, no rotation (ADR-0017).

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

Implemented today: the **per-frame `page`** field end-to-end (schema + `shard_atlas.py` emitter +
loader parsing/validation + tests), the single-page alias + back-compat, **`per_state`** sharding, and
**in-baker auto-paging** (ADR-0037): `bake_asset` auto-shards any single-page bake that overflows
`MAX_PAGE_PX` into per-state pages, so the one-command bake of an 8+ state combat character just works
(a character that fits one page stays single-page, byte-identical). Gate-1 (`gate_engine_accept`) and the
build log validate the paged form; the vendored engine schema was synced to its loader (accepts `pages`).

FUTURE (not yet implemented; the manifest/loader contract above does **not** change when they land):
- **greedy-within-state split** — splitting a single oversized state across pages, emitting
  `animations[state].pages = [start, end]`, and teaching the loader to read + validate that span
  (today `AnimDef`/`AnimMeta` ignore it). Until then a single state must fit one 4096-wide page.
- **`greedy` policy** — bin-packing across states for one-shot effect sets.
