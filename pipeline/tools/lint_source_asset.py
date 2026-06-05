#!/usr/bin/env python3
"""Source-asset descriptor linter v1 (P4).

Validates a source_asset descriptor (P3 schema) against the locked contract and
the naming conventions BEFORE Blender export. v1 is descriptor-level plus a
source-file existence check; geometry checks (objects actually present, min_z
tolerance, skeleton, clips) need Blender and arrive in P5.

  python pipeline/tools/lint_source_asset.py <descriptor.json> [--require-source]

Exit 0 if no errors (warnings allowed); nonzero on any error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
SCHEMA = PIPELINE_ROOT / "schema" / "source_asset.schema.json"

# Locked contract invariants (sprite_contract.lock.json / docs/next_slices_plan.md §2).
FORWARD_AXIS = "+X"
UP_AXIS = "+Z"
UNITS = "meter"

# Body-only this iteration (region_assignment_policy.md, naming_conventions.md).
BODY_REGIONS = {"head", "torso", "arms", "legs"}
DEFERRED_REGIONS = {"shield", "weapon", "gear"}
BASE_SOCKETS = {"origin", "head_center", "hand_l", "hand_r"}
DEFERRED_SOCKETS = {"weapon_grip", "weapon_tip", "muzzle", "muzzle_back", "shield_center"}

ORIGIN_POLICY_BY_CLASS = {
    "probe": "ground_footprint_center",
    "character": "ground_footprint_center",
    "effect": "emission_point",
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, m: str) -> None:
        self.errors.append(m)

    def warn(self, m: str) -> None:
        self.warnings.append(m)


def lint(descriptor_path: Path, require_source: bool = False) -> Report:
    r = Report()
    data = json.loads(descriptor_path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    # 1. Schema. If the shape is wrong, stop -- later checks assume valid shape.
    schema_errs = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    for e in schema_errs:
        r.err(f"schema /{'/'.join(map(str, e.path))}: {e.message}")
    if schema_errs:
        return r

    vclass = data["variant_class"]

    # 2-4. Axes / units must match the locked contract.
    if data["forward_axis"] != FORWARD_AXIS:
        r.err(f"forward_axis must be {FORWARD_AXIS} (got {data['forward_axis']})")
    if data["up_axis"] != UP_AXIS:
        r.err(f"up_axis must be {UP_AXIS} (got {data['up_axis']})")
    if data["units"] != UNITS:
        r.err(f"units must be {UNITS} (got {data['units']})")

    # 5. origin_policy per variant_class.
    expected_policy = ORIGIN_POLICY_BY_CLASS.get(vclass)
    if expected_policy and data["origin_policy"] != expected_policy:
        r.err(f"origin_policy must be {expected_policy} for variant_class {vclass} (got {data['origin_policy']})")

    # 6. sockets: origin required; weapon sockets deferred this iteration.
    sockets = data["sockets"]
    if "origin" not in sockets:
        r.err("required socket 'origin' missing")
    for s in sockets:
        if s in DEFERRED_SOCKETS:
            r.err(f"socket '{s}' is deferred this iteration (weapons/equipment)")
        elif s not in BASE_SOCKETS:
            r.warn(f"socket '{s}' is not a known base socket")

    # 7. visual objects: VIS_ prefix; probe/character need at least one.
    if vclass in ("probe", "character") and not data["visual_objects"]:
        r.err(f"variant_class {vclass} requires at least one visual object")
    for n in data["visual_objects"]:
        if not n.startswith("VIS_"):
            r.err(f"visual object '{n}' must start with VIS_")

    # 8. hit proxies: HIT_ prefix; body-only regions; effects have none.
    if vclass == "effect" and data["hit_proxy_objects"]:
        r.err("effect must have no hit proxies")
    for hp in data["hit_proxy_objects"]:
        if not hp["name"].startswith("HIT_"):
            r.err(f"hit proxy '{hp['name']}' must start with HIT_")
        region = hp["region"]
        if region in DEFERRED_REGIONS:
            r.err(f"hit region '{region}' is deferred this iteration (weapons/equipment)")
        elif region not in BODY_REGIONS:
            r.err(f"hit region '{region}' is not an allowed body region")

    # 9. metric proxies: METRIC_ prefix.
    for n in data["metric_proxy_objects"]:
        if not n.startswith("METRIC_"):
            r.err(f"metric proxy '{n}' must start with METRIC_")

    # 10. source file existence. Geometry checks (objects present, min_z) are P5/Blender.
    source_file = data.get("source_file")
    if source_file:
        if (descriptor_path.parent / source_file).exists():
            r.warn(f"source file present ({source_file}); geometry checks (objects, min_z) deferred to P5/Blender")
        else:
            msg = f"source file not found: {source_file} (geometry checks deferred to P5/Blender)"
            (r.err if require_source else r.warn)(msg)
    else:
        r.warn("no source_file declared; cannot check source existence")

    return r


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint a source-asset descriptor (v1).")
    ap.add_argument("descriptor", type=Path)
    ap.add_argument("--require-source", action="store_true",
                    help="Treat a missing source file as an error (use with Blender/CI).")
    args = ap.parse_args()
    r = lint(args.descriptor.resolve(), require_source=args.require_source)
    for w in r.warnings:
        print(f"WARN: {w}")
    for e in r.errors:
        print(f"ERROR: {e}")
    print(f"{'OK' if not r.errors else 'FAIL'}: {args.descriptor.name} "
          f"({len(r.errors)} error(s), {len(r.warnings)} warning(s))")
    return 0 if not r.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
