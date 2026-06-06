#!/usr/bin/env python3
"""Acceptance test for the terrain bake (closes terrain-variant-class-three-way-drift).

Asserts the ADR-0006 contract end-to-end:
  - the emitted manifest has variant_class:"terrain", direction_count:1, a single frame
    (direction 0, rect = whole atlas, anchor = atlas centre) and NO world_metrics block;
  - the tile is a clean 2:1; the four corners are alpha 0 and the centre is alpha 255;
  - the source texture is seamless in both axes (so the diamond grid tiles seamlessly);
  - the package PASSES Gate-1 (engine acceptance) — i.e. the engine loader would accept it;
  - a WRONG-elevation bake is REJECTED on emit by Gate-3 (never produces a committable package).

Run: python pipeline/tools/test_terrain_bake.py   (exit 0 = all pass)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake_terrain import bake_terrain, procedural_arid_texture, is_seamless  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "ground_test"
        m = bake_terrain(out, "ground_test_v1", write_preview=False)

        # --- manifest shape (ADR-0006 sec.6-8) ---
        ok &= check("variant_class == terrain", m.get("variant_class") == "terrain")
        ok &= check("direction_count == 1", m.get("direction_count") == 1)
        ok &= check("exactly one frame", len(m.get("frames", [])) == 1)
        f0 = m["frames"][0]
        ok &= check("frame 0 is direction 0", f0.get("direction") == 0)
        ok &= check("rect == whole atlas [0,0,256,128]", f0.get("rect") == [0, 0, 256, 128])
        ok &= check("anchor == atlas centre [128,64]", f0.get("anchor") == [128.0, 64.0])
        ok &= check("NO world_metrics block", "world_metrics" not in m)
        ok &= check("camera id == game_iso_v1", m["camera"]["id"] == "game_iso_v1")
        ok &= check("camera elevation stamped == 30", m["camera"]["camera_elevation_degrees"] == 30)
        ok &= check("frame_canvas 2:1 [256,128]", m.get("frame_canvas") == [256, 128])

        # --- Gate-1: the engine loader would accept it ---
        ok &= check("Gate-1 engine_accept passes (no reasons)", engine_accept(m) == [])

        # --- alpha-cut (ADR-0006 sec.4) ---
        atlas = np.asarray(Image.open(out / "color_atlas.png").convert("RGBA"))
        corners_clear = (atlas[0, 0, 3] == 0 and atlas[0, -1, 3] == 0
                         and atlas[-1, 0, 3] == 0 and atlas[-1, -1, 3] == 0)
        ok &= check("four corner triangles are alpha 0", corners_clear)
        ok &= check("diamond centre is alpha 255", atlas[64, 128, 3] == 255)

        # --- seamlessness (ADR-0006 sec.5): grid is seamless IFF the source is, in both axes ---
        ok &= check("procedural source tiles seamlessly (both axes)", is_seamless(procedural_arid_texture(256)))

        # --- Gate-3 (emit reject): a wrong-elevation bake never produces a package ---
        rejected = False
        try:
            bake_terrain(Path(td) / "bad", "bad_elevation_v1", elevation=26.565, write_preview=False)
        except SystemExit:
            rejected = True
        ok &= check("wrong-elevation (26.565) bake REJECTED on emit by Gate-3", rejected)
        ok &= check("rejected bake wrote NO package", not (Path(td) / "bad" / "manifest.json").exists())

        # --- a non-2:1 / non-multiple size is rejected ---
        bad_size = False
        try:
            bake_terrain(Path(td) / "badsize", "bad_size_v1", size=(100, 50), write_preview=False)
        except SystemExit:
            bad_size = True
        ok &= check("non-(64x32-multiple) tile size rejected", bad_size)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
