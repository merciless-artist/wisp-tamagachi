"""Tests for the life engine: eggs, fullness, stages and death."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from wisp.life import (
    Event,
    EventKind,
    Life,
    Mood,
    Phase,
    add_care,
    add_growth,
    age_days,
    caretakers_needed,
    egg_after,
    feed,
    is_over,
    is_sick,
    jump_to,
    mood,
    new_egg,
    ready_to_pass_on,
    schedule_cold,
    starve,
    tick,
)
from wisp.rules import (
    CARE_DRAIN_PER_DAY,
    CARE_MAX,
    CARE_START,
    COAL_EGG_FOOD,
    COLD_EARLIEST,
    COLD_LATEST,
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    FAREWELL_AT_DAY,
    FULL_DRAIN_PER_DAY,
    FULL_MAX,
    HATCHED_FULL,
    HATCHING_TIME,
    LONELY_BELOW,
    MAX_CREDITED_GAP,
    OLD_FOGEY_AT_DAY,
    OLD_FOGEY_FULL_DRAIN_PER_DAY,
    ROCKSTAR_HAPPINESS,
    ROCKSTAR_HAPPY_FOR,
    SICK_DRAIN_MULTIPLIER,
    SICK_FOR,
    SICK_FULL_FLOOR,
    STAGE_MIN_TIME,
    STAGE_RULES,
    TICK_EVERY,
    Stage,
)

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
FEEDER = 4242


def alive(
    full: float = HATCHED_FULL,
    at: datetime = T0,
    stage: Stage = Stage.BABY,
    **fields: object,
) -> Life:
    """Build a living Wisp that hatched at `at`."""
    life = new_egg(1, at)
    life.phase = Phase.ALIVE
    life.stage = stage
    life.peak_stage = stage
    life.full = full
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
    people: int = 0,
    fed: bool = False,
    cared: bool = False,
) -> list[Event]:
    """Tick `life` every `step` for `duration`, optionally topping meters up.

    `fed` keeps the full meter topped up and `cared` the care meter.
    """
    events: list[Event] = []
    end = life.last_tick_at + duration
    while life.last_tick_at < end:
        if fed:
            life.full = FULL_MAX
        if cared:
            life.care = CARE_MAX
        events += tick(
            life,
            life.last_tick_at + step,
            frozen=frozen,
            happiness=happiness,
            caretakers=caretakers,
            people=people,
        )
    return events


def tended(life: Life, duration: timedelta) -> list[Event]:
    """Tick a fed, cared-for Wisp who is happy enough to become a Rockstar."""
    return run(life, duration, happiness=ROCKSTAR_HAPPINESS, fed=True, cared=True)


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


def test_hatching_finishes_after_five_hours_at_fifty_full() -> None:
    egg = new_egg(1, T0)
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    assert run(egg, HATCHING_TIME - TICK_EVERY) == []
    events = run(egg, TICK_EVERY)
    assert events == [Event(EventKind.HATCHED)]
    assert egg.phase is Phase.ALIVE
    assert egg.stage is Stage.BABY
    assert egg.peak_stage is Stage.BABY
    assert egg.full == HATCHED_FULL
    assert egg.hatched_at == egg.stage_started_at == egg.last_tick_at
    assert egg.phase_seconds == 0


def test_hatching_does_not_drain_the_newborn_in_the_same_tick() -> None:
    egg = new_egg(1, T0)
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    egg.phase_seconds = HATCHING_TIME.total_seconds() - 1
    tick(egg, T0 + MAX_CREDITED_GAP, frozen=False, happiness=0, caretakers=0, people=0)
    assert egg.full == HATCHED_FULL


def test_feeding_while_hatching_is_ignored() -> None:
    egg = new_egg(1, T0)
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    snapshot = (egg.egg_food, egg.hatched_by, egg.phase_seconds)
    assert feed(egg, 10, 99, T0 + timedelta(hours=1)) == []
    assert (egg.egg_food, egg.hatched_by, egg.phase_seconds) == snapshot
    assert egg.phase is Phase.HATCHING


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD])
def test_feeding_over_life_is_ignored(phase: Phase) -> None:
    life = alive(full=40.0)
    life.phase = phase
    assert feed(life, 10, FEEDER, T0) == []
    assert life.full == 40.0
    assert life.egg_food == 0


# ---
# Full
# ---


def test_full_drains_fifteen_per_day() -> None:
    life = alive(full=80.0)
    run(life, timedelta(days=1), step=MAX_CREDITED_GAP)
    assert life.full == pytest.approx(80.0 - FULL_DRAIN_PER_DAY)


def test_long_gap_only_drains_fifteen_minutes() -> None:
    life = alive(full=50.0, at=T0)
    tick(
        life, T0 + timedelta(hours=6), frozen=False, happiness=0, caretakers=0, people=0
    )
    assert life.full == pytest.approx(50.0 - 15.0 * (15 / (24 * 60)))
    assert life.last_tick_at == T0 + timedelta(hours=6)


def test_frozen_tick_drains_nothing() -> None:
    life = alive(full=50.0)
    now = T0 + timedelta(minutes=10)
    assert tick(life, now, frozen=True, happiness=0, caretakers=0, people=0) == []
    assert life.full == 50.0
    assert life.phase_seconds == 0
    assert life.last_tick_at == now


def test_clock_going_backwards_credits_nothing() -> None:
    life = alive(full=50.0)
    tick(
        life,
        T0 - timedelta(minutes=5),
        frozen=False,
        happiness=0,
        caretakers=0,
        people=0,
    )
    assert life.full == 50.0


def test_hungry_and_fading_warn_once_each() -> None:
    life = alive(full=30.02)
    events = run(life, timedelta(days=1, hours=12))
    assert kinds(events) == [EventKind.HUNGRY, EventKind.FADING]
    assert life.warned is EventKind.FADING
    assert life.phase is Phase.ALIVE


def test_one_tick_can_cross_both_thresholds() -> None:
    life = alive(full=10.02)
    events = run(life, TICK_EVERY)
    assert kinds(events) == [EventKind.HUNGRY, EventKind.FADING]


def test_feeding_above_threshold_rearms_warning() -> None:
    life = alive(full=5.0, warned=EventKind.FADING)
    feed(life, 3, FEEDER, T0)
    assert life.warned is EventKind.FADING
    feed(life, 26, FEEDER, T0)
    assert life.full == 34.0
    assert life.warned is None
    events = run(life, timedelta(hours=8))
    assert kinds(events) == [EventKind.HUNGRY]


def test_fading_rearms_after_feeding_into_the_hungry_band() -> None:
    life = alive(full=5.0, warned=EventKind.FADING)
    feed(life, 10, FEEDER, T0)
    assert life.full == 15.0
    assert life.warned is EventKind.HUNGRY
    events = run(life, timedelta(hours=10))
    assert kinds(events) == [EventKind.FADING]


def test_full_never_exceeds_max() -> None:
    life = alive(full=95.0)
    assert feed(life, 50, FEEDER, T0) == []
    assert life.full == FULL_MAX


def test_death_at_zero_full() -> None:
    life = alive(full=0.03)
    now = T0 + TICK_EVERY
    events = tick(life, now, frozen=False, happiness=0, caretakers=0, people=0)
    assert events == [Event(EventKind.DIED)]
    assert life.phase is Phase.DEAD
    assert life.full == 0
    assert life.ended_at == now
    assert is_over(life)


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD])
def test_tick_on_over_life_is_a_no_op(phase: Phase) -> None:
    life = alive(full=0.0)
    life.phase = phase
    before = (life.full, life.last_tick_at, life.phase_seconds, life.ended_at)
    later = T0 + timedelta(hours=1)
    assert tick(life, later, frozen=False, happiness=100, caretakers=9, people=0) == []
    assert (life.full, life.last_tick_at, life.phase_seconds, life.ended_at) == before


@pytest.mark.parametrize(
    "full,expected",
    [(29.9, Mood.HANGRY), (30.0, Mood.HAPPY), (80.0, Mood.HAPPY)],
)
def test_mood_is_hangry_below_thirty(full: float, expected: Mood) -> None:
    assert mood(alive(full=full)) is expected


# ---
# Care
# ---


def test_care_starts_at_half_when_he_hatches() -> None:
    egg = new_egg(1, T0)
    egg.care = 0.0
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    run(egg, HATCHING_TIME)
    assert egg.phase is Phase.ALIVE
    assert egg.care == CARE_START
    assert not egg.lonely_warned


def test_care_drains_ten_a_day() -> None:
    life = alive(full=FULL_MAX, care=80.0)
    run(life, timedelta(days=1), step=MAX_CREDITED_GAP, fed=True)
    assert life.care == pytest.approx(80.0 - CARE_DRAIN_PER_DAY)


def test_care_never_drains_below_zero() -> None:
    life = alive(full=FULL_MAX, care=0.01)
    run(life, timedelta(hours=1), fed=True)
    assert life.care == 0.0
    assert life.phase is Phase.ALIVE


def test_care_does_not_drain_while_frozen_or_unhatched() -> None:
    life = alive(full=FULL_MAX, care=60.0)
    run(life, timedelta(days=1), step=MAX_CREDITED_GAP, frozen=True)
    assert life.care == 60.0
    egg = new_egg(1, T0)
    run(egg, timedelta(hours=1))
    assert egg.care == CARE_START


def test_add_care_caps_at_max_and_only_while_alive() -> None:
    life = alive(care=CARE_MAX - 3)
    add_care(life, 10)
    assert life.care == CARE_MAX
    for phase in (Phase.EGG, Phase.HATCHING, Phase.DEAD, Phase.COLD, Phase.PASSED):
        other = alive(care=40.0)
        other.phase = phase
        add_care(other, 10)
        assert other.care == 40.0


def test_mood_hangry_beats_lonely() -> None:
    assert mood(alive(full=10.0, care=10.0)) is Mood.HANGRY


@pytest.mark.parametrize(
    "care,expected",
    [(LONELY_BELOW - 0.1, Mood.LONELY), (LONELY_BELOW, Mood.HAPPY), (90.0, Mood.HAPPY)],
)
def test_mood_lonely_below_the_line(care: float, expected: Mood) -> None:
    assert mood(alive(full=80.0, care=care)) is expected


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
def test_only_a_living_wisp_is_lonely(phase: Phase) -> None:
    life = alive(full=80.0, care=5.0)
    life.phase = phase
    assert mood(life) is Mood.HAPPY


def test_lonely_warns_once_per_drop() -> None:
    life = alive(full=FULL_MAX, stage=Stage.CHILD, care=LONELY_BELOW + 0.02)
    events = run(life, timedelta(hours=1), fed=True)
    assert events == [Event(EventKind.LONELY, Stage.CHILD)]
    assert life.lonely_warned
    assert run(life, timedelta(days=1), fed=True) == []

    add_care(life, LONELY_BELOW - life.care - 1)
    assert life.lonely_warned
    add_care(life, 1)
    assert life.care == pytest.approx(LONELY_BELOW)
    assert not life.lonely_warned
    events = run(life, timedelta(hours=1), fed=True)
    assert events == [Event(EventKind.LONELY, Stage.CHILD)]


def test_loneliness_never_hurts_him() -> None:
    life = alive(full=FULL_MAX, care=0.0, at=T0 - STAGE_MIN_TIME, growth=25)
    events = tick(life, T0, frozen=False, happiness=0, caretakers=3, people=0)
    assert kinds(events) == [EventKind.LONELY, EventKind.STAGE_UP]
    assert life.phase is Phase.ALIVE
    assert life.full == pytest.approx(FULL_MAX, abs=0.2)


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


_CHILD = STAGE_RULES[Stage.CHILD]
_THREE_DAYS = STAGE_MIN_TIME


@pytest.mark.parametrize(
    "in_stage,growth,caretakers,people,advances",
    [
        (_THREE_DAYS, _CHILD.growth, 1, 4, True),
        (_THREE_DAYS - timedelta(hours=1), _CHILD.growth, 1, 4, False),
        (_THREE_DAYS, _CHILD.growth - 1, 1, 4, False),
        (_THREE_DAYS, _CHILD.growth, 0, 4, False),
        (_THREE_DAYS, _CHILD.growth, 1, 8, False),
        (_THREE_DAYS, _CHILD.growth, 2, 8, True),
        (timedelta(days=_CHILD.by_day), 0, 0, 20, True),
    ],
)
def test_stage_up_needs_three_days_growth_and_a_share_of_his_people(
    in_stage: timedelta, growth: int, caretakers: int, people: int, advances: bool
) -> None:
    life = alive(full=FULL_MAX, at=T0 - in_stage, growth=growth)
    events = tick(
        life, T0, frozen=False, happiness=0, caretakers=caretakers, people=people
    )
    if advances:
        assert events == [Event(EventKind.STAGE_UP, Stage.CHILD)]
        assert life.stage is Stage.CHILD
        assert life.peak_stage is Stage.CHILD
        assert life.stage_started_at == T0
    else:
        assert events == []
        assert life.stage is Stage.BABY
        assert life.stage_started_at == T0 - in_stage


@pytest.mark.parametrize(
    "stage,people,needed",
    [
        (Stage.CHILD, 4, 1),
        (Stage.TEEN, 4, 2),
        (Stage.ADULT, 4, 3),
        (Stage.TEEN, 5, 3),
        (Stage.ADULT, 20, 15),
        (Stage.ADULT, 0, 1),
        (Stage.CHILD, 1, 1),
    ],
)
def test_caretakers_needed_is_a_share_of_his_people_rounded_up(
    stage: Stage, people: int, needed: int
) -> None:
    assert caretakers_needed(stage, people) == needed


@pytest.mark.parametrize(
    "stage,grows_into",
    [(Stage.BABY, Stage.CHILD), (Stage.CHILD, Stage.TEEN), (Stage.TEEN, Stage.ADULT)],
)
def test_he_grows_up_on_the_deadline_day_no_matter_what(
    stage: Stage, grows_into: Stage
) -> None:
    by_day = timedelta(days=STAGE_RULES[grows_into].by_day)
    life = alive(full=FULL_MAX, at=T0 - by_day, stage=stage, stage_started_at=T0)
    almost = alive(
        full=FULL_MAX,
        at=T0 - by_day + timedelta(hours=1),
        stage=stage,
        stage_started_at=T0,
    )
    assert tick(life, T0, frozen=False, happiness=0, caretakers=0, people=9) == [
        Event(EventKind.STAGE_UP, grows_into)
    ]
    assert tick(almost, T0, frozen=False, happiness=0, caretakers=0, people=9) == []


def test_stage_up_moves_one_stage_per_tick() -> None:
    life = alive(full=FULL_MAX, at=T0 - timedelta(days=40), growth=500)
    first = tick(life, T0, frozen=False, happiness=0, caretakers=20, people=0)
    second = tick(
        life, T0 + TICK_EVERY, frozen=False, happiness=0, caretakers=20, people=0
    )
    assert first == [Event(EventKind.STAGE_UP, Stage.CHILD)]
    assert second == [Event(EventKind.STAGE_UP, Stage.TEEN)]


def test_late_bloomer_grows_when_caretakers_arrive() -> None:
    life = alive(
        full=FULL_MAX,
        at=T0 - STAGE_MIN_TIME - timedelta(days=1),
        growth=_CHILD.growth + 30,
        last_tick_at=T0,
    )
    assert run(life, timedelta(hours=1), caretakers=1, people=8) == []
    assert life.stage is Stage.BABY
    events = run(life, TICK_EVERY, caretakers=2, people=8)
    assert events == [Event(EventKind.STAGE_UP, Stage.CHILD)]
    assert life.stage_started_at == life.last_tick_at


def test_rockstar_after_seven_happy_days() -> None:
    life = alive(full=FULL_MAX, stage=Stage.ADULT)
    almost = ROCKSTAR_HAPPY_FOR - timedelta(hours=1)
    events = tended(life, almost)
    assert events == []
    events = tended(life, timedelta(hours=2))
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]
    assert life.stage is Stage.ROCKSTAR
    assert life.peak_stage is Stage.ROCKSTAR


def test_happiness_dip_resets_rockstar_clock() -> None:
    almost = ROCKSTAR_HAPPY_FOR - timedelta(days=1)
    life = alive(full=FULL_MAX, stage=Stage.ADULT)
    tended(life, almost)
    assert life.high_happiness_since is not None
    run(life, TICK_EVERY, happiness=ROCKSTAR_HAPPINESS - 1, fed=True, cared=True)
    assert life.high_happiness_since is None
    events = tended(life, almost)
    assert events == []
    assert life.stage is Stage.ADULT
    events = run(life, timedelta(days=1, hours=1), happiness=100, fed=True, cared=True)
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]


def test_only_adults_build_a_rockstar_streak() -> None:
    life = alive(full=FULL_MAX, stage=Stage.TEEN)
    run(life, timedelta(hours=1), happiness=100, fed=True)
    assert life.high_happiness_since is None


def test_frozen_span_does_not_count_toward_rockstar() -> None:
    life = alive(full=FULL_MAX, stage=Stage.ADULT)
    tended(life, timedelta(days=1))
    run(life, ROCKSTAR_HAPPY_FOR, step=MAX_CREDITED_GAP, frozen=True)
    events = tended(life, TICK_EVERY)
    assert events == []
    assert life.stage is Stage.ADULT
    remaining = ROCKSTAR_HAPPY_FOR - timedelta(days=1)
    events = tended(life, remaining)
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]


def test_offline_gap_counts_only_fifteen_minutes_toward_rockstar() -> None:
    life = alive(full=FULL_MAX, stage=Stage.ADULT)
    tick(life, T0 + TICK_EVERY, frozen=False, happiness=100, caretakers=0, people=0)
    since = life.high_happiness_since
    assert since is not None
    back = T0 + TICK_EVERY + timedelta(days=ROCKSTAR_HAPPY_FOR.days + 1)
    life.full = FULL_MAX
    events = tick(life, back, frozen=False, happiness=100, caretakers=0, people=0)
    assert events == []
    assert life.stage is Stage.ADULT
    assert life.high_happiness_since == back - MAX_CREDITED_GAP


# ---
# Old age
# ---


def old(stage: Stage, days: int, **fields: object) -> Life:
    """Build a Wisp of `stage` that hatched `days` days before T0."""
    return alive(full=FULL_MAX, at=T0 - timedelta(days=days), stage=stage, **fields)


@pytest.mark.parametrize("stage", [Stage.ADULT, Stage.ROCKSTAR])
def test_adult_and_rockstar_grow_old_at_day_45(stage: Stage) -> None:
    life = old(stage, OLD_FOGEY_AT_DAY)
    events = tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0)
    assert events == [Event(EventKind.GREW_OLD, Stage.OLD_FOGEY)]
    assert life.stage is Stage.OLD_FOGEY
    assert life.peak_stage is stage
    assert life.stage_started_at == T0
    assert life.phase is Phase.ALIVE


def test_adult_one_day_short_of_old_age_stays_adult() -> None:
    life = old(Stage.ADULT, OLD_FOGEY_AT_DAY - 1)
    assert tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0) == []
    assert life.stage is Stage.ADULT


def test_old_age_wins_over_rockstar_in_the_same_tick() -> None:
    life = old(
        Stage.ADULT,
        OLD_FOGEY_AT_DAY,
        high_happiness_since=T0 - ROCKSTAR_HAPPY_FOR,
    )
    events = tick(
        life, T0, frozen=False, happiness=ROCKSTAR_HAPPINESS, caretakers=0, people=0
    )
    assert events == [Event(EventKind.GREW_OLD, Stage.OLD_FOGEY)]
    assert life.stage is Stage.OLD_FOGEY
    assert life.peak_stage is Stage.ADULT
    assert life.high_happiness_since is None


def test_no_wisp_lives_past_the_farewell_day() -> None:
    life = old(Stage.TEEN, FAREWELL_AT_DAY + 1, stage_started_at=T0, last_tick_at=T0)
    events = run(life, TICK_EVERY * 3, fed=True, cared=True)
    assert events == [
        Event(EventKind.STAGE_UP, Stage.ADULT),
        Event(EventKind.GREW_OLD, Stage.OLD_FOGEY),
        Event(EventKind.FAREWELL),
    ]
    assert life.phase is Phase.PASSED


def test_old_fogey_drains_slower() -> None:
    life = old(Stage.OLD_FOGEY, OLD_FOGEY_AT_DAY, last_tick_at=T0)
    tick(life, T0 + MAX_CREDITED_GAP, frozen=False, happiness=0, caretakers=0, people=0)
    drained = OLD_FOGEY_FULL_DRAIN_PER_DAY * MAX_CREDITED_GAP / timedelta(days=1)
    assert life.full == pytest.approx(FULL_MAX - drained)


def test_old_fogey_does_not_grow_old_twice() -> None:
    life = old(Stage.OLD_FOGEY, OLD_FOGEY_AT_DAY + 1)
    assert tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0) == []
    assert life.stage is Stage.OLD_FOGEY


def test_farewell_at_day_60() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY)
    events = tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0)
    assert events == [Event(EventKind.FAREWELL)]
    assert life.phase is Phase.PASSED
    assert life.ended_at == T0
    assert is_over(life)


def test_old_fogey_lives_until_day_60() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY - 1)
    assert tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0) == []
    assert life.phase is Phase.ALIVE


def test_neglect_still_kills_an_old_fogey() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY)
    life.full = 0.01
    events = tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0)
    assert events == [Event(EventKind.DIED)]
    assert life.phase is Phase.DEAD


def test_passed_life_is_inert() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY)
    tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0)
    assert (
        tick(life, T0 + TICK_EVERY, frozen=False, happiness=0, caretakers=0, people=0)
        == []
    )
    assert feed(life, 10, FEEDER, T0) == []
    assert mood(life) is Mood.HAPPY


def test_egg_after_farewell_is_half_hatched_coal() -> None:
    passed = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY)
    passed.phase = Phase.PASSED
    egg = egg_after(passed, 4, T0)
    assert egg.version == 4
    assert egg.phase is Phase.EGG
    assert egg.egg_food == COAL_EGG_FOOD
    assert egg.from_coal
    assert egg.laid_at == T0


def test_coal_egg_hatches_after_the_remaining_food() -> None:
    passed = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY)
    passed.phase = Phase.PASSED
    egg = egg_after(passed, 2, T0)
    assert feed(egg, EGG_FOOD_NEEDED - COAL_EGG_FOOD - 1, FEEDER, T0) == []
    assert feed(egg, 1, FEEDER, T0) == [Event(EventKind.HATCH_STARTED)]


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD])
def test_egg_after_other_endings_is_fresh(phase: Phase) -> None:
    ended = alive()
    ended.phase = phase
    egg = egg_after(ended, 5, T0)
    assert (egg.version, egg.phase, egg.egg_food) == (5, Phase.EGG, 0)
    assert not egg.from_coal


def test_egg_after_nothing_is_fresh() -> None:
    egg = egg_after(None, 1, T0)
    assert (egg.version, egg.phase, egg.egg_food) == (1, Phase.EGG, 0)
    assert not egg.from_coal


# ---
# The childhood cold
# ---


class EdgeRng(random.Random):
    """An rng whose `uniform` always lands on one end of its range."""

    def __init__(self, *, high: bool) -> None:
        super().__init__(0)
        self.high = high

    def uniform(self, a: float, b: float) -> float:
        return b if self.high else a


def due(life: Life, at: datetime) -> Life:
    """Give `life` a cold that is due at `at`, ticked up to just before it."""
    life.cold_due_at = at
    life.last_tick_at = at - TICK_EVERY
    return life


def sick(full: float) -> Life:
    """Build a Wisp in the middle of his cold."""
    return alive(full, cold_left=SICK_FOR.total_seconds(), had_cold=True)


@pytest.mark.parametrize(
    ("high", "after"), [(False, COLD_EARLIEST), (True, COLD_LATEST)]
)
def test_schedule_cold_lands_between_day_one_and_seven(
    high: bool, after: timedelta
) -> None:
    life = alive(at=T0 - timedelta(days=2))
    schedule_cold(life, EdgeRng(high=high))
    assert life.cold_due_at == T0 - timedelta(days=2) + after
    assert (COLD_EARLIEST, COLD_LATEST) == (timedelta(days=1), timedelta(days=7))
    assert COLD_LATEST + SICK_FOR <= 3 * STAGE_MIN_TIME


def test_a_legacy_child_gets_a_cold_scheduled() -> None:
    life = alive(stage=Stage.CHILD, at=T0 - timedelta(days=5))
    assert (life.cold_due_at, life.cold_left, life.had_cold) == (None, 0.0, False)
    schedule_cold(life, random.Random(7))
    assert life.cold_due_at is not None
    assert (
        T0 - timedelta(days=4)
        <= life.cold_due_at
        <= T0 - timedelta(days=5) + COLD_LATEST
    )
    assert not is_sick(life)


@pytest.mark.parametrize("stage", [Stage.ADULT, Stage.ROCKSTAR, Stage.OLD_FOGEY])
def test_an_adult_never_catches_a_cold(stage: Stage) -> None:
    life = alive(full=FULL_MAX, stage=stage, at=T0 - timedelta(days=20))
    schedule_cold(life, random.Random(1))
    assert life.cold_due_at is None
    events = run(life, timedelta(days=3), fed=True, cared=True)
    assert EventKind.SICK not in kinds(events)
    assert not is_sick(life)


def test_an_egg_gets_no_cold_until_he_hatches() -> None:
    egg = new_egg(1, T0)
    schedule_cold(egg, random.Random(1))
    assert egg.cold_due_at is None


def test_schedule_cold_never_twice() -> None:
    life = alive(at=T0 - timedelta(days=2))
    schedule_cold(life, EdgeRng(high=False))
    first = life.cold_due_at
    schedule_cold(life, EdgeRng(high=True))
    assert life.cold_due_at == first

    over = alive(had_cold=True)
    schedule_cold(over, EdgeRng(high=False))
    assert over.cold_due_at is None

    dead = alive(at=T0 - timedelta(days=2))
    dead.phase = Phase.DEAD
    schedule_cold(dead, EdgeRng(high=False))
    assert dead.cold_due_at is None


def test_the_cold_starts_when_due_and_lasts_48_credited_hours() -> None:
    life = due(alive(full=FULL_MAX, stage=Stage.CHILD), T0 + timedelta(days=2))
    assert not is_sick(life)

    events = run(life, SICK_FOR - TICK_EVERY, fed=True, cared=True)
    assert events == [Event(EventKind.SICK, Stage.CHILD)]
    assert is_sick(life)
    assert life.had_cold
    assert life.cold_left == TICK_EVERY.total_seconds()

    assert run(life, TICK_EVERY, fed=True, cared=True) == [
        Event(EventKind.RECOVERED, Stage.CHILD)
    ]
    assert not is_sick(life)
    assert run(life, timedelta(days=3), fed=True, cared=True) == []


def test_a_due_cold_starts_before_growth_in_the_same_tick() -> None:
    life = alive(
        full=FULL_MAX,
        stage=Stage.TEEN,
        at=T0 - timedelta(days=10),
        growth=STAGE_RULES[Stage.ADULT].growth,
        cold_due_at=T0 - timedelta(days=4),
    )
    back = T0 + timedelta(days=2)
    events = tick(life, back, frozen=False, happiness=0, caretakers=1, people=0)
    assert events == [
        Event(EventKind.SICK, Stage.TEEN),
        Event(EventKind.STAGE_UP, Stage.ADULT),
    ]
    assert is_sick(life)
    assert life.cold_left == (SICK_FOR - MAX_CREDITED_GAP).total_seconds()


def test_frozen_time_does_not_count_down_the_cold() -> None:
    life = sick(full=FULL_MAX)
    assert run(life, timedelta(days=3), step=MAX_CREDITED_GAP, frozen=True) == []
    assert life.cold_left == SICK_FOR.total_seconds()

    waiting = due(alive(full=FULL_MAX), T0 + timedelta(hours=1))
    run(waiting, timedelta(days=1), frozen=True)
    assert not is_sick(waiting)
    assert not waiting.had_cold
    events = run(waiting, TICK_EVERY, fed=True, cared=True)
    assert events == [Event(EventKind.SICK, Stage.BABY)]


def test_sick_drains_full_one_and_a_half_times_as_fast() -> None:
    assert SICK_DRAIN_MULTIPLIER == 1.5
    life = sick(full=80.0)
    run(life, timedelta(days=1), step=MAX_CREDITED_GAP)
    assert life.full == pytest.approx(80.0 - FULL_DRAIN_PER_DAY * 1.5)
    assert life.cold_left == timedelta(days=1).total_seconds()


def test_he_cannot_die_while_sick() -> None:
    life = due(alive(full=12.0, care=CARE_MAX), T0 + TICK_EVERY)
    events: list[Event] = []
    for _ in range(int(SICK_FOR / TICK_EVERY)):
        events += run(life, TICK_EVERY)
        assert life.full >= SICK_FULL_FLOOR == 1.0
        assert life.phase is Phase.ALIVE
    assert kinds(events) == [
        EventKind.SICK,
        EventKind.HUNGRY,
        EventKind.FADING,
        EventKind.RECOVERED,
    ]
    assert life.full == SICK_FULL_FLOOR

    now = life.last_tick_at
    after: list[Event] = []
    for _ in range(int(timedelta(hours=2) / TICK_EVERY)):
        now += TICK_EVERY
        after += tick(life, now, frozen=False, happiness=0, caretakers=0, people=0)
    assert kinds(after) == [EventKind.DIED]
    assert life.phase is Phase.DEAD


def test_the_sick_floor_never_feeds_him() -> None:
    life = sick(full=0.5)
    run(life, timedelta(hours=1))
    assert life.full == 0.5
    assert life.phase is Phase.ALIVE


# ---
# Staff tests
# ---


@pytest.mark.parametrize(
    ("stage", "kind"),
    [
        (Stage.CHILD, EventKind.STAGE_UP),
        (Stage.TEEN, EventKind.STAGE_UP),
        (Stage.ADULT, EventKind.STAGE_UP),
        (Stage.ROCKSTAR, EventKind.STAGE_UP),
        (Stage.OLD_FOGEY, EventKind.GREW_OLD),
    ],
)
def test_a_jumped_wisp_stays_in_his_stage(stage: Stage, kind: EventKind) -> None:
    life = alive(full=FULL_MAX, last_tick_at=T0)
    assert jump_to(life, stage, T0) == Event(kind, stage)
    assert (life.stage, life.stage_started_at) == (stage, T0)
    assert run(life, timedelta(days=2), fed=True, cared=True, people=1) == []
    assert life.stage is stage


def test_a_jump_back_to_baby_is_not_announced() -> None:
    life = alive(full=FULL_MAX, stage=Stage.TEEN, last_tick_at=T0)
    assert jump_to(life, Stage.BABY, T0) is None
    assert (life.stage, life.peak_stage, life.hatched_at) == (
        Stage.BABY,
        Stage.BABY,
        T0,
    )


def test_an_old_fogey_jumped_to_counts_as_a_grown_up() -> None:
    young = alive(full=FULL_MAX, stage=Stage.CHILD)
    jump_to(young, Stage.OLD_FOGEY, T0)
    assert young.peak_stage is Stage.ADULT
    star = alive(full=FULL_MAX, stage=Stage.ROCKSTAR)
    jump_to(star, Stage.OLD_FOGEY, T0)
    assert star.peak_stage is Stage.ROCKSTAR


def test_ready_to_pass_on_says_farewell_on_the_next_tick() -> None:
    life = alive(full=FULL_MAX, stage=Stage.CHILD, last_tick_at=T0)
    ready_to_pass_on(life, T0)
    assert tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0) == [
        Event(EventKind.FAREWELL)
    ]
    assert life.phase is Phase.PASSED


def test_starve_ends_even_a_sick_wisp_on_the_next_tick() -> None:
    life = sick(full=FULL_MAX)
    life.last_tick_at = T0
    starve(life)
    events = tick(life, T0, frozen=False, happiness=0, caretakers=0, people=0)
    assert events == [Event(EventKind.DIED)]
    assert life.phase is Phase.DEAD
