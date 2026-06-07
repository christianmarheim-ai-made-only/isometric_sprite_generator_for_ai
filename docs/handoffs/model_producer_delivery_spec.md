# Model Producer AI — Delivery Spec for `game_iso_v1` Sprites

- Status: Proposed
- Date: 2026-06-07
- Supersedes: `docs/modeling_the_body.md`, `docs/texturing_the_body.md`, `docs/external_asset_contract.md` (this document **consolidates and tightens** all three into one authoritative producer spec; those remain as background tutorials, but where they conflict with this document, **this document wins**)
- Related: ADR-0006 (topmost-surface region mask), ADR-0008 (source-asset separation + hit proxies), ADR-0024 (effects layering + `core` anchor + fat-body orbit rule), ADR-0025 (per-frame region mask + derived AABBs); the new producer-facing ADRs **ADR-0026 … ADR-0032** (per-rule citations inline below); engine ADR-029/030 (rig-derived region pass + AABBs, both Accepted); engine ADR-044 (clip vocabulary). Gold-standard worked example: the **color-coded CALIBRATION model (ADR-0030)**.

---

## Context

You are an AI (or human) that **produces a 3D model**. This pipeline turns that model into a `game_iso_v1` sprite package: a 16-direction color atlas + an R8 per-region hit-mask + a manifest. You do **not** produce sprites. You produce the **3D source** and a small manifest, and the pipeline bakes it.

The locked target contract `game_iso_v1` is non-negotiable and is **not yours to change**: 2:1 dimetric, azimuth 45° / elevation 30°, 16 directions, forward `+X`, up `+Z`, tile 64×32, per-frame canvas 256², max atlas page 4096px. Everything below tells you how to deliver *into* that contract.

**Why this document exists.** Three earlier docs described the same pipeline, and producers followed them — and still shipped broken deliveries that the pipeline **green-lit anyway**. Verified failures from real deliveries:

- **ogre + dragon**: glbs were **geometry-only** — 0 materials, 0 textures, 0 images, and **zero UVs** on every part. Their `*_texture_atlas.png` files were **orphan sidecars bound to nothing**.
- **red_ball**: 1 mesh, 0 UVs, 0 texture binding — orphan atlas.
- **pirate_v2**: 19 region-keyworded materials, **all** carrying `baseColorTexture` bound to one embedded atlas — but **all 37 primitives had degenerate UVs collapsed to a single point** (each pinned to the centre of one swatch-grid tile). Every material therefore sampled **exactly one texel** → one flat colour per part. A "flat-colour-via-texture" hack that *looks* textured to a shallow check.

None of these was caught at delivery, because the only UV-quality signal in the pipeline (`degenerate_uv`) is a **non-aborting `warn`**, and the build log's `ok` flag only flips false on `severity == "error"`. **A textured-but-flat bake ships green.** This spec closes that by (a) making every acceptance criterion machine-checkable, (b) defining a **self-verify gate the producer runs and must pass before handoff**, and (c) naming the exact anti-patterns above so you recognise and avoid each.

The known-good shape every textured delivery must match is `pipeline/examples/texture_starter/humanoid_textured.glb`: a real unwrap with UV island area spanning ~0.40–0.92, `baseColorTexture` bound on each region material.

---

## Decision

A compliant delivery is a **package** that declares one `texture_mode`, satisfies every per-stage machine-checkable predicate, and **passes the self-verify gate before handoff**. The rest of this document is that contract.

### 1. The Delivery Contract (read this first)

#### 1.1 The file set of a package

You deliver a folder. The mesh is **always** `.glb` (glTF 2.0) for an animated/rigged/textured delivery — `.obj` is permitted **only** for a static, untextured, flat-region body (no rig, no animation, no bound texture). One embedded `.glb` is strongly preferred because it carries mesh + rig + skin + animation + texture in one file with no loose-sidecar ambiguity.

| File | Required? | What it is |
|---|---|---|
| `<variant>.glb` | **required** | The model: one clean triangulated mesh, region-keyworded materials, **UVs + bound `baseColorTexture` if `textured`**, rig + skin + animation clips if animated. The single source of truth. |
| `<variant>.asset.json` | **required** | The manifest (§7). Declares `texture_mode`, `archetype`, `rig`, `geometry`, `animations`, `world_metrics`. Validated by `lint_external_asset.py`. |
| `<variant>_basecolor.png` | required **iff** `texture_mode: textured` **and** you ship the texture as a sidecar instead of embedding | sRGB power-of-two base colour. **A loose sidecar PNG is NOT a binding** — see §1.3. Prefer embedding the image in the glb. |
| `<variant>_hitbox.json` | recommended | Per-region AABBs / collision capsule (ADR-0025; min/max over region vertices). Engine/runtime data; the bake derives the mask itself, but this carries the per-region boxes the engine reads by default. |
| `<variant>_spell_orbits.json` | optional | Orbit/effect anchor rings (ADR-0024). Runtime sidecar; **never consumed by the bake**. Must obey the fat-body radius rule (§6.3). |
| `<variant>_anim.json` | optional | `anim_clips_v1` keyframe JSON, paired via `files.animation_clips` if you author animation as text instead of baking clips into the glb. |

