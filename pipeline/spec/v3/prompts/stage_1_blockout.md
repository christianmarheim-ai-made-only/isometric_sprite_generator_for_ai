# Stage 1 — Block out the body (scale / forward / origin)

## PROMPT

Block out the creature's body as a single rough mesh in **metres**. Get the three things the baker
cannot fix for you exactly right: **scale**, **forward**, and **origin**. Detail comes later — this
stage is about the model sitting correctly in world space (ADR-0035).

Author to these axes and the origin convention:

- **Up = +Z. Forward = +X** (= direction 0). The creature faces +X.
- **Origin = the ground-footprint centre.** The lowest foot/contact verts sit at **z = 0**; the model
  is centred over the origin in X/Y (so `footprint_radius_world ≈ max(|x|, |y|)` of the ground-band
  verts). The baker measures height as `z.max()` and footprint from the ground band
  (`z ≤ zmin + 0.15·height`, `GROUND_BAND`) — author so those measurements come out at your target.
- **Scale in real metres.** A biped fighter ≈ 1.8 m tall. If you build the calibration biped, height
  is **exactly 1.80 m**, footprint radius **0.40 m** (calib_dragon: 2.128 m / 1.55 m). Declare
  `world_metrics.height_world` to match the mesh; a >25% gap between declared and measured height
  trips `world_metrics_mismatch` at bake.
- If you author facing a different axis, set `geometry.forward` (`+x|-x|+y|-y`) — the baker rotates the
  declared forward onto +X via `forward_yaw()`. It is a LIVE correction, so it must be correct, not
  decorative. Forward is a ground-plane heading; `+z/-z` are not valid.
- **Front must differ from back.** A combat creature is not radially symmetric — give it a clear face /
  chest so the front≠back distinctness gate passes (only `ball`/radial props are exempt).
- **Stay upright.** A biped silhouette must be **portrait** (taller than wide) in nearly every
  direction. A landscape silhouette means it baked lying down / wrong up-axis.

## CONSTRAINTS

- Units = metres, `unit: meter`. No arbitrary scale; the engine reads real-world size.
- Do not bake yet; this is geometry + the `geometry`/`world_metrics` manifest fields only.

## GATES THIS STAGE MUST PASS

- `forward_axis` (code `forward_axis_mismatch`, error) — the baked forward must land on +X.
- `ground_origin` (code `ground_origin_mismatch`, error) — foot at z=0, origin at footprint centre.
- `scale` (code `world_metrics_mismatch`, error) — declared vs measured height within 25%.
- `upright` (code `non_upright_biped`, warn) — biped silhouette stays portrait, not lying down.
- `front_back_distinctness` (code `front_back_indistinct`, error) — front ≠ back (non-radial).

## DONE WHEN

The block-out mesh stands at the origin, foot on z=0, facing +X, at the target height in metres; a
quick `hitbox_from_mesh.py` read on a proxy `.obj` returns the intended `height_world` /
`footprint_radius_world`, and the silhouette is portrait and front-distinct.
