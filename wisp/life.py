"""Wisp's life: eggs, hatching, his meters, Monster Pox, a cold, stages and death.

Pure game logic. Nothing here touches the database, Discord or the clock;
callers pass the current time (timezone-aware UTC) into every call, and the
one random roll, when Monster Pox is due, takes the caller's rng.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum, auto

from wisp.rules import (
    COAL_EGG_FOOD,
    COLD_EARLIEST,
    COLD_LATEST,
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    FADING_BELOW,
    FAREWELL_AT_DAY,
    HANGRY_BELOW,
    HATCHING_TIME,
    HEALTH_MAX,
    HEALTH_PENALTY,
    HEALTH_START,
    HEALTH_STRETCH,
    LONELY_BELOW,
    MAX_CREDITED_GAP,
    OLD_FOGEY_AT_DAY,
    OLD_FOGEY_HEALTH_PENALTY,
    ROCKSTAR_WELLBEING,
    ROCKSTAR_WELLBEING_FOR,
    SICK_DRAIN_MULTIPLIER,
    SICK_FOR,
    SICK_FULL_FLOOR,
    SNIFFLES_FOR,
    STAGE_MIN_TIME,
    STAGE_RULES,
    WELLBEING_MAX,
    WELLBEING_PENALTY,
    WELLBEING_START,
    WELLBEING_STRETCH,
    Stage,
)

_NEXT_STAGE = {
    Stage.BABY: Stage.CHILD,
    Stage.CHILD: Stage.TEEN,
    Stage.TEEN: Stage.ADULT,
}
_COLD_STAGES = frozenset({Stage.BABY, Stage.CHILD})

# ---
# Types
# ---


class Phase(StrEnum):
    """Where a life is in its story."""

    EGG = auto()
    HATCHING = auto()
    ALIVE = auto()
    DEAD = auto()
    COLD = auto()
    PASSED = auto()


class Mood(StrEnum):
    """How Wisp feels about his health and his wellbeing."""

    HAPPY = auto()
    HANGRY = auto()
    LONELY = auto()


class Sickness(StrEnum):
    """What he is sick with: Monster Pox or a cold."""

    POX = auto()
    COLD = auto()


class Meter(StrEnum):
    """The two meters members fill: Health, his body, and Wellbeing, his heart."""

    HEALTH = auto()
    WELLBEING = auto()


class EventKind(StrEnum):
    """Things that happen to a life and are worth announcing."""

    HUNGRY = auto()
    FADING = auto()
    DIED = auto()
    EGG_COLD = auto()
    HATCH_STARTED = auto()
    HATCHED = auto()
    STAGE_UP = auto()
    GREW_OLD = auto()
    FAREWELL = auto()
    LONELY = auto()
    SICK = auto()
    RECOVERED = auto()
    METER_DROP = auto()


@dataclass(frozen=True)
class Event:
    """Something that happened during a tick or a feed.

    A METER_DROP names the `meter` that paid for a filled stretch, how much it
    `lost` (what really came off, after Monster Pox, a cold and the sick
    floor) and its new `value`.
    """

    kind: EventKind
    stage: Stage | None = None
    meter: Meter | None = None
    lost: float = 0.0
    value: float = 0.0


@dataclass
class Life:
    """One Wisp, from egg to its end. Mirrors a row of the lives table.

    `favorite_snack` is the key of the snack he loves most, chosen when he
    hatches; None while he is an egg. `wellbeing` is the Wellbeing meter, and
    `lonely_warned` whether he has said he is lonely since it last dropped
    below the lonely line. `high_mood_since` is when an Adult's Wellbeing
    reached the Rockstar line and has stayed there since; otherwise None.

    His one childhood cold is due at `cold_due_at` (None until it is rolled),
    `cold_left` is the credited seconds of it still to go, and `had_cold`
    whether he has caught it, so he never catches it twice.

    `frozen_seconds` is how long he has been frozen since he hatched. His age
    leaves it out, so his stage days, old age, farewell and Monster Pox all
    wait out a freeze (see `own_time`).

    `health_stretch` and `wellbeing_stretch` are the counted seconds each meter
    has spent in its current stretch, and `sniffles_left` the counted seconds
    of his cold still to go.

    The mess: `mess_in` counts down to the next one, `mess_left` and `mess_gap`
    are counted seconds, and `mess_message_id` is the post that shows it.

    The tantrum is due at `tantrum_due_at`, `tantrum_left` is its counted
    seconds still to go and `tantrum_message_id` the post that shows it. He is
    spoiled until `spoiled_until`.

    The nap starts at `nap_slot`; `nap_left` and `lights_left` are counted
    seconds, `nap_message_id` the post that shows it, and he is cranky until
    `cranky_until`.
    """

    id: int | None
    version: int
    phase: Phase
    stage: Stage
    health: float
    egg_food: int
    growth: int
    laid_at: datetime
    last_tick_at: datetime
    peak_stage: Stage
    phase_seconds: float = 0.0
    hatch_started_at: datetime | None = None
    hatched_at: datetime | None = None
    stage_started_at: datetime | None = None
    ended_at: datetime | None = None
    high_mood_since: datetime | None = None
    warned: EventKind | None = None
    hatched_by: int | None = None
    from_coal: bool = False
    favorite_snack: str | None = None
    wellbeing: float = WELLBEING_START
    lonely_warned: bool = False
    cold_due_at: datetime | None = None
    cold_left: float = 0.0
    had_cold: bool = False
    health_stretch: float = 0.0
    wellbeing_stretch: float = 0.0
    sniffles_left: float = 0.0
    mess_in: float = 0.0
    mess_left: float = 0.0
    mess_gap: float = 0.0
    mess_message_id: int | None = None
    tantrum_due_at: datetime | None = None
    tantrum_left: float = 0.0
    tantrum_message_id: int | None = None
    spoiled_until: datetime | None = None
    nap_slot: datetime | None = None
    nap_left: float = 0.0
    lights_left: float = 0.0
    nap_message_id: int | None = None
    cranky_until: datetime | None = None
    frozen_seconds: float = 0.0


# ---
# Creation and queries
# ---


def new_egg(version: int, now: datetime) -> Life:
    """Lay a fresh egg."""
    return Life(
        id=None,
        version=version,
        phase=Phase.EGG,
        stage=Stage.EGG,
        health=0.0,
        egg_food=0,
        growth=0,
        laid_at=now,
        last_tick_at=now,
        peak_stage=Stage.EGG,
    )


def egg_after(ended: Life | None, version: int, now: datetime) -> Life:
    """Lay the egg that follows `ended`: coal after a full life, else a fresh one."""
    egg = new_egg(version, now)
    if ended is not None and ended.phase is Phase.PASSED:
        egg.from_coal = True
        egg.egg_food = COAL_EGG_FOOD
    return egg


def is_over(life: Life) -> bool:
    """Whether this life has ended: died, a cold egg, or a full life passed."""
    return life.phase in (Phase.DEAD, Phase.COLD, Phase.PASSED)


def mood(life: Life) -> Mood:
    """How a living Wisp feels; anything else is happy.

    Hangry while his health is below the hangry line, else lonely while
    his wellbeing is below the lonely line.
    """
    if life.phase is not Phase.ALIVE:
        return Mood.HAPPY
    if life.health < HANGRY_BELOW:
        return Mood.HANGRY
    if life.wellbeing < LONELY_BELOW:
        return Mood.LONELY
    return Mood.HAPPY


def is_sick(life: Life) -> bool:
    """Whether he has Monster Pox right now."""
    return life.cold_left > 0


def has_sniffles(life: Life) -> bool:
    """Whether he has a cold right now."""
    return life.sniffles_left > 0


def sickness(life: Life) -> Sickness | None:
    """What he is sick with right now, or None; Monster Pox wins over a cold."""
    if is_sick(life):
        return Sickness.POX
    if has_sniffles(life):
        return Sickness.COLD
    return None


def hours_left(seconds: float) -> int:
    """Whole hours of a sickness still to go, rounded up, as the status card says."""
    return math.ceil(seconds / timedelta(hours=1).total_seconds())


def own_time(life: Life, now: datetime) -> datetime:
    """`now` on his own clock, which stands still while he is frozen."""
    return now - timedelta(seconds=life.frozen_seconds)


def age_days(life: Life, now: datetime) -> int:
    """Whole days since hatching, frozen time left out; zero before hatching."""
    if life.hatched_at is None:
        return 0
    return (own_time(life, now) - life.hatched_at).days


# ---
# Feeding and growth
# ---


def feed(life: Life, meal_points: int, feeder_id: int, now: datetime) -> list[Event]:
    """Feed an egg or a living Wisp; ignored in every other phase."""
    if life.phase is Phase.EGG:
        return _feed_egg(life, meal_points, feeder_id, now)
    change_meter(life, Meter.HEALTH, meal_points, ends_stretch=True)
    return []


def add_growth(life: Life, points: int) -> None:
    """Add growth points; they only count while Wisp is alive."""
    if life.phase is Phase.ALIVE:
        life.growth += points


def change_meter(
    life: Life, meter: Meter, amount: float, *, ends_stretch: bool = False
) -> None:
    """Move one meter by `amount`, kept between 0 and its max; only while alive.

    `ends_stretch` starts that meter's empty stretch over (see `end_stretch`).
    Health back above a warning line arms that warning again, and Wellbeing
    back at or above the lonely line arms the lonely warning.
    """
    if life.phase is not Phase.ALIVE:
        return
    match meter:
        case Meter.HEALTH:
            life.health = _clamped(life.health + amount, HEALTH_MAX)
            if life.health >= HANGRY_BELOW:
                life.warned = None
            elif life.health >= FADING_BELOW and life.warned is EventKind.FADING:
                life.warned = EventKind.HUNGRY
        case Meter.WELLBEING:
            life.wellbeing = _clamped(life.wellbeing + amount, WELLBEING_MAX)
            if life.wellbeing >= LONELY_BELOW:
                life.lonely_warned = False
    if ends_stretch:
        end_stretch(life, meter)


def end_stretch(life: Life, meter: Meter) -> None:
    """Start one meter's empty stretch over, as a credited action does.

    The meter itself does not move. Only while alive.
    """
    if life.phase is not Phase.ALIVE:
        return
    match meter:
        case Meter.HEALTH:
            life.health_stretch = 0.0
        case Meter.WELLBEING:
            life.wellbeing_stretch = 0.0


def _clamped(value: float, most: float) -> float:
    return min(max(value, 0.0), most)


def _feed_egg(
    life: Life, meal_points: int, feeder_id: int, now: datetime
) -> list[Event]:
    life.egg_food += meal_points
    if life.egg_food < EGG_FOOD_NEEDED:
        return []
    _enter(life, Phase.HATCHING)
    life.hatch_started_at = now
    life.hatched_by = feeder_id
    return [Event(EventKind.HATCH_STARTED)]


# ---
# The childhood cold
# ---


def schedule_cold(life: Life, rng: random.Random) -> None:
    """Roll when a young Wisp's one cold is due, if it is not rolled yet.

    Only a living Baby or Child who has not had his cold gets one, due
    between COLD_EARLIEST and COLD_LATEST after he hatched. A due time already
    past starts the cold on his next tick.
    """
    if (
        life.phase is not Phase.ALIVE
        or life.stage not in _COLD_STAGES
        or life.had_cold
        or life.cold_due_at is not None
        or life.hatched_at is None
    ):
        return
    life.cold_due_at = life.hatched_at + _cold_offset(rng)


def _cold_offset(rng: random.Random) -> timedelta:
    """How long after its start Monster Pox is due: COLD_EARLIEST to COLD_LATEST."""
    offset = rng.uniform(COLD_EARLIEST.total_seconds(), COLD_LATEST.total_seconds())
    return timedelta(seconds=offset)


def _catch_due_cold(life: Life, now: datetime) -> list[Event]:
    """Start Monster Pox once it is due, only for a Baby or Child.

    A due time found at a later stage is cleared, never caught.
    """
    if life.cold_due_at is not None and life.stage not in _COLD_STAGES:
        life.cold_due_at = None
    if (
        life.had_cold
        or life.cold_due_at is None
        or own_time(life, now) < life.cold_due_at
    ):
        return []
    life.had_cold = True
    life.cold_left = SICK_FOR.total_seconds()
    return [Event(EventKind.SICK, stage=life.stage)]


def _count_down_cold(life: Life, elapsed: timedelta) -> list[Event]:
    if not is_sick(life):
        return []
    life.cold_left = max(life.cold_left - elapsed.total_seconds(), 0.0)
    if is_sick(life):
        return []
    return [Event(EventKind.RECOVERED, stage=life.stage)]


# ---
# A cold
# ---


def catch_sniffles(life: Life) -> bool:
    """Give a living Wisp a cold for SNIFFLES_FOR of counted time.

    Returns False, and changes nothing, when he is not alive, already has a
    cold or has Monster Pox.
    """
    if life.phase is not Phase.ALIVE or has_sniffles(life) or is_sick(life):
        return False
    life.sniffles_left = SNIFFLES_FOR.total_seconds()
    return True


def cure_sniffles(life: Life) -> bool:
    """End his cold at once; returns whether he had one."""
    had = has_sniffles(life)
    life.sniffles_left = 0.0
    return had


# ---
# Ticking time
# ---


def credited_gap(life: Life, now: datetime, *, frozen: bool) -> timedelta:
    """How much of the time since his last tick counts.

    None while frozen and none when the clock went backwards; after an outage
    at most MAX_CREDITED_GAP.
    """
    if frozen:
        return timedelta(0)
    return max(min(now - life.last_tick_at, MAX_CREDITED_GAP), timedelta(0))


def tick(
    life: Life, now: datetime, *, frozen: bool, caretakers: int, people: int
) -> list[Event]:
    """Advance a life to `now`, counting only its `credited_gap`.

    `caretakers` cared for him this stage; `people` is how many he saw in the
    last PEOPLE_WINDOW, which sets how many caretakers growing up takes. A
    hatched Wisp who is frozen adds the time to `frozen_seconds`, so his age
    waits.
    """
    if is_over(life):
        return []
    gap = now - life.last_tick_at
    elapsed = credited_gap(life, now, frozen=frozen)
    if frozen and life.phase is Phase.ALIVE:
        life.frozen_seconds += max(gap, timedelta(0)).total_seconds()
    if life.high_mood_since is not None:
        life.high_mood_since += max(gap - elapsed, timedelta(0))
    life.last_tick_at = now
    if frozen:
        return []
    life.phase_seconds += elapsed.total_seconds()
    if life.phase is Phase.EGG:
        return _tick_egg(life, now)
    if life.phase is Phase.HATCHING:
        return _tick_hatching(life, now)
    return _tick_alive(life, now, elapsed, caretakers, people)


def _enter(life: Life, phase: Phase) -> None:
    life.phase = phase
    life.phase_seconds = 0.0


def _tick_egg(life: Life, now: datetime) -> list[Event]:
    if life.phase_seconds < EGG_WARMTH.total_seconds():
        return []
    _enter(life, Phase.COLD)
    life.ended_at = now
    return [Event(EventKind.EGG_COLD)]


def _tick_hatching(life: Life, now: datetime) -> list[Event]:
    if life.phase_seconds < HATCHING_TIME.total_seconds():
        return []
    _enter(life, Phase.ALIVE)
    life.stage = life.peak_stage = Stage.BABY
    life.health = HEALTH_START
    life.wellbeing = WELLBEING_START
    life.health_stretch = life.wellbeing_stretch = 0.0
    life.hatched_at = life.stage_started_at = now
    return [Event(EventKind.HATCHED)]


def _tick_alive(
    life: Life, now: datetime, elapsed: timedelta, caretakers: int, people: int
) -> list[Event]:
    """Advance a living Wisp; due Monster Pox starts before anything else.

    Then each meter pays for an empty stretch that filled up. Monster Pox or
    a cold makes the Health penalty bigger but never takes his Health below
    SICK_FULL_FLOOR, so neither can kill him.
    """
    events = _catch_due_cold(life, now)
    drops = _penalties(life, elapsed.total_seconds())
    if life.health == 0:
        _enter(life, Phase.DEAD)
        life.ended_at = now
        return [Event(EventKind.DIED)]
    if life.stage is Stage.OLD_FOGEY and age_days(life, now) >= FAREWELL_AT_DAY:
        _enter(life, Phase.PASSED)
        life.ended_at = now
        return [Event(EventKind.FAREWELL)]
    events += _count_down_cold(life, elapsed)
    life.sniffles_left = max(life.sniffles_left - elapsed.total_seconds(), 0.0)
    events += _warnings(life)
    events += _grow(life, now, caretakers, people)
    return events + drops


def _penalties(life: Life, seconds: float) -> list[Event]:
    """Add counted time to each meter's empty stretch; a full stretch costs it.

    Returns a METER_DROP for each meter that really lost something.
    """
    drops: list[Event] = []
    life.health_stretch, health_due = _filled(
        life.health_stretch, seconds, HEALTH_STRETCH
    )
    if health_due:
        penalty = HEALTH_PENALTY
        if life.stage is Stage.OLD_FOGEY:
            penalty = OLD_FOGEY_HEALTH_PENALTY
        floor = 0.0
        if sickness(life) is not None:
            penalty *= SICK_DRAIN_MULTIPLIER
            floor = min(life.health, SICK_FULL_FLOOR)
        before = life.health
        life.health = max(life.health - penalty, floor)
        drops += _drop(Meter.HEALTH, before, life.health)
    life.wellbeing_stretch, wellbeing_due = _filled(
        life.wellbeing_stretch, seconds, WELLBEING_STRETCH
    )
    if wellbeing_due:
        before = life.wellbeing
        life.wellbeing = max(life.wellbeing - WELLBEING_PENALTY, 0.0)
        drops += _drop(Meter.WELLBEING, before, life.wellbeing)
    return drops


def _drop(meter: Meter, before: float, after: float) -> list[Event]:
    if after >= before:
        return []
    return [Event(EventKind.METER_DROP, meter=meter, lost=before - after, value=after)]


def _filled(stretch: float, seconds: float, length: timedelta) -> tuple[float, bool]:
    """The stretch `seconds` longer, and whether that filled it.

    A filled stretch starts over with whatever ran past its length.
    """
    stretch += seconds
    if stretch < length.total_seconds():
        return stretch, False
    return stretch - length.total_seconds(), True


def _warnings(life: Life) -> list[Event]:
    events: list[Event] = []
    if life.health < HANGRY_BELOW and life.warned is None:
        life.warned = EventKind.HUNGRY
        events.append(Event(EventKind.HUNGRY))
    if life.health < FADING_BELOW and life.warned is not EventKind.FADING:
        life.warned = EventKind.FADING
        events.append(Event(EventKind.FADING))
    if life.wellbeing < LONELY_BELOW and not life.lonely_warned:
        life.lonely_warned = True
        events.append(Event(EventKind.LONELY, stage=life.stage))
    return events


# ---
# Stages
# ---


def _grow(life: Life, now: datetime, caretakers: int, people: int) -> list[Event]:
    """Move a living Wisp up one stage, or into old age, when it is time."""
    stage = life.stage
    if (
        stage in (Stage.ADULT, Stage.ROCKSTAR)
        and age_days(life, now) >= OLD_FOGEY_AT_DAY
    ):
        life.high_mood_since = None
        return [_advance(life, Stage.OLD_FOGEY, now, keep_peak=True)]
    if stage is Stage.ADULT:
        if _kept_happy_long_enough(life, now):
            return [_advance(life, Stage.ROCKSTAR, now)]
        return []
    next_stage = _NEXT_STAGE.get(stage)
    if next_stage is not None and _ready_for(life, next_stage, now, caretakers, people):
        return [_advance(life, next_stage, now)]
    return []


def _advance(
    life: Life, stage: Stage, now: datetime, *, keep_peak: bool = False
) -> Event:
    life.stage = stage
    if not keep_peak:
        life.peak_stage = stage
    life.stage_started_at = now
    kind = EventKind.GREW_OLD if stage is Stage.OLD_FOGEY else EventKind.STAGE_UP
    return Event(kind, stage)


def caretakers_needed(stage: Stage, people: int) -> int:
    """Caretakers growing into `stage` takes when he saw `people` people lately."""
    return max(math.ceil(people * STAGE_RULES[stage].share), 1)


def _ready_for(
    life: Life, stage: Stage, now: datetime, caretakers: int, people: int
) -> bool:
    """Whether he earned `stage`, or reached the day he grows into it anyway."""
    rule = STAGE_RULES[stage]
    if age_days(life, now) >= rule.by_day:
        return True
    return (
        life.stage_started_at is not None
        and now - life.stage_started_at >= STAGE_MIN_TIME
        and life.growth >= rule.growth
        and caretakers >= caretakers_needed(stage, people)
    )


def _kept_happy_long_enough(life: Life, now: datetime) -> bool:
    """Track the high Wellbeing streak; report whether it has lasted long enough."""
    if life.wellbeing < ROCKSTAR_WELLBEING:
        life.high_mood_since = None
        return False
    if life.high_mood_since is None:
        life.high_mood_since = now
    return now - life.high_mood_since >= ROCKSTAR_WELLBEING_FOR


# ---
# Staff tests
# ---


def _jump_age(stage: Stage) -> int:
    """How many days old a Wisp put straight into `stage` is.

    Old enough for that stage, and short of the day he must grow out of it.
    """
    if stage is Stage.BABY:
        return 0
    if stage is Stage.OLD_FOGEY:
        return OLD_FOGEY_AT_DAY
    if stage is Stage.ROCKSTAR:
        return STAGE_RULES[Stage.ADULT].by_day
    return STAGE_RULES[stage].by_day


def jump_to(
    life: Life, stage: Stage, now: datetime, rng: random.Random
) -> Event | None:
    """Put a living Wisp straight into `stage`, for staff testing it.

    His age is set to match, frozen time forgotten, so he stays in the stage
    until he grows out of it on his own. A Baby or Child who has not had
    Monster Pox has it rolled again from now (never from his new, earlier
    hatch time, which would start it at once); any other stage has no Pox
    due. An Old Fogey jumped to from a young stage is counted as having been
    an Adult. Returns the event to announce; a Baby has none.
    """
    life.hatched_at = now - timedelta(days=_jump_age(stage))
    life.frozen_seconds = 0.0
    life.cold_due_at = None
    if stage in _COLD_STAGES and not life.had_cold:
        start = max(life.hatched_at, own_time(life, now))
        life.cold_due_at = start + _cold_offset(rng)
    life.high_mood_since = None
    keep_peak = stage is Stage.OLD_FOGEY
    if keep_peak and life.peak_stage not in (Stage.ADULT, Stage.ROCKSTAR):
        life.peak_stage = Stage.ADULT
    event = _advance(life, stage, now, keep_peak=keep_peak)
    return None if stage is Stage.BABY else event


def ready_to_pass_on(life: Life, now: datetime, rng: random.Random) -> None:
    """Make a living Wisp an Old Fogey on his farewell day; his next tick ends it."""
    jump_to(life, Stage.OLD_FOGEY, now, rng)
    life.hatched_at = now - timedelta(days=FAREWELL_AT_DAY)


def starve(life: Life) -> None:
    """Empty a living Wisp's health; his next tick, even a sick one, ends his life."""
    life.health = 0.0
