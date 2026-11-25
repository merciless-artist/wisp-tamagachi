"""Tests for finding artwork on disk."""

import random
from pathlib import Path

import pytest

from cogs import assets
from cogs.assets import (
    ASSETS_DIR,
    MOOD_GIFS,
    MoodGif,
    asset_image,
    mood_image,
    stage_art,
)
from wisp.rules import (
    LONELY_PICTURES,
    MEDICINE_PICTURE,
    MESSES,
    POX_PICTURES,
    SNIFFLES_PICTURE,
    TANTRUM_PICTURES,
    Stage,
)

GROWN = [stage for stage in Stage if stage is not Stage.EGG]


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


def test_stage_art_is_the_stages_png_or_none_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assets, "ASSETS_DIR", tmp_path)
    (tmp_path / "stages").mkdir()
    (tmp_path / "stages" / "old_fogey.png").write_bytes(b"PNG")
    (tmp_path / "stages" / "teen.gif").write_bytes(b"GIF")

    assert stage_art(Stage.OLD_FOGEY) == tmp_path / "stages" / "old_fogey.png"
    assert stage_art(Stage.TEEN) is None


def test_every_chore_picture_is_in_the_moments_folder() -> None:
    names = [
        *(picture for _, _, picture in MESSES.values() if picture is not None),
        SNIFFLES_PICTURE,
        MEDICINE_PICTURE,
        *LONELY_PICTURES.values(),
        *TANTRUM_PICTURES.values(),
        *(name for pool in POX_PICTURES.values() for name in pool),
    ]
    for name in names:
        assert (ASSETS_DIR / "moments" / name).is_file(), name


@pytest.fixture
def gifs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty mood gif folder standing in for ASSETS."""
    monkeypatch.setattr(assets, "ASSETS_DIR", tmp_path)
    folder = tmp_path / MOOD_GIFS
    folder.mkdir(parents=True)
    return folder


def add_gifs(folder: Path, *names: str) -> None:
    for name in names:
        (folder / name).write_bytes(b"GIF89a")


def test_a_mood_gif_is_found_by_stage_run_together_and_mood(gifs: Path) -> None:
    add_gifs(gifs, "oldfogeyangry.gif")

    picked = mood_image(Stage.OLD_FOGEY, MoodGif.ANGRY, random.Random(1))

    assert picked == gifs / "oldfogeyangry.gif"


def test_every_numbered_variant_gets_its_turn(gifs: Path) -> None:
    add_gifs(gifs, "teenlol.gif", "teenlol2.gif", "teenlol10.gif")
    rng = random.Random(3)

    picked = {mood_image(Stage.TEEN, MoodGif.LOL, rng) for _ in range(60)}

    assert picked == {
        gifs / name for name in ("teenlol.gif", "teenlol2.gif", "teenlol10.gif")
    }


@pytest.mark.parametrize(
    "name",
    ["teenlolly.gif", "teenlol_old.gif", "teenlol.png", "xteenlol.gif"],
)
def test_other_files_are_not_variants(gifs: Path, name: str) -> None:
    add_gifs(gifs, name)

    assert mood_image(Stage.TEEN, MoodGif.LOL, random.Random(0)) is None


def test_a_missing_mood_gif_is_none(gifs: Path) -> None:
    add_gifs(gifs, "adultcry.gif")

    assert mood_image(Stage.CHILD, MoodGif.CRY, random.Random(0)) is None
    assert mood_image(Stage.EGG, MoodGif.CRY, random.Random(0)) is None


def test_no_mood_gif_folder_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assets, "ASSETS_DIR", tmp_path)

    assert mood_image(Stage.ADULT, MoodGif.ANGRY, random.Random(0)) is None


def test_a_new_gif_is_used_as_soon_as_it_is_on_disk(gifs: Path) -> None:
    assert mood_image(Stage.CHILD, MoodGif.CRY, random.Random(0)) is None

    add_gifs(gifs, "childcry.gif")

    assert mood_image(Stage.CHILD, MoodGif.CRY, random.Random(0)) == (
        gifs / "childcry.gif"
    )


@pytest.mark.parametrize("stage", GROWN)
@pytest.mark.parametrize("mood", [MoodGif.ANGRY, MoodGif.ANNOYED, MoodGif.LOL])
def test_every_stage_has_its_angry_annoyed_and_lol_gifs(
    stage: Stage, mood: MoodGif
) -> None:
    assert mood_image(stage, mood, random.Random(0)) is not None


@pytest.mark.parametrize("stage", GROWN)
def test_a_stage_without_a_cry_gif_has_a_lonely_fallback(stage: Stage) -> None:
    crying = mood_image(stage, MoodGif.CRY, random.Random(0))

    assert crying is not None or stage in LONELY_PICTURES
