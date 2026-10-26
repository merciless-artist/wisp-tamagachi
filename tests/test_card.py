"""Tests for the status card text, checked against Myra's template."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wisp.card import LABEL_PADDING, CardFacts, bar, render_status
from wisp.life import Life, Phase, new_egg
from wisp.rules import EGG_FOOD_NEEDED, EGG_WARMTH, HATCHING_TIME, Stage
from wisp.text import MESSAGE_LIMIT, text_length

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
TEMPLATE = (
    (Path(__file__).parent.parent / "DOCS" / "specs" / "status_menu_template.txt")
    .read_bytes()
    .decode("utf-8")
    .split("\n")
)
WISP_ID = 1560213420068966441
HOUSE_ID = 1563693152882262026
FACTS = CardFacts(
    happiness=90,
    fed_today=3,
    viibr_tracks=6,
    suno_tracks=2,
    wisp_id=WISP_ID,
    house_id=HOUSE_ID,
)

# ---
# Myra's template
# ---

# Her template's lines, by what they are.
TOP, TITLE_RULE, DAY, GAP_ABOVE_BARS, CARE, HAPPY, HUNGER = TEMPLATE[:7]
POKE, SNACKPACK = TEMPLATE[12:14]
STAGE = TEMPLATE[16]


def padded(label: str) -> str:
    return label + " " * LABEL_PADDING[label]


def template_card(
    *, day: list[str], bars: list[str], poke: str = POKE, stage: str = STAGE
) -> list[str]:
    """Her template with the day line, bars, poke hint and stage swapped in.

    The snackpack hint always names `/wisp snackpack`, as agreed with Myra.
    """
    snackpack = SNACKPACK.replace("with /snackpack", "with /wisp snackpack")
    return [
        TOP,
        TITLE_RULE,
        *day,
        GAP_ABOVE_BARS,
        *bars,
        *TEMPLATE[7:12],
        poke,
        snackpack,
        *TEMPLATE[14:16],
        stage,
        *TEMPLATE[17:],
    ]


def alive_life(**fields: object) -> Life:
    life = new_egg(3, NOW - timedelta(days=4))
    life.phase = Phase.ALIVE
    life.stage = life.peak_stage = Stage.BABY
    life.full = 50.0
    life.care = 60.0
    life.hatched_at = NOW - timedelta(days=1, hours=3)
    for name, value in fields.items():
        setattr(life, name, value)
    return life


def test_the_template_is_read_as_myra_wrote_it() -> None:
    assert len(TEMPLATE) == 20
    assert HUNGER == "▐・Hunger " + "🟦" * 5 + "│50%"
    assert DAY.startswith("▐▀━━・・𝐃𝐀𝐘 **1**・")


def test_a_living_baby_matches_myras_template() -> None:
    full = HUNGER.replace("Hunger ", padded("Full"))

    card = render_status(alive_life(), NOW, FACTS)

    assert card.split("\n") == template_card(day=[DAY], bars=[full, HAPPY, CARE])


# ---
# Bars
# ---


@pytest.mark.parametrize(
    ("value", "squares", "percent"),
    [
        (0, 0, 0),
        (4, 0, 4),
        (5, 1, 5),
        (44.5, 5, 45),
        (45, 5, 45),
        (72, 7, 72),
        (74.9, 8, 75),
        (75, 8, 75),
        (100, 10, 100),
        (-5, 0, 0),
        (140, 10, 100),
    ],
)
def test_bars_are_one_square_per_ten_percent(
    value: float, squares: int, percent: int
) -> None:
    assert bar(value, "🟦") == "🟦" * squares + f"│{percent}%"


def test_the_bars_are_full_happy_then_care_in_their_colours() -> None:
    card = render_status(alive_life(full=100.0, care=0.0), NOW, FACTS)

    assert card.split("\n")[4:7] == [
        "▐・" + padded("Full") + "🟦" * 10 + "│100%",
        "▐・" + padded("Happy") + "🟪" * 9 + "│90%",
        "▐・" + padded("Care") + "│0%",
    ]


# ---
# Facts
# ---


@pytest.mark.parametrize(
    ("fed", "words"),
    [(0, "00 people"), (1, "01 person"), (3, "03 people"), (12, "12 people")],
)
def test_fed_by_is_two_digits_and_singular_for_one(fed: int, words: str) -> None:
    card = render_status(alive_life(), NOW, replace(FACTS, fed_today=fed))

    assert f"▐▄━━❰・Fed by {words} today・♬‿♩. ♪\n" in card


@pytest.mark.parametrize(
    ("viibr", "suno", "words"),
    [
        (1, 1, "1 ViiBR track and 1 Suno track"),
        (0, 2, "0 ViiBR tracks and 2 Suno tracks"),
        (3, 1, "3 ViiBR tracks and 1 Suno track"),
    ],
)
def test_tracks_line_is_singular_for_one(viibr: int, suno: int, words: str) -> None:
    facts = replace(FACTS, viibr_tracks=viibr, suno_tracks=suno)

    card = render_status(alive_life(), NOW, facts)

    assert f"▐▀━━❰・{words}・♪‿♫ ♪\n" in card


@pytest.mark.parametrize(
    ("stage", "bold"),
    [
        (Stage.BABY, "𝐁𝐀𝐁𝐘"),
        (Stage.CHILD, "𝐂𝐇𝐈𝐋𝐃"),
        (Stage.TEEN, "𝐓𝐄𝐄𝐍"),
        (Stage.ADULT, "𝐀𝐃𝐔𝐋𝐓"),
        (Stage.ROCKSTAR, "𝐑𝐎𝐂𝐊𝐒𝐓𝐀𝐑"),
        (Stage.OLD_FOGEY, "𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘"),
    ],
)
def test_stage_is_in_bold_letters(stage: Stage, bold: str) -> None:
    card = render_status(alive_life(stage=stage), NOW, FACTS)

    assert f"▐▄━━❰・・**life stage**・{bold}・♪‿♪ ♫.\n" in card


def test_day_counts_whole_days_since_hatching() -> None:
    life = alive_life(hatched_at=NOW - timedelta(days=12, hours=23))

    card = render_status(life, NOW, FACTS)

    assert DAY.replace("**1**", "**12**") in card.split("\n")


def test_no_house_channel_says_his_house() -> None:
    card = render_status(alive_life(), NOW, replace(FACTS, house_id=None))

    expected = f"▐・Poke him or tag <@{WISP_ID}> in his House to say hi!!"
    assert expected in card.split("\n")
    assert "<#" not in card


# ---
# Eggs
# ---


def test_egg_and_hatching_cards_use_the_frame() -> None:
    egg = new_egg(4, NOW)
    egg.phase_seconds = EGG_WARMTH.total_seconds() / 4
    egg.egg_food = EGG_FOOD_NEEDED // 2
    poke = POKE.replace("Poke him", "Poke the egg")
    egg_bars = [
        "▐・" + padded("Warmth") + "🟧" * 8 + "│75%",
        "▐・" + padded("Hatching") + "🟨" * 5 + "│50%",
    ]
    egg_stage = STAGE.replace("𝐁𝐀𝐁𝐘", "𝐄𝐆𝐆")

    assert render_status(egg, NOW, FACTS).split("\n") == template_card(
        day=[], bars=egg_bars, poke=poke, stage=egg_stage
    )

    egg.phase = Phase.HATCHING
    egg.phase_seconds = HATCHING_TIME.total_seconds() / 5
    hatching_bars = ["▐・" + padded("Emerging") + "🟨" * 2 + "│20%"]
    hatching_stage = STAGE.replace("𝐁𝐀𝐁𝐘", "𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆")

    assert render_status(egg, NOW, FACTS).split("\n") == template_card(
        day=[], bars=hatching_bars, poke=poke, stage=hatching_stage
    )


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD, Phase.PASSED])
def test_finished_lives_are_not_rendered(phase: Phase) -> None:
    life = new_egg(4, NOW)
    life.phase = phase
    with pytest.raises(ValueError, match="finished"):
        render_status(life, NOW, FACTS)


# ---
# The cold
# ---


@pytest.mark.parametrize(
    ("cold_left", "hours"),
    [(48 * 3600, 48), (47 * 3600 + 1, 48), (3600, 1), (1, 1)],
)
def test_a_sick_card_says_hours_left(cold_left: float, hours: int) -> None:
    card = render_status(alive_life(cold_left=cold_left), NOW, FACTS)

    lines = card.split("\n")
    assert lines[2:4] == [DAY, f"▐・he has a cold・{hours} h left"]
    assert lines[4] == GAP_ABOVE_BARS


def test_a_well_wisp_has_no_cold_line() -> None:
    assert "cold" not in render_status(alive_life(), NOW, FACTS)


# ---
# Size
# ---


def test_the_fullest_card_fits_one_message() -> None:
    life = alive_life(
        stage=Stage.OLD_FOGEY,
        full=100.0,
        care=100.0,
        cold_left=48 * 3600,
        hatched_at=NOW - timedelta(days=9999),
    )
    facts = CardFacts(
        happiness=100,
        fed_today=99999,
        viibr_tracks=99999,
        suno_tracks=99999,
        wisp_id=2**64 - 1,
        house_id=2**64 - 1,
    )

    card = render_status(life, NOW, facts)

    assert "𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘" in card and "he has a cold" in card
    assert text_length(card) <= MESSAGE_LIMIT
