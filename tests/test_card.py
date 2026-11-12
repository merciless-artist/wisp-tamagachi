"""Tests for the status card text, in Myra's emoji frame (house style v3)."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tests.layout import rows
from wisp.card import CardFacts, bar, render_status, waiting
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
from wisp.text import (
    FRAME_EMOJIS,
    LAYOUT_TEXT_LIMIT,
    UNICODE_FRAME,
    Frame,
    emoji_frame,
    round_half_up,
    text_length,
    timestamp,
)


def october(day: int, hour: int, minute: int = 0) -> datetime:
    """That UTC moment in October 2026."""
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


NOW = october(20, 12)
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
# Most cards are checked in the Unicode fallback frame; one is in her emoji frame.
FRAME = UNICODE_FRAME
EMOJI_FRAME = emoji_frame(
    *(f"<:{name}:{index}>" for index, name in enumerate(FRAME_EMOJIS, start=1))
)
BLANK = FRAME.blank
RIGHT_NOW = FRAME.heading("Right now")
# NOW is 5am Pacific, so his next nap is 7am Pacific.
NEXT_NAP_TEXT = f"next nap {timestamp(october(20, 14))}"
NEXT_NAP = FRAME.sub(NEXT_NAP_TEXT)


def need(text: str) -> str:
    """A Right now item as the card shows it, wrapped to fit the frame."""
    return FRAME.wrap(FRAME.item(text))


HUNGRY = need(f"hungry: drop a track in <#{TRACKS_ID}>")
LONELY = need("lonely: chat, play, poke or give him a snack or gift")
MESS = need("a mess is waiting in his House")
TANTRUM = need("he's having a tantrum in his House")
LIGHTS = need("he's asleep: turn the lights off in his House")
HAPPY = need("happy")


def pox_need(track_drop: str) -> str:
    return need(
        f"Monster Pox: feed him tracks in {track_drop}: every meal gets him "
        "better faster"
    )


POX = pox_need(f"<#{TRACKS_ID}>")


def stage_line(stage: str, frame: Frame = FRAME) -> str:
    return frame.wrap(frame.heading(f"Life stage ・ {stage}"))


def render(life: Life, emojis: Callable[[str], str] | None = None) -> str:
    """The card in the Unicode frame, with `emoji` unless other emojis are given."""
    return render_status(life, NOW, FACTS, emojis or emoji, FRAME)


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


def tail(
    poke: str, stage: str, facts: CardFacts = FACTS, frame: Frame = FRAME
) -> list[str]:
    """The card after its bars: the facts, the hints, the stage and the end."""
    people = "person" if facts.fed_today == 1 else "people"
    viibr = "track" if facts.viibr_tracks == 1 else "tracks"
    suno = "track" if facts.suno_tracks == 1 else "tracks"
    return rows(
        frame,
        frame.blank,
        frame.sub(f"Fed by {facts.fed_today:02d} {people} today"),
        frame.blank,
        frame.sub(
            f"{facts.viibr_tracks} ViiBR {viibr} and {facts.suno_tracks} Suno {suno}"
        ),
        frame.blank,
        frame.item(f"Poke {poke} or tag <@{WISP_ID}> in <#{HOUSE_ID}> to say hi!!"),
        frame.blank,
        frame.item("feed Wisp, shop the Vault and play with the buttons below!"),
        frame.blank,
        frame.blank,
        stage_line(stage, frame),
        frame.blank,
        frame.bottom,
    )


def right_now(card: str) -> list[str]:
    """The card's Right now items, each wrapped item one entry, up to the nap line."""
    lines = card.split("\n")
    start = lines.index(RIGHT_NOW) + 1
    end = next(
        index
        for index in range(start, len(lines))
        if lines[index].startswith(FRAME.sub_mark)
    )
    items: list[str] = []
    for line in lines[start:end]:
        if line.startswith(FRAME.continuation) and items:
            items[-1] += "\n" + line
        else:
            items.append(line)
    return [FRAME.wrap(need) for need in items]


def meters(card: str) -> list[str]:
    """The card's meter lines: from the first label to the blank line after."""
    lines = card.split("\n")
    start = lines.index(FRAME.item("Health"))
    return lines[start : lines.index(BLANK, start)]


# ---
# The whole card
# ---


