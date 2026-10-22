"""Tests for the life engine: eggs, care, stages and death."""

from datetime import UTC, datetime, timedelta

import pytest

from wisp.life import (
    Event,
    EventKind,
    Life,
    Mood,
    Phase,
    add_growth,
    age_days,
    feed,
    is_over,
    mood,
    new_egg,
    tick,
)
from wisp.rules import (
    CARE_DRAIN_PER_DAY,
    CARE_MAX,
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    HATCHED_CARE,
    HATCHING_TIME,
    MAX_CREDITED_GAP,
    ROCKSTAR_HAPPINESS,
    ROCKSTAR_HAPPY_FOR,
    STAGE_RULES,
    TICK_EVERY,
    Stage,
)

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
FEEDER = 4242


def alive(
    care: float = HATCHED_CARE,
    at: datetime = T0,
    stage: Stage = Stage.BABY,
    **fields: object,
) -> Life:
    """Build a living Wisp that hatched at `at`."""
    life = new_egg(1, at)
    life.phase = Phase.ALIVE
    life.stage = stage
    life.peak_stage = stage
    life.care = care
    life.hatched_at = at
    life.stage_started_at = at
    for name, value in fields.items():
        setattr(life, name, value)
    return life


def run(
    life: Life,
    duration: timedelta,
    *,
    step: timedelta = TICK_EVERY,
    frozen: bool = False,
    happiness: int = 0,
    caretakers: int = 0,
    fed: bool = False,
) -> list[Event]:
    """Tick `life` every `step` for `duration`, optionally topping care up."""
    events: list[Event] = []
    end = life.last_tick_at + duration
    while life.last_tick_at < end:
        if fed:
            life.care = CARE_MAX
        events += tick(
            life,
            life.last_tick_at + step,
            frozen=frozen,
            happiness=happiness,
            caretakers=caretakers,
        )
    return events


def kinds(events: list[Event]) -> list[EventKind]:
    return [event.kind for event in events]


# ---
# Eggs
# ---


def test_new_egg_starts_cold_free() -> None:
    egg = new_egg(3, T0)
    assert egg.id is None
    assert egg.version == 3
    assert egg.phase is Phase.EGG
    assert egg.stage is Stage.EGG
    assert egg.peak_stage is Stage.EGG
    assert egg.egg_food == 0
    assert egg.laid_at == egg.last_tick_at == T0
    assert egg.phase_seconds == 0
    assert egg.warned is None
    assert egg.hatched_by is None


def test_feeding_egg_to_thirty_starts_hatching_and_credits_feeder() -> None:
    egg = new_egg(1, T0)
    assert feed(egg, EGG_FOOD_NEEDED - 1, 7, T0) == []
    events = feed(egg, 1, FEEDER, T0 + timedelta(hours=1))
    assert events == [Event(EventKind.HATCH_STARTED)]
    assert egg.phase is Phase.HATCHING
    assert egg.hatched_by == FEEDER
    assert egg.hatch_started_at == T0 + timedelta(hours=1)
    assert egg.phase_seconds == 0


def test_egg_goes_cold_after_48_credited_hours() -> None:
    egg = new_egg(1, T0)
    events = run(egg, EGG_WARMTH - TICK_EVERY)
    assert events == []
    events = run(egg, TICK_EVERY)
    assert events == [Event(EventKind.EGG_COLD)]
    assert egg.phase is Phase.COLD
    assert egg.ended_at == egg.last_tick_at
    assert is_over(egg)


def test_freeze_pauses_egg_warmth() -> None:
    egg = new_egg(1, T0)
    run(egg, timedelta(days=3), step=MAX_CREDITED_GAP, frozen=True)
    assert egg.phase_seconds == 0
    assert egg.last_tick_at == T0 + timedelta(days=3)
    run(egg, EGG_WARMTH - TICK_EVERY)
    assert run(egg, TICK_EVERY) == [Event(EventKind.EGG_COLD)]


def test_hatching_finishes_after_five_hours_at_fifty_care() -> None:
    egg = new_egg(1, T0)
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    assert run(egg, HATCHING_TIME - TICK_EVERY) == []
    events = run(egg, TICK_EVERY)
    assert events == [Event(EventKind.HATCHED)]
    assert egg.phase is Phase.ALIVE
    assert egg.stage is Stage.BABY
    assert egg.peak_stage is Stage.BABY
    assert egg.care == HATCHED_CARE
    assert egg.hatched_at == egg.stage_started_at == egg.last_tick_at
    assert egg.phase_seconds == 0


def test_hatching_does_not_drain_the_newborn_in_the_same_tick() -> None:
    egg = new_egg(1, T0)
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    egg.phase_seconds = HATCHING_TIME.total_seconds() - 1
    tick(egg, T0 + MAX_CREDITED_GAP, frozen=False, happiness=0, caretakers=0)
    assert egg.care == HATCHED_CARE


