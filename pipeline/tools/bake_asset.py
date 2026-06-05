#!/usr/bin/env python3
"""One-command content production: read an external `<variant>.asset.json` (the contract front
door), validate it, and bake it into a game_iso_v1 sprite package -- routing to the right baker:

  - OBJ mesh                       -> bake.bake_mesh           (numpy, static)
  - glTF/glb, no rig/animations    -> blender_bake.bake_blender (Blender, static)
  - glTF/glb + rig + animations    -> blender_bake.bake_animated (Blender, samples the clips)

So a producer just delivers a model + `.asset.json`, and you run one command.

  python pipeline/tools/bake_asset.py your.asset.json [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lint_external_asset import lint  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402


def bake_asset(manifest_path: Path, out: Path | None = None) -> dict:
    errs = lint(manifest_path)
    if errs:
        raise SystemExit("asset lint failed:\n  " + "\n  ".join(errs))
    asset = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    base = Path(manifest_path).parent
    variant_id = asset["variant_id"]
    out = (out or (PIPELINE_ROOT / "output" / variant_id)).resolve()
    mesh = (asset.get("files") or {}).get("mesh")
    if not mesh:
        raise SystemExit("asset has no files.mesh to bake")
    mesh_path = (base / mesh).resolve()
    up = (asset.get("geometry") or {}).get("up", "z")
    anims = asset.get("animations")
    ext = mesh_path.suffix.lower()

    if ext == ".obj":
        from bake import bake_mesh
        manifest = bake_mesh(str(mesh_path), out, variant_id=variant_id, up=up)
        route = "numpy / OBJ static"
    elif ext in (".glb", ".gltf"):
        import subprocess
        from blender_bake import find_blender, bake_blender, bake_animated
        blender = find_blender()
        if not blender:
            raise SystemExit("Blender not found; needed to bake a glTF (set $BLENDER).")
        if asset.get("rig") and anims:
            mesh_for_bake = str(mesh_path)
            clips_rel = (asset.get("files") or {}).get("animation_clips")
            route = "Blender / rigged + animated"
            if clips_rel:
                # embed the anim_clips_v1 JSON as glTF clips on the rigged mesh first
                out.mkdir(parents=True, exist_ok=True)
                animated = out / f"{variant_id}_animated.glb"
                cmd = [blender, "--background", "--python", str(SCRIPT_DIR / "bake_anim_from_json.py"),
                       "--", str(mesh_path), str((base / clips_rel).resolve()), str(animated)]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0 or not animated.exists():
                    raise SystemExit("bake_anim_from_json failed:\n" + (proc.stdout or "")[-1500:] + (proc.stderr or "")[-1500:])
                mesh_for_bake = str(animated)
                route = "Blender / rigged + animated (clips embedded from animation_clips JSON)"
            manifest, _ = bake_animated(out, blender, mesh_for_bake, anims, variant_id)
        else:
            manifest, _ = bake_blender(out, blender, str(mesh_path), variant_id)
            route = "Blender / static"
    else:
        raise SystemExit(f"unsupported mesh format: {ext}")

    errs = engine_accept(manifest)
    if errs:
        raise SystemExit("baked package failed Gate-1:\n  " + "\n  ".join(errs))
    print(f"BAKE_ASSET OK [{route}]: {variant_id} -> {out}  ({len(manifest['frames'])} frames)")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake an external asset (.asset.json) into a sprite package.")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    bake_asset(args.manifest, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
