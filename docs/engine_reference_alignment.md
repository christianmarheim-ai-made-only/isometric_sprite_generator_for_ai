# Engine Reference Alignment — `game_iso_v1` golden target

**Instruction-to-self (2026-06-05).** How to make this pipeline's output *completely
correct* against the engine. No code changed yet — this is the map + the gaps +
the follow-ups. Source material is read-only reference, not implemented here.

## What the reference is / where it lives

- **Source:** `C:\Code\Claude\dist\game_iso_v1_reference_v1.zip` — the engine team's
  contract handoff ("golden reference … the perfect shape to generate toward").
  Extracted scratch copy: `C:\Ny mappe\game_iso_v1_reference_v1\`.
- It contains the **engine-consumed manifest schema** (`CONTRACT/manifest.schema.json`),
  the format spec, an arrow-probe reconciliation note, a QA/acceptance doc, and a
  **verified working `arrow_probe` sample** (manifest + atlases + oracle).
- **Final authority is the engine source**, in this repo's sibling engine repo
  (`C:\Code\Claude`): `crates/client_bevy/src/sprite.rs :: parse_manifest` (loader)
  and `render.rs` (projection). The contract docs mirror it.

## Bottom line

1. Our **direction/azimuth convention is verified correct end-to-end** (all 16) —
   keep it exactly.
2. Our generated manifest is close but **would NOT load**: it lacks the required
   top-level **`camera` block**. Fix that first.
3. Generate toward the golden **shape**. The engine schema is
   `additionalProperties: true` everywhere and the loader **ignores unknown fields**,
   so all our richer debug fields (build, lockfile_hashes, expected_facing,
   surface_policy, animations, mask_rect, boxes) are fine to keep.

## Engine-consumed manifest (Gate 1 — required to load)

Required top-level: **`camera`, `direction_count`, `frame_canvas`, `atlases`, `frames`**
(+ `world_metrics` for `character`/`effect`).

- `camera.id` **must** `== "game_iso_v1"` (engine rejects otherwise). May also carry
  `azimuth_degrees`, `camera_elevation_degrees`, `projection`, `screen_y`, `tile_px`.
- `direction_count` ∈ {1,2,4,8,16}.
- `frame_canvas` = `[w,h]` px (anchors are in these px).
- `atlases.color.{path,size}` — **path is relative to the manifest's own dir**
  (e.g. `"color_atlas.png"`). `atlases.hitmask` optional (engine-future; keep emitting).
- `frames[]`: each needs `direction`, `rect [x,y,w,h]`, `anchor [x,y]` (frame_canvas
  px, y-down). Optional `sockets` (`origin`, `direction_tip`).
- `world_metrics {height_world>0, footprint_radius_world>0, eye_height_world? ≤ height}`
  — **required** for character/effect, optional/placeholder for probe.
- **Cross-field rules the schema can't express (loader-enforced):**
  (1) `frames.length == direction_count`; (2) directions `0..N-1` unique + all covered;
  (3) every `rect` has `w>0,h>0`.

## Concrete gaps: our `generate_arrow_pilot` output vs the engine format

| # | Gap | Severity |
|---|---|---|
| 1 | **No top-level `camera` block** (engine requires `camera.id`) → would be rejected | **blocker** |
| 2 | No per-frame **`direction_tip`** socket (we emit only `origin`); Gate 2 needs `tip−origin` | high |
| 3 | `frame_canvas` is `[128,128]`; golden sample is `[256,256]` (allowed to vary, but the target is 256) | medium |
| 4 | `schema_version`/`manifest_version` still debug/`*_fake_*` flavored; bump to e.g. `sprite_manifest_v1` for engine-facing output | low |

**Already aligned (do not change):** explicit per-frame `rect`s + 4px padding + 4px
extrusion; atlas `path` relative to manifest; R8 hitmask + palette
(`none0/head1/torso2/arms3/legs4/shield5/weapon6/gear7`); `world_metrics` semantics;
`expected_facing_table.json` oracle; the 16-direction convention.

## The 3 acceptance gates (a package is good only if all pass)

- **Gate 1 — engine acceptance:** validate manifest against the engine
  `manifest.schema.json` **plus** the two cross-field rules above.
- **Gate 2 — direction:** for each frame, `normalize(direction_tip − origin)` equals
  the oracle's `screen_direction_vector` (< 1e-2). Cardinals: yaw `45°→down`,
  `135°→left`, `225°→up`, `315°→right`; `dir00 (+X) → down-right [0.894,0.447]`.
- **Gate 3 — bake/elevation (separate; the flat arrow can't reveal it):** the
  `camera_elevation_degrees` metadata + how real heights foreshorten. **OPEN — see below.**

## Engine constants (authoritative)

- tile `64×32`; **`HEIGHT_SCREEN_SCALE = 24`** (px per world height-unit); `1 unit = 1 m`;
  ground plane `z = 0`; azimuth `45°`.
- Engine projection: `screen_x = (x−y)·32`, `screen_y = −(x+y)·16 + height·24`
  (Bevy **y-up**; our pipeline renders y-down and the engine re-flips — output must
  look right on screen, checked via the oracle).
- `eye_height_world` absent → engine uses **`0.85 · height_world`**.

## Camera elevation = 30° (engine-confirmed & verified); height is engine-sized by `height_world`

**Verified against the corrected reference package (`game_iso_v1_reference_v1_corrected.zip`, 2026-06-05).**
Elevation `30°` is confirmed and now documented consistently across the engine schema,
the manifest (`camera_elevation_degrees: 30` + new `camera_elevation_definition` /
`camera_geometry_note` fields), the format/QA/reconciliation specs, and a new
`CAMERA_GEOMETRY_NOTE.md`. The golden sample passes **Gate 1** (schema + cross-field
rules). Geometry: `sin(elevation)=0.5 → 30°` for the 2:1 ground tile; `arctan(0.5)≈26.565°`
is the on-screen tile-edge angle, **not** the camera elevation (a 26.565° camera would
render ≈2.236:1 — wrong). This matches ADR-0018.

**Height — RESOLVED (read `crates/client_bevy/src/render.rs`):** `render.rs::sprite_size`
sets on-screen **height = `height_world × 24`** and **width = height × frame_aspect**
(`rect.w/rect.h`). The `×24` is applied **engine-side**. So the bake's obligation is
**azimuth 45° + elevation 30°** (correct ground + height *foreshortening*, which fixes the
frame's aspect + internal proportions) **+ emit correct `world_metrics.height_world`** —
**no in-bake `×24`**. ADR-0018/0019 reconciled accordingly (see their Resolution sections).
The bake-side calibration is therefore a *foreshortening/aspect* check at 30° (R3), not a
24-px/unit check.

> **Reference-package defect (engine-side):** the corrected zip's `README.md` was not
> updated — it still says *"`camera_elevation_degrees: 30` … That is wrong … bake at
> 26.565°"*, contradicting every other (corrected) doc in the same package. Flagged for
> the engine team; harmless to us (the README is not engine-consumed).

## Instruction when work resumes

1. **Add the `camera` block** + per-frame **`direction_tip`** socket to
   `generate_arrow_pilot` (keep all extras). This makes our output engine-loadable.
2. **Vendor** the engine `manifest.schema.json` + golden sample manifest into the repo
   as a CI fixture; add a **Gate-1 engine-acceptance** check (schema + the 2 cross-field
   rules) to `build.py`.
3. Add **Gate-2** (sockets→oracle direction) and **Gate-3** (elevation metadata) to the
   package acceptance.
4. **Resolve the elevation** (user) → reconcile/revise ADR-0018; only then bake 3D.
5. Keep emitting `expected_facing_table.json` and the hitmask.
6. **M3 real art:** bake at the resolved elevation; emit real `world_metrics`; run the
   height calibration (2 m → 48 px) before baking the roster.

> Note: this refines, and takes precedence over, the manifest-shape assumptions in
> `docs/next_slices_plan.md` (P2/M3). The golden sample here is the authority for shape.
