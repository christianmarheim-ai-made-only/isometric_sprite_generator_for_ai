#!/usr/bin/env python3
"""Env gate self-test (world-scenery track). Pins the env_asset_v1 contract: every example validates,
the per-kind shape holds, the trimmed-ness holds (no rig/clips/archetype/calibration), and the ONE-WAY
boundary holds (pipeline/tools must never import pipeline/env). Runs in the SEPARATE env gate
(build_env.py), NEVER the character 42-gate. Pure schema validation -- no Blender.

  python pipeline/env/self_test.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
from jsonschema import Draft202012Validator   # noqa: E402


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def main():
    ok = True
    schema = json.loads((HERE / "schema" / "env_asset.schema.json").read_text(encoding="utf-8"))
    V = Draft202012Validator(schema)

    def valid(obj):
        return not list(V.iter_errors(obj))

    # 1. every example validates + the per-kind shape is right
    ex = {p.stem.replace(".asset", ""): json.loads(p.read_text(encoding="utf-8"))
          for p in (HERE / "examples").glob("*.asset.json")}
    ok &= check(f"4 examples present (terrain/prop/blocking_feature/water)", len(ex) == 4)
    for name, o in sorted(ex.items()):
        ok &= check(f"example {name} validates vs env_asset_v1", valid(o))
    by_kind = {o["kind"]: o for o in ex.values()}
    ok &= check("terrain has NO collision + NO world_metrics",
                "collision" not in by_kind["terrain"] and "world_metrics" not in by_kind["terrain"])
    ok &= check("prop has world_metrics", "world_metrics" in by_kind["prop"])
    ok &= check("blocking_feature has collision + world_metrics",
                "collision" in by_kind["blocking_feature"] and "world_metrics" in by_kind["blocking_feature"])
    ok &= check("water has collision + tiling, NO world_metrics",
                "collision" in by_kind["water"] and "tiling" in by_kind["water"] and "world_metrics" not in by_kind["water"])

    base = by_kind["prop"]
    def mut(**kw):
        o = json.loads(json.dumps(base)); o.update(kw); return o

    # 2. NEGATIVES (the contract must REJECT these)
    ok &= check("terrain WITH a collider -> rejected (terrain is walkable)",
                not valid({**by_kind["terrain"], "collision": by_kind["water"]["collision"]}))
    bf = json.loads(json.dumps(by_kind["blocking_feature"])); bf.pop("collision")
    ok &= check("blocking_feature WITHOUT a collider -> rejected", not valid(bf))
    p = json.loads(json.dumps(by_kind["prop"])); p.pop("world_metrics")
    ok &= check("prop WITHOUT world_metrics -> rejected", not valid(p))
    ok &= check("trimmed: an asset declaring a rig -> rejected", not valid(mut(rig="biped_v1")))
    ok &= check("trimmed: an asset declaring animations -> rejected", not valid(mut(animations={"idle": {}})))
    ok &= check("trimmed: an asset declaring calibration -> rejected", not valid(mut(calibration={"enabled": True})))
    ok &= check("wrong env_contract_version -> rejected", not valid(mut(env_contract_version="env_asset_v2")))
    ok &= check("tier block (reserved, flat-only) is empty/unused in the examples",
                all("tier" not in o for o in ex.values()))

    # 3. ONE-WAY BOUNDARY: no file under pipeline/tools may import pipeline/env (env -> tools only)
    offenders = []
    for f in (ROOT / "pipeline" / "tools").glob("*.py"):
        t = f.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^\s*(from|import)\s+env\b|pipeline\.env|from\s+\.\.env", t, re.M):
            offenders.append(f.name)
    ok &= check("one-way boundary: pipeline/tools does NOT import pipeline/env", not offenders)
    if offenders:
        print("   offenders:", offenders)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
