# Modeling the body (before textures)

**Audience:** whoever (a human modeler or a mesh-making AI) builds the **3D body** that this
pipeline turns into a `game_iso_v1` 16-direction sprite. This is the **geometry stage** — the
untextured body. Textures, rig, and animation come *after* and are covered by
[`external_asset_contract.md`](external_asset_contract.md). Body-only this iteration (no weapons /
shields / gear).

Do this stage right and the body drops straight in. The single most common way to waste work is to
texture a body that was modeled wrong (wrong scale, wrong front) — so there's a **5-minute check at
the end you run before you touch textures.**

---

## What "the body" is at this stage

A single clean mesh, at real-world scale, standing on the ground, facing forward, **split into named
parts** so the pipeline knows which polygons are head / torso / arms / legs. No UV maps and no image
textures yet — but the **material (or part) *names* are part of this deliverable**, because the
gameplay hit-regions come from those names.

Output you hand off after this stage: `body.obj` (static) or `body.glb` (preferred — also carries a
rig later), with parts named by region keyword. That's it.

---

## The 6 rules that must be right

If any of these is wrong the body will look wrong in-engine no matter how good the texture is.

1. **Real scale, in metres.** A 1.8 m human is **1.8 units** tall. A sparrow ~0.22 m. The sprite is
   sized from real height; wrong scale ⇒ wrong on-screen size next to everything else.
2. **Up axis.** Build Z-up, or Y-up and declare `up: "y"` in the manifest later. (glTF is Y-up by
   default; the pipeline converts.)
3. **Forward = +X.** The body **faces +X** — that is "direction 0". Nose/chest/beak point down the
   +X axis. (If you must face another way, you'll declare `forward` later, but +X is the default and
   the simplest.)
4. **Origin = ground footprint centre.** The lowest point sits at **z = 0**, and the standing
   footprint is centred on **x = y = 0**. Feet on the floor, body over the origin.
5. **Give it a FRONT — front and back must look different.** This is the rule people miss. If the
   body is symmetric under a 180° turn (a centered torso + a head with no face + arms that mirror
   left/right), then the render of heading N is *identical* to heading N+8 — **you only get 8 real
   directions and the engine can't tell front from back.** Break it on purpose: a face / visor on
   the front of the head, a chest vs. a flat back, a snout, a beak + tail. Anything that reads as
   "this side is the front." (This actually shipped as a bug here once — see *Worked references*.)
6. **One clean, triangulatable mesh.** One logical mesh (or cleanly separable parts), no stray loose
   geometry, manifold-ish, **~300–8 000 triangles** total. More detail than that is wasted at sprite
   size and slows the bake.

---

## Build it, step by step

1. **Block the silhouette first.** Rough the big forms — overall height, the head, torso, limb
   masses. At iso sprite scale the **silhouette and large shapes are all that read**; fine surface
   detail disappears. Get the outline recognizable from the front, side, and 3/4 before refining.
2. **Set real scale and plant it.** Scale so height = real metres; drop it so feet are at z = 0;
   centre the footprint on x = y = 0; rotate so it faces **+X**.
