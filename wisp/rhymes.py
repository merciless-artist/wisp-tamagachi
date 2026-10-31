"""Perfect and slant rhyme checks, and the rhymes Wisp picks himself.

Pronunciations come from the CMU Pronouncing Dictionary. A word's rhyme is its
phones from the last stressed vowel to the end, with the stress marks dropped.
Wisp only ever answers with words from `data/common_words.txt`.
"""

import random
import re
import string
from collections import defaultdict
from enum import StrEnum, auto
from functools import cache
from pathlib import Path
from typing import Final

import pronouncing

from wisp.rules import (
    MAX_WORD_LENGTH,
    RHYME_OPENER_RHYMES,
    RHYME_PERFECT_POINTS,
    RHYME_SKILL,
    RHYME_SLANT_POINTS,
    RHYME_SURE_TURNS,
    RHYME_TIRING,
    Stage,
)

_WORDS_FILE: Final = Path(__file__).resolve().parent / "data" / "common_words.txt"
_WORD: Final = re.compile(r"[a-z]+(?:'[a-z]+)*")
_STRESS_MARKS: Final = "012"
_STRESSED: Final = "12"

_Phones = tuple[str, ...]


class RhymeKind(StrEnum):
    """How well two words rhyme."""

    PERFECT = auto()
    SLANT = auto()


_POINTS: Final = {
    RhymeKind.PERFECT: RHYME_PERFECT_POINTS,
    RhymeKind.SLANT: RHYME_SLANT_POINTS,
}

# ---
# Rhyme checks
# ---


def _rhyme_part(phones: str) -> _Phones:
    """The phones from the last stressed vowel on, without stress marks.

    A word with no stressed vowel rhymes from its last vowel.
    """
    split = phones.split()
    vowels = [index for index, phone in enumerate(split) if phone[-1].isdigit()]
    stressed = [index for index in vowels if split[index][-1] in _STRESSED]
    start = (stressed or vowels or [0])[-1]
    return tuple(phone.rstrip(_STRESS_MARKS) for phone in split[start:])


def _rhymes_of(word: str) -> frozenset[_Phones]:
    """The rhyme of every pronunciation of a word; empty when it is unknown."""
    phones: list[str] = pronouncing.phones_for_word(word)
    return frozenset(_rhyme_part(pronunciation) for pronunciation in phones)


def _sounds_of(word: str) -> frozenset[_Phones]:
    """Every whole pronunciation of a word, without stress marks."""
    phones: list[str] = pronouncing.phones_for_word(word)
    return frozenset(
        tuple(phone.rstrip(_STRESS_MARKS) for phone in pronunciation.split())
        for pronunciation in phones
    )


def rhyme_kind(first: str, second: str) -> RhymeKind | None:
    """How two words rhyme, comparing every pair of their pronunciations.

    None when either word is unknown, they are the same word, they can sound
    exactly alike (right, write) or they do not rhyme. PERFECT when the phones
    match from the last stressed vowel to the end, SLANT when only that vowel
    matches.
    """
    first, second = first.lower(), second.lower()
    if first == second or _sounds_of(first) & _sounds_of(second):
        return None
    first_rhymes, second_rhymes = _rhymes_of(first), _rhymes_of(second)
    if first_rhymes & second_rhymes:
        return RhymeKind.PERFECT
    if {rhyme[0] for rhyme in first_rhymes} & {rhyme[0] for rhyme in second_rhymes}:
        return RhymeKind.SLANT
    return None


def score(kind: RhymeKind) -> int:
    """Points a player's rhyme earns."""
    return _POINTS[kind]


def clean_word(text: str) -> str | None:
    """The single lowercase word in a message, or None when it is not one word.

    Surrounding punctuation is dropped and curly apostrophes become straight.
    Anything longer than MAX_WORD_LENGTH is not a word.
    """
    word = text.strip().lower().replace("’", "'").strip(string.punctuation)
    if len(word) > MAX_WORD_LENGTH or not _WORD.fullmatch(word):
        return None
    return word


# ---
# Wisp's picks
# ---


@cache
def _common_by_rhyme() -> dict[_Phones, frozenset[str]]:
    """Every common word, grouped by each of its rhymes."""
    grouped: defaultdict[_Phones, set[str]] = defaultdict(set)
    for word in _WORDS_FILE.read_text(encoding="utf-8").split():
        for rhyme in _rhymes_of(word):
            grouped[rhyme].add(word)
    return {rhyme: frozenset(words) for rhyme, words in grouped.items()}


def _common_rhymes(word: str) -> set[str]:
    """The common words that rhyme perfectly with `word`.

    The word itself and words that can sound exactly like it are left out.
    """
    by_rhyme = _common_by_rhyme()
    sounds = _sounds_of(word)
    return {
        other
        for rhyme in _rhymes_of(word)
        for other in by_rhyme.get(rhyme, frozenset())
        if other != word and not _sounds_of(other) & sounds
    }


@cache
def _openers() -> tuple[str, ...]:
    """Common words with enough perfect rhymes to start a duel with."""
    words = sorted({word for words in _common_by_rhyme().values() for word in words})
    return tuple(
        word for word in words if len(_common_rhymes(word)) >= RHYME_OPENER_RHYMES
    )


def opening_word(rng: random.Random) -> str:
    """The word Wisp starts a duel with."""
    return rng.choice(_openers())


def rhyme_chance(stage: Stage, turn: int) -> float:
    """The chance that Wisp finds a rhyme on his `turn` (1 for his first) of a duel.

    Certain on his stage's RHYME_SURE_TURNS, then his RHYME_SKILL, dropping by
    RHYME_TIRING each turn after that, like a kid getting tired, never below 0.
    """
    sure = RHYME_SURE_TURNS[stage]
    if turn <= sure:
        return 1.0
    return max(RHYME_SKILL[stage] - RHYME_TIRING * (turn - sure - 1), 0.0)


def wisp_reply(
    word: str, used: set[str], stage: Stage, turn: int, rng: random.Random
) -> str | None:
    """Wisp's unused perfect rhyme for `word` on his `turn`, or None when he runs out.

    He finds one with the chance `rhyme_chance` gives him, and only when an
    unused common word rhymes.
    """
    if rng.random() >= rhyme_chance(stage, turn):
        return None
    options = sorted(_common_rhymes(word.lower()) - used)
    return rng.choice(options) if options else None
