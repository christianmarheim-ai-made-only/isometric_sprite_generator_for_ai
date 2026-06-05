#!/usr/bin/env python3
"""Generate C5 style assets: palette swatch + readability previews (headless PIL).

Outputs (under pipeline/style/):
- palette_swatch.png  : labeled swatch of palette.json
- style_previews.png  : a sample sprite at 256 px / 128 px + silhouette

Self-checks palette shape, straight-alpha (RGBA) sample, and that outputs render.
Run: python pipeline/tools/make_style_assets.py   (exit 0 = ok)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
STYLE_DIR = PIPELINE_ROOT / "style"
PALETTE = STYLE_DIR / "palette.json"
SAMPLE = PIPELINE_ROOT / "output" / "arrow_pilot" / "frames" / "color" / "arrow_idle_dir02_frame00.png"
PANEL = (240, 242, 245, 255)
OUTLINE = (26, 22, 30, 255)


def make_swatch(colors) -> Image.Image:
    cols = 4
    rows = (len(colors) + cols - 1) // cols
    cw, ch, pad = 150, 58, 10
    img = Image.new("RGBA", (cols * cw + pad, rows * ch + pad), PANEL)
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for i, c in enumerate(colors):
        cx = pad + (i % cols) * cw
        cy = pad + (i // cols) * ch
        rgba = tuple(c["rgba"])
        d.rectangle([cx, cy, cx + 40, cy + 40], fill=rgba, outline=OUTLINE)
        hexs = "#%02X%02X%02X" % (rgba[0], rgba[1], rgba[2])
        d.text((cx + 48, cy + 4), c["name"], fill=(0, 0, 0, 255), font=font)
        d.text((cx + 48, cy + 18), c.get("role", ""), fill=(90, 90, 90, 255), font=font)
        d.text((cx + 48, cy + 30), hexs, fill=(60, 60, 60, 255), font=font)
    return img


def make_previews(sample: Image.Image) -> Image.Image:
    p256 = sample.resize((256, 256), Image.NEAREST)
    p128 = sample.copy()
    sil = Image.new("RGBA", sample.size, (0, 0, 0, 0))
    spx, apx = sil.load(), sample.load()
    for y in range(sample.size[1]):
        for x in range(sample.size[0]):
            if apx[x, y][3] >= 8:
                spx[x, y] = OUTLINE
    panels = [("256 px", p256), ("128 px", p128), ("silhouette", sil)]
    gap, label_h = 16, 18
    width = sum(p.size[0] for _, p in panels) + gap * (len(panels) + 1)
    height = max(p.size[1] for _, p in panels) + gap * 2 + label_h
    out = Image.new("RGBA", (width, height), PANEL)
    d = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    x = gap
    for label, p in panels:
        out.alpha_composite(p, (x, gap + label_h))
        d.text((x, gap), label, fill=(0, 0, 0, 255), font=font)
        x += p.size[0] + gap
    return out


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    colors = json.loads(PALETTE.read_text(encoding="utf-8"))["colors"]
    ok &= check("palette has colors", len(colors) > 0)
    shape_ok = all(
        isinstance(c["rgba"], list) and len(c["rgba"]) == 4
        and all(isinstance(v, int) and 0 <= v <= 255 for v in c["rgba"])
        for c in colors
    )
    ok &= check("every color is RGBA ints 0..255", shape_ok)

    make_swatch(colors).save(STYLE_DIR / "palette_swatch.png")
    ok &= check("palette_swatch.png written", (STYLE_DIR / "palette_swatch.png").exists())

    if SAMPLE.exists():
        sample = Image.open(SAMPLE)
        ok &= check("sample sprite is straight-alpha RGBA", sample.mode == "RGBA")
        make_previews(sample.convert("RGBA")).save(STYLE_DIR / "style_previews.png")
        ok &= check("style_previews.png written (256/128/silhouette)", (STYLE_DIR / "style_previews.png").exists())
    else:
        print(f"WARN: sample sprite not found ({SAMPLE}); run build.py first to generate previews")

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
