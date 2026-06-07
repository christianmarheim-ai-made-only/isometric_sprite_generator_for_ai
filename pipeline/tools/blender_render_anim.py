"""R8: render a RIGGED + ANIMATED glb's clips through the game_iso_v1 camera (Blender). For each
declared (state, frame_index) it poses the armature (samples the clip) and renders 16 directions
(color + region passes). Emits anim_meta.json for the multi-state package assembler.

  blender --background --python blender_render_anim.py -- OUT TOOLS MESH.glb STATES_JSON
STATES_JSON file = {"idle": {"clip":"idle","frames":1}, "fly": {"clip":"fly","frames":4}}
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT, TOOLS, MESH_FILE, STATES_JSON = argv[0], argv[1], argv[2], argv[3]
UP = argv[4] if len(argv) > 4 else "y"  # asset geometry.up; "z" needs a Z-up correction (see below)
FORWARD = argv[5] if len(argv) > 5 else "+x"  # asset geometry.forward; rotated onto +X (direction 0)
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, TOOLS)
from mesh_io import region_for_name, REGION_KEYWORDS  # noqa: E402
from constants import CANVAS, DIRS, GROUND_BAND, REGION_RGB, forward_yaw  # noqa: E402

states = json.loads(open(STATES_JSON, encoding="utf-8").read())
COS30, SIN30, INV2 = math.cos(math.radians(30.0)), 0.5, 1.0 / math.sqrt(2.0)
REGION_COLOR = REGION_RGB

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.view_settings.view_transform = 'Standard'
try:                                      # pin the full colour-management state so textured albedo
    scene.view_settings.look = 'None'     # bakes faithfully regardless of the host Blender config
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.display_settings.display_device = 'sRGB'
except Exception:
    pass

before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=MESH_FILE)
imported = [o for o in bpy.data.objects if o not in before]
arm = next((o for o in imported if o.type == 'ARMATURE'), None)
meshes = [o for o in imported if o.type == 'MESH']
# Multi-PART delivery (e.g. a quadruped built as separate body-part meshes): JOIN the
# material-bearing meshes into one so height/footprint, region assignment, and texture/UV checks
# cover the WHOLE model. Measuring only the first mesh gives a torso-only hitmask + a too-short
# height. 0-material marker meshes (the generators' stray Icosphere) are excluded, so single-mesh
# deliveries -- and grunt/sparrow's Icosphere -- are unchanged.
real = [m for m in meshes if len(m.data.materials) > 0] or meshes
if len(real) > 1:
    for o in bpy.data.objects:
        o.select_set(False)
    for mo in real:
        mo.select_set(True)
    bpy.context.view_layer.objects.active = real[0]
    bpy.ops.object.join()
obj = real[0]
root_obj = arm if arm else obj

# Honor the asset's declared up-axis. Blender's glTF importer ALWAYS assumes the file is glTF
# Y-up and rotates +90deg about X. A glb authored Z-up (geometry.up == "z") therefore lands on
# its back (body along Blender -Y). Undo it with a -90deg X rotation so the character stands
# head-up (+Z), forward unchanged (+X). up == "y" (standard glTF, e.g. grunt/sparrow) needs none.
if UP == "z":
    root_obj.matrix_world = Matrix.Rotation(math.radians(-90.0), 4, 'X') @ root_obj.matrix_world
    bpy.context.view_layer.update()

bpy.context.view_layer.update()
cos = [obj.matrix_world @ v.co for v in obj.data.vertices]      # rest world coords
xs = [c.x for c in cos]; ys = [c.y for c in cos]; zs = [c.z for c in cos]
shift = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)))  # foot -> origin
root_obj.location = root_obj.location - shift
bpy.context.view_layer.update()
# Honor the asset's declared forward: rotate the model about world +Z (the foot sits at the origin, so
# this is anchor-stable) so the declared forward lands on +X = direction 0. forward == "+x" is the no-op
# default -- this block is skipped, so a +x bake is byte-identical to before. Same yaw + CCW convention
# as the per-direction orbit below, so it composes cleanly.
if FORWARD != "+x":
    root_obj.matrix_world = Matrix.Rotation(forward_yaw(FORWARD), 4, 'Z') @ root_obj.matrix_world
    bpy.context.view_layer.update()
base_mat = root_obj.matrix_world.copy()
cos = [obj.matrix_world @ v.co for v in obj.data.vertices]
zs = [c.z for c in cos]
height = max(zs) - min(zs)
ground = [max(abs(c.x), abs(c.y)) for c in cos if c.z <= min(zs) + 0.15 * height]
footprint = max(ground) if ground else max(max(abs(c.x), abs(c.y)) for c in cos)

region_of = {m.name: region_for_name(m.name) for m in obj.data.materials if m}
# materials whose name matched NO region keyword silently default to torso=2 -> a likely mistake
region_fallback = sorted(n for n in region_of if not any(kw in n.lower() for kw, _ in REGION_KEYWORDS))
has_tex = any(m and m.use_nodes and any(n.type == 'TEX_IMAGE' and n.image
              for n in m.node_tree.nodes) for m in obj.data.materials)
# Degenerate-UV detection: a material whose faces all sample ~one UV point collapses the embedded
# atlas to a single flat swatch (textured-but-renders-flat). Only meaningful when a texture exists.
degenerate_uv = []
if has_tex and obj.data.uv_layers:
    _uv = obj.data.uv_layers.active.data
    for _mi, _mat in enumerate(obj.data.materials):
        if _mat is None:
            continue
        _loops = [li for poly in obj.data.polygons if poly.material_index == _mi for li in poly.loop_indices]
        if _loops:
            _u = [_uv[li].uv[0] for li in _loops]
            _v = [_uv[li].uv[1] for li in _loops]
            if max(max(_u) - min(_u), max(_v) - min(_v)) < 1e-4:
                degenerate_uv.append(_mat.name)
# Resolve each material's flat MATERIAL-mode colour (Workbench reads diffuse_color). A clean factor-only
# material carries the colour on the Principled Base Color socket default. But a glTF re-import of a mesh
# that shipped vertex colours wires Color-Attribute -> Mix -> Base Color: the socket default is left at
# flat 0.8 grey while the real colour sits on an upstream constant input. Reading the default then renders
# SILENTLY grey. Detect that case (base_color_linked_materials warning) and best-effort recover the
# upstream constant colour by walking the feeder nodes for the first unlinked colour input.
base_color_linked = []


def _flat_base_color(bsdf):
    bc = bsdf.inputs['Base Color']
    if not bc.is_linked:
        return bc.default_value
    stack = [lk.from_node for lk in bc.links]
    seen = set()
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for inp in n.inputs:
            if inp.is_linked:
                stack.extend(lk.from_node for lk in inp.links)
            elif hasattr(inp, 'default_value'):
                try:
                    if len(inp.default_value) >= 3:   # first unlinked colour constant == baseColorFactor
                        return inp.default_value
                except TypeError:
                    pass
    return bc.default_value


def _basecolor_direct_tex(bsdf):
    bc = bsdf.inputs['Base Color']
    return bool(bc.is_linked and bc.links and bc.links[0].from_node.type == 'TEX_IMAGE')


for _m in obj.data.materials:
    if _m and _m.use_nodes:
        _b = next((n for n in _m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if _b is not None:
            # base_color_linked = the REAL grey bug ONLY: a Base Color linked through a NON-texture
            # node (glTF vertex-colour Color-Attribute -> Mix) parks the socket default at flat grey.
            # A DIRECT TEX_IMAGE link is a legitimate texture (renders correctly in TEXTURE mode) and
            # must NOT be flagged -- it previously fired on every textured model incl. the known-good
            # fixture (a near-universal false positive that would mis-trip the fidelity gate).
            if _b.inputs['Base Color'].is_linked and not _basecolor_direct_tex(_b):
                base_color_linked.append(_m.name)
            _c = _flat_base_color(_b)
            _m.diffuse_color = (_c[0], _c[1], _c[2], 1.0)
        for _n in _m.node_tree.nodes:        # pin base-colour textures to sRGB (faithful albedo)
            if _n.type == 'TEX_IMAGE' and _n.image:
                try:
                    _n.image.colorspace_settings.name = 'sRGB'
                except Exception:
                    pass

right = Vector((1.0, -1.0, 0.0)).normalized()
up = Vector((-0.5 * INV2, -0.5 * INV2, COS30)).normalized()
back = Vector((COS30 * INV2, COS30 * INV2, SIN30)).normalized()
rot = Matrix(((right.x, up.x, back.x), (right.y, up.y, back.y), (right.z, up.z, back.z))).to_4x4()
target = Vector((0.0, 0.0, height / 2.0))
cam_data = bpy.data.cameras.new("isocam")
cam_data.type = 'ORTHO'
span = max(max(xs) - min(xs), max(ys) - min(ys), height)
cam_data.ortho_scale = span * 1.9 + 0.05
cam = bpy.data.objects.new("isocam", cam_data)
scene.collection.objects.link(cam)
cam.matrix_world = Matrix.Translation(target + back * 100.0) @ rot
scene.camera = cam

r = scene.render
r.engine = 'BLENDER_WORKBENCH'
r.resolution_x = r.resolution_y = CANVAS
r.resolution_percentage = 100
r.film_transparent = True
r.image_settings.file_format = 'PNG'
r.image_settings.color_mode = 'RGBA'
shading = scene.display.shading

from bpy_extras.object_utils import world_to_camera_view  # noqa: E402


def probe(p):
    co = world_to_camera_view(scene, cam, Vector(p))
    return [co.x, 1.0 - co.y]


camera_probe = {k: probe(v) for k, v in {"origin": (0, 0, 0), "px": (1, 0, 0), "py": (0, 1, 0), "pz": (0, 0, 1)}.items()}

actions = {a.name: a for a in bpy.data.actions}
poses = []  # (state, frame_index, action_name|None, frame_value|None)
missing_clips = []  # declared states whose clip is absent from the glb -> rendered as the REST pose
for state, spec in states.items():
    clip, nf = spec.get("clip", state), spec["frames"]
    playback = spec.get("playback", "loop")
    act = actions.get(clip)
    if act:
        f0, f1 = act.frame_range
        # loop: half-open [f0,f1) -- the authored seam frame N+1 == frame 1 is skipped (samples
        # fi/nf). once: closed [f0,f1] -- the LAST sprite frame must BE the authored terminal/held
        # pose (the engine holds it as the corpse/settle), so sample fi/(nf-1) to land on f1.
        denom = nf if playback == "loop" else max(nf - 1, 1)
        for fi in range(nf):
            poses.append((state, fi, clip, f0 + (f1 - f0) * (fi / denom)))
    else:
        missing_clips.append(state)
        poses.append((state, 0, None, None))

if arm and not arm.animation_data:
    arm.animation_data_create()


def apply(name, fv, d):
    if arm and name:
        arm.animation_data.action = actions[name]
        scene.frame_set(int(round(fv)))
    root_obj.matrix_world = Matrix.Rotation(d * (2 * math.pi / DIRS), 4, 'Z') @ base_mat
    bpy.context.view_layer.update()


def render_all(prefix):
    for (state, fi, an, fv) in poses:
        for d in range(DIRS):
            apply(an, fv, d)
            r.filepath = os.path.join(OUT, f"{prefix}_{state}_f{fi}_dir{d:02d}.png")
            bpy.ops.render.render(write_still=True)


shading.color_type = 'TEXTURE' if has_tex else 'MATERIAL'
# Textured albedo already bakes AO/value into the texture, and STUDIO light roughly halves its
# saturation -> render the textured colour pass FLAT for faithful colour. Untextured flat_region
# keeps STUDIO so its solid per-region colours read with some form. (ADR-0032.)
shading.light = 'FLAT' if has_tex else 'STUDIO'
scene.display.render_aa = '8'
render_all("color")
for m in obj.data.materials:
    if m is not None:
        m.use_nodes = False
        m.diffuse_color = (*REGION_COLOR[region_of.get(m.name, 2)], 1.0)
shading.color_type = 'MATERIAL'
shading.light = 'FLAT'
scene.display.render_aa = 'OFF'
render_all("region")

meta = {
    "canvas": CANVAS, "dirs": DIRS, "region_color": {str(k): list(v) for k, v in REGION_COLOR.items()},
    "camera_probe": camera_probe, "anchor_frac": probe((0, 0, 0)),
    "mesh_height": round(height, 6), "mesh_footprint": round(footprint, 6),
    "poses": [[s, fi] for (s, fi, _, _) in poses],
    "region_fallback_materials": region_fallback,
    "missing_clips": missing_clips,
    "degenerate_uv_materials": degenerate_uv,
    "base_color_linked_materials": base_color_linked,
    "blender_version": bpy.app.version_string,
}
json.dump(meta, open(os.path.join(OUT, "anim_meta.json"), "w"), indent=2)
print("R8_ANIM_DONE", OUT, len(poses), "poses x", DIRS, "dirs")
