"""Remove a flat white backdrop from a frame sequence.

Only near-white, unsaturated pixels connected to the frame border count as
backdrop, so white sparkles and highlights inside the character survive.
A few pixels around the backdrop fade by lightness, so no white halo is left
on dark Discord themes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

NEAR_WHITE = 232  # darkest channel must be at least this bright
MAX_TINT = 24  # and the channels this close together (unsaturated)
FADE_FROM = 200  # edge pixels lighter than this fade toward transparent


def key_frame(path: Path) -> None:
    """Replace the border-connected white backdrop of one frame with transparency."""
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    low = rgb.min(axis=2)
    tint = rgb.max(axis=2) - low

    whiteish = (low >= NEAR_WHITE) & (tint <= MAX_TINT)
    labels, count = ndimage.label(whiteish)
    if count:
        border = np.unique(
            np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
        )
        backdrop = np.isin(labels, border[border > 0])
    else:
        backdrop = np.zeros_like(whiteish)

    band = ndimage.binary_dilation(backdrop, iterations=3) & ~backdrop
    fade = np.clip((low - FADE_FROM) / (255.0 - FADE_FROM), 0.0, 1.0)
    fade = fade * (tint <= MAX_TINT * 2)
    alpha = np.full(low.shape, 255.0)
    alpha[backdrop] = 0.0
    alpha[band] = 255.0 * (1.0 - fade[band])

    out = np.dstack([rgb, alpha]).clip(0, 255).astype(np.uint8)
    Image.fromarray(out, mode="RGBA").save(path)


def main() -> None:
    frames = sorted(Path(sys.argv[1]).glob("*.png"))
    for frame in frames:
        key_frame(frame)
    print(f"keyed {len(frames)} frames")


if __name__ == "__main__":
    main()
