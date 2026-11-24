"""Tests for Spanish rhyme keys, readings and Wisp's Spanish picks."""

import random
from pathlib import Path

import pytest

from wisp import rhymes, rhymes_es
from wisp.language import Language
from wisp.rhyme_keys import RhymeKind, compare
from wisp.rhymes import clean_word, opening_word, rhyme_kind, wisp_reply
from wisp.rhymes_es import keys_of, readings, stressed_vowel
from wisp.rules import (
    RHYME_OPENER_MIN_LETTERS,
    RHYME_OPENER_RHYMES,
    RHYME_OPENER_SKIP_TOP,
    Stage,
)

ROOT = Path(__file__).resolve().parent.parent

PERFECT = [
    ("canción", "corazón"), ("amor", "dolor"), ("cielo", "pelo"), ("luna", "cuna"),
    ("casa", "masa"), ("única", "túnica"), ("calle", "valle"), ("calle", "raye"),
    ("lava", "baba"), ("guerra", "tierra"), ("pingüino", "camino"),
    ("quiso", "piso"), ("guiso", "piso"), ("queso", "beso"), ("país", "maíz"),
    ("día", "tía"), ("poeta", "meta"), ("rey", "ley"), ("hoy", "voy"),
    ("muy", "fui"), ("ciudad", "verdad"), ("cuidado", "olvidado"),
    ("lentamente", "gente"), ("gente", "mente"), ("estás", "jamás"),
    ("noche", "coche"), ("fuego", "juego"), ("huevo", "nuevo"), ("hielo", "cielo"),
    ("mar", "amar"), ("camión", "canción"), ("guion", "camión"), ("leer", "creer"),
    ("construir", "vivir"), ("reír", "vivir"), ("ahumado", "cansado"),
]  # fmt: skip
SLANT = [
    ("casa", "cama"), ("casa", "casas"), ("música", "única"), ("patio", "radio"),
    ("patio", "barco"), ("gloria", "sombra"), ("pálido", "llano"),
    ("rápido", "cántaro"), ("venus", "beso"), ("tribu", "libro"), ("tesis", "mece"),
    ("día", "vida"), ("rápidamente", "siempre"), ("perro", "pero"),
    ("fuego", "beso"), ("aire", "baile"), ("árbol", "mármol"),
]  # fmt: skip
HOMOPHONES = [("casa", "caza"), ("hola", "ola"), ("vaca", "baca"), ("gente", "jente")]
NONE = [
    ("árbol", "cielo"), ("sol", "mar"), ("joven", "examen"), ("útil", "fácil"),
    ("régimen", "imagen"),
]  # fmt: skip


def _common_es() -> tuple[str, ...]:
    return rhymes._common(Language.ES)


# ---
# Keys from spelling
# ---


@pytest.mark.parametrize(("first", "second"), PERFECT)
def test_spanish_perfect_rhymes(first: str, second: str) -> None:
    assert compare(keys_of(first), keys_of(second)) is RhymeKind.PERFECT


@pytest.mark.parametrize(("first", "second"), SLANT)
def test_spanish_slant_rhymes(first: str, second: str) -> None:
    assert compare(keys_of(first), keys_of(second)) is RhymeKind.SLANT


@pytest.mark.parametrize(("first", "second"), HOMOPHONES)
def test_spanish_homophones_are_not_rhymes(first: str, second: str) -> None:
    assert compare(keys_of(first), keys_of(second)) is None


@pytest.mark.parametrize(("first", "second"), NONE)
def test_spanish_non_rhymes(first: str, second: str) -> None:
    assert compare(keys_of(first), keys_of(second)) is None


@pytest.mark.parametrize(
    ("word", "stressed"),
    [("guion", "o"), ("ciudad", "a"), ("fui", "i"), ("rápidamente", "e"),
     ("estoy", "o"), ("muy", "i"), ("búho", "u"), ("ahora", "o")],
)  # fmt: skip
def test_spanish_stressed_vowel(word: str, stressed: str) -> None:
    assert stressed_vowel(word) == stressed


@pytest.mark.parametrize("spelling", ["", "fuego2", "dos palabras", "hhh", "brr"])
def test_unreadable_spellings_have_no_keys(spelling: str) -> None:
    assert keys_of(spelling) is None


