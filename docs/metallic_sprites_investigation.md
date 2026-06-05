# Metallic / specular sprites — feasibility investigation (decision-complete)

**Status:** INVESTIGATION — decision-complete, no code written. **Purpose:** answer "can
game_iso_v1 sprites show metallic / specular / shiny effects, and what would each approach
take?" with enough grounding that a future cold session can pick an option and execute without
re-deriving the costs. Cross-repo: the **pipeline** (`C:\Code\isometric_sprite_generator_for_ai`)
bakes; the **engine** (`C:\Code\Claude`, Bevy 0.17 / wgpu) consumes.

**Anchors (read before executing):**
Pipeline — `pipeline/tools/blender_render.py` (Workbench studio-lit COLOR pass + flat REGION→R8
pass, ~lines 120/143-144/151-164), `pipeline/tools/render3d.py` (software probe: per-face normals
already at line 152, z-buffer at 77/101-104, R8 mask write at 109-111), `pipeline/tools/bake.py`
(R8 pack pattern 81-85/179, shared placements ~106-114/287), `pipeline/tools/mesh_io.py`
(name→region authoring 30-44), `pipeline/tools/constants.py` (id→RGB table 29-34),
`adr/ADR-0006-visible-topmost-surface-hitmask.md` (the reusable z-buffered topmost pass),
`docs/atlas_paging_contract.md` (additive 3rd-atlas precedent), `docs/texturing_the_body.md`
(step 5: normal/roughness/metallic already an authoring affordance, currently dropped),
`pipeline/schema/sprite_manifest.schema.json` (the one closed object: `atlases.additionalProperties:false`, line 72).
Engine (read-only contract) — `crates/client_bevy/src/render.rs` (vanilla batched `Sprite` + flat
tint, spawn ~386-402, sync ~499, camera ~254), `crates/client_bevy/src/sprite.rs` (`AtlasesDef`
~250-253, `parse_manifest` ~326), `docs/pipeline/manifest.schema.json` (engine-vendored contract,
`atlases` ~54, `hitmask` precedent ~77-82), `docs/adr/ADR-044-sprite-animation-clips.md`.

---

## 1. SHORT ANSWER

**Yes — sprites can show metallic / specular effects, and there is a path that works *today* with
zero engine work and zero contract change.** The cheapest, real win is to bake the shine into the
color atlas at render time (it is *already* an authoring affordance in `texturing_the_body.md`
step 5) and/or use pixel-art-style high-contrast metal ramps — fully static, per-direction, no
coordination. The headline cost only appears if you want **dynamic** metal that tracks a moving
light: that requires the engine's **first** custom shader (`Material2d` + WGSL), which forfeits
Bevy's built-in sprite batching, **plus** a new per-direction normal-map atlas on the pipeline
side — *and the engine has no lighting system at all today*, so a dynamic light direction would
also have to be invented. The single fact that gates every dynamic option: **the engine is fully
unlit/flat — there is no light, no normal, no per-fragment shading for a sprite to react to.**

---

## 2. The one load-bearing fact: the engine does not light sprites at all

This gates the entire menu, so it is stated once, up front, and the three findings agree on it
without exception:

- The engine draws Bevy's **built-in `Sprite`** (a textured quad) through Bevy 0.17's **batched
  sprite pipeline**, under a `Camera2d` with `Tonemapping::None`. Output is the raw atlas texel ×
  a flat per-sprite RGBA tint (`proxy_color`). (`render.rs:386-402, 254`.)
- There is **no lighting system of any kind**: a whole-repo search for `PointLight`,
  `DirectionalLight`, `AmbientLight`, `StandardMaterial`, `Material2d`, `AsBindGroup`,
  `normal_map`, `specular`, `metallic`, `fragment_shader` returned **zero matches in any `.rs`
  file**, and there are **no `.wgsl` files anywhere in the repo** (`**/*.wgsl` → none).
- The only existing per-sprite effect is the flat `color` tint multiply (player-blue vs tan,
  `render.rs:178-184`). It is constant per fragment — a tint, not lighting.

**Consequence.** Anything "dynamic" (a glint that moves when a light or the unit moves) cannot
extend an existing capability — it must *introduce* the engine's first material, first WGSL shader,
first multi-texture bind, **and** (because there is no light) a first light-direction input. Every
static option avoids all of that. This is why the recommendation is sharply phased.

---

## 3. Tiered menu — cheapest → most capable