def test_feeding_while_hatching_is_ignored() -> None:
    egg = new_egg(1, T0)
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    snapshot = (egg.egg_food, egg.hatched_by, egg.phase_seconds)
    assert feed(egg, 10, 99, T0 + timedelta(hours=1)) == []
    assert (egg.egg_food, egg.hatched_by, egg.phase_seconds) == snapshot
    assert egg.phase is Phase.HATCHING


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD])
def test_feeding_over_life_is_ignored(phase: Phase) -> None:
    life = alive(care=40.0)
    life.phase = phase
    assert feed(life, 10, FEEDER, T0) == []
    assert life.care == 40.0
    assert life.egg_food == 0


# ---
# Care
# ---


def test_care_drains_fifteen_per_day() -> None:
    life = alive(care=80.0)
    run(life, timedelta(days=1), step=MAX_CREDITED_GAP)
    assert life.care == pytest.approx(80.0 - CARE_DRAIN_PER_DAY)


def test_long_gap_only_drains_fifteen_minutes() -> None:
    life = alive(care=50.0, at=T0)
    tick(life, T0 + timedelta(hours=6), frozen=False, happiness=0, caretakers=0)
    assert life.care == pytest.approx(50.0 - 15.0 * (15 / (24 * 60)))
    assert life.last_tick_at == T0 + timedelta(hours=6)


def test_frozen_tick_drains_nothing() -> None:
    life = alive(care=50.0)
    now = T0 + timedelta(minutes=10)
    assert tick(life, now, frozen=True, happiness=0, caretakers=0) == []
    assert life.care == 50.0
    assert life.phase_seconds == 0
    assert life.last_tick_at == now


def test_clock_going_backwards_credits_nothing() -> None:
    life = alive(care=50.0)
    tick(life, T0 - timedelta(minutes=5), frozen=False, happiness=0, caretakers=0)
    assert life.care == 50.0


def test_hungry_and_fading_warn_once_each() -> None:
    life = alive(care=30.02)
    events = run(life, timedelta(days=1, hours=12))
    assert kinds(events) == [EventKind.HUNGRY, EventKind.FADING]
    assert life.warned is EventKind.FADING
    assert life.phase is Phase.ALIVE


def test_one_tick_can_cross_both_thresholds() -> None:
    life = alive(care=10.02)
    events = run(life, TICK_EVERY)
    assert kinds(events) == [EventKind.HUNGRY, EventKind.FADING]


def test_feeding_above_threshold_rearms_warning() -> None:
    life = alive(care=5.0, warned=EventKind.FADING)
    feed(life, 3, FEEDER, T0)
    assert life.warned is EventKind.FADING
    feed(life, 26, FEEDER, T0)
    assert life.care == 34.0
    assert life.warned is None
    events = run(life, timedelta(hours=8))
    assert kinds(events) == [EventKind.HUNGRY]


def test_fading_rearms_after_feeding_into_the_hungry_band() -> None:
    life = alive(care=5.0, warned=EventKind.FADING)
    feed(life, 10, FEEDER, T0)
    assert life.care == 15.0
    assert life.warned is EventKind.HUNGRY
    events = run(life, timedelta(hours=10))
    assert kinds(events) == [EventKind.FADING]


def test_care_never_exceeds_max() -> None:
    life = alive(care=95.0)
    assert feed(life, 50, FEEDER, T0) == []
    assert life.care == CARE_MAX


def test_death_at_zero_care() -> None:
    life = alive(care=0.03)
    now = T0 + TICK_EVERY
    events = tick(life, now, frozen=False, happiness=0, caretakers=0)
    assert events == [Event(EventKind.DIED)]
    assert life.phase is Phase.DEAD
    assert life.care == 0
    assert life.ended_at == now
    assert is_over(life)


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD])
def test_tick_on_over_life_is_a_no_op(phase: Phase) -> None:
    life = alive(care=0.0)
    life.phase = phase
    before = (life.care, life.last_tick_at, life.phase_seconds, life.ended_at)
    later = T0 + timedelta(hours=1)
    assert tick(life, later, frozen=False, happiness=100, caretakers=9) == []
    assert (life.care, life.last_tick_at, life.phase_seconds, life.ended_at) == before


@pytest.mark.parametrize(
    "care,expected",
    [(29.9, Mood.HANGRY), (30.0, Mood.HAPPY), (80.0, Mood.HAPPY)],
)
def test_mood_is_hangry_below_thirty(care: float, expected: Mood) -> None:
    assert mood(alive(care=care)) is expected


# ---
# Growth and stages
# ---


def test_add_growth_only_counts_while_alive() -> None:
    egg = new_egg(1, T0)
    add_growth(egg, 5)
    assert egg.growth == 0
    life = alive()
    add_growth(life, 5)
    add_growth(life, 2)
    assert life.growth == 7
    life.phase = Phase.DEAD
    add_growth(life, 5)
    assert life.growth == 7


def test_age_counts_whole_days_from_hatching() -> None:
    life = alive(at=T0 - timedelta(days=3, hours=23))
    assert age_days(life, T0) == 3
    assert age_days(new_egg(1, T0), T0) == 0


