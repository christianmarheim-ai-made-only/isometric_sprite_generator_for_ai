#!/usr/bin/env python3
"""R6 engine load-test runner.

Runs the `bevy_reference` cargo test, which parses the committed manifests (the reference
character + the arrow pilot) through `loader::parse_manifest` -- vendored verbatim from the
engine `crates/client_bevy/src/sprite.rs::parse_manifest` -- i.e. the REAL engine
accept/reject logic, no Bevy build required.

Skips gracefully (exit 0) when cargo is not installed, so the Python gate still passes on
machines without the Rust toolchain.

Run: python pipeline/tools/test_engine_load.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CRATE = Path(__file__).resolve().parents[1] / "bevy_reference" / "Cargo.toml"


def main() -> int:
    if shutil.which("cargo") is None:
        print("SKIP: cargo not found; engine load-test (bevy_reference) not run on this machine.")
        return 0
    proc = subprocess.run(["cargo", "test", "--manifest-path", str(CRATE), "--quiet"],
                          capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        print("FAIL: cargo engine load-test")
        return 1
    print("PASS: cargo engine load-test (reference character + arrow pilot accepted by the vendored engine loader)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
