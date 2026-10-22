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
    RHYME_OPENER_RHYMES,
    RHYME_PERFECT_POINTS,
    RHYME_SKILL,
    RHYME_SLANT_POINTS,
    Stage,
)

_WORDS_FILE: Final = Path(__file__).resolve().parent / "data" / "common_words.txt"
_WORD: Final = re.compile(r"[a-z]+(?:'[a-z]+)*")
_STRESS_MARKS: Final = "012"
_STRESSED: Final = "12"

_Rhyme = tuple[str, ...]


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


def _rhyme_part(phones: str) -> _Rhyme:
    """The phones from the last stressed vowel on, without stress marks.

    A word with no stressed vowel rhymes from its last vowel.
    """
    split = phones.split()
    vowels = [index for index, phone in enumerate(split) if phone[-1].isdigit()]
    stressed = [index for index in vowels if split[index][-1] in _STRESSED]
    start = (stressed or vowels or [0])[-1]
    return tuple(phone.rstrip(_STRESS_MARKS) for phone in split[start:])


def _rhymes_of(word: str) -> frozenset[_Rhyme]:
    """The rhyme of every pronunciation of a word; empty when it is unknown."""
    phones: list[str] = pronouncing.phones_for_word(word)
    return frozenset(_rhyme_part(pronunciation) for pronunciation in phones)


def rhyme_kind(first: str, second: str) -> RhymeKind | None:
    """How two words rhyme, comparing every pair of their pronunciations.

    None when either word is unknown, they are the same word or they do not
    rhyme. PERFECT when the phones match from the last stressed vowel to the
    end, SLANT when only that vowel matches.
    """
    first, second = first.lower(), second.lower()
    if first == second:
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
    """
    word = text.strip().lower().replace("’", "'").strip(string.punctuation)
    return word if _WORD.fullmatch(word) else None


# ---
# Wisp's picks
# ---


@cache
def _common_by_rhyme() -> dict[_Rhyme, frozenset[str]]:
    """Every common word, grouped by each of its rhymes."""
    grouped: defaultdict[_Rhyme, set[str]] = defaultdict(set)
    for word in _WORDS_FILE.read_text(encoding="utf-8").split():
        for rhyme in _rhymes_of(word):
            grouped[rhyme].add(word)
    return {rhyme: frozenset(words) for rhyme, words in grouped.items()}


def _common_rhymes(word: str) -> set[str]:
    """The common words that rhyme perfectly with `word`, other than itself."""
    by_rhyme = _common_by_rhyme()
    found = {
        other
        for rhyme in _rhymes_of(word)
        for other in by_rhyme.get(rhyme, frozenset())
    }
    return found - {word}


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


def wisp_reply(
    word: str, used: set[str], stage: Stage, rng: random.Random
) -> str | None:
    """Wisp's unused perfect rhyme for `word`, or None when he runs out.

    He finds one with the chance his stage gives him in RHYME_SKILL, and only
    when an unused common word rhymes.
    """
    if rng.random() >= RHYME_SKILL[stage]:
        return None
    options = sorted(_common_rhymes(word.lower()) - used)
    return rng.choice(options) if options else None
