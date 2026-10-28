"""Tests for the status card text, checked against Myra's house style."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wisp.card import (
    STATUS_TITLE,
    STATUS_WIDTH,
    WAITING,
    CardFacts,
    bar,
    render_status,
)
from wisp.life import Life, Phase, new_egg
from wisp.rules import EGG_FOOD_NEEDED, EGG_WARMTH, HATCHING_TIME, Stage
from wisp.text import (
    MESSAGE_LIMIT,
    WIDTHS,
    bars,
    box_room,
    text_length,
    visual_width,
    wrap,
)

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
TOP = ["𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈 𝄇𝄡𝄚𝄚𝄚𝄚𝄂", "╔═════════════════════════╗"]
BOTTOM = ["╚═════════════════════════╝", "𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂"]
BREAK = "╠═══⇕"
BLANK = "║"
DAY = "║𝄡𝄚𝄂・・𝐃𝐀𝐘 **1**・♫ ♪. ♫‿♪"
FED = "║𝄡𝄚𝄂 Fed by 03 people today・♬‿♩. ♪"
TRACKS = ["║𝄡𝄚𝄂 6 ViiBR tracks and 2 Suno tracks", "║ ・♪‿♫ ♪"]
POKE = [f"║𝄡 Poke him or tag <@{WISP_ID}> in", f"║ <#{HOUSE_ID}> to say hi!!"]
HINTS = [
    "║𝄡 check your snackpack with /wisp",
    "║ snackpack",
    "║𝄡 check the ViiBR Vault to buy treats",
    "║ and toys for Wisp!",
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


def meters(card: str) -> list[str]:
    """The card's meter lines: from the first label to the blank line after."""
    lines = card.split("\n")
    start = lines.index(BREAK) + 1 if lines[3].startswith("║𝄡𝄚𝄂") else 3
    return lines[start : lines.index(BLANK, start)]


# ---
# The whole card
# ---


def test_a_living_baby_matches_the_house_style() -> None:
    card = render_status(alive_life(), NOW, FACTS, emoji)

    assert card.split("\n") == [
        *TOP,
        BLANK,
        DAY,
        BLANK,
        BREAK,
        "║𝄡 Care",
        f"║{pieces('care_full', 6)}{emoji('care_left')}│65%",
        "║𝄡 Happy",
        f"║{pieces('happiness_full', 9)} │90%",
        "║𝄡 Hunger",
        f"║{pieces('full_full', 5)}{emoji('full_left')}│55%",
        BLANK,
        BREAK,
        FED,
        BLANK,
        *TRACKS,
        BLANK,
        BREAK,
        *POKE,
        *HINTS,
        BLANK,
        BREAK,
        stage_line("𝐁𝐀𝐁𝐘"),
        BLANK,
        *BOTTOM,
    ]


def test_the_frame_lines_are_copied_from_the_spec() -> None:
    card = render_status(alive_life(), NOW, FACTS, emoji)

    lines = card.split("\n")
    for line in (*TOP, BREAK, *BOTTOM):
        assert line in SPEC_LINES, line
        assert line in lines, line
    assert STATUS_TITLE == "𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈"
    assert (TOP[0], BOTTOM[1]) == bars(STATUS_TITLE)


def test_the_box_is_as_wide_as_a_full_bar() -> None:
    full_bar = "║" + emoji("full_full") * 10 + "│100%"

    assert visual_width(full_bar) <= box_room(STATUS_WIDTH)
    assert visual_width(full_bar) > box_room(STATUS_WIDTH - 1)
    assert TOP[1] == "╔" + "═" * STATUS_WIDTH + "╗"


