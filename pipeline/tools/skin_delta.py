"""Texture-only SKIN DELTA -- a production skin that re-uses a base model's body (review #24 variant
compatibility; v3 plan).

A skin delta ships ONLY a new base-colour map + a reference to a BASE asset; the geometry, UVs, rig,
anchors, metrics and hitboxes are CLONED from the base. This module:

  * GUARDS that the delta is a legitimate texture-only change -- the resolved variant is provably
    geometry+UV IDENTICAL to the base, so a "skin" can never silently smuggle a re-model; and the new
    texture is a valid power-of-two PNG that the base's UVs can actually carry.
  * RESOLVES the delta into a bakeable variant: it clones the base glb, swaps in the new base-colour
    texture (Blender), and synthesizes a clean external_asset_v2 manifest -> ready for bake_asset.

  python skin_delta.py validate <delta.json> <base_dir>
  python skin_delta.py apply    <delta.json> <base_dir> <out_dir>
"""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from glb_texture_probe import _load_glb, _COMP, _NUMC, texture_capable  # noqa: E402

POW2 = {512, 1024, 2048, 4096}


def _acc_bytes(g, b, idx):
    acc = g['accessors'][idx]
    bv = g['bufferViews'][acc['bufferView']]
    comp, csize = _COMP[acc['componentType']]
    nc = _NUMC[acc['type']]
    base = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
    stride = bv.get('byteStride') or (csize * nc)
    out = bytearray()
    for i in range(acc['count']):
        s = base + i * stride
        out += b[s:s + csize * nc]
    return bytes(out)


def geometry_fingerprint(glb_path):
    """sha256 over every primitive's POSITION + TEXCOORD_0 + NORMAL accessor data (mesh/prim order).
    Two glbs with identical geometry + UVs (a clone + texture swap) share this fingerprint."""
    g, b = _load_glb(glb_path)
    h = hashlib.sha256()
    for mesh in g.get('meshes', []):
        for prim in mesh.get('primitives', []):
            a = prim.get('attributes', {})
            for key in ('POSITION', 'TEXCOORD_0', 'NORMAL'):
                if key in a:
                    h.update(key.encode())
                    h.update(_acc_bytes(g, b, a[key]))
    return h.hexdigest()


def geometry_identical(glb_a, glb_b):
    return geometry_fingerprint(glb_a) == geometry_fingerprint(glb_b)


def _png_dims(path):
    with open(path, 'rb') as f:
        head = f.read(26)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])


def _base_glb(delta, base_dir):
    return Path(base_dir) / (delta.get("base_glb") or f"{delta.get('base_asset_id')}.glb")


def _base_asset(base_dir, bid):
    """The base model's .asset.json (its full contract), if it sits next to the base glb."""
    p = Path(base_dir) / f"{bid}.asset.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _clone_hitbox(base_dir, bid, out_dir, vid):
    """Clone the base's EXPLICIT region-hitbox sidecar (the authoritative per-region AABB map) into the
    variant package as `<vid>_hitbox.json`, rewriting its asset_id. This is the 'everything else' that a
    texture-only skin inherits from its base: a single-material art model carries its regions here, not in
    materials. Looks up files.hitbox in the base asset, then the `<bid>_hitbox.json` sibling convention.
    Returns the number of regions cloned (0 = the base shipped no explicit region map)."""
    base_dir, out_dir = Path(base_dir), Path(out_dir)
    ba = _base_asset(base_dir, bid)
    cands = []
    hb = (ba.get("files") or {}).get("hitbox")
    if hb:
        cands.append(base_dir / hb)
    cands.append(base_dir / f"{bid}_hitbox.json")              # sibling convention (matches calibration packages)
    for src in cands:
        if not src.exists():
            continue
        try:
            hbj = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            continue
        regions = hbj.get("region_hitboxes") or {}
        if regions:
            hbj["asset_id"] = vid
            hbj["cloned_from_base"] = bid
            (out_dir / f"{vid}_hitbox.json").write_text(json.dumps(hbj, indent=2), encoding="utf-8")
            return len(regions)
    return 0


def validate_delta(delta, base_dir, delta_dir, variant_glb=None):
    """The GUARD. base_glb resolves under base_dir; base_color under delta_dir. variant_glb (optional)
    is a full variant mesh the producer also shipped -- if present it must be geometry-identical to the
    base. Returns a list of '<code>: <detail>' strings (empty = OK)."""
    base_dir, delta_dir = Path(base_dir), Path(delta_dir)
    errs = []
    vid, bid = delta.get("variant_id"), delta.get("base_asset_id")
    if not vid or not bid:
        return ["skin_delta_invalid: delta needs variant_id + base_asset_id"]
    if vid == bid:
        errs.append("skin_delta_self_reference: variant_id must differ from base_asset_id")
    base_glb = _base_glb(delta, base_dir)
    if not base_glb.exists():
        return errs + [f"skin_delta_base_missing: base glb '{base_glb.name}' not found in base_dir"]
    # the base must be re-skinnable: real UVs + a bound texture slot to swap
    _cap, _reasons, rec = texture_capable(str(base_glb))
    if rec["primitives"] and rec["no_uv"] == rec["primitives"]:
        errs.append("skin_delta_base_not_capable: base glb has NO UVs -- a new skin cannot map onto it")
    if rec["bound_textures"] == 0:
        errs.append("skin_delta_base_not_capable: base glb has no bound base-colour texture slot to replace")
    # the replacement texture
    bc = delta.get("base_color")
    tex = delta_dir / bc if bc else None
    if not bc or not tex.exists():
        errs.append(f"skin_delta_texture_missing: replacement base_color '{bc}' not found in delta_dir")
    else:
        dims = _png_dims(tex)
        if not dims:
            errs.append("skin_delta_texture_invalid: base_color is not a valid PNG")
        elif dims[0] not in POW2 or dims[1] not in POW2:
            errs.append(f"skin_delta_texture_invalid: base_color dims {dims} must be power-of-two in {sorted(POW2)}")
    if delta.get("real_albedo") is True and delta.get("calibration") is True:
        errs.append("skin_delta_real_albedo_conflict: a calibration skin must not claim real_albedo:true")
    # a shipped full variant mesh MUST be geometry+UV identical to the base (no smuggled re-model)
    if variant_glb and Path(variant_glb).exists():
        if not geometry_identical(str(base_glb), str(variant_glb)):
            errs.append("skin_delta_geometry_changed: the shipped variant glb is NOT geometry+UV identical "
                        "to the base -- a skin delta may change ONLY the texture")
    return errs


