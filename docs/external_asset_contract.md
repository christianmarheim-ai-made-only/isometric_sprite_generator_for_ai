# External asset contract (v1) — what to deliver for the game_iso_v1 sprite pipeline

**Audience:** an external producer (an art AI, an animation AI, or a human artist) making a
3D model, texture, and/or animation that this pipeline turns into a `game_iso_v1` sprite
package (16-direction color atlas + R8 HIT-mask + manifest). This doc says **exactly** what
to deliver so it drops in. Validate your delivery with
`python pipeline/tools/lint_external_asset.py your_asset.asset.json`.

What you get back: an engine-loadable sprite package (see `docs/multistate_sprite_contract.md`
and `pipeline/docs/BEVY_LOADER_INTEGRATION.md`). You do **not** produce sprites — you produce
the **3D source**, and a small `*.asset.json` manifest that tells the pipeline how to read it.

---

## 0. The reuse split (read this first — it is how we scale)

Deliver three things **separately** so they recombine:

| Layer | Shared across | Example (birds) | Produced by |
|---|---|---|---|
| **Rig** (skeleton) | an *archetype* | one `bird_v1` skeleton | once |
| **Animation library** (clips) | a rig | `idle/fly` on `bird_v1` | once |
| **Mesh + texture** (a *variant*) | nothing — one per model | `sparrow`, `crow`, … skinned to `bird_v1` | per model |

So **10 birds = 10 meshes/textures + ONE `bird_v1` rig + ONE animation library.** An "art AI"
makes only meshes+textures (all skinned to the same named bones); the animation is authored once
and reused, because clips target **bone names**, not a specific mesh. A "static" variant with no
rig falls back to the pipeline's procedural animation.

The pipeline combines `variant_mesh (rig=bird_v1)` + `bird_v1 animation library` → renders every
declared state. To add a bird, you deliver only a new skinned mesh + texture.

---

## 1. Coordinate + scale conventions (non-negotiable)

- **Units = metres.** A 1.8 m humanoid is 1.8 units tall. The pipeline sizes sprites from real
  height, so wrong scale = wrong on-screen size.
- **Up axis:** declare `up` (`"y"` glTF-standard Y-up, `"z"` Z-up; default `z`). **HONORED for
  `.obj`** — a Y-up obj without `up:"y"` bakes sideways. For `.glb`/`.gltf` the importer reads the
  file's own axis and this field is currently inert; set it correctly anyway for portability.
- **Forward = +X — required.** The model MUST face +X (direction 0). `forward` is declared-only (the
  schema pins it to `"+x"`) and is **not applied by any baker yet** — a model facing another way
  renders 90/180° wrong. (Pipeline-applied `forward` rotation is a planned follow-up.)
- **Origin = ground footprint centre.** The root/feet sit at the origin on the ground plane
  (the lowest point at height 0, the footprint centred on x=y=0). The pipeline re-normalizes,
  but author close to this so the rig/anim root is sane.

## 2. Mesh

> **Building the body from scratch?** See [`modeling_the_body.md`](modeling_the_body.md) for the
> step-by-step geometry how-to (scale, forward axis, giving it a *front*, region-named parts) plus a
> 5-minute pre-texture check. This section is the spec; that doc is the tutorial.

- **Format:** glTF 2.0 **`.glb`** (preferred — carries rig + skin + animation + textures in one
  file) or **`.obj`** (static only, no rig/animation). Triangulated.
- **One logical mesh** (or cleanly mergeable parts). No non-manifold edges required, but remove
  stray/loose geometry and interior faces (the baker does not validate this).
- **Budget (advisory, not enforced):** roughly **300–8000 triangles**. Nothing rejects more, but
  bake time grows and sub-pixel detail is wasted.
- **UVs:** a non-overlapping UV unwrap if you ship a texture.
- **Sharpness:** the sprite is rasterized at a per-frame logical canvas (default 256²) then the
  engine scales it. Detail finer than ~1 px at the sprite's on-screen size is wasted — model +
  texture **silhouette and large forms first**; that is what reads at iso scale.

## 3. Texture / material (for "look sharp")

> **Painting the texture?** See [`texturing_the_body.md`](texturing_the_body.md) for the how-to —
> with a ready UV-unwrapped model + layout template to paint on, and a verify step. This section is
> the spec.

- **Format:** PNG, **sRGB** base color; each dimension a power of two in {512, 1024, 2048} (width
  and height may differ, e.g. 1024×2048).
- **What renders this iteration:** only an **embedded-glb base color** (Workbench TEXTURE pass).
  `normal`/`roughness`/`metallic` — and anything in the manifest `textures` map — are **recorded but
  NOT rendered** yet. An `.obj` delivery renders a **flat per-region colour** (no texture). Reference
  the base color from the glTF material's `baseColorTexture`.
