#!/usr/bin/env python3
"""Compute body world_metrics from a METRIC_ proxy bounding box (C4).

Pure, Blender-free computation. The Blender exporter measures the METRIC_body
proxy axis-aligned bounds (meters, +Z up, ground plane at z = 0, origin at the
footprint center) and an optional head/eye socket Z, then calls
compute_world_metrics(). Held weapons, shields, loose gear, backpacks, capes, and
VFX are EXCLUDED from the proxy and therefore from these metrics (ADR-0007);
visual/equipment bounds, if needed, are reported separately.

Run directly for a self-check:  python pipeline/tools/measure_metrics.py
"""
from __future__ import annotations

from typing import Optional

Vec3 = tuple[float, float, float]


def compute_world_metrics(body_min: Vec3, body_max: Vec3, eye_z: Optional[float] = None) -> dict:
    """Return world_metrics (meters) from a METRIC_body AABB.

    Convention: +Z up, ground plane at z = 0, origin at the footprint center.
    - height_world: top of the body above the ground (body_max.z).
    - footprint_radius_world: largest horizontal half-extent from the origin.
    - eye_height_world: head/eye height, only when provided; must be <= height.
    """
    min_x, min_y, _min_z = body_min
    max_x, max_y, max_z = body_max

    height_world = max_z
    footprint_radius_world = max(abs(min_x), abs(max_x), abs(min_y), abs(max_y))

    if height_world <= 0:
        raise ValueError(f"height_world must be > 0 (got {height_world}); check proxy/units")
    if footprint_radius_world <= 0:
        raise ValueError(f"footprint_radius_world must be > 0 (got {footprint_radius_world})")

    metrics = {
        "height_world": round(height_world, 4),
        "footprint_radius_world": round(footprint_radius_world, 4),
        "unit": "meter",
    }
    if eye_z is not None:
        if eye_z <= 0:
            raise ValueError(f"eye_height_world must be > 0 when present (got {eye_z})")
        if eye_z > height_world + 1e-6:
            raise ValueError(f"eye_height_world ({eye_z}) must be <= height_world ({height_world})")
        metrics["eye_height_world"] = round(eye_z, 4)
    # No head/eye bone -> omit eye entirely (never emit zero).
    return metrics


def _selfcheck() -> int:
    ok = True

    m = compute_world_metrics((-0.32, -0.30, 0.0), (0.32, 0.30, 1.82), eye_z=1.62)
    c1 = (m["height_world"] == 1.82 and m["footprint_radius_world"] == 0.32
          and m["eye_height_world"] == 1.62 and m["unit"] == "meter")
    print(("PASS" if c1 else "FAIL") + f": humanoid -> {m}")
    ok &= c1

    no_eye = compute_world_metrics((-0.1, -0.1, 0.0), (0.1, 0.1, 0.2))
    c2 = "eye_height_world" not in no_eye
    print(("PASS" if c2 else "FAIL") + f": no eye bone omits eye -> {no_eye}")
    ok &= c2

    rejected = False
    try:
        compute_world_metrics((-0.1, -0.1, 0.0), (0.1, 0.1, 1.0), eye_z=2.0)
    except ValueError:
        rejected = True
    print(("PASS" if rejected else "FAIL") + ": eye > height rejected")
    ok &= rejected

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
