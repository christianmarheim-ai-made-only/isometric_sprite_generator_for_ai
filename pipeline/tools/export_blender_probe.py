#!/usr/bin/env python3
"""Export the Blender-authored arrow probe (P2) -- RUNS INSIDE BLENDER.

    blender --background source_assets/arrow_probe/arrow_probe.blend \
            --python pipeline/tools/export_blender_probe.py

Requires Blender's `bpy` (and Pillow available to Blender's Python). It is NOT
exercised by build.py and cannot render in plain CPython -- only its packing and
manifest path (reused from generate_arrow_pilot) are tested headless. It renders
16 game_iso_v1 directions of the probe, packs color + R8 hitmask atlases, writes
a probe manifest, and validates it with the existing validator.

.blend requirements (docs/naming_conventions.md): VIS_arrow (visual mesh),
HIT_torso (hit proxy), SOCKET_origin (ground anchor). Forward +X, up +Z, 1u = 1m.

Prerequisite: sprite_variants.lock.json must contain an "arrow_probe" entry
(variant_class "probe", supported_states ["idle"], direction_count 16,
frame_canvas [128, 128]). Adding a variant does NOT change contract_hash (the
hash covers only sprite_contract.lock.json). The exporter validates at the end
and reports a clear error if the entry is missing.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Tested, Blender-free helpers reused verbatim.
from generate_arrow_pilot import (  # noqa: E402
    CANVAS, ANCHOR, PAD, DIRS, REGION_TORSO,
    make_atlases, write_json, region_box,
    world_to_screen_vector, screen_label, diagnostic_label,
)
from contract_hash import compute_contract_hash, compute_individual_hashes  # noqa: E402
from validate_debug_subset import validate_debug_subset  # noqa: E402

VARIANT_ID = "arrow_probe"
OUTPUT_DIR = PIPELINE_ROOT / "output" / "arrow_probe_blender"

# game_iso_v1 camera (LOCKED): orthographic, azimuth 45 deg, elevation 30 deg.
# sin(30 deg) = 0.5 is the 2:1 ground foreshortening that matches
# screen_y=(wx+wy)*16 vs screen_x=(wx-wy)*32. Do not "correct" these.
AZIMUTH_DEG = 45.0
ELEVATION_DEG = 30.0


def _require_bpy():
    try:
        import bpy  # type: ignore
        import mathutils  # type: ignore
        return bpy, mathutils
    except ImportError as exc:  # pragma: no cover - only inside Blender
        raise SystemExit(
            "export_blender_probe.py must run inside Blender:\n"
            "  blender --background <arrow_probe.blend> --python "
            "pipeline/tools/export_blender_probe.py\n"
            f"({exc})")


def setup_scene(bpy, mathutils):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"  # flat + version-stable; human may switch to EEVEE
    scene.render.resolution_x = CANVAS[0]
    scene.render.resolution_y = CANVAS[1]
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    cam_data = bpy.data.cameras.new("game_iso_v1")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.5  # TUNE in .blend so subject + anchor frame correctly
    # Shift framing so SOCKET_origin (ground center) lands on ANCHOR=[64,112]
    # (near the bottom) rather than the frame centre: (112-64)/128 = 0.375.
    cam_data.shift_y = (ANCHOR[1] - CANVAS[1] / 2.0) / CANVAS[1]  # 0.375; verify vs debug sheet
    cam = bpy.data.objects.new("game_iso_v1", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    az, el = math.radians(AZIMUTH_DEG), math.radians(ELEVATION_DEG)
    dist = 10.0
    cam.location = (dist * math.cos(el) * math.cos(az),
                    dist * math.cos(el) * math.sin(az),
                    dist * math.sin(el))
    cam.rotation_euler = (-mathutils.Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    return scene, cam


def _render_to_pil(bpy, hide_visual: bool, hide_hit: bool):
    from PIL import Image
    vis = bpy.data.objects.get("VIS_arrow")
    hit = bpy.data.objects.get("HIT_torso")
    if vis:
        vis.hide_render = hide_visual
    if hit:
        hit.hide_render = hide_hit
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "f.png"
        bpy.context.scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        return Image.open(out).convert("RGBA").copy()


def render_direction(bpy, direction: int):
    """Return (color RGBA, mask L) 128x128 PIL frames for one direction."""
    from PIL import Image
    yaw = direction * (2 * math.pi / DIRS)
    for name in ("VIS_arrow", "HIT_torso"):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.rotation_euler = (0.0, 0.0, yaw)

    bpy.context.scene.render.filter_size = 1.5            # color: anti-aliased
    color = _render_to_pil(bpy, hide_visual=False, hide_hit=True)

    bpy.context.scene.render.filter_size = 0.01           # mask: binary coverage, no AA
    hit_rgba = _render_to_pil(bpy, hide_visual=True, hide_hit=False)
    mask = Image.new("L", CANVAS, 0)
    mpx, hpx = mask.load(), hit_rgba.load()
    for y in range(CANVAS[1]):
        for x in range(CANVAS[0]):
            if hpx[x, y][3] >= 128:
                mpx[x, y] = REGION_TORSO
    return color, mask


def build_manifest(rects, expected, color_size, mask_size) -> dict:
    states = json.loads((PIPELINE_ROOT / "lockfiles" / "sprite_states.lock.json").read_text(encoding="utf-8"))
    lock = PIPELINE_ROOT / "lockfiles"
    frames = []
    for d, rect in enumerate(rects):
        meta = expected[d]
        frames.append({
            "state": "idle", "direction": d, "frame_index": 0,
            "world_yaw_degrees": meta["world_yaw_degrees"],
            "screen_direction_vector": meta["screen_direction_vector"],
            "screen_label": meta["screen_label"],
            "rect": rect, "mask_rect": rect,
            "anchor": [ANCHOR[0], ANCHOR[1]],
            "sockets": {"origin": [ANCHOR[0], ANCHOR[1]]},
            "boxes": meta["boxes"],
        })
    return {
        "manifest_version": "sprite_manifest_debug_subset_v1",
        "contract_hash": compute_contract_hash(lock),
        "state_contract_version": states["state_contract_version"],
        "variant_id": VARIANT_ID,
        "variant_class": "probe",
        "frame_canvas": list(CANVAS),
        "direction_count": DIRS,
        "surface_policy": {
            "mask_semantics": "debug_single_foreground_region; see ADR-0015",
            "selection": "any_nonzero_region_selects_owner",
            "equipment_surface_policy": "not_exercised_in_arrow_probe",
        },
        "animations": {"idle": {"playback": "loop", "directions": DIRS, "frames": 1, "fps": 1, "markers": []}},
        "atlases": {
            "color": {"path": "color_atlas.png", "size": list(color_size),
                      "format": "PNG_RGBA8_sRGB_straight_alpha", "sampling": "linear",
                      "padding_px": PAD, "extrusion_px": PAD},
            "hitmask": {"path": "hitmask_atlas.png", "size": list(mask_size),
                        "format": "PNG_R8_UINT_linear_no_antialias", "sampling": "nearest",
                        "padding_px": PAD, "extrusion_px": PAD,
                        "palette": {"none": 0, "torso": REGION_TORSO}},
        },
        "frames": frames,
        "expected_facing": expected,
        "world_metrics": {"height_world": 0.1, "footprint_radius_world": 0.25,
                          "metrics_policy": "debug_placeholder_only_not_gameplay"},
        "build": {"generator": "pipeline/tools/export_blender_probe.py",
                  "generator_mode": "blender_render", "variant_class": "probe",
                  "lockfile_hashes": compute_individual_hashes(lock)},
    }


def main() -> int:
    bpy, mathutils = _require_bpy()
    setup_scene(bpy, mathutils)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    frames, masks, expected = [], [], []
    for d in range(DIRS):
        color, mask = render_direction(bpy, d)
        frames.append(color)
        masks.append(mask)
        dx, dy = world_to_screen_vector(d * (2 * math.pi / DIRS))
        box = region_box(mask, REGION_TORSO)
        if box is None:
            raise SystemExit(f"dir {d}: empty hit mask -- check HIT_torso / camera framing")
        expected.append({
            "direction": d,
            "world_yaw_degrees": round(math.degrees(d * (2 * math.pi / DIRS)), 6),
            "screen_direction_vector": [round(dx, 6), round(dy, 6)],
            "screen_label": screen_label(dx, dy),
            "diagnostic": diagnostic_label(d, dx, dy),
            "boxes": {"torso": box},
        })

    color_atlas, mask_atlas, rects = make_atlases(frames, masks)
    color_atlas.save(OUTPUT_DIR / "color_atlas.png")
    mask_atlas.save(OUTPUT_DIR / "hitmask_atlas.png")
    write_json(OUTPUT_DIR / "manifest.json", build_manifest(rects, expected, color_atlas.size, mask_atlas.size))

    report = validate_debug_subset(OUTPUT_DIR / "manifest.json", PIPELINE_ROOT)
    if not report["ok"]:
        print("VALIDATION FAILED:")
        for e in report["errors"]:
            print("  ", e)
        return 1
    print(f"Blender arrow probe exported + validated OK at {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
