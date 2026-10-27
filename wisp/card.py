"""Text of Wisp's status card, in the frame of Myra's template.

Her template is `DOCS/specs/status_menu_template.txt`. The frame lines and the
`▐` lines with trailing spaces are copied from it exactly, spaces included.
"""

import math
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
from wisp.text import count

# ---
# Layout
# ---

_PERCENT_PER_SQUARE: Final = 10
_MATH_BOLD_A: Final = 0x1D400
_HOUR: Final = timedelta(hours=1).total_seconds()

# Spaces after each bar label, so the bars of one card start in the same
# column in Discord's proportional font. Myra tuned Care 6, Happy 3 and
# Hunger 1 by eye; "Full" is narrower than "Care", so it gets two more. On
# the egg cards the longest label gets one space, like Hunger did. Adjust
# from her screenshot.
LABEL_PADDING: Final[dict[str, int]] = {
    "Full": 8,
    "Happy": 3,
    "Care": 6,
    "Warmth": 3,
    "Hatching": 1,
    "Emerging": 1,
}

_TOP: Final = "▐" + "▀" * 10 + " 🔸❱━ Wisp Stats ━❰🔸" + "▀" * 11 + "▌"
_RULE: Final = "▐" + "━" * 37 + "❰❰"
_TITLE_RULE: Final = _RULE + " " * 8
_GAP: Final = "▐"
_GAP_ABOVE_BARS: Final = "▐" + " " * 112
_GAP_ABOVE_BOTTOM: Final = "▐" + " " * 103
_BOTTOM: Final = "▐" + "▄" * 33 + "▌"
_SNACKPACK_HINT: Final = "▐・check your snackpack with /wisp snackpack"
_VAULT_HINT: Final = "▐・check the ViiBR Vault to buy treats and toys for Wisp!"


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


def render_status(life: Life, now: datetime, facts: CardFacts) -> str:
    """The status card for an egg, a hatching egg or a living Wisp.

    Raises:
        ValueError: The life is over, so it has no card.
    """
    if life.phase is Phase.EGG:
        warmth = 100 - _share(life.phase_seconds, EGG_WARMTH.total_seconds())
        hatching = _share(life.egg_food, EGG_FOOD_NEEDED)
        bars = [
            _bar_line("Warmth", "🟧", warmth),
            _bar_line("Hatching", "🟨", hatching),
        ]
        return _card([], bars, "the egg", "EGG", facts)
    if life.phase is Phase.HATCHING:
        emerging = _share(life.phase_seconds, HATCHING_TIME.total_seconds())
        bars = [_bar_line("Emerging", "🟨", emerging)]
        return _card([], bars, "the egg", "HATCHING", facts)
    if life.phase is Phase.ALIVE:
        heading = [f"▐▀━━・・𝐃𝐀𝐘 **{age_days(life, now)}**・♫ ♪. ♫‿♪" + " " * 54]
        if is_sick(life):
            hours = math.ceil(life.cold_left / _HOUR)
            heading.append(f"▐・he has a cold・{hours} h left")
        bars = [
            _bar_line("Full", "🟦", life.full / FULL_MAX * 100),
            _bar_line("Happy", "🟪", facts.happiness),
            _bar_line("Care", "🟥", life.care / CARE_MAX * 100),
        ]
        return _card(heading, bars, "him", life.stage.label.upper(), facts)
    raise ValueError(f"A finished life has no status card (phase {life.phase}).")


def _card(
    heading: list[str], bars: list[str], poke: str, stage: str, facts: CardFacts
) -> str:
    """Myra's frame around the heading, the bars and the facts."""
    people = "person" if facts.fed_today == 1 else "people"
    tracks = (
        f"{count(facts.viibr_tracks, 'ViiBR track')} and "
        f"{count(facts.suno_tracks, 'Suno track')}"
    )
    house = "his House" if facts.house_id is None else f"<#{facts.house_id}>"
    return "\n".join(
        [
            _TOP,
            _TITLE_RULE,
            *heading,
            _GAP_ABOVE_BARS,
            *bars,
            _GAP,
            f"▐▄━━❰・Fed by {facts.fed_today:02d} {people} today・♬‿♩. ♪",
            _RULE,
            f"▐▀━━❰・{tracks}・♪‿♫ ♪",
            _GAP,
            f"▐・Poke {poke} or tag <@{facts.wisp_id}> in {house} to say hi!!",
            _SNACKPACK_HINT,
            _VAULT_HINT,
            _GAP,
            f"▐▄━━❰・・**life stage**・{_bold(stage)}・♪‿♪ ♫.",
            _RULE,
            _GAP_ABOVE_BOTTOM,
            _BOTTOM,
        ]
    )


# ---
# Pieces
# ---


def bar(value: float, square: str) -> str:
    """A meter for a value from 0 to 100: one `square` per 10%, then the percent.

    The percent is rounded half up and the squares follow it, also rounded
    half up, so 45 shows five squares. Only filled squares are shown.
    """
    percent = _round_half_up(min(max(value, 0.0), 100.0))
    return square * _round_half_up(percent / _PERCENT_PER_SQUARE) + f"│{percent}%"


def _bold(text: str) -> str:
    """`text` with A to Z in Mathematical Bold capitals; other characters kept."""
    return "".join(
        chr(_MATH_BOLD_A + ord(letter) - ord("A")) if "A" <= letter <= "Z" else letter
        for letter in text
    )


def _bar_line(label: str, square: str, value: float) -> str:
    return f"▐・{label}{' ' * LABEL_PADDING[label]}{bar(value, square)}"


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def _share(part: float, whole: float) -> float:
    """`part` as a percentage of `whole`, kept between 0 and 100."""
    return min(max(part / whole * 100, 0.0), 100.0)
