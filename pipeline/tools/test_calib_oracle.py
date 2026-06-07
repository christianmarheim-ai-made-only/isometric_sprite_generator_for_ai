"""Synthetic unit tests for calib_oracle (no Blender, no live bake).

We forge tiny in-memory hitmask atlases + manifests so the oracle LOGIC is exercised deterministically:
  (a) legs translate frame-to-frame      -> intent 'walk' PASSES (deform-live + intent + AABB).
  (b) nothing moves (rest pose baked Nx) -> DEAD CLIP fires.
  (c) the WRONG region (arms) moves for a walk -> WRONG REGION MOVED fires.
  (d) legs centroid moves but AABB is pinned -> AABB STATIC fires.
  (e) static clips (idle, single-frame calibration_pose) never fail.

Run: python pipeline/tools/test_calib_oracle.py   (exit 0 = pass)
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calib_oracle as co  # noqa: E402

PASS = True


def check(cond, label):
    global PASS
    print(("PASS" if cond else "FAIL") + " - " + label)
    if not cond:
        PASS = False


# --- synthetic-atlas builder -------------------------------------------------
# We pack every frame of a synthetic clip into ONE atlas, side by side, and give each frame a
# mask_rect into it. A frame is described by per-region rectangles {region_id: (x0,y0,w,h)} in
# frame-local coordinates; the builder paints them at the right atlas offset.

REGION = {"head": 1, "torso": 2, "arms": 3, "legs": 4}


def build(clip_frames, state, ndirs=2, tile=64):
    """clip_frames: list of dicts {region_name: (x0,y0,w,h)} (frame-local). Returns (atlas, manifest).

    The same clip is replicated across `ndirs` directions (oracle averages over directions)."""
    nframes = len(clip_frames)
    cols = nframes
    rows = ndirs
    atlas = np.zeros((rows * tile, cols * tile), dtype=np.uint8)
    frames = []
    for dd in range(ndirs):
        for fi, regs in enumerate(clip_frames):
            ox, oy = fi * tile, dd * tile
            for name, (x0, y0, w, h) in regs.items():
                rid = REGION[name]
                atlas[oy + y0:oy + y0 + h, ox + x0:ox + x0 + w] = rid
            frames.append({"state": state, "direction": dd, "frame_index": fi,
                           "mask_rect": [ox, oy, tile, tile]})
    return atlas, {"frames": frames}


def run(clip_frames, state, ndirs=2):
    atlas, manifest = build(clip_frames, state, ndirs=ndirs)
    return co.oracle_from_manifest("<synthetic>", manifest, atlas)


# A stable body layout; the moving region is shifted per frame by the caller.
def body(legs_y=40, arms_x=8, head_y=2):
    return {
        "head":  (24, head_y, 16, 10),
        "torso": (22, 14, 20, 22),
        "arms":  (arms_x, 18, 8, 16),
        "legs":  (24, legs_y, 16, 18),
    }


# --- (a) legs translate -> walk PASSES --------------------------------------
def test_walk_legs_pass():
    # legs slide down a few px each frame; arms/head/torso fixed.
    frames = [body(legs_y=30), body(legs_y=34), body(legs_y=38), body(legs_y=42)]
    rep = run(frames, "walk")
    st = rep["states"]["walk"]
    check(rep["ok"], "(a) walk with moving legs -> oracle ok")
    check(st.get("verdict") == "ok", "(a) walk verdict == ok")
    check(st["top_mover"] == "legs", "(a) legs is the top mover")
    check(st["region_motion_px"]["legs"] >= co.DEAD_CLIP_PX, "(a) legs motion above dead-clip floor")
    check(not rep["failures"], "(a) no failures reported")


# --- (b) nothing moves -> DEAD CLIP -----------------------------------------
def test_dead_clip():
    same = body(legs_y=40)
    frames = [dict(same), dict(same), dict(same), dict(same)]
    rep = run(frames, "walk")
    check(not rep["ok"], "(b) frozen walk -> oracle NOT ok")
    check(rep["states"]["walk"].get("verdict") == "dead_clip", "(b) verdict == dead_clip")
    check(any("DEAD CLIP" in f for f in rep["failures"]), "(b) DEAD CLIP failure present")


# --- (c) wrong region moves -> WRONG REGION MOVED ---------------------------
def test_wrong_region():
    # walk, but only ARMS translate; legs/head/torso fixed -> intent 'legs' barely moves.
    frames = [body(arms_x=4), body(arms_x=12), body(arms_x=20), body(arms_x=28)]
    rep = run(frames, "walk")
    st = rep["states"]["walk"]
    check(not rep["ok"], "(c) walk where only arms move -> oracle NOT ok")
    check(st.get("verdict") == "wrong_region", "(c) verdict == wrong_region")
    check(st["top_mover"] == "arms", "(c) arms is the (wrong) top mover")
    check(any("WRONG REGION" in f for f in rep["failures"]), "(c) WRONG REGION failure present")


# --- (d) centroid moves but AABB pinned -> AABB STATIC -----------------------
def test_aabb_static():
    # Forge legs whose CENTROID drifts (we toggle a few pixels inside a FIXED bounding box) while the
    # tight AABB stays pinned. We hand-build atlases for this one because `body()` translates the box.
    tile = 64
    ndirs = 2
    nframes = 4
    atlas = np.zeros((ndirs * tile, nframes * tile), dtype=np.uint8)
    frames = []
    for dd in range(ndirs):
        for fi in range(nframes):
            ox, oy = fi * tile, dd * tile
            # fixed body
            atlas[oy + 2:oy + 12, ox + 24:ox + 40] = 1        # head
            atlas[oy + 14:oy + 36, ox + 22:ox + 42] = 2       # torso
            atlas[oy + 18:oy + 34, ox + 8:ox + 16] = 3        # arms
            # legs: keep the EXTREME corners pinned (fixes AABB) but shift interior mass.
            atlas[oy + 40, ox + 24] = 4                        # pinned top-left corner
            atlas[oy + 57, ox + 39] = 4                        # pinned bottom-right corner
            # interior blob slides right with frame -> centroid drifts, AABB unchanged.
            bx = 26 + fi * 3
            atlas[oy + 46:oy + 52, ox + bx:ox + bx + 4] = 4
            frames.append({"state": "walk", "direction": dd, "frame_index": fi,
                           "mask_rect": [ox, oy, tile, tile]})
    rep = co.oracle_from_manifest("<synthetic>", {"frames": frames}, atlas)
    st = rep["states"]["walk"]
    # Sanity: centroid moved enough to clear the dead-clip floor and stay top region.
    check(st["region_motion_px"]["legs"] >= co.DEAD_CLIP_PX, "(d) legs centroid moved (above dead floor)")
    check(st["region_aabb_travel_px"]["legs"] < co.AABB_SHIFT_PX, "(d) legs AABB did NOT travel")
    check(not rep["ok"], "(d) pinned-AABB walk -> oracle NOT ok")
    check(st.get("verdict") == "aabb_static", "(d) verdict == aabb_static")
    check(any("AABB STATIC" in f for f in rep["failures"]), "(d) AABB STATIC failure present")


# --- (e) static clips never fail --------------------------------------------
def test_static_never_fails():
    # idle: tiny jitter, multi-frame, but STATIC -> skipped (no failure).
    frames = [body(legs_y=40), body(legs_y=40), body(legs_y=41)]
    rep_idle = run(frames, "idle")
    check(rep_idle["ok"], "(e) idle (static) never fails even if nearly frozen")
    check("verdict" not in rep_idle["states"]["idle"], "(e) idle is not adjudicated")
    # single-frame calibration_pose -> skipped on nframes<=1.
    single, manifest = build([body(legs_y=40)], "calibration_pose", ndirs=2)
    rep_cal = co.oracle_from_manifest("<synthetic>", manifest, single)
    check(rep_cal["ok"], "(e) single-frame calibration_pose never fails")


# --- (f) intent at top is fine even when other regions also move -------------
def test_intent_near_top_passes():
    # attack: arms move MOST, legs also drift a little (whole-body), arms is intent -> PASS.
    frames = [
        {"head": (24, 2, 16, 10), "torso": (22, 14, 20, 22), "arms": (4, 18, 8, 16), "legs": (24, 40, 16, 18)},
        {"head": (24, 2, 16, 10), "torso": (22, 14, 20, 22), "arms": (16, 18, 8, 16), "legs": (25, 41, 16, 18)},
        {"head": (24, 2, 16, 10), "torso": (22, 14, 20, 22), "arms": (28, 18, 8, 16), "legs": (24, 42, 16, 18)},
    ]
    rep = run(frames, "attack")
    st = rep["states"]["attack"]
    check(rep["ok"], "(f) attack with arms as top mover -> ok")
    check(st["top_mover"] == "arms" and st.get("verdict") == "ok", "(f) attack verdict ok, arms top")


def main():
    for t in (test_walk_legs_pass, test_dead_clip, test_wrong_region,
              test_aabb_static, test_static_never_fails, test_intent_near_top_passes):
        print("--- " + t.__name__ + " ---")
        t()
    print()
    print("ALL PASS" if PASS else "SOME FAILED")
    return 0 if PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
