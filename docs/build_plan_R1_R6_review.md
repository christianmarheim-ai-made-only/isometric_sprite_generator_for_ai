# Sprite-Generator Pipeline — Build Plan R1–R7 (review copy, **v2**)

> **Self-contained for external review.** **v2** incorporates the external review
> (2026-06-05): the direction-binning `floor`→`round` fix, the tight-crop-vs-engine-sizing
> block, an independent oracle, the ADR-0018/0019 rewrites, a body-only content scope, the
> answered open questions, and a new **R7** (production-renderer parity). Green-light status
> in §3. Supersedes `docs/next_slices_plan.md` (legacy P/C plan); for R2–R7 this file is
> authoritative. Date: 2026-06-05.

---

## 0. Context

### What this is
A **headless pipeline** that turns a rigged 3D model into **16-direction isometric sprite
sheets + a machine-readable manifest** consumed by a Bevy/Vulkan iso game (format
**`game_iso_v1`**). The engine-facing output is a **fixed contract**; the pipeline behind
it is free. Core discipline: **avoid silent contract bugs**. Plain Python (Pillow, numpy,
jsonschema); a dependency-light software rasterizer → everything builds/tests **headless**.

### The engine contract `game_iso_v1` (pinned from the engine's Rust source)
- **Loader (`sprite.rs::parse_manifest`) requires** top-level: `camera.id=="game_iso_v1"`;
  `direction_count`∈{1,2,4,8,16}; `frame_canvas[w,h]`; `atlases.color.{path,size}` (path
  relative to the manifest dir); `frames[]` each `{direction, rect[x,y,w,h] (w,h>0),
  anchor[x,y] in frame_canvas px}`, with `frames.len()==direction_count` and directions
  `0..N-1` unique+covered; `world_metrics` required for character/effect, optional for
  probe. **Unknown fields are ignored** (serde) → emit extras freely.
- **Projection (`render.rs::project_iso`):** `screen_x=(x−y)·32`, `screen_y=−(x+y)·16 +
  height·24` (Bevy y-up). Camera azimuth 45°, **elevation 30°** (`sin30°=0.5` ⇒ 2:1 ground).
  `arctan(0.5)≈26.565°` is the tile-edge **screen** angle, **not** the camera elevation.
- **Direction binning (`sprite.rs::direction_index`):** **`i = round(facing/(TAU/N)) mod N`**,
  `0=+X` East, CCW. Frames render at `i·(360/N)°` = the **bin center** under round-binning.
  ⚠️ The repo lockfile currently mis-states this as `floor` / "lower edge" — **R2 fixes it**
  (no re-bake; frames already render at `i·22.5°`). Verified vs the `expected_facing_table.json`
  oracle (an engine test).
- **Sizing (`render.rs::sprite_size`):** on-screen **height = `height_world × 24`**,
  **width = height × frame_aspect** (`rect.w/rect.h`). ⇒ **the engine derives width from the
  atlas rect aspect.** This is **load-bearing** and constrains cropping (see R5).
- **Hitmask:** R8 region-ID, discrete, no AA; palette `none0 head1 torso2 arms3 legs4
  shield5 weapon6 gear7`; authoritative source = rig-bound **HIT_ proxy** geometry.

### Independent oracle (review fix)
The engine ships a committed `expected_facing_table.json` (used by its own tests). **Vendor
it** into `pipeline/schema/engine/` and compare the renderer / Gate-2 against **that file**,
not against a sibling Python function (which could share a bug).

### Locked conventions (never "correct")
Forward **+X**, up **+Z**, **1u=1m**, origin = ground footprint center; world-CCW reads
clockwise on screen; `dir02` down, `dir10` up; elevation **30°**.

### Content scope — **body-only this iteration** (review fix)
- **Active sockets:** `origin`, `head_center`, `hand_l`, `hand_r`.
- **Active regions:** `head`, `torso`, `arms`, `legs`.
- **Active states** (defined in R5 from `sprite_states.lock.json`): `idle`, `walk`, `hurt`,
  `death`, `resurrect`, `jump`, `attack_fist` (fist only — references a **hand**, not a weapon).
- **Deferred (M2A+):** `shoot`; `fire` marker; `muzzle`, `muzzle_back`, `weapon_tip`,
  `weapon_grip`, `shield_center` sockets; `shield`/`weapon`/`gear` regions. The weapon ADRs
  (0009/0010/0011) remain but are **INACTIVE** until M2A. (Any external content prompt that
  lists muzzle/weapon_tip/shoot is out of scope for R1–R7.)

### Current state
R1 done + green. R2–R4 green-lit (R2 after its contract fixes). R5 **split** (R5A yes; R5B
blocked on a sizing decision). R6 reframed (reference/contract proof, not final M3). R7 new.

---

## 1. The slices