def test_the_card_is_myras_layout_in_her_emoji_frame() -> None:
    life = alive_life(
        stage=Stage.CHILD,
        wellbeing=WELLBEING_MAX,
        health=HEALTH_MAX,
        hatched_at=NOW - timedelta(days=5, hours=1),
    )
    facts = CardFacts(2, 1, 1, WISP_ID, HOUSE_ID, TRACKS_ID)
    ids = {"full_full": HEALTH_EMOJI, "care_full": WELLBEING_EMOJI}
    frame = EMOJI_FRAME

    card = render_status(life, NOW, facts, lambda name: ids.get(name, ""), frame)

    assert card.split("\n") == [
        *rows(
            frame,
            frame.heading("Day 5 ・ ♫ ♪. ♫‿♪"),
            frame.blank,
            frame.heading("Right now"),
            frame.item("happy"),
            frame.sub(NEXT_NAP_TEXT),
            frame.blank,
            frame.item("Health"),
        ),
        f"{HEALTH_EMOJI * 10} 100%",
        frame.item("Wellbeing"),
        f"{WELLBEING_EMOJI * 10} 100%",
        *tail("him", "CHILD", facts, frame),
    ]
    assert not any(mark in card for mark in "║╠═╚│𝄡𝄚𝄂𝄆")
    assert not any(line.startswith(">") for line in card.split("\n"))
    assert "𝐂" not in card


def test_a_living_baby_has_every_line_in_its_place() -> None:
    card = render(alive_life())

    assert card.split("\n") == [
        FRAME.heading("Day 1 ・ ♫ ♪. ♫‿♪"),
        BLANK,
        RIGHT_NOW,
        HAPPY,
        NEXT_NAP,
        BLANK,
        FRAME.item("Health"),
        f"{pieces('full_full', 5)}{emoji('full_left')} 55%",
        FRAME.item("Wellbeing"),
        f"{pieces('care_full', 6)}{emoji('care_left')} 65%",
        *tail("him", "BABY"),
    ]


def test_every_line_but_the_bars_is_in_the_frame() -> None:
    lines = render(alive_life()).split("\n")

    assert lines[-1] == FRAME.bottom
    framed = [line for line in lines[:-1] if not line.startswith("<:")]
    assert len(framed) == len(lines) - 3
    assert all(line.startswith(FRAME.blank) for line in framed)


def test_the_waiting_card_has_only_its_line_in_the_frame() -> None:
    assert waiting(FRAME).split("\n") == [
        FRAME.sub("No Wisp right now. Waiting for staff to begin again."),
        FRAME.blank,
        FRAME.bottom,
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
    pieces = "F" * full + ("L" if left else "")

    assert bar(value, "F", "L") == (f"{pieces} {percent}%" if pieces else f"{percent}%")


@pytest.mark.parametrize("value", [0, 1, 4])
def test_under_5_percent_shows_no_pieces(value: float) -> None:
    assert bar(value, "F", "L") == f"{value}%"


def test_a_left_piece_not_uploaded_is_left_out() -> None:
    assert bar(65, "F", "") == "FFFFFF 65%"


def test_bars_without_any_emojis_keep_the_labels_and_percents() -> None:
    card = render(alive_life(), emojis=no_emoji)

    assert meters(card) == [FRAME.item("Health"), "55%", FRAME.item("Wellbeing"), "65%"]
    assert "<:" not in card


def test_the_card_has_two_bars_health_then_wellbeing() -> None:
    life = alive_life(health=HEALTH_MAX, wellbeing=WELLBEING_MAX / 4)

    card = render_status(life, NOW, FACTS, emoji, FRAME)

    assert meters(card) == [
        FRAME.item("Health"),
        f"{pieces('full_full', 10)} 100%",
        FRAME.item("Wellbeing"),
        f"{pieces('care_full', 2)}{emoji('care_left')} 25%",
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
    card = render_status(alive_life(), NOW, replace(FACTS, fed_today=fed), emoji, FRAME)

    assert FRAME.wrap(FRAME.sub(f"Fed by {words} today")) in card


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

    card = render_status(alive_life(), NOW, facts, emoji, FRAME)

    assert FRAME.wrap(FRAME.sub(words)) in card


@pytest.mark.parametrize(
    ("stage", "word"),
    [
        (Stage.BABY, "BABY"),
        (Stage.CHILD, "CHILD"),
        (Stage.TEEN, "TEEN"),
        (Stage.ADULT, "ADULT"),
        (Stage.ROCKSTAR, "ROCKSTAR"),
        (Stage.OLD_FOGEY, "OLD FOGEY"),
    ],
)
def test_stage_is_in_capitals_just_above_the_end(stage: Stage, word: str) -> None:
    card = render(alive_life(stage=stage))

    assert card.endswith("\n".join([stage_line(word), BLANK, FRAME.bottom]))


def test_day_counts_whole_days_since_hatching() -> None:
    life = alive_life(hatched_at=NOW - timedelta(days=12, hours=23))

    card = render_status(life, NOW, FACTS, emoji, FRAME)

    assert card.split("\n")[0] == FRAME.heading("Day 12 ・ ♫ ♪. ♫‿♪")


def test_no_house_channel_says_his_house() -> None:
    card = render_status(alive_life(), NOW, replace(FACTS, house_id=None), emoji, FRAME)

    expected = FRAME.item(f"Poke him or tag <@{WISP_ID}> in his House to say hi!!")
    assert FRAME.wrap(expected) in card
    assert "<#" not in card


# ---
# Eggs
# ---


def test_egg_and_hatching_cards_open_with_their_bars() -> None:
    egg = new_egg(4, NOW)
    egg.phase_seconds = EGG_WARMTH.total_seconds() / 4
    egg.egg_food = EGG_FOOD_NEEDED // 2

    assert render(egg).split("\n") == [
        FRAME.item("Warmth"),
        f"{pieces('full_full', 7)}{emoji('full_left')} 75%",
        FRAME.item("Hatching"),
        f"{pieces('happiness_full', 5)} 50%",
        *tail("the egg", "EGG"),
    ]

    egg.phase = Phase.HATCHING
    egg.phase_seconds = HATCHING_TIME.total_seconds() / 5

    assert render(egg).split("\n") == [
        FRAME.item("Emerging"),
        f"{pieces('happiness_full', 2)} 20%",
        *tail("the egg", "HATCHING"),
    ]


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD, Phase.PASSED])
def test_finished_lives_are_not_rendered(phase: Phase) -> None:
    life = new_egg(4, NOW)
    life.phase = phase
    with pytest.raises(ValueError, match="finished"):
        render_status(life, NOW, FACTS, emoji, FRAME)


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
    card = render_status(alive_life(cold_left=cold_left), NOW, FACTS, emoji, FRAME)

    assert card.startswith(
        "\n".join(
            rows(
                FRAME,
                FRAME.heading("Day 1 ・ ♫ ♪. ♫‿♪"),
                FRAME.sub(f"he has Monster Pox ・ {hours} h left"),
                BLANK,
                RIGHT_NOW,
            )
        )
    )


