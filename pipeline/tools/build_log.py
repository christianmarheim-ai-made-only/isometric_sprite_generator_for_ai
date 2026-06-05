#!/usr/bin/env python3
"""Per-bake production log (sprite_build_log_v1) + per-batch index. A durable, diffable record so a
later-noticed error is troubleshootable and a fix is verifiable by `git diff` of two logs.

Surfaces the two normally-SILENT failures ("baked green but looks wrong"):
  - region_fallback_torso     a material name matched no region keyword -> silently defaulted to torso
  - missing_clip_rest_pose    a declared state's clip was absent from the glb -> rendered the rest pose
(both read from the Blender *_meta.json the renderer now emits).

Written by the PRODUCTION entry points (bake_asset.py, produce_verify_set.py) -- NOT by the core
bake_* functions, so committed reference packages (baked via bake_character*/test_references) get no
log and their byte-for-byte reproducibility check is unaffected.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from constants import MAX_PAGE_PX  # noqa: E402  (canonical per-page cap)

SCHEMA = "sprite_build_log_v1"
_GIT_COMMIT_CACHE: list = []


def file_sha256(path: Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"path": str(p), "sha256": h, "bytes": p.stat().st_size}


def git_commit() -> dict:
    if not _GIT_COMMIT_CACHE:
        info = {"commit": None, "dirty": None}
        try:
            info["commit"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                            capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip() or None
            info["dirty"] = bool(subprocess.run(["git", "status", "--porcelain"],
                                                capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip())
        except Exception:
            pass
        _GIT_COMMIT_CACHE.append(info)
    return _GIT_COMMIT_CACHE[0]


def _packing(manifest: dict):
    frames = manifest.get("frames", [])
    color = manifest.get("atlases", {}).get("color", {})
    if "pages" in color:
        page_area = sum(p["size"][0] * p["size"][1] for p in color["pages"])
        over = any(max(p["size"]) > MAX_PAGE_PX for p in color["pages"])
    elif "size" in color:
        page_area = color["size"][0] * color["size"][1]
        over = max(color["size"]) > MAX_PAGE_PX
    else:
        return None, False
    used = sum(f["rect"][2] * f["rect"][3] for f in frames if "rect" in f)
    return (round(used / page_area, 4) if page_area else None), over


def _atlases(manifest: dict) -> dict:
    out = {}
    for name, a in manifest.get("atlases", {}).items():
        out[name] = {"pages": [p["size"] for p in a["pages"]]} if "pages" in a else {"size": a.get("size")}
    return out


def _artifacts(out_dir: Path) -> dict:
    """sha256 the produced output files so a reviewer can answer 'which hitmask came from which
    model' end-to-end: inputs.mesh.sha256 -> outputs.artifacts.hitmask_atlas.sha256."""
    arts = {}
    for key, fname in (("color_atlas", "color_atlas.png"), ("hitmask_atlas", "hitmask_atlas.png")):
        h = file_sha256(out_dir / fname)
        if h:
            arts[key] = h
    return arts


