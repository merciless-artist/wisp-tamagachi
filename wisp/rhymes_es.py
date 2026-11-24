"""Spanish rhyme keys, read from the spelling.

Spanish is spelled the way it sounds, so rules find the stressed vowel and
normalise the sounds after it (seseo, yeísmo, b and v alike) instead of a
pronouncing dictionary. A player's word only counts when it is in the known
word list in `data/`, or reaches one through the accent map there, so
`cancion` reads as `canción` while a made-up word like `xuego` is rejected.
"""

import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Final, NamedTuple

from wisp.language import Language
from wisp.rhyme_keys import WordKeys, fold, merge

__all__ = ["WORD", "keys", "keys_of", "readings", "stressed_vowel"]

WORD: Final = re.compile(r"[a-záéíóúüñ]+")

_DATA: Final = Path(__file__).resolve().parent / "data"
_KNOWN_FILE: Final = _DATA / "known_words_es.txt"
_ACCENTS_FILE: Final = _DATA / "accents_es.txt"

_VOWELS: Final = frozenset("aeiouáéíóúü")
_STRONG: Final = frozenset("aeoáéó")
_ACCENTED: Final = frozenset("áéíóú")
_ALONE: Final = frozenset("íú")
_FRONT: Final = frozenset("eéií")
_PLAIN_STRESS_ENDINGS: Final = frozenset("aeiouns")
_VOWEL_SOUNDS: Final = {
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "y": "i",
}  # fmt: skip
_PAIR_SOUNDS: Final = {"ch": "C", "ll": "y", "rr": "R"}
_CONSONANT_SOUNDS: Final = {
    "v": "b", "z": "s", "j": "x", "G": "g", "q": "k", "x": "ks", "w": "u",
}  # fmt: skip
_FINAL_WEAK_SOUNDS: Final = {"i": "e", "u": "o"}


class _Letter(NamedTuple):
    """A letter that is heard, and whether it is a vowel here."""

    char: str
    vowel: bool


class _Reading(NamedTuple):
    """A spelling split into heard letters and vowel groups, one per syllable."""

    letters: list[_Letter]
    groups: list[list[int]]
    stressed_group: int
    stressed: int


# ---
# Syllables and stress
# ---


def _letters(spelling: str) -> list[_Letter]:
    """The heard letters of a spelling.

    h is silent outside ch. The u of que, qui, gue and gui is silent, its q
    becoming k and its g a hard G. y is a vowel when it is the whole word or no
    vowel follows it.
    """
    letters: list[_Letter] = []
    for index, char in enumerate(spelling):
        before = spelling[index - 1] if index else ""
        after = spelling[index + 1 : index + 2]
        if char == "h" and before != "c":
            continue
        if char == "u" and before in ("q", "g") and after in _FRONT:
            letters[-1] = _Letter("k" if before == "q" else "G", vowel=False)
            continue
        if char == "y":
            vowel = len(spelling) == 1 or after not in _VOWELS
            letters.append(_Letter(char, vowel))
            continue
        letters.append(_Letter(char, char in _VOWELS))
    return letters


def _groups(letters: list[_Letter]) -> list[list[int]]:
    """The vowel groups, as letter indices.

    Neighbouring vowels join, except that a stressed í or ú stands alone and
    two strong vowels never share a group.
    """
    groups: list[list[int]] = []
    current: list[int] = []
    for index, letter in enumerate(letters):
        if not letter.vowel:
            if current:
                groups.append(current)
            current = []
            continue
        if current and (
            letter.char in _ALONE
            or letters[current[-1]].char in _ALONE
            or (
                letter.char in _STRONG
                and any(letters[other].char in _STRONG for other in current)
            )
        ):
            groups.append(current)
            current = []
        current.append(index)
    if current:
        groups.append(current)
    return groups


def _stressed_group(
    spelling: str, letters: list[_Letter], groups: list[list[int]]
) -> int:
    """Which vowel group carries the stress."""
    if spelling.endswith("mente") and len(groups) > 2:
        return len(groups) - 2
    accented = [
        number
        for number, group in enumerate(groups)
        if any(letters[index].char in _ACCENTED for index in group)
    ]
    if accented:
        return accented[-1]
    if len(groups) == 1:
        return 0
    if spelling[-1] in _PLAIN_STRESS_ENDINGS:
        return len(groups) - 2
    return len(groups) - 1


