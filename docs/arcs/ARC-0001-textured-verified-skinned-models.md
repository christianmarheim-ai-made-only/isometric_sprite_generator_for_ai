# ARC-0001: Textured & verified skinned models — end-to-end

- Status: **Proposed** (planning arc; the constituent ADRs **0026–0032** carry the binding decisions)
- Date: 2026-06-07
- Owner: sprite-pipeline
- Scope: this repo (the sprite-bake pipeline). Engine items at `C:/Code/Claude` are **read-only** → see [`../handoffs/engine_team_brief.md`](../handoffs/engine_team_brief.md).
- Source investigation: glb UV/binding parse + atlas reads (this session); the two decomposition workflows (Epic A texture-fidelity, Epic B verification) whose backlogs feed the two implementation briefs.

---

## TL;DR

We accept "textured / skinned" model deliveries, bake them, and ship them **green** — while the texture art never reaches a pixel. The verified cause is not one bug but a stack: the models aren't actually skinned to their textures (no UVs / orphan atlases / degenerate UVs), the auto-rig *flattens* what little is there (and crashes on the richest deliveries), and **no gate fails a flat bake**. This arc:

1. makes a **textured delivery a machine-checkable contract** (`texture_mode` + the `texture-capable(glb)` predicate) — ADR-0026;
2. **preserves textures + UVs through rigging** and routes textured models around the flattening auto-rig — ADR-0027;
3. **gates a flat-when-textured bake as a hard failure** (`ok=false`), on both render paths and at intake — ADR-0028;
4. records **texture/UV provenance** so the engine knows real albedo from flat — ADR-0029;
5. stands up a **color-coded calibration model + region↔color oracle** (ADR-0030) and a **per-bake cross-stage verification report** (ADR-0031) so every bake **proves** model / skin / anim / hitbox / texture were *applied* — or fails loudly;
6. pins **faithful color management + the baked-atlas contract** — ADR-0032.

Deliverables in this arc: **7 ADRs (0026–0032)**, **two implementation briefs** (pipeline hardening = Epic A; verification subsystem = Epic B), and a **standalone Model Producer delivery spec** (the handoff that closes the gap at the source).

---

## 1. The verified gap (evidence — do not re-investigate)

"Verify a texture" means one thing: *do the model's UVs land on the painted atlas islands?* Parsing every delivered glb and reading every committed atlas gave ground truth:

| Model | Materials | Base texture bound in glb? | UVs | **texture-capable?** |
|---|---|---|---|---|
| green_ogre | 0 | none | **0 UVs on all 24 parts** | **NO** (L0) |
| red_dragon | 0 | none | **0 UVs on all 27 parts** | **NO** (L0) |
| red_ball | 0 | none | **0 UVs** | **NO** (L0) |
| **pirate_v2** | 19 | ✅ all 19 → 1 embedded atlas | **all 37 prims collapsed to a point** (area 0) | **NO** (L1) |
| *humanoid_textured (known-good baseline)* | 4 | ✅ | real unwrap, **area 0.40–0.92** | **YES** |

- **The committed `*_texture_atlas.png` are flat placeholders** (pirate = labelled swatch grid; dragon/ogre = noise/tiling fill), *not* painted art. Detailed painted atlases exist but are (a) bound into no glb and (b) unusable because the models have no real UVs.
- **What the producer actually did:** painted standalone atlas art **and** built geometry, but never coupled them with a real UV unwrap. Ogre/dragon/ball ship a loose PNG next to a model with *zero* UVs (orphan). The pirate went further and faked it: it pinned every vertex of each material to the **centre of that material's swatch-grid tile** — a "flat-colour-via-texture" hack that *looks* textured to a shallow check but samples exactly one texel per part.

**The four root-cause layers (each independently sufficient to flatten output):**

- **L0** — geometry-only mesh + orphan atlas (ogre/dragon/ball): nothing to sample.
- **L1** — degenerate UVs (pirate): bound texture, every island is a point.
- **L2** — the auto-rig (`rig_from_profile.py`) *replaces* every part material with a flat per-region colour, strips UVs/vertex-colours, never reads the texture — **and crashes on the pirate's dict-shaped `materials.json`**.
- **L3** — the renderer is texture-*capable* (Workbench TEXTURE iff `has_tex`) but only as good as its input.
- **L4** — **no gate.** `degenerate_uv` is a non-aborting `warn`, and `build_log.ok` only flips on `severity=error`. A textured-but-flat bake ships green.

---

