"""Tests for rhyme checks and Wisp's own rhyme picks."""

import random
import re
from pathlib import Path

import pronouncing
import pytest

from wisp.language import Language
from wisp.rhymes import (
    RhymeKind,
    clean_word,
    fold,
    opening_word,
    rhyme_chance,
    rhyme_kind,
    score,
    wisp_reply,
)
from wisp.rules import (
    MAX_WORD_LENGTH,
    RHYME_OPENER_RHYMES,
    RHYME_SKILL,
    RHYME_SURE_TURNS,
    RHYME_TIRING,
    Stage,
)

WORDS_FILE = Path(__file__).resolve().parent.parent / "wisp/data/common_words.txt"
COMMON = WORDS_FILE.read_text(encoding="utf-8").splitlines()
TWO_LETTER_WORDS = {
    "go", "no", "so", "me", "we", "my", "by", "hi", "oh", "yo", "up", "us", "is",
    "it", "at", "an", "as", "be", "do", "he", "if", "in", "of", "on", "or", "to",
}  # fmt: skip
JUNK = {
    "st", "co", "inc", "mrs", "ms", "de", "re", "et", "du", "il", "sa", "se", "mi",
    "na", "la", "le", "el", "en", "er", "fi", "li", "des", "los", "del", "pre",
    "non", "gen", "ed", "ho",
}  # fmt: skip
HATCHED = [Stage.BABY, Stage.CHILD, Stage.TEEN, Stage.ADULT, Stage.ROCKSTAR]
TRIALS = 1000
LEAF = Path(__file__).resolve().parent.parent / "wisp/rhyme_keys.py"
WIKIPRON_FILE = Path(__file__).resolve().parent.parent / "wisp/data/wikipron_en.txt"


def reply_rate(stage: Stage, turn: int | None = None) -> float:
    """How often Wisp answers "day" on `turn`; by default his first unsure one."""
    rng = random.Random(15)
    turn = RHYME_SURE_TURNS[stage] + 1 if turn is None else turn
    hits = sum(
        wisp_reply("day", {"day"}, stage, turn, rng, language=Language.EN) is not None
        for _ in range(TRIALS)
    )
    return hits / TRIALS


# ---
# Rhyme checks
# ---


@pytest.mark.parametrize(("first", "second"), [("fire", "choir"), ("cat", "hat")])
def test_perfect_rhyme(first: str, second: str) -> None:
    assert rhyme_kind(first, second, language=Language.EN) is RhymeKind.PERFECT
    assert rhyme_kind(second, first, language=Language.EN) is RhymeKind.PERFECT


def test_slant_rhyme() -> None:
    assert rhyme_kind("fire", "mine", language=Language.EN) is RhymeKind.SLANT
    assert rhyme_kind("mine", "fire", language=Language.EN) is RhymeKind.SLANT


def test_not_a_rhyme() -> None:
    assert rhyme_kind("fire", "water", language=Language.EN) is None


@pytest.mark.parametrize(("first", "second"), [("fire", "zzqx"), ("blorptang", "hat")])
def test_unknown_word_rejected(first: str, second: str) -> None:
    assert rhyme_kind(first, second, language=Language.EN) is None


@pytest.mark.parametrize(("first", "second"), [("fire", "fire"), ("Fire", "fire")])
def test_same_word_rejected(first: str, second: str) -> None:
    assert rhyme_kind(first, second, language=Language.EN) is None


@pytest.mark.parametrize(
    ("first", "second"),
    [("right", "write"), ("night", "knight"), ("to", "two"), ("flower", "flour")],
)
def test_homophones_are_not_rhymes(first: str, second: str) -> None:
    assert rhyme_kind(first, second, language=Language.EN) is None
    assert rhyme_kind(second, first, language=Language.EN) is None


