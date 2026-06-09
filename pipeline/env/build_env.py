#!/usr/bin/env python3
"""The WORLD-SCENERY (env) gate -- SEPARATE from the character gate (pipeline/tools/build.py). A broken env
bake turns THIS gate red and leaves the character 42-gate green. A change to the SHARED core must pass both
(run pipeline/env/build_all.py). Env reuses pipeline/tools read-only; the dependency is strictly one-way.

  python pipeline/env/build_env.py        # full output
  python pipeline/env/build_env.py --ci   # one PASS/FAIL line per step
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ENV_DIR = Path(__file__).resolve().parent

STEPS = [
    ("env_self_test", [str(ENV_DIR / "self_test.py")]),
    # (future) env_terrain_bake, env_seamless_tiling, env_prop_hitmask, env_elevation_guard
]


def main() -> int:
    ap = argparse.ArgumentParser(description="World-scenery (env) gate.")
    ap.add_argument("--ci", action="store_true")
    args = ap.parse_args()
    failures = []
    for name, cmd in STEPS:
        proc = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(name)
        if not args.ci:
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
        print(f"[{name}] {'PASS' if proc.returncode == 0 else 'FAIL'} (exit {proc.returncode})")
    total = len(STEPS)
    if failures:
        print(f"ENV GATE FAIL: {len(failures)}/{total} step(s) failed: {', '.join(failures)}")
        return 1
    print(f"ENV GATE PASS: {total}/{total} steps green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
