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
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
SCHEMA = PIPELINE_ROOT / "schema" / "external_asset.schema.json"
RIG_DIR = PIPELINE_ROOT / "schema" / "rig_profiles"


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

    if asset.get("region_source", "material_name") in ("vertex_attribute", "region_texture"):
        print(f"NOTE: region_source={asset['region_source']} is a documented extension; "
              "only material_name bakes today.")

    for state, spec in (asset.get("animations") or {}).items():
        if spec.get("playback") not in ("loop", "once", "hold"):
            errs.append(f"animations.{state}.playback must be loop|once|hold")
        if not (isinstance(spec.get("frames"), int) and spec["frames"] >= 1):
            errs.append(f"animations.{state}.frames must be an integer >= 1")
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
