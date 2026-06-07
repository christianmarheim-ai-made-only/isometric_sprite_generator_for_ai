#!/usr/bin/env python3
"""Gate: in-baker atlas paging (ADR-0037). A single-page bake that overflows MAX_PAGE_PX is auto-sharded
into per-state pages by bake_asset._page_if_oversize, the paged manifest passes Gate-1 (engine acceptance),
and the loader's paging invariants are enforced. Exercises the REAL auto-shard code path -- no Blender.

  python pipeline/tools/test_atlas_paging.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from constants import MAX_PAGE_PX            # noqa: E402
from bake_asset import _page_if_oversize     # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def _oversize_package(out: Path):
    """An OVERSIZE single-page multistate package: 1 direction, idle(1 frame)+walk(2 frames), packed into a
    120 x 5000 atlas (5000 > MAX_PAGE_PX) so paging must kick in. Frame content is non-zero (not blank)."""
    W, H, FW, FH = 120, 5000, 80, 200
    frames = [("idle", 0, 0, 0, 0), ("walk", 0, 0, 0, 300), ("walk", 0, 1, 0, 600)]
    color = np.zeros((H, W, 4), np.uint8)
    mask = np.zeros((H, W), np.uint8)
    fr = []
    for st, d, fi, x, y in frames:
        color[y:y + FH, x:x + FW] = (200, 120, 60, 255)
        mask[y:y + FH, x:x + FW] = 2          # torso id -> non-blank
        fr.append({"state": st, "direction": d, "frame_index": fi, "page": 0,
                   "rect": [x, y, FW, FH], "mask_rect": [x, y, FW, FH], "anchor": [40, 190]})
    Image.fromarray(color, "RGBA").save(out / "color_atlas.png")
    Image.fromarray(mask, "L").save(out / "hitmask_atlas.png")
    manifest = {
        "manifest_version": "sprite_manifest_multistate_v1",
        "camera": {"id": "game_iso_v1", "azimuth_degrees": 45, "camera_elevation_degrees": 30,
                   "projection": "orthographic_pixel_iso_dimetric_2_to_1", "screen_y": "down", "tile_px": [64, 32]},
        "variant_id": "pager_test", "variant_class": "character", "direction_count": 1,
        "frame_canvas": [256, 256], "logical_frame_canvas": [256, 256], "default_state": "idle",
        "animations": {"idle": {"directions": 1, "frames": 1, "fps": 1, "playback": "loop"},
                       "walk": {"directions": 1, "frames": 2, "fps": 8, "playback": "loop"}},
        "atlases": {"color": {"path": "color_atlas.png", "size": [W, H]},
                    "hitmask": {"path": "hitmask_atlas.png", "size": [W, H],
                                "format": "PNG_R8_UINT_linear_no_antialias", "sampling": "nearest",
                                "palette": {"none": 0, "head": 1, "torso": 2, "arms": 3, "legs": 4}}},
        "frames": fr,
        "world_metrics": {"height_world": 1.8, "footprint_radius_world": 0.4},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    ok = True

    # single-page that FITS -> unchanged (byte-identical; goldens safe)
    fit = {"atlases": {"color": {"path": "c.png", "size": [2048, 1576]}}}
    ok &= check("fits one page -> NOT paged (unchanged)", _page_if_oversize(Path("."), fit) is fit)

    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        src = _oversize_package(out)
        ok &= check("setup: single page exceeds MAX_PAGE_PX", max(src["atlases"]["color"]["size"]) > MAX_PAGE_PX)

        paged = _page_if_oversize(out, src)
        col = paged["atlases"]["color"]
        hit = paged["atlases"]["hitmask"]
        ok &= check("oversize bake -> auto-sharded into pages", "pages" in col and "pages" in hit)
        ok &= check("per_state policy -> one page per state (idle, walk)", len(col["pages"]) == 2)
        ok &= check("color.pages == hitmask.pages (loader invariant 1)", len(col["pages"]) == len(hit["pages"]))
        ok &= check("every page within MAX_PAGE_PX", all(max(p["size"]) <= MAX_PAGE_PX for p in col["pages"]))
        ok &= check("every frame carries a page index", all("page" in f for f in paged["frames"]))
        ok &= check("walk frames -> a different page than idle",
                    {f["page"] for f in paged["frames"] if f["state"] == "idle"} !=
                    {f["page"] for f in paged["frames"] if f["state"] == "walk"})
        ok &= check("orphaned single-page color_atlas.png removed", not (out / "color_atlas.png").exists())
        ok &= check("per-state page PNGs written", (out / "color.idle.png").exists() and (out / "color.walk.png").exists())

        # the PAGED manifest is engine-acceptable (Gate-1)
        ok &= check("paged manifest passes Gate-1 (engine acceptance)", engine_accept(paged) == [])

        # NEGATIVE: a paged frame whose rect exceeds its page is rejected
        bad = json.loads(json.dumps(paged))
        bad["frames"][0]["rect"] = [0, 0, 99999, 99999]
        ok &= check("paged frame rect exceeding its page -> Gate-1 FAIL",
                    any("exceeds page" in e for e in engine_accept(bad)))

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
