import pytest

from wisp.text import count, strip_emoji


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(0, "0 points"), (1, "1 point"), (2, "2 points")],
)
def test_count_pluralises_unless_one(amount: int, expected: str) -> None:
    assert count(amount, "point") == expected


def test_strip_emoji_keeps_dots_and_notes() -> None:
    assert strip_emoji("・♪ hi ♫ 🔥✨☀️❤️👩‍🎤🇺🇸 ok ─ <3") == "・♪ hi ♫  ok ─ <3"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("⭐ star", " star"),
        ("⌚ late", " late"),
        ("wow‼", "wow"),
        ("what⁉", "what"),
        ("1️⃣ first", "1 first"),
        ("⬛⬆", ""),
    ],
)
def test_strip_emoji_removes_the_symbol_blocks(text: str, expected: str) -> None:
    assert strip_emoji(text) == expected


def test_strip_emoji_keeps_the_flair() -> None:
    assert strip_emoji("・♪ ────────・──────── ♪・ ♫") == "・♪ ────────・──────── ♪・ ♫"
