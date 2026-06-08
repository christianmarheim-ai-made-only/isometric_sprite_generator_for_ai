# Stage 5 — Rig to the profile

## PROMPT

Skin the mesh to the rig profile chosen in Stage 0 (`pipeline/schema/rig_profiles/<rig>.json`). The
bone names are the contract: the shared archetype animation library targets **bone names**, so one clip
set drives every body skinned to the same profile. Skin to the profile's **exact** bone names.

For `biped_v1` the skeleton is body-only, ~1.8 m, bind pose a relaxed A-pose, feet at the origin on
z=0, facing +X. Its bones (skin to these):

```
root, hips, spine, chest, head,
arm.L, forearm.L, hand.L,  arm.R, forearm.R, hand.R,
thigh.L, shin.L, foot.L,  thigh.R, shin.R, foot.R
```

The profile also carries `region_by_bone` (head→head, spine/chest/hips→torso, arm*/hand*→arms,
thigh*/shin*/foot*→legs) — keep your Stage-2 part regions consistent with it.

Requirements:

- **Every part is weighted** to a real bone — no orphan/unweighted geometry (`unweighted_part`, error).
- **Bone names exist in the profile.** If you ship a `<variant_id>_skin_binding.json` sidecar, the
  linter checks every `assignments[part].bone` is a real profile bone; a typo or invented bone is
  `missing_required_bone` (error) caught statically before any bake.
- **≤ 4 influences per vertex** (`too_many_influences`, error). glTF skinning is 4-weight.
- If you deliver **no armature**, the pipeline can auto-rig from the profile (`rig_from_profile`); this
  stamps an `auto_rigged` note (info) and the baked glb becomes pipeline-derived, not your delivered
  mesh. Prefer shipping your own rig for a combat creature so the attack/hit poses are yours.

## CONSTRAINTS

- `rig` in the manifest must be a known profile id (`schema/rig_profiles/<rig>.json` exists), else the
  linter rejects it.
- Do not rename profile bones. A flavour state (e.g. dragon `breath`) is allowed at the clip layer, not
  by renaming bones.

## GATES THIS STAGE MUST PASS

- `required_bones_present` (code `missing_required_bone`, error) — bound bones exist in the rig.
- `all_parts_weighted` (code `unweighted_part`, error) — no unweighted geometry.
- `max_4_influences` (code `too_many_influences`, error) — ≤ 4 bone influences per vertex.

## DONE WHEN

The mesh is fully skinned to the profile's exact bone names, every part is weighted, no vertex exceeds
4 influences, and (if shipped) `<variant_id>_skin_binding.json` lints clean against the rig profile.
