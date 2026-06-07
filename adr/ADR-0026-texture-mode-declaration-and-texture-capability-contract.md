# ADR-0026: Texture-mode declaration and the texture-capability contract

- Status: Proposed
- Date: 2026-06-07
- Blocks: a trustworthy "textured creature" delivery (ogre/dragon/pirate retexture); the fidelity gate (ADR-0028) that must reject a textured-but-flat bake
- Related: ADR-0024 (color variations — textured base color is the *baked-in identity* path that runtime tint sits on top of), ADR-0025 (region mask is a second flat pass, independent of the color pass this ADR governs), ADR-0027 (auto-rig preservation — the auto-rig is the L2 mechanism that strips UVs/replaces materials, so a `textured` declaration is meaningless unless ADR-0027 preserves them), ADR-0028 (fidelity gate — the *consumer* of the `texture-capable(glb)` predicate defined here), ADR-0029 (provenance — records the measured predicate result per bake); `docs/texturing_the_body.md`. Engine-side: this affirms the renderer's existing TEXTURE-vs-MATERIAL split (`blender_render.py:147`) — no engine change.

## Context

A "textured creature" delivery is currently accepted, baked green, and ships **flat** — the texture art never reaches a pixel. Parsing the delivered glbs + reading the atlases established the ground truth (do not re-investigate):

- **ogre + dragon glbs are GEOMETRY-ONLY**: 0 materials, 0 textures, 0 images, and **zero UVs** (no `TEXCOORD_0`) on every primitive. Their `*_texture_atlas.png` sidecars are bound to nothing — **orphans**. `green_ogre_v1_materials.json` is a **LIST** of `{name, region, base_color, surface, texture}`; the `texture` field names the orphan atlas but no glb consumes it.
- **red_ball glb**: 1 mesh, 0 UVs, 0 binding. Orphan atlas.
- **pirate_v2 glb**: 1 mesh, 19 region-keyworded materials, **all 19 carry `baseColorTexture`** bound to 1 embedded atlas — **but** all 37 primitives have **DEGENERATE UVs collapsed to a single point**, each pinned to the centre of its swatch-grid tile (visible as the `uv_center_gltf` field in `pirate_duelist_v2_materials.json`, a **DICT** keyed by material name). Each material therefore samples exactly **one texel** → one flat colour per part. "Flat colour via texture."
- **KNOWN-GOOD baseline** `humanoid_textured.glb`: 1 mesh, 4 region materials, `baseColorTexture` bound, **UVs spanning area 0.40–0.92** — a real unwrap. This is the shape a correct textured delivery must match; it is the fixture the TEXTURE-pass gate (`test_texture_pass.py`) already bakes.
- The committed `*_texture_atlas.png` are **flat placeholders** (pirate = labelled swatch grid; dragon/ogre = noise/tiling fill), **not painted art**. Detailed painted atlases may exist but are (a) bound into no glb and (b) unusable because the models have no real UVs.

**Why a green-lit flat bake ships today** (the four root-cause layers):

- **L0** — geometry-only mesh + orphan atlas (ogre/dragon/ball): nothing to sample.
- **L1** — degenerate UVs (pirate): bound texture, but every island is a point.
- **L2** — the auto-rig (`rig_from_profile.py`) **replaces every part material with a flat per-region colour, strips UVs/vertex-colours, and never reads the texture** — and **crashes on the pirate dict-shaped `materials.json`**. (Fixed by ADR-0027; called out here because it can manufacture an L0/L1 condition even from a good delivery.)
- **L3** — the renderer is texture-*capable*: it takes the TEXTURE branch **iff `has_tex`** (`blender_render.py:78,147`, where `has_tex = any material with a TEX_IMAGE node carrying an image`), else MATERIAL. It is only ever as good as its input.
- **L4** — **no gate.** The UV diagnostic exists (`_diag_glb_uvmesh.py` already computes per-material UV bbox extent and flags `degenerate_uv` when `max(Δu, Δv) < 1e-4`), but degenerate UV is a **non-aborting WARN**, and `build_log` only flips `ok=false` on `severity=error`. A textured-but-flat bake is therefore **green**.

The current contract makes this unavoidable in two places:

