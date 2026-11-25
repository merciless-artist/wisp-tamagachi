"""Build the pronunciation files in wisp/data/ that widen the Rhyme Duel.

Run from the repo root, as a module so `wisp` imports, after putting the raw
downloads in tools/raw/ (gitignored):

    PYTHONUTF8=1 .venv/Scripts/python -m tools.build_pronunciations <en|es|fr>

Then rebuild that language's word lists with `tools.build_common_words`, so
its accent map reaches the new words too.

- **en** reads WikiPron's English (US) broad list,
  `tools/raw/wikipron/eng_latn_us_broad.tsv`, from
  https://github.com/CUNY-CL/wikipron (data/scrape/tsv). It keeps the
  lowercase words the CMU dictionary lacks, maps their IPA to ARPAbet and
  writes `wisp/data/wikipron_en.txt`, `word<TAB>phones<TAB>phones...`.
  WikiPron drops stress, so one vowel per reading is marked stressed (1) and
  the rest unstressed (0); see `stressed_vowel`. A reading with a segment the
  map does not know is left out rather than guessed.
- **es** reads WikiPron's Spanish (Latin American) broad list,
  `tools/raw/wikipron/spa_latn_la_broad.tsv`, and writes the words the
  spelling rules can read to `wisp/data/wikipron_es.txt`, one per line. The
  rules, not the IPA, give their sounds: Spanish spelling is phonetic, and
  the Latin American list matches the rules' seseo and yeísmo.
- **fr** reads Lexique 3.83 (http://www.lexique.org),
  `tools/raw/lexique/Lexique383.tsv`, and writes every single-word form with
  its `phon` readings, mapped to the one-character phones of
  `wisp.rhymes_fr`, to `wisp/data/lexique_fr.txt`,
  `word<TAB>reading<TAB>reading...`.

Spanish and French leave out words that are really English, by the same
wordfreq test as the known word lists (`build_common_words.english`), so
`love` and `game` stay unknown.
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Final

import pronouncing

from tools.build_common_words import english
from wisp import rhymes_es, rhymes_fr
from wisp.language import Language

ROOT: Final = Path(__file__).resolve().parent.parent
RAW: Final = ROOT / "tools/raw"
DATA: Final = ROOT / "wisp/data"
LEXIQUE: Final = RAW / "lexique/Lexique383.tsv"
WIKIPRON_EN: Final = RAW / "wikipron/eng_latn_us_broad.tsv"
WIKIPRON_ES: Final = RAW / "wikipron/spa_latn_la_broad.tsv"
LEXIQUE_OUTPUT: Final = DATA / "lexique_fr.txt"
WIKIPRON_EN_OUTPUT: Final = DATA / "wikipron_en.txt"
WIKIPRON_ES_OUTPUT: Final = DATA / "wikipron_es.txt"

_ENGLISH_WORD: Final = re.compile(r"[a-z]+(?:'[a-z]+)*")


def _rows(path: Path) -> Iterator[list[str]]:
    """The rows of a tab-separated file, read as UTF-8 without quoting."""
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)


def _grouped(pairs: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    """Each word and its distinct readings, in the order first seen."""
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for word, reading in pairs:
        if reading not in grouped[word]:
            grouped[word].append(reading)
    return dict(grouped)


def _write(path: Path, lines: list[str]) -> None:
    """Write `lines` to `path`, one per line, with Unix line endings."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {len(lines)} lines ({path.stat().st_size:,} bytes) to {path}")


# ---
# English
# ---

