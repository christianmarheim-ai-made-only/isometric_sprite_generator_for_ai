#!/usr/bin/env python3
"""Model previewer (host orchestrator). From a `*.asset.json`, render the SOURCE model's diagnostic
stages (blender_preview.py) and composite ONE labelled `<variant>_source_preview.png` so you can
localize a fault -- mesh / texture / hit-region / rig / animation -- BEFORE or alongside the baked
sprite. Open this first when "a sprite looks wrong": walk the rows to see WHICH stage is at fault.

  python pipeline/tools/preview_source.py your.asset.json [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_bake import find_blender  # noqa: E402
from lint_external_asset import lint  # noqa: E402


def _font(sz):
    try:
        return ImageFont.truetype("arial.ttf", sz)
    except Exception:
        try:
            return ImageFont.load_default(sz)
        except Exception:
            return ImageFont.load_default()


def _checker(d, step=8):
    yy, xx = np.mgrid[0:d, 0:d]
    m = ((xx // step + yy // step) % 2).astype(bool)
    a, b = np.array((54, 55, 62), np.uint8), np.array((41, 42, 48), np.uint8)
    return Image.fromarray(np.where(m[..., None], b, a).astype(np.uint8), "RGB")


def _compose(out: Path, meta: dict, variant: str, cell: int = 140) -> Image.Image:
    angles = meta["angles"]
    rows = [
        ("mesh (silhouette)", [f"mesh_{a}" for a in angles]),
        ("texture" if meta["has_tex"] else "material", [f"tex_{a}" for a in angles]),
        ("hit regions", [f"region_{a}" for a in angles]),
    ]
    if meta["rigged"]:
        rows.append(("rig bind pose", [f"bind_{a}" for a in angles]))
        states = []
        for cp in meta["clip_poses"]:
            st = cp.split("/")[0]
            if st not in states:
                states.append(st)
        for st in states:
            rows.append((f"anim: {st}", [f"pose_{st}_first", f"pose_{st}_last"]))

    ncol = max(len(imgs) for _, imgs in rows)
    gutter, head, pad = 120, 22, 4
    W = gutter + ncol * (cell + pad) + pad
    H = head + len(rows) * (cell + pad) + 26
    sheet = Image.new("RGB", (W, H), (26, 27, 31))
    d = ImageDraw.Draw(sheet)
    fbig, flab, fsm = _font(15), _font(12), _font(11)
    d.text((10, 4), f"{variant} — source preview  (diagnostic angles, NOT the iso camera)", font=fbig, fill=(224, 226, 232))
    for ci, a in enumerate(angles):
        d.text((gutter + ci * (cell + pad) + 4, head - 2), a, font=fsm, fill=(150, 153, 162))
    checker = _checker(cell)
    y = head + 8
    for lab, imgs in rows:
        d.text((6, y + cell // 2 - 6), lab, font=flab, fill=(224, 226, 232))
        for ci, name in enumerate(imgs):
            x = gutter + ci * (cell + pad) + pad
            block = checker.copy()
            p = out / f"{name}.png"
            if p.exists():
                im = Image.open(p).convert("RGBA").resize((cell, cell))
                block.paste(im, (0, 0), im)
            sheet.paste(block, (x, y))
            d.rectangle([x, y, x + cell, y + cell], outline=(70, 72, 80))
            if name.startswith("pose_"):
                d.text((x + 3, y + cell - 14), name.rsplit("_", 1)[-1], font=fsm, fill=(150, 153, 162))
        y += cell + pad
    fb = meta["region_fallback_materials"]
    legend = "walk mesh -> texture -> region -> rig -> anim to localize a fault."
    if fb:
        legend += f"   WARNING materials with NO region keyword (default to torso): {', '.join(fb)}"
    d.text((10, H - 18), legend, font=fsm, fill=(225, 185, 80) if fb else (150, 153, 162))
    return sheet


def _index(out: Path, meta: dict, variant: str, sheet_name: str) -> None:
    lines = [
        f"# {variant} — source preview", "",
        "Diagnostic, NON-iso views of the SOURCE model, to localize a fault before/while it becomes a sprite.",
        "", f"![source preview]({sheet_name})", "",
        f"- has_tex: **{meta['has_tex']}**  ·  rigged: **{meta['rigged']}**",
        f"- material -> region: `{meta['material_region']}`",
    ]
    if meta["region_fallback_materials"]:
        lines.append(f"- **WARNING** materials with no region keyword (silently default to torso): "
                     f"`{meta['region_fallback_materials']}`")
    lines += ["", "Stages: mesh (silhouette) -> texture -> hit regions -> rig bind -> per-clip first/last poses.",
              "Regenerate: `python pipeline/tools/preview_source.py <asset>.asset.json`"]
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def preview(asset_path, out=None) -> Path:
    asset_path = Path(asset_path)
    errs = lint(asset_path)
    if errs:
        raise SystemExit("asset lint failed:\n  " + "\n  ".join(errs))
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    base, variant = asset_path.parent, asset["variant_id"]
    out = Path(out) if out else (PIPELINE_ROOT / "output" / variant / "preview")
    out.mkdir(parents=True, exist_ok=True)
    mesh_path = (base / (asset.get("files") or {})["mesh"]).resolve()
    blender = find_blender()
    if not blender:
        raise SystemExit("Blender not found; needed for the source preview (set $BLENDER).")

    preview_mesh, states_json = str(mesh_path), None
    anims = asset.get("animations")
    clips_rel = (asset.get("files") or {}).get("animation_clips")
    if asset.get("rig") and anims:
        states = {s: {"clip": v.get("clip", s)} for s, v in anims.items()}
        sj = out / "_states.json"
        sj.write_text(json.dumps(states), encoding="utf-8")
        states_json = str(sj)
        if clips_rel:  # embed the text-authored clips so the rig poses show real animation
            animated = out / f"{variant}_animated.glb"
            r = subprocess.run([blender, "--background", "--python", str(SCRIPT_DIR / "bake_anim_from_json.py"),
                                "--", str(mesh_path), str((base / clips_rel).resolve()), str(animated)],
                               capture_output=True, text=True)
            if r.returncode != 0 or not animated.exists():
                raise SystemExit("embed clips failed:\n" + (r.stderr or "")[-1500:])
            preview_mesh = str(animated)

    cmd = [blender, "--background", "--python", str(SCRIPT_DIR / "blender_preview.py"),
           "--", str(out), str(SCRIPT_DIR), preview_mesh]
    if states_json:
        cmd.append(states_json)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if "PREVIEW_DONE" not in (r.stdout or ""):
        raise SystemExit("preview render failed:\n" + (r.stdout or "")[-1500:] + (r.stderr or "")[-1500:])

    meta = json.loads((out / "preview_meta.json").read_text(encoding="utf-8"))
    sheet_name = f"{variant}_source_preview.png"
    _compose(out, meta, variant).save(out / sheet_name)
    _index(out, meta, variant, sheet_name)
    print(f"PREVIEW {variant}: {out / sheet_name}  (has_tex={meta['has_tex']}, rigged={meta['rigged']}, "
          f"fallback={meta['region_fallback_materials']})")
    return out / sheet_name


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a diagnostic source preview from an asset manifest.")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    preview(args.manifest, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