1. `external_asset.schema.json` has a `textures` block whose description says base color is *"RECORDED but NOT rendered… OBJ deliveries render a flat per-region color"* — a **stale caveat**: an embedded-glb `baseColorTexture` **DOES** render (the TEXTURE branch). The schema documents the opposite of the truth and offers **no way to declare textured intent**, so there is nothing for a gate to check against.
2. `lint_external_asset.py` checks only that `textures.*` **files exist** (line 47–49) — an orphan atlas that exists on disk **passes the linter**. Existence is not binding.

There is no field that says "this asset is meant to be textured," and therefore no machine-checkable definition of what "textured" *requires*. Without that declaration, flat and textured are indistinguishable to every gate, and the worst outcome — a textured-*looking* delivery that bakes flat — is the silent default.

## Decision

### 1. Add a `texture_mode` field to the asset contract

Add `texture_mode ∈ {flat_region, textured}` to **both** `external_asset.schema.json` (the producer's front door) and `source_asset.schema.json` (the internal descriptor). It declares **intent**, and intent is what a gate is checked against.

- **`flat_region`** (default when omitted — back-compatible): the asset is shaded by per-region base colours, the existing path. The `materials.json` `base_color` / `base_color_factor` per region is authoritative; the renderer takes the MATERIAL branch. Cow, ball, and **ogre/dragon in their pre-texture state stay VALID** — declaring `flat_region` is honest and passes. A `*_texture_atlas.png` sidecar MAY persist as human reference but binds nothing.
- **`textured`**: the asset's colour comes from a base-colour image **bound in the glb**. `textured` is **VALID only if `texture-capable(glb)` holds** (predicate below). Declaring `textured` is a **promise the gate enforces** — a false promise is an **error**, not a warning.

### 2. The `texture-capable(glb)` predicate (precise + machine-checkable)

`texture-capable(glb)` is **TRUE** iff, for the imported mesh set, **BOTH** hold for **every** part-mesh:

**(A) Real UV unwrap — not collapsed, in-range.** For each material `mi` on a mesh, gather the UV coords of all loops with `material_index == mi`, and require:

- the UV bounding box is **non-degenerate**: `max(Δu, Δv) ≥ ε_uv` with **ε_uv = 1e-3** (one order looser than the existing `1e-4` diagnostic floor, so a barely-spread point still fails); AND
- the per-material UV-bbox **area** `Δu · Δv ≥ ε_area`, **ε_area = 1e-4** (rejects a thin-line unwrap that has extent on one axis only — the degenerate-but-stretched case a single-axis check misses); AND
- islands lie within `[0,1]` (with a small bleed tolerance, `−ε_uv ≤ u,v ≤ 1+ε_uv`) so the bound atlas is actually addressed, not sampled off-canvas.

This is the existing `_diag_glb_uvmesh.py` computation **promoted from a diagnostic print to a checked predicate**, with the area term added and the threshold raised to ε_uv.

**(B) Base-colour image BOUND IN THE GLB.** For each material that owns a region, a `baseColorTexture` resolves to an **embedded image** in the glb (i.e. a material node graph with a `TEX_IMAGE` node carrying a non-null `image` — exactly the renderer's existing `has_tex` test, `blender_render.py:78`). A loose `*_texture_atlas.png` referenced only by a `materials.json` `texture`/`texture_atlas` field, with **no glb binding**, does **not** satisfy (B): it is an **ORPHAN** and is **REJECTED** for `textured`.

The predicate output is a structured record `{texture_capable: bool, per_mesh: [{mesh, has_bound_tex, degenerate_materials:[...], offcanvas_materials:[...]}], reason}` so ADR-0028 can gate on it and ADR-0029 can record it.

Note the predicate cleanly classifies every real delivery: ogre/dragon/ball **fail (B)** (orphan, no binding — also fail (A), no UVs); pirate **passes (B), fails (A)** (bound texture, point-collapsed UVs → `max(Δu,Δv) ≈ 0 < ε_uv`); `humanoid_textured` **passes both** (area 0.40–0.92 ≫ ε_area, bound checker).

### 3. Orphan atlas is rejected for `textured`, allowed only as reference

A `*_texture_atlas.png` that is not bound in the glb is an **orphan**. Under `textured` it is a **hard reject** (fails (B)). Under `flat_region` it is **tolerated as non-authoritative human reference** and MUST NOT be presented as the render source. The linter stops treating mere file-existence as sufficient: for `textured`, the producer must also satisfy the binding check (deep glb checks run at bake; the linter does the shallow part it can — see work-list).

### 4. Reconcile the stale `textures` caveat in the schema

Rewrite the `external_asset.schema.json` `textures` description: an **embedded-glb `baseColorTexture` base colour DOES render** (TEXTURE branch). Keep the honest part of the caveat — `normal`/`roughness`/`metallic` are still **RECORDED but NOT rendered** this iteration (the renderer is 2D unlit; ADR-0024/ADR-0020 territory). State that the rendered base colour for a `textured` asset comes from the **glb-bound** image, and that loose `textures.base_color` paths are reference/provenance, not the render source.

## Consequences

### Positive

- A textured-but-flat bake becomes a **declared, machine-detectable contract violation** instead of a silent green ship. Intent (`texture_mode`) is finally separable from outcome, so a gate (ADR-0028) has something to check.
- **One predicate, three consumers**: ADR-0028 gates on `texture-capable(glb)`, ADR-0029 records it, the renderer's `has_tex` is its (B) half. No new bespoke logic — the UV math already exists in `_diag_glb_uvmesh.py` and the binding test is the renderer's own `has_tex`.
- **Flat creatures stay first-class.** `flat_region` is the default; cow/ball/pre-texture ogre/dragon validate honestly with zero rework. No forced retexture.
- The schema stops lying: the `textures` caveat matches what the renderer actually does.
- Orphan atlases can no longer masquerade as delivered texture — existence-only acceptance is closed.

### Negative

- The full predicate (UV bbox per material, embedded-image resolution) needs the **glb parsed** — it runs at bake/intake (Blender or a glTF reader), not in the no-Blender front-door linter. The linter can only do the shallow half (declaration present, sidecar-vs-binding sanity); the binding/UV truth is a bake-time gate.
- Producers who shipped a loose painted atlas + UV-less mesh must now **either** rebind+unwrap (to keep `textured`) **or** down-declare to `flat_region`. This is correct but is real migration work for ogre/dragon/pirate.
- Two thresholds (ε_uv, ε_area) are tunable knobs; a too-tight value could reject a legitimately small but real island. Mitigated by choosing ε deliberately looser than the point-collapse floor and recording the measured per-material extents in provenance (ADR-0029) so a false reject is diagnosable.

## Alternatives considered

- **Infer textured-ness, no declaration.** Treat "has a bound texture" as the whole truth and skip `texture_mode`. *Rejected*: this is exactly today's `has_tex` behavior, and it green-lights the **pirate** (bound texture, degenerate UVs) — a flat bake that *looks* textured to the renderer. Without a declared intent there is no way to assert "you promised textured, deliver real UVs." Declaration is what makes (A) enforceable.
- **UV check only (drop the binding requirement (B)).** *Rejected*: passes the **orphan** case (ogre has — would have — UVs but no binding) and lets a loose atlas pose as the source. Binding is the other half of "the pixels actually come from the art."
- **Binding check only (drop the UV requirement (A)).** *Rejected*: passes the **pirate** — bound texture, one texel sampled per part. Flat colour laundered through a texture. Both halves are load-bearing; each alternative is defeated by exactly one real delivery.
- **Keep degenerate-UV a WARN, just make it louder.** *Rejected*: severity, not volume, is the bug — `build_log.ok` only flips on `severity=error`, so any non-error ships green (L4). The fix is to make a broken `textured` promise an **error**, which requires the declaration to break the promise *against*.
- **Single ε on `max(Δu,Δv)` only** (the existing `1e-4` line). *Rejected as insufficient*: a unwrap collapsed to a **thin line** (extent on one axis, ~0 on the other) passes a max-extent test but samples a 1-D strip of texels — still effectively flat. The **area** term (ε_area) closes it.
- **OBJ/loose-atlas textured path.** *Rejected for this iteration*: the contract binds `textured` to the **embedded-glb** base colour, matching the only path the renderer supports (TEXTURE branch reads the glb's bound image). OBJ stays `flat_region`. Revisit only if a loose-atlas render path is ever built.

## Acceptance criteria (each assertable by a CI test)

```text
SCHEMA
- external_asset.schema.json and source_asset.schema.json both define texture_mode
  with enum exactly {flat_region, textured}; omission defaults to flat_region.
- external_asset.schema.json `textures` description no longer claims base_color is
  "RECORDED but NOT rendered"; it states embedded-glb baseColorTexture renders, and
  normal/roughness/metallic remain recorded-not-rendered.

PREDICATE texture-capable(glb)  (one source of truth; ADR-0028/0029 consume it)
- Returns a structured {texture_capable, per_mesh[...], reason} record.
- TRUE for examples/texture_starter/humanoid_textured.glb (real unwrap area 0.40-0.92,
  bound checker base color).
- FALSE for the pirate_duelist_v2 glb: (B) holds (19 bound baseColorTextures) but (A)
  fails -- every primitive's per-material max(Δu,Δv) < ε_uv (point-collapsed). reason
  cites degenerate_uv.
- FALSE for the ogre/dragon/red_ball glbs: (B) fails -- 0 bound baseColorTexture
  (orphan sidecar); reason cites orphan_atlas / no_binding (and no_uv for A).
- (A) thresholds: a material with max(Δu,Δv) < 1e-3 OR area Δu·Δv < 1e-4 fails;
  a material whose UVs exceed [0,1] beyond ε_uv bleed fails (offcanvas).
- (B): a material satisfies binding iff it resolves a baseColorTexture to an embedded
  glb image (== the renderer's has_tex test, blender_render.py:78). A materials.json
  `texture`/`texture_atlas` path with no glb binding does NOT satisfy (B).

GATE BEHAVIOR (the contract this ADR sets up; enforced in ADR-0028)
- An asset declaring texture_mode=textured for which texture-capable(glb) is FALSE is
  an ERROR (build_log.ok == false), not a WARN. (Regression test: a fixture that is
  textured-declared + degenerate fails the build; flipping it to flat_region passes.)
- An asset declaring texture_mode=flat_region (or omitting it) with an unbound
  *_texture_atlas.png on disk still passes -- the sidecar is tolerated as reference.

MISS-FLAT-CREATURES-STAY-VALID
- cow / ball / pre-texture ogre / pre-texture dragon, declared flat_region, validate
  and bake green with no texture binding and no UVs.
```

## Implementer work-list

Consolidates backlog stories: **declare-texture-mode**, **contract-textured-intent**, **gate-textured-requires-bound-tex-uv**, **kill-orphan-texture-atlas**, **miss-flat-creatures-stay-valid**.

1. **declare-texture-mode / contract-textured-intent** — Add `texture_mode` (`enum {flat_region, textured}`, default `flat_region`) to `pipeline/schema/external_asset.schema.json` and `pipeline/schema/source_asset.schema.json`. Update `docs/external_asset_contract.md` + `docs/texturing_the_body.md`.
2. **Reconcile the stale caveat** — Rewrite the `textures` block description in `external_asset.schema.json` per Decision §4 (embedded-glb base colour renders; normal/roughness/metallic still recorded-not-rendered; loose paths are reference).
3. **gate-textured-requires-bound-tex-uv** — Promote `_diag_glb_uvmesh.py` from a diagnostic into a reusable predicate `texture_capable(glb) -> record` (add the ε_area area term + the `[0,1]` off-canvas check; reuse the renderer's `has_tex` node test for (B)). Have the bake path call it whenever `texture_mode=textured`.
4. **Wire the gate (hand-off to ADR-0028)** — Make a failed `textured` predicate raise `severity=error` so `build_log.ok` flips false (close L4). Record the structured predicate record in the build log (hand-off to ADR-0029).
5. **kill-orphan-texture-atlas** — In `lint_external_asset.py`, replace existence-only handling (lines 47–49) for `textured` assets: a `*_texture_atlas.png` with no declared glb binding is flagged orphan (front-door warning; the binding truth is the bake-time gate in step 3). Under `flat_region` keep it tolerated as reference.
6. **miss-flat-creatures-stay-valid** — Add fixtures/regression tests proving: (a) `humanoid_textured` passes the predicate; (b) a textured-declared degenerate fixture (pirate-shaped) is an error, and flipping it to `flat_region` passes; (c) cow/ball/ogre/dragon declared `flat_region` bake green. Extend `test_texture_pass.py` to cover the FALSE branches, not only the PASS branch.
7. **Cross-ADR seam** — ADR-0027 must guarantee the auto-rig (`rig_from_profile.py`) does **not** strip UVs / replace bound materials on a `textured` asset (else it manufactures an L0/L1 failure from a good delivery); ADR-0028 consumes the predicate as its gate; ADR-0029 records the predicate record per bake.
