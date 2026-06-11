#!/usr/bin/env python3
"""Derive + validate the additive `collision_volumes` manifest block (engine contract:
docs/handoff/sprite-scenery-contracts/CONTRACT-scenery-structure-metadata.md).

A STRUCTURE model -- a wall with a window -- ships ONE block of per-part colliders so the engine never
needs to re-bake the model when its (currently OWED) consumers land. The contract splits the work:

  GEOMETRY is DERIVED (measured, by the bake):
    `footprint` (aabb: offset_world + half_extents_world) + `span_world` [bottom, top] come from each
    region's WORLD-space AABB in the region_hitboxes sidecar. World units = meters, +Z up, ground at
    z=0, origin at the ground-footprint center (ADR-0035). Direction-invariant, intact pose, ONE set
    per model (NOT per frame) -- LOS must not flicker with animation (the contract S4 rule). region_
    hitboxes is ALREADY the bake's per-region world input (ADR-0036; region_hitboxes.schema.json), so
    the volumes are that same measurement promoted to world units -- nothing re-implemented.

  SEMANTICS are AUTHORED (ride next to the geometry):
    `vision` (opaque|transparent) / `passable` / `material_class` / `projectile_response` (default +
    per-class) / `damage_variant_role` -- the modeler knows what is glass; not a measurement.

Pure: no Blender, no engine import. The ADR-034 guard holds -- the block carries FACTS (measured
geometry) and CLASS names, NEVER gameplay numbers (no HP / damage / resistance numerals; the engine
owns class -> MaterialBody). This module is the env consumer's; it imports nothing from pipeline/tools.
"""
from __future__ import annotations

import math

# The contract's closed enums (S3 / S6). The engine maps these names; the manifest never carries numbers.
PROJECTILE_RESPONSES = ("block_and_damage", "pass_ignore", "pass_and_damage")
VISION = ("opaque", "transparent")
DAMAGE_ROLES = ("damaged", "destroyed", None)


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def aabb_to_footprint_span(world_min, world_max) -> tuple[dict, list]:
    """A world-space AABB (meters, +Z up, origin at the ground-footprint center) -> (footprint, span_world).

    footprint = the HORIZONTAL (xy) occupancy as an aabb {shape, offset_world, half_extents_world};
    span_world = the VERTICAL [bottom, top] z interval. Both are direction-invariant world facts (the
    contract S4 derivation: span from the vertical extent, footprint from the horizontal extent + the
    origin anchor). offset_world is the volume center relative to the model origin.
    """
    mnx, mny, mnz = float(world_min[0]), float(world_min[1]), float(world_min[2])
    mxx, mxy, mxz = float(world_max[0]), float(world_max[1]), float(world_max[2])
    footprint = {
        "shape": "aabb",
        "offset_world": [round((mnx + mxx) / 2.0, 4), round((mny + mxy) / 2.0, 4)],
        "half_extents_world": [round((mxx - mnx) / 2.0, 4), round((mxy - mny) / 2.0, 4)],
    }
    span_world = [round(mnz, 4), round(mxz, 4)]
    return footprint, span_world


def _norm_response(pr: dict) -> dict:
    """Keep `default` (always) + `by_class` (only when authored) -- the contract S3 shape, stable key order."""
    out = {"default": pr["default"]}
    by = pr.get("by_class") or {}
    if by:
        out["by_class"] = {str(k): v for k, v in by.items()}
    return out


def derive_volumes(region_hitboxes: dict, authored: list) -> list:
    """Build the emitted `collision_volumes[]` from per-region WORLD AABBs + AUTHORED semantics.

    `region_hitboxes`: {region_name -> {"min":[x,y,z], "max":[x,y,z]}} (meters), the sidecar the bake
    already consumes. `authored`: the asset's per-region semantic rows (region + vision + passable +
    material_class + projectile_response + damage_variant_role). Authoring ORDER is preserved. Every
    authored region MUST have a world AABB (else its geometry cannot be measured -> hard error, never a
    silent guess).
    """
    volumes = []
    for a in authored:
        region = a["region"]
        box = (region_hitboxes or {}).get(region)
        if not (isinstance(box, dict) and isinstance(box.get("min"), list) and isinstance(box.get("max"), list)):
            raise SystemExit(
                f"collision_volumes: authored region '{region}' has no world AABB in the region_hitboxes "
                f"sidecar -- the bake measures geometry, it does not invent it. Add region_hitboxes['{region}'] "
                f"(min/max in meters) or remove the authored volume.")
        footprint, span_world = aabb_to_footprint_span(box["min"], box["max"])
        volumes.append({
            "region": region,
            "footprint": footprint,
            "span_world": span_world,
            "vision": a["vision"],
            "passable": bool(a["passable"]),
            "material_class": a["material_class"],
            "projectile_response": _norm_response(a["projectile_response"]),
            "damage_variant_role": a.get("damage_variant_role"),
        })
    return volumes


def _footprint_extents(fp: dict):
    shape = (fp or {}).get("shape")
    if shape == "aabb":
        return fp.get("half_extents_world")
    if shape == "circle":
        r = fp.get("radius_world")
        return [r] if r is not None else None
    return None


