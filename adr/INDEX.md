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

**ADR-0020 – ADR-0023 are explicitly PARKED** (Proposed, recorded for later review, not scheduled): metallic materials, M2A execution detail, the 256² canvas lock, and the world-scale multiplier. They capture decisions + recommendations so a future session can ratify cold. See each ADR's `Related:` line for the source investigation doc.

## Review order

1. ADR-0015 and ADR-0014 first: they affect the included M1/M2 implementation.
2. ADR-0006 through ADR-0013 before M3: they define arms, weapons, shields, gear, sockets, and effects.
3. ADR-0016 and ADR-0017 before M4/M5: they control generator rollout and memory/compression work.
4. ADR-0018 and ADR-0019 before any height-bearing bake (M2A/M3): they pin vertical projection by a height pixel scale and gate it with a calibration probe.
