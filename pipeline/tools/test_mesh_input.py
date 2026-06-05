#!/usr/bin/env python3
"""R8 gate: load a REAL on-disk mesh (OBJ) and bake it into an engine package.

Proves the external-mesh path end-to-end: `mesh_io.load_obj` assigns HIT regions by
material/group NAME, and `bake.bake_mesh` renders -> packs -> an engine-accepted CHARACTER
package equivalent to the in-code humanoid. Real art (an OBJ/glTF whose materials are named
head/torso/arms/legs) uses the identical path.

Run: python pipeline/tools/test_mesh_input.py
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

import meshes  # noqa: E402
from mesh_io import load_obj, region_for_name  # noqa: E402
from bake import bake_mesh, bake_character  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402

FIXTURE = PIPELINE_ROOT / "test_meshes" / "humanoid.obj"


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    ok &= check("region_for_name maps head/torso/arms/legs + synonyms (unmatched -> torso)",
                region_for_name("Head_MAT") == 1 and region_for_name("chest") == 2
                and region_for_name("Left_Arm") == 3 and region_for_name("foot_L") == 4
                and region_for_name("mystery") == 2)

    v, _f, r = load_obj(FIXTURE)
    _, _, r0 = meshes.humanoid()
    ok &= check("load_obj assigns the same region multiset as the source mesh",
                sorted(np.bincount(r).tolist()) == sorted(np.bincount(r0).tolist()))
    ok &= check("loaded mesh normalized to the contract (foot z=0, footprint centered on origin)",
                abs(float(v[:, 2].min())) < 1e-6
                and abs(float((v[:, 0].min() + v[:, 0].max()) / 2)) < 1e-6
                and abs(float((v[:, 1].min() + v[:, 1].max()) / 2)) < 1e-6)

    with tempfile.TemporaryDirectory() as td:
        m = bake_mesh(FIXTURE, Path(td) / "obj", 256)
        ok &= check("bake_mesh(OBJ) -> engine-accepted CHARACTER (Gate-1)", not engine_accept(m))
        mask = np.asarray(Image.open(Path(td) / "obj" / "hitmask_atlas.png").convert("L"))
        vals = {int(x) for x in np.unique(mask)}
        ok &= check(f"hitmask discrete + all 4 regions (got {sorted(vals)})",
                    vals <= {0, 1, 2, 3, 4} and {1, 2, 3, 4} <= vals)

        ref = bake_character(Path(td) / "ref", 256)
        ok &= check("OBJ bake metrics == in-code humanoid bake (loader fidelity)",
                    m["world_metrics"]["height_world"] == ref["world_metrics"]["height_world"]
                    and m["world_metrics"]["footprint_radius_world"] == ref["world_metrics"]["footprint_radius_world"])

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
