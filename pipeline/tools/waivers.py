#!/usr/bin/env python3
"""Named, single-check, EXPIRING severity waivers (review snippet 07; ADR-0028/0031).

A waiver lets a *declared* asset downgrade EXACTLY ONE named check code from `error` to `waived`
(so the build still passes) -- e.g. a calibration/debug texture that intentionally bakes flat
colours trips `atlas_colour_rich_low`, which is correct *for that asset*. A waiver is NOT a way to
hide a broken production bake:

  - it names EXACTLY ONE `code` (an unknown / non-waivable code is rejected: `waiver_unknown_code`);
  - it MUST carry `expires_at` (ISO date); compared to the bake/lint date it is invalid once the
    date is reached or past (`waiver_expired` / `waiver_missing` when expires_at is absent);
  - it MUST NOT attempt to claim real albedo (`engine_real_albedo: true` -> `waiver_attempts_real_albedo_true`);
  - it may downgrade ONLY a documented WAIVABLE code -- never a structural code (missing bone /
    region collapse / unweighted part / wrong scale, ...). See `WAIVABLE_CODES` below.

A waived check is NOT removed -- it still appears (as severity `waived`) in build_log.warnings and
verification_report.json, so the downgrade is always visible and auditable.

`today` is INJECTABLE everywhere (pass an ISO `YYYY-MM-DD` string) so tests are deterministic and
never call Date.now / date.today().

Public API:
  WAIVABLE_CODES                              -- the documented allowlist (frozenset of code strings)
  validate(waivers, today_iso)                -- structural validation -> list of error-dicts (empty = ok)
  resolve(check_code, waivers, today_iso)     -- the VALID waiver downgrading `check_code`, or None
"""
from __future__ import annotations

import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from error_codes import is_known  # noqa: E402

# --- The documented WAIVABLE allowlist -------------------------------------------------------------
# A waiver may downgrade ONLY these codes. They are the "intentional for a declared debug/flat asset"
# texture-fidelity / symmetry signals, NOT structural truth claims:
#   atlas_colour_rich_low  -- a calibration/debug texture deliberately uses flat, high-contrast colours
#                             (snippet 07's canonical example; improvement_addendum "Rule").
#   degenerate_uv          -- a declared-flat debug asset has no real unwrap (ADR-0028 example).
#   front_back_indistinct  -- a symmetric prop has no inherent front (ADR-0031 symmetric-prop exempt).
# Structural codes (missing_required_bone, unweighted_part, region_missing, world_metrics_mismatch,
# missing_required_clip, ...) are NEVER waivable -- a waiver naming one is `waiver_unknown_code`.
WAIVABLE_CODES = frozenset({
    "atlas_colour_rich_low",
    "degenerate_uv",
    "front_back_indistinct",
})


def _err(code: str, detail: str, waiver_id=None) -> dict:
    e = {"code": code, "severity": "error", "detail": detail}
    if waiver_id is not None:
        e["waiver_id"] = waiver_id
    return e


def _is_expired(expires_at: str, today_iso: str) -> bool:
    """A waiver is expired when today >= expires_at. ISO `YYYY-MM-DD` strings sort lexicographically,
    so a plain string compare is a correct date compare (no parsing, no locale)."""
    return str(today_iso) >= str(expires_at)


def validate(waivers, today_iso: str) -> list[dict]:
    """Structurally validate a list of waiver blocks against `today_iso` (ISO `YYYY-MM-DD`).

    Returns a list of error-dicts {code, severity:'error', detail, waiver_id?} -- empty list = all
    waivers are well-formed and in-date. Emits, per waiver:
      waiver_missing                     -- no `code`, or no `expires_at`
      waiver_unknown_code                -- `code` is unknown OR not in the WAIVABLE allowlist
      waiver_expired                     -- today >= expires_at
      waiver_attempts_real_albedo_true   -- engine_real_albedo is true
    `waivers` may be None / [] (no waivers -> no errors).
    """
    errs: list[dict] = []
    for w in (waivers or []):
        wid = (w or {}).get("waiver_id")
        code = (w or {}).get("code")
        expires_at = (w or {}).get("expires_at")

        if not code:
            errs.append(_err("waiver_missing", "waiver names no `code` (a waiver downgrades exactly "
                             "one named check)", wid))
        elif not is_known(code):
            errs.append(_err("waiver_unknown_code", f"waiver `code` '{code}' is not a known error code",
                             wid))
        elif code not in WAIVABLE_CODES:
            errs.append(_err("waiver_unknown_code", f"`code` '{code}' is a structural / non-waivable "
                             f"check; only {sorted(WAIVABLE_CODES)} may be waived", wid))

        if not expires_at:
            errs.append(_err("waiver_missing", f"waiver '{wid}' has no `expires_at` (a waiver MUST "
                             "expire)", wid))
        elif _is_expired(expires_at, today_iso):
            errs.append(_err("waiver_expired", f"waiver '{wid}' expired (expires_at {expires_at} <= "
                             f"today {today_iso})", wid))

        if (w or {}).get("engine_real_albedo") is True:
            errs.append(_err("waiver_attempts_real_albedo_true", f"waiver '{wid}' sets "
                             "engine_real_albedo:true -- a waiver must NEVER claim real albedo", wid))
    return errs


def resolve(check_code: str, waivers, today_iso: str):
    """Return the single VALID waiver that downgrades `check_code` for this bake, else None.

    A waiver matches when it names `check_code`, is in the WAIVABLE allowlist, is NOT expired against
    `today_iso`, and does not attempt real albedo. (An expired / malformed / real-albedo waiver does
    NOT match here -- it is surfaced as an error by `validate`, never silently honoured.) First valid
    match wins; its `waiver_id` is what the caller records on the downgraded warning.
    """
    for w in (waivers or []):
        if not w or w.get("code") != check_code:
            continue
        if check_code not in WAIVABLE_CODES:
            continue
        expires_at = w.get("expires_at")
        if not expires_at or _is_expired(expires_at, today_iso):
            continue
        if w.get("engine_real_albedo") is True:
            continue
        return w
    return None
