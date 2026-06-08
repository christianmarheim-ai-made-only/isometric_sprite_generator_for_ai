# UV + Texture Format Spec — `texture_mode: textured` delivery (v3)

**Status:** normative. This is the EXPLICIT, machine-enforced contract for how UV maps and
texture files must be authored when you declare `texture_mode: textured` in an
`external_asset_v2` manifest. Every requirement below is enforced by a real tool in
`pipeline/tools/`; the authoritative behaviour is the code, and this document is exact to it.

Ground every decision in the actual gate, not in this prose. The gate is
`pipeline/tools/glb_texture_probe.py :: texture_capable(glb)`, called from
`pipeline/tools/lint_external_asset.py` (the front door) BEFORE any bake (ADR-0026).

---

## 0. The locked target (NOT yours to change)

You are delivering into a fixed render target, `game_iso_v1`. These values are constants and a
producer does not negotiate them:

| Property | Value |
|---|---|
| Projection | 2:1 dimetric, azimuth 45°, elevation 30° |
| Directions | 16 |
| Forward / up | forward `+X` (direction 0), up `+Z` |
| Tile | 64 × 32 px |
| Frame canvas | 256 px (`CANVAS`, `constants.py`) |
| Atlas page cap | ≤ 4096 px per dimension (`MAX_PAGE_PX`, `constants.py`) |

You control the mesh, the UVs, the texture, the rig, the clips, and the hitbox sidecar. You do NOT
control the camera, the direction count, the canvas, or the atlas paging — the baker owns those.

---

## 1. The delivery contract

The manifest is validated against `pipeline/schema/external_asset.schema.json`
(`asset_contract_version: "external_asset_v2"`). For a textured delivery:

- `texture_mode` is **REQUIRED** and must be `"textured"` (the other legal value is `"flat_region"`).
  Absent ⇒ treated as `flat_region` (back-compat); `texture_mode_missing` is an `input` ERROR if the
  field is structurally absent where required.
- `archetype` ∈ `{biped, bird, quadruped, ball, dragon}`.
- `files.mesh` MUST be a `.glb` (or `.gltf`). **A textured `.obj` is rejected** with
  `obj_textured_unsupported` (`input`, ERROR): an `.obj` carries no embedded `baseColorTexture`, so it
  can only be a static `flat_region` asset.

### A COMBAT CREATURE must ship (focus of this spec)

A combat creature is a textured, animated, hittable delivery. It MUST include:

1. **A rig** — a known profile (`pipeline/schema/rig_profiles/<rig>.json`, e.g. `biped_v1`). The
   `archetype` must match the rig (`archetype_rig_mismatch`, ERROR).
2. **The required clips** — `idle` is the hard gate-required clip for every archetype
   (`CLIP_REQUIREMENTS`, `constants.py`); a combat creature additionally SHIPS `attack`, `hit`, and
   `death`, and SHOULD ship `walk` + `run`. Clip names must be on the engine vocabulary
   (`ENGINE_CLIP_VOCAB`); an off-vocab name (e.g. `move`, `shoot`, `hurt`) bakes but is never
   selected by the renderer and silently falls back to `idle` — `offvocab_clip` (WARN) flags the
   rename (`move→walk`, `shoot→attack`, `hurt→hit`). A missing required clip is
   `missing_required_clip` (ERROR).
3. **A FINISHED skin** — for `textured`, a REAL painted `baseColorTexture` bound in the glb (this
   document). (For `flat_region`, instead a per-region material `base_color_factor` — and NO texture.)
4. **A `region_hitboxes` sidecar** — `<variant_id>_hitbox.json` (or referenced via `files.hitbox`),
   with ≥ 2 distinct regions each carrying valid `min`/`max` AABBs (ADR-0036; `bake_asset.py ::
   _explicit_region_path`). This is the authoritative, explicit region map; with it present a
   single-material art model bakes without `region_fallback_torso` being treated as a *silent*
   fallback.

---

## 2. The degeneracy rule — EXACT, from `glb_texture_probe.py`

`texture_capable(glb)` reads the glTF JSON + BIN with **no Blender** and decides whether the model
may legitimately declare `textured`. It is capable iff **every part-mesh has (A) a real UV unwrap
(non-degenerate, in-range) AND (B) a base-colour image bound as `baseColorTexture`.**

