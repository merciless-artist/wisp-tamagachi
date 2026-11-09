"""Tests for the life engine: eggs, the meters, colds, stages and death."""

import dataclasses
import random
from datetime import UTC, datetime, timedelta

import pytest

from wisp.life import (
    Event,
    EventKind,
    Life,
    Meter,
    Mood,
    Phase,
    add_growth,
    age_days,
    caretakers_needed,
    catch_sniffles,
    change_meter,
    credited_gap,
    cure_sniffles,
    cut_short,
    egg_after,
    end_stretch,
    feed,
    has_sniffles,
    is_over,
    is_sick,
    jump_to,
    mood,
    new_egg,
    own_time,
    ready_to_pass_on,
    schedule_cold,
    tick,
)
from wisp.rules import (
    COAL_EGG_FOOD,
    COLD_EARLIEST,
    COLD_LATEST,
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    FAREWELL_AT_DAY,
    HATCHING_TIME,
    HEALTH_MAX,
    HEALTH_START,
    HEALTH_STRETCH,
    LONELY_BELOW,
    MAX_CREDITED_GAP,
    OLD_FOGEY_AT_DAY,
    POX_HEALED_PER_MEAL_POINT,
    ROCKSTAR_WELLBEING,
    ROCKSTAR_WELLBEING_FOR,
    SICK_DRAIN_MULTIPLIER,
    SICK_FOR,
    SICK_FULL_FLOOR,
    SNIFFLES_FOR,
    STAGE_MIN_TIME,
    STAGE_RULES,
    TICK_EVERY,
    WELLBEING_MAX,
    WELLBEING_START,
    WELLBEING_STRETCH,
    Stage,
)

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
FEEDER = 4242
SIX_HOURS = timedelta(hours=6)
STRETCHES = ("health_stretch", "wellbeing_stretch")
LEVELS = {
    Meter.HEALTH: "health",
    Meter.WELLBEING: "wellbeing",
}


def alive(
    health: float = HEALTH_START,
    at: datetime = T0,
    stage: Stage = Stage.BABY,
    **fields: object,
) -> Life:
    """Build a living Wisp that hatched at `at`."""
    life = new_egg(1, at)
    life.phase = Phase.ALIVE
    life.stage = stage
    life.peak_stage = stage
    life.health = health
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
    caretakers: int = 0,
    people: int = 0,
    fed: bool = False,
    cared: bool = False,
    wellbeing_at: float | None = None,
) -> list[Event]:
    """Tick `life` every `step` for `duration`, optionally tending a meter.

    Before every step `fed` fills health, `cared` fills wellbeing and
    `wellbeing_at` sets it, each ending that meter's stretch, as a track, a
    chat or a game would.
    """
    events: list[Event] = []
    end = life.last_tick_at + duration
    while life.last_tick_at < end:
        if fed:
            life.health, life.health_stretch = HEALTH_MAX, 0.0
        if cared:
            life.wellbeing, life.wellbeing_stretch = WELLBEING_MAX, 0.0
        if wellbeing_at is not None:
            life.wellbeing, life.wellbeing_stretch = wellbeing_at, 0.0
        events += tick(
            life,
            life.last_tick_at + step,
            frozen=frozen,
            caretakers=caretakers,
            people=people,
        )
    return events


def tended(life: Life, duration: timedelta) -> list[Event]:
    """Tick a Wisp fed and cared for enough to become a Rockstar."""
    return run(life, duration, fed=True, wellbeing_at=ROCKSTAR_WELLBEING)


def stretch_left(length: timedelta) -> float:
    """A stretch of `length` with one tick still to go, in seconds."""
    return (length - TICK_EVERY).total_seconds()


def kinds(events: list[Event]) -> list[EventKind]:
    """The kinds of the events, leaving out meter drops (see `drops`)."""
    return [event.kind for event in events if event.kind is not EventKind.METER_DROP]


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
    assert egg.health == HEALTH_START
    assert egg.hatched_at == egg.stage_started_at == egg.last_tick_at
    assert egg.phase_seconds == 0


def test_hatching_does_not_drain_the_newborn_in_the_same_tick() -> None:
    egg = new_egg(1, T0)
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    egg.phase_seconds = HATCHING_TIME.total_seconds() - 1
    tick(egg, T0 + MAX_CREDITED_GAP, frozen=False, caretakers=0, people=0)
    assert egg.health == HEALTH_START
    assert [getattr(egg, name) for name in STRETCHES] == [0.0, 0.0]


def test_meters_start_at_fifty_when_he_hatches() -> None:
    egg = new_egg(1, T0)
    egg.wellbeing = 0.0
    egg.health_stretch = egg.wellbeing_stretch = 600.0
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    run(egg, HATCHING_TIME)
    assert egg.phase is Phase.ALIVE
    assert (egg.health, egg.wellbeing) == (50.0, 50.0)
    assert (HEALTH_START, WELLBEING_START) == (50.0, 50.0)
    assert [getattr(egg, name) for name in STRETCHES] == [0.0, 0.0]
    assert not egg.lonely_warned


def test_feeding_while_hatching_is_ignored() -> None:
    egg = new_egg(1, T0)
    feed(egg, EGG_FOOD_NEEDED, FEEDER, T0)
    snapshot = (egg.egg_food, egg.hatched_by, egg.phase_seconds)
    assert feed(egg, 10, 99, T0 + timedelta(hours=1)) == []
    assert (egg.egg_food, egg.hatched_by, egg.phase_seconds) == snapshot
    assert egg.phase is Phase.HATCHING


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD])
def test_feeding_over_life_is_ignored(phase: Phase) -> None:
    life = alive(health=40.0)
    life.phase = phase
    assert feed(life, 10, FEEDER, T0) == []
    assert life.health == 40.0
    assert life.egg_food == 0


# ---
# The meters
# ---


