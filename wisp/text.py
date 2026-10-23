"""Small text pieces shared by Wisp's posts."""

import re
from typing import Final

SEPARATOR: Final = "・♪ ────────・──────── ♪・"
MESSAGE_LIMIT: Final = 2000
USER_ERROR: Final = "Something went wrong. Staff have been told."

# Pictographs, the technical, arrow and symbol blocks emoji come from (minus the
# music notes ♪ and ♫), ‼ and ⁉, plus the keycap, variation selector and
# zero-width joiner that build emoji sequences.
_EMOJI: Final = re.compile(
    "[\U0001f000-\U0001faff\u2300-\u23ff\u2600-\u2669\u266c-\u27bf"
    "\u2b00-\u2bff\u203c\u2049\u20e3\ufe0f\u200d]"
)


def count(amount: int, noun: str) -> str:
    """`amount` with `noun`, pluralised with an "s" unless the amount is one."""
    return f"{amount} {noun}" if amount == 1 else f"{amount} {noun}s"


def strip_emoji(text: str) -> str:
    """Remove Unicode emoji, keeping the ♪ and ♫ flair and every other character."""
    return _EMOJI.sub("", text)
