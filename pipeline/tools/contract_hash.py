#!/usr/bin/env python3
"""Compute the engine-facing contract hash for the M1/M2 sprite pipeline debug subset."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

# The engine-facing seam lives in this lockfile alone (camera, coordinates,
# formats, palette, sampling, packing); it is the only input to contract_hash.
CONTRACT_LOCKFILE_NAME = "sprite_contract.lock.json"

# All lockfiles, hashed individually for provenance in manifest.build.
LOCKFILE_NAMES = [
    CONTRACT_LOCKFILE_NAME,
    "sprite_states.lock.json",
    "sprite_variants.lock.json",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_contract_hash(lockfiles_dir: Path) -> str:
    """Hash only the engine-facing contract lockfile.

    The contract_hash guards the seam the engine actually consumes -- camera,
    coordinates, formats, palette, sampling, packing -- so it is derived from
    sprite_contract.lock.json alone. State compatibility is carried separately
    by state_contract_version, and variant compatibility by the validator's
    per-variant cross-check, so adding a variant or editing the states lock must
    NOT change this hash or invalidate previously generated manifests.
    See ADR-0014 and the M1/M2 review.
    """
    path = lockfiles_dir / CONTRACT_LOCKFILE_NAME
    if not path.exists():
        raise FileNotFoundError(f"Missing lockfile: {path}")
    digest = hashlib.sha256(canonical_json_bytes(load_json(path))).hexdigest()
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
