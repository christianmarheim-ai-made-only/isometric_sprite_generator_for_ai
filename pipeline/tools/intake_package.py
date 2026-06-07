#!/usr/bin/env python3
"""Generated-package intake: synthesize the .asset.json front door + GATE the delivery.

A producer delivers a self-describing PACKAGE (not a pipeline-internal .asset.json):

  <id>.package_manifest.json   inventory: entry_files{role -> filename}  (generated_asset_package_v1)
  <id>.source_asset.json       descriptor: axes/units, part names, hit_proxy_objects (the region map),
                               clips_states, and -- newly -- archetype + rig + per-clip fps
  <id>_hitbox.json             world_metrics (height/footprint/eye) + per-region AABBs
  <id>_anim.json               animation clips (anim_clips_v1)
  <id>.glb / <id>_rigged.glb   mesh (delivered, possibly unrigged / rigged by rig_from_profile)
  <id>_materials.json, <id>_texture_atlas.png, ...

The .asset.json that `bake_asset` consumes is a PIPELINE-INTERNAL contract (its archetype enum, rig
names and region_source move when the pipeline moves), so the pipeline OWNS it rather than asking the
producer to hand-author it. `synthesize_asset` builds it DETERMINISTICALLY from the package -- every
field traces to a declared source (see FIELD MAP). `lint_package` is the intake GATE: it fails a
delivery BEFORE a batch wastes time baking it, catching the gaps that otherwise surface as a random
mid-batch error or a silently-wrong sprite (missing file, undeclared archetype/rig, a rig profile that
isn't installed, a hit region outside the 4-region engine contract, a clip with no fps).

  python pipeline/tools/intake_package.py lint  <package_dir>
  python pipeline/tools/intake_package.py synth <package_dir> [--write]

FIELD MAP (asset.json  <-  package):
  asset_contract_version  = "external_asset_v2"
  texture_mode            = source_asset.texture_mode (REQUIRED in v2; default flat_region)
  variant_id              = source_asset.asset_id
  archetype               = source_asset.archetype                          (REQUIRED, gate-checked)
  rig                     = source_asset.rig                                (REQUIRED, gate-checked)
  files.mesh              = <id>_rigged.glb if present else source_asset.source_file
  files.animation_clips   = package_manifest.entry_files.animation_data
  geometry.up             = "y" if the rigged glb is used else source_asset.up_axis (sign dropped)
  geometry.forward        = source_asset.forward_axis (lower-cased, sign kept)
  geometry.unit           = source_asset.units
  region_source           = "material_name"  (the rig step bakes the declared regions into mat names)
  default_state           = source_asset.default_state | "idle" | first clip
  textures.base_color     = package_manifest.entry_files.texture_atlas
  animations[state]       = {clip, frames, playback, fps} from source_asset.clips_states
                            fps = clip.fps | source_asset.default_fps | DEFAULT_FPS
  world_metrics           = hitbox.world_metrics
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
SCHEMA_DIR = PIPELINE_ROOT / "schema"
RIG_PROFILE_DIR = SCHEMA_DIR / "rig_profiles"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from constants import offvocab_clip_renames  # noqa: E402

DEFAULT_FPS = 12                                   # last-resort playback fps when none is declared
BODY_REGIONS = {"head", "torso", "arms", "legs"}   # the 4 engine R8 body regions (5-7 = deferred gear)
WORLD_METRIC_KEYS = ("height_world", "footprint_radius_world", "eye_height_world")


# --------------------------------------------------------------------------- helpers
def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _find(package_dir: Path, *patterns: str) -> Path | None:
    for pat in patterns:
        hits = sorted(package_dir.glob(pat))
        if hits:
            return hits[0]
    return None


def _archetype_enum() -> list[str]:
    """The authoritative archetype list lives in the external_asset schema (single source of truth)."""
    props = _load(SCHEMA_DIR / "external_asset.schema.json").get("properties", {})
    return props.get("archetype", {}).get("enum", [])


def _rig_profile_path(rig: str, package_dir: Path) -> Path | None:
    """Resolve a rig profile: installed in the pipeline OR shipped in the package's schema_extensions."""
    for cand in (RIG_PROFILE_DIR / f"{rig}.json",
                 package_dir / "schema_extensions" / f"{rig}.rig_profile.json",
                 package_dir / "schema_extensions" / f"{rig}.json"):
        if cand.exists():
            return cand
    return None


def find_package(package_dir: Path) -> dict:
    """Locate the three driver files. Returns {manifest, source_asset, hitbox} as Paths (or None)."""
    package_dir = Path(package_dir)
    return {
        "manifest": _find(package_dir, "*.package_manifest.json"),
        "source_asset": _find(package_dir, "*.source_asset.json"),
        "hitbox": _find(package_dir, "*_hitbox.json", "*.hitbox.json"),
    }


def is_package(package_dir: Path) -> bool:
    """A delivered generated package is identified by its package_manifest.json (+ a source_asset)."""
    f = find_package(Path(package_dir))
    return f["manifest"] is not None and f["source_asset"] is not None