For each primitive's `TEXCOORD_0`, the probe computes the UV bounding box
`w = umax − umin`, `h = vmax − vmin`, with these thresholds (literal, from the module):

```
EPS_EXTENT = 1e-3      # per-material UV bbox WIDTH and HEIGHT must each exceed this
EPS_AREA   = 1e-5      # per-material UV bbox AREA must exceed this (catches a UV collapsed to a LINE)
BLEED      = 1e-3      # islands may bleed this far outside [0,1]
```

A material's UV is **degenerate** (rejected) iff:

```
w < 1e-3   OR   h < 1e-3   OR   (w * h) < 1e-5
```

In plain terms:

- **Collapsed to a POINT** — both `w` and `h` tiny ⇒ degenerate.
- **Collapsed to a LINE** — one axis tiny (e.g. `w = 0`, `h = 0.8`) ⇒ degenerate, because it samples a
  single texel column/row and is unusable. The `(w*h) < 1e-5` area term is what catches the line/sliver
  case that a width-and-height-only test would miss.

**This is the hard rejection threshold. It is NOT a quality target.** The "good UV island coverage is
roughly 0.4–0.9 of the [0,1] square" guidance is a QUALITY goal you should hit for crisp texels — it
is *not* what `degenerate_uv` measures. A perfectly tiny-but-valid 0.05-wide island passes the
degeneracy gate (it is not collapsed) yet is a poor unwrap; conversely there is no upper coverage
bound in the gate.

Separately, the probe records **out-of-range** UVs when any coordinate falls below `−BLEED` or above
`1 + BLEED` (i.e. outside `[−0.001, 1.001]`). Islands may bleed up to `1e-3` outside `[0,1]`; beyond
that is recorded in `record["out_of_range_uv"]`.

### Mode-aware escalation (ADR-0028)

`degenerate_uv` and the hitbox `region_fallback_torso` are default-WARN
(`error_codes.py`). For a **textured, non-calibration** delivery they ESCALATE to ERROR in
`build_log.py` (so `build_log.ok` flips false). `flat_region` keeps them as warnings; a calibration
package bypasses escalation (its colour pass is intentional). Net effect: for a real combat creature,
a degenerate UV that "bakes flat" is a hard failure — there is no quietly-flat path.

---

## 3. The texture file — EXACT requirements

1. **Bound IN the glb (embedded).** The `baseColorTexture` MUST be a bound image inside the `.glb`
   (`images[].bufferView`, i.e. embedded — not an external `uri`). `texture_capable` requires
   `bound > 0 AND len(images) > 0`; otherwise it returns `texture_unbound`. A glb that ships UVs but
   no bound image, or an image present but not referenced by any material's `baseColorTexture`, is
   NOT capable.
2. **Power-of-two square dimensions ∈ {512, 1024, 2048, 4096}.** sRGB colour space (the
   `baseColorTexture` is colour data, not data-linear). 4096 is the hard ceiling
   (`MAX_PAGE_PX = 4096`); the baker auto-shards 8+ state characters into per-state pages
   (ADR-0037 in-baker atlas paging), and `oversize_atlas_page` (ERROR) fires if any baked page
   exceeds 4096.
