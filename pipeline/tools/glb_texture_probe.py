"""Host-side texture-capability probe -- reads a .glb's glTF JSON + BIN with NO Blender (ADR-0026).

`texture_capable(glb)` decides whether a model can legitimately declare `texture_mode: textured`:
it is capable iff every part-mesh has (A) a real UV unwrap (non-degenerate, in-range) AND (B) a
base-colour image bound as `baseColorTexture`. The linter calls this BEFORE any bake so an orphan
atlas / collapsed UVs are rejected up front (deterministic input gate), never baked flat.

Standalone (stdlib only); the Blender-side twin is `_diag_glb_uvmesh.py`.
"""
from __future__ import annotations
import json
import struct

EPS_EXTENT = 1e-3      # per-material UV bbox WIDTH and HEIGHT must each exceed this
EPS_AREA = 1e-5        # per-material UV bbox area must exceed this (catches a UV collapsed to a LINE)
BLEED = 1e-3           # islands may bleed this far outside [0,1]

_COMP = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
_NUMC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def _load_glb(path):
    with open(path, 'rb') as f:
        d = f.read()
    if d[:4] != b'glTF':
        raise ValueError("not a binary glTF (.glb)")
    off, jb, bb, n = 12, None, None, len(d)
    while off + 8 <= n:
        clen, ctype = struct.unpack_from('<II', d, off)
        off += 8
        ch = d[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            jb = json.loads(ch.decode('utf-8'))
        elif ctype == 0x004E4942:
            bb = ch
    return jb, bb


def _read_uv(g, b, acc_idx):
    acc = g['accessors'][acc_idx]
    bv = g['bufferViews'][acc['bufferView']]
    comp, csize = _COMP[acc['componentType']]
    nc = _NUMC[acc['type']]
    base = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
    stride = bv.get('byteStride') or (csize * nc)
    us, vs = [], []
    for i in range(acc['count']):
        vals = struct.unpack_from('<' + comp * nc, b, base + i * stride)
        us.append(vals[0])
        vs.append(vals[1])
    return us, vs


def texture_capable(glb_path):
    """Return (ok: bool, reasons: sorted list of error codes, record: dict)."""
    g, b = _load_glb(glb_path)
    meshes = g.get('meshes', [])
    mats = g.get('materials', [])
    imgs = g.get('images', [])
    rec = {
        "primitives": 0, "no_uv": 0, "degenerate_uv": [], "out_of_range_uv": [],
        "bound_textures": 0, "materials": len(mats),
        "embedded_images": sum(1 for im in imgs if 'bufferView' in im),
        "external_images": sum(1 for im in imgs if 'uri' in im),
    }
    reasons = []
    bound = sum(1 for m in mats if (m.get('pbrMetallicRoughness') or {}).get('baseColorTexture') is not None)
    rec["bound_textures"] = bound
    if not (bound > 0 and len(imgs) > 0):
        reasons.append("texture_unbound")
    for mesh in meshes:
        for pi, prim in enumerate(mesh.get('primitives', [])):
            rec["primitives"] += 1
            attrs = prim.get('attributes', {})
            mi = prim.get('material')
            mn = (mats[mi].get('name') if (mi is not None and mi < len(mats)) else None) or f"{mesh.get('name','mesh')}[{pi}]"
            if 'TEXCOORD_0' not in attrs:
                rec["no_uv"] += 1
                continue
            us, vs = _read_uv(g, b, attrs['TEXCOORD_0'])
            if not us:
                rec["no_uv"] += 1
                continue
            umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
            w, h = (umax - umin), (vmax - vmin)
            # degenerate = collapsed to a POINT (both tiny) OR a LINE (one axis tiny) OR a sliver
            # (tiny area) -- a UV [w=0, h=0.8] still samples a single texel column and is unusable.
            if w < EPS_EXTENT or h < EPS_EXTENT or (w * h) < EPS_AREA:
                rec["degenerate_uv"].append(mn)
            if umin < -BLEED or vmin < -BLEED or umax > 1 + BLEED or vmax > 1 + BLEED:
                rec["out_of_range_uv"].append(mn)
    if rec["primitives"] > 0 and rec["no_uv"] == rec["primitives"]:
        reasons.append("texture_unbound")     # no UVs anywhere -> cannot sample a texture
    if rec["degenerate_uv"]:
        reasons.append("degenerate_uv")
    rec["degenerate_uv"] = sorted(set(rec["degenerate_uv"]))
    rec["out_of_range_uv"] = sorted(set(rec["out_of_range_uv"]))
    return (not reasons), sorted(set(reasons)), rec


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        ok, reasons, rec = texture_capable(p)
        print(f"{'CAPABLE' if ok else 'NOT-CAPABLE':12s} {p}")
        print(f"   reasons={reasons}  record={rec}")