DIPHTHONGS: Final = {
    ("a", "ɪ"): "AY",
    ("a", "ʊ"): "AW",
    ("e", "ɪ"): "EY",
    ("o", "ʊ"): "OW",
    ("ɔ", "ɪ"): "OY",
    ("ɜ", "ɹ"): "ER",
    ("ə", "ɹ"): "ER",
}
VOWELS: Final = {
    "i": "IY", "ɪ": "IH", "ɨ": "IH", "ᵻ": "IH", "e": "EY", "ɛ": "EH", "æ": "AE",
    "a": "AA", "ɑ": "AA", "ɒ": "AA", "ɔ": "AO", "o": "OW", "ɵ": "OW", "ʊ": "UH",
    "u": "UW", "ʉ": "UW", "ʌ": "AH", "ə": "AH", "ɐ": "AH", "ɘ": "AH", "ɚ": "ER",
    "ɝ": "ER", "ɜ": "ER",
}  # fmt: skip
SYLLABIC: Final = {"l̩": "L", "n̩": "N", "m̩": "M"}
CONSONANTS: Final = {
    "p": "P", "b": "B", "t": "T", "d": "D", "k": "K", "ɡ": "G", "f": "F", "v": "V",
    "θ": "TH", "ð": "DH", "s": "S", "z": "Z", "ʃ": "SH", "ʒ": "ZH", "h": "HH",
    "t͡ʃ": "CH", "d͡ʒ": "JH", "m": "M", "n": "N", "ŋ": "NG", "l": "L", "ɫ": "L",
    "ɹ": "R", "j": "Y", "w": "W", "ʍ": "W", "x": "K", "ɾ": "T", "ʔ": "T",
    "ɾ̃": "N",
}  # fmt: skip
WEAK: Final = frozenset({"ə", "ɚ", "ɐ", "ɘ"})
LIGHT: Final = frozenset({"ɪ", "ɨ", "ᵻ", "ʊ"})
_LENGTH: Final = "ː"
_OFFGLIDE: Final = "̯"


def _ipa_segments(transcription: str) -> list[str]:
    """WikiPron's space-separated segments without length marks.

    An offglide (ɪ̯) is read as the plain vowel, so it joins a diphthong.
    """
    return [
        segment.replace(_LENGTH, "").replace(_OFFGLIDE, "")
        for segment in transcription.split()
    ]


def _english_vowels(segments: list[str]) -> list[tuple[str, str]] | None:
    """Each segment group as (ARPAbet phone, IPA source); None on an unknown one.

    Diphthongs join two segments; a syllabic consonant is schwa plus the
    consonant, with the schwa as its source.
    """
    phones: list[tuple[str, str]] = []
    index = 0
    while index < len(segments):
        segment = segments[index]
        pair = (segment, segments[index + 1]) if index + 1 < len(segments) else None
        if pair in DIPHTHONGS:
            phones.append((DIPHTHONGS[pair], segment))
            index += 2
            continue
        if segment in SYLLABIC:
            phones.extend((("AH", "ə"), (SYLLABIC[segment], "")))
        elif segment in VOWELS:
            phones.append((VOWELS[segment], segment))
        elif segment in CONSONANTS:
            phones.append((CONSONANTS[segment], ""))
        else:
            return None
        index += 1
    return phones


def stressed_vowel(sources: list[str]) -> int:
    """Which vowel (an index into `sources`, the vowels' IPA) takes the stress.

    WikiPron has no stress marks. CMU rhymes from the last vowel with primary
    or secondary stress, and unstressed English vowels are mostly reduced, so
    the stress goes on the last full vowel: not a schwa (WEAK), not a lax ɪ
    or ʊ (LIGHT), and not a word-final i (happy). With no full vowel it goes
    on the first LIGHT one (city, visit), then on a final i (agree), then on
    the first vowel.
    """
    last = len(sources) - 1
    full = [
        index
        for index, source in enumerate(sources)
        if source not in WEAK | LIGHT and not (source == "i" and index == last > 0)
    ]
    if full:
        return full[-1]
    light = [index for index, source in enumerate(sources) if source in LIGHT]
    if light:
        return light[0]
    if sources[last] == "i":
        return last
    return 0


def arpabet(transcription: str) -> str | None:
    """A WikiPron IPA reading in ARPAbet with stress digits; None when unmapped."""
    phones = _english_vowels(_ipa_segments(transcription))
    if phones is None:
        return None
    vowel_sources = [source for _, source in phones if source]
    if not vowel_sources:
        return None
    stressed = stressed_vowel(vowel_sources)
    marked: list[str] = []
    vowel = 0
    for phone, source in phones:
        if source:
            marked.append(phone + ("1" if vowel == stressed else "0"))
            vowel += 1
        else:
            marked.append(phone)
    return " ".join(marked)


