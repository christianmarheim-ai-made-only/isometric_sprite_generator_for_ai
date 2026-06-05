#!/usr/bin/env python3
"""Generate a UV-checker texture: a rainbow-by-column, value-alternating grid that makes UV
mapping, orientation, and stretch obvious when applied to a body. Texturers use it to validate a
UV unwrap before painting real art (every square should read square and roughly equal-sized).

  python pipeline/tools/gen_uv_checker.py OUT.png [--size 1024] [--cells 16]
"""
from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def uv_checker(size: int = 1024, cells: int = 16) -> Image.Image:
    img = np.zeros((size, size, 3), dtype=np.uint8)
    step = size / cells
    for cy in range(cells):
        for cx in range(cells):
            hue = cx / cells                      # rainbow across U (left -> right)
            val = 0.9 if (cx + cy) % 2 == 0 else 0.45   # checker value
            r, g, b = colorsys.hsv_to_rgb(hue, 0.65, val)
            y0, y1 = int(round(cy * step)), int(round((cy + 1) * step))
            x0, x1 = int(round(cx * step)), int(round((cx + 1) * step))
            img[y0:y1, x0:x1] = (int(r * 255), int(g * 255), int(b * 255))
    out = Image.fromarray(img, "RGB")
    d = ImageDraw.Draw(out)
    for i in range(cells + 1):                    # thin grid lines
        p = int(round(i * step))
        d.line([(p, 0), (p, size)], fill=(20, 20, 20), width=1)
        d.line([(0, p), (size, p)], fill=(20, 20, 20), width=1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a UV-checker validation texture.")
    ap.add_argument("out", type=Path)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--cells", type=int, default=16)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    uv_checker(args.size, args.cells).save(args.out)
    print(f"UV checker -> {args.out}  ({args.size}px, {args.cells}x{args.cells})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
