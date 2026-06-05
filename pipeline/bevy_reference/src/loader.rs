//! Engine sprite-manifest LOADER, vendored/extended from the engine
//! `crates/client_bevy/src/sprite.rs::parse_manifest`, reduced to std+serde (no Bevy/sim).
//!
//! Implements BOTH:
//!  - the CURRENT engine single-state contract (one `{direction, rect, anchor}` frame per
//!    direction; `frames.len() == direction_count`), mirroring the shipped `parse_manifest`; AND
//!  - the multi-state + tight-crop contract (multistate_sprite_contract.md): a top-level
//!    `animations` map + per-frame `(state, frame_index)` + `default_state`, tight `rect` +
//!    `trim` + `logical_frame_canvas`, logical-coords `anchor`. MIN engine behavior: validate
//!    coverage and load the DEFAULT state's frame 0 per direction.
//!
//! Backward-compatible: a manifest with no `animations` loads exactly as the shipped engine
//! does. The multi-state half is the reference for the pending engine loader slice; the
//! single-state half mirrors the shipped engine. KEEP IN SYNC with the engine.

use std::collections::BTreeMap;

use serde::Deserialize;

pub const FORMAT_ID: &str = "game_iso_v1";
pub const PROBE_DEFAULT_HEIGHT: f32 = 2.0;
pub const PROBE_DEFAULT_FOOTPRINT: f32 = 0.5;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct WorldMetrics {
    pub height_world: f32,
    pub footprint_radius_world: f32,
    pub eye_height_world: Option<f32>,
}

