//! Engine sprite-manifest LOADER, vendored/extended from the engine
//! `crates/client_bevy/src/sprite.rs::parse_manifest`, reduced to std+serde (no Bevy/sim).
//!
//! Implements BOTH:
//!  - the CURRENT engine single-state contract (one `{direction, rect, anchor}` frame per
//!    direction; `frames.len() == direction_count`), mirroring the shipped `parse_manifest`; AND
//!  - the multi-state + tight-crop contract (docs/multistate_sprite_contract.md): a top-level
//!    `animations` map (frames/fps/playback) + per-frame `(state, frame_index)` + `default_state`,
//!    tight `rect` + `trim` + `logical_frame_canvas`, logical-coords `anchor`. It parses ALL
//!    states + the tight-crop fields, validates coverage, builds the full
//!    `(state, direction, frame_index)` atlas, and exposes the default state's frame 0 per
//!    direction. `FrameDef::screen_placement` is the EXECUTABLE spec for contract section 3
//!    (deterministic tight-crop sizing); the engine slice should reproduce it.
//!
//! Backward-compatible: a manifest with no `animations` loads exactly as the shipped engine.
//! KEEP IN SYNC with the engine.

use std::collections::BTreeMap;

use serde::Deserialize;

pub const FORMAT_ID: &str = "game_iso_v1";
pub const PROBE_DEFAULT_HEIGHT: f32 = 2.0;
pub const PROBE_DEFAULT_FOOTPRINT: f32 = 0.5;
/// On-screen px per world meter of height (engine render.rs HEIGHT_SCREEN_SCALE).
pub const HEIGHT_SCREEN_SCALE: f32 = 24.0;

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
    /// Atlas page this frame's pixels live on (0 for single-page packages).
    pub page: usize,
    /// Tight atlas rect (the actual pixels), LOCAL to `page`.
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
    /// Tight rect's top-left WITHIN the logical (untrimmed) frame.
    pub trim_x: u32,
    pub trim_y: u32,
    /// The untrimmed logical cell (the sizing/anchoring reference).
    pub logical_w: u32,
    pub logical_h: u32,
    /// Foot anchor as a fraction of the LOGICAL frame.
    pub anchor_x: f32,
    pub anchor_y: f32,
}

