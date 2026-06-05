#!/usr/bin/env python3
"""Render a UV-layout template PNG from uv_islands.json (dumped by gen_texture_starter.py).

Draws each UV face polygon into texture space, tinted by HIT region (head=red, torso=green,
arms=blue, legs=yellow) so the texturer can see which island is which body part and paint inside
the wireframe. (Blender's bpy.ops.uv.export_layout needs a GPU and is unavailable headless, so the
layout is drawn here with PIL instead.)

  python pipeline/tools/draw_uv_layout.py uv_islands.json OUT.png [--size 1024]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

REGION_FILL = {1: (219, 56, 56), 2: (56, 179, 92), 3: (69, 120, 242), 4: (237, 201, 51)}


def draw_layout(islands_path: Path, out: Path, size: int = 1024) -> None:
    data = json.loads(Path(islands_path).read_text(encoding="utf-8"))
    img = Image.new("RGBA", (size, size), (250, 250, 250, 255))
    fill_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fill_layer)
    d = ImageDraw.Draw(img)
    for poly in data["polys"]:
        pts = [(u * size, (1.0 - v) * size) for u, v in poly["uv"]]  # V up -> image y down
        if len(pts) < 3:
            continue
        col = REGION_FILL.get(int(poly["region"]), (150, 150, 150))
        fd.polygon(pts, fill=(*col, 70))
    img.alpha_composite(fill_layer)
    for poly in data["polys"]:
        pts = [(u * size, (1.0 - v) * size) for u, v in poly["uv"]]
        if len(pts) < 3:
            continue
        col = REGION_FILL.get(int(poly["region"]), (90, 90, 90))
        d.line(pts + [pts[0]], fill=(*col, 255), width=2)
    img.convert("RGB").save(out)
    print(f"UV layout -> {out}  ({len(data['polys'])} faces, {size}px)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a UV-layout template from uv_islands.json.")
    ap.add_argument("islands", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--size", type=int, default=1024)
    args = ap.parse_args()
    draw_layout(args.islands, args.out, args.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
