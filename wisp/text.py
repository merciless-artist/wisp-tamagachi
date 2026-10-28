"""Small text pieces shared by Wisp's posts, and the frame of Myra's house style.

The house style is `DOCS/specs/2026-10-27-house-style.md`. Its marks work like
markdown: `#` is a section heading, `##` a sub-heading or information line, `###`
an item, `>` the break between sections and `>>>` the end of the box.
"""

import re
from collections.abc import Sequence
from typing import Final

MESSAGE_LIMIT: Final = 2000
LAYOUT_TEXT_LIMIT: Final = 4000
USER_ERROR: Final = "That didn't work. The error is posted in this channel."

# Pictographs, the technical, arrow and symbol blocks emoji come from (minus the
# music notes ♪ and ♫), ‼ and ⁉, plus the keycap, variation selector and
# zero-width joiner that build emoji sequences.
_EMOJI: Final = re.compile(
    "[\U0001f000-\U0001faff\u2300-\u23ff\u2600-\u2669\u266c-\u27bf"
    "\u2b00-\u2bff\u203c\u2049\u20e3\ufe0f\u200d]"
)

# ---
# Widths
# ---

# Estimated widths in em of Discord's proportional font, by kind of character.
# Discord does not say how wide a line is, so these are calibrated on Myra's
# own layouts: in her Burrito post a 22-`═` box holds every line and breaks
# exactly where she broke them, and its 6-`𝄚` title bar is as wide as its
# 20-`𝄚` bottom bar; her hand-tuned padding before the Vault's `│` makes a
# space about 0.22 em.
WIDTHS: Final[dict[str, float]] = {
    "space": 0.22,
    "thin": 0.25,
    "narrow": 0.35,
    "letter": 0.52,
    "digit": 0.55,
    "capital": 0.65,
    "wide": 0.8,
    "tiny": 0.35,
    "fancy": 0.54,
    "staff": 0.75,
    "music": 0.6,
    "box": 0.662,
    "dot": 1.0,
    "emoji": 1.375,
    "mention": 6.0,
    "unseen": 0.0,
    "other": 0.6,
}

_THIN: Final = frozenset("ijl.,:;'!|`")
_NARROW: Final = frozenset("frtI/()[]-")
_WIDE: Final = frozenset("mwMW%@&")
_STAFF: Final = "𝄚"
_DOT: Final = "・"
_UNSEEN: Final = frozenset("\u20e3\ufe0f\u200d")
_MUSIC_NOTES: Final = frozenset("♩♪♫♬")
# Superscript and modifier letters, such as the small print ᵗʰᵉˢᵉ.
_TINY: Final = re.compile("[\u02b0-\u02ff\u1d2c-\u1d6a\u1d9b-\u1dbf\u2070-\u209f]")
# Mathematical letters such as 𝕎 or 𝒾, and letterlike ones such as ℙ or ℝ.
_FANCY: Final = re.compile("[\U0001d400-\U0001d7ff\u2100-\u214f]")
_MUSIC: Final = re.compile("[\U0001d100-\U0001d1ff]")
_BOX_DRAWING: Final = re.compile("[\u2500-\u257f]")
_CUSTOM_EMOJI: Final = r"<a?:\w+:\d+>"

# What a line is made of, as Discord shows it: a masked link (only its label
# shows), a custom emoji, a mention, a bold mark, an escaped character, or
# any other single character.
_TOKEN: Final = re.compile(
    r"\[(?P<label>[^\]\n]*)\]\(<?https?://[^)\s]*>?\)"
    rf"|(?P<emoji>{_CUSTOM_EMOJI})"
    r"|(?P<mention><(?:@[!&]?|#)\d+>)"
    r"|(?P<bold>\*\*)"
    r"|\\(?P<escaped>[^\w\s])"
    r"|.",
    re.DOTALL,
)


def _character_kind(character: str) -> str:
    """The `WIDTHS` kind of one character."""
    if character == " ":
        return "space"
    if character.isascii():
        if character in _THIN:
            return "thin"
        if character in _NARROW:
            return "narrow"
        if character in _WIDE:
            return "wide"
        if character.isupper():
            return "capital"
        return "digit" if character.isdigit() else "letter"
    if character in _UNSEEN:
        return "unseen"
    if character == _STAFF:
        return "staff"
    if character == _DOT:
        return "dot"
    for pattern, kind in (
        (_MUSIC, "music"),
        (_FANCY, "fancy"),
        (_TINY, "tiny"),
        (_BOX_DRAWING, "box"),
    ):
        if pattern.match(character):
            return kind
    if character not in _MUSIC_NOTES and _EMOJI.match(character):
        return "emoji"
    return "other"


def _token_width(token: re.Match[str]) -> float:
    if (label := token["label"]) is not None:
        return visual_width(label)
    if token["emoji"]:
        return WIDTHS["emoji"]
    if token["mention"]:
        return WIDTHS["mention"]
    if token["bold"]:
        return WIDTHS["unseen"]
    return WIDTHS[_character_kind(token["escaped"] or token[0])]


