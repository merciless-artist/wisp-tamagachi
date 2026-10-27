"""Tests for Wisp's lines and the shuffle-bag line picker."""

import random
import re
import unicodedata
from collections.abc import MutableSequence
from string import Formatter
from typing import Any

import pytest

from wisp.life import Mood
from wisp.lines import FIELDS, LINES, LinePicker, Moment, lines_for
from wisp.rules import Stage

SAMPLE_FIELDS = {
    "name": "Myra",
    "version": "4",
    "stage": "teen",
    "word": "fire",
    "gift": "Blue Alien Doll",
    "collection": "Alien Dolls",
}
LONGEST_FIELDS = {
    "name": "W" * 32,
    "version": "9999",
    "stage": "rockstar",
    "word": "w" * 40,
    "gift": "Future Is Bright Affirmation Card",
    "collection": "Affirmation Cards",
}
ONE_MOOD_MOMENTS = {
    Moment.HUNGRY,
    Moment.FADING,
    Moment.DIED,
    Moment.NEW_EGG,
    Moment.EGG_COLD,
    Moment.HATCH_STARTED,
    Moment.HATCHED,
    Moment.BANNED,
    Moment.NOT_ENOUGH_POINTS,
    Moment.GREW_OLD,
    Moment.FAREWELL,
    Moment.COAL_EGG,
    Moment.LAST_EMBER,
    Moment.EGG_POKE,
    Moment.KEEPSAKE_WON,
    Moment.LONELY,
    Moment.SICK,
    Moment.RECOVERED,
}
LONELY_TALK_MOMENTS = [Moment.POKED, Moment.CHAT_FALLBACK, Moment.BABY_TALK]
FAREWELL_MOMENTS = [
    Moment.GREW_OLD,
    Moment.FAREWELL,
    Moment.COAL_EGG,
    Moment.LAST_EMBER,
]
ALL_KEYS = sorted(LINES)
GROWN_STAGES = [Stage.CHILD, Stage.TEEN, Stage.ADULT, Stage.ROCKSTAR]
STAGE_NOUNS = ("Wisp", "era", "years", "phase")
STAGE_UP_LINES = [
    line
    for (moment, _), lines in LINES.items()
    if moment is Moment.STAGE_UP
    for line in lines
]


def fields_for(
    moment: Moment, values: dict[str, str] = SAMPLE_FIELDS
) -> dict[str, str]:
    return {field: values[field] for field in FIELDS[moment]}


def placeholders(line: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(line) if field is not None}


def every_line() -> list[tuple[Moment, str]]:
    return [(moment, line) for (moment, _), lines in LINES.items() for line in lines]


# ---
# The line set
# ---


@pytest.mark.parametrize("moment", list(Moment))
@pytest.mark.parametrize("mood", list(Mood))
def test_every_moment_has_lines_for_every_mood(moment: Moment, mood: Mood) -> None:
    assert len(lines_for(moment, mood)) >= 4
    line = LinePicker(random.Random(1)).pick(moment, mood, **fields_for(moment))
    assert line in {
        text.format(**fields_for(moment)) for text in lines_for(moment, mood)
    }


@pytest.mark.parametrize("moment", sorted(set(Moment) - ONE_MOOD_MOMENTS))
def test_happy_and_hangry_are_always_written(moment: Moment) -> None:
    assert (moment, Mood.HAPPY) in LINES and (moment, Mood.HANGRY) in LINES


def test_a_lonely_moment_without_lonely_lines_falls_back_to_happy() -> None:
    assert (Moment.TRACK_FED, Mood.LONELY) not in LINES
    assert (
        lines_for(Moment.TRACK_FED, Mood.LONELY)
        is LINES[(Moment.TRACK_FED, Mood.HAPPY)]
    )


def test_lonely_and_happy_share_a_bag_when_lonely_falls_back() -> None:
    picker = LinePicker(random.Random(4))
    happy = LINES[(Moment.QUIET, Mood.HAPPY)]
    turns = [(Mood.LONELY, Mood.HAPPY)[turn % 2] for turn in range(len(happy))]
    picks = [picker.pick(Moment.QUIET, feeling) for feeling in turns]
    assert sorted(picks) == sorted(happy)


