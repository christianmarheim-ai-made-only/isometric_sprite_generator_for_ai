# Texturing the body

**Audience:** whoever paints the **texture** for a body that's already modeled (see
[`modeling_the_body.md`](modeling_the_body.md)). This stage adds the **base-color texture** (the
look) — and optionally normal / roughness — onto the body's UVs.

You do **not** texture in the abstract: you get the **actual body mesh with a UV unwrap** and a **UV
layout template**, and you paint into that. A ready-to-use example ships in
**`pipeline/examples/texture_starter/`** so you can see exactly what "the model + the layout + the
result" looks like.

---

## The starter kit (the model + layout you paint on)

In `pipeline/examples/texture_starter/`:

| File | What it is |
|---|---|
| `humanoid_uv.glb` | the body, **UV-unwrapped**, materials named by region (`head/torso/arms/legs`), **no texture** — this is the model you paint onto |
| `humanoid_uv_layout.png` | the **UV layout template** — every face drawn in texture space, tinted by region (head=red, torso=green, arms=blue, legs=yellow). Paint inside these islands. |
| `uv_checker.png` | a UV-validation texture (rainbow checker) |
| `humanoid_textured.glb` + `humanoid_textured.asset.json` | a **worked example**: the body with `uv_checker.png` wired as base color, ready to bake |
| `humanoid_textured_preview.png` | what that example renders to through the pipeline (16 directions) |

Make the same kit for **your own** body:

```text
# 1. a UV-validation checker (reuse the one above, or:)
python pipeline/tools/gen_uv_checker.py my_checker.png

# 2. (humanoid worked example) unwrap + export the UV body, layout, and a checker-textured glb
blender --background --python pipeline/tools/gen_texture_starter.py -- OUTDIR pipeline/tools my_checker.png
python pipeline/tools/draw_uv_layout.py OUTDIR/uv_islands.json OUTDIR/uv_layout.png
```

For a non-humanoid body, unwrap it in your own DCC (Blender/Maya), use `gen_uv_checker.py` to make a
checker, and validate with the bake below — the rules and the verify step are identical.

---

## What the pipeline needs from your texture

1. **A UV unwrap.** Non-overlapping islands. The body from the modeling stage should already have
   one; if not, unwrap it (a cube/box projection reads cleanly on blocky bodies, smart-UV on organic
   ones). The renderer samples your texture through these UVs.
2. **Base color = PNG, sRGB, power-of-two** (512–2048 px). This is the "diffuse"/albedo — the color
   of the surface. (The pipeline renders with `view_transform = Standard`, so your sRGB colors show
   as authored — no filmic/AgX shift.)
3. **Wire it as the glTF base color**, i.e. an **Image Texture → Principled BSDF "Base Color"** on
   each material, then export `.glb` (the image embeds). The pipeline detects that and renders your
   texture (Workbench **TEXTURE** pass, studio-lit). Alternatively ship the PNG separately and list
   it under `textures.base_color` in the asset manifest.
4. **KEEP the region-keyworded material names.** This is the one thing texturing can quietly break.
   The gameplay **HIT regions come from the material *name*, not the texture** — `head/torso/arms/
   legs` (case-insensitive substring; full list in [`modeling_the_body.md`](modeling_the_body.md)).
   You may split into as many materials as you like for texturing **as long as every name still
   contains a region keyword** — e.g. `head_skin`, `torso_armor`, `arm_cloth_L`, `leg_boot_R`. Do
   **not** rename them to `skin` / `cloth` / `metal` — that silently dumps everything into `torso`.
   (The worked example proves regions stay intact after texturing — its hit sheet is still
   head=red / torso=green / arms=blue / legs=yellow.)
5. **Bake light/form into the base color.** The render is flat-ish (Workbench studio light), so the
   texture carries the read: paint **value contrast, ambient occlusion, and large shading** into the
   base color. A flat untextured fill will look flat.
6. **Paint for iso scale.** The sprite is small and seen from a fixed 2:1 dimetric angle — only the
   top/oblique-facing surfaces show, and detail finer than ~1 px on-screen is wasted. Prioritize
   **silhouette-edge color, big shapes, and value blocking** over fine detail.

> Body-only this iteration: texture the body. No weapon/shield/gear textures yet.

---

## Do it, step by step

1. **Open the UV'd body** (`humanoid_uv.glb`, or your own). Confirm it has a UV map.
2. **Validate the UVs with the checker** — apply `uv_checker.png` as base color and bake (command
   below). Every square should read roughly square and similar-sized; big stretching or seams across
   a visible face means re-unwrap before painting.
3. **Paint the base color** into the layout (`humanoid_uv_layout.png` as a guide), region by region.
   Bake AO / large shading in. sRGB, power-of-two.
4. **Wire it up** — set the painted PNG as each material's Base Color (Image Texture node), keeping
   the region-keyworded material names. Export `.glb`.
5. **(Optional) normal / roughness / metallic** maps (linear, referenced from the same materials)
   for nicer shading.
6. **Write/extend the asset manifest** (`*.asset.json`) — see
   [`external_asset_contract.md`](external_asset_contract.md) §3/§7.

---

## Verify it renders (before you call it done)

Bake the textured body and look at all 16 directions:

```text
python pipeline/tools/lint_external_asset.py your.asset.json
python pipeline/tools/bake_asset.py your.asset.json
python pipeline/tools/make_contact_sheet.py pipeline/output/<variant_id>
```

You pass the texture stage when:

- [ ] **The texture actually shows** on the body in the `*_color_sheet.png` (not a flat fill) and
      reads at sprite scale.
- [ ] **Hit regions survived** — the `*_hit_sheet.png` is still head=red / torso=green / arms=blue /
      legs=yellow. If a region went missing or everything turned green (torso), a material lost its
      region keyword (rule 4).
- [ ] **16 directions still distinct**, anchor at the feet, value reads against a dark and a light
      background.

This is the same flow the worked example uses: `humanoid_textured.glb` → `bake_asset` →
`make_contact_sheet` → `humanoid_textured_preview.png` (the checker visibly wraps the body, regions
intact).

---

## Where this fits

`modeling_the_body.md` (build + UV the body) → **this doc** (paint the texture) →
[`external_asset_contract.md`](external_asset_contract.md) (rig + animation + the asset manifest) →
`bake_asset.py` (one command → sprite package).

**Reuse:** the **texture is per-variant** — one per model (each of 10 birds gets its own). The rig
and animation library are shared across the archetype, so re-texturing a new variant never touches
the animation.
