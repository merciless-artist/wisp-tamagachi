"""Tests for the status card text, checked against Myra's quote layout."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from wisp.card import WAITING, CardFacts, bar, render_status
from wisp.life import Life, Phase, new_egg
from wisp.rules import (
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    HANGRY_BELOW,
    HATCHING_TIME,
    HEALTH_MAX,
    LIGHTS_WINDOW,
    LONELY_BELOW,
    MESS_LEFT_FOR,
    NAP_FOR,
    SNIFFLES_FOR,
    TANTRUM_WINDOW,
    WELLBEING_MAX,
    Stage,
)
from wisp.text import MESSAGE_LIMIT, text_length

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
WISP_ID = 1560213420068966441
HOUSE_ID = 1563693152882262026
TRACKS_ID = 1563693152882262027
FACTS = CardFacts(
    fed_today=3,
    viibr_tracks=6,
    suno_tracks=2,
    wisp_id=WISP_ID,
    house_id=HOUSE_ID,
    tracks_id=TRACKS_ID,
)
HEALTH_EMOJI = "<:full_full:1564444125976068186>"
WELLBEING_EMOJI = "<:care_full:1564443602506088480>"
# Myra's card of 2026-10-31, byte for byte except that her Mood bar is gone
# (Mood folded into Wellbeing on 2026-11-06), the Right now block sits under
# the day and one line points at the buttons in place of her two hints (the
# control panel, 2026-11-06), with the real mention and House link where her
# copy shows them as Discord displays them.
MYRAS_CARD = "\n".join(
    [
        "> ",
        "> 𝄡𝄚𝄂・・𝐃𝐀𝐘 **5**・♫ ♪. ♫‿♪",
        "> ",
        "> 𝄡𝄚𝄂 **right now**",
        "> 𝄡 happy",
        "> 𝄡𝄚𝄂 next nap 18:00 UTC",
        "> ",
        "> 𝄡 Health",
        f"> {HEALTH_EMOJI * 10} │100%",
        "> 𝄡 Wellbeing",
        f"> {WELLBEING_EMOJI * 10} │100%",
        "> ",
        "> 𝄡𝄚𝄂 Fed by 02 people today・♬‿♩. ♪",
        "> ",
        "> 𝄡𝄚𝄂 1 ViiBR track and 1 Suno track ・♪‿♫ ♪",
        "> ",
        f"> 𝄡 Poke him or tag <@{WISP_ID}> in <#{HOUSE_ID}> to say hi!!",
        "> ",
        "> 𝄡 feed Wisp, shop the Vault and play",
        ">  with the buttons below!",
        "> ",
        "> ",
        "> 𝄡𝄚𝄂・・**life stage**・𝐂𝐇𝐈𝐋𝐃・♪‿♪ ♫.",
    ]
)
BLANK = "> "
RIGHT_NOW = "> 𝄡𝄚𝄂 **right now**"
NEXT_NAP = "> 𝄡𝄚𝄂 next nap 18:00 UTC"
HUNGRY = f"> 𝄡 hungry: drop a track in <#{TRACKS_ID}>"
LONELY = "> 𝄡 lonely: chat, play, poke or give him a snack or gift"
MESS = "> 𝄡 a mess is waiting in his House"
TANTRUM = "> 𝄡 he's having a tantrum in his House"
LIGHTS = "> 𝄡 he's asleep: turn the lights off in his House"
HAPPY = "> 𝄡 happy"


def stage_line(bold: str) -> str:
    return f"> 𝄡𝄚𝄂・・**life stage**・{bold}・♪‿♪ ♫."


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
    life.health = 55.0
    life.wellbeing = 65.0
    life.hatched_at = NOW - timedelta(days=1, hours=3)
    for name, value in fields.items():
        setattr(life, name, value)
    return life


def tail(poke: str, stage: str) -> list[str]:
    """The card after its bars: the facts, the hints and the stage."""
    return [
        BLANK,
        "> 𝄡𝄚𝄂 Fed by 03 people today・♬‿♩. ♪",
        BLANK,
        "> 𝄡𝄚𝄂 6 ViiBR tracks and 2 Suno tracks ・♪‿♫ ♪",
        BLANK,
        f"> 𝄡 Poke {poke} or tag <@{WISP_ID}> in <#{HOUSE_ID}> to say hi!!",
        BLANK,
        "> 𝄡 feed Wisp, shop the Vault and play",
        ">  with the buttons below!",
        BLANK,
        BLANK,
        stage_line(stage),
    ]


def right_now(card: str) -> list[str]:
    """The card's Right now items, from under its line to the next nap."""
    lines = card.split("\n")
    start = lines.index(RIGHT_NOW) + 1
    return lines[start : lines.index(NEXT_NAP, start)]


