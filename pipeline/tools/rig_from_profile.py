"""In-Blender: assemble an UNRIGGED part-mesh glb + a rig profile into a RIGGED glb.

Some producers deliver a model as separate body-part meshes (e.g. torso_body, head_head,
arms_front_leg_0) plus a rig PROFILE (bone head/tail/parent positions) plus anim clips that target
the profile's bone names -- but NOT an actual armature in the glb. bake_anim_from_json then fails
"no armature found". This tool builds the armature from the profile and rigidly skins each part-mesh
to its NEAREST bone (vertex group weight 1 + armature modifier), so the part follows that bone (and,
via the bone hierarchy, its parent's keyed motion). Rigid part-skinning is the natural choice for a
part-based mesh -- no weight painting, deterministic.

  blender --background --python rig_from_profile.py -- IN_UNRIGGED.glb RIG_PROFILE.json UP OUT_RIGGED.glb

UP = the asset's geometry.up ("z" or "y"): a Z-up-authored glb is stood upright before rigging so it
aligns with the profile's +Z-up bone frame; the exported glb is standard glTF (Y-up), so the asset's
geometry.up for the RIGGED glb is "y".
"""
import bpy, sys, json, math, os
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import region_for_name, material_region_name, REGION_NAMES, REGION_NAME_TO_ID  # shared region table (no drift)

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, PROFILE, UP, OUT = argv[0], argv[1], argv[2], argv[3]
MATERIALS = argv[4] if len(argv) > 4 and argv[4] else None      # optional sidecar materials.json (region + base_color)
SOURCE_ASSET = argv[5] if len(argv) > 5 and argv[5] else None   # optional source_asset.json (DECLARED hit_proxy regions)

for o in list(bpy.data.objects):           # clean default scene (cube/camera/light) so it doesn't export
    bpy.data.objects.remove(o, do_unlink=True)

prof = json.loads(open(PROFILE, encoding="utf-8").read())

before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=GLB)
meshes = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
if not meshes:
    raise SystemExit("rig_from_profile: no meshes imported")

# Stand a Z-up-authored glb upright (Blender's glTF import lays it on -Y) so it aligns with the
# profile's +Z-up bone positions before we measure centroids + skin.
if UP == "z":
    rot = Matrix.Rotation(math.radians(-90.0), 4, 'X')
    for m in meshes:
        m.matrix_world = rot @ m.matrix_world
    bpy.context.view_layer.update()

# Build the armature from the profile (bones are in the +Z-up rig frame == the corrected mesh frame).
arm_data = bpy.data.armatures.new("rig")
arm = bpy.data.objects.new(prof["rig_profile"], arm_data)
bpy.context.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
ebones = {}
for b in prof["bones"]:
    eb = arm_data.edit_bones.new(b["name"])
    eb.head = Vector(b["head"])
    eb.tail = Vector(b["tail"])
    if (eb.tail - eb.head).length < 1e-4:   # zero-length bones are deleted by Blender
        eb.tail = eb.head + Vector((0.0, 0.0, 0.02))
    ebones[b["name"]] = eb
for b in prof["bones"]:
    if b.get("parent") and b["parent"] in ebones:
        ebones[b["name"]].parent = ebones[b["parent"]]
bpy.ops.object.mode_set(mode='OBJECT')

# Nearest-bone proximity (exclude the static root). Each part-mesh binds 100% to one bone.
bone_mid = {b["name"]: (Vector(b["head"]) + Vector(b["tail"])) / 2
            for b in prof["bones"] if b["name"] != "root"}


def nearest_bone(c):
    return min(bone_mid, key=lambda bn: (bone_mid[bn] - c).length)


for m in meshes:
    cen = sum((m.matrix_world @ v.co for v in m.data.vertices), Vector()) / max(1, len(m.data.vertices))
    bone = nearest_bone(cen)
    vg = m.vertex_groups.new(name=bone)
    vg.add([v.index for v in m.data.vertices], 1.0, 'REPLACE')
    mod = m.modifiers.new(name="Armature", type='ARMATURE')
    mod.object = arm
    m.parent = arm
    m.matrix_parent_inverse = arm.matrix_world.inverted()   # keep the mesh in place under the new parent
    print(f"RIG: {m.name} -> {bone}")

# Material fix-up: the delivered glb carries generic DefaultMaterial names with no base colour, but
# the region + colour intent lives in the part-mesh OBJECT names (torso_body, head_head, ...) and the
# sidecar materials.json. Name each mesh's material after the mesh (so region_source=material_name
# resolves head/torso/arms/legs) and paint its base colour from the sidecar -- so the bake renders the
# right per-region colour instead of flat grey, and the R8 hitmask gets all four regions.
# Region assignment. The AUTHORITATIVE source is the producer's DECLARED hit_proxy_objects (region per
# part name) in the source_asset; fall back to the shared keyword table (constants.region_for_name) only
# when a part is not declared. This is what makes non-keyword creature parts survive -- a squid's
# `tentacle_3` declared `legs`, a dragon's `wing_L` declared `arms` -- instead of silently collapsing to
# torso. The keyword table is shared with the bake (mesh_io re-exports it), so the two never drift.
_declared = {}   # part name -> region id, from the source_asset's hit_proxy_objects
if SOURCE_ASSET:
    for hp in json.loads(open(SOURCE_ASSET, encoding="utf-8").read()).get("hit_proxy_objects", []):
        rid = REGION_NAME_TO_ID.get(hp.get("region"))
        if rid:
            _declared[hp["name"]] = rid


