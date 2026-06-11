#!/usr/bin/env python3
"""bake_env.py -- the world-scenery bake entry. Reads an `env_asset_v1` package (.asset.json), validates it
against the env contract, and ROUTES by `kind` into the SHARED core (pipeline/tools), which it imports
READ-ONLY:

  - terrain / water  -> pipeline/tools/bake_terrain.bake_terrain  (2D texture-warp tile; Gate-3 + Gate-1 on
                        emit; water also stamps the `collision` block into the manifest, ADR-055)
  - prop / blocking_feature -> pipeline/tools/blender_bake.bake_blender (static 16-dir mesh sprite + hitmask),
                        then a `scenery` block (kind + collision) is folded into the manifest for the map.

It NEVER modifies pipeline/tools (the one-way boundary the env self-test enforces). Tiered terrain
(cliff_face / ramp) is gated (ADR-0039) and not routed here yet.

  python pipeline/env/bake_env.py <env_asset.json> --out DIR [--blender PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools"
sys.path.insert(0, str(TOOLS))            # reuse the shared core READ-ONLY
sys.path.insert(0, str(HERE))             # env-local modules (collision_volumes)

from jsonschema import Draft202012Validator   # noqa: E402
import collision_volumes as cv                # noqa: E402  (env consumer; pure, no core/engine import)

SCHEMA = json.loads((HERE / "schema" / "env_asset.schema.json").read_text(encoding="utf-8"))


def validate(asset: dict) -> list[str]:
    return [f"/{'/'.join(map(str, e.path))}: {e.message}"
            for e in sorted(Draft202012Validator(SCHEMA).iter_errors(asset), key=lambda e: list(e.path))]


def bake_env(asset_path: Path, out: Path, blender: str | None = None) -> dict:
    asset_path, out = Path(asset_path), Path(out)
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    errs = validate(asset)
    if errs:
        raise SystemExit(f"env asset invalid ({asset_path.name}):\n  " + "\n  ".join(errs))
    kind, vid, base = asset["kind"], asset["variant_id"], asset_path.parent

    if kind in ("terrain", "water"):
        from bake_terrain import bake_terrain        # core, read-only
        bc = (asset.get("textures") or {}).get("base_color")
        src = base / bc if bc else None
        manifest = bake_terrain(out, vid, source=src if (src and src.exists()) else None)
        if src and not src.exists():
            print(f"  NOTE: source texture '{bc}' not authored yet -> baked a PROCEDURAL placeholder tile.")
        if kind == "water":
            # ADR-055: a water tile is a terrain render PLUS a sight+movement collider. Stamp it (additive;
            # the engine + the map feature list read it; variant_class stays 'terrain' for the render).
            manifest["collision"] = asset["collision"]
            (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"  WATER: stamped collision (blocks_movement={asset['collision']['blocks_movement']}, "
                  f"blocks_vision={asset['collision']['blocks_vision']}, occluder={asset['collision'].get('occluder_height_world')}m)")
        return manifest

    # prop / blocking_feature -> a STATIC mesh bake through the shared core.
    if not blender:
        from blender_bake import find_blender
        blender = find_blender()
    if not blender:
        raise SystemExit(f"a {kind} mesh bake needs Blender (set $BLENDER); terrain/water bakes do not.")
    mesh = base / asset["files"]["mesh"]
    if not mesh.exists():
        raise SystemExit(f"files.mesh '{mesh.name}' not found -- a {kind} needs its 3D model to bake.")

    # A STRUCTURE (multi-volume) ships a region_hitboxes sidecar (schema-enforced). Pass it as the region
    # map so the SHARED core projects each region's world AABB -> a px rect PER DIRECTION *keeping its name*
    # (blender_render region_rects) -- we read those back for the window sockets, re-projecting nothing.
    volumes_spec = asset.get("collision_volumes")
    region_hitboxes, region_map = None, None
    if volumes_spec:
        hb = (asset.get("files") or {}).get("hitbox")
        sidecar = base / hb
        if not sidecar.exists():
            raise SystemExit(f"files.hitbox '{hb}' not found -- collision_volumes geometry is MEASURED from "
                             f"the region_hitboxes sidecar; it cannot be baked without it.")
        region_hitboxes = (json.loads(sidecar.read_text(encoding="utf-8")).get("region_hitboxes") or {})
        region_map = str(sidecar)

    from blender_bake import bake_blender            # core, read-only (static path)
    forward = (asset.get("geometry") or {}).get("forward", "+x")
    manifest, meta = bake_blender(out, blender, str(mesh), vid, forward=forward, region_map=region_map)

    if volumes_spec:
        # DERIVE geometry (footprint + span_world) from the per-region world AABBs; MERGE the authored
        # semantics (vision/passable/material_class/projectile_response/damage_variant_role); VALIDATE (S6)
        # so a bad block never ships; STAMP additively (the engine ignores unknown fields by construction).
        vols = cv.derive_volumes(region_hitboxes, volumes_spec)
        errs, warns = cv.validate_volumes(vols, world_metrics_present=bool(asset.get("world_metrics")))
        if errs:
            raise SystemExit(f"collision_volumes invalid ({asset_path.name}):\n  " + "\n  ".join(errs))
        for w in warns:
            print(f"  WARN collision_volumes: {w}")
        manifest["collision_volumes"] = vols
        # window_<n>_center sockets: the projected px center of each TRANSPARENT (aperture) region, per
        # frame, from the core's named region_rects -- positional-only, the ADR-0009 per-frame socket shape.
        window_regions = [v["region"] for v in vols if v["vision"] == "transparent"]
        socks = cv.window_sockets(meta.get("region_rects") or {}, window_regions, len(manifest.get("frames", [])))
        for d, names in socks.items():
            manifest["frames"][d].setdefault("sockets", {}).update(names)
        n_socks = sum(len(s) for s in socks.values())
        print(f"  STRUCTURE [{kind}]: {len(vols)} collision_volume(s); "
              f"{len(window_regions)} window aperture(s) -> {n_socks} per-frame socket(s).")

    # Fold the SCENERY semantics into the manifest (variant_class stays 'character' = an engine-accepted
    # static sprite; a dedicated scenery variant_class is a future engine co-design). The map reads these.
    manifest["scenery"] = {"kind": kind, "collision": asset.get("collision"),
                           "collision_volumes": bool(volumes_spec),
                           "declared_world_metrics": asset.get("world_metrics")}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not volumes_spec:
        print(f"  SCENERY [{kind}]: folded collision={'yes' if asset.get('collision') else 'none'} into manifest.")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake a world-scenery env_asset_v1 package.")
    ap.add_argument("asset", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--blender", default=None)
    args = ap.parse_args()
    m = bake_env(args.asset, args.out, blender=args.blender)
    print(f"BAKE_ENV OK [{m.get('variant_class')}]: {m['variant_id']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
