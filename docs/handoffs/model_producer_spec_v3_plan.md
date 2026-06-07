# Model Producer Spec v3 — plan (post-hardening + independent review)

- Status: **Plan** (roadmap to build the v3 pack; supersedes the v2 ZIP `dist/model_producer_delivery_spec_v2/`)
- Date: 2026-06-07
- Driver: an independent review of v2 (12 blockers + staged-pipeline + ~25 contract decisions) **plus** the pipeline hardening landed this session (external_asset_v2 migration, mode-aware severity, calibration oracle, waivers, AABBs, ADR-0035 anchor contract).
- Core finding: many v2 "blockers" target the **v2 ZIP as built** (commit `5a8e54e`), but the live pipeline has since moved past several of them. v3 = **regenerate the pack from the now-current pipeline + ship real schemas + add the staged workflow + per-stage prompts + the newly-decided contracts.**

## 1. Reviewer blocker triage (what's already done vs what v3 must do)

| # | Blocker | Status | v3 action |
|---|---|---|---|
| 1 | Version strings inconsistent (`v1`/`v2`, Proposed/Accepted) | doc | One version everywhere: `producer_spec_version: model_producer_delivery_spec_v3`, `status: Proposed` until v3 self-tests pass, then `Accepted`. Every example/report uses it. |
| 2 | Bundled schema still `external_asset_v1` | **DONE in live** (`c3ad372`: const `external_asset_v2`, `texture_mode` required) | Ship the **live** schema in the pack; examples validate against it in CI. |
| 3 | Delta notes ≠ schemas | code | Author real JSON Schemas: `producer_preflight_v1`, `verification_report_v1`, `waiver`, `texture_provenance`, `calibration_package` (+ the live `external_asset`). All examples validate in CI. |
| 4 | Severities conflict (THRESHOLDS hard-fail vs `error_codes` warn) | **DONE in code** (build_log escalates `degenerate_uv`/`region_fallback_torso`→error for `textured`; calibration bypasses) | Make `error_codes.md` **mode-aware**: add a `producer_gate_severity` column (`flat_region` vs `textured` vs `calibration`). The code already behaves this way; the table must say so. |
| 5 | Region naming by substring (`armor`→`arms` trap) | **code (new)** | Adopt **tokenized regions**: a material property `hit_region` OR an explicit `region__<id>` token; substring becomes a deprecated compat path. Touches `constants.region_for_name`. |
| 6 | Sidecar vs embedded texture ambiguous | doc/decision | **Embedded-only** for v3 `textured` (the `baseColorTexture` must be bound in the GLB; a sidecar PNG is provenance/debug only, never authoritative). The `texture_capable` gate already enforces binding; the spec must state it and the schema mark the sidecar non-authoritative. |
| 7 | "One clean mesh" ambiguous (exporter-dependent) | doc | Redefine the invariant: *one logical visual body, no stray loose objects, no unskinned visual parts if rigged, every visual part region-tagged + sharing origin/scale/forward/rig*. The probe **reports** object/mesh/primitive counts; it does not require exactly 1 imported mesh. |
| 8 | UV degeneracy misses **lines** (only checks max-extent) | **code (tweak)** | Tighten `glb_texture_probe`: require `width≥1e-3 AND height≥1e-3 AND area≥1e-5` (catches a UV collapsed to a line, not just a point). Keep `0.4–0.9` as a quality *target*, not the degeneracy threshold. |
| 9 | `region_source` enum invites misuse | doc/schema | v3 schema: `region_source` is `const "material_name"` (+ tokenized, see #5); `vertex_attribute`/`region_texture` documented as future proposals, not valid delivery values. |
| 10 | up-axis correction contradictory (spec says honored; schema says inert for glb) | doc/decision | **Decision:** `geometry.up` is **provenance/documentation only for GLB** — the GLB transform must already be correct; preflight verifies imported bounds match the declared up. (Honored only for `.obj`.) |
| 11 | Rig profiles referenced but not shipped | pack | Ship `rig_profiles/*.json` (+ their sha256) inside the v3 pack so a producer has the canonical bone set, not prose. |
| 12 | Calibration examples incomplete | examples | Ship the **calibration humanoid** (now a gold-standard, oracle-passing package) as the full calibration example: `calibration{}` block, provenance, `real_albedo:false`, + the `debug_region_legend`/`skin_binding`/`texture_regions` sidecars. |

## 2. The staged producer pipeline (adopt the reviewer's Stage 0–9)

v3 reorganizes the spec from one document into **stage contracts**, because order is load-bearing: **model → UV → texture**, **rig → animation**, **animation → mask**. Each stage = inputs, output artifact, and a machine-checkable gate.

| Stage | Output | Gate (summary) |
|---|---|---|
| **0 Creative brief / target** | `asset_plan.json` | schema-valid; archetype allowed; `texture_mode` chosen; front/back plan unless `radial_symmetric`; required clips listed |
| **1 Blockout** | proportions/silhouette/origin/scale/forward | height ≈ `world_metrics`; origin = footprint anchor (ADR-0035); front≠back readable; tri budget rough |
| **2 Final mesh + regions** | frozen topology + region materials | no stray objects; every face region-tagged (tokenized, #5); no torso-fallback; tri budget; **freeze point for UVs** |
| **3 UV unwrap** | UV layout | `TEXCOORD_0`; width/height/area thresholds (#8); islands in [0,1]; overlap only if declared; texel density |
| **4 Texture paint** | bound base colour | `baseColorTexture` **embedded** (#6); atlas richness passes; not swatch/orphan/degenerate; `real_albedo` true only for real production texture |
| **5 Rig + skin** | armature + weights | rig profile exists; exact bone names; all visual parts skinned; ≤4 influences; neutral bind; root at origin (ADR-0035) |
| **6 Animation** | clips | clip vocab valid; declared clips exist; loops loop; **in-place** (ADR-0035); right regions move (calibration oracle) |
| **7 Hitbox / mask / proxies** | R8 mask + AABBs + proxies | regions present; mask follows pose; per-region AABBs match masks (ADR-0025); whole-body collider |
| **8 Export package** | GLB + manifest + preflight | GLB probe passes; manifest schema passes; `preflight_report` generated; all referenced files exist; no orphans |
| **9 Bake + output verify** | sprite package | bake ok; contact sheets; `preflight.ok == verification.ok == build_log.ok == true` |

### Invalidation matrix (prevents agents patching the wrong stage)
```
change topology            -> redo UV, texture, skin, animation, hitbox, bake   (from Stage 3)
change UVs                 -> redo texture, bake                                (from Stage 4)
change material/region names -> redo hitmask, hitbox, bake (maybe texture)      (from Stage 7, maybe 4)
change scale/origin/forward -> redo metrics, hitbox, bake, maybe animation      (from Stage 1)
change rig                 -> redo skin, animation, hitbox, bake                (from Stage 5)
change skin weights        -> redo animation verify, hitbox, bake               (from Stage 6)
change animation           -> redo per-frame masks, bake                        (from Stage 6/7)
change texture             -> redo atlas richness, bake                         (from Stage 4)
```
**Rule in every stage:** *if you change an upstream artifact, restart from the earliest invalidated stage.* Final texture painting (Stage 4) may not begin until topology is frozen (Stage 2) and the UV gate (Stage 3) passes. A lightweight **art-direction** phase (concept/palette/material-plan/region-plan/front-back-plan) is allowed *before* Stage 1 — intent early, final pixels late.

## 3. The prompt library (the new v3 deliverable you asked for)

Alongside the technical stage contracts, v3 ships `prompts/` — one **ready-to-paste producer prompt per stage** for a model-generating AI. Each prompt is self-contained and contains, in this fixed template:
```
ROLE + STAGE GOAL          (what to produce in this stage, nothing more)
PRECONDITIONS              (which prior-stage artifacts must already pass their gate)
EXACT REQUIREMENTS         (every numeric value/threshold for this stage, copied from THRESHOLDS)
THE OUTPUT ARTIFACT        (file name + schema it must validate against)
THE SELF-CHECK COMMAND     (the exact gate command + the pass predicate)
ANTI-PATTERNS              (the real failures we caught that this stage prevents)
INVALIDATION               (if you change X here, which later stages must restart)
```
So a producer is driven stage-by-stage with no room to "paint a final texture onto unstable geometry." The prompts reference the schemas (authoritative) and the calibration gold-standard (diff target), never loose prose.

## 4. "Decide now" contract decisions (resolutions; ADR-0035 covers the coordinate cluster)

Resolved here (adopt unless overridden): **anchor/pivot/origin/direction-0/camera/canvas/root-motion** → ADR-0035. **Region grammar** → tokenized `hit_region` property or `region__<id>` token, no substring (#5). **Texture authority** → embedded-GLB only for v3 (#6). **region_source** → `const material_name` (#9). **up-axis** → glb provenance-only, must be pre-correct (#10). **Variant compatibility** → variants of an archetype MUST preserve origin/forward/scale/rig/sockets/region-IDs/clip-vocab; texture-only variants differ only in texture/provenance. **Visual-vs-hit classification** → every visual primitive declares one of `{body_region, equipment, effect, non_hittable_visual}` so the mask verifier knows a missing region is intentional vs a bug. **Sockets** → reserved naming `socket__{mouth,hand_L,hand_R,weapon_tip,muzzle,tail_tip,core,feet_center}` (emit + verify; ties to ADR-0033/0034). **Oversize** → core body must fit the 256² class; oversized transient effects are separate overlay layers. **Reserved-not-built** → `material_semantics` (flesh/metal/bone…) + `proxy__*` colliders + shadow anchor: declared-optional, not rendered yet (the ADR-0026/0033 "record now, render later" pattern).

## 5. v3 pack structure
```
model_producer_delivery_spec_v3/
  README.md                         one version everywhere
  spec/  00_brief ... 09_bake_verify (stage contracts)
  prompts/ stage_0 ... stage_9 (the prompt library, section 3)
  THRESHOLDS.md  (mode-aware)        error_codes.md (mode-aware severity column)
  invalidation_matrix.md
  schema/  external_asset(v2 live) + producer_preflight + verification_report + waiver
           + texture_provenance + calibration_package + rig_profiles/*.json(+sha256)
  examples/ one fully-valid manifest+reports per archetype + the gold calibration humanoid
  fixtures/ positive/ (validate) + negative/ (must FAIL with the named code)
  source_package_spec.md            (the .blend/source-art package, not only the GLB)
  self_test.py                      runs section 6 in CI
```

## 6. v3 self-tests (the pack must pass these before ratification)
1. all JSON parses; 2. all example manifests validate vs bundled schemas; 3. all example preflight reports validate; 4. all example verification reports validate; 5. every code in THRESHOLDS exists in error_codes; 6. every severity matches the mode-aware policy; 7. all README-listed files exist; 8. all version strings agree (README ≡ examples ≡ schemas); 9. calibration examples carry required calibration metadata; 10. **negative fixtures fail with the expected code**: orphan_texture, obj+textured, degenerate_uv (point), degenerate_uv (line), unbound sidecar, region_fallback_torso, front_back_indistinct (non-radial). The negative fixtures matter most — they are to *rejection* what the calibration model was to *acceptance*: concrete truth.

## 7. Source-art package (not only the delivery package)
v3 also defines a **source package** (`<variant>.blend` + `source_asset.json` + `/textures/source` + `/references` + `/export/<variant>.glb` + `/reports`). The GLB is the *exported delivery artifact*, not the only source of truth — so an AI can revise topology/UV/rig/material without brittle GLB surgery. The delivery package remains the gate; the source package is where named collections / visual objects / hit-proxy / sockets / armature / actions / material slots / UV maps / source images are enforced.

## 8. Build order
1. (this doc + ADR-0035) — done. 2. Code: tokenized regions (#5) + UV-line check (#8). 3. Schemas: the 6 JSON schemas (#3). 4. Regenerate pack from live pipeline (#1,2,4,9,11,12). 5. Stage contracts + prompt library + invalidation matrix. 6. Fixtures (positive + negative). 7. `self_test.py` green → flip status Accepted.
