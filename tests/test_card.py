"""Tests for the status card text, checked against Myra's house style."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wisp.card import (
    LABEL_PADDING,
    STATUS_TITLE,
    WAITING,
    CardFacts,
    bar,
    render_status,
)
from wisp.life import Life, Phase, new_egg
from wisp.rules import EGG_FOOD_NEEDED, EGG_WARMTH, HATCHING_TIME, Stage
from wisp.text import MESSAGE_LIMIT, text_length

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
SPEC_LINES = frozenset(
    (Path(__file__).parent.parent / "DOCS" / "specs" / "2026-10-27-house-style.md")
    .read_bytes()
    .decode("utf-8")
    .splitlines()
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
TOP = ["𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈 𝄇𝄡𝄚𝄚𝄚𝄚𝄂", "╔════════════════════╗"]
BOTTOM = ["╚════════════════════╝", "𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂"]
BREAK = "╠═══⇕"
DAY = "║𝄡𝄚𝄂・・𝐃𝐀𝐘 **1**・♫ ♪. ♫‿♪"
FED = "║𝄡𝄚𝄂 Fed by 03 people today・♬‿♩. ♪"
TRACKS = "║𝄡𝄚𝄂 6 ViiBR tracks and 2 Suno tracks・♪‿♫ ♪"
POKE = f"║𝄡 Poke him or tag <@{WISP_ID}> in <#{HOUSE_ID}> to say hi!!"
HINTS = [
    "║𝄡 check your snackpack with /wisp snackpack",
    "║𝄡 check the ViiBR Vault to buy treats and toys for Wisp!",
]


def stage_line(bold: str) -> str:
    return f"║𝄡𝄚𝄂・・**life stage**・{bold}・♪‿♪ ♫."


def emoji(name: str) -> str:
    return f"<:{name}:9>"


def no_emoji(_name: str) -> str:
    return ""


def pieces(name: str, count: int) -> str:
    return emoji(name) * count


def alive_life(**fields: object) -> Life:
    life = new_egg(3, NOW - timedelta(days=4))
    life.phase = Phase.ALIVE
    life.stage = life.peak_stage = Stage.BABY
    life.full = 55.0
    life.care = 65.0
    life.hatched_at = NOW - timedelta(days=1, hours=3)
    for name, value in fields.items():
        setattr(life, name, value)
    return life


# ---
# The whole card
# ---


def test_a_living_baby_matches_the_house_style() -> None:
    card = render_status(alive_life(), NOW, FACTS, emoji)

    assert card.split("\n") == [
        *TOP,
        DAY,
        BREAK,
        f"║𝄡 Care      {pieces('care_full', 6)}{emoji('care_left')}│65%",
        f"║𝄡 Happy   {pieces('happiness_full', 9)} │90%",
        f"║𝄡 Hunger {pieces('full_full', 5)}{emoji('full_left')}│55%",
        BREAK,
        FED,
        TRACKS,
        BREAK,
        POKE,
        *HINTS,
        BREAK,
        stage_line("𝐁𝐀𝐁𝐘"),
        *BOTTOM,
    ]


def test_the_fixed_lines_are_copied_from_the_spec() -> None:
    card = render_status(alive_life(), NOW, FACTS, emoji)

    lines = card.split("\n")
    for line in (*TOP, BREAK, *HINTS, *BOTTOM):
        assert line in SPEC_LINES, line
        assert line in lines, line
    assert STATUS_TITLE == "𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈"


def test_the_label_padding_is_myras() -> None:
    assert {label: LABEL_PADDING[label] for label in ("Care", "Happy", "Hunger")} == {
        "Care": 6,
        "Happy": 3,
        "Hunger": 1,
    }


def test_the_waiting_card_has_only_its_line_in_the_frame() -> None:
    assert WAITING.split("\n") == [
        *TOP,
        "║𝄡𝄚𝄂 No Wisp right now. Waiting for staff to begin again.",
        *BOTTOM,
    ]


# ---
# Bars
# ---


@pytest.mark.parametrize(
    ("value", "full", "left", "percent"),
    [
        (0, 0, False, 0),
        (4, 0, False, 4),
        (4.4, 0, False, 4),
        (4.5, 0, True, 5),
        (5, 0, True, 5),
        (44.5, 4, True, 45),
        (55, 5, True, 55),
        (65, 6, True, 65),
        (69, 6, True, 69),
        (72, 7, False, 72),
        (90, 9, False, 90),
        (94.9, 9, True, 95),
        (100, 10, False, 100),
        (-5, 0, False, 0),
        (140, 10, False, 100),
    ],
)
def test_bars_are_a_full_piece_per_ten_and_a_left_piece_for_five(
    value: float, full: int, left: bool, percent: int
) -> None:
    end = "L" if left else " "

    assert bar(value, "F", "L") == "F" * full + end + f"│{percent}%"


def test_65_percent_is_six_full_and_a_left() -> None:
    assert bar(65, "F", "L") == "FFFFFFL│65%"


def test_90_percent_is_nine_full_and_a_space() -> None:
    assert bar(90, "F", "L") == "FFFFFFFFF │90%"


@pytest.mark.parametrize("value", [0, 1, 4])
def test_under_5_percent_shows_no_pieces(value: float) -> None:
    assert bar(value, "F", "L") == f" │{value}%"


def test_a_left_piece_not_uploaded_leaves_the_space() -> None:
    assert bar(65, "F", "") == "FFFFFF │65%"


def test_bars_without_any_emojis_keep_the_labels_and_percents() -> None:
    card = render_status(alive_life(), NOW, FACTS, no_emoji)

    assert card.split("\n")[4:7] == [
        "║𝄡 Care       │65%",
        "║𝄡 Happy    │90%",
        "║𝄡 Hunger  │55%",
    ]
    assert "<:" not in card


def test_the_bars_are_care_happy_then_hunger_in_their_meters() -> None:
    card = render_status(alive_life(full=100.0, care=0.0), NOW, FACTS, emoji)

    assert card.split("\n")[4:7] == [
        "║𝄡 Care       │0%",
        f"║𝄡 Happy   {pieces('happiness_full', 9)} │90%",
        f"║𝄡 Hunger {pieces('full_full', 10)} │100%",
    ]


# ---
# Facts
# ---


@pytest.mark.parametrize(
    ("fed", "words"),
    [(0, "00 people"), (1, "01 person"), (3, "03 people"), (12, "12 people")],
)
def test_fed_by_is_two_digits_and_singular_for_one(fed: int, words: str) -> None:
    card = render_status(alive_life(), NOW, replace(FACTS, fed_today=fed), emoji)

    assert f"║𝄡𝄚𝄂 Fed by {words} today・♬‿♩. ♪" in card.split("\n")


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

    card = render_status(alive_life(), NOW, facts, emoji)

    assert f"║𝄡𝄚𝄂 {words}・♪‿♫ ♪" in card.split("\n")


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
    card = render_status(alive_life(stage=stage), NOW, FACTS, emoji)

    assert stage_line(bold) in card.split("\n")


def test_day_counts_whole_days_since_hatching() -> None:
    life = alive_life(hatched_at=NOW - timedelta(days=12, hours=23))

    card = render_status(life, NOW, FACTS, emoji)

    assert DAY.replace("**1**", "**12**") in card.split("\n")


def test_no_house_channel_says_his_house() -> None:
    card = render_status(alive_life(), NOW, replace(FACTS, house_id=None), emoji)

    expected = f"║𝄡 Poke him or tag <@{WISP_ID}> in his House to say hi!!"
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
    tail = [BREAK, FED, TRACKS, BREAK, poke, *HINTS, BREAK]

    assert render_status(egg, NOW, FACTS, emoji).split("\n") == [
        *TOP,
        f"║𝄡 Warmth   {pieces('full_full', 7)}{emoji('full_left')}│75%",
        f"║𝄡 Hatching {pieces('happiness_full', 5)} │50%",
        *tail,
        stage_line("𝐄𝐆𝐆"),
        *BOTTOM,
    ]

    egg.phase = Phase.HATCHING
    egg.phase_seconds = HATCHING_TIME.total_seconds() / 5

    assert render_status(egg, NOW, FACTS, emoji).split("\n") == [
        *TOP,
        f"║𝄡 Emerging {pieces('happiness_full', 2)} │20%",
        *tail,
        stage_line("𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆"),
        *BOTTOM,
    ]


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD, Phase.PASSED])
def test_finished_lives_are_not_rendered(phase: Phase) -> None:
    life = new_egg(4, NOW)
    life.phase = phase
    with pytest.raises(ValueError, match="finished"):
        render_status(life, NOW, FACTS, emoji)


# ---
# Sickness
# ---


@pytest.mark.parametrize(
    ("cold_left", "hours"),
    [(48 * 3600, 48), (47 * 3600 + 1, 48), (3600, 1), (1, 1)],
)
def test_a_sick_card_says_hours_left(cold_left: float, hours: int) -> None:
    card = render_status(alive_life(cold_left=cold_left), NOW, FACTS, emoji)

    lines = card.split("\n")
    assert lines[2:5] == [DAY, f"║𝄡𝄚𝄂 he has Monster Pox・{hours} h left", BREAK]


def test_a_well_wisp_has_no_sick_line() -> None:
    assert "Monster Pox" not in render_status(alive_life(), NOW, FACTS, emoji)


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

    card = render_status(life, NOW, facts, lambda name: f"<a:{name}:{2**64 - 1}>")

    assert "𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘" in card and "Monster Pox" in card
    assert card.count("_full:") == 30
    assert text_length(card) <= MESSAGE_LIMIT
