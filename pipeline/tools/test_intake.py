#!/usr/bin/env python3
"""Gate the generated-package INTAKE path: deterministic asset.json synthesis + the delivery gate.

The cow/ball deliveries shipped WITHOUT a .asset.json (the producer omits the pipeline-internal front
door). intake_package.synthesize_asset builds it deterministically from the package; lint_package gates
the delivery before a batch bakes it. This test pins both, plus the no-drift region table and the
squid/dragon material-naming rule -- all pure Python (no Blender), so it runs in build.py --ci.

Run: python pipeline/tools/test_intake.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mesh_io  # noqa: E402
from constants import material_region_name, offvocab_clip_renames, region_for_name, REGION_NAME_TO_ID  # noqa: E402
from intake_package import lint_package, synthesize_asset  # noqa: E402

PKG = REPO / "creative" / "incoming"
PACKAGES = ["cow_brown_farm_v1", "red_ball_arrow_v1"]


def check(label: str, cond: bool) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    return cond


def main() -> int:
    ok = True

    # 1. Synthesis is deterministic AND matches the committed asset.json (the front door the pipeline owns).
    for n in PACKAGES:
        pkg = PKG / n
        if not pkg.exists():
            print(f"SKIP: {n} (package not present)")
            continue
        syn = synthesize_asset(pkg)
        committed = json.loads((pkg / f"{n}.asset.json").read_text(encoding="utf-8"))
        ok &= check(f"synth({n}) == committed {n}.asset.json", syn == committed)
        # idempotent: synthesizing twice gives the same dict
        ok &= check(f"synth({n}) is idempotent", synthesize_asset(pkg) == syn)
        # 2. The gate passes a complete, consistent delivery.
        rep = lint_package(pkg)
        ok &= check(f"lint_package({n}) OK ({len(rep.errors)} err, {len(rep.warnings)} warn)", rep.ok)

    # 3. The gate FAILS a broken delivery (missing file + bad archetype + bad rig + out-of-contract region).
    src = PKG / "cow_brown_farm_v1"
    if src.exists():
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "broken"
            shutil.copytree(src, dst)
            sa_p = dst / "cow_brown_farm_v1.source_asset.json"
            sa = json.loads(sa_p.read_text(encoding="utf-8"))
            sa["archetype"] = "griffon"                       # not in the archetype enum
            sa["rig"] = "griffon_v9"                          # no installed rig profile
            sa["hit_proxy_objects"].append({"name": "wing_L", "region": "weapon"})  # outside 4-region contract
            sa_p.write_text(json.dumps(sa), encoding="utf-8")
            (dst / "cow_brown_farm_v1_texture_atlas.png").unlink()  # a DECLARED entry_file now missing
            rep = lint_package(dst)
            blob = " ".join(rep.errors)
            ok &= check("broken delivery: gate FAILs", not rep.ok)
            ok &= check("broken: missing declared file caught", "texture_atlas" in blob)
            ok &= check("broken: unknown archetype caught", "griffon" in blob and "archetype" in blob)
            ok &= check("broken: missing rig profile caught", "griffon_v9" in blob)
            ok &= check("broken: out-of-contract region caught", "weapon" in blob)

    # 4. No region-table drift: the auto-rigger and the bake resolve names through the SAME function.
    ok &= check("region table shared (mesh_io re-exports constants.region_for_name)",
                mesh_io.region_for_name is region_for_name)
    ok &= check("shared table knows fancy keywords (wing->arms, tail->torso, beak->head)",
                region_for_name("wing_L") == 3 and region_for_name("tail_tip") == 2 and region_for_name("beak") == 1)

    # 5. material_region_name (the squid/dragon rule): keyword parts untouched; declared parts encoded so
    #    the bake's region_for_name resolves them to the DECLARED region.
    ok &= check("keyword part untouched (head_head stays head_head)",
                material_region_name("head_head", 1) == "head_head")
    legs = REGION_NAME_TO_ID["legs"]
    head = REGION_NAME_TO_ID["head"]
    ok &= check("squid tentacle declared legs -> tentacle_3__legs",
                material_region_name("tentacle_3", legs) == "tentacle_3__legs")
    # wing_L carries 'wing' (=arms), which OUTRANKS leg in the keyword order, so appending can't win --
    # the encoding must drop the conflicting name. Contract = the result resolves to the DECLARED region.
    wl = material_region_name("wing_L", legs)
    ok &= check(f"declared beats a higher-priority keyword (wing_L declared legs -> '{wl}' resolves legs)",
                region_for_name(wl) == legs and wl != "wing_L")
    # round-trip: the name a part is given resolves back to the region it was assigned
    for part, rid in [("tentacle_3", legs), ("siphon", head), ("wing_L", legs), ("head_head", head)]:
        nm = material_region_name(part, rid)
        ok &= check(f"round-trip region_for_name('{nm}') == {rid}", region_for_name(nm) == rid)

    # 6. clip-vocab gate: a clip named off the engine's vocabulary (move/shoot/hurt) bakes fine but the
    #    renderer never selects it -> silent idle fallback. Catch the rename; never false-positive on
    #    legit non-engine extras (graze/reload/celebrate) or when the canonical is already declared.
    ok &= check("clip-vocab: move/shoot/hurt flagged -> walk/attack/hit",
                dict(offvocab_clip_renames(["idle", "move", "run", "shoot", "hurt", "death"]))
                == {"move": "walk", "shoot": "attack", "hurt": "hit"})
    ok &= check("clip-vocab: canonical idle/walk/run/attack/hit is clean",
                offvocab_clip_renames(["idle", "walk", "run", "attack", "hit", "death"]) == [])
    ok &= check("clip-vocab: no false positive on legit extras (cow graze/death, ball roll/pop/explode)",
                offvocab_clip_renames(["idle", "walk", "run", "graze", "hit", "death"]) == []
                and offvocab_clip_renames(["idle", "roll", "pop", "explode"]) == [])
    ok &= check("clip-vocab: a synonym is NOT flagged when its canonical is also declared",
                offvocab_clip_renames(["walk", "move"]) == [])

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
