"""Tests for the Rhyme Duel's words in each language and the language picker."""

import dataclasses
import re
import unicodedata
from string import Formatter

import pytest

from wisp.duel_text import DUEL_TEXT, LANGUAGE_PICKER, DuelText
from wisp.language import Language

FIELDS = {
    "word_line": {"word"},
    "timed_out": set(),
    "not_one_word": set(),
    "already_used": {"answer"},
    "no_rhyme_with": {"answer", "word"},
    "score_line": {"points"},
    "point": set(),
    "points_noun": set(),
    "picked": set(),
}


def placeholders(text: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(text) if field is not None}


def texts(duel_text: DuelText) -> dict[str, str]:
    return {
        field.name: getattr(duel_text, field.name)
        for field in dataclasses.fields(duel_text)
        if isinstance(getattr(duel_text, field.name), str)
    }


# ---
# English
# ---


def test_english_duel_text_is_unchanged() -> None:
    en = DUEL_TEXT[Language.EN]
    assert en.word_line.format(word="**fire**") == "・The word to rhyme is: **fire**"
    assert (en.timed_out, en.not_one_word) == ("Time ran out", "That wasn't one word")
    assert en.already_used.format(answer="hat") == "hat was already used"
    assert (
        en.no_rhyme_with.format(answer="dog", word="fire")
        == "dog doesn't rhyme with fire"
    )
    assert en.score_line.format(points=en.points(3)) == "・Score: 3 points"
    assert en.points(1) == "1 point" and en.points(0) == "0 points"


# ---
# Every language
# ---


def test_every_language_has_duel_text() -> None:
    assert set(DUEL_TEXT) == set(Language)


@pytest.mark.parametrize(
    ("language", "zero", "one", "two"),
    [
        (Language.EN, "0 points", "1 point", "2 points"),
        (Language.ES, "0 puntos", "1 punto", "2 puntos"),
        (Language.FR, "0 point", "1 point", "2 points"),
    ],
)
def test_points_pluralise_per_language(
    language: Language, zero: str, one: str, two: str
) -> None:
    duel_text = DUEL_TEXT[language]
    assert (duel_text.points(0), duel_text.points(1), duel_text.points(2)) == (
        zero,
        one,
        two,
    )


@pytest.mark.parametrize(
    ("language", "word_line", "score_line", "picked"),
    [
        (
            Language.ES,
            "・La palabra para rimar es: **fuego**",
            "・Puntuación: 2 puntos",
            "♪ Rimamos en español.",
        ),
        (
            Language.FR,
            "・Le mot à faire rimer, c'est **fuego**",
            "・Score : 2 points",
            "♪ On rime en français.",
        ),
        (
            Language.EN,
            "・The word to rhyme is: **fuego**",
            "・Score: 2 points",
            "♪ We rhyme in English.",
        ),
    ],
)
def test_duel_text_reads_as_the_spec_writes_it(
    language: Language, word_line: str, score_line: str, picked: str
) -> None:
    duel_text = DUEL_TEXT[language]
    assert duel_text.word_line.format(word="**fuego**") == word_line
    assert duel_text.score_line.format(points=duel_text.points(2)) == score_line
    assert duel_text.picked == picked


@pytest.mark.parametrize(
    ("language", "verdicts"),
    [
        (
            Language.ES,
            (
                "Se acabó el tiempo",
                "Eso no era una sola palabra",
                "amor ya se usó",
                "sol no rima con mar",
            ),
        ),
        (
            Language.FR,
            (
                "Le temps est écoulé",
                "Ce n'était pas un seul mot",
                "amour a déjà été dit",
                "sol ne rime pas avec mar",
            ),
        ),
    ],
)
def test_verdicts_read_as_the_spec_writes_them(
    language: Language, verdicts: tuple[str, str, str, str]
) -> None:
    duel_text = DUEL_TEXT[language]
    answer = "amor" if language is Language.ES else "amour"
    assert (
        duel_text.timed_out,
        duel_text.not_one_word,
        duel_text.already_used.format(answer=answer),
        duel_text.no_rhyme_with.format(answer="sol", word="mar"),
    ) == verdicts


@pytest.mark.parametrize("language", list(Language))
def test_duel_text_takes_its_fields(language: Language) -> None:
    assert {
        name: placeholders(text) for name, text in texts(DUEL_TEXT[language]).items()
    } == FIELDS


@pytest.mark.parametrize("language", list(Language))
def test_duel_text_follows_the_line_rules(language: Language) -> None:
    for text in texts(DUEL_TEXT[language]).values():
        assert "—" not in text and "–" not in text, text
        assert " " not in text and " " not in text, text
        assert "‍" not in text and "️" not in text, text
        assert "\n" not in text, text
        for char in text:
            assert char == "♪" or unicodedata.category(char) != "So", text


def test_french_duel_text_spaces_before_its_marks() -> None:
    for text in texts(DUEL_TEXT[Language.FR]).values():
        assert not re.search(r"[^ ][!?:]", text), text


# ---
# The language picker
# ---


def test_language_picker_text() -> None:
    assert LANGUAGE_PICKER == (
        "♪ Which language should we rhyme in?\n"
        "・¿En qué idioma rimamos?\n"
        "・On rime en quelle langue ?\n"
        "・Change it any time with /wisp play rhyme."
    )
    assert " " not in LANGUAGE_PICKER and " " not in LANGUAGE_PICKER