# --------------------------------------------------------------------------- synthesis
def synthesize_asset(package_dir: Path) -> dict:
    """Deterministically build the external_asset_v2 .asset.json dict from a delivered package.

    Raises ValueError on the designer-only gaps (archetype/rig) so a direct call is as loud as the gate.
    """
    package_dir = Path(package_dir)
    f = find_package(package_dir)
    if not f["manifest"] or not f["source_asset"]:
        raise ValueError(f"not a generated package (need *.package_manifest.json + *.source_asset.json): {package_dir}")
    pm = _load(f["manifest"])
    sa = _load(f["source_asset"])
    entry = pm.get("entry_files", {})
    rid = sa["asset_id"]

    if not sa.get("archetype"):
        raise ValueError(f"{rid}: source_asset.archetype is required to synthesize the asset.json")
    if not sa.get("rig"):
        raise ValueError(f"{rid}: source_asset.rig is required to synthesize the asset.json")

    # mesh + up: prefer the rigged glb if the rig step has produced it (it re-exports standard Y-up glTF);
    # otherwise reference the delivered mesh and carry its declared up-axis through to the bake.
    rigged = package_dir / f"{rid}_rigged.glb"
    if rigged.exists():
        mesh, up = rigged.name, "y"
    else:
        mesh = sa.get("source_file") or entry.get("glb_mesh")
        up = sa["up_axis"].lstrip("+-").lower()

    asset: dict = {
        "asset_contract_version": "external_asset_v2",
        "variant_id": rid,
        "archetype": sa["archetype"],
        "texture_mode": sa.get("texture_mode", "flat_region"),
        "files": {"mesh": mesh},
        "geometry": {
            "up": up,
            "forward": sa["forward_axis"].lower(),
            "unit": sa["units"],
        },
        "rig": sa["rig"],
        "region_source": "material_name",
    }
    anim_file = entry.get("animation_data") or (f"{rid}_anim.json" if (package_dir / f"{rid}_anim.json").exists() else None)
    if anim_file:
        asset["files"]["animation_clips"] = anim_file

    states = [c["state"] for c in sa.get("clips_states", [])]
    asset["default_state"] = sa.get("default_state") or ("idle" if "idle" in states else (states[0] if states else "idle"))

    tex = entry.get("texture_atlas")
    if tex and (package_dir / tex).exists():
        asset["textures"] = {"base_color": tex}

    anims = {}
    for c in sa.get("clips_states", []):
        anims[c["state"]] = {
            "clip": c.get("clip") or c["state"],
            "frames": c["frames"],
            "fps": c.get("fps") or sa.get("default_fps") or DEFAULT_FPS,
            "playback": c.get("playback") or "loop",
        }
    asset["animations"] = anims

    if f["hitbox"]:
        wm = _load(f["hitbox"]).get("world_metrics", {})
        picked = {k: wm[k] for k in WORLD_METRIC_KEYS if k in wm}
        if picked:
            asset["world_metrics"] = picked
    return asset


def write_asset(package_dir: Path) -> Path:
    """Synthesize and write <id>.asset.json into the package. Returns the written path."""
    package_dir = Path(package_dir)
    asset = synthesize_asset(package_dir)
    out = package_dir / f"{asset['variant_id']}.asset.json"
    out.write_text(json.dumps(asset, indent=2) + "\n", encoding="utf-8")
    return out


# --------------------------------------------------------------------------- gate
class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, m: str) -> None:
        self.errors.append(m)

    def warn(self, m: str) -> None:
        self.warnings.append(m)

    @property
    def ok(self) -> bool:
        return not self.errors


