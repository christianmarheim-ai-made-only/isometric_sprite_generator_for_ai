# Sprite Pipeline Runbook

How to build, validate, and review the sprite-pipeline output. Start here.

## Prerequisites

- Python 3.x with `pillow` and `jsonschema`:
  ```
  pip install -r requirements.txt
  ```

## One command

```
python pipeline/tools/build.py --ci
```

Regenerates the pilot, validates (and writes the report), runs the smoke test and
the regression tests, and exits nonzero if any step fails.

## Step by step

1. **Generate:** `python pipeline/tools/generate_arrow_pilot.py --clean`
2. **Validate:** `python pipeline/tools/validate_manifest.py pipeline/output/arrow_pilot/manifest.json --report pipeline/output/arrow_pilot/validation_report.json` → expect `ok: true`
3. **Smoke test:** `python pipeline/tools/smoke_test.py` → `PASS valid` / `PASS corrupted-hash-rejected`
4. **Regression tests:**
   - `python pipeline/tools/test_contract_hash.py`
   - `python pipeline/tools/test_mask_discrete.py`
   - `python pipeline/tools/test_fixtures.py`

## Human review (debug sheet)

Open `pipeline/output/arrow_pilot/debug_sheet.png` and confirm:

- `dir02` points straight **down**
- `dir10` points straight **up**
- the spin winds **clockwise** on screen as the direction index increases
- the red anchor cross sits in the same spot in every cell

If `dir02` / `dir10` are swapped, the exporter and engine disagree about world
sign or projection orientation — **fix the source, never the winding** (the
clockwise-on-screen reading is correct; see `docs/next_slices_plan.md` §2).

## Outputs

`pipeline/output/arrow_pilot/`: `manifest.json`, `color_atlas.png`,
`hitmask_atlas.png`, `debug_sheet.png`, `expected_facing_table.json`,
`validation_report.json`, `frames/`.

## Contract

The engine-facing contract (camera, coordinates, palette, formats, sampling,
packing) lives in `pipeline/lockfiles/sprite_contract.lock.json`; `contract_hash`
is its SHA-256, and a mismatch is a hard failure. Design decisions live in
`adr/`; the original M1/M2 runbook is `pipeline/docs/M1_M2_RUNBOOK.md`.
