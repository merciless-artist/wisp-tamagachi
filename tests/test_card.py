"""Tests for the status card text."""

from datetime import UTC, datetime, timedelta

import pytest

from wisp.card import bar, render_status
from wisp.life import Life, Phase, new_egg
from wisp.rules import (
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    HATCHING_TIME,
    OLD_FOGEY_AT_DAY,
    Stage,
)
from wisp.text import SEPARATOR

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "░░░░░░░░░░"),
        (4, "░░░░░░░░░░"),
        (5, "█░░░░░░░░░"),
        (72, "███████░░░"),
        (74.9, "███████░░░"),
        (75, "████████░░"),
        (100, "██████████"),
        (-5, "░░░░░░░░░░"),
        (140, "██████████"),
    ],
)
def test_bar_rounds(value: float, expected: str) -> None:
    assert bar(value) == expected


def alive_life(**fields: object) -> Life:
    life = new_egg(3, NOW - timedelta(days=12))
    life.phase = Phase.ALIVE
    life.stage = Stage.TEEN
    life.care = 72.0
    life.hatched_at = NOW - timedelta(days=9, hours=3)
    for name, value in fields.items():
        setattr(life, name, value)
    return life


def test_alive_card_matches_spec_exactly() -> None:
    expected = (
        "♪ WISP v3 ・ TEEN ・ day 9\n"
        "care       ███████░░░  72\n"
        "happiness  █████░░░░░  50\n"
        "fed today by 4 people\n"
        "・♪ ────────・──────── ♪・"
    )
    assert render_status(alive_life(), NOW, happiness=50, fed_today=4) == expected


def test_old_fogey_card_title_is_spaced_and_upper_case() -> None:
    life = alive_life(
        stage=Stage.OLD_FOGEY, hatched_at=NOW - timedelta(days=OLD_FOGEY_AT_DAY)
    )
    card = render_status(life, NOW, happiness=50, fed_today=2)
    assert "OLD FOGEY ・ day 45" in card.splitlines()[0]


def test_alive_card_uses_singular_for_one_person() -> None:
    card = render_status(alive_life(), NOW, happiness=0, fed_today=1)
    assert "fed today by 1 person\n" in card


def test_egg_card() -> None:
    egg = new_egg(4, NOW)
    egg.phase_seconds = EGG_WARMTH.total_seconds() / 4
    egg.egg_food = EGG_FOOD_NEEDED // 2
    expected = (
        "♪ WISP v4 ・ EGG\n"
        "warmth     ████████░░  75\n"
        "hatching   █████░░░░░  50\n" + SEPARATOR
    )
    assert render_status(egg, NOW, happiness=0, fed_today=0) == expected


def test_hatching_card() -> None:
    egg = new_egg(4, NOW)
    egg.phase = Phase.HATCHING
    egg.phase_seconds = HATCHING_TIME.total_seconds() / 5
    expected = "♪ WISP v4 ・ HATCHING\nemerging   ██░░░░░░░░  20\n" + SEPARATOR
    assert render_status(egg, NOW, happiness=0, fed_today=0) == expected


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING])
def test_unhatched_cards_end_with_separator(phase: Phase) -> None:
    life = new_egg(1, NOW)
    life.phase = phase
    assert render_status(life, NOW, happiness=0, fed_today=0).endswith(SEPARATOR)


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD])
def test_finished_lives_are_not_rendered(phase: Phase) -> None:
    life = new_egg(4, NOW)
    life.phase = phase
    with pytest.raises(ValueError, match="finished"):
        render_status(life, NOW, happiness=0, fed_today=0)