There is **no standalone rig or animation-library file delivery**: clips are embedded in (or paired with) the variant glb, because clips target **bone names** and replay on any mesh skinned to the same rig profile.

#### 1.2 The `texture_mode` declaration (and what each obliges)

Every manifest **must** declare exactly one `texture_mode`. This is the single switch that determines which acceptance bar applies. There is no implicit/default mode — declare it.

| `texture_mode` | What it means | What it obliges (hard) |
|---|---|---|
| `flat_region` | Each region is one flat colour. No UVs, no texture image required. The pipeline renders Workbench MATERIAL mode (flat per-material base colour). | Every material sets a sensible non-grey base colour. Region-keyworded names (§4). **No** texture image needs to be bound. You may ship `.obj` or `.glb`. *(This is what the ogre/dragon/ball SHOULD have declared — flat is honest; orphan atlases pretending to be textured are not.)* |
| `textured` | The model carries a real painted base-colour atlas sampled through a real UV unwrap. The pipeline renders Workbench TEXTURE mode. | **All** of §3 (UV + texture) is mandatory: real per-material UV bbox area > 0, islands in [0,1], a power-of-two sRGB base-colour PNG **bound as `baseColorTexture` on every region material inside the glb**, AO/value baked into albedo. A loose sidecar PNG with no glb binding is **rejected**. Degenerate UVs are **rejected** (not warned). |

The mode you declare is checked end-to-end by the self-verify gate (§7): `texture_mode: textured` ⇒ baked `has_tex == true` **AND** `degenerate_uv` empty **AND** the atlas is colour-rich.

> **Picking a mode.** If you cannot produce a real unwrap + painted atlas, declare `flat_region` and ship honest flat colours. **Do not** declare `textured` and bind an orphan/degenerate atlas — that is the exact failure class this spec exists to stop. `flat_region` is a first-class, fully-supported delivery.

#### 1.3 What "bound" means (the orphan-atlas killer)

A texture is **bound** only when, inside the glb, an Image Texture node feeds the Principled BSDF **Base Color** socket of the material (glTF `material.pbrMetallicRoughness.baseColorTexture` → an `images[]` entry that is **embedded** or referenced and present). A PNG sitting next to the glb, or listed under manifest `textures.base_color` but **not wired into any material**, is an **orphan sidecar** and is treated as **no texture**. The verified failures (ogre/dragon/ball) all shipped orphan atlases. The machine check is in §3 and §7.

#### 1.4 Delivery contract — pass/fail checklist

- [ ] Folder contains `<variant>.glb` and `<variant>.asset.json`.
- [ ] `asset.json` declares exactly one `texture_mode ∈ {flat_region, textured}`.
- [ ] `lint_external_asset.py <variant>.asset.json` exits 0 (schema, files exist, rig is a known profile, animations well-formed).
- [ ] If `texture_mode: textured`: a base-colour image is **bound in the glb** (not a loose sidecar); §3 applies in full.
- [ ] If `flat_region`: every material has a non-default base colour; `.obj` permitted only here.
- [ ] No file in the package is referenced-but-missing and no image is present-but-orphan.

---

### 2. Stage GEOMETRY

Build a single clean mesh, at real metre scale, standing on the ground, facing `+X`, split into region-named parts. (ADR-0026.)

**How to:**

1. **Real scale, in metres.** A 1.8 m human is **1.8 units** tall; a sparrow ~0.22 m. The sprite is sized from real height — wrong scale = wrong on-screen size next to everything else.
2. **Declare the up axis.** Build Z-up (`up: "z"`) or Y-up (`up: "y"`); declare it in `geometry.up`. glTF importers assume Y-up, so a Z-up glb is rotated upright by the bake **only if you declare `up:"z"`** — an undeclared Z-up glb bakes lying down.
3. **Forward = `+X`, declared planar.** Author facing `+X` (direction 0 = the travel/look heading: biped chest/face, bird beak, quadruped nose, dragon jaw). If you author facing another planar axis, **declare `geometry.forward ∈ {+x,-x,+y,-y}`** and the baker rotates it onto `+X`. The correction trusts the **declared** value — if it disagrees with the geometry it still bakes wrong, so declare truthfully.
4. **Origin = ground footprint centre.** Lowest point at `z = 0`; standing footprint centred on `x = y = 0`.
5. **FRONT ≠ back (the rule producers miss).** If the body is symmetric under a 180° turn (centred torso, faceless head, mirrored arms), heading N renders **identical** to heading N+8 — you get only 8 real directions and the engine can't tell front from back. Break it on purpose: a face/visor on `+X`, a chest vs flat back, a snout, a beak+tail. **Exempt:** radially-symmetric props (ball/orb) — near-identical directions are correct; align any directional marker to `+X`.
6. **One clean mesh, region-keyworded parts.** One logical triangulated mesh, no stray/loose/interior geometry. Split into parts named `head / torso / arms / legs` (§4). Tri budget **~300–8 000** total.

