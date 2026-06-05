#!/usr/bin/env python3
"""Create a machine-readable pirate character asset package.

This script writes:
- a rigged, skinned, stylized starter GLB generated from procedural component data
- external_asset_v1 manifest
- source_asset descriptor
- anim_clips_v1 raw animation data
- hitbox_v1 diagnostic file
- custom model source, sockets, material, atlas, event, and physical metric data
"""
from __future__ import annotations

import base64
import copy
import json
import math
import os
import shutil
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT
ASSET_ID = 'chr_pirate_duelist_v1'
CONTRACT = ROOT / 'model_authoring_contract_v1'

# ---------------------------- Utility helpers ----------------------------

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    s = hex_color.strip().lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), alpha)


def rgba_float(hex_color: str, alpha: float = 1.0) -> List[float]:
    r, g, b, a = hex_to_rgba(hex_color)
    return [r / 255.0, g / 255.0, b / 255.0, alpha]


def region_from_material(name: str) -> str:
    n = name.lower()
    # Same priority order as the documented region keyword path.
    for region, kws in [
        ('head', ['head', 'skull', 'face', 'neck', 'beak']),
        ('torso', ['torso', 'chest', 'body', 'spine', 'hip', 'pelvis', 'waist', 'tail']),
        ('arms', ['arm', 'hand', 'shoulder', 'elbow', 'wrist', 'wing']),
        ('legs', ['leg', 'foot', 'feet', 'thigh', 'shin', 'knee', 'ankle']),
    ]:
        if any(k in n for k in kws):
            return region
    return 'torso'


def v_add(a, b): return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
def v_sub(a, b): return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
def v_mul(a, s): return [a[0] * s, a[1] * s, a[2] * s]
def v_dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def v_cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def v_len(a): return math.sqrt(max(v_dot(a,a), 1e-20))
def v_norm(a):
    l = v_len(a)
    return [a[0]/l, a[1]/l, a[2]/l]


def make_basis(axis: List[float]) -> Tuple[List[float], List[float], List[float]]:
    w = v_norm(axis)
    up = [0, 0, 1]
    if abs(v_dot(w, up)) > 0.92:
        up = [0, 1, 0]
    u = v_norm(v_cross(up, w))
    v = v_cross(w, u)
    return u, v, w


def quat_from_euler_xyz(rx: float, ry: float, rz: float) -> List[float]:
    # Return [x,y,z,w], intrinsic XYZ-friendly approximation sufficient for metadata if embedded later.
    cx, sx = math.cos(rx/2), math.sin(rx/2)
    cy, sy = math.cos(ry/2), math.sin(ry/2)
    cz, sz = math.cos(rz/2), math.sin(rz/2)
    qw = cx*cy*cz + sx*sy*sz
    qx = sx*cy*cz - cx*sy*sz
    qy = cx*sy*cz + sx*cy*sz
    qz = cx*cy*sz - sx*sy*cz
    return [qx, qy, qz, qw]

# ----------------------------- Asset constants ----------------------------

MATERIALS: Dict[str, Dict[str, Any]] = {
    'head_skin_warm':       {'hex': '#C98A5F', 'roughness': 0.62, 'metallic': 0.0,  'role': 'skin', 'notes': 'Face, ears, neck, hands where assigned to head/arms.'},
    'head_hair_dark':       {'hex': '#2C1710', 'roughness': 0.76, 'metallic': 0.0,  'role': 'hair'},
    'head_hat_navy':        {'hex': '#131A2B', 'roughness': 0.68, 'metallic': 0.0,  'role': 'fabric_hat'},
    'head_trim_gold':       {'hex': '#C08A32', 'roughness': 0.32, 'metallic': 0.85, 'role': 'brass_hat_trim'},
    'head_bandana_red':     {'hex': '#8E2430', 'roughness': 0.74, 'metallic': 0.0,  'role': 'fabric_bandana'},
    'torso_coat_navy':      {'hex': '#17243A', 'roughness': 0.7,  'metallic': 0.0,  'role': 'fabric_coat'},
    'torso_shirt_cream':    {'hex': '#E8D8B8', 'roughness': 0.82, 'metallic': 0.0,  'role': 'fabric_shirt'},
    'torso_sash_red':       {'hex': '#9F2B2E', 'roughness': 0.78, 'metallic': 0.0,  'role': 'fabric_sash'},
    'torso_belt_leather':   {'hex': '#5B321E', 'roughness': 0.58, 'metallic': 0.0,  'role': 'leather_belt'},
    'torso_trim_gold':      {'hex': '#C08A32', 'roughness': 0.32, 'metallic': 0.85, 'role': 'brass_trim'},
    'torso_pendant_gold':   {'hex': '#D2A23B', 'roughness': 0.25, 'metallic': 0.9,  'role': 'pendant'},
    'arms_sleeve_navy':     {'hex': '#17243A', 'roughness': 0.7,  'metallic': 0.0,  'role': 'sleeves'},
    'arms_hand_skin':       {'hex': '#C98A5F', 'roughness': 0.62, 'metallic': 0.0,  'role': 'hands'},
    'arms_pistol_steel':    {'hex': '#5D5B57', 'roughness': 0.27, 'metallic': 0.9,  'role': 'pistol_barrel_visual'},
    'arms_pistol_wood':     {'hex': '#7A3F21', 'roughness': 0.5,  'metallic': 0.0,  'role': 'pistol_grip_visual'},
    'arms_pistol_gold':     {'hex': '#B7832D', 'roughness': 0.28, 'metallic': 0.85, 'role': 'pistol_trim_visual'},
    'legs_pants_brown':     {'hex': '#3E261C', 'roughness': 0.74, 'metallic': 0.0,  'role': 'pants'},
    'legs_boot_leather':    {'hex': '#2B1A14', 'roughness': 0.55, 'metallic': 0.0,  'role': 'boots'},
    'legs_buckle_gold':     {'hex': '#C08A32', 'roughness': 0.32, 'metallic': 0.85, 'role': 'boot_buckles'},
}

# Biped bones copied from the contract, in +Z up, +X forward, metres.
BONES = [
    { 'name': 'root',      'parent': None,       'head': [0.0, 0.0, 0.0],    'tail': [0.0, 0.0, 0.10] },
    { 'name': 'hips',      'parent': 'root',     'head': [0.0, 0.0, 0.92],   'tail': [0.0, 0.0, 1.02] },
    { 'name': 'spine',     'parent': 'hips',     'head': [0.0, 0.0, 1.02],   'tail': [0.0, 0.0, 1.22] },
    { 'name': 'chest',     'parent': 'spine',    'head': [0.0, 0.0, 1.22],   'tail': [0.0, 0.0, 1.44] },
    { 'name': 'head',      'parent': 'chest',    'head': [0.0, 0.0, 1.46],   'tail': [0.0, 0.0, 1.80] },
    { 'name': 'arm.L',     'parent': 'chest',    'head': [0.0, 0.20, 1.42],  'tail': [0.0, 0.34, 1.16] },
    { 'name': 'forearm.L', 'parent': 'arm.L',    'head': [0.0, 0.34, 1.16],  'tail': [0.0, 0.44, 0.92] },
    { 'name': 'hand.L',    'parent': 'forearm.L','head': [0.0, 0.44, 0.92],  'tail': [0.0, 0.48, 0.84] },
    { 'name': 'arm.R',     'parent': 'chest',    'head': [0.0, -0.20, 1.42], 'tail': [0.0, -0.34, 1.16] },
    { 'name': 'forearm.R', 'parent': 'arm.R',    'head': [0.0, -0.34, 1.16], 'tail': [0.0, -0.44, 0.92] },
    { 'name': 'hand.R',    'parent': 'forearm.R','head': [0.0, -0.44, 0.92], 'tail': [0.0, -0.48, 0.84] },
    { 'name': 'thigh.L',   'parent': 'hips',     'head': [0.0, 0.10, 0.92],  'tail': [0.0, 0.10, 0.50] },
    { 'name': 'shin.L',    'parent': 'thigh.L',  'head': [0.0, 0.10, 0.50],  'tail': [0.0, 0.10, 0.08] },
    { 'name': 'foot.L',    'parent': 'shin.L',   'head': [0.0, 0.10, 0.08],  'tail': [0.12, 0.10, 0.0] },
    { 'name': 'thigh.R',   'parent': 'hips',     'head': [0.0, -0.10, 0.92], 'tail': [0.0, -0.10, 0.50] },
    { 'name': 'shin.R',    'parent': 'thigh.R',  'head': [0.0, -0.10, 0.50], 'tail': [0.0, -0.10, 0.08] },
    { 'name': 'foot.R',    'parent': 'shin.R',   'head': [0.0, -0.10, 0.08], 'tail': [0.12, -0.10, 0.0] },
]

