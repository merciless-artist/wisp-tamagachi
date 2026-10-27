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
_EMOJI: Final = re.compile("[\U0001f000-\U0001faff⌀-⏿☀-♩♬-➿" "⬀-⯿‼⁉⃣️‍]")

# ---
# The house style frame
# ---

SEPARATOR: Final = "𝄡" + "𝄚" * 22 + "𝄂"
BOX_TOP: Final = "╔" + "═" * 20 + "╗"
BOX_BOTTOM: Final = "╚" + "═" * 20 + "╝"
BOTTOM_BAR: Final = "𝄃𝄣" + "𝄚" * 20 + "𝄂"
BOX_CLOSE: Final = (BOX_BOTTOM, BOTTOM_BAR)
SECTION_BREAK: Final = "╠═══⇕"
RAIL: Final = "║"
HEADING_MARK: Final = "║𝄡𝄚𝄂𝄆"
SUB_MARK: Final = "║𝄡𝄚𝄂"
ITEM_MARK: Final = "║𝄡"
_TITLE_LEFT: Final = "𝄃𝄞" + "𝄚" * 4 + "𝄆"
_TITLE_RIGHT: Final = "𝄇𝄡" + "𝄚" * 4 + "𝄂"


def title_bar(title: str) -> str:
    """The bar above the box, with `title` between the repeat signs."""
    return f"{_TITLE_LEFT} {title} {_TITLE_RIGHT}"


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


def box_open(title: str) -> list[str]:
    """The title bar and the top of the box."""
    return [title_bar(title), BOX_TOP]


def sections(*parts: Sequence[str]) -> list[str]:
    """The lines of each part, with a section break between parts."""
    lines: list[str] = []
    for index, part in enumerate(parts):
        if index:
            lines.append(SECTION_BREAK)
        lines.extend(part)
    return lines


def framed(title: str, body: Sequence[str]) -> str:
    """`body` in the box under `title`, closed by the bottom bar."""
    return "\n".join([*box_open(title), *body, *BOX_CLOSE])


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
