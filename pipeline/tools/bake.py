#!/usr/bin/env python3
"""bake.py — orchestrate a 3D mesh into an engine-shaped game_iso_v1 package (R2).

The renderer-driven path (vs generate_arrow_pilot's 2D draw): render 16 directions
through the game_iso_v1 camera (R1 render3d), pack a color atlas, emit an
engine-valid manifest (top-level `camera` block + per-frame rect/anchor/sockets +
`world_metrics`) + the direction oracle, and run Gate 1 (engine acceptance).

R4 extends this with the HIT-proxy R8 hitmask + measured metrics; here it is color +
placeholder probe metrics on a procedural mesh.

Run: python pipeline/tools/bake.py [--mesh cube|pole|arrow] [--out DIR] [--canvas N]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import meshes  # noqa: E402
from render3d import render_directions, ground_screen_direction  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402

PAD = 4
DIRS = 16
MESHES = {"cube": meshes.cube, "pole": meshes.pole, "arrow": meshes.arrow_wedge}


def _extrude_paste(atlas: Image.Image, frame: Image.Image, x: int, y: int, pad: int) -> None:
    w, h = frame.size
    atlas.paste(frame, (x, y))
    atlas.paste(frame.crop((0, 0, 1, h)).resize((pad, h), Image.NEAREST), (x - pad, y))
    atlas.paste(frame.crop((w - 1, 0, w, h)).resize((pad, h), Image.NEAREST), (x + w, y))
    atlas.paste(frame.crop((0, 0, w, 1)).resize((w, pad), Image.NEAREST), (x, y - pad))
    atlas.paste(frame.crop((0, h - 1, w, h)).resize((w, pad), Image.NEAREST), (x, y + h))
    atlas.paste(frame.crop((0, 0, 1, 1)).resize((pad, pad), Image.NEAREST), (x - pad, y - pad))
    atlas.paste(frame.crop((w - 1, 0, w, 1)).resize((pad, pad), Image.NEAREST), (x + w, y - pad))
    atlas.paste(frame.crop((0, h - 1, 1, h)).resize((pad, pad), Image.NEAREST), (x - pad, y + h))
    atlas.paste(frame.crop((w - 1, h - 1, w, h)).resize((pad, pad), Image.NEAREST), (x + w, y + h))


def pack(frames, canvas, pad=PAD):
    cw, ch = canvas
    cols = rows = 4
    cell_w, cell_h = cw + 2 * pad, ch + 2 * pad
    atlas = Image.new("RGBA", (cols * cell_w, rows * cell_h), (0, 0, 0, 0))
    rects = []
    for i, fr in enumerate(frames):
        col, row = i % cols, i // cols
        x, y = col * cell_w + pad, row * cell_h + pad
        _extrude_paste(atlas, fr.rgba, x, y, pad)
        rects.append([x, y, cw, ch])
    return atlas, rects


def bake(mesh: str, out: Path, canvas_px: int = 256, variant_id: str | None = None) -> dict:
    variant_id = variant_id or f"{mesh}_probe"
    out.mkdir(parents=True, exist_ok=True)
    canvas = (canvas_px, canvas_px)
    verts, faces = MESHES[mesh]()
    frames = render_directions(verts, faces, n=DIRS, canvas=canvas)
    atlas, rects = pack(frames, canvas)
    atlas.save(out / "color_atlas.png")

    tip_len = canvas_px * 0.1
    manifest_frames, expected = [], []
    for i, (fr, rect) in enumerate(zip(frames, rects)):
        yaw = i * (2 * math.pi / DIRS)
        sdv = [round(v, 6) for v in ground_screen_direction(yaw).tolist()]
        ax, ay = round(fr.anchor[0], 3), round(fr.anchor[1], 3)
        manifest_frames.append({
            "direction": i,
            "rect": rect,
            "anchor": [ax, ay],
            "world_yaw_degrees": round(math.degrees(yaw), 6),
            "screen_direction_vector": sdv,
            "sockets": {
                "origin": [ax, ay],
                "direction_tip": [round(ax + sdv[0] * tip_len, 3), round(ay + sdv[1] * tip_len, 3)],
            },
        })
        expected.append({"direction": i, "world_yaw_degrees": round(math.degrees(yaw), 6),
                         "screen_direction_vector": sdv})

    manifest = {
        "manifest_version": "sprite_manifest_bake_v1",
        "camera": {"id": "game_iso_v1", "azimuth_degrees": 45, "camera_elevation_degrees": 30,
                   "projection": "orthographic_pixel_iso_dimetric_2_to_1", "screen_y": "down",
                   "tile_px": [64, 32]},
        "variant_id": variant_id,
        "variant_class": "probe",
        "direction_count": DIRS,
        "frame_canvas": list(canvas),
        "atlases": {"color": {"path": "color_atlas.png", "size": list(atlas.size)}},
        "frames": manifest_frames,
        "expected_facing": expected,
        "world_metrics": {"height_world": 0.01, "footprint_radius_world": 0.5,
                          "metrics_policy": "probe_placeholder"},
        "build": {"generator": "pipeline/tools/bake.py", "mesh": mesh, "renderer": "render3d_software"},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "expected_facing_table.json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake a procedural mesh into an engine-shaped package.")
    ap.add_argument("--mesh", choices=list(MESHES), default="cube")
    ap.add_argument("--variant-id", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--canvas", type=int, default=256)
    args = ap.parse_args()
    variant_id = args.variant_id or f"{args.mesh}_probe"
    out = (args.out or (PIPELINE_ROOT / "output" / variant_id)).resolve()
    manifest = bake(args.mesh, out, args.canvas, variant_id)
    errors = engine_accept(manifest)
    if errors:
        print(f"BAKE FAIL: Gate-1 rejected {variant_id} ({len(errors)} reason(s))")
        for e in errors:
            print("   ", e)
        return 1
    print(f"BAKE OK: {variant_id} -> {out}  (Gate-1 PASS, {len(manifest['frames'])} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
