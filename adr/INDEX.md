# ADR Review Pack — Sprite Pipeline Blockers

This directory contains proposed ADRs that close or explicitly defer the blockers found during review of the sprite-generation plan.

All ADRs are **Proposed** unless ratified by the engine/gameplay review group. The M1/M2 arrow pilot intentionally avoids weapons/equipment; those decisions become blocking before M3 controlled real variants.

| ADR | Topic | Blocks |
|---|---|---|
| ADR-0006 | Visible topmost-surface hitmask semantics | M3 |
| ADR-0007 | Body-only world metrics; equipment excluded | M3 |
| ADR-0008 | Source asset separation + rig-bound hit proxies | M3/M4 |
| ADR-0009 | Socket pairs for orientable equipment | M3 |
| ADR-0010 | Outgoing weapon damage from markers/socket traces | M3 |
| ADR-0011 | v1 baked equipment variants; no runtime layering | M3 design scope |
| ADR-0012 | Effects as renderable sprite variants, not runtime GIFs | M3/M4 |
| ADR-0013 | M2A combat-surface harness before M3 | M3 |
| ADR-0014 | Validator/runtime contract, hit-test orientation, scale term | M2 |
| ADR-0015 | M1/M2 arrow pilot direction-only scope | M1/M2 |
| ADR-0016 | AI generation behind proven seam + cleanup/source validator | M4 |
| ADR-0017 | Atlas/compression/streaming deferred until measured | M4/M5 |
| ADR-0018 | Camera elevation 30° (confirmed); height pinned by an explicit pixel scale | M3 |
| ADR-0019 | Height-calibration probe + gate before height bakes | M2A/M3 |
| ADR-0020 | Metallic/specular sprite materials — baked-static v1; dynamic-lit parked | — (parked) |
| ADR-0021 | M2A equipment-layering execution stance (affirms ADR-0011) | — (parked; first equipped character) |
| ADR-0022 | Lock 256² as the engine-facing logical frame canvas | Task #21 / D-canvas (engine sign-off) |
| ADR-0023 | `world_scale_multiplier` deferred; measured height is sufficient | — (parked) |
| ADR-0024 | Color variations (runtime tint first) + effects as separate layers, never baked in | effects/M2A milestone |
| ADR-0025 | Hit-region output: keep per-frame region mask, ADD per-region AABBs derived from it (align pipeline to engine ADR-029/030) | M3 hit detection / roadmap hitmask Phase-0 |
| ADR-0026 | Texture-mode declaration + the `texture-capable(glb)` contract (real UVs + bound texture) | ARC-0001 / textured deliveries |
| ADR-0027 | Auto-rig preserves textures + UVs; textured models ship pre-rigged | ARC-0001 / textured deliveries |
| ADR-0028 | A textured delivery that bakes flat is a **blocking** failure (fidelity gates + severity) | ARC-0001 / textured deliveries |
| ADR-0029 | Texture/UV provenance in the baked manifest (`real_albedo` the engine reads) | ARC-0001 / engine tint |
| ADR-0030 | Color-coded calibration model + region↔color oracle (e2e visual-regression basis) | ARC-0001 / verification |
| ADR-0031 | Per-bake cross-stage verification report + severity policy (model/skin/anim/hitbox verified-applied); implements ADR-0025 AABBs | ARC-0001 / verification |
| ADR-0032 | Faithful color: pinned Standard/sRGB color management + baked-atlas contract | ARC-0001 / textured deliveries |
| ADR-0033 | Creature-traits seam (archetype->traits, REGION_SETS, has_direction/is_radial, reserved emissive/mount fields) for cars/horses/eyeless blobs/energy-creatures | seams (bake in now) |
| ADR-0034 | Mounting (rider on horse/motorbike/skateboard/airship) — runtime socket-composited, **DEFERRED until after combat** | seams (deferred) |
| ADR-0035 | Model origin = ground-footprint anchor; bake pivot = +Z through origin; sprite anchor = projected origin; never mesh-bounds-center; in-place/no-root-motion + model_space metadata | v3 producer spec (hard gate) |

**ADR-0026 – ADR-0032 belong to [ARC-0001: Textured & verified skinned models](../docs/arcs/ARC-0001-textured-verified-skinned-models.md)** — the arc that closes the verified gap where "textured/skinned" deliveries bake flat and ship green (no UVs / orphan atlases / degenerate UVs; auto-rig flattens; no gate). The arc carries the per-asset evidence, the merged backlog (Epic A pipeline hardening + Epic B verification), the critical path, and the handoffs (incl. the standalone Model Producer delivery spec). Implementation order and the locks-to-resolve are in the arc §6–§7.

**ADR-0020 – ADR-0023 are explicitly PARKED** (Proposed, recorded for later review, not scheduled): metallic materials, M2A execution detail, the 256² canvas lock, and the world-scale multiplier. They capture decisions + recommendations so a future session can ratify cold. See each ADR's `Related:` line for the source investigation doc.

## Review order

1. ADR-0015 and ADR-0014 first: they affect the included M1/M2 implementation.
2. ADR-0006 through ADR-0013 before M3: they define arms, weapons, shields, gear, sockets, and effects.
3. ADR-0016 and ADR-0017 before M4/M5: they control generator rollout and memory/compression work.
4. ADR-0018 and ADR-0019 before any height-bearing bake (M2A/M3): they pin vertical projection by a height pixel scale and gate it with a calibration probe.
5. **ADR-0025 is cross-repo** and should be reviewed jointly with the engine: it aligns the pipeline's hit-region output to two **Accepted** engine ADRs (ADR-029 rig-derived regions, ADR-030 mask + derived AABBs / engine reads boxes by default). The pipeline already bakes the per-frame region mask; the new deliverable is the **per-region AABBs derived from it**, plus open questions on the region source (material-name vs bone-derived) and screen-space-vs-world-height hit resolution.
