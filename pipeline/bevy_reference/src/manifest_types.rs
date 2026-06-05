//! Serde-compatible manifest types for the M1/M2 debug subset.
//! Copy/adapt into the engine repo and pin to your Bevy version.

use std::collections::HashMap;

use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct SpriteManifest {
    pub manifest_version: String,
    pub contract_hash: String,
    pub state_contract_version: String,
    pub variant_id: String,
    pub variant_class: String,
    pub frame_canvas: [u32; 2],
    pub direction_count: u32,
    pub animations: HashMap<String, AnimationSpec>,
    pub atlases: Atlases,
    pub frames: Vec<FrameSpec>,
    pub world_metrics: WorldMetrics,
}

#[derive(Debug, Deserialize)]
pub struct AnimationSpec {
    pub playback: String,
    pub directions: u32,
    pub frames: u32,
    pub fps: f32,
    #[serde(default)]
    pub markers: Vec<MarkerSpec>,
}

#[derive(Debug, Deserialize)]
pub struct MarkerSpec {
    pub name: String,
    pub frame: u32,
    pub socket: String,
}

#[derive(Debug, Deserialize)]
pub struct Atlases {
    pub color: AtlasSpec,
    pub hitmask: AtlasSpec,
}

#[derive(Debug, Deserialize)]
pub struct AtlasSpec {
    pub path: String,
    pub size: [u32; 2],
    pub format: String,
    pub sampling: String,
}

#[derive(Debug, Deserialize)]
pub struct FrameSpec {
    pub state: String,
    pub direction: u32,
    pub frame_index: u32,
    pub world_yaw_degrees: f32,
    pub rect: [u32; 4],
    pub mask_rect: [u32; 4],
    pub anchor: [f32; 2],
    pub sockets: HashMap<String, [f32; 2]>,
    pub boxes: HashMap<String, [u32; 4]>,
}

#[derive(Debug, Deserialize)]
pub struct WorldMetrics {
    pub height_world: f32,
    pub footprint_radius_world: f32,
    pub eye_height_world: Option<f32>,
}

impl SpriteManifest {
    pub fn frame(&self, state: &str, direction: u32, frame_index: u32) -> Option<&FrameSpec> {
        self.frames.iter().find(|f| f.state == state && f.direction == direction && f.frame_index == frame_index)
    }

    /// Fail closed on stale or mismatched assets.
    ///
    /// `expected_contract_hash` is the hash of the engine's `sprite_contract.lock.json`
    /// alone (the contract seam). State and variant compatibility are checked separately
    /// via `state_contract_version` and the validator's per-variant cross-check, so adding
    /// a variant does not change the hash or reject existing assets.
    pub fn critical_runtime_asserts(&self, expected_contract_hash: &str, expected_state_contract_version: &str) -> Result<(), String> {
        if self.contract_hash != expected_contract_hash {
            return Err(format!("contract_hash mismatch: asset={} engine={}", self.contract_hash, expected_contract_hash));
        }
        if self.state_contract_version != expected_state_contract_version {
            return Err(format!("state_contract_version mismatch: asset={} engine={}", self.state_contract_version, expected_state_contract_version));
        }
        if let Some(eye) = self.world_metrics.eye_height_world {
            if eye > self.world_metrics.height_world {
                return Err("eye_height_world > height_world".to_string());
            }
        }
        Ok(())
    }
}
