#!/usr/bin/env python3
"""R7: drive the Blender production renderer and assemble an engine-shaped CHARACTER
package, then prove render3d <-> Blender camera parity.

Blender (blender_render.py) renders the humanoid through the EXACT game_iso_v1 camera
(color + flat region passes); this packs the atlases, maps the region pass -> R8 ids,
measures metrics, emits an engine-loadable manifest, and checks Gate-1 + camera parity.

Run: python pipeline/tools/blender_bake.py [--out DIR] [--blender PATH]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import meshes  # noqa: E402
from render3d import ground_screen_direction  # noqa: E402
from measure_metrics import compute_world_metrics  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402
from bake import _pack, _contract_fields  # noqa: E402  (reuse the atlas packer + contract fields)

CANVAS, DIRS = 256, 16


def _srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def find_blender(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get("BLENDER")
    if env and Path(env).exists():
        return env
    onpath = shutil.which("blender")
    if onpath:
        return onpath
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "blender-portable"
    if base.exists():
        for exe in base.rglob("blender.exe"):
            return str(exe)
    return None


def _run_blender(blender: str, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [blender, "--background", "--python", str(SCRIPT_DIR / "blender_render.py"),
         "--", str(out), str(SCRIPT_DIR)],
        capture_output=True, text=True)
    meta = out / "blender_meta.json"
    if proc.returncode != 0 or not meta.exists():
        raise RuntimeError(f"Blender render failed (exit {proc.returncode}):\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
    return json.loads(meta.read_text(encoding="utf-8"))


def _region_ids(png: Path, targets: dict[int, list[int]]) -> np.ndarray:
    arr = np.asarray(Image.open(png).convert("RGBA"))
    rgb = arr[:, :, :3].astype(np.int32)
    out = np.zeros(arr.shape[:2], dtype=np.uint8)
    best = None
    for rid, col in targets.items():
        d = ((rgb - np.array(col, dtype=np.int32)) ** 2).sum(axis=2)
        if best is None:
            best = d.copy()
            out[:] = rid
        else:
            m = d < best
            out[m] = rid
            best = np.where(m, d, best)
    out[arr[:, :, 3] <= 127] = 0  # background (transparent) -> none
    return out


def camera_parity_error(meta: dict) -> float:
    """Worst |Blender screen-direction - render3d/oracle| over +X,+Y,+Z (0 = identical)."""
    cp = meta["camera_probe"]
    origin = np.array(cp["origin"])
    worst = 0.0
    for key, expected in (
        ("px", ground_screen_direction(0.0)),
        ("py", ground_screen_direction(math.pi / 2)),
        ("pz", np.array([0.0, -1.0])),
    ):
        v = np.array(cp[key]) - origin
        v = v / (np.linalg.norm(v) or 1.0)
        worst = max(worst, float(np.linalg.norm(v - np.asarray(expected))))
    return worst


def bake_blender(out: Path, blender_exe: str) -> tuple[dict, dict]:
    meta = _run_blender(blender_exe, out)
    targets = {int(k): [round(_srgb(c) * 255) for c in v] for k, v in meta["region_color"].items()}
    color_imgs = [Image.open(out / f"color_dir{i:02d}.png").convert("RGBA") for i in range(DIRS)]
    region_arrs = [_region_ids(out / f"region_dir{i:02d}.png", targets) for i in range(DIRS)]
    canvas = (CANVAS, CANVAS)
    color_atlas, rects = _pack(color_imgs, canvas, "RGBA")
    mask_atlas, _ = _pack([Image.fromarray(a, "L") for a in region_arrs], canvas, "L")
    color_atlas.save(out / "color_atlas.png")
    mask_atlas.save(out / "hitmask_atlas.png")

    verts = meshes.humanoid()[0]
    height = float(verts[:, 2].max())
    z_floor = float(verts[:, 2].min())
    ground = verts[verts[:, 2] <= z_floor + 0.15 * height]
    foot_r = float(np.max(np.abs(ground[:, :2])))
    metrics = compute_world_metrics((-foot_r, -foot_r, 0.0), (foot_r, foot_r, height),
                                    eye_z=round(height * 0.9, 4))

    ax = round(meta["anchor_frac"][0] * CANVAS, 3)
    ay = round(meta["anchor_frac"][1] * CANVAS, 3)
    tip_len = CANVAS * 0.1
    frames, expected = [], []
    for i, rect in enumerate(rects):
        yaw = i * (2 * math.pi / DIRS)
        sdv = [round(v, 6) for v in ground_screen_direction(yaw).tolist()]
        frames.append({
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
        "variant_id": "humanoid_blender",
        "variant_class": "character",
        "direction_count": DIRS,
        "frame_canvas": list(canvas),
        "atlases": {
            "color": {"path": "color_atlas.png", "size": list(color_atlas.size)},
            "hitmask": {"path": "hitmask_atlas.png", "size": list(mask_atlas.size),
                        "format": "PNG_R8_UINT_linear_no_antialias", "sampling": "nearest",
                        "palette": {"none": 0, "head": 1, "torso": 2, "arms": 3, "legs": 4}},
        },
        "frames": frames,
        "expected_facing": expected,
        "world_metrics": metrics,
        "build": {"generator": "pipeline/tools/blender_bake.py", "mesh": "humanoid",
                  "renderer": f"blender_workbench_{meta.get('blender_version', '?')}"},
    }
    manifest.update(_contract_fields())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest, meta


def main() -> int:
    ap = argparse.ArgumentParser(description="R7: Blender-render a character package + check parity.")
    ap.add_argument("--out", type=Path, default=PIPELINE_ROOT / "reference" / "humanoid_blender")
    ap.add_argument("--blender", default=None)
    args = ap.parse_args()
    blender = find_blender(args.blender)
    if not blender:
        print("SKIP: Blender not found (set $BLENDER or install to %LOCALAPPDATA%\\blender-portable).")
        return 0
    out = args.out.resolve()
    manifest, meta = bake_blender(out, blender)
    parity = camera_parity_error(meta)
    errors = engine_accept(manifest)
    print(f"R7: Blender {meta.get('blender_version')} -> {out}")
    print(f"R7: camera parity worst err {parity:.4f} (render3d<->Blender; < 0.02 ok)")
    print(f"R7: Gate-1 {'PASS' if not errors else 'FAIL ' + str(errors)}")
    ok = parity < 0.02 and not errors
    print("R7 OK" if ok else "R7 FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
