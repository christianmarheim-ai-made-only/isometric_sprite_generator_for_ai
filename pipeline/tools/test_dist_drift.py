#!/usr/bin/env python3
"""Guard: the shipped model-authoring contract zip must match a FRESH stage() of the live
pipeline docs/schemas/examples. Catches the shipped contract silently rotting to a stale set
(e.g. a 4-clip example template after the source moved to 9 clips). Pure Python, no Blender.

Run: python pipeline/tools/test_dist_drift.py
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
REPO = PIPELINE_ROOT.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from package_authoring_contract import stage  # noqa: E402

ZIP = REPO / "dist" / "model_authoring_contract_v1.zip"
BASE = "model_authoring_contract_v1"  # the zip's top dir (make_archive base_dir)


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    if not ZIP.exists():
        print(f"FAIL: committed contract zip missing: {ZIP}")
        return 1
    ok = True
    with tempfile.TemporaryDirectory() as td:
        fresh = Path(td) / "fresh"
        stage(fresh)
        fresh_tree = _tree(fresh)

        ext = Path(td) / "ext"
        with zipfile.ZipFile(ZIP) as z:
            z.extractall(ext)
        zip_tree = _tree(ext / BASE)

    ok &= check(f"file set matches fresh stage ({len(fresh_tree)} files)",
                set(fresh_tree) == set(zip_tree))
    miss = sorted(set(fresh_tree) - set(zip_tree))
    extra = sorted(set(zip_tree) - set(fresh_tree))
    if miss:
        print(f"  in fresh-stage but MISSING from zip: {miss}")
    if extra:
        print(f"  in zip but NOT in fresh-stage (stale): {extra}")
    diff = sorted(f for f in (set(fresh_tree) & set(zip_tree)) if fresh_tree[f] != zip_tree[f])
    ok &= check("file contents match", not diff)
    if diff:
        print(f"  CONTENT DRIFT in: {diff}")
    if not ok:
        print("DIST DRIFT: re-run `python pipeline/tools/package_authoring_contract.py` and commit the zip.")
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
