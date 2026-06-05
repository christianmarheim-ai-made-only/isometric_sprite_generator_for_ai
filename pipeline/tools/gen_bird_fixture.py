"""Generate a RIGGED + ANIMATED bird glb for the external-animation demo (R8). A body-only bird
skinned to the bird_v1 rig with `idle` + `fly` (wing-flap) clips. Body color is a CLI arg, so the
SAME rig + animation authoring produces multiple variants -- the "many birds, one rig" reuse case.

Run in Blender:  blender --background --python gen_bird_fixture.py -- OUT.glb [r,g,b]
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
body_rgb = tuple(float(x) for x in (argv[1] if len(argv) > 1 else "0.45,0.30,0.18").split(","))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---- bird mesh from boxes; per-part region material + per-bone vertex ranges ----
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


box("body", "body", -0.10, 0.08, -0.05, 0.05, 0.10, 0.20)
box("head", "head", 0.08, 0.16, -0.04, 0.04, 0.15, 0.22)
box("tail", "tail", -0.18, -0.10, -0.03, 0.03, 0.13, 0.18)
box("wing.L", "wing", -0.06, 0.04, 0.05, 0.20, 0.135, 0.155)
box("wing.R", "wing", -0.06, 0.04, -0.20, -0.05, 0.135, 0.155)
box("leg.L", "leg", -0.01, 0.02, 0.02, 0.05, 0.0, 0.10)
box("leg.R", "leg", -0.01, 0.02, -0.05, -0.02, 0.0, 0.10)

mesh = bpy.data.meshes.new("bird")
mesh.from_pydata(verts, [], faces)
mesh.update()
dark = tuple(c * 0.7 for c in body_rgb)
mat_colors = {"body": (*body_rgb, 1), "head": (0.92, 0.72, 0.20, 1), "wing": (*dark, 1),
              "tail": (*body_rgb, 1), "leg": (0.85, 0.62, 0.18, 1)}
mat_slot = {}
for name, col in mat_colors.items():
    m = bpy.data.materials.new(name)
    m.use_nodes = True  # set the Principled Base Color so glTF export captures it
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = col
    m.diffuse_color = col
    mat_slot[name] = len(mesh.materials)
    mesh.materials.append(m)
for fi, poly in enumerate(mesh.polygons):
    poly.material_index = mat_slot[part_mat[fi]]
bird = bpy.data.objects.new("bird", mesh)
scene.collection.objects.link(bird)

# ---- bird_v1 armature ----
arm_data = bpy.data.armatures.new("bird_v1")
arm = bpy.data.objects.new("bird_v1", arm_data)
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = arm_data.edit_bones


def bone(name, parent, head, tail):
    b = eb.new(name)
    b.head, b.tail = head, tail
    if parent:
        b.parent = eb[parent]


bone("root", None, (0, 0, 0), (0, 0, 0.05))
bone("body", "root", (0, 0, 0.10), (0, 0, 0.20))
bone("neck", "body", (0.06, 0, 0.18), (0.10, 0, 0.19))
bone("head", "neck", (0.10, 0, 0.19), (0.16, 0, 0.20))
bone("wing.L", "body", (0, 0.05, 0.15), (0, 0.20, 0.15))
bone("wingtip.L", "wing.L", (0, 0.20, 0.15), (0, 0.24, 0.15))
bone("wing.R", "body", (0, -0.05, 0.15), (0, -0.20, 0.15))
bone("wingtip.R", "wing.R", (0, -0.20, 0.15), (0, -0.24, 0.15))
bone("tail", "body", (-0.10, 0, 0.16), (-0.18, 0, 0.16))
bone("leg.L", "body", (0, 0.035, 0.10), (0, 0.035, 0.0))
bone("leg.R", "body", (0, -0.035, 0.10), (0, -0.035, 0.0))
bpy.ops.object.mode_set(mode='OBJECT')

# ---- skin: each part 100% to its bone (deterministic, no bone-heat) ----
mod = bird.modifiers.new("Armature", 'ARMATURE')
mod.object = arm
bird.parent = arm
for bone_name, idxs in part_verts.items():
    bird.vertex_groups.new(name=bone_name).add(idxs, 1.0, 'REPLACE')

# ---- animation clips: fly (wing flap) + idle (rest) ----
bpy.context.view_layer.objects.active = arm
arm.animation_data_create()


def author(action_name, keys):
    act = bpy.data.actions.new(action_name)
    arm.animation_data.action = act
    bpy.ops.object.mode_set(mode='POSE')
    wl, wr = arm.pose.bones["wing.L"], arm.pose.bones["wing.R"]
    wl.rotation_mode = wr.rotation_mode = 'XYZ'
    for frame, ang in keys:
        wl.rotation_euler = (ang, 0, 0)
        wr.rotation_euler = (-ang, 0, 0)
        wl.keyframe_insert("rotation_euler", frame=frame)
        wr.keyframe_insert("rotation_euler", frame=frame)
    bpy.ops.object.mode_set(mode='OBJECT')


author("fly", [(1, -0.8), (3, 0.8), (5, -0.8)])   # flap down/up/down (loops)
author("idle", [(1, 0.0)])                        # wings at rest

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_animations=True,
                          export_animation_mode='ACTIONS', export_skins=True, use_selection=True)
print("WROTE_BIRD", OUT, "actions:", sorted(a.name for a in bpy.data.actions))
