"""Remove a green screen without eating dark parts of the character.

A plain chroma key also catches near-black pixels that picked up a green tint
from the backdrop (Wisp's body). Here a pixel is background only if it is
clearly bright green AND connected to the frame border; enclosed regions survive.
Edges get a soft alpha and green spill is pulled back to neutral.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

MIN_GREEN = 80        # green channel must be at least this bright
DOMINANCE = 1.35      # ...and this many times stronger than red and blue


def key_frame(path: Path) -> None:
    """Replace the border-connected green backdrop of one frame with transparency."""
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    other = np.maximum(r, b) + 1.0

    greenish = (g >= MIN_GREEN) & (g / other >= DOMINANCE)
    labels, count = ndimage.label(greenish)
    if count:
        border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
        backdrop = np.isin(labels, border[border > 0])
    else:
        backdrop = np.zeros_like(greenish)
    # Trapped pockets between flame tendrils: unmistakably bright green is
    # backdrop anywhere. Wisp's dark body is never this bright or this green.
    backdrop |= (g >= 120) & (g / other >= 1.8)

    # Edge band: pixels near the backdrop that are still partly green are mixed
    # with the backdrop. Fade them out in proportion to how green they are.
    band = ndimage.binary_dilation(backdrop, iterations=4) & ~backdrop
    # Real flame is orange (green well under red). Olive means flame mixed with
    # backdrop, so fade by how far green climbs toward red, for low-blue pixels.
    olive = np.clip((g / (r + 1.0) - 0.6) / 0.4, 0.0, 1.0) * (b < 110)
    spill = np.maximum(np.clip((g - np.maximum(r, b)) / (g + 1.0) * 2.5, 0.0, 1.0), olive)
    alpha = np.full(g.shape, 255.0)
    alpha[backdrop] = 0.0
    alpha[band] = 255.0 * (1.0 - spill[band])
    # Haze: faint flame wisps painted over the green read as dim mustard. Real
    # flame is bright, or properly orange; dim AND yellow near the backdrop is
    # backdrop showing through, so fade it.
    halo = ndimage.binary_dilation(backdrop, iterations=12) & ~backdrop
    yellowness = np.clip((g / (r + 1.0) - 0.65) / 0.2, 0.0, 1.0)
    dimness = np.clip((190.0 - r) / 60.0, 0.0, 1.0)
    haze = yellowness * dimness * (b < 80) * halo
    alpha = alpha * (1.0 - haze)
    alpha = alpha.astype(np.uint8)

    # Spill suppression on everything kept: green may not exceed max(red, blue).
    g_fixed = np.where(g > other - 1.0, other - 1.0, g)
    out = np.dstack([r, g_fixed, b]).clip(0, 255).astype(np.uint8)
    Image.fromarray(np.dstack([out, alpha]), mode="RGBA").save(path)


def main() -> None:
    frames = sorted(Path(sys.argv[1]).glob("*.png"))
    for frame in frames:
        key_frame(frame)
    print(f"keyed {len(frames)} frames")


if __name__ == "__main__":
    main()
