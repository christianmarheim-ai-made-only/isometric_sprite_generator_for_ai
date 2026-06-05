#!/usr/bin/env python3
"""produce_verify_set.py -- bake a SET of real sprite packages that exercises every input route,
generate human-viewable contact sheets, and Gate-1 each one. The deliverable for "produce content
so I can verify it works": open pipeline/output/verify_set/INDEX.md and the *_sheet.png files.

Routes covered:
  humanoid_obj   numpy   OBJ static                         (bake_asset -> numpy baker)
  humanoid_anim  numpy   procedural multi-state idle/walk/attack
  humanoid_v1    Blender static glTF                        (bake_asset -> Blender baker)
  sparrow        Blender rigged+animated idle/fly
  crow           Blender rigged+animated idle/fly           (reuses sparrow's rig + clip)

  python pipeline/tools/produce_verify_set.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
EX = PIPELINE_ROOT / "examples"
VERIFY = PIPELINE_ROOT / "output" / "verify_set"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake_asset import bake_asset            # noqa: E402
from bake import bake_character_anim          # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402
from make_contact_sheet import contact_sheet  # noqa: E402
from build_log import write_build_log, write_build_index, index_summary  # noqa: E402

JOBS = [
    ("humanoid_obj", "humanoid_obj.asset.json", "numpy · OBJ static"),
    ("humanoid_anim", None, "numpy · procedural multi-state (idle/walk/attack)"),
    ("humanoid_v1", "humanoid_v1.asset.json", "Blender · static glTF"),
    ("sparrow", "sparrow.asset.json", "Blender · rigged+animated (idle/fly)"),
    ("crow", "crow.asset.json", "Blender · rigged+animated (idle/fly) — reuses sparrow's rig+clip"),
]


def _states_summary(m: dict) -> str:
    anims = m.get("animations")
    if anims:
        return ", ".join(f"{s}×{anims[s]['frames']}" for s in sorted(anims))
    return "idle×1 (single-state)"


def main() -> int:
    VERIFY.mkdir(parents=True, exist_ok=True)
    rows, logs = [], []
    for variant, asset, route in JOBS:
        out = VERIFY / variant
        print(f"\n=== {variant}  [{route}] ===")
        if asset:
            m = bake_asset(EX / asset, out)
        else:
            m = bake_character_anim(out, variant_id=variant)
            print(f"BAKE OK [numpy/procedural]: {variant} -> {out}  ({len(m['frames'])} frames)")
        errs = engine_accept(m)
        gate = "PASS" if not errs else "FAIL: " + "; ".join(errs)
        # bake_asset already wrote build_log.json; the procedural path didn't -> write one now
        blog = out / "build_log.json"
        logs.append(json.loads(blog.read_text(encoding="utf-8")) if blog.exists()
                    else write_build_log(out, m, route, gate_reasons=errs, meta={}))
        info = contact_sheet(out)
        rows.append({
            "variant": variant, "route": route, "gate": gate,
            "frames": len(m["frames"]), "states": _states_summary(m),
            "directions": m["direction_count"],
            "atlas": m["atlases"]["color"]["size"],
            "color_sheet": Path(info["color_sheet"]).name,
            "hit_sheet": Path(info["hit_sheet"]).name,
            "class": m.get("variant_class", "?"),
        })
        print(f"  gate: {gate}")
        print(f"  sheets: {Path(info['color_sheet']).name}, {Path(info['hit_sheet']).name}")

    lines = [
        "# Sprite verification set",
        "",
        "Real `game_iso_v1` packages baked across every input route. Each folder has "
        "`color_atlas.png`, `hitmask_atlas.png`, `manifest.json`, and two **contact sheets** to "
        "eyeball:",
        "",
        "- `*_color_sheet.png` — every (state, frame, direction) in a grid. **Magenta cross** = "
        "anchor (foot/origin); **cyan arrow** = facing. Scan a row left→right to watch it spin "
        "through 16 directions; scan a column top→bottom to watch the animation.",
        "- `*_hit_sheet.png` — the R8 hit-mask recoloured by region "
        "(**head=red, torso=green, arms=blue, legs=yellow**). Confirms gameplay hit regions exist "
        "and track the body. (Body-only this iteration — no weapon/shield regions.)",
        "",
        "| Variant | Route | Class | Directions | States×frames | Frames | Atlas | Gate-1 | Sheets |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['variant']}` | {r['route']} | {r['class']} | {r['directions']} | "
            f"{r['states']} | {r['frames']} | {r['atlas'][0]}×{r['atlas'][1]} | "
            f"{'✅' if r['gate']=='PASS' else '❌ '+r['gate']} | "
            f"`{r['variant']}/{r['color_sheet']}` · `{r['variant']}/{r['hit_sheet']}` |"
        )
    lines += [
        "",
        "## What correct looks like",
        "- **16 distinct directions**, rotating smoothly; the cyan facing arrow sweeps once "
        "around as d00→d15.",
        "- **Anchor stays put** at the foot/origin across directions and animation frames (the "
        "character animates around a stable ground point).",
        "- **Animation reads**: `humanoid_anim` walk legs/arms swing; attack arm ramps forward. "
        "`sparrow`/`crow` fly wings flap (idle = level).",
        "- **Reuse**: `sparrow` and `crow` are different meshes/colours with identical motion — "
        "one `bird_v1` rig + one fly clip drives both.",
        "- **Hit regions** cover the silhouette and match the body part under them.",
        "",
        "Regenerate: `python pipeline/tools/produce_verify_set.py`",
        "",
        "**Build logs:** per-bake `<variant>/build_log.json` (inputs+hashes, env, gate, warnings) + "
        "batch `build_index.json`. Diff two runs to verify a fix.",
    ]
    (VERIFY / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    idx = write_build_index(VERIFY, logs, batch_id="verify_set")

    failed = [r["variant"] for r in rows if r["gate"] != "PASS"]
    total_warn = sum(r["warnings"] for r in idx)
    print("\n" + "=" * 60)
    print(index_summary(idx))
    print("=" * 60)
    print(f"VERIFY SET: {len(rows)} packages -> {VERIFY}")
    print(f"INDEX: {VERIFY / 'INDEX.md'}  |  BUILD INDEX: {VERIFY / 'build_index.json'}")
    if total_warn:
        print(f"WARNINGS this batch: {total_warn} (see per-variant build_log.json)")
    if failed:
        print(f"GATE FAILURES: {failed}")
        return 1
    print("ALL PACKAGES PASS GATE-1 [OK]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
