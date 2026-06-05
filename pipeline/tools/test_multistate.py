#!/usr/bin/env python3
"""R5 gate: bake the multi-state, tight-cropped humanoid and assert the multi-state +
tight-crop contract (multistate_sprite_contract.md):
  - Gate-1 acceptance (coverage rules);
  - per-(state,direction) frame_index complete + unique;
  - tight-crop sizing invariant (tight rect + trim fit within logical_frame_canvas);
  - root-XY stability (the foot anchor is identical across all frames -> no foot slide);
  - discrete R8 hitmask with all four regions;
  - backward-compat (the single-state character is still engine-accepted).

Run: python pipeline/tools/test_multistate.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake import bake_character_anim, bake_character  # noqa: E402
from gate_engine_accept import engine_accept  # noqa: E402


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "humanoid_anim"
        m = bake_character_anim(out, canvas_px=256)
        anims = m["animations"]

        ok &= check("multi-state package engine-accepted (Gate-1 coverage)", not engine_accept(m))
        ok &= check("animations: idle(1) + walk(4); default_state idle",
                    anims["idle"]["frames"] == 1 and anims["walk"]["frames"] == 4 and m["default_state"] == "idle")

        cover: dict = {}
        for f in m["frames"]:
            cover.setdefault((f["state"], f["direction"]), set()).add(f["frame_index"])
        cov_ok = all(cover.get((s, d)) == set(range(anims[s]["frames"])) for s in anims for d in range(16))
        ok &= check("coverage complete+unique per (state,direction); total = 16*(1+4)",
                    cov_ok and len(m["frames"]) == 16 * (1 + 4))

        lw, lh = m["logical_frame_canvas"]
        crop_ok = all(
            0 <= f["trim"][0] and 0 <= f["trim"][1]
            and f["trim"][0] + f["rect"][2] <= lw and f["trim"][1] + f["rect"][3] <= lh
            for f in m["frames"]
        )
        ok &= check("tight rect+trim fits within logical_frame_canvas (R5B sizing invariant)", crop_ok)

        anchors = {tuple(f["anchor"]) for f in m["frames"]}
        ok &= check(f"root anchor identical across all frames -> no foot slide ({len(anchors)} unique)", len(anchors) == 1)

        mask = np.asarray(Image.open(out / "hitmask_atlas.png").convert("L"))
        vals = {int(v) for v in np.unique(mask)}
        ok &= check(f"hitmask discrete & all 4 regions (got {sorted(vals)})", vals <= {0, 1, 2, 3, 4} and {1, 2, 3, 4} <= vals)

        m1 = bake_character(Path(td) / "humanoid_ref", canvas_px=256)
        ok &= check("single-state character still engine-accepted (backward-compat)", not engine_accept(m1))

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
