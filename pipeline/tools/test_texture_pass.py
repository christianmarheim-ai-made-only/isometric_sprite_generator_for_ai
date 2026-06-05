#!/usr/bin/env python3
"""Gate the Workbench TEXTURE render pass. Every other Blender gate hits the MATERIAL branch, so the
base-color-texture path (the real-art look) was never baked -- a Blender texture-shading regression
would ship silently. Bakes the UV-textured humanoid (humanoid_textured.glb, checker base color) and
asserts the renderer took the TEXTURE branch (has_tex) AND the baked body shows real texture
variation (the checker), not a flat per-region fill. Blender-skip.

Run: python pipeline/tools/test_texture_pass.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_bake import find_blender, bake_blender  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    blender = find_blender()
    if not blender:
        print("SKIP: Blender not found (texture-pass gate)")
        return 0
    glb = PIPELINE_ROOT / "examples" / "texture_starter" / "humanoid_textured.glb"
    if not glb.exists():
        print(f"FAIL: missing fixture {glb}")
        return 1
    ok = True
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "tex"
        _m, meta = bake_blender(out, blender, str(glb), "humanoid_textured")
        ok &= check("renderer detected an embedded base-color texture (has_tex) -> TEXTURE branch",
                    meta.get("has_tex") is True)

        # body pixels (where the hit-mask is a region) should carry MANY distinct colors (the
        # checker), not a handful of flat region fills. Quantize to drop AA noise.
        color = np.asarray(Image.open(out / "color_atlas.png").convert("RGB"))
        hit = np.asarray(Image.open(out / "hitmask_atlas.png").convert("L"))
        body = color[hit > 0]
        distinct = len(np.unique((body >> 3).astype(np.uint16) @ np.array([1, 64, 4096], dtype=np.uint16)))
        ok &= check(f"textured body has rich colour variation (checker), {distinct} quantized colours > 30",
                    distinct > 30)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
