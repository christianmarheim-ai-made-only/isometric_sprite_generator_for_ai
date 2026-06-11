#!/usr/bin/env python3
"""Env bake + scenery-gate tests (#3/#4). Runs in the env gate (build_env.py).

  - bake_env routes terrain -> bake_terrain (variant_class:terrain, dir 1, elevation 30, Gate-1 ok),
    emits the 3x3 tiling preview, and water stamps a collision block.
  - the ELEVATION GUARD (Gate-3, the irreversible-mistake gate) rejects any bake off 30 deg.
  - the SEAMLESS gate flags a non-tiling source.
  - bake_env VALIDATES the env contract (rejects an off-contract asset).
  - (Blender-gated) a prop mesh routes to the static bake -> a non-empty hitmask + a `scenery` block.

  python pipeline/env/test_env_bake.py
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

import numpy as np
import bake_env                                   # noqa: E402
import bake_terrain as bt                         # noqa: E402  (core, read-only)
from gate_engine_accept import engine_accept      # noqa: E402


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def _box_glb(path: Path, hx=0.4, height=1.2):
    """A minimal single-material box, glTF Y-up (imports upright Z-up) -- a stand-in prop mesh."""
    P = [(-hx, 0.0, -hx), (hx, 0.0, -hx), (hx, 0.0, hx), (-hx, 0.0, hx),
         (-hx, height, -hx), (hx, height, -hx), (hx, height, hx), (-hx, height, hx)]
    F = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1),
         (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]
    pos = b"".join(struct.pack("<3f", *p) for p in P)
    idx = b"".join(struct.pack("<H", i) for f in F for i in f)
    idx += b"\x00" * (-len(idx) % 4)
    binb = pos + idx
    pmin = [min(p[k] for p in P) for k in range(3)]
    pmax = [max(p[k] for p in P) for k in range(3)]
    g = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
         "materials": [{"name": "rock", "pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.42, 0.34, 1]}}],
         "buffers": [{"byteLength": len(binb)}],
         "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos), "target": 34962},
                         {"buffer": 0, "byteOffset": len(pos), "byteLength": len(idx), "target": 34963}],
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": pmin, "max": pmax},
                       {"bufferView": 1, "componentType": 5123, "count": len(F) * 3, "type": "SCALAR"}]}
    js = json.dumps(g).encode(); js += b" " * (-len(js) % 4)
    blob = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(binb))
    blob += struct.pack("<I", len(js)) + b"JSON" + js + struct.pack("<I", len(binb)) + b"BIN\x00" + binb
    path.write_bytes(blob)


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # --- terrain via bake_env (procedural fallback) ---
        ta = td / "ground.asset.json"
        ta.write_text(json.dumps({"env_contract_version": "env_asset_v1", "variant_id": "t_ground",
                                  "kind": "terrain", "texture_mode": "textured",
                                  "textures": {"base_color": "missing.png"}, "direction_count": 1,
                                  "tiling": {"seamless": True}}), encoding="utf-8")
        out = td / "t_out"
        m = bake_env.bake_env(ta, out)
        ok &= check("terrain bake_env -> variant_class:terrain, dir 1, elevation 30",
                    m["variant_class"] == "terrain" and m["direction_count"] == 1 and m["camera"]["camera_elevation_degrees"] == 30)
        ok &= check("terrain bake emits the 3x3 tiling preview", (out / "preview_3x3.png").exists())
        ok &= check("terrain manifest passes Gate-1 (engine acceptance)", engine_accept(m) == [])

        # --- ELEVATION GUARD (Gate-3): the irreversible-mistake gate rejects off-30 ---
        try:
            bt.bake_terrain(td / "bad", "t_bad", elevation=26.565)
            ok &= check("elevation guard rejects a 26.565 bake", False)
        except SystemExit:
            ok &= check("elevation guard rejects a 26.565 bake (Gate-3)", True)

        # --- SEAMLESS gate ---
        ok &= check("seamless gate: procedural arid texture tiles", bt.is_seamless(bt.procedural_arid_texture(64)))
        noise = (np.arange(64 * 64 * 3).reshape(64, 64, 3) % 256).astype(np.uint8)   # hard left/right edge mismatch
        ok &= check("seamless gate: a non-tiling source is flagged", not bt.is_seamless(noise))

        # --- water stamps a collision block ---
        wa = td / "water.asset.json"
        wa.write_text(json.dumps({"env_contract_version": "env_asset_v1", "variant_id": "t_water", "kind": "water",
                                  "texture_mode": "textured", "textures": {"base_color": "missing.png"},
                                  "direction_count": 1, "tiling": {"seamless": True},
                                  "collision": {"footprint": {"shape": "aabb", "half_extents_world": [0.5, 0.5]},
                                                "occluder_height_world": 0.6, "blocks_movement": True, "blocks_vision": True}}),
                      encoding="utf-8")
        wm = bake_env.bake_env(wa, td / "w_out")
        ok &= check("water bake stamps collision (blocks_movement+vision)",
                    wm.get("collision", {}).get("blocks_movement") is True and wm["collision"]["blocks_vision"] is True)

        # --- bake_env VALIDATES the contract (off-contract terrain+collider rejected) ---
        bad = td / "bad.asset.json"
        bad.write_text(json.dumps({"env_contract_version": "env_asset_v1", "variant_id": "x", "kind": "terrain",
                                   "texture_mode": "textured", "textures": {"base_color": "m.png"},
                                   "collision": {"footprint": {"shape": "circle", "radius_world": 1},
                                                 "blocks_movement": True, "blocks_vision": True}}), encoding="utf-8")
        try:
            bake_env.bake_env(bad, td / "x_out")
            ok &= check("bake_env rejects an off-contract asset (terrain + collider)", False)
        except SystemExit:
            ok &= check("bake_env rejects an off-contract asset (terrain + collider)", True)

        # --- (Blender-gated) prop mesh -> static bake -> hitmask + scenery block ---
        from blender_bake import find_blender
        blender = find_blender()
        if not blender:
            print("SKIP: Blender not found -> prop static-bake + hitmask gate not exercised")
        else:
            _box_glb(td / "rock.glb")
            pa = td / "rock.asset.json"
            pa.write_text(json.dumps({"env_contract_version": "env_asset_v1", "variant_id": "t_rock", "kind": "blocking_feature",
                                      "texture_mode": "flat_region", "files": {"mesh": "rock.glb"}, "direction_count": 16,
                                      "world_metrics": {"height_world": 1.2, "footprint_radius_world": 0.4},
                                      "collision": {"footprint": {"shape": "aabb", "half_extents_world": [0.4, 0.4]},
                                                    "occluder_height_world": 1.2, "blocks_movement": True, "blocks_vision": True}}),
                          encoding="utf-8")
            pm = bake_env.bake_env(pa, td / "p_out", blender=blender)
            from PIL import Image
            hm = Image.open(td / "p_out" / "hitmask_atlas.png").convert("L")
            ok &= check("prop bake -> NON-EMPTY hitmask (static-prop hitmask gate)", hm.getbbox() is not None)
            ok &= check("prop manifest carries the scenery block (kind + collision)",
                        pm.get("scenery", {}).get("kind") == "blocking_feature" and pm["scenery"]["collision"] is not None)

            # --- (Blender-gated) STRUCTURE: a windowed wall -> the additive collision_volumes block ---
            # The glb is just the sprite; the per-region GEOMETRY is MEASURED from the sidecar (the contract S2
            # example), and the window SOCKET falls out of the core's named region_rects. Full end-to-end.
            _box_glb(td / "wall.glb", hx=1.5, height=3.0)
            (td / "wall_hitbox.json").write_text(json.dumps({"asset_id": "t_wall", "region_hitboxes": {
                "wall_body":     {"min": [-1.5, -0.2, 0.0], "max": [1.5, 0.2, 3.0]},
                "window_sill":   {"min": [0.1, -0.2, 0.0],  "max": [1.1, 0.2, 1.0]},
                "window_glass":  {"min": [0.1, -0.05, 1.0], "max": [1.1, 0.05, 2.2]},
                "window_lintel": {"min": [0.1, -0.2, 2.2],  "max": [1.1, 0.2, 3.0]}}}), encoding="utf-8")
            wla = td / "wall.asset.json"
            wla.write_text(json.dumps({"env_contract_version": "env_asset_v1", "variant_id": "t_wall",
                "kind": "blocking_feature", "texture_mode": "flat_region",
                "files": {"mesh": "wall.glb", "hitbox": "wall_hitbox.json"}, "region_source": "explicit_region_hitboxes",
                "direction_count": 16, "world_metrics": {"height_world": 3.0, "footprint_radius_world": 1.5},
                "collision_volumes": [
                    {"region": "wall_body", "vision": "opaque", "passable": False, "material_class": "stone",
                     "projectile_response": {"default": "block_and_damage"}, "damage_variant_role": None},
                    {"region": "window_sill", "vision": "opaque", "passable": False, "material_class": "stone",
                     "projectile_response": {"default": "block_and_damage"}, "damage_variant_role": None},
                    {"region": "window_glass", "vision": "transparent", "passable": False, "material_class": "glass",
                     "projectile_response": {"default": "block_and_damage", "by_class": {"bullet": "pass_ignore"}},
                     "damage_variant_role": "damaged"},
                    {"region": "window_lintel", "vision": "opaque", "passable": False, "material_class": "stone",
                     "projectile_response": {"default": "block_and_damage"}, "damage_variant_role": None}]}),
                encoding="utf-8")
            wm2 = bake_env.bake_env(wla, td / "wall_out", blender=blender)
            vols = wm2.get("collision_volumes") or []
            ok &= check("windowed wall -> manifest carries 4 collision_volumes", len(vols) == 4)
            gv = next((v for v in vols if v["region"] == "window_glass"), {})
            ok &= check("baked glass volume: transparent + bullet pass_ignore + span [1.0,2.2] (geometry MEASURED)",
                        gv.get("vision") == "transparent"
                        and gv.get("projectile_response", {}).get("by_class", {}).get("bullet") == "pass_ignore"
                        and gv.get("span_world") == [1.0, 2.2])
            n_sock = sum(1 for f in (wm2.get("frames") or []) if "window_0_center" in (f.get("sockets") or {}))
            ok &= check("windowed wall -> per-frame window_0_center socket present", n_sock >= 1)
            ok &= check("windowed wall manifest STILL engine-accepted (additive block, Gate-1)", engine_accept(wm2) == [])

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
