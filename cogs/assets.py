"""Wisp's artwork: where it lives on disk and how a picture is found."""

from pathlib import Path
from typing import Final

from wisp.rules import NAP_STAGES, Stage

ASSETS_DIR: Final = Path(__file__).resolve().parent.parent / "ASSETS"
_ART_FORMATS: Final = (".gif", ".png")


def asset_image(folder: Path, name: str) -> Path | None:
    """The picture called `name` in `folder`: an animated GIF, else a PNG, else None."""
    return next(
        (
            path
            for suffix in _ART_FORMATS
            if (path := folder / f"{name}{suffix}").is_file()
        ),
        None,
    )


def nap_image(stage: Stage) -> Path | None:
    """The nap picture while Wisp is young enough to have one, else None."""
    if stage not in NAP_STAGES:
        return None
    return asset_image(ASSETS_DIR / "moments", "nap")