impl WorldMetrics {
    pub fn validate(&self) -> Result<(), String> {
        if !(self.height_world > 0.0) {
            return Err(format!("height_world must be > 0 (got {})", self.height_world));
        }
        if !(self.footprint_radius_world > 0.0) {
            return Err(format!("footprint_radius_world must be > 0 (got {})", self.footprint_radius_world));
        }
        if let Some(eye) = self.eye_height_world {
            if !(eye > 0.0) {
                return Err(format!("eye_height_world must be > 0 (got {eye})"));
            }
            if eye > self.height_world {
                return Err(format!("eye_height_world ({eye}) must be <= height_world ({})", self.height_world));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FrameDef {
    pub direction: usize,
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
    pub anchor_x: f32,
    pub anchor_y: f32,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SpriteVariant {
    pub directions: usize,
    pub atlas_w: u32,
    pub atlas_h: u32,
    /// The DEFAULT state's frame 0, one per direction (MIN engine behavior).
    pub frames: Vec<FrameDef>,
    pub metrics: WorldMetrics,
    /// All animation state names (sorted). A single-state manifest yields `["idle"]`.
    pub states: Vec<String>,
    pub default_state: String,
}

pub struct LoadedSprite {
    pub variant: SpriteVariant,
    pub atlas: String,
    pub name: String,
}

#[derive(Deserialize)]
struct CameraDef {
    id: String,
}
#[derive(Deserialize)]
struct ColorAtlasDef {
    path: String,
    size: [u32; 2],
}
#[derive(Deserialize)]
struct AtlasesDef {
    color: ColorAtlasDef,
}
#[derive(Deserialize)]
struct FrameEntry {
    direction: usize,
    rect: [u32; 4],
    anchor: [f32; 2],
    #[serde(default)]
    state: Option<String>,
    #[serde(default)]
    frame_index: Option<usize>,
}
#[derive(Deserialize)]
struct AnimDef {
    directions: usize,
    frames: usize,
    #[serde(default)]
    playback: String,
}
#[derive(Deserialize)]
struct WorldMetricsDef {
    height_world: f32,
    footprint_radius_world: f32,
    #[serde(default)]
    eye_height_world: Option<f32>,
}
#[derive(Deserialize)]
struct ManifestDef {
    camera: CameraDef,
    #[serde(default)]
    variant_id: String,
    #[serde(default)]
    variant_class: String,
    direction_count: usize,
    frame_canvas: [u32; 2],
    atlases: AtlasesDef,
    frames: Vec<FrameEntry>,
    #[serde(default)]
    world_metrics: Option<WorldMetricsDef>,
    #[serde(default)]
    animations: Option<BTreeMap<String, AnimDef>>,
    #[serde(default)]
    default_state: Option<String>,
    #[serde(default)]
    logical_frame_canvas: Option<[u32; 2]>,
}

/// Parse + validate a `game_iso_v1` manifest (single-state or multi-state).
pub fn parse_manifest(json: &str) -> Result<LoadedSprite, String> {
    let m: ManifestDef = serde_json::from_str(json).map_err(|e| format!("manifest JSON: {e}"))?;
    if m.camera.id != FORMAT_ID {
        return Err(format!("camera.id must be \"{FORMAT_ID}\" (got \"{}\")", m.camera.id));
    }
    let dc = m.direction_count;
    if dc == 0 {
        return Err("direction_count must be > 0".to_string());
    }
    let [fcw, fch] = m.frame_canvas;
    if fcw == 0 || fch == 0 {
        return Err("frame_canvas dimensions must be > 0".to_string());
    }
    let [aw, ah] = m.atlases.color.size;
    if aw == 0 || ah == 0 {
        return Err("atlases.color.size dimensions must be > 0".to_string());
    }
    // Every frame's rect: nonzero + within the atlas (u64 avoids overflow on a hostile rect).
    for fr in &m.frames {
        let [x, y, w, h] = fr.rect;
        if w == 0 || h == 0 {
            return Err(format!("frame (dir {}) has a zero-size rect", fr.direction));
        }
        if x as u64 + w as u64 > aw as u64 || y as u64 + h as u64 > ah as u64 {
            return Err(format!("frame (dir {}) rect [{x}, {y}, {w}, {h}] exceeds the atlas {aw}x{ah}", fr.direction));
        }
    }

    // Anchor is expressed in LOGICAL frame coordinates (== frame_canvas when uncropped).
    let [lw, lh] = m.logical_frame_canvas.unwrap_or(m.frame_canvas);
    let (lw, lh) = (lw as f32, lh as f32);

    let (frames, states, default_state) = match &m.animations {
        Some(anims) if !anims.is_empty() => build_multistate(&m, anims, dc, lw, lh)?,
        _ => (build_single(&m, dc, lw, lh)?, vec!["idle".to_string()], "idle".to_string()),
    };

    let metrics = if m.variant_class == "probe" {
        WorldMetrics {
            height_world: PROBE_DEFAULT_HEIGHT,
            footprint_radius_world: PROBE_DEFAULT_FOOTPRINT,
            eye_height_world: None,
        }
    } else {
        match &m.world_metrics {
            Some(w) => {
                let metrics = WorldMetrics {
                    height_world: w.height_world,
                    footprint_radius_world: w.footprint_radius_world,
                    eye_height_world: w.eye_height_world,
                };
                metrics.validate()?;
                metrics
            }
            None => {
                return Err(format!(
                    "world_metrics is required for variant_class \"{}\" (only \"probe\" may placeholder it)",
                    m.variant_class
                ));
            }
        }
    };

    Ok(LoadedSprite {
        variant: SpriteVariant { directions: dc, atlas_w: aw, atlas_h: ah, frames, metrics, states, default_state },
        atlas: m.atlases.color.path,
        name: m.variant_id,
    })
}

/// Legacy single-state: exactly one frame per direction (the shipped engine rule).
fn build_single(m: &ManifestDef, dc: usize, lw: f32, lh: f32) -> Result<Vec<FrameDef>, String> {
    if m.frames.len() != dc {
        return Err(format!("frames ({}) must equal direction_count ({dc})", m.frames.len()));
    }
    let mut slots: Vec<Option<FrameDef>> = vec![None; dc];
    for fr in &m.frames {
        if fr.direction >= dc {
            return Err(format!("frame.direction {} out of range 0..{dc}", fr.direction));
        }
        if slots[fr.direction].is_some() {
            return Err(format!("duplicate frame for direction {}", fr.direction));
        }
        slots[fr.direction] = Some(frame_def(fr, lw, lh));
    }
    slots.into_iter().enumerate().map(|(i, f)| f.ok_or_else(|| format!("missing frame for direction {i}"))).collect()
}

/// Multi-state contract: validate full `(state, direction, frame_index)` coverage and return
/// the default state's frame 0 per direction.
fn build_multistate(
    m: &ManifestDef,
    anims: &BTreeMap<String, AnimDef>,
    dc: usize,
    lw: f32,
    lh: f32,
) -> Result<(Vec<FrameDef>, Vec<String>, String), String> {
    for (state, a) in anims {
        if a.directions != dc {
            return Err(format!("animations.{state}.directions ({}) must equal direction_count ({dc})", a.directions));
        }
        if a.frames == 0 {
            return Err(format!("animations.{state}.frames must be > 0"));
        }
        if !matches!(a.playback.as_str(), "loop" | "once" | "hold") {
            return Err(format!("animations.{state}.playback must be loop|once|hold (got {:?})", a.playback));
        }
    }
    let default_state = match &m.default_state {
        Some(ds) => {
            if !anims.contains_key(ds) {
                return Err(format!("default_state {ds:?} is not an animations key"));
            }
            ds.clone()
        }
        None => {
            if anims.contains_key("idle") {
                "idle".to_string()
            } else {
                anims.keys().next().expect("non-empty animations").clone()
            }
        }
    };

    // coverage[(state, direction)] = bitset over frame_index 0..frames-1
    let mut covered: BTreeMap<(&str, usize), Vec<bool>> = BTreeMap::new();
    for (state, a) in anims {
        for d in 0..dc {
            covered.insert((state.as_str(), d), vec![false; a.frames]);
        }
    }
    let mut default_frames: Vec<Option<FrameDef>> = vec![None; dc];
    for fr in &m.frames {
        let state = fr.state.as_deref().ok_or("multi-state frame missing `state`")?;
        let a = anims.get(state).ok_or_else(|| format!("frame references unknown state {state:?}"))?;
        let fi = fr.frame_index.ok_or_else(|| format!("frame ({state}) missing `frame_index`"))?;
        if fr.direction >= dc {
            return Err(format!("frame ({state}) direction {} out of range 0..{dc}", fr.direction));
        }
        if fi >= a.frames {
            return Err(format!("frame ({state}, dir {}) frame_index {fi} out of range 0..{}", fr.direction, a.frames));
        }
        let slot = covered.get_mut(&(state, fr.direction)).expect("seeded");
        if slot[fi] {
            return Err(format!("duplicate frame ({state}, dir {}, f{fi})", fr.direction));
        }
        slot[fi] = true;
        if state == default_state && fi == 0 {
            default_frames[fr.direction] = Some(frame_def(fr, lw, lh));
        }
    }
    for ((state, d), got) in &covered {
        if got.iter().any(|b| !b) {
            return Err(format!("state {state:?} dir {d}: incomplete frame_index coverage"));
        }
    }
    let frames: Vec<FrameDef> = default_frames
        .into_iter()
        .enumerate()
        .map(|(d, f)| f.ok_or_else(|| format!("missing default-state \"{default_state}\" frame 0 for direction {d}")))
        .collect::<Result<_, _>>()?;
    Ok((frames, anims.keys().cloned().collect(), default_state))
}

fn frame_def(fr: &FrameEntry, lw: f32, lh: f32) -> FrameDef {
    let [x, y, w, h] = fr.rect;
    FrameDef { direction: fr.direction, x, y, w, h, anchor_x: fr.anchor[0] / lw, anchor_y: fr.anchor[1] / lh }
}