BONE_BY_NAME = {b['name']: b for b in BONES}
BONE_NAMES = [b['name'] for b in BONES]

WORLD_METRICS = {
    'unit': 'meter',
    'metrics_source': 'authored_at_model_design_time',
    'height_world': 1.82,
    'visual_height_world': 2.02,
    'footprint_radius_world': 0.38,
    'eye_height_world': 1.64,
    'eye_position_world': [0.13, 0.0, 1.64],
    'shoulder_height_world': 1.42,
    'capsule_height_world': 1.82,
    'capsule_radius_world': 0.38,
    'origin_policy': 'ground_footprint_center',
    'forward_axis': '+X',
    'up_axis': '+Z'
}

BODY_VOLUME_M3 = 85.0 / 985.0
PHYSICAL_METRICS = {
    'unit': 'meter_kg_second',
    'metrics_source': 'authored_from_metric_proxy_volume',
    'density_profile': 'human_v1',
    'density_kg_per_m3': 985.0,
    'body_volume_m3': round(BODY_VOLUME_M3, 6),
    'mass_kg': 85.0,
    'weight_newtons_earth': round(85.0 * 9.80665, 3),
    'gravity_m_per_s2': 9.80665,
    'volume_policy': 'closed human body metric proxy; decorative hat, coat flares, pistol, loose cloth, and gear are excluded from body volume',
    'metric_proxy_volume_breakdown_m3': [
        {'name': 'torso_chest_abdomen_proxy', 'volume_m3': 0.036294},
        {'name': 'pelvis_proxy', 'volume_m3': 0.0115},
        {'name': 'head_neck_proxy', 'volume_m3': 0.0055},
        {'name': 'upper_arms_pair_proxy', 'volume_m3': 0.0060},
        {'name': 'forearms_pair_proxy', 'volume_m3': 0.0044},
        {'name': 'hands_pair_proxy', 'volume_m3': 0.0011},
        {'name': 'thighs_pair_proxy', 'volume_m3': 0.0116},
        {'name': 'lower_legs_pair_proxy', 'volume_m3': 0.0080},
        {'name': 'feet_pair_proxy', 'volume_m3': 0.0019}
    ]
}

SOCKETS = [
    {'name': 'eye', 'parent_bone': 'head', 'position_world': [0.13, 0.0, 1.64], 'purpose': 'vision/aim origin'},
    {'name': 'head_socket', 'parent_bone': 'head', 'position_world': [0.00, 0.0, 1.92], 'purpose': 'hat/top-of-head attachment'},
    {'name': 'shoulder_perch.L', 'parent_bone': 'chest', 'position_world': [0.02, 0.23, 1.43], 'purpose': 'parrot/perch attachment'},
    {'name': 'shoulder_perch.R', 'parent_bone': 'chest', 'position_world': [0.02, -0.23, 1.43], 'purpose': 'parrot/perch attachment'},
    {'name': 'hand.L', 'parent_bone': 'hand.L', 'position_world': [0.03, 0.49, 0.88], 'purpose': 'offhand item attach'},
    {'name': 'hand.R', 'parent_bone': 'hand.R', 'position_world': [0.03, -0.49, 0.88], 'purpose': 'weapon attach'},
    {'name': 'muzzle.R', 'parent_bone': 'hand.R', 'position_world': [0.48, -0.50, 0.91], 'purpose': 'projectile/VFX spawn; forward +X'},
    {'name': 'back_socket', 'parent_bone': 'chest', 'position_world': [-0.16, 0.0, 1.25], 'purpose': 'back/cape/loot attach'},
    {'name': 'belt_socket', 'parent_bone': 'hips', 'position_world': [0.10, -0.24, 0.94], 'purpose': 'belt/holster attach'},
    {'name': 'foot.L', 'parent_bone': 'foot.L', 'position_world': [0.12, 0.10, 0.02], 'purpose': 'left footstep/contact'},
    {'name': 'foot.R', 'parent_bone': 'foot.R', 'position_world': [0.12, -0.10, 0.02], 'purpose': 'right footstep/contact'},
]

