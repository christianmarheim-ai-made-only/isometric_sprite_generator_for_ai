#!/usr/bin/env python3
"""shard_atlas.py -- re-pack a baked SINGLE-page package into a MULTI-page (paged) package, one
atlas page per animation state (atlas_page_policy="per_state"). This is the atlas-paging emitter:
the pipeline bakes a single page by default; shard a package once it exceeds the per-page budget
(16 dirs x many frames x many actions x higher resolution won't fit one page). Per-state pages let
the engine lazy/partial-load by state. See docs/atlas_paging_contract.md.

  python pipeline/tools/shard_atlas.py PACKAGE_DIR --out OUT_DIR

The output package is byte-equivalent in pixels to the input, just split across per-state pages;
the manifest gains atlases.color.pages / atlases.hitmask.pages and a per-frame `page`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake import shelf_place, place_into  # noqa: E402
from constants import MAX_PAGE_PX, PAD  # noqa: E402  (per-page cap; see atlas_paging_contract.md §5)


def _box(rect):
    x, y, w, h = rect
    return (x, y, x + w, y + h)


def _single_path(atlas: dict, key: str) -> str:
    if "pages" in atlas:
        raise SystemExit(f"atlases.{key} is already paged")
    return atlas["path"]


class OversizePageError(RuntimeError):
    """A sharded page exceeds MAX_PAGE_PX. Hard failure (not a warning): an oversize page is a
    package the engine cannot load. See build_log.oversize_atlas_page (severity=error) for the
    production-gate side and atlas_paging_contract.md §7 for the FUTURE within-state split."""


def shard(pkg: Path, out: Path, policy: str = "per_state") -> dict:
    pkg, out = Path(pkg), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    m = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    color = Image.open(pkg / _single_path(m["atlases"]["color"], "color")).convert("RGBA")
    hit = Image.open(pkg / _single_path(m["atlases"]["hitmask"], "hitmask")).convert("L")
    frames = m["frames"]
    states = sorted({f.get("state", "idle") for f in frames})  # per_state: one page per state

    color_pages, hit_pages, new_frames, oversize = [], [], [], []
    for page_index, state in enumerate(states):
        sfr = [f for f in frames if f.get("state", "idle") == state]
        cims = [color.crop(_box(f["rect"])) for f in sfr]
        mims = [hit.crop(_box(f.get("mask_rect", f["rect"]))) for f in sfr]
        # Target MAX_PAGE_PX - PAD: shelf_place returns content_width + PAD, so packing up to
        # MAX_PAGE_PX would overshoot the cap by PAD (a fully-packed row yielded 4097-4099px).
        placements, atlas_size = shelf_place([im.size for im in cims], max_w=MAX_PAGE_PX - PAD)
        cpage, rects = place_into(cims, placements, atlas_size, "RGBA")
        mpage, _ = place_into(mims, placements, atlas_size, "L")
        if cpage.width > MAX_PAGE_PX or cpage.height > MAX_PAGE_PX:
            oversize.append((state, list(cpage.size)))
        cpage.save(out / f"color.{state}.png")
        mpage.save(out / f"mask.{state}.png")
        color_pages.append({"path": f"color.{state}.png", "size": list(cpage.size)})
        hit_pages.append({"path": f"mask.{state}.png", "size": list(mpage.size)})
        for f, r in zip(sfr, rects):
            nf = dict(f)
            nf["page"], nf["rect"], nf["mask_rect"] = page_index, r, r
            new_frames.append(nf)

    col0, hm0 = m["atlases"]["color"], m["atlases"]["hitmask"]
    out_m = dict(m)
    out_m["atlases"] = {
        "color": {**{k: col0[k] for k in ("format", "sampling") if k in col0}, "pages": color_pages},
        "hitmask": {**{k: hm0[k] for k in ("format", "sampling", "palette") if k in hm0}, "pages": hit_pages},
    }
    out_m["frames"] = new_frames
    out_m["atlas_page_policy"] = policy
    (out / "manifest.json").write_text(json.dumps(out_m, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if oversize:
        detail = ", ".join(f"{s} {sz}" for s, sz in oversize)
        raise OversizePageError(
            f"{len(oversize)} page(s) exceed {MAX_PAGE_PX}px: {detail}. A single state larger than one "
            f"max page needs the greedy-within-state split (FUTURE; atlas_paging_contract.md §7).")
    return out_m


def main() -> int:
    ap = argparse.ArgumentParser(description="Shard a single-page package into per-state atlas pages.")
    ap.add_argument("package", type=Path, help="baked single-page package dir (manifest.json + atlases)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    try:
        m = shard(args.package, args.out)
    except OversizePageError as e:
        print(f"SHARD FAILED: {e}")
        return 1
    pages = len(m["atlases"]["color"]["pages"])
    print(f"SHARDED [per_state]: {m['variant_id']} -> {args.out}  ({pages} pages, {len(m['frames'])} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
