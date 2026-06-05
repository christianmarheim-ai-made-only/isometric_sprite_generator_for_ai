#!/usr/bin/env python3
"""Gate 1 — engine acceptance: would the engine loader accept this manifest? (R2)

Validates a manifest against the VENDORED engine schema
(pipeline/schema/engine/manifest.schema.json — the engine team's PUBLISHED contract)
PLUS the cross-field rules JSON Schema cannot express, mirroring the loader
`crates/client_bevy/src/sprite.rs::parse_manifest` + the multi-state contract:
  - single-state: frames.len == direction_count, directions 0..N-1 unique + covered;
  - multi-state (animations present): per (state,direction) frame_index 0..frames-1
    unique+covered, animations[state].directions == direction_count, total frame count;
  - each rect w,h > 0 and within the color atlas;
  - eye_height_world <= height_world for non-probe variants (WorldMetrics::validate).

Fidelity note: the vendored schema is the engine's published contract and is in a few
places STRICTER than the bare loader (direction_count enum [1,2,4,8,16] vs the loader's
>0; world_metrics value floors and the variant_class enum apply to all variants, while
the loader ignores a probe's metrics). Those are all in the SAFE (false-reject)
direction, so the gate never admits a manifest the loader would reject.

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


def _frame_label(f: dict) -> str:
    if "state" in f:
        return f"frame ({f.get('state')},dir{f.get('direction')},f{f.get('frame_index')})"
    return f"frame dir {f.get('direction')}"


def _multistate_errors(dc: int, frames: list, animations: dict, default_state) -> list[str]:
    """Coverage rules for the multi-state contract (multistate_sprite_contract.md)."""
    errs: list[str] = []
    if default_state is not None and default_state not in animations:
        errs.append(f"default_state {default_state!r} is not an animations key")
    for state, spec in animations.items():
        if spec.get("directions") != dc:
            errs.append(f"animations.{state}.directions ({spec.get('directions')}) must equal direction_count ({dc})")
        if not (isinstance(spec.get("frames"), int) and spec["frames"] > 0):
            errs.append(f"animations.{state}.frames must be a positive integer")
        if spec.get("playback") not in ("loop", "once"):
            errs.append(f"animations.{state}.playback must be loop|once (got {spec.get('playback')!r})")
    for f in frames:
        if f.get("state") not in animations:
            errs.append(f"frame references unknown state {f.get('state')!r}")
            break
    seen: dict = {}
    for f in frames:
        seen.setdefault((f.get("state"), f.get("direction")), []).append(f.get("frame_index"))
    total = 0
    for state, spec in animations.items():
        fr = spec.get("frames")
        if not (isinstance(fr, int) and fr > 0):
            continue
        total += dc * fr
        for d in range(dc):
            got = sorted(v for v in seen.get((state, d), []) if isinstance(v, int))
            if got != list(range(fr)):
                errs.append(f"state {state!r} dir {d}: frame_index must be 0..{fr - 1} unique+covered (got {got})")
    if len(frames) != total:
        errs.append(f"frames ({len(frames)}) must equal sum over states of directions*frames ({total})")
    return errs


def engine_accept(manifest: dict) -> list[str]:
    """Return a list of reasons the engine loader would reject the manifest (empty = accepted)."""
    errors: list[str] = []
    schema = json.loads(ENGINE_SCHEMA.read_text(encoding="utf-8"))
    for e in sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: list(e.path)):
        errors.append(f"schema /{'/'.join(map(str, e.path))}: {e.message}")

    dc = manifest.get("direction_count")
    frames = manifest.get("frames", []) or []
    animations = manifest.get("animations")

    if animations:  # multi-state contract
        if isinstance(dc, int) and dc > 0:
            errors += _multistate_errors(dc, frames, animations, manifest.get("default_state"))
        else:
            errors.append("direction_count must be a positive integer")
    elif isinstance(dc, int) and dc > 0:  # legacy single-state: one frame per direction
        if len(frames) != dc:
            errors.append(f"frames ({len(frames)}) must equal direction_count ({dc})")
        dirs = sorted(f["direction"] for f in frames if isinstance(f.get("direction"), int))
        if dirs != list(range(dc)):
            errors.append(f"directions must be 0..{dc - 1} unique+covered (got {dirs})")

    # rect w,h > 0 and within the color atlas (mirrors the loader bounds check), every frame.
    size = (((manifest.get("atlases") or {}).get("color") or {}).get("size")) or [0, 0]
    aw, ah = (list(size) + [0, 0])[:2]
    for f in frames:
        rect = f.get("rect", [])
        if not (len(rect) == 4 and rect[2] > 0 and rect[3] > 0):
            errors.append(f"{_frame_label(f)}: rect w,h must be > 0 (got {rect})")
        elif isinstance(aw, int) and aw > 0 and (rect[0] + rect[2] > aw or rect[1] + rect[3] > ah):
            errors.append(f"{_frame_label(f)}: rect {rect} exceeds the atlas {aw}x{ah}")

    # Non-probe variants: the engine rejects eye_height_world > height_world.
    if manifest.get("variant_class") != "probe":
        wm = manifest.get("world_metrics") or {}
        h, e = wm.get("height_world"), wm.get("eye_height_world")
        if isinstance(h, (int, float)) and isinstance(e, (int, float)) and e > h:
            errors.append(f"world_metrics.eye_height_world ({e}) must be <= height_world ({h})")
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
