# Authoring a new sprite (or new animation state)

How to generate a new `game_iso_v1` sprite package the engine can load + test. Body-only this
iteration (no weapons/equipment). Everything below is gated by
`python pipeline/tools/build.py --ci` (+ the `cargo` engine load-test).

## A new CHARACTER (new mesh)

1. **Mesh** — add a procedural mesh to `pipeline/tools/meshes.py` returning
   `(verts Nx3, faces Mx3, face_region M,)` with per-face HIT region ids
   (`head 1, torso 2, arms 3, legs 4`; `0 = none`). Foot at the origin, forward `+X`, up `+Z`,
   metres. (Or load an OBJ/glTF, keeping the same return shape + region tags.)
2. **Bake** — render + pack + emit an engine-shaped package:
   - single static pose: extend `bake.bake_character` (color + R8 hitmask + measured metrics);
   - multi-state/animation: extend `bake.bake_character_anim` (it reads the states from
     `sprite_states.lock.json` and poses per state — see the walk/attack pose selection);
   - production (Blender) render: `python pipeline/tools/blender_bake.py --out DIR`
     (Workbench, the exact `game_iso_v1` camera; render3d↔Blender parity is gated).
3. **Metrics** — `measure_metrics.compute_world_metrics`: `height_world` = max z;
   `footprint_radius_world` = the GROUND-CONTACT (legs/feet) horizontal extent, **not** the arm
   span; `eye_height_world ≤ height_world`. `variant_class: "character"` ⇒ metrics required + valid.
4. **Commit** the package under `pipeline/reference/<variant_id>/` (`color_atlas.png`,
   `hitmask_atlas.png`, `manifest.json`) and add it to `test_references.py` (Gate-1 + drift) and a
   `bevy_reference/tests/engine_load.rs` load-test.

## A new STATE (e.g. run, jump, death)

1. Declare it in `pipeline/lockfiles/sprite_states.lock.json`: `directions` (== `direction_count`),
   `frames` (per direction), `fps`, `playback` (`loop` | `once`). The engine reads
   whatever `animations` declares — there is no engine-side state list to edit.
2. Add its pose in `bake.bake_character_anim` (how the limbs move per `frame_index`; the root stays
   fixed so the foot anchor is stable — root-XY stability is gated).
3. Re-bake; the manifest's `animations` map + per-frame `(state, frame_index)` follow automatically.

## What the gates enforce

`build.py --ci` (15 steps) + the `cargo` engine load-test: engine-shaped manifest (Gate-1),
direction vs the oracle (Gate-2), elevation/foreshortening (Gate-3), discrete R8 hitmask, measured
metrics, multi-state coverage + tight-crop sizing reconstruction, render3d↔Blender parity, and
committed-reference acceptance + byte-reproducibility. A new package must pass all of them.