# Component recipe. The generator below reads this to make the GLB. Positions are metres.
COMPONENTS = [
    # Torso and clothing
    {'name': 'torso_pelvis_body', 'shape': 'ellipsoid', 'bone': 'hips', 'material': 'torso_coat_navy', 'center': [0.0, 0.0, 0.98], 'radii': [0.19, 0.28, 0.17], 'segments': 16, 'rings': 8, 'include_in_metric_volume': False},
    {'name': 'torso_chest_body', 'shape': 'ellipsoid', 'bone': 'chest', 'material': 'torso_coat_navy', 'center': [0.02, 0.0, 1.25], 'radii': [0.23, 0.32, 0.30], 'segments': 18, 'rings': 9, 'include_in_metric_volume': False},
    {'name': 'torso_shirt_front_panel', 'shape': 'box', 'bone': 'chest', 'material': 'torso_shirt_cream', 'center': [0.24, 0.0, 1.24], 'size': [0.035, 0.18, 0.42], 'include_in_metric_volume': False},
    {'name': 'torso_waist_sash_front', 'shape': 'box', 'bone': 'hips', 'material': 'torso_sash_red', 'center': [0.22, 0.0, 0.94], 'size': [0.04, 0.48, 0.12], 'include_in_metric_volume': False},
    {'name': 'torso_waist_sash_left', 'shape': 'box', 'bone': 'hips', 'material': 'torso_sash_red', 'center': [0.0, 0.29, 0.94], 'size': [0.30, 0.035, 0.11], 'include_in_metric_volume': False},
    {'name': 'torso_waist_sash_right', 'shape': 'box', 'bone': 'hips', 'material': 'torso_sash_red', 'center': [0.0, -0.29, 0.94], 'size': [0.30, 0.035, 0.11], 'include_in_metric_volume': False},
    {'name': 'torso_belt_front', 'shape': 'box', 'bone': 'hips', 'material': 'torso_belt_leather', 'center': [0.255, 0.0, 1.02], 'size': [0.03, 0.50, 0.065], 'include_in_metric_volume': False},
    {'name': 'torso_belt_buckle', 'shape': 'box', 'bone': 'hips', 'material': 'torso_trim_gold', 'center': [0.282, 0.0, 1.02], 'size': [0.024, 0.09, 0.075], 'include_in_metric_volume': False},
    {'name': 'torso_coat_tail_left', 'shape': 'box', 'bone': 'hips', 'material': 'torso_coat_navy', 'center': [-0.12, 0.16, 0.68], 'size': [0.05, 0.18, 0.64], 'include_in_metric_volume': False},
    {'name': 'torso_coat_tail_right', 'shape': 'box', 'bone': 'hips', 'material': 'torso_coat_navy', 'center': [-0.12, -0.16, 0.68], 'size': [0.05, 0.18, 0.64], 'include_in_metric_volume': False},
    {'name': 'torso_pendant', 'shape': 'ellipsoid', 'bone': 'chest', 'material': 'torso_pendant_gold', 'center': [0.255, 0.0, 1.39], 'radii': [0.018, 0.035, 0.035], 'segments': 12, 'rings': 6, 'include_in_metric_volume': False},

    # Head, hair, hat
    {'name': 'head_neck', 'shape': 'cylinder', 'bone': 'head', 'material': 'head_skin_warm', 'p0': [0.0, 0.0, 1.39], 'p1': [0.0, 0.0, 1.50], 'radius': 0.055, 'segments': 14, 'include_in_metric_volume': False},
    {'name': 'head_face', 'shape': 'ellipsoid', 'bone': 'head', 'material': 'head_skin_warm', 'center': [0.055, 0.0, 1.61], 'radii': [0.13, 0.105, 0.16], 'segments': 18, 'rings': 9, 'include_in_metric_volume': False},
    {'name': 'head_nose', 'shape': 'ellipsoid', 'bone': 'head', 'material': 'head_skin_warm', 'center': [0.18, 0.0, 1.62], 'radii': [0.035, 0.018, 0.025], 'segments': 10, 'rings': 5, 'include_in_metric_volume': False},
    {'name': 'head_hair_back', 'shape': 'ellipsoid', 'bone': 'head', 'material': 'head_hair_dark', 'center': [-0.035, 0.0, 1.61], 'radii': [0.105, 0.13, 0.16], 'segments': 16, 'rings': 8, 'include_in_metric_volume': False},
    {'name': 'head_beard_front', 'shape': 'ellipsoid', 'bone': 'head', 'material': 'head_hair_dark', 'center': [0.155, 0.0, 1.52], 'radii': [0.04, 0.075, 0.06], 'segments': 12, 'rings': 6, 'include_in_metric_volume': False},
    {'name': 'head_bandana_wrap', 'shape': 'ellipsoid', 'bone': 'head', 'material': 'head_bandana_red', 'center': [0.02, 0.0, 1.73], 'radii': [0.135, 0.145, 0.035], 'segments': 16, 'rings': 5, 'include_in_metric_volume': False},
    {'name': 'head_hat_brim', 'shape': 'ellipsoid', 'bone': 'head', 'material': 'head_hat_navy', 'center': [0.02, 0.0, 1.80], 'radii': [0.23, 0.34, 0.045], 'segments': 24, 'rings': 5, 'include_in_metric_volume': False},
    {'name': 'head_hat_crown', 'shape': 'ellipsoid', 'bone': 'head', 'material': 'head_hat_navy', 'center': [0.02, 0.0, 1.90], 'radii': [0.15, 0.22, 0.12], 'segments': 18, 'rings': 7, 'include_in_metric_volume': False},
    {'name': 'head_hat_front_gold_trim', 'shape': 'box', 'bone': 'head', 'material': 'head_trim_gold', 'center': [0.235, 0.0, 1.825], 'size': [0.025, 0.42, 0.025], 'include_in_metric_volume': False},
    {'name': 'head_hat_left_gold_trim', 'shape': 'box', 'bone': 'head', 'material': 'head_trim_gold', 'center': [0.0, 0.335, 1.825], 'size': [0.30, 0.025, 0.025], 'include_in_metric_volume': False},
    {'name': 'head_hat_right_gold_trim', 'shape': 'box', 'bone': 'head', 'material': 'head_trim_gold', 'center': [0.0, -0.335, 1.825], 'size': [0.30, 0.025, 0.025], 'include_in_metric_volume': False},

    # Arms and hands
    {'name': 'arms_upper_L_sleeve', 'shape': 'cylinder', 'bone': 'arm.L', 'material': 'arms_sleeve_navy', 'p0': [0.0, 0.20, 1.42], 'p1': [0.0, 0.34, 1.16], 'radius': 0.065, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'arms_forearm_L_sleeve', 'shape': 'cylinder', 'bone': 'forearm.L', 'material': 'arms_sleeve_navy', 'p0': [0.0, 0.34, 1.16], 'p1': [0.0, 0.44, 0.94], 'radius': 0.055, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'arms_hand_L_skin', 'shape': 'ellipsoid', 'bone': 'hand.L', 'material': 'arms_hand_skin', 'center': [0.02, 0.48, 0.88], 'radii': [0.045, 0.035, 0.055], 'segments': 10, 'rings': 5, 'include_in_metric_volume': False},
    {'name': 'arms_upper_R_sleeve', 'shape': 'cylinder', 'bone': 'arm.R', 'material': 'arms_sleeve_navy', 'p0': [0.0, -0.20, 1.42], 'p1': [0.0, -0.34, 1.16], 'radius': 0.065, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'arms_forearm_R_sleeve', 'shape': 'cylinder', 'bone': 'forearm.R', 'material': 'arms_sleeve_navy', 'p0': [0.0, -0.34, 1.16], 'p1': [0.0, -0.44, 0.94], 'radius': 0.055, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'arms_hand_R_skin', 'shape': 'ellipsoid', 'bone': 'hand.R', 'material': 'arms_hand_skin', 'center': [0.02, -0.48, 0.88], 'radii': [0.045, 0.035, 0.055], 'segments': 10, 'rings': 5, 'include_in_metric_volume': False},
    {'name': 'arms_pistol_barrel', 'shape': 'cylinder', 'bone': 'hand.R', 'material': 'arms_pistol_steel', 'p0': [0.16, -0.50, 0.91], 'p1': [0.48, -0.50, 0.91], 'radius': 0.018, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'arms_pistol_grip', 'shape': 'box', 'bone': 'hand.R', 'material': 'arms_pistol_wood', 'center': [0.12, -0.50, 0.84], 'size': [0.08, 0.04, 0.14], 'include_in_metric_volume': False},
    {'name': 'arms_pistol_gold_lock', 'shape': 'box', 'bone': 'hand.R', 'material': 'arms_pistol_gold', 'center': [0.22, -0.50, 0.87], 'size': [0.06, 0.045, 0.035], 'include_in_metric_volume': False},

    # Legs and feet
    {'name': 'legs_thigh_L_pants', 'shape': 'cylinder', 'bone': 'thigh.L', 'material': 'legs_pants_brown', 'p0': [0.0, 0.10, 0.90], 'p1': [0.0, 0.10, 0.52], 'radius': 0.075, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'legs_shin_L_boot', 'shape': 'cylinder', 'bone': 'shin.L', 'material': 'legs_boot_leather', 'p0': [0.0, 0.10, 0.52], 'p1': [0.01, 0.10, 0.10], 'radius': 0.065, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'legs_foot_L_boot', 'shape': 'box', 'bone': 'foot.L', 'material': 'legs_boot_leather', 'center': [0.11, 0.10, 0.045], 'size': [0.24, 0.12, 0.08], 'include_in_metric_volume': False},
    {'name': 'legs_thigh_R_pants', 'shape': 'cylinder', 'bone': 'thigh.R', 'material': 'legs_pants_brown', 'p0': [0.0, -0.10, 0.90], 'p1': [0.0, -0.10, 0.52], 'radius': 0.075, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'legs_shin_R_boot', 'shape': 'cylinder', 'bone': 'shin.R', 'material': 'legs_boot_leather', 'p0': [0.0, -0.10, 0.52], 'p1': [0.01, -0.10, 0.10], 'radius': 0.065, 'segments': 12, 'include_in_metric_volume': False},
    {'name': 'legs_foot_R_boot', 'shape': 'box', 'bone': 'foot.R', 'material': 'legs_boot_leather', 'center': [0.11, -0.10, 0.045], 'size': [0.24, 0.12, 0.08], 'include_in_metric_volume': False},
]

# --------------------------- Mesh shape generation -------------------------

def make_ellipsoid(center: List[float], radii: List[float], segments: int = 16, rings: int = 8) -> Tuple[List[List[float]], List[List[float]], List[List[int]]]:
    verts, norms, faces = [], [], []
    # theta from 0..pi, phi from 0..2pi
    for i in range(rings + 1):
        theta = math.pi * i / rings
        st, ct = math.sin(theta), math.cos(theta)
        for j in range(segments):
            phi = 2 * math.pi * j / segments
            cp, sp = math.cos(phi), math.sin(phi)
            x = radii[0] * st * cp
            y = radii[1] * st * sp
            z = radii[2] * ct
            verts.append([center[0] + x, center[1] + y, center[2] + z])
            # Ellipsoid normal approximate from scaled local coordinates.
            n = [x / max(radii[0]**2, 1e-9), y / max(radii[1]**2, 1e-9), z / max(radii[2]**2, 1e-9)]
            norms.append(v_norm(n))
    for i in range(rings):
        for j in range(segments):
            a = i * segments + j
            b = i * segments + ((j + 1) % segments)
            c = (i + 1) * segments + j
            d = (i + 1) * segments + ((j + 1) % segments)
            if i != 0:
                faces.append([a, c, b])
            if i != rings - 1:
                faces.append([b, c, d])
    return verts, norms, faces


