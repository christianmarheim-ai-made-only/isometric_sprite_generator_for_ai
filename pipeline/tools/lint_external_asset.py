#!/usr/bin/env python3
"""Validate an EXTERNAL asset manifest against the contract (docs/external_asset_contract.md),
so an external producer (an art/animation AI or a human artist) gets actionable feedback BEFORE
delivery -- this is the front door for external inputs.

Checks (no Blender needed): schema (schema/external_asset.schema.json); declared files exist;
`rig` (if present) is a known profile (schema/rig_profiles/<rig>.json); region_source is
supported; animations are well-formed. The deep geometry/rig/clip validation happens when the
asset is actually baked (bake.py / blender_bake.py).

  python pipeline/tools/lint_external_asset.py asset.asset.json [--no-files]
exit 0 = OK.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
SCHEMA = PIPELINE_ROOT / "schema" / "external_asset.schema.json"
RIG_DIR = PIPELINE_ROOT / "schema" / "rig_profiles"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from constants import offvocab_clip_renames, CLIP_REQUIREMENTS  # noqa: E402
from waivers import validate as validate_waivers  # noqa: E402


def lint(path: Path, check_files: bool = True, today: str | None = None) -> list[str]:
    """Return a list of contract violations for an asset manifest (empty = OK).

    `today` is the injectable ISO `YYYY-MM-DD` lint date the waiver-expiry checks measure against
    (defaults to date.today() -- tests pass an explicit date)."""
    errs: list[str] = []
    asset = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for e in sorted(Draft202012Validator(schema).iter_errors(asset), key=lambda e: list(e.path)):
        errs.append(f"schema /{'/'.join(map(str, e.path))}: {e.message}")
    if errs:
        return errs  # structure broken; deeper checks would just be noise

    # --- WAIVER front door (review snippet 07; ADR-0028/0031): validate any declared waivers BEFORE
    # any bake. An expired / unknown-or-non-waivable code / real-albedo-claiming waiver is rejected
    # here (waiver_expired / waiver_unknown_code / waiver_missing / waiver_attempts_real_albedo_true),
    # so a package can never carry a stale or over-broad waiver into the baker. ---
    today_iso = today or date.today().isoformat()
    for we in validate_waivers(asset.get("waivers"), today_iso):
        errs.append(f"{we['code']}: {we['detail']}")

    base = Path(path).parent
    if check_files:
        for kind, rel in (asset.get("files") or {}).items():
            if isinstance(rel, str) and not (base / rel).exists():        # skip non-path values
                errs.append(f"files.{kind}: '{rel}' not found (relative to the manifest)")
        for kind, rel in (asset.get("textures") or {}).items():
            if isinstance(rel, str) and not (base / rel).exists():        # textures may carry real_albedo:bool
                errs.append(f"textures.{kind}: '{rel}' not found")

    rig = asset.get("rig")
    if rig and not (RIG_DIR / f"{rig}.json").exists():
        known = sorted(p.stem for p in RIG_DIR.glob("*.json"))
        errs.append(f"rig '{rig}' is not a known profile (have: {known})")

    # if an anim_clips_v1 JSON is paired with the mesh, validate it against its schema too
    clips_rel = (asset.get("files") or {}).get("animation_clips")
    if clips_rel and check_files:
        clips_path = base / clips_rel
        if clips_path.exists():
            ac_schema = json.loads((PIPELINE_ROOT / "schema" / "animation_clips.schema.json").read_text(encoding="utf-8"))
            clips = json.loads(clips_path.read_text(encoding="utf-8"))
            for e in sorted(Draft202012Validator(ac_schema).iter_errors(clips), key=lambda e: list(e.path)):
                errs.append(f"files.animation_clips /{'/'.join(map(str, e.path))}: {e.message}")
            if clips.get("rig") and rig and clips["rig"] != rig:
                errs.append(f"files.animation_clips rig '{clips['rig']}' != asset rig '{rig}'")

    if asset.get("region_source", "material_name") == "vertex_attribute":
        print("NOTE: region_source=vertex_attribute is a documented extension; not baked today "
              "(material_name, region_texture, and explicit_region_hitboxes are implemented).")

    for state, spec in (asset.get("animations") or {}).items():
        if spec.get("playback") not in ("loop", "once"):
            errs.append(f"animations.{state}.playback must be loop|once")
        if not (isinstance(spec.get("frames"), int) and spec["frames"] >= 1):
            errs.append(f"animations.{state}.frames must be an integer >= 1")
    # Clip-vocabulary WARNING (non-aborting): a clip named off the engine's vocabulary (move/shoot/hurt)
    # bakes fine but the renderer never selects it -> it silently falls back to idle. Catch the rename.
    for declared, canon in offvocab_clip_renames(list((asset.get("animations") or {}).keys())):
        print(f"WARN: animation '{declared}' is off the engine clip vocabulary -- the renderer selects "
              f"'{canon}' for that action and falls back to idle for '{declared}'. Rename '{declared}' -> '{canon}'.")

    # --- ANIMATION gate (ADR-0031): an ANIMATED delivery must declare its archetype's REQUIRED clip(s).
    # Static (no-animations) deliveries are unaffected. Off-vocab synonyms count as their canonical name. ---
    anim_keys = list((asset.get("animations") or {}).keys())
    if anim_keys:
        _canon = dict(offvocab_clip_renames(anim_keys))
        present = {str(k).lower() for k in anim_keys} | {_canon.get(k, k) for k in anim_keys}
        for req in CLIP_REQUIREMENTS.get(asset.get("archetype"), {}).get("required", ["idle"]):
            if req not in present:
                errs.append(f"missing_required_clip: archetype '{asset.get('archetype')}' requires clip "
                            f"'{req}' but it is not declared (have {sorted(set(anim_keys))})")

    # --- SKINNING gate (ADR-0031): if a *_skin_binding.json sidecar is shipped, every part must bind a
    # REAL rig bone (catches a mis-named / non-existent bone statically, before any bake). ---
    if check_files and rig:
        _sb = base / f"{asset.get('variant_id')}_skin_binding.json"
        _prof = RIG_DIR / f"{rig}.json"
        if _sb.exists() and _prof.exists():
            _bones = {b["name"] for b in json.loads(_prof.read_text(encoding="utf-8")).get("bones", [])}
            for part, a in (json.loads(_sb.read_text(encoding="utf-8")).get("assignments") or {}).items():
                if isinstance(a, dict) and a.get("bone") not in _bones:
                    errs.append(f"missing_required_bone: skin_binding part '{part}' -> bone "
                                f"'{a.get('bone')}' is not in rig '{rig}'")

    # --- texture_mode INPUT GATE (ADR-0026; additive -- engages only when the producer DECLARES it) ---
    # Absent texture_mode == flat_region (back-compat), so existing v1 assets are unaffected. A
    # 'textured' delivery must be texture-capable (real UVs + a bound baseColorTexture) BEFORE any
    # bake, so an orphan atlas / collapsed UVs are rejected at the front door, never baked flat.
    texture_mode = asset.get("texture_mode", "flat_region")
    mesh_rel = (asset.get("files") or {}).get("mesh", "")
    if texture_mode == "textured":
        if mesh_rel.lower().endswith(".obj"):
            errs.append("obj_textured_unsupported: a textured package must be GLB/GLTF with real UVs "
                        "and a bound baseColorTexture (.obj is only for static flat_region assets)")
        elif check_files and mesh_rel and (base / mesh_rel).suffix.lower() in (".glb", ".gltf") and (base / mesh_rel).exists():
            try:
                from glb_texture_probe import texture_capable
                cap, reasons, rec = texture_capable(str(base / mesh_rel))
                if not cap:
                    for code in reasons:
                        errs.append(f"{code}: texture_mode=textured but the GLB is not texture-capable "
                                    f"(prims={rec['primitives']} no_uv={rec['no_uv']} "
                                    f"degenerate_uv={len(rec['degenerate_uv'])} bound_tex={rec['bound_textures']}). "
                                    f"A real UV unwrap + a bound baseColorTexture are required (ADR-0026).")
            except Exception as ex:
                errs.append(f"texture_capable probe failed on '{mesh_rel}': {ex}")
    elif texture_mode == "flat_region":
        prov = ((asset.get("provenance") or {}).get("texture") or {})
        if prov.get("real_albedo") is True:
            errs.append("flat_region_real_albedo: a flat_region package must not claim real_albedo:true")
        # flat_region = flat per-region colours via MATERIAL base colours. A bound base-colour texture is
        # the "flat-via-degenerate-UV-texture" hack (looks textured, bakes ~one texel/material): reject it.
        if check_files and mesh_rel and (base / mesh_rel).suffix.lower() in (".glb", ".gltf") and (base / mesh_rel).exists():
            try:
                from glb_texture_probe import texture_capable
                _cap, _reasons, rec = texture_capable(str(base / mesh_rel))
                bound = rec.get("bound_textures", 0)
                prims, degen = rec.get("primitives", 0), len(rec.get("degenerate_uv", []))
                if isinstance(bound, int) and bound > 0:
                    hint = (f" and every material's UVs are degenerate ({degen}/{prims}) -> the texture "
                            "contributes ~one texel per part") if degen and degen >= prims else ""
                    errs.append(f"flat_region_bound_texture: a flat_region delivery binds {bound} base-colour "
                                f"texture(s){hint}. flat_region uses material base colours, not a texture -- "
                                "drop the texture, or declare texture_mode=textured with a real UV unwrap.")
            except Exception as ex:
                errs.append(f"texture_capable probe failed on '{mesh_rel}': {ex}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint an external asset manifest against external_asset_v2.")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--no-files", action="store_true", help="skip file-existence checks (template mode)")
    args = ap.parse_args()
    errs = lint(args.manifest, check_files=not args.no_files)
    if errs:
        print(f"ASSET LINT FAIL: {args.manifest.name} ({len(errs)} issue(s))")
        for e in errs:
            print("   ", e)
        return 1
    print(f"ASSET LINT OK: {args.manifest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
