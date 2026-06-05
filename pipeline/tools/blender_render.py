"""R7 production renderer (Blender, headless). NOT imported by the Python gate; it runs
inside Blender:  blender --background --python blender_render.py -- <out_dir> <tools_dir>

Renders the SAME body-only humanoid as render3d through the EXACT game_iso_v1 orthographic
camera (azimuth 45, elevation 30), 16 directions, two passes:
  - color  (Workbench studio-lit, per-part body colors)  -> color_dirNN.png
  - region (Workbench flat, distinct per-part colors)     -> region_dirNN.png  (-> R8 ids)
and writes blender_meta.json (the camera-probe + anchor) so the Python side can prove
render3d <-> Blender camera parity and pack an engine-loadable package.

The camera matrix is built directly from render3d's projection axes (rx=(x-y)/sqrt2,
ry=(x+y)/(2 sqrt2) - z cos30), so the Blender camera IS the game_iso_v1 camera by
construction, not by eyeballed Euler angles.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0]
TOOLS = argv[1]
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, TOOLS)
import meshes  # noqa: E402  (Blender's bundled numpy)

CANVAS, DIRS = 256, 16
COS30, SIN30, INV2 = math.cos(math.radians(30.0)), 0.5, 1.0 / math.sqrt(2.0)
# region id -> body color (the "art"); the region pass uses the same hue, flat-lit.
REGION_COLOR = {1: (0.86, 0.22, 0.22), 2: (0.22, 0.70, 0.36), 3: (0.27, 0.47, 0.95), 4: (0.93, 0.79, 0.20)}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.view_settings.view_transform = 'Standard'  # predictable sRGB (not AgX) for region->id mapping

# --- mesh: a real glTF/glb file (--mesh-file; HIT regions by material name), or the procedural humanoid ---
MESH_FILE = argv[2] if len(argv) > 2 and argv[2] else None
if MESH_FILE:
    from mesh_io import region_for_name  # noqa: E402
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=MESH_FILE)  # Blender converts glTF Y-up -> Z-up
    imported = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if not imported:
        raise SystemExit(f"no mesh imported from {MESH_FILE}")
    bpy.ops.object.select_all(action='DESELECT')
    for o in imported:
        o.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    if len(imported) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.rotation_mode = 'XYZ'  # glTF import sets QUATERNION; the render loop uses rotation_euler
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mesh = obj.data
    cos = [v.co for v in mesh.vertices]
    shift = Vector((  # foot (min z) -> 0, footprint centered on x=y=0 (the game_iso_v1 contract)
        (min(c.x for c in cos) + max(c.x for c in cos)) / 2.0,
        (min(c.y for c in cos) + max(c.y for c in cos)) / 2.0,
        min(c.z for c in cos),
    ))
    for v in mesh.vertices:
        v.co = v.co - shift
    if not mesh.materials:  # no materials -> a single torso slot
        mesh.materials.append(bpy.data.materials.new("torso"))
        for poly in mesh.polygons:
            poly.material_index = 0
    # Keep the ART materials for the color pass; record each material's HIT region (by NAME) for
    # the region pass; detect whether any material carries a base-color texture (-> real look).
    region_of = {mat.name: region_for_name(mat.name) for mat in mesh.materials if mat}
    has_tex = any(mat and mat.use_nodes and any(n.type == 'TEX_IMAGE' and n.image
                  for n in mat.node_tree.nodes) for mat in mesh.materials)
else:
    verts, faces, freg = meshes.humanoid()
    mesh = bpy.data.meshes.new("humanoid")
    mesh.from_pydata([[float(c) for c in v] for v in verts], [], [[int(c) for c in f] for f in faces])
    mesh.update()
    obj = bpy.data.objects.new("humanoid", mesh)
    scene.collection.objects.link(obj)
    slot = {}
    for rid, (r, g, b) in REGION_COLOR.items():
        m = bpy.data.materials.new(f"region{rid}")
        m.use_nodes = False
        m.diffuse_color = (r, g, b, 1.0)
        slot[rid] = len(mesh.materials)
        mesh.materials.append(m)
    for i, poly in enumerate(mesh.polygons):
        poly.material_index = slot[int(freg[i])]
    region_of = {f"region{rid}": rid for rid in REGION_COLOR}  # procedural: art color == region color
    has_tex = False

# --- EXACT game_iso_v1 camera: local X=screen-right, Y=screen-up, Z=toward-camera ---
right = Vector((1.0, -1.0, 0.0)).normalized()                       # d(x-y)
up = Vector((-0.5 * INV2, -0.5 * INV2, COS30)).normalized()         # -d(ry)
back = Vector((COS30 * INV2, COS30 * INV2, SIN30)).normalized()     # toward camera
rot = Matrix(((right.x, up.x, back.x),
              (right.y, up.y, back.y),
              (right.z, up.z, back.z))).to_4x4()
target = Vector((0.0, 0.0, 0.9))                                    # body centre, for framing
cam_data = bpy.data.cameras.new("isocam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 2.3
cam = bpy.data.objects.new("isocam", cam_data)
scene.collection.objects.link(cam)
cam.matrix_world = Matrix.Translation(target + back * 100.0) @ rot
scene.camera = cam

# --- render settings ---
r = scene.render
r.engine = 'BLENDER_WORKBENCH'
r.resolution_x = r.resolution_y = CANVAS
r.resolution_percentage = 100
r.film_transparent = True
r.image_settings.file_format = 'PNG'
r.image_settings.color_mode = 'RGBA'
shading = scene.display.shading
shading.color_type = 'MATERIAL'

from bpy_extras.object_utils import world_to_camera_view  # noqa: E402


def probe(p):
    co = world_to_camera_view(scene, cam, Vector(p))
    return [co.x, 1.0 - co.y]  # screen fraction, y-DOWN to match the pipeline


# camera-probe of fixed world points (direction-independent camera parity vs render3d)
camera_probe = {k: probe(v) for k, v in
                {"origin": (0, 0, 0), "px": (1, 0, 0), "py": (0, 1, 0), "pz": (0, 0, 1)}.items()}

# COLOR pass -- the ART's real look (base-color TEXTURE if present, else the material base
# colors), studio-lit. (Procedural/untextured -> MATERIAL shows its diffuse_color.)
shading.color_type = 'TEXTURE' if has_tex else 'MATERIAL'
shading.light = 'STUDIO'
scene.display.render_aa = '8'
for i in range(DIRS):
    obj.rotation_euler = (0.0, 0.0, i * (2 * math.pi / DIRS))
    r.filepath = os.path.join(OUT, f"color_dir{i:02d}.png")
    bpy.ops.render.render(write_still=True)

# Recolor every material to its flat HIT-region color for the REGION pass (-> R8 hit-mask).
for mat in mesh.materials:
    if mat is not None:
        mat.use_nodes = False
        mat.diffuse_color = (*REGION_COLOR[region_of.get(mat.name, 2)], 1.0)

# REGION pass -- flat region colors, no AA.
shading.color_type = 'MATERIAL'
shading.light = 'FLAT'
scene.display.render_aa = 'OFF'
for i in range(DIRS):
    obj.rotation_euler = (0.0, 0.0, i * (2 * math.pi / DIRS))
    r.filepath = os.path.join(OUT, f"region_dir{i:02d}.png")
    bpy.ops.render.render(write_still=True)

# Measured world metrics from the FINAL mesh (local coords; foot at z~0 after normalization).
_z = [v.co.z for v in mesh.vertices]
_zmin, _zmax = min(_z), max(_z)
_ground = [max(abs(v.co.x), abs(v.co.y)) for v in mesh.vertices if v.co.z <= _zmin + 0.15 * (_zmax - _zmin)]
meta = {
    "canvas": CANVAS, "dirs": DIRS, "ortho_scale": cam_data.ortho_scale,
    "region_color": {str(k): list(v) for k, v in REGION_COLOR.items()},
    "camera_probe": camera_probe,
    "anchor_frac": probe((0, 0, 0)),  # foot (world origin) is rotation-invariant about +Z
    "mesh_height": round(_zmax, 6),
    "mesh_footprint": round(max(_ground) if _ground else 0.0, 6),
    "blender_version": bpy.app.version_string,
}
with open(os.path.join(OUT, "blender_meta.json"), "w") as f:
    json.dump(meta, f, indent=2)
print("R7_BLENDER_DONE", OUT)
