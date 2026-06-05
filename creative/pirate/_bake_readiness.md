# Bake Readiness — chr_pirate_duelist_v1 (game_iso_v1)

Decision-complete readiness report synthesizing the three sub-analyses (RIG-BINDING,
MATERIALS/REGIONS/TEXTURE, ANIM-CLIPS) against the actual delivered artifacts and the actual
pipeline code. **Verdict: READY TO BAKE. Zero blockers. Run the bake; then shard for engine load.**

Delivered package: `C:\Code\isometric_sprite_generator_for_ai\creative\pirate\`
Front door: `chr_pirate_duelist_v1.asset.json` (drives the route, the state list, and the lint).

---

## 1. BLOCKERS (stop the bake) — NONE

Every condition that would make `bake_asset.py` raise `SystemExit` has been checked against the
delivered files and is satisfied. There is nothing to edit before baking.

| Potential blocker | Where enforced | Status on this asset |
|---|---|---|
| `death` playback `"hold"` (not in enum) | `lint_external_asset.py:69`, `gate_engine_accept.py:52` | **ALREADY FIXED** — delivered `asset.json` and `_anim.json` both say `"once"`. No edit. |
| asset schema invalid | `lint_external_asset.py:33` | PASS — `external_asset_v1` valid. |
| declared `files.*` / `textures.*` missing on disk | `lint_external_asset.py:40-45` | PASS — `chr_pirate_duelist_v1.glb`, `chr_pirate_duelist_v1_anim.json`, `chr_pirate_duelist_v1_texture_atlas.png` all present. |
| unknown `rig` profile | `lint_external_asset.py:48` | PASS — `biped_v1` resolves to `schema/rig_profiles/biped_v1.json`. |
| anim_clips schema invalid / `rig` mismatch | `lint_external_asset.py:57-62` | PASS — `anim_clips_v1` clean post death→once; clips `rig="biped_v1"` == asset `rig`. |
| `playback` not in `loop|once`, `frames` < 1 | `lint_external_asset.py:68-72` | PASS — all 8 states `loop` or `once`, frames 5..12. |
| clip bone target not in rig (would skip channel) | `bake_anim_from_json.py:41` guard | PASS — all 13 keyed bones ∈ the 17 GLB joints; guard never trips, no empty-clip fallback. |
| missing clip → rest-pose state | `blender_render_anim.py:103` `actions.get(clip)` | PASS — 8 asset states ↔ 8 baked actions, bijective; `missing_clips` stays empty. |
| Gate-1 engine-acceptance of the baked manifest | `bake_asset.py:82` → `gate_engine_accept.engine_accept` | Expected PASS (see §4). Runs on the SINGLE-page manifest inside the bake. |

**No edits required to proceed.** Do not rename bones (canonical `biped_v1` set), do not touch
material names (all 19 map to a real region, zero torso fallbacks), do not edit `frames`/`fps`
(asset↔anim parity is exact 8/8).

> Regen caveat (only if someone re-runs the generator, NOT a blocker for this bake):
> `FILE: C:\Code\isometric_sprite_generator_for_ai\creative\pirate\generate_pirate_glb.py` — lines
> 674 and 710 still emit the stale `"playback": "hold"`. The DELIVERED artifacts were hand-fixed to
> `"once"`, so the bake is fine. But re-running this generator would re-introduce an invalid enum and
> re-block the lint. Change both `'hold'` → `'once'` before any regeneration.

---

## 2. DEGRADES (do not block the bake; output is shippable as-is) — least-invasive fixes

These do **not** stop the bake and do **not** cause silent rest-pose fallback. They are
quality/operational notes. The recommended action for the current goal (a clean, correctly-colored
package) is "none" for all but the atlas-paging item, which is the standard supported follow-up.

### 2a. Single-page atlas is oversize for engine load → SHARD (the one required follow-up)
- **What:** `bake_animated` packs all 1040 cells (65 frames × 16 dirs) into ONE page via
  `shelf_place(..., max_w=2048)` (default; `blender_bake.py:200`). `shelf_place` only WRAPS, it never
  raises a ceiling — so the bake SUCCEEDS, producing a ~2048-wide × very-tall single page. Gate-1's
  per-frame bounds check uses that page's own reported size, so it PASSES. **Not a bake blocker,
  not a Gate-1 blocker.**
- **Why it still matters:** a multi-thousand-pixel-tall single page exceeds the per-page budget
  (`MAX_PAGE_PX=4096`) the engine/GPU expects. The supported remedy is per-state paging.
- **Least-invasive fix:** run `shard_atlas.py` once after the bake (§3). It re-packs into one page
  per state. Largest state ≤ 12 frames × 16 dirs = 192 cells, which fits inside one 4096² page, so
  `OversizePageError` is NOT expected (no single state alone overflows). Result: a paged
  (`atlases.color.pages[]` / `hitmask.pages[]`, per-frame `page`) package the engine can lazy-load.
- **Operational note:** point any single-page debug validator (`validate_debug_subset.py`) at the
  PRE-shard package, not the paged manifest.

### 2b. Embedded texture renders FLAT (degenerate UVs) — accept; do not fix for this PoC
- **What:** every vertex of a material samples the tile CENTER (`generate_pirate_glb.py:461-465`),
  so the embedded 1024² atlas (wired as `baseColorTexture[0]` on all 19 materials) collapses to one
  near-solid swatch per material. `has_tex` evaluates True, render runs in `TEXTURE` mode
  (`blender_render_anim.py:135`), but the result is visually identical to flat per-material color.
- **Impact:** colors are CORRECT (navy coat, red sash, brass trim, warm skin); only texture
  detail/gradient is absent. Does not block; does not degrade region/color correctness.
- **Least-invasive fix (only if real texturing is later wanted, NOT now):**
  `FILE: C:\Code\isometric_sprite_generator_for_ai\creative\pirate\generate_pirate_glb.py` lines
  461-465 — assign each vertex a real UV inside its tile rect instead of `uv_center_gltf`. **Action
  for this bake: none.**

### 2c. External `..._texture_atlas.png` is NOT consumed by the bake — informational only
- **What:** the render path only ever reads the atlas EMBEDDED in the GLB. The standalone
  `chr_pirate_duelist_v1_texture_atlas.png` (and `textures.base_color` in the asset manifest) is
  never opened by `blender_render_anim.py`. It is producer-side / human-reference metadata.
- **Impact:** none on output. (Note: lint DOES require the file to EXIST —
  `lint_external_asset.py:43-45` — so leave it in place; just know it is decorative to the bake.)
- **Action: none.**

### 2d. Clip vocabulary off canonical engine vocab — downstream gameplay concern, not bake
- **What:** `move/run/shoot/reload/hurt/celebrate` are not the canonical `biped_v1` state names
  (idle/walk/punch/death…). The bake does NOT enforce engine vocab — `bake_animated` bakes whatever
  the asset `animations` map declares — so all 8 bake and render fine.
- **Impact:** purely a play-time selection mapping (engine falls back to idle for a state it does not
  recognize). Not a bake or rig failure.
- **Least-invasive fix:** do NOT rename clips in the delivered files. Handle as a gameplay
  state-name → clip-name mapping in the engine/asset-binding layer, or document the alias (see §5).
  **Action for this bake: none.**

### 2e. Unkeyed bones hold bind pose — correct, listed for completeness
- `root`, `hand.L`, `foot.L`, `foot.R` are never keyed by any clip. They hold bind pose. This is
  correct skeletal behavior, not a fault. **Action: none.**

---

## 3. Exact bake command + shard follow-up

Run from the pipeline repo root `C:\Code\isometric_sprite_generator_for_ai`. Requires Blender on
PATH or `$env:BLENDER` set (the rigged+animated route needs it; `bake_asset.py:56`).

**Step 1 — bake (lint → embed clips → bake_animated → Gate-1 → build_log + provenance):**
```powershell
python pipeline/tools/bake_asset.py creative/pirate/chr_pirate_duelist_v1.asset.json
```
- Output dir (default): `pipeline/output/chr_pirate_duelist_v1/`
  (= `PIPELINE_ROOT/output/<variant_id>`; override with `--out DIR`).
- Route taken: **"Blender / rigged + animated (clips embedded from animation_clips JSON)"** — it
  first writes `…_animated.glb` (clips embedded via `bake_anim_from_json.py`), then samples all 8
  clips × 16 dirs.
- Success line: `BAKE_ASSET OK [...]: chr_pirate_duelist_v1 -> ...  (1040 frames)[ N warning(s): ...]`.

**Step 2 — shard into per-state pages (required; single page is oversize for engine load, §2a):**
```powershell
python pipeline/tools/shard_atlas.py pipeline/output/chr_pirate_duelist_v1 --out pipeline/output/chr_pirate_duelist_v1_paged
```
- Expected: `SHARDED [per_state]: chr_pirate_duelist_v1 -> ...  (8 pages, 1040 frames)`.
- If it prints `SHARD FAILED: ... page(s) exceed 4096px`, a single state overflowed one page
  (NOT expected here — largest state is 192 cells). The remedy would be the within-state greedy
  split (FUTURE; `atlas_paging_contract.md §7`), not a config edit.

> The PAGED package (`…_chr_pirate_duelist_v1_paged/`) is the engine-deliverable. The pre-shard
> single-page package remains valid for contact-sheet/debug-subset inspection.

---

## 4. Post-bake verification

### Gate-1 — engine acceptance (runs automatically inside the bake; can re-run standalone)
- `bake_asset.py:82` calls `engine_accept(manifest)` on the SINGLE-page baked manifest; a non-empty
  result raises `SystemExit("baked package failed Gate-1: …")`. A clean bake means Gate-1 already
  passed. To re-run explicitly:
  ```powershell
  python pipeline/tools/gate_engine_accept.py pipeline/output/chr_pirate_duelist_v1/manifest.json
  ```
  Expect: `GATE 1 PASS`.
- What it checks for this asset: multi-state coverage — per (state, dir) frame_index 0..frames-1
  unique+covered for all 8 states × 16 dirs; `animations[state].directions == 16`;
  `len(frames) == Σ dirs·frames == 1040`; every rect w,h > 0 and within the atlas; `default_state`
  ("idle") ∈ animations; `eye_height_world (1.64) <= height_world (1.82)`. All expected to hold.
- Optional: re-run Gate-1 on the PAGED manifest too — `engine_accept` reads
  `atlases.color.size` (line 100); the paged manifest uses `pages[]` instead, so the bounds branch
  no-ops (aw=0) — still PASS. Coverage and metric checks are page-agnostic.

### 16/16 direction distinctness per state
- Verify each of the 8 states renders 16 DISTINCT direction sprites (no collapsed/duplicate
  facings). Source of truth: `DIRS=16` (game_iso_v1) in `blender_render_anim.py`; each (state,frame)
  emits one color + one region render per direction.
- By eye: on the contact sheet (below), within a state's frame row the 16 `d00..d15` cells must show
  the character ROTATING — the cyan FACING arrow (from the `direction_tip` socket) must sweep through
  16 distinct headings, and the silhouette must change pose-orientation across the row. Identical
  cells across directions = a direction-binning defect to flag.

### Contact sheet (human eyeball pass)
```powershell
python pipeline/tools/make_contact_sheet.py pipeline/output/chr_pirate_duelist_v1
```
- Writes `chr_pirate_duelist_v1_color_sheet.png` and `chr_pirate_duelist_v1_hit_sheet.png` into the
  package dir. Color sheet overlays the magenta anchor cross + cyan facing arrow; hit sheet recolors
  the R8 mask by region.
- Confirm on the COLOR sheet: 8 state banners (idle marked ◀ default), correct per-state
  `[playback, fps]` tags, all frame rows populated (no red "missing frame" outlines), solid correct
  colors (navy/red/brass/skin), 16 distinct directions per row (see above).
- Confirm on the HIT sheet: **all four regions present and plausibly placed** — head=red,
  torso=green, arms=blue, legs=yellow. No magenta (id 5 reserved-equip) should appear (body-only).
  This is the visual proof of the "zero torso fallback, 4 regions present" claim from the materials
  analysis.
- (Works on the single-page package directly. For the paged package, run it on the pre-shard dir —
  the sheet tool reads `atlases.color.path`, the single-page shape.)

### build_log warnings
- `bake_asset.py:104-106` prints a trailing `[ N warning(s): <codes> ]` and writes the full
  `build_log` into the output dir. After baking, READ it and triage every warning code:
  ```powershell
  python -c "import json,glob;{print(w) for w in json.load(open(glob.glob('pipeline/output/chr_pirate_duelist_v1/build_log*.json')[0]))['warnings']}"
  ```
  (or open the build_log JSON in the output dir directly).
- Expected for this asset: `region_fallback_materials` is EMPTY (all 19 materials mapped), so no
  region-fallback warning. Watch specifically for `oversize_atlas_page` (severity note about §2a),
  any `missing_clip`/`bone not in rig` (NONE expected), and any anchor/loop-seam warnings from the
  loop-seam gate. Anything unexpected → investigate before treating the package as final.

---

## 5. CONTRACT / INSTRUCTION updates this PoC implies

Concrete documentation/contract changes the pipeline owners should land so the next producer does
not hit the same rough edges:

1. **Producers MUST use `playback ∈ {loop, once}` — never `hold`.** `hold` is not in the
   `animation_clips.schema.json` enum and is rejected at BOTH the asset lint
   (`lint_external_asset.py:69`) and Gate-1 (`gate_engine_accept.py:52`). For a one-shot terminal
   pose (death), use `once` — the renderer treats anything `!= "loop"` as terminal-hold
   (`blender_render_anim.py:108`), so `once` lands the final frame correctly. Document this in the
   external_asset / animation_clips contract with the death example.
   *Also: fix the generator template (`generate_pirate_glb.py:674,710` `'hold'`→`'once'`) so it stops
   emitting an invalid enum on regen.*

2. **Document the gameplay state-name vs clip-name vocabulary gap.** `bake_animated` bakes whatever
   the asset `animations` map declares; it does NOT enforce the canonical engine state vocab
   (idle/walk/punch/…). So `move/run/shoot/reload/hurt/celebrate` bake fine but the engine will only
   SELECT states it recognizes (unknown → idle fallback at play time). Either (a) add a documented
   `move→walk` style alias map in the engine/asset-binding layer, or (b) publish the canonical state
   vocab in the contract and have producers name clips to it. Capture the decision in the
   multistate/engine contract so this is intentional, not incidental.

3. **Clarify `textures.base_color` semantics.** The bake renders ONLY the GLB-EMBEDDED atlas; the
   external `textures.base_color` PNG is required-to-exist by lint but never consumed by the renderer.
   Document explicitly that `textures.base_color` is producer/reference metadata and that the
   engine-facing color comes from the embedded glTF image — so producers do not expect edits to the
   standalone PNG to change the bake.

4. **Texturing realism is a known producer-side limitation (degenerate UVs), not a pipeline bug.**
   For genuinely textured output, producers must author real per-vertex UVs within each tile rect
   (vs the single tile-center UV). Note in the producer guide that "embedded atlas present" does NOT
   imply "textured result" unless UVs span the tile. Optional pipeline hardening: emit a build_log
   warning when a material's UVs are degenerate (all vertices share one UV) so this is visible rather
   than silent.

5. **Make atlas paging part of the standard multi-state runbook, not an afterthought.** Any
   16-dir × many-frames × many-state asset overflows a single page; `bake_asset.py` does not shard,
   and `bake_animated` packs with `max_w=2048` and no ceiling raise. Document the canonical sequence
   **bake → `shard_atlas.py` → ship the paged package**, and that single-page Gate-1 passing does NOT
   mean the page is engine-loadable at size. (Optionally have the bake emit the `oversize_atlas_page`
   build_log note automatically when the single page exceeds `MAX_PAGE_PX`.)

6. **Rig-profile gap: none for `biped_v1`.** The delivered GLB joints, the rig profile, and the clip
   bone targets are identical 1:1 (17 joints; 13 keyed). No rig-profile change is implied by this
   PoC. (Recording this as a positive finding: `biped_v1` is validated end-to-end by a real delivered
   asset.)
