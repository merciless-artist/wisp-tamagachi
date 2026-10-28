from pathlib import Path

import pytest

from wisp.text import (
    BLANK,
    BOX_WIDTH,
    MESSAGE_LIMIT,
    SECTION_BREAK,
    SEPARATOR,
    USER_ERROR,
    WIDTHS,
    bars,
    box_bottom,
    box_close,
    box_open,
    box_room,
    box_top,
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
    visual_width,
    wrap,
    wrapped,
)

SPEC = Path(__file__).parent.parent / "DOCS" / "specs" / "2026-10-27-house-style.md"
SPEC_LINES = frozenset(SPEC.read_bytes().decode("utf-8").splitlines())
LAYOUT_TITLES = (
    "𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈",
    "𝕍𝒾𝒾𝔹ℝ <:viibr_logo:1533030151015895120> 𝕍𝒶𝓊𝓁𝓉",
    "𝕍𝒾𝒾𝔹ℝ 𝕍𝒶𝓊𝓁𝓉",
    "𝕊𝓃𝒶𝒸𝓀 ℙ𝒶𝒸𝓀",
    "𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍",
    "𝕃𝑒𝒶𝒹𝑒𝓇𝒷𝑜𝒶𝓇𝒹",
)
BURRITO_TITLE = "𝔹𝓊𝓇𝓇𝒾𝓉𝑜"
# Half a 𝄚: the closest two bars made of whole 𝄚 can come.
BAR_TOLERANCE = WIDTHS["staff"] / 2


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


def test_the_box_lines_have_the_same_number_of_rules() -> None:
    for width in (BOX_WIDTH, 24, 25):
        assert box_top(width) == "╔" + "═" * width + "╗"
        assert box_bottom(width) == "╚" + "═" * width + "╝"
    assert SECTION_BREAK in SPEC_LINES
    assert box_top() in SPEC_LINES


@pytest.mark.parametrize("title", LAYOUT_TITLES)
def test_the_title_bar_and_the_bottom_bar_look_as_wide(title: str) -> None:
    top, bottom = bars(title)

    assert top == f"𝄃𝄞𝄚𝄚𝄚𝄚𝄆 {title} 𝄇𝄡𝄚𝄚𝄚𝄚𝄂"
    assert bottom.startswith("𝄃𝄣𝄚") and bottom.endswith("𝄚𝄂")
    assert set(bottom[2:-1]) == {"𝄚"}
    assert abs(visual_width(top) - visual_width(bottom)) <= BAR_TOLERANCE
    assert title_bar(title) == top
    assert box_open(title)[0] == top
    assert box_close(title)[1] == bottom


def test_the_bars_are_calibrated_on_myras_burrito_post() -> None:
    top, bottom = bars(BURRITO_TITLE, side=6)

    assert top == "𝄃𝄞𝄚𝄚𝄚𝄚𝄚𝄚𝄆 𝔹𝓊𝓇𝓇𝒾𝓉𝑜 𝄇𝄡𝄚𝄚𝄚𝄚𝄚𝄚𝄂"
    assert bottom == "𝄃𝄣" + "𝄚" * 20 + "𝄂"


def test_her_burrito_lines_fit_a_22_box_and_her_breaks_are_kept() -> None:
    room = box_room(22)

    for line in (
        "║𝄡𝄚𝄂 Burrito is Wisp's fairy god-bot.",
        "║𝄡 Ask him anything about how",
        "║𝄡 He'll point you to where to look",
    ):
        assert visual_width(line) <= room, line
    for line in (
        "║𝄡 Ask him anything about how Wisp",
        "║𝄡 He'll point you to where to look for",
    ):
        assert visual_width(line) > room, line
    assert wrap(item("He'll point you to where to look for Wisp's live stats.")) == (
        "║𝄡 He'll point you to where to look\n║ for Wisp's live stats."
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<:wisp_coin:1563694541310267493>", WIDTHS["emoji"]),
        ("<a:snack_sinewave:1563694534490329098>", WIDTHS["emoji"]),
        ("\U0001f525", WIDTHS["emoji"]),
        ("<@1560213420068966441>", WIDTHS["mention"]),
        ("<#1563693152882262026>", WIDTHS["mention"]),
        ("**ab**", 2 * WIDTHS["letter"]),
        ("[ab](https://viibrmusic.com/s/Kg4qckZe)", 2 * WIDTHS["letter"]),
        ("\\*", WIDTHS["letter"]),
        ("a b", 2 * WIDTHS["letter"] + WIDTHS["space"]),
        ("𝄚", WIDTHS["staff"]),
        ("𝄡", WIDTHS["music"]),
        ("𝕎", WIDTHS["fancy"]),
        ("ℙ", WIDTHS["fancy"]),
        ("ᵗ", WIDTHS["tiny"]),
        ("═", WIDTHS["box"]),
        ("・", WIDTHS["dot"]),
        ("♪", WIDTHS["other"]),
        ("", 0.0),
    ],
)
def test_visual_width_counts_what_discord_shows(text: str, expected: float) -> None:
    assert visual_width(text) == pytest.approx(expected)


def test_a_custom_emoji_is_wider_than_a_letter() -> None:
    assert visual_width("<:x:1>") > visual_width("W")


