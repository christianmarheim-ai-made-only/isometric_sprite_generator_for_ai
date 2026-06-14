#!/usr/bin/env python3
"""regions_from_color: the `region_texture` source -- classify a calib-coloured render -> R8 region ids.

Proves the painted calibration colour IS the segmentation: head red->1, torso grey->2, left arm green +
right arm blue -> arms=3, legs purple->4, weapon cyan/magenta->6 (when present); transparent -> 0; and
that the classifier reads the SAME calib_spec.CALIBRATION_COLORS the colour oracle does (cannot drift).

  python pipeline/tools/test_regions_from_color.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import regions_from_color as rfc           # noqa: E402
from calib_spec import CALIBRATION_COLORS  # noqa: E402


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def _swatch(key, h=4, w=4):
    a = np.zeros((h, w, 4), np.uint8)
    a[..., :3] = CALIBRATION_COLORS[key]
    a[..., 3] = 255
    return a


def main():
    ok = True
    fold = {"head": 1, "torso": 2, "arm_left": 3, "arm_right": 3, "legs": 4}
    for key, rid in fold.items():
        ok &= check(f"{key} {tuple(CALIBRATION_COLORS[key])} -> R8 id {rid}",
                    int(rfc.classify_regions(_swatch(key))[0, 0]) == rid)

    ok &= check("transparent background -> id 0",
                int(rfc.classify_regions(np.zeros((4, 4, 4), np.uint8)).max()) == 0)

    # a 5-band figure classifies to the right ids, left-to-right
    keys = ["head", "torso", "arm_left", "arm_right", "legs"]
    img = np.zeros((6, 50, 4), np.uint8)
    for i, k in enumerate(keys):
        img[:, i * 10:(i + 1) * 10, :3] = CALIBRATION_COLORS[k]
        img[:, i * 10:(i + 1) * 10, 3] = 255
    ids = rfc.classify_regions(img)
    ok &= check("5-band figure -> [1,2,3,3,4] across the bands",
                [int(ids[3, i * 10 + 5]) for i in range(5)] == [1, 2, 3, 3, 4])

    # the classifier reads the LIVE calib table -> cannot drift from the colour oracle
    ok &= check("palette keys == calib_spec.CALIBRATION_COLORS", set(rfc._KEYS) == set(CALIBRATION_COLORS))

    # weapon colours fold to weapon=6 (only checked once the calib_halberd extension adds them)
    for wk in ("weapon_shaft", "weapon_head"):
        if wk in CALIBRATION_COLORS:
            ok &= check(f"{wk} -> weapon id 6", int(rfc.classify_regions(_swatch(wk))[0, 0]) == 6)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