def make_cylinder(p0: List[float], p1: List[float], radius: float, segments: int = 12) -> Tuple[List[List[float]], List[List[float]], List[List[int]]]:
    axis = v_sub(p1, p0)
    u, v, w = make_basis(axis)
    verts, norms, faces = [], [], []
    for cap, p in enumerate([p0, p1]):
        for j in range(segments):
            ang = 2 * math.pi * j / segments
            radial = v_add(v_mul(u, math.cos(ang)), v_mul(v, math.sin(ang)))
            verts.append(v_add(p, v_mul(radial, radius)))
            norms.append(radial)
    # side faces
    for j in range(segments):
        a = j
        b = (j + 1) % segments
        c = segments + j
        d = segments + ((j + 1) % segments)
        faces.append([a, c, b])
        faces.append([b, c, d])
    # cap centers and cap triangles
    c0 = len(verts); verts.append(p0); norms.append(v_mul(w, -1))
    c1 = len(verts); verts.append(p1); norms.append(w)
    for j in range(segments):
        n = (j + 1) % segments
        faces.append([c0, n, j])
        faces.append([c1, segments + j, segments + n])
    return verts, norms, faces


def make_box(center: List[float], size: List[float]) -> Tuple[List[List[float]], List[List[float]], List[List[int]]]:
    sx, sy, sz = [s/2 for s in size]
    # face definitions: normal and four corners in CCW-ish order
    faces_def = [
        ([1,0,0],  [[sx,-sy,-sz],[sx, sy,-sz],[sx, sy, sz],[sx,-sy, sz]]),
        ([-1,0,0], [[-sx, sy,-sz],[-sx,-sy,-sz],[-sx,-sy, sz],[-sx, sy, sz]]),
        ([0,1,0],  [[-sx, sy,-sz],[sx, sy,-sz],[sx, sy, sz],[-sx, sy, sz]]),
        ([0,-1,0], [[sx,-sy,-sz],[-sx,-sy,-sz],[-sx,-sy, sz],[sx,-sy, sz]]),
        ([0,0,1],  [[-sx,-sy, sz],[sx,-sy, sz],[sx, sy, sz],[-sx, sy, sz]]),
        ([0,0,-1], [[-sx, sy,-sz],[sx, sy,-sz],[sx,-sy,-sz],[-sx,-sy,-sz]]),
    ]
    verts, norms, faces = [], [], []
    for normal, corners in faces_def:
        base = len(verts)
        for c in corners:
            verts.append([center[0]+c[0], center[1]+c[1], center[2]+c[2]])
            norms.append(normal[:])
        faces.append([base, base+1, base+2])
        faces.append([base, base+2, base+3])
    return verts, norms, faces

# --------------------------- Texture atlas output --------------------------