def test_he_has_two_meters_health_and_wellbeing() -> None:
    assert list(Meter) == [Meter.HEALTH, Meter.WELLBEING]
    fields = {field.name for field in dataclasses.fields(Life)}
    assert not {"mood_meter", "mood_stretch"} & fields


def test_nothing_drains_between_penalties() -> None:
    life = alive()
    run(life, timedelta(hours=5, minutes=55))
    assert (life.health, life.wellbeing) == (50.0, 50.0)


def test_six_hours_without_a_track_costs_eight_health() -> None:
    life = alive()
    run(life, SIX_HOURS)
    assert life.health == 42.0


def test_an_old_fogey_loses_six_health() -> None:
    life = alive(stage=Stage.OLD_FOGEY)
    run(life, SIX_HOURS)
    assert life.health == 44.0


def test_monster_pox_makes_the_health_penalty_twelve() -> None:
    assert SICK_DRAIN_MULTIPLIER == 1.5
    life = sick(health=50.0)
    run(life, SIX_HOURS)
    assert life.health == 38.0


def test_monster_pox_keeps_him_at_one_health() -> None:
    life = sick(health=5.0)
    events = run(life, SIX_HOURS)
    assert life.health == 1.0
    assert EventKind.DIED not in kinds(events)
    assert life.phase is Phase.ALIVE


def test_a_fed_track_restarts_the_health_stretch() -> None:
    life = alive()
    run(life, timedelta(hours=5))
    feed(life, 5, FEEDER, life.last_tick_at)
    run(life, timedelta(hours=5, minutes=55))
    assert life.health == 55.0
    run(life, TICK_EVERY)
    assert life.health == 47.0


def test_zero_health_from_a_penalty_kills_him() -> None:
    life = alive(health=8.0)
    events = run(life, SIX_HOURS)
    assert EventKind.DIED in kinds(events)
    assert life.phase is Phase.DEAD
    assert (life.health, life.ended_at) == (0.0, life.last_tick_at)
    assert is_over(life)


def test_six_hours_without_a_chat_or_snack_costs_ten_wellbeing() -> None:
    life = alive()
    run(life, SIX_HOURS)
    assert life.wellbeing == 40.0


def test_a_cold_makes_the_health_penalty_twelve_not_the_wellbeing_one() -> None:
    life = alive(sniffles_left=SNIFFLES_FOR.total_seconds())
    run(life, SIX_HOURS)
    assert life.health == 50.0 - 8.0 * SICK_DRAIN_MULTIPLIER == 38.0
    assert life.wellbeing == 40.0


def test_a_cold_keeps_him_at_one_health() -> None:
    life = alive(health=5.0, sniffles_left=SNIFFLES_FOR.total_seconds())
    events = run(life, SIX_HOURS)
    assert life.health == SICK_FULL_FLOOR == 1.0
    assert EventKind.DIED not in kinds(events)
    assert life.phase is Phase.ALIVE


def test_monster_pox_and_a_cold_together_cost_health_only_once_over() -> None:
    life = alive(
        cold_left=SICK_FOR.total_seconds(),
        had_cold=True,
        sniffles_left=SNIFFLES_FOR.total_seconds(),
    )
    run(life, SIX_HOURS)
    assert life.health == 38.0
    assert life.wellbeing == 40.0


def test_a_penalty_never_takes_wellbeing_below_zero() -> None:
    life = alive(wellbeing=3.0, wellbeing_stretch=stretch_left(WELLBEING_STRETCH))
    run(life, TICK_EVERY)
    assert life.wellbeing == 0.0
    assert life.phase is Phase.ALIVE


def test_change_meter_ending_a_stretch_restarts_only_that_meter() -> None:
    three_hours = timedelta(hours=3).total_seconds()
    life = alive(health_stretch=three_hours, wellbeing_stretch=three_hours)
    change_meter(life, Meter.WELLBEING, 5, ends_stretch=True)
    assert life.wellbeing_stretch == 0.0
    assert life.health_stretch == three_hours
    assert life.wellbeing == 55.0


def test_change_meter_without_ending_keeps_the_stretch() -> None:
    life = alive(wellbeing_stretch=600.0)
    change_meter(life, Meter.WELLBEING, 5)
    assert (life.wellbeing, life.wellbeing_stretch) == (55.0, 600.0)


def test_end_stretch_restarts_one_stretch_without_moving_the_meter() -> None:
    life = alive(health_stretch=600.0, wellbeing_stretch=900.0, wellbeing=40.0)
    end_stretch(life, Meter.WELLBEING)
    assert (life.wellbeing, life.wellbeing_stretch) == (40.0, 0.0)
    assert life.health_stretch == 600.0
    end_stretch(life, Meter.HEALTH)
    assert (life.health, life.health_stretch) == (HEALTH_START, 0.0)


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
def test_end_stretch_only_counts_while_alive(phase: Phase) -> None:
    life = alive(health_stretch=600.0, wellbeing_stretch=600.0)
    life.phase = phase
    for meter in Meter:
        end_stretch(life, meter)
    assert [getattr(life, name) for name in STRETCHES] == [600.0] * 2


@pytest.mark.parametrize("meter", list(Meter))
def test_change_meter_clamps_and_only_counts_while_alive(meter: Meter) -> None:
    assert (HEALTH_MAX, WELLBEING_MAX) == (100.0,) * 2
    life = alive()
    change_meter(life, meter, 80)
    assert getattr(life, LEVELS[meter]) == 100.0
    change_meter(life, meter, -200)
    assert getattr(life, LEVELS[meter]) == 0.0
    for phase in (Phase.EGG, Phase.HATCHING, Phase.DEAD, Phase.COLD, Phase.PASSED):
        other = alive(health_stretch=600.0, wellbeing_stretch=600.0)
        other.phase = phase
        change_meter(other, meter, 10, ends_stretch=True)
        assert getattr(other, LEVELS[meter]) == 50.0
        assert [getattr(other, name) for name in STRETCHES] == [600.0] * 2


