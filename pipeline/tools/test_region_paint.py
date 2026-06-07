#!/usr/bin/env python3
"""Gate: region_paint.relabel_region_ids recovers a multi-region mask from projected AABBs.

The core claim of the explicit-hitbox baking path: a single-material (all-torso) silhouette + the
projected per-region screen boxes yields a hit-mask with >1 region id, WITHOUT growing the silhouette
or painting the background. Pure numpy, fast.

  python pipeline/tools/test_region_paint.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from region_paint import relabel_region_ids  # noqa: E402


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def main():
    ok = True

    # all-torso silhouette (id 2) with a 2-row background strip on top
    ids = np.full((20, 20), 2, np.uint8)
    ids[0:2, :] = 0
    rects = [{"region_id": 1, "rect": [0, 2, 20, 6]},     # head band  rows 2..7
             {"region_id": 4, "rect": [0, 14, 20, 6]}]     # legs band  rows 14..19
    out = relabel_region_ids(ids, rects)
    ok &= check("single-material -> >1 region id", len(set(np.unique(out)) - {0}) > 1)
    ok &= check("head band relabelled to 1", bool((out[2:8, :] == 1).all()))
    ok &= check("legs band relabelled to 4", bool((out[14:20, :] == 4).all()))
    ok &= check("untouched middle stays torso (2)", bool((out[8:14, :] == 2).all()))
    ok &= check("background strip preserved (not painted)", bool((out[0:2, :] == 0).all()))
    ok &= check("silhouette not grown (same non-bg footprint)",
                bool(((out != 0) == (ids != 0)).all()))

    # smallest-area box wins on overlap (specific part beats body)
    ids2 = np.full((10, 10), 2, np.uint8)
    out2 = relabel_region_ids(ids2, [{"region_id": 3, "rect": [0, 0, 10, 10]},     # big "arms"
                                     {"region_id": 1, "rect": [3, 3, 2, 2]}])        # small "head"
    ok &= check("smallest box wins inside overlap", out2[4, 4] == 1)
    ok &= check("larger box elsewhere", out2[0, 0] == 3)

    # all-background never gets painted
    bg = np.zeros((5, 5), np.uint8)
    ok &= check("all-background untouched", bool((relabel_region_ids(bg, [{"region_id": 1, "rect": [0, 0, 5, 5]}]) == 0).all()))

    # a box fully outside the array is a no-op (clamped)
    ok &= check("out-of-bounds box clamped (no crash, no change)",
                bool((relabel_region_ids(ids2, [{"region_id": 1, "rect": [50, 50, 5, 5]}]) == 2).all()))

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
