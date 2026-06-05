# World Metrics Policy (C4)

`world_metrics` are the body-scale numbers the engine uses for collision, fog of
war (FOW), and line of sight (LOS). **Body-only** by decision (ADR-0007): held
equipment and VFX never inflate them.

## Fields (meters)

| Field | Required | Meaning |
|---|---|---|
| `height_world` | yes, > 0 | top of the body above the ground plane |
| `footprint_radius_world` | yes, > 0 | horizontal footprint radius from the origin |
| `eye_height_world` | optional, > 0, ≤ height | head/eye height for the LOS/FOW eye point |

## Source

- Measured from the `METRIC_body` proxy axis-aligned bounds (+Z up, ground at
  z = 0, origin at the footprint center), plus an optional head/eye socket/bone Z.
- `pipeline/tools/measure_metrics.py` does the pure computation; the Blender
  exporter supplies the proxy bbox and eye Z.

## Body-only rule (ADR-0007)

**Excluded** from `METRIC_body`, and therefore from these metrics: held weapons,
shields, loose gear, backpacks, capes, and all VFX (flames, muzzle flashes,
particles). This stops pikes/shields/capes from acting like collision or LOS
walls and keeps character scale stable across equipment variants.

**Visual / equipment bounds** (full silhouette, weapon reach, shield extent) may
be reported *separately* as optional metadata (`visual_bounds_world`,
`equipment_bounds_world`) for targeting/cover previews — but the engine uses
`world_metrics` for body collision, FOW, and LOS defaults, never the visual
bounds.

## Eye height

- Emitted **only** when a head/eye bone/socket exists; otherwise **omitted**
  (never emitted as zero — the engine applies its own default).
- Must satisfy `eye_height_world ≤ height_world` (validator + runtime assert).

## Units

Meters; `1 unit = 1 meter` (contract). All metrics strictly positive.

## Arrow pilot (M1/M2)

The arrow pilot emits tiny positive **placeholders** (`height_world = 0.1`,
`footprint_radius_world = 0.25`, no eye) flagged
`debug_placeholder_only_not_gameplay` — plumbing only (ADR-0015). Real per-variant
metrics are measured at M3.

## Enforcement

The validator checks positivity and `eye ≤ height`; the humanoid source linter
(P5) checks that the metric proxy exists and that equipment is excluded from it.
