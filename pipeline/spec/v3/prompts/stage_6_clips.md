# Stage 6 — Author the required combat clips (idle / attack / hit / death)

## PROMPT

Author the animation clips a combat creature must ship and embed them so the engine actually selects
them. Channels target **bone names** (radians for rotation, metres for translation; root stays in
place — no horizontal locomotion). Author an `anim_clips_v1` JSON
(`pipeline/schema/animation_clips.schema.json`) and declare each as a state in `animations` of the
asset manifest.

Combat creature required clips: **idle, attack, hit, death** (walk/run recommended).

Use the engine's **canonical clip vocabulary** — the read-only engine renderer selects clips by these
names and **silently falls back to idle** for any other name:

```
idle, walk, run, attack, hit, jump, fall, crouch_idle, crouch_walk
```

Off-vocab names are auto-flagged with the rename the engine actually selects (`CLIP_SYNONYMS`):

- motion: `move/stroll → walk`; `jog/sprint/dash → run`
- attack: `shoot/fire/swing/slash/stab/cast/punch/melee/strike/jab → attack`
- hurt: `hurt/damage/flinch/stagger/recoil/hitreact → hit`
- terminal: `die/dead/dying/ko → death` (death/fly/roll are non-load-bearing but may ship)

Name your attack clip **`attack`** and your hit clip **`hit`** — `punch` is off-vocab for the LIVE
engine (it selects `attack`). `death` plays **once** (holds the dead pose); `hit` plays **once**;
`idle`/`walk` **loop**.

Make the motion **real and limb-correct**, because the calibration oracle (`calib_oracle.py`) checks
that the right region moves:

- `attack` → the **arms** region (id 3) must be the top mover; a mis-skin where legs move on an attack
  is flagged `wrong_region`.
- `walk`/`run` → **legs** (id 4) move most.
- Every non-static clip must actually DEFORM — if nothing moves > ~2 px the oracle calls it a
  `dead_clip` (the rest pose baked N times).
- Looping clips (`idle`, `walk`) must be **loop-continuous** — first ≈ last pose, or `loop_continuity`
  (warn) flags an anchor-drift seam.

## CONSTRAINTS

- For each state, asset `animations[state].frames` MUST equal the clip's `frames`; `fps > 0`;
  `playback ∈ {loop, once}`.
- Pair the clips with the mesh either by embedding (`bake_anim_from_json.py`) or via
  `files.animation_clips`; the clips' `rig` must match the asset `rig`.

## GATES THIS STAGE MUST PASS

- `required_clips_present` (code `missing_required_clip`, error) — the archetype's required clip(s) are
  declared (combat: idle + attack + hit + death). Off-vocab synonyms count as their canonical name.
- `clip_vocab` (code `offvocab_clip`, warn) — clip names are on the engine vocabulary (no silent
  idle-fallback).
- `loop_continuity` (code `loop_discontinuity`, warn) — looping clips don't drift at the seam.
- (verify) `calib_oracle` — `attack` moves arms, locomotion moves legs, no `dead_clip`/`wrong_region`.

## DONE WHEN

`idle`, `attack`, `hit`, `death` are authored, on-vocabulary, embedded/paired with matching
`frames`/`fps`/`playback`, and the limb that should move for each clip does (oracle-clean: no
`dead_clip`, no `wrong_region`).
