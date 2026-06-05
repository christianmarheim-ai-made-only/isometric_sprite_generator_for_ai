# Validator fixtures

Data-driven valid/invalid fixtures for the M1/M2 manifest validator, consumed by
`pipeline/tools/test_fixtures.py` (and via `pipeline/tools/build.py`).

Rather than commit many near-duplicate manifests and binary atlases, each case is
defined in `invalid_cases.json` and applied at test time to a fresh copy of the
generated pilot output (`pipeline/output/arrow_pilot/`). The real output is never
mutated.

- **valid:** the unmutated generated pilot must validate (`ok: true`).
- **invalid:** each case mutates one thing and must be rejected (`ok: false`) with
  an error containing `expect_error_substring`.

Case kinds:

- `manifest_set` — set `path` (keys/indices into `manifest.json`) to `value`.
- `manifest_delete` — delete `path`.
- `mask_region_pixel` — repaint the first hitmask pixel of `region_value` (inside
  frame 0's rect) to `new_value` (exercises the palette check).
- `mask_transparent_pixel` — set the first fully transparent / mask-0 pixel inside
  frame 0's rect to `new_value` (exercises the alpha→mask-0 rule).

To add a case, append to `invalid_cases.json`; no code change is needed for the
existing kinds.