def test_visual_width_of_lines_is_the_widest() -> None:
    assert visual_width("ab\nabcd\na") == visual_width("abcd")


def test_the_line_marks_follow_myras_rules() -> None:
    assert heading("Snacks") == "║𝄡𝄚𝄂𝄆 **Snacks**"
    assert sub("Fed by") == "║𝄡𝄚𝄂 Fed by"
    assert item("cheese") == "║𝄡 cheese"
    assert note("plain") == "║ plain"
    assert BLANK == "║"
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


def test_framed_puts_the_wrapped_body_in_the_box() -> None:
    long = item("word " * 12 + "end")

    assert framed("T", ["║ x", long]).splitlines() == [
        *box_open("T"),
        "║ x",
        *wrap(long).splitlines(),
        *box_close("T"),
    ]
    assert framed("T", ["║ x"], 25).splitlines()[1] == box_top(25)


# ---
# Wrapping
# ---


def test_a_line_that_fits_is_left_alone() -> None:
    assert wrap("║𝄡 short") == "║𝄡 short"


def test_wrapped_rows_continue_with_a_rail_and_a_space_never_a_clef() -> None:
    words = "one two three four five six seven eight nine ten"

    rows = wrap(item(words)).split("\n")

    assert len(rows) > 1
    assert rows[0].startswith("║𝄡 one")
    assert all(row.startswith("║ ") and "𝄡" not in row for row in rows[1:])
    unwrapped = [row.removeprefix("║𝄡 ").removeprefix("║ ") for row in rows]
    assert " ".join(unwrapped) == words
    assert all(visual_width(row) <= box_room() for row in rows)


@pytest.mark.parametrize("width", [22, 24, 25, 26])
def test_no_row_passes_the_box(width: int) -> None:
    text = sub("Fed by 03 people today and some more words to go past the box edge")

    rows = wrap(text, width).split("\n")

    assert len(rows) > 1
    assert all(visual_width(row) <= box_room(width) for row in rows)


def test_a_wider_box_wraps_later() -> None:
    line = item("one two three four five six seven eight nine")

    first_rows = [wrap(line, width).split("\n")[0] for width in (22, 26)]

    assert len(first_rows[1]) > len(first_rows[0])


def test_emoji_only_lines_wrap_between_emoji() -> None:
    joined = item("".join(f"<:gift_{n}:1>" for n in range(16)))
    spaced = item(" ".join(f"<:gift_{n}:1>" for n in range(16)))

    for line in (joined, spaced):
        rows = wrap(line).split("\n")
        assert len(rows) > 1
        assert all(visual_width(row) <= box_room() for row in rows)
        assert "".join(rows).count("<:gift_") == 16


def test_padding_bold_and_masked_links_never_break() -> None:
    padded = item("team viibr              │<:b:1>・<:m:1> 250 WC・Bandmates only")
    bold = sub("**a b c d e f g h i j k l m n o p q r s t u v w x y z**")
    link = item("[a b c d e f g h i j k l m n o p q r s t](https://viibrmusic.com/s/x)")

    assert wrap(padded, 24).split("\n")[0].startswith("║𝄡 team viibr              │")
    assert wrap(bold) == bold
    assert wrap(link) == link


def test_a_line_breaks_before_a_dot_but_not_between_dots() -> None:
    rows = wrap("║𝄡𝄚𝄂・・𝐃𝐀𝐘 **1**・" + "a" * 24).split("\n")

    assert rows == ["║𝄡𝄚𝄂・・𝐃𝐀𝐘 **1**", "║ ・" + "a" * 24]


def test_a_dot_part_keeps_together_on_its_own_row() -> None:
    line = item("v1 ・ went out after 18 days ・ peak Teen ・ hatched by <@2>")

    assert wrap(line).split("\n") == [
        "║𝄡 v1 ・ went out after 18 days",
        "║ ・ peak Teen",
        "║ ・ hatched by <@2>",
    ]


def test_the_first_row_is_never_cut_short_at_a_dot() -> None:
    rows = wrap(item("v1 ・ went out after a very long time indeed")).split("\n")

    assert rows[0].startswith("║𝄡 v1 ・ went out after")
    assert all(not row.endswith("・") for row in rows)


def test_a_badge_reason_moves_down_whole_after_its_price() -> None:
    row = item("team viibr              │<:b:1>・<:m:1> 250 WC・Bandmates only")

    assert wrap(row, 24).split("\n") == [
        "║𝄡 team viibr              │<:b:1>・<:m:1> 250 WC",
        "║ ・Bandmates only",
    ]


def test_a_word_too_wide_alone_stays_whole() -> None:
    url = "https://viibrmusic.com/songs/0b6f2a1e-7c3d-4e8f-9a0b-1c2d3e4f5a6b"

    assert wrap(item(url)) == item(url)


def test_lines_outside_the_box_are_not_wrapped() -> None:
    line = "♪ Bought Cheese for 6 WC. " * 4

    assert wrap(line) == line


def test_wrapped_keeps_one_entry_per_line() -> None:
    long = item("word " * 20)

    assert wrapped([item("x"), long]) == [item("x"), wrap(long)]


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
