"""Gifts for Wisp: what the Vault has in stock and whether he keeps one.

Pure game logic. Nothing here touches the database, Discord or the clock.
"""

import random
from dataclasses import dataclass
from enum import StrEnum, auto

from wisp.rules import (
    GIFT_COLLECTIONS,
    GIFT_LIKE_CHANCE,
    GIFT_LIKE_RISE,
    TV_SHOWS,
    Gift,
    GiftCollection,
    Stage,
    TvShow,
)

_VOWELS = frozenset("AEIOUaeiou")
# Letters whose names start with a vowel sound: "an L Block", "an S Block".
_VOWEL_LETTERS = frozenset("AEFHILMNORSX")
_STAGE_ORDER = tuple(Stage)


class Outcome(StrEnum):
    """What Wisp does with a gift."""

    KEPT = auto()
    PASSED = auto()
    FULL = auto()


@dataclass(frozen=True)
class GiftState:
    """The gifts of one life on one UTC day.

    `kept` holds the keys of the gifts he kept this life, `given_today` the keys
    of the collections someone gave from today, `kept_today` whether he
    kept one today, and `stage` the stage he is at, which a growing gift's
    look follows.
    """

    kept: frozenset[str]
    given_today: frozenset[str]
    kept_today: bool
    stage: Stage

    def emoji_name(self, gift: Gift) -> str:
        """Name of the app emoji that shows `gift` now."""
        return gift.emoji_name(self.stage)

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


def like_chance(state: GiftState) -> float:
    """His chance of keeping the next gift on a day he has kept none yet.

    Every gift given today was passed on, one per collection, and each one
    makes him `GIFT_LIKE_RISE` more open to the next.
    """
    return min(1.0, GIFT_LIKE_CHANCE + GIFT_LIKE_RISE * len(state.given_today))


def decide(state: GiftState, rng: random.Random) -> Outcome:
    """Whether he keeps a gift: full after one kept today, else a roll of `rng`."""
    if state.kept_today:
        return Outcome.FULL
    return Outcome.KEPT if rng.random() < like_chance(state) else Outcome.PASSED


def with_article(title: str) -> str:
    """`title` after "a", or "an" before a vowel sound.

    A first word that is a single letter is read as the letter's name, so it
    is "an L Block" but "a T Block".
    """
    first = title.split(" ", 1)[0]
    vowels = _VOWEL_LETTERS if len(first) == 1 else _VOWELS
    return f"an {title}" if first[:1] in vowels else f"a {title}"


def named(gift: Gift) -> str:
    """One gift as messages name it after "gave Wisp".

    "a Red Book" or "an Arcade"; a plural title stands alone, as "TV Shows".
    """
    return gift.title if gift.plural else with_article(gift.title)


@dataclass(frozen=True)
class Episode:
    """One episode on Wisp's TV: its show, its number from 1 and its link."""

    show: TvShow
    number: int
    link: str


def tv_episode(
    kept_at: Stage, stage: Stage, skipped: frozenset[Stage] = frozenset()
) -> Episode | None:
    """The episode on his TV at `stage`, for a TV he kept at `kept_at`.

    The show is the one for `stage`. It starts at episode 1 on the stage he
    kept the TV, or on the show's first stage when he kept it during the
    other show, and moves on one episode for each of its stages he lived in,
    so a `skipped` stage skips no episode. None at a stage no show has, a
    skipped one, or one before he had the TV.
    """
    if _STAGE_ORDER.index(stage) < _STAGE_ORDER.index(kept_at):
        return None
    show = next((show for show in TV_SHOWS if stage in show.stages), None)
    if show is None or stage in skipped:
        return None
    lived = [each for each in show.stages if each not in skipped]
    start = lived.index(kept_at) if kept_at in lived else 0
    number = lived.index(stage) - start
    return Episode(show, number + 1, show.episodes[number])


def tv_line(episode: Episode) -> str:
    """The House line that says what is on his TV now."""
    return (
        f"♪ Now on Wisp's TV: {episode.show.name}, episode {episode.number}\n"
        f"{episode.link}"
    )