## 2. The outcome ("fixed" =)

A bake is correct iff, for every package: `texture_mode` is declared and schema-valid; `texture-capable(glb)` is computed once and recorded; a `textured`-declared package that is not capable or bakes flat is `severity:error ⇒ ok=false` on **both** render paths and at intake (unless an explicit audited waiver downgrades exactly that code); auto-rig provably preserves bound texture+UVs on textured input or the bake fails; the manifest provenance records the texture/UV identity; a **per-archetype calibration fixture + oracle bakes green every commit**, and a **mutation harness proves each detector fires**; and a `verification_report.json` aggregates **modeling / skinning / animation / hitbox** with load-bearing severities driving `ok`. The arc is **done** when a deliberately-broken input of each of the four shapes (geometry-only, degenerate-UV, auto-rig-flattened, missing-region) turns the build **red**, while `humanoid_textured.glb` and the calibration fixtures stay **green**.

---

## 3. The decisions — ADRs 0026–0032

> **Numbering note:** this repo uses `ADR-00NN`. The **engine** repo has its *own* `ADR-026/028/029/030/031/032` (hit-regions) in a different namespace. Cross-references qualify "engine ADR-0NN" vs the pipeline numbers below.

| ADR | Decision (one line) |
|---|---|
| **0026** [texture-mode + capability contract](../../adr/ADR-0026-texture-mode-declaration-and-texture-capability-contract.md) | Declare `texture_mode ∈ {flat_region, textured}`; `textured` is valid only if `texture-capable(glb)` = (real per-material UVs, area>0, in-range) **AND** (base colour **bound in the glb**, not an orphan sidecar). |
| **0027** [auto-rig preserves textures/UVs](../../adr/ADR-0027-auto-rig-preserves-textures-and-uvs.md) | Auto-rig keeps existing UVs + bound texture (flat-per-region only as fallback); fix the dict-`materials.json` crash; thread export flags through both re-exports; textured models **ship pre-rigged** or the bake fails rather than silently flatten. |
| **0028** [textured-flat is blocking](../../adr/ADR-0028-textured-flat-bake-is-a-blocking-failure.md) | One shared fidelity detector → a `textured` delivery that is not-capable / degenerate / flat-atlas is `severity:error ⇒ ok=false`, on both paths + at intake; per-asset waiver for deliberately-flat. |
| **0029** [texture/UV provenance](../../adr/ADR-0029-texture-uv-provenance-in-the-baked-manifest.md) | Manifest provenance records `has_bound_tex` + a derived `real_albedo` + UV coverage + per-image hash + `uv_repaired`/`flat_fallback`; consistency gate. The field the engine reads to know real albedo from flat. |
| **0030** [calibration model + oracle](../../adr/ADR-0030-color-coded-calibration-model-and-region-color-oracle.md) | A `CALIB_RGB` per-bone palette (color pass only; region pass stays canonical `REGION_RGB`) + a `calib_oracle.py` + one fixture **per archetype** + a mutation harness = the automated **e2e visual-regression** substrate. |
| **0031** [per-bake verification report](../../adr/ADR-0031-per-bake-cross-stage-verification-report.md) | Every bake emits `verification_report.json` over **modeling / skinning / anim / hitbox**, with load-bearing severities flipping `ok`; finally **implements ADR-0025's per-region AABBs**. |
| **0032** [faithful color + atlas contract](../../adr/ADR-0032-faithful-color-management-and-baked-atlas-contract.md) | Pin full Standard/sRGB color management; render textured color pass FLAT (AO baked in); sRGB-8 lossless atlas; record page sizes vs `MAX_PAGE_PX`. |

---

## 4. The work — two implementation epics

The decomposition produced ~90 implementation-ready stories. They split into two epics, each with its own brief (story id, acceptance, touchpoints, gate severity):

### Epic A — texture fidelity → [`../handoffs/pipeline_hardening_brief.md`](../handoffs/pipeline_hardening_brief.md)
Implements ADR-0026/0027/0028/0029/0032. Auto-rig texture/UV preservation + the dict-`materials.json` fix + export-flag round-trip; `texture_mode` schema + linter; the shared fidelity detector + blocking gate (build/intake/batch); manifest texture provenance; faithful color management; a non-skipping textured golden; the pirate UV-repair fallback (proof-of-chain).

