import bpy, sys
glb = sys.argv[sys.argv.index("--") + 1:][0]
before = set(bpy.data.objects)               # mirror blender_render_anim: exclude default-scene objects
bpy.ops.import_scene.gltf(filepath=glb)
imported = [o for o in bpy.data.objects if o not in before]
meshes = [o for o in imported if o.type == 'MESH']
print("DIAG_IMPORTED_MESH_COUNT", len(meshes), [o.name for o in meshes])
for o in meshes:
    me = o.data
    has_tex = any(m and m.use_nodes and any(n.type == 'TEX_IMAGE' and n.image
                  for n in m.node_tree.nodes) for m in me.materials)
    if me.uv_layers:
        uv = me.uv_layers.active.data
        degen = []
        for mi, mat in enumerate(me.materials):
            loops = [li for poly in me.polygons if poly.material_index == mi for li in poly.loop_indices]
            if loops:
                mu = [uv[li].uv[0] for li in loops]; mv = [uv[li].uv[1] for li in loops]
                if max(max(mu) - min(mu), max(mv) - min(mv)) < 1e-4:
                    degen.append(mat.name if mat else f"mat{mi}")
        print(f"DIAG {o.name}: has_tex={has_tex} materials={len(me.materials)} degenerate_uv={len(degen)}/{len(me.materials)}")
    else:
        print(f"DIAG {o.name}: has_tex={has_tex} materials={len(me.materials)} NO_UV_LAYER")
