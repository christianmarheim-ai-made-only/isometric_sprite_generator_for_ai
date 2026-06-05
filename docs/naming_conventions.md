# Source Asset Naming Conventions (C0)

Deterministic object naming for Blender source assets, so the exporter, the
source linter (P4/P5), and human reviewers agree on what every object is without
parsing geometry. **Body-only this iteration** — weapon/shield/gear objects are
deferred (see `docs/next_slices_plan.md` §6 and ADR-0009/0010/0011).

## Object name prefixes

Every pipeline-relevant object's name begins with one of these prefixes:

| Prefix | Meaning | Authoritative for |
|---|---|---|
| `VIS_` | Visual mesh (what renders) | color atlas |
| `HIT_` | Hit-proxy mesh (gameplay surface) | hitmask (M3+) |
| `METRIC_` | Metric proxy (collision / LOS scale) | `world_metrics` |
| `SOCKET_` | Attachment / measurement point (empty) | sockets, markers |
| `ARMATURE_` | The rig | skeleton, clips |

Rule: the hitmask is generated from `HIT_` proxies, **not** from `VIS_` meshes
(ADR-0006/0008). `VIS_` material/vertex tags may drive debug overlays but are not
authoritative unless explicitly marked as such.

## Grammar

```
<PREFIX><region>[_<side>]
```

- `<region>` is a lowercase body region (below).
- `<side>` is `l` or `r` for paired parts; omit it for centerline parts.
- Prefixes are UPPERCASE, regions are lowercase, names are case-sensitive.
- Examples: `HIT_torso`, `HIT_head`, `HIT_arm_l`, `HIT_arm_r`, `VIS_body`,
  `METRIC_body`, `ARMATURE_rig`.

## Body regions (this iteration)

Active: `head`, `torso`, `arms`, `legs`. The mask palette also reserves
`shield`, `weapon`, `gear` (IDs 5/6/7) — **not authored this iteration**.
Background is `none` (ID 0) and implicit.

`HIT_` proxies use region names directly:
`HIT_head`, `HIT_torso`, `HIT_arm_l`, `HIT_arm_r`, `HIT_leg_l`, `HIT_leg_r`.

## Sockets (this iteration)

Base sockets (empties), body-only:
`SOCKET_origin`, `SOCKET_head_center`, `SOCKET_hand_l`, `SOCKET_hand_r`.
Weapon/shield sockets (`weapon_grip`, `weapon_tip`, `muzzle`, `muzzle_back`,
`shield_center`) are deferred.

- `SOCKET_origin` is the ground footprint center and **must equal the frame
  anchor**.
- Where orientation matters later, paired sockets define a frame-local vector
  (arrives with weapons post-M3).

## Axes / units (must match the contract)

- Forward = **+X** (East). Up = **+Z**. **1 unit = 1 meter**.
- Origin at the ground footprint center (under `SOCKET_origin`).
- Declared in the source descriptor (P3) and checked by the linter (P4) against
  `sprite_contract.lock.json`. A mismatch is a hard failure.

## Example: arrow probe (P2)

```
arrow_probe                 (root)
  SOCKET_origin             empty, ground center = anchor
  VIS_arrow                 visual mesh
  HIT_torso                 single body proxy — exercises mask plumbing
```

No armature required for the probe (`variant_class=probe`, idle, 16 directions).

## Example: humanoid character, body-only (C1/C6)

```
soldier                     (root)
  ARMATURE_rig
  VIS_body
  HIT_head  HIT_torso  HIT_arm_l  HIT_arm_r  HIT_leg_l  HIT_leg_r
  METRIC_body
  SOCKET_origin  SOCKET_head_center  SOCKET_hand_l  SOCKET_hand_r
```

Weapon/shield/gear visual + proxy objects and their sockets are added post-M3.

## Collections (optional grouping)

Grouping mirrors ADR-0008's structure and is for authoring convenience only; it
does not override prefixes:

```
root / ARMATURE / VISUAL / HIT_PROXIES / METRIC_PROXIES / SOCKETS
```

## How this is enforced

- P3 lists objects by name in the source descriptor; P4/P5 lint prefixes, allowed
  region names (body-only now), required sockets, and axis/unit declarations.
- Anything outside this grammar is either ignored (non-pipeline helper objects)
  or flagged by the linter, depending on its collection.