def test_frozen_and_offline_time_never_fill_a_stretch() -> None:
    life = alive()
    run(life, timedelta(hours=7), step=MAX_CREDITED_GAP, frozen=True)
    assert (life.health, life.wellbeing) == (50.0, 50.0)
    assert [getattr(life, name) for name in STRETCHES] == [0.0, 0.0]
    back = life.last_tick_at + timedelta(hours=7)
    tick(life, back, frozen=False, caretakers=0, people=0)
    gap = MAX_CREDITED_GAP.total_seconds()
    assert [getattr(life, name) for name in STRETCHES] == [gap, gap]
    assert (life.health, life.wellbeing) == (50.0, 50.0)


def test_an_egg_fills_no_stretch() -> None:
    egg = new_egg(1, T0)
    run(egg, timedelta(hours=7))
    assert [getattr(egg, name) for name in STRETCHES] == [0.0, 0.0]
    assert egg.wellbeing == WELLBEING_START


@pytest.mark.parametrize(
    ("since_last_tick", "frozen", "credited"),
    [
        (timedelta(minutes=5), False, timedelta(minutes=5)),
        (MAX_CREDITED_GAP, False, MAX_CREDITED_GAP),
        (timedelta(hours=7), False, MAX_CREDITED_GAP),
        (timedelta(minutes=5), True, timedelta(0)),
        (timedelta(hours=7), True, timedelta(0)),
        (-timedelta(minutes=5), False, timedelta(0)),
    ],
)
def test_credited_gap_is_zero_frozen_capped_and_never_negative(
    since_last_tick: timedelta, frozen: bool, credited: timedelta
) -> None:
    life = alive(last_tick_at=T0)
    assert credited_gap(life, T0 + since_last_tick, frozen=frozen) == credited
    assert life.last_tick_at == T0


def test_frozen_tick_changes_nothing() -> None:
    life = alive(health=50.0)
    now = T0 + timedelta(minutes=10)
    assert tick(life, now, frozen=True, caretakers=0, people=0) == []
    assert life.health == 50.0
    assert life.phase_seconds == 0
    assert life.last_tick_at == now


def test_clock_going_backwards_credits_nothing() -> None:
    life = alive(health=50.0)
    tick(life, T0 - timedelta(minutes=5), frozen=False, caretakers=0, people=0)
    assert life.health == 50.0
    assert [getattr(life, name) for name in STRETCHES] == [0.0, 0.0]


def test_hungry_and_fading_warn_once_each() -> None:
    life = alive(health=34.0)
    events = run(life, timedelta(days=1), cared=True)
    assert kinds(events) == [EventKind.HUNGRY, EventKind.FADING]
    assert life.health == 2.0
    assert life.warned is EventKind.FADING
    assert life.phase is Phase.ALIVE


def test_one_tick_can_cross_both_thresholds() -> None:
    life = alive(health=12.0, health_stretch=stretch_left(HEALTH_STRETCH))
    events = run(life, TICK_EVERY)
    assert kinds(events) == [EventKind.HUNGRY, EventKind.FADING]


def test_feeding_above_threshold_rearms_warning() -> None:
    life = alive(health=5.0, warned=EventKind.FADING)
    feed(life, 3, FEEDER, T0)
    assert life.warned is EventKind.FADING
    feed(life, 26, FEEDER, T0)
    assert life.health == 34.0
    assert life.warned is None
    events = run(life, timedelta(hours=8))
    assert kinds(events) == [EventKind.HUNGRY]


def test_fading_rearms_after_feeding_into_the_hungry_band() -> None:
    life = alive(health=5.0, warned=EventKind.FADING)
    feed(life, 10, FEEDER, T0)
    assert life.health == 15.0
    assert life.warned is EventKind.HUNGRY
    events = run(life, timedelta(hours=10))
    assert kinds(events) == [EventKind.FADING]


def test_full_never_exceeds_max() -> None:
    life = alive(health=95.0)
    assert feed(life, 50, FEEDER, T0) == []
    assert life.health == HEALTH_MAX


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD])
def test_tick_on_over_life_is_a_no_op(phase: Phase) -> None:
    life = alive(health=0.0)
    life.phase = phase
    before = (life.health, life.last_tick_at, life.phase_seconds, life.ended_at)
    later = T0 + timedelta(hours=1)
    assert tick(life, later, frozen=False, caretakers=9, people=0) == []
    assert (life.health, life.last_tick_at, life.phase_seconds, life.ended_at) == before


# ---
# How he feels
# ---


@pytest.mark.parametrize(
    "health,expected",
    [(29.9, Mood.HANGRY), (30.0, Mood.HAPPY), (80.0, Mood.HAPPY)],
)
def test_mood_is_hangry_below_thirty(health: float, expected: Mood) -> None:
    assert mood(alive(health=health)) is expected


def test_mood_hangry_beats_lonely() -> None:
    assert mood(alive(health=10.0, wellbeing=10.0)) is Mood.HANGRY


@pytest.mark.parametrize(
    "wellbeing,expected",
    [(LONELY_BELOW - 0.1, Mood.LONELY), (LONELY_BELOW, Mood.HAPPY), (90.0, Mood.HAPPY)],
)
def test_mood_lonely_below_the_line(wellbeing: float, expected: Mood) -> None:
    assert mood(alive(health=80.0, wellbeing=wellbeing)) is expected


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
def test_only_a_living_wisp_is_lonely(phase: Phase) -> None:
    life = alive(health=80.0, wellbeing=5.0)
    life.phase = phase
    assert mood(life) is Mood.HAPPY