def lint_package(package_dir: Path) -> Report:
    """Intake gate for a delivered generated package. Errors -> do not bake; warnings -> bake but review."""
    package_dir = Path(package_dir)
    r = Report()
    f = find_package(package_dir)

    # 1. inventory: manifest present + every declared entry file exists on disk.
    if not f["manifest"]:
        r.err("no *.package_manifest.json (not a delivered generated package)")
        return r
    pm = _load(f["manifest"])
    entry = pm.get("entry_files", {})
    if not entry:
        r.err("package_manifest.entry_files is empty (nothing declared)")
    for role, fname in entry.items():
        if not (package_dir / fname).exists():
            r.err(f"declared file missing: {role} -> {fname}")

    # 2. source_asset present + schema-valid.
    if not f["source_asset"]:
        r.err("no *.source_asset.json")
        return r
    sa = _load(f["source_asset"])
    sa_schema = _load(SCHEMA_DIR / "source_asset.schema.json")
    sa_errs = sorted(Draft202012Validator(sa_schema).iter_errors(sa), key=lambda e: list(e.path))
    for e in sa_errs:
        r.err(f"source_asset schema /{'/'.join(map(str, e.path))}: {e.message}")
    if sa_errs:
        return r                                   # shape is wrong; later checks assume valid shape

    rid = sa["asset_id"]

    # 3. archetype: declared + in the authoritative enum.
    arch = sa.get("archetype")
    enum = _archetype_enum()
    if not arch:
        r.err(f"{rid}: source_asset.archetype is required (one of {enum})")
    elif enum and arch not in enum:
        r.err(f"{rid}: archetype '{arch}' is not a known archetype {enum} "
              f"(add it to external_asset.schema.json + ship a rig profile)")

    # 4. rig: declared + a matching profile is installed or shipped.
    rig = sa.get("rig")
    if not rig:
        r.err(f"{rid}: source_asset.rig is required")
    elif _rig_profile_path(rig, package_dir) is None:
        r.err(f"{rid}: rig profile '{rig}' not found "
              f"(expected schema/rig_profiles/{rig}.json or schema_extensions/{rig}.rig_profile.json)")

    # 5. hitbox: present + authored world_metrics (the world_metrics_mismatch detector needs them).
    if not f["hitbox"]:
        r.warn(f"{rid}: no *_hitbox.json -> asset.json will carry no authored world_metrics "
               "(world_metrics_mismatch detector disabled for this package)")
    else:
        wm = _load(f["hitbox"]).get("world_metrics", {})
        missing = [k for k in WORLD_METRIC_KEYS if k not in wm]
        if missing:
            r.warn(f"{rid}: hitbox.world_metrics missing {missing}")
        regions = _load(f["hitbox"]).get("regions", {})
        bad = sorted(set(regions) - BODY_REGIONS)
        if bad:
            r.err(f"{rid}: hitbox declares non-contract regions {bad} (only {sorted(BODY_REGIONS)} ship today)")

    # 6. hit_proxy_objects: regions inside the 4-region contract; at least one declared.
    hp = sa.get("hit_proxy_objects", [])
    declared_regions = {h["region"] for h in hp}
    out_of_contract = sorted(declared_regions - BODY_REGIONS)
    if out_of_contract:
        r.err(f"{rid}: hit_proxy regions {out_of_contract} are outside the 4-region contract "
              f"{sorted(BODY_REGIONS)} (shield/weapon/gear are deferred)")
    if sa.get("variant_class") != "effect" and not hp:
        r.warn(f"{rid}: no hit_proxy_objects declared -> every part falls back to torso in the hitmask")

    # 7. clips: fps resolvable; default_state valid.
    states = [c["state"] for c in sa.get("clips_states", [])]
    if not states:
        r.err(f"{rid}: clips_states is empty (no animation states to bake)")
    for c in sa.get("clips_states", []):
        if not c.get("fps") and not sa.get("default_fps"):
            r.warn(f"{rid}: clip '{c['state']}' has no fps and no default_fps -> pipeline default {DEFAULT_FPS}")
    ds = sa.get("default_state")
    if ds and ds not in states:
        r.err(f"{rid}: default_state '{ds}' is not one of the declared states {states}")
    # clip vocabulary: a clip named off the engine vocabulary (move/shoot/hurt) bakes fine but the
    # renderer never selects it -> it silently plays idle for that action. Flag the rename.
    for declared, canon in offvocab_clip_renames(states):
        r.warn(f"{rid}: clip '{declared}' is off the engine clip vocabulary -> the renderer selects "
               f"'{canon}' and falls back to idle for '{declared}'; rename '{declared}' -> '{canon}'")

    # 8. rig step readiness: note if the delivery looks unrigged (no *_rigged.glb yet). bake_asset
    #    AUTO-RIGS an unrigged glb from the declared rig profile at bake time, so this is informational.
    if rig and not (package_dir / f"{rid}_rigged.glb").exists():
        r.warn(f"{rid}: no {rid}_rigged.glb present -> if the delivered glb is an UNRIGGED part-mesh set, "
               "bake_asset will auto-rig it from the declared rig profile at bake time")

    # 9. the synthesized asset.json must itself be schema-valid (closes the loop).
    try:
        asset = synthesize_asset(package_dir)
        ea_schema = _load(SCHEMA_DIR / "external_asset.schema.json")
        for e in sorted(Draft202012Validator(ea_schema).iter_errors(asset), key=lambda e: list(e.path)):
            r.err(f"synthesized asset.json /{'/'.join(map(str, e.path))}: {e.message}")
    except ValueError as e:
        r.err(f"{rid}: synthesis failed: {e}")

    return r


# --------------------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="Generated-package intake: synthesize asset.json + gate.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("lint", help="gate a delivered package (errors -> do not bake)")
    pl.add_argument("package_dir", type=Path)
    ps = sub.add_parser("synth", help="synthesize the asset.json from a delivered package")
    ps.add_argument("package_dir", type=Path)
    ps.add_argument("--write", action="store_true", help="write <id>.asset.json into the package")
    args = ap.parse_args()

    if args.cmd == "lint":
        r = lint_package(args.package_dir.resolve())
        for w in r.warnings:
            print(f"WARN: {w}")
        for e in r.errors:
            print(f"ERROR: {e}")
        print(f"{'OK' if r.ok else 'FAIL'}: {args.package_dir.name} "
              f"({len(r.errors)} error(s), {len(r.warnings)} warning(s))")
        return 0 if r.ok else 1

    # synth
    if args.write:
        out = write_asset(args.package_dir.resolve())
        print(f"WROTE {out}")
    else:
        print(json.dumps(synthesize_asset(args.package_dir.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