def test_stress_level_does_not_break_a_rhyme() -> None:
    assert rhyme_kind("day", "birthday", language=Language.EN) is RhymeKind.PERFECT


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
        pytest.param("a" * MAX_WORD_LENGTH, "a" * MAX_WORD_LENGTH, id="at-limit"),
        pytest.param("a" * (MAX_WORD_LENGTH + 1), None, id="over-limit"),
        pytest.param("b" * 2000, None, id="huge"),
    ],
)
def test_clean_word(text: str, word: str | None) -> None:
    assert clean_word(text, language=Language.EN) == word


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("«hat»", "hat"),
        ("hat !", "hat"),
        ("hat\u202f!", "hat"),
        ("\u00a0hat\u00a0", "hat"),
        ("¡hat…", "hat"),
        ("“hat”", "hat"),
        ("don’t", "don't"),
        pytest.param("he\u0301llo", None, id="nfc-keeps-english-ascii"),
    ],
)
def test_clean_word_strips_unicode_edges(text: str, word: str | None) -> None:
    assert clean_word(text, language=Language.EN) == word


def _old_rhyme_kind(first: str, second: str) -> RhymeKind | None:
    """The English rule before languages, kept here to prove nothing changed."""

    def rhyme_part(phones: str) -> tuple[str, ...]:
        split = phones.split()
        vowels = [index for index, phone in enumerate(split) if phone[-1].isdigit()]
        stressed = [index for index in vowels if split[index][-1] in "12"]
        start = (stressed or vowels or [0])[-1]
        return tuple(phone.rstrip("012") for phone in split[start:])

    def sounds(word: str) -> set[tuple[str, ...]]:
        return {
            tuple(phone.rstrip("012") for phone in phones.split())
            for phones in pronouncing.phones_for_word(word)
        }

    if first == second or sounds(first) & sounds(second):
        return None
    first_rhymes = {rhyme_part(phones) for phones in pronouncing.phones_for_word(first)}
    second_rhymes = {
        rhyme_part(phones) for phones in pronouncing.phones_for_word(second)
    }
    if first_rhymes & second_rhymes:
        return RhymeKind.PERFECT
    if {rhyme[0] for rhyme in first_rhymes} & {rhyme[0] for rhyme in second_rhymes}:
        return RhymeKind.SLANT
    return None


def test_english_keys_match_the_old_rhyme_kind() -> None:
    rng = random.Random(7)
    kinds = set()
    for _ in range(2000):
        first, second = rng.choice(COMMON), rng.choice(COMMON)
        kind = rhyme_kind(first, second, language=Language.EN)
        assert kind is _old_rhyme_kind(first, second), (first, second)
        kinds.add(kind)
    assert kinds == {None, RhymeKind.SLANT, RhymeKind.PERFECT}


@pytest.mark.parametrize(
    ("word", "language", "folded"),
    [
        ("corazón", Language.ES, "corazon"),
        ("pingüino", Language.ES, "pinguino"),
        ("año", Language.ES, "año"),
        ("ça", Language.FR, "ca"),
        ("garçon", Language.FR, "garcon"),
        ("cœur", Language.FR, "coeur"),
        ("ex-æquo", Language.FR, "ex-aequo"),
        ("maïs", Language.FR, "mais"),
        ("forêt", Language.FR, "foret"),
        ("à", Language.FR, "a"),
        ("ca\u0301ncion", Language.ES, "cancion"),
        ("choir", Language.EN, "choir"),
    ],
)
def test_fold_per_language(word: str, language: Language, folded: str) -> None:
    assert fold(word, language=language) == folded


def test_rhyme_keys_is_a_leaf_module() -> None:
    source = LEAF.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+wisp\.rhymes", source, re.MULTILINE)


# ---
# Wisp's picks
# ---


def test_wisp_never_repeats() -> None:
    rng = random.Random(3)
    used = {"day"}
    replies = []
    for _ in range(200):
        reply = wisp_reply("day", used, Stage.ROCKSTAR, 1, rng, language=Language.EN)
        if reply is not None:
            assert reply not in used
            assert rhyme_kind("day", reply, language=Language.EN) is RhymeKind.PERFECT
            used.add(reply)
            replies.append(reply)
    assert len(replies) > 20
    assert set(replies) <= set(COMMON)
    everything = used | set(COMMON)
    assert all(
        wisp_reply("day", everything, Stage.ROCKSTAR, 1, rng, language=Language.EN)
        is None
        for _ in range(20)
    )


@pytest.mark.parametrize(
    ("word", "homophone"), [("night", "knight"), ("right", "write")]
)
def test_wisp_never_answers_with_a_homophone(word: str, homophone: str) -> None:
    assert homophone in COMMON
    rng = random.Random(9)
    used = {word}
    for _ in range(300):
        reply = wisp_reply(word, used, Stage.ROCKSTAR, 1, rng, language=Language.EN)
        if reply is not None:
            used.add(reply)
    assert homophone not in used
    assert len(used) > 10


