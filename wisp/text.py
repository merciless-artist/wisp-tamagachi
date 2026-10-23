"""Small text pieces shared by Wisp's posts."""

import re
from collections.abc import Sequence
from typing import Final

SEPARATOR: Final = "・♪ ────────・──────── ♪・"
MESSAGE_LIMIT: Final = 2000
USER_ERROR: Final = "That didn't work. The error is posted in this channel."

# Pictographs, the technical, arrow and symbol blocks emoji come from (minus the
# music notes ♪ and ♫), ‼ and ⁉, plus the keycap, variation selector and
# zero-width joiner that build emoji sequences.
_EMOJI: Final = re.compile(
    "[\U0001f000-\U0001faff\u2300-\u23ff\u2600-\u2669\u266c-\u27bf"
    "\u2b00-\u2bff\u203c\u2049\u20e3\ufe0f\u200d]"
)


def with_emoji(emoji: str, text: str) -> str:
    """`text` after its emoji and a space, or alone when there is no emoji."""
    return f"{emoji} {text}" if emoji else text


def fit(head: list[str], optional: list[str], tail: Sequence[str] = ()) -> str:
    """Join `head`, as many whole `optional` lines as fit in one message, and `tail`.

    Optional lines are taken in order, so the ones to drop first go last.
    """
    lines = head
    for line in optional:
        if len("\n".join([*lines, line, *tail])) > MESSAGE_LIMIT:
            break
        lines = [*lines, line]
    return "\n".join([*lines, *tail])


def count(amount: int, noun: str) -> str:
    """`amount` with `noun`, pluralised with an "s" unless the amount is one."""
    return f"{amount} {noun}" if amount == 1 else f"{amount} {noun}s"


def strip_emoji(text: str) -> str:
    """Remove Unicode emoji, keeping the ♪ and ♫ flair and every other character."""
    return _EMOJI.sub("", text)
