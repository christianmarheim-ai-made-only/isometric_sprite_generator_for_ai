#!/usr/bin/env python3
"""collision_volumes derivation + validation tests (pure Python, NO Blender -- always runs in the env gate).

Proves:
  - the SHIPPED worked example (examples/wall_window_v1) derives to the engine contract's EXACT geometry
    (CONTRACT-scenery-structure-metadata S2): footprint offset/half-extents + span_world, from the
    region_hitboxes sidecar -- and the authored semantics ride unchanged;
  - the S6 validation gate REJECTS a bad emitted block (bottom>top, duplicate region, bad enum, a fully
    inert set, missing world_metrics) and WARNS (not rejects) on a nested-window overlap;
  - window_<n>_center sockets fall out of the core's named region_rects;
  - the env SCHEMA accepts the example and rejects the off-contract authorings (volumes without the
    sidecar, volumes + a single collision, volumes on terrain, a missing required field / bad enum).

  python pipeline/env/test_collision_volumes.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import collision_volumes as cv     # noqa: E402
import bake_env                    # noqa: E402  (the real schema validator; lazy core import, light)

EX = HERE / "examples"


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    return ok


def main():
    ok = True

    # ---- the worked example derives to the contract's EXACT geometry (S2) ----
    asset = json.loads((EX / "wall_window_v1.asset.json").read_text(encoding="utf-8"))
    rh = json.loads((EX / "wall_window_v1_hitbox.json").read_text(encoding="utf-8"))["region_hitboxes"]
    vols = cv.derive_volumes(rh, asset["collision_volumes"])

    by = {v["region"]: v for v in vols}
    wall = by["wall_body"]
    ok &= check("wall_body footprint == contract (offset [0,0], half [1.5,0.2])",
                wall["footprint"] == {"shape": "aabb", "offset_world": [0.0, 0.0], "half_extents_world": [1.5, 0.2]})
    ok &= check("wall_body span_world == [0.0, 3.0]", wall["span_world"] == [0.0, 3.0])

    glass = by["window_glass"]
    ok &= check("window_glass footprint == contract (offset [0.6,0], half [0.5,0.05])",
                glass["footprint"] == {"shape": "aabb", "offset_world": [0.6, 0.0], "half_extents_world": [0.5, 0.05]})
    ok &= check("window_glass span_world == [1.0, 2.2] (the vision aperture band)", glass["span_world"] == [1.0, 2.2])

    # ---- authored semantics ride unchanged ----
    ok &= check("glass authored: transparent + non-passable", glass["vision"] == "transparent" and glass["passable"] is False)
    ok &= check("glass authored: material_class 'glass'", glass["material_class"] == "glass")
    ok &= check("glass authored: bullet -> pass_ignore, default block_and_damage",
                glass["projectile_response"] == {"default": "block_and_damage", "by_class": {"bullet": "pass_ignore"}})
    ok &= check("glass authored: damage_variant_role 'damaged'", glass["damage_variant_role"] == "damaged")
    ok &= check("wall_body authored: damage_variant_role null", wall["damage_variant_role"] is None)
    ok &= check("authoring ORDER preserved (wall,sill,glass,lintel)",
                [v["region"] for v in vols] == ["wall_body", "window_sill", "window_glass", "window_lintel"])

    # ---- the derived block VALIDATES (S6): no errors; a nested-window overlap WARNS ----
    errs, warns = cv.validate_volumes(vols, world_metrics_present=True)
    ok &= check("worked example validates clean (no S6 errors)", errs == [])
    ok &= check("nested window emits a span-overlap WARNING (not an error)", len(warns) >= 1)

    # ---- S6 negatives: each must be an ERROR ----
    bad_span = [dict(wall, span_world=[3.0, 0.0])]
    ok &= check("S6: span bottom>top rejected", any("bottom" in e for e in cv.validate_volumes(bad_span, True)[0]))

    dup = [wall, dict(glass, region="wall_body")]
    ok &= check("S6: duplicate region rejected", any("unique" in e for e in cv.validate_volumes(dup, True)[0]))

    bad_enum = [dict(wall, vision="frosted")]
    ok &= check("S6: bad vision enum rejected", any("vision" in e for e in cv.validate_volumes(bad_enum, True)[0]))

    bad_proj = [dict(wall, projectile_response={"default": "deflect"})]
    ok &= check("S6: bad projectile_response rejected", any("projectile_response" in e for e in cv.validate_volumes(bad_proj, True)[0]))

    inert = [dict(wall, passable=True, vision="transparent")]
    ok &= check("S6: a fully passable+transparent set rejected (inert)", any("inert" in e or "non-passable" in e for e in cv.validate_volumes(inert, True)[0]))

    ok &= check("S6: collision_volumes without world_metrics rejected",
                any("world_metrics" in e for e in cv.validate_volumes(vols, world_metrics_present=False)[0]))

    # ---- window sockets from named region_rects (the core projects + keeps the name) ----
    rr = {"0": [{"name": "window_glass", "region_id": 2, "rect": [100, 50, 20, 40]},
                {"name": "wall_body", "region_id": 2, "rect": [10, 10, 200, 200]}]}
    socks = cv.window_sockets(rr, ["window_glass"], dirs=1)
    ok &= check("window_0_center = projected rect center [110, 70]", socks.get(0) == {"window_0_center": [110.0, 70.0]})

    # ---- the env SCHEMA: accepts the example, rejects the off-contract authorings ----
    ok &= check("schema ACCEPTS the wall_window_v1 example", bake_env.validate(asset) == [])

    no_sidecar = json.loads(json.dumps(asset)); no_sidecar["files"] = {"mesh": "wall_window_v1.glb"}
    ok &= check("schema REJECTS collision_volumes without files.hitbox", bake_env.validate(no_sidecar) != [])

    both = json.loads(json.dumps(asset))
    both["collision"] = {"footprint": {"shape": "circle", "radius_world": 1.0}, "blocks_movement": True, "blocks_vision": True}
    ok &= check("schema REJECTS collision + collision_volumes together", bake_env.validate(both) != [])

    on_terrain = {"env_contract_version": "env_asset_v1", "variant_id": "x", "kind": "terrain", "texture_mode": "textured",
                  "textures": {"base_color": "t.png"}, "collision_volumes": asset["collision_volumes"]}
    ok &= check("schema REJECTS collision_volumes on terrain", bake_env.validate(on_terrain) != [])

    missing_field = json.loads(json.dumps(asset))
    del missing_field["collision_volumes"][2]["vision"]
    ok &= check("schema REJECTS a volume missing a required field (vision)", bake_env.validate(missing_field) != [])

    bad_by_class = json.loads(json.dumps(asset))
    bad_by_class["collision_volumes"][2]["projectile_response"]["by_class"]["bullet"] = "deflect"
    ok &= check("schema REJECTS a bad by_class projectile enum", bake_env.validate(bad_by_class) != [])

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
