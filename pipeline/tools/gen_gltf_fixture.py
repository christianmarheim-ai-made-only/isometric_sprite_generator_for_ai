"""Mint a glTF (.glb) test fixture for R8: the humanoid with per-part materials NAMED by HIT
region (head/torso/arms/legs), so the glTF import path's region-by-material-name is exercised
on a real file. Runs in Blender:  blender --background --python gen_gltf_fixture.py -- OUT.glb TOOLS
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
OUT, TOOLS = argv[0], argv[1]
os.makedirs(os.path.dirname(OUT), exist_ok=True)
sys.path.insert(0, TOOLS)
import meshes  # noqa: E402
from mesh_io import REGION_NAMES  # noqa: E402

bpy.ops.wm.read_factory_settings(use_empty=True)
verts, faces, freg = meshes.humanoid()
mesh = bpy.data.meshes.new("humanoid")
mesh.from_pydata([[float(c) for c in v] for v in verts], [], [[int(c) for c in f] for f in faces])
mesh.update()
obj = bpy.data.objects.new("humanoid", mesh)
bpy.context.scene.collection.objects.link(obj)

slot = {}
for rid, name in REGION_NAMES.items():           # materials named head/torso/arms/legs
    slot[rid] = len(mesh.materials)
    mesh.materials.append(bpy.data.materials.new(name))
for i, poly in enumerate(mesh.polygons):
    poly.material_index = slot[int(freg[i])]

bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=True)
print("WROTE_GLTF", OUT)
