# game_iso_v1 — multi-state + tight-crop contract (R5 / R5A unblock)

**Audience:** informational — this is the **output** format the pipeline emits and the engine loads.
A model producer authors **none** of it; it documents what comes back. (Producers deliver a
`*.asset.json` — see `external_asset_contract.md`.)

**Status:** ✅ **LANDED** — the engine multi-state loader shipped (engine **ADR-044**, Arc 5; the
amended `docs/pipeline/manifest.schema.json` is the contract to target). The engine now plays our
clips on a real-time frame timer, selected from disclosed entity state; the reference loader here is
backstopped by the real engine. Keep emitting the `animations` block + per-frame `state`/`frame_index`
— the engine consumes exactly that. Frame key = **(state, frame_index, direction)**. Canonical clip
names that "light up": `idle` (required + fallback), `walk`, `crouch_idle`, `crouch_walk`, `jump`,
`fall`, `hit`, + future `punch`/`death` (ADR-040/041). Atlas **paging is NOT engine-consumed yet**
(TASK-018, deferred — emit single-page for engine playback).

**(historical)** engine *consumption* designed (verified against the current loader). This is the
contract the pipeline emits to **now** so R5/R5A can proceed; the engine loader implementation
lands as a dedicated engine slice (its own branch). **Backward-compatible:** the single-state
arrow probe loads byte-for-byte unchanged.

## 1. The blocker (today)
`client_bevy/src/sprite.rs::parse_manifest` requires exactly **one frame per direction**
(`frames.len() == direction_count`; a second frame on a direction is a "duplicate" error) and
**ignores** `animations` / per-frame `state` / `frame_index` (serde forward-compatible). So a
multi-state or multi-frame manifest is **rejected at load** → R5A blocked. Tight-cropped frames
also mis-size (the engine derives aspect from the atlas `rect`, which a trimmed rect breaks).

## 2. Multi-state (R5A) — formalize what you already emit
No new field names except one optional scalar. The engine will **consume**:

**(A) Top-level `animations` map** (already emitted):
```json
"animations": { "<state>": { "directions": <==direction_count>, "fps": <num>,
                             "frames": <count per direction>, "playback": "loop|once" } }
```
- `<state>` = the state key (`idle`, `walk`, `attack`, …); `frames` = animation-frame count for
  that state **per direction**; `directions` MUST equal top-level `direction_count`.

**(B) Per-frame `state` + `frame_index`** (already emitted) on each `frames[]` entry. An atlas
cell's full address is the triple `(state, direction, frame_index)`:
- `state` matches an `animations` key, `direction` ∈ `0..direction_count-1`,
  `frame_index` ∈ `0..animations[state].frames-1`, plus the existing `rect` + `anchor`.
- Coverage MUST be **complete + unique** per `(state, direction)`: `frame_index` `0..frames-1`,
  no gaps/dupes. Total `frames[]` length == Σ over states of `direction_count × frames`.

**(C) `default_state`** (NEW, optional scalar): the state shown when nothing is playing. Omit →
engine defaults to `"idle"`; if no `idle`, the **lexicographically-first** state name (byte/ASCII
order) — e.g. with states `{attack, fly}` and no idle, `attack`.

