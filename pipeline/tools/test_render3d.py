#!/usr/bin/env python3
"""Tests for the R1 headless 3D renderer.

Validates the camera against the engine's ground-direction oracle and checks that
meshes actually rasterize with sane silhouettes/aspect. No Blender, no GPU.

Run: python pipeline/tools/test_render3d.py   (exit 0 = all pass)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from render3d import project_raw, ground_screen_direction, render_directions  # noqa: E402
import meshes  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True

    # 1. Camera ground projection matches the engine oracle for all 16 directions.
    worst = 0.0
    for i in range(16):
        yaw = i * (2 * math.pi / 16)
        fwd = np.array([[math.cos(yaw), math.sin(yaw), 0.0]])
        raw, _ = project_raw(fwd)
        v = raw[0]
        v = v / (np.linalg.norm(v) or 1.0)
        exp = ground_screen_direction(yaw)
        worst = max(worst, float(np.linalg.norm(v - exp)))
    ok &= check(f"camera ground direction matches oracle for all 16 (worst {worst:.2e})", worst < 1e-6)

    # 2. dir00 (+X) projects down-right = [0.894, 0.447] (the golden dir00 vector).
    raw0, _ = project_raw(np.array([[1.0, 0.0, 0.0]]))
    d0 = raw0[0] / np.linalg.norm(raw0[0])
    ok &= check("dir00 == [0.894, 0.447]", abs(d0[0] - 0.894427) < 1e-4 and abs(d0[1] - 0.447214) < 1e-4)

    # 3. A cube renders to a non-empty RGBA frame at the canvas size.
    v, f = meshes.cube(1.0)
    frames = render_directions(v, f, n=16, canvas=(256, 256))
    f0 = frames[0]
    ok &= check("16 frames produced", len(frames) == 16)
    ok &= check("frame is RGBA 256x256", f0.rgba.mode == "RGBA" and f0.rgba.size == (256, 256))
    ok &= check("cube frame has filled (alpha>0) pixels", f0.bbox[2] > 0 and f0.bbox[3] > 0)

    # 4. A tall pole renders taller than it is wide (foreshortened height still dominates).
    pv, pf = meshes.pole(height=2.0, radius=0.06)
    pframe = render_directions(pv, pf, n=4, canvas=(256, 256))[0]
    _, _, pw, ph = pframe.bbox
    ok &= check(f"pole renders taller than wide (w={pw}, h={ph})", ph > pw)

    # 5. The foot anchor is identical across directions (the world origin is rotation-invariant).
    anchors = {tuple(round(c, 3) for c in fr.anchor) for fr in frames}
    ok &= check("foot anchor stable across all directions", len(anchors) == 1)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
