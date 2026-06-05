#!/usr/bin/env python3
"""Fixture-driven validator tests (M1/M2 slice P1).

Builds each case in pipeline/tests/fixtures/invalid_cases.json over a fresh copy
of the generated pilot output and asserts the validator rejects it (ok=false)
with an error containing the case's expect_error_substring. Also asserts the
unmutated pilot validates (ok=true). The real output is never mutated.

Run: python pipeline/tools/test_fixtures.py   (exit 0 = all pass)
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
OUTPUT = PIPELINE_ROOT / "output" / "arrow_pilot"
CASES = PIPELINE_ROOT / "tests" / "fixtures" / "invalid_cases.json"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from generate_arrow_pilot import main as generate_main  # noqa: E402
from validate_manifest import validate_manifest  # noqa: E402


def _regenerate() -> None:
    old = sys.argv[:]
    try:
        sys.argv = ["generate_arrow_pilot.py", "--pipeline-root", str(PIPELINE_ROOT),
                    "--output", str(OUTPUT), "--clean"]
        generate_main()
    finally:
        sys.argv = old


def _nav(obj, path):
    for p in path[:-1]:
        obj = obj[p]
    return obj, path[-1]


def _first_pixel_in_rect(predicate, rect):
    rx, ry, rw, rh = rect
    for y in range(ry, ry + rh):
        for x in range(rx, rx + rw):
            if predicate(x, y):
                return x, y
    return None


def _apply(case, manifest_path: Path) -> None:
    kind = case["kind"]
    if kind in ("manifest_set", "manifest_delete"):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        parent, last = _nav(data, case["path"])
        if kind == "manifest_set":
            parent[last] = case["value"]
        else:
            del parent[last]
        manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return

    base = manifest_path.parent
    rect = json.loads(manifest_path.read_text(encoding="utf-8"))["frames"][0]["rect"]
    mask_path = base / "hitmask_atlas.png"
    mask = Image.open(mask_path).convert("L")
    mpx = mask.load()
    if kind == "mask_region_pixel":
        hit = _first_pixel_in_rect(lambda x, y: mpx[x, y] == case["region_value"], rect)
        if hit is None:
            raise RuntimeError(f"{case['name']}: no pixel with value {case['region_value']} in frame rect")
        mpx[hit[0], hit[1]] = case["new_value"]
    elif kind == "mask_transparent_pixel":
        cpx = Image.open(base / "color_atlas.png").convert("RGBA").load()
        hit = _first_pixel_in_rect(lambda x, y: cpx[x, y][3] < 8 and mpx[x, y] == 0, rect)
        if hit is None:
            raise RuntimeError(f"{case['name']}: no transparent / mask-0 pixel in frame rect")
        mpx[hit[0], hit[1]] = case["new_value"]
    else:
        raise ValueError(f"unknown case kind {kind!r}")
    mask.save(mask_path)


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    _regenerate()
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    ok = True

    # Valid: the unmutated pilot must validate.
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "arrow_pilot"
        shutil.copytree(OUTPUT, dst)
        report = validate_manifest(dst / "manifest.json", PIPELINE_ROOT)
        ok &= check("valid fixture accepted (ok=true)", report["ok"])

    # Invalid: each must be rejected with the expected error substring.
    for case in cases:
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "arrow_pilot"
            shutil.copytree(OUTPUT, dst)
            try:
                _apply(case, dst / "manifest.json")
                report = validate_manifest(dst / "manifest.json", PIPELINE_ROOT)
                passed = (not report["ok"]) and any(
                    case["expect_error_substring"] in e for e in report["errors"])
            except Exception as exc:  # noqa: BLE001
                print(f"  ({case['name']} raised {type(exc).__name__}: {exc})")
                passed = False
            ok &= check(f"invalid '{case['name']}' rejected for {case['expect_error_substring']!r}", passed)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