def test_lonely_warns_once_per_drop() -> None:
    life = alive(
        stage=Stage.CHILD,
        wellbeing=LONELY_BELOW + 5,
        wellbeing_stretch=stretch_left(WELLBEING_STRETCH),
    )
    events = run(life, TICK_EVERY, fed=True)
    assert events == [
        Event(EventKind.LONELY, Stage.CHILD),
        Event(EventKind.METER_DROP, meter=Meter.WELLBEING, lost=10.0, value=25.0),
    ]
    assert life.lonely_warned
    assert kinds(run(life, timedelta(days=1), fed=True)) == []

    change_meter(life, Meter.WELLBEING, LONELY_BELOW - life.wellbeing - 1)
    assert life.lonely_warned
    change_meter(life, Meter.WELLBEING, 1)
    assert life.wellbeing == LONELY_BELOW
    assert not life.lonely_warned
    life.wellbeing_stretch = stretch_left(WELLBEING_STRETCH)
    assert kinds(run(life, TICK_EVERY, fed=True)) == [EventKind.LONELY]


def test_loneliness_never_hurts_him() -> None:
    life = alive(health=HEALTH_MAX, wellbeing=0.0, at=T0 - STAGE_MIN_TIME, growth=25)
    events = tick(life, T0, frozen=False, caretakers=3, people=0)
    assert kinds(events) == [EventKind.LONELY, EventKind.STAGE_UP]
    assert life.phase is Phase.ALIVE
    assert life.health == HEALTH_MAX


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
    life = alive(health=HEALTH_MAX, at=T0 - in_stage, growth=growth)
    events = tick(life, T0, frozen=False, caretakers=caretakers, people=people)
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
    life = alive(health=HEALTH_MAX, at=T0 - by_day, stage=stage, stage_started_at=T0)
    almost = alive(
        health=HEALTH_MAX,
        at=T0 - by_day + timedelta(hours=1),
        stage=stage,
        stage_started_at=T0,
    )
    assert tick(life, T0, frozen=False, caretakers=0, people=9) == [
        Event(EventKind.STAGE_UP, grows_into)
    ]
    assert tick(almost, T0, frozen=False, caretakers=0, people=9) == []


def test_stage_up_moves_one_stage_per_tick() -> None:
    life = alive(health=HEALTH_MAX, at=T0 - timedelta(days=40), growth=500)
    first = tick(life, T0, frozen=False, caretakers=20, people=0)
    second = tick(life, T0 + TICK_EVERY, frozen=False, caretakers=20, people=0)
    assert first == [Event(EventKind.STAGE_UP, Stage.CHILD)]
    assert second == [Event(EventKind.STAGE_UP, Stage.TEEN)]


def test_late_bloomer_grows_when_caretakers_arrive() -> None:
    life = alive(
        health=HEALTH_MAX,
        at=T0 - STAGE_MIN_TIME - timedelta(days=1),
        growth=_CHILD.growth + 30,
        last_tick_at=T0,
    )
    assert run(life, timedelta(hours=1), caretakers=1, people=8) == []
    assert life.stage is Stage.BABY
    events = run(life, TICK_EVERY, caretakers=2, people=8)
    assert events == [Event(EventKind.STAGE_UP, Stage.CHILD)]
    assert life.stage_started_at == life.last_tick_at


def test_rockstar_after_four_days_of_wellbeing_at_eighty() -> None:
    assert (ROCKSTAR_WELLBEING, ROCKSTAR_WELLBEING_FOR) == (80, timedelta(days=4))
    life = alive(health=HEALTH_MAX, stage=Stage.ADULT)
    almost = ROCKSTAR_WELLBEING_FOR - timedelta(hours=1)
    events = tended(life, almost)
    assert events == []
    events = tended(life, timedelta(hours=2))
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]
    assert life.stage is Stage.ROCKSTAR
    assert life.peak_stage is Stage.ROCKSTAR


def test_a_wellbeing_dip_resets_the_rockstar_clock() -> None:
    almost = ROCKSTAR_WELLBEING_FOR - timedelta(days=1)
    life = alive(health=HEALTH_MAX, stage=Stage.ADULT)
    tended(life, almost)
    assert life.high_mood_since is not None
    run(life, TICK_EVERY, fed=True, wellbeing_at=ROCKSTAR_WELLBEING - 1)
    assert life.high_mood_since is None
    events = tended(life, almost)
    assert events == []
    assert life.stage is Stage.ADULT
    events = run(life, timedelta(days=1, hours=1), fed=True, cared=True)
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]


def test_a_wellbeing_penalty_below_eighty_resets_the_rockstar_clock() -> None:
    life = alive(health=HEALTH_MAX, stage=Stage.ADULT)
    tended(life, timedelta(days=1))
    assert life.high_mood_since is not None
    life.wellbeing_stretch = stretch_left(WELLBEING_STRETCH)
    run(life, TICK_EVERY, fed=True)
    assert life.wellbeing == ROCKSTAR_WELLBEING - 10
    assert life.high_mood_since is None


def test_only_adults_build_a_rockstar_streak() -> None:
    life = alive(health=HEALTH_MAX, stage=Stage.TEEN)
    run(life, timedelta(hours=1), fed=True, cared=True)
    assert life.high_mood_since is None


def test_frozen_span_does_not_count_toward_rockstar() -> None:
    life = alive(health=HEALTH_MAX, stage=Stage.ADULT)
    tended(life, timedelta(days=1))
    run(life, ROCKSTAR_WELLBEING_FOR, step=MAX_CREDITED_GAP, frozen=True)
    events = tended(life, TICK_EVERY)
    assert events == []
    assert life.stage is Stage.ADULT
    remaining = ROCKSTAR_WELLBEING_FOR - timedelta(days=1)
    events = tended(life, remaining)
    assert events == [Event(EventKind.STAGE_UP, Stage.ROCKSTAR)]


