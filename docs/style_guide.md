# Texture / Style Guide (C5)

How sprites should look so they stay readable at isometric game scale and pack
cleanly through the pipeline. Body-only this iteration; the rules are general.

## Readability acceptance (per asset)

Every authored sprite frame must pass:

- **Readable 256 px preview** — clear at authoring scale.
- **Readable 128 px preview** — clear at ~in-game scale (`frame_canvas` is 128).
- **Silhouette preview** — the alpha-only shape is recognizable on its own.
- **Straight (non-premultiplied) alpha** — transparent background, `RGBA`.

Generate these with `python pipeline/tools/make_style_assets.py` (writes
`pipeline/style/style_previews.png`) and eyeball them.

## Palette

- Use the limited palette in `pipeline/style/palette.json` (rendered to
  `pipeline/style/palette_swatch.png`). Keep counts low; reuse role ramps
  (shadow / mid / light) per material (skin, cloth, leather, metal, neutral).
- This is the **visual** palette. It is distinct from the **hitmask** region
  palette (`none/head/torso/arms/legs/...` in `sprite_contract.lock.json`), which
  is discrete region IDs, never a color.

## Outline & shading

- Unified dark **outline** (`outline` color), ~1 px at frame scale, around the
  readable silhouette.
- Light from a consistent high angle; use the shadow → mid → light ramp. Avoid
  busy interior detail that disappears at 128 px.
- Prioritize **silhouette first**: shape reads before color.

## Alpha & anti-aliasing

- Color may be anti-aliased; keep edges crisp enough to read at 128 px.
- A pixel with color alpha `< 8/255` is background and must be hitmask `0`
  (validator-enforced).
- The R8 **hitmask is never anti-aliased** — discrete region IDs only
  (`Image.NEAREST` everywhere). Color AA and mask discreteness are independent.

## Contrast & background

- Author on transparent; never bake a background.
- Ensure value contrast against typical ground tiles so the sprite does not melt
  into the map at small scale.

## Tooling

- `pipeline/tools/make_style_assets.py` renders the palette swatch and the
  readability preview sheet, and self-checks palette shape + straight alpha.
