# ADR-0034: Mounting (rider on horse / motorbike / skateboard / airship) — preliminary, DEFERRED

- Status: **Proposed — DEFERRED until after combat works** (design only; build nothing now)
- Date: 2026-06-07
- Owner: sprite-pipeline (+ engine-team contract items flagged)
- Related: ADR-0009/0010 (orientable equipment socket pairs + outgoing markers — the precedent), ADR-0011 (v1 baked equipment variants, no runtime layering — the blowup this avoids), ADR-0021 (socket projection), ADR-0024 (effects/overlay + depth), ADR-0033 (reserves the mounting grammar). Engine repo read-only.

## Context

There is **no mounting today** and it is **not a priority before combat is decent**. But the question was asked — sit on a horse, ride a motorbike, skate a skateboard, drive a horse-drawn cart, captain a steampunk airship — so this ADR records the design and, crucially, the **zero-cost seams to leave open now** so mounting is purely additive later.

The iso pipeline bakes flat per-direction sprites. A rider+mount is therefore one of:
- **(a) bake every pairing as one combined package** — simplest to render, but a combinatorial blowup (R riders × M mounts × directions × frames) and re-bakes on every costume change. ADR-0011 already rejected this layering blowup for equipment; the same logic rejects it here.
- **(b) composite at runtime from two sprites** (rider + mount) via a per-direction, per-frame **attach socket** (a `seat`/`saddle`/`deck`/`helm` point) with a screen-space offset + draw order. This dodges the blowup and matches how equipment is already meant to work.

**Decision direction (preliminary): (b) runtime socket-composited.** It reuses the socket-projection machinery (ADR-0021) and the overlay/depth contract (ADR-0024), and keeps riders and mounts independent assets.

## The four hard problems (and where each is solved)
1. **The seat point per direction/frame.** The mount emits a `seat` socket projected to screen space for every (direction, frame) — exactly the per-frame socket emission ADR-0021 already defines for equipment. A galloping horse's saddle moves; the socket tracks it.
2. **Draw order / occlusion (rider behind the mount when facing away).** Per direction the rider is in front of or behind the mount. This is derivable from the **`depth` channel** the region/projection pass already produces (`project_raw`) — a per-(direction) `rider_in_front` bit, or a per-pixel depth compare. No new render pass.
3. **Animation sync (mount gait vs rider pose).** Rider and mount share a runtime clock; the mount's `walk/run/fly` drives the pose cadence and the rider plays a `ride_idle`/`ride_attack` clip locked to the same frame index. Pure runtime; no bake coupling.
4. **The rider must be able to act while mounted** (attack from horseback, fire from a deck). This depends on combat + the socket/marker outgoing-damage system (ADR-0010) already working — hence "defer until after combat."

## Decision

**Defer the implementation in full.** Build none of it now. Reserve only the **zero-cost seams** (these live in ADR-0033 D5, behaviour-preserving):
- the reserved socket vocabulary `seat/saddle/deck/helm/hitch` (sockets are already free-string + `additionalProperties:true`, so no schema change);
- an OPTIONAL `mount_role` (`rider`|`mount`|`none`) + `provides_seat`/`consumes_seat` flags, declared but unused;
- the constraint that any future socket-projection emitter is **generic over socket names**, so an existing point like the cow's `back_socket [-0.02, 0, 1.28]` carries through for free as a saddle anchor.

Flip no linter rule, emit no `seat` socket into a real bake, and add `mount_role` to no shipped descriptor until a mounted unit is actually on the roadmap.

## Consequences
- **+** When mounting is scheduled, it is additive: emit the `seat` socket through the existing projection, add a runtime composite + depth-ordered draw, and a `ride_*` clip set — no re-architecture, no per-pairing bake blowup.
- **+** Avoids ADR-0011's combinatorial explosion by choosing runtime composition.
- **−** Runtime composition pushes per-direction occlusion + sync onto the engine (read-only repo) — an **engine-team contract item** to be specified when scheduled (the `depth`-channel ordering + the shared clock).
- **−** Some mounts (airship) are large enough that the rider is a tiny overlay; sizing/anchor precision at sprite scale is an open question for that case.

## Open questions (for when this is scheduled, not now)
1. Per-direction `rider_in_front` bit vs full per-pixel depth composite — which does the engine want?
2. Do large mounts (airship, cart) need their own non-`body4` region set (ADR-0033) for hit detection of the vehicle vs its rider?
3. Multi-rider mounts (cart with driver + passengers) — multiple `seat` sockets indexed?
4. Does a mounted rider's hit-region come from the rider, the mount, or a merged silhouette?

**Bottom line:** record the design, reserve the cheap seams (ADR-0033 D5), build nothing. Revisit only after combat (riders that can fight) is working.
