# Self-verify gate — run this and pass it BEFORE handoff

A package handed off without a passing self-verify is **incomplete**. The receiving pipeline re-runs everything anyway (your reports are a gate *input*, never trusted blind), but a green self-verify is what makes the handoff automatic.

## 1. Lint the manifest (input gate — no Blender)

```text
python pipeline/tools/lint_external_asset.py <variant>.asset.json
```
Must print `ASSET LINT OK`. This enforces the schema, declared-files-exist, rig-is-known, clip-vocab, and — when you declare `texture_mode: textured` — the **texture-capable** gate (real UVs + a bound `baseColorTexture`). An orphan atlas / collapsed UVs / `.obj`+textured is rejected **here**, before any bake.

## 2. Bake (the pipeline)

```text
python pipeline/tools/bake_asset.py <variant>.asset.json
```
Produces `pipeline/output/<variant_id>/` with `color_atlas.png`, `hitmask_atlas.png`, `manifest.json`, `build_log.json`, and (once wired) `verification_report.json`.

## 3. Build the contact sheets and look at all 16 directions

```text
python pipeline/tools/make_contact_sheet.py pipeline/output/<variant_id>
#  -> <variant>_color_sheet.png : the cyan facing arrow sweeps once around; textures read at sprite scale
#  -> <variant>_hit_sheet.png   : head=red torso=green arms=blue legs=yellow
```

## 4. The machine-checkable pass bar

```text
texture_mode: textured  =>  build_log has_tex == true
                            degenerate_uv_materials == []
                            atlas richness PASSES (THRESHOLDS.md) unless a calibration waiver applies
                            provenance.texture.real_albedo == true (false for calibration)
regions intact          =>  hit_sheet is head=red / torso=green / arms=blue / legs=yellow
                            (no region collapsed to torso)
16 distinct directions  =>  front != back (THRESHOLDS.md) unless radial_symmetric + exempt
all clips present        =>  no missing_clip_rest_pose; required clips per archetype present
ok agreement            =>  preflight_report.ok == verification_report.ok == build_log.ok == true
```

## 5. Emit your `preflight_report.json`

Record what you ran (so the package proves it was not handed off blind):

```json
{
  "preflight_report_version": "producer_preflight_v1",
  "producer_spec_version": "model_producer_delivery_spec_v1",
  "asset_id": "<variant_id>",
  "texture_mode": "textured",
  "ok": true,
  "tool_versions": { "blender": "<x.y.z>", "pipeline_commit": "<sha>" },
  "checks": {
    "geometry": {"status":"pass"}, "texture": {"status":"pass"}, "rig_skin": {"status":"pass"},
    "animation": {"status":"pass"}, "hitbox": {"status":"pass"}, "bake": {"status":"pass"}
  },
  "artifacts": {
    "color_sheet": "contact_sheets/<variant>_color_sheet.png",
    "hit_sheet": "contact_sheets/<variant>_hit_sheet.png",
    "build_log": "build_log.json",
    "verification_report": "verification_report.json"
  }
}
```

`preflight_report.ok == false` means **do not deliver**.

## If you cannot pass the textured bar

Declare `texture_mode: flat_region` and ship honest per-region solid colours (no UVs/atlas required). That is a first-class, fully-supported delivery. **Do not** declare `textured` and bind an orphan/degenerate atlas — that is the exact failure class this contract exists to stop.
