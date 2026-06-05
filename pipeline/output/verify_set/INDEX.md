# Sprite verification set

Real `game_iso_v1` packages baked across every input route. Each folder has `color_atlas.png`, `hitmask_atlas.png`, `manifest.json`, and two **contact sheets** to eyeball:

- `*_color_sheet.png` — every (state, frame, direction) in a grid. **Magenta cross** = anchor (foot/origin); **cyan arrow** = facing. Scan a row left→right to watch it spin through 16 directions; scan a column top→bottom to watch the animation.
- `*_hit_sheet.png` — the R8 hit-mask recoloured by region (**head=red, torso=green, arms=blue, legs=yellow**). Confirms gameplay hit regions exist and track the body. (Body-only this iteration — no weapon/shield regions.)

| Variant | Route | Class | Directions | States×frames | Frames | Atlas | Gate-1 | Sheets |
|---|---|---|---|---|---|---|---|---|
| `humanoid_obj` | numpy · OBJ static | character | 16 | idle×1 (single-state) | 16 | 1056×1056 | ✅ | `humanoid_obj/humanoid_obj_color_sheet.png` · `humanoid_obj/humanoid_obj_hit_sheet.png` |
| `humanoid_anim` | numpy · procedural multi-state (idle/walk/attack) | character | 16 | attack×3, idle×1, walk×4 | 128 | 2041×1576 | ✅ | `humanoid_anim/humanoid_anim_color_sheet.png` · `humanoid_anim/humanoid_anim_hit_sheet.png` |
| `humanoid_v1` | Blender · static glTF | character | 16 | idle×1 (single-state) | 16 | 1056×1056 | ✅ | `humanoid_v1/humanoid_v1_color_sheet.png` · `humanoid_v1/humanoid_v1_hit_sheet.png` |
| `sparrow` | Blender · rigged+animated (idle/fly) | character | 16 | fly×4, idle×1 | 80 | 2029×526 | ✅ | `sparrow/sparrow_color_sheet.png` · `sparrow/sparrow_hit_sheet.png` |
| `crow` | Blender · rigged+animated (idle/fly) — reuses sparrow's rig+clip | character | 16 | fly×4, idle×1 | 80 | 2029×526 | ✅ | `crow/crow_color_sheet.png` · `crow/crow_hit_sheet.png` |

## What correct looks like
- **16 distinct directions**, rotating smoothly; the cyan facing arrow sweeps once around as d00→d15.
- **Anchor stays put** at the foot/origin across directions and animation frames (the character animates around a stable ground point).
- **Animation reads**: `humanoid_anim` walk legs/arms swing; attack arm ramps forward. `sparrow`/`crow` fly wings flap (idle = level).
- **Reuse**: `sparrow` and `crow` are different meshes/colours with identical motion — one `bird_v1` rig + one fly clip drives both.
- **Hit regions** cover the silhouette and match the body part under them.

Regenerate: `python pipeline/tools/produce_verify_set.py`

**Build logs:** per-bake `<variant>/build_log.json` (inputs+hashes, env, gate, warnings) + batch `build_index.json`. Diff two runs to verify a fix.
