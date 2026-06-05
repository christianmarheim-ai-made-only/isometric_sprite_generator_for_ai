//! Engine-faithful reference for the `game_iso_v1` sprite manifest.
//!
//! - [`loader`] mirrors the engine's `crates/client_bevy/src/sprite.rs::parse_manifest`
//!   accept/reject (the R6 CI load-test target): it parses the minimal subset the engine
//!   consumes and ignores unknown fields (serde forward-compat).
//! - [`direction`] mirrors the round-to-nearest facing binning (`direction_index`).
//!
//! The richer `manifest_types.rs` / `hit_test.rs` snippets in this directory are
//! reference-only and intentionally NOT part of this crate's build.
pub mod direction;
pub mod loader;
