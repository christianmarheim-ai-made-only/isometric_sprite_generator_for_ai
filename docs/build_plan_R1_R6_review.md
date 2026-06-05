# Sprite-Generator Pipeline — Build Plan R1–R6 (review copy)

> **Self-contained for external review.** A reviewer needs no repo access: §0 gives
> the system + the engine contract + conventions; §1 lists the six slices (R1 done,
> R2–R6 planned); §2 covers sequencing, open questions, and what's deferred.
> Date: 2026-06-05.

> Supersedes `docs/next_slices_plan.md` (the legacy M1/M2 + setup plan, slices P0–P5 /
> C0–C9, now shipped as the R1-equivalent foundation). For R2–R6 **this file is
> authoritative**; ignore that file's §8 P/C status tracker.

---

## 0. Context

### What this is
A **headless pipeline** that turns a rigged 3D model into **16-direction isometric
sprite sheets + a machine-readable manifest** consumed by a Bevy/Vulkan isometric
game (format id **`game_iso_v1`**). The engine-facing output (manifest + color atlas
+ R8 hitmask atlas) is a **fixed contract**; the pipeline behind it is free. The
project's core discipline: **avoid silent contract bugs** — output that looks right
but is subtly wrong (a half-bin rotation, a flipped axis, a wrong camera angle, a
blended mask value).

The pipeline is plain Python (Pillow, numpy, jsonschema). The renderer is a
**dependency-light software rasterizer** (no Blender, no GPU) so everything builds and
tests **headless**; real art (Blender / glTF / AI-generated meshes) swaps in at a
mesh-input seam without pipeline changes.

