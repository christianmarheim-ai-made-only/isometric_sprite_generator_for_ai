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
from measure_metrics import compute_world_metrics  # noqa: E402

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


def _pack(images, canvas, mode, pad=PAD):
    cw, ch = canvas
    cols = rows = 4
    cell_w, cell_h = cw + 2 * pad, ch + 2 * pad
    bg = (0, 0, 0, 0) if mode == "RGBA" else 0
    atlas = Image.new(mode, (cols * cell_w, rows * cell_h), bg)
    rects = []
    for i, im in enumerate(images):
        col, row = i % cols, i // cols
        x, y = col * cell_w + pad, row * cell_h + pad
        _extrude_paste(atlas, im, x, y, pad)
        rects.append([x, y, cw, ch])
    return atlas, rects


def pack(frames, canvas, pad=PAD):
    return _pack([fr.rgba for fr in frames], canvas, "RGBA", pad)


def pack_region(frames, canvas, pad=PAD):
    """Pack the per-frame R8 HIT-region maps into a single-channel atlas (NEAREST
    extrusion keeps region ids discrete -- no anti-aliased in-between values)."""
    from PIL import Image as _Image
    return _pack([_Image.fromarray(fr.region, "L") for fr in frames], canvas, "L", pad)


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


def bake_character(out: Path, canvas_px: int = 256, variant_id: str = "humanoid_ref") -> dict:
    """Bake a body-only humanoid: color + R8 HIT-proxy hitmask + measured world_metrics
    -> an engine-shaped CHARACTER package (R4). variant_class=character, so the engine
    requires valid world_metrics (height/footprint > 0, eye <= height)."""
    out.mkdir(parents=True, exist_ok=True)
    canvas = (canvas_px, canvas_px)
    verts, faces, face_region = meshes.humanoid()
    frames = render_directions(verts, faces, n=DIRS, canvas=canvas, face_region=face_region)
    color_atlas, rects = pack(frames, canvas)
    mask_atlas, _ = pack_region(frames, canvas)
    color_atlas.save(out / "color_atlas.png")
    mask_atlas.save(out / "hitmask_atlas.png")

    bmin = tuple(float(v) for v in verts.min(axis=0))
    bmax = tuple(float(v) for v in verts.max(axis=0))
    metrics = compute_world_metrics(bmin, bmax, eye_z=round(bmax[2] * 0.9, 4))

    tip_len = canvas_px * 0.1
    manifest_frames, expected = [], []
    for i, (fr, rect) in enumerate(zip(frames, rects)):
        yaw = i * (2 * math.pi / DIRS)
        sdv = [round(v, 6) for v in ground_screen_direction(yaw).tolist()]
        ax, ay = round(fr.anchor[0], 3), round(fr.anchor[1], 3)
        manifest_frames.append({
            "direction": i, "rect": rect, "mask_rect": rect, "anchor": [ax, ay],
            "world_yaw_degrees": round(math.degrees(yaw), 6), "screen_direction_vector": sdv,
            "sockets": {"origin": [ax, ay],
                        "direction_tip": [round(ax + sdv[0] * tip_len, 3), round(ay + sdv[1] * tip_len, 3)]},
        })
        expected.append({"direction": i, "world_yaw_degrees": round(math.degrees(yaw), 6),
                         "screen_direction_vector": sdv})

    manifest = {
        "manifest_version": "sprite_manifest_bake_v1",
        "camera": {"id": "game_iso_v1", "azimuth_degrees": 45, "camera_elevation_degrees": 30,
                   "projection": "orthographic_pixel_iso_dimetric_2_to_1", "screen_y": "down",
                   "tile_px": [64, 32]},
        "variant_id": variant_id,
        "variant_class": "character",
        "direction_count": DIRS,
        "frame_canvas": list(canvas),
        "atlases": {
            "color": {"path": "color_atlas.png", "size": list(color_atlas.size)},
            "hitmask": {"path": "hitmask_atlas.png", "size": list(mask_atlas.size),
                        "format": "PNG_R8_UINT_linear_no_antialias", "sampling": "nearest",
                        "palette": {"none": 0, "head": 1, "torso": 2, "arms": 3, "legs": 4}},
        },
        "frames": manifest_frames,
        "expected_facing": expected,
        "world_metrics": metrics,
        "build": {"generator": "pipeline/tools/bake.py", "mesh": "humanoid",
                  "renderer": "render3d_software"},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "expected_facing_table.json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake a procedural mesh into an engine-shaped package.")
    ap.add_argument("--mesh", choices=list(MESHES) + ["humanoid"], default="cube")
    ap.add_argument("--variant-id", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--canvas", type=int, default=256)
    args = ap.parse_args()
    if args.mesh == "humanoid":
        variant_id = args.variant_id or "humanoid_ref"
        out = (args.out or (PIPELINE_ROOT / "output" / variant_id)).resolve()
        manifest = bake_character(out, args.canvas, variant_id)
    else:
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
