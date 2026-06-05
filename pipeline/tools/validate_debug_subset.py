#!/usr/bin/env python3
"""Validate the M1/M2 arrow-pilot DEBUG-SUBSET manifest against its lockfiles + images.

NOTE the name: this is NOT the system contract gate. It is the single-page, full-canvas
debug-subset validator wired only to the arrow pilot (`output/arrow_pilot/manifest.json`); it
asserts pilot-specific shape (full-canvas rects, a single `idle` state, the debug-subset
lockfiles). The real engine-acceptance gate for ALL package shapes is `gate_engine_accept.py`
(Gate-1). Renamed from `validate_manifest.py` to stop it reading as the system validator
(D-validate decision)."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from PIL import Image
from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from contract_hash import compute_contract_hash, compute_individual_hashes  # noqa: E402
from constants import MAX_PAGE_PX  # noqa: E402

ALLOWED_MASK_VALUES = {0, 1, 2, 3, 4, 5, 6, 7}
TAU = 2 * math.pi


class ValidationFailure(Exception):
    pass


class Reporter:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks: list[str] = []

    def ok(self, msg: str) -> None:
        self.checks.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def assert_true(self, cond: bool, msg: str) -> None:
        if cond:
            self.ok(msg)
        else:
            self.error(msg)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_schema(manifest: dict[str, Any], schema_path: Path, reporter: Reporter) -> None:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: list(e.path))
    if not errors:
        reporter.ok("JSON schema validation passed")
        return
    for err in errors:
        loc = "/" + "/".join(str(p) for p in err.path)
        reporter.error(f"Schema error at {loc}: {err.message}")


def validate_lockfiles(manifest: dict[str, Any], lockfiles_dir: Path, reporter: Reporter) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_json(lockfiles_dir / "sprite_contract.lock.json")
    states = load_json(lockfiles_dir / "sprite_states.lock.json")
    variants = load_json(lockfiles_dir / "sprite_variants.lock.json")
    expected_hash = compute_contract_hash(lockfiles_dir)
    reporter.assert_true(manifest.get("contract_hash") == expected_hash, "contract_hash matches lockfiles")
    reporter.assert_true(manifest.get("state_contract_version") == states.get("state_contract_version"), "state_contract_version matches states lockfile")
    variant_id = manifest.get("variant_id")
    reporter.assert_true(variant_id in variants.get("variants", {}), f"variant_id {variant_id!r} exists in variants lockfile")
    actual_hashes = compute_individual_hashes(lockfiles_dir)
    manifest_hashes = manifest.get("build", {}).get("lockfile_hashes", {})
    reporter.assert_true(manifest_hashes == actual_hashes, "build.lockfile_hashes match recomputed lockfile hashes")
    return contract, states, variants


def validate_variant_and_states(manifest: dict[str, Any], states: dict[str, Any], variants: dict[str, Any], reporter: Reporter) -> None:
    variant = variants["variants"].get(manifest["variant_id"], {})
    supported = set(variant.get("supported_states", []))
    manifest_states = set(manifest.get("animations", {}).keys())
    reporter.assert_true(manifest_states == supported, "manifest states match variant supported_states")
    reporter.assert_true(manifest.get("frame_canvas") == variant.get("frame_canvas"), "frame_canvas matches variant lock")
    reporter.assert_true(manifest.get("direction_count") == variant.get("direction_count"), "direction_count matches variant lock")
    for state_name, anim in manifest.get("animations", {}).items():
        state_lock = states.get("states", {}).get(state_name)
        if not state_lock:
            reporter.error(f"state {state_name!r} missing from states lock")
            continue
        reporter.assert_true(anim.get("playback") == state_lock.get("playback"), f"{state_name}: playback matches lock")
        reporter.assert_true(anim.get("directions") == state_lock.get("directions"), f"{state_name}: direction count matches lock")
        reporter.assert_true(anim.get("frames") == state_lock.get("frames"), f"{state_name}: frame count matches lock")
        for socket in state_lock.get("required_sockets", []):
            missing = [f for f in manifest["frames"] if f["state"] == state_name and socket not in f.get("sockets", {})]
            reporter.assert_true(not missing, f"{state_name}: required socket {socket!r} present on every frame")
        required_markers = set(state_lock.get("required_markers", []))
        marker_names = {m.get("name") for m in anim.get("markers", [])}
        reporter.assert_true(required_markers.issubset(marker_names), f"{state_name}: required markers present")
        frame_count = sum(1 for f in manifest["frames"] if f["state"] == state_name)
        reporter.assert_true(frame_count == anim["directions"] * anim["frames"], f"{state_name}: manifest has directions*frames entries")


def validate_images(manifest_path: Path, manifest: dict[str, Any], reporter: Reporter) -> tuple[Image.Image, Image.Image]:
    base = manifest_path.parent
    color_info = manifest["atlases"]["color"]
    mask_info = manifest["atlases"]["hitmask"]
    # This is the SINGLE-PAGE debug-subset validator (see module docstring + the
    # D-validate decision in docs/next_phase_plan.md). Paged atlases are accepted by
    # gate_engine_accept (Gate-1) + the build log's oversize_atlas_page check -- not here. Detect a
    # paged manifest and fail gracefully instead of KeyError-ing on the absent single-page "path".
    if "pages" in color_info or "pages" in mask_info:
        raise ValidationFailure(
            "validate_debug_subset is single-page only; use gate_engine_accept for paged atlases")
    color_path = base / color_info["path"]
    mask_path = base / mask_info["path"]
    reporter.assert_true(color_path.exists(), f"color atlas exists: {color_info['path']}")
    reporter.assert_true(mask_path.exists(), f"hitmask atlas exists: {mask_info['path']}")
    if not color_path.exists() or not mask_path.exists():
        raise ValidationFailure("Missing atlas image")
    color = Image.open(color_path)
    mask = Image.open(mask_path)
    reporter.assert_true(color.mode == "RGBA", "color atlas mode is RGBA")
    reporter.assert_true(mask.mode == "L", "hitmask atlas mode is L/R8")
    reporter.assert_true(list(color.size) == color_info["size"], "color atlas size matches manifest")
    reporter.assert_true(list(mask.size) == mask_info["size"], "hitmask atlas size matches manifest")
    reporter.assert_true(color.size[0] <= MAX_PAGE_PX and color.size[1] <= MAX_PAGE_PX,
                         f"color atlas within {MAX_PAGE_PX}x{MAX_PAGE_PX} page max")
    reporter.assert_true(mask.size[0] <= MAX_PAGE_PX and mask.size[1] <= MAX_PAGE_PX,
                         f"hitmask atlas within {MAX_PAGE_PX}x{MAX_PAGE_PX} page max")
    return color, mask


def rect_inside(rect: list[int], size: tuple[int, int]) -> bool:
    x, y, w, h = rect
    return x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= size[0] and y + h <= size[1]


def validate_frame_images(manifest: dict[str, Any], color: Image.Image, mask: Image.Image, reporter: Reporter) -> None:
    canvas_w, canvas_h = manifest["frame_canvas"]
    mask_palette = manifest.get("atlases", {}).get("hitmask", {}).get("palette", {})
    palette_values = set(mask_palette.values()) or ALLOWED_MASK_VALUES
    for frame in manifest["frames"]:
        label = f"{frame['state']} dir{frame['direction']:02d} frame{frame['frame_index']:02d}"
        rect = frame["rect"]
        mask_rect = frame["mask_rect"]
        # Frame-local coords (anchor/sockets/boxes) are defined relative to the
        # rect's top-left and bounded by the rect's own w/h -- not frame_canvas.
        # They coincide today because the pilot never crops (rect == canvas; the
        # assertion below enforces that). When M3 tight-crop lands (rect.w <
        # canvas_w), this is the correct bound; the crop-contains-anchor rule and
        # the canvas-sized pixel loops below will then need a dedicated M3 test.
        rect_w, rect_h = rect[2], rect[3]
        reporter.assert_true(rect_inside(rect, color.size), f"{label}: color rect inside atlas")
        reporter.assert_true(rect_inside(mask_rect, mask.size), f"{label}: mask rect inside atlas")
        reporter.assert_true(rect[2:] == [canvas_w, canvas_h], f"{label}: color rect dimensions equal frame_canvas")
        reporter.assert_true(mask_rect[2:] == rect[2:], f"{label}: mask rect dimensions equal color rect")
        ax, ay = frame["anchor"]
        reporter.assert_true(0 <= ax < rect_w and 0 <= ay < rect_h, f"{label}: anchor inside frame rect")
        origin = frame.get("sockets", {}).get("origin")
        reporter.assert_true(origin == frame["anchor"], f"{label}: origin socket equals anchor")
        for socket_name, point in frame.get("sockets", {}).items():
            sx, sy = point
            reporter.assert_true(0 <= sx < rect_w and 0 <= sy < rect_h, f"{label}: socket {socket_name} inside frame rect")

        color_crop = color.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
        mask_crop = mask.crop((mask_rect[0], mask_rect[1], mask_rect[0] + mask_rect[2], mask_rect[1] + mask_rect[3]))
        color_pixels = color_crop.load()
        mask_pixels = mask_crop.load()
        values_seen: set[int] = set()
        # Validate alpha->mask-none rule and palette membership.
        for y in range(canvas_h):
            for x in range(canvas_w):
                alpha = color_pixels[x, y][3]
                value = int(mask_pixels[x, y])
                values_seen.add(value)
                if alpha < 8 and value != 0:
                    reporter.error(f"{label}: transparent pixel ({x},{y}) has nonzero mask value {value}")
        bad_values = values_seen - set(palette_values) - {0}
        reporter.assert_true(not bad_values, f"{label}: mask values are in allowed palette")

        # Boxes: check each box is inside frame and bounds its region pixels.
        for region_name, box in frame.get("boxes", {}).items():
            if region_name not in mask_palette:
                reporter.error(f"{label}: box region {region_name!r} not in mask palette")
                continue
            region_value = int(mask_palette[region_name])
            bx, by, bw, bh = box
            reporter.assert_true(0 <= bx < rect_w and 0 <= by < rect_h and bw > 0 and bh > 0 and bx + bw <= rect_w and by + bh <= rect_h, f"{label}: {region_name} box inside frame")
            xs: list[int] = []
            ys: list[int] = []
            for y in range(canvas_h):
                for x in range(canvas_w):
                    if int(mask_pixels[x, y]) == region_value:
                        xs.append(x)
                        ys.append(y)
            if not xs:
                reporter.error(f"{label}: {region_name} box exists but no pixels found")
                continue
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            reporter.assert_true(bx <= min_x and by <= min_y and bx + bw - 1 >= max_x and by + bh - 1 >= max_y, f"{label}: {region_name} box bounds mask pixels")


def validate_directions(manifest: dict[str, Any], reporter: Reporter) -> None:
    direction_count = manifest["direction_count"]
    expected_count = direction_count * manifest["animations"]["idle"]["frames"]
    reporter.assert_true(len(manifest["frames"]) == expected_count, "frame count equals direction_count * idle frames")
    seen_dirs = sorted(f["direction"] for f in manifest["frames"] if f["state"] == "idle")
    reporter.assert_true(seen_dirs == list(range(direction_count)), "idle directions are dense 0..N-1")
    for frame in manifest["frames"]:
        expected_degrees = frame["direction"] * 360.0 / direction_count
        reporter.assert_true(abs(frame["world_yaw_degrees"] - expected_degrees) < 1e-5, f"dir{frame['direction']:02d}: world yaw equals direction bin center (i*360/N)")

    # M1 diagnostic pair.
    by_dir = {f["direction"]: f for f in manifest["frames"]}
    if 2 in by_dir:
        dx, dy = by_dir[2]["screen_direction_vector"]
        reporter.assert_true(abs(dx) < 0.0001 and dy > 0.99, "M1 diagnostic: dir02 points straight down")
    else:
        reporter.error("M1 diagnostic: dir02 missing")
    if 10 in by_dir:
        dx, dy = by_dir[10]["screen_direction_vector"]
        reporter.assert_true(abs(dx) < 0.0001 and dy < -0.99, "M1 diagnostic: dir10 points straight up")
    else:
        reporter.error("M1 diagnostic: dir10 missing")


def validate_world_metrics(manifest: dict[str, Any], reporter: Reporter) -> None:
    metrics = manifest.get("world_metrics", {})
    height = metrics.get("height_world")
    radius = metrics.get("footprint_radius_world")
    reporter.assert_true(isinstance(height, (int, float)) and height > 0, "height_world is positive")
    reporter.assert_true(isinstance(radius, (int, float)) and radius > 0, "footprint_radius_world is positive")
    eye = metrics.get("eye_height_world")
    if eye is not None:
        reporter.assert_true(isinstance(eye, (int, float)) and eye > 0, "eye_height_world is positive when present")
        reporter.assert_true(eye <= height, "eye_height_world <= height_world")


def validate_camera(manifest: dict[str, Any], reporter: Reporter) -> None:
    """Engine camera-contract checks (game_iso_v1): id, azimuth 45, elevation 30
    (reject the 26.565 tile-edge angle), tile 64x32, screen_y down."""
    cam = manifest.get("camera", {})
    reporter.assert_true(cam.get("id") == "game_iso_v1", "camera.id == game_iso_v1")
    reporter.assert_true(cam.get("azimuth_degrees") == 45, "camera.azimuth_degrees == 45")
    elev = cam.get("camera_elevation_degrees")
    reporter.assert_true(elev == 30, "camera.camera_elevation_degrees == 30")
    reporter.assert_true(not (isinstance(elev, (int, float)) and abs(elev - 26.565) < 0.5),
                         "camera elevation is NOT 26.565 (that is the screen tile-edge angle)")
    reporter.assert_true(cam.get("tile_px") == [64, 32], "camera.tile_px == [64, 32]")
    reporter.assert_true(cam.get("screen_y") == "down", "camera.screen_y == down")


def validate_debug_subset(manifest_path: Path, pipeline_root: Path) -> dict[str, Any]:
    reporter = Reporter()
    manifest = load_json(manifest_path)
    schema_path = pipeline_root / "schema" / "sprite_manifest.schema.json"
    lockfiles_dir = pipeline_root / "lockfiles"
    validate_schema(manifest, schema_path, reporter)
    validate_camera(manifest, reporter)
    _, states, variants = validate_lockfiles(manifest, lockfiles_dir, reporter)
    validate_variant_and_states(manifest, states, variants, reporter)
    color, mask = validate_images(manifest_path, manifest, reporter)
    validate_frame_images(manifest, color, mask, reporter)
    validate_directions(manifest, reporter)
    validate_world_metrics(manifest, reporter)
    # Store a stable, repo-relative manifest path so the report is reproducible
    # and diffable across machines (not an absolute C:\... or /mnt/... path).
    try:
        manifest_display = manifest_path.resolve().relative_to(pipeline_root.parent.resolve()).as_posix()
    except ValueError:
        manifest_display = manifest_path.name
    return {
        "manifest": manifest_display,
        "ok": not reporter.errors,
        "checks_passed": len(reporter.checks),
        "warnings": reporter.warnings,
        "errors": reporter.errors,
        "checks": reporter.checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate sprite manifest debug subset.")
    parser.add_argument("manifest", type=Path, nargs="?", default=Path(__file__).resolve().parents[1] / "output" / "arrow_pilot" / "manifest.json")
    parser.add_argument("--pipeline-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    report = validate_debug_subset(args.manifest.resolve(), args.pipeline_root.resolve())
    if args.report:
        write_json(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
