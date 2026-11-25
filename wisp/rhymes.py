"""Perfect and slant rhyme checks, and the rhymes Wisp picks himself.

Every language turns a word into `WordKeys`, and `compare` decides how two
words rhyme from them. English pronunciations come from the CMU Pronouncing
Dictionary, and for words it lacks from WikiPron's English (US) list (from
Wiktionary, CC BY-SA 4.0) in `data/`, mapped to the same phones: a word's
rhyme is its phones from the last stressed vowel to the end, with the stress
marks dropped. Spanish and French keys come from spelling
rules in `rhymes_es` and `rhymes_fr`. Wisp only ever answers with words from
his language's common word list in `data/`.
"""

import random
import re
import string
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Final

import pronouncing

from wisp import rhymes_es, rhymes_fr
from wisp.language import Language
from wisp.rhyme_keys import RhymeKind, WordKeys, compare, fold
from wisp.rules import (
    MAX_WORD_LENGTH,
    RHYME_OPENER_MIN_LETTERS,
    RHYME_OPENER_RHYMES,
    RHYME_OPENER_SKIP_TOP,
    RHYME_PERFECT_POINTS,
    RHYME_SKILL,
    RHYME_SLANT_POINTS,
    RHYME_SURE_TURNS,
    RHYME_TIRING,
    Stage,
)

__all__ = [
    "EDGE",
    "ENGLISH_WORD",
    "RhymeKind",
    "WordKeys",
    "clean_word",
    "compare",
    "fold",
    "keys",
    "opening_word",
    "rhyme_chance",
    "rhyme_kind",
    "same_word_key",
    "score",
    "wisp_reply",
]

_DATA: Final = Path(__file__).resolve().parent / "data"
_WORD_FILES: Final[dict[Language, Path]] = {
    Language.EN: _DATA / "common_words.txt",
    Language.ES: _DATA / "common_words_es.txt",
    Language.FR: _DATA / "common_words_fr.txt",
}
_WIKIPRON_EN_FILE: Final = _DATA / "wikipron_en.txt"
ENGLISH_WORD: Final = re.compile(r"[a-z]+(?:'[a-z]+)*")
_WORDS: Final[dict[Language, re.Pattern[str]]] = {
    Language.EN: ENGLISH_WORD,
    Language.ES: rhymes_es.WORD,
    Language.FR: rhymes_fr.WORD,
}
EDGE: Final = string.punctuation + "¡¿«»“”‘’…"
_EDGES: Final = re.compile(rf"^[\s{re.escape(EDGE)}]+|[\s{re.escape(EDGE)}]+$")
_STRESS_MARKS: Final = "012"
_STRESSED: Final = "12"

_POINTS: Final = {
    RhymeKind.PERFECT: RHYME_PERFECT_POINTS,
    RhymeKind.SLANT: RHYME_SLANT_POINTS,
}

# ---
# English keys
# ---


def _rhyme_part(phones: str) -> str:
    """The phones from the last stressed vowel on, without stress marks.

    A word with no stressed vowel rhymes from its last vowel.
    """
    split = phones.split()
    vowels = [index for index, phone in enumerate(split) if phone[-1].isdigit()]
    stressed = [index for index in vowels if split[index][-1] in _STRESSED]
    start = (stressed or vowels or [0])[-1]
    return " ".join(phone.rstrip(_STRESS_MARKS) for phone in split[start:])


@cache
def _wikipron_english() -> dict[str, str]:
    """Each WikiPron word CMU lacks and its tab-separated ARPAbet readings."""
    lines = _WIKIPRON_EN_FILE.read_text(encoding="utf-8").splitlines()
    return dict(line.split("\t", 1) for line in lines)


def _english_pronunciations(word: str) -> list[str]:
    """A word's CMU pronunciations, else its WikiPron ones; empty when unknown."""
    cmu: list[str] = pronouncing.phones_for_word(word)
    if cmu:
        return cmu
    wikipron = _wikipron_english().get(word)
    return wikipron.split("\t") if wikipron else []


def _english_keys(word: str) -> WordKeys | None:
    """The keys of every pronunciation of a word; None when it is unknown.

    The slant key is the rhyme's stressed vowel.
    """
    pronunciations = _english_pronunciations(word)
    if not pronunciations:
        return None
    rhymes = frozenset(_rhyme_part(phones) for phones in pronunciations)
    return WordKeys(
        whole=frozenset(
            " ".join(phone.rstrip(_STRESS_MARKS) for phone in phones.split())
            for phones in pronunciations
        ),
        perfect=rhymes,
        slant=frozenset(rhyme.split()[0] for rhyme in rhymes),
    )


_KEYS: Final[dict[Language, Callable[[str], WordKeys | None]]] = {
    Language.EN: _english_keys,
    Language.ES: rhymes_es.keys,
    Language.FR: rhymes_fr.keys,
}

