#!/usr/bin/env python3
"""Test: bake.py renders procedural meshes into engine-accepted packages (R2 + R4).

Bakes to a temp dir (no committed output) and asserts:
  - probe meshes (cube/pole) -> Gate-1 (engine acceptance) passes (R2);
  - the body-only humanoid CHARACTER -> Gate-1 passes (variant_class=character with
    measured world_metrics), its R8 HIT-proxy hitmask is DISCRETE and within the body
    palette {0..4} with all four regions present, and metrics are valid (R4).

Run: python pipeline/tools/test_bake.py   (exit 0 = all pass)
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

from bake import bake, bake_character  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        # R2: probe meshes are engine-accepted.
        for mesh in ("cube", "pole"):
            manifest = bake(mesh, Path(td) / f"{mesh}_probe", canvas_px=256)
            ok &= check(f"bake probe '{mesh}' -> engine-accepted package", not engine_accept(manifest))

        # R4: body-only humanoid character (color + R8 HIT hitmask + metrics).
        out = Path(td) / "humanoid_ref"
        manifest = bake_character(out, canvas_px=256)
        errors = engine_accept(manifest)
        ok &= check("bake character humanoid -> engine-accepted (character + valid metrics)", not errors)
        for e in errors:
            print("   ", e)

        mask = np.asarray(Image.open(out / "hitmask_atlas.png").convert("L"))
        vals = {int(v) for v in np.unique(mask)}
        ok &= check(f"hitmask discrete & within body palette {{0..4}} (got {sorted(vals)})", vals <= {0, 1, 2, 3, 4})
        ok &= check("all 4 body regions present (head/torso/arms/legs)", {1, 2, 3, 4} <= vals)

        m = manifest["world_metrics"]
        eye = m.get("eye_height_world", 0.0)
        ok &= check(
            f"metrics valid (h={m['height_world']}, foot={m['footprint_radius_world']}, eye={eye}<=h)",
            m["height_world"] > 0 and m["footprint_radius_world"] > 0 and 0 < eye <= m["height_world"],
        )

        # R4 review: footprint must be the standing (ground) footprint, not the arm span.
        from meshes import humanoid as _humanoid
        verts = _humanoid()[0]
        full_xy = float(np.max(np.abs(verts[:, :2])))
        ok &= check(
            f"footprint is the ground footprint, not the arm span (foot={m['footprint_radius_world']} < full_xy {full_xy:.3f})",
            m["footprint_radius_world"] < full_xy - 0.02,
        )

        # R4 review: color alpha>0 iff hitmask region>0, per frame rect (alignment invariant).
        color = np.asarray(Image.open(out / "color_atlas.png").convert("RGBA"))
        aligned = all(
            np.array_equal(color[y:y + h, x:x + w, 3] > 0, mask[y:y + h, x:x + w] > 0)
            for (x, y, w, h) in (f["rect"] for f in manifest["frames"])
        )
        ok &= check("color alpha>0 iff hitmask region>0 (per frame rect)", aligned)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
