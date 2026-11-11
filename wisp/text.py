"""Small text pieces shared by Wisp's posts, and the frame of Myra's house style.

The house style is `DOCS/specs/2026-10-27-house-style.md`. Its marks work like
markdown: `#` is a section heading, `##` a sub-heading or information line, `###`
an item, `>` the break between sections and `>>>` the end of the box.
"""

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final, TypeVar

MESSAGE_LIMIT: Final = 2000
LAYOUT_TEXT_LIMIT: Final = 4000
USER_ERROR: Final = "That didn't work. The error is posted in this channel."

_Words = TypeVar("_Words", bound=str | None)

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
SECTION_BREAK: Final = "╠═══⇕"
RAIL: Final = "║"
BLANK: Final = RAIL
SUB_CLEF: Final = "𝄡𝄚𝄂"
ITEM_CLEF: Final = "𝄡"
HEADING_MARK: Final = f"{RAIL}{SUB_CLEF}𝄆"
SUB_MARK: Final = f"{RAIL}{SUB_CLEF}"
ITEM_MARK: Final = f"{RAIL}{ITEM_CLEF}"
QUOTE: Final = "> "
CONTINUATION: Final = f"{RAIL} "
_MARKS: Final = (HEADING_MARK, SUB_MARK, ITEM_MARK, RAIL)


def box_top(width: int = BOX_WIDTH) -> str:
    """The top of a box `width` `═` wide."""
    return "╔" + "═" * width + "╗"


def box_bottom(width: int = BOX_WIDTH) -> str:
    """The bottom of a box `width` `═` wide."""
    return "╚" + "═" * width + "╝"


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


def sections(*parts: Sequence[str]) -> list[str]:
    """The lines of each part, with a section break between parts."""
    lines: list[str] = []
    for index, part in enumerate(parts):
        if index:
            lines.append(SECTION_BREAK)
        lines.extend(part)
    return lines


def quoted(lines: Sequence[str]) -> str:
    """`lines` as one Discord quote: each starts with `> `, an empty one too."""
    return "\n".join(QUOTE + line for line in lines)


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


def _wrap_line(
    line: str,
    room: float,
    marks: Sequence[str] = _MARKS,
    continuation: str = CONTINUATION,
) -> list[str]:
    """One box line broken at word boundaries so each row fits `room`.

    `marks` are the frame's line starts, longest first, and rows after the
    first start with `continuation`. A row that runs out of room breaks
    before its last `・` part, so each `・` part keeps together, unless that
    would leave the first row less than half full; otherwise it breaks before
    the word that did not fit. A word that alone is too wide stays whole on its
    row. A line that is not inside a box is left as it is.
    """
    mark = next((mark for mark in marks if line.startswith(mark)), None)
    if visual_width(line) <= room or mark is None:
        return [line]
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
                    start == continuation
                    or visual_width(_joined(start, row[:index])) >= room / 2
                )
            ),
            len(row),
        )
        rows.append(_joined(start, row[:cut]))
        start, row = continuation, [*row[cut:], piece]
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
# The emoji frame (house style v3)
# ---

# Wisp's app emojis the v3 frame is made of, in the order `emoji_frame` takes.
FRAME_EMOJIS: Final = (
    "header_edge",
    "header",
    "header2",
    "header3",
    "rest_bar",
    "clef",
)
_BOTTOM_BARS: Final = 16


