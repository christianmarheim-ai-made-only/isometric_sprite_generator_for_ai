//! R6 engine load-test: the committed pipeline packages must be accepted by the REAL
//! engine accept/reject logic (vendored verbatim in `loader::parse_manifest`). Proves the
//! pipeline -> engine path end-to-end, in CI, without a Bevy build.

use bevy_reference_loader::loader::parse_manifest;
use std::path::{Path, PathBuf};

fn manifest(rel: &str) -> String {
    let p: PathBuf = Path::new(env!("CARGO_MANIFEST_DIR")).join(rel);
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("read {}: {e}", p.display()))
}

#[test]
fn reference_character_is_engine_loadable() {
    let json = manifest("../reference/humanoid_ref/manifest.json");
    let s = parse_manifest(&json).expect("engine parse_manifest must accept the reference character");
    assert_eq!(s.variant.directions, 16, "16 directions");
    assert_eq!(s.variant.frames.len(), 16, "one frame per direction");
    assert_eq!(s.name, "humanoid_ref");
    let m = s.variant.metrics;
    assert!(m.height_world > 0.0 && m.footprint_radius_world > 0.0, "positive metrics");
    let eye = m.eye_height_world.expect("character carries eye_height_world");
    assert!(eye <= m.height_world, "eye <= height");
}

#[test]
fn reference_blender_character_is_engine_loadable() {
    // R7: the Blender-rendered production package is engine-loadable too.
    let json = manifest("../reference/humanoid_blender/manifest.json");
    let s = parse_manifest(&json).expect("engine must accept the Blender-rendered reference character");
    assert_eq!(s.variant.frames.len(), 16);
    assert_eq!(s.name, "humanoid_blender");
    let m = s.variant.metrics;
    assert!(m.eye_height_world.unwrap() <= m.height_world, "eye <= height");
}

#[test]
fn arrow_pilot_is_engine_loadable_forward_compat() {
    // The rich M1/M2 pilot manifest carries extra fields (state, animations, boxes,
    // hitmask, contract_hash, ...); the engine loader ignores them (serde forward-compat).
    let json = manifest("../output/arrow_pilot/manifest.json");
    let s = parse_manifest(&json).expect("engine must accept the arrow pilot");
    assert_eq!(s.variant.frames.len(), 16);
}

#[test]
fn loader_actually_rejects_bad_metrics() {
    // Guard that the load-test is not a no-op: a character with eye > height must FAIL.
    let bad = r#"{"camera":{"id":"game_iso_v1"},"variant_class":"character","direction_count":1,
        "frame_canvas":[10,10],"atlases":{"color":{"path":"c.png","size":[10,10]}},
        "frames":[{"direction":0,"rect":[0,0,10,10],"anchor":[5,9]}],
        "world_metrics":{"height_world":1.0,"footprint_radius_world":0.2,"eye_height_world":5.0}}"#;
    assert!(parse_manifest(bad).is_err(), "eye_height_world > height_world must be rejected");
}

#[test]
fn loader_rejects_rect_exceeding_atlas() {
    // rect x+w = 5+8 = 13 > atlas width 10 -> the engine (and the vendored loader) reject.
    let bad = r#"{"camera":{"id":"game_iso_v1"},"variant_class":"probe","direction_count":1,
        "frame_canvas":[10,10],"atlases":{"color":{"path":"c.png","size":[10,10]}},
        "frames":[{"direction":0,"rect":[5,0,8,8],"anchor":[5,9]}]}"#;
    assert!(parse_manifest(bad).is_err(), "a rect exceeding the atlas must be rejected");
}

#[test]
fn loader_rejects_zero_size_atlas() {
    let bad = r#"{"camera":{"id":"game_iso_v1"},"variant_class":"probe","direction_count":1,
        "frame_canvas":[10,10],"atlases":{"color":{"path":"c.png","size":[0,0]}},
        "frames":[{"direction":0,"rect":[0,0,8,8],"anchor":[5,9]}]}"#;
    assert!(parse_manifest(bad).is_err(), "a zero-size atlas must be rejected");
}