def test_the_lonely_moment_has_its_own_lines() -> None:
    assert FIELDS[Moment.LONELY] == set()
    lines = LINES[(Moment.LONELY, Mood.HAPPY)]
    assert len(lines) >= 8
    others = {
        line
        for (moment, _), written in LINES.items()
        if moment is not Moment.LONELY
        for line in written
    }
    assert not set(lines) & others


@pytest.mark.parametrize("moment", [Moment.SICK, Moment.RECOVERED])
def test_the_monster_pox_moments_have_about_eight_lines(moment: Moment) -> None:
    assert FIELDS[moment] == set()
    assert len(LINES[(moment, Mood.HAPPY)]) >= 8


@pytest.mark.parametrize("moment", [Moment.SICK, Moment.RECOVERED])
def test_the_monster_pox_lines_are_spotty_not_sneezy(moment: Moment) -> None:
    lines = [line.lower() for line in LINES[(moment, Mood.HAPPY)]]
    assert any("monster pox" in line for line in lines)
    assert any("spots" in line for line in lines)
    for line in lines:
        for word in ("cold", "sneez", "sniff", "achoo", "tissue", "nose"):
            assert word not in line


@pytest.mark.parametrize("moment", LONELY_TALK_MOMENTS)
def test_lonely_talk_has_its_own_lines(moment: Moment) -> None:
    lonely = set(LINES[(moment, Mood.LONELY)])
    assert len(lonely) >= 8
    assert not lonely & set(LINES[(moment, Mood.HAPPY)])
    assert not lonely & set(LINES[(moment, Mood.HANGRY)])


@pytest.mark.parametrize("moment", sorted(ONE_MOOD_MOMENTS))
def test_one_mood_moments_share_one_set(moment: Moment) -> None:
    assert LINES[(moment, Mood.HAPPY)] is LINES[(moment, Mood.HANGRY)]


@pytest.mark.parametrize("moment", sorted(set(Moment) - ONE_MOOD_MOMENTS))
def test_two_mood_moments_have_their_own_sets(moment: Moment) -> None:
    assert not set(LINES[(moment, Mood.HAPPY)]) & set(LINES[(moment, Mood.HANGRY)])


def test_no_line_is_written_twice() -> None:
    sets = {id(lines): lines for lines in LINES.values()}.values()
    written = [line for lines in sets for line in lines]
    assert len(written) == len(set(written))


def test_no_line_has_unicode_emoji() -> None:
    for _, line in every_line():
        assert "\u200d" not in line and "\ufe0f" not in line, line
        for char in line:
            assert char == "♪" or unicodedata.category(char) != "So", line


def test_no_line_has_dashes_wisp_would_not_type() -> None:
    for _, line in every_line():
        assert "\u2014" not in line and "\u2013" not in line, line


def test_lines_fit_one_message() -> None:
    for moment, line in every_line():
        assert line.count("\n") <= 1, line
        assert len(line.format(**fields_for(moment, LONGEST_FIELDS))) < 2000


def test_lines_only_use_their_moments_fields() -> None:
    for moment, line in every_line():
        assert placeholders(line) <= FIELDS[moment], line


@pytest.mark.parametrize("stage", GROWN_STAGES)
@pytest.mark.parametrize("line", STAGE_UP_LINES)
def test_stage_up_lines_read_for_every_stage(line: str, stage: Stage) -> None:
    text = line.format(stage=stage)
    awkward = rf"\b(a|an|I'm|to|officially)\s+{stage}\b"
    as_adjective = rf"\b{stage}\s+({'|'.join(STAGE_NOUNS)})\b"
    assert not re.search(awkward, text, re.IGNORECASE), text
    assert re.search(as_adjective, text), text


def test_fields_cover_every_moment() -> None:
    assert set(FIELDS) == set(Moment)


def test_rhyme_start_lines_say_the_word() -> None:
    for mood in Mood:
        for line in lines_for(Moment.RHYME_START, mood):
            assert placeholders(line) == {"word"}, line


