"""In-Blender helper for skin_delta.apply_delta: import a base glb, replace EVERY material's base-colour
image with a new PNG (geometry/UVs/rig untouched), and re-export the variant glb.

  blender --background --python swap_basecolor.py -- BASE.glb NEW_BASECOLOR.png OUT.glb
"""
import bpy, sys

argv = sys.argv[sys.argv.index("--") + 1:]
GLB_IN, PNG, GLB_OUT = argv[0], argv[1], argv[2]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=GLB_IN)

newimg = bpy.data.images.load(PNG)
try:
    newimg.colorspace_settings.name = 'sRGB'
except Exception:
    pass

swapped = 0
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image is not None:
            n.image = newimg          # repoint the base-colour texture node at the new skin
            swapped += 1
print(f"SWAP: repointed {swapped} TEX_IMAGE node(s) -> {PNG}")
if swapped == 0:
    raise SystemExit("swap_basecolor: base glb had no TEX_IMAGE node to replace")

bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format='GLB', use_selection=False, export_materials='EXPORT')
print("WROTE", GLB_OUT)
