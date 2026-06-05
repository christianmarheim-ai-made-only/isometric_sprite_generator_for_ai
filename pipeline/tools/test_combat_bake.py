#!/usr/bin/env python3
"""Gate the rigged biped COMBAT bake (the canonical idle/move/punch/death template). The
`bake_anim_from_json` -> `bake_animated` path (JSON clip embedding onto biped_v1) had ZERO
end-to-end coverage -- only the bird was gated, so a regression in biped combat baking was silent.
Blender-skip (like the other Blender gates).

Run: python pipeline/tools/test_combat_bake.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_bake import find_blender  # noqa: E402
from bake_asset import bake_asset  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    if not find_blender():
        print("SKIP: Blender not found (combat-bake gate)")
        return 0
    ok = True
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "grunt"
        m = bake_asset(PIPELINE_ROOT / "examples" / "grunt.asset.json", out)
        anims = m["animations"]
        ok &= check("states are idle/move/punch/death", set(anims) == {"idle", "move", "punch", "death"})
        ok &= check("death playback=hold (final frame is the held corpse)", anims["death"]["playback"] == "hold")

        atlas = Image.open(out / "color_atlas.png").convert("RGBA")

        def dir_sigs(state: str, fi: int) -> dict:
            sig = {}
            for f in m["frames"]:
                if f.get("state") == state and f["frame_index"] == fi:
                    x, y, w, h = f["rect"]
                    sig[f["direction"]] = np.asarray(atlas.crop((x, y, x + w, y + h)).resize((48, 48))).tobytes()
            return sig

        for st in sorted(anims):
            c = dir_sigs(st, 0)
            ok &= check(f"{st}: 16/16 distinct directions (no 180-deg aliasing)",
                        len(c) == 16 and len(set(c.values())) == 16)

        hit_ids = set(int(v) for v in np.unique(np.asarray(Image.open(out / "hitmask_atlas.png").convert("L")))) - {0}
        ok &= check(f"hit regions within body set {{1,2,3,4}} and non-empty (got {sorted(hit_ids)})",
                    bool(hit_ids) and hit_ids <= {1, 2, 3, 4})

        log = json.loads((out / "build_log.json").read_text(encoding="utf-8"))
        ok &= check(f"build log clean: 0 warnings (got {[w['code'] for w in log['warnings']]})",
                    not log["warnings"])
        ok &= check("build log gate-1 pass", log["gates"]["gate_1_engine_accept"]["pass"])

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
