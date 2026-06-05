# Sprite Pipeline M1/M2 Review Bundle

This bundle contains two things:

1. **ADR review pack** for the blockers identified before M3: arms, weapons, shields, gear, metrics, sockets, effects, AI generation, validation, and atlas/compression policy.
2. **M1/M2 direction-only implementation** using a generated arrow sprite to verify direction bins, screen projection, atlas packing, hitmask plumbing, anchors, manifest structure, lockfile hash, and validation.

The implementation intentionally does **not** solve arms/weapons/equipment in this iteration. Those decisions are captured in proposed ADRs and should be reviewed before M3.

## Directory layout

```text
adr/
  INDEX.md
  ADR-0006 ... ADR-0017

pipeline/
  lockfiles/
    sprite_contract.lock.json
    sprite_states.lock.json
    sprite_variants.lock.json
  schema/
    sprite_manifest.schema.json
  tools/
    contract_hash.py
    generate_arrow_pilot.py
    validate_manifest.py
    smoke_test.py
  output/arrow_pilot/
    manifest.json
    color_atlas.png
    hitmask_atlas.png
    debug_sheet.png
    expected_facing_table.json
    validation_report.json
    frames/
  docs/
    M1_M2_RUNBOOK.md
    ASSUMPTIONS.md
    BEVY_LOADER_INTEGRATION.md
  bevy_reference/
    src/
```

## Quick start

From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python pipeline/tools/generate_arrow_pilot.py --clean
python pipeline/tools/validate_manifest.py pipeline/output/arrow_pilot/manifest.json --report pipeline/output/arrow_pilot/validation_report.json
python pipeline/tools/smoke_test.py
```

Expected result: validator reports `ok: true`, and smoke test confirms that a corrupted hash fails closed.

## Human review target

Open:

```text
pipeline/output/arrow_pilot/debug_sheet.png
```

Verify:

- `dir00` is world `+X / East` and appears down-right under the 2:1 iso projection.
- `dir02` points straight down.
- `dir10` points straight up.
- The red cross marks the frame-local anchor `[64,112]`.
- Direction order winds clockwise on screen as world yaw increases CCW.

## What is implemented

- 16 deterministic direction frames.
- one color atlas with 4px padding/extrusion.
- one R8 hitmask atlas with 4px padding/extrusion.
- manifest with `contract_hash`, `state_contract_version`, atlas rects, frame-local anchor, socket, boxes, world-yaw values, and screen direction vectors.
- JSON schema.
- lockfile hash computation.
- validator cross-checks for lockfiles, states, images, masks, boxes, metrics, dense directions, and M1 diagnostic pair.
- Bevy/Rust reference snippets for direction lookup, anchor conversion, and hit testing.

## What is intentionally deferred

- Blender headless rendering.
- real character capsule placeholder.
- rig-derived hit proxies.
- arms/weapons/shields/gear combat surfaces.
- markers and effects.
- runtime Bevy plugin integration.
- AI generation.
- compression/streaming.

Those are covered by the ADRs and should be handled as M2A/M3/M4 work.
