# Next 3 build slices (R1–R3) — engine-shaped output + headless 3D renderer

Buildable, **spec-resolved**, headless-testable. Designed so a long autonomous run
can execute them **without asking questions** — the engine contract is now fully
pinned from the engine source (`C:\Code\Claude\crates\client_bevy\src\{sprite,render}.rs`).
Nothing below depends on an open decision.

## Engine contract — pinned facts (read from engine source, 2026-06-05)

- **Loader** (`sprite.rs::parse_manifest`) requires, top-level: `camera.id == "game_iso_v1"`,
  `direction_count > 0`, `frame_canvas [w,h] > 0`, `atlases.color.{path,size}`, and
  `frames[]` each with `direction` + `rect [x,y,w,h]` (w,h>0) + `anchor [x,y]` (in
  frame_canvas px, y-down); `frames.len() == direction_count` covering `0..N-1` uniquely.
  `world_metrics` required for `character`/`effect`, optional for `probe` (probe defaults:
  height 2.0, footprint 0.5; eye absent → `0.85·height`). **serde ignores unknown fields**
  → all our extra fields are fine.
- **Projection** (`render.rs::project_iso`): `screen_x=(x−y)·32`, `screen_y=−(x+y)·16 + height·24`,
  depth `(x+y)·0.001`; Bevy **y-up**. Camera azimuth 45°, **elevation 30°** (`sin30°=0.5` ⇒ 2:1 ground).
- **Sizing** (`render.rs::sprite_size`): on-screen **height = `height_world × 24`**, **width =
  height × frame_aspect** (`rect.w/rect.h`). ⇒ the **engine owns absolute on-screen size**;
  the **bake owns the 30° foreshortening** (which sets the frame aspect + internal
  proportions) **and the emitted `height_world`**. **No in-bake ×24** (this supersedes
  ADR-0018's earlier "pin height in the bake" framing).
- **Direction**: `i = round(facing/(TAU/N)) mod N`, `0=+X` East, CCW — **verified end-to-end**
  vs our `expected_facing_table.json` (the engine asserts against it). Keep emitting the oracle.
- Engine loads `assets/sprites/pilot.json` or `assets/sprites/arrow_probe/manifest.json`;
  atlas path is relative to the manifest dir.

---

## Slice R1 — Headless 3D renderer ("view the model as 3D → images")

**Goal:** turn a 3D triangle mesh into the 16 `game_iso_v1` direction frames, headless
(no Blender, no GPU). This is the M3 bake engine; validate it now on procedural meshes.

Deliverables:
- `pipeline/tools/render3d.py` — numpy orthographic rasterizer:
  - Camera: orthographic, azimuth 45°, **elevation 30°**, +Z up. World→screen uses the
    locked iso basis so the **ground** matches `project_iso` (`(x−y)`/`(x+y)` with the 2:1 +
    30° height foreshortening, `sin30=0.5`).
  - Per direction `i` in `0..15`: rotate the mesh about +Z by `i·22.5°`, rasterize with a
    z-buffer into the frame canvas → RGBA (flat/normal-shaded silhouette) + a coverage/depth
    buffer.
  - Compute the per-frame tight bbox + the **foot anchor** (projection of the model's
    ground-contact origin) in frame_canvas px.
- `pipeline/tools/meshes.py` — procedural test meshes: unit **cube**, a **vertical pole**
  (foreshortening/height calibration), a flat **arrow wedge** (cross-check vs the 2D pilot).
- `pipeline/tools/test_render3d.py` (wired into `build.py`):
  - cube/pole render non-empty, mode/size correct, silhouette coverage > 0;
  - the **ground** projection of a known world vector matches `project_iso` direction
    (cross-check a directional marker vs the oracle);
  - foreshortening sanity: an upright `1×1×H` box's rendered height:width ratio matches the
    30° prediction (the bake-side calibration; see R3).
- Add **numpy** to `requirements.txt`. (OBJ loading via `trimesh` is optional, later.)

Self-contained: no dependency on R2/R3, no Blender, no GL, no open spec.

---

## Slice R2 — Engine-shaped manifest + bake orchestration ("build script")

**Goal:** make our output engine-loadable and add one orchestrator: mesh → validated package.

Deliverables:
- **Emit the `camera` block** (currently missing → engine rejects our output): `{ id:"game_iso_v1",
  azimuth_degrees:45, camera_elevation_degrees:30, camera_elevation_definition:…,
  camera_geometry_note:…, projection:"orthographic_pixel_iso_dimetric_2_to_1",
  screen_y:"down", tile_px:[64,32] }`. Add to `generate_arrow_pilot` and the R1 bake path.
- **Emit per-frame `sockets.direction_tip`** (`= origin + screen_direction_vector·len`)
  alongside `origin`, for the Gate-2 direction check.
- `pipeline/tools/bake.py` — orchestrator: (mesh or descriptor) → R1 render 16 frames →
  pack atlases (`make_atlases`) → engine-shaped manifest → `expected_facing_table.json` →
  validate. Reuses the existing packing/manifest helpers.
- **Vendor** the engine `manifest.schema.json` → `pipeline/schema/engine/manifest.schema.json`
  (+ the golden sample as a fixture). Add **Gate 1 (engine acceptance)** to `build.py`:
  validate our manifest against the engine schema **plus** the two cross-field rules
  (`frames == direction_count`; directions `0..N-1` unique + covered).

Covers tasks #16, #17, #18, #21.

---

## Slice R3 — Acceptance gates + calibration (Gate-2 / Gate-3) + ADR reconcile

**Goal:** the engine's 3 gates as our package acceptance, including the (reconciled)
height/foreshortening calibration the flat arrow can't do.

Deliverables:
- **Gate 2 (direction):** for all frames `normalize(direction_tip − origin) ≈
  oracle.screen_direction_vector` (< 1e-2); `world_yaw_degrees == i·360/N`.
- **Gate 3 (elevation/foreshortening):** assert `camera_elevation_degrees == 30`; **and** the
  bake-side foreshortening check via R1 — render a known-proportion object and assert its
  rendered aspect/height matches the 30° projection. (This is the bake's job; the
  engine-side `height_world×24` sizing is verified by an engine test, not here.)
- **Reconcile ADR-0018/0019** to the engine truth: `render.rs::sprite_size` applies
  `height_world×24` engine-side; the bake = 30° foreshortening + correct `height_world`;
  no in-bake ×24. (Already noted in those ADRs' Resolution sections.)
- `build.py` runs all gates green.

Covers tasks #19, #20, and the ADR reconciliation.

---

## Sequencing / notes

- **R1 → R2 → R3.** R1 is self-contained; R2 needs R1's frames + the vendored engine schema;
  R3 needs R2's manifest + R1's renderer.
- Blender stays the M3 **production** renderer; R1 is the headless engine for autonomous
  progress + calibration. A Blender exporter can later emit the same package shape (R2) —
  the manifest/packing path is shared.
- The existing 2D `generate_arrow_pilot` stays as the verified **direction oracle**; R1 is the
  forward path for real 3D meshes (validate it against procedural meshes now).
- Everything here is spec-resolved — **no clarification needed mid-run.**
