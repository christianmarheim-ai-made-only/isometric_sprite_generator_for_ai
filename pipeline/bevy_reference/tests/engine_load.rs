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