def _main_vowel(letters: list[_Letter], group: list[int]) -> int:
    """The vowel a group is heard on: accented, else strong, else the last."""
    accented = [index for index in group if letters[index].char in _ACCENTED]
    strong = [index for index in group if letters[index].char in _STRONG]
    return (accented or strong or group[-1:])[0]


def _read(spelling: str) -> _Reading | None:
    """A spelling's letters, vowel groups and stress; None when it cannot be read."""
    spelling = unicodedata.normalize("NFC", spelling).lower()
    if not WORD.fullmatch(spelling):
        return None
    letters = _letters(spelling)
    groups = _groups(letters)
    if not groups:
        return None
    stressed_group = _stressed_group(spelling, letters, groups)
    stressed = _main_vowel(letters, groups[stressed_group])
    return _Reading(letters, groups, stressed_group, stressed)


# ---
# Sounds
# ---


def _vowel_sound(char: str) -> str:
    """A vowel letter as it is heard: accents and diaeresis dropped, y as i."""
    return _VOWEL_SOUNDS.get(char, char)


def _sound(letters: list[_Letter], start: int) -> str:
    """The normalised sound of the letters from `start` to the end."""
    sounds: list[str] = []
    index = start
    while index < len(letters):
        char, vowel = letters[index]
        after = letters[index + 1].char if index + 1 < len(letters) else ""
        if vowel:
            sounds.append(_vowel_sound(char))
        elif char + after in _PAIR_SOUNDS:
            sounds.append(_PAIR_SOUNDS[char + after])
            index += 1
        elif char == "c":
            sounds.append("s" if after in _FRONT else "k")
        elif char == "g":
            sounds.append("x" if after in _FRONT else "g")
        else:
            sounds.append(_CONSONANT_SOUNDS.get(char, char))
        index += 1
    return "".join(sounds)


def stressed_vowel(spelling: str) -> str | None:
    """The stressed vowel of a spelling, plain; None when it cannot be read."""
    reading = _read(spelling)
    if reading is None:
        return None
    return _vowel_sound(reading.letters[reading.stressed].char)


def keys_of(spelling: str) -> WordKeys | None:
    """The rhyme keys of one spelling, known word or not.

    The perfect key (rima consonante) is the sound from the stressed vowel to
    the end. The slant key (rima asonante) is the stressed vowel and the main
    vowel of the last group after it, a final i heard as e and u as o.
    """
    reading = _read(spelling)
    if reading is None:
        return None
    letters, groups, stressed_group, stressed = reading
    slant = _vowel_sound(letters[stressed].char)
    if stressed_group < len(groups) - 1:
        last = _vowel_sound(letters[_main_vowel(letters, groups[-1])].char)
        slant += _FINAL_WEAK_SOUNDS.get(last, last)
    return WordKeys(
        whole=frozenset({_sound(letters, 0)}),
        perfect=frozenset({_sound(letters, stressed)}),
        slant=frozenset({slant}),
    )


# ---
# Known words
# ---


@cache
def _known() -> frozenset[str]:
    """Every Spanish word a player may use."""
    return frozenset(_KNOWN_FILE.read_text(encoding="utf-8").split())


@cache
def _accents() -> dict[str, tuple[str, ...]]:
    """Each unaccented spelling and the accented known words it can stand for."""
    lines = _ACCENTS_FILE.read_text(encoding="utf-8").splitlines()
    return {
        unaccented: tuple(accented.split())
        for unaccented, accented in (line.split("\t") for line in lines)
    }


def readings(word: str) -> tuple[str, ...]:
    """The known spellings `word` can be read as; empty when it is unknown.

    A word that carries an accent is only itself. An unaccented one is itself
    when known, plus the accented twins the accent map lists for it.
    """
    word = unicodedata.normalize("NFC", word)
    own = (word,) if word in _known() else ()
    if fold(word, language=Language.ES) != word:
        return own
    return own + _accents().get(word, ())


def keys(word: str) -> WordKeys | None:
    """The keys of every reading of `word`; None when it is not a known word."""
    return merge(keys_of(reading) for reading in readings(word))
