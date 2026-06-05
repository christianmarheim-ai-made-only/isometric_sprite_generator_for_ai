"""R8: render a RIGGED + ANIMATED glb's clips through the game_iso_v1 camera (Blender). For each
declared (state, frame_index) it poses the armature (samples the clip) and renders 16 directions
(color + region passes). Emits anim_meta.json for the multi-state package assembler.

  blender --background --python blender_render_anim.py -- OUT TOOLS MESH.glb STATES_JSON
STATES_JSON file = {"idle": {"clip":"idle","frames":1}, "fly": {"clip":"fly","frames":4}}
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT, TOOLS, MESH_FILE, STATES_JSON = argv[0], argv[1], argv[2], argv[3]
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, TOOLS)
from mesh_io import region_for_name, REGION_KEYWORDS  # noqa: E402

states = json.loads(open(STATES_JSON, encoding="utf-8").read())
CANVAS, DIRS = 256, 16
COS30, SIN30, INV2 = math.cos(math.radians(30.0)), 0.5, 1.0 / math.sqrt(2.0)
REGION_COLOR = {1: (0.86, 0.22, 0.22), 2: (0.22, 0.70, 0.36), 3: (0.27, 0.47, 0.95), 4: (0.93, 0.79, 0.20)}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.view_settings.view_transform = 'Standard'

before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=MESH_FILE)
imported = [o for o in bpy.data.objects if o not in before]
obj = next(o for o in imported if o.type == 'MESH')
arm = next((o for o in imported if o.type == 'ARMATURE'), None)
root_obj = arm if arm else obj

bpy.context.view_layer.update()
cos = [obj.matrix_world @ v.co for v in obj.data.vertices]      # rest world coords
xs = [c.x for c in cos]; ys = [c.y for c in cos]; zs = [c.z for c in cos]
shift = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)))  # foot -> origin
root_obj.location = root_obj.location - shift
bpy.context.view_layer.update()
base_mat = root_obj.matrix_world.copy()
cos = [obj.matrix_world @ v.co for v in obj.data.vertices]
zs = [c.z for c in cos]
height = max(zs) - min(zs)
ground = [max(abs(c.x), abs(c.y)) for c in cos if c.z <= min(zs) + 0.15 * height]
footprint = max(ground) if ground else max(max(abs(c.x), abs(c.y)) for c in cos)

region_of = {m.name: region_for_name(m.name) for m in obj.data.materials if m}
# materials whose name matched NO region keyword silently default to torso=2 -> a likely mistake
region_fallback = sorted(n for n in region_of if not any(kw in n.lower() for kw, _ in REGION_KEYWORDS))
has_tex = any(m and m.use_nodes and any(n.type == 'TEX_IMAGE' and n.image
              for n in m.node_tree.nodes) for m in obj.data.materials)
for _m in obj.data.materials:  # show the real PBR base color in MATERIAL mode (Workbench reads diffuse_color)
    if _m and _m.use_nodes:
        _b = next((n for n in _m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if _b is not None:
            _c = _b.inputs['Base Color'].default_value
            _m.diffuse_color = (_c[0], _c[1], _c[2], 1.0)

right = Vector((1.0, -1.0, 0.0)).normalized()
up = Vector((-0.5 * INV2, -0.5 * INV2, COS30)).normalized()
back = Vector((COS30 * INV2, COS30 * INV2, SIN30)).normalized()
rot = Matrix(((right.x, up.x, back.x), (right.y, up.y, back.y), (right.z, up.z, back.z))).to_4x4()
target = Vector((0.0, 0.0, height / 2.0))
cam_data = bpy.data.cameras.new("isocam")
cam_data.type = 'ORTHO'
span = max(max(xs) - min(xs), max(ys) - min(ys), height)
cam_data.ortho_scale = span * 1.9 + 0.05
cam = bpy.data.objects.new("isocam", cam_data)
scene.collection.objects.link(cam)
cam.matrix_world = Matrix.Translation(target + back * 100.0) @ rot
scene.camera = cam

r = scene.render
r.engine = 'BLENDER_WORKBENCH'
r.resolution_x = r.resolution_y = CANVAS
r.resolution_percentage = 100
r.film_transparent = True
r.image_settings.file_format = 'PNG'
r.image_settings.color_mode = 'RGBA'
shading = scene.display.shading

from bpy_extras.object_utils import world_to_camera_view  # noqa: E402


def probe(p):
    co = world_to_camera_view(scene, cam, Vector(p))
    return [co.x, 1.0 - co.y]


camera_probe = {k: probe(v) for k, v in {"origin": (0, 0, 0), "px": (1, 0, 0), "py": (0, 1, 0), "pz": (0, 0, 1)}.items()}

actions = {a.name: a for a in bpy.data.actions}
poses = []  # (state, frame_index, action_name|None, frame_value|None)
missing_clips = []  # declared states whose clip is absent from the glb -> rendered as the REST pose
for state, spec in states.items():
    clip, nf = spec.get("clip", state), spec["frames"]
    act = actions.get(clip)
    if act:
        f0, f1 = act.frame_range
        for fi in range(nf):
            poses.append((state, fi, clip, f0 + (f1 - f0) * (fi / nf)))
    else:
        missing_clips.append(state)
        poses.append((state, 0, None, None))

if arm and not arm.animation_data:
    arm.animation_data_create()


def apply(name, fv, d):
    if arm and name:
        arm.animation_data.action = actions[name]
        scene.frame_set(int(round(fv)))
    root_obj.matrix_world = Matrix.Rotation(d * (2 * math.pi / DIRS), 4, 'Z') @ base_mat
    bpy.context.view_layer.update()


def render_all(prefix):
    for (state, fi, an, fv) in poses:
        for d in range(DIRS):
            apply(an, fv, d)
            r.filepath = os.path.join(OUT, f"{prefix}_{state}_f{fi}_dir{d:02d}.png")
            bpy.ops.render.render(write_still=True)


shading.color_type = 'TEXTURE' if has_tex else 'MATERIAL'
shading.light = 'STUDIO'
scene.display.render_aa = '8'
render_all("color")
for m in obj.data.materials:
    if m is not None:
        m.use_nodes = False
        m.diffuse_color = (*REGION_COLOR[region_of.get(m.name, 2)], 1.0)
shading.color_type = 'MATERIAL'
shading.light = 'FLAT'
scene.display.render_aa = 'OFF'
render_all("region")

meta = {
    "canvas": CANVAS, "dirs": DIRS, "region_color": {str(k): list(v) for k, v in REGION_COLOR.items()},
    "camera_probe": camera_probe, "anchor_frac": probe((0, 0, 0)),
    "mesh_height": round(height, 6), "mesh_footprint": round(footprint, 6),
    "poses": [[s, fi] for (s, fi, _, _) in poses],
    "region_fallback_materials": region_fallback,
    "missing_clips": missing_clips,
    "blender_version": bpy.app.version_string,
}
json.dump(meta, open(os.path.join(OUT, "anim_meta.json"), "w"), indent=2)
print("R8_ANIM_DONE", OUT, len(poses), "poses x", DIRS, "dirs")
