"""Tests for French rhyme keys, readings and Wisp's French picks."""

import random
from functools import partial
from pathlib import Path

import pytest

from wisp import rhymes, rhymes_fr
from wisp.language import Language
from wisp.rhyme_keys import RhymeKind, WordKeys, compare
from wisp.rhymes import clean_word, opening_word, rhyme_kind, same_word_key, wisp_reply
from wisp.rhymes_fr import keys_of, phones_of, readings, tail
from wisp.rules import (
    RHYME_OPENER_MIN_LETTERS,
    RHYME_OPENER_RHYMES,
    RHYME_OPENER_SKIP_TOP,
    Stage,
)

ROOT = Path(__file__).resolve().parent.parent
SILENT = rhymes_fr._silent_ent()

PERFECT = [
    ("parler", "aller"), ("été", "côté"), ("beauté", "été"), ("forfait", "bienfait"),
    ("fait", "bienfait"), ("mort", "sort"), ("porte", "sorte"), ("chat", "achat"),
    ("moi", "toi"), ("roi", "loi"), ("mer", "fer"), ("mer", "amer"),
    ("hiver", "enfer"), ("château", "gâteau"), ("temps", "content"),
    ("moment", "vraiment"), ("aiment", "crème"), ("chantent", "plantent"),
    ("raison", "maison"), ("nation", "passion"), ("nation", "camion"),
    ("fille", "famille"), ("soleil", "pareil"), ("soleil", "abeille"),
    ("travail", "détail"), ("yeux", "cieux"), ("fleur", "cœur"), ("fleur", "peur"),
    ("heure", "beurre"), ("chose", "rose"), ("ville", "tranquille"),
    ("nuit", "minuit"), ("nuit", "pluie"), ("lui", "pluie"), ("vie", "envie"),
    ("ami", "parmi"), ("dur", "sûr"), ("amour", "toujours"), ("jour", "tour"),
    ("voix", "fois"), ("noir", "soir"), ("noir", "avoir"), ("cheval", "animal"),
    ("ciel", "miel"), ("bec", "sec"), ("neuf", "œuf"), ("prix", "gris"),
    ("gentil", "outil"), ("croire", "boire"), ("table", "câble"),
    ("sable", "diable"), ("l'été", "côté"), ("lumière", "rivière"),
    ("étoile", "voile"), ("tienne", "vienne"), ("bien", "rien"), ("chien", "lien"),
    ("client", "orient"), ("tient", "vient"), ("respect", "aspect"),
    ("direct", "correct"), ("femme", "flamme"), ("prudemment", "vraiment"),
    ("question", "bastion"), ("monsieur", "mieux"), ("long", "blond"),
]  # fmt: skip
SLANT = [
    ("chanter", "parler"), ("été", "café"), ("lait", "fait"), ("mort", "porte"),
    ("chat", "rat"), ("beau", "peau"), ("bateau", "chapeau"), ("chaud", "faux"),
    ("trop", "mot"), ("loup", "fou"), ("genou", "bijou"), ("hibou", "caillou"),
    ("temps", "vent"), ("enfant", "temps"), ("enfant", "content"), ("pain", "main"),
    ("matin", "chemin"), ("plein", "rein"), ("bon", "pont"), ("feu", "jeu"),
    ("ami", "souris"), ("rue", "vue"), ("plus", "jus"), ("grand", "blanc"),
    ("nez", "assez"), ("chez", "parler"), ("patient", "souvent"), ("os", "dos"),
    ("deux", "eux"),
]  # fmt: skip
HOMOPHONES = [
    ("aller", "allée"), ("vert", "verre"), ("eau", "haut"), ("cou", "coup"),
    ("sang", "cent"), ("brun", "brin"), ("sept", "cette"),
]  # fmt: skip
NONE = [("parlent", "chantent"), ("parlent", "lent")]


def _keys(word: str) -> WordKeys | None:
    return keys_of(tail(word), SILENT)


def _common_fr() -> tuple[str, ...]:
    return rhymes._common(Language.FR)


# ---
# Keys from spelling
# ---


@pytest.mark.parametrize(("first", "second"), PERFECT)
def test_french_perfect_rhymes(first: str, second: str) -> None:
    assert compare(_keys(first), _keys(second)) is RhymeKind.PERFECT


