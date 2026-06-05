#!/usr/bin/env python3
"""R8 demo/gate: bake a RIGGED + ANIMATED bird (an external glTF with a skeleton + clips) into a
multi-state package by SAMPLING its clips -- proving the pipeline runs real animated models.
Skips if Blender is absent.

The "many birds, one rig+animation" reuse: pipeline/test_meshes/sparrow.glb + crow.glb share the
bird_v1 rig and the SAME idle/fly authoring (gen_bird_fixture); only the mesh/color differs. This
gate bakes one and asserts: multi-state (idle + a real multi-frame fly), Gate-1 acceptance, camera
parity, that the fly animation actually MOVES, and that the body HIT regions are present.

Run: python pipeline/tools/test_rigged_anim.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_bake import bake_animated, find_blender, camera_parity_error  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402

GLB = PIPELINE_ROOT / "test_meshes" / "sparrow.glb"
ANIMS = {"idle": {"clip": "idle", "frames": 1, "fps": 1, "playback": "loop"},
         "fly": {"clip": "fly", "frames": 3, "fps": 12, "playback": "loop"}}


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    blender = find_blender()
    if not blender:
        print("SKIP: Blender not found; rigged-animation demo not run on this machine.")
        return 0
    if not GLB.exists():
        print("FAIL: pipeline/test_meshes/sparrow.glb fixture missing")
        return 1
    ok = True
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "sparrow"
        m, meta = bake_animated(out, blender, str(GLB), ANIMS, "sparrow")
        ok &= check("rigged bird -> engine-accepted MULTI-STATE package (Gate-1)", not engine_accept(m))
        ok &= check(f"render3d <-> Blender camera parity (worst {camera_parity_error(meta):.4f} < 0.02)",
                    camera_parity_error(meta) < 0.02)
        ok &= check("states = idle + fly; fly is a REAL multi-frame clip; total = 16*(1+3)",
                    set(m["animations"]) == {"idle", "fly"} and m["animations"]["fly"]["frames"] >= 2
                    and len(m["frames"]) == 16 * (1 + 3))
        a = Image.open(out / "color_fly_f0_dir02.png").convert("RGB")
        b = Image.open(out / "color_fly_f2_dir02.png").convert("RGB")
        ok &= check("fly animation actually MOVES (sampled pose changes between frames)",
                    ImageChops.difference(a, b).getbbox() is not None)
        mask = np.asarray(Image.open(out / "hitmask_atlas.png").convert("L"))
        vals = {int(v) for v in np.unique(mask)}
        ok &= check(f"hitmask body regions present (got {sorted(vals)})", {1, 2, 3, 4} <= vals)
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
