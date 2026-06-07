#!/usr/bin/env python3
"""Gate the named, single-check, EXPIRING severity waivers (review snippet 07; ADR-0028/0031).

A waiver downgrades EXACTLY ONE named, WAIVABLE check code from `error` to `waived` for a *declared*
asset (so ok stays true and the check still appears) -- it is NOT a way to hide a broken bake:
  - a valid in-date richness waiver downgrades atlas_colour_rich_low -> waived (ok stays TRUE);
  - an EXPIRED waiver -> waiver_expired error (ok FALSE);
  - engine_real_albedo:true -> waiver_attempts_real_albedo_true error;
  - an unknown / structural (non-waivable) code -> waiver_unknown_code error;
  - a waiver with no expires_at -> waiver_missing error.
`today` is injected (an ISO date string) -- no Date.now. No Blender: we build warnings lists + call
the resolver/validator directly, and drive write_build_log on a tiny in-memory manifest.

Run: python pipeline/tools/test_waivers.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from waivers import WAIVABLE_CODES, resolve, validate  # noqa: E402
from build_log import write_build_log  # noqa: E402

TODAY = "2026-06-07"  # the injected "bake date"


def _waiver(code="atlas_colour_rich_low", expires_at="2026-07-01", real_albedo=False, wid="W1"):
    w = {"waiver_id": wid, "code": code, "reason": "calibration flat debug colours",
         "approved_by": "pipeline-owner", "created_at": "2026-06-01", "expires_at": expires_at,
         "engine_real_albedo": real_albedo}
    return w


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def _codes(errs):
    return {e["code"] for e in errs}


def main() -> int:
    ok = True

    # ============================ resolve() ============================
    rich = [_waiver()]
    ok &= check("resolve: in-date richness waiver MATCHES atlas_colour_rich_low",
                resolve("atlas_colour_rich_low", rich, TODAY) is not None)
    ok &= check("resolve: returns the matching waiver_id",
                (resolve("atlas_colour_rich_low", rich, TODAY) or {}).get("waiver_id") == "W1")
    ok &= check("resolve: a waiver for code A does NOT downgrade a different code B",
                resolve("degenerate_uv", rich, TODAY) is None)
    ok &= check("resolve: an EXPIRED waiver does NOT match (today >= expires_at)",
                resolve("atlas_colour_rich_low", [_waiver(expires_at="2026-06-07")], TODAY) is None)
    ok &= check("resolve: expiry boundary is inclusive (expires_at == today -> expired)",
                resolve("atlas_colour_rich_low", [_waiver(expires_at=TODAY)], TODAY) is None)
    ok &= check("resolve: a real-albedo waiver does NOT silently match",
                resolve("atlas_colour_rich_low", [_waiver(real_albedo=True)], TODAY) is None)
    ok &= check("resolve: a non-waivable code never matches even if named",
                resolve("region_missing", [_waiver(code="region_missing")], TODAY) is None)
    ok &= check("resolve: None / empty waivers -> None",
                resolve("atlas_colour_rich_low", None, TODAY) is None and
                resolve("atlas_colour_rich_low", [], TODAY) is None)

    # ============================ validate() ============================
    ok &= check("validate: a clean in-date richness waiver -> NO errors",
                validate([_waiver()], TODAY) == [])
    ok &= check("validate: EXPIRED -> waiver_expired",
                _codes(validate([_waiver(expires_at="2026-01-01")], TODAY)) == {"waiver_expired"})
    ok &= check("validate: engine_real_albedo:true -> waiver_attempts_real_albedo_true",
                "waiver_attempts_real_albedo_true" in _codes(validate([_waiver(real_albedo=True)], TODAY)))
    ok &= check("validate: an UNKNOWN code -> waiver_unknown_code",
                _codes(validate([_waiver(code="not_a_real_code")], TODAY)) == {"waiver_unknown_code"})
    ok &= check("validate: a known-but-STRUCTURAL code -> waiver_unknown_code (non-waivable)",
                _codes(validate([_waiver(code="missing_required_bone")], TODAY)) == {"waiver_unknown_code"})
    ok &= check("validate: no expires_at -> waiver_missing",
                "waiver_missing" in _codes(validate([_waiver(expires_at=None)], TODAY)))
    ok &= check("validate: no code -> waiver_missing",
                "waiver_missing" in _codes(validate([_waiver(code=None)], TODAY)))
    ok &= check("validate: None / [] -> no errors",
                validate(None, TODAY) == [] and validate([], TODAY) == [])
    ok &= check("validate: degenerate_uv and front_back_indistinct are in the WAIVABLE allowlist",
                {"degenerate_uv", "front_back_indistinct", "atlas_colour_rich_low"} <= set(WAIVABLE_CODES))

    # ============================ write_build_log wiring ============================
    # A textured (non-calibration) bake that trips atlas_colour_rich_low as an ERROR... a VALID waiver
    # downgrades it to `waived` so build_log.ok stays TRUE and the check STILL APPEARS.
    base_manifest = {"variant_id": "wv", "animations": {}, "frames": [],
                     "atlases": {"color": {"size": [10, 10]}}}

    with tempfile.TemporaryDirectory() as td:
        # Drive a real error->waived downgrade through the public entry point: a `textured` bake with a
        # degenerate-UV material escalates degenerate_uv to ERROR (build_log.py texture gate); a VALID
        # degenerate_uv waiver then downgrades it to `waived`. (We use degenerate_uv rather than
        # atlas_colour_rich_low because the latter requires a real color_atlas.png on disk to fire.)
        log_waived = write_build_log(
            Path(td), base_manifest, "test", texture_mode="textured",
            meta={"degenerate_uv_materials": ["debug_flat"]},
            waivers=[_waiver(code="degenerate_uv")], today=TODAY)
        dw = [w for w in log_waived["warnings"] if w["code"] == "degenerate_uv"]
        ok &= check("build_log: textured degenerate_uv ERROR + valid waiver -> severity 'waived'",
                    len(dw) == 1 and dw[0]["severity"] == "waived" and dw[0].get("waiver_id") == "W1")
        ok &= check("build_log: a waived check keeps ok == True", log_waived["ok"] is True)
        ok &= check("build_log: the waived warning is NOT removed (still appears)",
                    any(w["code"] == "degenerate_uv" for w in log_waived["warnings"]))

        # an EXPIRED waiver does NOT downgrade and ADDS a waiver_expired error -> ok flips FALSE.
        log_exp = write_build_log(
            Path(td), base_manifest, "test", texture_mode="textured",
            meta={"degenerate_uv_materials": ["debug_flat"]},
            waivers=[_waiver(code="degenerate_uv", expires_at="2026-01-01")], today=TODAY)
        codes_exp = [w["code"] for w in log_exp["warnings"]]
        dw_exp = [w for w in log_exp["warnings"] if w["code"] == "degenerate_uv"]
        ok &= check("build_log: EXPIRED waiver -> waiver_expired error AND degenerate_uv stays error",
                    "waiver_expired" in codes_exp and dw_exp and dw_exp[0]["severity"] == "error")
        ok &= check("build_log: EXPIRED waiver -> ok == False", log_exp["ok"] is False)

        # a real-albedo waiver -> waiver_attempts_real_albedo_true error (and no silent downgrade).
        log_ra = write_build_log(
            Path(td), base_manifest, "test", texture_mode="textured",
            meta={"degenerate_uv_materials": ["debug_flat"]},
            waivers=[_waiver(code="degenerate_uv", real_albedo=True)], today=TODAY)
        ok &= check("build_log: real_albedo waiver -> waiver_attempts_real_albedo_true + ok False",
                    "waiver_attempts_real_albedo_true" in {w["code"] for w in log_ra["warnings"]}
                    and log_ra["ok"] is False)

        # no waivers at all -> behaviour unchanged (the degenerate_uv error stands, ok False).
        log_none = write_build_log(
            Path(td), base_manifest, "test", texture_mode="textured",
            meta={"degenerate_uv_materials": ["debug_flat"]}, today=TODAY)
        ok &= check("build_log: no waivers -> unchanged (degenerate_uv error, ok False)",
                    log_none["ok"] is False
                    and all(w["code"] != "waiver_expired" for w in log_none["warnings"]))

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
