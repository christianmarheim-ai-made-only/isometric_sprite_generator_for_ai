#!/usr/bin/env python3
"""Gate: calib_color verifies the calibration TEXTURE colour matches each region HITBOX (calib_v1).

A region painted its expected calibration colour at the hitbox centre PASSES; painting it the wrong colour
(e.g. the head blue instead of red) is caught as a mismatch. Pure numpy/PIL, no Blender.

  python pipeline/tools/test_calib_color.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from calib_spec import CALIBRATION_COLORS   # noqa: E402
import calib_color                          # noqa: E402


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def _scene(tmp, head_rgb):
    """A 256x256 single-frame atlas: a head box (painted head_rgb) + an arm_left box (green), transparent
    elsewhere. region_rects place the hitbox centres on those boxes."""
    a = np.zeros((256, 256, 4), np.uint8)
    a[20:60, 40:80] = (*head_rgb, 255)                       # head box (centre ~ (60,40))
    a[20:60, 150:190] = (*CALIBRATION_COLORS["arm_left"], 255)  # left arm = green (centre ~ (170,40))
    Image.fromarray(a, "RGBA").save(os.path.join(tmp, "color_atlas.png"))
    manifest = {"atlases": {"color": {"path": "color_atlas.png", "size": [256, 256]}},
                "frames": [{"direction": 0, "rect": [0, 0, 256, 256]}]}
    meta = {"region_rects": {"0": [{"name": "head", "region_id": 1, "rect": [40, 20, 40, 40]},
                                   {"name": "wing_left", "region_id": 3, "rect": [150, 20, 40, 40]}]}}
    return manifest, meta


def main():
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        # correct: head painted RED, left wing GREEN
        man, meta = _scene(tmp, CALIBRATION_COLORS["head"])
        rep = calib_color.verify(tmp, man, meta)
        ok &= check("correct calibration colours -> ok=True, no mismatches", rep["ok"] and not rep["mismatches"])
        ok &= check("head verified as red", rep["regions"].get("head", {}).get("ok") is True)
        ok &= check("wing_left (green) folded to arm_left + verified",
                    rep["regions"].get("wing_left", {}).get("expected") == "arm_left"
                    and rep["regions"]["wing_left"]["ok"] is True)

        # wrong: head painted BLUE (the right-arm colour) -> mismatch
        man2, meta2 = _scene(tmp, CALIBRATION_COLORS["arm_right"])
        rep2 = calib_color.verify(tmp, man2, meta2)
        ok &= check("head painted blue (wrong) -> mismatch, ok=False",
                    (not rep2["ok"]) and "head" in rep2["mismatches"]
                    and rep2["regions"]["head"]["dominant"] == "arm_right")

    # nearest-colour sanity
    ok &= check("nearest_calib_color: pure red -> head", calib_color.nearest_calib_color((216, 38, 38))[0] == "head")
    ok &= check("nearest_calib_color: pure orange -> tail", calib_color.nearest_calib_color((240, 138, 30))[0] == "tail")

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
