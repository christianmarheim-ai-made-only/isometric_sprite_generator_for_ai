# Stage 9 — Package + deliver (bake, prove ok=true)

## PROMPT

Bake the asset and prove the production `build_log.json` reports `ok: true`. This is the final gate —
the bake renders all 16 directions × every clip, packs the atlas (paging if needed), decodes the R8
hitmask, and runs the output-fidelity checks. Your job is to make it come back clean.

Run the production bake:

```
python pipeline/tools/bake_asset.py <variant>.asset.json --out <bake_dir>
```

Then open `<bake_dir>/build_log.json` and confirm:

- **`ok: true`** — i.e. Gate-1 engine-accept passed AND no warning has `severity: error`.
- **No `blank_frame`** (ADR-0037, error) — every baked direction/state rendered a non-empty
  silhouette. A blank frame means a direction/clip rendered empty (a failed/empty render).
- **No `oversize_atlas_page`** (error) — every atlas page ≤ **4096 px** (`MAX_PAGE_PX`). An 8+-state
  combat character auto-shards into per-state ≤4096 pages (in-baker atlas paging, ADR-0037); confirm
  the pages, not a single oversized sheet.
- **`hit_regions_present`** lists the body regions you expect (e.g. `[1,2,3,4]`), not torso-only — your
  explicit `region_hitboxes` sidecar (Stage 7) drove multi-region labelling.
- For **textured non-calibration**: no escalated `degenerate_uv` / `region_fallback_torso` /
  `atlas_colour_rich_low` errors (ADR-0028). For **flat_region**: those stay warnings.
- **`verification_build_log_disagree`** must NOT appear — the `verification_report.json` is a pure
  projection of the build_log, so the two `ok` flags agree by construction (`ok_agreement`).

Optionally run `python pipeline/tools/calib_oracle.py <bake_dir>` to confirm the clips are
VERIFIED-APPLIED (attack moves arms, locomotion moves legs, no dead clip).

Assemble the delivery package: the `<variant>.glb` (rigged + skinned + clips embedded),
`<variant>.asset.json` (`external_asset_v2`), `<variant>_hitbox.json` (region_hitboxes sidecar), any
`base_color` texture (textured), and the `build_log.json` provenance record.

## CONSTRAINTS

- You do not change canvas/page-size/direction-count to make the bake pass — fix the model. A genuinely
  accepted, expiring exception may carry a valid waiver (downgrades a specific error to `waived`,
  keeping `ok: true`), never a blanket bypass and never on `real_albedo`.
- The shipped package must be self-contained and re-bakeable from the manifest alone.

## GATES THIS STAGE MUST PASS

- `no_blank_frames` (code `blank_frame`, error) — no empty baked direction/state.
- `atlas_page_size` (code `oversize_atlas_page`, error) — every page ≤ 4096 px.
- `ok_agreement` (code `verification_build_log_disagree`, error) — build_log.ok == verification.ok.
- Net result: **`build_log.json` → `ok: true`** with zero `severity: error` warnings.

## DONE WHEN

`bake_asset.py` produces a `build_log.json` with `ok: true`, no `blank_frame`/`oversize_atlas_page`
errors, the expected `hit_regions_present`, and the full package (glb + asset.json + `_hitbox.json` +
texture + build_log) is assembled and ready to deliver.
