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
    ("ipa", "phones"),
    [
        ("k ɝ", "K ER1"),
        ("f a ɪ ɚ", "F AY1 ER0"),
        ("l ɑ l i ɡ æ ɡ", "L AA0 L IY0 G AE1 G"),
        ("b ɑ t l̩", "B AA1 T AH0 L"),
        ("t͡ʃ e ɪ̯ n", "CH EY1 N"),
        ("p ə ɹ e ɪ d", "P ER0 EY1 D"),
    ],
)
def test_ipa_maps_to_arpabet(ipa: str, phones: str) -> None:
    assert arpabet(ipa) == phones


@pytest.mark.parametrize("ipa", ["k ɛ̃", "s t", ""])
def test_unmapped_ipa_is_left_out(ipa: str) -> None:
    assert arpabet(ipa) is None


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
