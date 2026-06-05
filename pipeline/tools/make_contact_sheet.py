#!/usr/bin/env python3
"""make_contact_sheet.py -- turn a baked game_iso_v1 sprite package into human-viewable
contact sheets so a person can VERIFY it by eye.

For a package directory (manifest.json + color_atlas.png + hitmask_atlas.png) it writes:
  <variant>_color_sheet.png  -- every (state, frame, direction) laid out in a labelled grid,
                                each frame reconstructed in its logical canvas, with the
                                ANCHOR (magenta cross) and FACING arrow (cyan) overlaid so you
                                can confirm the 16 directions rotate correctly.
  <variant>_hit_sheet.png    -- the same layout, but the R8 HIT-mask recoloured by region
                                (head=red torso=green arms=blue legs=yellow) so you can confirm
                                the gameplay hit regions are present and sane.

Works for BOTH manifest shapes: single-state (full-canvas rects) and multi-state
(tight-crop rect + trim + logical_frame_canvas, top-level `animations`).

  python pipeline/tools/make_contact_sheet.py PACKAGE_DIR [--cell 104]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Region id -> RGB (matches blender_render.REGION_COLOR scaled to 0..255).
REGION_COLOR = {
    1: (219, 56, 56),    # head
    2: (56, 179, 92),    # torso
    3: (69, 120, 242),   # arms
    4: (237, 201, 51),   # legs
    5: (200, 120, 220),  # reserved equip (should not appear: body-only)
    6: (120, 200, 220),
    7: (220, 160, 120),
}
ANCHOR_RGB = (255, 64, 200)
FACE_RGB = (64, 230, 230)
BG = (26, 27, 31)
CHECK_A = (54, 55, 62)
CHECK_B = (41, 42, 48)
INK = (224, 226, 232)
DIM = (150, 153, 162)


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.load_default(size)
        except Exception:
            return ImageFont.load_default()


def _checker(disp: int, step: int = 8) -> Image.Image:
    a = np.array(CHECK_A, dtype=np.uint8)
    b = np.array(CHECK_B, dtype=np.uint8)
    yy, xx = np.mgrid[0:disp, 0:disp]
    mask = ((xx // step + yy // step) % 2).astype(bool)
    img = np.where(mask[..., None], b, a).astype(np.uint8)
    return Image.fromarray(img, "RGB")


def _logical_canvas(manifest: dict, frame: dict):
    lc = frame.get("logical_frame_canvas") or manifest.get("logical_frame_canvas") or manifest["frame_canvas"]
    return int(lc[0]), int(lc[1])


def _reconstruct_color(atlas: Image.Image, frame: dict, lw: int, lh: int) -> Image.Image:
    x, y, w, h = frame["rect"]
    crop = atlas.crop((x, y, x + w, y + h)).convert("RGBA")
    cell = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    tx, ty = frame.get("trim", [0, 0])
    cell.alpha_composite(crop, (int(tx), int(ty)))
    return cell


def _reconstruct_hit(hit: Image.Image, frame: dict, lw: int, lh: int) -> Image.Image:
    x, y, w, h = frame.get("mask_rect", frame["rect"])
    arr = np.asarray(hit.crop((x, y, x + w, y + h)).convert("L"))
    rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
    for rid, col in REGION_COLOR.items():
        m = arr == rid
        if m.any():
            rgba[m] = (*col, 255)
    cell = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    tx, ty = frame.get("trim", [0, 0])
    cell.alpha_composite(Image.fromarray(rgba, "RGBA"), (int(tx), int(ty)))
    return cell


def _group(manifest: dict):
    default_state = manifest.get("default_state", "idle")
    states: dict[str, dict[tuple, dict]] = {}
    for f in manifest["frames"]:
        st = f.get("state", default_state)
        states.setdefault(st, {})[(f.get("frame_index", 0), f["direction"])] = f
    # order states: default first, then the rest alphabetically
    keys = sorted(states, key=lambda s: (s != default_state, s))
    return keys, states, default_state


def _draw_arrow(draw: ImageDraw.ImageDraw, p0, p1, color, width=2):
    draw.line([p0, p1], fill=color, width=width)
    import math
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(dx, dy)
    if n < 1e-3:
        draw.ellipse([p1[0] - 2, p1[1] - 2, p1[0] + 2, p1[1] + 2], fill=color)
        return
    ux, uy = dx / n, dy / n
    a = 5
    left = (p1[0] - a * ux + a * 0.6 * uy, p1[1] - a * uy - a * 0.6 * ux)
    right = (p1[0] - a * ux - a * 0.6 * uy, p1[1] - a * uy + a * 0.6 * ux)
    draw.polygon([p1, left, right], fill=color)


def contact_sheet(pkg_dir: Path, out_dir: Path | None = None, cell: int = 104) -> dict:
    pkg_dir = Path(pkg_dir)
    manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    color_atlas = Image.open(pkg_dir / manifest["atlases"]["color"]["path"]).convert("RGBA")
    hit_atlas = Image.open(pkg_dir / manifest["atlases"]["hitmask"]["path"]).convert("L")
    out_dir = Path(out_dir) if out_dir else pkg_dir
    variant = manifest["variant_id"]
    dc = int(manifest["direction_count"])

    keys, states, default_state = _group(manifest)
    f_big, f_lab, f_small = _font(15), _font(12), _font(11)

    gutter, header_h, banner_h, pad, top, bottom = 46, 16, 24, 3, 30, 26
    cols = dc
    block_w = gutter + cols * (cell + pad) + pad
    sheet_w = max(block_w, 560)

    # measure height
    nfs = {st: (max(fi for (fi, _d) in states[st]) + 1) for st in keys}
    total_h = top
    for st in keys:
        total_h += banner_h + header_h + nfs[st] * (cell + pad) + 10
    total_h += bottom

    def build(kind: str) -> Image.Image:
        sheet = Image.new("RGB", (sheet_w, total_h), BG)
        d = ImageDraw.Draw(sheet)
        checker = _checker(cell)
        d.text((10, 8), f"{variant}  —  {kind} sheet   ({dc} dirs, canvas {manifest['frame_canvas']}, "
                        f"atlas {manifest['atlases']['color']['size']})", font=f_big, fill=INK)
        y = top
        for st in keys:
            anim = (manifest.get("animations") or {}).get(st, {})
            tag = f"  [{anim.get('playback','-')}, {anim.get('fps','-')}fps]" if anim else ""
            star = "  ◀ default" if st == default_state else ""
            d.rectangle([6, y, sheet_w - 6, y + banner_h - 4], fill=(38, 39, 46))
            d.text((12, y + 3), f"state: {st}{tag}{star}", font=f_lab, fill=INK)
            y += banner_h
            # direction header
            for di in range(cols):
                cx = gutter + di * (cell + pad) + pad
                d.text((cx + 2, y + 2), f"d{di:02d}", font=f_small, fill=DIM)
            y += header_h
            nf = nfs[st]
            for fi in range(nf):
                d.text((8, y + cell // 2 - 6), f"f{fi}", font=f_lab, fill=INK)
                for di in range(cols):
                    fr = states[st].get((fi, di))
                    cx = gutter + di * (cell + pad) + pad
                    if fr is None:
                        d.rectangle([cx, y, cx + cell, y + cell], outline=(90, 40, 40))
                        continue
                    lw, lh = _logical_canvas(manifest, fr)
                    rec = (_reconstruct_color(color_atlas, fr, lw, lh) if kind == "color"
                           else _reconstruct_hit(hit_atlas, fr, lw, lh))
                    disp = rec.resize((cell, cell), Image.NEAREST if kind == "hit" else Image.BILINEAR)
                    block = checker.copy()
                    block.paste(Image.new("RGB", (cell, cell), (0, 0, 0)), (0, 0), disp.split()[3])
                    block.paste(disp, (0, 0), disp)
                    sheet.paste(block, (cx, y))
                    d.rectangle([cx, y, cx + cell, y + cell], outline=(70, 72, 80))
                    # overlays in logical coords -> display coords
                    sx, sy = cell / lw, cell / lh
                    ax, ay = fr["anchor"]
                    apx, apy = cx + ax * sx, y + ay * sy
                    sock = fr.get("sockets", {})
                    o = sock.get("origin", fr["anchor"])
                    t = sock.get("direction_tip")
                    if t is not None:
                        _draw_arrow(d, (cx + o[0] * sx, y + o[1] * sy), (cx + t[0] * sx, y + t[1] * sy), FACE_RGB)
                    d.line([(apx - 4, apy), (apx + 4, apy)], fill=ANCHOR_RGB, width=1)
                    d.line([(apx, apy - 4), (apx, apy + 4)], fill=ANCHOR_RGB, width=1)
                y += cell + pad
            y += 10
        legend = ("anchor=magenta cross · facing=cyan arrow"
                  if kind == "color"
                  else "head=red · torso=green · arms=blue · legs=yellow")
        d.text((10, total_h - 18), legend, font=f_small, fill=DIM)
        return sheet

    color_path = out_dir / f"{variant}_color_sheet.png"
    hit_path = out_dir / f"{variant}_hit_sheet.png"
    build("color").save(color_path)
    build("hit").save(hit_path)
    return {"variant": variant, "color_sheet": str(color_path), "hit_sheet": str(hit_path),
            "states": {st: nfs[st] for st in keys}, "directions": dc}


def main() -> int:
    ap = argparse.ArgumentParser(description="Render contact sheets for a baked sprite package.")
    ap.add_argument("package", type=Path, help="package dir containing manifest.json")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--cell", type=int, default=104)
    args = ap.parse_args()
    info = contact_sheet(args.package, args.out, args.cell)
    print(f"CONTACT SHEET {info['variant']}: {info['states']} dirs={info['directions']}")
    print(f"  color -> {info['color_sheet']}")
    print(f"  hit   -> {info['hit_sheet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
