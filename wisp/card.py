"""Text of Wisp's status card, in WiSP's Favorites style (house style v4).

The card sits under her Wisp Stats title picture: its title line, the day and
what he needs right now, his meters, then under Today the day's facts and
the buttons' hint, then his life stage and the footer line. Each meter is two
lines, its name and its bar, between `SPACER` lines as the Favorites' songs
are.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from wisp.chores import (
    dozes_off_at,
    is_napping,
    is_open,
    nap_ends_at,
    next_nap_start,
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
from wisp.text import SPACER, Frame, channel_or, count, round_half_up, timestamp

# ---
# Layout
# ---

_TITLE: Final = "Wisp stats"
_WAITING: Final = "No Wisp right now. Waiting for staff to begin again."
_RIGHT_NOW: Final = "Right now"
_TODAY: Final = "Today"
_LONELY: Final = "lonely: chat, play, poke or give him a snack or gift"
_CHORE_NEEDS: Final = {
    Chore.MESS: "a mess is waiting in his House",
    Chore.TANTRUM: "he's having a tantrum in his House",
    Chore.NAP: "it's nap time: turn the lights off in his House",
}
_POX_NEED: Final = "Monster Pox: feed him tracks in"
_HAPPY: Final = "happy"
# Each section's place in the card, for its icon.
_DAY: Final = 0
_NOW: Final = 1
_FACTS: Final = 2
_STAGE: Final = 3

_PERCENT_PER_PIECE: Final = 10
_LEFT_FROM: Final = 5

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


def waiting(frame: Frame) -> str:
    """The card while there is no Wisp: its title, one line, then the footer."""
    return "\n".join([frame.title(_TITLE), frame.item(_WAITING), frame.footer])


def render_status(
    life: Life, now: datetime, facts: CardFacts, emoji: Emoji, frame: Frame
) -> str:
    """The status card in `frame` for an egg, a hatching egg or a living Wisp.

    `emoji` gives an app emoji's text by name, or "" when it is not uploaded.

    Raises:
        ValueError: The life is over, so it has no card.
    """
    if life.phase is Phase.EGG:
        warmth = 100 - _share(life.phase_seconds, EGG_WARMTH.total_seconds())
        hatching = _share(life.egg_food, EGG_FOOD_NEEDED)
        bars = _meters(
            _meter(frame, "Warmth", warmth, HEALTH_BAR, emoji),
            _meter(frame, "Hatching", hatching, EGG_BAR, emoji),
        )
        return _card(frame, [], bars, "the egg", "Egg", facts)
    if life.phase is Phase.HATCHING:
        emerging = _share(life.phase_seconds, HATCHING_TIME.total_seconds())
        bars = _meters(_meter(frame, "Emerging", emerging, EGG_BAR, emoji))
        return _card(frame, [], bars, "the egg", "Hatching", facts)
    if life.phase is Phase.ALIVE:
        heading = [frame.heading(f"Day {age_days(life, now)} ・ ♫ ♪. ♫‿♪", _DAY)]
        if is_sick(life):
            hours = hours_left(life.cold_left)
            heading.append(frame.item(f"he has Monster Pox ・ {hours} h left"))
        if has_sniffles(life):
            hours = hours_left(life.sniffles_left)
            heading.append(frame.item(f"he has a cold ・ {hours} h left"))
        health = life.health / HEALTH_MAX * 100
        wellbeing = life.wellbeing / WELLBEING_MAX * 100
        heading.extend(_right_now(frame, life, health, wellbeing, now, facts))
        bars = _meters(
            _meter(frame, "Health", health, HEALTH_BAR, emoji),
            _meter(frame, "Wellbeing", wellbeing, WELLBEING_BAR, emoji),
        )
        return _card(frame, heading, bars, "him", life.stage.label, facts)
    raise ValueError(f"A finished life has no status card (phase {life.phase}).")


def _card(
    frame: Frame,
    heading: list[str],
    bars: list[str],
    poke: str,
    stage: str,
    facts: CardFacts,
) -> str:
    """The card: title, heading, bars, Today's facts and hints, then the stage.

    An egg has no heading, so its card opens with its bars under the title.
    """
    people = "person" if facts.fed_today == 1 else "people"
    tracks = (
        f"{count(facts.viibr_tracks, 'ViiBR track')} and "
        f"{count(facts.suno_tracks, 'Suno track')}"
    )
    house = "his House" if facts.house_id is None else f"<#{facts.house_id}>"
    lines = [
        frame.heading(_TODAY, _FACTS),
        frame.item(f"Fed by {facts.fed_today:02d} {people} today"),
        frame.item(tracks),
        frame.item(f"Poke {poke} or tag <@{facts.wisp_id}> in {house} to say hi!!"),
        frame.item("feed Wisp, shop the Vault and play: tap Interaction below!"),
        frame.heading(f"Life stage ・ {stage}", _STAGE),
        frame.footer,
    ]
    return "\n".join([frame.title(_TITLE), *heading, *bars, *lines])


def _right_now(
    frame: Frame,
    life: Life,
    health: float,
    wellbeing: float,
    now: datetime,
    facts: CardFacts,
) -> list[str]:
    """The Right now block: what he needs, worst first, then his nap.

    While he has Monster Pox the first need says how to get him better, and it
    stands in for the hungry line, since both ask for tracks. Otherwise he is
    hungry while the Health bar shows a percent under the hangry line,
    lonely while the Wellbeing bar shows one under the lonely line, so the
    block always agrees with the bars; `health` and `wellbeing` are the bars'
    values from 0 to 100. Then each chore waiting in his House is named; with
    nothing to do he is happy. The last line is when he wakes while he naps,
    when he dozes off again while a poke has him up, else when his next nap
    starts.
    """
    track_drop = channel_or("the track drop", facts.tracks_id)
    if is_sick(life):
        food = [f"{_POX_NEED} {track_drop}: every meal gets him better faster"]
    elif _shown_percent(health) < HANGRY_BELOW:
        food = [f"hungry: drop a track in {track_drop}"]
    else:
        food = []
    needs = [
        *food,
        *([_LONELY] if _shown_percent(wellbeing) < LONELY_BELOW else []),
        *(need for chore, need in _CHORE_NEEDS.items() if is_open(life, chore)),
    ]
    return [
        frame.heading(_RIGHT_NOW, _NOW),
        *(frame.item(need) for need in needs or [_HAPPY]),
        frame.item(_nap_line(life, now)),
    ]


def _nap_line(life: Life, now: datetime) -> str:
    """What the Right now block's last line says about his nap.

    While he naps it is when he wakes, while a poke has him up when he dozes
    off again, otherwise when his next nap starts, each a timestamp members
    see in their own time zone.
    """
    if is_napping(life):
        return f"napping until {timestamp(nap_ends_at(life, now))}"
    dozes = dozes_off_at(life, now)
    if dozes is not None:
        return f"back to sleep {timestamp(dozes)}"
    return f"next nap {timestamp(next_nap_start(now))}"


# ---
# Pieces
# ---


def bar(value: float, full: str, left: str) -> str:
    """A meter for a value from 0 to 100, then a space and the percent.

    The percent is rounded half up. There is one `full` piece per whole 10% of
    it, and one `left` piece when its last digit is 5 to 9 and it is
    uploaded. With no pieces it is the percent alone.
    """
    percent = _shown_percent(value)
    tens, ones = divmod(percent, _PERCENT_PER_PIECE)
    pieces = full * tens + (left if ones >= _LEFT_FROM else "")
    return f"{pieces} {percent}%" if pieces else f"{percent}%"


def _shown_percent(value: float) -> int:
    """The whole percent a bar shows for a value from 0 to 100, rounded half up."""
    return round_half_up(min(max(value, 0.0), 100.0))


def _meter(
    frame: Frame, label: str, value: float, meter: BarEmoji, emoji: Emoji
) -> list[str]:
    """The meter's two lines: its name in bold, then its bar."""
    shown = bar(value, emoji(meter.full), emoji(meter.left))
    return [frame.note(f"**{label}**"), frame.note(shown)]


def _meters(*meters: list[str]) -> list[str]:
    """The meters' lines, a `SPACER` line before each meter and after the last."""
    return [*(line for meter in meters for line in (SPACER, *meter)), SPACER]


def _share(part: float, whole: float) -> float:
    """`part` as a percentage of `whole`, kept between 0 and 100."""
    return min(max(part / whole * 100, 0.0), 100.0)
