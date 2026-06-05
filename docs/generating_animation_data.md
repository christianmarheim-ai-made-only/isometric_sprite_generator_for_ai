# Generating animation data (from the model's rig)

**Audience:** whoever (a human or an AI) produces the **motion** for a body. Animation here is
**compact text**: per-bone keyframes that target the **rig's bone names** — the model's own known
data. Because channels target bone *names* (not a specific mesh), one animation file drives **every**
variant skinned to that rig (the "10 birds, 1 animation" reuse). An AI can author this by reasoning
about each bone and iterating angles — no DCC required to write it.

> Prereq: the body is **rigged** — skinned to a rig profile (`bird_v1`, `biped_v1`, …) whose bones
> have the exact names in `pipeline/schema/rig_profiles/`. See
> [`external_asset_contract.md`](external_asset_contract.md) §5. (Un-rigged? See *Rig-free* below.)

---

## The format (`anim_clips_v1`)

A small JSON. Schema: `pipeline/schema/animation_clips.schema.json`. Example:
`pipeline/examples/animation/bird_v1_anim.json` (the worked example below).

```json
{
  "anim_spec_version": "anim_clips_v1",
  "rig": "bird_v1",
  "clips": {
    "idle": { "playback": "loop", "frames": 1, "fps": 1,  "duration_frames": 1, "bones": {} },
    "fly":  { "playback": "loop", "frames": 4, "fps": 12, "duration_frames": 6,
      "bones": {
        "wing.L": { "rotation_euler": [[1,[-0.8,0,0]], [3,[0.8,0,0]], [5,[-0.8,0,0]]] },
        "wing.R": { "rotation_euler": [[1,[ 0.8,0,0]], [3,[-0.8,0,0]], [5,[ 0.8,0,0]]] }
      }
    }
  }
}
```

- **`clips`** — one entry per animation **state** (`idle`, `walk`, `fly`, `attack`, …).
- **`bones`** — per bone, the channels: `rotation_euler` (radians; applied in Blender intrinsic XYZ
  order, in the **bone's LOCAL rest frame**) and/or `location` (metres). Each keyframe is
  `[frame_number, [x,y,z]]` with `frame_number` a **1-based integer** timeline position. **Bones you
  don't list stay at the bind pose** — a flap is just the two wing bones; everything else holds. (For
  the shipped rigs the major bones are axis-aligned at bind, so local ≈ world — verify per rig.)
- **`frames`** — how many sprite frames to sample per direction. **`fps`** + **`playback`**
  (`loop`/`once`; `once` holds the last frame) carry the timing. These three map 1:1 to the asset manifest's `animations`
  block (same field names). `duration_frames` is authoring-only.

### The rules that keep it valid

- **Radians / metres**, matching the rig's rest orientation (forward +X, +Z up).
- **States**: each rig profile's `states` block lists what a variant may deliver (required `idle` +
  optional extras — biped `walk`/`punch`/`death`, bird `fly`); whatever `clips` declares is what bakes.
- **Reuse:** target bone **names** only. The same file animates `sparrow`, `crow`, … on `bird_v1`.

### Keyframe timeline & sampling (exact)

