# Stage 8 — Self-check (texture_capable + full lint), the front door

## PROMPT

Before packaging, run the pipeline's **front-door** checks yourself and fix every issue. These are
deterministic, no-Blender, and run BEFORE any bake — passing them is the cost of admission.

Run, in order:

1. **Texture capability** (textured only):
   ```
   python pipeline/tools/glb_texture_probe.py <variant>.glb
   ```
   Must print `CAPABLE` with `reasons=[]`: real non-degenerate in-range UVs on every part
   (`degenerate_uv: []`, `out_of_range_uv: []`, `no_uv: 0`) AND a bound `baseColorTexture`
   (`bound_textures > 0`, an image present). `NOT-CAPABLE` means you cannot declare `textured`.

2. **Full manifest lint:**
   ```
   python pipeline/tools/lint_external_asset.py <variant>.asset.json
   ```
   Exit 0 = OK. This checks: schema validity against `external_asset_v2`; declared `files`/`textures`
   exist; `rig` is a known profile; `archetype` ↔ `rig`; `texture_mode` present; the textured/​flat_region
   capability rules (incl. `flat_region_bound_texture`, `flat_region_real_albedo`); `animations`
   well-formed; the archetype's **required clips** are declared (`missing_required_clip`); off-vocab
   clip warnings; `skin_binding` bones exist; and any declared waivers (must be in-date, single-check,
   never claim `real_albedo`).

3. **Manifest sanity** — confirm the producer-owned fields are coherent: `texture_mode`, `archetype`,
   `rig`, `variant_id`, `geometry.forward`, `world_metrics`, `animations` (idle/attack/hit/death with
   matching `frames`/`fps`/`playback`), and the `<variant>_hitbox.json` sidecar present.

Fix every reported issue and re-run until clean. Do not waive a real defect — a waiver is a named,
expiring, single-check downgrade for an accepted exception, never a way past a true error, and never
on `real_albedo`.

## CONSTRAINTS

- These checks need no Blender; they are the same code the intake/batch path runs, so a clean local run
  predicts a clean intake.
- A `textured` `.obj` is auto-rejected (`obj_textured_unsupported`) — textured must be GLB/GLTF.

## GATES THIS STAGE MUST PASS

- `texture_capable` (textured) — CAPABLE, `reasons=[]`.
- Full `lint_external_asset` — exit 0, zero issues, including:
  `texture_mode_declared`, `archetype_matches_rig`, `required_clips_present`,
  `flat_region_no_bound_texture`, `flat_region_no_real_albedo`, `referenced_files_exist`,
  and any `waiver_*` validity.

## DONE WHEN

`glb_texture_probe` reports CAPABLE (for textured) and `lint_external_asset.py <variant>.asset.json`
exits 0 with `ASSET LINT OK`. The package is admissible to the bake.