### The engine contract `game_iso_v1` (pinned from the engine's Rust source)
- **Manifest (what the loader `parse_manifest` requires), top-level:** `camera.id ==
  "game_iso_v1"`; `direction_count` ∈ {1,2,4,8,16}; `frame_canvas [w,h]`;
  `atlases.color.{path,size}` (path **relative to the manifest's own dir**); `frames[]`
  each `{direction, rect[x,y,w,h] (w,h>0), anchor[x,y] in frame_canvas px}`; with
  `frames.len() == direction_count` and directions `0..N-1` **unique + fully covered**;
  `world_metrics {height_world>0, footprint_radius_world>0, eye_height_world? ≤ height}`
  — **required** for `character`/`effect`, optional for `probe`. **The loader ignores
  unknown fields** (serde) → the pipeline may emit extra provenance/metadata freely.
- **Projection (engine `project_iso`):** `screen_x=(x−y)·32`, `screen_y=−(x+y)·16 +
  height·24` (Bevy **y-up**). Camera **azimuth 45°, elevation 30°** (`sin30°=0.5` ⇒ a
  2:1 ground tile). NOTE: `arctan(0.5)≈26.565°` is the *on-screen tile-edge angle*, **not**
  the camera elevation — conflating them is a known trap; the elevation is **30°**.
- **Sizing (engine `sprite_size`):** on-screen **height = `height_world × 24`**, **width =
  height × frame_aspect** (`rect.w/rect.h`). ⇒ the **engine owns absolute on-screen size**;
  the **bake owns the 30° foreshortening** (which fixes the frame aspect + internal
  proportions) **and the emitted `height_world`**. There is **no in-bake `×24`**.
- **Direction binning:** `i = round(facing/(TAU/N)) mod N`, `0 = +X` (East), CCW. The
  pipeline emits `expected_facing_table.json` (per-direction yaw + screen vector); the
  engine has a test asserting its binning/projection against that **oracle**, so the
  convention cannot silently drift. **Keep emitting the oracle.**
- **Hitmask (future engine consumer):** single-channel **R8** region-ID mask, discrete IDs,
  **no anti-aliasing**; palette `none0 head1 torso2 arms3 legs4 shield5 weapon6 gear7`.
  Authoritative mask source = **rig-bound HIT_ proxy geometry**, not the visual mesh.

### Locked conventions (never "correct" these)
Forward **+X** (East); up **+Z**; **1 unit = 1 meter**; origin = **ground footprint
center**. Because `screen_y` is down, **world-CCW reads clockwise on screen**; diagnostics
`dir02` points down, `dir10` points up. A wrong **elevation** is the one irreversible
mistake (it bakes the foreshortening) → a re-bake.

### Scope guard (this iteration)
**Weapons & equipment are OUT.** Regions `shield/weapon/gear`, weapon/shield sockets, and
weapon markers are deferred. **Body-only** (`head/torso/arms/legs`).

### Current state
- M1/M2 arrow pilot done; a hardening fix pass + a source-side toolchain (descriptor
  schema, linter, naming/region/metrics policies, style guide) are in.
- **R1 (below) is shipped and green**; R2–R6 are the forward plan.

---

## 1. The six slices

Each slice is **spec-resolved** (no open decision blocks it) and **headless-testable**
(procedural meshes; no Blender/GPU). "Gate-N" refers to the engine's 3 acceptance gates:
**Gate 1** = engine-loadable (schema + cross-field rules), **Gate 2** = direction
(socket→oracle), **Gate 3** = elevation/foreshortening.

### R1 — Headless 3D renderer ✅ DONE
**Goal:** turn a triangle mesh into 16 `game_iso_v1` direction frames, headless.
**Delivered:** `render3d.py` (numpy orthographic rasterizer; az 45 / el 30 camera; per
direction rotate mesh `i·22.5°` about +Z, z-buffer rasterize, auto-fit scale, foot
anchor) · `meshes.py` (procedural cube / pole / arrow-wedge) · `test_render3d.py`.
**Acceptance (met):** the renderer's camera **matches the engine ground-direction oracle
for all 16 directions to `1.1e-16`** (provably the same projection); `dir00=[0.894,0.447]`;
meshes rasterize; a tall pole renders tall; foot anchor stable. In the `build.py` gate (8/8).
**Why it matters:** proves the camera is engine-correct on real geometry — the riskiest
part — and is the bake engine for everything below.

### R2 — Engine-shaped manifest + bake orchestrator + Gate-1
**Goal:** make pipeline output **engine-loadable** and add one orchestrator: mesh → package.
**Deliverables:**
- Emit the top-level **`camera` block** (currently missing → the engine would reject our
  output): `{id:"game_iso_v1", azimuth_degrees:45, camera_elevation_degrees:30,
  camera_elevation_definition, camera_geometry_note, projection, screen_y:"down",
  tile_px:[64,32]}`.
- Emit per-frame **`sockets.direction_tip`** (`= origin + screen_direction_vector·len`) for
  the Gate-2 direction check.
- `bake.py` — orchestrator: (mesh/descriptor) → R1 render 16 frames → pack atlases →
  engine-shaped manifest → `expected_facing_table.json` → validate.
- **Vendor the engine `manifest.schema.json`** — from the engine repo's **corrected** copy
  `C:\Code\Claude\docs\pipeline\manifest.schema.json` (30°), **not** the stale
  `dist/game_iso_v1_reference_v1/CONTRACT/manifest.schema.json` (still says 26.565°).
  Add **Gate 1** to `build.py` (validate our manifest against it + the two cross-field rules).
**Acceptance:** our generated manifest passes the vendored engine schema + cross-field
rules; `bake.py` produces a complete package from a procedural mesh; existing gate green.
**Depends on:** R1. **Spec status:** fully resolved (the loader contract is pinned).

### R3 — Acceptance gates (Gate-2/Gate-3) + foreshortening calibration
**Goal:** the engine's three gates as our package acceptance, incl. the height/foreshortening
calibration a flat arrow can't do.
**Deliverables:**
- **Gate 2:** for every frame, `normalize(direction_tip − origin) ≈ oracle vector` (<1e-2);
  `world_yaw_degrees == i·360/N`.
- **Gate 3:** assert `camera_elevation_degrees == 30`; **and** a bake-side foreshortening
  check via R1 — render a known-proportion object (the pole/cube) and assert its rendered
  aspect/height matches the 30° prediction. (The engine-side `height_world×24` sizing is an
  *engine* test, not a bake gate.)
- One `build.py` runs all gates green.
**Acceptance:** all three gates green on the R2 package. **Depends on:** R1, R2.
**Spec status:** resolved (engine sizes by `height_world×24`; bake = 30° + `height_world`).

### R4 — Real mesh input + hit-proxy hitmask + world metrics (body-only)
**Goal:** consume a real **source asset** (per the existing `source_asset` descriptor) and
produce **color + R8 hitmask** atlases from actual geometry, plus measured `world_metrics`.
Bridge from procedural boxes to real, region-tagged models.
**Deliverables:**
- **Mesh input:** an OBJ (and optionally glTF) loader → vertices/faces (via `trimesh`, a new
  optional dep, with a tiny built-in OBJ fallback). Procedural meshes remain for tests.
- **A procedural humanoid placeholder** (`capsule_knight`: box/capsule torso, box head,
  box limbs), each part tagged with its body region — so the **multi-region** pipeline is
  testable headless without real art.
- **Hit-proxy → R8 mask:** render each `HIT_<region>` proxy through R1, composite the
  **topmost-visible** region per pixel (engine ADR-0006) into the discrete R8 mask
  (`Image.NEAREST`, no AA); emit per-frame region **boxes** that bound their mask pixels.
- **`world_metrics`:** measured from the `METRIC_body` proxy bbox (height, footprint radius)
  + an optional head/eye socket (eye height), via the existing metrics helper.
- The bake reads `source_asset.json` (the descriptor) → resolves `VIS_/HIT_/METRIC_/SOCKET_`
  objects → renders the color (from `VIS_`) and the mask (from `HIT_`).
**Acceptance (machine):** hitmask values ⊆ palette (discrete, no AA); `head/torso/arms/legs`
each present in ≥1 frame; boxes bound their region pixels; `world_metrics` positive with
`eye ≤ height`; color+hitmask atlases pack + dims agree; the manifest still passes Gate-1;
the source descriptor passes the linter (body-only).
**Depends on:** R1, R2, R3; the descriptor schema + linter + metrics helper (already built).
**Spec status:** resolved (mask semantics, naming, metrics are all ratified-proposed). Idle
only, 16-dir, body-only. **Risk:** topmost-visible compositing across overlapping proxies
needs care (depth from the same z-buffer the color pass uses).

### R5 — Animation states + tight-crop + full manifest convergence (M3 shape)
**Goal:** multi-state / multi-frame animation, **tight per-frame crop**, and convergence of
the manifest from today's "debug subset" to the engine's richer target shape.
**Deliverables:**
- **States × frames:** render `idle`, `walk`, … each `N` directions × `F` frames; **frame
  counts come from `sprite_states.lock.json`, not prose** (a contract invariant). Headless:
  drive motion with a procedural pose function (a parametric walk cycle on the placeholder
  limbs); real clips (glTF/Blender animation) swap in at the same seam.
- **Tight-crop:** pack each frame at its **tight alpha bbox** (`rect.w < frame_canvas`)
  rather than the full canvas; update the validator to bound `anchor/sockets/boxes` against
  the per-frame **rect** (a fix already staged in the validator) and enforce the
  **crop-contains-anchor** rule; add a dedicated cropped-frame test.
- **Manifest convergence:** emit the full target shape (states → directions → frames, with
  per-frame `hitregions`/boxes and a `contract` echo block) and bump `manifest_version` off
  the debug-subset string. The engine still consumes its subset (it ignores the extras).
**Acceptance:** per-state frame counts == the states lock; cropped frames validate
(anchor/box inside rect, crop contains anchor); Gate-1 still green; mask stays discrete.
**Depends on:** R4. **Spec status:** resolved **except** one coordination point — see Open
Question Q1 (the engine loader is currently single-state). **Risk:** packing many cropped
frames into ≤2048² atlases; validator O(canvas²) cost → vectorize (numpy) before scale.

### R6 — First reference character, end-to-end + engine load-test
**Goal:** one **body-only character** through the **entire** pipeline, validated **and
load-tested against the real engine** — the M3 "controlled real variant" proof.
**Deliverables:**
- A staged reference character (B0 static → B1 idle → B2 walk) using the procedural humanoid
  (or a provided OBJ/glTF): `source_asset.json` → **lint** → **R4** render (color + hitmask)
  → **measure** metrics → **R5** manifest → **all gates green**.
- **Engine load-test:** write the package where the engine reads it
  (`assets/sprites/<variant>/`) and run the engine's own `cargo test -p client_bevy`
  (`parse_manifest` + the binning/projection oracle) to prove it **loads + binds + matches
  the oracle**. (Needs the Rust toolchain — may be a CI/human step if `cargo` isn't in the
  autonomous environment; flagged.)
- **Height calibration** with the character's real `height_world` (bake-side foreshortening
  via R1; the engine sizes it `height_world×24`).
