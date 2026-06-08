# Stage 4 — Paint the FINISHED skin

## PROMPT

Deliver a **finished** skin — no flat-grey placeholder, no swatch. The exact deliverable depends on
`texture_mode`, and the two modes are mutually exclusive at the contract level.

### If `texture_mode = textured`

- Paint a **real albedo** and bind it as the glb's **`baseColorTexture`** on every part (closes
  requirement (B) of `texture_capable`). The image must be embedded/referenced so the probe sees
  `bound_textures > 0` and `images > 0`.
- The painted atlas must be **colour-rich**, not a baked-flat colour: `atlas_colour_rich` needs
  `unique ≥ 64`, `entropy ≥ 3.0`, `largest single colour ≤ 0.65`. A textured delivery that bakes flat
  fails with `atlas_colour_rich_low` (error). Paint actual detail.
- Set provenance `provenance.texture.real_albedo = true` (a real painted skin).
- Drive base colour from the **Principled BSDF default**, not a node graph. A node-driven base colour
  (e.g. a vertex-colour Mix from a glTF re-import) trips `base_color_linked` (warn) — the
  silent-flat-grey risk. Bake the colour into the texture.

### If `texture_mode = flat_region`

- Shade each region by its **material `base_color_factor`** (per-region flat colour). This is a
  first-class, fully supported delivery — no UVs, no texture.
- **Do NOT bind a base-colour texture.** A `flat_region` delivery that binds a baseColorTexture is the
  **flat-via-degenerate-UV-texture hack** and is rejected by `flat_region_bound_texture` (ADR-0037,
  error). Drop the texture, or switch to `textured` with a real unwrap.
- **Do NOT claim `real_albedo: true`.** `flat_region` + `real_albedo:true` is `flat_region_real_albedo`
  (error). A flat_region package's `provenance.texture.real_albedo` must be false/absent.

### Calibration skins only

If you are building a calibration/oracle model, paint each region the **EXACT** `calib_v1` colour
(head red 216,38,38 · torso grey 130,130,130 · arm/wing_L green 42,196,64 · arm/wing_R blue
40,90,224 · legs purple 150,42,200 · tail orange 240,138,30), set `calibration` and
`real_albedo:false`. Calibration bypasses ADR-0028 escalation (the debug colours are intentional).

## CONSTRAINTS

- One mode, one skin form. Never both a `flat_region` material set **and** a bound texture.
- Skin-only variants: if this is a re-skin of an existing base, ship a `*.skin_delta.json` (texture +
  base reference) — geometry/UV/rig/hitboxes clone from the base; the swap is geometry+UV byte-identical
  or it hard-fails `skin_delta_geometry_changed`.

## GATES THIS STAGE MUST PASS

- `flat_region_no_bound_texture` (code `flat_region_bound_texture`, error) — flat_region binds NO texture.
- `flat_region_no_real_albedo` (code `flat_region_real_albedo`, error) — flat_region never claims real albedo.
- `atlas_colour_rich` (code `atlas_colour_rich_low`, error for textured non-calib) — painted atlas is rich.
- `base_color_source` (code `base_color_linked`, warn) — base colour is the Principled default, not node-driven.

## DONE WHEN

The skin is final: `textured` → a rich painted `baseColorTexture` is bound on every part and
`texture_capable` returns CAPABLE; `flat_region` → every region carries its `base_color_factor`, no
texture is bound, and `real_albedo` is not true. No placeholder grey remains.