def meters(card: str) -> list[str]:
    """The card's meter lines: from the first label to the blank line after."""
    lines = card.split("\n")
    start = next(index for index, line in enumerate(lines) if line == "> 𝄡 Health")
    return lines[start : lines.index(BLANK, start)]


# ---
# The whole card
# ---


def test_the_card_is_myras_layout_byte_for_byte() -> None:
    life = alive_life(
        stage=Stage.CHILD,
        wellbeing=WELLBEING_MAX,
        health=HEALTH_MAX,
        hatched_at=NOW - timedelta(days=5, hours=1),
    )
    facts = CardFacts(2, 1, 1, WISP_ID, HOUSE_ID, TRACKS_ID)
    ids = {"full_full": HEALTH_EMOJI, "care_full": WELLBEING_EMOJI}

    card = render_status(life, NOW, facts, lambda name: ids.get(name, ""))

    assert card == MYRAS_CARD


def test_a_living_baby_has_every_line_in_its_place() -> None:
    card = render_status(alive_life(), NOW, FACTS, emoji)

    assert card.split("\n") == [
        BLANK,
        "> 𝄡𝄚𝄂・・𝐃𝐀𝐘 **1**・♫ ♪. ♫‿♪",
        BLANK,
        RIGHT_NOW,
        HAPPY,
        NEXT_NAP,
        BLANK,
        "> 𝄡 Health",
        f"> {pieces('full_full', 5)}{emoji('full_left')}│55%",
        "> 𝄡 Wellbeing",
        f"> {pieces('care_full', 6)}{emoji('care_left')}│65%",
        *tail("him", "𝐁𝐀𝐁𝐘"),
    ]


def test_every_line_is_in_the_quote() -> None:
    card = render_status(alive_life(), NOW, FACTS, emoji)

    assert all(line.startswith("> ") for line in card.split("\n"))


