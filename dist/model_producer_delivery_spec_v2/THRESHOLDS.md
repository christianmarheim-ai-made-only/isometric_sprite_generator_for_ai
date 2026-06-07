# THRESHOLDS — every number a producer must hit

These are the load-bearing, machine-checked values. Each maps to a canonical code in `error_codes.md`. Hit all of them and the bake is automatic and the sprite looks right in all 16 directions.

## Texture (only when `texture_mode: textured`)

### Texture-capable (INPUT gate — rejected before any bake, by `glb_texture_probe.texture_capable`)
| Check | Requirement | Code on fail |
|---|---|---|
| base-colour bound | a `baseColorTexture` is bound on region materials **inside the glb**, ≥1 embedded image | `texture_unbound` |
| UVs present | every part-mesh primitive has `TEXCOORD_0` | `texture_unbound` |
| UVs non-degenerate | per-material UV bbox `max(width,height)` **> 1e-4** (probe margin **≥ 1e-3**); target span **≈ 0.4–0.9** | `degenerate_uv` |
| UVs in range | islands within `[0,1]` (bleed ≤ 1e-3) | (recorded) |
| mesh format | `.glb`/`.gltf` (never `.obj` for textured) | `obj_textured_unsupported` |

### Atlas richness (OUTPUT gate — on the baked colour body; calibration bypasses via waiver, never `real_albedo:true`)
| Metric | Requirement | Code on fail |
|---|---|---|
| `quantized_unique_rgb_4bit` | **≥ 64** | `atlas_colour_rich_low` |
| `rgb_entropy_bits` | **≥ 3.0** | `atlas_colour_rich_low` |
| `largest_single_colour_fraction` | **≤ 0.65** | `atlas_colour_rich_low` |
| `non_background_pixel_fraction` | **≥ 0.20** *(of the source atlas in preflight; recorded-only on the baked body — small sprites must not fail it)* | — |

### UV overlap & base-colour image
| Check | Requirement | Code |
|---|---|---|
| different-region UV overlap | `≤ 0.02` (mirroring must be declared in `provenance.texture.mirrored_uv_regions`) | `uv_overlap_undeclared` |
| base-colour PNG | sRGB; each dimension ∈ **{512, 1024, 2048}** (W and H may differ) | — |

## Geometry (modeling)
| Check | Requirement | Code on fail |
|---|---|---|
| scale | measured height within **±25%** of `world_metrics.height_world` | `world_metrics_mismatch` |
| ground origin | min Z **≈ 0**; footprint centred x = y ≈ 0 | `ground_origin_mismatch` |
| forward axis | mesh faces declared `forward ∈ {+x,-x,+y,-y}` (required iff `has_direction`; baker rotates onto +X) | `forward_axis_mismatch` |
| up axis | `up ∈ {y,z}` declared | — |
| triangle budget | total **[300, 8000]** | — |
| front ≠ back | `mean_abs_rgb_difference ≥ 8.0` **OR** `edge_ssim ≤ 0.92` (dir N vs N+8 over the 16 dirs); exempt iff `radial_symmetric:true` AND `front_back_distinctness_exempt:true` | `front_back_indistinct` |

## Rig / skin
| Check | Requirement | Code on fail |
|---|---|---|
| influences | **≤ 4** bone influences per vertex | `too_many_influences` |
| coverage | **0** unweighted parts | `unweighted_part` |
| bone names | exactly per `schema/rig_profiles/<rig>.json` | `missing_required_bone` |
| archetype ↔ rig | `archetype` matches the rig family | `archetype_rig_mismatch` |

## Animation
| Check | Requirement | Code on fail |
|---|---|---|
| in-place | net horizontal (X,Y) bone translation per clip within **~1%** of `footprint_radius` | — |
| frames / fps | `frames ≥ 1`; `fps > 0` | (schema) |
| playback | `playback ∈ {loop, once}` — there is **NO `hold`** (`once` already holds the last frame) | (schema) |
| vocabulary | clip names ∈ engine vocab `{idle, walk, run, attack, hit, jump, fall, crouch_idle, crouch_walk}` (no bare `crouch`); off-vocab → `offvocab_clip` warn → renamed | `missing_required_clip` |
| declared clips exist | every declared state's clip is in the glb (or paired via `files.animation_clips`) | `missing_clip_rest_pose` |
| required clips (gate = required only) | see per-archetype below | `missing_required_clip` |

### Per-archetype clip requirements
| archetype | required | recommended | optional |
|---|---|---|---|
| biped | `idle` | walk, run, attack, hit | jump, fall, crouch_idle, crouch_walk, death |
| bird | `idle` | fly, hit | attack, death |
| quadruped | `idle` | walk, run, hit | attack, death |
| dragon | `idle` | walk, run, attack, hit, fly | jump, fall, death |
| ball | `idle` | roll, hit | attack, death |

> `death`/`fly` are **non-load-bearing**: the read-only engine vocabulary does not select `death`, so it is never *required* by the gate (you may ship it). Off-vocab profile states (e.g. dragon `bite`/`breath`/`takeoff`, ball `pop`/`explode`, quadruped `graze`) route through the synonym table to canonical clips; do not invent new engine vocabulary.

## Hitbox
| Check | Requirement | Code on fail |
|---|---|---|
| regions present | the R8 mask is non-empty for every declared region | `region_missing` |
| no torso fallback | no material silently collapses to torso (a real mistake for textured) | `region_fallback_torso` (error when textured) |
| region tiling | regions tile the silhouette with no large gaps | (verification) |

## Waivers
- must set `expires_at` (compared to the bake date) — expired ⇒ `waiver_expired`
- `engine_real_albedo` must be **false** ⇒ else `waiver_attempts_real_albedo_true`
- downgrades exactly **one** named `code`; the waived check still appears in `verification_report.json`

## The agreement invariant
`preflight_report.ok == verification_report.ok == build_log.ok` — all three derive from the same "any `severity==error`" rule. A disagreement is itself an error (`verification_build_log_disagree`).
