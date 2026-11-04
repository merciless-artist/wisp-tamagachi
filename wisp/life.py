"""Wisp's life: eggs, hatching, health, wellbeing, his cold, stages and death.

Pure game logic. Nothing here touches the database, Discord or the clock;
callers pass the current time (timezone-aware UTC) into every call, and the
one random roll, when his cold is due, takes the caller's rng.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum, auto

from wisp.rules import (
    CARE_DRAIN_PER_DAY,
    COAL_EGG_FOOD,
    COLD_EARLIEST,
    COLD_LATEST,
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    FADING_BELOW,
    FAREWELL_AT_DAY,
    FULL_DRAIN_PER_DAY,
    HANGRY_BELOW,
    HATCHING_TIME,
    HEALTH_MAX,
    HEALTH_START,
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
    WELLBEING_MAX,
    WELLBEING_START,
    Stage,
)

_DAY_SECONDS = timedelta(days=1).total_seconds()
_NEXT_STAGE = {
    Stage.BABY: Stage.CHILD,
    Stage.CHILD: Stage.TEEN,
    Stage.TEEN: Stage.ADULT,
}
_COLD_STAGES = frozenset({Stage.BABY, Stage.CHILD, Stage.TEEN})

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


@dataclass(frozen=True)
class Event:
    """Something that happened during a tick or a feed."""

    kind: EventKind
    stage: Stage | None = None


@dataclass
class Life:
    """One Wisp, from egg to its end. Mirrors a row of the lives table.

    `favorite_snack` is the key of the snack he loves most, chosen when he
    hatches; None while he is an egg. `wellbeing` is the wellbeing meter, filled by
    duels and gifts, and `lonely_warned` whether he has said he is lonely
    since it last dropped below the lonely line.

    His one childhood cold is due at `cold_due_at` (None until it is rolled),
    `cold_left` is the credited seconds of it still to go, and `had_cold`
    whether he has caught it, so he never catches it twice.
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
    """Whether he has his cold right now."""
    return life.cold_left > 0


def age_days(life: Life, now: datetime) -> int:
    """Whole days since hatching; zero for a Wisp that has not hatched."""
    if life.hatched_at is None:
        return 0
    return (now - life.hatched_at).days


# ---
# Feeding and growth
# ---


def feed(life: Life, meal_points: int, feeder_id: int, now: datetime) -> list[Event]:
    """Feed an egg or a living Wisp; ignored in every other phase."""
    if life.phase is Phase.EGG:
        return _feed_egg(life, meal_points, feeder_id, now)
    if life.phase is Phase.ALIVE:
        life.health = min(life.health + meal_points, HEALTH_MAX)
        if life.health >= HANGRY_BELOW:
            life.warned = None
        elif life.health >= FADING_BELOW and life.warned is EventKind.FADING:
            life.warned = EventKind.HUNGRY
    return []


def add_growth(life: Life, points: int) -> None:
    """Add growth points; they only count while Wisp is alive."""
    if life.phase is Phase.ALIVE:
        life.growth += points


def add_care(life: Life, points: float) -> None:
    """Add wellbeing, up to WELLBEING_MAX; it only counts while Wisp is alive.

    Back at or above the lonely line, his next drop below it is announced.
    """
    if life.phase is not Phase.ALIVE:
        return
    life.wellbeing = min(life.wellbeing + points, WELLBEING_MAX)
    if life.wellbeing >= LONELY_BELOW:
        life.lonely_warned = False


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

    Only a living Baby, Child or Teen who has not had his cold gets one, due
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
    offset = rng.uniform(COLD_EARLIEST.total_seconds(), COLD_LATEST.total_seconds())
    life.cold_due_at = life.hatched_at + timedelta(seconds=offset)


def _catch_due_cold(life: Life, now: datetime) -> list[Event]:
    if life.had_cold or life.cold_due_at is None or now < life.cold_due_at:
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
# Ticking time
# ---


