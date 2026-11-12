from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from wisp.card import bar
from wisp.text import (
    BOX_WIDTH,
    FRAME_EMOJIS,
    HEADING_MARK,
    ITEM_MARK,
    MESSAGE_LIMIT,
    RAIL,
    SECTION_BREAK,
    SEPARATOR,
    SUB_MARK,
    UNICODE_FRAME,
    USER_ERROR,
    WIDTHS,
    any_role,
    box_bottom,
    channel_or,
    clip,
    count,
    daily_reset,
    emoji_frame,
    fit,
    frame_of,
    meter_receipt,
    richest,
    round_half_up,
    strip_emoji,
    text_length,
    timestamp,
    visual_width,
)

SPEC = Path(__file__).parent.parent / "DOCS" / "specs" / "2026-10-27-house-style.md"
SPEC_LINES = frozenset(SPEC.read_bytes().decode("utf-8").splitlines())
# The fallback frame, the v2.1 Unicode pieces; it wraps like her 22-wide box.
U = UNICODE_FRAME


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(0, "0 points"), (1, "1 point"), (2, "2 points")],
)
def test_count_pluralises_unless_one(amount: int, expected: str) -> None:
    assert count(amount, "point") == expected


@pytest.mark.parametrize(
    ("words", "channel_id", "expected"),
    [
        ("the track drop", 1563693152882262027, "<#1563693152882262027>"),
        ("the track drop", None, "the track drop"),
        ("the Status post", 60, "<#60>"),
        ("the Status post", None, "the Status post"),
        (None, 60, "<#60>"),
        (None, None, None),
    ],
)
def test_channel_or_links_a_set_channel_and_names_one_not_set(
    words: str | None, channel_id: int | None, expected: str | None
) -> None:
    assert channel_or(words, channel_id) == expected


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (58.0, 66.0, "Wellbeing +8 (now 66)"),
        (58.4, 66.4, "Wellbeing +8 (now 66)"),
        (96.0, 100.0, "Wellbeing +4 (now 100)"),
        (100.0, 100.0, "Wellbeing +0 (now 100)"),
        (40.0, 25.0, "Wellbeing -15 (now 25)"),
        (60.0, 66.5, "Wellbeing +7 (now 67)"),
    ],
)
def test_meter_receipt_adds_up_in_whole_numbers(
    before: float, after: float, expected: str
) -> None:
    assert meter_receipt("Wellbeing", before, after) == expected


def test_a_receipt_rounds_a_half_up_as_the_status_card_does() -> None:
    assert round_half_up(66.5) == 67
    assert meter_receipt("Health", 66.5, 66.5) == "Health +0 (now 67)"
    assert bar(66.5, "", "") == "67%"


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


def test_a_timestamp_is_the_short_time_of_its_whole_second() -> None:
    assert timestamp(datetime(2026, 11, 2, 6, tzinfo=UTC)) == "<t:1793599200:t>"
    assert timestamp(datetime(2026, 11, 2, 6, 0, 1, 999999, tzinfo=UTC)) == (
        "<t:1793599201:t>"
    )


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 2, tzinfo=UTC), "<t:1793664000:t>"),
        (datetime(2026, 11, 2, 13, 30, tzinfo=UTC), "<t:1793664000:t>"),
        (datetime(2026, 11, 2, 23, 59, 59, 999999, tzinfo=UTC), "<t:1793664000:t>"),
        # 8pm Pacific on the 2nd is already the 3rd in UTC.
        (
            datetime(2026, 11, 2, 20, tzinfo=ZoneInfo("America/Los_Angeles")),
            ("<t:1793750400:t>"),
        ),
    ],
)
def test_daily_limits_reset_at_the_next_utc_midnight(
    now: datetime, expected: str
) -> None:
    assert daily_reset(now) == expected


def test_a_timestamp_is_never_broken_across_rows() -> None:
    line = U.item(f"Wisp is napping until {'<t:1793599200:t> ' * 4}and more")

    rows = U.wrap(line).split("\n")

    assert len(rows) > 1
    assert "".join(rows).count("<t:1793599200:t>") == 4


def test_separator_is_myras_plain_divider() -> None:
    assert SEPARATOR == "𝄡" + "𝄚" * 22 + "𝄂"
    assert SEPARATOR in SPEC.read_bytes().decode("utf-8")


# ---
# The house style frame
# ---


def test_the_unicode_box_bottom_has_its_width_of_rules() -> None:
    for width in (BOX_WIDTH, 24, 25):
        assert box_bottom(width) == "╚" + "═" * width + "╝"
    assert SECTION_BREAK in SPEC_LINES
    assert box_bottom() in SPEC_LINES


