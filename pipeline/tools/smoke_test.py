#!/usr/bin/env python3
"""M1/M2 smoke test: valid manifest passes, corrupted hash fails closed."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from generate_arrow_pilot import main as generate_main  # noqa: E402
from validate_manifest import validate_manifest  # noqa: E402


def main() -> int:
    pipeline_root = Path(__file__).resolve().parents[1]
    output = pipeline_root / "output" / "arrow_pilot"

    # Generate first to keep smoke test deterministic.
    old_argv = sys.argv[:]
    try:
        sys.argv = ["generate_arrow_pilot.py", "--pipeline-root", str(pipeline_root), "--output", str(output), "--clean"]
        generate_main()
    finally:
        sys.argv = old_argv

    manifest = output / "manifest.json"
    report = validate_manifest(manifest, pipeline_root)
    if not report["ok"]:
        print("FAIL: valid manifest rejected")
        print(json.dumps(report, indent=2))
        return 1
    print("PASS: valid manifest accepted")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Copy the whole output so relative atlas paths remain valid.
        copied = tmp / "arrow_pilot"
        shutil.copytree(output, copied)
        corrupt_manifest = copied / "manifest.json"
        data = json.loads(corrupt_manifest.read_text(encoding="utf-8"))
        data["contract_hash"] = "sha256:" + "0" * 64
        corrupt_manifest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        corrupt_report = validate_manifest(corrupt_manifest, pipeline_root)
        if corrupt_report["ok"]:
            print("FAIL: corrupted contract_hash was accepted")
            return 1
        if not any("contract_hash" in err for err in corrupt_report["errors"]):
            print("FAIL: corrupted manifest failed, but not because of contract_hash")
            print(json.dumps(corrupt_report, indent=2))
            return 1
        print("PASS: corrupted contract_hash rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
