from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from wisp.card import bar
from wisp.text import (
    FOOTER_BAR,
    FOOTER_MIC,
    MESSAGE_LIMIT,
    SECTION_ICONS,
    SEPARATOR,
    SITE,
    SPACER,
    TITLE_BAR,
    UNICODE_FRAME,
    USER_ERROR,
    any_role,
    channel_or,
    clip,
    count,
    daily_reset,
    fit,
    frame_of,
    heading_case,
    meter_receipt,
    richest,
    round_half_up,
    strip_emoji,
    text_length,
    timestamp,
)

SPEC = Path(__file__).parent.parent / "DOCS" / "specs" / "2026-10-27-house-style.md"


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


def test_separator_is_myras_plain_divider() -> None:
    assert SEPARATOR == "𝄡" + "𝄚" * 22 + "𝄂"
    assert SEPARATOR in SPEC.read_bytes().decode("utf-8")


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
# The Favorites style (house style v4)
# ---


def uploaded(*names: str) -> Callable[[str], str]:
    """An app emoji lookup that gives `<:name:1>` for `names`, else ""."""
    return lambda name: f"<:{name}:1>" if name in names else ""


ALL = (*TITLE_BAR, *FOOTER_BAR, FOOTER_MIC, *SECTION_ICONS)
FRAME = frame_of(uploaded(*ALL))
WAVE = "<:wisp_waveform:1>"
RIGHT, LEFT, PLAIN = "<:headerbarright:1>", "<:headerbarleft:1>", "<:headerbar:1>"
TOP_BAR = f"{RIGHT}{WAVE}{LEFT}"
LONG_BAR = f"{RIGHT}{PLAIN}{WAVE}{PLAIN}{LEFT}"


def test_the_style_is_made_of_myras_favorites_emojis() -> None:
    assert TITLE_BAR == ("headerbarright", "wisp_waveform", "headerbarleft")
    assert FOOTER_BAR == (
        "headerbarright",
        "headerbar",
        "wisp_waveform",
        "headerbar",
        "headerbarleft",
    )
    assert FOOTER_MIC == "mic2"
    assert SECTION_ICONS == ("boing_bass", "wisp_play", "wisp_pause", "wisp_stop")
    assert SITE == "https://viibrmusic.com"
    assert SPACER == "** **"


def test_the_title_is_bold_capitals_between_two_bars() -> None:
    assert FRAME.title("Wisp stats") == f"# {TOP_BAR} **WiSP STATS** {TOP_BAR}"
    assert FRAME.title("ViiBR Vault") == f"# {TOP_BAR} **ViiBR VAULT** {TOP_BAR}"


def test_the_footer_is_the_favorites_footer_exactly() -> None:
    assert FRAME.footer == (
        f"### ・{LONG_BAR}<:mic2:1>https://viibrmusic.com {LONG_BAR}・"
    )


@pytest.mark.parametrize(
    ("place", "icon"),
    [
        (0, "boing_bass"),
        (1, "wisp_play"),
        (2, "wisp_pause"),
        (3, "wisp_stop"),
        (4, "boing_bass"),
        (6, "wisp_pause"),
    ],
)
def test_section_icons_take_turns_by_place(place: int, icon: str) -> None:
    assert FRAME.heading("Snacks", place) == f"## <:{icon}:1> **SNACKS**"


def test_a_heading_can_keep_myras_own_size_and_gap() -> None:
    assert FRAME.heading("Favorite snacks", 1, size="###", gap="") == (
        "### <:wisp_play:1>**FAVORITE SNACKS**"
    )
    assert FRAME.heading("Favorite gifts", 3, gap="  ") == (
        "## <:wisp_stop:1>  **FAVORITE GIFTS**"
    )


def test_items_and_notes_are_plain_lines() -> None:
    assert FRAME.item("Cloud Wave ・ 3 WC") == " ・Cloud Wave ・ 3 WC"
    assert FRAME.big_item("jellywave") == "### ・jellywave"
    assert FRAME.note("wisp coins: 4") == " wisp coins: 4"


def test_no_line_has_an_edge_emoji_or_a_bar_row() -> None:
    lines = [
        FRAME.title("x"),
        FRAME.heading("x", 0),
        FRAME.item("x"),
        FRAME.big_item("x"),
        FRAME.note("x"),
        FRAME.footer,
    ]

    assert all("header_edge" not in line and "rest_bar" not in line for line in lines)


def test_the_divider_is_the_footer_bar() -> None:
    assert FRAME.divider == LONG_BAR


def test_with_no_emojis_the_style_is_plain_readable_text() -> None:
    assert frame_of(uploaded()) == UNICODE_FRAME
    assert UNICODE_FRAME.title("Wisp stats") == "# **WiSP STATS**"
    assert UNICODE_FRAME.heading("Snacks", 2) == "## **SNACKS**"
    assert UNICODE_FRAME.footer == "### ・https://viibrmusic.com"
    assert UNICODE_FRAME.divider == SEPARATOR
    assert "<:" not in UNICODE_FRAME.footer


@pytest.mark.parametrize("missing", sorted(set(ALL)))
def test_a_missing_emoji_is_left_out_cleanly(missing: str) -> None:
    frame = frame_of(uploaded(*(name for name in ALL if name != missing)))

    lines = [frame.title("x"), frame.footer, *(frame.heading("x", n) for n in range(4))]

    assert all(f":{missing}:" not in line for line in lines)
    assert frame.title("x").startswith("# ")
    assert "  " not in frame.title("x")
    assert frame.footer.startswith("### ・")
    assert frame.footer.count(SITE) == 1


def test_a_heading_without_its_icon_has_no_double_space() -> None:
    frame = frame_of(uploaded("wisp_play"))

    assert frame.heading("Snacks", 0) == "## **SNACKS**"
    assert frame.heading("Snacks", 1) == "## <:wisp_play:1> **SNACKS**"
    assert frame.footer == "### ・https://viibrmusic.com"


def test_the_footer_without_its_bars_keeps_the_mic() -> None:
    assert frame_of(uploaded("mic2")).footer == "### ・<:mic2:1>https://viibrmusic.com"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Wisp's favorites", "WiSP'S FAVORITES"),
        ("wisp", "WiSP"),
        ("Feed WISP now", "FEED WiSP NOW"),
        ("Wispy clouds", "WISPY CLOUDS"),
        ("Snacks", "SNACKS"),
        ("ViiBR Vault", "ViiBR VAULT"),
        ("viibr tracks", "ViiBR TRACKS"),
        ("VIIBRATIONS cover", "VIIBRATIONS COVER"),
        ("Wisp's ViiBR wave", "WiSP'S ViiBR WAVE"),
    ],
)
def test_headings_keep_myras_spellings(name: str, expected: str) -> None:
    assert heading_case(name) == expected
    assert FRAME.heading(name, 0) == f"## <:boing_bass:1> **{expected}**"
    assert UNICODE_FRAME.title(name) == f"# **{expected}**"


def test_fit_takes_a_limit() -> None:
    text = fit(["head"], ["x" * 2500, "y"], ["tail"], 4000)

    assert text == "\n".join(["head", "x" * 2500, "y", "tail"])