**Acceptance:** full `build.py` gate green; the engine's `cargo test` passes on the generated
package; (human/visual) the character renders correctly in the engine's `losdemo`.
**Depends on:** R4, R5; a humanoid source linter (skeleton/socket/clip checks — the planned
"linter v2"); the engine repo for the load-test. **Spec status:** resolved; the load-test
has an external `cargo` dependency.

---

## 2. Sequencing, open questions, deferrals

### Sequencing
`R1 → R2 → R3 → R4 → R5 → R6`. R1 is done. R2 unblocks engine-loadability (the current #1
gap — our manifest has no `camera` block). R3 adds the gates. R4 brings real geometry +
the multi-region hitmask + metrics. R5 adds animation + crop + the M3 manifest shape. R6 is
the first real character, proven against the live engine. Everything before R6 runs fully
headless on procedural meshes; **real art (Blender/glTF/AI) plugs into the R4 mesh-input
seam and the R5 animation seam without pipeline changes.**

### Open questions for the reviewer
- **Q1 (R5):** the engine loader is currently **single-state** (`frames` = one flat list of
  `direction_count` entries). Multi-state output must keep an engine-consumed single-state
  `frames` at top level (e.g., the default/idle state) while carrying the full
  states→directions→frames structure as ignored extras — **or** the engine loader is
  extended. Which? (Affects R5's manifest shape + R6's load-test.)
