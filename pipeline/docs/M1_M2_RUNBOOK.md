# M1/M2 Arrow Pilot Runbook

## 1. Generate assets

```bash
python pipeline/tools/generate_arrow_pilot.py --clean
```

Outputs are written to:

```text
pipeline/output/arrow_pilot/
```

Important files:

```text
manifest.json
color_atlas.png
hitmask_atlas.png
debug_sheet.png
expected_facing_table.json
validation_report.json
frames/color/*.png
frames/hitmask/*.png
```

## 2. Validate manifest and images

```bash
python pipeline/tools/validate_manifest.py pipeline/output/arrow_pilot/manifest.json --report pipeline/output/arrow_pilot/validation_report.json
```

Expected output:

```json
{
  "ok": true,
  "errors": []
}
```

## 3. Fail-closed smoke test

```bash
python pipeline/tools/smoke_test.py
```

Expected output:

```text
PASS: valid manifest accepted
PASS: corrupted contract_hash rejected
```

## 4. Human direction review

Open:

```text
pipeline/output/arrow_pilot/debug_sheet.png
```

Check:

```text
dir00: yaw 0°, world +X/East, appears down-right
dir02: yaw 45°, points straight down
dir10: yaw 225°, points straight up
```

If `dir02` and `dir10` are swapped, the engine and exporter disagree about world sign or projection orientation.

## 5. Engine integration checklist

- Load `manifest.json`.
- Assert `contract_hash` equals lockfile hash from engine repo.
- Assert `state_contract_version` equals engine-pinned state version.
- Load `color_atlas.png` into a texture atlas layout using the manifest rects.
- Load `hitmask_atlas.png` into CPU-readable bytes for hit testing.
- Convert frame-local anchor to engine sprite anchor.
- Render directions 0 through 15 as a spin test.
- Verify mouse hit-test uses:

```text
frame_pixel = screen_offset / render_scale + anchor
```

where frame coordinates are top-left origin and +Y down.
