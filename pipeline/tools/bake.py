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

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import meshes  # noqa: E402
from render3d import render_directions, ground_screen_direction, compute_fit  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402
from measure_metrics import compute_world_metrics  # noqa: E402
from contract_hash import compute_contract_hash  # noqa: E402

PAD = 4
DIRS = 16
MESHES = {"cube": meshes.cube, "pole": meshes.pole, "arrow": meshes.arrow_wedge}
LOCKFILES = PIPELINE_ROOT / "lockfiles"


def _contract_fields() -> dict:
    """contract_hash (sprite_contract.lock.json) + state_contract_version, so the engine's
    documented fail-closed asserts (docs/BEVY_LOADER_INTEGRATION.md) apply to bake packages too."""
    states = json.loads((LOCKFILES / "sprite_states.lock.json").read_text(encoding="utf-8"))
    return {"contract_hash": compute_contract_hash(LOCKFILES),
            "state_contract_version": states["state_contract_version"]}


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


def shelf_place(sizes, max_w=2048, pad=PAD):
    """Shelf/row bin-pack variable-size TIGHT frames -> (placements, atlas_size)."""
    x = y = pad
    row_h = 0
    width = pad
    placements = []
    for (w, h) in sizes:
        if x + w + pad > max_w and x > pad:
            x = pad
            y += row_h + pad
            row_h = 0
        placements.append((x, y))
        x += w + pad
        row_h = max(row_h, h)
        width = max(width, x)
    return placements, (width + pad, y + row_h + pad)


def place_into(images, placements, atlas_size, mode, pad=PAD):
    """Place images at given placements into one atlas (color + mask share placements ->
    mask_rect == rect)."""
    atlas = Image.new(mode, atlas_size, (0, 0, 0, 0) if mode == "RGBA" else 0)
    rects = []
    for im, (x, y) in zip(images, placements):
        _extrude_paste(atlas, im, x, y, pad)
        rects.append([x, y, im.size[0], im.size[1]])
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
    manifest.update(_contract_fields())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "expected_facing_table.json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _bake_mesh_character(verts, faces, face_region, out: Path, canvas_px: int, variant_id: str,
                         mesh_name: str) -> dict:
    """Shared core: render a `(verts, faces, face_region)` mesh into an engine-shaped CHARACTER
    package (color + R8 HIT-proxy hitmask + measured ground-footprint metrics). Used by
    `bake_character` (procedural humanoid) and `bake_mesh` (a loaded OBJ). variant_class=character,
    so the engine requires valid world_metrics (height/footprint > 0, eye <= height)."""
    out.mkdir(parents=True, exist_ok=True)
    canvas = (canvas_px, canvas_px)
    verts = np.asarray(verts, dtype=float)
    frames = render_directions(verts, faces, n=DIRS, canvas=canvas, face_region=face_region)
    color_atlas, rects = pack(frames, canvas)
    mask_atlas, _ = pack_region(frames, canvas)
    color_atlas.save(out / "color_atlas.png")
    mask_atlas.save(out / "hitmask_atlas.png")

    height = float(verts[:, 2].max())
    # footprint = GROUND-CONTACT horizontal extent (legs/feet), NOT the widest above-ground
    # cross-section (arms): the engine consumes footprint_radius_world as the collision/LOS
    # radius, so an above-ground appendage must not inflate it (docs/world_metrics_policy.md).
    z_floor = float(verts[:, 2].min())
    ground = verts[verts[:, 2] <= z_floor + 0.15 * height]
    foot_r = float(np.max(np.abs(ground[:, :2])))
    metrics = compute_world_metrics((-foot_r, -foot_r, 0.0), (foot_r, foot_r, height),
                                    eye_z=round(height * 0.9, 4))

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
        "build": {"generator": "pipeline/tools/bake.py", "mesh": mesh_name,
                  "renderer": "render3d_software"},
    }
    manifest.update(_contract_fields())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "expected_facing_table.json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def bake_character(out: Path, canvas_px: int = 256, variant_id: str = "humanoid_ref") -> dict:
    """Bake the procedural body-only humanoid -> engine-shaped CHARACTER package (R4)."""
    verts, faces, face_region = meshes.humanoid()
    return _bake_mesh_character(verts, faces, face_region, out, canvas_px, variant_id, "humanoid")


def bake_mesh(mesh_path, out: Path, canvas_px: int = 256, variant_id: str | None = None,
              up: str = "z") -> dict:
    """Bake a REAL external mesh (OBJ; HIT regions by material/group name) -> CHARACTER package (R8).
    The mesh is normalized to the contract (foot at origin, +Z up; up='y' rotates a Y-up file)."""
    from mesh_io import load_obj
    verts, faces, face_region = load_obj(mesh_path, up=up)
    variant_id = variant_id or Path(mesh_path).stem
    return _bake_mesh_character(verts, faces, face_region, out, canvas_px, variant_id, Path(mesh_path).name)


