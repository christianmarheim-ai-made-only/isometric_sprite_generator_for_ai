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
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lint_external_asset import lint  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402


def _gltf_json(path: Path) -> dict:
    """Top-level glTF JSON from a .glb (binary JSON chunk) or a .gltf (text)."""
    path = Path(path)
    if path.suffix.lower() == ".gltf":
        return json.loads(path.read_text(encoding="utf-8"))
    import struct
    with open(path, "rb") as f:
        f.read(12)                                   # 12-byte glb header
        clen, _ = struct.unpack("<II", f.read(8))    # first chunk = JSON
        return json.loads(f.read(clen).decode("utf-8"))


def _glb_has_armature(path: Path) -> bool:
    """True if the glTF declares a skin (an armature). An UNRIGGED part-mesh delivery has none. On any
    parse trouble, assume rigged (True) so we never auto-rig blindly -- the existing 'no armature found'
    failure still applies, i.e. zero behaviour change for the un-parseable case."""
    try:
        return bool(_gltf_json(path).get("skins"))
    except Exception:
        return True


def _resolve_rig_profile(rig: str, base: Path) -> Path | None:
    """A rig profile installed in the pipeline OR shipped in the delivery's schema_extensions/."""
    for c in (PIPELINE_ROOT / "schema" / "rig_profiles" / f"{rig}.json",
              base / "schema_extensions" / f"{rig}.rig_profile.json",
              base / "schema_extensions" / f"{rig}.json"):
        if c.exists():
            return c
    return None


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
    forward = (asset.get("geometry") or {}).get("forward", "+x")  # rotated onto +X by the baker
    anims = asset.get("animations")
    clips_rel = (asset.get("files") or {}).get("animation_clips")
    ext = mesh_path.suffix.lower()
    auto_rigged_from = None   # set if the pipeline rigs an unrigged delivery on the fly (provenance)

    import time
    t0 = time.perf_counter()
    if ext == ".obj":
        from bake import bake_mesh
        manifest = bake_mesh(str(mesh_path), out, variant_id=variant_id, up=up, forward=forward)
        route = "numpy / OBJ static"
    elif ext in (".glb", ".gltf"):
        import subprocess
        from blender_bake import find_blender, bake_blender, bake_animated
        blender = find_blender()
        if not blender:
            raise SystemExit("Blender not found; needed to bake a glTF (set $BLENDER).")
        if asset.get("rig") and anims:
            # AUTO-RIG: the rigged+animated route needs an armature, but a producer may deliver UNRIGGED
            # part-meshes + a rig profile (no skeleton in the glb) -> bake_anim_from_json would hard-fail
            # "no armature found". Detect that and build the armature from the declared rig profile
            # (rig_from_profile) here, then bake from the derived glb. rig_from_profile re-exports standard
            # Y-up glTF, so the subsequent bake switches up -> "y". The manual path (asset already points
            # at a rigged glb) is unaffected: a rigged glb has a skin, so this block is skipped.
            if not _glb_has_armature(mesh_path):
                profile = _resolve_rig_profile(asset["rig"], base)
                if profile is None:
                    raise SystemExit(f"asset declares rig '{asset['rig']}' and the delivered mesh has no "
                                     f"armature, but no rig profile was found "
                                     f"(schema/rig_profiles/{asset['rig']}.json or "
                                     f"{base.name}/schema_extensions/{asset['rig']}.rig_profile.json)")
                out.mkdir(parents=True, exist_ok=True)
                rigged = out / f"{variant_id}_rigged.glb"
                materials = base / f"{variant_id}_materials.json"          # optional: per-region base colour
                source_asset = base / f"{variant_id}.source_asset.json"    # optional: DECLARED hit regions
                cmd = [blender, "--background", "--python", str(SCRIPT_DIR / "rig_from_profile.py"), "--",
                       str(mesh_path), str(profile), up, str(rigged),
                       str(materials) if materials.exists() else "",
                       str(source_asset) if source_asset.exists() else ""]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0 or not rigged.exists():
                    raise SystemExit("auto-rig (rig_from_profile) failed:\n"
                                     + (proc.stdout or "")[-1500:] + (proc.stderr or "")[-1500:])
                auto_rigged_from = mesh_path           # remember the delivered mesh for provenance
                mesh_path = rigged                     # everything downstream bakes from the rigged glb
                up = "y"                               # rig_from_profile output is standard Y-up glTF
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
            manifest, _ = bake_animated(out, blender, mesh_for_bake, anims, variant_id,
                                        default_state=asset.get("default_state"), up=up, forward=forward)
        else:
            manifest, _ = bake_blender(out, blender, str(mesh_path), variant_id, forward=forward)
            route = "Blender / static"
    else:
        raise SystemExit(f"unsupported mesh format: {ext}")

    bake_ms = round((time.perf_counter() - t0) * 1000, 1)
    errs = engine_accept(manifest)
    if errs:
        raise SystemExit("baked package failed Gate-1:\n  " + "\n  ".join(errs))

    from build_log import write_build_log, stamp_provenance
    from contract_hash import compute_individual_hashes
    meta = {}
    for mf in ("anim_meta.json", "blender_meta.json"):
        mp = out / mf
        if mp.exists():
            meta = json.loads(mp.read_text(encoding="utf-8"))
            break
    if auto_rigged_from is not None:                 # record the on-the-fly rig in the build log
        meta["auto_rigged_from"] = str(auto_rigged_from)
    clips_path = (base / clips_rel).resolve() if clips_rel else None
    rig = asset.get("rig")
    texture_mode = asset.get("texture_mode", "flat_region")
    calibration = bool(asset.get("calibration")
                       or ((asset.get("provenance") or {}).get("texture") or {}).get("calibration_texture"))
    log = write_build_log(out, manifest, route, asset_path=manifest_path, mesh=mesh_path,
                          clips=clips_path, rig=rig, archetype=asset.get("archetype"),
                          authored_metrics=asset.get("world_metrics"), gate_reasons=[], meta=meta,
                          stages=[{"name": "bake", "ms": bake_ms}],
                          texture_mode=texture_mode, calibration=calibration)
    # Deterministic OUTPUT-verify artifact: project the build_log warnings into a per-stage report;
    # verification_report.ok == build_log.ok by construction (both = "no severity==error").
    from verification_report import write_report
    from build_log import file_sha256
    vrep = write_report(out / "verification_report.json", variant_id, texture_mode, log["warnings"], log["ok"])
    if not vrep["ok_agrees_with_build_log"]:
        print("WARN: verification_build_log_disagree -- verification_report.ok != build_log.ok")
    # Texture/UV provenance for the shipped manifest (ADR-0029): real_albedo is true ONLY for real
    # painted art (textured AND not calibration), computed at this single site so it can never leak.
    bc = (asset.get("textures") or {}).get("base_color")
    bc_path = (base / bc) if bc else None
    tex_block = {
        "texture_mode": texture_mode,
        "has_bound_tex": texture_mode == "textured",
        "real_albedo": (texture_mode == "textured") and not calibration,
        "calibration_texture": bool(calibration),
        "basecolor_sha256": (file_sha256(bc_path) or {}).get("sha256") if (bc_path and bc_path.exists()) else None,
        "degenerate_uv_materials": sorted(meta.get("degenerate_uv_materials", [])),
        "flat_fallback": False,
        "uv_repaired": bool(auto_rigged_from is not None and texture_mode == "textured"),
    }
    # Self-describing provenance in the shipped manifest: which model+clips+rig+lockfiles+texture made it.
    block = stamp_provenance(out / "manifest.json", asset_path=manifest_path, mesh=mesh_path,
                             clips=clips_path, rig=rig,
                             lockfile_hashes=compute_individual_hashes(PIPELINE_ROOT / "lockfiles"),
                             texture=tex_block)
    manifest["provenance"] = block

    # === SPRITE_DEBUG troubleshooting dump (spiking/discovery phase ONLY -- delete this block later) ===
    # Set the env var SPRITE_DEBUG=1 to drop an out/_debug/diagnostics.json with everything useful for
    # debugging BOTH the model the producer shipped and what the bake decided. Off by default; never
    # affects the shipped package. Remove this block (grep SPRITE_DEBUG) once the pipeline is stable.
    if os.environ.get("SPRITE_DEBUG"):
        try:
            from glb_texture_probe import texture_capable
            dbg = out / "_debug"
            dbg.mkdir(parents=True, exist_ok=True)
            try:
                tc_ok, tc_reasons, tc_rec = texture_capable(str(auto_rigged_from or mesh_path))
            except Exception as _e:
                tc_ok, tc_reasons, tc_rec = None, [f"probe_error:{_e}"], None
            diag = {
                "marker": "SPRITE_DEBUG_DIAGNOSTICS (spiking phase -- safe to delete)",
                "variant_id": variant_id, "route": route, "bake_ms": bake_ms,
                "texture_mode": texture_mode, "calibration": calibration,
                "texture_capable": {"ok": tc_ok, "reasons": tc_reasons, "record": tc_rec},
                "texture_provenance": tex_block,
                "render_signals": {k: meta.get(k) for k in
                                   ("degenerate_uv_materials", "base_color_linked_materials",
                                    "region_fallback_materials", "missing_clips", "blender_version")},
                "verification_report": {"ok": vrep["ok"], "errors": vrep["errors"], "warnings": vrep["warnings"]},
                "build_log_ok": log["ok"], "git": log["environment"]["git"],
            }
            (dbg / "diagnostics.json").write_text(json.dumps(diag, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"  [SPRITE_DEBUG] -> {dbg / 'diagnostics.json'}")
        except Exception as _e:
            print(f"  [SPRITE_DEBUG] diagnostics dump failed: {_e}")
    # === end SPRITE_DEBUG block ===

    nwarn = len(log["warnings"])
    tail = f"  [{nwarn} warning(s): {', '.join(sorted({w['code'] for w in log['warnings']}))}]" if nwarn else ""
    print(f"BAKE_ASSET OK [{route}]: {variant_id} -> {out}  ({len(manifest['frames'])} frames){tail}")
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
