import bpy, sys
glb = sys.argv[sys.argv.index("--") + 1:][0]
bpy.ops.import_scene.gltf(filepath=glb)
mn = [1e9] * 3
mx = [-1e9] * 3
for o in bpy.data.objects:
    if o.type == 'MESH':
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            for i in range(3):
                mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
dims = [round(mx[i] - mn[i], 4) for i in range(3)]
print("DIAG_DIMS_XYZ", dims)
print("DIAG_MIN", [round(v, 4) for v in mn])
print("DIAG_MAX", [round(v, 4) for v in mx])
# which axis holds the tallest (body height) extent?
tallest = max(range(3), key=lambda i: dims[i])
print("DIAG_TALLEST_AXIS", "XYZ"[tallest], dims[tallest])