def _region_of(part_name):
    return _declared.get(part_name) or region_for_name(part_name)


# Per-region representative base colour from the sidecar (materials.json carries an explicit `region` +
# base_color per material). region id -> colour; the first material seen for a region wins.
_region_color = {}
if MATERIALS:
    _mats_raw = json.loads(open(MATERIALS, encoding="utf-8").read()).get("materials", [])
    # materials.json ships in TWO shapes: a LIST of {name,region,base_color} (materials_v1) OR a
    # name-keyed DICT {name: {region, base_color_factor, ...}} (character_materials_v1, e.g. the
    # pirate). Iterating a dict yields its string keys -> AttributeError; normalise both to dicts.
    if isinstance(_mats_raw, dict):
        _mats_iter = [dict(v, name=v.get("name", k)) for k, v in _mats_raw.items() if isinstance(v, dict)]
    else:
        _mats_iter = [mm for mm in _mats_raw if isinstance(mm, dict)]
    for mm in _mats_iter:
        rid = REGION_NAME_TO_ID.get(mm.get("region")) or region_for_name(mm.get("name", ""))
        col = mm.get("base_color") or mm.get("base_color_factor")
        if col:
            _region_color.setdefault(rid, col)

# Uncovered-region fallback: a region present on the mesh but with NO base_color in materials.json (a
# common producer gap -- e.g. limbs left unpainted, as in the green ogre's arms/legs and the red dragon's
# hindlegs) would otherwise bake flat 0.8 GREY -- a grey-limbed "green ogre". Inherit the BODY (torso,
# region 2) colour instead: it is the creature's skin/scale colour, a far better default than grey.
# Fall back to any declared colour, then grey. Warn once per region so the producer gap stays visible.
_warned_regions = set()


def _color_for(rid):
    col = _region_color.get(rid)
    if col:
        return col
    fb = _region_color.get(2) or (next(iter(_region_color.values()), None) if _region_color else None)
    if rid not in _warned_regions:
        _warned_regions.add(rid)
        print(f"WARN: region {rid} ({REGION_NAMES.get(rid, '?')}) has no base_color in materials.json -> "
              f"inheriting the body/torso colour {fb if fb else 'grey'} (paint it in the sidecar to override)")
    return fb or (0.8, 0.8, 0.8)

# REPLACE each part-mesh's material with a clean, fresh single-Principled material: the delivered glb's
# imported node graph resolves to flat 0.8 grey through the glTF exporter (see the vertex-colour note
# below), so a clean material is the only thing that round-trips. The material NAME must make the
# downstream bake resolve the part to the SAME region we assigned here -- keep the part name when its own
# keyword already resolves correctly, else append the canonical region keyword (e.g. a `tentacle_3`
# declared `legs` becomes `tentacle_3__legs`) so region_for_name agrees. The base colour comes from the
# sidecar, so the bake renders true per-region colour instead of grey.
def _mesh_is_textured(m):
    """A part-mesh that ALREADY carries a bound base-colour image + real (non-degenerate) UVs is a
    genuine textured delivery -- PRESERVE it through rigging (ADR-0027) instead of flattening it to a
    per-region colour. (Today's deliveries are all un-textured part-meshes, so this is a forward-looking
    guard; an unrigged+textured delivery keeps its texture instead of silently baking flat.)"""
    if not m.data.uv_layers or not m.data.uv_layers.active:
        return False
    uv = m.data.uv_layers.active.data
    if not uv:
        return False
    us = [d.uv[0] for d in uv]
    vs = [d.uv[1] for d in uv]
    if max(max(us) - min(us), max(vs) - min(vs)) < 1e-4:
        return False
    return any(mat and mat.use_nodes and any(n.type == 'TEX_IMAGE' and n.image for n in mat.node_tree.nodes)
               for mat in m.data.materials)


for _idx, m in enumerate(meshes):
    if _mesh_is_textured(m):
        print(f"MAT: {m.name} -> PRESERVED (bound texture + real UVs kept; flat per-region replace skipped)")
        continue
    region_id = _region_of(m.name)
    col = _color_for(region_id)
    mat_name = material_region_name(m.name, region_id, _idx)
    newmat = bpy.data.materials.new(name=mat_name)
    newmat.use_nodes = True
    bsdf = next(n for n in newmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (col[0], col[1], col[2], 1.0)
    newmat.diffuse_color = (col[0], col[1], col[2], 1.0)
    m.data.materials.clear()
    m.data.materials.append(newmat)
    # Strip vertex-colour attributes: if present, the glTF exporter writes a COLOR_0 stream and the
    # re-importer wires Color-Attribute -> Mix -> Principled Base Color, which parks the real baseColor
    # off the Principled default (left at flat 0.8 grey). MATERIAL-mode bake reads that default -> grey.
    # We want flat per-region colour, so drop the vertex colours entirely.
    while m.data.color_attributes:
        m.data.color_attributes.remove(m.data.color_attributes[0])
    src = "declared" if m.name in _declared else "keyword"
    print(f"MAT: {m.name} -> region {region_id} ({src}) mat='{mat_name}'  base {[round(c, 2) for c in (col[0], col[1], col[2])]}")

bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=False,
                          export_materials='EXPORT')   # keep bound base-colour images on round-trip
print(f"RIGGED -> {OUT}  ({len(meshes)} parts, {len(prof['bones'])} bones)")
