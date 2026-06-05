#!/usr/bin/env python3
"""Regression guard: a CHARACTER must render 16 DISTINCT directions.

Catches the 180-degree render-aliasing class of bug: when a body is symmetric under a 180-deg
rotation about the vertical axis (centered torso/head + anti-phase L/R limbs), heading N renders
BYTE-IDENTICAL to heading N+8 -- front cannot be told from back, and only 8 of 16 facings are real.

This shipped once: the procedural humanoid was front/back symmetric until a front feature (face
visor + chest plate) was added to meshes.humanoid(). Gate-1 and the structural gates all PASSED on
the broken output (coverage/bounds/facing were fine); only a pixel-distinctness check catches it.
Numpy-only so it always runs (no Blender dependency) and is fast.

Run: python pipeline/tools/test_direction_distinctness.py
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

from bake import bake_character, bake_character_anim  # noqa: E402

FB_MAD_MIN = 1.0  # color: front (dir N) vs back (dir N+8) must differ by >= this mean-abs-diff


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def _groups(manifest: dict):
    g: dict[tuple, dict[int, dict]] = {}
    for f in manifest["frames"]:
        g.setdefault((f.get("state", "idle"), f.get("frame_index", 0)), {})[f["direction"]] = f
    return g


def _assert(label: str, mpath: Path, apath: Path, rect_key: str, mad_min: float | None, ok: bool) -> bool:
    m = json.loads(mpath.read_text(encoding="utf-8"))
    atlas = Image.open(apath)
    dc = int(m["direction_count"])
    half = dc // 2
    for (state, fi), by_dir in _groups(m).items():
        crops = {}
        for d, f in by_dir.items():
            x, y, w, h = f[rect_key]
            crops[d] = np.asarray(atlas.crop((x, y, x + w, y + h)).convert("RGBA"), dtype=np.int16)
        uniq = len({c.tobytes() for c in crops.values()})
        ok &= check(f"{label} {state} f{fi}: {uniq}/{dc} directions byte-distinct (no 180-deg aliasing)",
                    uniq == dc and len(crops) == dc)
        if mad_min is not None:
            worst, worst_pair = 1e9, None
            for i in range(half):
                a, b = crops.get(i), crops.get(i + half)
                if a is None or b is None:
                    continue
                mad = 1e9 if a.shape != b.shape else float(np.abs(a - b).mean())
                if mad < worst:
                    worst, worst_pair = mad, (i, i + half)
            ok &= check(f"{label} {state} f{fi}: front/back min MAD={worst:.3f} > {mad_min} "
                        f"(pair d{worst_pair[0]}/d{worst_pair[1]})", worst > mad_min)
    return ok


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        bake_character(tdp / "ref", 256)
        bake_character_anim(tdp / "anim", 256)
        for name in ("ref", "anim"):
            mp = tdp / name / "manifest.json"
            ok = _assert(f"humanoid_{name} color", mp, tdp / name / "color_atlas.png", "rect", FB_MAD_MIN, ok)
            ok = _assert(f"humanoid_{name} hit", mp, tdp / name / "hitmask_atlas.png", "mask_rect", None, ok)
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
