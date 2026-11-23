"""Wisp's Craving: the rules of the daily snack guess, without Discord.

Wisp craves one snack the member can buy. Each wrong guess leaves the menu
and earns a clearer hint; CRAVING_GUESSES wrong guesses lose the round.
"""

import random
from datetime import datetime
from enum import Enum

from wisp.lines import CRAVING_HINTS
from wisp.rules import CRAVING_GUESSES, CRAVING_TIMEOUT, PAID_SNACKS, Snack

# ---
# The round
# ---


class Verdict(Enum):
    """What one guess did: won the round, was wrong, or used the last guess."""

    RIGHT = "right"
    WRONG = "wrong"
    OUT = "out"


def pick_craving(rng: random.Random) -> Snack:
    """The snack Wisp craves today; never the free one."""
    return rng.choice(PAID_SNACKS)


def hint_for(round_snack: str, wrong: int) -> str:
    """Wisp's hint for `round_snack` after `wrong` wrong guesses, clearest last."""
    hints = CRAVING_HINTS[round_snack]
    return hints[min(wrong, len(hints) - 1)]


def snacks_left(guesses: tuple[str, ...]) -> tuple[Snack, ...]:
    """The snacks still on the menu once the wrong `guesses` are taken out."""
    return tuple(snack for snack in PAID_SNACKS if snack.key not in guesses)


def guesses_left(guesses: tuple[str, ...]) -> int:
    """How many guesses the member has left after the wrong `guesses`."""
    return CRAVING_GUESSES - len(guesses)


def judge(snack: str, guesses: tuple[str, ...], guess: str) -> Verdict:
    """Judge `guess` in a round craving `snack` with the wrong `guesses` so far."""
    if guess == snack:
        return Verdict.RIGHT
    if len(guesses) + 1 >= CRAVING_GUESSES:
        return Verdict.OUT
    return Verdict.WRONG


def is_idle(last_at: datetime, now: datetime) -> bool:
    """Whether a round last guessed at `last_at` has timed out by `now`."""
    return now - last_at > CRAVING_TIMEOUT