def test_offline_gap_counts_only_fifteen_minutes_toward_rockstar() -> None:
    life = alive(health=HEALTH_MAX, stage=Stage.ADULT, wellbeing=WELLBEING_MAX)
    tick(life, T0 + TICK_EVERY, frozen=False, caretakers=0, people=0)
    since = life.high_mood_since
    assert since is not None
    back = T0 + TICK_EVERY + timedelta(days=ROCKSTAR_WELLBEING_FOR.days + 1)
    life.health = HEALTH_MAX
    events = tick(life, back, frozen=False, caretakers=0, people=0)
    assert events == []
    assert life.stage is Stage.ADULT
    assert life.high_mood_since == back - MAX_CREDITED_GAP


# ---
# Old age
# ---


def old(stage: Stage, days: int, **fields: object) -> Life:
    """Build a Wisp of `stage` that hatched `days` days before T0."""
    return alive(health=HEALTH_MAX, at=T0 - timedelta(days=days), stage=stage, **fields)


@pytest.mark.parametrize("stage", [Stage.ADULT, Stage.ROCKSTAR])
def test_adult_and_rockstar_grow_old_at_day_45(stage: Stage) -> None:
    life = old(stage, OLD_FOGEY_AT_DAY)
    events = tick(life, T0, frozen=False, caretakers=0, people=0)
    assert events == [Event(EventKind.GREW_OLD, Stage.OLD_FOGEY)]
    assert life.stage is Stage.OLD_FOGEY
    assert life.peak_stage is stage
    assert life.stage_started_at == T0
    assert life.phase is Phase.ALIVE


def test_adult_one_day_short_of_old_age_stays_adult() -> None:
    life = old(Stage.ADULT, OLD_FOGEY_AT_DAY - 1)
    assert tick(life, T0, frozen=False, caretakers=0, people=0) == []
    assert life.stage is Stage.ADULT


def test_old_age_wins_over_rockstar_in_the_same_tick() -> None:
    life = old(
        Stage.ADULT,
        OLD_FOGEY_AT_DAY,
        high_mood_since=T0 - ROCKSTAR_WELLBEING_FOR,
        wellbeing=float(ROCKSTAR_WELLBEING),
    )
    events = tick(life, T0, frozen=False, caretakers=0, people=0)
    assert events == [Event(EventKind.GREW_OLD, Stage.OLD_FOGEY)]
    assert life.stage is Stage.OLD_FOGEY
    assert life.peak_stage is Stage.ADULT
    assert life.high_mood_since is None


def test_no_wisp_lives_past_the_farewell_day() -> None:
    life = old(Stage.TEEN, FAREWELL_AT_DAY + 1, stage_started_at=T0, last_tick_at=T0)
    events = run(life, TICK_EVERY * 3, fed=True, cared=True)
    assert events == [
        Event(EventKind.STAGE_UP, Stage.ADULT),
        Event(EventKind.GREW_OLD, Stage.OLD_FOGEY),
        Event(EventKind.FAREWELL),
    ]
    assert life.phase is Phase.PASSED


def test_old_fogey_does_not_grow_old_twice() -> None:
    life = old(Stage.OLD_FOGEY, OLD_FOGEY_AT_DAY + 1)
    assert tick(life, T0, frozen=False, caretakers=0, people=0) == []
    assert life.stage is Stage.OLD_FOGEY


def test_farewell_at_day_60() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY)
    events = tick(life, T0, frozen=False, caretakers=0, people=0)
    assert events == [Event(EventKind.FAREWELL)]
    assert life.phase is Phase.PASSED
    assert life.ended_at == T0
    assert is_over(life)


def test_old_fogey_lives_until_day_60() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY - 1)
    assert tick(life, T0, frozen=False, caretakers=0, people=0) == []
    assert life.phase is Phase.ALIVE


def test_neglect_still_kills_an_old_fogey() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY)
    life.health = 0.01
    life.health_stretch = stretch_left(HEALTH_STRETCH)
    events = tick(life, T0, frozen=False, caretakers=0, people=0)
    assert events == [Event(EventKind.DIED)]
    assert life.phase is Phase.DEAD


def test_passed_life_is_inert() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY)
    tick(life, T0, frozen=False, caretakers=0, people=0)
    assert tick(life, T0 + TICK_EVERY, frozen=False, caretakers=0, people=0) == []
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


def sick(health: float) -> Life:
    """Build a Wisp in the middle of his cold."""
    return alive(health, cold_left=SICK_FOR.total_seconds(), had_cold=True)


@pytest.mark.parametrize(
    ("high", "after"), [(False, COLD_EARLIEST), (True, COLD_LATEST)]
)
def test_schedule_cold_lands_between_day_one_and_five(
    high: bool, after: timedelta
) -> None:
    life = alive(at=T0 - timedelta(days=2))
    schedule_cold(life, EdgeRng(high=high))
    assert life.cold_due_at == T0 - timedelta(days=2) + after
    assert (COLD_EARLIEST, COLD_LATEST) == (timedelta(days=1), timedelta(days=5))
    assert COLD_LATEST + SICK_FOR <= 3 * STAGE_MIN_TIME
    assert COLD_LATEST < 2 * STAGE_MIN_TIME


def test_a_teen_who_has_not_had_the_pox_never_gets_a_due_time() -> None:
    life = alive(stage=Stage.TEEN, at=T0 - timedelta(days=6))
    schedule_cold(life, random.Random(3))
    assert life.cold_due_at is None
    assert not life.had_cold


@pytest.mark.parametrize("seed", range(20))
def test_a_babys_due_time_is_one_to_five_days_after_hatching(seed: int) -> None:
    life = alive(stage=Stage.BABY)
    schedule_cold(life, random.Random(seed))
    assert life.cold_due_at is not None
    assert T0 + timedelta(days=1) <= life.cold_due_at <= T0 + timedelta(days=5)


