# Generated-package intake — how a delivered model becomes a baked sprite package

A producer (the model/anim AI) delivers a **self-describing package** of source files. The pipeline
turns that into the `external_asset_v1` **`.asset.json` front door** that `bake_asset` consumes — the
producer does **not** hand-author the `.asset.json`. This doc is the contract for that hand-off and the
gates that protect it.

> **Why the pipeline synthesizes the front door (not the producer).** The `.asset.json` is a
> *pipeline-internal* schema: its archetype enum, rig names, and `region_source` change whenever the
> pipeline changes. Asking the producer to author it couples them to our internals — and they already
> decline to when the contract lags (the cow/ball packages shipped with a `package_manifest` note:
> *"a schema-valid external_asset_v1 manifest is not included when the current contract lacks the needed
> archetype/rig"*). So the producer ships their natural source format; **`intake_package.py` synthesizes
> the front door deterministically and gates the delivery.**

---

## What a package contains

Every delivered package is a directory whose inventory is declared in **`<id>.package_manifest.json`**:

```jsonc
{
  "package_manifest_version": "generated_asset_package_v1",
  "asset_id": "cow_brown_farm_v1",
  "entry_files": {                       // role -> filename; the gate checks every one EXISTS
    "glb_mesh":         "cow_brown_farm_v1.glb",
    "source_asset":     "cow_brown_farm_v1.source_asset.json",
    "animation_data":   "cow_brown_farm_v1_anim.json",
    "hitbox":           "cow_brown_farm_v1_hitbox.json",
    "physical_metrics": "cow_brown_farm_v1_physical_metrics.json",
    "materials":        "cow_brown_farm_v1_materials.json",
    "texture_atlas":    "cow_brown_farm_v1_texture_atlas.png",
    "sockets":          "cow_brown_farm_v1_sockets.json",
    "spell_orbits":     "cow_brown_farm_v1_spell_orbits.json"
  }
}
```

| File | Role | Feeds the asset.json |
|---|---|---|
| `<id>.package_manifest.json` | the inventory (`entry_files`) | file presence gate |
| `<id>.source_asset.json` | axes/units, part names, **hit_proxy_objects (region map)**, clips, **archetype/rig/fps** | most fields |
| `<id>_hitbox.json` | `world_metrics` (height/footprint/eye) + per-region AABBs | `world_metrics` |
| `<id>_anim.json` | `anim_clips_v1` keyframes targeting the rig's bone names | `files.animation_clips` |
| `<id>.glb` (or `<id>_rigged.glb`) | mesh (delivered, possibly an unrigged part-mesh set) | `files.mesh` |
| `<id>_materials.json` | per-part `region` + `base_color` | rig step's flat per-region colour |
| `<id>_texture_atlas.png` | base-colour texture | `textures.base_color` |

---

## The three fields the producer MUST declare (in `source_asset.json`)

Every other asset.json field maps deterministically from the package. These three are **designer-only**
— they have no other source, so the producer declares them in `source_asset.json`. (They are *optional*
in the schema for back-compat with internal descriptors, but the **intake gate requires them** for a
delivered package.)

| Field | Where | Example | If missing |
|---|---|---|---|
| `archetype` | top-level | `"quadruped"` | gate FAIL (must be one of the `external_asset` archetype enum) |
| `rig` | top-level | `"quadruped_v1"` | gate FAIL (a matching rig profile must be installed/shipped) |
| `fps` | per `clips_states` item (or top-level `default_fps`) | `"fps": 10` | falls back to `default_fps` → pipeline default `12` (gate WARNs) |

Optional: `default_state` (else synthesis uses `"idle"`, else the first clip).

> Before this contract, those three had **no home** — the first cow/ball intake had to *invent*
> `quadruped`, `quadruped_v1`, and all six fps values. Declaring them makes synthesis fully deterministic.

---

## Synthesis — `intake_package.py`

```bash
python pipeline/tools/intake_package.py synth <package_dir>            # print the asset.json
python pipeline/tools/intake_package.py synth <package_dir> --write    # write <id>.asset.json into the package
```

The full field map lives in the module docstring. Key rules:

- **`files.mesh` / `geometry.up`** — if a `<id>_rigged.glb` is present (the rig step ran) it's used with
  `up:"y"` (the rig step re-exports standard Y-up glTF); otherwise the delivered mesh is used with the
  declared `up_axis` (sign dropped, e.g. `"+Z"` → `"z"`).
- **`animations[state]`** = `{clip, frames, playback, fps}` from `clips_states`; `fps = clip.fps |
  default_fps | 12`.
- **`world_metrics`** = `hitbox.world_metrics` (authored — drives the `world_metrics_mismatch` detector).
- **`region_source`** = `"material_name"` — the rig step bakes the declared regions into the material names.

Synthesis is **deterministic and idempotent**: same package → byte-identical asset.json (gated by
`test_intake.py`).

---

## The intake gate — `intake_package.py lint`

```bash
python pipeline/tools/intake_package.py lint <package_dir>
```

Run **before** baking. **Errors** mean *do not bake* (the package is incomplete/inconsistent);
**warnings** bake but flag a review. It checks:

- **Inventory** — every `entry_files` path exists on disk.
- **Schema** — `source_asset.json` validates; the *synthesized* `asset.json` validates.
- **archetype** present + in the authoritative enum; **rig** present + a profile resolves
  (`schema/rig_profiles/<rig>.json` or the package's `schema_extensions/<rig>.rig_profile.json`).
- **Regions** — every `hit_proxy_objects.region` and every `hitbox.regions` key is one of the four
  engine body regions `{head, torso, arms, legs}` (shield/weapon/gear are deferred).
- **world_metrics** present (else the mismatch detector is disabled — a warning).
- **fps** resolvable for every clip; **default_state** is a real state.
- **Clip vocabulary** — warns when a clip is named off the **engine clip vocabulary** (`idle`, `walk`,
  `run`, `attack`, `hit`, + `jump`/`fall`/`crouch_idle`/`crouch_walk`). A clip authored as a synonym
  (`move`→`walk`, `shoot`→`attack`, `hurt`→`hit`, `punch`→`attack`) **bakes fine but the engine renderer
  never selects it** — it silently falls back to `idle`. Name a character's locomotion/attack/hit clips
  with the canonical names so they actually play. (This also runs in `lint_external_asset` on every bake.)
- **Rig readiness** — notes if no `<id>_rigged.glb` is present; `bake_asset` **auto-rigs** an unrigged
  delivery from the declared rig profile at bake time (see below), so no manual rig step is needed.

**`bake_batch` runs this automatically.** It discovers delivered packages (by `package_manifest.json`),
gates each, synthesizes the missing `asset.json`, then bakes — a gate-failing package is skipped and
reported, never baked into a wrong sprite:

```bash
python pipeline/tools/bake_batch.py creative/incoming --sheets    # gate + synth + bake every package
python pipeline/tools/bake_batch.py creative/incoming --dry-run   # gate + list what would bake / be skipped
```

---

## Preparing for new creatures (giant squid, dragon, …)

The cow surfaced the template stresses; here is what to do so a squid or dragon lands cleanly.

### 0. Orient it forward = +X — the head/travel direction
The bake spins the model about vertical Z in 16 equal steps from **exactly how it was authored** and
**reads no `forward` metadata**, so +X *is* heading-0. Build any non-biped facing +X by its travel
direction: a **quadruped**'s head/nose at `+X` (spine `+X`→`−X` tail), a fish/serpent's mouth, a
dragon's snout. A model built facing the wrong axis bakes 90/180° rotated **and passes every gate
silently** — the fix is to re-orient the *source* (`forward_axis` is inert; the bake will not correct
it). A radially-symmetric prop (ball/orb) has no forward and bakes near-identical in every direction —
that's correct; align a directional marker (the ball's arrow) to +X. See `modeling_the_body.md` rule 3.

### 1. Declare regions explicitly — never rely on part names
The four engine HIT regions are `head/torso/arms/legs` (R8 ids 1–4); there is **no** `tentacle`,
`wing`, or `tail` region. The producer **maps** creature parts onto the four, *explicitly*, in
`source_asset.json`'s `hit_proxy_objects` (and mirrors it in `hitbox.json`). The cow already does this —
*"front legs → arms, hind legs → legs to preserve four-region contract compatibility."*

The rig step (`rig_from_profile.py`) uses the **declared** region first and only falls back to keyword
inference when a part is undeclared, so a `tentacle_3` declared `legs` lands in legs (it would otherwise
keyword-collapse to torso), and a `wing_L` a designer declares `legs` lands in legs even though the
shared keyword table maps `wing → arms`. The keyword table is the single source in `constants.py`
(`region_for_name`), shared by the rigger and the bake, so the colour a part gets and the region the
mask assigns can never drift apart.

### 2. Add the archetype + ship a rig profile
A new creature class = one enum line + one rig profile:
1. add the archetype to `external_asset.schema.json`'s `archetype` enum (e.g. `"octopod"`, `"dragon"`);
2. add `pipeline/schema/rig_profiles/<rig>.json` (bone head/tail/parent + a `region_by_bone` map);
3. declare `archetype` + `rig` in the delivery's `source_asset.json`.
The gate fails loudly if the archetype is unknown or the rig profile is missing — at intake, not mid-bake.

### 3. Auto-rig is automatic — but it does RIGID part-skinning
An UNRIGGED part-mesh delivery (separate meshes + a rig profile but no armature in the glb) does **not**
need a manual rig step: `bake_asset` detects the missing armature and **auto-invokes `rig_from_profile`**
at bake time (threading the source up-axis + the materials/source_asset sidecars, and recording an
`auto_rigged` provenance note in the build log). The manual path still works — point `files.mesh` at a
pre-rigged glb and the auto-rig is skipped (a rigged glb already has a skin).

The limit to know: `rig_from_profile` binds each **part-mesh** 100 % to its nearest bone — perfect for
discrete parts (cow legs, a dragon's segmented tail), but a single continuous mesh that should *deform*
smoothly across many bones (an octopus tentacle that curls, a membranous wing) will move rigidly. Deliver
such creatures either **pre-rigged with smooth skin weights** or as **segmented parts** (one mesh per
bone-ish segment), so rigid skinning reads as articulation.

### 4. Watch the atlas budget
A big multi-clip creature at 256² overflows the 4096 single-page advisory (the cow already trips
`oversize_atlas_page`; the engine still loads single-page up to the ~8192 GPU cap). For a dragon with
many clips, expect the same flag — curate clips, shrink the canvas, or wait on engine paging (TASK-018).

---

See also: [`external_asset_contract.md`](external_asset_contract.md) (the asset.json contract itself),
and `build_log_warnings.md` in the pipeline repo (the silent-failure detectors that run during the bake).
