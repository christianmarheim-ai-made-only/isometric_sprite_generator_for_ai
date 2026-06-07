#!/usr/bin/env python3
"""Gate the AUTO-RIG path: an UNRIGGED part-mesh delivery (a rig profile but NO armature in the glb)
baked through bake_asset rigs ITSELF (rig_from_profile) instead of hard-failing "no armature found".

Reuses the cow delivery's RAW (unrigged) glb + its rig profile / materials / source_asset / anim, copied
into a temp package, with a single 1-frame state to keep the bake fast (16 frames). Asserts the auto-rig
fired, the package is Gate-1 OK, the provenance records it, and the DECLARED regions survived (all four
body regions in the hitmask). Skips if Blender is absent. Mirror of test_rigged_anim for the unrigged case.

Run: python pipeline/tools/test_auto_rig.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
REPO = PIPELINE_ROOT.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake_asset import bake_asset, _glb_has_armature  # noqa: E402
from blender_bake import find_blender  # noqa: E402

COW = REPO / "creative" / "incoming" / "cow_brown_farm_v1"
SIDECARS = ["cow_brown_farm_v1.glb", "cow_brown_farm_v1_materials.json",
            "cow_brown_farm_v1.source_asset.json", "cow_brown_farm_v1_anim.json"]


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    if not find_blender():
        print("SKIP: Blender not found; auto-rig path not run on this machine.")
        return 0
    if not (COW / "cow_brown_farm_v1.glb").exists():
        print("SKIP: cow raw delivery fixture missing")
        return 0

    ok = True
    ok &= check("sanity: the DELIVERED cow glb is unrigged (no armature/skin)",
                not _glb_has_armature(COW / "cow_brown_farm_v1.glb"))

    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "cow_brown_farm_v1"
        pkg.mkdir(parents=True)
        for fn in SIDECARS:                                  # copy the raw delivery + auto-rig sidecars
            shutil.copy(COW / fn, pkg / fn)
        # a minimal asset.json pointing at the RAW (unrigged) glb, up=z, ONE 1-frame state -> 16 frames
        asset = {
            "asset_contract_version": "external_asset_v2",
            "variant_id": "cow_brown_farm_v1",
            "archetype": "quadruped",
            "texture_mode": "flat_region",
            "files": {"mesh": "cow_brown_farm_v1.glb", "animation_clips": "cow_brown_farm_v1_anim.json"},
            "geometry": {"up": "z", "forward": "+x", "unit": "meter"},
            "rig": "quadruped_v1",
            "region_source": "material_name",
            "default_state": "idle",
            "animations": {"idle": {"clip": "idle", "frames": 1, "fps": 6, "playback": "loop"}},
        }
        ap = pkg / "cow_brown_farm_v1.asset.json"
        ap.write_text(json.dumps(asset, indent=2), encoding="utf-8")

        out = Path(td) / "out"
        m = bake_asset(ap, out)                              # <-- full entry: lint -> AUTO-RIG -> bake -> Gate-1

        rigged = out / "cow_brown_farm_v1_rigged.glb"
        ok &= check("auto-rig produced a rigged glb (now WITH an armature)",
                    rigged.exists() and _glb_has_armature(rigged))
        ok &= check("baked a valid package (16 frames = 1 state x 16 dirs)", len(m.get("frames", [])) == 16)

        log = json.loads((out / "build_log.json").read_text(encoding="utf-8"))
        codes = {w["code"] for w in log["warnings"]}
        ok &= check("build_log records the auto_rigged provenance note", "auto_rigged" in codes)
        ok &= check("package is Gate-1 OK (auto_rigged is info-severity, does not fail ok)", log["ok"])

        prov = json.loads((out / "manifest.json").read_text(encoding="utf-8")).get("provenance", {})
        ok &= check("provenance.mesh hashes the derived rigged glb (not None)", bool(prov.get("mesh")))

        mask = np.asarray(Image.open(out / "hitmask_atlas.png").convert("L"))
        vals = {int(v) for v in np.unique(mask)}
        ok &= check(f"DECLARED regions survived auto-rig: all 4 body regions present (got {sorted(vals)})",
                    {1, 2, 3, 4} <= vals)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