- **Vertex colors** are accepted in place of (or alongside) a texture.
- A material with no texture must at least set a sensible base color.
- For crisp iso reads, bake **ambient occlusion / large shading into the base color** if you can —
  the pipeline's default render is flat-ish Workbench shading.

## 4. HIT regions (gameplay hit-mask — body-only this iteration)

> **Generating the hit/collision data?** See [`generating_hitbox_data.md`](generating_hitbox_data.md)
> — the R8 mask comes free from the region tags, and the collision capsule is pure min/max over the
> vertices (a tool + the by-hand math). This section is the spec.

Every face needs a body **HIT region** so the pipeline can emit the R8 hit-mask. Pick ONE:

- **By material name (default, simplest):** name each material so its name CONTAINS a region
  keyword. Canonical keyword → region id (single source of truth: `pipeline/tools/mesh_io.py`
  `REGION_KEYWORDS`):

  | Region (id) | Name contains any of |
  |---|---|
  | `head` (1)  | head, skull, face, neck, **beak** |
  | `torso` (2) | torso, chest, body, spine, hip, pelvis, waist, **tail** |
  | `arms` (3)  | arm, hand, shoulder, elbow, wrist, **wing** |
  | `legs` (4)  | leg, foot, feet, thigh, shin, knee, ankle |

  **Matching rule:** the lowercased name is scanned in the fixed priority order above; the **first
  keyword that occurs anywhere (substring, not whole-word) wins** — so `forearm` → arms (via `arm`),
  `armor` → arms (also via `arm`). **Avoid names containing more than one region keyword.** Unmatched
  → `torso` (the loader warns). Region 0 = none/background, never authored.
- **By region map (finer control):** a per-vertex integer attribute named `HIT_REGION`, or a
  separate small region texture; declare `region_source` in the manifest. (Pipeline support: the
  material-name path ships today; the attribute/texture path is a documented extension.)

**Regions 5–7 (weapon/shield/gear) have no authoring path** this iteration: weapon/shield material
names match no keyword and fall back to `torso` like any unmatched name. 5–7 are reserved in the
palette for a future gear iteration — do not attempt to author them.

## 5. Rig / skeleton (only if you ship animation)

- An **armature/skeleton** with bones named **exactly** per a **rig profile** (the shared bone
  contract). Profiles live in `pipeline/schema/rig_profiles/` — e.g. `biped_v1.json`,
  `bird_v1.json`. Each profile lists the required bone names + parents, **per-bone bind-pose
  positions** (`head`/`tail` in metres, +Z up, +X forward — enough to build the skeleton from
  scratch), a `region_by_bone` map, and the `states` a variant may deliver (required `idle` + optional
  extras).
- **Skin** the mesh to those bones (standard glTF skin: joints + weights, ≤4 influences/vertex).
- **Bind pose** = the model's neutral rest (T/A-pose for biped; wings level for bird), foot/root
  at the origin, facing +X.
- A variant mesh that declares `rig: "bird_v1"` MUST use exactly the `bird_v1` bone names so the
  shared animations apply. **This is the key to reuse.**
- If you have no rig, omit it — the pipeline animates the biped procedurally (`idle`, `walk`,
  `attack`; see `bake.bake_character_anim`), and you only owe mesh + texture + HIT regions.

## 6. Animation (the movement data — read + write)

> **Generating the animation?** See [`generating_animation_data.md`](generating_animation_data.md)
> for authoring motion as a compact per-bone keyframe JSON (`anim_clips_v1`) that an AI can write by
> hand, plus `bake_anim_from_json.py` to turn it into the glTF clips described below.

Animations are **glTF 2.0 animation clips** — this IS the movement-data format, and it is what you
read/write:

- Each clip = a named entry in the glTF `animations` array (`"idle"`, `"walk"`, `"fly"`, …). A clip
  is a set of **channels**; each channel targets a bone (node) and a path
  (`translation`/`rotation`/`scale`) with a **sampler** = keyframe `times` + TRS `values` +
  interpolation (`LINEAR`/`STEP`/`CUBICSPLINE`). That triple — *(bone, path, keyframes)* — is the
  movement data. Author it in any DCC (Blender/Maya) or generate it directly; export glb.
- **In-place / no root motion:** the cumulative **world-space horizontal (X, Y) translation of every
  bone, over a clip, must net to ≈0** — no bone may drift the silhouette off the origin across the
  loop (keep within ~1% of `footprint_radius`). Vertical (Z) bob is fine. Locomotion is the game's
  job. (Prose-only rule; not enforced by tooling yet.)
