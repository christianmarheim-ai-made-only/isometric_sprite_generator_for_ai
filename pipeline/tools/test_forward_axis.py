#!/usr/bin/env python3
"""Gate the LIVE forward-axis correction: a model authored facing the wrong axis is now fixed by the
declared `geometry.forward` (the bake rotates it onto +X = direction 0), instead of baking 90/180 deg
rotated. Uses the deterministic NUMPY path (bake_mesh), so it runs WITHOUT Blender and pins the sign.

The proof: take the humanoid, author a copy facing +Y (rotate it 90 deg about Z), and bake it with
forward:"+y". It must equal the +X-authored humanoid baked with forward:"+x". A WRONG forward must NOT
match (the correction actually does something), and forward:"+x" must be a byte-exact no-op.

Run: python pipeline/tools/test_forward_axis.py
"""
from __future__ import annotations

import hashlib
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake import bake_mesh  # noqa: E402
from constants import REGION_NAMES, forward_yaw  # noqa: E402
from mesh_io import load_obj  # noqa: E402
from render3d import rotate_z  # noqa: E402

HUMANOID = PIPELINE_ROOT / "test_meshes" / "humanoid.obj"


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_obj(path: Path, verts, faces, freg) -> None:
    """Write a minimal OBJ with one usemtl group per HIT region (region name -> load_obj region id)."""
    lines = []
    for v in verts:
        lines.append(f"v {float(v[0]):.10f} {float(v[1]):.10f} {float(v[2]):.10f}")
    by_region = defaultdict(list)
    for fi, f in enumerate(faces):
        by_region[int(freg[fi])].append(f)
    for rid, fs in sorted(by_region.items()):
        lines.append(f"usemtl {REGION_NAMES.get(rid, 'torso')}")
        for f in fs:
            lines.append("f " + " ".join(str(int(i) + 1) for i in f))  # OBJ is 1-based
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ok = True
    ok &= check("forward_yaw('+x') == 0 (the no-op default)", abs(forward_yaw("+x")) < 1e-12)
    ok &= check("forward_yaw signs (+y=-90, -y=+90, -x=+-180)",
                abs(math.degrees(forward_yaw("+y")) + 90) < 1e-9
                and abs(math.degrees(forward_yaw("-y")) - 90) < 1e-9
                and abs(abs(math.degrees(forward_yaw("-x"))) - 180) < 1e-9)

    if not HUMANOID.exists():
        print("SKIP: humanoid.obj fixture missing")
        return 0 if ok else 1

    vX, faces, freg = load_obj(str(HUMANOID), up="z")     # +X-authored, contract-normalized
    vY = rotate_z(np.asarray(vX, dtype=float), math.pi / 2)  # the SAME model authored facing +Y

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        write_obj(td / "x.obj", vX, faces, freg)
        write_obj(td / "y.obj", vY, faces, freg)

        outX = td / "outX"
        outY = td / "outY"
        outW = td / "outWrong"
        outD = td / "outDefault"
        bake_mesh(str(td / "x.obj"), outX, variant_id="fx_x", up="z", forward="+x")
        bake_mesh(str(td / "y.obj"), outY, variant_id="fx_y", up="z", forward="+y")   # corrected
        bake_mesh(str(td / "y.obj"), outW, variant_id="fx_w", up="z", forward="+x")   # NOT corrected
        bake_mesh(str(td / "x.obj"), outD, variant_id="fx_d", up="z")                  # default == +x

        def hm(o):
            return _sha(o / "hitmask_atlas.png")

        def col(o):
            from PIL import Image
            return np.asarray(Image.open(o / "color_atlas.png").convert("RGBA"), dtype=np.int16)

        # CORRECTION: +Y-authored + forward:"+y" == +X-authored + forward:"+x" (discrete hitmask -> exact).
        ok &= check("forward correction: +Y model (forward:+y) hitmask == +X model (forward:+x)",
                    hm(outY) == hm(outX))
        cX, cY = col(outX), col(outY)
        same_shape = cX.shape == cY.shape
        ndiff = int(np.count_nonzero(np.abs(cX - cY).max(axis=2) > 2)) if same_shape else -1
        ok &= check(f"forward correction: color atlas matches within edge tolerance (shape ok, {ndiff} px differ)",
                    same_shape and 0 <= ndiff <= max(8, cX[..., 3].size // 2000))

        # SIGN DISCRIMINATOR: a WRONG forward (+x on a +Y model) must NOT match -- proves the correction
        # actually rotates and that the sign is load-bearing.
        ok &= check("wrong forward (+Y model, forward:+x) does NOT match -- correction is real",
                    hm(outW) != hm(outX))

        # NO-OP: explicit forward:"+x" is byte-identical to the default (no forward applied).
        ok &= check("forward:'+x' is a byte-exact no-op (== default bake)", hm(outD) == hm(outX))

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
