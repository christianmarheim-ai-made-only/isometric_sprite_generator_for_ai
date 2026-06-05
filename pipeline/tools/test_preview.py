#!/usr/bin/env python3
"""Gate the model previewer (preview_source.py + blender_preview.py): render the source preview for
the rigged combat fixture and assert it emits the expected per-stage images + a correct preview_meta
(material->region map, no silent fallback, per-clip poses). Blender-skip.

Run: python pipeline/tools/test_preview.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_bake import find_blender  # noqa: E402
from preview_source import preview  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    if not find_blender():
        print("SKIP: Blender not found (preview gate)")
        return 0
    ok = True
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "prev"
        sheet = preview(PIPELINE_ROOT / "examples" / "grunt.asset.json", out)
        ok &= check("source preview sheet produced", sheet.exists())
        meta = json.loads((out / "preview_meta.json").read_text(encoding="utf-8"))
        ok &= check("rigged detected", meta["rigged"] is True)
        ok &= check("material->region covers head/torso/arms/legs (1,2,3,4)",
                    set(meta["material_region"].values()) == {1, 2, 3, 4})
        ok &= check(f"no region fallback (clean material names), got {meta['region_fallback_materials']}",
                    not meta["region_fallback_materials"])
        ok &= check("per-clip poses rendered for idle/move/punch/death",
                    {cp.split("/")[0] for cp in meta["clip_poses"]} == {"idle", "move", "punch", "death"})
        for f in ("mesh_front.png", "tex_front.png", "region_front.png", "bind_front.png", "pose_move_last.png"):
            ok &= check(f"stage image {f} present", (out / f).exists())
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
