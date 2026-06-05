#!/usr/bin/env python3
"""Self-test for the external-asset contract (docs/external_asset_contract.md): the example
manifests lint clean, the rig profiles are well-formed, and the linter actually REJECTS a
malformed asset (so the front door for external inputs is real, not vacuous).

Run: python pipeline/tools/test_external_asset.py
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

from lint_external_asset import lint  # noqa: E402

EX = PIPELINE_ROOT / "examples"
RIG = PIPELINE_ROOT / "schema" / "rig_profiles"


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    ok &= check("examples/humanoid_v1.asset.json lints clean (real committed mesh, static)",
                not lint(EX / "humanoid_v1.asset.json"))
    ok &= check("examples/bird_v1.asset.json lints clean as a template (--no-files)",
                not lint(EX / "bird_v1.asset.json", check_files=False))

    for prof in ("biped_v1", "bird_v1"):
        p = json.loads((RIG / f"{prof}.json").read_text(encoding="utf-8"))
        names = [b["name"] for b in p["bones"]]
        roots = [b for b in p["bones"] if b["parent"] is None]
        parents_ok = all(b["parent"] is None or b["parent"] in names for b in p["bones"])
        regions_ok = set(p.get("region_by_bone", {}).values()) <= {"head", "torso", "arms", "legs"}
        ok &= check(f"rig profile {prof}: unique bones, single root, parents resolve, regions in palette",
                    len(names) == len(set(names)) and len(roots) == 1 and parents_ok
                    and regions_ok and p["rig_profile"] == prof)

    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad.asset.json"
        bad.write_text(json.dumps({
            "asset_contract_version": "external_asset_v1", "variant_id": "Bad Name",
            "archetype": "bird", "files": {}, "rig": "nonexistent_rig",
            "animations": {"fly": {"frames": 0, "fps": 12, "playback": "bounce"}},
        }), encoding="utf-8")
        errs = lint(bad, check_files=False)
        ok &= check(f"linter REJECTS a malformed asset (bad id/playback/frames) -> {len(errs)} issue(s)", len(errs) >= 1)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