def apply_delta(delta, base_dir, delta_dir, out_dir, blender):
    """Resolve the delta -> a bakeable variant package. Clones the base glb, swaps in the new texture
    (Blender), and writes a clean external_asset_v2 manifest. Returns the variant .asset.json path."""
    base_dir, delta_dir, out_dir = Path(base_dir), Path(delta_dir), Path(out_dir)
    errs = validate_delta(delta, base_dir, delta_dir)
    if errs:
        raise SystemExit("skin delta invalid:\n  " + "\n  ".join(errs))
    vid, bid = delta["variant_id"], delta["base_asset_id"]
    base_glb = _base_glb(delta, base_dir)
    tex = delta_dir / delta["base_color"]
    out_dir.mkdir(parents=True, exist_ok=True)
    variant_glb = out_dir / f"{vid}.glb"
    proc = subprocess.run([blender, "--background", "--python", str(SCRIPT_DIR / "swap_basecolor.py"),
                           "--", str(base_glb), str(tex), str(variant_glb)], capture_output=True, text=True)
    if proc.returncode != 0 or not variant_glb.exists():
        raise SystemExit("skin-delta texture swap failed:\n" + (proc.stdout or "")[-1500:] + (proc.stderr or "")[-1500:])
    # the resolved variant MUST still be geometry-identical to the base (the swap touched only the image)
    if not geometry_identical(str(base_glb), str(variant_glb)):
        raise SystemExit("skin_delta_geometry_changed: the texture swap altered geometry (export bug)")
    # clone the base's authoritative region map -- a texture-only skin inherits regions/hitboxes from the
    # base (single-material art models declare regions explicitly, not via per-region materials).
    region_n = _clone_hitbox(base_dir, bid, out_dir, vid)
    # synthesize a CLEAN external_asset_v2 manifest (do not inherit the base's draft dialect)
    wm = {}
    bm = base_dir / f"{bid}.metrics.json"
    if bm.exists():
        m = json.loads(bm.read_text(encoding="utf-8")).get("world_metrics", {})
        for k, src in (("height_world", "height_world_m"), ("footprint_radius_world", "footprint_radius_world_m_body_core"),
                       ("eye_height_world", "eye_height_world_m")):
            if isinstance(m.get(src), (int, float)):
                wm[k] = m[src]
    asset = {
        "asset_contract_version": "external_asset_v2",
        "variant_id": vid,
        "archetype": delta.get("archetype", "dragon"),
        "texture_mode": "textured",
        "files": {"mesh": f"{vid}.glb"},
        "geometry": {"up": "z", "forward": "+x", "unit": "meter"},
        "region_source": "material_name",
        "provenance": {"texture": {"real_albedo": bool(delta.get("real_albedo", True)), "skin_delta_of": bid}},
        "notes": (f"Resolved texture-only skin delta of base '{bid}'; geometry+UV+rig cloned from the base"
                  + (f"; {region_n} region(s) cloned from the base hitbox map." if region_n else
                     " (base shipped no explicit region map).")),
    }
    if wm:
        asset["world_metrics"] = wm
    out_asset = out_dir / f"{vid}.asset.json"
    out_asset.write_text(json.dumps(asset, indent=2), encoding="utf-8")
    return out_asset


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    if len(sys.argv) < 4 or sys.argv[1] not in ("validate", "apply"):
        print(__doc__)
        return 2
    cmd, delta_path, base_dir = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    delta = _load(delta_path)
    if cmd == "validate":
        errs = validate_delta(delta, base_dir, delta_path.parent,
                              variant_glb=sys.argv[4] if len(sys.argv) > 4 else None)
        if errs:
            print(f"SKIN DELTA FAIL: {delta_path.name} ({len(errs)} issue(s))")
            for e in errs:
                print("   ", e)
            return 1
        print(f"SKIN DELTA OK: {delta_path.name} (base {delta.get('base_asset_id')} -> variant {delta.get('variant_id')})")
        return 0
    # apply
    if len(sys.argv) < 5:
        print("apply needs: <delta.json> <base_dir> <out_dir>")
        return 2
    from blender_bake import find_blender
    out = apply_delta(delta, base_dir, delta_path.parent, sys.argv[4], find_blender())
    print(f"SKIN DELTA APPLIED: {delta.get('variant_id')} -> {out}  (bake it with bake_asset.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