def _xy_overlap(a: dict, b: dict) -> bool:
    """AABB-footprint overlap in the horizontal plane (circle footprints fall back to a bounding box)."""
    def box(v):
        fp = v.get("footprint") or {}
        ox, oy = (fp.get("offset_world") or [0, 0])[:2]
        ext = _footprint_extents(fp) or [0, 0]
        hx = ext[0]
        hy = ext[1] if len(ext) > 1 else ext[0]
        return ox - hx, oy - hy, ox + hx, oy + hy
    ax0, ay0, ax1, ay1 = box(a)
    bx0, by0, bx1, by1 = box(b)
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def _span_overlap(s1, s2) -> bool:
    if not (isinstance(s1, list) and isinstance(s2, list) and len(s1) == 2 and len(s2) == 2):
        return False
    return s1[0] < s2[1] and s2[0] < s1[1]


def validate_volumes(volumes: list, world_metrics_present: bool) -> tuple[list, list]:
    """Mirror the contract S6 validation for the EMITTED block (the owed loader asserts the same shape;
    we assert it at BAKE time so a bad block never ships). Returns (errors, warnings): any error fails
    the bake; warnings are printed but allowed.
    """
    errors, warnings = [], []
    seen = set()
    for i, v in enumerate(volumes):
        tag = f"volume[{i}]({v.get('region', '?')})"
        region = v.get("region")
        if not region:
            errors.append(f"{tag}: region must be non-empty")
        elif region in seen:
            errors.append(f"{tag}: region '{region}' is not unique within the model")
        else:
            seen.add(region)

        span = v.get("span_world")
        if not (isinstance(span, list) and len(span) == 2 and all(_finite(s) for s in span)):
            errors.append(f"{tag}: span_world must be two finite numbers [bottom, top]")
        elif span[0] > span[1]:
            errors.append(f"{tag}: span_world bottom ({span[0]}) > top ({span[1]})")

        ext = _footprint_extents(v.get("footprint") or {})
        if not (ext and all(_finite(e) and e > 0 for e in ext)):
            errors.append(f"{tag}: footprint extents must be finite and > 0")

        if v.get("vision") not in VISION:
            errors.append(f"{tag}: vision must be one of {VISION}")
        if not isinstance(v.get("passable"), bool):
            errors.append(f"{tag}: passable must be a bool")

        pr = v.get("projectile_response") or {}
        if pr.get("default") not in PROJECTILE_RESPONSES:
            errors.append(f"{tag}: projectile_response.default must be one of {PROJECTILE_RESPONSES}")
        for cls, val in (pr.get("by_class") or {}).items():
            if val not in PROJECTILE_RESPONSES:
                errors.append(f"{tag}: projectile_response.by_class.{cls} must be one of {PROJECTILE_RESPONSES}")

        if v.get("damage_variant_role") not in DAMAGE_ROLES:
            errors.append(f"{tag}: damage_variant_role must be one of damaged|destroyed|null")

    # cross-volume: a fully inert volume set (every part passable AND transparent) is suspicious.
    if volumes and not any((not v.get("passable")) or v.get("vision") == "opaque" for v in volumes):
        errors.append("cross-volume: at least one volume must be non-passable OR opaque "
                      "(a fully passable+transparent set blocks nothing -- likely a mistake)")

    # warn (never reject) when two volumes occupy overlapping 3D space (the S6 span-overlap check,
    # tightened to xy AND z so far-apart parts at the same height are not flagged).
    for i in range(len(volumes)):
        for j in range(i + 1, len(volumes)):
            if _span_overlap(volumes[i].get("span_world"), volumes[j].get("span_world")) and _xy_overlap(volumes[i], volumes[j]):
                warnings.append(f"span overlap: '{volumes[i].get('region')}' and '{volumes[j].get('region')}' "
                                f"occupy overlapping space (ok for a window nested in a wall; check if unintended)")

    # whole-model: collision_volumes present requires world_metrics (sizing + eye source stay there).
    if volumes and not world_metrics_present:
        errors.append("whole-model: collision_volumes present requires world_metrics "
                      "(it stays as the sizing/eye source; the volumes only supersede the collider mapping)")

    return errors, warnings


def window_sockets(region_rects_by_dir: dict, window_regions: list, dirs: int) -> dict:
    """Per-direction projected px CENTER of each window (transparent) region, named `window_<n>_center`
    (n = the region's order in `window_regions`). Reuses the core's `region_rects` -- blender_render.py
    projects each region's world AABB to a px rect per direction AND keeps its `name` -- so nothing is
    re-projected here. Returns {dir_index: {socket_name: [px_x, px_y]}} for the directions that have a hit.
    """
    out = {}
    for d in range(dirs):
        per = region_rects_by_dir.get(str(d)) or region_rects_by_dir.get(d) or []
        by_name = {r.get("name"): r.get("rect") for r in per if r.get("name") and r.get("rect")}
        socks = {}
        for n, region in enumerate(window_regions):
            rect = by_name.get(region)
            if isinstance(rect, list) and len(rect) == 4:
                socks[f"window_{n}_center"] = [round(rect[0] + rect[2] / 2.0, 3), round(rect[1] + rect[3] / 2.0, 3)]
        if socks:
            out[d] = socks
    return out
