# ADR-0038: Front portrait render for the character screen

Status: Proposed
Date: 2026-06-08
Related: game_iso_v1 (the LOCKED gameplay camera — this is deliberately NOT that), ADR-0035 (model origin =
ground-footprint anchor / forward = +X), ADR-0032 (faithful colour / Workbench light), the render paths
`pipeline/tools/blender_render.py` + `blender_render_anim.py` + `blender_preview.py`, `bake_asset.py`.

## Context

The pipeline bakes the 16-direction **gameplay** sprite set through the locked `game_iso_v1` camera
(2:1 dimetric, azimuth 45° / elevation 30°). That 3/4 down-angle is correct for the iso playfield but is a
**poor portrait**: the character is foreshortened, tilted, and seen from above — fine for a unit on the map,
wrong for a **character screen** (character select, party/stats panel, inventory, "now playing as…"), where
the player wants to look the creature **in the face, upright, face-on**.

There is no front, eye-level image of a creature in the package today. The engine's character screen has
nothing clean to show, and cropping a gameplay iso frame looks like a gameplay sprite, not a portrait.

## Decision

Emit a dedicated **front portrait** image per `character` variant, rendered through a **separate** camera —
never the locked gameplay one — and reference it from the manifest. Pinned choices:

1. **Separate camera, gameplay contract untouched.** The portrait is an additional render pass; it does NOT
   change `game_iso_v1`, the 16-direction frames, anchors, hitmask, or world-metrics. game_iso_v1 stays
   locked and authoritative for gameplay.
2. **Front, eye-level, orthographic.** The camera sits on the creature's **forward** axis looking back at its
   face, `up = +Z`, **elevation 0°** (true front, no iso skew, no perspective). The declared `geometry.forward`
   is rotated to face the camera (every creature faces the viewer regardless of authored forward), the same
   `forward_yaw` correction the gameplay bake already uses. Result: an upright, undistorted front view.
3. **Default/idle rest pose, static.** One still image from the default state's frame 0 (the calm "hero"
   pose), not an animation.
4. **Presentation lighting (STUDIO), not gameplay FLAT.** A portrait is a presentation image, so it uses the
   flattering Workbench STUDIO light rather than the faithful-but-flat gameplay pass. (Calibration models are
   exempt — they are never shown in a character screen.)
5. **Dedicated portrait canvas + recorded framing.** Render at **512×512** (2× the gameplay frame), the
   creature centred and framed to its full height with a small margin; record the tight bounding box + a
   `head_anchor`/`foot_anchor` so the UI can place a frame, nameplate, or selection glow deterministically.
6. **Additive manifest contract.** A new top-level block, ignored by the gameplay loader:
   ```jsonc
   "portrait": {
     "path": "portrait.png",
     "size": [512, 512],
     "pose": "idle",            // default state, frame 0
     "style": "front_eye_level", // reserved: future "front_three_quarter"
     "bbox": [x, y, w, h],       // tight crop of the creature within the canvas
     "lighting": "studio"
   }
   ```
   Emitted only for `variant_class: character` (not `probe`/`terrain`/`effect`); a `calibration` model omits
   it. Vendor the field into `pipeline/schema/engine/manifest.schema.json` (additionalProperties is already
   true, so it is forward-compatible) + `sprite_manifest.schema.json`, and add it to the reference loader
   when the engine team wires the character screen.

## Consequences

- The character screen gets a clean, upright, face-on image with deterministic framing anchors.
- Cost: one extra Blender render pass per character (negligible vs the 16×N gameplay frames) + one PNG.
- Pure addition: single-page/paged gameplay manifests are byte-identical; no gameplay gate changes.
- The portrait is **engine-facing presentation**, so the engine team owns whether/how the character screen
  consumes it; the pipeline's job is to emit it to this contract. Treat the field as Proposed until the
  engine confirms the shape (size, anchors).

## Open questions (resolve before Accepted)

- **Exact angle:** pinned to true front (elevation 0) per the request; do we also want a `front_three_quarter`
  style (a slight hero angle for depth)? Left as a reserved `style` value.
- **Crop vs full canvas:** ship the tight `bbox` (above) and let the UI decide, vs pre-cropping the PNG.
- **Resolution:** 512 proposed; confirm with the character-screen UI scale.
- **Animated portrait:** static idle frame 0 now; a looping idle portrait is a possible later `portrait.mode`.

## Implementation sketch (when Accepted)

Add a `render_portrait` pass (reuse `blender_preview.py`'s camera scaffolding) invoked from `bake_asset` for
`character` variants: front orthographic camera, STUDIO light, idle pose, 512², write `portrait.png`, compute
the bbox, and add the `portrait` block to the manifest. Gate it behind a `--portrait` / asset flag initially
so existing bakes are unchanged, then make it default for characters. Add a test (Blender-gated) that a
character bake emits a non-empty, correctly-framed `portrait.png` + the manifest block.