def test_her_burrito_lines_fit_a_22_box_and_her_breaks_are_kept() -> None:
    for line in (
        "║𝄡𝄚𝄂 Burrito is Wisp's fairy god-bot.",
        "║𝄡 Ask him anything about how",
        "║𝄡 He'll point you to where to look",
    ):
        assert visual_width(line) <= U.room, line
    for line in (
        "║𝄡 Ask him anything about how Wisp",
        "║𝄡 He'll point you to where to look for",
    ):
        assert visual_width(line) > U.room, line
    assert U.wrap(
        U.item("He'll point you to where to look for Wisp's live stats.")
    ) == ("║𝄡 He'll point you to where to look\n║ for Wisp's live stats.")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<:wisp_coin:1563694541310267493>", WIDTHS["emoji"]),
        ("<a:snack_sinewave:1563694534490329098>", WIDTHS["emoji"]),
        ("\U0001f525", WIDTHS["emoji"]),
        ("<@1560213420068966441>", WIDTHS["mention"]),
        ("<#1563693152882262026>", WIDTHS["mention"]),
        ("<t:1793599200:t>", WIDTHS["timestamp"]),
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


def test_the_unicode_marks_follow_myras_rules() -> None:
    assert U.heading("Snacks") == "║𝄡𝄚𝄂𝄆 SNACKS"
    assert U.sub("Fed by") == "║𝄡𝄚𝄂 Fed by"
    assert U.item("cheese") == "║𝄡 cheese"
    assert U.note("plain") == "║ plain"
    assert U.blank == "║"
    assert U.continuation == "║ "


def test_sections_put_a_break_only_between_parts() -> None:
    assert U.sections(["a"], ["b", "c"], ["d"]) == [
        "a",
        SECTION_BREAK,
        "b",
        "c",
        SECTION_BREAK,
        "d",
    ]
    assert U.sections(["a"]) == ["a"]


# ---
# Wrapping
# ---


def test_a_line_that_fits_is_left_alone() -> None:
    assert U.wrap("║𝄡 short") == "║𝄡 short"


def test_wrapped_rows_continue_with_a_rail_and_a_space_never_a_clef() -> None:
    words = "one two three four five six seven eight nine ten"

    rows = U.wrap(U.item(words)).split("\n")

    assert len(rows) > 1
    assert rows[0].startswith("║𝄡 one")
    assert all(row.startswith("║ ") and "𝄡" not in row for row in rows[1:])
    unwrapped = [row.removeprefix("║𝄡 ").removeprefix("║ ") for row in rows]
    assert " ".join(unwrapped) == words
    assert all(visual_width(row) <= U.room for row in rows)


def test_no_row_passes_the_box() -> None:
    text = U.sub("Fed by 03 people today and some more words to go past the box edge")

    rows = U.wrap(text).split("\n")

    assert len(rows) > 1
    assert all(visual_width(row) <= U.room for row in rows)


def test_emoji_only_lines_wrap_between_emoji() -> None:
    joined = U.item("".join(f"<:gift_{n}:1>" for n in range(16)))
    spaced = U.item(" ".join(f"<:gift_{n}:1>" for n in range(16)))

    for line in (joined, spaced):
        rows = U.wrap(line).split("\n")
        assert len(rows) > 1
        assert all(visual_width(row) <= U.room for row in rows)
        assert "".join(rows).count("<:gift_") == 16


def test_padding_bold_and_masked_links_never_break() -> None:
    padded = U.item("team viibr              <:b:1>・<:m:1> 250 WC")
    bold = U.sub("**a b c d e f g h i j k l m n o p q r s t u v w x y z**")
    link = U.item(
        "[a b c d e f g h i j k l m n o p q r s t](https://viibrmusic.com/s/x)"
    )

    assert U.wrap(padded).split("\n")[0].startswith("║𝄡 team viibr              ")
    assert U.wrap(bold) == bold
    assert U.wrap(link) == link


def test_a_line_breaks_before_a_dot_but_not_between_dots() -> None:
    rows = U.wrap("║𝄡𝄚𝄂・・DAY **1**・" + "a" * 24).split("\n")

    assert rows == ["║𝄡𝄚𝄂・・DAY **1**", "║ ・" + "a" * 24]


def test_a_dot_part_keeps_together_on_its_own_row() -> None:
    line = U.item("v1 ・ went out after 18 days ・ peak Teen ・ hatched by <@2>")

    assert U.wrap(line).split("\n") == [
        "║𝄡 v1 ・ went out after 18 days",
        "║ ・ peak Teen",
        "║ ・ hatched by <@2>",
    ]


def test_the_first_row_is_never_cut_short_at_a_dot() -> None:
    rows = U.wrap(U.item("v1 ・ went out after a very long time indeed")).split("\n")

    assert rows[0].startswith("║𝄡 v1 ・ went out after")
    assert all(not row.endswith("・") for row in rows)


def test_a_badge_reason_moves_down_whole_after_its_price() -> None:
    row = U.item("<:b:1> Team ViiBR ・ <:m:1> 250 WC ・ Bandmates only")

    assert U.wrap(row).split("\n") == [
        "║𝄡 <:b:1> Team ViiBR ・ <:m:1> 250 WC",
        "║ ・ Bandmates only",
    ]


def test_a_word_too_wide_alone_stays_whole() -> None:
    url = "https://viibrmusic.com/songs/0b6f2a1e-7c3d-4e8f-9a0b-1c2d3e4f5a6b"

    assert U.wrap(U.item(url)) == U.item(url)


