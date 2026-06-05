#!/usr/bin/env python3
"""Regression tests for the narrowed contract_hash (M1/M2 Fix 1).

The contract_hash must depend ONLY on sprite_contract.lock.json so that growing
the variant roster (M4) or editing the states lock does not change the hash and
invalidate every previously generated manifest. These tests operate on temp
copies and never mutate the real lockfiles.

Run: python pipeline/tools/test_contract_hash.py   (exit 0 = all pass)
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from contract_hash import compute_contract_hash  # noqa: E402

REAL_LOCKFILES = SCRIPT_DIR.parent / "lockfiles"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        locks = Path(td) / "lockfiles"
        shutil.copytree(REAL_LOCKFILES, locks)
        baseline = compute_contract_hash(locks)
        ok &= check("baseline hash is sha256-prefixed", baseline.startswith("sha256:"))

        # 1. Adding a variant must NOT change the contract hash (the M4 scenario).
        variants_path = locks / "sprite_variants.lock.json"
        variants = _load(variants_path)
        variants["variants"]["pilot_arrow_v2"] = {
            "direction_count": 8,
            "equipment_baked": False,
            "frame_canvas": [128, 128],
            "notes": "test-only extra variant",
            "required_sockets": ["origin"],
            "supported_states": ["idle"],
            "variant_class": "debug_direction_pilot",
        }
        _dump(variants_path, variants)
        ok &= check(
            "adding a variant leaves contract_hash unchanged",
            compute_contract_hash(locks) == baseline,
        )

        # 2. Editing the states lock must NOT change the contract hash.
        states_path = locks / "sprite_states.lock.json"
        states = _load(states_path)
        states["states"]["idle"]["frames"] = 99
        _dump(states_path, states)
        ok &= check(
            "editing the states lock leaves contract_hash unchanged",
            compute_contract_hash(locks) == baseline,
        )

        # 3. Editing the contract lock (a projection/seam change) MUST change it.
        contract_path = locks / "sprite_contract.lock.json"
        contract = _load(contract_path)
        contract["camera"]["projection"] = str(contract["camera"]["projection"]) + "_changed"
        _dump(contract_path, contract)
        ok &= check(
            "editing the contract lock changes contract_hash",
            compute_contract_hash(locks) != baseline,
        )

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
