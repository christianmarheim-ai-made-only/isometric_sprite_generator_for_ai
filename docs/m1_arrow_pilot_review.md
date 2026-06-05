# M1/M2 Arrow Pilot — Review

**Status: PASS.** The M1/M2 direction-only arrow pilot proves the engine-facing
seam end to end (generate → atlas → manifest → validator → Rust loader), and the
facing is correct in pixels, not just in metadata.

## Verified

- **Facing math.** The generator (`screen_x=(wx−wy)·32`, `screen_y=(wx+wy)·16`)
  agrees with the rendered arrows and the locked facing table on all eight
  cardinals. `dir02` renders straight down, `dir10` straight up, and the spin
  winds clockwise on screen as world yaw increases CCW (because `screen_y` is
  down). The dir02/dir10 diagnostic pair is wired with tight numeric tolerance.
- **Discrete masks.** The R8 hitmask atlas contains only `{0, 2}` across all 16
  frames and the packed atlas — edge extrusion introduced no blended region IDs.
  This is now structural (via `Image.NEAREST`), not incidental — see fix pass.
- **Hash gate.** The smoke test passes both ways: a valid manifest is accepted,
  and a corrupted `contract_hash` is rejected — and rejected for the hash reason
  specifically.
- **Validator coverage (203 checks).** JSON schema; `contract_hash` vs lockfiles;
  `state_contract_version`; variant cross-check (`supported_states`,
  `frame_canvas`, `direction_count`); per-state playback/direction/frame counts
  vs the states lock; required sockets; required markers; image modes/sizes;
  rect-inside-atlas; `rect` dims == `frame_canvas`; `mask_rect` dims == `rect`;
  anchor/sockets/boxes within the per-frame rect; `origin` socket == anchor;
  alpha < 8/255 ⇒ mask 0; mask values in palette; boxes bound their region's mask
  pixels; dense directions `0..N-1`; world yaw == direction bin center (i·360/N); the
  dir02-down / dir10-up diagnostic; world metrics positive with `eye ≤ height`.
- **Rust reference loader.** `hit_test` has the anchor Y-flip and the scale term
  (`frame_pixel = screen_offset / render_scale + anchor`);
  `critical_runtime_asserts` mirrors `contract_hash` + `state_contract_version` +
  `eye ≤ height`; `direction_index` round-bins to the nearest frame center, matching
  the contract and engine `sprite.rs::direction_index`.

## Fix pass (commit `f7e2750`)

- `contract_hash` narrowed to `sprite_contract.lock.json` only (was all three
  lockfiles), so growing the variant roster no longer invalidates existing
  manifests. **Before** `sha256:6cba4162…`, **after** `sha256:87ceec8b…`.
- `Image.NEAREST` extrusion — mask discreteness is now structural.
- Validator bounds frame-local coords against the per-frame `rect` (forward-compat
  for M3 tight-crop). No existing check removed; still 203, `ok: true`.

## Human gate (`debug_sheet.png`)

Confirmed visually: `dir02` down, `dir10` up, clockwise spin, stable anchor cross.

## Scope

Direction-only. No weapons, equipment, effects, or animation clips. See
`adr/ADR-0015` and `docs/next_slices_plan.md`.
