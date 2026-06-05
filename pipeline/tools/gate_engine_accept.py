#!/usr/bin/env python3
"""Gate 1 — engine acceptance: would the engine loader accept this manifest? (R2)

Validates a manifest against the VENDORED engine schema
(pipeline/schema/engine/manifest.schema.json — the exact contract the engine loader
`crates/client_bevy/src/sprite.rs::parse_manifest` enforces) PLUS the two cross-field
rules the schema cannot express: `frames.len == direction_count`, and directions
`0..N-1` unique + fully covered (and each `rect` w,h > 0).

Run: python pipeline/tools/gate_engine_accept.py [manifest.json]   (exit 0 = accepted)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
ENGINE_SCHEMA = PIPELINE_ROOT / "schema" / "engine" / "manifest.schema.json"


def engine_accept(manifest: dict) -> list[str]:
    """Return a list of reasons the engine loader would reject the manifest (empty = accepted)."""
    errors: list[str] = []
    schema = json.loads(ENGINE_SCHEMA.read_text(encoding="utf-8"))
    for e in sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: list(e.path)):
        errors.append(f"schema /{'/'.join(map(str, e.path))}: {e.message}")

    dc = manifest.get("direction_count")
    frames = manifest.get("frames", []) or []
    if isinstance(dc, int) and dc > 0:
        if len(frames) != dc:
            errors.append(f"frames ({len(frames)}) must equal direction_count ({dc})")
        dirs = sorted(f["direction"] for f in frames if isinstance(f.get("direction"), int))
        if dirs != list(range(dc)):
            errors.append(f"directions must be 0..{dc - 1} unique+covered (got {dirs})")
    for f in frames:
        rect = f.get("rect", [])
        if not (len(rect) == 4 and rect[2] > 0 and rect[3] > 0):
            errors.append(f"frame dir {f.get('direction')}: rect w,h must be > 0 (got {rect})")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate 1: engine-acceptance of a manifest.")
    ap.add_argument("manifest", type=Path, nargs="?",
                    default=PIPELINE_ROOT / "output" / "arrow_pilot" / "manifest.json")
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = engine_accept(manifest)
    if errors:
        print(f"GATE 1 FAIL: engine would reject {args.manifest.name} ({len(errors)} reason(s))")
        for e in errors:
            print("   ", e)
        return 1
    print(f"GATE 1 PASS: engine would accept {args.manifest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
