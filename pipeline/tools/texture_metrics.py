"""Numeric texture/visual gates on the BAKED outputs (ADR-0028/0031; review snippets 03/10).

These run on the baked colour frames (not the producer's source atlas) so they can't be gamed by
an unbound rich atlas. `atlas_colour_rich` catches a flat/swatch/one-colour "textured" delivery;
`front_back_distinctness` turns "front must differ from back" into a number.
"""
from __future__ import annotations
import math
from collections import Counter

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

RICHNESS = dict(
    quantized_unique_rgb_4bit_min=64,
    rgb_entropy_bits_min=3.0,
    largest_single_colour_fraction_max=0.65,
    non_background_pixel_fraction_min=0.20,
)
FRONT_BACK_MAD_MIN = 8.0   # mean abs per-channel rgb difference over the silhouette union


def _body(color_png, alpha_min=180):
    im = Image.open(color_png).convert("RGBA")
    px = [p[:3] for p in im.getdata() if p[3] >= alpha_min]
    return px, (im.size[0] * im.size[1])


def atlas_colour_rich(color_png):
    """Return (ok, metrics). Measures the baked colour body, masked by alpha."""
    px, total = _body(color_png)
    n = len(px)
    if n == 0:
        return False, dict(reason="empty_body", quantized_unique_rgb_4bit=0, rgb_entropy_bits=0.0,
                           largest_single_colour_fraction=1.0, non_background_pixel_fraction=0.0)
    q = Counter(((r >> 4) << 4, (g >> 4) << 4, (b >> 4) << 4) for r, g, b in px)
    uniq = len(q)
    largest = max(q.values()) / n
    ent = -sum((c / n) * math.log2(c / n) for c in q.values())
    nonbg = n / total if total else 0.0
    m = dict(quantized_unique_rgb_4bit=uniq, rgb_entropy_bits=round(ent, 3),
             largest_single_colour_fraction=round(largest, 3), non_background_pixel_fraction=round(nonbg, 4))
    # The baked-body richness gate is uniq + entropy + largest-fraction -- these measure "is the
    # colour rich vs a flat swatch". non_background_pixel_fraction measures the BODY's share of the
    # full 256 canvas (i.e. on-screen sprite SIZE), not richness, so a small-but-richly-textured
    # sprite must not fail on it; it stays a recorded metric only. (For a SOURCE-atlas richness check
    # the producer's preflight applies non_bg against the atlas, where it is meaningful.)
    ok = (uniq >= RICHNESS["quantized_unique_rgb_4bit_min"]
          and ent >= RICHNESS["rgb_entropy_bits_min"]
          and largest <= RICHNESS["largest_single_colour_fraction_max"])
    return ok, m


def front_back_distinctness(front_png, back_png):
    """Pass when mean_abs_rgb_difference >= FRONT_BACK_MAD_MIN over the silhouette union of dir N vs N+8.
    (Stricter single-metric form of the review's `mad>=8 OR edge_ssim<=0.92`.)"""
    fa = Image.open(front_png).convert("RGBA")
    ba = Image.open(back_png).convert("RGBA")
    if fa.size != ba.size:
        ba = ba.resize(fa.size)
    fp, bp = fa.load(), ba.load()
    W, H = fa.size
    diff, n = 0.0, 0
    for y in range(H):
        for x in range(W):
            f, b = fp[x, y], bp[x, y]
            if f[3] < 128 and b[3] < 128:
                continue
            diff += (abs(f[0] - b[0]) + abs(f[1] - b[1]) + abs(f[2] - b[2])) / 3.0
            n += 1
    mad = diff / n if n else 0.0
    return (mad >= FRONT_BACK_MAD_MIN), dict(mean_abs_rgb_difference=round(mad, 3), union_pixels=n)