def bake_character_anim(out: Path, canvas_px: int = 256, variant_id: str = "humanoid_anim") -> dict:
    """Bake a MULTI-STATE, TIGHT-CROPPED humanoid (R5A + R5B) per multistate_sprite_contract.md:
    a top-level `animations` map + per-frame `(state, direction, frame_index)` + `default_state`,
    with tight `rect` + `trim` + `logical_frame_canvas` and a logical-coords `anchor`. One render
    scale across every frame (no resize); the root anchor is constant (root-XY stable)."""
    out.mkdir(parents=True, exist_ok=True)
    canvas = (canvas_px, canvas_px)
    states = json.loads((PIPELINE_ROOT / "lockfiles" / "sprite_states.lock.json").read_text(encoding="utf-8"))["states"]

    swing, attack = 0.35, 1.1
    posed = {}
    for state, spec in states.items():
        nf = spec["frames"]
        for fi in range(nf):
            if state == "walk":
                ls = swing * math.sin(2 * math.pi * fi / nf)
                posed[(state, fi)] = meshes.humanoid(leg_swing=ls, arm_swing=ls)
            elif state == "attack":
                a = attack * (fi / (nf - 1) if nf > 1 else 1.0)  # ramp arms forward, hold terminal
                posed[(state, fi)] = meshes.humanoid(leg_swing=0.0, arm_swing=a)
            else:  # idle / rest pose
                posed[(state, fi)] = meshes.humanoid()
    rest_verts = meshes.humanoid()[0]
    fit = compute_fit([v for (v, _, _) in posed.values()], n=DIRS, canvas=canvas)

    color_imgs, region_imgs, fmeta = [], [], []
    for (state, fi), (verts, faces, region) in sorted(posed.items()):
        frames = render_directions(verts, faces, n=DIRS, canvas=canvas, face_region=region, fit=fit)
        for d, fr in enumerate(frames):
            bx, by, bw, bh = fr.bbox
            color_imgs.append(fr.rgba.crop((bx, by, bx + bw, by + bh)))
            region_imgs.append(Image.fromarray(fr.region[by:by + bh, bx:bx + bw], "L"))
            fmeta.append((state, d, fi, [bx, by], (round(fr.anchor[0], 3), round(fr.anchor[1], 3))))

    placements, atlas_size = shelf_place([im.size for im in color_imgs])
    color_atlas, rects = place_into(color_imgs, placements, atlas_size, "RGBA")
    mask_atlas, _ = place_into(region_imgs, placements, atlas_size, "L")
    color_atlas.save(out / "color_atlas.png")
    mask_atlas.save(out / "hitmask_atlas.png")

    height = float(rest_verts[:, 2].max())
    z_floor = float(rest_verts[:, 2].min())
    ground = rest_verts[rest_verts[:, 2] <= z_floor + 0.15 * height]
    foot_r = float(np.max(np.abs(ground[:, :2])))
    metrics = compute_world_metrics((-foot_r, -foot_r, 0.0), (foot_r, foot_r, height),
                                    eye_z=round(height * 0.9, 4))

    tip_len = canvas_px * 0.1
    manifest_frames, expected = [], []
    for (state, d, fi, trim, (ax, ay)), rect in zip(fmeta, rects):
        yaw = d * (2 * math.pi / DIRS)
        sdv = [round(v, 6) for v in ground_screen_direction(yaw).tolist()]
        manifest_frames.append({
            "state": state, "direction": d, "frame_index": fi,
            "rect": rect, "mask_rect": rect, "trim": trim, "logical_frame_canvas": list(canvas),
            "anchor": [ax, ay], "world_yaw_degrees": round(math.degrees(yaw), 6),
            "screen_direction_vector": sdv,
            "sockets": {"origin": [ax, ay],
                        "direction_tip": [round(ax + sdv[0] * tip_len, 3), round(ay + sdv[1] * tip_len, 3)]},
        })
        if state == "idle" and fi == 0:
            expected.append({"direction": d, "world_yaw_degrees": round(math.degrees(yaw), 6),
                             "screen_direction_vector": sdv})

    animations = {s: {"directions": DIRS, "fps": spec["fps"], "frames": spec["frames"],
                      "playback": spec["playback"]} for s, spec in states.items()}
    manifest = {
        "manifest_version": "sprite_manifest_multistate_v1",
        "camera": {"id": "game_iso_v1", "azimuth_degrees": 45, "camera_elevation_degrees": 30,
                   "projection": "orthographic_pixel_iso_dimetric_2_to_1", "screen_y": "down",
                   "tile_px": [64, 32]},
        "variant_id": variant_id,
        "variant_class": "character",
        "direction_count": DIRS,
        "frame_canvas": list(canvas),
        "logical_frame_canvas": list(canvas),
        "default_state": "idle",
        "animations": animations,
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
                  "renderer": "render3d_software", "states": sorted(states)},
    }
    manifest.update(_contract_fields())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "expected_facing_table.json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake a procedural mesh into an engine-shaped package.")
    ap.add_argument("--mesh", choices=list(MESHES) + ["humanoid", "humanoid_anim"], default="cube")
    ap.add_argument("--mesh-file", default=None, help="bake a real OBJ mesh (HIT regions by material name)")
    ap.add_argument("--up", default="z", choices=["z", "y"], help="up axis of --mesh-file (y rotates to +Z)")
    ap.add_argument("--variant-id", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--canvas", type=int, default=256)
    args = ap.parse_args()
    if args.mesh_file:
        variant_id = args.variant_id or Path(args.mesh_file).stem
        out = (args.out or (PIPELINE_ROOT / "output" / variant_id)).resolve()
        manifest = bake_mesh(args.mesh_file, out, args.canvas, variant_id, args.up)
    elif args.mesh == "humanoid":
        variant_id = args.variant_id or "humanoid_ref"
        out = (args.out or (PIPELINE_ROOT / "output" / variant_id)).resolve()
        manifest = bake_character(out, args.canvas, variant_id)
    elif args.mesh == "humanoid_anim":
        variant_id = args.variant_id or "humanoid_anim"
        out = (args.out or (PIPELINE_ROOT / "output" / variant_id)).resolve()
        manifest = bake_character_anim(out, args.canvas, variant_id)
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