### Epic B — cross-stage verification → [`../handoffs/verification_subsystem_brief.md`](../handoffs/verification_subsystem_brief.md)
Implements ADR-0030/0031 (and consumes 0025/0028). The `CALIB_RGB` palette + per-archetype calibration fixtures + `calib_oracle.py` + AA-tolerant buckets + silhouette-band + plausibility; skinning applied-verification (every part bound, intended bone via `region_by_bone`, deform-live); animation applied-verification (dead-clip, intent oracle, loop seam, vocab coverage); hitbox applied-verification (per-region AABBs derived + tracking, mask↔color alignment, coverage/collapse); the unified `verification_report.json` + severity policy + batch surfacing; the **negative/mutation harness** proving each detector fires.

> The two epics share three seams — the **fidelity detector** (one shared helper, not three), the **calibration fixture** (one generator, per archetype), and the **severity/`ok` model** (one policy). The briefs are written to converge on those, not duplicate them.

---

## 5. The calibration model — the keystone (ADR-0030)

The per-limb-coloured model currently being authored is the spine of the whole verification story. Because **each part is a distinct, known colour**, the pipeline can *programmatically prove*, not eyeball:

- **skinning** — each part's known colour sits where its bone is and **moves when that bone moves**; a part bound to the wrong bone (the unvalidated nearest-bone-by-centroid bind) or left static shows up as colour in the wrong place / not moving;
- **animation** — the **right** region moved for a clip (walk→legs, attack→arms) and frames differ from the rest pose;
- **hitbox** — the R8 region mask / per-region AABB for region R **overlaps R's known colour** in the color pass.

Design locks (from ADR-0030): a **separate `CALIB_RGB`** palette painted into the **color pass only** (the canonical 4-id `REGION_RGB` can't tell left-arm from right-arm — exactly the discrimination mis-skin detection needs); the region/R8 pass stays byte-unchanged so the two passes cross-check; **one fixture per rig archetype** (one model can't exercise biped/bird/quadruped/dragon/ball skeletons); symmetric props (ball) are exempt from front≠back / motion oracles; a **mutation harness** (deliberately mis-bind a limb, kill a clip, swap a colour) proves the oracle is non-vacuous. This is the committed golden baked **every commit** = the regression net.

---

## 6. Critical path (must-be-this-order)

```
PREREQ  Resolve the `death` clip gap (add to ENGINE_CLIP_VOCAB or drop it from ADR-0031 gating);
        the bare-`crouch` spec drift is already fixed.

SLICE 1  ADR-0026 — texture_mode (both schemas + linter) + texture-capable(glb) as a STANDALONE
         glTF-JSON predicate (NO Blender, NO renderer edit). Smallest slice; de-risks everything.

SLICE 2  ADR-0027 — auto-rig preserve-branch + dict-materials.json loader + export_materials on
         BOTH export sites + texture-drop guard.  MUST precede the Slice-3 error gate (else good
         textured inputs hard-fail with no preserve path).

SLICE 3  ADR-0028 — one shared texture_fidelity() detector (kills static-path drift) THEN the
         blocking gate (trigger = texture_mode==textured) + intake reject + richness floor.

SLICE 4  ADR-0029 — provenance.texture block (has_bound_tex + derived real_albedo) + consistency gate.

SLICE 5  ADR-0030 — CALIB_RGB + per-archetype fixtures + oracle + mutation harness. (Independent of 1–4.)

SLICE 6  ADR-0031 — verification_report aggregating all stages; consumes ADR-0030 + ADR-0028;
         IMPLEMENTS ADR-0025 AABBs. The roof — last.

SLICE 7  ADR-0032 — pin color-management + FLAT-for-textured + texel-fidelity fixture; re-bake
         textured goldens. Parallel to 4–6; its D7 gate trigger defers to ADR-0028.
```

**Smallest first slice:** Slice 1 — land `texture_mode` + the standalone `texture-capable(glb)` predicate as a glTF-JSON reader. It creates the declared intent the whole arc gates against, makes the orphan (Failure A) and degenerate (Failure B) cases machine-classifiable *without touching the render path or auto-rig*, changes no bake output, and ships green immediately (default `flat_region` keeps every existing asset valid).

**Biggest risk:** the shared-detector refactor edits *both* production render entry points. Mitigation (already in Slice 1): make `texture-capable(glb)` an **out-of-renderer** predicate, so Failure B closes without that refactor and the in-renderer detector becomes a nicety, not the load-bearing gate input. Secondary risk: shipping the Slice-3 gate *before* the Slice-2 preserve fix hard-blocks every in-flight textured delivery — keep the order.

---

## 7. Locks to resolve before implementation (from the consistency/gap critic)

