"""Tests for the offline pronunciation builder's IPA and Lexique mapping."""

import pytest

from tools.build_pronunciations import arpabet, french_reading, stressed_vowel


@pytest.mark.parametrize(
    ("vowels", "stressed"),
    [
        (["ɝ", "e"], 1),
        (["ɪ", "i"], 0),
        (["ə", "i"], 1),
        (["ɪ", "ɪ"], 0),
        (["æ", "ə"], 0),
        (["ə"], 0),
        (["i"], 0),
    ],
)
def test_stress_goes_on_the_last_full_vowel(vowels: list[str], stressed: int) -> None:
    assert stressed_vowel(vowels) == stressed


@pytest.mark.parametrize(
    ("word", "ipa", "phones"),
    [
        ("cur", "k ɝ", "K ER1"),
        ("fire", "f a ɪ ɚ", "F AY1 ER0"),
        ("lollygag", "l ɑ l i ɡ æ ɡ", "L AA0 L IY0 G AE1 G"),
        ("bottle", "b ɑ t l̩", "B AA1 T AH0 L"),
        ("chain", "t͡ʃ e ɪ̯ n", "CH EY1 N"),
        ("parade", "p ə ɹ e ɪ d", "P ER0 EY1 D"),
        ("housemother", "h ʌ ʊ s m ʌ ð ɚ", "HH AW0 S M AH1 DH ER0"),
    ],
)
def test_ipa_maps_to_arpabet(word: str, ipa: str, phones: str) -> None:
    assert arpabet(word, ipa) == phones


@pytest.mark.parametrize(
    ("word", "ipa", "phones"),
    [
        ("accoast", "ə k ə ʊ s t", "AH0 K OW1 S T"),
        ("aikido", "a ɪ k iː d ə ʊ", "AY0 K IY0 D OW1"),
        ("vacuole", "v æ k j ʊ ə ʊ l", "V AE0 K Y UH0 OW1 L"),
        ("geosphere", "d͡ʒ iː ə s f ɪ ə", "JH IY0 AH0 S F IH1 R"),
        ("hearable", "h ɪ ə ɹ ə b ə l", "HH IH1 R AH0 B AH0 L"),
        ("abamperes", "æ b æ m p ɛ ə", "AE0 B AE0 M P EH1 R"),
        ("beared", "b ɛ ə d", "B EH1 R D"),
        ("immure", "ɪ m j ʊ ə", "IH0 M Y UH1 R"),
        ("wayfare", "w e ɪ f ɛ ɚ", "W EY0 F EH1 R"),
        ("musketeer", "m ʌ s k ə t ɪ ɚ", "M AH0 S K AH0 T IH1 R"),
    ],
)
def test_british_vowels_join_like_cmu(word: str, ipa: str, phones: str) -> None:
    assert arpabet(word, ipa) == phones


@pytest.mark.parametrize(
    ("word", "ipa", "phones"),
    [
        ("porphyria", "p ɔː f ɪ ɹ ɪ ə", "P AO1 F IH0 R IH0 AH0"),
        ("brunneous", "b ɹ ʌ n ɪ ə s", "B R AH1 N IH0 AH0 S"),
        ("effectually", "iː f ɛ k t͡ʃ ʊ ə l i", "IY0 F EH1 K CH UH0 AH0 L IY0"),
        ("pandan", "p ɛ ə̯ n d ə n", "P AE1 N D AH0 N"),
    ],
)
def test_two_syllable_and_tensed_vowels_stay_apart(
    word: str, ipa: str, phones: str
) -> None:
    assert arpabet(word, ipa) == phones


@pytest.mark.parametrize("ipa", ["k ɛ̃", "s t", ""])
def test_unmapped_ipa_is_left_out(ipa: str) -> None:
    assert arpabet("word", ipa) is None


@pytest.mark.parametrize(
    ("phon", "phones"),
    [
        ("mEz§", "mEzO"),
        ("bl@S°", "blAS"),
        ("l°", "l2"),
        ("paRkiG", "paRkiN"),
        ("ap8i", "apHi"),
        ("illegal", "ilegal"),
        ("k§t@", "kOtA"),
    ],
)
def test_lexique_phon_maps_to_rhyme_phones(phon: str, phones: str) -> None:
    assert french_reading(phon) == phones


@pytest.mark.parametrize("phon", ["pst", "Q", ""])
def test_unreadable_lexique_phon_is_left_out(phon: str) -> None:
    assert french_reading(phon) is None
