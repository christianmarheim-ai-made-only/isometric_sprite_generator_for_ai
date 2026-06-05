#!/usr/bin/env python3
"""Tests for the source-asset linter v1 (P4).

Lints the committed arrow_probe fixtures: the valid descriptor must lint clean
(no errors), and each broken descriptor must error with the expected substring.

Run: python pipeline/tools/test_lint_source.py   (exit 0 = all pass)
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
FIX = PIPELINE_ROOT / "tests" / "fixtures" / "source"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lint_source_asset import lint  # noqa: E402

EXPECT = [
    ("arrow_probe.valid.json", None),
    ("arrow_probe.bad_forward_axis.json", "forward_axis must be +X"),
    ("arrow_probe.bad_units.json", "units must be meter"),
    ("arrow_probe.bad_region.json", "deferred this iteration"),
    ("arrow_probe.missing_origin_socket.json", "required socket 'origin'"),
    ("arrow_probe.bad_prefix.json", "must start with VIS_"),
]


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    for name, expect in EXPECT:
        r = lint(FIX / name)
        if expect is None:
            ok &= check(f"{name} lints clean (no errors)", not r.errors)
        else:
            ok &= check(f"{name} errors with {expect!r}",
                        bool(r.errors) and any(expect in e for e in r.errors))
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
