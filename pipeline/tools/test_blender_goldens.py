#!/usr/bin/env python3
"""Gate the committed BLENDER goldens by CHECKSUM -- NON-SKIPPING (no Blender needed).

The Blender parity gates (test_blender_parity, test_combat_bake, test_rigged_anim, test_preview) all
SKIP when Blender is absent, so on a no-Blender CI box the committed Blender-baked reference output is
NEVER re-verified -> silent drift/corruption, and an undetected cross-Blender-version change. This
gate closes that hole: it hashes the committed goldens against reference/blender_goldens.lock.json and
fails on any mismatch, with NO Blender dependency. When Blender IS present it additionally WARNS (does
not fail) if the local Blender version differs from the pinned bake version.

Re-bake + update the lock atomically when intentionally regenerating a Blender golden.

Run: python pipeline/tools/test_blender_goldens.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
LOCK = PIPELINE_ROOT / "reference" / "blender_goldens.lock.json"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_bake import find_blender  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _local_blender_version(exe: str) -> str | None:
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
        for tok in out.split():
            if tok[:1].isdigit() and "." in tok:  # "Blender 5.1.2" -> 5.1.2
                return tok
    except Exception:
        pass
    return None


def main() -> int:
    ok = True
    ok &= check(f"blender goldens lock present: {LOCK.name}", LOCK.exists())
    if not LOCK.exists():
        return 1
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    pin = lock.get("blender_version_pin")
    ok &= check("blender_version_pin is set", bool(pin))

    n_files = 0
    for variant, info in sorted(lock.get("goldens", {}).items()):
        base = PIPELINE_ROOT / "reference" / variant
        for fname, want in sorted(info.get("files", {}).items()):
            p = base / fname
            present = p.exists()
            ok &= check(f"{variant}/{fname} present", present)
            if not present:
                continue
            got = _sha(p)
            ok &= check(f"{variant}/{fname} checksum matches lock", got == want)
            if got != want:
                print(f"   want {want}\n   got  {got}  -- re-bake + update {LOCK.name}, or investigate drift")
            n_files += 1
    ok &= check(f"checksummed at least one golden file (got {n_files})", n_files > 0)

    # Non-fatal cross-version heads-up, only when Blender is actually available.
    exe = find_blender()
    if exe:
        local = _local_blender_version(exe)
        if local and pin and local != pin:
            print(f"WARN: local Blender {local} != pinned bake version {pin}; "
                  f"re-verify parity before re-baking goldens.")
        else:
            print(f"INFO: local Blender {local or '?'} (pin {pin}).")
    else:
        print(f"INFO: Blender absent -- the checksum gate ran anyway (that is the point). Pin {pin}.")

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
