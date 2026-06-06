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
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
SCHEMA = PIPELINE_ROOT / "schema" / "external_asset.schema.json"
RIG_DIR = PIPELINE_ROOT / "schema" / "rig_profiles"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from constants import offvocab_clip_renames  # noqa: E402


def lint(path: Path, check_files: bool = True) -> list[str]:
    """Return a list of contract violations for an asset manifest (empty = OK)."""
    errs: list[str] = []
    asset = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for e in sorted(Draft202012Validator(schema).iter_errors(asset), key=lambda e: list(e.path)):
        errs.append(f"schema /{'/'.join(map(str, e.path))}: {e.message}")
    if errs:
        return errs  # structure broken; deeper checks would just be noise

    base = Path(path).parent
    if check_files:
        for kind, rel in (asset.get("files") or {}).items():
            if not (base / rel).exists():
                errs.append(f"files.{kind}: '{rel}' not found (relative to the manifest)")
        for kind, rel in (asset.get("textures") or {}).items():
            if not (base / rel).exists():
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

    if asset.get("region_source", "material_name") in ("vertex_attribute", "region_texture"):
        print(f"NOTE: region_source={asset['region_source']} is a documented extension; "
              "only material_name bakes today.")

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
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint an external asset manifest against external_asset_v1.")
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