def test_a_childs_running_pox_carries_into_teen() -> None:
    by_day = timedelta(days=STAGE_RULES[Stage.TEEN].by_day)
    life = alive(
        health=HEALTH_MAX,
        at=T0 - by_day,
        stage=Stage.CHILD,
        stage_started_at=T0,
        had_cold=True,
        cold_left=SICK_FOR.total_seconds(),
    )
    events = tick(life, T0, frozen=False, caretakers=0, people=9)
    assert events == [Event(EventKind.STAGE_UP, Stage.TEEN)]
    assert life.stage is Stage.TEEN
    assert is_sick(life)


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
    life = alive(health=HEALTH_MAX, stage=stage, at=T0 - timedelta(days=20))
    schedule_cold(life, random.Random(1))
    assert life.cold_due_at is None
    events = run(life, timedelta(days=3), fed=True, cared=True)
    assert EventKind.SICK not in kinds(events)
    assert not is_sick(life)


@pytest.mark.parametrize("stage", [Stage.TEEN, Stage.ADULT, Stage.OLD_FOGEY])
def test_a_due_time_found_after_childhood_is_cleared_never_caught(
    stage: Stage,
) -> None:
    life = due(alive(health=HEALTH_MAX, stage=stage), T0 - timedelta(days=1))
    events = tick(life, T0, frozen=False, caretakers=0, people=0)
    assert EventKind.SICK not in kinds(events)
    assert (life.cold_due_at, life.cold_left, life.had_cold) == (None, 0.0, False)
    schedule_cold(life, random.Random(1))
    assert life.cold_due_at is None


@pytest.mark.parametrize("stage", [Stage.TEEN, Stage.ADULT, Stage.ROCKSTAR])
def test_a_jump_past_childhood_clears_the_pox_due_time(stage: Stage) -> None:
    life = alive(health=HEALTH_MAX, cold_due_at=T0 + timedelta(days=3))
    jump_to(life, stage, T0, EdgeRng(high=False))
    assert life.cold_due_at is None
    run(life, timedelta(days=5), fed=True, cared=True, people=1)
    assert not life.had_cold
    assert not is_sick(life)


@pytest.mark.parametrize("stage", [Stage.BABY, Stage.CHILD])
@pytest.mark.parametrize(
    ("high", "after"), [(False, COLD_EARLIEST), (True, COLD_LATEST)]
)
def test_a_young_jump_rolls_the_pox_from_now_never_at_once(
    stage: Stage, high: bool, after: timedelta
) -> None:
    life = alive(
        health=HEALTH_MAX,
        cold_due_at=T0 - timedelta(days=1),
        last_tick_at=T0,
        frozen_seconds=timedelta(days=2).total_seconds(),
    )
    jump_to(life, stage, T0, EdgeRng(high=high))
    assert life.cold_due_at == T0 + after
    events = tick(life, T0 + TICK_EVERY, frozen=False, caretakers=0, people=0)
    assert EventKind.SICK not in kinds(events)
    assert not is_sick(life)


def test_a_young_jump_after_the_pox_rolls_nothing() -> None:
    life = alive(health=HEALTH_MAX, had_cold=True)
    jump_to(life, Stage.CHILD, T0, EdgeRng(high=False))
    assert life.cold_due_at is None


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
    life = due(alive(health=HEALTH_MAX, stage=Stage.CHILD), T0 + timedelta(days=2))
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
        health=HEALTH_MAX,
        stage=Stage.CHILD,
        at=T0 - timedelta(days=10),
        growth=STAGE_RULES[Stage.TEEN].growth,
        cold_due_at=T0 - timedelta(days=4),
    )
    back = T0 + timedelta(days=2)
    events = tick(life, back, frozen=False, caretakers=1, people=0)
    assert events == [
        Event(EventKind.SICK, Stage.CHILD),
        Event(EventKind.STAGE_UP, Stage.TEEN),
    ]
    assert is_sick(life)
    assert life.cold_left == (SICK_FOR - MAX_CREDITED_GAP).total_seconds()


def test_frozen_time_does_not_count_down_the_cold() -> None:
    life = sick(health=HEALTH_MAX)
    assert run(life, timedelta(days=3), step=MAX_CREDITED_GAP, frozen=True) == []
    assert life.cold_left == SICK_FOR.total_seconds()

    waiting = due(alive(health=HEALTH_MAX), T0 + timedelta(hours=1))
    run(waiting, timedelta(days=1), frozen=True)
    assert not is_sick(waiting)
    assert not waiting.had_cold
    events = run(waiting, TICK_EVERY, fed=True, cared=True)
    assert events == [Event(EventKind.SICK, Stage.BABY)]


def test_he_cannot_die_while_sick() -> None:
    life = due(alive(health=12.0), T0 + TICK_EVERY)
    events: list[Event] = []
    for _ in range(int(SICK_FOR / TICK_EVERY)):
        events += run(life, TICK_EVERY, cared=True)
        assert life.health >= SICK_FULL_FLOOR == 1.0
        assert life.phase is Phase.ALIVE
    assert kinds(events) == [
        EventKind.SICK,
        EventKind.HUNGRY,
        EventKind.FADING,
        EventKind.RECOVERED,
    ]
    assert life.health == SICK_FULL_FLOOR

    now = life.last_tick_at
    after: list[Event] = []
    for _ in range(int(HEALTH_STRETCH / TICK_EVERY)):
        now += TICK_EVERY
        after += tick(life, now, frozen=False, caretakers=0, people=0)
    assert kinds(after) == [EventKind.DIED]
    assert life.phase is Phase.DEAD


def test_pox_heals_15_minutes_per_meal_point_fed() -> None:
    assert POX_HEALED_PER_MEAL_POINT == timedelta(minutes=15)
    life = sick(health=50.0)

    assert feed(life, 5, FEEDER, T0) == []

    assert life.cold_left == SICK_FOR.total_seconds() - 5 * 15 * 60
    assert life.health == 55.0


