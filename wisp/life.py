"""Wisp's life: eggs, hatching, care, stages and death.

Pure game logic. Nothing here touches the database, Discord or the clock;
callers pass the current time (timezone-aware UTC) into every call.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum, auto

from wisp.rules import (
    CARE_DRAIN_PER_DAY,
    CARE_MAX,
    EGG_FOOD_NEEDED,
    EGG_WARMTH,
    FADING_BELOW,
    HANGRY_BELOW,
    HATCHED_CARE,
    HATCHING_TIME,
    MAX_CREDITED_GAP,
    ROCKSTAR_HAPPINESS,
    ROCKSTAR_HAPPY_FOR,
    STAGE_RULES,
    Stage,
)

_DAY_SECONDS = timedelta(days=1).total_seconds()
_STAGES = tuple(Stage)

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


class Mood(StrEnum):
    """How Wisp feels about his care."""

    HAPPY = auto()
    HANGRY = auto()


class EventKind(StrEnum):
    """Things that happen to a life and are worth announcing."""

    HUNGRY = auto()
    FADING = auto()
    DIED = auto()
    EGG_COLD = auto()
    HATCH_STARTED = auto()
    HATCHED = auto()
    STAGE_UP = auto()


@dataclass(frozen=True)
class Event:
    """Something that happened during a tick or a feed."""

    kind: EventKind
    stage: Stage | None = None


@dataclass
class Life:
    """One Wisp, from egg to its end. Mirrors a row of the lives table."""

    id: int | None
    version: int
    phase: Phase
    stage: Stage
    care: float
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
    high_happiness_since: datetime | None = None
    warned: EventKind | None = None
    hatched_by: int | None = None


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
        care=0.0,
        egg_food=0,
        growth=0,
        laid_at=now,
        last_tick_at=now,
        peak_stage=Stage.EGG,
    )


def is_over(life: Life) -> bool:
    """Whether this life has ended, by death or a cold egg."""
    return life.phase in (Phase.DEAD, Phase.COLD)


def mood(life: Life) -> Mood:
    """Hangry while a living Wisp's care is below the hangry line."""
    if life.phase is Phase.ALIVE and life.care < HANGRY_BELOW:
        return Mood.HANGRY
    return Mood.HAPPY


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
        life.care = min(life.care + meal_points, CARE_MAX)
        if life.care >= HANGRY_BELOW:
            life.warned = None
        elif life.care >= FADING_BELOW and life.warned is EventKind.FADING:
            life.warned = EventKind.HUNGRY
    return []


def add_growth(life: Life, points: int) -> None:
    """Add growth points; they only count while Wisp is alive."""
    if life.phase is Phase.ALIVE:
        life.growth += points


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
# Ticking time
# ---


def tick(
    life: Life, now: datetime, *, frozen: bool, happiness: int, caretakers: int
) -> list[Event]:
    """Advance a life to `now`, crediting at most MAX_CREDITED_GAP of time."""
    if is_over(life):
        return []
    gap = now - life.last_tick_at
    elapsed = timedelta(0) if frozen else max(min(gap, MAX_CREDITED_GAP), timedelta(0))
    if life.high_happiness_since is not None:
        life.high_happiness_since += max(gap - elapsed, timedelta(0))
    life.last_tick_at = now
    if frozen:
        return []
    life.phase_seconds += elapsed.total_seconds()
    if life.phase is Phase.EGG:
        return _tick_egg(life, now)
    if life.phase is Phase.HATCHING:
        return _tick_hatching(life, now)
    return _tick_alive(life, now, elapsed, happiness, caretakers)


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
    life.care = HATCHED_CARE
    life.hatched_at = life.stage_started_at = now
    return [Event(EventKind.HATCHED)]


def _tick_alive(
    life: Life,
    now: datetime,
    elapsed: timedelta,
    happiness: int,
    caretakers: int,
) -> list[Event]:
    life.care = max(
        life.care - CARE_DRAIN_PER_DAY * elapsed.total_seconds() / _DAY_SECONDS, 0.0
    )
    if life.care == 0:
        _enter(life, Phase.DEAD)
        life.ended_at = now
        return [Event(EventKind.DIED)]
    events = _warnings(life)
    next_stage = _next_stage(life.stage)
    if next_stage and _ready_for(life, next_stage, now, happiness, caretakers):
        life.stage = life.peak_stage = next_stage
        life.stage_started_at = now
        events.append(Event(EventKind.STAGE_UP, next_stage))
    return events


def _warnings(life: Life) -> list[Event]:
    events: list[Event] = []
    if life.care < HANGRY_BELOW and life.warned is None:
        life.warned = EventKind.HUNGRY
        events.append(Event(EventKind.HUNGRY))
    if life.care < FADING_BELOW and life.warned is not EventKind.FADING:
        life.warned = EventKind.FADING
        events.append(Event(EventKind.FADING))
    return events


# ---
# Stages
# ---


def _next_stage(stage: Stage) -> Stage | None:
    index = _STAGES.index(stage) + 1
    return _STAGES[index] if index < len(_STAGES) else None


def _ready_for(
    life: Life, stage: Stage, now: datetime, happiness: int, caretakers: int
) -> bool:
    if stage is Stage.ROCKSTAR:
        return _kept_happy_long_enough(life, now, happiness)
    min_age, min_growth, min_caretakers = STAGE_RULES[stage]
    return (
        age_days(life, now) >= min_age
        and life.growth >= min_growth
        and caretakers >= min_caretakers
    )


def _kept_happy_long_enough(life: Life, now: datetime, happiness: int) -> bool:
    """Track the happiness streak and report whether it has lasted long enough."""
    if happiness < ROCKSTAR_HAPPINESS:
        life.high_happiness_since = None
        return False
    if life.high_happiness_since is None:
        life.high_happiness_since = now
    return now - life.high_happiness_since >= ROCKSTAR_HAPPY_FOR
