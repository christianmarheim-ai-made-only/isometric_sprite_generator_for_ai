# Atlas / batch scaling — deferred work (decision-complete)

**Status:** DEFERRED — not a runtime blocker. **Purpose:** capture the scaling work
(frame-dedup, atlas paging, batch throughput) in enough detail that a future *cold* session can
execute it without re-deriving any number, threshold, or decision recorded here.

**Why deferred.** The engine consumes **single-page** atlases only today (ADR-044 §Context: atlas
*scaling* is **TASK-018, explicitly deferred** — PM call: "get real features working, optimize
later"). The baker already emits a valid single page that the engine plays. So dedup / paging /
batch are **next-milestone optimizations**, not things that block animated sprites from rendering.
Everything below is measured-this-session and stable; it is safe to act on cold.

**Anchors (read these in the repo before executing):**
`pipeline/tools/bake.py` (`shelf_place`, `place_into`, `bake_character_anim`),
`pipeline/tools/blender_bake.py` (`bake_animated`, packing ~line 198),
`pipeline/tools/shard_atlas.py`, `pipeline/tools/build_log.py`,
`pipeline/tools/test_references.py`, `docs/atlas_paging_contract.md`, `docs/next_phase_plan.md §4`.
Engine contract (read-only): `../Claude/docs/adr/ADR-044-sprite-animation-clips.md`,
`../Claude/docs/pipeline/manifest.schema.json`.

---

## 1. Budget model — where the atlas crosses the GPU caps

**Closed form.** A single-page variant packs

```
cells(variant) = direction_count (16)  ×  Σ_over_clips frames(clip)
atlas_area_px  ≈ cells × canvas_px²            (PAD=4 + 4 px extrusion is a small constant on top)
```

i.e. the cell count is `16 × (total frames per direction)`, and the packed area scales as
`cells × canvas²`. The shelf packer (`shelf_place`) wraps rows at a fixed **width** and grows
**height** without a cap, so the binding question is always: *does the page height cross 2048 / 4096
at this width?*

**Full ADR-044 9-clip vocabulary — frames per direction:**

| Clip | frames |
|---|---|
| idle | 1 |
| walk | 6 |
| crouch_idle | 1 |
| crouch_walk | 4 |
| jump | 2 |
| fall | 2 |
| hit | 3 |
| punch | 4 |
| death | 6 |
| **Σ per direction** | **29** |

So a full combat unit is `29 × 16 = ` **464 frames**.

**Crude cell-area budget (canvas² × 464, before packing slack), vs the page caps:**

| canvas_px | per-frame px² | total cell area px² | √area (square-equiv side) | 2048² page? | 4096² page? |
|---|---|---|---|---|---|
| 256 | 65,536 | 30.4 M | ~5,515 | **overflows** | **overflows a *square* 4096**, but the packer is not square — see measured below |
| 512 | 262,144 | 121.6 M | ~11,029 | overflows | overflows |

The square-equivalent side over-states height because real frames are **tight-cropped** (a humanoid
occupies far less than the full canvas), and the packer lays out wide (4096) and short. So ground the
threshold in the **measured** bake, not the crude bound:

**MEASURED — the real 9-clip grunt (Blender `bake_animated`, 256 px canvas):**

- 464 frames packed to a single-page color atlas of **2050 × 2289 px**, **~79% packed**.
- That **overflows a 2048-wide *and* 2048-tall page** (2050 > 2048 on width, 2289 > 2048 on height).
- It **fits comfortably inside 4096** in both dimensions (2050 × 2289 ≪ 4096²), and 4096 is well
  under the conservative **8192** GPU 2D-texture cap (`atlas_paging_contract.md §5`).

**Plain statement to carry forward:** *the full 9-clip grunt OVERFLOWS a 2048 page but FITS a single
4096 page (and is far under the 8192 GPU cap).* This is exactly why the size ceiling must be 4096
(§5) and why dedup (§2–3) is the cheapest way to claw back headroom inside that page.

---

## 2. Dedup spike results (MEASURED this session — record, do NOT implement yet)

Throwaway content-hash spikes on **real packages**, reporting unique-frame and recoverable-area:

| Package | route | frames | unique | duplicates | dup % of frames | recoverable atlas area |
|---|---|---|---|---|---|---|
| **grunt** (full 9-clip) | Blender `bake_animated` | 464 | 368 | 96 | **21%** | **~20%** |
| **humanoid_anim** (3-state) | procedural `bake_character_anim` | 128 | 80 | 48 | **38%** | **~32%** |

**Interpretation.** Dup rate is **higher on low-animation variants**: the more static a variant, the
more rest-pose frames collapse onto one rect (idle, walk zero-crossings, attack/ punch frame-0, the
crouch rest pose all render to the identical rest pose). A full combat unit, with more genuinely
distinct poses, still recovers **~one fifth** of its atlas — meaningful headroom inside the 4096 page.

**DECISION TO RECORD (do not implement yet):** dedup runs in the **single-page baker, BEFORE
`shard_atlas`**. Cross-state dedup strictly beats per-state-page dedup, because the highest-yield
duplicates are **cross-state** (e.g. `idle` rest-pose frame == `walk` zero-crossing frame ==
`crouch_idle` rest pose). Those cannot collapse across a `per_state` page boundary (each state is a
separate page after sharding, so an idle-rest == walk-rest duplicate is split across two pages and
can no longer share a rect). Therefore: **dedup first (single page), shard second.** This is the
spike-2 result from `next_phase_plan.md §4` made concrete with grunt numbers.

---

## 3. Dedup mechanism + invariant (decision-complete — codeable cold)

### Mechanism

Content-hash each frame's **`(color_crop.tobytes(), region_crop.tobytes())` jointly**. Color and
mask already share one placement in `place_into` (color `rect` == `mask_rect`), so hashing them
together means **the hitmask dedups for free** — there is no separate mask hash, no risk of a color
match with a divergent mask. First occurrence of a hash defines the atlas rect; every later
byte-identical frame **points at the same rect**.

### Invariant (this is what makes dedup contract-safe)

> Only the **`(state, direction, frame_index)` ADDRESS** must be unique — **NOT the pixels.**

Two frame entries may **legally share a `rect`**. This is consistent with everything downstream:

- `atlas_paging_contract.md §3` validates each frame's `rect` against the page **bounds**, never
  against rect **uniqueness**.
- The engine loader reads **each frame's rect independently**; nothing asserts distinct rects.
- Per-frame `trim`, `anchor`, and `sockets` stay **independent even when the rect is shared** —
  they are emitted per frame-entry, not per rect, so two frames sharing a rect can still carry
  different trim/anchor/sockets (they happen to be equal for true duplicates, but the code path does
  not assume it).

### Exact helper to add

Add to `bake.py`, called by **BOTH** `bake_character_anim` (procedural) AND `bake_animated`
(`blender_bake.py`), replacing the current `shelf_place` + `place_into` pair at each call site:

```python
def dedup_place(color_imgs, region_imgs, pad=PAD):
    """Content-hash each (color, region) frame jointly; byte-identical frames share one atlas rect.
    Returns:
      color_atlas  : RGBA Image
      mask_atlas   : 'L' Image (shares placements with color -> mask_rect == rect)
      per_frame_rects : list[[x,y,w,h]] aligned 1:1 with the INPUT frame order (duplicates
                        resolve to the rect of their first occurrence)
      stats        : {"total": N, "unique": U, "duplicates": N-U,
                      "dedup_ratio": round((N-U)/N, 4)}
    Invariant: only (state,direction,frame_index) need be unique, not pixels; per-frame
    trim/anchor/sockets remain independent of rect sharing.
    """
```

Implementation sketch (deterministic, sorted-stable): iterate frames in the existing emission order;
key on `hash((c.tobytes(), r.tobytes()))`; place only first-seen images via `shelf_place` +
`place_into`; map every frame index (incl. dupes) to its representative rect; assemble both atlases
from the unique placement set. `per_frame_rects[i]` is written verbatim into `frames[i]["rect"]` and
`["mask_rect"]` at the existing manifest-assembly loops (`bake.py` ~L301, `blender_bake.py` ~L209).

### Regeneration cost (do this atomically when dedup is turned on)

`test_references.py` re-bakes `humanoid_anim` (and `humanoid_ref`) and asserts **committed ==
fresh, byte-for-byte** (`fresh_anim == committed_anim`). Dedup changes **every rect**, so the
committed `reference/humanoid_anim/` manifest + atlas PNGs **MUST be regenerated in the same commit
that turns dedup on** — otherwise the determinism gate fails instantly. This is a single atomic
change: flip dedup on → re-bake reference → commit manifest+atlases together.

### Build-log additions

Add to `build_log.py` `outputs`: **`dedup_ratio`** and **`unique_frame_count`** (both already
computed by `dedup_place` `stats`). Diffing two `build_log.json` then shows the dedup win directly
(`unique_frame_count` drops, `packing_efficiency` recomputes against the smaller atlas).

---

## 4. Batch driver spec

**Today (serial).** `produce_verify_set.py` loops a **fixed roster** sequentially; `bake_asset.py`
bakes a **single** asset. No parallelism, no incremental skip, one build_index per run.

**Spec — `batch_bake` driver:**

- **Input:** a manifest of **N variants** (each: asset path / mesh / clips / canvas / variant_id),
  not a hardcoded roster.
- **Fan-out:** **parallel worker processes** (one per variant; pool sized to CPU count). Each worker
  is the existing single-asset bake path — no bake-core change, just a driver wrapping it.
- **Fan-in:** **ONE aggregated `build_index.json`** via `build_log.write_build_index(batch_dir,
  logs)` (already accepts a list of logs) — collect each worker's `build_log.json`, pass the list in.
- **Incremental skip:** keyed on the **`file_sha256`** the build log already computes
  (`build_log.file_sha256` → `{path, sha256, bytes}` over mesh + clips + asset). **Skip a variant
  whose mesh + clips + asset shas are all unchanged** vs its committed `build_log.json` `inputs`
  block (`inputs.mesh.sha256`, `inputs.clips.sha256`, `inputs.asset_path`). A changed sha re-bakes;
  an unchanged one reuses the prior output and log row.

**Composition note:** this composes with the **provenance `batch_id`** landing in this same session
— the batch driver stamps each worker's `build_log.json` with the shared `batch_id`, so one batch
run is one queryable provenance group. No conflict; the batch driver is the natural place to mint and
thread the `batch_id`.

---

## 5. Atlas-ceiling cross-reference

There is a **live size-ceiling contradiction** being fixed **THIS session**:

- `validate_debug_subset.py` hard-codes **2048** (and KeyErrors on a `pages` manifest).
- `shard_atlas.py` uses **4096** and only **WARNs** on overflow.

**Fix landing this session (`next_phase_plan.md` H5):** a single enforced **`MAX_PAGE_PX = 4096`** in
a **shared constants module**, imported by `shard_atlas.py`, `build_log.py` (which already mirrors
`MAX_PAGE_PX = 4096` with a "keep in sync" comment — exactly the duplication the module removes), and
`validate_debug_subset.py`. The 4096 ceiling is what lets the §1 grunt (2050 × 2289) pass as a single
page; a 2048 ceiling would wrongly reject it.

**FUTURE (do NOT build now):** the **within-state greedy page-split** — when a *single* state's
frames exceed one 4096 page, split that state across consecutive pages and record
`animations[state].pages = [start, end]`, teaching the loader to read+validate that span (today
`AnimDef`/`AnimMeta` ignore it; `shard_atlas.py` emits one over-tall page and warns). See
`atlas_paging_contract.md §4 / §7`. Not needed until a single state alone exceeds 4096, which no
ADR-044 clip does at 256 px.

---

## 6. Open decision stub — D6: per-variant world-scale exaggeration

The world-scale chain is **already physically faithful**: the engine derives on-screen size from
**measured `height_world × 24`** (engine-side). No correctness gap.

The **only** open question is an **optional art-direction exaggeration multiplier** — a
`world_scale_multiplier = 1.0` enabler (additive, engine-ignored by default) to let a large/small
creature read bigger/smaller than its literal measured height for readability, ahead of an M4 roster.

**Recorded as a STUB — do not decide here.** If pursued: additive manifest field defaulting to 1.0,
engine free to ignore it (faithful path unchanged), only consulted by an opt-in art-direction pass.
Cross-ref `next_phase_plan.md §8 D6` / ADR-0018.
