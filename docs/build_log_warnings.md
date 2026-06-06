# Build-log warning codes — the silent-failure detection layer

Every production bake (`bake_asset.py`, `produce_verify_set.py`) writes a per-bake
`build_log.json` and a per-batch `build_index.json`. These carry **warning codes** that surface the
failures which otherwise pass every structural gate (Gate-1, 16/16-direction distinctness, region
presence) on a sprite that is actually wrong. **This is how a batch flags a bad variant without a
human eyeballing each one.**

## How to triage a batch

1. Open `pipeline/output/<batch>/build_index.json`. Each variant row has `ok`, `warnings` (count),
   and **`warning_codes`** (which codes fired).
2. Any variant with `ok: false` produced an **error**-severity warning — treat it as suspect.
3. Look up each code below for what it means and what to do.

`ok` is `false` when Gate-1 fails **or** any `error`-severity warning fired. A `warn`-severity code
does not flip `ok` (the package is shippable but has a quality issue); an `info` code is pure
provenance (e.g. `auto_rigged`) and never flips `ok`.

## Warning codes

| Code | Severity | Means | What to do |
|---|---|---|---|
| **`non_upright_biped`** | error | A biped's silhouette is **landscape, not portrait** (median frame aspect > 1.0, or > 35% of frames wider than tall). The character almost certainly **baked lying down / wrong up-axis**. *This is the failure that passes Gate-1 + 16/16-distinctness silently — a flat character still spins into 16 distinct frames.* | Check `geometry.up` in the asset matches how the glb is actually authored (a Z-up glb must declare `up:"z"`). |
| **`world_metrics_mismatch`** | error | The asset's **authored** `world_metrics.height_world` and the bake's **measured** height diverge by > 25%. Wrong scale, or the model baked lying down (measured height collapses). | Verify the glb scale (1 unit = 1 m) and orientation. ~10% over authored is normal (a hat sits above the body-height); 40%+ is a bug. |
| **`degenerate_uv`** | warn | A **textured** material's UVs collapse to ~one point, so the embedded atlas renders as one **flat swatch** (textured-but-flat). Per material. | Producer-side: author real per-vertex UVs spanning each tile rect. Colors are still correct; only fine detail is lost. |
| **`auto_rigged`** | info | The delivery had **no armature**, so `bake_asset` built one from the declared rig profile (`rig_from_profile`) on the fly. The baked glb is **pipeline-derived**, not the delivered mesh (`provenance.mesh` hashes the derived rigged glb). Not a defect — a provenance record. | None. To ship pre-rigged instead, point `files.mesh` at a rigged glb. |
| **`base_color_linked`** | warn | A material's Principled **Base Color is driven by a node graph** (not the socket default). A glTF **re-import of a mesh that shipped vertex colours** wires `Color-Attribute → Mix → Base Color`, leaving the socket default at flat **0.8 grey** while the real colour sits upstream. MATERIAL-mode reads the default → **silent grey render**. The renderer now recovers the upstream constant colour, but flags the material so the recovery is verified. | If colour looks right, no action. To remove at source, strip vertex-colour attributes before export (the auto-rigger `rig_from_profile.py` now does this). |
| **`oversize_atlas_page`** | error | An atlas page exceeds `MAX_PAGE_PX` (4096). A full multi-clip combat character at 256² overflows a single page. | Engine consumes single-page only today (loads up to the ~8192 GPU cap, so it still works). For production: shard (paging = TASK-018), shrink the canvas, or curate clips. |
| **`region_fallback_torso`** | warn | A material name matched **no** region keyword (`head`/`torso`/`arms`/`legs`) and silently defaulted to torso (id 2). The hitmask region for those faces is wrong. | Rename the material to contain the body-part keyword (`region_source: material_name`). |
| **`missing_clip_rest_pose`** | warn | A declared animation state's clip is **absent from the glb** → that state rendered the static rest pose, not the animation. | Embed the clip (or fix the clip name) so the state animates. |

## Calibration (where the thresholds come from)

The two orientation detectors were calibrated on the `chr_pirate_duelist_v1` PoC, which first baked
**lying down** and passed every other gate:

- **Upright:** the correct standing pirate is median aspect **0.57**, **4.7% landscape**; a lying-down
  biped is ~median 1.0+ / ~40% landscape. Threshold `median > 1.0 OR landscape > 35%` separates them
  with wide margin (`celebrate`'s arms-out 24% per-state stays safe). **Archetype-gated to `biped`** —
  a bird's wings are legitimately wide.
- **Metrics:** authored 1.82 vs measured 2.015 (a tricorn hat) = **10.7%**; the lying-down bake was
  **43%**. Threshold **25%** separates hat-overhang from orientation/scale bugs. Height only —
  footprint legitimately differs (measured foot-stance vs declared body radius).

Detector logic is gated by `test_bake_warnings.py` (pure Python, in `build.py --ci`).

## Known gaps (not yet auto-detected)

- **Forward-axis** is now a LIVE correction: the baker rotates the declared `geometry.forward` onto +X
  (gated by `test_forward_axis.py`), so a mis-faced delivery is a one-line metadata fix. The remaining
  gap is the *oracle*: the correction trusts the DECLARED value, so a model whose declared `forward`
  disagrees with its actual geometry still bakes rotated and passes distinctness. Auto-detecting the
  TRUE forward (a facing oracle) is not yet built (see `external_asset_contract.md`).
- **Stray geometry:** the example generators leave a 0-material `Icosphere` in each glb (universal,
  benign — ignored for measurement, doesn't visibly pollute). A genuinely material-bearing second
  mesh would render into the sprite; not currently flagged (it would false-positive on the Icosphere).
