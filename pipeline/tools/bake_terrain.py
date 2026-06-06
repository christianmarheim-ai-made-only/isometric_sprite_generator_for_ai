#!/usr/bin/env python3
"""bake_terrain.py — bake a flat ground tile into a game_iso_v1 `variant_class:"terrain"` package.

Terrain is NOT a 3D mesh render — no Blender, no z-buffer, no 16-direction bake. A flat z=0 quad
under the LOCKED game_iso_v1 camera (orthographic, azimuth 45deg, elevation 30deg = arcsin(0.5))
projects by a PURE 2D AFFINE map, so a 1x1 m ground tile is a 2:1 diamond that is just a shear+scale
of a square source texture (engine ADR-053; pipeline ADR-0006 "Implementation note — no 3D-model
machinery is required"). This tool bakes exactly that:

  - warp a SEAMLESS square ground texture into the 2:1 iso diamond, ALPHA-CUT to the diamond
    geometry (transparent corners — the engine reference tile's defect was opaque white corners),
  - emit a one-frame game_iso_v1 manifest (variant_class:"terrain", direction_count:1, a single
    frame: direction 0, rect = whole atlas, anchor = atlas centre; NO world_metrics block — terrain
    is flat z=0 ground, not an occluder/viewer; the terrain tag IS the signal), and
  - GATE-3 ON EMIT: refuse to write any package whose camera elevation strays from 30deg by
    >= ELEVATION_EPS. This is the one IRREVERSIBLE mistake the gate exists to catch: NEVER bake at
    26.565deg (= arctan(0.5), the on-screen tile-EDGE angle, a screen result) — a camera literally
    at 26.57deg renders a ~2.236:1 diamond, wrong and unfixable after the bake.

Seamlessness (ADR-0006 sec.5): the diamond grid is seamless IFF the square source is seamless in
BOTH axes (adjacent diamonds are adjacent unit ground squares; the warp WRAP-samples the source, so
ground u=1 wraps to source u=0). The procedural texture below is seamless by construction (integer
harmonics, period 1); an authored --source is checked for edge-wrap continuity and warned if not.

Run:
  python pipeline/tools/bake_terrain.py --out DIR --variant-id ground_arid_v1
  python pipeline/tools/bake_terrain.py --out DIR --variant-id g --source tex.png --size 512x256
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from gate_engine_accept import engine_accept  # noqa: E402

# --- LOCKED game_iso_v1 terrain geometry (ADR-0006; not re-decided here) ----------------------
CAMERA_ELEVATION_DEGREES = 30          # = arcsin(0.5). NEVER 26.565 (= arctan(0.5), the tile-edge angle)
CAMERA_AZIMUTH_DEGREES = 45
ELEVATION_EPS = 0.05                    # Gate-3 emit-reject tolerance (ADR-0006 sec.2)
TILE_BASE = (64, 32)                    # a 1x1 m tile projects to a 64x32 diamond (2:1)
DEFAULT_TILE = (256, 128)              # minimal clean 2:1 multiple (matches the ground_example fixture)
SEAM_TOL = 6.0                          # mean |edge - opposite-edge| (0..255) below which a source tiles


def assert_clean_2to1(size: tuple[int, int]) -> None:
    """ADR-0006 sec.3: a terrain tile must be a clean 2:1, a multiple of the 64x32 base diamond."""
    w, h = size
    if w != 2 * h:
        raise SystemExit(f"terrain tile must be 2:1 (got {w}x{h})")
    if w % TILE_BASE[0] or h % TILE_BASE[1]:
        raise SystemExit(f"terrain tile {w}x{h} must be a multiple of {TILE_BASE[0]}x{TILE_BASE[1]}")


def procedural_arid_texture(s: int = 256) -> np.ndarray:
    """A deterministic, SEAMLESS (both-axes period-1) arid ground texture, shape (s, s, 3) uint8.
    Uses only integer-harmonic sin/cos of the normalized coords, so the field is exactly periodic
    over the tile (no RNG, no edge seam). Intentionally subtle — an arid backdrop, not clutter."""
    n = (np.arange(s) + 0.5) / s
    U, V = np.meshgrid(n, n)
    tau = 2.0 * np.pi
    field = (0.50
             + 0.18 * np.sin(tau * 1 * U) * np.cos(tau * 1 * V)
             + 0.12 * np.sin(tau * 2 * U + 1.7) * np.sin(tau * 3 * V + 0.5)
             + 0.08 * np.cos(tau * 4 * (U + V)))
    field = np.clip(field, 0.0, 1.0)
    lo = np.array([176.0, 150.0, 105.0])   # drier brown
    hi = np.array([205.0, 185.0, 138.0])   # sandy tan
    rgb = lo[None, None, :] + field[..., None] * (hi - lo)[None, None, :]
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _bilinear_wrap(src: np.ndarray, su: np.ndarray, sv: np.ndarray) -> np.ndarray:
    """Bilinear-sample src (H,W,C) at fractional pixel coords (su,sv), WRAPPING (so the result is
    seamless when src is). Vectorized over the (H,W) sample grid."""
    H, W = src.shape[:2]
    x0 = np.floor(su).astype(int)
    y0 = np.floor(sv).astype(int)
    fx = (su - x0)[..., None]
    fy = (sv - y0)[..., None]
    x0m, x1m = x0 % W, (x0 + 1) % W
    y0m, y1m = y0 % H, (y0 + 1) % H
    c00 = src[y0m, x0m].astype(float)
    c10 = src[y0m, x1m].astype(float)
    c01 = src[y1m, x0m].astype(float)
    c11 = src[y1m, x1m].astype(float)
    top = c00 * (1 - fx) + c10 * fx
    bot = c01 * (1 - fx) + c11 * fx
    return top * (1 - fy) + bot * fy


def warp_to_diamond(src_rgb: np.ndarray, size: tuple[int, int] = DEFAULT_TILE) -> np.ndarray:
    """Project a seamless square ground texture into the 2:1 iso diamond; alpha-cut to the diamond.

    Ground (u,v) in the unit square map to the diamond's vertices (top/right/bottom/left). For an
    output pixel centre (px,py), with centre (cx,cy):
        a = (px - cx) / (W/2)  = u - v   in [-1, 1]
        b = 1 + (py - cy)/(H/2) = u + v  in [ 0, 2]    ->  u = (a+b)/2, v = (b-a)/2
    A pixel is INSIDE the diamond iff u,v in [0,1) (the diamond IS the image of the unit square);
    outside -> alpha 0. WRAP-sampling the source keeps the diamond grid seamless. Returns (H,W,4)."""
    W, H = size
    cx, cy = W / 2.0, H / 2.0
    S = src_rgb.shape[0]
    PX, PY = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)   # (H, W) pixel centres
    a = (PX - cx) / (W / 2.0)
    b = 1.0 + (PY - cy) / (H / 2.0)
    u = (a + b) / 2.0
    v = (b - a) / 2.0
    inside = (u >= 0.0) & (u < 1.0) & (v >= 0.0) & (v < 1.0)
    rgb = _bilinear_wrap(src_rgb, (u % 1.0) * S, (v % 1.0) * S)
    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[inside, 3] = 255
    return out


def is_seamless(src_rgb: np.ndarray, tol: float = SEAM_TOL) -> bool:
    """Both-axes edge-wrap continuity: mean |opposite-edge diff| within tol (0..255)."""
    a = src_rgb.astype(float)
    dx = float(np.abs(a[:, 0, :] - a[:, -1, :]).mean())
    dy = float(np.abs(a[0, :, :] - a[-1, :, :]).mean())
    return dx <= tol and dy <= tol


def tile_3x3(diamond: np.ndarray) -> Image.Image:
    """Lay the diamond on a 3x3 iso grid (ADR-0006 sec.5 seam-check artifact). Tile (col,row) centre
    is at screen ((col-row)*W/2, (col+row)*H/2); alpha-composited so shared diamond edges abut."""
    H, W = diamond.shape[:2]
    tile = Image.fromarray(diamond, "RGBA")
    span = 3
    canvas_w = (span + 1) * W
    canvas_h = (span + 1) * H
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    ox, oy = canvas_w // 2 - W // 2, H  # origin so the block sits in view
    for col in range(span):
        for row in range(span):
            x = ox + (col - row) * (W // 2)
            y = oy + (col + row) * (H // 2)
            canvas.alpha_composite(tile, (x, y))
    return canvas


def bake_terrain(out: Path, variant_id: str, source: Path | None = None,
                 size: tuple[int, int] = DEFAULT_TILE,
                 elevation: float = CAMERA_ELEVATION_DEGREES,
                 write_preview: bool = True) -> dict:
    """Bake a `variant_class:"terrain"` package into `out`. Returns the emitted manifest dict.
    Raises SystemExit on the Gate-3 elevation guard or a Gate-1 (engine-acceptance) failure — so a
    bad-elevation tile NEVER produces a committable package."""
    # GATE-3 (emit reject) FIRST — the one irreversible mistake (ADR-0006 sec.2).
    if abs(elevation - 30.0) >= ELEVATION_EPS:
        raise SystemExit(
            f"GATE 3 FAIL: terrain camera elevation {elevation} must be 30 (|elev-30| < {ELEVATION_EPS}). "
            f"26.565 is arctan(0.5), the on-screen tile-edge angle, NOT the camera elevation; a 26.57deg "
            f"bake renders a ~2.236:1 diamond — wrong and unfixable after the bake.")
    assert_clean_2to1(size)
    out.mkdir(parents=True, exist_ok=True)
    W, H = size

    if source is not None:
        img = Image.open(source).convert("RGB")
        s = min(img.size)                      # the warp expects a SQUARE ground texture
        src_rgb = np.asarray(img.resize((s, s), Image.LANCZOS))
        src_label = str(source)
    else:
        src_rgb = procedural_arid_texture(256)
        src_label = "procedural_arid"

    if not is_seamless(src_rgb):
        print(f"WARN: source for {variant_id} is not edge-seamless; the diamond grid may show seams "
              f"(ADR-0006 sec.5 — label it one-off or supply a seamless texture).")

    diamond = warp_to_diamond(src_rgb, size)
    # ADR-0006 sec.4 self-check: corners transparent, centre opaque.
    if not (diamond[0, 0, 3] == 0 and diamond[0, W - 1, 3] == 0
            and diamond[H - 1, 0, 3] == 0 and diamond[H - 1, W - 1, 3] == 0):
        raise SystemExit("alpha-cut failed: a corner triangle is not fully transparent")
    if diamond[H // 2, W // 2, 3] != 255:
        raise SystemExit("alpha-cut failed: the diamond centre is not opaque")

    atlas_name = "color_atlas.png"
    Image.fromarray(diamond, "RGBA").save(out / atlas_name)
    if write_preview:
        tile_3x3(diamond).save(out / "preview_3x3.png")

    manifest = {
        "camera": {
            "id": "game_iso_v1",
            "azimuth_degrees": CAMERA_AZIMUTH_DEGREES,
            # pipeline convention + the field the elevation gate reads:
            "camera_elevation_degrees": elevation,
            # ADR-0006 / ground_example.json provenance alias (engine ignores both — needs only id):
            "elevation_degrees": elevation,
            "projection": "orthographic_pixel_iso_dimetric_2_to_1",
            "screen_y": "down",
            "tile_px": list(TILE_BASE),
        },
        "variant_id": variant_id,
        "variant_class": "terrain",
        "direction_count": 1,                                  # flat ground is rotation-invariant
        "frame_canvas": [W, H],
        "atlases": {"color": {"path": atlas_name, "size": [W, H]}},
        # one frame: rect = whole atlas, anchor = diamond centre (ADR-0006 sec.8).
        "frames": [{"direction": 0, "rect": [0, 0, W, H], "anchor": [W / 2.0, H / 2.0]}],
        # NO world_metrics (ADR-0006 sec.7): terrain is flat z=0 ground, not an occluder/viewer.
        "build": {"generator": "pipeline/tools/bake_terrain.py", "source": src_label,
                  "renderer": "affine_2d_warp"},
    }
    # GATE-1: would the engine loader accept this? (Re-uses the vendored engine schema + loader rules.)
    errs = engine_accept(manifest)
    if errs:
        raise SystemExit("terrain package failed Gate-1 (engine acceptance):\n  " + "\n  ".join(errs))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"BAKE_TERRAIN OK: {variant_id} -> {out}  (tile {W}x{H}, elevation {elevation}, source {src_label})")
    return manifest


def _parse_size(s: str) -> tuple[int, int]:
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except Exception:
        raise SystemExit(f"--size must be WxH (e.g. 256x128), got {s!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake a flat ground tile into a game_iso_v1 terrain package.")
    ap.add_argument("--out", type=Path, required=True, help="output package dir")
    ap.add_argument("--variant-id", required=True, help="variant id (output name)")
    ap.add_argument("--source", type=Path, default=None, help="seamless square source texture (PNG); omit for a procedural arid tile")
    ap.add_argument("--size", type=_parse_size, default=DEFAULT_TILE, help="tile WxH, a clean 2:1 multiple of 64x32 (default 256x128)")
    ap.add_argument("--elevation", type=float, default=CAMERA_ELEVATION_DEGREES, help="camera elevation (Gate-3 rejects anything off 30)")
    args = ap.parse_args()
    bake_terrain(args.out, args.variant_id, source=args.source, size=args.size, elevation=args.elevation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
