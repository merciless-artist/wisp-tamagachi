"""Small text pieces shared by Wisp's posts."""

import re
from typing import Final

SEPARATOR: Final = "・♪ ────────・──────── ♪・"
MESSAGE_LIMIT: Final = 2000
USER_ERROR: Final = "Something went wrong. Staff have been told."

# Pictographs and symbol emoji, minus the music notes ♪ and ♫, plus the
# variation selector and zero-width joiner that build emoji sequences.
_EMOJI: Final = re.compile("[\U0001f000-\U0001faff☀-♩♬-➿️‍]")


def count(amount: int, noun: str) -> str:
    """`amount` with `noun`, pluralised with an "s" unless the amount is one."""
    return f"{amount} {noun}" if amount == 1 else f"{amount} {noun}s"


def strip_emoji(text: str) -> str:
    """Remove Unicode emoji, keeping the ♪ and ♫ flair and every other character."""
    return _EMOJI.sub("", text)
