#!/usr/bin/env python3
"""VERSIONED, HARD-CODED calibration-model definition (calib_v1). Single source of truth for both the
calibration-colour verification gate (calib_color.py) and the v3 producer spec. Calibration models are
fixed + versioned so they cannot be re-modelled and silently break the tests that depend on them.

The calibration skin paints each region a distinct, well-separated colour; the region_hitboxes sidecar
must cover the matching colour. The bake then verifies (calib_color.py) that the hitbox centre samples
the expected colour -- proving the texture, the UVs, AND the hitbox all agree.
"""
from __future__ import annotations

CALIB_SPEC_VERSION = "calib_v1"

# region (canonical key) -> the EXACT painted calibration colour (sRGB 0..255). Well-separated hues so a
# nearest-colour match is unambiguous. left = green, right = blue (the model's own left/right).
CALIBRATION_COLORS = {
    "head":      (216, 38, 38),    # red
    "torso":     (130, 130, 130),  # grey
    "arm_left":  (42, 196, 64),    # green   (left arm OR left wing)
    "arm_right": (40, 90, 224),    # blue    (right arm OR right wing)
    "legs":      (150, 42, 200),   # purple
    "tail":      (240, 138, 30),   # orange
}

# Hitbox region NAME -> canonical colour key. A calibration model may name a region by its anatomy
# (wing_left, foreleg, jaw, ...); this folds it to the 6 calibration colours. Order matters: the FIRST
# token found wins, and left/right qualifiers are checked before the bare limb.
_NAME_RULES = [
    ("head", "head"), ("skull", "head"), ("face", "head"), ("jaw", "head"), ("horn", "head"),
    ("mouth", "head"), ("eye", "head"), ("beak", "head"), ("neck", "head"),
    ("tail", "tail"),
    ("torso", "torso"), ("chest", "torso"), ("body", "torso"), ("spine", "torso"), ("pelvis", "torso"),
    ("wing_left", "arm_left"), ("wing_l", "arm_left"), ("arm_left", "arm_left"), ("arm_l", "arm_left"),
    ("foreleg_left", "arm_left"), ("foreleg_l", "arm_left"),
    ("wing_right", "arm_right"), ("wing_r", "arm_right"), ("arm_right", "arm_right"), ("arm_r", "arm_right"),
    ("foreleg_right", "arm_right"), ("foreleg_r", "arm_right"),
    ("leg", "legs"), ("hindleg", "legs"), ("foot", "legs"), ("thigh", "legs"), ("shin", "legs"),
]


def calib_color_key(region_name: str):
    """Fold a hitbox region name to its calibration colour key, or None if it is not a colour-bearing
    region (e.g. anchor_marker). Left/right qualifiers ('_left'/'_l', '_right'/'_r') win over the bare limb."""
    n = (region_name or "").lower()
    # explicit left/right limb qualifiers first
    for side, key in (("left", "arm_left"), ("_l", "arm_left"), ("right", "arm_right"), ("_r", "arm_right")):
        if side in n and ("wing" in n or "arm" in n or "foreleg" in n):
            return key
    for token, key in _NAME_RULES:
        if token in n:
            return key
    return None


# The IMMUTABLE per-archetype calibration model definitions (hard-coded world metrics + the region set
# each model must paint + hitbox). These are versioned: a producer reproduces THESE numbers exactly.
CALIBRATION_MODELS = {
    "biped": {
        "variant_id": "calib_biped_v1",
        "world_metrics": {"height_world": 1.80, "eye_height_world": 1.62, "footprint_radius_world": 0.40},
        "mass_kg": 75.0,
        "regions": ["head", "torso", "arm_left", "arm_right", "legs"],   # no tail
    },
    "dragon": {
        "variant_id": "calib_dragon_v1",
        "world_metrics": {"height_world": 2.128, "eye_height_world": 1.638, "footprint_radius_world": 1.55},
        "mass_kg": 862.0,
        "regions": ["head", "torso", "arm_left", "arm_right", "legs", "tail"],  # wings = arm_left/right
    },
}
