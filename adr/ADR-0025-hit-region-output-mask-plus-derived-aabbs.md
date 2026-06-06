# ADR-0025: Hit-region output — keep the per-frame region mask, add per-region AABBs derived from it

- Status: **Proposed — needs cross-repo review** (engine + pipeline; this aligns the pipeline to two
  *Accepted* engine ADRs but adds a real pipeline deliverable + reopens the region-source question)
- Date: 2026-06-06
- Blocks: M3 controlled real variants (hit detection); the roadmap "hitmask status" Phase-0 item
- Supersedes: none
- Related: pipeline ADR-0006 (topmost-surface mask semantics), ADR-0008 (rig-bound hit proxies),
  ADR-0014 (hit-test scale); **engine** ADR-028 (precision hit-regions north-star), **engine ADR-029
  (hit regions rig-derived — Accepted), engine ADR-030 (mask + derived AABBs — Accepted)**, engine
  ADR-026/031 (v1 single collider), engine ADR-032 (mask-sampling for occlusion); `docs/pipeline_hardening_roadmap.md`
  (`core`/hitmask findings, "Beyond the 83": *hitmask consumed by nothing*).

## Context

This started from a concrete question: *"for pixel-perfect projectile collision against the sprite, do
we need a hit mask per animation frame?"* Tracing it surfaced a gap between what the pipeline bakes and
what the engine has **already decided** to consume.

### What the pipeline emits today
- A per-`(state, frame, direction)` **R8 region-ID mask** — a second flat-shaded render pass through the
  identical camera/pose as the color frame, mapped to region ids `{none 0, head 1, torso 2, arms 3,
  legs 4}` (`blender_render_anim.py` region pass; `bake.py` numpy path). One mask tile per animation
  frame, packed into `hitmask_atlas.png`.
- Per frame the manifest carries `rect` and `mask_rect` (`sprite_manifest.schema.json` frames require
  both). **`mask_rect` today == the whole-frame tight-crop rectangle** (shared with the color `rect`) —
  i.e. a single whole-silhouette box, **not** per-region boxes.
- Region id per pixel comes from the **material NAME** (`constants.region_for_name`), not from the bone
  hierarchy. The rig profiles carry a `region_by_bone` map that is **currently inert** (roadmap finding
  `region-by-bone-inert`).

### What the engine has ALREADY decided (both Accepted)
- **Engine ADR-029 (Accepted):** hit regions are **rig-derived in the render pass** — "render the model
  with each part flat-shaded in its region identifier, through the identical camera, yaw, and posed
  frame as the sprite." *This is exactly the pipeline's region pass.* So per-frame masks are the
  **chosen mechanism**, not waste. It requires "every vertex assigned to exactly one region
  (default-derivable from the bone hierarchy)."
- **Engine ADR-030 (Accepted):** emit **both** from that one pass — the **region-ID mask** (primary,
  lossless, occlusion-correct via the bake z-buffer) **and per-region AABBs derived FROM the mask** —
  and carry both in the manifest **per frame**. **The engine reads the AABBs by default (v1).**
  Mask-sampling (per-pixel) is **reserved** for poses/mechanics where geometry occludes a lethal region
  (engine ADR-032), switched on by the consumer, **never by re-baking**. The boxes MUST be derived
  *from* the mask (one source of truth; machine-checkable).
- **Engine ADR-026/031:** v1/MVP reads a **single whole-body collider**; per-region is the next step;
  pixel-mask sampling is the north-star (ADR-028/032). Regions must **partition a solid silhouette with
  NO gaps** (precision = small regions, not empty space between limbs).

### The verified reality (today)
- The engine consumes **neither** the mask nor any AABBs yet: `grep -rn hitmask crates/**/*.rs` → **zero
  hits**; the sprite loader references `color` and never `hitmask`. So the hitmask is **unimplemented on
  the consumer, not unwanted** — engine ADR-029/030 are the spec for wiring it.
- **The gap:** the engine's *default* read is **per-region AABBs**, and the pipeline **does not emit
  them**. It emits the mask + a single whole-silhouette `mask_rect`. So even when the engine wires
  ADR-031, there is nothing for it to read at the per-region level.

## Decision (proposed, pipeline-side)

Align the pipeline output to engine ADR-029/030. Concretely:

1. **Keep baking the per-`(state,frame,direction)` R8 region mask.** Engine ADR-030 mandates emitting
   it (cheap per variant; the occlusion-correct primary per pipeline ADR-0006). **Do NOT drop per-frame
   masks** — an earlier instinct to replace them with skeleton capsules is *rejected* below; the engine
   already weighed and rejected hand-authored/capsule hitboxes (ADR-029 "parallel art-volume, drifts").
2. **Add per-region AABBs DERIVED FROM the mask**, per frame, to the manifest — the field the engine
   reads by default (ADR-030). For each frame: for each region id present, the tight screen-space AABB
   of that region's mask pixels. Machine-checkable: every AABB bounds exactly its region's mask pixels.
3. **v1 single-collider is already satisfiable.** The whole-silhouette `mask_rect` already present is
   the single broad-phase body box engine ADR-026/031 reads for v1; the per-region AABBs are additive
   and ride the same pass — so this is forward-compatible, not a v1 blocker.
4. **Reserve mask-sampling for occlusion (ADR-032), do not make it the default.** Pixel-perfect point
   tests stay a switchable consumer path; the default hit is box-based.

## On the original question (pixel-perfect projectile collision) — resolved

- **Pixel-perfect *hit / no-hit* (silhouette)** is the **color alpha**, already baked per frame — no R8
  mask needed for that.
