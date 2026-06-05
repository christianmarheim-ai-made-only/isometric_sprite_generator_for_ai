"""Bake animation CLIPS from a compact JSON keyframe spec (anim_clips_v1) onto a RIGGED glb,
producing an animated glb the pipeline can render. This is the "animation as text" bridge: an AI
writes per-bone keyframes as JSON; this turns them into real glTF animation clips on the rig.

  blender --background --python bake_anim_from_json.py -- IN_RIGGED.glb ANIM.json OUT.glb

ANIM.json (anim_clips_v1): a `clips` map; each clip has playback/fps/sample_frames + a `bones` map
of {bone_name: {rotation_euler: [[frame,[x,y,z]],...], location: [[frame,[x,y,z]],...]}} (radians /
metres). Bones not listed stay at the bind pose. Channels target bone NAMES, so one file animates
every body skinned to the same rig profile.
"""
import json
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
IN, ANIM, OUT = argv[0], argv[1], argv[2]
spec = json.load(open(ANIM))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if arm is None:
    raise SystemExit(f"no armature found in {IN}")

# the JSON is the single source of truth -> drop any clips the rigged glb shipped with
for act in list(bpy.data.actions):
    bpy.data.actions.remove(act)

bpy.context.view_layer.objects.active = arm
arm.animation_data_create()
bone_names = {b.name for b in arm.pose.bones}

for clip_name, clip in spec["clips"].items():
    act = bpy.data.actions.new(clip_name)
    arm.animation_data.action = act
    bpy.ops.object.mode_set(mode='POSE')
    authored = 0
    for bname, channels in (clip.get("bones") or {}).items():
        if bname not in bone_names:
            print("WARN bone not in rig, skipped:", bname)
            continue
        pb = arm.pose.bones[bname]
        if "rotation_euler" in channels:
            pb.rotation_mode = 'XYZ'
            for frame, xyz in channels["rotation_euler"]:
                pb.rotation_euler = xyz
                pb.keyframe_insert("rotation_euler", frame=frame)
                authored += 1
        if "location" in channels:
            for frame, xyz in channels["location"]:
                pb.location = xyz
                pb.keyframe_insert("location", frame=frame)
                authored += 1
    # an empty clip (e.g. idle with no moving bones) still needs one key so it has a frame range
    if authored == 0:
        root = arm.pose.bones.get("root") or arm.pose.bones[0]
        root.rotation_mode = 'XYZ'
        root.keyframe_insert("rotation_euler", frame=int(clip.get("duration_frames", 1)))
    bpy.ops.object.mode_set(mode='OBJECT')

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_animations=True,
                          export_animation_mode='ACTIONS', export_skins=True, use_selection=True)
print("BAKED_ANIM", OUT, "clips:", sorted(a.name for a in bpy.data.actions))
