# Authoring a model's data (overview)

One 3D model yields several **small, model-derived data packages**. Each is derived from the model's
own known data, so a single powerful AI can produce **all of them for one model in one pass** — and
iterate, because everything is compact text/numbers it can compute and adjust directly.

| Stage | How-to | Derived from the model's… | What you produce |
|---|---|---|---|
| 1. Body mesh | [`modeling_the_body.md`](modeling_the_body.md) | (you build it) | `.obj`/`.glb`, real scale, facing +X, a **front**, parts named by region |
| 2. Texture | [`texturing_the_body.md`](texturing_the_body.md) | the body's **UVs** | sRGB base-color PNG (ships a UV-unwrapped model + layout to paint on) |
| 3. Animation | [`generating_animation_data.md`](generating_animation_data.md) | the rig's **bone names** + bind pose | `anim_clips_v1` JSON — per-bone keyframes (one file drives every variant on that rig) |
| 4. Hitbox / collision | [`generating_hitbox_data.md`](generating_hitbox_data.md) | the **region-tagged vertices** | `hitbox_v1` JSON (capsule + per-region AABB); the R8 hit-mask bakes automatically |

The **synergy**: it's the *same* model data viewed four ways — UVs for the look, bone names for the
motion, region-tagged vertices for the hits, geometry for the silhouette. Tag and measure once;
every package falls out. Animation and hitbox in particular are **pure derivations** (keyframe angles
the AI reasons out; min/max over vertices) — no art pass, ideal for raw iterative computation.

## Order & glue

1–2 are the body + its look; 3 needs a rig (add per [`external_asset_contract.md`](external_asset_contract.md) §5);
4 is free once parts are region-tagged. Bundle the files with a small **asset manifest**
(`*.asset.json`, contract §7), then one command bakes the sprite package:

```text
python pipeline/tools/bake_asset.py your.asset.json
python pipeline/tools/make_contact_sheet.py pipeline/output/<variant_id>   # eyeball 16 directions
```

**Scale (the payoff):** rig + animation library are shared per *archetype*; mesh + texture are
per *variant*. So **10 birds = 10 bodies/textures + 1 `bird_v1` rig + 1 animation file**, and the
hitbox for each falls out of its geometry. One AI can churn the whole set.

> Body-only this iteration: no weapons/shields/gear (HIT regions 5–7 reserved).
