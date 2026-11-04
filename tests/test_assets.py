"""Tests for finding artwork on disk."""

from pathlib import Path

from cogs.assets import ASSETS_DIR, asset_image
from wisp.rules import (
    MEDICINE_PICTURE,
    MESSES,
    SNIFFLES_PICTURE,
    TANTRUM_PICTURES,
)


def test_an_animated_gif_wins_over_a_png(tmp_path: Path) -> None:
    (tmp_path / "ruby.png").write_bytes(b"PNG")
    (tmp_path / "ruby.gif").write_bytes(b"GIF")

    assert asset_image(tmp_path, "ruby") == tmp_path / "ruby.gif"


def test_a_png_is_used_when_there_is_no_gif(tmp_path: Path) -> None:
    (tmp_path / "book_red.png").write_bytes(b"PNG")

    assert asset_image(tmp_path, "book_red") == tmp_path / "book_red.png"


def test_missing_art_is_none(tmp_path: Path) -> None:
    assert asset_image(tmp_path, "nothing") is None
    assert asset_image(tmp_path / "no_folder", "nothing") is None


def test_a_folder_of_that_name_is_not_art(tmp_path: Path) -> None:
    (tmp_path / "odd.gif").mkdir()

    assert asset_image(tmp_path, "odd") is None


def test_every_chore_picture_is_in_the_moments_folder() -> None:
    names = [
        *(picture for _, _, picture in MESSES.values() if picture is not None),
        SNIFFLES_PICTURE,
        MEDICINE_PICTURE,
        *TANTRUM_PICTURES.values(),
    ]
    for name in names:
        assert (ASSETS_DIR / "moments" / name).is_file(), name
