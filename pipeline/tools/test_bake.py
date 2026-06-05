#!/usr/bin/env python3
"""Test: bake.py renders a procedural mesh into an engine-accepted package (R2).

Bakes to a temp dir (no committed output) and asserts Gate-1 (engine acceptance)
passes — proving the render3d -> pack -> engine-shaped-manifest path is loadable.

Run: python pipeline/tools/test_bake.py   (exit 0 = all pass)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake import bake  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        for mesh in ("cube", "pole"):
            manifest = bake(mesh, Path(td) / f"{mesh}_probe", canvas_px=256)
            errors = engine_accept(manifest)
            ok &= check(f"bake '{mesh}' -> engine-accepted package", not errors)
            if errors:
                for e in errors:
                    print("   ", e)
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