**Machine-checkable checklist (GEOMETRY):**

```text
# Inspect bounds/orientation:
blender --background --python pipeline/tools/_diag_glb_bounds.py -- <variant>.glb
```
- [ ] **Scale:** measured mesh height (`DIAG ... dims` Z extent, or the declared-up extent) equals real metres within ±25% of `world_metrics.height_world` (the bake's `world_metrics_mismatch` is a hard **error** above 25%).
- [ ] **Up axis declared** and the `tallest=` axis from `_diag_glb_bounds.py` matches the declared up (Z-up ⇒ tallest=Z; Y-up ⇒ tallest=Y). A biped that bakes landscape trips `non_upright_biped` (hard error).
- [ ] **Forward declared planar:** `geometry.forward ∈ {+x,-x,+y,-y}` and matches the modelled front.
- [ ] **Origin:** min Z ≈ 0 and footprint centred on x=y≈0 (`DIAG ... min/max` straddles 0 in X/Y, min Z ≈ 0).
- [ ] **FRONT ≠ back:** on the baked `*_color_sheet.png`, direction N and N+8 are **visibly distinct** (the direction-distinctness gate). Radial props exempt.
- [ ] **One mesh:** `_diag_glb_uvmesh.py` reports `DIAG_IMPORTED_MESH_COUNT 1` (or cleanly separable region parts), no stray objects.
- [ ] **Region parts:** every part's material name resolves to head/torso/arms/legs via §4 (no fallback-to-torso warnings).
- [ ] **Tri budget:** total triangles in `[300, 8000]`.

---

### 3. Stage UV + TEXTURE — **this is THE gap**

Applies in full when `texture_mode: textured`. (If `flat_region`, skip to §5 — you owe only non-grey per-region base colours.)

The three verified failures all live here: orphan atlases (no binding), and degenerate UVs (binding present, but UVs collapsed to a point so each material samples one texel). The rules below are written to make both impossible to ship green.

**How to:**

1. **Real UV unwrap, per part.** Every part-mesh must have a UV map with a **real** unwrap: cube/box projection on blocky bodies, smart-UV on organic ones. The per-material UV bounding-box **area must be > 0** — i.e. **not** collapsed to a point or a line. The pipeline's degenerate detector flags any material where `max(uv_bbox_width, uv_bbox_height) < 1e-4`; your unwrap must be far above that. **Target the known-good range: per-island UV bbox extent ≈ 0.4–0.9** of UV space (this is what `humanoid_textured.glb` does).
2. **Islands in `[0,1]`, non-overlapping.** All UVs inside the unit square; no overlapping islands between region materials.
3. **Base colour = PNG, sRGB, power-of-two** in `{512, 1024, 2048}` per dimension (W and H may differ, e.g. 1024×2048). This is albedo. The pipeline renders `view_transform = Standard` — sRGB shows as authored.
4. **BIND it in the glb** as `baseColorTexture` on **each** region material (Image Texture → Principled BSDF **Base Color**), then export `.glb` so the image embeds. **A loose sidecar PNG is REJECTED** (§1.3) — listing it under `textures.base_color` without wiring it into the materials does not count.
5. **Keep region-keyworded material names** (§4). You may split into many materials for texturing **as long as every name still contains a region keyword** (`head_skin`, `torso_armor`, `arm_cloth_L`, `leg_boot_R`). Renaming to `skin`/`cloth`/`metal` silently dumps everything into `torso`.
6. **Bake AO/value into albedo.** The render is flat-ish Workbench studio light; paint value contrast, ambient occlusion, and large shading into the base colour. A flat fill looks flat.
7. **Paint for iso scale.** Prioritise silhouette-edge colour, big shapes, and value blocking; detail finer than ~1px on-screen is wasted.

**The exact known-good glb shape to match (`humanoid_textured.glb`):** N region materials, **each** with `baseColorTexture` bound to one embedded atlas, **each** with a real UV island of area ≈ 0.4–0.9, islands inside `[0,1]`, names region-keyworded. Diff your delivery against it.

**Machine-checkable checklist (UV + TEXTURE), required only for `textured`:**

```text
# The producer-side ground-truth probe (same logic the bake uses):
blender --background --python pipeline/tools/_diag_glb_uvmesh.py -- <variant>.glb
#   -> per mesh: "has_tex=True materials=N degenerate_uv=0/N"
#      NO_UV_LAYER  or  degenerate_uv>0  is a HARD FAIL for textured mode.
```
- [ ] **Texture bound:** `_diag_glb_uvmesh.py` reports `has_tex=True` (an Image Texture with an image feeds Base Color on the region materials). Orphan sidecar / unbound PNG ⇒ FAIL.
- [ ] **UV layer present:** no `NO_UV_LAYER` line for any mesh.
- [ ] **No degenerate UVs:** `degenerate_uv=0/N` for every mesh (every material's `max(uv_bbox_w, uv_bbox_h) ≥ 1e-4`; in practice ≈ 0.4–0.9). **Any degenerate material is a reject for `textured`.**
- [ ] **Islands in `[0,1]`**, non-overlapping between region materials.
- [ ] **PNG format:** sRGB, each dimension ∈ `{512,1024,2048}`.
- [ ] **Region names intact:** every textured material's name still resolves head/torso/arms/legs (§4); no `region_fallback_torso`.
- [ ] **Atlas colour-rich:** the painted atlas is not a single flat fill / not a labelled swatch grid (more than a trivial number of distinct colours; AO/value present).

---

### 4. Region naming (shared by GEOMETRY, TEXTURE, HITBOXES)

The gameplay HIT region of every face comes from its **material/part name** (case-insensitive substring), resolved through the single canonical table (`constants.REGION_KEYWORDS`; `mesh_io.region_for_name`). The lowercased name is scanned in this fixed priority order; the **first keyword that occurs anywhere wins**:

| Region (id) | Name contains any of |
|---|---|
| `head` (1) | head, skull, face, neck, beak |
| `torso` (2) | torso, chest, body, spine, hip, pelvis, waist, tail |
| `arms` (3) | arm, hand, shoulder, elbow, wrist, wing |
| `legs` (4) | leg, foot, feet, thigh, shin, knee, ankle |

Priority order is **head < torso < arms < legs**: `forearm` → arms (via `arm`), `armor` → arms (via `arm`). **Avoid names with more than one region keyword.** Unmatched → **torso (2)** with a warning (`region_fallback_torso`). Region 0 = background (never authored). **Regions 5–7 (weapon/shield/gear) have no authoring path this iteration** — do not attempt them; body-only.

Non-anatomical bodies map onto the four regions: a **quadruped's** forelegs → `arms`, hindlegs → `legs`, head/neck → `head`, spine/tail → `torso`. A **dragon's** wings + forelegs → `arms`, hindlegs → `legs`, tail → `torso`, horns/jaw → `head`.

---

### 5. Stage RIG + SKIN

Required only if you ship animation. **Textured models SHOULD ship pre-rigged.** A static (rig-less) delivery is valid — the pipeline animates the biped procedurally — but then you owe only mesh + texture + regions. (ADR-0027.)

**How to:**

1. **Armature with bones named exactly per a rig profile.** Profiles live in `pipeline/schema/rig_profiles/<rig>.json` and carry the required bone names + parents, per-bone bind-pose positions (metres, +Z up, +X forward), a `region_by_bone` map, and the deliverable `states`. The five archetype profiles:

   - **biped_v1:** `root, hips, spine, chest, head, arm.L, forearm.L, hand.L, arm.R, forearm.R, hand.R, thigh.L, shin.L, foot.L, thigh.R, shin.R, foot.R`
   - **bird_v1:** `root, body, neck, head, wing.L, wingtip.L, wing.R, wingtip.R, tail, leg.L, leg.R`
   - **quadruped_v1:** `root, pelvis, spine, chest, neck, head, tail, foreleg.L, foreshin.L, forehoof.L, foreleg.R, foreshin.R, forehoof.R, hindleg.L, hindshin.L, hindhoof.L, hindleg.R, hindshin.R, hindhoof.R` (head/neck +X, tail −X; forelegs→arms, hindlegs→legs)
   - **dragon_v1:** `root, pelvis, spine, chest, neck, head, jaw, horn.L, horn.R, wing.L, wing.R, foreleg.L, foreleg.R, hindleg.L, hindleg.R, tail.1, tail.2, tail.3` (head/jaw +X, tail −X; wings+forelegs→arms, hindlegs→legs, tail→torso, horns/jaw→head)
   - **ball_v1:** `root, body, marker` (directional prop; align `marker` to +X)

2. **Skin the mesh** to those bones — standard glTF skin (joints + weights, **≤4 influences/vertex**). **Every part skinned to a bone; no static unskinned part.**
3. **Neutral bind pose** = the model's rest: biped T- or A-pose, bird wings level, foot/root at origin, facing +X.
4. A variant declaring `rig: "<name>"` **must** use exactly that profile's bone names — this is the key to reuse (one rig + one animation library across the whole archetype).

**Machine-checkable checklist (RIG + SKIN):**

- [ ] **Rig name valid:** `asset.json.rig` matches a profile file in `pipeline/schema/rig_profiles/` (linter enforces).
- [ ] **Bone names exact:** every bone required by the profile is present, named exactly (verified at bake by the Blender baker).
- [ ] **Every part skinned:** no mesh part has zero skin weights; max **4 influences/vertex**.
- [ ] **Bind pose neutral:** rest pose is T/A-pose (biped) / wings level (bird), feet at origin, facing +X.
- [ ] **Textured ⇒ rigged:** if `texture_mode: textured`, the glb carries an armature (SHOULD).

---

### 6. Stage ANIMATION

Animations are glTF 2.0 animation clips embedded in the variant glb (or paired as `anim_clips_v1` JSON via `files.animation_clips`). Each clip = named channels targeting `(bone, path ∈ {translation,rotation,scale}, keyframes)`. (ADR-0028.)

#### 6.1 Clip vocabulary and which regions move

Clip names must target the **engine's canonical vocabulary** (engine ADR-044) or the renderer never selects them and silently falls back to idle:

`idle`, `walk`, `run`, `attack`, `hit`, `jump`, `fall`, and (where the profile lists them) `crouch_idle` / `crouch_walk`. **There is no bare `crouch`** — use `crouch_idle` / `crouch_walk` (this is the exact `ENGINE_CLIP_VOCAB`). A clip named off-vocabulary (`move`/`shoot`/`hurt`/bare `crouch`) bakes fine but is a **dead clip** — the linter warns; rename it. (`death` is **not** in the base vocabulary — it exists only as a synonym target; deliver it only if the target rig profile's `states` explicitly require it.)

The **right regions must move per clip** (no dead motion):

- `idle` — subtle whole-body settle/breath; no foot drift.
- `walk` / `run` — legs swing as the primary read; arms counter-swing; torso bob.
- `attack` — the acting arm(s)/weapon-arm ramps forward; one-shot.
- `hit` — recoil through torso/head; one-shot.
- `jump` / `fall` / `crouch_idle` / `crouch_walk` — legs + torso drive vertical pose change.

#### 6.2 Authoring rules

- **In-place / no root motion:** the cumulative world-space horizontal (X,Y) translation of every bone over a clip must net to ≈0 (within ~1% of `footprint_radius`). Vertical (Z) bob is fine. Locomotion is the game's job.
- **Declare each clip** in the manifest with `frames` (poses sampled per direction), `fps`, and `playback ∈ {loop, once}`. `loop` wraps; `once` holds the last frame (one-shot hit/attack).
- **Loop continuity:** for a `loop` clip, the last pose must transition seamlessly to the first (no snap). Anchor must not drift across the loop (loop-seam/anchor-drift gate).
- **No dead clip:** every clip declared in the manifest must exist in the glb (or be embedded via `files.animation_clips`). A declared state whose clip is absent renders the static rest pose — caught as `missing_clip_rest_pose`.

#### 6.3 Effect/orbit data (optional, ADR-0024)

If you ship `<variant>_spell_orbits.json`, any ring meant to **encircle** the body must obey the **fat-body invariant**: `radius_world ≥ body_half_extent(plane, height) + clearance_radial_world`. A machine-checkable lower bound is the **torso-region AABB** from `<variant>_hitbox.json`: `radius_world ≥ torso_half_extent + clearance`. A ring that deliberately hugs the body must say so in its `note`. This sidecar is **never consumed by the bake**.

**Machine-checkable checklist (ANIMATION):**

- [ ] **Vocabulary:** every clip name ∈ `{idle, walk, run, attack, hit, jump, fall, crouch_idle, crouch_walk}` (no bare `crouch`); linter raises **no** off-vocabulary warning.
- [ ] **All declared clips exist** in the glb (no `missing_clip_rest_pose`).
- [ ] **fps + frames + playback** set per clip; `frames ≥ 1`; `playback ∈ {loop, once}` (linter enforces).
- [ ] **In-place:** net horizontal bone translation per clip ≈ 0 (≤ ~1% footprint_radius).
- [ ] **Loop continuity:** `loop` clips pass the loop-seam / anchor-drift gate (no snap, anchor stable).
- [ ] **Right regions move:** walk/run legs swing; attack arm ramps; idle ≠ a frozen pose — visible on the baked `*_color_sheet.png` column.
- [ ] **No dead clip:** every declared state animates (not the rest pose).

---

### 7. Stage HITBOXES

The R8 per-region hit-mask comes **free** from the region tags (§4): the pipeline renders a second flat-shaded pass through the identical camera/yaw/pose as the colour frame, mapping each face to its region id (ADR-0006; engine ADR-029). You author nothing extra to get the mask — but the regions must tile the silhouette and you should ship the derived boxes. (ADR-0029, engine ADR-030.)

**How to:**

1. **Per-region declarations.** Every face has a region via its material name. Optionally ship `<variant>_hitbox.json` with per-region AABBs (tight min/max over each region's vertices) + a single whole-body collider — the field the engine reads by default (engine ADR-030).
2. **Regions tile the silhouette — no gaps.** Regions must partition a solid silhouette with no inter-limb holes a projectile could thread (engine ADR-028). Precision = small regions, not empty space between limbs.
3. **Per-frame masks for animation.** The mask is per-`(state, frame, direction)` (ADR-0025) — it tracks the animated pose automatically because it shares the projection path with the colour frame.

**Machine-checkable checklist (HITBOXES):**

- [ ] **Regions present:** the baked `*_hit_sheet.png` shows **head=red, torso=green, arms=blue, legs=yellow**, covering the silhouette and tracking the body part underneath.
- [ ] **No fallback:** no `region_fallback_torso` warning (no part silently dumped into torso).
- [ ] **Tiles, no gaps:** regions partition the silhouette (no inter-region holes) — the AABB/mask consistency gate.
- [ ] **Per-frame:** the mask is emitted for every `(state, frame, direction)` (shares `rect`/`mask_rect` with the colour frame).
- [ ] **(If shipped) AABBs derive from mask:** every per-region AABB in `<variant>_hitbox.json` bounds exactly its region's mask pixels.

---

### 8. The asset manifest (`<variant>.asset.json`)

Schema: `pipeline/schema/external_asset.schema.json`. Validated by `lint_external_asset.py`.

```json
{
  "asset_contract_version": "external_asset_v1",
  "variant_id": "sparrow",
  "archetype": "bird",
  "texture_mode": "textured",
  "files": { "mesh": "sparrow.glb" },
  "geometry": { "up": "y", "forward": "+x", "unit": "meter" },
  "rig": "bird_v1",
  "region_source": "material_name",
  "textures": { "base_color": "sparrow_basecolor.png" },
  "animations": {
    "idle": { "clip": "idle", "frames": 1, "fps": 1,  "playback": "loop" },
    "walk": { "clip": "walk", "frames": 4, "fps": 12, "playback": "loop" }
  },
  "world_metrics": { "height_world": 0.22, "footprint_radius_world": 0.12 },
  "notes": "wings named wing.L/wing.R; in-place walk cycle; base color BOUND in glb."
}
```

- `files.mesh` is **required**; `texture_mode` is **required**; `archetype` + `rig` select the shared rig + animation library.
- For `textured`, the base colour must be **bound in the glb** even if also listed under `textures.base_color` (the list alone is not a binding — §1.3).
- Omit `rig`/`animations` for a static `flat_region` mesh (procedural animation).
- `world_metrics` optional (measured from the AABB); provide it to override.

---

## Anti-patterns — why deliveries fail (the real examples we caught)

Read this table before you hand off. Each row is a verified failure that **passed the old checks** and shipped a broken sprite. Recognise the shape and avoid it.

| Asset | Failure layer | What was wrong (verified) | Why it slipped through | Correct delivery |
|---|---|---|---|---|
| **ogre** | L0 geometry-only + orphan atlas | glb had **0 materials, 0 textures, 0 images, 0 UVs** on every part; `ogre_texture_atlas.png` was a sidecar **bound to nothing** (a noise/tiling fill, not painted art). | No gate required a bound texture; an unbound PNG looked like "a texture was delivered." | Declare `texture_mode: flat_region` with honest per-region base colours — **or** add a real unwrap + a base colour **bound** in the glb and declare `textured`. |
| **dragon** | L0 geometry-only + orphan atlas | Same as ogre: geometry-only, zero UVs, orphan `dragon_texture_atlas.png`. `materials.json` carried only a few flat per-region base colours. | Same as ogre. | `flat_region` (honest) or a real bound `textured` delivery; rig to `dragon_v1`. |
| **red_ball** | L0 geometry-only + orphan atlas | 1 mesh, **0 UVs**, no binding; orphan atlas. | Same as ogre. | `flat_region` ball (radially symmetric is fine); rig to `ball_v1`, align `marker` to +X. |
| **pirate_v2** | L1 degenerate UVs (the subtle one) | 19 region-keyworded materials, **all** with `baseColorTexture` bound to one embedded atlas — **but all 37 primitives had UVs collapsed to a single point**, each pinned to the centre of one swatch-grid tile. Each material sampled **one texel** → one flat colour per part. A "flat-colour-via-texture" hack. | `has_tex` was true and the binding existed, so a shallow check passed; `degenerate_uv` is only a non-aborting **`warn`**, and `ok` flips false only on `severity == "error"` — **so the flat-via-texture bake shipped green.** | A real unwrap: per-material UV bbox area > 0, islands ≈ 0.4–0.9 in `[0,1]` (match `humanoid_textured.glb`). The §3 + §7 gate **rejects** degenerate UVs for `textured`. |
| *(general)* L2 auto-rig hazard | — | The pipeline's `rig_from_profile.py` auto-rig **replaces** every part material with a flat per-region colour, strips UVs/vertex-colours, never reads the texture, and **crashes on dict-shaped `materials.json`** (pirate). | A geometry-only delivery that relies on auto-rig loses any texture and may not bake at all. | **Ship pre-rigged** (§5) so auto-rig never runs; keep materials list-shaped + region-keyworded. |
| *(general)* L4 no gate | — | `degenerate_uv` = WARN; `build_log.ok` only false on `error`. So a textured-but-flat bake is green-lit. | The very reason this spec adds the self-verify gate below. | Run the self-verify gate (§ below) and meet its pass bar; it elevates the textured-mode UV/binding checks to **delivery-blocking**. |

**The one-line rule:** if you cannot deliver a real unwrap + a **bound, painted, non-degenerate** atlas, declare `flat_region` and ship honest flat colours. Never declare `textured` over an orphan or degenerate atlas.

---

## Self-verify gate — run this and pass it BEFORE handoff

This is mandatory. You run these exact commands and meet the pass bar; only then is the package deliverable. The gate elevates the textured-mode UV/binding checks (today a non-aborting `warn`) to **delivery-blocking for the producer**.

```text
# --- 0. PROBE THE GLB DIRECTLY (producer ground truth; same logic the bake uses) ---
blender --background --python pipeline/tools/_diag_glb_uvmesh.py -- <variant>.glb
#   EXPECT (textured): "DIAG_IMPORTED_MESH_COUNT 1 ..." then per mesh
#                      "DIAG <mesh>: has_tex=True materials=N degenerate_uv=0/N"
#   FAIL if: NO_UV_LAYER, has_tex=False, or degenerate_uv != 0/N
blender --background --python pipeline/tools/_diag_glb_bounds.py -- <variant>.glb
#   EXPECT: dims ~= real metres; tallest axis == declared up; min Z ~= 0; footprint straddles x=y=0

# --- 1. LINT THE MANIFEST (schema, files exist, rig known, animations well-formed) ---
python pipeline/tools/lint_external_asset.py <variant>.asset.json
#   EXPECT: "ASSET LINT OK"; exit 0; NO off-vocabulary clip warning

# --- 2. BAKE TO A REAL SPRITE PACKAGE ---
python pipeline/tools/bake_asset.py <variant>.asset.json
#   EXPECT: a package under pipeline/output/<variant_id>/ with color_atlas.png,
#           hitmask_atlas.png, manifest.json, build_log.json; Gate-1 PASS

# --- 3. CONTACT SHEETS (eyeball + machine-confirm) ---
python pipeline/tools/make_contact_sheet.py pipeline/output/<variant_id>
#   -> <variant>_color_sheet.png : 16 directions; cyan facing arrow sweeps once; anchor (magenta) at feet
#   -> <variant>_hit_sheet.png   : head=red torso=green arms=blue legs=yellow

# --- 4. READ THE BUILD LOG: the cross-stage verification_report must be all-green ---
#   pipeline/output/<variant_id>/build_log.json
#   REQUIRE: "ok": true  AND  warnings[] contains NO entry with severity "error"
#   For texture_mode "textured", ALSO require warnings[] contains NO "degenerate_uv"
#   and NO "region_fallback_torso" entry (producer-blocking, stricter than the default gate).
```

**Pass bar (every line must hold):**

- [ ] **`texture_mode: textured` ⇒** baked `has_tex == true` **AND** `degenerate_uv` empty (`0/N` on every mesh) **AND** the atlas is colour-rich (not a flat fill / not a swatch grid). *(For `flat_region`, instead: every region has a sensible non-grey base colour.)*
- [ ] **Regions intact** on `<variant>_hit_sheet.png`: **head=red, torso=green, arms=blue, legs=yellow**, tiling the silhouette, no `region_fallback_torso`.
- [ ] **16 distinct directions** on `<variant>_color_sheet.png`: direction N ≠ direction N+8 (front ≠ back), the cyan arrow sweeps once around, anchor stays at the feet. *(Radial props exempt from the distinctness requirement.)*
- [ ] **The cross-stage verification_report (build_log.json) is all-green:** `ok == true`, no `severity:"error"` warning, Gate-1 PASS; and for `textured`, no `degenerate_uv` and no `region_fallback_torso`.
- [ ] **Animation reads** (if animated): walk/run legs swing, attack arm ramps, no dead/missing clips, loops seamless.

If any line fails, fix the model and re-run the whole gate. **Do not hand off a package that fails the pass bar.** A `flat_region` package that cannot meet the textured bar is the correct delivery — declare it honestly rather than shipping a degenerate `textured`.

---

## The gold-standard worked examples (diff against these)

- **`pipeline/examples/texture_starter/humanoid_textured.glb`** — the canonical **textured** shape: N region materials, each with `baseColorTexture` bound to one embedded atlas, real UV islands area ≈ 0.4–0.9 in `[0,1]`, region-keyworded names. Your `textured` delivery's `_diag_glb_uvmesh.py` output should look like this one's.
- **The color-coded CALIBRATION model (ADR-0030)** — the gold-standard *worked example a producer diffs against*: every stage authored correctly (scale, forward, regions, unwrap, binding, rig, clips, hitboxes), color-coded by region so a producer can visually and machine-check their own delivery stage-by-stage against it. Use it as the reference when any predicate above is ambiguous.

---

## Consequences

### Positive
- One `texture_mode` switch makes the obligation explicit; `flat_region` is a first-class honest path so producers stop faking `textured` with orphan/degenerate atlases.
- Every acceptance criterion is a number, a predicate, or a command's expected output — no "looks right."
- The self-verify gate elevates the textured-mode UV/binding checks (today a non-aborting `warn`) to producer-blocking, closing the "textured-but-flat ships green" hole at the source.
- The anti-patterns table teaches the exact verified failures (orphan atlas, degenerate UVs, auto-rig material-strip) so a producer recognises and avoids each.
- Pre-rigged textured deliveries sidestep the auto-rig material-strip/crash hazard.

### Negative
- Producers must run a Blender-headless probe (`_diag_glb_uvmesh.py` / `_diag_glb_bounds.py`) before handoff — a heavier pre-flight than the old "lint + eyeball."
- The stricter textured pass bar (no `degenerate_uv`, no `region_fallback_torso`) is producer-enforced ahead of the pipeline's default gate; until the pipeline promotes `degenerate_uv` to `error` for `texture_mode: textured`, the two can diverge if a producer skips the gate.
- This spec assumes the new ADRs 0026–0032 land; if any rule there changes, the corresponding stage section must follow.

## Alternatives considered

- **Keep three separate docs, just tighten each.** Rejected — producers followed all three as written and still shipped orphan atlases and degenerate UVs; the gap was the *absence of a single blocking gate and a mode declaration*, which no amount of per-doc tightening supplies.
- **Make the pipeline reject degenerate UVs unconditionally (promote `degenerate_uv` to `error`).** Complementary, not a substitute — even with that, a producer needs a stand-alone pre-handoff gate and an honest `flat_region` escape hatch; and some deliveries legitimately want flat regions. This spec pairs the producer gate with the recommendation to promote the severity for `texture_mode: textured`.
- **Drop textures entirely (flat-region only).** Rejected — `humanoid_textured.glb` proves real textured deliveries render correctly; the goal is to make textured deliveries *honest and checkable*, not to ban them.

## Acceptance criteria (for this spec as a deliverable)

```text
The doc leads with the delivery contract: the file-set table + texture_mode {flat_region, textured}
  and what each obliges.
Every stage (geometry, uv+texture, rig+skin, animation, hitboxes) ends with a pass/fail checklist
  whose every item is a number, a predicate, or a command's expected output.
The uv+texture stage spells out: real per-material UV bbox area > 0 (not < 1e-4 / not collapsed),
  islands in [0,1], sRGB power-of-two PNG BOUND as baseColorTexture in the glb (loose sidecar
  rejected), region-keyworded names kept, AO baked, and the known-good shape == humanoid_textured.glb.
An anti-patterns table names the real caught failures (ogre/dragon/ball = geometry-only + orphan
  atlas; pirate = bound-but-degenerate UVs) with the correct fix per row.
A copy-paste self-verify gate lists the exact commands (lint_external_asset.py, bake_asset.py,
  make_contact_sheet.py, _diag_glb_uvmesh.py / _diag_glb_bounds.py, build_log.json) and a pass bar:
  textured => has_tex true AND degenerate_uv empty AND atlas colour-rich; regions
  head=red/torso=green/arms=blue/legs=yellow; 16 distinct directions; verification_report all-green.
Each rule cites the ADR it comes from (0024 effects, 0025/0029 hitmask, 0026-0032 producer rules);
  the calibration model (ADR-0030) is named as the gold-standard diff target.
```

## Work-list (for the pipeline implementer, to make this gate self-enforcing)

1. Add a required `texture_mode ∈ {flat_region, textured}` field to `external_asset.schema.json` and the linter.
2. When `texture_mode: textured`, promote `degenerate_uv` (and a new `texture_unbound` / orphan-atlas check) from `severity:"warn"` to `severity:"error"` in `build_log.py` so the default gate fails — collapsing the producer gate and the pipeline gate into one.
3. Add an `atlas_colour_rich` check (distinct-colour count over a threshold) for `textured`, emitted to the build log.
4. Emit a single cross-stage `verification_report` block in `build_log.json` aggregating geometry/uv/texture/rig/anim/hitbox pass-fail, so "all-green" is one machine-readable field.
5. Harden `rig_from_profile.py` against dict-shaped `materials.json` (the pirate crash) and stop it from silently stripping UVs/textures when a pre-rigged textured mesh is delivered.

---

*Returned-file note (for the orchestrator): this is the full standalone document to write to disk; the verified file:line touchpoints behind every predicate are `pipeline/tools/constants.py:47-61` (region table), `pipeline/tools/blender_render_anim.py:85-100` (has_tex + degenerate_uv `<1e-4` detection), `pipeline/tools/build_log.py:140-141,167,172` (degenerate_uv = warn; `ok` only false on error — the gap), `pipeline/tools/lint_external_asset.py:32-82` (lint scope), `pipeline/tools/_diag_glb_uvmesh.py` / `_diag_glb_bounds.py` (producer probes), and `pipeline/examples/texture_starter/humanoid_textured.asset.json` (known-good shape).*
