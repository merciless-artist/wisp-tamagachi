"""Wisp's artwork: where it lives on disk and how a picture is found."""

import random
import re
from enum import StrEnum, auto
from pathlib import Path
from typing import Final

from wisp.rules import NAP_STAGES, Stage

ASSETS_DIR: Final = Path(__file__).resolve().parent.parent / "ASSETS"
BANNERS: Final = "wisp-studio-rooms"
"""The folder under ASSETS with Myra's banner for each Studio post."""
MOOD_GIFS: Final = "wispmoods/gifs"
"""The folder under ASSETS with Myra's mood gifs, `<stage><mood>.gif`."""
_ART_FORMATS: Final = (".gif", ".png")


class MoodGif(StrEnum):
    """A feeling Myra drew a gif of Wisp showing, for each stage."""

    ANGRY = auto()
    ANNOYED = auto()
    LOL = auto()
    CRY = auto()


def stage_name(stage: Stage) -> str:
    """The stage's name run together, as Myra's file names have it (`oldfogey`)."""
    return stage.value.replace("_", "")


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


def stage_art(stage: Stage) -> Path | None:
    """The PNG of Wisp at `stage` in ASSETS/stages when it exists, else None."""
    path = ASSETS_DIR / "stages" / f"{stage.value}.png"
    return path if path.is_file() else None


def moment_image(name: str) -> Path | None:
    """The picture called `name` in ASSETS/moments when it exists, else None."""
    path = ASSETS_DIR / "moments" / name
    return path if path.is_file() else None


def nap_image(stage: Stage) -> Path | None:
    """The nap picture while Wisp is young enough to have one, else None."""
    if stage not in NAP_STAGES:
        return None
    return asset_image(ASSETS_DIR / "moments", "nap")


def mood_image(stage: Stage, mood: MoodGif, rng: random.Random) -> Path | None:
    """One of Myra's gifs of Wisp at `stage` showing `mood`, at random, or None.

    The options are `<stage><mood>.gif` and its numbered variants
    (`teenlol2.gif`); a new one is used as soon as it is on disk.
    """
    name = f"{stage_name(stage)}{mood.value}"
    variant = re.compile(rf"{re.escape(name)}\d*")
    found = sorted(
        path
        for path in (ASSETS_DIR / MOOD_GIFS).glob(f"{name}*.gif")
        if path.is_file() and variant.fullmatch(path.stem)
    )
    return rng.choice(found) if found else None
