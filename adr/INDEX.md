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

## Review order

1. ADR-0015 and ADR-0014 first: they affect the included M1/M2 implementation.
2. ADR-0006 through ADR-0013 before M3: they define arms, weapons, shields, gear, sockets, and effects.
3. ADR-0016 and ADR-0017 before M4/M5: they control generator rollout and memory/compression work.
