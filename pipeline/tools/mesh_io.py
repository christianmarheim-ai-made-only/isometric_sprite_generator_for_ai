#!/usr/bin/env python3
"""Load a real mesh (Wavefront OBJ) into the pipeline's (verts, faces, face_region) shape (R8).

The numpy render path (render3d) consumes a triangle soup + a per-face HIT region id; this
turns an external OBJ into exactly that, assigning the body region (head 1, torso 2, arms 3,
legs 4) per face by the face's material/group NAME (keyword match). Real art just names its
materials/groups head/torso/arms/legs (or chest/hand/foot/...). glTF goes through Blender's
native importer (blender_render.py); OBJ is handled here with no extra dependency.

The mesh is normalized to the game_iso_v1 contract: +Z up, foot at the world origin (min z -> 0,
footprint centered on x=y=0), metres. `up="y"` rotates a Y-up art file into +Z up first.

CLI:  python pipeline/tools/mesh_io.py export-humanoid OUT.obj   # write a test fixture
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import meshes  # noqa: E402

REGION_NAMES = {1: "head", 2: "torso", 3: "arms", 4: "legs"}
# keyword (lowercased substring of the material/group name) -> region id. Order: specific first.
REGION_KEYWORDS = [
    ("head", 1), ("skull", 1), ("face", 1), ("neck", 1), ("beak", 1),
    ("torso", 2), ("chest", 2), ("body", 2), ("spine", 2), ("hip", 2), ("pelvis", 2), ("waist", 2), ("tail", 2),
    ("arm", 3), ("hand", 3), ("shoulder", 3), ("elbow", 3), ("wrist", 3), ("wing", 3),
    ("leg", 4), ("foot", 4), ("feet", 4), ("thigh", 4), ("shin", 4), ("knee", 4), ("ankle", 4),
]


def region_for_name(name: str) -> int:
    """Body HIT region for a material/group name; unmatched body faces default to torso (2)."""
    n = (name or "").lower()
    for kw, rid in REGION_KEYWORDS:
        if kw in n:
            return rid
    return 2


def load_obj(path, up: str = "z", normalize: bool = True):
    """Load an OBJ -> (verts Nx3 float, faces Mx3 int, face_region M int). Triangulates polygons
    (fan); reads `usemtl`/`g`/`o` for the region; handles 1-based + negative `f` indices."""
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    face_region: list[int] = []
    cur = 2  # default region until a usemtl/group says otherwise
    unmatched = 0
    for raw in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tag, _, rest = line.partition(" ")
        if tag == "v":
            p = rest.split()
            verts.append((float(p[0]), float(p[1]), float(p[2])))
        elif tag in ("usemtl", "g", "o"):
            name = rest.strip()
            cur = region_for_name(name)
            if cur == 2 and not any(kw in name.lower() for kw, _ in REGION_KEYWORDS):
                unmatched += 1
        elif tag == "f":
            idx = []
            for tok in rest.split():
                i = int(tok.split("/")[0])
                idx.append(i - 1 if i > 0 else len(verts) + i)
            for k in range(1, len(idx) - 1):  # fan triangulation
                faces.append((idx[0], idx[k], idx[k + 1]))
                face_region.append(cur)
    if not verts or not faces:
        raise ValueError(f"{path}: no geometry parsed (v={len(verts)}, f={len(faces)})")
    v = np.asarray(verts, dtype=float)
    if up == "y":  # Y-up art -> +Z up (rotate +90deg about X: (x,y,z) -> (x,-z,y))
        v = np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1)
    if normalize:  # foot to origin: min z -> 0, footprint centered on x=y=0
        lo = v.min(axis=0)
        hi = v.max(axis=0)
        v = v - np.array([(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, lo[2]])
    if unmatched:
        print(f"WARN load_obj: {unmatched} material/group(s) had no head/torso/arms/legs keyword -> torso")
    return v, np.asarray(faces, dtype=int), np.asarray(face_region, dtype=int)


def write_obj(path, verts, faces, face_region, region_names=REGION_NAMES) -> None:
    """Write an OBJ (+ minimal MTL) with per-region `usemtl` groups -- used to mint test fixtures."""
    path = Path(path)
    mtl = path.with_suffix(".mtl")
    out = [f"mtllib {mtl.name}"]
    for v in verts:
        out.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    order = sorted(range(len(faces)), key=lambda i: int(face_region[i]))
    cur = None
    for i in order:
        r = int(face_region[i])
        if r != cur:
            out.append(f"usemtl {region_names.get(r, 'torso')}")
            cur = r
        f = faces[i]
        out.append(f"f {int(f[0]) + 1} {int(f[1]) + 1} {int(f[2]) + 1}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    mtl.write_text("".join(f"newmtl {n}\nKd 0.6 0.6 0.6\n\n" for n in region_names.values()), encoding="utf-8")


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "export-humanoid":
        verts, faces, face_region = meshes.humanoid()
        write_obj(sys.argv[2], verts, faces, face_region)
        print(f"wrote {sys.argv[2]} ({len(verts)} verts, {len(faces)} faces)")
        return 0
    print("usage: mesh_io.py export-humanoid OUT.obj")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
