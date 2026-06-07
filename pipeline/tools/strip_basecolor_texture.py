"""In-Blender helper: import a glb, REMOVE every base-colour TEX_IMAGE node (so each material falls back
to its Principled Base Color = the glTF baseColorFactor), and re-export. Turns a 'flat-via-texture' hack
delivery into a clean flat_region glb (material base colours, no bound texture). Demo/repair tool.

  blender --background --python strip_basecolor_texture.py -- IN.glb OUT.glb
"""
import bpy, sys

argv = sys.argv[sys.argv.index("--") + 1:]
GLB_IN, GLB_OUT = argv[0], argv[1]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=GLB_IN)

removed = 0
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type == 'TEX_IMAGE':              # drop the base-colour texture node + its links
            nt.nodes.remove(n)
            removed += 1
print(f"STRIP: removed {removed} TEX_IMAGE node(s) -> base colour now = Principled default (baseColorFactor)")

bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format='GLB', use_selection=False, export_materials='EXPORT')
print("WROTE", GLB_OUT)