This **extends** game_iso_v1 (`camera.id` stays `"game_iso_v1"`; all existing required fields +
loader rules unchanged; the schema's `additionalProperties:true` already permits these).

### Backward-compat (guaranteed)
- Arrow probe (`animations.idle`, `frames:1`, 16 dirs) collapses to today's per-direction model →
  loads unchanged.
- A manifest with **no** `animations` block → engine synthesizes a single implicit `idle` state
  from the flat `frames[]` (today's behavior). Minimal/legacy manifests still load.

## 3. Tight-crop (R5) — the sizing decision
Tight-cropping trims transparent padding, so a frame's `rect` is smaller than its logical cell.
The engine sizes via `scale = world_height × HEIGHT_SCREEN_SCALE / logical_frame_canvas.h`, then
draws the tight `rect` at `rect.w × scale` by `rect.h × scale`, and anchors by a fraction of the
**logical** frame. A trimmed `rect` alone breaks both. So carry the logical frame explicitly. Emit
per frame (or top-level if uniform):
- **`logical_frame_canvas`**: `[w, h]` — the **untrimmed** cell size; the sizing reference that
  maps to `world_metrics` (height). (Equals today's `frame_canvas` for uncropped frames.)
- **`rect`**: `[x, y, w, h]` — the **tight** color-atlas region (the actual pixels), as today.
- **`mask_rect`**: `[x, y, w, h]` — the tight region in the **hitmask** atlas; its `w,h` MUST equal
  `rect`'s `w,h` (the engine rejects a size mismatch). Position may differ if the atlases pack
  independently; today `mask_rect == rect`.
- **`trim`**: `[ox, oy]` — the tight rect's top-left **within** the logical frame (`[0,0]` if
  uncropped).
- **`anchor`**: `[ax, ay]` — the foot, in **absolute logical-frame PIXELS** (top-left origin, +Y
  down; NOT a 0..1 fraction). The engine divides by `logical_frame_canvas` to normalize.

**Atlases:** the manifest carries `atlases.color` (`path` + `size`) and `atlases.hitmask` (`path` +
`size` + `format` + `sampling` + `palette`). For large models (16 dirs × many frames × many actions
× higher res) these may be **paged** — multiple atlas pages addressed by a per-frame `page` index;
see [`atlas_paging_contract.md`](atlas_paging_contract.md). Single-page is the default and loads
unchanged.

Engine sizing/placement (deterministic):
- `scale = world_height × HEIGHT_SCREEN_SCALE / logical_frame_canvas.h`
- on-screen size = `rect.w × scale` by `rect.h × scale` (the tight region only)
- the tight region is offset within the logical frame by `trim × scale`; the logical anchor
  (`anchor × scale`) lands on the projected foot. Trimmed padding is implied, never drawn.

Net: tight-cropped atlases render at the correct size + position + anchor; the logical frame is
the single sizing/anchoring reference, the `rect` is just where the pixels live.

## 4. What the engine ships (staging)
- **MIN (the R5A unblock):** the loader parses all states + the tight-crop fields, validates
  coverage, builds the full `(state, direction, frame_index)` atlas, and renders the **default
  state's frame 0** at the binned direction. A multi-state, tight-cropped manifest stops being
  rejected and renders (as its default pose) — you can emit + verify against the engine
  immediately.
- **FULL (follow-up, same contract, no re-emit):** per-proxy animation clock (loop/once over
  `fps`) + a client-side state selector mapping sim signals (`z>0`→jump, motion→walk,
  stance→crouch, else default) to playback + state switching. No sim/`Entity` changes — state
  stays derived at the client edge.

## 5. What the pipeline must confirm
- The canonical **state set** + per-state `frames`/`fps`/`playback` live in your
  `sprite_states.lock.json` (hash-pinned, not vendored). The engine will **not** hardcode a state
  list — it reads whatever `animations` declares. Confirm names + counts there.
- `playback` vocabulary = `{loop, once}` (engine ADR-044). `once` **holds the terminal frame** (the
  engine's one-shot — hit/punch/death); `loop` wraps. There is no separate `hold`.
- Per-state `directions` == top-level `direction_count` (engine rejects mismatches).
- Whether you emit `default_state`, or guarantee `idle` is always present.
- Tight-crop: emit `logical_frame_canvas` + per-frame `trim`; keep `anchor` in logical coords.

## 6. R7 (Blender/glTF renderer) — NOT an engine blocker
R7 (no Blender installed → can't run the production 3D renderer) is a **pipeline-side environment
blocker**, not an engine-contract gap. The engine consumes the manifest + atlas you produce,
*regardless of how they're rendered* — the contract above is renderer-agnostic. Resolve R7 on the
pipeline side (install/provision Blender, or stand up a headless/software render path). The engine
cannot unblock R7.
