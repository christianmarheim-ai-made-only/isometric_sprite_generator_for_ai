#!/usr/bin/env python3
"""ADR-0025 gate: per-region TIGHT screen-space AABBs derived from the R8 region mask.

Asserts three things, deterministically and WITHOUT Blender:
  1. region_aabbs() bounds a SYNTHETIC mask exactly (pure helper unit test) -- absent ids omitted,
     present ids -> the tight [x,y,w,h] of their pixels in frame-local coords.
  2. Against the LIVE baked package pipeline/output/calibration_humanoid_v1 (READ-ONLY): for every
     frame, reconstruct that frame's region map by cropping the packed hitmask_atlas.png with the
     frame's mask_rect, derive region_aabbs() from it, and assert each box EXACTLY bounds that
     region's pixels (every region pixel inside the box; no rows/cols of the box empty of the region).
     This proves the derivation the bake performs is the tight bound the manifest will carry.
  3. The committed sprite_manifest.schema.json PERMITS a frame carrying region_aabbs (additive,
     optional) and REJECTS an out-of-range region id key -- existing manifests still validate.

  python pipeline/tools/test_region_aabbs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_bake import region_aabbs  # noqa: E402

SCHEMA = PIPELINE_ROOT / "schema" / "sprite_manifest.schema.json"
CALIB = PIPELINE_ROOT / "output" / "calibration_humanoid_v1"


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}: {label}{('  -> ' + detail) if detail and not ok else ''}")
    return ok


def box_is_tight(ids: np.ndarray, rid: int, box: list[int]) -> tuple[bool, str]:
    """True iff `box` [x,y,w,h] is the EXACT tight bound of id `rid` in `ids`: every rid pixel lies
    inside the box, and the box's first/last row and first/last column each contain >=1 rid pixel."""
    x, y, w, h = box
    H, W = ids.shape
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > W or y + h > H:
        return False, f"box {box} out of bounds for {ids.shape}"
    mask = (ids == rid)
    inside = mask[y:y + h, x:x + w]
    if int(inside.sum()) != int(mask.sum()):
        return False, f"id {rid}: {int(mask.sum()) - int(inside.sum())} pixel(s) outside box {box}"
    # tightness: the bounding rows/cols must touch the region (no slack border)
    if not (inside[0, :].any() and inside[-1, :].any() and inside[:, 0].any() and inside[:, -1].any()):
        return False, f"id {rid}: box {box} has a slack (region-free) border row/col"
    return True, ""


def test_synthetic() -> bool:
    ok = True
    # 6x5 mask (rows x cols): a 2x2 block of id1 at (col1,row1), a single id2 at (col4,row4); no id3/id4.
    ids = np.zeros((6, 5), dtype=np.uint8)
    ids[1:3, 1:3] = 1   # rows 1..2, cols 1..2
    ids[4, 4] = 2       # row 4, col 4
    aabbs = region_aabbs(ids)
    ok &= check("synthetic: only present ids emitted (1,2)", set(aabbs.keys()) == {"1", "2"},
                f"got {sorted(aabbs.keys())}")
    ok &= check("synthetic: id1 tight box == [1,1,2,2]", aabbs.get("1") == [1, 1, 2, 2], str(aabbs.get("1")))
    ok &= check("synthetic: id2 single-pixel box == [4,4,1,1]", aabbs.get("2") == [4, 4, 1, 1], str(aabbs.get("2")))
    # an all-background mask emits nothing
    ok &= check("synthetic: empty mask -> {}", region_aabbs(np.zeros((4, 4), np.uint8)) == {})
    # every emitted box is genuinely tight by the independent checker
    for k, b in aabbs.items():
        good, why = box_is_tight(ids, int(k), b)
        ok &= check(f"synthetic: box for id {k} is exactly tight", good, why)
    return ok


