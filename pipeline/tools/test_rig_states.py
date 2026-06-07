#!/usr/bin/env python3
"""Gate R-5: every rig-profile STATE name is a clip the engine can actually select.

A rig profile's `states` map (rig_profiles/*.json) names the animation clips a creature of that
archetype may deliver. The engine renderer SELECTS clips by the canonical names in
constants.ENGINE_CLIP_VOCAB; a state authored under any OTHER name is never selected and silently
falls back to `idle` -- the motion bakes but is dead. The shipped creature profiles drifted off
that vocabulary (dragon: bite/breath/takeoff/hurt; quadruped: graze; ball: pop/explode), so this
test pins the reconciliation: NO profile state is an off-vocabulary ORPHAN.

The invariant (per profile):
  1. `idle` is present (the universal required clip + fallback).
  2. NO ORPHAN: every state name is in ENGINE_CLIP_VOCAB, OR resolves through CLIP_SYNONYMS to a
     canonical clip name. (death/fly/roll are kept NON-load-bearing: not in ENGINE_CLIP_VOCAB, but
     self-mapped in CLIP_SYNONYMS so they resolve to a canonical *name* without being engine-selected.)
  3. CLEAN (R-5 reconciled profiles): constants.offvocab_clip_renames(states) is EMPTY -- no state is
     a synonym whose canonical engine clip is NOT also co-declared in the profile (which would be a
     "rename me" finding). A distinct flavour state (dragon `breath`, quadruped `graze`) is kept only
     when its canonical (`attack`/`walk`) is co-declared, so it never reads as an off-vocab rename.

biped_v1 is OUT OF THE R-5 LANE (owned elsewhere) and still carries the deliberate, documented
`punch -> attack` cross-repo drift (see the CLIP_SYNONYMS comment in constants.py: the pipeline's
ADR-044 canon uses `punch` but the live engine selects `attack`). This test does NOT fix biped; it
asserts biped has no ORPHAN and that its ONLY residual off-vocab finding is exactly that known drift,
so the gate stays honest (it would still fire if biped grew a NEW orphan or a different rename).

Run: python pipeline/tools/test_rig_states.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
RIG_DIR = PIPELINE_ROOT / "schema" / "rig_profiles"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from constants import ENGINE_CLIP_VOCAB, CLIP_SYNONYMS, offvocab_clip_renames  # noqa: E402

# R-5 reconciled creature profiles: these MUST be fully clean (no orphan, no off-vocab rename).
RECONCILED = {"dragon_v1", "quadruped_v1", "ball_v1", "bird_v1"}
# Out-of-lane profiles whose KNOWN, documented off-vocab residue is tolerated (state -> canonical).
# biped's `punch` is the engine/pipeline `punch` vs `attack` drift called out in constants.py.
KNOWN_OFFVOCAB = {"biped_v1": {("punch", "attack")}}

_VOCAB = set(ENGINE_CLIP_VOCAB)


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def _states(profile: dict) -> list:
    """State keys of a rig profile, dropping any documentation `_note`-style key."""
    return [k for k in (profile.get("states") or {}).keys() if not str(k).startswith("_")]


def _orphans(states) -> list:
    """States that are neither in ENGINE_CLIP_VOCAB nor resolvable via CLIP_SYNONYMS."""
    return [s for s in states if str(s).lower() not in _VOCAB and str(s).lower() not in CLIP_SYNONYMS]


def main() -> int:
    ok = True
    profiles = sorted(RIG_DIR.glob("*.json"))
    ok &= check(f"discovered rig_profiles/*.json (found {len(profiles)})", len(profiles) >= 1)

    seen_reconciled = set()
    for path in profiles:
        prof = json.loads(path.read_text(encoding="utf-8"))
        name = prof.get("rig_profile") or path.stem
        states = _states(prof)

        # (0) the profile actually declares states.
        ok &= check(f"{name}: declares at least one state", len(states) >= 1)

        # (1) idle present in EVERY profile.
        ok &= check(f"{name}: 'idle' state present", "idle" in states)

        # (2) NO ORPHAN in EVERY profile -- in vocab or resolves via CLIP_SYNONYMS.
        orphans = _orphans(states)
        ok &= check(f"{name}: no off-vocab orphan states (orphans={orphans})", not orphans)

        # (3) CLEAN renames. Reconciled profiles must be empty; out-of-lane profiles may carry only
        #     their KNOWN documented residue.
        ov = set(offvocab_clip_renames(states))
        if name in RECONCILED:
            seen_reconciled.add(name)
            ok &= check(f"{name}: offvocab_clip_renames is empty (clean) -> {sorted(ov)}", not ov)
        else:
            allowed = KNOWN_OFFVOCAB.get(name, set())
            unexpected = ov - allowed
            ok &= check(
                f"{name}: only KNOWN off-vocab residue {sorted(allowed)} (unexpected={sorted(unexpected)})",
                not unexpected,
            )

    # All four R-5 lane profiles were actually present and exercised (guard against silent skips).
    missing = RECONCILED - seen_reconciled
    ok &= check(f"all R-5 reconciled profiles present {sorted(RECONCILED)} (missing={sorted(missing)})",
                not missing)

    # Self-mapped NON-load-bearing clips resolve to themselves yet stay OUT of ENGINE_CLIP_VOCAB
    # (still non-load-bearing: the engine never selects them).
    for clip in ("death", "fly", "roll"):
        ok &= check(
            f"'{clip}' resolves to itself via CLIP_SYNONYMS and stays out of ENGINE_CLIP_VOCAB",
            CLIP_SYNONYMS.get(clip) == clip and clip not in _VOCAB,
        )
    # Regression: the die/dead/dying/ko family still folds ONTO death (self-map did not clobber it).
    ok &= check("die/dead/dying/ko still fold to 'death'",
                all(CLIP_SYNONYMS.get(k) == "death" for k in ("die", "dead", "dying", "ko")))

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
