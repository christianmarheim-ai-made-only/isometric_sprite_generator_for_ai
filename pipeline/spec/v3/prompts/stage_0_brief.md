# Stage 0 — Creative brief: pick archetype + rig + texture_mode

## PROMPT

You are producing ONE combat creature for `game_iso_v1`. Write the creative brief and lock the three
contract decisions that every later stage depends on. Do **not** model anything yet.

Decide and record:

1. **`archetype`** — one of `{biped, bird, quadruped, ball, dragon}`. A combat creature is normally
   **`biped`** (humanoid fighter) or **`dragon`** (winged quadruped). The archetype selects the shared
   rig + the engine clip library, so it is load-bearing, not flavour.
2. **`rig`** — the matching rig profile id under `pipeline/schema/rig_profiles/`:
   `biped → biped_v1`, `dragon → dragon_v1`, `quadruped → quadruped_v1`, `bird → bird_v1`,
   `ball → ball_v1`. The mesh you build later MUST skin to this profile's exact bone names.
3. **`texture_mode`** — `flat_region` (per-region material `base_color_factor`, no texture, fastest)
   or `textured` (real UV unwrap + a painted `baseColorTexture` bound in the glb). Pick deliberately:
   `textured` opts you into ADR-0028 escalation (degenerate UVs / region fallback become **errors**).
4. **`variant_id`** — lowercase `^[a-z0-9_]+$`; becomes the output dir name, so it must be unique.
5. The combat intent: silhouette, scale in metres, the four required actions (idle/attack/hit/death),
   and which limb is the attack limb (drives the Stage 6 + Stage 7 motion check).

## CONSTRAINTS

- This is the locked target — you do not change projection, 16 directions, canvas 256, tile 64×32, or
  the 4096 px page cap. You only fill the producer-owned fields of `external_asset_v2`.
- `archetype` and `rig` must be a **legal pair**. The linter raises `archetype_rig_mismatch` if they
  are not (e.g. `archetype: biped` with `rig: dragon_v1`).
- A combat creature is **animated**, so the archetype's required clips will be enforced later — confirm
  now that you can deliver **idle + attack + hit + death** for the chosen rig.

## GATES THIS STAGE MUST PASS

- `texture_mode_declared` (code `texture_mode_missing`, error) — `texture_mode` is REQUIRED in the
  manifest; absence is rejected at the front door.
- `archetype_matches_rig` (code `archetype_rig_mismatch`, error) — archetype ↔ rig must be a legal pair.

## DONE WHEN

A one-paragraph brief plus a locked decision record exists with: `archetype`, `rig` (a real profile
id), `texture_mode ∈ {flat_region, textured}`, a unique `variant_id`, and the four named combat
actions with the designated attack limb. No geometry yet.