impl FrameDef {
    /// Contract section-3 deterministic sizing/placement. Returns the on-screen
    /// `(w, h, offset_x, offset_y)` in px for a sprite of `height_world` meters:
    /// `scale = height_world * HEIGHT_SCREEN_SCALE / logical_h`; the tight region is drawn at
    /// `rect.w*scale x rect.h*scale`, offset `trim*scale` from the logical top-left; the logical
    /// anchor (`anchor * logical * scale`) lands on the projected foot. Trimmed padding is implied.
    pub fn screen_placement(&self, height_world: f32) -> (f32, f32, f32, f32) {
        let scale = height_world * HEIGHT_SCREEN_SCALE / self.logical_h as f32;
        (self.w as f32 * scale, self.h as f32 * scale, self.trim_x as f32 * scale, self.trim_y as f32 * scale)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct AnimMeta {
    pub frames: usize,
    pub fps: f32,
    pub playback: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SpriteVariant {
    pub directions: usize,
    /// Atlas pages as (path, w, h). Single-page packages have exactly one; `FrameDef::page`
    /// indexes this list (atlas paging -- docs/atlas_paging_contract.md).
    pub pages: Vec<(String, u32, u32)>,
    /// Page 0 size, for single-page consumers.
    pub atlas_w: u32,
    pub atlas_h: u32,
    /// The DEFAULT state's frame 0, one per direction (MIN render set).
    pub frames: Vec<FrameDef>,
    pub metrics: WorldMetrics,
    pub states: Vec<String>,
    pub default_state: String,
    /// Per-state animation metadata (frames/fps/playback). Single-state -> `{idle: 1, 1, loop}`.
    pub animations: BTreeMap<String, AnimMeta>,
    /// The full atlas, addressed by `(state, direction, frame_index)`.
    pub all_frames: BTreeMap<(String, usize, usize), FrameDef>,
}

impl SpriteVariant {
    pub fn frame(&self, state: &str, direction: usize, frame_index: usize) -> Option<&FrameDef> {
        self.all_frames.get(&(state.to_string(), direction, frame_index))
    }
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
#[derive(Deserialize, Clone)]
struct PageDef {
    path: String,
    size: [u32; 2],
}
#[derive(Deserialize, Clone)]
struct AtlasDef {
    #[serde(default)]
    path: Option<String>,
    #[serde(default)]
    size: Option<[u32; 2]>,
    #[serde(default)]
    pages: Vec<PageDef>,
}
impl AtlasDef {
    /// Resolve to a page list: explicit `pages`, else the single-page `path`+`size` alias.
    fn page_list(&self) -> Result<Vec<PageDef>, String> {
        if !self.pages.is_empty() {
            Ok(self.pages.clone())
        } else if let (Some(p), Some(s)) = (self.path.clone(), self.size) {
            Ok(vec![PageDef { path: p, size: s }])
        } else {
            Err("atlas needs either `pages` or `path`+`size`".to_string())
        }
    }
}
#[derive(Deserialize)]
struct AtlasesDef {
    color: AtlasDef,
    #[serde(default)]
    hitmask: Option<AtlasDef>,
}
#[derive(Deserialize)]
struct FrameEntry {
    direction: usize,
    rect: [u32; 4],
    anchor: [f32; 2],
    #[serde(default)]
    page: usize,
    #[serde(default)]
    mask_rect: Option<[u32; 4]>,
    #[serde(default)]
    state: Option<String>,
    #[serde(default)]
    frame_index: Option<usize>,
    #[serde(default)]
    trim: Option<[u32; 2]>,
    #[serde(default)]
    logical_frame_canvas: Option<[u32; 2]>,
}
#[derive(Deserialize)]
struct AnimDef {
    directions: usize,
    frames: usize,
    #[serde(default)]
    fps: f32,
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

type Built = (Vec<FrameDef>, BTreeMap<(String, usize, usize), FrameDef>, BTreeMap<String, AnimMeta>, Vec<String>, String);

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
    let pages = m.atlases.color.page_list()?;
    for (i, pg) in pages.iter().enumerate() {
        if pg.size[0] == 0 || pg.size[1] == 0 {
            return Err(format!("atlases.color page {i} has a zero dimension"));
        }
    }
    if let Some(hm) = &m.atlases.hitmask {
        let hpages = hm.page_list()?;
        if hpages.len() != pages.len() {
            return Err(format!(
                "atlases.hitmask pages ({}) must equal atlases.color pages ({})",
                hpages.len(), pages.len()
            ));
        }
    }
    for fr in &m.frames {
        let [x, y, w, h] = fr.rect;
        if w == 0 || h == 0 {
            return Err(format!("frame (dir {}) has a zero-size rect", fr.direction));
        }
        let pg = pages.get(fr.page).ok_or_else(|| {
            format!("frame (dir {}) page {} out of range 0..{}", fr.direction, fr.page, pages.len())
        })?;
        let [pw, ph] = pg.size;
        if x as u64 + w as u64 > pw as u64 || y as u64 + h as u64 > ph as u64 {
            return Err(format!(
                "frame (dir {}) rect [{x}, {y}, {w}, {h}] exceeds page {} ({pw}x{ph})",
                fr.direction, fr.page
            ));
        }
        if let Some([_, _, mw, mh]) = fr.mask_rect {
            if mw != w || mh != h {
                return Err(format!(
                    "frame (dir {}) mask_rect {mw}x{mh} must match rect {w}x{h}",
                    fr.direction
                ));
            }
        }
    }
    let aw = pages[0].size[0];
    let ah = pages[0].size[1];
    let atlas_path = pages[0].path.clone();
    let page_list: Vec<(String, u32, u32)> =
        pages.iter().map(|p| (p.path.clone(), p.size[0], p.size[1])).collect();

    let [lw0, lh0] = m.logical_frame_canvas.unwrap_or(m.frame_canvas);

    let (frames, all_frames, animations, states, default_state) = match &m.animations {
        Some(anims) if !anims.is_empty() => build_multistate(&m, anims, dc, lw0, lh0)?,
        _ => build_single(&m, dc, lw0, lh0)?,
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
        variant: SpriteVariant {
            directions: dc,
            pages: page_list,
            atlas_w: aw,
            atlas_h: ah,
            frames,
            metrics,
            states,
            default_state,
            animations,
            all_frames,
        },
        atlas: atlas_path,
        name: m.variant_id,
    })
}

/// Legacy single-state: exactly one frame per direction (the shipped engine rule).
fn build_single(m: &ManifestDef, dc: usize, lw0: u32, lh0: u32) -> Result<Built, String> {
    if m.frames.len() != dc {
        return Err(format!("frames ({}) must equal direction_count ({dc})", m.frames.len()));
    }
    let mut slots: Vec<Option<FrameDef>> = vec![None; dc];
    let mut all: BTreeMap<(String, usize, usize), FrameDef> = BTreeMap::new();
    for fr in &m.frames {
        if fr.direction >= dc {
            return Err(format!("frame.direction {} out of range 0..{dc}", fr.direction));
        }
        if slots[fr.direction].is_some() {
            return Err(format!("duplicate frame for direction {}", fr.direction));
        }
        let fd = frame_def(fr, lw0, lh0);
        slots[fr.direction] = Some(fd);
        all.insert(("idle".to_string(), fr.direction, 0), fd);
    }
    let frames: Vec<FrameDef> = slots
        .into_iter()
        .enumerate()
        .map(|(i, f)| f.ok_or_else(|| format!("missing frame for direction {i}")))
        .collect::<Result<_, _>>()?;
    let mut animations = BTreeMap::new();
    animations.insert("idle".to_string(), AnimMeta { frames: 1, fps: 1.0, playback: "loop".to_string() });
    Ok((frames, all, animations, vec!["idle".to_string()], "idle".to_string()))
}

/// Multi-state contract: validate full coverage, build the full atlas, return the default
/// state's frame 0 per direction + animation metadata.
fn build_multistate(m: &ManifestDef, anims: &BTreeMap<String, AnimDef>, dc: usize, lw0: u32, lh0: u32) -> Result<Built, String> {
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

    let mut covered: BTreeMap<(&str, usize), Vec<bool>> = BTreeMap::new();
    for (state, a) in anims {
        for d in 0..dc {
            covered.insert((state.as_str(), d), vec![false; a.frames]);
        }
    }
    let mut default_frames: Vec<Option<FrameDef>> = vec![None; dc];
    let mut all: BTreeMap<(String, usize, usize), FrameDef> = BTreeMap::new();
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
        let fd = frame_def(fr, lw0, lh0);
        all.insert((state.to_string(), fr.direction, fi), fd);
        if state == default_state && fi == 0 {
            default_frames[fr.direction] = Some(fd);
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
    let animations: BTreeMap<String, AnimMeta> = anims
        .iter()
        .map(|(s, a)| (s.clone(), AnimMeta { frames: a.frames, fps: a.fps, playback: a.playback.clone() }))
        .collect();
    Ok((frames, all, animations, anims.keys().cloned().collect(), default_state))
}

fn frame_def(fr: &FrameEntry, lw0: u32, lh0: u32) -> FrameDef {
    let [x, y, w, h] = fr.rect;
    let [tx, ty] = fr.trim.unwrap_or([0, 0]);
    let [lw, lh] = fr.logical_frame_canvas.unwrap_or([lw0, lh0]);
    FrameDef {
        direction: fr.direction,
        page: fr.page,
        x,
        y,
        w,
        h,
        trim_x: tx,
        trim_y: ty,
        logical_w: lw,
        logical_h: lh,
        anchor_x: fr.anchor[0] / lw as f32,
        anchor_y: fr.anchor[1] / lh as f32,
    }
}