@pytest.mark.parametrize(
    ("moment", "fields"),
    [
        (Moment.GREW_OLD, set()),
        (Moment.FAREWELL, {"version"}),
        (Moment.COAL_EGG, {"version"}),
        (Moment.LAST_EMBER, {"name", "version"}),
    ],
)
def test_farewell_moments_take_their_fields(moment: Moment, fields: set[str]) -> None:
    assert FIELDS[moment] == fields


@pytest.mark.parametrize(
    "moment", [Moment.EGG_POKE, Moment.BABY_TALK, Moment.CHAT_FALLBACK]
)
def test_talk_moments_take_no_fields(moment: Moment) -> None:
    assert FIELDS[moment] == set()


@pytest.mark.parametrize("moment", [Moment.FAREWELL, Moment.COAL_EGG])
def test_farewell_and_coal_egg_lines_name_the_version(moment: Moment) -> None:
    for line in LINES[(moment, Mood.HAPPY)]:
        assert placeholders(line) == {"version"}, line


def test_keepsake_won_lines_speak_to_the_member_without_numbers() -> None:
    assert FIELDS[Moment.KEEPSAKE_WON] == {"name"}
    lines = LINES[(Moment.KEEPSAKE_WON, Mood.HAPPY)]
    assert len(lines) >= 6
    for line in lines:
        assert placeholders(line) == {"name"}, line
        assert not re.search(r"\d", line), line


@pytest.mark.parametrize("mood", list(Mood))
def test_poked_lines_name_the_poker(mood: Mood) -> None:
    assert FIELDS[Moment.POKED] == {"name"}
    lines = lines_for(Moment.POKED, mood)
    assert len(lines) >= 8
    for line in lines:
        assert placeholders(line) == {"name"}, line


def test_last_ember_lines_speak_to_the_member() -> None:
    for line in LINES[(Moment.LAST_EMBER, Mood.HAPPY)]:
        assert "name" in placeholders(line), line


@pytest.mark.parametrize("moment", [Moment.FAVORITE_SONG, Moment.SNACK_FAVORITE])
def test_lunchbox_moments_speak_of_the_member(moment: Moment) -> None:
    assert FIELDS[moment] == {"name"}


@pytest.mark.parametrize("moment", [Moment.FAVORITE_SONG, Moment.SNACK_FAVORITE])
@pytest.mark.parametrize("mood", list(Mood))
def test_lunchbox_moments_have_about_six_lines_and_no_numbers(
    moment: Moment, mood: Mood
) -> None:
    lines = lines_for(moment, mood)
    assert len(lines) >= 6
    for line in lines:
        assert not re.search(r"\d", line), line


GIFT_MOMENTS = [
    Moment.GIFT_KEPT,
    Moment.GIFT_PASSED,
    Moment.GIFT_FULL,
    Moment.COLLECTION_DONE,
]


@pytest.mark.parametrize("moment", GIFT_MOMENTS)
@pytest.mark.parametrize("mood", list(Mood))
def test_gift_moments_have_about_six_lines_and_no_numbers(
    moment: Moment, mood: Mood
) -> None:
    lines = lines_for(moment, mood)
    assert len(lines) >= 6
    for line in lines:
        assert not re.search(r"\d", line), line


def test_gift_lines_never_put_an_article_before_the_gift() -> None:
    for moment, line in every_line():
        if "gift" in FIELDS[moment]:
            assert not re.search(r"\ban? \{gift\}", line, re.IGNORECASE), line


@pytest.mark.parametrize(
    ("moment", "fields"),
    [
        (Moment.GIFT_KEPT, {"name", "gift"}),
        (Moment.GIFT_PASSED, {"name", "gift"}),
        (Moment.GIFT_FULL, {"name", "gift"}),
        (Moment.COLLECTION_DONE, {"name", "collection"}),
    ],
)
def test_gift_moments_take_their_fields(moment: Moment, fields: set[str]) -> None:
    assert FIELDS[moment] == fields


@pytest.mark.parametrize("moment", FAREWELL_MOMENTS)
def test_farewell_moment_lines_have_no_numbers(moment: Moment) -> None:
    for line in LINES[(moment, Mood.HAPPY)]:
        assert not re.search(r"\d", line), line


# ---
# The picker
# ---