# ---
# Readings
# ---


def test_unknown_spanish_word_rejected() -> None:
    assert rhyme_kind("fuego", "xuego", language=Language.ES) is None


def test_unaccented_spanish_word_reads_as_accented() -> None:
    assert rhyme_kind("canción", "corazon", language=Language.ES) is RhymeKind.PERFECT


def test_esta_reads_both_ways() -> None:
    assert set(readings("esta")) == {"esta", "está"}


def test_an_accented_word_is_never_expanded() -> None:
    assert readings("público") == ("público",)


def test_a_common_unaccented_word_keeps_its_own_reading() -> None:
    assert readings("casa") == ("casa",)


def test_an_unaccented_repeat_is_the_same_word() -> None:
    assert rhyme_kind("corazón", "corazon", language=Language.ES) is None


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("¡fuego!", "fuego"),
        ("¿qué?", "qué"),
        ("**Fuego**", "fuego"),
        ("canción", "canción"),
        ("«Año»", "año"),
        ("dos palabras", None),
        ("fuego2", None),
    ],
)
def test_clean_spanish_word(text: str, word: str | None) -> None:
    assert clean_word(text, language=Language.ES) == word


# ---
# Wisp's picks
# ---


def test_wisp_never_answers_a_used_word_in_another_spelling() -> None:
    rng = random.Random(3)
    for turn in range(200):
        reply = wisp_reply(
            "corazón", {"cancion"}, Stage.ADULT, turn, rng, language=Language.ES
        )
        assert reply != "canción"


def test_wisp_answers_spanish_with_perfect_common_rhymes_only() -> None:
    rng = random.Random(5)
    common = set(_common_es())
    used = {"fuego"}
    replies = []
    for _ in range(200):
        reply = wisp_reply("fuego", used, Stage.ROCKSTAR, 1, rng, language=Language.ES)
        if reply is None:
            continue
        assert reply in common
        assert reply not in used
        assert rhyme_kind("fuego", reply, language=Language.ES) is RhymeKind.PERFECT
        fuego, answer = rhymes_es.keys("fuego"), rhymes_es.keys(reply)
        assert fuego is not None and answer is not None
        assert not fuego.whole & answer.whole
        used.add(reply)
        replies.append(reply)
    every_rhyme = {
        other
        for other in common
        if rhyme_kind("fuego", other, language=Language.ES) is RhymeKind.PERFECT
    }
    assert len(replies) >= 5
    assert set(replies) == every_rhyme


def test_spanish_openers_have_rhymes_and_skip_function_words() -> None:
    common = _common_es()
    top = set(common[:RHYME_OPENER_SKIP_TOP])
    rng = random.Random(11)
    picks = [opening_word(rng, language=Language.ES) for _ in range(50)]
    for word in set(picks):
        rhymed = [
            other
            for other in common
            if rhyme_kind(word, other, language=Language.ES) is RhymeKind.PERFECT
        ]
        assert word in common
        assert len(word) >= RHYME_OPENER_MIN_LETTERS
        assert word not in top
        assert len(rhymed) >= RHYME_OPENER_RHYMES, word
    assert len(set(picks)) > 1
    assert not {"la", "que", "el", "los", "por"} & set(picks)


# ---
# The word lists
# ---


def test_spanish_common_list_hygiene() -> None:
    common = _common_es()
    known = rhymes_es._known()
    assert 4500 <= len(common) <= 5500
    assert len(set(common)) == len(common)
    assert all(keys_of(word) for word in common)
    assert set(common) <= known
    assert not {"madrid", "méxico", "maría", "puta", "mierda"} & set(common)
    assert not {"love", "game", "the"} & known
    assert not {"cancion", "corazon", "tambien"} & known


def test_spanish_accent_map_reaches_known_words() -> None:
    known = rhymes_es._known()
    accents = rhymes_es._accents()
    assert accents["cancion"] == ("canción",)
    for spellings in accents.values():
        assert set(spellings) <= known


def test_no_wordfreq_at_runtime() -> None:
    sources = [*(ROOT / "wisp").rglob("*.py"), *(ROOT / "cogs").rglob("*.py")]
    assert not [
        path for path in sources if "wordfreq" in path.read_text(encoding="utf-8")
    ]
