#!/usr/bin/env python3
"""Assemble the self-contained "Model Authoring Contract" package (README + docs + schemas +
examples + rig profiles) and zip it. Reproducible: stages a clean tree then archives it.

  python pipeline/tools/package_authoring_contract.py [--out dist/model_authoring_contract_v1.zip]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
REPO = PIPELINE_ROOT.parent
DOCS = REPO / "docs"

DOC_FILES = [
    "authoring_overview.md",
    "modeling_the_body.md",
    "texturing_the_body.md",
    "generating_animation_data.md",
    "generating_hitbox_data.md",
    "external_asset_contract.md",
    "multistate_sprite_contract.md",
    "atlas_paging_contract.md",
]
SCHEMA_FILES = [
    "external_asset.schema.json",
    "animation_clips.schema.json",
    "hitbox_spec.schema.json",
    "sprite_manifest.schema.json",
    "source_asset.schema.json",
]


def stage(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "docs").mkdir(parents=True)
    for f in DOC_FILES:
        shutil.copy(DOCS / f, dst / "docs" / f)
    shutil.copy(DOCS / "PACKAGE_README.md", dst / "README.md")

    (dst / "schema").mkdir()
    for f in SCHEMA_FILES:
        shutil.copy(PIPELINE_ROOT / "schema" / f, dst / "schema" / f)
    shutil.copytree(PIPELINE_ROOT / "schema" / "rig_profiles", dst / "schema" / "rig_profiles")

    # examples: include all JSON + the small texture-starter PNGs; exclude heavy .glb (they live in
    # the repo's test_meshes and are referenced illustratively).
    shutil.copytree(PIPELINE_ROOT / "examples", dst / "examples",
                    ignore=shutil.ignore_patterns("*.glb"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Package the model-authoring contract into a zip.")
    ap.add_argument("--out", type=Path, default=REPO / "dist" / "model_authoring_contract_v1.zip")
    args = ap.parse_args()
    staging = REPO / "dist" / "model_authoring_contract_v1"
    stage(staging)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    archive = shutil.make_archive(str(args.out.with_suffix("")), "zip", root_dir=staging.parent,
                                  base_dir=staging.name)
    n = sum(1 for _ in staging.rglob("*") if _.is_file())
    print(f"PACKAGED {n} files -> {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