def test_a_meal_that_ends_the_pox_says_he_recovered() -> None:
    life = sick(health=50.0)
    life.cold_left = 10 * 60.0

    events = feed(life, 1, FEEDER, T0)

    assert kinds(events) == [EventKind.RECOVERED]
    assert events[0].stage is Stage.BABY
    assert life.cold_left == 0.0
    assert not is_sick(life)


def test_feeding_a_well_wisp_or_a_cold_leaves_the_pox_alone() -> None:
    well = alive(50.0)
    cold = alive(50.0, sniffles_left=SNIFFLES_FOR.total_seconds())

    assert feed(well, 5, FEEDER, T0) == []
    assert feed(cold, 5, FEEDER, T0) == []

    assert well.cold_left == 0.0 and cold.cold_left == 0.0
    assert cold.sniffles_left == SNIFFLES_FOR.total_seconds()


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.PASSED, Phase.HATCHING])
def test_feeding_a_sick_life_that_is_not_alive_heals_nothing(phase: Phase) -> None:
    life = sick(health=50.0)
    life.phase = phase

    assert feed(life, 5, FEEDER, T0) == []
    assert life.cold_left == SICK_FOR.total_seconds()


def test_the_sick_floor_never_feeds_him() -> None:
    life = sick(health=0.5)
    run(life, SIX_HOURS)
    assert life.health == 0.5
    assert life.phase is Phase.ALIVE


# ---
# A cold (sniffles)
# ---


def test_catch_sniffles_starts_a_48_hour_cold() -> None:
    assert SNIFFLES_FOR == timedelta(hours=48)
    life = alive()
    assert not has_sniffles(life)
    assert catch_sniffles(life) is True
    assert life.sniffles_left == SNIFFLES_FOR.total_seconds()
    assert has_sniffles(life)
    assert not is_sick(life)


@pytest.mark.parametrize(
    "fields",
    [
        {"cold_left": SICK_FOR.total_seconds(), "had_cold": True},
        {"sniffles_left": 1000.0},
    ],
    ids=["monster-pox", "a-cold-already"],
)
def test_no_cold_while_he_has_monster_pox_or_one_already(
    fields: dict[str, object],
) -> None:
    life = alive(**fields)
    before = life.sniffles_left
    assert catch_sniffles(life) is False
    assert life.sniffles_left == before


@pytest.mark.parametrize(
    "phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD, Phase.COLD, Phase.PASSED]
)
def test_only_a_living_wisp_catches_a_cold(phase: Phase) -> None:
    life = alive()
    life.phase = phase
    assert catch_sniffles(life) is False
    assert life.sniffles_left == 0.0


def test_a_cold_wears_off_after_48_counted_hours() -> None:
    life = alive(health=HEALTH_MAX)
    catch_sniffles(life)
    assert run(life, SNIFFLES_FOR - TICK_EVERY, fed=True, cared=True) == []
    assert life.sniffles_left == TICK_EVERY.total_seconds()
    run(life, timedelta(days=1), step=MAX_CREDITED_GAP, frozen=True)
    assert life.sniffles_left == TICK_EVERY.total_seconds()
    assert run(life, TICK_EVERY, fed=True, cared=True) == []
    assert life.sniffles_left == 0.0
    assert not has_sniffles(life)


def test_cure_sniffles_ends_it_at_once() -> None:
    life = alive()
    catch_sniffles(life)
    assert cure_sniffles(life) is True
    assert (life.sniffles_left, has_sniffles(life)) == (0.0, False)
    assert cure_sniffles(life) is False
    assert catch_sniffles(life) is True


def test_a_cold_never_kills_him() -> None:
    sniffly = alive(health=1.0, sniffles_left=SNIFFLES_FOR.total_seconds())
    events = run(sniffly, timedelta(days=1))
    assert sniffly.health == 1.0
    assert EventKind.DIED not in kinds(events)
    assert sniffly.phase is Phase.ALIVE


# ---
# Freezing pauses his age
# ---


def test_frozen_days_do_not_age_him() -> None:
    life = alive(health=HEALTH_MAX, at=T0 - timedelta(days=5), last_tick_at=T0)
    run(life, timedelta(days=7), step=timedelta(hours=1), frozen=True)
    end = T0 + timedelta(days=7)
    assert life.frozen_seconds == timedelta(days=7).total_seconds()
    assert age_days(life, end) == 5
    assert own_time(life, end) == T0


def test_an_old_fogey_frozen_over_his_farewell_day_waits_it_out() -> None:
    life = old(Stage.OLD_FOGEY, FAREWELL_AT_DAY - 5, last_tick_at=T0)
    assert run(life, timedelta(days=7), step=timedelta(hours=1), frozen=True) == []
    after_freeze = run(life, timedelta(days=1), fed=True, cared=True)
    assert EventKind.FAREWELL not in kinds(after_freeze)
    assert life.phase is Phase.ALIVE
    later = life.last_tick_at + timedelta(days=4)
    assert tick(life, later, frozen=False, caretakers=0, people=0) == [
        Event(EventKind.FAREWELL)
    ]


def test_a_frozen_baby_does_not_grow_up_by_his_day() -> None:
    by_day = STAGE_RULES[Stage.CHILD].by_day
    life = alive(health=HEALTH_MAX, at=T0 - timedelta(days=by_day - 1), last_tick_at=T0)
    run(life, timedelta(days=3), step=timedelta(hours=1), frozen=True)
    run(life, timedelta(hours=1), fed=True, cared=True)
    assert life.stage is Stage.BABY


