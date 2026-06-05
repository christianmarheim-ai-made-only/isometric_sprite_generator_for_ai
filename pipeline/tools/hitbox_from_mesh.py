#!/usr/bin/env python3
"""Derive HITBOX data from a model's geometry -- the compact, model-derived collision/hit data the
pipeline emits, expressed as text you (or an AI) can read, author, and sanity-check.

From a region-tagged mesh it computes:
  - world_metrics  : the collision CAPSULE proxy -- height_world (top above ground),
                     footprint_radius_world (ground-contact half-extent), eye_height_world.
                     This is exactly what bake.py writes into the manifest.
  - regions        : a per-region world AABB (head/torso/arms/legs), from that region's vertices.
                     Coarse per-part boxes for cheap hit queries; the authoritative per-pixel map is
                     the R8 hit-mask the renderer bakes from the same region tags.

Pure numpy + the OBJ loader -- no Blender. An AI can reproduce every number here by iterating the
vertex list directly (min/max), which is the point: it's all small, known data.

  python pipeline/tools/hitbox_from_mesh.py MESH.obj [--up z|y] [--out OUT.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mesh_io import load_obj, REGION_NAMES  # noqa: E402
from measure_metrics import compute_world_metrics  # noqa: E402
from constants import GROUND_BAND, EYE_FRACTION  # noqa: E402  (canonical: must match bake.py)


def hitbox_from_mesh(mesh_path: str, up: str = "z") -> dict:
    verts, faces, face_region = load_obj(mesh_path, up=up)
    verts = np.asarray(verts, dtype=float)
    faces = np.asarray(faces, dtype=int)
    face_region = np.asarray(face_region, dtype=int)

    height = float(verts[:, 2].max())
    z_floor = float(verts[:, 2].min())
    ground = verts[verts[:, 2] <= z_floor + GROUND_BAND * height]
    foot_r = float(np.max(np.abs(ground[:, :2])))
    metrics = compute_world_metrics((-foot_r, -foot_r, 0.0), (foot_r, foot_r, height),
                                    eye_z=round(height * EYE_FRACTION, 4))

    regions = {}
    for rid in sorted(set(int(r) for r in face_region)):
        vidx = np.unique(faces[face_region == rid].reshape(-1))
        rv = verts[vidx]
        regions[REGION_NAMES.get(rid, f"region{rid}")] = {
            "id": rid,
            "aabb_min": [round(float(c), 4) for c in rv.min(axis=0)],
            "aabb_max": [round(float(c), 4) for c in rv.max(axis=0)],
        }

    return {
        "hitbox_spec_version": "hitbox_v1",
        "from_mesh": Path(mesh_path).name,
        "unit": "meter",
        "up": "z",
        "world_metrics": metrics,
        "collision_capsule": {
            "radius_world": metrics["footprint_radius_world"],
            "height_world": metrics["height_world"],
            "note": "axis-aligned capsule/cylinder of this radius and height, centered on the foot at the origin",
        },
        "regions": regions,
        "hitmask_note": "the authoritative per-pixel HIT map is the R8 hitmask the renderer bakes "
                        "from the SAME region tags (palette none0/head1/torso2/arms3/legs4); these "
                        "AABBs are the coarse world-space boxes.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Derive hitbox data (capsule + per-region AABB) from a mesh.")
    ap.add_argument("mesh")
    ap.add_argument("--up", default="z", choices=["z", "y"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    spec = hitbox_from_mesh(args.mesh, args.up)
    text = json.dumps(spec, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"HITBOX -> {args.out}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
