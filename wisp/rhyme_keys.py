"""The rhyme keys every language shares, and how two words' keys compare.

This is a leaf module: it imports nothing from the other rhyme modules, so
each language's rules and the word-list builder can all import it.
"""

import unicodedata
from collections.abc import Iterable, Mapping
from enum import StrEnum, auto
from pathlib import Path
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


def merge(readings: Iterable[WordKeys | None]) -> WordKeys | None:
    """The keys of every reading of a word together; None when none can be read."""
    read = [word_keys for word_keys in readings if word_keys is not None]
    if not read:
        return None
    return WordKeys(
        whole=frozenset().union(*(word_keys.whole for word_keys in read)),
        perfect=frozenset().union(*(word_keys.perfect for word_keys in read)),
        slant=frozenset().union(*(word_keys.slant for word_keys in read)),
    )


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


def read_accents(path: Path) -> dict[str, tuple[str, ...]]:
    """An accent map file: each unaccented spelling and the known words it stands for.

    One line per entry, `unaccented<TAB>accented accented ...`.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return {
        unaccented: tuple(accented.split())
        for unaccented, accented in (line.split("	") for line in lines)
    }


def known_spellings(
    word: str,
    *,
    language: Language,
    known: frozenset[str],
    accents: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """The known spellings `word` can be read as; empty when it is unknown.

    A word that carries an accent is only itself. An unaccented one is itself
    when known, plus the accented twins `accents` lists for it.
    """
    word = unicodedata.normalize("NFC", word)
    own = (word,) if word in known else ()
    if fold(word, language=language) != word:
        return own
    return own + tuple(accents.get(word, ()))
