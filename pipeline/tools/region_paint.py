"""Re-label a DEGENERATE per-frame region-id mask from projected region AABBs (ADR-0025 follow-up).

A single-material art model (one 'Material_0', e.g. a dragon) renders an all-torso region pass: the
R8 hit-mask has exactly one body id, even though the model's explicit hitbox map declares many regions.
This re-labels the silhouette using the per-region screen-space AABBs that blender_render.py projects
(world region_hitboxes -> screen, through the SAME camera+shift as the mesh, so they are pixel-aligned).

Only the SILHOUETTE (non-background) pixels are touched; the background and the silhouette SHAPE are
preserved exactly. Smaller-area boxes win (painted last), so a specific part (head) overrides the body.
This recovers a coarse multi-region mask collapsed to the engine's 4-body palette {head,torso,arms,legs};
the exact per-region world AABBs remain in the `<id>_hitbox.json` sidecar for any finer use.
"""
from __future__ import annotations

import numpy as np


def _area(rect) -> int:
    return max(0, int(rect[2])) * max(0, int(rect[3]))


def relabel_region_ids(ids: np.ndarray, rects) -> np.ndarray:
    """Return a copy of `ids` (2-D uint8, 0=bg) with silhouette pixels re-labelled by `rects`.

    `rects`: list of {"region_id": int(1..4), "rect": [x,y,w,h]} in the SAME frame-local pixel space
    as `ids`. Boxes are applied largest-first so the smallest (most specific) box wins on overlap.
    Background pixels (id 0) are never painted; the silhouette is never grown.
    """
    out = ids.copy()
    sil = ids != 0
    if not sil.any():
        return out
    h, w = ids.shape
    for r in sorted(rects, key=lambda r: _area(r.get("rect", [0, 0, 0, 0])), reverse=True):
        bid = int(r.get("region_id", 0))
        if bid <= 0:
            continue
        x, y, bw, bh = (int(v) for v in r["rect"])
        x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + bw), min(h, y + bh)
        if x1 <= x0 or y1 <= y0:
            continue
        view = out[y0:y1, x0:x1]            # basic slice -> a view; boolean assignment writes through
        view[sil[y0:y1, x0:x1]] = bid
    return out
