//! Direction-bin helpers for the sprite manifest contract.
//!
//! Contract convention:
//! - world yaw 0 = +X / East
//! - positive yaw is CCW toward +Y
//! - 16 bins, lower-edge render convention
//! - reduced N collapses from bin16 by integer division

pub const TAU: f32 = std::f32::consts::PI * 2.0;

pub fn direction_bin16(mut angle_rad: f32) -> usize {
    angle_rad = angle_rad.rem_euclid(TAU);
    let bin = (angle_rad / (TAU / 16.0)).floor() as usize;
    bin.min(15)
}

pub fn collapse_bin16(bin16: usize, direction_count: usize) -> usize {
    assert!(matches!(direction_count, 1 | 2 | 4 | 8 | 16));
    assert!(bin16 < 16);
    bin16 / (16 / direction_count)
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
    fn lower_edge_bins() {
        assert_eq!(direction_bin16(0.0), 0);
        assert_eq!(direction_bin16(TAU / 16.0), 1);
        assert_eq!(direction_bin16(TAU - 0.0001), 15);
    }

    #[test]
    fn collapse_to_8() {
        assert_eq!(collapse_bin16(0, 8), 0);
        assert_eq!(collapse_bin16(1, 8), 0);
        assert_eq!(collapse_bin16(2, 8), 1);
        assert_eq!(collapse_bin16(15, 8), 7);
    }
}
