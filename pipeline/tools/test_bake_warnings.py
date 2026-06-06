#!/usr/bin/env python3
"""Gate the build-log SILENT-FAILURE detectors added after the pirate PoC.

The pirate first baked LYING DOWN (wrong up-axis) yet passed Gate-1 AND 16/16-direction-distinctness
AND region checks -- every gate green on a broken sprite. These detectors turn that class of silent
failure into build_log warnings (surfaced per-variant in build_index, so a BATCH flags it):
  - world_metrics_mismatch : authored vs measured height diverge (wrong scale / lying down)
  - non_upright_biped      : a biped silhouette that is landscape, not portrait
  - degenerate_uv          : a textured material whose UVs collapse -> renders flat
  - base_color_linked      : a material's Base Color is node-driven (vertex-colour Mix from a glTF
                             re-import), not the Principled default -> risk of silent flat-grey render
Pure Python, fast (no Blender).

Run: python pipeline/tools/test_bake_warnings.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_log import _metrics_mismatch, _non_upright, write_build_log  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True

    # --- world_metrics_mismatch: authored vs measured height (calibrated on the pirate) ---
    lying = {"world_metrics": {"height_world": 1.03}}      # the lying-down bake
    standing = {"world_metrics": {"height_world": 2.015}}  # standing = body 1.82 + hat
    ok &= check("metrics: authored 1.82 vs measured 1.03 (43%) FIRES",
                _metrics_mismatch(lying, {"height_world": 1.82}) is not None)
    ok &= check("metrics: authored 1.82 vs measured 2.015 (hat, 10.7%) does NOT fire",
                _metrics_mismatch(standing, {"height_world": 1.82}) is None)
    ok &= check("metrics: no authored metrics -> no fire",
                _metrics_mismatch(lying, None) is None)

    # --- non_upright_biped: silhouette aspect, archetype-gated ---
    portrait = {"frames": [{"rect": [0, 0, 70, 126]}] * 16}    # pirate idle 0.56
    landscape = {"frames": [{"rect": [0, 0, 134, 76]}] * 16}   # lying-down idle 1.76
    ok &= check("upright: landscape biped FIRES", _non_upright(landscape, "biped") is not None)
    ok &= check("upright: portrait biped does NOT fire", _non_upright(portrait, "biped") is None)
    ok &= check("upright: landscape NON-biped (bird wings) skipped",
                _non_upright(landscape, "bird") is None)

    # --- integration through write_build_log ---
    with tempfile.TemporaryDirectory() as td:
        deg = write_build_log(Path(td), {"variant_id": "t", "animations": {}, "frames": [],
                                         "atlases": {"color": {"size": [10, 10]}}},
                              "test", meta={"degenerate_uv_materials": ["coat", "sash"]})
        ok &= check("degenerate_uv: 2 collapsed materials -> 2 warnings",
                    [w["code"] for w in deg["warnings"]].count("degenerate_uv") == 2)

        # base_color_linked: a glTF re-import wiring vertex-colour Mix into Base Color renders SILENT grey
        bcl = write_build_log(Path(td), {"variant_id": "c", "animations": {}, "frames": [],
                                         "atlases": {"color": {"size": [10, 10]}}},
                              "test", meta={"base_color_linked_materials": ["torso_body", "head_head"]})
        ok &= check("base_color_linked: 2 node-driven base colours -> 2 warnings",
                    [w["code"] for w in bcl["warnings"]].count("base_color_linked") == 2)

        bad = {"variant_id": "b", "world_metrics": {"height_world": 1.03}, "animations": {},
               "frames": [{"rect": [0, 0, 134, 76]}] * 16, "atlases": {"color": {"size": [10, 10]}}}
        log = write_build_log(Path(td), bad, "test", archetype="biped",
                              authored_metrics={"height_world": 1.82})
        codes = {w["code"] for w in log["warnings"]}
        ok &= check("lying-down biped: BOTH detectors fire and log.ok=False",
                    "non_upright_biped" in codes and "world_metrics_mismatch" in codes and not log["ok"])

        # a correct standing biped trips neither orientation detector
        good = {"variant_id": "g", "world_metrics": {"height_world": 2.015}, "animations": {},
                "frames": [{"rect": [0, 0, 70, 126]}] * 16, "atlases": {"color": {"size": [10, 10]}}}
        glog = write_build_log(Path(td), good, "test", archetype="biped",
                               authored_metrics={"height_world": 1.82})
        gcodes = {w["code"] for w in glog["warnings"]}
        ok &= check("standing biped: neither orientation detector fires",
                    "non_upright_biped" not in gcodes and "world_metrics_mismatch" not in gcodes)

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
