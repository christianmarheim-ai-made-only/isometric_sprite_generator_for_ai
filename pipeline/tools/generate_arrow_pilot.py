#!/usr/bin/env python3
"""Generate the M1/M2 direction-only arrow pilot.

This intentionally avoids Blender and real character content. It creates a deterministic
16-direction atlas using the game_iso_v1 ground-plane projection convention so the
engine can verify yaw-bin, atlas, anchor, manifest, mask, and validation plumbing.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Allow running the script directly without installing a package.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from contract_hash import compute_contract_hash, compute_individual_hashes  # noqa: E402

CANVAS = (128, 128)
ANCHOR = (64.0, 112.0)
DRAW_CENTER = (64.0, 72.0)
PAD = 4
DIRS = 16
REGION_TORSO = 2
# direction_tip = origin + screen_direction_vector * this (frame px); 15 keeps the
# tip in-bounds for all 16 directions at anchor [64,112] (down-most: 112+15=127<128).
DIRECTION_TIP_LEN = 15.0


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def world_to_screen_vector(yaw_rad: float) -> tuple[float, float]:
    """Project a unit ground-plane world vector into screen px convention.

    screen_x = (world_x - world_y) * 32
    screen_y = (world_x + world_y) * 16
    +Y is down.
    """
    wx = math.cos(yaw_rad)
    wy = math.sin(yaw_rad)
    sx = (wx - wy) * 32.0
    sy = (wx + wy) * 16.0
    length = math.hypot(sx, sy)
    if length == 0:
        return (0.0, 0.0)
    return (sx / length, sy / length)


def screen_label(dx: float, dy: float) -> str:
    # A simple human-facing label for debug tables. The diagnostic check is numeric.
    eps = 0.12
    if abs(dx) < eps and dy > 0:
        return "down"
    if abs(dx) < eps and dy < 0:
        return "up"
    if dx > 0 and abs(dy) < eps:
        return "right"
    if dx < 0 and abs(dy) < eps:
        return "left"
    if dx > 0 and dy > 0:
        return "down_right"
    if dx < 0 and dy > 0:
        return "down_left"
    if dx > 0 and dy < 0:
        return "up_right"
    if dx < 0 and dy < 0:
        return "up_left"
    return "center"


def polygon_arrow(dx: float, dy: float) -> list[tuple[float, float]]:
    px, py = -dy, dx  # perpendicular
    cx, cy = DRAW_CENTER
    tail_len = 30.0
    shaft_end_len = 10.0
    tip_len = 36.0
    shaft_half = 5.5
    head_half = 15.0

    tail = (cx - dx * tail_len, cy - dy * tail_len)
    shaft_end = (cx + dx * shaft_end_len, cy + dy * shaft_end_len)
    tip = (cx + dx * tip_len, cy + dy * tip_len)

    return [
        (tail[0] + px * shaft_half, tail[1] + py * shaft_half),
        (shaft_end[0] + px * shaft_half, shaft_end[1] + py * shaft_half),
        (shaft_end[0] + px * head_half, shaft_end[1] + py * head_half),
        tip,
        (shaft_end[0] - px * head_half, shaft_end[1] - py * head_half),
        (shaft_end[0] - px * shaft_half, shaft_end[1] - py * shaft_half),
        (tail[0] - px * shaft_half, tail[1] - py * shaft_half),
    ]


def rounded(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    return [(int(round(x)), int(round(y))) for x, y in points]


def make_frame(direction: int) -> tuple[Image.Image, Image.Image, dict[str, Any]]:
    yaw = direction * (2 * math.pi / DIRS)
    dx, dy = world_to_screen_vector(yaw)
    points = rounded(polygon_arrow(dx, dy))

    color = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    mask = Image.new("L", CANVAS, 0)
    d = ImageDraw.Draw(color)
    md = ImageDraw.Draw(mask)

    # Fill + outline. Colors are debug-only and intentionally high contrast.
    d.polygon(points, fill=(72, 170, 255, 255), outline=(8, 22, 36, 255))
    md.polygon(points, fill=REGION_TORSO)

    box = region_box(mask, REGION_TORSO)
    if box is None:
        raise RuntimeError(f"Generated empty arrow mask for direction {direction}")

    meta = {
        "direction": direction,
        "world_yaw_degrees": round(math.degrees(yaw), 6),
        "screen_direction_vector": [round(dx, 6), round(dy, 6)],
        "screen_label": screen_label(dx, dy),
        "diagnostic": diagnostic_label(direction, dx, dy),
        "boxes": {"torso": box},
    }
    return color, mask, meta


def diagnostic_label(direction: int, dx: float, dy: float) -> str:
    if direction == 2:
        return "dir02_should_point_down"
    if direction == 10:
        return "dir10_should_point_up"
    if direction == 0:
        return "dir00_world_+X_East"
    return ""


def region_box(mask: Image.Image, value: int) -> list[int] | None:
    pixels = mask.load()
    w, h = mask.size
    min_x, min_y = w, h
    max_x, max_y = -1, -1
    for y in range(h):
        for x in range(w):
            if pixels[x, y] == value:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < 0:
        return None
    return [min_x, min_y, max_x - min_x + 1, max_y - min_y + 1]


def extrude_frame(atlas: Image.Image, frame: Image.Image, rect_x: int, rect_y: int, pad: int) -> None:
    """Paste frame and extrude its frame edges into the pad area.

    Edge extrusion replicates the 1px border into the gutter, so every resize
    uses NEAREST. For the R8 hitmask this keeps region IDs discrete -- no
    interpolated in-between values -- making mask discreteness structural rather
    than an accident of today's 1px-uniform strips. The color atlas uses NEAREST
    too: for a 1px-wide source strip it is identical to any filter and it states
    the replication intent.
    """
    w, h = frame.size
    atlas.paste(frame, (rect_x, rect_y))

    # Sides.
    left_col = frame.crop((0, 0, 1, h)).resize((pad, h), Image.NEAREST)
    right_col = frame.crop((w - 1, 0, w, h)).resize((pad, h), Image.NEAREST)
    top_row = frame.crop((0, 0, w, 1)).resize((w, pad), Image.NEAREST)
    bottom_row = frame.crop((0, h - 1, w, h)).resize((w, pad), Image.NEAREST)
    atlas.paste(left_col, (rect_x - pad, rect_y))
    atlas.paste(right_col, (rect_x + w, rect_y))
    atlas.paste(top_row, (rect_x, rect_y - pad))
    atlas.paste(bottom_row, (rect_x, rect_y + h))

    # Corners.
    atlas.paste(frame.crop((0, 0, 1, 1)).resize((pad, pad), Image.NEAREST), (rect_x - pad, rect_y - pad))
    atlas.paste(frame.crop((w - 1, 0, w, 1)).resize((pad, pad), Image.NEAREST), (rect_x + w, rect_y - pad))
    atlas.paste(frame.crop((0, h - 1, 1, h)).resize((pad, pad), Image.NEAREST), (rect_x - pad, rect_y + h))
    atlas.paste(frame.crop((w - 1, h - 1, w, h)).resize((pad, pad), Image.NEAREST), (rect_x + w, rect_y + h))


def make_atlases(frames: list[Image.Image], masks: list[Image.Image]) -> tuple[Image.Image, Image.Image, list[list[int]]]:
    cols, rows = 4, 4
    cell_w = CANVAS[0] + 2 * PAD
    cell_h = CANVAS[1] + 2 * PAD
    atlas_size = (cols * cell_w, rows * cell_h)
    color_atlas = Image.new("RGBA", atlas_size, (0, 0, 0, 0))
    mask_atlas = Image.new("L", atlas_size, 0)
    rects: list[list[int]] = []
    for i, (frame, mask) in enumerate(zip(frames, masks, strict=True)):
        col = i % cols
        row = i // cols
        x = col * cell_w + PAD
        y = row * cell_h + PAD
        extrude_frame(color_atlas, frame, x, y, PAD)
        extrude_frame(mask_atlas, mask, x, y, PAD)
        rects.append([x, y, CANVAS[0], CANVAS[1]])
    return color_atlas, mask_atlas, rects


def make_debug_sheet(frames: list[Image.Image], expected: list[dict[str, Any]]) -> Image.Image:
    cols, rows = 4, 4
    cell_w, cell_h = 192, 176
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (240, 242, 245, 255))
    font = ImageFont.load_default()
    draw = ImageDraw.Draw(sheet)
    for i, frame in enumerate(frames):
        col = i % cols
        row = i // cols
        x0 = col * cell_w
        y0 = row * cell_h
        sheet.paste(frame, (x0 + 32, y0 + 28), frame)
        # Anchor cross in red overlay.
        ax = x0 + 32 + int(ANCHOR[0])
        ay = y0 + 28 + int(ANCHOR[1])
        draw.line((ax - 5, ay, ax + 5, ay), fill=(220, 0, 0, 255), width=1)
        draw.line((ax, ay - 5, ax, ay + 5), fill=(220, 0, 0, 255), width=1)
        draw.text((x0 + 8, y0 + 6), f"dir {i:02d} yaw {expected[i]['world_yaw_degrees']:.1f}°", fill=(0, 0, 0, 255), font=font)
        draw.text((x0 + 8, y0 + 146), expected[i]["screen_label"], fill=(0, 0, 0, 255), font=font)
        if expected[i]["diagnostic"]:
            draw.text((x0 + 8, y0 + 160), expected[i]["diagnostic"], fill=(160, 0, 0, 255), font=font)
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the M1/M2 arrow direction pilot assets.")
    parser.add_argument("--pipeline-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--clean", action="store_true", help="Remove output directory before generation.")
    args = parser.parse_args()

    pipeline_root = args.pipeline_root.resolve()
    lockfiles_dir = pipeline_root / "lockfiles"
    output_dir = (args.output or (pipeline_root / "output" / "arrow_pilot")).resolve()
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "frames" / "color").mkdir(parents=True, exist_ok=True)
    (output_dir / "frames" / "hitmask").mkdir(parents=True, exist_ok=True)

    contract_hash = compute_contract_hash(lockfiles_dir)
    individual_hashes = compute_individual_hashes(lockfiles_dir)
    states_lock = load_json(lockfiles_dir / "sprite_states.lock.json")
    variants_lock = load_json(lockfiles_dir / "sprite_variants.lock.json")

    frames: list[Image.Image] = []
    masks: list[Image.Image] = []
    expected: list[dict[str, Any]] = []
    for direction in range(DIRS):
        frame, mask, meta = make_frame(direction)
        frame.save(output_dir / "frames" / "color" / f"arrow_idle_dir{direction:02d}_frame00.png")
        mask.save(output_dir / "frames" / "hitmask" / f"arrow_idle_dir{direction:02d}_frame00.png")
        frames.append(frame)
        masks.append(mask)
        expected.append(meta)

    color_atlas, mask_atlas, rects = make_atlases(frames, masks)
    color_atlas.save(output_dir / "color_atlas.png")
    mask_atlas.save(output_dir / "hitmask_atlas.png")
    make_debug_sheet(frames, expected).save(output_dir / "debug_sheet.png")
    write_json(output_dir / "expected_facing_table.json", expected)

    manifest_frames: list[dict[str, Any]] = []
    for direction, rect in enumerate(rects):
        meta = expected[direction]
        manifest_frames.append({
            "state": "idle",
            "direction": direction,
            "frame_index": 0,
            "world_yaw_degrees": meta["world_yaw_degrees"],
            "screen_direction_vector": meta["screen_direction_vector"],
            "screen_label": meta["screen_label"],
            "rect": rect,
            "mask_rect": rect,
            "anchor": [ANCHOR[0], ANCHOR[1]],
            "sockets": {
                "origin": [ANCHOR[0], ANCHOR[1]],
                "direction_tip": [
                    round(ANCHOR[0] + meta["screen_direction_vector"][0] * DIRECTION_TIP_LEN, 3),
                    round(ANCHOR[1] + meta["screen_direction_vector"][1] * DIRECTION_TIP_LEN, 3),
                ]
            },
            "boxes": meta["boxes"],
            "debug_source_frame": f"frames/color/arrow_idle_dir{direction:02d}_frame00.png"
        })

    manifest = {
        "manifest_version": "sprite_manifest_debug_subset_v1",
        "camera": {
            "id": "game_iso_v1",
            "azimuth_degrees": 45,
            "camera_elevation_degrees": 30,
            "camera_elevation_definition": "angle of the orthographic camera ray above the ground plane; not the screen tile-edge angle",
            "camera_geometry_note": "2:1 ground tile => sin(camera_elevation)=0.5 => 30 deg; arctan(0.5)~=26.565 is the screen tile-edge angle, not the camera elevation. Engine applies on-screen height = height_world * 24 (render.rs::sprite_size).",
            "projection": "orthographic_pixel_iso_dimetric_2_to_1",
            "screen_y": "down",
            "tile_px": [64, 32]
        },
        "contract_hash": contract_hash,
        "state_contract_version": states_lock["state_contract_version"],
        "variant_id": "pilot_arrow",
        "variant_class": variants_lock["variants"]["pilot_arrow"]["variant_class"],
        "frame_canvas": list(CANVAS),
        "direction_count": DIRS,
        "surface_policy": {
            "mask_semantics": "debug_single_foreground_region; see ADR-0015",
            "selection": "any_nonzero_region_selects_owner",
            "equipment_surface_policy": "not_exercised_in_m1_m2_arrow_pilot"
        },
        "animations": {
            "idle": {
                "playback": "loop",
                "directions": DIRS,
                "frames": 1,
                "fps": 1,
                "markers": []
            }
        },
        "atlases": {
            "color": {
                "path": "color_atlas.png",
                "size": list(color_atlas.size),
                "format": "PNG_RGBA8_sRGB_straight_alpha",
                "sampling": "linear",
                "padding_px": PAD,
                "extrusion_px": PAD
            },
            "hitmask": {
                "path": "hitmask_atlas.png",
                "size": list(mask_atlas.size),
                "format": "PNG_R8_UINT_linear_no_antialias",
                "sampling": "nearest",
                "padding_px": PAD,
                "extrusion_px": PAD,
                "palette": {
                    "none": 0,
                    "torso": REGION_TORSO
                }
            }
        },
        "frames": manifest_frames,
        "expected_facing": expected,
        "world_metrics": {
            "height_world": 0.1,
            "footprint_radius_world": 0.25,
            "metrics_policy": "debug_placeholder_only_not_gameplay"
        },
        "build": {
            "generator": "pipeline/tools/generate_arrow_pilot.py",
            "generator_mode": "deterministic_python_no_blender",
            "lockfile_hashes": individual_hashes,
            "assumptions": [
                "Arrow pilot verifies direction/atlas/manifest plumbing only.",
                "Blender camera and real rig-derived proxy rendering are deferred.",
                "Weapons/equipment/arms are deferred to M2A/M3 ADR review."
            ]
        }
    }
    write_json(output_dir / "manifest.json", manifest)
    print(f"Generated arrow pilot at {output_dir}")
    print(f"contract_hash={contract_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
