# game_iso_v1 — Model Authoring Contract

Everything an AI (or human) needs to produce **all the data for a new model** that the `game_iso_v1`
sprite pipeline turns into a 16-direction sprite package. One model yields several small,
model-derived data packages: **mesh + texture + animation + hitbox + a tiny manifest** — each
derived from the model's own known data, so one producer can author the whole set in one pass.

You produce the **3D source + small JSON descriptors**. You do **not** produce sprites — the pipeline
bakes those from what you deliver.

---

## Read in this order

1. **`docs/authoring_overview.md`** — the map: one model → four data packages, the order, the synergy.
2. The four how-tos (each is compact and self-checking):
   - **`docs/modeling_the_body.md`** — build the untextured body (real metric scale, **+X forward**,
     give it a *front*, parts named by HIT region).
   - **`docs/texturing_the_body.md`** — paint the base color onto the body's UVs (ships a
     UV-unwrapped model + a layout template to paint on).
   - **`docs/generating_animation_data.md`** — author motion as `anim_clips_v1` JSON (per-bone
     keyframes targeting the rig's bone names; one file animates every variant on that rig).
   - **`docs/generating_hitbox_data.md`** — derive the collision capsule + regions (pure min/max over
     vertices; no art).
3. **`docs/external_asset_contract.md`** — the SPEC: every field of the `<variant>.asset.json` you
   deliver, what's required vs optional, validation, and how each delivery bakes.

## What you deliver, per variant

A model file (`.glb` preferred, or `.obj`) + a **`<variant>.asset.json`** (schema:
`schema/external_asset.schema.json`). Worked examples are in `examples/`.

## Validate + bake (commands run against the pipeline repo)

```text
python pipeline/tools/lint_external_asset.py  your.asset.json            # validate BEFORE delivery
python pipeline/tools/bake_asset.py           your.asset.json            # one command -> sprite package
python pipeline/tools/make_contact_sheet.py   pipeline/output/<variant_id>   # eyeball all 16 directions
```

`bake_asset.py` routes by file type (`.obj` → numpy; static `.glb` → Blender; rigged `.glb` +
`animations` → Blender animation baker; add `files.animation_clips` to embed text-authored clips
first). The tools live in the pipeline repo (`pipeline/tools/`), not this package — this package is
the **spec + instructions + examples** they consume.

Every shipped example **lints clean with full file checks straight from this folder** (the meshes
they reference are in `test_meshes/`) — e.g. `lint_external_asset.py examples/grunt.asset.json`. The
one exception is `examples/bird_v1.asset.json`, a reuse **template** that points at an illustrative
(not-shipped) texture; lint it with `--no-files`.

## What comes back (output format)

- **`docs/multistate_sprite_contract.md`** — the manifest + color/hitmask atlases the engine loads
  (states, tight-crop sizing, anchor, `mask_rect`).
- **`docs/atlas_paging_contract.md`** — multi-atlas paging for large models (16 dirs × many frames ×
  many actions × higher resolution split across atlas pages; backward-compatible).

## Conventions (non-negotiable)

- **Units = metres.** A 1.8 m biped is 1.8 units tall.
- **Up = +Z** internally; declare source `up` (`y`/`z`).
- **Forward = +X** — the model faces +X = **direction 0**. Required this iteration (declared-only;
  not auto-rotated).
- **Origin = ground footprint centre** (feet at z=0, footprint centred on x=y=0).
- **Body-only this iteration:** HIT regions are head / torso / arms / legs (ids 1–4). 5–7
  (weapon/shield/gear) are reserved for a future iteration — no authoring path yet.

## Contents of this package

```
README.md                     this file
docs/                         the overview + 4 how-tos + 2 output contracts
schema/                       JSON Schemas (Draft 2020-12):
  external_asset.schema.json    the <variant>.asset.json you deliver
  animation_clips.schema.json   anim_clips_v1 (text keyframes)
  hitbox_spec.schema.json       hitbox_v1 (optional verification artifact)
  sprite_manifest.schema.json   the output manifest (incl. atlas paging)
  source_asset.schema.json      (legacy source descriptor)
  rig_profiles/                 biped_v1, bird_v1 — bone names, parents, bind-pose
                                positions, region map, and per-archetype states
examples/                     worked *.asset.json, animation/, hitbox/, atlas_paging/, texture_starter/
test_meshes/                  the small box-fixture meshes the examples reference (.obj/.mtl/.glb)
```

## Versions

`external_asset_v1` · `anim_clips_v1` · `hitbox_v1` · sprite output (`sprite_manifest_*_v1`) ·
atlas paging (additive). Rig profiles are versioned (`biped_v1`, `bird_v1`); a new bone layout = a
new profile id.