@pytest.mark.parametrize(("first", "second"), SLANT)
def test_french_slant_rhymes(first: str, second: str) -> None:
    assert compare(_keys(first), _keys(second)) is RhymeKind.SLANT


@pytest.mark.parametrize(("first", "second"), HOMOPHONES)
def test_french_homophones_are_not_rhymes(first: str, second: str) -> None:
    assert compare(_keys(first), _keys(second)) is None


@pytest.mark.parametrize(("first", "second"), NONE)
def test_french_non_rhymes(first: str, second: str) -> None:
    assert compare(_keys(first), _keys(second)) is None


@pytest.mark.parametrize(
    ("word", "reads"),
    [
        ("parlent", {"paRl"}),
        ("moment", {"momA"}),
        ("content", {"kOtA", "kOt"}),
        ("tient", {"tjI"}),
        ("client", {"klijA"}),
        ("parlaient", {"paRlE"}),
        ("parents", {"paRA"}),
    ],
)
def test_french_ent_endings(word: str, reads: set[str]) -> None:
    assert phones_of(word, SILENT) == frozenset(reads)


@pytest.mark.parametrize(
    ("word", "reads"),
    [
        ("long", {"lO"}),
        ("blanc", {"blA"}),
        ("plomb", {"plO"}),
        ("vie", {"vi"}),
        ("rue", {"Ry"}),
        ("pluie", {"plHi"}),
        ("dur", {"dyR"}),
        ("respect", {"REspE"}),
        ("clef", {"kle"}),
        ("que", {"k2"}),
        ("soleil", {"solEj"}),
        ("jouer", {"Zwe"}),
        ("premier", {"pR@mje"}),
    ],
)
def test_french_readings_from_the_review(word: str, reads: set[str]) -> None:
    assert phones_of(word, SILENT) == frozenset(reads)


@pytest.mark.parametrize("spelling", ["", "l'été", "mot2", "deux mots", "pfft"])
def test_unreadable_french_spellings_have_no_keys(spelling: str) -> None:
    assert keys_of(spelling, SILENT) is None


def test_regiment_reads_its_ending() -> None:
    assert phones_of("régiment", SILENT) == frozenset({"ReZimA"})


# ---
# Readings
# ---


def test_elision_rhymes_on_the_word_after_it() -> None:
    assert rhyme_kind("l'été", "côté", language=Language.FR) is RhymeKind.PERFECT


@pytest.mark.parametrize("word", ["blorp'été", "xyz-côté"])
def test_elision_needs_a_real_prefix(word: str) -> None:
    assert rhyme_kind(word, "côté", language=Language.FR) is None


def test_same_word_key_folds_and_drops_elision() -> None:
    key = partial(same_word_key, language=Language.FR)
    assert key("l'été") == key("été")
    assert key("coeur") == key("cœur")
    assert rhyme_kind("l'été", "été", language=Language.FR) is None


def test_unknown_french_word_rejected() -> None:
    assert rhyme_kind("maison", "blorpaison", language=Language.FR) is None
    assert rhyme_kind("maison", "blorp'aison", language=Language.FR) is None


def test_unaccented_french_word_reads_as_accented() -> None:
    assert rhyme_kind("ete", "côté", language=Language.FR) is RhymeKind.PERFECT
    assert "garçon" in readings("garcon")
    assert "ça" in readings("ca")


def test_known_words_are_not_expanded_to_rare_twins() -> None:
    assert readings("mais") == ("mais",)


def test_an_accented_french_word_is_never_expanded() -> None:
    assert readings("maïs") == ("maïs",)


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("«cœur»", "cœur"),
        ("mot !", "mot"),
        ("mot ?", "mot"),
        ("« Été »", "été"),
        ("aujourd’hui", "aujourd'hui"),
        ("arc-en-ciel", "arc-en-ciel"),
        ("deux mots", None),
        ("mot2", None),
    ],
)
def test_clean_french_word(text: str, word: str | None) -> None:
    assert clean_word(text, language=Language.FR) == word


# ---
# Wisp's picks
# ---


def test_wisp_never_answers_a_used_french_word_in_another_spelling() -> None:
    rng = random.Random(3)
    for turn in range(200):
        reply = wisp_reply(
            "côté", {"ete"}, Stage.ADULT, turn, rng, language=Language.FR
        )
        assert reply != "été"


