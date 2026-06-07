# Canonical error / warning codes

Generated from `pipeline/tools/error_codes.py` (the single source of truth).

| code | default severity | stage | verification check |
|---|---|---|---|
| `loop_discontinuity` | warn | animation | `loop_continuity` |
| `missing_clip_rest_pose` | warn | animation | `declared_clips_exist` |
| `missing_required_clip` | error | animation | `required_clips_present` |
| `offvocab_clip` | warn | animation | `clip_vocab` |
| `oversize_atlas_page` | error | bake | `atlas_page_size` |
| `verification_build_log_disagree` | error | bake | `ok_agreement` |
| `region_fallback_torso` | warn | hitbox | `no_region_fallback` |
| `region_missing` | error | hitbox | `regions_present` |
| `archetype_rig_mismatch` | error | input | `archetype_matches_rig` |
| `obj_textured_unsupported` | error | input | `mesh_format_supports_mode` |
| `package_manifest_mismatch` | error | input | `manifest_matches_files` |
| `preflight_missing` | error | input | `preflight_present` |
| `preflight_not_ok` | error | input | `preflight_ok` |
| `preflight_stale` | warn | input | `preflight_fresh` |
| `referenced_file_missing` | error | input | `referenced_files_exist` |
| `texture_mode_missing` | error | input | `texture_mode_declared` |
| `waiver_attempts_real_albedo_true` | error | input | `waiver_no_real_albedo` |
| `waiver_expired` | error | input | `waiver_valid` |
| `waiver_missing` | error | input | `waiver_present` |
| `waiver_unknown_code` | error | input | `waiver_code_known` |
| `forward_axis_mismatch` | error | modeling | `forward_axis` |
| `front_back_indistinct` | error | modeling | `front_back_distinctness` |
| `ground_origin_mismatch` | error | modeling | `ground_origin` |
| `non_upright_biped` | warn | modeling | `upright` |
| `world_metrics_mismatch` | error | modeling | `scale` |
| `auto_rigged` | warn | skinning | `auto_rig_note` |
| `missing_required_bone` | error | skinning | `required_bones_present` |
| `too_many_influences` | error | skinning | `max_4_influences` |
| `unweighted_part` | error | skinning | `all_parts_weighted` |
| `atlas_colour_rich_low` | error | texture | `atlas_colour_rich` |
| `base_color_linked` | warn | texture | `base_color_source` |
| `degenerate_uv` | warn | texture | `degenerate_uv` |
| `flat_region_real_albedo` | error | texture | `flat_region_no_real_albedo` |
| `orphan_texture` | error | texture | `orphan_texture` |
| `texture_unbound` | error | texture | `has_bound_tex` |
| `uv_overlap_undeclared` | error | texture | `uv_overlap` |
