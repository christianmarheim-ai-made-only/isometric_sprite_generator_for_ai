"""Mint a TEXTURE-STARTER kit for the humanoid body so a texturer has something concrete to paint,
not just instructions. Runs in Blender:

  blender --background --python gen_texture_starter.py -- OUTDIR TOOLS CHECKER_PNG

Writes into OUTDIR:
  humanoid_uv.glb       -- the body, UV-unwrapped, materials named by HIT region (head/torso/arms/
                           legs), NO texture. This is the model you UV-paint onto.
  uv_islands.json       -- the UV polygons (per face: uv loop + region id), so the layout template
                           can be drawn host-side with PIL (Blender's export_layout needs a GPU and
                           is unavailable headless).
  humanoid_textured.glb -- the same body with CHECKER_PNG wired as base color (Image Texture ->
                           Principled Base Color) on every material -- a worked example proving the
                           texture round-trip renders.
"""
import json
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
OUT, TOOLS, CHECKER = argv[0], argv[1], argv[2]
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, TOOLS)
import meshes  # noqa: E402
from mesh_io import REGION_NAMES, region_for_name  # noqa: E402

bpy.ops.wm.read_factory_settings(use_empty=True)

verts, faces, freg = meshes.humanoid()
mesh = bpy.data.meshes.new("humanoid")
mesh.from_pydata([[float(c) for c in v] for v in verts], [], [[int(c) for c in f] for f in faces])
mesh.update()
obj = bpy.data.objects.new("humanoid", mesh)
bpy.context.scene.collection.objects.link(obj)

slot = {}
for rid, name in REGION_NAMES.items():            # materials named head/torso/arms/legs
    slot[rid] = len(mesh.materials)
    mesh.materials.append(bpy.data.materials.new(name))
for i, poly in enumerate(mesh.polygons):
    poly.material_index = slot[int(freg[i])]

# --- UV unwrap (cube projection reads cleanly on a boxy body) ---
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.cube_project(cube_size=1.0, correct_aspect=True)
bpy.ops.uv.pack_islands(margin=0.03)
bpy.ops.object.mode_set(mode='OBJECT')

# --- dump UV islands (per face: region + uv loop) for host-side layout rendering ---
uvs = mesh.uv_layers.active.data
mat_region = {i: region_for_name(mesh.materials[i].name) for i in range(len(mesh.materials))}
islands = [{"region": mat_region[poly.material_index],
            "uv": [[uvs[li].uv.x, uvs[li].uv.y] for li in poly.loop_indices]}
           for poly in mesh.polygons]
with open(os.path.join(OUT, "uv_islands.json"), "w") as f:
    json.dump({"polys": islands}, f)

# --- export the UV'd, untextured body (the model to paint onto) ---
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "humanoid_uv.glb"),
                          export_format='GLB', use_selection=True)
print("WROTE humanoid_uv.glb + uv_islands.json")

# --- worked example: wire the checker as base color on every material, export textured glb ---
img = bpy.data.images.load(CHECKER)
img.pack()
for mat in mesh.materials:
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    mat.diffuse_color = (0.8, 0.8, 0.8, 1.0)  # MATERIAL-mode fallback
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "humanoid_textured.glb"),
                          export_format='GLB', use_selection=True)
print("WROTE humanoid_textured.glb")
print("TEXTURE_STARTER_DONE", OUT)
