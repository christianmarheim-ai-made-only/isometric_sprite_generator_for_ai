#!/usr/bin/env python3
"""Single build + verify entrypoint for the sprite pipeline harness.

Runs the full gate in order and exits nonzero if any step fails. `validate` runs
last so the written report matches the final regenerated output.

  python pipeline/tools/build.py        # full sub-tool output
  python pipeline/tools/build.py --ci   # one PASS/FAIL line per step + summary
"""
# Status: R1-R7 implemented and this gate is green (14 steps; the R7 Blender step skips where
# Blender is absent). Plan: docs/build_plan_R1_R6_review.md + multistate_sprite_contract.md.
# Gate-1 (engine-acceptance) R2; Gate-2/Gate-3 R3; bake/character (test_bake) R2/R4;
# multi-state + tight-crop (test_multistate) R5; cargo engine load-test (test_engine_load ->
# bevy_reference) R6; Blender<->render3d parity (test_blender_parity) R7.
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
OUTPUT = PIPELINE_ROOT / "output" / "arrow_pilot"

STEPS = [
    ("generate", [str(SCRIPT_DIR / "generate_arrow_pilot.py"), "--clean"]),
    ("smoke_test", [str(SCRIPT_DIR / "smoke_test.py")]),
    ("test_contract_hash", [str(SCRIPT_DIR / "test_contract_hash.py")]),
    ("test_mask_discrete", [str(SCRIPT_DIR / "test_mask_discrete.py")]),
    ("test_fixtures", [str(SCRIPT_DIR / "test_fixtures.py")]),
    ("test_lint_source", [str(SCRIPT_DIR / "test_lint_source.py")]),
    ("test_render3d", [str(SCRIPT_DIR / "test_render3d.py")]),
    ("validate", [
        str(SCRIPT_DIR / "validate_manifest.py"),
        str(OUTPUT / "manifest.json"),
        "--report", str(OUTPUT / "validation_report.json"),
    ]),
    ("gate1_engine_accept", [str(SCRIPT_DIR / "gate_engine_accept.py"), str(OUTPUT / "manifest.json")]),
    ("test_gates", [str(SCRIPT_DIR / "test_gates.py")]),
    ("test_bake", [str(SCRIPT_DIR / "test_bake.py")]),
    ("test_multistate", [str(SCRIPT_DIR / "test_multistate.py")]),
    ("test_references", [str(SCRIPT_DIR / "test_references.py")]),
    ("test_direction_distinctness", [str(SCRIPT_DIR / "test_direction_distinctness.py")]),
    ("test_mesh_input", [str(SCRIPT_DIR / "test_mesh_input.py")]),
    ("test_external_asset", [str(SCRIPT_DIR / "test_external_asset.py")]),
    ("test_schemas", [str(SCRIPT_DIR / "test_schemas.py")]),
    ("test_engine_load", [str(SCRIPT_DIR / "test_engine_load.py")]),
    ("test_blender_parity", [str(SCRIPT_DIR / "test_blender_parity.py")]),
    ("test_rigged_anim", [str(SCRIPT_DIR / "test_rigged_anim.py")]),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and verify the sprite pipeline.")
    parser.add_argument("--ci", action="store_true",
                        help="One summary line per step; suppress sub-tool stdout/stderr.")
    args = parser.parse_args()

    failures: list[str] = []
    for name, cmd in STEPS:
        proc = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
        ok = proc.returncode == 0
        if not ok:
            failures.append(name)
        if not args.ci:
            if proc.stdout:
                sys.stdout.write(proc.stdout)
            if proc.stderr:
                sys.stderr.write(proc.stderr)
        print(f"[{name}] {'PASS' if ok else 'FAIL'} (exit {proc.returncode})")

    total = len(STEPS)
    if failures:
        print(f"BUILD FAIL: {len(failures)}/{total} step(s) failed: {', '.join(failures)}")
        return 1
    print(f"BUILD PASS: {total}/{total} steps green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
