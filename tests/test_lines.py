"""Tests for Wisp's lines and the no-repeat line picker."""

import random
import re
import unicodedata
from string import Formatter

import pytest

from wisp.life import Mood
from wisp.lines import FIELDS, LINES, LinePicker, Moment
from wisp.rules import Stage

SAMPLE_FIELDS = {"name": "Myra", "version": "4", "stage": "teen", "word": "fire"}
LONGEST_FIELDS = {
    "name": "W" * 32,
    "version": "9999",
    "stage": "rockstar",
    "word": "w" * 40,
}
ONE_MOOD_MOMENTS = {
    Moment.HUNGRY,
    Moment.FADING,
    Moment.DIED,
    Moment.NEW_EGG,
    Moment.EGG_COLD,
    Moment.HATCH_STARTED,
    Moment.HATCHED,
    Moment.COMPLIMENT_HANGRY,
    Moment.BANNED,
    Moment.NOT_ENOUGH_POINTS,
}
ALL_KEYS = sorted(LINES)
GROWN_STAGES = [Stage.CHILD, Stage.TEEN, Stage.ADULT, Stage.ROCKSTAR]
STAGE_NOUNS = ("Wisp", "era", "years", "phase")
STAGE_UP_LINES = [line for mood in Mood for line in LINES[(Moment.STAGE_UP, mood)]]


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
def test_every_moment_has_lines_for_both_moods(moment: Moment, mood: Mood) -> None:
    assert len(LINES[(moment, mood)]) >= 4


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
        for line in LINES[(Moment.RHYME_START, mood)]:
            assert placeholders(line) == {"word"}, line


# ---
# The picker
# ---


@pytest.mark.parametrize("key", ALL_KEYS)
def test_picker_does_not_repeat_recent(key: tuple[Moment, Mood]) -> None:
    moment, mood = key
    picker = LinePicker(random.Random(7))
    window = min(len(LINES[key]) - 1, 5)
    picks = [picker.pick(moment, mood, **fields_for(moment)) for _ in range(60)]
    for index, line in enumerate(picks):
        assert line not in picks[max(0, index - window) : index]


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
