#!/usr/bin/env python3
"""Gate: the texture-only SKIN DELTA process + guard (no Blender).

A skin delta clones a base model's geometry/UV/rig and swaps only the base-colour texture. The guard
must (a) prove the variant is geometry+UV identical to the base, and (b) reject anything that is not a
clean texture-only change. Uses committed glbs as fixtures.

  python pipeline/tools/test_skin_delta.py
"""
from __future__ import annotations
import os
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

import error_codes as ec
import skin_delta as sd

FX = os.path.join(ROOT, "pipeline", "examples", "texture_starter", "humanoid_textured.glb")  # base (texture-capable)
DIFF = os.path.join(ROOT, "pipeline", "test_meshes", "grunt.glb")                             # different geometry
OGRE = os.path.join(ROOT, "creative", "incoming", "green_ogre_v1", "green_ogre_v1.glb")        # geometry-only (no UV)


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def main():
    ok = True

    ok &= check("error_codes: all skin_delta_* registered",
                all(ec.is_known(c) for c in ("skin_delta_base_missing", "skin_delta_geometry_changed",
                    "skin_delta_texture_invalid", "skin_delta_base_not_capable", "skin_delta_self_reference",
                    "skin_delta_texture_missing", "skin_delta_real_albedo_conflict")))

    if os.path.exists(FX):
        ok &= check("geometry_identical: a glb vs itself -> True", sd.geometry_identical(FX, FX))
    if os.path.exists(FX) and os.path.exists(DIFF):
        ok &= check("geometry_identical: different glbs -> False", not sd.geometry_identical(FX, DIFF))

    try:
        from PIL import Image
        d = tempfile.mkdtemp()
        Image.new("RGBA", (512, 512), (40, 120, 60, 255)).save(os.path.join(d, "skin.png"))
        Image.new("RGBA", (500, 512), (0, 0, 0, 255)).save(os.path.join(d, "bad.png"))      # non-power-of-two
        base_dir = os.path.dirname(FX)

        def mk(**kw):
            base = {"variant_id": "humanoid_green_skin", "base_asset_id": "humanoid_textured",
                    "base_glb": "humanoid_textured.glb", "base_color": "skin.png", "real_albedo": True}
            base.update(kw)
            return base

        ok &= check("validate: valid texture-only delta -> OK", sd.validate_delta(mk(), base_dir, d) == [])
        ok &= check("validate: self-reference -> skin_delta_self_reference",
                    any("self_reference" in x for x in sd.validate_delta(mk(variant_id="humanoid_textured"), base_dir, d)))
        ok &= check("validate: missing texture -> skin_delta_texture_missing",
                    any("texture_missing" in x for x in sd.validate_delta(mk(base_color="nope.png"), base_dir, d)))
        ok &= check("validate: non-power-of-two texture -> skin_delta_texture_invalid",
                    any("texture_invalid" in x for x in sd.validate_delta(mk(base_color="bad.png"), base_dir, d)))
        ok &= check("validate: real_albedo + calibration -> skin_delta_real_albedo_conflict",
                    any("real_albedo_conflict" in x for x in sd.validate_delta(mk(real_albedo=True, calibration=True), base_dir, d)))
        ok &= check("validate: missing base glb -> skin_delta_base_missing",
                    any("base_missing" in x for x in sd.validate_delta(mk(base_glb="missing.glb"), base_dir, d)))
        if os.path.exists(OGRE):
            e = sd.validate_delta(mk(base_asset_id="green_ogre_v1", base_glb=os.path.basename(OGRE)),
                                  os.path.dirname(OGRE), d)
            ok &= check("validate: UV-less base -> skin_delta_base_not_capable", any("base_not_capable" in x for x in e))
        if os.path.exists(DIFF):
            ok &= check("validate: shipped variant != base geometry -> skin_delta_geometry_changed",
                        any("geometry_changed" in x for x in sd.validate_delta(mk(), base_dir, d, variant_glb=DIFF)))
    except ImportError:
        print("SKIP: PIL not available -> validate_delta texture cases not exercised")

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
