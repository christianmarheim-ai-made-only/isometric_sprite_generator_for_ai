#!/usr/bin/env python3
"""Gate the COMMITTED reference packages directly (not only via the cargo load-test), and
guard against drift between a committed package and its generator (R1-R7 review fixes).

  - Gate-1 (engine acceptance) on every committed reference manifest -- pure Python, so a
    corrupted committed humanoid_ref/anim/blender FAILS build.py even where cargo is absent.
  - Determinism: re-bake the numpy references (humanoid_ref, humanoid_anim) to a temp dir and
    assert the manifest is JSON-identical to the committed one (no silent drift).

Run: python pipeline/tools/test_references.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake import bake_character, bake_character_anim  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402

REF = PIPELINE_ROOT / "reference"


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    for name in ("humanoid_ref", "humanoid_anim", "humanoid_blender"):
        mpath = REF / name / "manifest.json"
        if not mpath.exists():
            ok &= check(f"committed reference {name} present", False)
            continue
        errs = engine_accept(json.loads(mpath.read_text(encoding="utf-8")))
        ok &= check(f"committed {name} engine-accepted (Gate-1)", not errs)
        for e in errs:
            print("   ", e)

    # Drift guard: the numpy references must reproduce JSON-identically (they are deterministic).
    with tempfile.TemporaryDirectory() as td:
        fresh_ref = bake_character(Path(td) / "r", 256)
        committed_ref = json.loads((REF / "humanoid_ref" / "manifest.json").read_text(encoding="utf-8"))
        ok &= check("humanoid_ref reproducible (committed == fresh bake)", fresh_ref == committed_ref)
        fresh_anim = bake_character_anim(Path(td) / "a", 256)
        committed_anim = json.loads((REF / "humanoid_anim" / "manifest.json").read_text(encoding="utf-8"))
        ok &= check("humanoid_anim reproducible (committed == fresh bake)", fresh_anim == committed_anim)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
