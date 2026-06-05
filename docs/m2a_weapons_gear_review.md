# M2A (Weapons / Gear / Equipment) — Deferred Workstream Review

**Status: DEFERRED. Blocked on user decision D1.** This is a decision-complete design
review, not a contract change. The equipment surface is already *reserved* end-to-end
(palette ids, source-schema region enum, sockets grammar, Rust manifest types), so no
contract edit is required to unblock — only a user call on D1 (baked-variants vs
runtime-overlay layering) plus the two enforcement-gate flips that D1 implies.

**Why this is gated.** Every M2A code path is conditional on D1 because D1 decides
*where* the palette-extension and socket-projection code lives and runs (bake time, in
one render package, vs runtime, across composited layers). Writing that code before D1 is
decided risks building it on the wrong side of the seam. The one exception is the 3D→2D
socket projection (§4), which both forks need identically and is therefore safe to write
now.

**Scope of this doc:** D1 decision matrix (§1), the load-bearing occlusion assumption to
never re-litigate (§2), the exact gate flips to perform *after* D1 (§3), the
D1-independent socket-projection spec that is safe to build first (§4), implementation
order (§5), and the coupled D4 mask-semantics cross-reference (§6).

---

## 1. D1 decision matrix — baked variants vs runtime overlay

D1 is the fork that gates **all** of M2A. Two options:

- **(A) Baked variants** — pre-render each body+gear *combination* into its own complete
  `game_iso_v1` sprite package. Gear meshes are placed into the *same* scene as the body
  and pass through the existing single render. One package == one fully-dressed character.
- **(B) Runtime overlay** — bake gear as *separate* layers (own atlas + own per-frame
  rects + synced hardpoints + per-direction front/behind z-order flags). The engine
  composites body + gear layers at runtime per frame.

| Axis | (A) Baked variants | (B) Runtime overlay |
|---|---|---|
| **Variant explosion** | High *if cartesian* — N_body × N_weapon × N_shield × N_gear packages. **Mitigated by a curated cap** (bake only an authored shortlist of combinations, never the full product). | Low — layers combine at runtime; the matrix lives in engine composition, not on disk. |
| **Atlas / VRAM budget** | Larger on-disk + per-combo VRAM, but each package is a single contiguous atlas the loader already understands; frame-dedup (≈38–40% byte-identical frames today) claws much of it back. | Smaller baked footprint, but every dressed entity costs N live layer draws + N resident layer atlases; runtime compositor VRAM and per-frame blend cost. |
| **Where palette + socket code lives** | **Bake time, in one place.** Palette extension (ids 5/6/7) and socket projection run once per package through the *existing* single-render path. No engine-side compositor. | **Split across the seam.** Bake emits layers + hardpoints + z-order flags; the **engine** gains a new runtime compositor that aligns layers by socket and resolves per-direction z-order. New engine code on the critical path. |
| **Animation-frame multiplication** | Frames multiply per *baked* combination (states × directions × frame_index × curated combos). Curated cap bounds it; dedup compresses it. | Frames are authored **once per layer**; the body's frame set is not re-multiplied per gear item. Best case for animation-heavy rosters. |
| **Occlusion** | **Free** — see §2; the single z-buffered topmost-surface pass already orders gear front/behind per direction with zero extra code. | **Must be reconstructed** — the bake has to emit per-direction front/behind z-order flags and the engine must honor them; occlusion that was structural becomes data + runtime logic. |
| **Reuses existing pipeline** | Yes — same `render_directions` occlusion pass, same atlas packer, same manifest shape, same Gate-1 acceptance. | Partial — new layer-atlas emit, new hardpoint sync contract, new engine compositor; more net-new surface on both sides. |

### Recommendation (explicit — but needs the user's call)

**RECOMMEND baked-variants-FIRST (Option A), WITH a curated-cap caveat.**

Rationale: Option A reuses the existing single-render occlusion pass **for free** (§2) —
the one depth pass that already produces correct per-direction gear ordering is the
single most expensive thing to re-derive, and (A) inherits it at zero cost. It keeps the
palette-extension and socket-projection code at **bake time in one place**, off the engine
critical path, and lands entirely within the already-reserved contract. The only real cost
of (A) — variant explosion — is contained by the **curated cap**: bake an *authored
shortlist* of body+gear combinations (the combos the game actually ships), **never the
cartesian product**. Frame-dedup further compresses each package.

Option B remains the right answer if the roster later needs arbitrary mix-and-match dress-up
at runtime (many gear items × many bodies, player-customizable), where the cartesian matrix
makes any curated baked set untenable. The two are not mutually exclusive long-term — (A) can
ship the first equipped characters while (B) is evaluated for a customization milestone.

**This recommendation is a recommendation, not a decision. D1 is the user's call** and gates
everything below. Do not flip the §3 gates until D1 is decided.

---

## 2. Occlusion = SOLVED (load-bearing assumption — never re-litigate)

**Record this as settled. Future M2A work must NOT redesign occlusion.**