- **`duration_frames` = loop length L.** Lay keyframes on the 1-based timeline `1..L`. For a seamless
  `loop`, make pose@(L+1) == pose@1 but **do not author the wrap frame** — e.g. a 6-frame flap keys
  frames 1,3,5 (frame 5's pose flows back into frame 1).
- **Half-open sampling:** the pipeline takes `frames` poses across the clip's authored span at
  positions `i/frames` for `i in 0..frames-1` — the last sample is BEFORE the wrap, so a looped clip
  never double-counts the seam. The sampler spans the baked action's first→last authored keyframe.
- **In place (precise):** the cumulative world-space horizontal (X, Y) translation of **every** bone
  over the clip must net to ≈0 — no bone drifts the silhouette off the origin across the loop.
  Vertical (Z) bob is fine. (Prose-only; not enforced by tooling.)

---

## How an AI authors it (the point: small, known data)

You have the rig's bones and their rest layout (from the rig profile). To make a motion, reason
per bone and write a few keyframes — then iterate the numbers:

1. Pick the moving bones (wings for a flap; `thigh.L/.R` + `arm.L/.R` for a walk).
2. Decide the swing (`0 → +a → 0 → −a → 0`). Two patterns:
   - **Walk = ANTI-PHASE** (contralateral): `thigh.L` forward while `thigh.R` is back — temporally
     opposite, staggered in time.
   - **Flap = MIRRORED** (symmetric): both wings rise/fall **together**. Because `wing.L`/`wing.R`
     sit on opposite sides, "both up together" is **opposite-signed** X-rotation (`wing.L −0.8`,
     `wing.R +0.8`). Don't make one wing up while the other is down — that reads as broken.
3. Place keyframes on a short timeline (`duration_frames`), set `frames` to how many sprite frames
   you want, and pick `fps`/`playback`.
4. Bake, look at it, adjust the angles. It is just numbers — iterate.

A biped **`walk`** cycle, same idea — the full canonical combat library
(`walk`/`punch`/`death`, clip names per engine ADR-044) is `pipeline/examples/animation/combat_biped_anim.json`:
```json
"walk": { "playback":"loop","frames":6,"fps":10,"duration_frames":8, "bones": {
  "thigh.L": { "rotation_euler": [[1,[ 0.5,0,0]],[5,[-0.5,0,0]],[9,[ 0.5,0,0]]] },
  "thigh.R": { "rotation_euler": [[1,[-0.5,0,0]],[5,[ 0.5,0,0]],[9,[-0.5,0,0]]] },
  "arm.L":   { "rotation_euler": [[1,[-0.4,0,0]],[5,[ 0.4,0,0]],[9,[-0.4,0,0]]] },
  "arm.R":   { "rotation_euler": [[1,[ 0.4,0,0]],[5,[-0.4,0,0]],[9,[ 0.4,0,0]]] }
}}
```
Keys 1 and 9 share a pose so the cycle closes seamlessly (half-open sampling skips frame 9).

---

## Bake it (text → clips → sprites)

**One command (recommended).** Point the asset manifest at your rigged glb **and** the anim JSON;
`bake_asset.py` embeds the clips, then bakes:

```text
# your.asset.json:
#   "files": { "mesh": "rigged.glb", "animation_clips": "your_anim.json" },
#   "rig": "bird_v1",
#   "animations": { "idle": {"clip":"idle","frames":1,"fps":1,"playback":"loop"},
#                   "fly":  {"clip":"fly","frames":4,"fps":12,"playback":"loop"} }
python pipeline/tools/lint_external_asset.py your.asset.json     # also validates the anim JSON
python pipeline/tools/bake_asset.py your.asset.json
python pipeline/tools/make_contact_sheet.py pipeline/output/<variant_id>
```

Each `clips[state]` in the anim JSON maps to one `animations[state]` in the asset manifest (same
`frames`/`fps`/`playback`; `clip` = the state name). Worked example:
`pipeline/examples/animation/crow_jsonanim.asset.json`.

**Manual (embed first, if you prefer):**

```text
blender --background --python pipeline/tools/bake_anim_from_json.py -- rigged.glb your_anim.json animated.glb
# then point files.mesh at animated.glb (omit files.animation_clips) and run bake_asset.
```

`bake_anim_from_json.py` clears any clips the glb shipped with and rebuilds them from your JSON, so
the JSON is the single source of truth.

### Rig-free alternative

A body with **no rig** is animated procedurally — the numpy humanoid swings legs/arms by a
parametric formula per state (`bake.bake_character_anim`: `leg_swing`/`arm_swing`). No keyframes to
author; you only choose the states. Use this when you don't need custom motion.

---

## Verify

- [ ] **It moves:** in the `*_color_sheet.png`, a multi-frame clip's frames differ down the column
      (wings flap / legs swing). A quick numeric check: the mean absolute pixel difference between
      frame 0 and frame 2 of a clip is clearly non-zero — the limbs visibly move (a flat/static clip
      would be ~0).
- [ ] **idle is steady**, the anchor stays at the feet across all frames, 16 directions intact.
- [ ] **Reuse holds:** the same `*_anim.json` baked onto a second variant of the same rig produces
      identical motion (the bird file drives both `sparrow` and `crow`).

The worked example (`bird_v1_anim.json` on a `bird_v1` body) is proven end-to-end: JSON → clips →
the wings visibly flap across the 4 `fly` frames in all 16 directions, idle level.

## Where this fits

The model's **rig** is the source: bone names + bind pose → keyframes. So once a body is rigged, its
animation is just a small text file, shared across the whole archetype. Sits alongside
[`generating_hitbox_data.md`](generating_hitbox_data.md) (collision from the same geometry); both
feed [`external_asset_contract.md`](external_asset_contract.md) and `bake_asset.py`.
