#!/usr/bin/env python3
"""The CROSS-CONSUMER gate: runs BOTH the character gate (pipeline/tools/build.py) and the world-scenery
gate (pipeline/env/build_env.py). This is the gate a change to the SHARED core (pipeline/tools generic
parts -- camera, atlas/paging, manifest, Gate-1, hitmask, clip sampling) MUST pass: the foundation only
moves when both consumers standing on it still stand. A character-only change need only pass build.py; a
scenery-only change need only pass build_env.py.

  python pipeline/env/build_all.py [--ci]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATES = [("character (build.py)", ROOT / "pipeline" / "tools" / "build.py"),
         ("scenery (build_env.py)", ROOT / "pipeline" / "env" / "build_env.py")]


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-consumer gate (character + scenery).")
    ap.add_argument("--ci", action="store_true")
    args = ap.parse_args()
    failed = []
    for name, path in GATES:
        print(f"\n===== {name} =====")
        cmd = [sys.executable, str(path)] + (["--ci"] if args.ci else [])
        if subprocess.run(cmd).returncode != 0:
            failed.append(name)
    if failed:
        print(f"\nBUILD_ALL FAIL: {', '.join(failed)}")
        return 1
    print("\nBUILD_ALL PASS: character + scenery gates both green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
