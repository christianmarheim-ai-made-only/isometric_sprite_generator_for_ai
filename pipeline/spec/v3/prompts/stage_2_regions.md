# Stage 2 — Split into region-named parts

## PROMPT

Split the block-out into parts whose names resolve to the engine's **4-body hit palette**:
`head(1) / torso(2) / arms(3) / legs(4)`. The bake reads a part/material name and maps it to a region
id via the keyword table in `pipeline/tools/constants.py` (`region_for_name`). Name parts so the
mapping is correct and **never silently defaults to torso**.

Use these keywords (first keyword found, in priority order head < torso < arms < legs, wins):

- **head (1):** `head, skull, face, neck, beak` (+ calib folding: `jaw, horn, mouth, eye`).
- **torso (2):** `torso, chest, body, spine, hip, pelvis, waist, tail`. (Tail folds to torso in the
  R8 palette; a `tail` region in the hitbox sidecar is still tracked separately for calibration.)
- **arms (3):** `arm, hand, shoulder, elbow, wrist, wing`. (Wings → arms; forelegs of a dragon → arms.)
- **legs (4):** `leg, foot, feet, thigh, shin, knee, ankle` (hindlegs → legs).

Resolution rules to respect:

- A name carrying a **higher-priority** conflicting keyword can't be overridden by a suffix — e.g.
  `wing_L` (`wing` → arms) cannot be re-tagged legs by appending `__legs`; `material_region_name()`
  drops it to a keyword-free ordinal in that case. Name parts cleanly so this never bites.
- For a **dragon**, map per anatomy: horns/jaw → head, wings + forelegs → arms, hindlegs → legs, tail →
  torso (R8) but a distinct `tail` hitbox region.
- A **single-material art model** (one `Material_0` over the whole mesh) renders an all-torso mask and
  triggers `region_fallback_torso`. That is acceptable ONLY if you instead ship the explicit
  authoritative `region_hitboxes` sidecar (Stage 7), which declares the regions so the fallback is not
  "silent". Otherwise, split into real region-named parts here.

## CONSTRAINTS

- Region names are the contract, not the material colour. Get the **name** right at this stage so the
  R8 hitmask decodes to the correct gameplay region.
- `region_source` stays `material_name` (the only mode that bakes today); `vertex_attribute` /
  `region_texture` are documented extensions only.

## GATES THIS STAGE MUST PASS (enforced downstream at bake)

- No **silent** `region_fallback_torso` (code, warn; **error** for textured non-calibration under
  ADR-0028) — every part resolves to its intended region by name, OR an explicit `region_hitboxes`
  map is provided in Stage 7.
- `regions_present` (code `region_missing`, error) — the eventual baked R8 hitmask has ≥1 body region,
  not all background.

## DONE WHEN

Every part has a name that `region_for_name()` resolves to its intended id (head/torso/arms/legs), with
no part falling through to the torso default — verified by running the part names through
`region_for_name` — OR you have explicitly chosen the single-material + Stage-7 sidecar route and noted it.