def test_lines_outside_the_box_are_not_wrapped() -> None:
    line = "♪ Bought Cheese for 6 WC. " * 4

    assert U.wrap(line) == line


def test_wrapped_keeps_one_entry_per_line() -> None:
    long = U.item("word " * 20)

    assert U.wrapped([U.item("x"), long]) == [U.item("x"), U.wrap(long)]


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


# ---
# Roles
# ---


@pytest.mark.parametrize(
    ("role_ids", "named"),
    [
        ((), ""),
        ((7,), "<@&7>"),
        ((9, 7), "<@&7> or <@&9>"),
        ((9, 7, 8), "<@&7>, <@&8> or <@&9>"),
        ((9, 7, 8, 6), "<@&6>, <@&7>, <@&8> or 1 more"),
        ((5, 9, 7, 8, 6), "<@&5>, <@&6>, <@&7> or 2 more"),
    ],
)
def test_any_role_names_the_roles_lowest_id_first(
    role_ids: tuple[int, ...], named: str
) -> None:
    assert any_role(role_ids, 3) == named


# ---
# The emoji frame (house style v3)
# ---

EMOJI_PIECES = tuple(f"<:{name}:{index}>" for index, name in enumerate(FRAME_EMOJIS))
EDGE, HEADER, HEADER2, HEADER3, REST, CLEF = EMOJI_PIECES
FRAME = emoji_frame(*EMOJI_PIECES)


def test_the_emoji_frame_pieces_are_myras() -> None:
    assert FRAME.heading("Favorite songs") == f"{EDGE}{HEADER2}{HEADER} FAVORITE SONGS"
    assert FRAME.sub("Nov 9") == f"{EDGE}{HEADER} Nov 9"
    assert FRAME.item("Cloud Wave") == f"{EDGE}{HEADER3} Cloud Wave"
    assert FRAME.note("hi") == f"{EDGE} hi"
    assert FRAME.blank == EDGE
    assert FRAME.section_break == f"{EDGE}{REST}{REST}"
    assert FRAME.group_break == f"{EDGE}{REST}"
    assert FRAME.bottom == f"{EDGE} {CLEF}{HEADER2 * 8}{HEADER}"
    assert FRAME.divider == f"{CLEF}{HEADER2 * 8}{HEADER}"
    assert FRAME.sections(["a"], ["b"]) == ["a", FRAME.section_break, "b"]


def test_the_emoji_frame_is_as_wide_as_its_bottom_line() -> None:
    assert FRAME.room == visual_width(FRAME.bottom)
    assert FRAME.room == pytest.approx(11 * WIDTHS["emoji"] + WIDTHS["space"])


def test_a_long_line_wraps_onto_edge_rows_in_the_emoji_frame() -> None:
    line = FRAME.item("word " * 40 + "end")

    rows = FRAME.wrap(line).split("\n")

    assert len(rows) > 1
    assert rows[0].startswith(f"{EDGE}{HEADER3} word")
    assert all(row.startswith(f"{EDGE} word") for row in rows[1:-1])
    assert rows[-1].endswith(" end")
    assert all(visual_width(row) <= FRAME.room for row in rows)


def test_a_short_line_and_a_line_outside_the_frame_are_left_alone() -> None:
    assert FRAME.wrap(FRAME.sub("short")) == FRAME.sub("short")
    outside = "x " * 80
    assert FRAME.wrap(outside) == outside


def test_the_unicode_frame_keeps_the_old_pieces() -> None:
    assert UNICODE_FRAME.heading("Favorite songs") == f"{HEADING_MARK} FAVORITE SONGS"
    assert UNICODE_FRAME.sub("x") == f"{SUB_MARK} x"
    assert UNICODE_FRAME.item("x") == f"{ITEM_MARK} x"
    assert UNICODE_FRAME.section_break == SECTION_BREAK
    assert UNICODE_FRAME.blank == RAIL
    assert UNICODE_FRAME.bottom == box_bottom()
    assert UNICODE_FRAME.divider == SEPARATOR


def uploaded(*names: str) -> Callable[[str], str]:
    """An app emoji lookup that gives `<:name:1>` for `names`, else ""."""
    return lambda name: f"<:{name}:1>" if name in names else ""


def test_the_frame_is_myras_emojis_when_all_are_uploaded() -> None:
    frame = frame_of(uploaded(*FRAME_EMOJIS))

    assert frame == emoji_frame(*(f"<:{name}:1>" for name in FRAME_EMOJIS))


@pytest.mark.parametrize("missing", FRAME_EMOJIS)
def test_one_missing_frame_emoji_falls_back_to_the_unicode_frame(missing: str) -> None:
    present = [name for name in FRAME_EMOJIS if name != missing]

    assert frame_of(uploaded(*present)) is UNICODE_FRAME


def test_fit_takes_a_limit() -> None:
    text = fit(["head"], ["x" * 2500, "y"], ["tail"], 4000)

    assert text == "\n".join(["head", "x" * 2500, "y", "tail"])