# ---
# Rhyme checks
# ---


def keys(word: str, *, language: Language) -> WordKeys | None:
    """What `word` sounds like in `language`; None when it cannot be read."""
    return _KEYS[language](word)


def same_word_key(word: str, *, language: Language) -> str:
    """The spelling two words share when they are the same word.

    French compares only the part after an elision, so l'été is été.
    """
    if language is Language.FR:
        word = rhymes_fr.tail(word)
    return fold(word, language=language)


def rhyme_kind(first: str, second: str, *, language: Language) -> RhymeKind | None:
    """How two words rhyme in `language`, comparing every pair of their readings.

    None when either word is unknown, they are the same word, they can sound
    exactly alike (right, write) or they do not rhyme. PERFECT when they match
    from the stressed vowel to the end, SLANT when only the looser key does.
    """
    first, second = first.lower(), second.lower()
    if same_word_key(first, language=language) == same_word_key(
        second, language=language
    ):
        return None
    return compare(keys(first, language=language), keys(second, language=language))


def score(kind: RhymeKind) -> int:
    """Points a player's rhyme earns."""
    return _POINTS[kind]


def clean_word(text: str, *, language: Language) -> str | None:
    """The single lowercase word in a message, or None when it is not one word.

    The text is NFC-normalised, curly apostrophes become straight, and
    whitespace and punctuation, Unicode ones included, are dropped from both
    ends. Anything longer than MAX_WORD_LENGTH is not a word.
    """
    lowered = unicodedata.normalize("NFC", text).lower().replace("’", "'")
    word = _EDGES.sub("", lowered)
    if len(word) > MAX_WORD_LENGTH or not _WORDS[language].fullmatch(word):
        return None
    return word


# ---
# Wisp's picks
# ---


@cache
def _common(language: Language) -> tuple[str, ...]:
    """Wisp's own words in `language`, most frequent first."""
    return tuple(_WORD_FILES[language].read_text(encoding="utf-8").split())


@cache
def _common_keys(language: Language) -> dict[str, WordKeys]:
    """The keys of every common word that can be read."""
    read = {word: keys(word, language=language) for word in _common(language)}
    return {
        word: word_keys for word, word_keys in read.items() if word_keys is not None
    }


@cache
def _common_by_perfect(language: Language) -> dict[str, frozenset[str]]:
    """Every common word, grouped by each of its perfect keys."""
    grouped: defaultdict[str, set[str]] = defaultdict(set)
    for word, word_keys in _common_keys(language).items():
        for perfect in word_keys.perfect:
            grouped[perfect].add(word)
    return {perfect: frozenset(words) for perfect, words in grouped.items()}


def _common_rhymes(word: str, used: set[str], language: Language) -> set[str]:
    """The common words that rhyme perfectly with `word`.

    The word itself, words that can sound exactly like it and every spelling
    of a word in `used` are left out.
    """
    word_keys = keys(word, language=language)
    if word_keys is None:
        return set()
    taken = {same_word_key(other, language=language) for other in used | {word}}
    common_keys = _common_keys(language)
    by_perfect = _common_by_perfect(language)
    return {
        other
        for perfect in word_keys.perfect
        for other in by_perfect.get(perfect, frozenset())
        if same_word_key(other, language=language) not in taken
        and compare(word_keys, common_keys[other]) is RhymeKind.PERFECT
    }


@cache
def _openers(language: Language) -> tuple[str, ...]:
    """Common words with enough perfect rhymes to start a duel with.

    Outside English an opener is also long enough and not one of the language's
    most frequent words, which are mostly function words.
    """
    english = language is Language.EN
    shortest = 1 if english else RHYME_OPENER_MIN_LETTERS
    too_common = set() if english else set(_common(language)[:RHYME_OPENER_SKIP_TOP])
    return tuple(
        word
        for word in sorted(_common_keys(language))
        if len(word) >= shortest
        and word not in too_common
        and len(_common_rhymes(word, set(), language)) >= RHYME_OPENER_RHYMES
    )


def opening_word(rng: random.Random, *, language: Language) -> str:
    """The word Wisp starts a duel with."""
    return rng.choice(_openers(language))


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
    word: str,
    used: set[str],
    stage: Stage,
    turn: int,
    rng: random.Random,
    *,
    language: Language,
) -> str | None:
    """Wisp's unused perfect rhyme for `word` on his `turn`, or None when he runs out.

    He finds one with the chance `rhyme_chance` gives him, and only when a
    common word rhymes that is no spelling of a word in `used`.
    """
    if rng.random() >= rhyme_chance(stage, turn):
        return None
    options = sorted(_common_rhymes(word.lower(), used, language))
    return rng.choice(options) if options else None
