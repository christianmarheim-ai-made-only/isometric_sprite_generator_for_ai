//! Direction-bin helpers for the sprite manifest contract.
//!
//! Contract convention (mirrors engine `client_bevy/src/sprite.rs::direction_index`
//! and `sprite_contract.lock.json` `facing.runtime_binning`):
//! - world yaw 0 = +X / East
//! - positive yaw is CCW toward +Y
//! - ROUND-to-nearest binning: `i = round(yaw / (TAU/N)) mod N` (bin CENTER, never a
//!   lower edge)
//! - frame `i` renders at yaw `i * TAU/N` (the bin center)

pub const TAU: f32 = std::f32::consts::PI * 2.0;

/// Bin a continuous world facing into one of `direction_count` frame indices.
/// Authoritative round-to-nearest rule, identical to engine `sprite.rs::direction_index`:
/// `i = round(yaw / (TAU/direction_count)) rem_euclid direction_count`, `i = 0` at +X.
pub fn direction_index(angle_rad: f32, direction_count: usize) -> usize {
    debug_assert!(direction_count > 0);
    let step = TAU / direction_count as f32;
    let raw = (angle_rad / step).round() as i64;
    raw.rem_euclid(direction_count as i64) as usize
}

/// 16-bin convenience wrapper (the `direction_count == 16` case of `direction_index`).
pub fn direction_bin16(angle_rad: f32) -> usize {
    direction_index(angle_rad, 16)
}

/// Collapse a 16-bin index to a coarser N. Round-binning is not a clean integer
/// division, so re-bin the source bin's CENTER yaw at the target N (prefer calling
/// `direction_index(yaw, n)` directly on the continuous facing when you have it).
pub fn collapse_bin16(bin16: usize, direction_count: usize) -> usize {
    assert!(matches!(direction_count, 1 | 2 | 4 | 8 | 16));
    assert!(bin16 < 16);
    let center_yaw = bin16 as f32 * (TAU / 16.0);
    direction_index(center_yaw, direction_count)
}

pub fn render_yaw_for_direction(direction: usize, direction_count: usize) -> f32 {
    assert!(matches!(direction_count, 1 | 2 | 4 | 8 | 16));
    assert!(direction < direction_count);
    direction as f32 * TAU / direction_count as f32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rounds_to_nearest_bin_center() {
        let step = TAU / 16.0;
        assert_eq!(direction_bin16(0.0), 0);
        // Just under a full turn rounds back to 0 (NOT 15 — that was the old floor bug).
        assert_eq!(direction_bin16(TAU - 0.0001), 0);
        // Below the half-step stays in the bin; above it snaps to the next.
        assert_eq!(direction_bin16(step * 0.49), 0);
        assert_eq!(direction_bin16(step * 0.51), 1);
        assert_eq!(direction_bin16(step), 1);
    }

    #[test]
    fn collapse_to_8_round() {
        assert_eq!(collapse_bin16(0, 8), 0);
        assert_eq!(collapse_bin16(2, 8), 1); // bin2 center = 45deg -> dir 1 at N=8
        assert_eq!(collapse_bin16(15, 8), 0); // bin15 center = 337.5deg -> rounds to 0 at N=8
    }
}
