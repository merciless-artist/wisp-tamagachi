"""Tests for bond tiers, daily caps, meeting and happiness."""

from datetime import UTC, datetime

import pytest

from wisp.bond import (
    casual_bond_grant,
    daily_meal_cap,
    happiness,
    meal_grant,
    should_meet,
    tier_for,
)
from wisp.life import Phase, new_egg
from wisp.rules import (
    DAILY_CASUAL_BOND_CAP,
    DAILY_MEAL_CAP,
    HAPPY_FULL_AT_PEOPLE,
    MEET_AFTER_DAYS,
    SICK_EXTRA_MEAL_CAP,
    SICK_FOR,
    Stage,
)


@pytest.mark.parametrize(
    ("bond", "tier"),
    [
        (0, "New face"),
        (49, "New face"),
        (50, "Familiar"),
        (149, "Familiar"),
        (150, "Friend"),
        (399, "Friend"),
        (400, "Bandmate"),
        (10_000, "Bandmate"),
    ],
)
def test_tiers_at_boundaries(bond: int, tier: str) -> None:
    assert tier_for(bond) == tier


def test_casual_bond_stops_at_seven() -> None:
    assert DAILY_CASUAL_BOND_CAP == 7
    assert casual_bond_grant(0, 3) == 3
    assert casual_bond_grant(5, 3) == 2
    assert casual_bond_grant(DAILY_CASUAL_BOND_CAP, 3) == 0
    assert casual_bond_grant(DAILY_CASUAL_BOND_CAP + 4, 3) == 0


def test_meal_grant_stops_at_fifteen() -> None:
    assert DAILY_MEAL_CAP == 15
    assert meal_grant(0, 5, DAILY_MEAL_CAP) == 5
    assert meal_grant(13, 5, DAILY_MEAL_CAP) == 2
    assert meal_grant(DAILY_MEAL_CAP, 5, DAILY_MEAL_CAP) == 0
    assert meal_grant(DAILY_MEAL_CAP + 3, 1, DAILY_MEAL_CAP) == 0


def test_the_meal_cap_doubles_while_sick() -> None:
    life = new_egg(1, datetime(2026, 10, 26, tzinfo=UTC))
    assert daily_meal_cap(None) == daily_meal_cap(life) == DAILY_MEAL_CAP
    life.phase = Phase.ALIVE
    life.stage = Stage.CHILD
    assert daily_meal_cap(life) == DAILY_MEAL_CAP
    life.cold_left = SICK_FOR.total_seconds()

    cap = daily_meal_cap(life)

    assert SICK_EXTRA_MEAL_CAP == 15
    assert cap == DAILY_MEAL_CAP + SICK_EXTRA_MEAL_CAP == 30
    assert meal_grant(DAILY_MEAL_CAP, 5, cap) == 5
    assert meal_grant(28, 5, cap) == 2
    assert meal_grant(cap, 5, cap) == 0


def test_meets_on_third_distinct_day_only_once() -> None:
    assert MEET_AFTER_DAYS == 3
    assert not should_meet(1, met=False)
    assert not should_meet(2, met=False)
    assert should_meet(3, met=False)
    assert should_meet(4, met=False)
    assert not should_meet(3, met=True)


def test_happiness_full_at_five_people() -> None:
    assert HAPPY_FULL_AT_PEOPLE == 5
    assert happiness(0) == 0
    assert happiness(1) == 20
    assert happiness(2) == 40
    assert happiness(5) == 100
    assert happiness(12) == 100