- **Q2 (R4):** topmost-visible hitmask from overlapping HIT_ proxies — composite from the
  same z-buffer as the color pass, or a separate per-proxy depth resolve? (Edge cases when a
  proxy is partly occluded by the visual mesh but not by another proxy.)
- **Q3 (R6):** is the autonomous environment expected to have **Blender** and/or **`cargo`**?
  If not, R6's real-art and engine-load-test steps become human/CI gates; the rest stays
  autonomous. Confirm so we can mark those steps correctly.
- **Q4 (general):** should the renderer move from the software rasterizer to a GPU/headless
  path (e.g., `pyrender`/`moderngl`) for real-mesh fidelity, or is the software rasterizer
  sufficient through M3? (Software is the most robust headless; GPU adds environment risk.)

### Deliberately deferred (not in R1–R6)
- **Weapons & equipment** (regions shield/weapon/gear; weapon/shield sockets + markers;
  outgoing-attack traces) — return post-M3 in an M2A combat-surface harness.
- **AI generation** (M4) — only behind the proven seam, after a controlled real variant
  passes; no roster-scale generation before then.
- **Atlas compression / streaming** (M5) — uncompressed PNG + decoded R8 until memory is
  measured.

### How each slice is verified (summary)
A single command (`build.py --ci`) runs the whole gate; each slice adds machine checks to
it (schema/cross-field for Gate-1; socket→oracle for Gate-2; elevation + foreshortening for
Gate-3; mask discreteness; per-state counts; crop-in-rect). R6 adds the engine `cargo test`.
No slice is "done" until its checks are green.
