#!/usr/bin/env python3
"""Gate: the pipeline KNOWS when it is baking useless/garbage content (hardening).

  - flat_region_bound_texture (input): a flat_region delivery that binds a base-colour texture is the
    "flat-via-degenerate-UV-texture" hack -> rejected at the front door.
  - blank_frame (output): a baked direction whose hitmask is entirely background rendered NOTHING -> an
    empty/useless frame is flagged, never silently shipped.

  python pipeline/tools/test_useless_content.py
"""
from __future__ import annotations

import glob
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def main():
    ok = True
    from lint_external_asset import lint
    from build_log import write_build_log

    # --- flat_region_bound_texture: the pirate hack is rejected; a clean flat_region is not ---
    pirate = os.path.join(ROOT, "creative", "incoming", "pirate_duelist_v2", "pirate_duelist_v2.asset.json")
    if os.path.exists(pirate):
        ok &= check("flat_region + bound texture (pirate) -> flat_region_bound_texture",
                    any("flat_region_bound_texture" in x for x in lint(pirate)))
    cow = glob.glob(os.path.join(ROOT, "creative", "incoming", "*cow*", "*.asset.json"))
    if cow:
        ok &= check("clean flat_region (no bound texture) -> NOT flagged",
                    not any("flat_region_bound_texture" in x for x in lint(cow[0])))

    # --- blank_frame: a direction whose hitmask is entirely background ---
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        mask = np.zeros((200, 200), np.uint8)
        mask[0:200, 0:80] = 2                       # dir0 = torso body; dir1 region stays all-zero (blank)
        Image.fromarray(mask, "L").save(out / "hitmask_atlas.png")
        Image.fromarray(np.zeros((200, 200, 4), np.uint8), "RGBA").save(out / "color_atlas.png")
        man = {"variant_id": "b", "animations": {},
               "frames": [{"direction": 0, "rect": [0, 0, 80, 200], "mask_rect": [0, 0, 80, 200]},
                          {"direction": 1, "rect": [80, 0, 80, 200], "mask_rect": [80, 0, 80, 200]}],
               "atlases": {"color": {"path": "color_atlas.png", "size": [200, 200]},
                           "hitmask": {"path": "hitmask_atlas.png", "size": [200, 200]}}}
        log = write_build_log(out, man, "test")
        codes = [w["code"] for w in log["warnings"]]
        ok &= check("blank dir1 -> exactly one blank_frame error, ok=False",
                    codes.count("blank_frame") == 1 and not log["ok"])
        ok &= check("the rendered dir0 is NOT flagged blank", codes.count("blank_frame") == 1)

        # all-rendered package -> no blank_frame
        mask2 = np.full((200, 200), 2, np.uint8)
        Image.fromarray(mask2, "L").save(out / "hitmask_atlas.png")
        log2 = write_build_log(out, man, "test")
        ok &= check("all frames rendered -> no blank_frame",
                    "blank_frame" not in [w["code"] for w in log2["warnings"]])

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
