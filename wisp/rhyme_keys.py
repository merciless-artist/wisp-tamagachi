"""The rhyme keys every language shares, and how two words' keys compare.

This is a leaf module: it imports nothing from the other rhyme modules, so
each language's rules and the word-list builder can all import it.
"""

import unicodedata
from enum import StrEnum, auto
from typing import Final, NamedTuple

from wisp.language import Language

_REMOVED_MARKS: Final = frozenset(
    {
        "̀",  # grave
        "́",  # acute
        "̂",  # circumflex
        "̈",  # diaeresis
    }
)
_CEDILLA: Final = "̧"
_FRENCH_LIGATURES: Final = str.maketrans({"œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE"})


class RhymeKind(StrEnum):
    """How well two words rhyme."""

    PERFECT = auto()
    SLANT = auto()


class WordKeys(NamedTuple):
    """What a word sounds like, one element per reading of it.

    `whole` is the whole word, so equal keys mean homophones; `perfect` is the
    sound from the stressed vowel to the end; `slant` is the looser match.
    """

    whole: frozenset[str]
    perfect: frozenset[str]
    slant: frozenset[str]


def fold(word: str, *, language: Language) -> str:
    """`word` with its acute, grave, circumflex and diaeresis accents removed.

    French also drops the cedilla and opens the ligatures (ç to c, œ to oe,
    æ to ae), as French speakers often type without them. Every other mark,
    like the tilde of Spanish ñ, is kept.
    """
    removed = _REMOVED_MARKS | {_CEDILLA} if language is Language.FR else _REMOVED_MARKS
    decomposed = unicodedata.normalize("NFD", word)
    kept = "".join(mark for mark in decomposed if mark not in removed)
    folded = unicodedata.normalize("NFC", kept)
    return folded.translate(_FRENCH_LIGATURES) if language is Language.FR else folded


def compare(first: WordKeys | None, second: WordKeys | None) -> RhymeKind | None:
    """How two words rhyme, from their keys.

    None when either word cannot be read or they can sound exactly alike.
    PERFECT when any perfect keys match, SLANT when only slant keys do.
    """
    if first is None or second is None or first.whole & second.whole:
        return None
    if first.perfect & second.perfect:
        return RhymeKind.PERFECT
    if first.slant & second.slant:
        return RhymeKind.SLANT
    return None