- **Naming → states:** clip names become animation states. Declare each in the manifest with
  `frames` (how many sprite frames to sample per direction), `fps`, and `playback`
  (`loop` | `once` | `hold`). The pipeline samples the clip uniformly across its duration into
  `frames` poses and renders 16 directions of each. `once`/`hold` are non-looping (attack/death);
  `loop` wraps. A state whose `clip` is **absent from the glb** renders the static rest pose (NOT an
  error) — so every declared clip must exist in the glb, or be embedded via `files.animation_clips`.
- **Reuse:** because channels target bone **names**, the same clip plays on any mesh skinned to the
  same rig profile. Ship the animation library once per archetype.

To **read** an existing model's animation: open its glb, list `animations[].name` and, per clip,
the per-bone TRS keyframes. To **write/improve** one: edit/add those channels for the rig's bones,
keep it in-place, re-export glb. (A worked read/write example + a Blender helper script ship with
the consumption tooling.)

## 7. The asset manifest (`<variant>.asset.json`)

A small JSON you deliver alongside the model. It tells the pipeline how to read your files.
Schema: `pipeline/schema/external_asset.schema.json`. Example: `pipeline/examples/`.

```json
{
  "asset_contract_version": "external_asset_v1",
  "variant_id": "sparrow",
  "archetype": "bird",
  "files": { "mesh": "sparrow.glb" },
  "geometry": { "up": "y", "forward": "+x", "unit": "meter" },
  "rig": "bird_v1",
  "region_source": "material_name",
  "textures": { "base_color": "sparrow_basecolor.png" },
  "animations": {
    "idle": { "clip": "idle", "frames": 1, "fps": 1,  "playback": "loop" },
    "fly":  { "clip": "fly",  "frames": 4, "fps": 12, "playback": "loop" }
  },
  "world_metrics": { "height_world": 0.22, "footprint_radius_world": 0.12 },
  "notes": "wings named wing.L/wing.R; in-place fly cycle."
}
```

- `archetype` + `rig` select the shared rig + animation library. `files.mesh` is **required**.
- **Authoring animation as text?** Pair the rigged glb with `files.animation_clips` (path to an
  `anim_clips_v1` JSON — see [`generating_animation_data.md`](generating_animation_data.md));
  `bake_asset.py` embeds those clips into the glb before baking. Otherwise the glb must already
  contain the named clips. Animations are always **embedded in a variant glb** — there is no
  standalone library delivery (clips target bone names, so one `*_anim.json` replays on every variant
  of the rig).
- Omit `rig`/`animations` for a static mesh (procedural animation).
- `world_metrics` is optional (measured from the mesh AABB); provide it to override.

## 8. What the pipeline does with it (consumption)

One command bakes any compliant asset:

```text
python pipeline/tools/bake_asset.py your.asset.json
```

It validates the manifest (the linter), then routes by type and emits an engine-loadable package
(Gate-1 checked):

| Delivery | Route |
|---|---|
| `.obj` mesh | numpy baker (static) |
| `.glb`/`.gltf`, no rig/animations | Blender baker (static) |
| `.glb`/`.gltf` + `rig` + `animations` | Blender **animation** baker — imports the skeleton + skin + clips, samples each declared state's clip into poses, renders the **multi-state** package |
| `.glb` + `rig` + `animations` + `files.animation_clips` | as above, but first embeds the `anim_clips_v1` JSON as glTF clips (`bake_anim_from_json.py`) — author animation as text, bake in one command |

All paths ship today. Rigged is demonstrated by `pipeline/examples/sparrow.asset.json` (clips already
in the glb) and `pipeline/examples/animation/crow_jsonanim.asset.json` (clips from a JSON, embedded
at bake). `crow.glb` reuses `sparrow`'s rig + animation — the reuse case.

## 9. Validation + acceptance

Run `python pipeline/tools/lint_external_asset.py <variant>.asset.json`. It checks: schema (contract
version, required fields, `archetype`/`forward`/`up`/`unit`, `playback ∈ {loop, once, hold}`,
`frames ≥ 1`), that declared files exist, `rig` matches a known profile NAME, `region_source` is
supported, and — if `files.animation_clips` is present — that the `anim_clips_v1` JSON is valid.
**lint does NOT open the glb:** bone-name coverage and clip existence are validated only at **bake
time** by the Blender baker. A clean lint means the structure/files/rig-name/regions/animation are
well-formed — not that the mesh + rig will bake.

## 10. Versioning

- This contract: `asset_contract_version: external_asset_v1`.
- Rig profiles are versioned (`bird_v1`, `biped_v1`); a new bone layout = a new profile id so old
  variants/animations keep working.
- The sprite **output** contract is separate (`docs/multistate_sprite_contract.md`).
