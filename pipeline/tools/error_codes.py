"""Canonical pipeline error/warning codes -- the single source of truth (review snippet 14).

Each code maps to (default_severity, stage, verification_check) so the linter, build_log, and
verification_report.json all speak ONE vocabulary and cannot drift. The verification report is a
pure projection of the build_log warnings through this table (so the two `ok` flags cannot disagree).

Stages: input | modeling | texture | skinning | animation | hitbox | bake | package.
Severities: error (flips ok=false) | warn | waived.
"""
from __future__ import annotations

STAGES = ("input", "modeling", "texture", "skinning", "animation", "hitbox", "bake", "package")

# code -> (default_severity, stage, verification_check)
CODES = {
    # --- input / package ---
    "referenced_file_missing":          ("error", "input",     "referenced_files_exist"),
    "package_manifest_mismatch":        ("error", "input",     "manifest_matches_files"),
    "texture_mode_missing":             ("error", "input",     "texture_mode_declared"),
    "obj_textured_unsupported":         ("error", "input",     "mesh_format_supports_mode"),
    "archetype_rig_mismatch":           ("error", "input",     "archetype_matches_rig"),
    "preflight_missing":                ("error", "input",     "preflight_present"),
    "preflight_not_ok":                 ("error", "input",     "preflight_ok"),
    "preflight_stale":                  ("warn",  "input",     "preflight_fresh"),
    # --- modeling ---
    "forward_axis_mismatch":            ("error", "modeling",  "forward_axis"),
    "ground_origin_mismatch":           ("error", "modeling",  "ground_origin"),
    "world_metrics_mismatch":           ("error", "modeling",  "scale"),
    "non_upright_biped":                ("warn",  "modeling",  "upright"),
    "front_back_indistinct":            ("error", "modeling",  "front_back_distinctness"),
    # --- texture ---
    "texture_unbound":                  ("error", "texture",   "has_bound_tex"),
    "degenerate_uv":                    ("warn",  "texture",   "degenerate_uv"),    # -> error when textured (B3)
    "orphan_texture":                   ("error", "texture",   "orphan_texture"),
    "atlas_colour_rich_low":            ("error", "texture",   "atlas_colour_rich"),
    "uv_overlap_undeclared":            ("error", "texture",   "uv_overlap"),
    "base_color_linked":                ("warn",  "texture",   "base_color_source"),  # never error (real grey-bug only)
    "flat_region_real_albedo":          ("error", "texture",   "flat_region_no_real_albedo"),
    "flat_region_bound_texture":        ("error", "texture",   "flat_region_no_bound_texture"),  # the flat-via-texture hack
    # --- bake: USELESS-content (the process must KNOW it baked junk) ---
    "blank_frame":                      ("error", "bake",      "no_blank_frames"),                # a baked direction/state rendered empty
    # --- skinning ---
    "missing_required_bone":            ("error", "skinning",  "required_bones_present"),
    "unweighted_part":                  ("error", "skinning",  "all_parts_weighted"),
    "too_many_influences":              ("error", "skinning",  "max_4_influences"),
    "auto_rigged":                      ("warn",  "skinning",  "auto_rig_note"),
    # --- animation ---
    "missing_clip_rest_pose":           ("warn",  "animation", "declared_clips_exist"),  # -> error for required clip
    "missing_required_clip":            ("error", "animation", "required_clips_present"),
    "offvocab_clip":                    ("warn",  "animation", "clip_vocab"),
    "loop_discontinuity":               ("warn",  "animation", "loop_continuity"),
    # --- hitbox ---
    "region_fallback_torso":            ("warn",  "hitbox",    "no_region_fallback"),   # -> error when textured (B3)
    "region_missing":                   ("error", "hitbox",    "regions_present"),
    "calib_region_color_mismatch":      ("error", "hitbox",    "calib_region_color_matches"),  # calib texture<->hitbox disagree
    # --- bake ---
    "oversize_atlas_page":              ("error", "bake",      "atlas_page_size"),
    "verification_build_log_disagree":  ("error", "bake",      "ok_agreement"),
    # --- waivers ---
    "waiver_missing":                   ("error", "input",     "waiver_present"),
    "waiver_expired":                   ("error", "input",     "waiver_valid"),
    "waiver_unknown_code":              ("error", "input",     "waiver_code_known"),
    "waiver_attempts_real_albedo_true": ("error", "input",     "waiver_no_real_albedo"),
    # --- skin / texture-only variant delta (review #24 variant compatibility) ---
    "skin_delta_invalid":               ("error", "input",     "skin_delta_well_formed"),
    "skin_delta_self_reference":        ("error", "input",     "skin_delta_distinct_variant"),
    "skin_delta_base_missing":          ("error", "input",     "skin_delta_base_present"),
    "skin_delta_base_not_capable":      ("error", "input",     "skin_delta_base_reskinnable"),
    "skin_delta_texture_missing":       ("error", "input",     "skin_delta_texture_present"),
    "skin_delta_texture_invalid":       ("error", "input",     "skin_delta_texture_valid"),
    "skin_delta_real_albedo_conflict":  ("error", "input",     "skin_delta_albedo_coherent"),
    "skin_delta_geometry_changed":      ("error", "input",     "skin_delta_geometry_identical"),
}


def _row(code):
    return CODES.get(code, ("error", "bake", code))


def severity_of(code):
    return _row(code)[0]


def stage_of(code):
    return _row(code)[1]


def check_of(code):
    return _row(code)[2]


def is_known(code):
    return code in CODES
