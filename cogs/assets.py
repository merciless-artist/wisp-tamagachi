"""Wisp's artwork: where it lives on disk and how a picture is found."""

from pathlib import Path
from typing import Final

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
