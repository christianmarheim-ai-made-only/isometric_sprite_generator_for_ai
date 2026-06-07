#!/usr/bin/env python3
"""Gate (Blender): a SINGLE-MATERIAL model + an explicit region hitbox bakes a MULTI-region hit-mask.

This is the end-to-end proof of the explicit-hitbox baking path: a one-material box renders an all-torso
region pass, but the projected region AABBs re-label it so the packed hitmask carries >1 region id, and
the regions land in the right screen places (head above legs). Skips cleanly where Blender is absent.

  python pipeline/tools/test_region_bake_e2e.py
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _write_box_glb(path: Path, hx: float = 0.3, height: float = 2.0):
    """A minimal single-material ('Material_0') box. Authored glTF Y-UP (height along +Y) so Blender's
    Y-up->Z-up import yields an UPRIGHT box (height along Blender +Z, foot at z=0) -- matching the
    Z-up region hitbox AABBs. (Authoring height along +Z would import lying down: the classic axis trap.)"""
    P = [(-hx, 0.0, -hx), (hx, 0.0, -hx), (hx, 0.0, hx), (-hx, 0.0, hx),          # 0..3 foot  (glTF y=0)
         (-hx, height, -hx), (hx, height, -hx), (hx, height, hx), (-hx, height, hx)]  # 4..7 top (glTF y=height)
    F = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1),
         (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]
    pos = b"".join(struct.pack("<3f", *p) for p in P)
    idx = b"".join(struct.pack("<H", i) for f in F for i in f)
    while len(idx) % 4:
        idx += b"\x00"
    binb = pos + idx
    pmin = [min(p[k] for p in P) for k in range(3)]
    pmax = [max(p[k] for p in P) for k in range(3)]
    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
        "materials": [{"name": "Material_0", "pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.5, 0.5, 1]}}],
        "buffers": [{"byteLength": len(binb)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos), "target": 34962},
                        {"buffer": 0, "byteOffset": len(pos), "byteLength": len(idx), "target": 34963}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": pmin, "max": pmax},
                      {"bufferView": 1, "componentType": 5123, "count": len(F) * 3, "type": "SCALAR"}],
    }
    js = json.dumps(gltf).encode("utf-8")
    while len(js) % 4:
        js += b" "
    glb = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(binb))
    glb += struct.pack("<I", len(js)) + b"JSON" + js
    glb += struct.pack("<I", len(binb)) + b"BIN\x00" + binb
    path.write_bytes(glb)


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def main():
    from blender_bake import find_blender, bake_blender
    blender = find_blender()
    if not blender:
        print("SKIP: Blender not found -> explicit-hitbox e2e not exercised")
        return 0

    import numpy as np
    from PIL import Image

    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        glb = td / "box.glb"
        _write_box_glb(glb)
        # 3 regions stacked along z -> head (top), torso (mid), legs (bottom) => body ids 1,2,4
        hitbox = td / "box_hitbox.json"
        hitbox.write_text(json.dumps({"asset_id": "box", "region_hitboxes": {
            "head": {"min": [-0.3, -0.3, 1.3], "max": [0.3, 0.3, 2.0]},
            "torso": {"min": [-0.3, -0.3, 0.7], "max": [0.3, 0.3, 1.3]},
            "legs": {"min": [-0.3, -0.3, 0.0], "max": [0.3, 0.3, 0.7]},
        }}), encoding="utf-8")

        out = td / "bake"
        manifest, _ = bake_blender(out, blender, str(glb), "box", region_map=str(hitbox))

        hm = np.array(Image.open(out / "hitmask_atlas.png").convert("L"))
        present = sorted(int(v) for v in np.unique(hm) if v)
        ok &= check(f"single-material + explicit hitbox -> multi-region hitmask (ids {present})", len(present) > 1)
        ok &= check("recovered the head(1)+legs(4) body ids", 1 in present and 4 in present)

        # geometry sanity on frame 0: head sits ABOVE legs (smaller screen-y), both within the silhouette
        ra = manifest["frames"][0].get("region_aabbs", {})
        if "1" in ra and "4" in ra:
            head_cy = ra["1"][1] + ra["1"][3] / 2.0
            legs_cy = ra["4"][1] + ra["4"][3] / 2.0
            ok &= check(f"head is above legs on screen (head_cy {head_cy:.0f} < legs_cy {legs_cy:.0f})",
                        head_cy < legs_cy)
        else:
            ok &= check("frame0 emitted head + legs region_aabbs", False)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
