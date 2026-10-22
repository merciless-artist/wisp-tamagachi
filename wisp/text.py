"""Small text pieces shared by Wisp's posts."""

from typing import Final

SEPARATOR: Final = "・♪ ────────・──────── ♪・"
MESSAGE_LIMIT: Final = 2000
USER_ERROR: Final = "Something went wrong. Staff have been told."


def count(amount: int, noun: str) -> str:
    """`amount` with `noun`, pluralised with an "s" unless the amount is one."""
    return f"{amount} {noun}" if amount == 1 else f"{amount} {noun}s"