def english_lines() -> list[str]:
    """`word<TAB>readings` for each WikiPron word CMU lacks, in word order."""
    pairs = (
        (word, reading)
        for word, transcription in _rows(WIKIPRON_EN)
        if _ENGLISH_WORD.fullmatch(word) and not pronouncing.phones_for_word(word)
        if (reading := arpabet(transcription)) is not None
    )
    grouped = _grouped(pairs)
    return [f"{word}\t" + "\t".join(grouped[word]) for word in sorted(grouped)]


# ---
# Spanish
# ---


def spanish_lines() -> list[str]:
    """Every WikiPron Spanish word the spelling rules can read, sorted."""
    words = {
        word
        for word, _ in _rows(WIKIPRON_ES)
        if rhymes_es.WORD.fullmatch(word)
        and rhymes_es.keys_of(word) is not None
        and not english(word, Language.ES)
    }
    return sorted(words)


# ---
# French
# ---

LEXIQUE_PHONES: Final = {
    "a": "a", "e": "e", "E": "E", "i": "i", "o": "o", "O": "o", "u": "u", "y": "y",
    "2": "2", "9": "2", "°": "@", "@": "A", "§": "O", "5": "I", "1": "I", "j": "j",
    "w": "w", "8": "H", "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "g",
    "f": "f", "v": "v", "s": "s", "z": "z", "m": "m", "n": "n", "l": "l", "S": "S",
    "Z": "Z", "N": "N", "G": "N", "R": "R", "x": "R", "h": "",
}  # fmt: skip
"""Lexique's phon alphabet in `rhymes_fr` phones.

The open and closed o (O, o) and eu (9, 2) merge, as the spelling rules do;
un (1) is in (5); the English ng (G) is gn and the Spanish jota (x) is R.
"""

_HEARD_VOWELS: Final = frozenset("aeEiouy2AIO")


def french_reading(phon: str) -> str | None:
    """A Lexique phon field in `rhymes_fr` phones; None when it has no vowel.

    A final schwa after a heard vowel is dropped (blanche, bl@S°, is blAS);
    one that is the only vowel is a final schwa, 2 (le). Doubled phones are
    one, like the spelling rules read them.
    """
    if any(char not in LEXIQUE_PHONES for char in phon):
        return None
    phones = "".join(LEXIQUE_PHONES[char] for char in phon)
    if phones.endswith("@"):
        body = phones[:-1]
        phones = body if _HEARD_VOWELS & set(body) else body + "2"
    phones = re.sub(r"(.)\1+", r"\1", phones)
    return phones if _HEARD_VOWELS & set(phones) else None


def french_lines() -> list[str]:
    """`word<TAB>readings` for every single-word Lexique form, in word order."""
    rows = _rows(LEXIQUE)
    header = next(rows)
    ortho, phon = header.index("ortho"), header.index("phon")
    pairs = (
        (word, reading)
        for row in rows
        if rhymes_fr.WORD.fullmatch(word := row[ortho])
        and rhymes_fr.tail(word) == word
        and not english(word, Language.FR)
        if (reading := french_reading(row[phon])) is not None
    )
    grouped = _grouped(pairs)
    return [f"{word}\t" + "\t".join(grouped[word]) for word in sorted(grouped)]


# ---
# Building
# ---

BUILDS: Final[dict[str, tuple[Callable[[], list[str]], Path]]] = {
    "en": (english_lines, WIKIPRON_EN_OUTPUT),
    "es": (spanish_lines, WIKIPRON_ES_OUTPUT),
    "fr": (french_lines, LEXIQUE_OUTPUT),
}


def main(argv: list[str]) -> None:
    """Build one language's pronunciation file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("language", choices=sorted(BUILDS))
    lines, output = BUILDS[parser.parse_args(argv).language]
    _write(output, lines())


if __name__ == "__main__":
    main(sys.argv[1:])
