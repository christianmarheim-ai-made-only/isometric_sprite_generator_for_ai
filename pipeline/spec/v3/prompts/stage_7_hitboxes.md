# Stage 7 — Author the region_hitboxes sidecar

## PROMPT

Author the **explicit authoritative region map**: `<variant_id>_hitbox.json`, a sibling of the asset
manifest. This is a required combat-creature deliverable. It declares per-region **world-space AABBs**
that the bake projects through the locked camera (per direction) to label the R8 hitmask
(explicit-hitbox region baking, ADR-0036) and to keep `region_fallback_torso` a visible warn (not a
silent default) for a single-material art model.

Write this exact shape (the bake reads top-level `region_hitboxes`; each box is `min`/`max` in metres):

```json
{
  "asset_id": "<variant_id>",
  "region_hitboxes": {
    "head":  { "min": [x, y, z], "max": [x, y, z] },
    "torso": { "min": [x, y, z], "max": [x, y, z] },
    "arm_left":  { "min": [x, y, z], "max": [x, y, z] },
    "arm_right": { "min": [x, y, z], "max": [x, y, z] },
    "legs":  { "min": [x, y, z], "max": [x, y, z] }
  }
}
```

Rules:

- **≥ 2 regions** with valid `min`/`max` lists (3 numbers each), or the pipeline won't recognise it as
  an explicit map (`bake_asset._has_explicit_regions`) — a stub can't dodge the region gate.
- Boxes are **world metres**, same origin as the mesh (foot at z=0, +X forward, +Z up). Each box must
  bound that region's geometry. Derive a starting set with
  `python pipeline/tools/hitbox_from_mesh.py <mesh> --out <variant>_hitbox.json` then rename
  `regions{aabb_min/aabb_max}` → `region_hitboxes{min/max}` if needed, keeping region names.
- Region **names fold** to the R8 body palette via `region_for_name` (so `arm_left`/`wing_left` →
  arms(3), `legs`/`hindleg` → legs(4), `tail` → torso(2)); the engine still gets the 4-id mask.
- A box that projects to < 1 px in a direction is skipped that direction — make boxes real-sized.

### Calibration models — colour agreement

If this is a calibration model, the sidecar regions must cover the painted `calib_v1` colours so
`calib_color.py` can verify each hitbox region's **centre samples the expected colour** (proving
texture + UV + hitbox agree). Region-name → colour folding (`calib_spec.py`): `head/skull/jaw/horn` →
red; `torso/chest/spine` → grey; `arm_left/wing_left/foreleg_left` → green; `arm_right/wing_right` →
blue; `leg/hindleg/foot` → purple; `tail` → orange. Reproduce the **immutable** calibration metadata
exactly:

- `calib_biped_v1`: height 1.80, eye 1.62, footprint 0.40, mass 75 kg, regions
  [head, torso, arm_left, arm_right, legs].
- `calib_dragon_v1`: height 2.128, eye 1.638, footprint 1.55, mass 862 kg, regions
  [head, torso, arm_left, arm_right, legs, tail] (wings = arm_left/right).

## CONSTRAINTS

- File name is exactly `<variant_id>_hitbox.json` (or referenced via `files.hitbox`).
- This is the SAME map a skin delta clones into a variant (`asset_id` rewritten) — keep it self-contained.

## GATES THIS STAGE MUST PASS

- `regions_present` (code `region_missing`, error) — the baked hitmask carries body regions.
- `no_region_fallback` (code `region_fallback_torso`, warn; **error** for textured non-calib UNLESS this
  explicit map is present) — shipping this sidecar keeps a single-material model's fallback a visible warn.
- (calibration only) calib-colour agreement — each region centre samples its `calib_v1` colour.

## DONE WHEN

`<variant_id>_hitbox.json` exists with ≥2 valid `region_hitboxes` (min/max metres), region names fold
to the intended R8 ids, and — for a calibration model — the regions cover the exact `calib_v1` colours
and the metadata matches the immutable numbers.
