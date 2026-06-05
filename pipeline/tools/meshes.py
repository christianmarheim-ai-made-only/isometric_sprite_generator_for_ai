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
