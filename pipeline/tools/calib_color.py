#!/usr/bin/env python3
"""Calibration colour <-> hitbox verification (calib_v1).

For a calibration model, each region is painted a distinct, hard-coded colour (calib_spec.CALIBRATION_COLORS:
head=red, torso=grey, left arm/wing=green, right arm/wing=blue, legs=purple, tail=orange) and the
region_hitboxes sidecar declares a box per region. This gate projects each region-hitbox's CENTRE through
the SAME per-direction camera the bake used (the region_rects blender_render emits, ADR-0036), samples the
baked COLOUR atlas at that centre, and asserts the sampled colour matches the region's EXPECTED calibration
colour. A mismatch means the texture, the UVs, or the hitbox disagree -- exactly the class of bug a
calibration model exists to catch.

Robust to occlusion: a region's centre is sampled in EVERY direction where it lands on the silhouette, and
the region passes iff the expected colour is the DOMINANT nearest-match across those directions.

  verify(out_dir, manifest, meta) -> {"ok": bool, "regions": {name: {...}}, "mismatches": [...]}
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from calib_spec import CALIBRATION_COLORS, calib_color_key  # noqa: E402

ALPHA_MIN = 200          # a sampled pixel counts only if effectively opaque (on the silhouette)
SAMPLE_RADIUS = 3        # majority colour in a (2r+1)^2 box around the centre (dodge AA seams / a thin centre)


def nearest_calib_color(rgb):
    """(key, distance) of the closest calibration colour to an (r,g,b)."""
    best, bd = None, 1e18
    for key, c in CALIBRATION_COLORS.items():
        d = (rgb[0] - c[0]) ** 2 + (rgb[1] - c[1]) ** 2 + (rgb[2] - c[2]) ** 2
        if d < bd:
            best, bd = key, d
    return best, bd ** 0.5


def _dominant_color(atlas, ax, ay, r=SAMPLE_RADIUS):
    """Most common opaque colour in a small box around (ax,ay), or None if all transparent/out of bounds."""
    W, H = atlas.size
    px = atlas.load()
    counts = Counter()
    for yy in range(max(0, ay - r), min(H, ay + r + 1)):
        for xx in range(max(0, ax - r), min(W, ax + r + 1)):
            p = px[xx, yy]
            if len(p) == 4 and p[3] < ALPHA_MIN:
                continue
            counts[(p[0], p[1], p[2])] += 1
    return counts.most_common(1)[0][0] if counts else None


def _color_atlas_pages(out_dir: Path, manifest: dict):
    a = (manifest.get("atlases") or {}).get("color") or {}
    if a.get("pages"):
        return [out_dir / p["path"] for p in a["pages"]]
    if a.get("path"):
        return [out_dir / a["path"]]
    return [out_dir / "color_atlas.png"]


def verify(out_dir, manifest: dict, meta: dict) -> dict:
    """Verify the calibration colours match the region hitboxes. `meta` is blender_meta.json (it carries the
    per-direction region_rects ADR-0036 projects). Returns a report; ['ok'] is False on any mismatch."""
    from PIL import Image
    out_dir = Path(out_dir)
    region_rects = (meta or {}).get("region_rects") or {}
    if not region_rects:
        return {"ok": True, "skipped": "no region_rects (model shipped no explicit hitbox map)", "regions": {}, "mismatches": []}

    pages = [Image.open(p).convert("RGBA") if p.exists() else None for p in _color_atlas_pages(out_dir, manifest)]
    frames = {}
    for f in manifest.get("frames", []) or []:
        frames.setdefault(f.get("direction"), f)     # static calibration bake: one frame per direction

    samples: dict[str, Counter] = {}
    for ds, regs in region_rects.items():
        d = int(ds)
        fr = frames.get(d)
        if not fr:
            continue
        atlas = pages[fr.get("page", 0)] if fr.get("page", 0) < len(pages) else None
        if atlas is None:
            continue
        fx, fy = fr["rect"][0], fr["rect"][1]
        for reg in regs:
            key = calib_color_key(reg.get("name", ""))
            if key is None:
                continue
            rx, ry, rw, rh = reg["rect"]
            col = _dominant_color(atlas, fx + rx + rw // 2, fy + ry + rh // 2)
            if col is None:
                continue                              # region centre occluded/off-silhouette this direction
            samples.setdefault(reg["name"], Counter())[nearest_calib_color(col)[0]] += 1

    regions, mismatches = {}, []
    for name, ctr in samples.items():
        expected = calib_color_key(name)
        dominant, n = ctr.most_common(1)[0]
        ok = dominant == expected
        regions[name] = {"expected": expected, "dominant": dominant, "ok": ok,
                         "samples": sum(ctr.values()), "agreement": round(n / sum(ctr.values()), 3)}
        if not ok:
            mismatches.append(name)
    # a calibration model that declares colour-bearing regions but never sampled any -> nothing proven
    declared = {reg.get("name") for regs in region_rects.values() for reg in regs if calib_color_key(reg.get("name", ""))}
    unsampled = sorted(declared - set(samples))
    return {"ok": not mismatches, "regions": regions, "mismatches": mismatches,
            "unsampled_regions": unsampled, "calib_spec_version": "calib_v1"}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: calib_color.py <baked_package_dir>")
        return 2
    pkg = Path(sys.argv[1])
    manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    meta_p = pkg / "blender_meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    rep = verify(pkg, manifest, meta)
    print(json.dumps(rep, indent=2))
    if rep.get("mismatches"):
        print(f"CALIB COLOUR FAIL: {len(rep['mismatches'])} region(s) mismatch: {rep['mismatches']}")
        return 1
    print("CALIB COLOUR OK" + (f" ({rep['skipped']})" if rep.get("skipped") else
          f" ({len(rep['regions'])} regions verified)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
