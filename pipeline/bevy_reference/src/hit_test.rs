//! Coordinate helpers for manifest-driven sprites.
//!
//! Manifest frame coordinates are top-left origin and +Y down.
//! Runtime screen offsets for hit tests must include render scale:
//!     frame_pixel = screen_offset / render_scale + anchor

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RectPx {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Vec2Px {
    pub x: f32,
    pub y: f32,
}

/// Convert a frame-local top-left/+Y-down anchor into Bevy's normalized custom anchor.
///
/// Bevy convention assumed here:
/// - center = (0, 0)
/// - bottom-left = (-0.5, -0.5)
/// - top-right = (0.5, 0.5)
pub fn bevy_custom_anchor_from_frame(anchor: Vec2Px, frame_w: f32, frame_h: f32) -> (f32, f32) {
    (anchor.x / frame_w - 0.5, 0.5 - anchor.y / frame_h)
}

/// Convert a screen-space offset from the rendered anchor to frame-local pixel coordinates.
///
/// `screen_offset` should be in screen pixels, with +Y down if using UI/screen coordinates.
/// If your engine gives +Y-up world-space deltas, flip Y before calling this.
pub fn frame_pixel_from_screen_offset(screen_offset: Vec2Px, anchor: Vec2Px, render_scale: f32) -> Option<(u32, u32)> {
    if render_scale <= 0.0 {
        return None;
    }
    let fx = screen_offset.x / render_scale + anchor.x;
    let fy = screen_offset.y / render_scale + anchor.y;
    if fx < 0.0 || fy < 0.0 {
        return None;
    }
    Some((fx.floor() as u32, fy.floor() as u32))
}

/// Sample an R8 hitmask atlas at frame-local coordinates.
pub fn hit_region_at(mask_bytes: &[u8], atlas_width: u32, atlas_height: u32, rect: RectPx, frame_x: u32, frame_y: u32) -> Option<u8> {
    if frame_x >= rect.w || frame_y >= rect.h {
        return None;
    }
    let atlas_x = rect.x + frame_x;
    let atlas_y = rect.y + frame_y;
    if atlas_x >= atlas_width || atlas_y >= atlas_height {
        return None;
    }
    let idx = (atlas_y * atlas_width + atlas_x) as usize;
    mask_bytes.get(idx).copied()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn anchor_conversion_bottom_centerish() {
        let anchor = Vec2Px { x: 64.0, y: 112.0 };
        let (x, y) = bevy_custom_anchor_from_frame(anchor, 128.0, 128.0);
        assert!((x - 0.0).abs() < 0.0001);
        assert!((y - (-0.375)).abs() < 0.0001);
    }

    #[test]
    fn screen_to_frame_includes_scale() {
        let anchor = Vec2Px { x: 64.0, y: 112.0 };
        let p = frame_pixel_from_screen_offset(Vec2Px { x: 20.0, y: -20.0 }, anchor, 2.0).unwrap();
        assert_eq!(p, (74, 102));
    }
}
