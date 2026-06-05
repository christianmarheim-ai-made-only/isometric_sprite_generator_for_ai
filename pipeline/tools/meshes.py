#!/usr/bin/env python3
"""Procedural test meshes for the R1 renderer (no external assets).

All meshes stand on the z=0 ground plane (foot at the world origin), forward +X,
up +Z, units = meters -- matching the game_iso_v1 contract.
"""
from __future__ import annotations

import numpy as np


def box(x0, x1, y0, y1, z0, z1):
    """An axis-aligned box as (vertices Nx3, faces Mx3)."""
    v = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ], dtype=float)
    f = np.array([
        [0, 2, 1], [0, 3, 2],   # bottom
        [4, 5, 6], [4, 6, 7],   # top
        [0, 1, 5], [0, 5, 4],   # -y
        [1, 2, 6], [1, 6, 5],   # +x
        [2, 3, 7], [2, 7, 6],   # +y
        [3, 0, 4], [3, 4, 7],   # -x
    ], dtype=int)
    return v, f


def cube(size=1.0):
    """Unit cube, base on z=0 (extends up)."""
    h = size / 2.0
    return box(-h, h, -h, h, 0.0, size)


def pole(height=2.0, radius=0.06):
    """A tall thin vertical post -- foreshortening / height calibration."""
    return box(-radius, radius, -radius, radius, 0.0, height)


def arrow_wedge(length=0.6, z=0.02):
    """A flat arrow in the XY plane pointing +X (foot at origin).

    Flat (near-zero thickness) so it reads as a ground decal -- the
    elevation-immune cross-check against the 2D direction pilot.
    """
    sw, hw = 0.08, 0.22         # shaft / head half-widths
    sx = length * 0.25          # shaft -> head transition
    tail = -length * 0.6
    tip = length
    pts = [
        (tail, sw), (sx, sw), (sx, hw), (tip, 0.0),
        (sx, -hw), (sx, -sw), (tail, -sw),
    ]
    v = np.array([[p[0], p[1], z] for p in pts], dtype=float)
    f = np.array([[0, 1, 5], [0, 5, 6], [2, 3, 4]], dtype=int)
    return v, f


# HIT regions (body-only; matches mask_palette none0/head1/torso2/arms3/legs4).
REGION = {"head": 1, "torso": 2, "arms": 3, "legs": 4}


def _assemble(parts):
    """Combine [(verts, faces, region_id), ...] into (verts, faces, face_region)."""
    vs, fs, rs = [], [], []
    offset = 0
    for v, f, r in parts:
        vs.append(v)
        fs.append(f + offset)
        rs.append(np.full(len(f), r, dtype=int))
        offset += len(v)
    return np.concatenate(vs), np.concatenate(fs), np.concatenate(rs)


def humanoid():
    """A body-only humanoid (~1.8 m) built from boxes -- foot at origin, facing +X.

    Per-face HIT region: head 1, torso 2, arms 3, legs 4 (no weapons/shield/gear this
    iteration). Returns (verts Nx3, faces Mx3, face_region M,) for the R8 HIT proxy.
    """
    parts = []
    for sy in (-1.0, 1.0):                                   # two legs
        cy = sy * 0.20
        parts.append((*box(-0.11, 0.11, cy - 0.10, cy + 0.10, 0.0, 0.92), REGION["legs"]))
    parts.append((*box(-0.16, 0.16, -0.24, 0.24, 0.88, 1.46), REGION["torso"]))
    for sy in (-1.0, 1.0):                                   # two arms, outboard of the torso
        cy = sy * 0.31
        parts.append((*box(-0.08, 0.08, cy - 0.07, cy + 0.07, 0.86, 1.42), REGION["arms"]))
    parts.append((*box(-0.12, 0.12, -0.12, 0.12, 1.46, 1.80), REGION["head"]))
    return _assemble(parts)
