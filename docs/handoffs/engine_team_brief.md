# Handoff: Engine team (read-only repo) — textured sprites + hit data

- For: the engine team / a chat working in `C:/Code/Claude` (the **read-only authoritative** engine repo).
- Parent: [`../arcs/ARC-0001-textured-verified-skinned-models.md`](../arcs/ARC-0001-textured-verified-skinned-models.md).
- Nature: **FYI + one engine-side ADR ask**. The sprite-bake pipeline (this repo) is doing the heavy lifting; these are the seams where the engine is affected. No pipeline change here forces an engine change for the *current* flat path — a textured atlas is a drop-in.

The engine consumes only `color_atlas.png` + the R8 `hitmask` + `manifest.json`. Once the arc lands, three things change at that seam.

## 1. `proxy_color` tint washes textured sprites — needs an engine ADR
**The actual fix, not just a note.** The engine applies a per-sprite `proxy_color` / tint that is correct for **flat** region-coloured sprites but **washes/over-tints a real albedo texture**. When sprites carry real painted albedo, the tint must switch to **identity (WHITE)** for textured variants.

- **Decision the engine must record (an engine ADR):** textured variants render with an identity tint; `proxy_color` remains only for flat/recolor variants.
- **How the engine knows which is which:** read the new manifest provenance field (next section). Pipeline backlog ids: `w5-engine-tint-note`, `miss-engine-white-tint-switch`.

## 2. The provenance field the engine reads (ADR-0029)
The baked manifest will carry, under `provenance.texture`:
- `has_bound_tex` (bool) — a base-colour texture was bound in the source glb;
- **`real_albedo`** (bool, derived = `has_bound_tex && !flat_fallback`) — **this is the field to branch the tint on**: `true` ⇒ identity/WHITE tint; `false` ⇒ flat sprite, `proxy_color` as today;
- `texture_mode` (`flat_region`|`textured`), per-image `sha256`, UV coverage, `uv_repaired`/`flat_fallback` flags.

Additive only (the engine manifest schema is `additionalProperties:true`), so it lands without breaking existing loads. **Do not** branch on a raw `textured` bool — for a degenerate "flat-via-texture" pirate, `has_bound_tex` is `true` but `real_albedo` is `false`; only `real_albedo` is safe.

## 3. Per-region hit AABBs become available (ADR-0025 → implemented by ADR-0031)
The pipeline currently bakes the per-frame R8 region mask but emits only a whole-silhouette `mask_rect`. The verification epic (ADR-0031) **implements the per-region AABBs** that engine ADR-030 says the engine reads by default (engine ADR-029 rig-derived regions, ADR-030 mask + derived AABBs — both Accepted). After it lands, each manifest frame carries per-region AABBs derived from the mask. No engine change is *required*, but this unblocks wiring engine ADR-031 (per-region collider) with no pipeline re-bake. See pipeline ADR-0025 for the cross-repo open questions (region source material-name vs bone-derived; screen-space boxes vs world height).

## 4. Re-vendoring once textured deliveries land
When the model-producer ships corrected (UV-unwrapped, texture-bound) models and the pipeline re-bakes them (`w5-rebake-revendor`), the refreshed `manifest.json` + `color_atlas.png` (+ hitmask) for `green_ogre_v1`, `red_dragon_v1`, `pirate_duelist_v2` are copied into the engine's `assets/sprites/<id>/`. A richer color atlas is a drop-in; the only behavioural change is the tint switch (§1), gated on `real_albedo` (§2).

---

**Summary ask of the engine team:** record an engine ADR for the **identity-tint-for-textured-variants** decision, branching on `manifest.provenance.texture.real_albedo`. Everything else is drop-in.
