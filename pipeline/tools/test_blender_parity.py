#!/usr/bin/env python3
"""R7 gate: Blender-render the humanoid to a temp dir and assert render3d <-> Blender
camera parity (worst err ~0) + Gate-1 acceptance + a discrete R8 hitmask with all four
body regions. Skips gracefully (exit 0) when Blender is not installed.

Run: python pipeline/tools/test_blender_parity.py
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

from blender_bake import find_blender, bake_blender, camera_parity_error  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    blender = find_blender()
    if not blender:
        print("SKIP: Blender not found; R7 parity gate not run on this machine.")
        return 0
    ok = True
    with tempfile.TemporaryDirectory() as td:
        manifest, meta = bake_blender(Path(td) / "humanoid_blender", blender)
        parity = camera_parity_error(meta)
        ok &= check(f"render3d <-> Blender camera parity (worst {parity:.4f} < 0.02)", parity < 0.02)
        ok &= check("Blender package engine-accepted (Gate-1)", not engine_accept(manifest))
        mask = np.asarray(Image.open(Path(td) / "humanoid_blender" / "hitmask_atlas.png").convert("L"))
        vals = {int(v) for v in np.unique(mask)}
        ok &= check(f"hitmask discrete & within body palette {{0..4}} (got {sorted(vals)})", vals <= {0, 1, 2, 3, 4})
        ok &= check("all 4 body regions present (head/torso/arms/legs)", {1, 2, 3, 4} <= vals)
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
