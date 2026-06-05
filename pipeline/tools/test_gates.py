#!/usr/bin/env python3
"""Gate 2 (direction) + Gate 3 (elevation/foreshortening) acceptance (R3).

Gate 2 — direction (RENDERED-pixel based): for each pilot frame, measure the arrow's
tip from the rasterized color atlas (farthest alpha pixel from the rotation-invariant
draw center) and compare its screen direction to the INDEPENDENT vendored engine
oracle (expected_facing_table.game_iso_v1.json), within ~7deg. Because it reads the
actual pixels, a draw/winding bug in polygon_arrow() is catchable (an earlier
metadata-only version was circular — see the R2/R3 review). world_yaw_degrees ==
i*360/N is also checked.

Gate 3 — elevation/foreshortening: camera_elevation_degrees == 30 (= arcsin(0.5);
26.565 = arctan(0.5) is the on-screen tile-edge angle, NOT the camera elevation). Plus
a consistency check that the rasterizer reproduces the 30deg projection's proportions
(render3d is hardwired to 30deg, so this verifies rasterizer-vs-projection agreement,
NOT the elevation value, and NOT absolute size — the engine owns height_world*24).

Run: python pipeline/tools/test_gates.py   (exit 0 = all pass)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import meshes  # noqa: E402
from render3d import render_directions  # noqa: E402
from generate_arrow_pilot import DRAW_CENTER  # noqa: E402  (single-source the draw center)

ORACLE = PIPELINE_ROOT / "schema" / "engine" / "expected_facing_table.game_iso_v1.json"
PILOT = PIPELINE_ROOT / "output" / "arrow_pilot" / "manifest.json"
COLOR_ATLAS = PILOT.parent / "color_atlas.png"

# Independent 30deg re-derivation (literal constants, NOT render3d.project_raw) so a
# drift in the renderer's projection constants would be caught here.
SIN30 = 0.5
COS30 = math.cos(math.radians(30.0))
INV_SQRT2 = 1.0 / math.sqrt(2.0)


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def _angle_err(u: np.ndarray, v) -> float:
    u = u / (np.linalg.norm(u) or 1.0)
    v = np.asarray(v, dtype=float)
    v = v / (np.linalg.norm(v) or 1.0)
    return float(np.arccos(np.clip(float(np.dot(u, v)), -1.0, 1.0)))


def _expected_aspect(verts: np.ndarray) -> float:
    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]
    rx = (x - y) * INV_SQRT2
    ry = (x + y) * INV_SQRT2 * SIN30 - z * COS30
    return float((rx.max() - rx.min()) / (ry.max() - ry.min()))


def gate2(ok: bool) -> bool:
    manifest = json.loads(PILOT.read_text(encoding="utf-8"))
    oracle = {e["direction"]: e["screen_direction_vector"] for e in json.loads(ORACLE.read_text(encoding="utf-8"))}
    n = manifest["direction_count"]
    atlas = np.asarray(Image.open(COLOR_ATLAS).convert("RGBA"))
    dcx, dcy = DRAW_CENTER
    worst, yaw_ok = 0.0, True
    for f in manifest["frames"]:
        d = f["direction"]
        x, y, w, h = f["rect"]
        alpha = atlas[y:y + h, x:x + w, 3]
        ys, xs = np.nonzero(alpha > 0)
        # The arrow tip is the single rendered pixel farthest from the (rotation-
        # invariant) draw center; its bearing is the rendered screen direction (y-down).
        k = int(np.argmax((xs - dcx) ** 2 + (ys - dcy) ** 2))
        v = np.array([xs[k] - dcx, ys[k] - dcy], dtype=float)
        worst = max(worst, _angle_err(v, oracle[d]))
        if abs(f["world_yaw_degrees"] - d * 360.0 / n) > 1e-4:
            yaw_ok = False
    ok &= check(f"Gate2: RENDERED arrow tip matches vendored oracle, all 16 (worst {math.degrees(worst):.2f}deg)", worst < 0.12)
    ok &= check("Gate2: world_yaw_degrees == direction * 360/N", yaw_ok)
    return ok


def gate3(ok: bool) -> bool:
    manifest = json.loads(PILOT.read_text(encoding="utf-8"))
    elev = manifest["camera"]["camera_elevation_degrees"]
    # 30deg = arcsin(0.5) (the 2:1 ground requirement). 26.565 = arctan(0.5) is the
    # on-screen tile-edge angle, deliberately NOT the camera elevation.
    ok &= check("Gate3: camera_elevation_degrees == 30 (not the 26.565 tile-edge angle)", elev == 30)
    # Consistency: the rasterizer reproduces the 30deg projection's proportions.
    # render3d is hardwired to 30deg, so this checks rasterizer-vs-projection agreement,
    # not the elevation value (the field check above) and not absolute size (engine-owned).
    verts, faces = meshes.cube(1.0)
    expected = _expected_aspect(verts)
    frame = render_directions(verts, faces, n=16, canvas=(256, 256))[0]
    _, _, w, h = frame.bbox
    rendered = w / h
    rel = abs(rendered - expected) / expected
    ok &= check(f"Gate3: rasterized cube aspect {rendered:.3f} matches 30deg projection {expected:.3f} (rel {rel:.2%})", rel < 0.03)
    return ok


def main() -> int:
    ok = True
    ok = gate2(ok)
    ok = gate3(ok)
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
