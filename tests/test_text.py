import pytest

from wisp.text import SEPARATOR, USER_ERROR, count, richest, strip_emoji


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(0, "0 points"), (1, "1 point"), (2, "2 points")],
)
def test_count_pluralises_unless_one(amount: int, expected: str) -> None:
    assert count(amount, "point") == expected


def test_richest_swaps_in_rich_lines_while_they_fit() -> None:
    plain = ["a", "b", "c"]
    rich = ["a" * 5, "b" * 50, "c" * 5]

    assert richest(plain, rich, 15) == ["aaaaa", "b", "ccccc"]
    assert richest(plain, rich, 100) == rich
    assert richest(plain, rich, 1) == plain


def test_separator_is_myras_divider() -> None:
    assert SEPARATOR == "❱❱━━━━━━━━━━━━━━━━━━━━━━━━━━❰❰"


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
    assert strip_emoji("・♪ ─ ・ ♪・ ♫") == "・♪ ─ ・ ♪・ ♫"


def test_the_member_is_told_where_the_error_is() -> None:
    assert USER_ERROR == "That didn't work. The error is posted in this channel."