3. **Add the front.** Put a clear front feature on the +X side (face/visor on the head, chest panel,
   snout, beak). Confirm front ≠ back by eye, and again with the check below. *(Rule 5 — don't skip.)*
4. **Split into body parts and name them by region.** The pipeline assigns each polygon a HIT region
   from the **material name (glTF) or material/group name (OBJ)**, case-insensitive substring match:

   | Region | id | Name your part any of … |
   |---|---|---|
   | head | 1 | `head`, `skull`, `face`, `neck`, `beak` |
   | torso | 2 | `torso`, `chest`, `body`, `spine`, `hip`, `pelvis`, `waist`, `tail` |
   | arms | 3 | `arm`, `hand`, `shoulder`, `elbow`, `wrist`, `wing` |
   | legs | 4 | `leg`, `foot`, `feet`, `thigh`, `shin`, `knee`, `ankle` |

   Anything unmatched falls back to **torso (2)** (and the loader warns). So give every part a slot
   named with one of these words — e.g. materials `head`, `torso`, `arm_L`, `arm_R`, `leg_L`,
   `leg_R`. Do **not** make weapon/shield/gear parts yet — body-only.
5. **If it will be animated, build it rig-ready.** Keep limbs as distinct masses (arms slightly out
   from the torso, legs separable) so they can be skinned to bones later, and pose it in a **neutral
   bind pose** (biped: T- or A-pose; bird: wings level), still facing +X with feet at origin. Lay the
   body out so it can be skinned to a rig profile's **skeleton** (the rig itself is added later — you
   just need a body whose limbs match where these bones go, so the shared animation library applies):
   - **biped_v1** bones: `root, hips, spine, chest, head, arm.L, forearm.L, hand.L, arm.R,
     forearm.R, hand.R, thigh.L, shin.L, foot.L, thigh.R, shin.R, foot.R`
   - **bird_v1** bones: `root, body, neck, head, wing.L, wingtip.L, wing.R, wingtip.R, tail, leg.L,
     leg.R`

   (A static body with no rig is fine too — the pipeline animates it procedurally. Then you only owe
   the named-by-region mesh.)
6. **Clean up.** Triangulate, merge doubles, remove interior/stray faces, recentre to the origin,
   confirm the tri budget. Export `body.obj` or `body.glb`.

---

## Verify the body BEFORE you texture it (the 5-minute check)

Run the body through the pipeline and **look at all 16 directions** before investing in textures.
This is the cheapest place to catch scale, front/back, and region mistakes.

```text
# 1. (optional) lint a manifest describing your body
python pipeline/tools/lint_external_asset.py your_body.asset.json

# 2. bake it to a sprite package (routes by file type automatically)
python pipeline/tools/bake_asset.py your_body.asset.json

# 3. build contact sheets from the baked package and open them
python pipeline/tools/make_contact_sheet.py pipeline/output/<variant_id>
#    -> <variant>_color_sheet.png  : 16 directions; the cyan facing arrow should sweep once around
#    -> <variant>_hit_sheet.png    : head=red torso=green arms=blue legs=yellow
```

You pass the body stage when:

- [ ] **16 *distinct* directions** — front-facing and back-facing frames clearly differ (rule 5). If
      heading N looks the same as the one 180° opposite, the body has no front — go back to step 3.
- [ ] **Scale reads right** — height looks correct relative to a 1.8 m reference.
- [ ] **Stands and faces correctly** — feet on the ground, facing down-right at direction 0, anchor
      (magenta cross) at the feet.
- [ ] **Hit regions cover the silhouette** and the colors match the body part underneath (head red
      on top, legs yellow at the bottom, etc.).
- [ ] **Tri budget** ~300–8 000; one mesh; no stray geometry.

Only once these pass is it worth UV-unwrapping and texturing.

---

## Worked references (copy these)

- **Humanoid body:** `pipeline/tools/meshes.py` → `humanoid()`. A body from boxes at real scale,
  foot at origin, facing +X, parts tagged head/torso/arms/legs. Note the explicit **face/visor + chest
  plate on +X** — those exist *only* to give the body a front; without them the figure was 180°
  symmetric and rendered the same front and back (the bug rule 5 warns about). This is the canonical
  example of "give it a front."
- **Bird body:** `pipeline/tools/gen_bird_fixture.py`. A bird from boxes — a head box (region head)
  at the front, a tail box (region torso) at the back, wings (arms) — naturally front/back distinct,
  skinned to `bird_v1`.

## After the body: textures, rig, animation

Once the body passes the check above, continue with
[`external_asset_contract.md`](external_asset_contract.md): UVs + base-color texture (§3), the rig +
skin if animated (§5), the animation clips (§6), and the small `*.asset.json` manifest (§7). The
**reuse split** there is why this stage matters: one body+texture per *variant*, but one rig + one
animation library shared across the whole *archetype* (10 birds = 10 bodies + 1 `bird_v1` rig + 1
animation library).
