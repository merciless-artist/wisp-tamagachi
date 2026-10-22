"""Tests for rhyme checks and Wisp's own rhyme picks."""

import random
import re
from pathlib import Path

import pronouncing
import pytest

from wisp.rhymes import (
    RhymeKind,
    clean_word,
    opening_word,
    rhyme_kind,
    score,
    wisp_reply,
)
from wisp.rules import RHYME_OPENER_RHYMES, Stage

WORDS_FILE = Path(__file__).resolve().parent.parent / "wisp/data/common_words.txt"
COMMON = WORDS_FILE.read_text(encoding="utf-8").splitlines()
HATCHED = [Stage.BABY, Stage.CHILD, Stage.TEEN, Stage.ADULT, Stage.ROCKSTAR]
TRIALS = 1000


def reply_rate(stage: Stage) -> float:
    rng = random.Random(15)
    hits = sum(
        wisp_reply("day", {"day"}, stage, rng) is not None for _ in range(TRIALS)
    )
    return hits / TRIALS


# ---
# Rhyme checks
# ---


@pytest.mark.parametrize(("first", "second"), [("fire", "choir"), ("cat", "hat")])
def test_perfect_rhyme(first: str, second: str) -> None:
    assert rhyme_kind(first, second) is RhymeKind.PERFECT
    assert rhyme_kind(second, first) is RhymeKind.PERFECT


def test_slant_rhyme() -> None:
    assert rhyme_kind("fire", "mine") is RhymeKind.SLANT
    assert rhyme_kind("mine", "fire") is RhymeKind.SLANT


def test_not_a_rhyme() -> None:
    assert rhyme_kind("fire", "water") is None


@pytest.mark.parametrize(("first", "second"), [("fire", "zzqx"), ("blorptang", "hat")])
def test_unknown_word_rejected(first: str, second: str) -> None:
    assert rhyme_kind(first, second) is None


@pytest.mark.parametrize(("first", "second"), [("fire", "fire"), ("Fire", "fire")])
def test_same_word_rejected(first: str, second: str) -> None:
    assert rhyme_kind(first, second) is None


def test_stress_level_does_not_break_a_rhyme() -> None:
    assert rhyme_kind("day", "birthday") is RhymeKind.PERFECT


def test_scores() -> None:
    assert score(RhymeKind.PERFECT) == 2
    assert score(RhymeKind.SLANT) == 1


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("choir", "choir"),
        ("  Choir! ", "choir"),
        ("**HAT**", "hat"),
        ("don’t", "don't"),
        ("two words", None),
        ("", None),
        ("!!!", None),
        ("h4t", None),
    ],
)
def test_clean_word(text: str, word: str | None) -> None:
    assert clean_word(text) == word


# ---
# Wisp's picks
# ---


def test_wisp_never_repeats() -> None:
    rng = random.Random(3)
    used = {"day"}
    replies = []
    for _ in range(200):
        reply = wisp_reply("day", used, Stage.ROCKSTAR, rng)
        if reply is not None:
            assert reply not in used
            assert rhyme_kind("day", reply) is RhymeKind.PERFECT
            used.add(reply)
            replies.append(reply)
    assert len(replies) > 20
    assert set(replies) <= set(COMMON)
    everything = used | set(COMMON)
    assert all(
        wisp_reply("day", everything, Stage.ROCKSTAR, rng) is None for _ in range(20)
    )


def test_wisp_has_nothing_for_an_unknown_word() -> None:
    assert wisp_reply("blorptang", set(), Stage.ROCKSTAR, random.Random(1)) is None


def test_wisp_reply_rate_rises_with_stage() -> None:
    rates = [reply_rate(stage) for stage in HATCHED]
    assert rates == sorted(rates)
    assert abs(rates[0] - 0.5) < 0.05
    assert abs(rates[-1] - 0.97) < 0.02


def test_opening_word_has_plenty_of_rhymes() -> None:
    for seed in range(20):
        word = opening_word(random.Random(seed))
        rhymes = [
            other for other in COMMON if rhyme_kind(word, other) is RhymeKind.PERFECT
        ]
        assert word in COMMON
        assert len(rhymes) >= RHYME_OPENER_RHYMES


def test_opening_word_varies() -> None:
    rng = random.Random(8)
    assert len({opening_word(rng) for _ in range(20)}) > 10


# ---
# The word list
# ---


def test_common_words_are_all_in_dictionary() -> None:
    assert 4500 <= len(COMMON) <= 5500
    assert len(COMMON) == len(set(COMMON))
    for word in COMMON:
        assert re.fullmatch(r"[a-z]{2,}", word), word
        assert pronouncing.phones_for_word(word), word


def test_common_words_skip_profanity() -> None:
    assert not {"fuck", "shit", "bitch", "damn", "hell", "sex"} & set(COMMON)
