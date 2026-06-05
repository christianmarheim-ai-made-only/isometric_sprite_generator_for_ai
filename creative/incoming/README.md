# Incoming sprite-package intake

Drop a delivered character/effect package here (one subfolder per package, or the files directly),
then batch-bake + review them in one pass:

```bash
python pipeline/tools/bake_batch.py creative/incoming --sheets
# preview what would bake, without baking:
python pipeline/tools/bake_batch.py creative/incoming --dry-run
```

It bakes every `*.asset.json` found (recursively) into `pipeline/output/incoming_batch/<variant>/`
through the full hardened path — up-axis correction, provenance stamping, Gate-1, and the
silent-failure detectors — then writes one `build_index.json` and prints, per package: **clean**,
**flagged** (with the warning codes), or **failed**. A bad package does not abort the batch.

## A delivered package contains
- `<id>.asset.json` — the contract front door (drives the bake). REQUIRED.
- `<id>.glb` — rigged + skinned mesh with embedded clips/texture. REQUIRED.
- `<id>_anim.json` — `anim_clips_v1` clips (if `files.animation_clips` is set).
- companions (optional, reference): `_materials`, `_hitbox`, `_sockets`, `_physical_metrics`,
  `_texture_atlas.png`, the generator, a `validation_report.json`.

## Contract reminders (the rough edges the pirate PoC hit)
- **`geometry.up`** must match how the glb is actually authored — `"z"` (Z-up) **and** `"y"`
  (standard glTF) are both honored now; declaring the wrong one bakes the character **lying down**
  (caught by `non_upright_biped` / `world_metrics_mismatch`).
- **`playback` is `loop | once`** — never `hold` (lint rejects it; `once` holds the terminal frame).
- **`region_source: "material_name"`** needs the body-part keyword (`head`/`torso`/`arms`/`legs`) in
  each material name, or it silently defaults to torso (`region_fallback_torso`).
- **UVs must span each material's tile** or the embedded texture renders flat (`degenerate_uv`).
- A full multi-clip combat character at 256² **overflows a 4096 single page** (`oversize_atlas_page`)
  — loads up to the GPU cap; shard / shrink-canvas / curate clips for production (TASK-018).

Warning-code reference + triage: `docs/build_log_warnings.md`.
The baked output (`pipeline/output/incoming_batch/`) is regenerable and gitignored — commit the
delivered **source** package here, not the bake output.