Gate-N = the engine's 3 acceptance gates: **Gate 1** engine-loadable (schema + cross-field),
**Gate 2** direction (socket→**independent** oracle), **Gate 3** elevation/foreshortening.

### R1 — Headless 3D renderer ✅ DONE
`render3d.py` (numpy ortho rasterizer; az 45 / el 30; z-buffer; auto-fit; foot anchor) +
`meshes.py` + `test_render3d.py`. The camera matches the engine ground-direction oracle to
`1.1e-16`. **Caveat (review):** that test compares `project_raw` to a *sibling* function in
the same module — partially self-referential. **R2/R3 add the independent comparison** to
the vendored engine oracle.

### R2 — Engine-shaped manifest + contract fixes + bake orchestrator + Gate-1
**Not "done" until a generated package would be accepted by the engine loader.**
- Emit the top-level **`camera` block** (the #1 blocker): `{id:"game_iso_v1",
  azimuth_degrees:45, camera_elevation_degrees:30, camera_elevation_definition,
  camera_geometry_note, projection, screen_y:"down", tile_px:[64,32]}`.
- **Contract-lockfile fixes, then regenerate `contract_hash`:**
  - `sprite_contract.lock.json` `facing`: change binning to **`round(facing_rad/(TAU/N))
    modulo N`** and `render_yaw` to "`direction_index·TAU/N`; **bin center under
    round-binning**" (it currently wrongly says `floor` / "lower edge"). No re-bake — this is
    contract/doc correctness; the frames already render at `i·22.5°`.
  - Add camera fields to the lockfile: `azimuth_degrees 45`, `camera_elevation_degrees 30`,
    `height_screen_scale 24` (engine-side), `tile_px [64,32]`.
  - Regenerate `contract_hash`; update the committed manifest + `test_contract_hash` / smoke.
- Emit per-frame **`sockets.direction_tip`** (`= origin + screen_direction_vector·len`).
- `bake.py` orchestrator: (mesh/descriptor) → R1 render → pack atlases → engine-shaped
  manifest → `expected_facing_table.json` → validate.
- **Vendor** (a) the engine `manifest.schema.json` from **`C:\Code\Claude\docs\pipeline\
  manifest.schema.json`** (30°, **not** the stale `dist/…/CONTRACT` copy that says 26.565),
  and (b) the engine `expected_facing_table.json` → `pipeline/schema/engine/`.
- Add **Gate 1** to `build.py` (validate vs the vendored engine schema + the 2 cross-field rules).
- Add **validator camera checks**: `camera.id==game_iso_v1`; `azimuth_degrees==45`;
  `camera_elevation_degrees==30` (reject 26.565); `tile_px==[64,32]`; `screen_y` convention.
- **Promote `build.lockfile_hashes` to a CI validation check** (assert per-lockfile provenance
  hashes; the engine still only cares about `contract_hash`). Optionally add
  `state_contract_hash` / `variant_contract_hash` fields.
**Acceptance:** the generated manifest passes Gate-1 + the vendored loader contract; `bake.py`
produces a full package from a procedural mesh; build green.

### R3 — Acceptance gates (Gate-2/Gate-3) + foreshortening calibration
**Prereq:** ADR-0018/0019 rewritten so the Decision IS the final truth (**done** in this commit).
- **Gate 2 (independent oracle):** `normalize(direction_tip − origin) ==` the **vendored
  engine** `expected_facing_table[dir].screen_direction_vector` (<1e-2), all frames;
  `world_yaw_degrees == i·360/N`. (Compare to the vendored engine file, not a sibling fn.)
- **Gate 3 (elevation/foreshortening):** `camera_elevation_degrees==30`; **26.565 rejected**
  as an elevation; a known cube/pole's rendered **aspect** matches the 30° projection
  prediction. NOT a "24 px/unit in the bake" check (engine-side; ADR-0019).
**Acceptance:** all 3 gates green on the R2 package.

### R4 — Body-only mesh + HIT-proxy R8 mask + metrics ✅ green-lit
- OBJ/glTF loader + a procedural region-tagged **humanoid placeholder**.
- **Separate HIT-proxy depth resolve (Q2):** render **only** `HIT_` proxies, same
  camera/pose/z-buffer as the color pass; topmost-visible `HIT_` proxy per pixel → its region
  ID. Visual-mesh topology is **not** the mask authority.
- `world_metrics` from the `METRIC_body` proxy bbox + head/eye socket.
- **Gates:** mask nonzero ⊆ visible alpha (no mask where color α<8, barring a reviewed
  exception); each active body region (head/torso/arms/legs) in ≥1 frame; **no
  shield/weapon/gear region** this iteration; boxes **bound** their region pixels (not required
  to equal exact re-derived boxes); all regions use the **same camera/depth path** as color;
  the metric proxy **excludes** non-body geometry. Idle, 16-dir, body-only.

### R5 — Animation states + crop — **SPLIT** (R5A green-lit · R5B **BLOCKED**)
**Precondition (R5B):** the engine derives sprite width from `rect.w/rect.h`
(`render.rs::sprite_size`). Tight-cropping engine-consumed frames to varying aspects would
silently break animation scale (a crouch/hurt/death pose gets stretched to `height_world×24`
tall at the wrong width). **Do NOT tight-crop engine-consumed frames** until the engine adds
a `logical_frame_canvas` sizing (size from `frame_canvas`; `rect` only selects pixels).
- **R5A (proceed):**
  - Multi-state **dual-shape manifest (Q1):** top-level engine-consumed `frames` = the
    **default state `idle`, FULL-CANVAS**; rich `states → directions → frames` as ignored
    extras + `engine_frames_state:"idle"` + a `states_layout` map.
  - State/frame counts from `sprite_states.lock.json` (contract invariant).
  - Procedural pose function (headless) for idle/walk/…; real clips swap in later.
  - Root-XY in-place validation (no drift beyond tolerance).
  - **Engine-consumed frames stay FULL-CANVAS.** (Rich/debug frames may experiment with tight
    crops, but no production animation scale depends on them.)
- **R5B (blocked):** tight-crop for engine-consumed frames — only after the engine/logical-frame
  sizing contract is fixed (an engine feature, coordinated with the engine flow). Then update
  the validator pixel loops (`range(rect_h)/range(rect_w)`) **and** relax the `rect==canvas`
  assertion together.

### R6 — First body-only reference character (**CONTRACT proof, not final M3**)
**Proves:** source descriptor → linter → procedural/OBJ mesh → color+mask+metrics → manifest →
all gates green; engine load-test of the **top-level idle frames** (`parse_manifest` + oracle).
**Does NOT yet prove:** final Blender material/texture output; real engine **animation
playback** (the loader is **single-state** — it consumes only the top-level idle frames; the
rich states are ignored until the engine consumes them); production art quality.
**Engine load-test (Q3):** package generation is autonomous; `cargo test -p client_bevy` +
Blender review are **external CI/human gates** (no cargo/Blender in the autonomous env).

### R7 — Blender/glTF production-renderer parity (NEW) — required for "real M3"
Same source asset + same camera contract + same manifest shape + same masks, rendered through
**Blender/glTF** (production materials/textures/lighting), **visually compared** against the R1
software/procedural gates; engine load-test + **human Bevy visual review** (`losdemo`). **M3 —
"a real controlled variant lands in Bevy" — is not truly done until R7.**

---

## 2. Sequencing + answered questions + deferrals

**Sequencing:** R1✅ → R2 → R3 → R4 → R5A → (R5B after the sizing decision) → R6 → R7.

**Answered open questions (review):**
- **Q1 (single-state engine vs multi-state):** **dual-shape manifest** — top-level idle frames
  for the engine + rich states as ignored extras + metadata. Don't make the engine multi-state
  in R5 (that's an engine feature slice). Honesty: R6 doesn't prove animation **playback** until
  the engine consumes states.
- **Q2 (overlapping HIT proxies):** **separate HIT-proxy depth resolve**, same camera/pose/z-buffer
  as color; topmost-visible `HIT_` proxy → region ID; visual-mesh topology is not the authority;
  mask ⊆ visible alpha.
- **Q3 (Blender/cargo):** **external CI/human gates** (not in the autonomous env). R1–R5A + R6
  package-gen are autonomous; `cargo test` + Blender review are external.
- **Q4 (software vs GPU renderer):** keep the **software renderer as the contract/calibration
  renderer** through R4/R5 (camera math, oracle, z-buffer, mask semantics, packing, manifest,
  metrics, procedural tests). It is **not** the production art renderer (materials/textures/
  alpha-edges/lighting/animation parity) — that is **R7**.

**Deferred (unchanged):** weapons/equipment (M2A), AI generation (M4), compression (M5).

---

## 3. Green-light status (external review, 2026-06-05)

- **R2:** green-light **after** the lockfile / camera / binning fixes (in §R2).
- **R3:** green-light **after** the independent oracle + the ADR-0018/0019 rewrite (**rewrite done**).
- **R4:** green-light as a body-only procedural geometry/mask/metrics proof.
- **R5:** **split** — R5A (multi-state) green; R5B (tight-crop) **blocked** on the engine sizing decision.
- **R6:** green-light only as a reference/procedural **contract** proof; not the final M3 unless
  Blender/cargo/engine-animation (**R7**) are included.

**Two hard rules:** (1) do **not** combine tight-crop with the engine's rect-based sizing until
that contract is fixed; (2) do **not** leave the camera/height ADRs or the direction-binning
lockfile contradictory — both fixed in this v2 (ADRs) and R2 (lockfile).
