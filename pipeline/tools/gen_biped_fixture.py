"""Generate a RIGGED biped glb (skinned to biped_v1) for the combat-unit template. The body is boxes,
each part skinned 100% to its biped_v1 bone (bind poses read from the rig profile). Materials are
named head/torso/arms/legs (HIT regions) with base colors. A FRONT feature (face + chest plate on
+X) keeps the 16 directions distinct. NO clips are embedded -- the combat clips come from an
anim_clips_v1 JSON via bake_anim_from_json (so the same animation file drives every biped variant).

  blender --background --python gen_biped_fixture.py -- OUT.glb TOOLS_DIR
"""
import json
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
OUT, TOOLS = argv[0], argv[1]
os.makedirs(os.path.dirname(OUT), exist_ok=True)
PIPELINE = os.path.dirname(os.path.normpath(TOOLS))
prof = json.load(open(os.path.join(PIPELINE, "schema", "rig_profiles", "biped_v1.json")))
BONES = {b["name"]: b for b in prof["bones"]}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

verts, faces, part_verts, part_mat = [], [], {}, {}


def box(bone, mat, x0, x1, y0, y1, z0, z1):
    b = len(verts)
    verts.extend([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                  (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
    for f in [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
              (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]:
        faces.append((f[0] + b, f[1] + b, f[2] + b))
        part_mat[len(faces) - 1] = mat
    part_verts.setdefault(bone, []).extend(range(b, b + 8))


# (bone, region-material, x0,x1, y0,y1, z0,z1) -- +X forward, +Y left, +Z up
box("head", "head", -0.10, 0.10, -0.11, 0.11, 1.46, 1.78)
box("head", "head", 0.10, 0.20, -0.08, 0.08, 1.50, 1.72)        # face (FRONT)
box("chest", "torso", -0.15, 0.15, -0.20, 0.20, 1.20, 1.44)
box("chest", "torso", 0.15, 0.23, -0.16, 0.16, 1.06, 1.40)      # chest plate (FRONT)
box("spine", "torso", -0.14, 0.14, -0.17, 0.17, 1.04, 1.20)
box("hips", "torso", -0.15, 0.15, -0.18, 0.18, 0.90, 1.04)
box("arm.L", "arms", -0.06, 0.06, 0.20, 0.36, 1.14, 1.44)
box("forearm.L", "arms", -0.06, 0.06, 0.30, 0.46, 0.88, 1.16)
box("arm.R", "arms", -0.06, 0.06, -0.36, -0.20, 1.14, 1.44)
box("forearm.R", "arms", -0.06, 0.06, -0.46, -0.30, 0.88, 1.16)
box("thigh.L", "legs", -0.08, 0.08, 0.02, 0.18, 0.50, 0.92)
box("shin.L", "legs", -0.08, 0.08, 0.02, 0.18, 0.08, 0.50)
box("foot.L", "legs", -0.06, 0.16, 0.02, 0.18, 0.0, 0.10)
box("thigh.R", "legs", -0.08, 0.08, -0.18, -0.02, 0.50, 0.92)
box("shin.R", "legs", -0.08, 0.08, -0.18, -0.02, 0.08, 0.50)
box("foot.R", "legs", -0.06, 0.16, -0.18, -0.02, 0.0, 0.10)

mesh = bpy.data.meshes.new("grunt")
mesh.from_pydata(verts, [], faces)
mesh.update()
mat_colors = {"head": (0.85, 0.68, 0.55, 1), "torso": (0.25, 0.40, 0.70, 1),
              "arms": (0.80, 0.62, 0.50, 1), "legs": (0.22, 0.24, 0.30, 1)}
mat_slot = {}
for name, col in mat_colors.items():
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = col
    m.diffuse_color = col
    mat_slot[name] = len(mesh.materials)
    mesh.materials.append(m)
for fi, poly in enumerate(mesh.polygons):
    poly.material_index = mat_slot[part_mat[fi]]
obj = bpy.data.objects.new("grunt", mesh)
scene.collection.objects.link(obj)

# ---- biped_v1 armature from the rig profile's bind poses ----
arm_data = bpy.data.armatures.new("biped_v1")
arm = bpy.data.objects.new("biped_v1", arm_data)
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = arm_data.edit_bones
for b in prof["bones"]:
    bone = eb.new(b["name"])
    bone.head, bone.tail = b["head"], b["tail"]
for b in prof["bones"]:
    if b["parent"]:
        eb[b["name"]].parent = eb[b["parent"]]
bpy.ops.object.mode_set(mode='OBJECT')

# ---- skin: each part 100% to its bone ----
mod = obj.modifiers.new("Armature", 'ARMATURE')
mod.object = arm
obj.parent = arm
for bone_name, idxs in part_verts.items():
    obj.vertex_groups.new(name=bone_name).add(idxs, 1.0, 'REPLACE')

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_skins=True,
                          export_animations=False, use_selection=True)
print("WROTE_BIPED", OUT, "bones:", len(prof["bones"]), "parts:", len(part_verts))