Costs below are grounded in the three findings; "machinery we already own" is called out because it
is the dominant discount. STATIC = highlight frozen into the baked frames (still differs per the 16
directions, so it reads as "consistent material"); DYNAMIC = responds to a moving light / unit turn
at runtime.

### Tier 0 — Baked-in shine in the color atlas  ·  STATIC  ·  **works today**
- **Looks like:** a fixed studio/hand-painted hotspot baked into each frame. Reads as
  "this material is shiny," consistent across the animation; does not move with a game light.
- **Pipeline cost:** ~zero. It is literally `texturing_the_body.md` step 5 ("bake light/form into
  base color"), or flip Workbench's *Specular Highlight* toggle
  (`scene.display.shading.show_specular_highlight`, currently never set → off) on the existing
  `light='STUDIO'` color pass. No new pass, no new atlas.
- **Contract cost:** none.
- **Engine cost:** none — the existing flat sprite path plays whatever color atlas it is handed.
- **Coordination:** none (pure pipeline).
- **Honest caveat:** Workbench specular is a single hardcoded studio shine, not PBR — it reads
  "plasticky shiny," and the real Principled `metallic`/`roughness` inputs are still ignored (only
  base color is read, `blender_render.py:76-81`). For convincing brushed metal, hand-authoring the
  ramp (Tier 1) usually beats the Workbench toggle.

### Tier 1 — Pixel-art metal ramp (high-contrast banding)  ·  STATIC  ·  **works today**
- **Looks like:** the classic dark→mid→bright→hot-spot banding the eye reads as metal, independent
  of any light. Crispest metal-read per pixel at iso scale.
- **Pipeline cost:** low — tune source-material roughness/ramps so the bake produces the banding
  (our sprites are 3D-rendered, not hand-pixeled, so this is "tune the source," not "hand-band").
  Optionally key the ramp by region using the **R8 hitmask we already emit**.
- **Contract cost:** none if baked into color.
- **Engine cost:** zero if baked; *tiny* if ever done as a runtime 1-D LUT (a small material, a ramp
  fetch — not lighting).
- **Coordination:** none (pure pipeline), unless you choose the runtime-LUT variant.
- **Note:** highest ROI **if the art target leans stylized/pixel**. For a rendered-3D look it folds
  into Tier 0.

### Tier 2 — R8 metalness / roughness mask  ·  STATIC data, *enabler*  ·  low pipeline cost
- **Looks like:** nothing on its own. It is a 1-channel atlas marking *which pixels are metal* (and
  how rough), so a later shine path only lights the sword, not the cloth.
- **Pipeline cost:** **low — it clones the R8 hitmask exactly.** Same R8 format, same z-buffered
  topmost pass (ADR-0006), same shelf packer; add a `face_metal` attribute threaded like
  `face_region` and a `pack_metal` clone, or a second flat recolor pass keyed off material. Authoring
  reuses the proven name→id hook (`mesh_io.py:30-44`, add `METAL_KEYWORDS`) or an explicit
  id→metalness table next to `constants.REGION_RGB` (`constants.py:29-34`).
- **Contract cost:** one new `atlases.metalness` (R8) entry — additive, reuses `mask_rect`
  (see §5). **One non-additive line** in the pipeline schema (`atlases.properties`), see §5.
- **Engine cost:** **zero by itself** (the engine can ignore it, exactly as it ignores `hitmask`
  today). It only costs engine work once something consumes it — and what it pairs with sets that
  cost: pair with Tier 5 (screen-space sweep) = a *light* shader; pair with Tier 6 (normals) =
  inherits the heavy shader.
- **Coordination:** pipeline can emit ahead of any engine consumption (non-breaking both ways).
- **Why it ranks high:** best "reuse what we already ship" story; gates the selective look that makes
  Tiers 5/6/the rim read as *metal* and not *wet plastic*.

### Tier 3 — Pre-baked glint *overlay* sprite (gear-POC compositing pattern)  ·  STATIC (per-direction)
- **Looks like:** a separate metallic-highlight sheet drawn additively over the body — a baked glint,
  per direction.
- **Pipeline cost:** low — author it as another named clip / overlay sheet (the additive-atlas /
  named-clip machinery already exists).
- **Contract cost:** ~zero (a named clip / second sheet; additive).
- **Engine cost:** small — a second sprite child drawn over the proxy; additive blend is the one
  wrinkle. **No shader.** This rides the existing "second sprite over base proxy" pattern from the
  combat-gear POC (`docs/handoff/combat-gear-poc/PART-2-DEMO.md:84-90`).
- **Coordination:** light — both sides touch the overlay seam, but no new render concepts.

### Tier 4 — Animated shine *sweep*  ·  STATIC data, animated read  ·  low cost
- **Looks like:** a glint that periodically sweeps across the metal — ARPG "this item is special"
  juice. Animated, **not** light-reactive.
- **Pipeline cost:** low. Overlay-clip form = just another `animations` clip (`shine`), zero new
  machinery, rides ADR-044's real-time frame timer. Scroll form = needs the Tier-2 mask.
- **Contract cost:** zero (named clip) or +the Tier-2 mask.
- **Engine cost:** low (additive overlay sprite) — or a small `Material2d` for the scrolling-UV
  variant.
- **Coordination:** light.

### Tier 5 — R8 mask + screen-space shine shader  ·  PSEUDO-DYNAMIC  ·  introduces the first shader
- **Looks like:** an animated sweep / Fresnel-ish band confined to metal pixels by the Tier-2 mask
  (`color += mask * shine(screen_uv, time)`). Moves, but is not physically lit.
- **Pipeline cost:** the Tier-2 mask (low).
- **Contract cost:** the Tier-2 `atlases.metalness` entry.
- **Engine cost:** **medium — this is where the engine's first custom `Material2d` + WGSL appears,
  and sprite batching is forfeited** (the dominant engine cost line). But it dodges normals, tangent
  space, and light-direction correctness — materially simpler than Tier 6.
- **Coordination:** real (cross-repo: pipeline emits mask, engine adds shader) — but no light rig
  needed, because the sweep is parametric (time/uv), not lit.
- **Mask-edge rim variant (sleeper):** detect mask silhouette edges and add a rim sheen — strong
  metallic/edge read for near-zero cost on a fixed camera; can even be baked into color (→ Tier 0,
  zero engine cost). Flagged because rim light reads especially well at small iso scale.

### Tier 6 — Normal-map atlas + dynamic Blinn-Phong (or matcap)  ·  TRULY DYNAMIC  ·  most capable, most expensive
- **Looks like:** real metal whose highlight shifts as the unit turns and as a light moves. The only
  "live" metal on the menu.
- **Pipeline cost:** **moderate-high.** Emit a per-frame **screen-space normal atlas**, one set per
  direction. The cheap source is the **software rasterizer** (`render3d.py`): per-face normals are
  *already computed* (line 152) and a working z-buffer already exists (77/101-104) — emitting the
  atlas is ~30-40 lines, the same write pattern as the R8 region (109-111). The **Blender** art path
  does **not** expose a clean normal AOV from Workbench; realistically this means standing up a
  dedicated **EEVEE/Cycles normal-AOV pass** — more plumbing, since the rest of the pipeline is
  committed to Workbench. *(Uncertainty flag: the cheapest correct normals live in the numpy probe,
  not the production art renderer — reconciling "numpy owns normals" with "Blender owns the art" is
  an open pipeline question, not a solved one.)*
- **Contract cost:** a new `atlases.normal` (RGB8, **linear**, view-space, `n*0.5+0.5`) entry —
  additive, reuses `rect`; plus the one non-additive `atlases.properties` schema line.
- **Engine cost:** **highest.** First `Material2d` + first WGSL + multi-texture bind (color + normal)
  + a light-direction uniform + Blinn-Phong (or, cheaper, a **matcap** lookup by `N.xy` into a
  painted chrome sphere — a trivial shader, no light math, art-directable stylized metal). All of it
  **forfeits sprite batching.** The normal atlas must load as **linear** (`Rgba8Unorm`, not `…Srgb`)
  or the normals are gamma-wrong, and it must be **coregistered** to the exact color frame rects.
- **Coordination:** heavy, joint, ADR-worthy (mirror ADR-044). Pipeline owns the normal bake +
  per-direction correctness; engine owns the shader, the material, and the light input.
- **The latent-payoff caveat (important):** the scene has **no dynamic light rig today**, so Tier 6's
  signature payoff — a glint that tracks a moving light — has nothing to track yet. Spending the full
  cost now buys a capability the rest of the game can't exercise. **Matcap** is the better buy if you
  want the *look* of real metal without a light rig, because it shares Tier 6's one hard prerequisite
  (the normal atlas) at a fraction of the shader cost and **needs no light direction**.
- **Iso-readability risk (honest):** per-pixel relit speculars shimmer/crawl on low-res sprites and
  can fight the studio shading already baked into the color atlas (a "double-lit" look). Needs
  clamping and the Tier-2 mask to confine spec to metal pixels.

### Menu at a glance

| Tier | Technique | Pipeline | Contract | Engine | Coordination | Static/Dynamic |
|---|---|---|---|---|---|---|
| 0 | Baked-in shine (color atlas) | ~0 (step 5 / Workbench flag) | none | **none** | none | Static (per-dir) |
| 1 | Pixel-art metal ramp | low (tune source / R8 key) | none | 0 baked / tiny LUT | none | Static |
| 2 | R8 metalness/roughness mask | **low (clones hitmask)** | +`atlases.metalness` (additive*) | 0 alone | emit-ahead OK | Static data (enabler) |
| 3 | Pre-baked glint overlay sprite | low | ~0 (named clip) | small (2nd sprite, additive) | light | Static (per-dir) |
| 4 | Animated shine sweep | low | 0 / +mask | low (additive overlay) | light | Animated, not lit |
| 5 | R8 mask + screen-space shine shader | low (mask) | +`atlases.metalness` | **medium (1st shader, loses batching)** | real, no light rig | Pseudo-dynamic |
| 6 | Normal atlas + Blinn-Phong / matcap | **mod-high (normal AOV)** | +`atlases.normal` | **highest (1st material+WGSL, light uniform, loses batching)** | heavy / joint / ADR | **Truly dynamic** |

\* additive at the *manifest data* level; one non-additive allow-list line in the pipeline schema — see §5.

---

## 4. RECOMMENDATION + phasing

**Phase A — ship a metal read NOW, zero coordination (Tier 0 + Tier 1).** Bake the shine into the
color atlas (step 5) and/or tune source ramps for a pixel-art metal banding. **Zero engine work,
zero contract change, pure pipeline.** For a stylized/pixel target this is often not just the floor
but the ceiling. Do this first regardless of what else you decide.

**Phase B — add the selective-shine enabler (Tier 2), cheaply and ahead of need.** Emit the R8
`atlases.metalness` mask by cloning the hitmask bake. It is low-cost, reuses the most-proven
machinery we have, and — like `hitmask` today — the engine can ignore it until ready, so emitting it
is non-breaking in both directions. This unblocks every later selective-shine path without committing
the engine to anything. **Pair it with the Tier-5 mask-edge rim** (or even a baked rim) for a strong,
cheap silhouette sheen on the fixed camera.

**Phase C — only if/when the game gains a dynamic light rig: the "real" dynamic metal.** The honest
gate: **the engine has no light direction today and no lighting system to extend.** True dynamic
metal (Tier 6) is therefore *three* firsts on the engine side (material, WGSL, multi-texture bind)
plus a *first light input*, plus a per-direction normal bake on the pipeline side, plus forfeiting
sprite batching. Its signature payoff (a glint that tracks a moving light) is **latent** until a light
rig exists. So:
- **Prerequisite for any honest Tier 6:** decide and add a **light-direction input** to the engine
  (even a single fixed/slow-orbiting "sun" vector). Without it, "dynamic" has nothing to be dynamic
  against — and a single global light vector may be all an iso game needs (see open decision D2).
- **If you want the metal *look* before/without a light rig, choose matcap over Blinn-Phong.** It
  shares the one hard prerequisite (the normal atlas) but needs no light uniform and a trivial shader,
  and reads as gorgeous stylized chrome. This is the recommended "real-ish metal" buy.
- **Defer physically-lit Blinn-Phong (Tier 6 full)** until the light rig is real; it is the highest
  fidelity but its cost lands before its payoff can.

**One-line phasing:** bake it now (A) → emit the cheap mask ahead of need (B) → only build the first
shader + normal bake once a light direction exists, preferring matcap (C).

---

## 5. Contract amendment surface — exact, and who owns it

There are **two schema files** (the pipeline's producer schema and the engine's vendored consumer
schema). Both are additive-friendly; the precedent is `atlases.hitmask`, an already-defined optional
companion atlas the engine doesn't consume yet.

**Engine consumer schema** (`C:\Code\Claude\docs\pipeline\manifest.schema.json`): `additionalProperties:
true` at root, in `camera`, in `atlases`, in `color`, in `frames[]` — so the pipeline can emit
`atlases.normal` / `atlases.metalness` **today** and the engine silently ignores them (serde drops
unknown fields; `AtlasesDef` declares only `color`, `sprite.rs:250-253`). Non-breaking both ways.
`atlases.hitmask` (schema ~77-82) is the exact precedent: *"Optional… not consumed by the engine
yet… keep emitting it."*

**Pipeline producer schema** (`C:\Code\isometric_sprite_generator_for_ai\pipeline\schema\sprite_manifest.schema.json`):
**this is the one place that is NOT fully additive.** `atlases` is closed —
`"atlases": { …, "additionalProperties": false }` (**line 72**) with `required: ["color","hitmask"]`.
A new `normal` or `metalness` key **fails validation here until added to `atlases.properties`** —
**one allow-list line per new atlas** (clone the `hitmask_atlas` $def). Everything else (paging,
per-frame rects, top-level, world_metrics) is open.

**Concrete additions:**
- *Metalness R8 (Phase B):* add `"metalness"` to `atlases.properties`; emit
  `atlases.metalness = {path, size, format:"PNG_R8_…no_antialias", sampling:"nearest"}`. **Reuses
  `mask_rect`** — color + mask already share placements (`bake.py:106-114,287`), so no new per-frame
  rect.
- *Normal RGB8 (Phase C):* add `"normal"` to `atlases.properties`; emit
  `atlases.normal = {path, size, format:"PNG_RGB8_normal_view_space", sampling:"linear"}`. Document
  the encoding (view-space, `n*0.5+0.5`, tied to the 16 directions). **Reuses `rect`.** Engine must
  load it **linear**, not sRGB.
- Optional: bump `manifest_version` / note a `material_model` in `build` — not required by either
  schema.

**Ownership (per ADR-044's "contract is co-owned, coordinated at the render seam"):**
- **Pipeline decides & owns:** how to author metal (name-keyword vs explicit id→value table), how to
  bake the mask/normal pass, per-direction normal correctness, packing/paging, the producer-schema
  allow-list edit.
- **Engine decides & owns:** whether/when to *consume* a channel, the consumer-schema field on
  `AtlasesDef`, the material/shader, the light-direction input, sRGB-vs-linear load, and the
  batching-vs-material tradeoff.
- **Joint / ADR-worthy:** introducing any *consumed* new atlas (normal or metalness-that-is-actually-
  lit) is a cross-repo contract amendment — a new ADR mirroring ADR-044 is the natural vehicle.
  Emitting an *unconsumed* atlas (Phase B) needs no ADR; it is the hitmask pattern.

---

## 6. OPEN DECISIONS for the user

These are the calls that change *which* tier to build; none are blocked on more investigation.

- **D1 — Static-baked vs dynamic-lit metal.** Is a per-direction *baked* glint (Tiers 0/1/3/4,
  zero/near-zero engine cost, works today) sufficient, or is a runtime glint that tracks a moving
  light a real requirement? This single call decides whether you ever pay the Tier-5/6 shader +
  batching cost. *Recommendation: baked is almost certainly enough for a stylized iso game; treat
  dynamic as a later, light-rig-gated upgrade.*
- **D2 — Is a single global light direction acceptable?** Dynamic metal needs *some* light input, and
  the engine has **none** today. For a fixed-camera iso game a single global "sun" vector (fixed or
  slowly orbiting) is likely all you need and is far cheaper than per-light shading. Confirm a global
  light is acceptable before any Tier-6 work — it sets the engine-side scope.
- **D3 — Stylized matcap vs physically-based metal.** If you do go dynamic, do you want art-directed
  *style* (matcap: trivial shader, no light rig, swap-a-sphere art control) or physical *light
  response* (Blinn-Phong: needs the light input, heavier shader, shimmer risk)? Both share the one
  hard prerequisite — the normal atlas — so this is a shader/art-direction choice, not a pipeline
  one. *Recommendation: matcap, unless physically-correct light tracking is a stated requirement.*
- **D4 — Emit the R8 metalness mask now, ahead of consumption?** Cheap, non-breaking, unblocks
  everything later (the hitmask precedent). Recommend **yes** if metal is on the roadmap at all.

**Uncertainty flags (do not overclaim):**
- The cheapest correct normals live in the **software probe** (`render3d.py`), not the **Blender art
  renderer**; a production normal atlas likely needs a *new EEVEE/Cycles AOV pass* in Blender. The
  "where do production normals come from" question is **open**, not solved.
- The engine findings are confident there is **no** lighting/shader today (multiple zero-match
  searches, no `.wgsl`), but the *cost* of standing up the first `Material2d` is an estimate — the
  team's own `client_bevy/Cargo.toml:18-20` note that a trimmed 2D feature set previously failed to
  draw sprites is a flag that the custom-material path may surface Bevy-version friction.
- Per-direction normal-map *correctness* (does the highlight track the body as it turns through the 16
  baked views?) is a genuine open question, not a closed one — it is the main fidelity risk in Tier 6.