@pytest.mark.parametrize(
    "age,growth,caretakers,advances",
    [
        (3, 20, 3, True),
        (2, 20, 3, False),
        (3, 19, 3, False),
        (3, 20, 2, False),
        (9, 99, 9, True),
    ],
)
def test_stage_up_needs_age_growth_and_caretakers(
    age: int, growth: int, caretakers: int, advances: bool
) -> None:
    life = alive(care=CARE_MAX, at=T0 - timedelta(days=age), growth=growth)
    events = tick(life, T0, frozen=False, happiness=0, caretakers=caretakers)
    if advances:
        assert events == [Event(EventKind.STAGE_UP, Stage.CHILD)]
        assert life.stage is Stage.CHILD
        assert life.peak_stage is Stage.CHILD
        assert life.stage_started_at == T0
    else:
        assert events == []
        assert life.stage is Stage.BABY
        assert life.stage_started_at == T0 - timedelta(days=age)


def test_stage_up_moves_one_stage_per_tick() -> None:
    life = alive(care=CARE_MAX, at=T0 - timedelta(days=40), growth=500)
    first = tick(life, T0, frozen=False, happiness=0, caretakers=20)
    second = tick(life, T0 + TICK_EVERY, frozen=False, happiness=0, caretakers=20)
    assert first == [Event(EventKind.STAGE_UP, Stage.CHILD)]
    assert second == [Event(EventKind.STAGE_UP, Stage.TEEN)]


def test_late_bloomer_grows_when_caretakers_arrive() -> None:
    min_age, growth, people = STAGE_RULES[Stage.CHILD]
    life = alive(
        care=CARE_MAX,
        at=T0 - timedelta(days=min_age + 10),
        growth=growth + 30,
        last_tick_at=T0,
    )
    assert run(life, timedelta(hours=1), caretakers=people - 1) == []
    assert life.stage is Stage.BABY
    events = run(life, TICK_EVERY, caretakers=people)
    assert events == [Event(EventKind.STAGE_UP, Stage.CHILD)]
    assert life.stage_started_at == life.last_tick_at


def test_rockstar_after_seven_happy_days() -> None:
    life = alive(care=CARE_MAX, stage=Stage.ADULT)
    almost = ROCKSTAR_HAPPY_FOR - timedelta(hours=1)
    events = run(life, almost, happiness=ROCKSTAR_HAPPINESS, fed=True)
    assert events == []
    events = run(life, timedelta(hours=2), happiness=ROCKSTAR_HAPPINESS, fed=True)
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]
    assert life.stage is Stage.ROCKSTAR
    assert life.peak_stage is Stage.ROCKSTAR


def test_happiness_dip_resets_rockstar_clock() -> None:
    life = alive(care=CARE_MAX, stage=Stage.ADULT)
    run(life, timedelta(days=6), happiness=ROCKSTAR_HAPPINESS, fed=True)
    assert life.high_happiness_since is not None
    run(life, TICK_EVERY, happiness=ROCKSTAR_HAPPINESS - 1, fed=True)
    assert life.high_happiness_since is None
    events = run(life, timedelta(days=6), happiness=ROCKSTAR_HAPPINESS, fed=True)
    assert events == []
    assert life.stage is Stage.ADULT
    events = run(life, timedelta(days=1, hours=1), happiness=100, fed=True)
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]


def test_only_adults_build_a_rockstar_streak() -> None:
    life = alive(care=CARE_MAX, stage=Stage.TEEN)
    run(life, timedelta(hours=1), happiness=100, fed=True)
    assert life.high_happiness_since is None


def test_frozen_span_does_not_count_toward_rockstar() -> None:
    life = alive(care=CARE_MAX, stage=Stage.ADULT)
    run(life, timedelta(days=1), happiness=ROCKSTAR_HAPPINESS, fed=True)
    run(life, ROCKSTAR_HAPPY_FOR, step=MAX_CREDITED_GAP, frozen=True)
    events = run(life, TICK_EVERY, happiness=ROCKSTAR_HAPPINESS, fed=True)
    assert events == []
    assert life.stage is Stage.ADULT
    remaining = ROCKSTAR_HAPPY_FOR - timedelta(days=1)
    events = run(life, remaining, happiness=ROCKSTAR_HAPPINESS, fed=True)
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]


def test_offline_gap_counts_only_fifteen_minutes_toward_rockstar() -> None:
    life = alive(care=CARE_MAX, stage=Stage.ADULT)
    tick(life, T0 + TICK_EVERY, frozen=False, happiness=100, caretakers=0)
    since = life.high_happiness_since
    assert since is not None
    back = T0 + TICK_EVERY + timedelta(days=ROCKSTAR_HAPPY_FOR.days + 1)
    life.care = CARE_MAX
    events = tick(life, back, frozen=False, happiness=100, caretakers=0)
    assert events == []
    assert life.stage is Stage.ADULT
    assert life.high_happiness_since == back - MAX_CREDITED_GAP
