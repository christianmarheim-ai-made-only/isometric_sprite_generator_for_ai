# Stage 3 — UV unwrap

## PROMPT

> **`flat_region` shortcut:** if `texture_mode = flat_region`, you need **no** UV unwrap and **no**
> texture — skip to Stage 4 and shade by material `base_color_factor`. This stage is for
> `texture_mode = textured` only.

For a **`textured`** delivery, produce a **real, non-degenerate UV unwrap** for every part-mesh. The
host-side probe `glb_texture_probe.texture_capable()` reads the glTF UVs with **no Blender** and
decides up-front whether the model may legitimately declare `textured`. It is capable iff **every**
part has (A) real UVs AND (B) a bound `baseColorTexture`. Unwrap so it passes (A) now; bind the texture
in Stage 4 for (B).

Requirements the probe enforces (exact thresholds from `glb_texture_probe.py`):

- **Not degenerate.** Per-material the UV bbox **width** and **height** must each exceed `1e-3`
  (`EPS_EXTENT`) **and** the bbox area must exceed `1e-5` (`EPS_AREA`). A UV collapsed to a **point**
  (both tiny) or a **line / sliver** (one axis tiny, e.g. `w=0, h=0.8`) is `degenerate_uv` — it samples
  a single texel and is unusable. Give each island real 2-D extent.
- **In range.** Islands stay within `[0,1]` with at most `1e-3` bleed (`BLEED`); out-of-range UVs are
  `out_of_range_uv`. Pack inside the unit square.
- **TEXCOORD_0 present on every primitive.** A primitive with no `TEXCOORD_0` counts as no-UV; if
  *every* primitive lacks UVs the probe returns `texture_unbound`.
- **No undeclared overlap.** Overlapping islands that aren't an intentional mirror trip
  `uv_overlap_undeclared`. Lay out islands without accidental overlap.

See `uv_format.md` (sibling spec) for island/layout conventions. Mind that ADR-0028 makes
`degenerate_uv` a hard **error** for a textured non-calibration delivery — there is no "textured but
flat" middle ground.

## CONSTRAINTS

- `textured` must be **GLB/GLTF**, never `.obj` (an `.obj` textured delivery is rejected with
  `obj_textured_unsupported`). `.obj` is for static `flat_region` only.
- The UVs ride **inside the glb** (the probe reads the embedded accessors); an external/orphan atlas
  with no bound texture is rejected (`orphan_texture` / `texture_unbound`).

## GATES THIS STAGE MUST PASS

- `degenerate_uv` (code, warn → **error** when textured non-calibration) — no point/line/sliver UVs.
- `uv_overlap` (code `uv_overlap_undeclared`, error) — no undeclared island overlap.
- `has_bound_tex` (code `texture_unbound`, error) — UVs exist to be sampled (texture bound in Stage 4).

## DONE WHEN

`python pipeline/tools/glb_texture_probe.py <model>.glb` reports the UV side clean — `degenerate_uv: []`,
`out_of_range_uv: []`, `no_uv: 0` — i.e. every part carries real in-range UVs. (`texture_unbound` may
still show until Stage 4 binds the baseColorTexture; the UV unwrap itself is done.)
