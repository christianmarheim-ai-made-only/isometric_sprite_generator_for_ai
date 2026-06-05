#!/usr/bin/env python3
"""Compute the shared lockfile hash for the M1/M2 sprite pipeline debug subset."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

LOCKFILE_NAMES = [
    "sprite_contract.lock.json",
    "sprite_states.lock.json",
    "sprite_variants.lock.json",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_contract_hash(lockfiles_dir: Path) -> str:
    bundle = {}
    for name in LOCKFILE_NAMES:
        path = lockfiles_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing lockfile: {path}")
        bundle[name] = load_json(path)
    digest = hashlib.sha256(canonical_json_bytes(bundle)).hexdigest()
    return f"sha256:{digest}"


def compute_individual_hashes(lockfiles_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in LOCKFILE_NAMES:
        path = lockfiles_dir / name
        result[name] = "sha256:" + hashlib.sha256(canonical_json_bytes(load_json(path))).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute sprite pipeline contract hash from lockfiles.")
    parser.add_argument("--lockfiles", type=Path, default=Path(__file__).resolve().parents[1] / "lockfiles")
    args = parser.parse_args()
    print(compute_contract_hash(args.lockfiles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
