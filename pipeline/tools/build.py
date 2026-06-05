#!/usr/bin/env python3
"""Single build + verify entrypoint for the sprite pipeline harness.

Runs the full gate in order and exits nonzero if any step fails. `validate` runs
last so the written report matches the final regenerated output.

  python pipeline/tools/build.py        # full sub-tool output
  python pipeline/tools/build.py --ci   # one PASS/FAIL line per step + summary
"""
# Status: R1 (render3d) is implemented and this 8-step gate is green. The forward plan
# R2-R6 is spec-resolved in docs/build_plan_R1_R6_review.md (authoritative; R-naming).
# New gates are appended to STEPS as slices land: Gate-1 (engine-acceptance) in R2;
# Gate-2 (direction) + Gate-3 (elevation/foreshortening) in R3.
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