def test_monster_pox_waits_out_a_freeze() -> None:
    life = alive(health=HEALTH_MAX, cold_due_at=T0 + timedelta(days=1), last_tick_at=T0)
    run(life, timedelta(days=3), step=timedelta(hours=1), frozen=True)
    assert EventKind.SICK not in kinds(run(life, timedelta(hours=12)))
    assert not is_sick(life)
    assert EventKind.SICK in kinds(run(life, timedelta(hours=13)))


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING])
def test_freezing_an_egg_adds_no_frozen_time(phase: Phase) -> None:
    egg = new_egg(1, T0)
    egg.phase = phase
    tick(egg, T0 + timedelta(days=2), frozen=True, caretakers=0, people=0)
    assert egg.frozen_seconds == 0.0


def test_an_unfrozen_tick_adds_no_frozen_time() -> None:
    life = alive(health=HEALTH_MAX, last_tick_at=T0)
    run(life, timedelta(days=1), fed=True, cared=True)
    assert life.frozen_seconds == 0.0


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
    life = alive(health=HEALTH_MAX, last_tick_at=T0, had_cold=True)
    assert jump_to(life, stage, T0, random.Random(1)) == Event(kind, stage)
    assert (life.stage, life.stage_started_at) == (stage, T0)
    assert run(life, timedelta(days=2), fed=True, cared=True, people=1) == []
    assert life.stage is stage


def test_a_jump_forgets_frozen_time() -> None:
    life = alive(health=HEALTH_MAX, frozen_seconds=timedelta(days=3).total_seconds())
    jump_to(life, Stage.TEEN, T0, random.Random(1))
    assert life.frozen_seconds == 0.0
    assert age_days(life, T0) == STAGE_RULES[Stage.TEEN].by_day


def test_a_jump_back_to_baby_is_not_announced() -> None:
    life = alive(health=HEALTH_MAX, stage=Stage.TEEN, last_tick_at=T0)
    assert jump_to(life, Stage.BABY, T0, random.Random(1)) is None
    assert (life.stage, life.peak_stage, life.hatched_at) == (
        Stage.BABY,
        Stage.BABY,
        T0,
    )


def test_an_old_fogey_jumped_to_counts_as_a_grown_up() -> None:
    young = alive(health=HEALTH_MAX, stage=Stage.CHILD)
    jump_to(young, Stage.OLD_FOGEY, T0, random.Random(1))
    assert young.peak_stage is Stage.ADULT
    star = alive(health=HEALTH_MAX, stage=Stage.ROCKSTAR)
    jump_to(star, Stage.OLD_FOGEY, T0, random.Random(1))
    assert star.peak_stage is Stage.ROCKSTAR


def test_ready_to_pass_on_says_farewell_on_the_next_tick() -> None:
    life = alive(health=HEALTH_MAX, stage=Stage.CHILD, last_tick_at=T0)
    ready_to_pass_on(life, T0, random.Random(1))
    assert tick(life, T0, frozen=False, caretakers=0, people=0) == [
        Event(EventKind.FAREWELL)
    ]
    assert life.phase is Phase.PASSED


@pytest.mark.parametrize(
    ("phase", "ended"),
    [
        (Phase.EGG, Phase.COLD),
        (Phase.HATCHING, Phase.COLD),
        (Phase.ALIVE, Phase.DEAD),
    ],
)
def test_cut_short_ends_a_life_at_once(phase: Phase, ended: Phase) -> None:
    life = alive(phase=phase, phase_seconds=60.0)
    cut_short(life, T0 + SIX_HOURS)
    assert (life.phase, life.phase_seconds, life.ended_at) == (
        ended,
        0.0,
        T0 + SIX_HOURS,
    )
    assert tick(life, T0 + SIX_HOURS, frozen=False, caretakers=0, people=0) == []


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD, Phase.PASSED])
def test_cut_short_leaves_an_ended_life_as_it_is(phase: Phase) -> None:
    life = alive(phase=phase, ended_at=T0)
    cut_short(life, T0 + SIX_HOURS)
    assert (life.phase, life.ended_at) == (phase, T0)


# ---
# Meter drops
# ---


def drops(events: list[Event]) -> list[Event]:
    return [event for event in events if event.kind is EventKind.METER_DROP]


def test_a_filled_stretch_reports_each_meter_drop_with_its_new_value() -> None:
    events = run(alive(), SIX_HOURS)
    assert drops(events) == [
        Event(EventKind.METER_DROP, meter=Meter.HEALTH, lost=8.0, value=42.0),
        Event(EventKind.METER_DROP, meter=Meter.WELLBEING, lost=10.0, value=40.0),
    ]


def test_a_meter_still_inside_its_stretch_reports_nothing() -> None:
    assert drops(run(alive(), timedelta(hours=5, minutes=55))) == []


def test_only_the_meter_that_ran_dry_is_reported() -> None:
    events = run(alive(), SIX_HOURS, fed=True)
    assert drops(events) == [
        Event(EventKind.METER_DROP, meter=Meter.WELLBEING, lost=10.0, value=40.0)
    ]


def test_the_sick_multiplier_shows_in_the_reported_health_loss() -> None:
    events = run(sick(health=50.0), SIX_HOURS, cared=True)
    assert drops(events) == [
        Event(EventKind.METER_DROP, meter=Meter.HEALTH, lost=12.0, value=38.0)
    ]


def test_the_sick_floor_limits_the_reported_loss() -> None:
    events = run(sick(health=5.0), SIX_HOURS, cared=True)
    assert drops(events) == [
        Event(EventKind.METER_DROP, meter=Meter.HEALTH, lost=4.0, value=1.0)
    ]


def test_a_meter_with_nothing_left_to_lose_reports_no_drop() -> None:
    life = alive(health=1.0, sniffles_left=SNIFFLES_FOR.total_seconds())
    events = run(life, SIX_HOURS, cared=True)
    assert drops(events) == []


def test_frozen_time_reports_no_drop() -> None:
    assert run(alive(), SIX_HOURS, frozen=True) == []


def test_a_life_cut_short_counts_as_testing() -> None:
    life = new_egg(1, T0)

    cut_short(life, T0 + SIX_HOURS)

    assert life.is_test