The existing R8 render is a **single z-buffered, topmost-visible-surface pass**
(`render3d.py::_rasterize`: one `zbuf`, `win = inside & (d > reg)`, depth from
`project_raw`). Gear modeled into the *same* scene as the body is rasterized in that same
one pass. Therefore **correct per-direction front/behind ordering between body and gear
emerges automatically** — no second pass, no manual z-sort, no per-item ordering code:

- A weapon held at the hand reads **in front of** the torso for south-facing
  (toward-camera) directions, and
- **behind** the torso for north-facing (away-from-camera) directions,

because the depth buffer resolves exactly which surface is topmost per pixel per direction.
This is a structural property of baking gear into the single render (Option A), not a feature
that needs building.

**Implication for D1:** Option A inherits this for free. Option B *forfeits* it — splitting
gear into runtime layers means the per-direction front/behind relationship must be
re-encoded as explicit z-order data the bake emits and the engine honors. This is the
single strongest pipeline-side argument for the baked-variants recommendation in §1.

---

## 3. The two gate flips (do NOT flip before D1 is decided)

Two enforcement points currently fence equipment off. Both are *policy* gates in front of
an *already-reserved* contract — flipping them does not change the contract, it stops
rejecting the reserved ids/regions/sockets. **Flip only after D1 is decided** (D1 may move
*where* the palette extension is applied — body-package baker vs a gear-layer baker).

### Gate flip (a) — source linter: allow the deferred regions + sockets

File: `pipeline/tools/lint_source_asset.py`

- **Line 33:** `DEFERRED_REGIONS = {"shield", "weapon", "gear"}` — these are rejected at
  check 8 (`hit region '...' is deferred this iteration`). Move them into the allowed set
  (e.g. fold into `BODY_REGIONS`, or introduce an `EQUIP_REGIONS` allow-set the check
  consults) so `shield`/`weapon`/`gear` HIT proxies validate.
- **Line 35:** `DEFERRED_SOCKETS = {"weapon_grip", "weapon_tip", "muzzle", "muzzle_back",
  "shield_center"}` — rejected at check 6 (`socket '...' is deferred this iteration`).
  Move into the allowed base-socket set so these socket names validate.

The source schema already permits both: `source_asset.schema.json` `hit_proxy_objects.region`
enum includes `"shield","weapon","gear"` (lines 46–49) and `sockets` is a free string array
(lines 57–60). So this flip is purely linter policy — no schema edit.

### Gate flip (b) — bakers: extend the body-only palette to 5/6/7

File: `pipeline/tools/bake.py`

The R8 hitmask palette is hardcoded body-only in **two** manifest emitters:

- `_bake_mesh_character(...)` — `"palette": {"none": 0, "head": 1, "torso": 2, "arms": 3,
  "legs": 4}` (~line 222)
- `bake_character_anim(...)` — the identical body-only palette (~line 334)

Extend **both** to the reserved ids: add `"shield": 5, "weapon": 6, "gear": 7`. These ids are
**already reserved and authoritative** — no contract change:

- `pipeline/lockfiles/sprite_contract.lock.json` `mask_palette` already lists
  `shield:5, weapon:6, gear:7` (alongside `none:0 … legs:4`).
- `source_asset.schema.json` region enum already includes `shield/weapon/gear`.

Note (couples to H6 in `next_phase_plan.md`): the palette literal is duplicated across the
two emitters — extend it in lockstep, or extract a single shared `REGION_PALETTE` constant so
they cannot drift. The region→face mapping also has to flow `face_region` ids 5/6/7 from the
mesh-region source (material/group name → id) through `render_directions(... face_region=...)`;
the renderer is already id-agnostic (it writes whatever id the face carries), so only the
*assignment* of 5/6/7 to gear faces is new.

---

## 4. 3D socket → 2D projection spec — the SAFE FIRST CODE (D1-independent)

**This is the one piece safe to write before D1.** Both D1 forks need per-frame 2D gear
attach points (Option A: to author/QA placement and drive effects; Option B: as the
hardpoints that sync the runtime layers). The projection math is identical either way, so it
is **D1-independent** and can land first.

**Goal.** Project the world-space bone positions `hand.L`, `hand.R`, `weapon_grip`,
`weapon_tip`, `muzzle` (and `muzzle_back` if present) through `render3d.py`'s **existing
camera basis** into per-frame 2D `sockets[]` entries, exactly as `direction_tip` and `origin`
are emitted today.

**Additive — no contract change.** The engine `manifest.schema.json` is
`additionalProperties: true` *everywhere*, and the per-frame `sockets` object is explicitly
`additionalProperties: true` ("Optional named points in frame_canvas px"). New socket keys are
forward-compatible: the engine ignores keys it does not consume. So this is purely additive
renderer output.

**Projection math (reuse the existing basis — do NOT invent a new one).** Use the **same
basis `direction_tip` already uses**: a world point is yaw-rotated for the direction, run
through `project_raw`, then mapped to frame pixels by the per-frame fit `(s, ox, oy)`. For a
world bone position `p = (x, y, z)` at direction `i` (yaw `θ_i = i·2π/N`):

