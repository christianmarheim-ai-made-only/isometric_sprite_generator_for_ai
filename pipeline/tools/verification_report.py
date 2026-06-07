"""verification_report_v1 -- the deterministic OUTPUT-verify artifact (ADR-0031; review snippet 17).

It is a pure PROJECTION of the build_log `warnings` list through the canonical error-code registry
(`error_codes.CODES`) into per-stage pass/fail. Because both `verification_report.ok` and
`build_log.ok` are computed from the same "any severity==error" rule, they CANNOT disagree by
construction -- and the bake asserts they agree (else `verification_build_log_disagree`).
"""
from __future__ import annotations
import json

from error_codes import STAGES, stage_of, check_of, severity_of

# the stages always shown (so a clean bake still lists every gate it passed)
_ALWAYS = ("modeling", "texture", "skinning", "animation", "hitbox")


def build_report(asset_id, texture_mode, warnings, build_log_ok):
    """warnings: list of dicts {code, severity, ...} from build_log. Returns the report dict."""
    stages = {s: {"ok": True, "checks": {}} for s in STAGES}
    errors, warns, waived = [], [], []
    for w in warnings:
        code = w.get("code")
        sev = w.get("severity", severity_of(code))
        st, ck = stage_of(code), check_of(code)
        if sev == "error":
            stages[st]["checks"][ck] = "fail"
            stages[st]["ok"] = False
            errors.append(code)
        elif sev == "waived":
            stages[st]["checks"].setdefault(ck, "waived")
            waived.append(code)
        else:
            stages[st]["checks"].setdefault(ck, "warn")
            warns.append(code)
    ok = not errors
    shown = {s: stages[s] for s in STAGES if stages[s]["checks"] or s in _ALWAYS}
    rep = {
        "verification_report_version": "verification_report_v1",
        "asset_id": asset_id,
        "ok": ok,
        "texture_mode": texture_mode,
        "stages": shown,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warns)),
        "waivers": sorted(set(waived)),
        "build_log_ok": build_log_ok,
        "ok_agrees_with_build_log": (ok == build_log_ok),
    }
    return rep


def write_report(out_path, asset_id, texture_mode, warnings, build_log_ok):
    rep = build_report(asset_id, texture_mode, warnings, build_log_ok)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2, sort_keys=False)
    return rep