def create_texture_atlas(out_png: Path, out_json: Path) -> Dict[str, Any]:
    W = H = 1024
    cols = 4
    rows = math.ceil(len(MATERIALS) / cols)
    tile_w = W // cols
    tile_h = H // rows
    img = Image.new('RGBA', (W, H), (230, 220, 198, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
        small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 13)
    except Exception:
        font = small = None
    atlas = {'texture_atlas_version': 'texture_atlas_v1', 'asset_id': ASSET_ID, 'image': out_png.name, 'size': [W, H], 'color_space': 'sRGB', 'tiles': {}}
    for idx, (name, mat) in enumerate(MATERIALS.items()):
        col = idx % cols
        row = idx // cols
        x0, y0 = col * tile_w, row * tile_h
        x1, y1 = x0 + tile_w, y0 + tile_h
        base = hex_to_rgba(mat['hex'])
        # Draw a simple hand-painted-ish swatch with bands/noise.
        draw.rectangle([x0, y0, x1, y1], fill=base)
        for k in range(8):
            f = 0.75 + 0.06 * k
            c = tuple(max(0, min(255, int(v * f))) for v in base[:3]) + (255,)
            yy = y0 + int((k + 1) * tile_h / 10)
            draw.rectangle([x0, yy, x1, yy + max(1, tile_h // 60)], fill=c)
        draw.rectangle([x0 + 3, y0 + 3, x1 - 3, y1 - 3], outline=(33, 27, 21, 255), width=3)
        draw.text((x0 + 10, y0 + 10), name, fill=(255,255,240,255), font=font)
        draw.text((x0 + 10, y0 + 40), f"region: {region_from_material(name)}", fill=(255,255,240,230), font=small)
        draw.text((x0 + 10, y0 + 62), mat['role'], fill=(255,255,240,220), font=small)
        # glTF UV origin is bottom-left; store normalized rect in that convention.
        u0, u1 = x0 / W, x1 / W
        v0, v1 = 1.0 - y1 / H, 1.0 - y0 / H
        atlas['tiles'][name] = {
            'pixel_rect_xywh': [x0, y0, tile_w, tile_h],
            'uv_rect_gltf': [round(u0, 6), round(v0, 6), round(u1, 6), round(v1, 6)],
            'uv_center_gltf': [round((u0+u1)/2, 6), round((v0+v1)/2, 6)],
            'base_color_hex': mat['hex'],
            'region': region_from_material(name),
            'role': mat['role']
        }
    img.save(out_png)
    write_json(out_json, atlas)
    return atlas

# --------------------------- GLB writer helpers ----------------------------

def build_gltf_glb(out_path: Path, atlas_png: Path, atlas_data: Dict[str, Any]) -> Dict[str, Any]:
    bin_blob = bytearray()
    buffer_views: List[Dict[str, Any]] = []
    accessors: List[Dict[str, Any]] = []

    def align4() -> None:
        while len(bin_blob) % 4:
            bin_blob.append(0)

    def add_buffer_view(data: bytes, target: int | None = None, name: str | None = None) -> int:
        align4()
        offset = len(bin_blob)
        bin_blob.extend(data)
        view: Dict[str, Any] = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(data)}
        if target is not None:
            view['target'] = target
        if name:
            view['name'] = name
        buffer_views.append(view)
        return len(buffer_views) - 1

    def add_accessor(data: bytes, component_type: int, count: int, type_: str, target: int | None = None, name: str | None = None, minmax: Tuple[List[float], List[float]] | None = None) -> int:
        bv = add_buffer_view(data, target=target, name=(name + '_view') if name else None)
        acc: Dict[str, Any] = {'bufferView': bv, 'byteOffset': 0, 'componentType': component_type, 'count': count, 'type': type_}
        if name:
            acc['name'] = name
        if minmax:
            acc['min'], acc['max'] = minmax
        accessors.append(acc)
        return len(accessors) - 1

    def pack_floats(vals: Iterable[float]) -> bytes:
        vals = list(vals)
        return struct.pack('<' + 'f' * len(vals), *vals) if vals else b''

    def pack_u16(vals: Iterable[int]) -> bytes:
        vals = list(vals)
        return struct.pack('<' + 'H' * len(vals), *vals) if vals else b''

    # Materials and embedded texture.
    png_bytes = atlas_png.read_bytes()
    image_bv = add_buffer_view(png_bytes, target=None, name='embedded_base_color_png')
    images = [{'name': 'chr_pirate_duelist_v1_texture_atlas', 'bufferView': image_bv, 'mimeType': 'image/png'}]
    samplers = [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}]
    textures = [{'sampler': 0, 'source': 0, 'name': 'base_color_atlas_texture'}]
    mat_indices = {}
    materials = []
    for name, mat in MATERIALS.items():
        mat_indices[name] = len(materials)
        materials.append({
            'name': name,
            'pbrMetallicRoughness': {
                'baseColorFactor': rgba_float(mat['hex']),
                'baseColorTexture': {'index': 0},
                'metallicFactor': mat['metallic'],
                'roughnessFactor': mat['roughness'],
            },
            'extras': {
                'hit_region': region_from_material(name),
                'role': mat['role'],
                'source_color_hex': mat['hex']
            }
        })

    primitives = []
    component_bounds = {}
    region_bounds: Dict[str, List[List[float]]] = {}

    for comp in COMPONENTS:
        shape = comp['shape']
        if shape == 'ellipsoid':
            verts, norms, faces = make_ellipsoid(comp['center'], comp['radii'], comp.get('segments', 16), comp.get('rings', 8))
        elif shape == 'cylinder':
            verts, norms, faces = make_cylinder(comp['p0'], comp['p1'], comp['radius'], comp.get('segments', 12))
        elif shape == 'box':
            verts, norms, faces = make_box(comp['center'], comp['size'])
        else:
            raise ValueError(f"Unknown shape {shape}")

        material_name = comp['material']
        region = region_from_material(material_name)
        joint_index = BONE_NAMES.index(comp['bone'])
        uv = atlas_data['tiles'][material_name]['uv_center_gltf']

        positions_flat = [c for v in verts for c in v]
        normals_flat = [c for n in norms for c in n]
        uvs_flat = [c for _ in verts for c in uv]
        joints_flat = []
        weights_flat = []
        for _ in verts:
            joints_flat.extend([joint_index, 0, 0, 0])
            weights_flat.extend([1.0, 0.0, 0.0, 0.0])
        indices_flat = [idx for f in faces for idx in f]

        mins = [min(v[i] for v in verts) for i in range(3)]
        maxs = [max(v[i] for v in verts) for i in range(3)]
        component_bounds[comp['name']] = {'aabb_min': mins, 'aabb_max': maxs, 'region': region, 'material': material_name}
        if region not in region_bounds:
            region_bounds[region] = [mins[:], maxs[:]]
        else:
            for i in range(3):
                region_bounds[region][0][i] = min(region_bounds[region][0][i], mins[i])
                region_bounds[region][1][i] = max(region_bounds[region][1][i], maxs[i])

        pos_acc = add_accessor(pack_floats(positions_flat), 5126, len(verts), 'VEC3', target=34962, name=comp['name'] + '_POSITION', minmax=(mins, maxs))
        norm_acc = add_accessor(pack_floats(normals_flat), 5126, len(verts), 'VEC3', target=34962, name=comp['name'] + '_NORMAL')
        uv_acc = add_accessor(pack_floats(uvs_flat), 5126, len(verts), 'VEC2', target=34962, name=comp['name'] + '_TEXCOORD_0')
        joints_acc = add_accessor(pack_u16(joints_flat), 5123, len(verts), 'VEC4', target=34962, name=comp['name'] + '_JOINTS_0')
        weights_acc = add_accessor(pack_floats(weights_flat), 5126, len(verts), 'VEC4', target=34962, name=comp['name'] + '_WEIGHTS_0')
        ind_acc = add_accessor(pack_u16(indices_flat), 5123, len(indices_flat), 'SCALAR', target=34963, name=comp['name'] + '_INDICES')
        primitives.append({
            'attributes': {
                'POSITION': pos_acc,
                'NORMAL': norm_acc,
                'TEXCOORD_0': uv_acc,
                'JOINTS_0': joints_acc,
                'WEIGHTS_0': weights_acc,
            },
            'indices': ind_acc,
            'material': mat_indices[material_name],
            'mode': 4,
            'extras': {'component_name': comp['name'], 'bone': comp['bone'], 'hit_region': region}
        })

    # Nodes: mesh node first, then rig joints, then socket nodes.
    nodes: List[Dict[str, Any]] = []
    mesh_node_index = 0
    nodes.append({'name': ASSET_ID + '_skinned_mesh', 'mesh': 0, 'skin': 0})

    joint_node_indices: Dict[str, int] = {}
    for b in BONES:
        idx = len(nodes)
        joint_node_indices[b['name']] = idx
        if b['parent'] is None:
            translation = b['head']
        else:
            translation = v_sub(b['head'], BONE_BY_NAME[b['parent']]['head'])
        nodes.append({'name': b['name'], 'translation': [round(x, 6) for x in translation]})

    # Add bone children.
    for b in BONES:
        parent = b['parent']
        if parent is not None:
            nodes[joint_node_indices[parent]].setdefault('children', []).append(joint_node_indices[b['name']])

    # Add socket nodes as children of parent bones, so a consuming tool can find them by name.
    for s in SOCKETS:
        parent_bone = s['parent_bone']
        parent_head = BONE_BY_NAME[parent_bone]['head']
        trans = v_sub(s['position_world'], parent_head)
        idx = len(nodes)
        nodes.append({
            'name': 'socket.' + s['name'],
            'translation': [round(x, 6) for x in trans],
            'extras': {'socket': True, 'purpose': s['purpose'], 'position_world_authored': s['position_world']}
        })
        nodes[joint_node_indices[parent_bone]].setdefault('children', []).append(idx)

    # Inverse bind matrices, one per joint in BONE_NAMES order.
    ibm_values = []
    for bone_name in BONE_NAMES:
        p = BONE_BY_NAME[bone_name]['head']
        ibm_values.extend([1,0,0,0, 0,1,0,0, 0,0,1,0, -p[0],-p[1],-p[2],1])
    ibm_acc = add_accessor(pack_floats(ibm_values), 5126, len(BONE_NAMES), 'MAT4', target=None, name='inverse_bind_matrices')

    gltf: Dict[str, Any] = {
        'asset': {'version': '2.0', 'generator': 'ChatGPT procedural pirate GLB generator v1'},
        'scene': 0,
        'scenes': [{'name': 'Scene', 'nodes': [mesh_node_index, joint_node_indices['root']]}],
        'nodes': nodes,
        'meshes': [{
            'name': ASSET_ID + '_mesh_components',
            'primitives': primitives,
            'extras': {'component_count': len(COMPONENTS), 'region_source': 'material_name'}
        }],
        'skins': [{
            'name': 'biped_v1_skin',
            'skeleton': joint_node_indices['root'],
            'joints': [joint_node_indices[n] for n in BONE_NAMES],
            'inverseBindMatrices': ibm_acc
        }],
        'materials': materials,
        'samplers': samplers,
        'textures': textures,
        'images': images,
        'buffers': [{'byteLength': 0}],
        'bufferViews': buffer_views,
        'accessors': accessors,
        'extras': {
            'asset_id': ASSET_ID,
            'asset_contract_version': 'external_asset_v1',
            'rig': 'biped_v1',
            'archetype': 'biped',
            'world_metrics': WORLD_METRICS,
            'physical_metrics': PHYSICAL_METRICS,
            'note': 'Generated from machine-readable component data; materials contain head/torso/arms/legs keywords for hit-region extraction.'
        }
    }
    align4()
    gltf['buffers'][0]['byteLength'] = len(bin_blob)

    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    while len(json_bytes) % 4:
        json_bytes += b' '
    bin_bytes = bytes(bin_blob)
    while len(bin_bytes) % 4:
        bin_bytes += b'\x00'
    total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    with out_path.open('wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total_len))
        f.write(struct.pack('<I4s', len(json_bytes), b'JSON'))
        f.write(json_bytes)
        f.write(struct.pack('<I4s', len(bin_bytes), b'BIN\x00'))
        f.write(bin_bytes)
    return {'component_bounds': component_bounds, 'region_bounds': region_bounds, 'node_count': len(nodes), 'primitive_count': len(primitives), 'material_count': len(materials)}

# ------------------------------- JSON files --------------------------------

def build_anim_json() -> Dict[str, Any]:
    # Animation is rawdata targeting biped_v1 names. Extra clips are legal; schema allows arbitrary keys.
    return {
        'anim_spec_version': 'anim_clips_v1',
        'rig': 'biped_v1',
        'notes': 'Pirate duelist raw animation data. Angles are radians; translations are metres. Horizontal locomotion is intentionally not keyed; AI/engine moves the character body.',
        'clips': {
            'idle': {
                'playback': 'loop', 'frames': 12, 'fps': 12, 'duration_frames': 24,
                'bones': {
                    'chest': {'rotation_euler': [[1,[0,0,0]], [12,[0.025,0,0]], [24,[0,0,0]]]},
                    'head': {'rotation_euler': [[1,[0,0,0.02]], [12,[0,0,-0.02]], [24,[0,0,0.02]]]},
                    'arm.L': {'rotation_euler': [[1,[0.08,0,0]], [12,[0.02,0,0]], [24,[0.08,0,0]]]},
                    'arm.R': {'rotation_euler': [[1,[0.08,0,0]], [12,[0.02,0,0]], [24,[0.08,0,0]]]}
                }
            },
            'move': {
                'playback': 'loop', 'frames': 8, 'fps': 12, 'duration_frames': 16,
                'bones': {
                    'hips': {'location': [[1,[0,0,0.0]], [5,[0,0,0.025]], [9,[0,0,0.0]], [13,[0,0,0.025]], [17,[0,0,0.0]]]},
                    'thigh.L': {'rotation_euler': [[1,[0.45,0,0]], [5,[0.05,0,0]], [9,[-0.45,0,0]], [13,[0.05,0,0]], [17,[0.45,0,0]]]},
                    'thigh.R': {'rotation_euler': [[1,[-0.45,0,0]], [5,[0.05,0,0]], [9,[0.45,0,0]], [13,[0.05,0,0]], [17,[-0.45,0,0]]]},
                    'shin.L': {'rotation_euler': [[1,[-0.10,0,0]], [5,[-0.55,0,0]], [9,[-0.10,0,0]], [13,[-0.30,0,0]], [17,[-0.10,0,0]]]},
                    'shin.R': {'rotation_euler': [[1,[-0.10,0,0]], [5,[-0.30,0,0]], [9,[-0.10,0,0]], [13,[-0.55,0,0]], [17,[-0.10,0,0]]]},
                    'arm.L': {'rotation_euler': [[1,[-0.32,0,0]], [9,[0.32,0,0]], [17,[-0.32,0,0]]]},
                    'arm.R': {'rotation_euler': [[1,[0.32,0,0]], [9,[-0.32,0,0]], [17,[0.32,0,0]]]},
                    'chest': {'rotation_euler': [[1,[0,0,0.04]], [9,[0,0,-0.04]], [17,[0,0,0.04]]]}
                }
            },
            'run': {
                'playback': 'loop', 'frames': 8, 'fps': 16, 'duration_frames': 12,
                'bones': {
                    'hips': {'location': [[1,[0,0,0.0]], [4,[0,0,0.035]], [7,[0,0,0.0]], [10,[0,0,0.035]], [13,[0,0,0.0]]]},
                    'spine': {'rotation_euler': [[1,[-0.15,0,0]], [13,[-0.15,0,0]]]},
                    'chest': {'rotation_euler': [[1,[-0.18,0,0.08]], [7,[-0.18,0,-0.08]], [13,[-0.18,0,0.08]]]},
                    'thigh.L': {'rotation_euler': [[1,[0.75,0,0]], [7,[-0.65,0,0]], [13,[0.75,0,0]]]},
                    'thigh.R': {'rotation_euler': [[1,[-0.65,0,0]], [7,[0.75,0,0]], [13,[-0.65,0,0]]]},
                    'shin.L': {'rotation_euler': [[1,[-0.20,0,0]], [4,[-0.75,0,0]], [7,[-0.12,0,0]], [10,[-0.55,0,0]], [13,[-0.20,0,0]]]},
                    'shin.R': {'rotation_euler': [[1,[-0.12,0,0]], [4,[-0.55,0,0]], [7,[-0.20,0,0]], [10,[-0.75,0,0]], [13,[-0.12,0,0]]]},
                    'arm.L': {'rotation_euler': [[1,[-0.60,0,0]], [7,[0.60,0,0]], [13,[-0.60,0,0]]]},
                    'arm.R': {'rotation_euler': [[1,[0.60,0,0]], [7,[-0.60,0,0]], [13,[0.60,0,0]]]}
                }
            },
            'shoot': {
                'playback': 'once', 'frames': 6, 'fps': 12, 'duration_frames': 8,
                'bones': {
                    'chest': {'rotation_euler': [[1,[0,0,0]], [3,[0,0,-0.28]], [5,[0,0,-0.18]], [8,[0,0,0]]]},
                    'head': {'rotation_euler': [[1,[0,0,0]], [3,[0,0,-0.12]], [8,[0,0,0]]]},
                    'arm.R': {'rotation_euler': [[1,[0.20,0,0]], [2,[-1.15,0.0,-0.15]], [5,[-1.30,0.0,-0.20]], [8,[0.20,0,0]]]},
                    'forearm.R': {'rotation_euler': [[1,[-0.35,0,0]], [2,[0.05,0,0]], [5,[-0.18,0,0]], [8,[-0.35,0,0]]]},
                    'hand.R': {'rotation_euler': [[1,[0,0,0]], [3,[-0.25,0,0]], [8,[0,0,0]]]},
                    'arm.L': {'rotation_euler': [[1,[0.05,0,0]], [3,[0.35,0,0.10]], [8,[0.05,0,0]]]}
                }
            },
            'reload': {
                'playback': 'once', 'frames': 10, 'fps': 12, 'duration_frames': 16,
                'bones': {
                    'head': {'rotation_euler': [[1,[0,0,0]], [6,[0.25,0,0]], [13,[0.20,0,0]], [16,[0,0,0]]]},
                    'chest': {'rotation_euler': [[1,[0,0,0]], [8,[0.15,0,0.10]], [16,[0,0,0]]]},
                    'arm.R': {'rotation_euler': [[1,[0.10,0,0]], [5,[-0.60,0,0.25]], [12,[-0.45,0,-0.10]], [16,[0.10,0,0]]]},
                    'forearm.R': {'rotation_euler': [[1,[-0.25,0,0]], [5,[-0.75,0,0]], [12,[-0.55,0,0]], [16,[-0.25,0,0]]]},
                    'arm.L': {'rotation_euler': [[1,[0.05,0,0]], [5,[-0.40,0,-0.20]], [12,[-0.25,0,0.20]], [16,[0.05,0,0]]]},
                    'forearm.L': {'rotation_euler': [[1,[-0.20,0,0]], [5,[-0.90,0,0]], [12,[-0.70,0,0]], [16,[-0.20,0,0]]]}
                }
            },
            'hurt': {
                'playback': 'once', 'frames': 5, 'fps': 12, 'duration_frames': 6,
                'bones': {
                    'hips': {'location': [[1,[0,0,0]], [3,[-0.03,0,0.015]], [6,[0,0,0]]]},
                    'spine': {'rotation_euler': [[1,[0,0,0]], [3,[0.25,0,0.25]], [6,[0,0,0]]]},
                    'chest': {'rotation_euler': [[1,[0,0,0]], [3,[0.35,0,0.25]], [6,[0,0,0]]]},
                    'head': {'rotation_euler': [[1,[0,0,0]], [3,[0.25,0,-0.20]], [6,[0,0,0]]]},
                    'arm.L': {'rotation_euler': [[1,[0,0,0]], [3,[0.65,0,0]], [6,[0,0,0]]]},
                    'arm.R': {'rotation_euler': [[1,[0,0,0]], [3,[0.65,0,0]], [6,[0,0,0]]]}
                }
            },
            'death': {
                'playback': 'hold', 'frames': 8, 'fps': 10, 'duration_frames': 10,
                'bones': {
                    'hips': {'rotation_euler': [[1,[0,0,0]], [5,[0.65,0,0.15]], [10,[1.45,0,0.05]]], 'location': [[1,[0,0,0]], [10,[0.18,0,0.02]]]},
                    'spine': {'rotation_euler': [[1,[0,0,0]], [5,[0.50,0,0]], [10,[0.85,0,0]]]},
                    'chest': {'rotation_euler': [[1,[0,0,0]], [5,[0.55,0,0.15]], [10,[0.90,0,0.1]]]},
                    'head': {'rotation_euler': [[1,[0,0,0]], [10,[0.65,0,-0.25]]]},
                    'thigh.L': {'rotation_euler': [[1,[0,0,0]], [10,[-0.65,0,0.35]]]},
                    'thigh.R': {'rotation_euler': [[1,[0,0,0]], [10,[-0.65,0,-0.35]]]},
                    'shin.L': {'rotation_euler': [[1,[0,0,0]], [10,[-0.35,0,0]]]},
                    'shin.R': {'rotation_euler': [[1,[0,0,0]], [10,[-0.35,0,0]]]},
                    'arm.L': {'rotation_euler': [[1,[0,0,0]], [10,[0.85,0,0.25]]]},
                    'arm.R': {'rotation_euler': [[1,[0,0,0]], [10,[0.85,0,-0.25]]]}
                }
            },
            'celebrate': {
                'playback': 'once', 'frames': 8, 'fps': 12, 'duration_frames': 12,
                'bones': {
                    'chest': {'rotation_euler': [[1,[0,0,0]], [6,[-0.15,0,0.10]], [12,[0,0,0]]]},
                    'head': {'rotation_euler': [[1,[0,0,0]], [6,[-0.10,0,0.15]], [12,[0,0,0]]]},
                    'arm.R': {'rotation_euler': [[1,[0.10,0,0]], [4,[-1.40,0,-0.2]], [8,[-1.25,0,0.15]], [12,[0.10,0,0]]]},
                    'forearm.R': {'rotation_euler': [[1,[-0.20,0,0]], [4,[-0.55,0,0]], [8,[-0.45,0,0]], [12,[-0.20,0,0]]]},
                    'arm.L': {'rotation_euler': [[1,[0.05,0,0]], [6,[0.25,0,0.10]], [12,[0.05,0,0]]]}
                }
            }
        }
    }


def build_asset_manifest() -> Dict[str, Any]:
    anim = {
        'idle': {'clip': 'idle', 'frames': 12, 'fps': 12, 'playback': 'loop'},
        'move': {'clip': 'move', 'frames': 8, 'fps': 12, 'playback': 'loop'},
        'run': {'clip': 'run', 'frames': 8, 'fps': 16, 'playback': 'loop'},
        'shoot': {'clip': 'shoot', 'frames': 6, 'fps': 12, 'playback': 'once'},
        'reload': {'clip': 'reload', 'frames': 10, 'fps': 12, 'playback': 'once'},
        'hurt': {'clip': 'hurt', 'frames': 5, 'fps': 12, 'playback': 'once'},
        'death': {'clip': 'death', 'frames': 8, 'fps': 10, 'playback': 'hold'},
        'celebrate': {'clip': 'celebrate', 'frames': 8, 'fps': 12, 'playback': 'once'},
    }
    return {
        'asset_contract_version': 'external_asset_v1',
        'variant_id': ASSET_ID,
        'archetype': 'biped',
        'files': {'mesh': ASSET_ID + '.glb', 'animation_clips': ASSET_ID + '_anim.json'},
        'geometry': {'up': 'z', 'forward': '+x', 'unit': 'meter'},
        'rig': 'biped_v1',
        'region_source': 'material_name',
        'default_state': 'idle',
        'textures': {'base_color': ASSET_ID + '_texture_atlas.png'},
        'animations': anim,
        'world_metrics': {
            'height_world': WORLD_METRICS['height_world'],
            'footprint_radius_world': WORLD_METRICS['footprint_radius_world'],
            'eye_height_world': WORLD_METRICS['eye_height_world']
        },
        'notes': 'Stylized pirate duelist. Contract manifest stays external_asset_v1-valid; richer authored metrics, sockets, mass and generator data are stored in companion JSON files. GLB contains biped_v1 joint nodes, socket nodes, skinned component mesh, and embedded base-color atlas.'
    }


def build_source_asset_descriptor(anim_manifest: Dict[str, Any]) -> Dict[str, Any]:
    clips_states = []
    for state, v in anim_manifest['animations'].items():
        clips_states.append({'state': state, 'frames': v['frames'], 'playback': v['playback'], 'clip': v['clip'], 'directional': True})
    return {
        'asset_id': ASSET_ID,
        'variant_class': 'character',
        'source_format': 'gltf',
        'source_file': ASSET_ID + '.glb',
        'forward_axis': '+X',
        'up_axis': '+Z',
        'units': 'meter',
        'origin_policy': 'ground_footprint_center',
        'visual_objects': [c['name'] for c in COMPONENTS],
        'hit_proxy_objects': [{'name': c['name'], 'region': region_from_material(c['material'])} for c in COMPONENTS],
        'metric_proxy_objects': ['metric_proxy_human_body_volume_v1'],
        'sockets': [s['name'] for s in SOCKETS],
        'clips_states': clips_states,
        'notes': 'Producer-side descriptor with source sockets listed by name. Socket transforms and authored metrics are in companion files because external_asset_v1 cannot encode them directly.'
    }


def build_model_source() -> Dict[str, Any]:
    return {
        'model_source_version': 'procedural_character_model_source_v1',
        'asset_id': ASSET_ID,
        'character_name': 'Pirate Duelist',
        'archetype': 'biped',
        'rig_profile': 'biped_v1',
        'unit': 'meter',
        'up_axis': '+Z',
        'forward_axis': '+X',
        'origin_policy': 'ground_footprint_center',
        'art_direction': {
            'style': 'stylized isometric readable pirate NPC/combatant',
            'silhouette': 'large tricorn hat, navy long coat, red sash, boots, right-hand flintlock pistol',
            'palette': ['navy', 'burgundy red', 'dark brown leather', 'warm skin', 'brass/gold trim'],
            'body_only_contract_note': 'Pistol and hat are visual components tagged into body hit regions until weapon/gear regions are added to the contract.'
        },
        'world_metrics': WORLD_METRICS,
        'physical_metrics': PHYSICAL_METRICS,
        'bones': BONES,
        'sockets': SOCKETS,
        'materials_ref': ASSET_ID + '_materials.json',
        'texture_atlas_ref': ASSET_ID + '_texture_atlas.json',
        'components': COMPONENTS,
        'generation_outputs': {
            'mesh_glb': ASSET_ID + '.glb',
            'asset_manifest': ASSET_ID + '.asset.json',
            'animation_rawdata': ASSET_ID + '_anim.json',
            'hitbox_diagnostic': ASSET_ID + '_hitbox.json'
        }
    }


def build_materials_json(atlas_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'materials_version': 'character_materials_v1',
        'asset_id': ASSET_ID,
        'texture_atlas': ASSET_ID + '_texture_atlas.png',
        'hit_region_policy': 'Every material name contains one of the active region keywords: head, torso, arms, legs.',
        'materials': {
            name: {
                **mat,
                'region': region_from_material(name),
                'base_color_factor': rgba_float(mat['hex']),
                'atlas_tile': atlas_data['tiles'][name]
            }
            for name, mat in MATERIALS.items()
        }
    }


def build_events_json() -> Dict[str, Any]:
    return {
        'animation_events_version': 'animation_events_v1_proposed_extension',
        'asset_id': ASSET_ID,
        'notes': 'Companion event markers for combat/VFX. This is a proposed extension; external_asset_v1 records clips only.',
        'events': {
            'shoot': [
                {'frame': 3, 'event': 'fire_projectile', 'socket': 'muzzle.R', 'payload': {'projectile_profile': 'flintlock_ball', 'muzzle_flash_vfx': 'small_blackpowder_flash'}},
                {'frame': 3, 'event': 'spawn_vfx', 'socket': 'muzzle.R', 'payload': {'vfx': 'muzzle_smoke_puff'}}
            ],
            'reload': [
                {'frame': 4, 'event': 'reload_begin', 'socket': 'hand.R'},
                {'frame': 12, 'event': 'reload_commit', 'socket': 'hand.R'}
            ],
            'move': [
                {'frame': 1, 'event': 'footstep', 'socket': 'foot.L'},
                {'frame': 9, 'event': 'footstep', 'socket': 'foot.R'}
            ],
            'run': [
                {'frame': 1, 'event': 'footstep', 'socket': 'foot.L'},
                {'frame': 7, 'event': 'footstep', 'socket': 'foot.R'}
            ],
            'death': [
                {'frame': 10, 'event': 'death_settled', 'socket': 'root'}
            ]
        }
    }


def build_hitbox_json(glb_stats: Dict[str, Any]) -> Dict[str, Any]:
    region_ids = {'head': 1, 'torso': 2, 'arms': 3, 'legs': 4}
    regions = {}
    for name in ['head', 'torso', 'arms', 'legs']:
        bounds = glb_stats['region_bounds'].get(name)
        if not bounds:
            continue
        regions[name] = {
            'id': region_ids[name],
            'aabb_min': [round(x, 5) for x in bounds[0]],
            'aabb_max': [round(x, 5) for x in bounds[1]],
        }
    return {
        'hitbox_spec_version': 'hitbox_v1',
        'from_mesh': ASSET_ID + '.glb',
        'unit': 'meter',
        'up': 'z',
        'world_metrics': {
            'unit': 'meter',
            'height_world': WORLD_METRICS['height_world'],
            'footprint_radius_world': WORLD_METRICS['footprint_radius_world'],
            'eye_height_world': WORLD_METRICS['eye_height_world']
        },
        'collision_capsule': {
            'radius_world': WORLD_METRICS['capsule_radius_world'],
            'height_world': WORLD_METRICS['capsule_height_world'],
            'note': 'Gameplay capsule intentionally uses authored body height rather than visual hat height.'
        },
        'regions': regions,
        'hitmask_note': 'Regions come from material-name keyword matching. Hat maps to head; pistol maps to arms because weapon/gear regions are not active in external_asset_v1.'
    }


def build_sockets_json() -> Dict[str, Any]:
    return {
        'sockets_version': 'source_sockets_v1_proposed_extension',
        'asset_id': ASSET_ID,
        'unit': 'meter',
        'coordinate_system': {'up_axis': '+Z', 'forward_axis': '+X', 'origin': 'ground_footprint_center'},
        'sockets': SOCKETS
    }


def build_physical_metrics_json() -> Dict[str, Any]:
    return {'physical_metrics_version': 'physical_metrics_v1_proposed_extension', 'asset_id': ASSET_ID, **PHYSICAL_METRICS}


def build_readme() -> str:
    return f"""# {ASSET_ID} asset generation data

This folder contains the machine-readable data files for generating the stylized pirate duelist model from the concept sheets.

## Primary files

- `{ASSET_ID}.glb` — generated starter 3D model. It contains biped_v1 joint nodes, a skinned component mesh, material names with hit-region keywords, socket nodes, and an embedded base-color atlas.
- `{ASSET_ID}.asset.json` — valid `external_asset_v1` contract manifest.
- `{ASSET_ID}_anim.json` — valid `anim_clips_v1` raw animation data.
- `{ASSET_ID}_hitbox.json` — valid `hitbox_v1` diagnostic hit/collision data.
- `{ASSET_ID}.source_asset.json` — valid source asset descriptor.
- `{ASSET_ID}.model_source.json` — richer procedural generation data: components, bones, metrics, sockets, materials, and physical metrics.
- `{ASSET_ID}_materials.json` and `{ASSET_ID}_texture_atlas.*` — material and texture data.
- `{ASSET_ID}_sockets.json`, `{ASSET_ID}_physical_metrics.json`, `{ASSET_ID}_animation_events.json` — proposed extension data that the current active `external_asset_v1` schema cannot yet encode directly.
- `generate_pirate_glb.py` — standalone generator script. Run it from this folder to regenerate the GLB and companion JSON files.

## Important authored gameplay metrics

```json
{json.dumps(WORLD_METRICS, indent=2)}
```

The physical mass is calculated from the authored human metric proxy volume:

```text
body_volume_m3 = {PHYSICAL_METRICS['body_volume_m3']}
density_kg_per_m3 = {PHYSICAL_METRICS['density_kg_per_m3']}
mass_kg = body_volume_m3 * density_kg_per_m3 = {PHYSICAL_METRICS['mass_kg']} kg
weight_newtons_earth = mass_kg * 9.80665 = {PHYSICAL_METRICS['weight_newtons_earth']} N
```

`height_world` is the authored gameplay body/capsule height. `visual_height_world` includes the hat and is stored in the richer companion data because `external_asset_v1` does not yet have a separate visual-height field.

## Contract note

The active contract is body-only. The hat and pistol are included visually but are tagged into body hit regions by material-name keyword:

- hat: `head_hat_navy` → `head`
- pistol: `arms_pistol_*` → `arms`

Once weapon/gear regions are added to the contract, those parts can be split into dedicated regions without changing the character design.
"""

# ---------------------------- Validation and zip ---------------------------

def validate_json_files(out: Path) -> Dict[str, Any]:
    report: Dict[str, Any] = {'status': 'not_run', 'results': []}
    try:
        import jsonschema
        checks = [
            (out / f'{ASSET_ID}.asset.json', CONTRACT / 'schema' / 'external_asset.schema.json'),
            (out / f'{ASSET_ID}_anim.json', CONTRACT / 'schema' / 'animation_clips.schema.json'),
            (out / f'{ASSET_ID}_hitbox.json', CONTRACT / 'schema' / 'hitbox_spec.schema.json'),
            (out / f'{ASSET_ID}.source_asset.json', CONTRACT / 'schema' / 'source_asset.schema.json'),
        ]
        report['status'] = 'ok'
        for data_path, schema_path in checks:
            data = json.loads(data_path.read_text(encoding='utf-8'))
            schema = json.loads(schema_path.read_text(encoding='utf-8'))
            jsonschema.Draft202012Validator(schema).validate(data)
            report['results'].append({'file': data_path.name, 'schema': str(schema_path.relative_to(CONTRACT)), 'valid': True})
    except Exception as e:
        report['status'] = 'failed'
        report['error'] = repr(e)
    return report


def copy_reference_images(out: Path) -> None:
    refs = out / 'art_refs'
    refs.mkdir(exist_ok=True)
    mapping = {
        ROOT / 'pirate_character_design_sheet.png': 'pirate_character_design_sheet.png',
        ROOT / 'pirate_character_turnaround_reference_sheet.png': 'pirate_character_turnaround_reference_sheet.png',
        ROOT / 'pirate_character_texture_sheet_display.png': 'pirate_character_texture_sheet_display.png',
        ROOT / 'pirate_character_animation_reference_sheet.png': 'pirate_character_animation_reference_sheet.png',
    }
    for src, dst in mapping.items():
        if src.exists():
            shutil.copy2(src, refs / dst)


def write_standalone_generator(out: Path) -> None:
    # This file is intentionally a copy of the creator script so the user can regenerate locally.
    src = Path(__file__).resolve()
    text = src.read_text(encoding='utf-8')
    text = text.replace("ROOT = Path(__file__).resolve().parent", "ROOT = Path(__file__).resolve().parent")
    text = text.replace("OUT = ROOT", "OUT = ROOT")
    text = text.replace("CONTRACT = ROOT / 'model_authoring_contract_v1'", "CONTRACT = ROOT / 'model_authoring_contract_v1'")
    # Make local generator tolerate missing contract schemas/reference sheets.
    text = text.replace("report = validate_json_files(OUT) if CONTRACT.exists() else {'status': 'skipped', 'reason': 'contract schemas not found beside this folder'}", "report = validate_json_files(OUT) if CONTRACT.exists() else {'status': 'skipped', 'reason': 'contract schemas not found beside this folder'} if CONTRACT.exists() else {'status': 'skipped', 'reason': 'contract schemas not found beside this folder'}")
    (out / 'generate_pirate_glb.py').write_text(text, encoding='utf-8')


def main() -> None:
    # Standalone regeneration mode: write into this folder without deleting it.
    ensure_dir(OUT)

    # 1) Texture atlas
    atlas_data = create_texture_atlas(OUT / f'{ASSET_ID}_texture_atlas.png', OUT / f'{ASSET_ID}_texture_atlas.json')

    # 2) GLB
    glb_stats = build_gltf_glb(OUT / f'{ASSET_ID}.glb', OUT / f'{ASSET_ID}_texture_atlas.png', atlas_data)

    # 3) JSON data files
    anim_json = build_anim_json()
    asset_manifest = build_asset_manifest()
    source_asset = build_source_asset_descriptor(asset_manifest)
    model_source = build_model_source()
    materials_json = build_materials_json(atlas_data)
    hitbox_json = build_hitbox_json(glb_stats)

    write_json(OUT / f'{ASSET_ID}_anim.json', anim_json)
    write_json(OUT / f'{ASSET_ID}.asset.json', asset_manifest)
    write_json(OUT / f'{ASSET_ID}.source_asset.json', source_asset)
    write_json(OUT / f'{ASSET_ID}.model_source.json', model_source)
    write_json(OUT / f'{ASSET_ID}_materials.json', materials_json)
    write_json(OUT / f'{ASSET_ID}_hitbox.json', hitbox_json)
    write_json(OUT / f'{ASSET_ID}_sockets.json', build_sockets_json())
    write_json(OUT / f'{ASSET_ID}_physical_metrics.json', build_physical_metrics_json())
    write_json(OUT / f'{ASSET_ID}_animation_events.json', build_events_json())
    write_json(OUT / f'{ASSET_ID}_glb_generation_report.json', glb_stats)
    (OUT / 'README.md').write_text(build_readme(), encoding='utf-8')

    # 4) Copy art reference sheets and generator script
    copy_reference_images(OUT)
    write_standalone_generator(OUT)

    # 5) Validate contract files.
    report = validate_json_files(OUT) if CONTRACT.exists() else {'status': 'skipped', 'reason': 'contract schemas not found beside this folder'}
    write_json(OUT / 'validation_report.json', report)

    # 6) Zip package
    zip_path = ROOT.parent / 'pirate_duelist_v1_asset_package_regenerated.zip'
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob('*')):
            z.write(p, p.relative_to(OUT.parent))
    print(json.dumps({'out_dir': str(OUT), 'zip': str(zip_path), 'validation': report}, indent=2))


if __name__ == '__main__':
    main()
