#!/usr/bin/env python3
"""Derive the R8 HIT-region mask from a CALIBRATION-COLOURED skin (the `region_texture` region_source).

A calibration model paints each body region a distinct, well-separated `calib_v1` colour (head red,
torso grey, left arm/wing green, right arm/wing blue, legs purple, tail orange; + weapon shaft/head when
present). That painted colour IS the region segmentation -- so instead of needing region-keyworded
material names or an explicit `region_hitboxes` sidecar, we classify every rendered pixel by NEAREST
calib colour and fold it to the engine's 4-id body palette (head=1, torso=2, arms=3, legs=4; weapon=6).

This is the inverse of `calib_color.py` (which SAMPLES a region's colour to VERIFY it); here we classify
ALL pixels to GENERATE the mask. Reuses `calib_spec.CALIBRATION_COLORS` so the two can never drift.

  python pipeline/tools/regions_from_color.py <baked_package_dir>   # reclassify color_atlas -> a preview

Pure numpy; no Blender. The bake wires `classify_regions()` in when `region_source == "region_texture"`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from calib_spec import CALIBRATION_COLORS  # noqa: E402

# calib colour key -> the R8 body-palette id the engine reads (constants REGION_NAME_TO_ID + the contract:
# both arms fold to arms=3; tail rides torso=2 like the dragon rig; the two weapon colours -> weapon=6).
REGION_FROM_CALIB_KEY = {
    "head": 1, "torso": 2, "arm_left": 3, "arm_right": 3, "legs": 4, "tail": 2,
    "weapon_shaft": 6, "weapon_head": 6,
}

_KEYS = list(CALIBRATION_COLORS.keys())
_PAL = np.array([CALIBRATION_COLORS[k] for k in _KEYS], dtype=np.int32)            # (K,3) sRGB
_IDS = np.array([REGION_FROM_CALIB_KEY.get(k, 2) for k in _KEYS], dtype=np.uint8)  # (K,) -> R8 id

# display colours for a human-readable preview (matches the pipeline hit-sheet legend).
_VIS = {0: (0, 0, 0, 0), 1: (216, 38, 38, 255), 2: (42, 196, 64, 255),
        3: (40, 90, 224, 255), 4: (240, 200, 30, 255), 6: (250, 60, 140, 255)}


def classify_regions(rgba: np.ndarray, alpha_thresh: int = 16) -> np.ndarray:
    """RGBA image (H,W,4 or H,W,3 uint8) -> (H,W) uint8 R8 region-id mask. Each non-background pixel is
    labelled by its NEAREST calib colour (squared-RGB distance) folded to the body palette; pixels below
    `alpha_thresh` (or, for RGB input, never) are background id 0."""
    arr = np.asarray(rgba)
    rgb = arr[..., :3].astype(np.int32)                                   # (H,W,3)
    d = ((rgb[..., None, :] - _PAL[None, None, :, :]) ** 2).sum(-1)       # (H,W,K)
    out = _IDS[d.argmin(-1)]                                              # (H,W) nearest-colour id
    if arr.shape[-1] == 4:
        out = np.where(arr[..., 3] >= alpha_thresh, out, 0)
    return out.astype(np.uint8)


def visualize(region_ids: np.ndarray) -> np.ndarray:
    """(H,W) id mask -> (H,W,4) RGBA preview using the hit-sheet legend colours."""
    h, w = region_ids.shape
    out = np.zeros((h, w, 4), np.uint8)
    for rid, col in _VIS.items():
        out[region_ids == rid] = col
    return out


def _report(region_ids: np.ndarray) -> dict:
    names = {1: "head", 2: "torso", 3: "arms", 4: "legs", 6: "weapon"}
    total = int((region_ids != 0).sum()) or 1
    counts = {names.get(int(i), str(int(i))): int((region_ids == i).sum())
              for i in np.unique(region_ids) if i != 0}
    pct = {k: round(100 * v / total, 1) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}
    return {"silhouette_px": total, "region_px": counts, "region_pct_of_silhouette": pct}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: regions_from_color.py <baked_package_dir>")
        return 2
    from PIL import Image
    pkg = Path(sys.argv[1])
    color = Image.open(pkg / "color_atlas.png").convert("RGBA")
    ids = classify_regions(np.array(color))
    rep = _report(ids)
    print(f"calib palette ({len(_KEYS)} colours): {_KEYS}")
    print(f"silhouette pixels: {rep['silhouette_px']}")
    print("region split (% of silhouette):")
    for k, v in rep["region_pct_of_silhouette"].items():
        print(f"  {k:7s} {v:5.1f}%  ({rep['region_px'][k]} px)")
    distinct = [k for k in rep["region_px"] if k != "torso"]
    print(f"\n=> {len(rep['region_px'])} region(s) found; "
          f"{'MULTI-REGION (not all-torso) -- the colour map works' if distinct else 'ALL-TORSO -- colours not separating'}")
    out = pkg / "hitmask_from_color_preview.png"
    Image.fromarray(visualize(ids), "RGBA").save(out)
    print(f"preview -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