def test_the_waiting_card_has_only_its_line_in_the_quote() -> None:
    assert WAITING.split("\n") == [
        BLANK,
        "> 𝄡𝄚𝄂 No Wisp right now. Waiting for staff to begin again.",
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


@pytest.mark.parametrize("value", [0, 1, 4])
def test_under_5_percent_shows_no_pieces(value: float) -> None:
    assert bar(value, "F", "L") == f" │{value}%"


def test_a_left_piece_not_uploaded_leaves_the_space() -> None:
    assert bar(65, "F", "") == "FFFFFF │65%"


def test_bars_without_any_emojis_keep_the_labels_and_percents() -> None:
    card = render_status(alive_life(), NOW, FACTS, no_emoji)

    assert meters(card) == [
        "> 𝄡 Health",
        ">  │55%",
        "> 𝄡 Wellbeing",
        ">  │65%",
    ]
    assert "<:" not in card


def test_the_card_has_two_bars_health_then_wellbeing() -> None:
    life = alive_life(health=HEALTH_MAX, wellbeing=WELLBEING_MAX / 4)

    card = render_status(life, NOW, FACTS, emoji)

    assert meters(card) == [
        "> 𝄡 Health",
        f"> {pieces('full_full', 10)} │100%",
        "> 𝄡 Wellbeing",
        f"> {pieces('care_full', 2)}{emoji('care_left')}│25%",
    ]
    assert "Mood" not in card
    assert "happiness" not in card


# ---
# Facts
# ---


@pytest.mark.parametrize(
    ("fed", "words"),
    [(0, "00 people"), (1, "01 person"), (3, "03 people"), (12, "12 people")],
)
def test_fed_by_is_two_digits_and_singular_for_one(fed: int, words: str) -> None:
    card = render_status(alive_life(), NOW, replace(FACTS, fed_today=fed), emoji)

    assert f"> 𝄡𝄚𝄂 Fed by {words} today・♬‿♩. ♪" in card.split("\n")


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

    assert f"> 𝄡𝄚𝄂 {words} ・♪‿♫ ♪" in card.split("\n")


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
def test_stage_is_in_bold_letters_on_the_last_line(stage: Stage, bold: str) -> None:
    card = render_status(alive_life(stage=stage), NOW, FACTS, emoji)

    assert card.split("\n")[-1] == stage_line(bold)


def test_day_counts_whole_days_since_hatching() -> None:
    life = alive_life(hatched_at=NOW - timedelta(days=12, hours=23))

    card = render_status(life, NOW, FACTS, emoji)

    assert card.split("\n")[1] == "> 𝄡𝄚𝄂・・𝐃𝐀𝐘 **12**・♫ ♪. ♫‿♪"


def test_no_house_channel_says_his_house() -> None:
    card = render_status(alive_life(), NOW, replace(FACTS, house_id=None), emoji)

    expected = f"> 𝄡 Poke him or tag <@{WISP_ID}> in his House to say hi!!"
    assert expected in card.split("\n")
    assert "<#" not in card


# ---
# Eggs
# ---


def test_egg_and_hatching_cards_have_their_bars_after_the_first_blank() -> None:
    egg = new_egg(4, NOW)
    egg.phase_seconds = EGG_WARMTH.total_seconds() / 4
    egg.egg_food = EGG_FOOD_NEEDED // 2

    assert render_status(egg, NOW, FACTS, emoji).split("\n") == [
        BLANK,
        "> 𝄡 Warmth",
        f"> {pieces('full_full', 7)}{emoji('full_left')}│75%",
        "> 𝄡 Hatching",
        f"> {pieces('happiness_full', 5)} │50%",
        *tail("the egg", "𝐄𝐆𝐆"),
    ]

    egg.phase = Phase.HATCHING
    egg.phase_seconds = HATCHING_TIME.total_seconds() / 5

    assert render_status(egg, NOW, FACTS, emoji).split("\n") == [
        BLANK,
        "> 𝄡 Emerging",
        f"> {pieces('happiness_full', 2)} │20%",
        *tail("the egg", "𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆"),
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
def test_a_sick_card_says_hours_left_under_the_day(
    cold_left: float, hours: int
) -> None:
    card = render_status(alive_life(cold_left=cold_left), NOW, FACTS, emoji)

    assert card.split("\n")[:5] == [
        BLANK,
        "> 𝄡𝄚𝄂・・𝐃𝐀𝐘 **1**・♫ ♪. ♫‿♪",
        f"> 𝄡𝄚𝄂 he has Monster Pox・{hours} h left",
        BLANK,
        RIGHT_NOW,
    ]


def test_a_well_wisp_has_no_sick_line() -> None:
    assert "Monster Pox" not in render_status(alive_life(), NOW, FACTS, emoji)


# ---
# Cold
# ---


@pytest.mark.parametrize(
    ("sniffles_left", "hours"),
    [(129600.0, 36), (129599.0, 36), (3600.0, 1), (1.0, 1)],
)
def test_a_card_with_a_cold_says_hours_left_under_the_day(
    sniffles_left: float, hours: int
) -> None:
    card = render_status(alive_life(sniffles_left=sniffles_left), NOW, FACTS, emoji)

    assert card.split("\n")[:5] == [
        BLANK,
        "> 𝄡𝄚𝄂・・𝐃𝐀𝐘 **1**・♫ ♪. ♫‿♪",
        f"> 𝄡𝄚𝄂 he has a cold・{hours} h left",
        BLANK,
        RIGHT_NOW,
    ]


def test_a_well_wisp_has_no_cold_line() -> None:
    assert "a cold" not in render_status(alive_life(), NOW, FACTS, emoji)


def test_a_wisp_with_the_pox_and_a_cold_shows_both_lines() -> None:
    life = alive_life(cold_left=3600.0, sniffles_left=7200.0)

    lines = render_status(life, NOW, FACTS, emoji).split("\n")

    assert lines[2:4] == [
        "> 𝄡𝄚𝄂 he has Monster Pox・1 h left",
        "> 𝄡𝄚𝄂 he has a cold・2 h left",
    ]


# ---
# Right now
# ---


@pytest.mark.parametrize(
    ("fields", "needs"),
    [
        ({}, [HAPPY]),
        ({"health": HANGRY_BELOW - 0.1}, [HUNGRY]),
        ({"health": HANGRY_BELOW}, [HAPPY]),
        ({"wellbeing": LONELY_BELOW - 0.1}, [LONELY]),
        ({"wellbeing": LONELY_BELOW}, [HAPPY]),
        ({"mess_left": MESS_LEFT_FOR.total_seconds()}, [MESS]),
        ({"mess_in": 60.0, "mess_gap": 60.0}, [HAPPY]),
        ({"tantrum_left": TANTRUM_WINDOW.total_seconds()}, [TANTRUM]),
        (
            {
                "nap_left": NAP_FOR.total_seconds(),
                "lights_left": LIGHTS_WINDOW.total_seconds(),
            },
            [LIGHTS],
        ),
        ({"nap_left": NAP_FOR.total_seconds()}, [HAPPY]),
    ],
)
def test_right_now_says_what_he_needs(
    fields: dict[str, float], needs: list[str]
) -> None:
    card = render_status(alive_life(**fields), NOW, FACTS, emoji)

    assert right_now(card) == needs


def test_right_now_lists_everything_he_needs_worst_first() -> None:
    life = alive_life(
        health=5.0,
        wellbeing=5.0,
        mess_left=60.0,
        tantrum_left=60.0,
        nap_left=60.0,
        lights_left=60.0,
    )

    card = render_status(life, NOW, FACTS, emoji)

    assert right_now(card) == [HUNGRY, LONELY, MESS, TANTRUM, LIGHTS]


def test_right_now_without_a_track_drop_names_it_in_words() -> None:
    life = alive_life(health=5.0)

    card = render_status(life, NOW, replace(FACTS, tracks_id=None), emoji)

    assert right_now(card) == ["> 𝄡 hungry: drop a track in the track drop"]


def test_the_right_now_block_sits_under_the_day_and_any_sickness() -> None:
    life = alive_life(cold_left=3600.0, sniffles_left=7200.0, health=5.0)

    lines = render_status(life, NOW, FACTS, emoji).split("\n")

    assert lines[:9] == [
        BLANK,
        "> 𝄡𝄚𝄂・・𝐃𝐀𝐘 **1**・♫ ♪. ♫‿♪",
        "> 𝄡𝄚𝄂 he has Monster Pox・1 h left",
        "> 𝄡𝄚𝄂 he has a cold・2 h left",
        BLANK,
        RIGHT_NOW,
        HUNGRY,
        NEXT_NAP,
        BLANK,
    ]


@pytest.mark.parametrize(
    ("now", "nap"),
    [
        (datetime(2026, 10, 20, 0, 0, tzinfo=UTC), "02:00"),
        (datetime(2026, 10, 20, 2, 0, tzinfo=UTC), "10:00"),
        (datetime(2026, 10, 20, 12, 0, tzinfo=UTC), "18:00"),
        (datetime(2026, 10, 20, 23, 59, tzinfo=UTC), "02:00"),
    ],
)
def test_the_card_says_when_his_next_nap_is(now: datetime, nap: str) -> None:
    card = render_status(alive_life(hatched_at=now), now, FACTS, emoji)

    assert f"> 𝄡𝄚𝄂 next nap {nap} UTC" in card.split("\n")


def test_eggs_have_no_right_now_or_next_nap() -> None:
    card = render_status(new_egg(4, NOW), NOW, FACTS, emoji)

    assert "right now" not in card
    assert "next nap" not in card


# ---
# Size
# ---


LONGEST_ID = 2**64 - 1
LONGEST_FACTS = CardFacts(
    fed_today=99999,
    viibr_tracks=99999,
    suno_tracks=99999,
    wisp_id=LONGEST_ID,
    house_id=LONGEST_ID,
    tracks_id=LONGEST_ID,
)


def longest_emoji(name: str) -> str:
    return f"<a:{name}:{LONGEST_ID}>"


def test_the_fullest_card_fits_one_message() -> None:
    life = alive_life(
        stage=Stage.OLD_FOGEY,
        health=100.0,
        wellbeing=100.0,
        cold_left=48 * 3600,
        sniffles_left=SNIFFLES_FOR.total_seconds(),
        hatched_at=NOW - timedelta(days=9999),
        mess_left=60.0,
        tantrum_left=60.0,
        nap_left=60.0,
        lights_left=60.0,
    )

    card = render_status(life, NOW, LONGEST_FACTS, longest_emoji)

    assert "𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘" in card and "Monster Pox" in card
    assert "a cold" in card
    assert card.count("_full:") == 20
    assert right_now(card) == [MESS, TANTRUM, LIGHTS]
    assert text_length(card) <= MESSAGE_LIMIT


def test_a_sick_card_needing_everything_fits_one_message() -> None:
    life = alive_life(
        stage=Stage.OLD_FOGEY,
        health=HANGRY_BELOW - 0.1,
        wellbeing=LONELY_BELOW - 0.1,
        cold_left=48 * 3600,
        sniffles_left=SNIFFLES_FOR.total_seconds(),
        hatched_at=NOW - timedelta(days=9999),
        mess_left=60.0,
        tantrum_left=60.0,
        nap_left=60.0,
        lights_left=60.0,
    )

    card = render_status(life, NOW, LONGEST_FACTS, longest_emoji)

    assert "Monster Pox" in card and "a cold" in card
    assert right_now(card) == [
        f"> 𝄡 hungry: drop a track in <#{LONGEST_ID}>",
        LONELY,
        MESS,
        TANTRUM,
        LIGHTS,
    ]
    assert text_length(card) <= MESSAGE_LIMIT