1. `p_rot = rotate_z(p, θ_i)` — same per-direction yaw the body verts get
   (`render3d.py::rotate_z`).
2. `(rx, ry), _ = project_raw(p_rot)` — the locked iso basis
   (`rx = (x−y)/√2`, `ry = (x+y)/(2√2) − z·cos30`; the depth component is unused for a 2D
   socket but is the same value the z-buffer uses).
3. `socket_px = (ox + s·rx, oy + s·ry)` — apply the **same** per-frame fit `(s, ox, oy)`
   used for the body in that frame (multistate must use the shared `compute_fit` so every
   frame/state shares one world→pixel scale and the foot anchor is stable). For tight-cropped
   frames, subtract the frame's `trim` `[bx, by]` so the socket is in the same logical-frame
   space as `anchor` and the existing sockets.

This is exactly the transform the body verts already take in `render_directions`
(`p2d = ox + s·raw`), so socket pixels land in the same frame space as `rect`/`anchor`/
`direction_tip` by construction — no separate calibration. Emit them alongside the existing
sockets per frame:

```
"sockets": {
  "origin":        [ax, ay],
  "direction_tip": [...],            // existing facing aid
  "hand_r":        [hx, hy],         // new — projected bone
  "hand_l":        [...],
  "weapon_grip":   [...],
  "weapon_tip":    [...],
  "muzzle":        [...]
}
```

**Source of the world bone positions.** The procedural/synthetic fixture (§5.i) can place
these as known constants; the rigged `biped_v1` path already carries `hand.L`/`hand.R` bones,
so the bone world positions per posed frame are available where the verts are posed. Project
them with the same `(s, ox, oy)` that frame used.

**QA hook (mirror `direction_tip`).** `direction_tip`/`origin` already power a direction
check (`normalize(direction_tip − origin) == screen_direction_vector`). The new sockets get a
cheap analog: with the same projection applied to a known fixture, the projected `weapon_tip`
must track the modeled tip across all 16 directions — a self-consistency gate that needs no
engine round-trip.

---

## 5. Implementation order

1. **(i) Synthetic placeholder gear fixture FIRST.** Build the ADR-0013 synthetic asset —
   body + a box "sword" off `hand.R` + a plate "shield" over the torso + a backpack "gear" —
   as the **durable regression fixture**. This exists before any gate flips so every later
   step has a deterministic, no-Blender thing to bake and diff. It also exercises the §2
   occlusion claim concretely (sword front/behind across directions).
2. **(ii) Gate flips + palette extension (§3).** Flip linter `DEFERRED_REGIONS`/
   `DEFERRED_SOCKETS` → allowed; extend both bakers' palette to `shield:5/weapon:6/gear:7`
   (ideally via the shared constant). Now the fixture's gear regions validate and bake into
   the R8 mask.
3. **(iii) Socket projection (§4).** Add the 3D→2D bone projection into per-frame `sockets[]`
   for `hand.L/R`, `weapon_grip`, `weapon_tip`, `muzzle`. D1-independent; can be developed in
   parallel with (i)/(ii) since it only adds keys.
4. **(iv) Baked-variant default path (per the §1 recommendation, pending D1).** Wire the
   curated-combination baked-variant path as the default equipped-character build. Gated on
   D1 being decided in favor of Option A; if D1 picks Option B, this step becomes the
   layer-emit + hardpoint-sync + engine-compositor track instead.

Steps (i)–(iii) are low-risk and (iii) is contract-safe regardless of D1; step (iv) is the
one that must wait on the D1 call.

---

## 6. D4 cross-reference — mask semantics when gear covers the torso (defer jointly)

**D4** (`next_phase_plan.md §8`, ADR-0006): when gear occludes the torso, the single
topmost-surface mask (§2) records the *gear* region at those pixels, not the torso beneath —
so a torso shot landing on covered pixels reads as `gear`, not `torso`. Three candidate
semantics:

- **No-damage-there** — single topmost mask; covered torso pixels are `gear` and the engine
  treats hits there per the gear region's rules (e.g. armor absorbs). Cheapest; no extra atlas.
- **Second body-damage mask** — emit a separate body-region mask *under* the gear so the
  engine can resolve both "what was hit visually" (gear) and "what body region is beneath"
  (torso). Doubles the mask channel/atlas for equipped variants.
- **Per-region passthrough (engine-side)** — the engine maps a `gear` hit back to the
  underlying body region by policy, keeping a single baked mask but moving the resolution
  into engine logic.

**This is coupled to D1 and must be deferred jointly.** The chosen D1 layering decides what
masks even exist: Option A (single render) naturally yields the one topmost mask (favoring
no-damage-there or engine-side passthrough, or an explicit second-mask emit); Option B
(layers) already separates body and gear masks by construction, which changes which D4 option
is cheap. **Do not decide D4 before D1.** Resolve D4 in the same pass that resolves D1.