#[test]
fn reference_multistate_character_is_engine_loadable() {
    // R5: the multi-state, tight-cropped character loads; the loader validates full
    // (state,direction,frame_index) coverage and builds the DEFAULT state's frame 0 per dir.
    let json = manifest("../reference/humanoid_anim/manifest.json");
    let s = parse_manifest(&json).expect("engine must accept the multi-state character");
    assert_eq!(s.variant.directions, 16);
    assert_eq!(s.variant.frames.len(), 16, "default-state frame 0 per direction");
    assert_eq!(s.variant.default_state, "idle");
    assert_eq!(s.variant.states, vec!["attack".to_string(), "idle".to_string(), "walk".to_string()]);
    assert_eq!(s.variant.animations["walk"].frames, 4);
    assert_eq!(s.variant.animations["attack"].playback, "once");
    assert!(s.variant.metrics.eye_height_world.unwrap() <= s.variant.metrics.height_world);
}

#[test]
fn multistate_tightcrop_sizing_reconstructs() {
    // R5 review: the loader carries trim + logical_frame_canvas and reproduces the contract
    // section-3 tight-crop sizing (NOT the rect-aspect mis-size of height*24).
    let json = manifest("../reference/humanoid_anim/manifest.json");
    let s = parse_manifest(&json).expect("multi-state loads");
    let fd = s.variant.frame("walk", 0, 0).expect("walk dir0 f0 in the full atlas");
    let h = s.variant.metrics.height_world;
    let scale = h * 24.0 / fd.logical_h as f32;
    let (w, ht, ox, oy) = fd.screen_placement(h);
    assert!((ht - fd.h as f32 * scale).abs() < 1e-3, "on-screen height = rect.h * scale");
    assert!((w - fd.w as f32 * scale).abs() < 1e-3, "on-screen width = rect.w * scale");
    assert!((ox - fd.trim_x as f32 * scale).abs() < 1e-3 && (oy - fd.trim_y as f32 * scale).abs() < 1e-3);
    assert!(fd.h < fd.logical_h, "frame is tight-cropped (tight rect < logical cell)");
    assert!(ht < h * 24.0, "tight-crop size is below the full logical-cell height (no rect-aspect mis-size)");
    assert!((0.0..=1.0).contains(&fd.anchor_x) && (0.0..=1.0).contains(&fd.anchor_y));
}

#[test]
fn loader_rejects_multistate_coverage_gap() {
    // walk declares 2 frames/direction but only frame_index 0 is supplied -> reject.
    let bad = r#"{"camera":{"id":"game_iso_v1"},"variant_class":"character","direction_count":1,
        "frame_canvas":[10,10],"atlases":{"color":{"path":"c.png","size":[100,100]}},
        "default_state":"walk","animations":{"walk":{"directions":1,"frames":2,"playback":"loop"}},
        "world_metrics":{"height_world":1.0,"footprint_radius_world":0.2},
        "frames":[{"state":"walk","direction":0,"frame_index":0,"rect":[0,0,8,8],"anchor":[5,9]}]}"#;
    assert!(parse_manifest(bad).is_err(), "incomplete frame_index coverage must be rejected");
}

#[test]
fn loader_rejects_anim_direction_mismatch() {
    // animations.idle.directions (2) != direction_count (1) -> reject.
    let bad = r#"{"camera":{"id":"game_iso_v1"},"variant_class":"character","direction_count":1,
        "frame_canvas":[10,10],"atlases":{"color":{"path":"c.png","size":[100,100]}},
        "animations":{"idle":{"directions":2,"frames":1,"playback":"loop"}},
        "world_metrics":{"height_world":1.0,"footprint_radius_world":0.2},
        "frames":[{"state":"idle","direction":0,"frame_index":0,"rect":[0,0,8,8],"anchor":[5,9]}]}"#;
    assert!(parse_manifest(bad).is_err(), "animations.directions != direction_count must be rejected");
}
