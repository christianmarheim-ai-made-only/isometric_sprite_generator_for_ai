"""Calibration colour-oracle (ADR-0030/0031): prove SKINNING + ANIMATION are VERIFIED-APPLIED.

From a baked calibration package it reads the PACKED hitmask atlas (hitmask_atlas.png, mode 'L',
clean region ids 0=bg,1=head,2=torso,3=arms,4=legs), crops each frame's region pixels by that
frame's manifest `mask_rect`, and tracks every region's centroid + tight AABB across the clip.

Three checks per non-static multi-frame clip:

  (1) DEFORM-LIVE / dead-clip: some region centroid must DISPLACE across frames beyond a small pixel
      threshold. If nothing moves, the skin/anim never took -- the rest pose was rendered N times.
  (2) INTENDED-REGION-MOVE: the clip's intent region must be (near) the top mover --
      walk/run/roll -> legs(4); attack/bite/swing -> arms(3); fly -> arms(3, wings).
      Catches a mis-skin where the WRONG limb animates.
  (3) PER-REGION AABB TRACKING: the moving (intent) region's AABB must itself shift across the clip
      (its box origin/size travels with the limb), not merely its centroid.

IMPORTANT: it reads ids from the PACKED hitmask_atlas.png (clean 0..4). It does NOT read the per-frame
region_<state>_f<fi>_dir<dd>.png files -- those are RGBA REGION_RGB-coloured, not id-valued.

Motion is AVERAGED over all baked directions: a single facing can foreshorten a limb's travel to near
zero, so a per-direction read is noisy; the cross-direction mean is the stable signal.

Standalone (numpy + PIL). Run:  python pipeline/tools/calib_oracle.py pipeline/output/<variant>
"""
from __future__ import annotations
import json
import os
import sys
from collections import defaultdict

try:
    import numpy as np
    from PIL import Image
except Exception:  # pragma: no cover
    np = None
    Image = None

REGION_NAMES = {1: "head", 2: "torso", 3: "arms", 4: "legs"}
# region id that should move MOST for a clip's intent (canonical + a few synonyms the rigs ship)
CLIP_INTENT = {"walk": 4, "run": 4, "roll": 4, "graze": 4, "sprint": 4, "jump": 4,
               "fly": 3, "attack": 3, "bite": 3, "swing": 3, "breath": 3, "punch": 3, "cast": 3}
STATIC = {"idle", "calibration_pose", "rest", "rest_pose"}   # expected to move little
DEAD_CLIP_PX = 2.0            # below this max region motion = dead clip (rest pose baked N times)
INTENT_FRACTION = 0.5        # intent region must move >= this * the top mover to count as "near top"
AABB_SHIFT_PX = 1.0          # intent-region AABB must travel at least this far across the clip


def _index_frames(manifest):
    """Index manifest frames by (state, direction, frame_index)."""
    return {(f["state"], int(f["direction"]), int(f["frame_index"])): f
            for f in manifest.get("frames", [])}


def _region_stats(atlas, mask_rect):
    """Per-region centroid (cx,cy) and tight AABB (x0,y0,x1,y1) in frame-local px from the PACKED atlas
    cropped by mask_rect=[x,y,w,h]. Returns {region_id: {"c": (cx,cy), "aabb": (x0,y0,x1,y1)}}."""
    x, y, w, h = (int(v) for v in mask_rect)
    crop = atlas[y:y + h, x:x + w]
    out = {}
    for r in (1, 2, 3, 4):
        ys, xs = np.where(crop == r)
        if xs.size:
            out[r] = {
                "c": (float(xs.mean()), float(ys.mean())),
                "aabb": (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())),
            }
    return out


def _max_pairwise(points):
    """Max pairwise Euclidean distance among a list of (x,y) points (0.0 if <2)."""
    if len(points) < 2:
        return 0.0
    return max(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
               for i, a in enumerate(points) for b in points[i + 1:])