def test_a_well_wisp_has_no_sick_line() -> None:
    assert "Monster Pox" not in render_status(alive_life(), NOW, FACTS, emoji, FRAME)


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
    card = render_status(
        alive_life(sniffles_left=sniffles_left), NOW, FACTS, emoji, FRAME
    )

    assert card.startswith(
        "\n".join(
            rows(
                FRAME,
                FRAME.heading("Day 1 ・ ♫ ♪. ♫‿♪"),
                FRAME.sub(f"he has a cold ・ {hours} h left"),
                BLANK,
                RIGHT_NOW,
            )
        )
    )


def test_a_well_wisp_has_no_cold_line() -> None:
    assert "a cold" not in render_status(alive_life(), NOW, FACTS, emoji, FRAME)


def test_a_wisp_with_the_pox_and_a_cold_shows_both_lines() -> None:
    life = alive_life(cold_left=3600.0, sniffles_left=7200.0)

    lines = render_status(life, NOW, FACTS, emoji, FRAME).split("\n")

    assert lines[1:3] == [
        FRAME.sub("he has Monster Pox ・ 1 h left"),
        FRAME.sub("he has a cold ・ 2 h left"),
    ]


# ---
# Right now
# ---


@pytest.mark.parametrize(
    ("fields", "needs"),
    [
        ({}, [HAPPY]),
        ({"health": HANGRY_BELOW - 1}, [HUNGRY]),
        ({"health": HANGRY_BELOW}, [HAPPY]),
        ({"wellbeing": LONELY_BELOW - 1}, [LONELY]),
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
    card = render_status(alive_life(**fields), NOW, FACTS, emoji, FRAME)

    assert right_now(card) == needs


@pytest.mark.parametrize(
    ("meter", "line", "need"),
    [
        ("Health", HANGRY_BELOW, HUNGRY),
        ("Wellbeing", LONELY_BELOW, LONELY),
    ],
)
@pytest.mark.parametrize(
    ("below", "needed"),
    [(0.1, False), (0.5, False), (0.6, True)],
)
def test_right_now_agrees_with_the_percent_the_bar_shows(
    meter: str, line: float, need: str, below: float, needed: bool
) -> None:
    life = alive_life(**{meter.lower(): line - below})

    card = render_status(life, NOW, FACTS, emoji, FRAME)

    shown = round_half_up(line) - (1 if needed else 0)
    label = meters(card).index(FRAME.item(meter))
    assert meters(card)[label + 1].endswith(f" {shown}%")
    assert right_now(card) == ([need] if needed else [HAPPY])


def test_right_now_lists_everything_he_needs_worst_first() -> None:
    life = alive_life(
        health=5.0,
        wellbeing=5.0,
        mess_left=60.0,
        tantrum_left=60.0,
        nap_left=60.0,
        lights_left=60.0,
    )

    card = render_status(life, NOW, FACTS, emoji, FRAME)

    assert right_now(card) == [HUNGRY, LONELY, MESS, TANTRUM, LIGHTS]


@pytest.mark.parametrize("health", [100.0, 5.0])
def test_with_monster_pox_right_now_says_feeding_gets_him_better(
    health: float,
) -> None:
    life = alive_life(cold_left=3600.0, health=health)

    card = render_status(life, NOW, FACTS, emoji, FRAME)

    assert right_now(card) == [POX]


def test_a_cold_alone_keeps_the_hungry_line() -> None:
    life = alive_life(sniffles_left=3600.0, health=5.0)

    assert right_now(render_status(life, NOW, FACTS, emoji, FRAME)) == [HUNGRY]


def test_the_pox_line_without_a_track_drop_names_it_in_words() -> None:
    life = alive_life(cold_left=3600.0)

    card = render_status(life, NOW, replace(FACTS, tracks_id=None), emoji, FRAME)

    assert right_now(card) == [pox_need("the track drop")]


def test_right_now_without_a_track_drop_names_it_in_words() -> None:
    life = alive_life(health=5.0)

    card = render_status(life, NOW, replace(FACTS, tracks_id=None), emoji, FRAME)

    assert right_now(card) == [need("hungry: drop a track in the track drop")]


def test_the_right_now_block_sits_under_the_day_and_any_sickness() -> None:
    life = alive_life(cold_left=3600.0, sniffles_left=7200.0, health=5.0)

    lines = render_status(life, NOW, FACTS, emoji, FRAME).split("\n")

    assert lines[: 8 + POX.count("\n")] == [
        FRAME.heading("Day 1 ・ ♫ ♪. ♫‿♪"),
        FRAME.sub("he has Monster Pox ・ 1 h left"),
        FRAME.sub("he has a cold ・ 2 h left"),
        BLANK,
        RIGHT_NOW,
        *FRAME.wrap(POX).split("\n"),
        NEXT_NAP,
        BLANK,
    ]


@pytest.mark.parametrize(
    ("now", "nap"),
    [
        # 10pm, 7am, 7am, 1pm and 10pm Pacific.
        (october(20, 0), october(20, 5)),
        (october(20, 5), october(20, 14)),
        (october(20, 12), october(20, 14)),
        (october(20, 14), october(20, 20)),
        (october(20, 23, 59), october(21, 5)),
    ],
)
def test_the_card_says_when_his_next_nap_is(now: datetime, nap: datetime) -> None:
    card = render_status(alive_life(hatched_at=now), now, FACTS, emoji, FRAME)

    assert FRAME.sub(f"next nap {timestamp(nap)}") in card.split("\n")


@pytest.mark.parametrize(
    ("nap_left", "until"),
    [
        # 6am and 5:02am Pacific: 90 seconds left rounds up to the minute.
        (NAP_FOR.total_seconds(), october(20, 13)),
        (90.0, october(20, 12, 2)),
    ],
)
def test_while_he_naps_the_card_says_when_he_wakes(
    nap_left: float, until: datetime
) -> None:
    card = render_status(alive_life(nap_left=nap_left), NOW, FACTS, emoji, FRAME)

    lines = card.split("\n")
    start = lines.index(RIGHT_NOW)
    assert lines[start : start + 3] == [
        RIGHT_NOW,
        HAPPY,
        FRAME.sub(f"napping until {timestamp(until)}"),
    ]
    assert not any("next nap" in line for line in lines)


def test_eggs_have_no_right_now_or_next_nap() -> None:
    card = render_status(new_egg(4, NOW), NOW, FACTS, emoji, FRAME)

    assert "RIGHT NOW" not in card
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

    card = render_status(life, NOW, LONGEST_FACTS, longest_emoji, FRAME)

    assert "OLD FOGEY" in card and "Monster Pox" in card
    assert "a cold" in card
    assert card.count("_full:") == 20
    assert right_now(card) == [pox_need(f"<#{LONGEST_ID}>"), MESS, TANTRUM, LIGHTS]
    assert text_length(card) <= LAYOUT_TEXT_LIMIT


def test_a_sick_card_needing_everything_fits_one_message() -> None:
    life = alive_life(
        stage=Stage.OLD_FOGEY,
        health=HANGRY_BELOW - 1,
        wellbeing=LONELY_BELOW - 1,
        cold_left=48 * 3600,
        sniffles_left=SNIFFLES_FOR.total_seconds(),
        hatched_at=NOW - timedelta(days=9999),
        mess_left=60.0,
        tantrum_left=60.0,
        nap_left=60.0,
        lights_left=60.0,
    )

    card = render_status(life, NOW, LONGEST_FACTS, longest_emoji, FRAME)

    assert "Monster Pox" in card and "a cold" in card
    assert right_now(card) == [
        pox_need(f"<#{LONGEST_ID}>"),
        LONELY,
        MESS,
        TANTRUM,
        LIGHTS,
    ]
    assert text_length(card) <= LAYOUT_TEXT_LIMIT
