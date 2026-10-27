"""Bond tiers, daily caps, meeting and happiness. Pure rules, no storage."""

from enum import StrEnum

from wisp.life import Life, is_sick
from wisp.rules import (
    BOND_TIERS,
    DAILY_CASUAL_BOND_CAP,
    DAILY_MEAL_CAP,
    HAPPY_FULL_AT_PEOPLE,
    MEET_AFTER_DAYS,
    SICK_EXTRA_MEAL_CAP,
)


class PickleStance(StrEnum):
    """Where a member stands on pickles. Wisp always takes the other side."""

    LOVE = "love"
    HATE = "hate"


def tier_for(bond: int) -> str:
    """Name of the highest tier that `bond` has reached."""
    name = BOND_TIERS[0][0]
    for tier_name, needed in BOND_TIERS:
        if bond >= needed:
            name = tier_name
    return name


def casual_bond_grant(earned_today: int, amount: int) -> int:
    """Bond from play and snacks that still fits under today's casual cap."""
    return max(min(amount, DAILY_CASUAL_BOND_CAP - earned_today), 0)


def daily_meal_cap(life: Life | None) -> int:
    """How many meal points each member may feed today; more while he is sick."""
    if life is not None and is_sick(life):
        return DAILY_MEAL_CAP + SICK_EXTRA_MEAL_CAP
    return DAILY_MEAL_CAP


def meal_grant(fed_today: int, points: int, cap: int) -> int:
    """Meal points that still fit under today's feeding cap of `cap`."""
    return max(min(points, cap - fed_today), 0)


def should_meet(distinct_days: int, met: bool) -> bool:
    """Whether Wisp should now learn this member's name, once."""
    return not met and distinct_days >= MEET_AFTER_DAYS


def happiness(distinct_people_24h: int) -> int:
    """Happiness from 0 to 100, full once enough people cared in a day."""
    share = distinct_people_24h / HAPPY_FULL_AT_PEOPLE
    return round(min(share, 1.0) * 100)
