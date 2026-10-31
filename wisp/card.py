"""Text of Wisp's status card, in Myra's quote layout.

The card is one Discord quote with her Wisp Stats title picture attached, so
the picture shows under it and closes it. Each line is copied from her draft
of 2026-10-31, blank lines and line breaks included.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from wisp.life import Life, Phase, age_days, is_sick
from wisp.rules import (
    CARE_MAX,
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    FULL_MAX,
    HATCHING_TIME,
)
from wisp.text import ITEM_CLEF, SUB_CLEF, count, quoted

# ---
# Layout
# ---

WAITING: Final = quoted(
    ["", f"{SUB_CLEF} No Wisp right now. Waiting for staff to begin again."]
)

_PERCENT_PER_PIECE: Final = 10
_LEFT_FROM: Final = 5
_MATH_BOLD_A: Final = 0x1D400
_HOUR: Final = timedelta(hours=1).total_seconds()

Emoji = Callable[[str], str]


@dataclass(frozen=True)
class Meter:
    """A bar's app emojis: one `full` per whole 10%, one `left` for 5 more."""

    full: str
    left: str


CARE: Final = Meter("care_full", "care_left")
HAPPY: Final = Meter("happiness_full", "happiness_left")
HUNGER: Final = Meter("full_full", "full_left")


@dataclass(frozen=True)
class CardFacts:
    """What the card shows besides the life itself.

    Attributes:
        happiness: The Happy meter, 0 to 100.
        fed_today: Members who fed Wisp or gave him a snack today (UTC).
        viibr_tracks: ViiBR tracks fed today (UTC).
        suno_tracks: Suno tracks fed today (UTC).
        wisp_id: Wisp's own Discord user ID, for the mention.
        house_id: The House channel's ID, or None when none is set.
    """

    happiness: int
    fed_today: int
    viibr_tracks: int
    suno_tracks: int
    wisp_id: int
    house_id: int | None


# ---
# The card
# ---


def render_status(life: Life, now: datetime, facts: CardFacts, emoji: Emoji) -> str:
    """The status card for an egg, a hatching egg or a living Wisp.

    `emoji` gives an app emoji's text by name, or "" when it is not uploaded.

    Raises:
        ValueError: The life is over, so it has no card.
    """
    if life.phase is Phase.EGG:
        warmth = 100 - _share(life.phase_seconds, EGG_WARMTH.total_seconds())
        hatching = _share(life.egg_food, EGG_FOOD_NEEDED)
        bars = [
            *_meter("Warmth", warmth, HUNGER, emoji),
            *_meter("Hatching", hatching, HAPPY, emoji),
        ]
        return _card([], bars, "the egg", "EGG", facts)
    if life.phase is Phase.HATCHING:
        emerging = _share(life.phase_seconds, HATCHING_TIME.total_seconds())
        bars = _meter("Emerging", emerging, HAPPY, emoji)
        return _card([], bars, "the egg", "HATCHING", facts)
    if life.phase is Phase.ALIVE:
        heading = [f"{SUB_CLEF}・・𝐃𝐀𝐘 **{age_days(life, now)}**・♫ ♪. ♫‿♪"]
        if is_sick(life):
            hours = math.ceil(life.cold_left / _HOUR)
            heading.append(f"{SUB_CLEF} he has Monster Pox・{hours} h left")
        bars = [
            *_meter("Care", life.care / CARE_MAX * 100, CARE, emoji),
            *_meter("Happy", facts.happiness, HAPPY, emoji),
            *_meter("Hunger", life.full / FULL_MAX * 100, HUNGER, emoji),
        ]
        return _card(heading, bars, "him", life.stage.label.upper(), facts)
    raise ValueError(f"A finished life has no status card (phase {life.phase}).")


def _card(
    heading: list[str], bars: list[str], poke: str, stage: str, facts: CardFacts
) -> str:
    """Myra's quote: the heading, the bars, the facts, the hints and the stage.

    An egg has no heading, so its bars follow the first blank line.
    """
    people = "person" if facts.fed_today == 1 else "people"
    tracks = (
        f"{count(facts.viibr_tracks, 'ViiBR track')} and "
        f"{count(facts.suno_tracks, 'Suno track')}"
    )
    house = "his House" if facts.house_id is None else f"<#{facts.house_id}>"
    return quoted(
        [
            "",
            *([*heading, ""] if heading else []),
            *bars,
            "",
            f"{SUB_CLEF} Fed by {facts.fed_today:02d} {people} today・♬‿♩. ♪",
            "",
            f"{SUB_CLEF} {tracks} ・♪‿♫ ♪",
            "",
            f"{ITEM_CLEF} Poke {poke} or tag <@{facts.wisp_id}> in {house} "
            "to say hi!!",
            "",
            f"{ITEM_CLEF} check your snackpack with /wisp",
            " snackpack",
            "",
            f"{ITEM_CLEF} check the ViiBR Vault to buy treats",
            " and toys for Wisp!",
            "",
            "",
            f"{SUB_CLEF}・・**life stage**・{_bold(stage)}・♪‿♪ ♫.",
        ]
    )


# ---
# Pieces
# ---


def bar(value: float, full: str, left: str) -> str:
    """A meter for a value from 0 to 100, then `│` and the percent.

    The percent is rounded half up. There is one `full` piece per whole 10% of
    it, and one `left` piece when its last digit is 5 to 9. A bar without a
    `left` piece, including one whose `left` is not uploaded, has a space
    before the `│`.
    """
    percent = int(min(max(value, 0.0), 100.0) + 0.5)
    tens, ones = divmod(percent, _PERCENT_PER_PIECE)
    end = left if ones >= _LEFT_FROM and left else " "
    return f"{full * tens}{end}│{percent}%"


def _bold(text: str) -> str:
    """`text` with A to Z in Mathematical Bold capitals; other characters kept."""
    return "".join(
        chr(_MATH_BOLD_A + ord(letter) - ord("A")) if "A" <= letter <= "Z" else letter
        for letter in text
    )


def _meter(label: str, value: float, meter: Meter, emoji: Emoji) -> list[str]:
    """The label's line, then the bar on its own line under it."""
    return [f"{ITEM_CLEF} {label}", bar(value, emoji(meter.full), emoji(meter.left))]


def _share(part: float, whole: float) -> float:
    """`part` as a percentage of `whole`, kept between 0 and 100."""
    return min(max(part / whole * 100, 0.0), 100.0)