3. **The bound glb texture is authoritative.** A sidecar PNG listed under `textures.base_color` is
   **provenance/debug only and is NEVER authoritative** — only the embedded-glb base colour renders
   this iteration (Workbench TEXTURE pass; see the schema's `textures` note). `normal`, `roughness`,
   `metallic` are RECORDED but NOT rendered. If you ship a rich sidecar PNG but the glb's bound image
   is degenerate/flat, you get a flat bake — the sidecar does not save you.
4. **Base colour must be a TEXTURE, not a node-driven constant.** If a material's Base Color is
   driven by a node graph (e.g. a vertex-colour Mix from a glTF re-import) rather than the Principled
   `baseColorTexture`, `base_color_linked` (WARN, never escalates — it is the real silent-grey risk
   only) fires: the material risks rendering as silent flat grey. Bind a real `baseColorTexture`.

---

## 4. The rule for UV islands per part

1. **One real UV unwrap per visual part.** Every primitive that carries a material must have a
   `TEXCOORD_0` whose bounding box clears the degeneracy thresholds in §2. A primitive with no
   `TEXCOORD_0` counts as `no_uv`; if *every* primitive is `no_uv`, the probe returns `texture_unbound`
   (no UVs anywhere ⇒ cannot sample a texture).
2. **No undeclared overlap.** Distinct visual parts must occupy distinct UV space unless you
   intentionally and declaredly share islands (e.g. mirrored limbs). Undeclared island overlap is
   `uv_overlap_undeclared` (`texture`, ERROR) — two parts silently sampling the same texels is a
   correctness bug, not a space optimisation.
3. **Skin deltas** (texture-only variants cloned from a base) must keep geometry **and UVs IDENTICAL**
   to the base — only the texture differs. A skin delta that changes geometry is
   `skin_delta_geometry_changed` (ERROR); the base must itself be texture-capable
   (`skin_delta_base_not_capable`, ERROR).

---

## 5. Failure modes you must avoid (code → meaning → fix)

| Error code | Stage / sev | What it means | Fix |
|---|---|---|---|
| `degenerate_uv` | texture / WARN → **ERROR when textured** | A material's UV bbox collapsed to a POINT (`w<1e-3` and `h<1e-3`) OR a LINE/sliver (`w*h<1e-5`). | Give that part a real unwrap that clears `EPS_EXTENT` on both axes AND `EPS_AREA` on area. |
| `texture_unbound` | texture / ERROR | No `baseColorTexture` bound + an image present (`bound>0 AND images>0` failed), OR every primitive has no `TEXCOORD_0`. | Bind an embedded `baseColorTexture`; ensure every textured part has a UV channel. |
| `orphan_texture` | texture / ERROR | A texture/atlas exists in the package but is not actually bound + sampled by the model (the inverse of "capable"): the probe sees no usable bound+UV'd image, so the texture is orphaned. | Embed the image and reference it from each material's `pbrMetallicRoughness.baseColorTexture`, with real UVs that sample it. |
| `base_color_linked` | texture / WARN (never escalates) | A material's Base Color is node-driven (not the Principled `baseColorTexture`) → silent-grey risk. | Connect a real `baseColorTexture` image to Base Color. |
| `uv_overlap_undeclared` | texture / ERROR | Distinct visual parts share UV space without declaring it. | Separate the islands, or declare the intentional share. |
| `flat_region_bound_texture` | texture / ERROR | A `flat_region` delivery binds a base-colour texture — the "flat-via-degenerate-UV-texture" hack (looks textured, bakes ~one texel per material). | If you want a texture, declare `texture_mode: textured` with a REAL unwrap; otherwise drop the texture and use per-region material base colours. |
| `blank_frame` | bake / ERROR | A baked direction/state rendered ENTIRELY empty (all-background hitmask crop). | Fix the mesh/clip/orientation so every baked frame has a silhouette. |
| `oversize_atlas_page` | bake / ERROR | A baked atlas page exceeds `MAX_PAGE_PX` (4096). | Keep source texture ≤ 4096 PoT; the baker shards states, but a single oversized texture still overflows. |
| `atlas_colour_rich_low` | texture / ERROR | EVERY baked colour page is flat/swatch (`unique<64`, `entropy<3.0`, or `largest>0.65` per `texture_metrics.atlas_colour_rich`). | Ship a genuinely painted texture — a one-colour or gradient fill reads as flat. |

Note: `degenerate_uv` (point AND line) and `texture_unbound`/`orphan_texture` are decided UP FRONT by
`texture_capable` at the front door, before any bake — an orphan atlas or collapsed UVs are rejected
deterministically and never baked flat. `blank_frame`, `oversize_atlas_page`, and
`atlas_colour_rich_low` are decided on the BAKED outputs in `build_log.py`.

---

## 6. Calibration models (only if you ship one)

A *calibration* package is a debug/oracle build that proves the texture, UVs, AND hitbox all agree.
It paints each region an EXACT calibration colour (`calib_v1`, `pipeline/tools/calib_spec.py`) and the
`region_hitboxes` must cover the matching colour; the oracle then samples each hitbox centre and
verifies it reads the expected colour.

**Calibration colours (`CALIBRATION_COLORS`, EXACT sRGB 0..255):**

| Region | Colour | sRGB |
|---|---|---|
| head | red | `(216, 38, 38)` |
| torso | grey | `(130, 130, 130)` |
| arm_left (LEFT arm / wing) | green | `(42, 196, 64)` |
| arm_right (RIGHT arm / wing) | blue | `(40, 90, 224)` |
| legs | purple | `(150, 42, 200)` |
| tail | orange | `(240, 138, 30)` |

**Immutable, versioned calibration metadata (`CALIBRATION_MODELS` — reproduce these EXACTLY; a
calibration model is never re-modelled):**

| | `calib_biped_v1` | `calib_dragon_v1` |
|---|---|---|
| height_world | 1.80 m | 2.128 m |
| eye_height_world | 1.62 m | 1.638 m |
| footprint_radius_world | 0.40 m | 1.55 m |
| mass | 75 kg | 862 kg |
| regions | head, torso, arm_left, arm_right, legs | head, torso, arm_left, arm_right, legs, tail (wings = arm_left/right) |

A calibration package sets `real_albedo: false` and bypasses the textured-mode escalation (its flat
debug colours are intentional). A combat creature is NOT a calibration build — it ships a real painted
skin, not the calib colour pass.

---

## 7. Checklist (before you ship a textured combat creature)

- [ ] `texture_mode: "textured"` in the manifest; `archetype` ∈ the 5 legal values and matches `rig`.
- [ ] `files.mesh` is `.glb`/`.gltf` (NOT `.obj`).
- [ ] Every visual part has its OWN `TEXCOORD_0` with a UV bbox that clears `w≥1e-3 AND h≥1e-3 AND
      area≥1e-5` (no point, no line, no sliver).
- [ ] UV islands target ~0.4–0.9 coverage of `[0,1]` (quality), all within `[−0.001, 1.001]` (no
      out-of-range bleed beyond 1e-3).
- [ ] No undeclared island overlap between distinct parts.
- [ ] A REAL painted `baseColorTexture` is EMBEDDED in the glb (`images[].bufferView`), sRGB, square
      PoT ∈ {512, 1024, 2048, 4096}.
- [ ] Base Color is the texture, not a node-driven constant (no `base_color_linked`).
- [ ] No degenerate-UV "flat-via-texture" hack; if you wanted flat, you'd be `flat_region` with NO
      bound texture.
- [ ] Clips: `idle` (required) + `attack`, `hit`, `death` shipped; `walk`/`run` recommended; all on
      the engine clip vocabulary.
- [ ] `<variant_id>_hitbox.json` sidecar present with ≥ 2 regions, each with valid `min`/`max` AABBs.
- [ ] Any sidecar PNG under `textures.*` is understood as provenance/debug only — the glb's bound
      image is authoritative.

---

## 8. How to verify BEFORE you ship — run the `texture_capable` probe

The probe is standalone (stdlib only) and is exactly what the front door runs:

```bash
python pipeline/tools/glb_texture_probe.py path/to/your_model.glb
```

Expected on success:

```
CAPABLE      path/to/your_model.glb
   reasons=[]  record={'primitives': N, 'no_uv': 0, 'degenerate_uv': [], 'out_of_range_uv': [],
                       'bound_textures': >=1, 'materials': M, 'embedded_images': >=1, 'external_images': 0}
```

If you see `NOT-CAPABLE`, the `reasons` list names the gate you tripped (`degenerate_uv`,
`texture_unbound`, …) and `record` shows the offending material names in
`record['degenerate_uv']` / `record['out_of_range_uv']`. Fix every named material until `reasons` is
empty.

Then run the full front-door lint (schema + files + texture-capability + clip/rig/hitbox checks):

```bash
python pipeline/tools/lint_external_asset.py path/to/your_asset.asset.json
```

`ASSET LINT OK` means the package will be ACCEPTED for bake. `ASSET LINT FAIL` prints every
contract violation with its error code — resolve all of them before delivery. Do not rely on the bake
to "fix" a UV or bind a texture: a non-capable textured glb is rejected at the front door (ADR-0026)
and never baked.