def visual_width(text: str) -> float:
    """An estimate, in em, of how wide `text` looks in Discord.

    A multi-line text is as wide as its widest line. Markdown that does not
    show (bold marks, escapes, a masked link's address) takes no room, and a
    mention counts as a name of typical length.
    """
    return max(
        sum(_token_width(token) for token in _TOKEN.finditer(line))
        for line in text.split("\n")
    )


# ---
# The house style frame
# ---

SEPARATOR: Final = "𝄡" + _STAFF * 22 + "𝄂"
BOX_WIDTH: Final = 22
TITLE_SIDE: Final = 4
SECTION_BREAK: Final = "╠═══⇕"
RAIL: Final = "║"
BLANK: Final = RAIL
HEADING_MARK: Final = "║𝄡𝄚𝄂𝄆"
SUB_MARK: Final = "║𝄡𝄚𝄂"
ITEM_MARK: Final = "║𝄡"
CONTINUATION: Final = f"{RAIL} "
_MARKS: Final = (HEADING_MARK, SUB_MARK, ITEM_MARK, RAIL)
_BOTTOM_ENDS: Final = ("𝄃𝄣", "𝄂")


def box_top(width: int = BOX_WIDTH) -> str:
    """The top of a box `width` `═` wide."""
    return "╔" + "═" * width + "╗"


def box_bottom(width: int = BOX_WIDTH) -> str:
    """The bottom of a box `width` `═` wide."""
    return "╚" + "═" * width + "╝"


def bars(title: str, side: int = TITLE_SIDE) -> tuple[str, str]:
    """The title bar with `title` and a bottom bar that looks just as wide.

    The title bar has `side` `𝄚` on each side of the title; the bottom bar has
    as many `𝄚` as bring it nearest the title bar's `visual_width`.
    """
    staff = _STAFF * side
    top = f"𝄃𝄞{staff}𝄆 {title} 𝄇𝄡{staff}𝄂"
    ends = visual_width("".join(_BOTTOM_ENDS))
    count = round((visual_width(top) - ends) / visual_width(_STAFF))
    return top, _BOTTOM_ENDS[0] + _STAFF * max(count, 0) + _BOTTOM_ENDS[1]


def title_bar(title: str, side: int = TITLE_SIDE) -> str:
    """The bar above the box, with `title` between the repeat signs."""
    return bars(title, side)[0]


def heading(name: str) -> str:
    """A `#` line: a section heading, always bold."""
    return f"{HEADING_MARK} **{name}**"


def sub(text: str) -> str:
    """A `##` line: a sub-heading or an information line."""
    return f"{SUB_MARK} {text}"


def item(text: str) -> str:
    """A `###` line: one item."""
    return f"{ITEM_MARK} {text}"


def note(text: str) -> str:
    """A plain line inside the box, with no clef."""
    return f"{RAIL} {text}"


def box_open(title: str, width: int = BOX_WIDTH, side: int = TITLE_SIDE) -> list[str]:
    """The title bar and the top of the box."""
    return [title_bar(title, side), box_top(width)]


def box_close(title: str, width: int = BOX_WIDTH, side: int = TITLE_SIDE) -> list[str]:
    """The bottom of the box and the bottom bar that matches `title`'s bar."""
    return [box_bottom(width), bars(title, side)[1]]


def sections(*parts: Sequence[str]) -> list[str]:
    """The lines of each part, with a section break between parts."""
    lines: list[str] = []
    for index, part in enumerate(parts):
        if index:
            lines.append(SECTION_BREAK)
        lines.extend(part)
    return lines


def framed(
    title: str,
    body: Sequence[str],
    width: int = BOX_WIDTH,
    side: int = TITLE_SIDE,
) -> str:
    """`body`, wrapped to fit, in a box `width` wide under `title`."""
    return "\n".join(
        [
            *box_open(title, width, side),
            *wrapped(body, width),
            *box_close(title, width, side),
        ]
    )


# ---
# Wrapping inside the box
# ---


def box_room(width: int = BOX_WIDTH) -> float:
    """How wide, in em, a line inside a box `width` `═` wide may look."""
    return visual_width(box_top(width))


def _is_emoji(token: str) -> bool:
    """Whether `token` is one custom emoji or one Unicode emoji character."""
    if re.fullmatch(_CUSTOM_EMOJI, token):
        return True
    return len(token) == 1 and _character_kind(token) == "emoji"


def _pieces(content: str) -> list[tuple[str, str]]:
    """`content` cut where a line may break, as (gap, word) pairs.

    A line may break at a single space, which the break swallows, between two
    emoji, and before a `・` that follows a word. A `・` is never left at the
    end of a row: it leads the next one, like one of Myra's bullets, so the
    space after a `・` is no break. Never inside bold text, a masked link or
    a run of spaces (Myra's padding), and never before the first word.
    """
    tokens = [token[0] for token in _TOKEN.finditer(content)]
    pieces: list[tuple[str, str]] = []
    gap, word, bold = "", "", False
    for index, token in enumerate(tokens):
        before = tokens[index - 1] if index else ""
        after = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token == "**":
            bold = not bold
        elif word.strip() and not bold:
            if token == " " and before not in (" ", _DOT) and after not in ("", " "):
                pieces.append((gap, word))
                gap, word = " ", ""
                continue
            if (_is_emoji(token) and _is_emoji(before)) or (
                token == _DOT and before not in (_DOT, " ")
            ):
                pieces.append((gap, word))
                gap, word = "", ""
        word += token
    pieces.append((gap, word))
    return pieces