def test_the_waiting_card_has_only_its_line_in_the_frame() -> None:
    assert WAITING.split("\n") == [
        *TOP,
        BLANK,
        "║𝄡𝄚𝄂 No Wisp right now. Waiting for",
        "║ staff to begin again.",
        BLANK,
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


def test_each_bar_is_on_its_own_line_under_its_label() -> None:
    card = render_status(alive_life(), NOW, FACTS, emoji)

    labels = meters(card)[::2]
    bar_lines = meters(card)[1::2]
    assert labels == ["║𝄡 Care", "║𝄡 Happy", "║𝄡 Hunger"]
    assert all(line.startswith("║<:") for line in bar_lines)


def test_bars_without_any_emojis_keep_the_labels_and_percents() -> None:
    card = render_status(alive_life(), NOW, FACTS, no_emoji)

    assert meters(card) == [
        "║𝄡 Care",
        "║ │65%",
        "║𝄡 Happy",
        "║ │90%",
        "║𝄡 Hunger",
        "║ │55%",
    ]
    assert "<:" not in card


def test_the_bars_are_care_happy_then_hunger_in_their_meters() -> None:
    card = render_status(alive_life(full=100.0, care=0.0), NOW, FACTS, emoji)

    assert meters(card) == [
        "║𝄡 Care",
        "║ │0%",
        "║𝄡 Happy",
        f"║{pieces('happiness_full', 9)} │90%",
        "║𝄡 Hunger",
        f"║{pieces('full_full', 10)} │100%",
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

    assert wrap(f"║𝄡𝄚𝄂 Fed by {words} today・♬‿♩. ♪", STATUS_WIDTH) in card


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

    assert wrap(f"║𝄡𝄚𝄂 {words}・♪‿♫ ♪", STATUS_WIDTH) in card


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

    assert wrap(stage_line(bold), STATUS_WIDTH) in card


def test_day_counts_whole_days_since_hatching() -> None:
    life = alive_life(hatched_at=NOW - timedelta(days=12, hours=23))

    card = render_status(life, NOW, FACTS, emoji)

    assert DAY.replace("**1**", "**12**") in card.split("\n")


def test_no_house_channel_says_his_house() -> None:
    card = render_status(alive_life(), NOW, replace(FACTS, house_id=None), emoji)

    expected = f"║𝄡 Poke him or tag <@{WISP_ID}> in his House to say hi!!"
    assert wrap(expected, STATUS_WIDTH) in card
    assert "<#" not in card


# ---
# Eggs
# ---


def test_egg_and_hatching_cards_use_the_frame() -> None:
    egg = new_egg(4, NOW)
    egg.phase_seconds = EGG_WARMTH.total_seconds() / 4
    egg.egg_food = EGG_FOOD_NEEDED // 2
    poke = wrap(
        f"║𝄡 Poke the egg or tag <@{WISP_ID}> in <#{HOUSE_ID}> to say hi!!",
        STATUS_WIDTH,
    ).split("\n")
    tail = [BLANK, BREAK, FED, BLANK, *TRACKS, BLANK, BREAK, *poke, *HINTS, BLANK]

    assert render_status(egg, NOW, FACTS, emoji).split("\n") == [
        *TOP,
        BLANK,
        "║𝄡 Warmth",
        f"║{pieces('full_full', 7)}{emoji('full_left')}│75%",
        "║𝄡 Hatching",
        f"║{pieces('happiness_full', 5)} │50%",
        *tail,
        BREAK,
        stage_line("𝐄𝐆𝐆"),
        BLANK,
        *BOTTOM,
    ]

    egg.phase = Phase.HATCHING
    egg.phase_seconds = HATCHING_TIME.total_seconds() / 5

    assert render_status(egg, NOW, FACTS, emoji).split("\n") == [
        *TOP,
        BLANK,
        "║𝄡 Emerging",
        f"║{pieces('happiness_full', 2)} │20%",
        *tail,
        BREAK,
        *wrap(stage_line("𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆"), STATUS_WIDTH).split("\n"),
        BLANK,
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
    assert lines[2:7] == [
        BLANK,
        DAY,
        f"║𝄡𝄚𝄂 he has Monster Pox・{hours} h left",
        BLANK,
        BREAK,
    ]


def test_a_well_wisp_has_no_sick_line() -> None:
    assert "Monster Pox" not in render_status(alive_life(), NOW, FACTS, emoji)


# ---
# Size
# ---


def fullest_card() -> str:
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
    return render_status(life, NOW, facts, lambda name: f"<a:{name}:{2**64 - 1}>")


def test_the_fullest_card_fits_one_message() -> None:
    card = fullest_card()

    assert "𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘" in card and "Monster Pox" in card
    assert card.count("_full:") == 30
    assert text_length(card) <= MESSAGE_LIMIT


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.ALIVE])
def test_no_line_passes_the_box(phase: Phase) -> None:
    if phase is Phase.ALIVE:
        card = fullest_card()
    else:
        egg = new_egg(4, NOW)
        egg.phase = phase
        egg.egg_food = EGG_FOOD_NEEDED
        card = render_status(egg, NOW, FACTS, emoji)

    inside = card.split("\n")[2:-2]
    assert all(visual_width(line) <= box_room(STATUS_WIDTH) for line in inside)
    assert all(
        visual_width(line) <= box_room(STATUS_WIDTH)
        for line in WAITING.split("\n")[2:-2]
    )


def test_the_bars_look_as_wide_as_each_other() -> None:
    top, bottom = fullest_card().split("\n")[0], fullest_card().split("\n")[-1]

    assert abs(visual_width(top) - visual_width(bottom)) <= WIDTHS["staff"] / 2