def test_wisp_answers_french_with_perfect_common_rhymes_only() -> None:
    rng = random.Random(5)
    common = set(_common_fr())
    used = {"maison"}
    replies = []
    for _ in range(200):
        reply = wisp_reply("maison", used, Stage.ROCKSTAR, 1, rng, language=Language.FR)
        if reply is None:
            continue
        assert reply in common
        assert reply not in used
        assert rhyme_kind("maison", reply, language=Language.FR) is RhymeKind.PERFECT
        maison, answer = rhymes_fr.keys("maison"), rhymes_fr.keys(reply)
        assert maison is not None and answer is not None
        assert not maison.whole & answer.whole
        used.add(reply)
        replies.append(reply)
    every_rhyme = {
        other
        for other in common
        if rhyme_kind("maison", other, language=Language.FR) is RhymeKind.PERFECT
    }
    assert len(replies) >= 5
    assert set(replies) == every_rhyme


def test_french_openers_have_rhymes_and_skip_function_words() -> None:
    common = _common_fr()
    top = set(common[:RHYME_OPENER_SKIP_TOP])
    rng = random.Random(11)
    picks = [opening_word(rng, language=Language.FR) for _ in range(50)]
    for word in set(picks):
        rhymed = [
            other
            for other in common
            if rhyme_kind(word, other, language=Language.FR) is RhymeKind.PERFECT
        ]
        assert word in common
        assert len(word) >= RHYME_OPENER_MIN_LETTERS
        assert word not in top
        assert len(rhymed) >= RHYME_OPENER_RHYMES, word
    assert len(set(picks)) > 1
    assert not {"les", "que", "des", "pour", "dans"} & set(picks)


# ---
# The word lists
# ---


def test_french_common_list_hygiene() -> None:
    common = _common_fr()
    known = rhymes_fr._known()
    assert 4500 <= len(common) <= 5500
    assert len(set(common)) == len(common)
    wholes = [_keys(word) for word in common]
    assert all(wholes)
    heard = [sound for keys in wholes if keys for sound in keys.whole]
    assert len(heard) == len(set(heard))
    assert set(common) <= known
    assert not {"paris", "marie", "jésus", "merde", "google", "macron"} & set(common)
    assert not {"love", "game", "the"} & known
    assert not {"garcon", "ete", "ca"} & known


def test_french_accent_map_reaches_known_words() -> None:
    known = rhymes_fr._known()
    accents = rhymes_fr._accents()
    assert accents["garcon"] == ("garçon",)
    for spellings in accents.values():
        assert set(spellings) <= known


def test_silent_ent_list_holds_verbs_only() -> None:
    assert {"parlent", "chantent", "aiment"} <= SILENT
    assert not {"talent", "moment", "régiment", "sergent", "survient"} & SILENT


# ---
# Lexique words
# ---


def test_a_rare_lexique_word_is_known_and_rhymes() -> None:
    frequent = (ROOT / "wisp/data/known_words_fr.txt").read_text(encoding="utf-8")
    assert "joufflu" not in frequent.split()
    assert rhyme_kind("joufflu", "exclu", language=Language.FR) is RhymeKind.PERFECT


def test_goutu_is_not_in_lexique() -> None:
    assert rhyme_kind("goûtu", "exclu", language=Language.FR) is None


def test_made_up_french_words_stay_unknown() -> None:
    assert rhyme_kind("joufflu", "blorpflu", language=Language.FR) is None
    assert rhymes_fr.keys("blorpflu") is None


def test_lexique_reading_wins_over_the_rules() -> None:
    assert phones_of("compte", SILENT) == frozenset({"kOpt"})
    assert rhyme_kind("compte", "raconte", language=Language.FR) is RhymeKind.PERFECT
    assert rhyme_kind("compte", "conte", language=Language.FR) is None


def test_the_whole_word_table_adds_to_lexique() -> None:
    word_keys = rhymes_fr.keys("tous")
    assert word_keys is not None
    assert {"tu", "tus"} <= word_keys.whole


def test_every_lexique_word_has_keys() -> None:
    lexique = rhymes_fr._lexique()
    assert len(lexique) > 100000
    assert set(lexique) <= rhymes_fr._known()
    assert all(rhymes_fr._known_keys(word) for word in lexique)
