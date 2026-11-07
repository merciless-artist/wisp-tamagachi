"""Text of Wisp's status card, in Myra's quote layout.

The card is one Discord quote with her Wisp Stats title picture attached, so
the picture shows under it and closes it. Each line is copied from her draft
of 2026-10-31, blank lines and line breaks included, apart from the Right now
block under the day and the one line pointing at the buttons under the card.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from wisp.chores import (
    is_napping,
    is_open,
    nap_ends_at,
    nap_time_text,
    next_nap_text,
)
from wisp.life import Life, Phase, age_days, has_sniffles, hours_left, is_sick
from wisp.rules import (
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    HANGRY_BELOW,
    HATCHING_TIME,
    HEALTH_MAX,
    LONELY_BELOW,
    WELLBEING_MAX,
    Chore,
)
from wisp.text import ITEM_CLEF, SUB_CLEF, channel_or, count, quoted, round_half_up

# ---
# Layout
# ---

WAITING: Final = quoted(
    ["", f"{SUB_CLEF} No Wisp right now. Waiting for staff to begin again."]
)

_RIGHT_NOW: Final = f"{SUB_CLEF} **right now**"
_LONELY: Final = "lonely: chat, play, poke or give him a snack or gift"
_CHORE_NEEDS: Final = {
    Chore.MESS: "a mess is waiting in his House",
    Chore.TANTRUM: "he's having a tantrum in his House",
    Chore.NAP: "he's asleep: turn the lights off in his House",
}
_HAPPY: Final = "happy"

_PERCENT_PER_PIECE: Final = 10
_LEFT_FROM: Final = 5
_MATH_BOLD_A: Final = 0x1D400

Emoji = Callable[[str], str]


@dataclass(frozen=True)
class BarEmoji:
    """A bar's app emojis: one `full` per whole 10%, one `left` for 5 more."""

    full: str
    left: str


HEALTH_BAR: Final = BarEmoji("full_full", "full_left")
WELLBEING_BAR: Final = BarEmoji("care_full", "care_left")
# The egg's Hatching bar and the hatching egg's Emerging bar.
EGG_BAR: Final = BarEmoji("happiness_full", "happiness_left")


@dataclass(frozen=True)
class CardFacts:
    """What the card shows besides the life itself.

    Attributes:
        fed_today: Members who fed Wisp or gave him a snack today (UTC).
        viibr_tracks: ViiBR tracks fed today (UTC).
        suno_tracks: Suno tracks fed today (UTC).
        wisp_id: Wisp's own Discord user ID, for the mention.
        house_id: The House channel's ID, or None when none is set.
        tracks_id: The track drop channel's ID, or None when none is set.
    """

    fed_today: int
    viibr_tracks: int
    suno_tracks: int
    wisp_id: int
    house_id: int | None
    tracks_id: int | None


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
            *_meter("Warmth", warmth, HEALTH_BAR, emoji),
            *_meter("Hatching", hatching, EGG_BAR, emoji),
        ]
        return _card([], bars, "the egg", "EGG", facts)
    if life.phase is Phase.HATCHING:
        emerging = _share(life.phase_seconds, HATCHING_TIME.total_seconds())
        bars = _meter("Emerging", emerging, EGG_BAR, emoji)
        return _card([], bars, "the egg", "HATCHING", facts)
    if life.phase is Phase.ALIVE:
        heading = [f"{SUB_CLEF}・・𝐃𝐀𝐘 **{age_days(life, now)}**・♫ ♪. ♫‿♪"]
        if is_sick(life):
            hours = hours_left(life.cold_left)
            heading.append(f"{SUB_CLEF} he has Monster Pox・{hours} h left")
        if has_sniffles(life):
            hours = hours_left(life.sniffles_left)
            heading.append(f"{SUB_CLEF} he has a cold・{hours} h left")
        health = life.health / HEALTH_MAX * 100
        wellbeing = life.wellbeing / WELLBEING_MAX * 100
        heading.extend(["", *_right_now(life, health, wellbeing, now, facts)])
        bars = [
            *_meter("Health", health, HEALTH_BAR, emoji),
            *_meter("Wellbeing", wellbeing, WELLBEING_BAR, emoji),
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
            f"{ITEM_CLEF} feed Wisp, shop the Vault and play",
            " with the buttons below!",
            "",
            "",
            f"{SUB_CLEF}・・**life stage**・{_bold(stage)}・♪‿♪ ♫.",
        ]
    )


def _right_now(
    life: Life, health: float, wellbeing: float, now: datetime, facts: CardFacts
) -> list[str]:
    """The Right now block: what he needs, worst first, then his nap.

    He is hungry while the Health bar shows a percent under the hangry line,
    lonely while the Wellbeing bar shows one under the lonely line, so the
    block always agrees with the bars; `health` and `wellbeing` are the bars'
    values from 0 to 100. Then each chore waiting in his House is named; with
    nothing to do he is happy. The last line is when he wakes while he naps,
    else when his next nap starts.
    """
    track_drop = channel_or("the track drop", facts.tracks_id)
    hungry = [f"hungry: drop a track in {track_drop}"]
    needs = [
        *(hungry if _shown_percent(health) < HANGRY_BELOW else []),
        *([_LONELY] if _shown_percent(wellbeing) < LONELY_BELOW else []),
        *(need for chore, need in _CHORE_NEEDS.items() if is_open(life, chore)),
    ]
    return [
        _RIGHT_NOW,
        *(f"{ITEM_CLEF} {need}" for need in needs or [_HAPPY]),
        f"{SUB_CLEF} {_nap_line(life, now)}",
    ]


def _nap_line(life: Life, now: datetime) -> str:
    """What the Right now block's last line says about his nap.

    While he naps it is when he wakes, such as "napping until 2pm Pacific";
    otherwise it is when his next nap starts.
    """
    if is_napping(life):
        return f"napping until {nap_time_text(nap_ends_at(life, now))}"
    return next_nap_text(now)


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
    percent = _shown_percent(value)
    tens, ones = divmod(percent, _PERCENT_PER_PIECE)
    end = left if ones >= _LEFT_FROM and left else " "
    return f"{full * tens}{end}│{percent}%"


def _shown_percent(value: float) -> int:
    """The whole percent a bar shows for a value from 0 to 100, rounded half up."""
    return round_half_up(min(max(value, 0.0), 100.0))


def _bold(text: str) -> str:
    """`text` with A to Z in Mathematical Bold capitals; other characters kept."""
    return "".join(
        chr(_MATH_BOLD_A + ord(letter) - ord("A")) if "A" <= letter <= "Z" else letter
        for letter in text
    )


def _meter(label: str, value: float, meter: BarEmoji, emoji: Emoji) -> list[str]:
    """The label's line, then the bar on its own line under it."""
    return [f"{ITEM_CLEF} {label}", bar(value, emoji(meter.full), emoji(meter.left))]


def _share(part: float, whole: float) -> float:
    """`part` as a percentage of `whole`, kept between 0 and 100."""
    return min(max(part / whole * 100, 0.0), 100.0)
