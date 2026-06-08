# Calibration Model (`calib_v1`) — immutable, versioned definition

> **HARD RULE. A calibration model is FIXED and VERSIONED. It must NEVER be re-modelled.**
> The colours, the per-region metadata, and the region set below are the *single source of truth*
> baked into `pipeline/tools/calib_spec.py` (version constant `CALIB_SPEC_VERSION = "calib_v1"`).
> Re-modelling — repainting a colour, nudging a height, renaming a region — does not "improve" the
> calibration model; it **silently breaks every test that depends on these exact numbers**
> (the colour-oracle, the metric checks, the region-presence checks). When you build a calibration
> package you do not author a new model: you **reproduce these values byte-for-byte**. If the
> calibration model genuinely must change, it is a *new version* (`calib_v2`), not an edit to `v1`.

A calibration model is the pipeline's *oracle*: a deliberately trivial, debug-coloured creature whose
every region is painted a known, well-separated flat colour and whose `region_hitboxes` sidecar covers
that exact colour. Baking it proves the whole chain agrees end-to-end — **the texture, the UVs, the
skin binding, the animation, AND the hitbox** — because the bake can sample the centre of each hitbox
and check that the colour underneath is the colour that region was supposed to be painted. It is the
fixed reference against which a *real* combat creature is judged.

This document is the producer-facing restatement of `calib_v1`. The authoritative code is
`pipeline/tools/calib_spec.py`; if this doc and that file ever disagree, **the file wins** and this
doc is the bug.

---

## 1. The calibration colour table (`calib_v1`, EXACT sRGB)

These are the **exact** painted calibration colours, copied from `CALIBRATION_COLORS` in
`pipeline/tools/calib_spec.py`. They are sRGB 0..255, chosen as well-separated hues so a
nearest-colour match is unambiguous. **`left = green`, `right = blue`** — and "left"/"right" always
mean **the model's own left and right**, never the viewer's.

| Region (canonical key) | Colour  | Hex       | RGB (sRGB 0..255) | Notes                                   |
|------------------------|---------|-----------|-------------------|-----------------------------------------|
| `head`                 | red     | `#D82626` | `(216, 38, 38)`   |                                         |
| `torso`                | grey    | `#828282` | `(130, 130, 130)` |                                         |
| `arm_left`             | green   | `#2AC440` | `(42, 196, 64)`   | left arm **or** left wing               |
| `arm_right`            | blue    | `#285AE0` | `(40, 90, 224)`   | right arm **or** right wing             |
| `legs`                 | purple  | `#962AC8` | `(150, 42, 200)`  |                                         |
| `tail`                 | orange  | `#F08A1E` | `(240, 138, 30)`  | tail-bearing archetypes only (e.g. dragon) |

There are exactly **six** colour-bearing regions. A biped paints five of them (no `tail`); a dragon
paints all six (its **wings are `arm_left` / `arm_right`**, its tail is `tail`).

A calibration model may *name* an anatomical part however its rig names it (`wing_left`, `foreleg_l`,
`jaw`, `hindleg`, …). `calib_spec.calib_color_key()` folds any such region name down to one of these
six canonical colour keys. The folding rule that matters most: **explicit left/right qualifiers
(`_left`/`_l`, `_right`/`_r`) on a `wing`/`arm`/`foreleg` are resolved before the bare limb token**,
so `wing_left → arm_left (green)` and `wing_right → arm_right (blue)` — never the reverse.

---

## 2. Each hitbox covers its colour; the bake verifies the centre sample

Two halves of one contract, both reproduced exactly from `calib_v1`:

1. **Painting (the skin):** each region of the calibration model is painted its single flat colour
   from the table above, with **no gradients, no shading, no texture detail** — one region, one
   colour, edge-to-edge.

2. **Covering (the hitbox):** the `region_hitboxes` sidecar (`<variant_id>_hitbox.json`) must place
   each region's box **over that region's painted colour**, so the box's centre pixel lands on the
   region's flat colour.

The bake then **verifies the hitbox centre samples the expected colour** (this contract is stated
verbatim in the `pipeline/tools/calib_spec.py` module docstring). Concretely: for each region it reads
the colour under the centre of that region's `region_hitbox`, folds the region's name to its canonical
key via `calib_color_key()`, looks up the expected colour in `CALIBRATION_COLORS`, and requires a
match. A mismatch means one of three things has silently broken and the calibration model has *failed*:

- the **texture/UVs** didn't take (the region rendered the wrong colour, or grey), or
- the **skin/animation** moved the region away from where the hitbox expects it, or
- the **hitbox** itself is mis-placed (centre is over the wrong region, or background).

This is exactly why a calibration model must never be re-modelled: every one of these checks is
pinned to the *exact* colours and the *exact* region set in `calib_spec.py`. Change the model and the
oracle no longer measures anything.

> Note on naming: `calib_spec.py` defines the colours and the folding; the *motion* half of the
> oracle (proving the skin+animation actually deformed, not that a rest pose was baked N times) lives
> in `pipeline/tools/calib_oracle.py` (`calib_oracle_v2`), which tracks each region's centroid + AABB
> across a clip. Together they verify the calibration model end-to-end.

