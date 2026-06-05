#!/usr/bin/env python3
"""Regression test for hitmask discreteness (M1/M2 Fix 2).

The R8 hitmask atlas must contain only discrete region IDs from the manifest
palette (plus 0/none). Edge extrusion must never interpolate region IDs into
in-between values. This regenerates the pilot, then scans the whole hitmask
atlas -- including the extruded gutters, which is exactly where a blending
resize would show up.

Run: python pipeline/tools/test_mask_discrete.py   (exit 0 = pass)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from generate_arrow_pilot import main as generate_main  # noqa: E402

PIPELINE_ROOT = SCRIPT_DIR.parent
OUTPUT = PIPELINE_ROOT / "output" / "arrow_pilot"


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    # Regenerate deterministically so the test does not depend on prior state.
    old_argv = sys.argv[:]
    try:
        sys.argv = ["generate_arrow_pilot.py", "--pipeline-root", str(PIPELINE_ROOT), "--output", str(OUTPUT), "--clean"]
        generate_main()
    finally:
        sys.argv = old_argv

    manifest = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))
    palette = manifest["atlases"]["hitmask"]["palette"]
    allowed = set(palette.values()) | {0}

    mask_atlas = Image.open(OUTPUT / "hitmask_atlas.png")
    ok = check("hitmask atlas mode is L/R8", mask_atlas.mode == "L")
    # getcolors returns (count, value) for every distinct value in an L image;
    # maxcolors well above 256 guarantees a non-None result.
    colors = mask_atlas.getcolors(maxcolors=512) or []
    seen = {value for _count, value in colors}
    bad = seen - allowed
    ok &= check(
        f"hitmask atlas values {sorted(seen)} subset of palette {sorted(allowed)}",
        not bad,
    )

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