def test_live_calibration() -> bool:
    """Reconstruct each frame's region map from the packed hitmask + mask_rect and assert the derived
    AABBs are exactly tight. Skips cleanly if the read-only calibration package is not present."""
    man_p = CALIB / "manifest.json"
    atlas_p = CALIB / "hitmask_atlas.png"
    if not (man_p.exists() and atlas_p.exists()):
        print("SKIP: calibration_humanoid_v1 not present; live AABB check not run.")
        return True
    manifest = json.loads(man_p.read_text(encoding="utf-8"))
    atlas = np.asarray(Image.open(atlas_p).convert("L"))  # packed R8 ids {0..4}
    ok = True
    frames = manifest["frames"]
    checked_boxes = 0
    frames_with_all_regions = 0
    for fr in frames:
        x, y, w, h = fr["mask_rect"]
        crop = atlas[y:y + h, x:x + w]
        present = {int(v) for v in np.unique(crop)} & {1, 2, 3, 4}
        if {1, 2, 3, 4} <= present:
            frames_with_all_regions += 1
        derived = region_aabbs(crop)
        # exactly the present body ids get a box, nothing else
        if {int(k) for k in derived} != present:
            ok &= check("live: region_aabbs keys == present body ids", False,
                        f"frame {fr.get('state')}/{fr.get('frame_index')}/d{fr.get('direction')}: "
                        f"derived {sorted(derived)} vs present {sorted(present)}")
            break
        for k, b in derived.items():
            good, why = box_is_tight(crop, int(k), b)
            checked_boxes += 1
            if not good:
                ok &= check("live: derived AABB exactly bounds its region pixels", False, why)
                break
        else:
            continue
        break
    ok &= check(f"live: all {checked_boxes} derived AABBs (over {len(frames)} frames) exactly bound "
                f"their region pixels", ok and checked_boxes > 0)
    ok &= check(f"live: frames carrying the full {{1,2,3,4}} region set exercised the path "
                f"({frames_with_all_regions} frames)", frames_with_all_regions > 0)
    return ok


def test_schema_permits() -> bool:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    base_frame = {
        "direction": 0, "world_yaw_degrees": 0.0, "rect": [4, 4, 10, 20], "mask_rect": [4, 4, 10, 20],
        "anchor": [5.0, 5.0], "sockets": {"origin": [5.0, 5.0]},
    }

    def frame_errs(extra: dict) -> list[str]:
        fr = dict(base_frame); fr.update(extra)
        man = {
            "manifest_version": "sprite_manifest_multistate_v1",
            "contract_hash": "sha256:" + "0" * 64, "state_contract_version": "v1",
            "camera": {"id": "game_iso_v1"}, "variant_id": "t", "variant_class": "character",
            "frame_canvas": [256, 256], "direction_count": 16,
            "atlases": {"color": {"path": "c.png", "size": [16, 16]},
                        "hitmask": {"path": "h.png", "size": [16, 16],
                                    "format": "PNG_R8_UINT_linear_no_antialias", "sampling": "nearest",
                                    "palette": {"none": 0}}},
            "frames": [fr], "world_metrics": {"height_world": 1.0, "footprint_radius_world": 0.5},
            "build": {},
        }
        return [f"/{'/'.join(map(str, e.path))}: {e.message}" for e in validator.iter_errors(man)]

    ok = True
    ok &= check("schema: a frame WITHOUT region_aabbs still validates (additive/optional)",
                not frame_errs({}))
    ok &= check("schema: a frame WITH a valid region_aabbs validates",
                not frame_errs({"region_aabbs": {"1": [0, 0, 4, 4], "3": [1, 1, 8, 19]}}),
                "; ".join(frame_errs({"region_aabbs": {"1": [0, 0, 4, 4]}})))
    ok &= check("schema: region_aabbs REJECTS an out-of-range id key ('5')",
                len(frame_errs({"region_aabbs": {"5": [0, 0, 4, 4]}})) >= 1)
    ok &= check("schema: region_aabbs REJECTS a malformed box (3-tuple)",
                len(frame_errs({"region_aabbs": {"2": [0, 0, 4]}})) >= 1)
    return ok


def main() -> int:
    ok = True
    ok &= test_synthetic()
    ok &= test_live_calibration()
    ok &= test_schema_permits()
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