- **Pixel-perfect *which body part*** needs the per-frame R8 mask — but per engine ADR-030 that is
  **reserved**, not the default. The default hit path reads **AABB boxes** (cheap, predictable,
  broad-phase / AoE friendly, and they *partition with no gaps* per ADR-028 so projectiles can't thread
  limb gaps).
- **Iso-depth caveat (open, cross-repo):** the mask and its AABBs are **screen-space**; iso depth
  **ignores height** (ADR-0018), so a projectile flying *over* a character can screen-overlap its torso
  pixels. A pixel/screen test alone would mis-resolve that; world-space resolution (height-aware) does
  not. *How the engine's AABB hit test reconciles screen-space region boxes with world height is an open
  question for the review* (see below) — it is the strongest reason mask-sampling is reserved, not
  default.

## Alternatives considered

- **Drop per-frame masks; do hit detection from runtime skeleton capsules (`hitbox_v1`).** *Rejected* —
  contradicts the engine's Accepted ADR-029 (the rig-derived render-pass mask is the chosen mechanism;
  hand-authored/posed capsules are a parallel art-volume that drifts from the animation) and ADR-030
  (the mask is reserved for occlusion). Recorded here because it is the intuitive "cheaper" option and
  the review should see it was already weighed and rejected upstream.
- **Mask only (no AABBs).** Rejected by engine ADR-030: pays per-pixel sampling for v1's label mechanic
  and loses cheap broad-phase / AoE.
- **Boxes only (no mask).** Rejected by engine ADR-030: forecloses the occlusion mechanic (ADR-032)
  without a future re-bake of every variant.

## Open questions for the review group (cross-repo — the "good review")

1. **Region source: material-name vs bone-derived.** Engine ADR-029 says regions are "default-derivable
   from the bone hierarchy"; the pipeline assigns by **material name** and `region_by_bone` is inert.
   Keep material-name (simple, works for the current deliveries) but make `region_by_bone` authoritative
   when present? Or switch to bone-derived as the source of truth? (This also bears on the
   *partition-with-no-gaps* requirement: material/part regions can leave gaps between limbs; ADR-028
   forbids gaps.)
2. **Partition-with-no-gaps (ADR-028).** Does the current per-part region render actually *tile* the
   silhouette, or can it leave inter-limb gaps a projectile could thread? If gaps are possible, we need a
   gap-fill / nearest-region rule + a gate.
3. **Z-occlusion correctness (ADR-030 / pipeline ADR-0006).** ADR-030 relies on "the bake z-buffer makes
   the nearest part own each pixel." Does the Workbench region pass z-resolve so an arm in front of a
   torso wins the pixel? Add an occlusion gate (the roadmap found none: `occlusion-pass-and-gate-missing`).
4. **Screen-space regions vs world height (the iso-depth caveat above).** How does the engine's box hit
   test handle a projectile whose height differs from the body it screen-overlaps?
5. **Manifest shape + schema** for per-frame per-region AABBs (where they live; how addressed alongside
   `rect`/`mask_rect`/`page`).
6. **Variant-count storage budget (engine ADR-030 caveat).** Mask is cheap per variant but total scales
   with baked-variant count; record the measured total and the revisit threshold.
7. **Single whole-body collider for v1:** derive from the silhouette `mask_rect`, the color alpha, or the
   union of region AABBs?

## Consequences

- **+** Closes the concrete gap: the engine's default read (per-region AABBs) becomes available, so
  wiring engine ADR-031 needs no pipeline change or re-bake.
- **+** Keeps the (already-baked) mask for the occlusion north-star (ADR-032) — no re-render later.
- **+** One source of truth: AABBs derived from the mask can never disagree with it (gateable).
- **−** Adds a pipeline step (AABB derivation), a manifest field, and two gates (AABB⊆mask consistency;
  occlusion correctness). Manifest grows modestly.
- **−** Until the engine implements ADR-031, the hit data remains **aligned but dormant** (consumed by
  nothing) — this ADR makes the seam correct, it does not make hit detection live.

## Acceptance criteria (when built)

```text
Each manifest frame carries a region-ID mask reference (mask_rect/page) AND per-region AABBs.
Every per-region AABB bounds EXACTLY the mask pixels of its region id (derived-from-mask, verifiable).
Region ids partition the silhouette with no gaps (ADR-028); a gate proves no inter-region holes.
The region mask is occlusion-correct (nearest part owns each pixel); an occlusion gate covers the
  arm-over-torso / (later) shield-over-torso cases (ADR-0006).
The v1 single-body collider is derivable from the frame without per-region data.
Total mask storage for the current variant set is measured and recorded.
forward/up/anchor parity with the color frame is preserved (regions share the projection path).
```

## Pipeline work-list (for the implementer, once reviewed)

1. In `bake_animated` (Blender) and `bake_character_anim`/`_bake_mesh_character` (numpy), after the
   region arrays are computed per frame, derive per-region screen-space AABBs (tight bbox of each region
   id's pixels, in the frame-local then atlas coordinate space) and attach them to `frames[]`.
2. Extend `sprite_manifest.schema.json` with the per-frame per-region AABB field.
3. Add a CI gate: each region AABB exactly bounds its region's mask pixels (consistency), and the
   regions partition the silhouette with no gaps.
4. Decide + implement the region source (material-name vs `region_by_bone`) per open question 1; if
   bone-derived, make `region_by_bone` live (it is currently inert).
5. Verify/repair z-occlusion in the region pass + add the occlusion gate (open question 3).
6. Record total mask storage in the build log / provenance (open question 6).
