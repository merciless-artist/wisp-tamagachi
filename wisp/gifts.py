"""Gifts for Wisp: what the Vault has in stock and whether he keeps one.

Pure game logic. Nothing here touches the database, Discord or the clock.
"""

import random
from dataclasses import dataclass
from enum import StrEnum, auto

from wisp.rules import GIFT_COLLECTIONS, GIFT_LIKE_CHANCE, Gift, GiftCollection

_VOWELS = frozenset("AEIOUaeiou")
# Letters whose names start with a vowel sound: "an L Block", "an S Block".
_VOWEL_LETTERS = frozenset("AEFHILMNORSX")


class Outcome(StrEnum):
    """What Wisp does with a gift."""

    KEPT = auto()
    PASSED = auto()
    FULL = auto()


@dataclass(frozen=True)
class GiftState:
    """The gifts of one life on one UTC day.

    `kept` holds the keys of the gifts he kept this life, `given_today` the keys
    of the collections someone gave from today, and `kept_today` whether he
    kept one today.
    """

    kept: frozenset[str]
    given_today: frozenset[str]
    kept_today: bool

    def in_stock(self, gift: Gift) -> bool:
        """Whether the Vault still has this gift: he has not kept it this life."""
        return gift.key not in self.kept

    def is_open(self, collection: GiftCollection) -> bool:
        """Whether nobody has given from this collection today."""
        return collection.key not in self.given_today

    def can_give(self, gift: Gift) -> bool:
        """Whether a member can give this gift now."""
        return self.in_stock(gift) and self.is_open(collection_of(gift))

    def offered_from(self, collection: GiftCollection) -> list[Gift]:
        """The collection's gifts that can be given now, in catalog order."""
        return [gift for gift in collection.gifts if self.can_give(gift)]

    def completes(self, gift: Gift) -> bool:
        """Whether keeping this gift would finish its collection."""
        collection = collection_of(gift)
        return all(
            other.key == gift.key or other.key in self.kept
            for other in collection.gifts
        )


def collection_of(gift: Gift) -> GiftCollection:
    """The collection a gift belongs to."""
    return next(group for group in GIFT_COLLECTIONS if group.key == gift.collection)


def decide(state: GiftState, rng: random.Random) -> Outcome:
    """Whether he keeps a gift: full after one kept today, else a roll of `rng`."""
    if state.kept_today:
        return Outcome.FULL
    return Outcome.KEPT if rng.random() < GIFT_LIKE_CHANCE else Outcome.PASSED


def with_article(title: str) -> str:
    """`title` after "a", or "an" before a vowel sound.

    A first word that is a single letter is read as the letter's name, so it
    is "an L Block" but "a T Block".
    """
    first = title.split(" ", 1)[0]
    vowels = _VOWEL_LETTERS if len(first) == 1 else _VOWELS
    return f"an {title}" if first[:1] in vowels else f"a {title}"