def _joined(start: str, pieces: Sequence[tuple[str, str]]) -> str:
    """A row: `start`, then the pieces with every gap but the first."""
    (_, first), *rest = pieces
    return start + first + "".join(gap + word for gap, word in rest)


def _wrap_line(line: str, room: float) -> list[str]:
    """One box line broken at word boundaries so each row fits `room`.

    Rows after the first start with `║ `. A row that runs out of room breaks
    before its last `・` part, so each `・` part keeps together, unless that
    would leave the first row less than half full; otherwise it breaks before
    the word that did not fit. A word that alone is too wide stays whole on its
    row. A line that is not inside a box is left as it is.
    """
    if visual_width(line) <= room or not line.startswith(RAIL):
        return [line]
    mark = next(mark for mark in _MARKS if line.startswith(mark))
    first, *rest = _pieces(line[len(mark) :])
    rows: list[str] = []
    start, row = mark, [first]
    for piece in rest:
        if visual_width(_joined(start, [*row, piece])) <= room:
            row.append(piece)
            continue
        cut = next(
            (
                index
                for index in range(len(row) - 1, 0, -1)
                if row[index][1].startswith(_DOT)
                and not piece[1].startswith(_DOT)
                and (
                    start == CONTINUATION
                    or visual_width(_joined(start, row[:index])) >= room / 2
                )
            ),
            len(row),
        )
        rows.append(_joined(start, row[:cut]))
        start, row = CONTINUATION, [*row[cut:], piece]
        if len(row) > 1 and visual_width(_joined(start, row)) > room:
            rows.append(_joined(start, row[:-1]))
            row = [piece]
    return [*rows, _joined(start, row)]


def wrap(text: str, width: int = BOX_WIDTH) -> str:
    """Each box line of `text` broken so nothing passes a box `width` wide."""
    room = box_room(width)
    return "\n".join(row for line in text.split("\n") for row in _wrap_line(line, room))


def wrapped(lines: Sequence[str], width: int = BOX_WIDTH) -> list[str]:
    """`lines`, each wrapped to a box `width` wide; a wrapped entry keeps its rows
    together as one entry, so a list cut short drops whole entries."""
    return [wrap(line, width) for line in lines]


# ---
# Lengths and fitting
# ---


def with_emoji(emoji: str, text: str) -> str:
    """`text` after its emoji and a space, or alone when there is no emoji."""
    return f"{emoji} {text}" if emoji else text


def text_length(text: str) -> int:
    """The length of `text` counted in UTF-16 units, as JavaScript counts it.

    Characters outside the Basic Multilingual Plane, such as the frame's music
    symbols, count twice, so a text this fits never runs over Discord's limit
    however Discord counts it.
    """
    return len(text.encode("utf-16-le")) // 2


def clip(text: str, room: int) -> str:
    """The longest start of `text` within `room` UTF-16 units.

    It never ends inside a character, so a character outside the Basic
    Multilingual Plane is kept whole or left out.
    """
    used = 0
    for index, character in enumerate(text):
        used += text_length(character)
        if used > room:
            return text[:index]
    return text


def fit(head: list[str], optional: list[str], tail: Sequence[str] = ()) -> str:
    """Join `head`, as many whole `optional` lines as fit in one message, and `tail`.

    Optional lines are taken in order, so the ones to drop first go last. The
    message is measured by `text_length`.
    """
    lines = head
    for line in optional:
        if text_length("\n".join([*lines, line, *tail])) > MESSAGE_LIMIT:
            break
        lines = [*lines, line]
    return "\n".join([*lines, *tail])


def richest(plain: Sequence[str], rich: Sequence[str], room: int) -> list[str]:
    """`plain`, with each line swapped for its `rich` form while all still fit.

    Lines are tried in order, and a swap is kept only when the joined lines
    stay within `room`, counted by `text_length`. The plain lines are kept
    even when they do not fit.
    """
    lines = list(plain)
    for index, line in enumerate(rich):
        tried = [*lines[:index], line, *lines[index + 1 :]]
        if text_length("\n".join(tried)) <= room:
            lines = tried
    return lines


def count(amount: int, noun: str) -> str:
    """`amount` with `noun`, pluralised with an "s" unless the amount is one."""
    return f"{amount} {noun}" if amount == 1 else f"{amount} {noun}s"


def strip_emoji(text: str) -> str:
    """Remove Unicode emoji, keeping the ♪ and ♫ flair and every other character."""
    return _EMOJI.sub("", text)