class FlippingShuffle(random.Random):
    """Shuffles by leaving every other bag in order and reversing the rest.

    The two deal the same lines in opposite orders, so each refill would start
    with the line the bag before it ended on.
    """

    def __init__(self) -> None:
        super().__init__()
        self.flip = False

    def shuffle(self, x: MutableSequence[Any]) -> None:
        if self.flip:
            x.reverse()
        self.flip = not self.flip


@pytest.mark.parametrize("key", ALL_KEYS)
def test_picker_deals_every_line_once_per_bag(key: tuple[Moment, Mood]) -> None:
    moment, mood = key
    picker = LinePicker(random.Random(7))
    expected = sorted(line.format(**fields_for(moment)) for line in LINES[key])
    size = len(expected)
    picks = [picker.pick(moment, mood, **fields_for(moment)) for _ in range(size * 4)]
    for start in range(0, len(picks), size):
        assert sorted(picks[start : start + size]) == expected


@pytest.mark.parametrize("key", ALL_KEYS)
@pytest.mark.parametrize("seed", range(5))
def test_picker_never_says_a_line_twice_in_a_row(
    key: tuple[Moment, Mood], seed: int
) -> None:
    moment, mood = key
    picker = LinePicker(random.Random(seed))
    picks = [picker.pick(moment, mood, **fields_for(moment)) for _ in range(60)]
    assert all(first != second for first, second in zip(picks, picks[1:]))


def test_a_refill_never_starts_with_the_line_that_ended_the_last_bag() -> None:
    picker = LinePicker(FlippingShuffle())
    size = len(LINES[(Moment.QUIET, Mood.HAPPY)])
    picks = [picker.pick(Moment.QUIET, Mood.HAPPY) for _ in range(size * 3)]
    for end in range(size, len(picks), size):
        assert picks[end] != picks[end - 1]
        assert len(set(picks[end : end + size])) == size


def test_each_moment_and_mood_has_its_own_bag() -> None:
    picker = LinePicker(random.Random(2))
    happy = len(LINES[(Moment.QUIET, Mood.HAPPY)])
    picker.pick(Moment.QUIET, Mood.HANGRY)
    picker.pick(Moment.HUNGRY, Mood.HAPPY)
    picks = [picker.pick(Moment.QUIET, Mood.HAPPY) for _ in range(happy)]
    assert set(picks) == set(LINES[(Moment.QUIET, Mood.HAPPY)])


@pytest.mark.parametrize("key", ALL_KEYS)
def test_picker_uses_every_line_eventually(key: tuple[Moment, Mood]) -> None:
    moment, mood = key
    picker = LinePicker(random.Random(11))
    expected = {line.format(**fields_for(moment)) for line in LINES[key]}
    picks = {picker.pick(moment, mood, **fields_for(moment)) for _ in range(200)}
    assert picks == expected


def test_picker_is_deterministic_with_a_seed() -> None:
    first = LinePicker(random.Random(3))
    second = LinePicker(random.Random(3))
    for _ in range(10):
        assert first.pick(Moment.QUIET, Mood.HAPPY) == second.pick(
            Moment.QUIET, Mood.HAPPY
        )


@pytest.mark.parametrize("key", ALL_KEYS)
def test_placeholders_filled(key: tuple[Moment, Mood]) -> None:
    moment, mood = key
    picker = LinePicker()
    for _ in range(len(LINES[key])):
        line = picker.pick(moment, mood, **fields_for(moment))
        assert "{" not in line and "}" not in line, line


def test_placeholder_values_land_in_the_line() -> None:
    picker = LinePicker(random.Random(5))
    lines = {picker.pick(Moment.DIED, Mood.HANGRY, version="17") for _ in range(20)}
    assert all("17" in line for line in lines)


@pytest.mark.parametrize(
    ("moment", "fields", "message"),
    [
        (Moment.TRACK_FED, {}, "name"),
        (Moment.DIED, {}, "version"),
        (Moment.STAGE_UP, {"name": "Myra"}, "stage"),
        (Moment.QUIET, {"name": "Myra"}, "name"),
    ],
)
def test_picker_rejects_wrong_fields(
    moment: Moment, fields: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        LinePicker().pick(moment, Mood.HAPPY, **fields)
