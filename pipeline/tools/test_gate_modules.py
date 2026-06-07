#!/usr/bin/env python3
"""Gate: the host-side gate modules (no Blender) -- error-code registry, texture-capability probe,
baked-atlas richness metric, and the verification-report projection + ok-agreement invariant.

  python pipeline/tools/test_gate_modules.py
"""
from __future__ import annotations
import os
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # repo root

import error_codes as ec
import verification_report as vr
from glb_texture_probe import texture_capable


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def main():
    ok = True

    # --- error_codes registry ---
    ok &= check("error_codes: all rows well-formed (severity in set, stage known)",
                all(sev in ("error", "warn", "waived") and st in ec.STAGES and isinstance(chk, str)
                    for (sev, st, chk) in ec.CODES.values()))
    ok &= check("error_codes: helpers resolve a known + unknown code",
                ec.severity_of("texture_unbound") == "error" and ec.is_known("degenerate_uv")
                and not ec.is_known("not_a_real_code"))

    # --- texture-capability probe on committed fixtures ---
    fx = os.path.join(ROOT, "pipeline", "examples", "texture_starter", "humanoid_textured.glb")
    pirate = os.path.join(ROOT, "creative", "incoming", "pirate_duelist_v2", "pirate_duelist_v2.glb")
    ogre = os.path.join(ROOT, "creative", "incoming", "green_ogre_v1", "green_ogre_v1.glb")
    if os.path.exists(fx):
        cap, reasons, rec = texture_capable(fx)
        ok &= check(f"texture_capable: known-good humanoid_textured -> CAPABLE ({rec['bound_textures']} bound, {rec['no_uv']} no-uv)", cap and not reasons)
    if os.path.exists(pirate):
        cap, reasons, _ = texture_capable(pirate)
        ok &= check("texture_capable: pirate collapsed-UV -> REJECT degenerate_uv", (not cap) and "degenerate_uv" in reasons)
    if os.path.exists(ogre):
        cap, reasons, _ = texture_capable(ogre)
        ok &= check("texture_capable: ogre geometry-only -> REJECT texture_unbound", (not cap) and "texture_unbound" in reasons)

    # --- baked-atlas richness metric (synthetic; needs PIL) ---
    try:
        from PIL import Image
        import texture_metrics as tm
        d = tempfile.mkdtemp()
        flat = os.path.join(d, "flat.png")
        Image.new("RGBA", (64, 64), (40, 80, 160, 255)).save(flat)
        rich = os.path.join(d, "rich.png")
        im = Image.new("RGBA", (64, 64))
        px = im.load()
        for y in range(64):
            for x in range(64):
                px[x, y] = ((x * 4) % 256, (y * 4) % 256, ((x + y) * 3) % 256, 255)
        im.save(rich)
        flat_ok, _ = tm.atlas_colour_rich(flat)
        rich_ok, _ = tm.atlas_colour_rich(rich)
        ok &= check("atlas_colour_rich: flat 1-colour -> LOW", not flat_ok)
        ok &= check("atlas_colour_rich: rich gradient -> rich", rich_ok)
    except ImportError:
        print("SKIP: PIL not available -> richness metric not exercised")

    # --- verification report projection + ok-agreement invariant ---
    rep = vr.build_report("demo", "textured",
                          [{"code": "degenerate_uv", "severity": "error"},
                           {"code": "auto_rigged", "severity": "warn"}], build_log_ok=False)
    ok &= check("verification_report: error projects to stage fail + ok=false",
                rep["ok"] is False and rep["stages"]["texture"]["ok"] is False and "degenerate_uv" in rep["errors"])
    ok &= check("verification_report: ok agrees with build_log", rep["ok_agrees_with_build_log"])
    clean = vr.build_report("demo2", "flat_region", [{"code": "auto_rigged", "severity": "warn"}], build_log_ok=True)
    ok &= check("verification_report: warn-only stays ok=true", clean["ok"] is True and clean["ok_agrees_with_build_log"])

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
