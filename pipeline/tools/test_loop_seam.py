#!/usr/bin/env python3
"""Gate loop-clip SEAM continuity + root/anchor stability on the committed numpy reference
(reference/humanoid_anim). NON-SKIPPING -- no Blender; runs on a committed golden everywhere.

Two silent failure modes nothing else catches:
  1. A non-seamless LOOP -- frame N-1 -> frame 0 is a visible POP, not a normal step. The bakers
     re-root every frame, which MASKS a bad wrap rather than detecting it.
  2. Anchor / silhouette DRIFT across a clip -- the body sliding off its foot anchor instead of
     animating around a stable ground point.

Method: for every loop clip with >=2 frames, reconstruct each frame in its LOGICAL canvas (paste the
tight atlas crop at its trim offset), then per direction measure:
  - seam:   mean-abs RGBA delta of the wrap pair (last->first) <= SEAM_TOL x the largest in-clip
            step (a seamless cycle has wrap ~= a normal step; measured 0.73-1.00 on humanoid_anim).
  - anchor: every frame's manifest anchor in the clip is identical (root-XY pinned).
  - drift:  the alpha-centroid range across the clip <= CENTROID_TOL_FRAC of the canvas
            (natural swing is a few px; a slide off-root is large).

Run: python pipeline/tools/test_loop_seam.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
REF = PIPELINE_ROOT / "reference" / "humanoid_anim"

SEAM_TOL = 2.0            # wrap delta <= SEAM_TOL * max in-clip step (measured ratio <= 1.0; 2x margin)
STEP_FLOOR = 1.0         # below this mean-delta a clip is effectively static -> use an absolute cap
STATIC_WRAP_CAP = 2.0    # absolute mean-delta cap for a near-static loop
CENTROID_TOL_FRAC = 0.20  # centroid range across a clip <= 20% of the canvas dim (measured ~3% here)


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def _logical_frame(atlas: Image.Image, fr: dict) -> np.ndarray:
    x, y, w, h = fr["rect"]
    bx, by = fr["trim"]
    cw, ch = fr["logical_frame_canvas"]
    canv = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    canv.paste(atlas.crop((x, y, x + w, y + h)), (bx, by))
    return np.asarray(canv).astype(np.int32)


def _centroid(arr: np.ndarray) -> tuple[float, float]:
    a = arr[:, :, 3]
    ys, xs = np.nonzero(a > 0)
    return (float(xs.mean()), float(ys.mean())) if len(xs) else (0.0, 0.0)


def main() -> int:
    ok = True
    m = json.loads((REF / "manifest.json").read_text(encoding="utf-8"))
    atlas = Image.open(REF / "color_atlas.png").convert("RGBA")
    cw, ch = m["frames"][0]["logical_frame_canvas"]
    dc = m["direction_count"]
    tested = 0
    for state, spec in sorted(m["animations"].items()):
        if spec.get("playback") != "loop" or spec.get("frames", 0) < 2:
            continue
        tested += 1
        seam_fail, anchor_fail, drift_fail = [], [], []
        worst_ratio = worst_xr = worst_yr = 0.0
        for d in range(dc):
            frs = sorted((f for f in m["frames"] if f["state"] == state and f["direction"] == d),
                         key=lambda f: f["frame_index"])
            if len(frs) < 2:
                continue
            imgs = [_logical_frame(atlas, f) for f in frs]
            n = len(imgs)
            steps = [float(np.abs(imgs[i] - imgs[i + 1]).mean()) for i in range(n - 1)]
            wrap = float(np.abs(imgs[n - 1] - imgs[0]).mean())
            mx = max(steps)
            if mx < STEP_FLOOR:
                if wrap > STATIC_WRAP_CAP:
                    seam_fail.append((d, round(wrap, 2)))
            else:
                ratio = wrap / mx
                worst_ratio = max(worst_ratio, ratio)
                if ratio > SEAM_TOL:
                    seam_fail.append((d, round(wrap, 1), round(mx, 1)))
            if len({tuple(f["anchor"]) for f in frs}) != 1:
                anchor_fail.append(d)
            cents = [_centroid(im) for im in imgs]
            xr = max(c[0] for c in cents) - min(c[0] for c in cents)
            yr = max(c[1] for c in cents) - min(c[1] for c in cents)
            worst_xr, worst_yr = max(worst_xr, xr), max(worst_yr, yr)
            if xr > CENTROID_TOL_FRAC * cw or yr > CENTROID_TOL_FRAC * ch:
                drift_fail.append((d, round(xr, 1), round(yr, 1)))
        ok &= check(f"{state}: loop seam smooth on all {dc} dirs "
                    f"(worst wrap/step {worst_ratio:.2f} <= {SEAM_TOL})", not seam_fail)
        if seam_fail:
            print(f"   seam pops at: {seam_fail}")
        ok &= check(f"{state}: anchor constant across clip on all {dc} dirs", not anchor_fail)
        if anchor_fail:
            print(f"   anchor-drift dirs: {anchor_fail}")
        ok &= check(f"{state}: centroid stays on root all {dc} dirs "
                    f"(worst range x {worst_xr:.1f} y {worst_yr:.1f} <= {CENTROID_TOL_FRAC * ch:.0f} px)",
                    not drift_fail)
        if drift_fail:
            print(f"   drift at: {drift_fail}")
    ok &= check(f"exercised at least one multi-frame loop clip (got {tested})", tested > 0)
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
