"""Text of Wisp's status card."""

from datetime import datetime

from wisp.life import Life, Phase, age_days
from wisp.rules import CARE_MAX, EGG_FOOD_NEEDED, EGG_WARMTH, HATCHING_TIME
from wisp.text import SEPARATOR

_BAR_CELLS = 10
_LABEL_WIDTH = 11


def bar(value: float) -> str:
    """A ten-cell bar for a value from 0 to 100, rounded to the nearest cell."""
    filled = min(max(_round_half_up(value / _BAR_CELLS), 0), _BAR_CELLS)
    return "█" * filled + "░" * (_BAR_CELLS - filled)


def render_status(life: Life, now: datetime, *, happiness: int, fed_today: int) -> str:
    """The status card for an egg, a hatching egg or a living Wisp."""
    title = f"♪ WISP v{life.version} ・ "
    if life.phase is Phase.EGG:
        warmth = 100 - _share(life.phase_seconds, EGG_WARMTH.total_seconds())
        return "\n".join(
            [
                title + "EGG",
                _row("warmth", warmth),
                _row("hatching", _share(life.egg_food, EGG_FOOD_NEEDED)),
                SEPARATOR,
            ]
        )
    if life.phase is Phase.HATCHING:
        emerging = _share(life.phase_seconds, HATCHING_TIME.total_seconds())
        return "\n".join([title + "HATCHING", _row("emerging", emerging), SEPARATOR])
    if life.phase is Phase.ALIVE:
        people = "1 person" if fed_today == 1 else f"{fed_today} people"
        return "\n".join(
            [
                f"{title}{life.stage.upper()} ・ day {age_days(life, now)}",
                _row("care", life.care / CARE_MAX * 100),
                _row("happiness", happiness),
                f"fed today by {people}",
                SEPARATOR,
            ]
        )
    raise ValueError(f"A finished life has no status card (phase {life.phase}).")


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def _share(part: float, whole: float) -> float:
    """`part` as a percentage of `whole`, kept between 0 and 100."""
    return min(max(part / whole * 100, 0.0), 100.0)


def _row(label: str, value: float) -> str:
    return f"{label:<{_LABEL_WIDTH}}{bar(value)}  {_round_half_up(value)}"