def tick(
    life: Life,
    now: datetime,
    *,
    frozen: bool,
    happiness: int,
    caretakers: int,
    people: int,
) -> list[Event]:
    """Advance a life to `now`, crediting at most MAX_CREDITED_GAP of time.

    `caretakers` cared for him this stage; `people` is how many he saw in the
    last PEOPLE_WINDOW, which sets how many caretakers growing up takes.
    """
    if is_over(life):
        return []
    gap = now - life.last_tick_at
    elapsed = timedelta(0) if frozen else max(min(gap, MAX_CREDITED_GAP), timedelta(0))
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
    return _tick_alive(life, now, elapsed, happiness, caretakers, people)


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
    life.hatched_at = life.stage_started_at = now
    return [Event(EventKind.HATCHED)]


def _tick_alive(
    life: Life,
    now: datetime,
    elapsed: timedelta,
    happiness: int,
    caretakers: int,
    people: int,
) -> list[Event]:
    """Advance a living Wisp; a due cold starts before anything else happens.

    While sick he drains faster, but the drain never takes his Full below
    SICK_FULL_FLOOR, so the cold cannot kill him.
    """
    events = _catch_due_cold(life, now)
    days = elapsed.total_seconds() / _DAY_SECONDS
    _drain_full(life, days)
    life.wellbeing = max(life.wellbeing - CARE_DRAIN_PER_DAY * days, 0.0)
    if life.health == 0:
        _enter(life, Phase.DEAD)
        life.ended_at = now
        return [Event(EventKind.DIED)]
    if life.stage is Stage.OLD_FOGEY and age_days(life, now) >= FAREWELL_AT_DAY:
        _enter(life, Phase.PASSED)
        life.ended_at = now
        return [Event(EventKind.FAREWELL)]
    events += _count_down_cold(life, elapsed)
    events += _warnings(life)
    events += _grow(life, now, happiness, caretakers, people)
    return events


def _drain_full(life: Life, days: float) -> None:
    drain = (
        OLD_FOGEY_FULL_DRAIN_PER_DAY
        if life.stage is Stage.OLD_FOGEY
        else FULL_DRAIN_PER_DAY
    )
    floor = 0.0
    if is_sick(life):
        drain *= SICK_DRAIN_MULTIPLIER
        floor = min(life.health, SICK_FULL_FLOOR)
    life.health = max(life.health - drain * days, floor)


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


def _grow(
    life: Life, now: datetime, happiness: int, caretakers: int, people: int
) -> list[Event]:
    """Move a living Wisp up one stage, or into old age, when it is time."""
    stage = life.stage
    if (
        stage in (Stage.ADULT, Stage.ROCKSTAR)
        and age_days(life, now) >= OLD_FOGEY_AT_DAY
    ):
        life.high_mood_since = None
        return [_advance(life, Stage.OLD_FOGEY, now, keep_peak=True)]
    if stage is Stage.ADULT:
        if _kept_happy_long_enough(life, now, happiness):
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


def _kept_happy_long_enough(life: Life, now: datetime, happiness: int) -> bool:
    """Track the happiness streak and report whether it has lasted long enough."""
    if happiness < ROCKSTAR_HAPPINESS:
        life.high_mood_since = None
        return False
    if life.high_mood_since is None:
        life.high_mood_since = now
    return now - life.high_mood_since >= ROCKSTAR_HAPPY_FOR


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


def jump_to(life: Life, stage: Stage, now: datetime) -> Event | None:
    """Put a living Wisp straight into `stage`, for staff testing it.

    His age is set to match, so he stays in the stage until he grows out of
    it on his own. An Old Fogey jumped to from a young stage is counted as
    having been an Adult. Returns the event to announce; a Baby has none.
    """
    life.hatched_at = now - timedelta(days=_jump_age(stage))
    life.high_mood_since = None
    keep_peak = stage is Stage.OLD_FOGEY
    if keep_peak and life.peak_stage not in (Stage.ADULT, Stage.ROCKSTAR):
        life.peak_stage = Stage.ADULT
    event = _advance(life, stage, now, keep_peak=keep_peak)
    return None if stage is Stage.BABY else event


def ready_to_pass_on(life: Life, now: datetime) -> None:
    """Make a living Wisp an Old Fogey on his farewell day; his next tick ends it."""
    jump_to(life, Stage.OLD_FOGEY, now)
    life.hatched_at = now - timedelta(days=FAREWELL_AT_DAY)


def starve(life: Life) -> None:
    """Empty a living Wisp's health; his next tick, even a sick one, ends his life."""
    life.health = 0.0
