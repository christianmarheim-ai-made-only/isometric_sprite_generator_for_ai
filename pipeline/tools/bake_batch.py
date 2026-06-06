#!/usr/bin/env python3
"""Batch-bake DELIVERED asset packages into game_iso_v1 sprite packages + one review index.

The intake path for incoming deliveries. Point it at `.asset.json` files (or directories to scan);
it bakes each via `bake_asset` -- so every package gets the up-axis correction, provenance stamping,
and the silent-failure detectors (non_upright_biped / world_metrics_mismatch / degenerate_uv /
oversize_atlas_page ...). A failing package does NOT abort the batch; it is recorded and the rest
continue. The aggregated `build_index.json` + console summary surface each package's Gate-1 status
and **warning codes**, so a reviewer sees at a glance which deliveries are clean, which need a look,
and which failed to bake -- the whole point of the build-log detection layer (docs/build_log_warnings.md).

  python pipeline/tools/bake_batch.py creative/incoming                 # every *.asset.json under the dir
  python pipeline/tools/bake_batch.py creative                          # all delivered packages under creative/
  python pipeline/tools/bake_batch.py a.asset.json b.asset.json         # an explicit list
  python pipeline/tools/bake_batch.py creative/incoming --sheets        # + per-package contact sheets to eyeball

Exit 0 only if every package baked AND is `ok` (Gate-1 pass + no error-severity warning).
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bake_asset import bake_asset  # noqa: E402
from build_log import write_build_index, index_summary  # noqa: E402
from intake_package import lint_package, write_asset, find_package  # noqa: E402


def prepare(paths, write: bool = True) -> tuple[list[dict], set, list[str]]:
    """Intake pre-pass: find every delivered generated package (a *.package_manifest.json), GATE it,
    and synthesize its <id>.asset.json when missing -- so a delivery that ships only its source files
    still bakes, and an incomplete/inconsistent one is caught HERE (skipped, recorded) instead of
    erroring at random mid-bake. Returns (intake_failures, skip_dirs, synthesized_variant_ids);
    skip_dirs hold packages whose gate failed (their asset.json, if any, is excluded from the bake).
    With write=False (dry run) it gates but writes nothing."""
    failures: list[dict] = []
    skip_dirs: set = set()
    synthesized: list[str] = []
    seen: set = set()
    for p in paths:
        p = Path(p)
        manifests = sorted(p.rglob("*.package_manifest.json")) if p.is_dir() else []
        for mani in manifests:
            pkg = mani.parent.resolve()
            if pkg in seen:
                continue
            seen.add(pkg)
            rep = lint_package(pkg)
            for w in rep.warnings:
                print(f"  intake warn [{pkg.name}]: {w}")
            if not rep.ok:
                print(f"  INTAKE FAIL [{pkg.name}]: {len(rep.errors)} error(s) -> not baked")
                for e in rep.errors:
                    print(f"     - {e}")
                failures.append({"package": pkg.name, "errors": rep.errors})
                skip_dirs.add(pkg)
                continue
            try:
                sa = find_package(pkg)["source_asset"]
                vid = json.loads(sa.read_text(encoding="utf-8"))["asset_id"]
                if not (pkg / f"{vid}.asset.json").exists():
                    synthesized.append(vid)
                    if write:
                        out = write_asset(pkg)
                        print(f"  intake: synthesized {out.name} for [{pkg.name}]")
                    else:
                        print(f"  intake: would synthesize {vid}.asset.json for [{pkg.name}]")
            except Exception as e:                       # synthesis blew up despite a clean gate -> record
                print(f"  INTAKE FAIL [{pkg.name}]: synth error {e!r} -> not baked")
                failures.append({"package": pkg.name, "errors": [repr(e)]})
                skip_dirs.add(pkg)
    return failures, skip_dirs, synthesized


def discover(paths) -> list[Path]:
    """Collect *.asset.json from files + (recursively) directories, de-duped, order-stable."""
    found: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            found += sorted(p.rglob("*.asset.json"))
        elif p.name.endswith(".asset.json") and p.exists():
            found.append(p)
        else:
            print(f"  skip (not an existing *.asset.json): {p}")
    seen, out = set(), []
    for a in found:
        r = a.resolve()
        if r not in seen:
            seen.add(r)
            out.append(a)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch-bake delivered asset packages + one review index.")
    ap.add_argument("paths", nargs="+", type=Path, help="*.asset.json files and/or directories to scan")
    ap.add_argument("--out", type=Path, default=PIPELINE_ROOT / "output" / "incoming_batch")
    ap.add_argument("--batch-id", default="incoming")
    ap.add_argument("--sheets", action="store_true", help="also write per-package contact sheets")
    ap.add_argument("--dry-run", action="store_true", help="list the packages that would bake, then stop")
    args = ap.parse_args()

    # Intake pre-pass: gate delivered packages + synthesize any missing asset.json front door.
    intake_failures, skip_dirs, would_synth = prepare(args.paths, write=not args.dry_run)

    assets = [a for a in discover(args.paths) if a.resolve().parent not in skip_dirs]
    if args.dry_run:
        print(f"DRY RUN: {len(assets) + len(would_synth)} package(s) would bake "
              f"({len(would_synth)} via synthesis); {len(intake_failures)} would be skipped (intake FAIL):")
        for a in assets:
            print(f"  {a}")
        for v in would_synth:
            print(f"  (synthesize) {v}.asset.json")
        for f in intake_failures:
            print(f"  SKIP {f['package']}: {len(f['errors'])} intake error(s)")
        return 0 if not intake_failures else 1
    if not assets:
        if intake_failures:
            print(f"\nINTAKE: all {len(intake_failures)} package(s) failed the gate; nothing to bake.")
            return 1
        print("no *.asset.json found under: " + ", ".join(str(p) for p in args.paths))
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"BATCH [{args.batch_id}]: {len(assets)} package(s) -> {args.out}")

    logs, failures = [], []
    for a in assets:
        try:
            variant_id = json.loads(a.read_text(encoding="utf-8")).get("variant_id", a.name[:-len(".asset.json")])
        except Exception:
            variant_id = a.name[:-len(".asset.json")]
        out_dir = args.out / variant_id
        print(f"\n=== {a.name}  ->  {variant_id} ===")
        try:
            bake_asset(a, out_dir)
        except SystemExit as e:                       # lint / Gate-1 failure (bake_asset raises this)
            print(f"  FAILED: {e}")
            failures.append({"asset": a.name, "variant": variant_id, "error": str(e)})
            continue
        except Exception as e:                        # anything unexpected (Blender, IO, ...)
            print(f"  ERROR: {e!r}")
            traceback.print_exc()
            failures.append({"asset": a.name, "variant": variant_id, "error": repr(e)})
            continue
        blog = out_dir / "build_log.json"
        if blog.exists():
            logs.append(json.loads(blog.read_text(encoding="utf-8")))
        if args.sheets:
            try:
                from make_contact_sheet import contact_sheet
                info = contact_sheet(out_dir)
                print(f"  sheets: {Path(info['color_sheet']).name}, {Path(info['hit_sheet']).name}")
            except Exception as e:
                print(f"  sheet failed: {e!r}")

    idx = write_build_index(args.out, logs, batch_id=args.batch_id) if logs else []

    print("\n" + "=" * 66)
    if idx:
        print(index_summary(idx))
    print("=" * 66)
    flagged = [r for r in idx if r.get("warning_codes")]
    if flagged:
        print("FLAGGED (baked, but review per-variant build_log.json):")
        for r in flagged:
            mark = "FAIL" if not r.get("ok", True) else "warn"
            print(f"  [{mark}] {r['variant']}: {', '.join(r['warning_codes'])}")
    if intake_failures:
        print(f"INTAKE FAILURES ({len(intake_failures)}) -- gated out, NOT baked:")
        for f in intake_failures:
            first = f["errors"][0][:160] if f["errors"] else ""
            print(f"  {f['package']}: {len(f['errors'])} error(s) (first: {first})")
    if failures:
        print(f"BAKE FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  {f['asset']} ({f['variant']}): {f['error'][:200]}")
    clean = sum(1 for r in idx if r.get("ok") and not r.get("warning_codes"))
    print(f"\nBATCH DONE: {clean} clean / {len(idx)} baked / {len(failures)} bake-fail / "
          f"{len(intake_failures)} intake-fail  ->  {args.out / 'build_index.json'}")
    return 0 if (not failures and not intake_failures and all(r.get("ok") for r in idx)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
