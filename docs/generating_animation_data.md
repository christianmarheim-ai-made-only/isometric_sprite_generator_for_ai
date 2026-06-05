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
    "idle": { "playback": "loop", "sample_frames": 1, "fps": 1,  "duration_frames": 1, "bones": {} },
    "fly":  { "playback": "loop", "sample_frames": 4, "fps": 12, "duration_frames": 6,
      "bones": {
        "wing.L": { "rotation_euler": [[1,[-0.8,0,0]], [3,[0.8,0,0]], [5,[-0.8,0,0]]] },
        "wing.R": { "rotation_euler": [[1,[ 0.8,0,0]], [3,[-0.8,0,0]], [5,[ 0.8,0,0]]] }
      }
    }
  }
}
```

- **`clips`** — one entry per animation **state** (`idle`, `walk`, `fly`, `attack`, …).
- **`bones`** — per bone, the channels: `rotation_euler` (radians, XYZ) and/or `location` (metres,
  XYZ). Each keyframe is `[frame_number, [x,y,z]]`. **Bones you don't list stay at the bind pose** —
  so a flap is just the two wing bones; everything else holds.
- **`sample_frames`** — how many sprite frames to sample per direction (the clip is sampled
  uniformly across `duration_frames`). **`fps`** + **`playback`** (`loop`/`once`/`hold`) carry the
  timing. These three line up 1:1 with the asset manifest's `animations` block (below).

### The rules that keep it valid

- **In place.** The **root must not translate horizontally** over a clip — locomotion is the game's
  job; the sprite animates on the spot. Vertical bob (root `location` z) is fine. Feet may cycle.
- **Radians / metres**, matching the rig's rest orientation (forward +X, +Z up).
- **States** can be the shared set (`idle` 1f loop, `walk` 4f loop, `attack` 3f once — see
  `pipeline/lockfiles/sprite_states.lock.json`) or your own; whatever `clips` declares is what bakes.
- **Reuse:** target bone **names** only. The same file animates `sparrow`, `crow`, … on `bird_v1`.

---

## How an AI authors it (the point: small, known data)

You have the rig's bones and their rest layout (from the rig profile). To make a motion, reason
per bone and write a few keyframes — then iterate the numbers:

1. Pick the moving bones (wings for a flap; `thigh.L/.R` + `arm.L/.R` for a walk).
2. Decide the swing: a cycle is usually `0 → +a → 0 → −a → 0`; left/right limbs go **anti-phase**
   (one forward while the other is back). For the bird flap: `wing.L` rotates about X by
   `−0.8 → +0.8 → −0.8`, `wing.R` the opposite sign.
3. Place keyframes on a short timeline (`duration_frames`), set `sample_frames` to how many sprite
   frames you want, and pick `fps`/`playback`.
4. Bake, look at it, adjust the angles. It is just numbers — iterate.

A biped walk, same idea:
```json
"walk": { "playback":"loop","sample_frames":4,"fps":8,"duration_frames":8, "bones": {
  "thigh.L": { "rotation_euler": [[1,[ 0.5,0,0]],[5,[-0.5,0,0]]] },
  "thigh.R": { "rotation_euler": [[1,[-0.5,0,0]],[5,[ 0.5,0,0]]] },
  "arm.L":   { "rotation_euler": [[1,[-0.4,0,0]],[5,[ 0.4,0,0]]] },
  "arm.R":   { "rotation_euler": [[1,[ 0.4,0,0]],[5,[-0.4,0,0]]] }
}}
```

---

## Bake it (text → clips → sprites)

```text
# 1. JSON keyframes -> an animated glb (clips authored onto the rigged body)
blender --background --python pipeline/tools/bake_anim_from_json.py -- your_rigged.glb your_anim.json out_animated.glb

# 2. declare the clips in the asset manifest (clip<->state, sample_frames->frames):
#   "animations": { "idle": {"clip":"idle","frames":1,"fps":1,"playback":"loop"},
#                   "fly":  {"clip":"fly","frames":4,"fps":12,"playback":"loop"} }
# 3. bake the package
python pipeline/tools/bake_asset.py your.asset.json
python pipeline/tools/make_contact_sheet.py pipeline/output/<variant_id>
```

`bake_anim_from_json.py` clears any clips the glb shipped with and rebuilds them from your JSON, so
the file is the single source of truth. The asset manifest's `animations` map is the same
`sample_frames`/`fps`/`playback` you wrote, renamed `frames`.

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
