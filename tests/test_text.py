from pathlib import Path

import pytest

from wisp.text import (
    BOTTOM_BAR,
    BOX_BOTTOM,
    BOX_TOP,
    MESSAGE_LIMIT,
    SECTION_BREAK,
    SEPARATOR,
    USER_ERROR,
    clip,
    count,
    fit,
    framed,
    heading,
    item,
    note,
    richest,
    sections,
    strip_emoji,
    sub,
    text_length,
    title_bar,
)

SPEC = Path(__file__).parent.parent / "DOCS" / "specs" / "2026-10-27-house-style.md"
SPEC_LINES = frozenset(SPEC.read_bytes().decode("utf-8").splitlines())


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


def test_richest_counts_utf16_units() -> None:
    clefs = "𝄞" * 5

    assert richest(["a"], [clefs], 9) == ["a"]
    assert richest(["a"], [clefs], 10) == [clefs]


def test_fit_counts_utf16_units() -> None:
    clef_line = "𝄞" * 500

    text = fit(["head"], [clef_line, clef_line], ["tail"])

    assert text == "\n".join(["head", clef_line, "tail"])
    assert len(text) < MESSAGE_LIMIT // 2
    assert text_length(text) <= MESSAGE_LIMIT


@pytest.mark.parametrize(
    ("text", "room", "expected"),
    [
        ("abc", 2, "ab"),
        ("abc", 9, "abc"),
        ("a𝄞b", 2, "a"),
        ("a𝄞b", 3, "a𝄞"),
        ("𝄞𝄞", 3, "𝄞"),
        ("𝄞", 1, ""),
        ("", 0, ""),
    ],
)
def test_clip_never_splits_a_character(text: str, room: int, expected: str) -> None:
    assert clip(text, room) == expected


def test_fit_keeps_the_tail_and_drops_the_last_optional_lines() -> None:
    text = fit(["head"], ["a" * 1000, "b" * 1000], ["end"])

    assert text.splitlines() == ["head", "a" * 1000, "end"]


def test_separator_is_myras_plain_divider() -> None:
    assert SEPARATOR == "𝄡" + "𝄚" * 22 + "𝄂"
    assert SEPARATOR in SPEC.read_bytes().decode("utf-8")


# ---
# The house style frame
# ---


def test_the_frame_lines_are_copied_from_the_spec() -> None:
    for line in (BOX_TOP, BOX_BOTTOM, BOTTOM_BAR, SECTION_BREAK):
        assert line in SPEC_LINES, line
    assert BOX_TOP == "╔" + "═" * 20 + "╗"
    assert BOX_BOTTOM == "╚" + "═" * 20 + "╝"
    assert BOTTOM_BAR == "𝄃𝄣" + "𝄚" * 20 + "𝄂"


@pytest.mark.parametrize(
    "title",
    ["𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈", "𝕊𝓃𝒶𝒸𝓀 ℙ𝒶𝒸𝓀", "𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍", "𝕃𝑒𝒶𝒹𝑒𝓇𝒷𝑜𝒶𝓇𝒹"],
)
def test_the_title_bar_matches_the_spec(title: str) -> None:
    bar = title_bar(title)

    assert bar in SPEC_LINES
    assert bar == f"𝄃𝄞𝄚𝄚𝄚𝄚𝄆 {title} 𝄇𝄡𝄚𝄚𝄚𝄚𝄂"


def test_the_line_marks_follow_myras_rules() -> None:
    assert heading("Snacks") == "║𝄡𝄚𝄂𝄆 **Snacks**"
    assert sub("Fed by") == "║𝄡𝄚𝄂 Fed by"
    assert item("cheese") == "║𝄡 cheese"
    assert note("plain") == "║ plain"
    assert heading("Snacks") in SPEC_LINES


def test_sections_put_a_break_only_between_parts() -> None:
    assert sections(["a"], ["b", "c"], ["d"]) == [
        "a",
        SECTION_BREAK,
        "b",
        "c",
        SECTION_BREAK,
        "d",
    ]
    assert sections(["a"]) == ["a"]


def test_framed_puts_the_body_in_the_box() -> None:
    assert framed("T", ["x"]).splitlines() == [
        title_bar("T"),
        BOX_TOP,
        "x",
        BOX_BOTTOM,
        BOTTOM_BAR,
    ]


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