These were surfaced by an adversarial critic over the ADR set. The clear factual contradictions are **already fixed** in the ADRs/spec; the rest are decisions to lock during Slice 1–2:

| # | Lock | Resolution |
|---|---|---|
| C1 | `texture_mode` enum mis-stated as `{flat/textured/uv_repaired}` | **Fixed** — enum is `{flat_region, textured}`; `uv_repaired` is a provenance bool. |
| C5 | bare `crouch` in spec; `death` gated by ADR-0031 but not in `ENGINE_CLIP_VOCAB` | bare `crouch` **fixed** in spec; `death` is the **PREREQ** above — add to vocab or stop gating it. |
| D/C11 | three ADRs promote-to-error on **different triggers** (`has_tex` vs `texture_mode==textured`) | **Fixed** — pin to `texture_mode==textured` (ADR-0032 D7 now defers to ADR-0028). |
| C3/C11 | ADR-0029 raw bool named `textured` is `true` for the flat pirate (== `has_tex`) — a cross-repo trap | **Lock:** rename raw bool `has_bound_tex`; expose derived `real_albedo = has_tex && !flat_fallback` as the engine-facing field. |
| C2 | richness floor `>30` vs `>=30`; name `atlas_color_richness` vs `atlas_colour_rich` | **Lock:** pin one comparison + one identifier before writing the gate test. |
| C4 | ADR-0030 CALIB background-distance cites `PREVIEW_BG_RGB`, but the bake bg is **transparent** | **Lock:** measure separation against the alpha-key, not the preview tint. |
| C6 | ADR-0026 Context overstates the schema as "documents the opposite of the truth" | **Lock:** rebase to the actual `external_asset.schema.json:37` text (already ~reconciled); keep the still-correct loose-path caveat. |
| C10 | engine-visible result of a **waived** flat-textured asset is unspecified | **Lock:** the waiver (0028/0031) and the albedo signal (0029) must agree on what the engine does. |
| — | `18` vs `19` degenerate pirate materials across docs | **Lock:** pin the canonical count (one material is non-degenerate) before acceptance tests assert it. |

Producer-spec hardness (advisory → tighten in Slice 1–3): add the explicit distinct-colour richness threshold + command to the self-verify pass bar; name the numeric front≠back distinctness test; either add an island-overlap probe or drop the unfalsifiable claim; enumerate which archetypes require which clips; add an `.obj + texture_mode:textured` front-door rejection.

---

## 8. Handoffs

| Handoff | For | Contains |
|---|---|---|
| [`../handoffs/model_producer_delivery_spec.md`](../handoffs/model_producer_delivery_spec.md) | the **model-producer AI** | the standalone, machine-checkable spec to deliver a fully animated, skinned, hit-boxed model that bakes to a sprite — the contract that closes the gap at the source. |
| [`../handoffs/pipeline_hardening_brief.md`](../handoffs/pipeline_hardening_brief.md) | the **pipeline-hardening chat** | Epic A backlog (ADR-0026/0027/0028/0029/0032), ordered by slice. |
| [`../handoffs/verification_subsystem_brief.md`](../handoffs/verification_subsystem_brief.md) | the **verification chat** | Epic B backlog (ADR-0030/0031), the calibration oracle + mutation harness + per-archetype fixtures. |
| [`../handoffs/engine_team_brief.md`](../handoffs/engine_team_brief.md) | the **engine team** (read-only repo) | the `proxy_color` tint that washes textured sprites; the `real_albedo` provenance field the engine reads; re-vendoring once textured deliveries land. |

---

## 9. Definition of done (whole arc)

Implemented when: (1) every package declares a schema-valid `texture_mode`; (2) `texture-capable(glb)` is computed once and in the build log; (3) a `textured` package that is not capable or bakes flat is `ok=false` on both render paths + at intake, unless an audited waiver downgrades exactly that code; (4) auto-rig provably preserves bound texture+UVs or the bake fails; (5) `manifest.provenance.texture` records `has_bound_tex` + `real_albedo` + UV coverage + per-image sha256, gated for consistency; (6) a per-archetype calibration fixture + oracle bakes green every commit and a mutation harness proves each detector fires; (7) `verification_report.json` aggregates modeling/skinning/animation/hitbox with load-bearing severities driving `ok`, and ADR-0025's per-region AABBs are emitted and gated. **Acceptance:** a deliberately-broken input of each of the four shapes turns the build red; `humanoid_textured.glb` + the calibration fixtures stay green.
