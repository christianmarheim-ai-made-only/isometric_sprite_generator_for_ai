//! Engine sprite-manifest LOADER, vendored from the engine's
//! `crates/client_bevy/src/sprite.rs::parse_manifest` (the parse path only), reduced to
//! the `std` + `serde` subset (no Bevy, no `sim`) so the pipeline can run the REAL engine
//! accept/reject logic in CI. KEEP IN SYNC with the engine `parse_manifest`.
//!
//! The engine consumes a minimal subset (camera.id, direction_count, frame_canvas,
//! atlases.color, one `{direction, rect, anchor}` frame per direction, world_metrics) and
//! ignores every other field, so this accepts both the minimal bake manifest and the rich
//! arrow-pilot manifest. NOTE the load-bearing constraint: `frames.len() == direction_count`
//! (one frame per direction) — there is no multi-state/animation support in the loader yet.

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
            return Err(format!(
                "footprint_radius_world must be > 0 (got {})",
                self.footprint_radius_world
            ));
        }
        if let Some(eye) = self.eye_height_world {
            if !(eye > 0.0) {
                return Err(format!("eye_height_world must be > 0 (got {eye})"));
            }
            if eye > self.height_world {
                return Err(format!(
                    "eye_height_world ({eye}) must be <= height_world ({})",
                    self.height_world
                ));
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
    pub frames: Vec<FrameDef>,
    pub metrics: WorldMetrics,
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
}

/// Parse + validate a `game_iso_v1` manifest exactly as the engine loader does.
pub fn parse_manifest(json: &str) -> Result<LoadedSprite, String> {
    let m: ManifestDef = serde_json::from_str(json).map_err(|e| format!("manifest JSON: {e}"))?;
    if m.camera.id != FORMAT_ID {
        return Err(format!("camera.id must be \"{FORMAT_ID}\" (got \"{}\")", m.camera.id));
    }
    if m.direction_count == 0 {
        return Err("direction_count must be > 0".to_string());
    }
    let [fcw, fch] = m.frame_canvas;
    if fcw == 0 || fch == 0 {
        return Err("frame_canvas dimensions must be > 0".to_string());
    }
    if m.frames.len() != m.direction_count {
        return Err(format!(
            "frames ({}) must equal direction_count ({})",
            m.frames.len(),
            m.direction_count
        ));
    }
    let mut slots: Vec<Option<FrameDef>> = vec![None; m.direction_count];
    for fr in &m.frames {
        if fr.direction >= m.direction_count {
            return Err(format!(
                "frame.direction {} out of range 0..{}",
                fr.direction, m.direction_count
            ));
        }
        let [x, y, w, h] = fr.rect;
        if w == 0 || h == 0 {
            return Err(format!("frame {} has a zero-size rect", fr.direction));
        }
        if slots[fr.direction].is_some() {
            return Err(format!("duplicate frame for direction {}", fr.direction));
        }
        slots[fr.direction] = Some(FrameDef {
            direction: fr.direction,
            x,
            y,
            w,
            h,
            anchor_x: fr.anchor[0] / fcw as f32,
            anchor_y: fr.anchor[1] / fch as f32,
        });
    }
    let frames: Vec<FrameDef> = slots
        .into_iter()
        .enumerate()
        .map(|(i, f)| f.ok_or_else(|| format!("missing frame for direction {i}")))
        .collect::<Result<_, _>>()?;

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

    let [aw, ah] = m.atlases.color.size;
    Ok(LoadedSprite {
        variant: SpriteVariant {
            directions: m.direction_count,
            atlas_w: aw,
            atlas_h: ah,
            frames,
            metrics,
        },
        atlas: m.atlases.color.path,
        name: m.variant_id,
    })
}