@dataclass(frozen=True)
class Frame:
    """The pieces of a house-style box: Myra's emoji frame, or the old Unicode one.

    The house style is `DOCS/specs/2026-11-11-house-style-v3-emoji-frame.md`.
    Headings are in capitals. Nothing in the box may look wider than its
    bottom line; `wrap` breaks longer lines onto rows that start with the
    blank edge and a space.
    """

    heading_mark: str
    sub_mark: str
    item_mark: str
    blank: str
    section_break: str
    group_break: str
    bottom: str
    divider: str

    @property
    def continuation(self) -> str:
        """The start of a wrapped line's later rows."""
        return f"{self.blank} "

    @property
    def room(self) -> float:
        """How wide, in em, a line inside the box may look: as wide as its bottom."""
        return visual_width(self.bottom)

    def heading(self, name: str) -> str:
        """A `#` line: a section heading, in capitals."""
        return f"{self.heading_mark} {name.upper()}"

    def sub(self, text: str) -> str:
        """A `##` line: a sub-heading or an information line."""
        return f"{self.sub_mark} {text}"

    def item(self, text: str) -> str:
        """A `###` line: one item."""
        return f"{self.item_mark} {text}"

    def note(self, text: str) -> str:
        """A plain line inside the box."""
        return f"{self.blank} {text}"

    def sections(self, *parts: Sequence[str]) -> list[str]:
        """The lines of each part, with a section break between parts."""
        lines: list[str] = []
        for index, part in enumerate(parts):
            if index:
                lines.append(self.section_break)
            lines.extend(part)
        return lines

    def wrap(self, text: str) -> str:
        """Each line of `text` broken so nothing looks wider than the box."""
        marks = (self.heading_mark, self.sub_mark, self.item_mark, self.blank)
        return "\n".join(
            row
            for line in text.split("\n")
            for row in _wrap_line(line, self.room, marks, self.continuation)
        )


def emoji_frame(
    edge: str, header: str, header2: str, header3: str, rest_bar: str, clef: str
) -> Frame:
    """Myra's emoji frame, from the text of each of its `FRAME_EMOJIS`."""
    return Frame(
        heading_mark=f"{edge}{header2}{header}",
        sub_mark=f"{edge}{header}",
        item_mark=f"{edge}{header3}",
        blank=edge,
        section_break=f"{edge}{rest_bar}{rest_bar}",
        group_break=f"{edge}{rest_bar}",
        bottom=f"{edge} {clef}{header2 * _BOTTOM_BARS}{header}",
        divider=f"{clef}{header2 * _BOTTOM_BARS}{header}",
    )


UNICODE_FRAME: Final = Frame(
    heading_mark=HEADING_MARK,
    sub_mark=SUB_MARK,
    item_mark=ITEM_MARK,
    blank=RAIL,
    section_break=SECTION_BREAK,
    group_break=RAIL,
    bottom=box_bottom(),
    divider=SEPARATOR,
)


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


def fit(
    head: list[str],
    optional: list[str],
    tail: Sequence[str] = (),
    limit: int = MESSAGE_LIMIT,
) -> str:
    """Join `head`, as many whole `optional` lines as fit in `limit`, and `tail`.

    Optional lines are taken in order, so the ones to drop first go last. The
    text is measured by `text_length`.
    """
    lines = head
    for line in optional:
        if text_length("\n".join([*lines, line, *tail])) > limit:
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


def any_role(role_ids: Collection[int], shown: int) -> str:
    """The roles as mentions, any one of which will do: "<@&1>, <@&2> or <@&3>".

    At most `shown` are named, lowest id first, then how many more there are,
    as in "<@&1>, <@&2> or 3 more". Empty when there are none. A mention only
    pings when the send allows it.
    """
    mentions = [f"<@&{role_id}>" for role_id in sorted(role_ids)]
    if len(mentions) > shown:
        named = mentions[:shown]
        return f"{', '.join(named)} or {len(mentions) - shown} more"
    if len(mentions) < 2:
        return "".join(mentions)
    return f"{', '.join(mentions[:-1])} or {mentions[-1]}"


def channel_or(words: _Words, channel_id: int | None) -> str | _Words:
    """The channel's link, `<#id>`, or `words` when no channel is given."""
    return words if channel_id is None else f"<#{channel_id}>"


def round_half_up(value: float) -> int:
    """`value` as a whole number, a half rounding up, as the status card shows it."""
    return int(value + 0.5)


def meter_receipt(meter: str, before: float, after: float) -> str:
    """What a meter did, as whole numbers: `Wellbeing +8 (now 66)`.

    The change is the difference of the shown numbers, so it always adds up.
    """
    shown = round_half_up(after)
    change = shown - round_half_up(before)
    return f"{meter} {change:+d} (now {shown})"


def strip_emoji(text: str) -> str:
    """Remove Unicode emoji, keeping the ♪ and ♫ flair and every other character."""
    return _EMOJI.sub("", text)
