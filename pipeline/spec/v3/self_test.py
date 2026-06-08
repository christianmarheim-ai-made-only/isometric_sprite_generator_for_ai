#!/usr/bin/env python3
"""v3 producer-spec-pack self-test. Pins the pack to the LIVE pipeline so the spec can never drift from
the code: the positive example validates + lints clean, the negative fixtures fail with their declared
code, the calibration colours + metadata in the doc equal calib_spec.py, every referenced code exists in
error_codes.py, and the version string is consistent. Runs in CI (registered in build.py).

  python pipeline/spec/v3/self_test.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent / "tools"
SCHEMA_DIR = HERE.parent.parent / "schema"
sys.path.insert(0, str(TOOLS))

from jsonschema import Draft202012Validator                    # noqa: E402
import error_codes as ec                                       # noqa: E402
from calib_spec import CALIBRATION_COLORS, CALIBRATION_MODELS, calib_color_key  # noqa: E402
from lint_external_asset import lint                            # noqa: E402


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def main():
    ok = True

    # 1. all pack files present
    expect = (["README.md", "calibration_model.md", "uv_format.md", "gate_reference.md", "fixtures_plan.md",
               "prompts/README.md"] + [f"prompts/stage_{i}_" for i in range(10)])
    files = {p.name for p in HERE.rglob("*")}
    ok &= check("pack: core docs present", all((HERE / f).exists() for f in expect[:6]))
    ok &= check("pack: 10 stage prompts present", sum(1 for p in (HERE / "prompts").glob("stage_*.md")) >= 10)

    # 2. POSITIVE example validates vs the LIVE external_asset schema + lints clean
    schema = json.loads((SCHEMA_DIR / "external_asset.schema.json").read_text(encoding="utf-8"))
    pos = json.loads((HERE / "examples" / "combat_biped_v1.asset.json").read_text(encoding="utf-8"))
    serrs = list(Draft202012Validator(schema).iter_errors(pos))
    ok &= check("positive example validates vs external_asset_v2", not serrs)
    lerrs = lint(HERE / "examples" / "combat_biped_v1.asset.json", check_files=False)
    ok &= check(f"positive example lints clean (check_files=False)", lerrs == [])

    # 3. the region_hitboxes sidecar validates + covers the biped region set
    rh_schema = json.loads((HERE / "schema" / "region_hitboxes.schema.json").read_text(encoding="utf-8"))
    hb = json.loads((HERE / "examples" / "combat_biped_v1_hitbox.json").read_text(encoding="utf-8"))
    ok &= check("hitbox sidecar validates vs region_hitboxes schema",
                not list(Draft202012Validator(rh_schema).iter_errors(hb)))
    folded = {calib_color_key(n) for n in hb["region_hitboxes"]}
    ok &= check("hitbox regions fold to the 5 biped calibration keys",
                folded == set(CALIBRATION_MODELS["biped"]["regions"]))

    # 4. NEGATIVE fixtures fail with their declared code
    negs = {"neg_missing_idle.asset.json": "missing_required_clip",
            "neg_flat_region_real_albedo.asset.json": "flat_region_real_albedo"}
    for fn, code in negs.items():
        errs = lint(HERE / "examples" / "negatives" / fn, check_files=False)
        ok &= check(f"negative {fn} -> {code}", any(code in e for e in errs))

    # 5. calibration COLOURS in the doc == calib_spec.py (doc cannot drift from the code)
    calib_md = (HERE / "calibration_model.md").read_text(encoding="utf-8")
    for key, (r, g, b) in CALIBRATION_COLORS.items():
        present = f"({r},{g},{b})" in calib_md or f"({r}, {g}, {b})" in calib_md
        ok &= check(f"calib colour {key} ({r},{g},{b}) documented", present)

    # 6. hard-coded calibration METADATA in the doc == calib_spec.py
    for arch, m in CALIBRATION_MODELS.items():
        wm = m["world_metrics"]
        nums_ok = all(str(v) in calib_md for v in (wm["height_world"], wm["eye_height_world"],
                                                   wm["footprint_radius_world"]))
        ok &= check(f"calib metadata for {arch} ({m['variant_id']}) documented", nums_ok)

    # 7. every snake_case `code` in gate_reference.md is a REAL error_codes code (no invented codes)
    gate_md = (HERE / "gate_reference.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"`([a-z][a-z0-9_]{6,})`", gate_md))
    code_like = {t for t in referenced if t in ec.CODES or (t.count("_") >= 2 and t.endswith(
        ("_missing", "_mismatch", "_texture", "_uv", "_clip", "_torso", "_page", "_frame", "_linked",
         "_unbound", "_albedo", "_indistinct", "_bone", "_part", "_influences", "_expired", "_present")))}
    unknown = sorted(t for t in code_like if not ec.is_known(t))
    ok &= check(f"gate_reference codes all exist in error_codes ({len(code_like)} referenced)", not unknown)
    if unknown:
        print("   unknown:", unknown)

    # 8. the NEW gates are documented in gate_reference
    for code in ("flat_region_bound_texture", "blank_frame", "calib_region_color_mismatch"):
        ok &= check(f"gate_reference documents {code}", code in gate_md)

    # 9. version string consistency
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    ok &= check("README declares producer_spec_version model_producer_delivery_spec_v3",
                "model_producer_delivery_spec_v3" in readme)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
