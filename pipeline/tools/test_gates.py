#!/usr/bin/env python3
"""Gate 2 (direction) + Gate 3 (elevation/foreshortening) acceptance (R3).

Gate 2 — direction: for the pilot manifest, normalize(direction_tip - origin) per
frame equals the INDEPENDENT vendored engine oracle's screen_direction_vector
(< 1e-2), and world_yaw_degrees == i*360/N. (Compared to the vendored engine file,
not to a sibling Python function.)

Gate 3 — elevation/foreshortening: camera_elevation_degrees == 30 (reject 26.565,
the tile-edge angle); and a known cube rendered via R1 has the screen-bbox aspect the
30deg orthographic projection predicts (the bake-side foreshortening check; the
engine owns the absolute height_world*24 sizing, so that is NOT checked here).

Run: python pipeline/tools/test_gates.py   (exit 0 = all pass)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import meshes  # noqa: E402
from render3d import render_directions  # noqa: E402

ORACLE = PIPELINE_ROOT / "schema" / "engine" / "expected_facing_table.game_iso_v1.json"
PILOT = PIPELINE_ROOT / "output" / "arrow_pilot" / "manifest.json"

# Independent 30deg re-derivation (literal constants, NOT render3d.project_raw) so a
# drift in the renderer's projection constants would be caught here.
SIN30 = 0.5
COS30 = math.cos(math.radians(30.0))
INV_SQRT2 = 1.0 / math.sqrt(2.0)


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def _expected_aspect(verts: np.ndarray) -> float:
    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]
    rx = (x - y) * INV_SQRT2
    ry = (x + y) * INV_SQRT2 * SIN30 - z * COS30
    return float((rx.max() - rx.min()) / (ry.max() - ry.min()))


def gate2(ok: bool) -> bool:
    manifest = json.loads(PILOT.read_text(encoding="utf-8"))
    oracle = {e["direction"]: e["screen_direction_vector"] for e in json.loads(ORACLE.read_text(encoding="utf-8"))}
    n = manifest["direction_count"]
    worst, yaw_ok = 0.0, True
    for f in manifest["frames"]:
        d = f["direction"]
        origin = np.array(f["sockets"]["origin"], dtype=float)
        tip = np.array(f["sockets"]["direction_tip"], dtype=float)
        v = tip - origin
        v = v / (np.linalg.norm(v) or 1.0)
        worst = max(worst, float(np.linalg.norm(v - np.array(oracle[d]))))
        if abs(f["world_yaw_degrees"] - d * 360.0 / n) > 1e-4:
            yaw_ok = False
    ok &= check(f"Gate2: direction_tip-origin matches vendored engine oracle, all 16 (worst {worst:.2e})", worst < 1e-2)
    ok &= check("Gate2: world_yaw_degrees == direction * 360/N", yaw_ok)
    return ok


def gate3(ok: bool) -> bool:
    manifest = json.loads(PILOT.read_text(encoding="utf-8"))
    elev = manifest["camera"]["camera_elevation_degrees"]
    ok &= check("Gate3: camera_elevation_degrees == 30", elev == 30)
    ok &= check("Gate3: elevation is NOT 26.565 (the tile-edge screen angle)", not (abs(elev - 26.565) < 0.5))
    verts, faces = meshes.cube(1.0)
    expected = _expected_aspect(verts)
    frame = render_directions(verts, faces, n=16, canvas=(256, 256))[0]
    _, _, w, h = frame.bbox
    rendered = w / h
    rel = abs(rendered - expected) / expected
    ok &= check(f"Gate3: cube rendered aspect {rendered:.3f} ~= 30deg projection {expected:.3f} (rel {rel:.2%})", rel < 0.08)
    return ok


def main() -> int:
    ok = True
    ok = gate2(ok)
    ok = gate3(ok)
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
