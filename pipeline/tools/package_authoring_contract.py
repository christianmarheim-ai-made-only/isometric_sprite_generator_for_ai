#!/usr/bin/env python3
"""Assemble the self-contained "Model Authoring Contract" package (README + docs + schemas +
examples + the small fixture meshes the examples reference) and zip it. Reproducible: stages a clean
tree then archives it. In-doc `pipeline/schema|examples|test_meshes/...` paths are rewritten to the
package-relative form so the docs match what ships (tool paths `pipeline/tools/...` are left as-is --
the tools live in the repo, noted in the README).

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
    "authoring_overview.md", "modeling_the_body.md", "texturing_the_body.md",
    "generating_animation_data.md", "generating_hitbox_data.md", "external_asset_contract.md",
    "generated_package_intake.md", "multistate_sprite_contract.md", "atlas_paging_contract.md",
]
SCHEMA_FILES = [
    "external_asset.schema.json", "animation_clips.schema.json", "hitbox_spec.schema.json",
    "sprite_manifest.schema.json", "source_asset.schema.json",
]
# the small box-fixture meshes the example *.asset.json files reference (relative to examples/)
MESH_FILES = ["humanoid.obj", "humanoid.mtl", "humanoid.glb", "sparrow.glb", "crow.glb", "grunt.glb"]


def _rewrite(text: str) -> str:
    """Make in-doc paths package-relative. Tool paths (pipeline/tools, pipeline/bevy_reference) are
    left as-is -- those live in the repo, not the package (the README says so)."""
    return (text.replace("pipeline/schema/", "schema/")
                .replace("pipeline/examples/", "examples/")
                .replace("pipeline/test_meshes/", "test_meshes/"))


def _rewrite_tree(d: Path) -> None:
    """Rewrite pipeline/ path prefixes in every text file (json/md/txt) under d; binaries untouched."""
    for p in d.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".json", ".md", ".txt"):
            p.write_text(_rewrite(p.read_text(encoding="utf-8")), encoding="utf-8")


def stage(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "docs").mkdir(parents=True)
    for f in DOC_FILES:
        (dst / "docs" / f).write_text(_rewrite((DOCS / f).read_text(encoding="utf-8")), encoding="utf-8")
    (dst / "README.md").write_text(_rewrite((DOCS / "PACKAGE_README.md").read_text(encoding="utf-8")), encoding="utf-8")

    (dst / "schema").mkdir()
    for f in SCHEMA_FILES:
        (dst / "schema" / f).write_text(_rewrite((PIPELINE_ROOT / "schema" / f).read_text(encoding="utf-8")), encoding="utf-8")
    shutil.copytree(PIPELINE_ROOT / "schema" / "rig_profiles", dst / "schema" / "rig_profiles")
    _rewrite_tree(dst / "schema" / "rig_profiles")

    shutil.copytree(PIPELINE_ROOT / "examples", dst / "examples")  # all examples incl. texture_starter glb
    _rewrite_tree(dst / "examples")  # rewrite pipeline/ refs in *.json/*.md notes; binaries untouched
    (dst / "test_meshes").mkdir()
    for f in MESH_FILES:
        shutil.copy(PIPELINE_ROOT / "test_meshes" / f, dst / "test_meshes" / f)


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