def clip_region_motion(atlas, frame_index, state):
    """Compute per-region motion for one clip, averaged over all baked directions.

    Returns (motion, aabb_travel, ndirs, nframes) where:
      motion[r]      = mean over directions of max centroid displacement (px) for region r
      aabb_travel[r] = mean over directions of max AABB-origin displacement (px) for region r
    """
    dirs = sorted({d for (st, d, fi) in frame_index if st == state})
    cent_disp = defaultdict(list)
    aabb_disp = defaultdict(list)
    nframes = 0
    for dd in dirs:
        fis = sorted({fi for (st, d, fi) in frame_index if st == state and d == dd})
        nframes = max(nframes, len(fis))
        per_c = defaultdict(list)   # region -> [centroid per frame]
        per_a = defaultdict(list)   # region -> [(x0,y0) aabb origin per frame]
        for fi in fis:
            f = frame_index.get((state, dd, fi))
            if f is None:
                continue
            stats = _region_stats(atlas, f["mask_rect"])
            for r, s in stats.items():
                per_c[r].append(s["c"])
                per_a[r].append((s["aabb"][0], s["aabb"][1]))
        for r, pts in per_c.items():
            cent_disp[r].append(_max_pairwise(pts))
        for r, pts in per_a.items():
            aabb_disp[r].append(_max_pairwise(pts))
    motion = {r: sum(v) / len(v) for r, v in cent_disp.items() if v}
    aabb_travel = {r: sum(v) / len(v) for r, v in aabb_disp.items() if v}
    return motion, aabb_travel, len(dirs), nframes


def oracle_from_manifest(out_dir, manifest, atlas):
    """Core: run the oracle given an already-loaded manifest dict and atlas ndarray."""
    frame_index = _index_frames(manifest)
    states = sorted({st for (st, d, fi) in frame_index})
    rep = {"oracle_version": "calib_oracle_v2", "out_dir": str(out_dir),
           "ok": True, "states": {}, "failures": []}
    for st in states:
        motion, aabb_travel, ndirs, nframes = clip_region_motion(atlas, frame_index, st)
        if not motion:
            continue
        mover = max(motion, key=motion.get)
        top = motion[mover]
        intent = CLIP_INTENT.get(st)
        entry = {
            "nframes": nframes,
            "ndirs": ndirs,
            "static_expected": st in STATIC,
            "region_motion_px": {REGION_NAMES.get(r, r): round(m, 2) for r, m in sorted(motion.items())},
            "region_aabb_travel_px": {REGION_NAMES.get(r, r): round(m, 2) for r, m in sorted(aabb_travel.items())},
            "top_mover": REGION_NAMES.get(mover, mover),
            "intent_region": REGION_NAMES.get(intent) if intent else None,
        }
        rep["states"][st] = entry
        if nframes <= 1 or st in STATIC:
            continue
        # (1) DEFORM-LIVE / dead clip
        if top < DEAD_CLIP_PX:
            rep["ok"] = False
            msg = f"{st}: DEAD CLIP -- no region moved (max {top:.2f}px < {DEAD_CLIP_PX:.1f}px); rest pose baked {nframes}x"
            rep["failures"].append(msg)
            entry["verdict"] = "dead_clip"
            continue
        # (2) INTENDED-REGION-MOVE
        if intent is not None:
            intent_motion = motion.get(intent, 0.0)
            if intent_motion < INTENT_FRACTION * top:
                rep["ok"] = False
                rep["failures"].append(
                    f"{st}: WRONG REGION MOVED -- intent '{REGION_NAMES[intent]}' moved {intent_motion:.2f}px "
                    f"(< {INTENT_FRACTION:.2f} x top); top mover is '{REGION_NAMES.get(mover)}' ({top:.2f}px)")
                entry["verdict"] = "wrong_region"
                continue
            # (3) PER-REGION AABB TRACKING for the intent region
            if aabb_travel.get(intent, 0.0) < AABB_SHIFT_PX:
                rep["ok"] = False
                rep["failures"].append(
                    f"{st}: AABB STATIC -- intent '{REGION_NAMES[intent]}' centroid moved but its AABB did not "
                    f"({aabb_travel.get(intent, 0.0):.2f}px < {AABB_SHIFT_PX:.1f}px)")
                entry["verdict"] = "aabb_static"
                continue
        entry["verdict"] = "ok"
    return rep


def oracle(out_dir):
    """Load manifest + packed hitmask atlas from out_dir and run the oracle. Standalone entry point."""
    out_dir = str(out_dir)
    manifest = json.loads(open(os.path.join(out_dir, "manifest.json"), encoding="utf-8").read())
    atlas_path = os.path.join(out_dir, "hitmask_atlas.png")
    img = Image.open(atlas_path)
    if img.mode != "L":
        img = img.convert("L")
    atlas = np.asarray(img)
    return oracle_from_manifest(out_dir, manifest, atlas)


def main():
    if len(sys.argv) < 2:
        print("usage: python calib_oracle.py <baked_output_dir>")
        return 2
    rep = oracle(sys.argv[1])
    print(json.dumps(rep, indent=2))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