def test_wisp_has_nothing_for_an_unknown_word() -> None:
    assert (
        wisp_reply(
            "blorptang",
            set(),
            Stage.ROCKSTAR,
            1,
            random.Random(1),
            language=Language.EN,
        )
        is None
    )


def test_wisp_reply_rate_rises_with_stage() -> None:
    rates = [reply_rate(stage) for stage in HATCHED]
    assert rates == sorted(rates)
    assert abs(rates[0] - 0.5) < 0.05
    assert abs(rates[-1] - 0.97) < 0.02


@pytest.mark.parametrize("stage", HATCHED + [Stage.OLD_FOGEY])
def test_he_always_answers_on_his_sure_turns(stage: Stage) -> None:
    for turn in range(1, RHYME_SURE_TURNS[stage] + 1):
        assert rhyme_chance(stage, turn) == 1.0
        assert reply_rate(stage, turn) == 1.0


def test_after_the_sure_turns_he_tires_ten_percent_a_turn() -> None:
    sure = RHYME_SURE_TURNS[Stage.CHILD]

    chances = [rhyme_chance(Stage.CHILD, sure + step) for step in range(1, 5)]

    assert RHYME_TIRING == 0.1
    assert chances == pytest.approx([0.65, 0.55, 0.45, 0.35])
    assert rhyme_chance(Stage.CHILD, sure + 50) == 0.0


def test_the_child_gets_three_sure_turns() -> None:
    assert RHYME_SURE_TURNS[Stage.CHILD] == 3
    assert RHYME_SKILL[Stage.CHILD] == 0.65


def test_opening_word_has_plenty_of_rhymes() -> None:
    for seed in range(20):
        word = opening_word(random.Random(seed), language=Language.EN)
        rhymes = [
            other
            for other in COMMON
            if rhyme_kind(word, other, language=Language.EN) is RhymeKind.PERFECT
        ]
        assert word in COMMON
        assert len(rhymes) >= RHYME_OPENER_RHYMES


def test_opening_word_varies() -> None:
    rng = random.Random(8)
    assert len({opening_word(rng, language=Language.EN) for _ in range(20)}) > 10


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
    assert not {"fuck", "shit", "bitch", "damn", "hell", "sex", "ho"} & set(COMMON)


def test_common_words_are_real_words() -> None:
    short = {word for word in COMMON if len(word) < 3}
    assert short <= TWO_LETTER_WORDS
    assert not JUNK & set(COMMON)


# ---
# WikiPron words
# ---


def test_a_word_cmu_lacks_rhymes_from_wikipron() -> None:
    assert not pronouncing.phones_for_word("lollygag")
    assert rhyme_kind("lollygag", "bag", language=Language.EN) is RhymeKind.PERFECT
    assert rhyme_kind("widdershins", "pins", language=Language.EN) is RhymeKind.SLANT


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("accoast", "coast"),
        ("accoast", "most"),
        ("aikido", "go"),
        ("wayfare", "chair"),
        ("immure", "pure"),
        ("geosphere", "fear"),
    ],
)
def test_british_style_wikipron_vowels_rhyme(first: str, second: str) -> None:
    assert not pronouncing.phones_for_word(first)
    assert rhyme_kind(first, second, language=Language.EN) is RhymeKind.PERFECT


def test_curr_is_in_neither_dictionary() -> None:
    assert rhyme_kind("curr", "were", language=Language.EN) is None


def test_every_wikipron_reading_has_one_stressed_vowel() -> None:
    readings = [
        reading
        for line in WIKIPRON_FILE.read_text(encoding="utf-8").splitlines()
        for reading in line.split("\t")[1:]
    ]
    assert len(readings) > 30000
    for reading in readings:
        stress = [phone[-1] for phone in reading.split() if phone[-1].isdigit()]
        assert stress.count("1") == 1, reading
        assert set(stress) <= {"0", "1"}, reading


def test_wikipron_words_are_all_missing_from_cmu() -> None:
    lines = WIKIPRON_FILE.read_text(encoding="utf-8").splitlines()
    words = [line.split("\t")[0] for line in lines]
    assert not [word for word in words[::50] if pronouncing.phones_for_word(word)]