def write_build_log(out_dir, manifest: dict, route: str, asset_path=None, mesh=None, clips=None,
                    rig=None, gate_reasons=None, meta: dict | None = None, stages=None) -> dict:
    """Assemble + write out_dir/build_log.json and return the log dict."""
    out_dir = Path(out_dir)
    meta = meta or {}
    gate_reasons = gate_reasons or []
    warnings = []
    for n in meta.get("region_fallback_materials", []):
        warnings.append({"code": "region_fallback_torso", "severity": "warn",
                         "detail": f"material '{n}' matched no region keyword -> silently defaulted to torso (id 2)"})
    for s in meta.get("missing_clips", []):
        warnings.append({"code": "missing_clip_rest_pose", "severity": "warn",
                         "detail": f"state '{s}': clip absent from the glb -> rendered the REST pose, not animated"})
    eff, over = _packing(manifest)
    if over:
        warnings.append({"code": "oversize_atlas_page", "severity": "error",
                         "detail": f"an atlas page exceeds {MAX_PAGE_PX}px"})

    anims = manifest.get("animations") or {}
    gate1_ok = not gate_reasons
    log = {
        "schema": SCHEMA,
        "variant_id": manifest.get("variant_id"),
        "variant_class": manifest.get("variant_class"),
        "route": route,
        "ok": gate1_ok and not any(w["severity"] == "error" for w in warnings),
        "inputs": {
            "asset_path": str(asset_path) if asset_path else None,
            "mesh": file_sha256(mesh) if mesh else None,
            "clips": file_sha256(clips) if clips else None,
            "rig": rig or manifest.get("build", {}).get("rig") or None,
        },
        "params": {
            "frame_canvas": manifest.get("frame_canvas"),
            "direction_count": manifest.get("direction_count"),
            "default_state": manifest.get("default_state"),
            "states": {s: {"frames": v.get("frames"), "fps": v.get("fps"), "playback": v.get("playback")}
                       for s, v in anims.items()} or None,
        },
        "environment": {
            "git": git_commit(),
            "blender_version": meta.get("blender_version"),
            "python": platform.python_version(),
            "contract_hash": manifest.get("contract_hash"),
            "state_contract_version": manifest.get("state_contract_version"),
        },
        "stages": stages or [],
        "outputs": {
            "frame_count": len(manifest.get("frames", [])),
            "atlases": _atlases(manifest),
            "artifacts": _artifacts(out_dir),
            "packing_efficiency": eff,
        },
        "gates": {"gate_1_engine_accept": {"pass": gate1_ok, "reasons": gate_reasons}},
        "warnings": warnings,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "build_log.json").write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return log


def stamp_provenance(manifest_path, *, asset_path=None, mesh=None, clips=None, rig=None,
                     lockfile_hashes=None, batch_id=None) -> dict:
    """Stamp a self-describing `provenance` block into a baked manifest.json (additive -- the engine
    schema is additionalProperties:true). Lets the SHIPPED package answer 'which model + clips + rig
    + lockfiles produced this' from manifest.json alone, and points at the build_log sidecar. Only
    production bakers stamp this; the committed numpy references bake through core bake.py and stay
    byte-reproducible."""
    manifest_path = Path(manifest_path)
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    block = {
        "schema": "sprite_provenance_v1",
        "batch_id": batch_id,
        "asset": file_sha256(asset_path) if asset_path else None,
        "mesh": file_sha256(mesh) if mesh else None,
        "clips": file_sha256(clips) if clips else None,
        "rig": rig,
        "contract_hash": m.get("contract_hash"),
        "lockfile_hashes": lockfile_hashes,
        "build_log": "build_log.json",
    }
    m["provenance"] = block
    manifest_path.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return block


def write_build_index(batch_dir, logs: list, batch_id=None) -> list:
    rows = []
    for l in logs:
        inp = l.get("inputs", {})
        arts = l.get("outputs", {}).get("artifacts", {})
        rows.append({
            "variant": l["variant_id"], "route": l["route"], "ok": l["ok"],
            "frames": l["outputs"]["frame_count"],
            "packing_efficiency": l["outputs"]["packing_efficiency"],
            "warnings": len(l["warnings"]),
            "commit": l["environment"]["git"].get("commit"),
            "build_log": f"{l['variant_id']}/build_log.json",
            "mesh_sha256": (inp.get("mesh") or {}).get("sha256"),
            "rig": inp.get("rig"),
            "hitmask_sha256": (arts.get("hitmask_atlas") or {}).get("sha256"),
        })
    index = {
        "schema": "sprite_build_index_v1",
        "batch_id": batch_id,
        "contract_hash": logs[0]["environment"].get("contract_hash") if logs else None,
        "commit": logs[0]["environment"]["git"].get("commit") if logs else None,
        "variant_count": len(rows),
        "variants": rows,
    }
    (Path(batch_dir) / "build_index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return rows


def index_summary(rows: list) -> str:
    out = [f"{'variant':<18} {'route':<30} {'frames':>6} {'pack':>6} {'warn':>5}  ok"]
    for r in rows:
        out.append(f"{str(r['variant']):<18} {str(r['route']):<30} {r['frames']:>6} "
                   f"{str(r['packing_efficiency']):>6} {r['warnings']:>5}  {'OK' if r['ok'] else 'FAIL'}")
    return "\n".join(out)
