#!/usr/bin/env python3
"""Gate: every committed schema validates the real artifacts it governs, and rejects malformed input.

Catches schema-vs-reality drift (the output schema must accept the manifests the pipeline actually
emits; the authoring schemas must accept their examples). Pure-Python (jsonschema), always runs.

  python pipeline/tools/test_schemas.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
SCHEMA = PIPELINE_ROOT / "schema"
EX = PIPELINE_ROOT / "examples"
REF = PIPELINE_ROOT / "reference"
OUT = PIPELINE_ROOT / "output"


def errs_for(schema_path: Path, data: dict) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return [f"/{'/'.join(map(str, e.path))}: {e.message}"
            for e in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))]


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}: {label}{('  -> ' + detail) if detail and not ok else ''}")
    return ok


def main() -> int:
    ok = True
    pairs = [
        (SCHEMA / "external_asset.schema.json",
         sorted(EX.glob("*.asset.json")) + [EX / "texture_starter" / "humanoid_textured.asset.json"]),
        (SCHEMA / "animation_clips.schema.json", [EX / "animation" / "bird_v1_anim.json"]),
        (SCHEMA / "hitbox_spec.schema.json", [EX / "hitbox" / "humanoid_hitbox.json"]),
        (SCHEMA / "sprite_manifest.schema.json",
         sorted(REF.glob("*/manifest.json")) + [OUT / "arrow_pilot" / "manifest.json"]),
    ]
    for schema_path, data_paths in pairs:
        for dp in data_paths:
            if not dp.exists():
                continue
            es = errs_for(schema_path, json.loads(dp.read_text(encoding="utf-8")))
            ok &= check(f"{schema_path.name} validates {dp.relative_to(PIPELINE_ROOT)}",
                        not es, "; ".join(es[:4]))

    # the schemas must also REJECT malformed input (not vacuous)
    bad_asset = {"asset_contract_version": "external_asset_v1", "variant_id": "Bad Caps",
                 "archetype": "dragon", "files": {}, "geometry": {"forward": "-y"}}
    ok &= check("external_asset rejects bad id/archetype/forward/missing-mesh",
                len(errs_for(SCHEMA / "external_asset.schema.json", bad_asset)) >= 3)
    bad_anim = {"anim_spec_version": "anim_clips_v1", "rig": "bird_v1",
                "clips": {"fly": {"playback": "bounce", "frames": 0, "fps": 12, "duration_frames": 6}}}
    ok &= check("anim_clips rejects bad playback + frames<1",
                len(errs_for(SCHEMA / "animation_clips.schema.json", bad_anim)) >= 2)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
