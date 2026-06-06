import bpy, sys
glb = sys.argv[sys.argv.index("--") + 1:][0]
before = set(bpy.data.objects)                       # exclude Blender default-scene objects
bpy.ops.import_scene.gltf(filepath=glb)
imported = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
main = max(imported, key=lambda o: len(o.data.vertices)) if imported else None  # the real mesh, not the marker Icosphere
for o in imported:
    mn = [1e9] * 3
    mx = [-1e9] * 3
    for v in o.data.vertices:
        w = o.matrix_world @ v.co
        for i in range(3):
            mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
    dims = [round(mx[i] - mn[i], 3) for i in range(3)]
    tallest = "XYZ"[max(range(3), key=lambda i: dims[i])]
    tag = "  <- MAIN" if o is main else ""
    print(f"DIAG {o.name}: dims {dims} min {[round(v,2) for v in mn]} max {[round(v,2) for v in mx]} tallest={tallest}{tag}")
