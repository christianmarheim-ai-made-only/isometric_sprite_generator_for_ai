"""Model PREVIEWER (runs in Blender): render the SOURCE model at diagnostic, NON-iso angles per
stage so a fault can be localized (mesh vs texture vs region vs rig) BEFORE/while it becomes a
sprite. Reuses blender_render's import/normalize/material-region conventions; uses FREE angles --
this is a diagnostic view, NEVER the locked iso camera or its parity gate.

  blender --background --python blender_preview.py -- OUT TOOLS MESH [STATES_JSON]

Emits per (stage, angle) PNGs + preview_meta.json:
  mesh_<angle>     flat single-colour, studio-lit  -> silhouette / topology sanity
  tex_<angle>      TEXTURE (or MATERIAL) studio-lit -> texture / look sanity
  region_<angle>   flat region colours              -> HIT-region sanity (catches mis-named materials)
  bind_<angle>     rig bind pose                    -> rig sanity (rigged only)
  pose_<state>_<first|last>  per-clip end poses     -> animation sanity (rigged only)
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT, TOOLS, MESH = argv[0], argv[1], argv[2]
STATES_JSON = argv[3] if len(argv) > 3 and argv[3] else None
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, TOOLS)
from mesh_io import region_for_name, REGION_KEYWORDS  # noqa: E402
from constants import CANVAS, REGION_RGB, PREVIEW_BG_RGB  # noqa: E402

REGION_COLOR = {0: PREVIEW_BG_RGB, **REGION_RGB}
SINGLE = (0.62, 0.64, 0.68)
ANGLES = [("front", 0.0, 8.0), ("threeq", 40.0, 22.0), ("side", 90.0, 8.0)]  # (name, az_deg, elev_deg)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.view_settings.view_transform = 'Standard'

before = set(bpy.data.objects)
ext = os.path.splitext(MESH)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=MESH)
elif ext == ".obj":
    try:
        bpy.ops.wm.obj_import(filepath=MESH)
    except Exception:
        bpy.ops.import_scene.obj(filepath=MESH)
else:
    raise SystemExit("unsupported mesh format: " + ext)

imported = [o for o in bpy.data.objects if o not in before]
mesh_objs = [o for o in imported if o.type == 'MESH']
obj = mesh_objs[0]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.select_all(action='DESELECT')
for o in mesh_objs:
    o.select_set(True)
if len(mesh_objs) > 1:
    bpy.ops.object.join()
obj = bpy.context.view_layer.objects.active
for o in imported:
    if o.type == 'MESH':
        o.rotation_mode = 'XYZ'
arm = next((o for o in imported if o.type == 'ARMATURE'), None)
root_obj = arm if arm else obj

bpy.context.view_layer.update()
cos = [obj.matrix_world @ v.co for v in obj.data.vertices]
xs = [c.x for c in cos]; ys = [c.y for c in cos]; zs = [c.z for c in cos]
root_obj.location = root_obj.location - Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)))
bpy.context.view_layer.update()
base_mat = root_obj.matrix_world.copy()
cos = [obj.matrix_world @ v.co for v in obj.data.vertices]
xs = [c.x for c in cos]; ys = [c.y for c in cos]; zs = [c.z for c in cos]
height = max(zs) - min(zs)
center = Vector((0.0, 0.0, height / 2.0))
span = max(max(xs) - min(xs), max(ys) - min(ys), height)

mats = [m for m in obj.data.materials if m]
region_of = {m.name: region_for_name(m.name) for m in mats}
region_fallback = sorted(n for n in region_of if not any(kw in n.lower() for kw, _ in REGION_KEYWORDS))
has_tex = any(m.use_nodes and any(n.type == 'TEX_IMAGE' and n.image for n in m.node_tree.nodes) for m in mats)
for m in mats:
    if m.use_nodes:
        b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if b:
            c = b.inputs['Base Color'].default_value
            m.diffuse_color = (c[0], c[1], c[2], 1.0)

r = scene.render
r.engine = 'BLENDER_WORKBENCH'
r.resolution_x = r.resolution_y = CANVAS
r.resolution_percentage = 100
r.film_transparent = True
r.image_settings.file_format = 'PNG'
r.image_settings.color_mode = 'RGBA'
shading = scene.display.shading
cam_data = bpy.data.cameras.new("prev")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = span * 1.25 + 0.05
cam = bpy.data.objects.new("prev", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def set_cam(az_deg, elev_deg):
    az, el = math.radians(az_deg), math.radians(elev_deg)
    d = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    pos = center + d * 100.0
    look = (center - pos).normalized()
    right = look.cross(Vector((0, 0, 1)))
    if right.length < 1e-4:
        right = Vector((1, 0, 0))
    right.normalize()
    up = right.cross(look).normalized()
    rot = Matrix(((right.x, up.x, d.x), (right.y, up.y, d.y), (right.z, up.z, d.z))).to_4x4()
    cam.matrix_world = Matrix.Translation(pos) @ rot


def render_to(name):
    r.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)


def render_angles(prefix):
    for nm, az, el in ANGLES:
        set_cam(az, el)
        render_to(f"{prefix}_{nm}.png")


def set_single():
    shading.color_type = 'SINGLE'
    shading.light = 'STUDIO'
    scene.display.render_aa = '8'
    try:
        shading.single_color = SINGLE
    except Exception:
        pass


# --- static stages: mesh silhouette, texture/material, region overlay ---
set_single()
render_angles("mesh")
shading.color_type = 'TEXTURE' if has_tex else 'MATERIAL'
shading.light = 'STUDIO'
render_angles("tex")
for m in mats:
    m.use_nodes = False
    m.diffuse_color = (*REGION_COLOR[region_of.get(m.name, 2)], 1.0)
shading.color_type = 'MATERIAL'
shading.light = 'FLAT'
scene.display.render_aa = 'OFF'
render_angles("region")

# --- rig stages: bind pose (all angles) + each clip first/last (three-quarter) ---
clip_poses = []
if arm:
    if not arm.animation_data:
        arm.animation_data_create()
    actions = {a.name: a for a in bpy.data.actions}
    set_single()
    arm.animation_data.action = None
    for nm, az, el in ANGLES:
        root_obj.matrix_world = base_mat
        bpy.context.view_layer.update()
        set_cam(az, el)
        render_to(f"bind_{nm}.png")
    states = json.loads(open(STATES_JSON, encoding="utf-8").read()) if STATES_JSON else {a: {"clip": a} for a in actions}
    for state, spec in states.items():
        act = actions.get(spec.get("clip", state))
        if not act:
            continue
        f0, f1 = act.frame_range
        for tag, fv in (("first", f0), ("last", f1)):
            arm.animation_data.action = act
            scene.frame_set(int(round(fv)))
            root_obj.matrix_world = base_mat
            bpy.context.view_layer.update()
            set_cam(40.0, 22.0)
            render_to(f"pose_{state}_{tag}.png")
            clip_poses.append(f"{state}/{tag}")

meta = {
    "angles": [a[0] for a in ANGLES],
    "has_tex": bool(has_tex),
    "rigged": bool(arm),
    "material_region": region_of,
    "region_fallback_materials": region_fallback,
    "clip_poses": clip_poses,
    "blender_version": bpy.app.version_string,
}
json.dump(meta, open(os.path.join(OUT, "preview_meta.json"), "w"), indent=2)
print("PREVIEW_DONE", OUT, "has_tex", has_tex, "rigged", bool(arm), "fallback", region_fallback)
