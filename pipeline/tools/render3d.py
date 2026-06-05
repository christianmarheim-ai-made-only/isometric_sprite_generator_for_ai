#!/usr/bin/env python3
"""Headless 3D renderer for the game_iso_v1 camera (slice R1).

A dependency-light (numpy) orthographic rasterizer that turns a triangle mesh into
the 16 game_iso_v1 direction frames -- no Blender, no GPU. The camera matches the
engine's projection: azimuth 45, elevation 30 (sin30=0.5 -> 2:1 ground, exactly
render.rs::project_iso for ground points). +X ground projects to screen (1, 0.5)
normalized = the oracle's dir00.

Absolute pixel scale is auto-fit to the canvas: the engine resizes the sprite by
height_world (render.rs::sprite_size), so only the foreshortening/aspect and the
directions matter here -- not pixels-per-meter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

COS30 = math.cos(math.radians(30.0))
SIN30 = 0.5  # sin(30) exactly
INV_SQRT2 = 1.0 / math.sqrt(2.0)


def rotate_z(verts: np.ndarray, yaw_rad: float) -> np.ndarray:
    """Rotate vertices about +Z (world heading), CCW."""
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return verts @ rot.T


def project_raw(verts: np.ndarray):
    """World (x,y,z) -> raw screen (rx, ry) at unit scale (y-down) + view depth.

    rx = (x - y)/sqrt2 ; ry = (x + y)/(2*sqrt2) - z*cos30
    Ground (z=0) is 2:1 and matches the engine; +X ground -> (1, 0.5) normalized.
    depth: larger = closer to the camera (used for the z-buffer).
    """
    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]
    rx = (x - y) * INV_SQRT2
    ry = (x + y) * (0.5 * INV_SQRT2) - z * COS30
    depth = (x + y) * (COS30 * INV_SQRT2) + z * SIN30
    return np.stack([rx, ry], axis=1), depth


def ground_screen_direction(yaw_rad: float) -> np.ndarray:
    """Unit screen direction (y-down) of a world heading -- the oracle definition."""
    wx, wy = math.cos(yaw_rad), math.sin(yaw_rad)
    v = np.array([wx - wy, 0.5 * (wx + wy)])
    n = np.linalg.norm(v)
    return v / n if n else v


@dataclass
class Frame:
    rgba: Image.Image
    bbox: tuple        # (x, y, w, h) tight alpha bbox in frame px
    anchor: tuple      # (ax, ay) foot (world origin) in frame px


def _fit(all_raw: np.ndarray, w: int, h: int, margin: int):
    rxmin, rymin = all_raw.min(axis=0)
    rxmax, rymax = all_raw.max(axis=0)
    s = min((w - 2 * margin) / max(rxmax - rxmin, 1e-6),
            (h - 2 * margin) / max(rymax - rymin, 1e-6))
    ox = w / 2.0 - s * (rxmin + rxmax) / 2.0
    oy = (h - margin) - s * rymax
    return s, ox, oy


def _rasterize(p2d, depth, faces, face_shade, w, h):
    color = np.zeros((h, w, 4), dtype=np.uint8)
    zbuf = np.full((h, w), -np.inf)
    for fi in range(len(faces)):
        a, b, c = faces[fi]
        xa, ya = p2d[a]
        xb, yb = p2d[b]
        xc, yc = p2d[c]
        minx = max(int(math.floor(min(xa, xb, xc))), 0)
        maxx = min(int(math.ceil(max(xa, xb, xc))), w - 1)
        miny = max(int(math.floor(min(ya, yb, yc))), 0)
        maxy = min(int(math.ceil(max(ya, yb, yc))), h - 1)
        if minx > maxx or miny > maxy:
            continue
        area = (xb - xa) * (yc - ya) - (xc - xa) * (yb - ya)
        if abs(area) < 1e-9:
            continue
        ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
        px = xs + 0.5
        py = ys + 0.5
        w0 = ((xb - px) * (yc - py) - (xc - px) * (yb - py)) / area
        w1 = ((xc - px) * (ya - py) - (xa - px) * (yc - py)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        d = w0 * depth[a] + w1 * depth[b] + w2 * depth[c]
        reg = zbuf[miny:maxy + 1, minx:maxx + 1]
        win = inside & (d > reg)
        reg[win] = d[win]
        sh = face_shade[fi]
        rgb = (int(40 + 200 * sh), int(60 + 180 * sh), int(95 + 150 * sh), 255)
        sub = color[miny:maxy + 1, minx:maxx + 1]
        sub[win] = rgb
    return color


def render_directions(verts, faces, n=16, canvas=(256, 256), margin=16, light=None):
    """Render `n` game_iso_v1 direction frames of a mesh. Returns a list of Frame."""
    verts = np.asarray(verts, dtype=float)
    faces = np.asarray(faces, dtype=int)
    w, h = canvas
    if light is None:
        light = np.array([0.3, 0.4, 0.85])
        light = light / np.linalg.norm(light)

    rots = [rotate_z(verts, i * (2 * math.pi / n)) for i in range(n)]
    all_raw = np.concatenate([project_raw(r)[0] for r in rots], axis=0)
    s, ox, oy = _fit(all_raw, w, h, margin)

    frames = []
    for r in rots:
        raw, depth = project_raw(r)
        p2d = np.stack([ox + s * raw[:, 0], oy + s * raw[:, 1]], axis=1)
        fn = np.cross(r[faces[:, 1]] - r[faces[:, 0]], r[faces[:, 2]] - r[faces[:, 0]])
        nrm = np.linalg.norm(fn, axis=1, keepdims=True)
        nrm[nrm == 0] = 1.0
        fn = fn / nrm
        shade = np.clip(np.abs(fn @ light), 0.15, 1.0)
        color = _rasterize(p2d, depth, faces, shade, w, h)
        img = Image.fromarray(color, "RGBA")
        ys, xs = np.where(color[:, :, 3] > 0)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)) if len(xs) else (0, 0, 0, 0)
        frames.append(Frame(img, bbox, (ox, oy)))
    return frames