---

## 3. Hard-coded metadata (copy-paste; reproduce EXACTLY)

These blocks are the immutable per-archetype world metrics + region set from `CALIBRATION_MODELS` in
`pipeline/tools/calib_spec.py`. A producer building a calibration package **reproduces these numbers
exactly** — they are never re-measured off a mesh and never rounded. World metrics are in **metres**;
mass in **kilograms**.

### `calib_biped_v1`

```json
{
  "variant_id": "calib_biped_v1",
  "world_metrics": {
    "height_world": 1.80,
    "eye_height_world": 1.62,
    "footprint_radius_world": 0.40
  },
  "mass_kg": 75.0,
  "regions": ["head", "torso", "arm_left", "arm_right", "legs"]
}
```

Five regions, **no `tail`**. Paints: head red, torso grey, **left arm green**, **right arm blue**,
legs purple.

### `calib_dragon_v1`

```json
{
  "variant_id": "calib_dragon_v1",
  "world_metrics": {
    "height_world": 2.128,
    "eye_height_world": 1.638,
    "footprint_radius_world": 1.55
  },
  "mass_kg": 862.0,
  "regions": ["head", "torso", "arm_left", "arm_right", "legs", "tail"]
}
```

Six regions, **plus `tail`**. The **wings are `arm_left` / `arm_right`**: paint the **left wing green**
and the **right wing blue**. Paints: head red, torso grey, left wing green, right wing blue, legs
purple, tail orange.

> Do not "fix" `height_world: 2.128`, `eye_height_world: 1.638`, or `footprint_radius_world: 1.55` to
> rounder numbers. Those exact values are what the metric checks compare against.

---

## 4. Step-by-step: paint the calibration skin + author the hitboxes

The calibration model ships as an `external_asset_v2` delivery (schema
`pipeline/schema/external_asset.schema.json`) flagged as a calibration/debug package. Build it in this
order:

### A. Pick the model + region set
1. Choose the archetype (`biped` or `dragon`) and use the **matching** `calib_*_v1` block from §3.
   Set `variant_id` to that block's `variant_id`, and `archetype` accordingly.
2. The model must have exactly the regions listed in that block — no more, no fewer. (Dragon: the
   wings are the two `arm_*` regions; the tail is `tail`.)

### B. Paint the skin — one flat colour per region
3. Give **each region one single flat colour** from the §1 table, edge-to-edge, with no shading,
   gradient, AO, or texture detail. The point is an unambiguous nearest-colour read.
4. Apply **left = green, right = blue from the MODEL's own left/right**, not the camera's. Stand
   behind the model facing the same way it faces (forward `+X`): its left hand/wing is on your left
   and must be **green `(42,196,64)`**; its right is on your right and must be **blue `(40,90,224)`**.
   Getting this backwards is the single most common calibration bug.
5. Use the exact RGB values. Do not colour-pick "close enough" — the verifier matches against the
   exact `CALIBRATION_COLORS` entries.
6. How the flat colour is delivered depends on `texture_mode`:
   - **`textured`** — paint a real albedo texture with one flat colour block per region, on a real
     (non-degenerate) UV unwrap, with that texture **bound as `baseColorTexture` in the glb**. A
     calibration package is the *one* delivery allowed to bake flat per-region colours without
     tripping the textured-fidelity escalation (`degenerate_uv` / `region_fallback_torso` stay
     warnings for a calibration bake, become errors for a normal textured one).
   - **`flat_region`** — set each region material's `base_color_factor` to the flat colour. Do **not**
     bind a base-colour texture on a `flat_region` delivery (that is the flat-via-texture hack the
     linter rejects as `flat_region_bound_texture`).

### C. Author the matching `region_hitboxes`
7. Write the sidecar `<variant_id>_hitbox.json` (e.g. `calib_biped_v1_hitbox.json`) with one entry
   per region in the §3 region set.
8. Name each hitbox region so it folds to the right colour key via `calib_color_key()` — anatomical
   names are fine (`head`, `torso`, `arm_left`/`wing_left`, `arm_right`/`wing_right`, `legs`, `tail`),
   but a wing/arm/foreleg **must carry its `_left`/`_right` qualifier** so left→green / right→blue.
9. Place each box so its **centre lands squarely on that region's painted flat colour** — not on a
   seam, not overlapping a neighbouring colour, not on background. The verifier samples the box centre.
10. Cover **every** colour-bearing region in the model's region set. A missing region's colour is
    never sampled (and an all-background hitmask is itself an error).

### D. Verify
11. Lint the package (`lint_external_asset.py`) and bake it. The bake samples each hitbox centre and
    checks the colour against `CALIBRATION_COLORS`; the motion oracle (`calib_oracle.py`) confirms the
    skin/animation actually deformed. A clean calibration bake means texture, UVs, skin, animation, and
    hitboxes all agree — which is the whole reason the calibration model exists.

---

*Source of truth: `pipeline/tools/calib_spec.py` (`CALIB_SPEC_VERSION = "calib_v1"`). This document is
a restatement; the file is authoritative.*
