"""Wisp's chores: messes, tantrums and naps.

Pure game logic. Nothing here touches the database, Discord or the clock;
callers pass the current time (timezone-aware UTC) and their rng. Deadlines
run on counted time, like his meters; only the nap start times are wall-clock.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum, auto

from wisp.life import Life, Meter, Phase, catch_sniffles, change_meter
from wisp.rules import (
    CRANKY_FOR,
    LIGHTS_MOOD_PENALTY,
    LIGHTS_WINDOW,
    MAX_CREDITED_GAP,
    MESS_DELAY_MAX,
    MESS_DELAY_MIN,
    MESS_GAP,
    MESS_LEFT_FOR,
    NAP_FOR,
    NAP_HOURS,
    TANTRUM_MOOD_PENALTY,
    TANTRUM_WINDOW,
    WELLBEING_PER_CLEANUP,
    Chore,
)

_MICROSECOND = timedelta(microseconds=1)

# ---
# Types
# ---


class ChoreEventKind(StrEnum):
    """Something a chore did during a tick."""

    MESS = auto()
    MESS_LEFT = auto()
    SNIFFLES = auto()
    TANTRUM = auto()
    TANTRUM_MISSED = auto()
    NAP = auto()
    LIGHTS_MISSED = auto()


@dataclass(frozen=True)
class ChoreEvent:
    """A chore event; `message_id` is the post a left or missed chore edits."""

    kind: ChoreEventKind
    message_id: int | None = None


# ---
# Queries
# ---


def is_open(life: Life, chore: Chore) -> bool:
    """Whether `chore` is waiting for a member; a nap's chore is the lights."""
    match chore:
        case Chore.MESS:
            return life.mess_left > 0
        case Chore.TANTRUM:
            return life.tantrum_left > 0
        case Chore.NAP:
            return life.lights_left > 0


def is_napping(life: Life) -> bool:
    """Whether he is asleep right now."""
    return life.nap_left > 0


def message_id(life: Life, chore: Chore) -> int | None:
    """The House post that shows `chore`, or None before it is posted."""
    match chore:
        case Chore.MESS:
            return life.mess_message_id
        case Chore.TANTRUM:
            return life.tantrum_message_id
        case Chore.NAP:
            return life.nap_message_id


def set_message_id(life: Life, chore: Chore, message_id: int) -> None:
    """Remember the House post that shows `chore`."""
    match chore:
        case Chore.MESS:
            life.mess_message_id = message_id
        case Chore.TANTRUM:
            life.tantrum_message_id = message_id
        case Chore.NAP:
            life.nap_message_id = message_id


# ---
# Opening and doing chores
# ---


def schedule_mess(life: Life, rng: random.Random) -> None:
    """Make a mess due after a fed track, unless one is open, pending or too soon."""
    if life.phase is not Phase.ALIVE:
        return
    if life.mess_in > 0 or life.mess_left > 0 or life.mess_gap > 0:
        return
    life.mess_in = rng.uniform(
        MESS_DELAY_MIN.total_seconds(), MESS_DELAY_MAX.total_seconds()
    )


def open_mess(life: Life) -> ChoreEvent:
    """Leave a mess now, and start the gap before the next one."""
    life.mess_in = 0.0
    life.mess_left = MESS_LEFT_FOR.total_seconds()
    life.mess_gap = MESS_GAP.total_seconds()
    life.mess_message_id = None
    return ChoreEvent(ChoreEventKind.MESS)


def open_tantrum(life: Life) -> ChoreEvent:
    """Throw a tantrum now."""
    life.tantrum_left = TANTRUM_WINDOW.total_seconds()
    life.tantrum_message_id = None
    return ChoreEvent(ChoreEventKind.TANTRUM)


def start_nap(life: Life) -> ChoreEvent:
    """Doze off now, with the lights still on."""
    life.nap_left = NAP_FOR.total_seconds()
    life.lights_left = LIGHTS_WINDOW.total_seconds()
    life.nap_message_id = None
    return ChoreEvent(ChoreEventKind.NAP)


def do_chore(life: Life, chore: Chore) -> bool:
    """Close an open chore; a cleanup also fills Wellbeing.

    Returns False, and changes nothing, when the chore was not open.
    """
    if not is_open(life, chore):
        return False
    match chore:
        case Chore.MESS:
            life.mess_left = 0.0
            change_meter(life, Meter.WELLBEING, WELLBEING_PER_CLEANUP)
        case Chore.TANTRUM:
            life.tantrum_left = 0.0
        case Chore.NAP:
            life.lights_left = 0.0
    return True


def wake(life: Life, now: datetime) -> bool:
    """End his nap at once and leave him cranky, with no Mood penalty.

    Returns whether the lights were still on.
    """
    lights_were_on = is_open(life, Chore.NAP)
    life.nap_left = 0.0
    life.lights_left = 0.0
    life.cranky_until = now + CRANKY_FOR
    return lights_were_on


# ---
# When naps and tantrums happen
# ---


def _midnight(moment: datetime) -> datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def latest_nap_start(now: datetime) -> datetime:
    """The latest of today's and yesterday's nap starts at or before `now`."""
    day = _midnight(now)
    starts = (
        day + timedelta(days=offset, hours=hour)
        for offset in (-1, 0)
        for hour in NAP_HOURS
    )
    return max(start for start in starts if start <= now)


def _awake_windows(day: datetime) -> list[tuple[datetime, datetime]]:
    """The UTC day from `day`, minus every nap and the TANTRUM_WINDOW before it.

    Naps starting the day before and the day after count too, clipped to the day.
    """
    end_of_day = day + timedelta(days=1)
    starts = [
        day + timedelta(days=offset, hours=hour)
        for offset in (-1, 0, 1)
        for hour in NAP_HOURS
    ]
    busy = sorted((start - TANTRUM_WINDOW, start + NAP_FOR) for start in starts)
    windows: list[tuple[datetime, datetime]] = []
    cursor = day
    for begin, end in busy:
        if begin > cursor:
            windows.append((cursor, min(begin, end_of_day)))
        cursor = max(cursor, end)
    if cursor < end_of_day:
        windows.append((cursor, end_of_day))
    return [(begin, end) for begin, end in windows if end > begin]


def next_tantrum(after: datetime, rng: random.Random) -> datetime:
    """A random awake moment of `after`'s UTC day from `after` on.

    When that day has no awake time left, a random awake moment of the next.
    """
    day = _midnight(after)
    windows = [
        (max(begin, after), end) for begin, end in _awake_windows(day) if end > after
    ]
    if not windows:
        windows = _awake_windows(day + timedelta(days=1))
    offset = rng.randrange(sum((end - begin) // _MICROSECOND for begin, end in windows))
    for begin, end in windows:
        length = (end - begin) // _MICROSECOND
        if offset < length:
            break
        offset -= length
    return begin + offset * _MICROSECOND


# ---
# Ticking time
# ---


def tick_chores(
    life: Life,
    now: datetime,
    elapsed: timedelta,
    rng: random.Random,
    *,
    frozen: bool,
) -> list[ChoreEvent]:
    """Advance his chores by `elapsed` of counted time, then start any that are due.

    A nap start that falls while he is frozen, or more than MAX_CREDITED_GAP
    before this tick, is skipped. No nap starts over an open tantrum, and no
    tantrum during a nap; a tantrum due then waits until he wakes.
    """
    if life.phase is not Phase.ALIVE:
        return []
    slot = latest_nap_start(now)
    new_slot = life.nap_slot is None or slot > life.nap_slot
    if new_slot:
        life.nap_slot = slot
    if frozen:
        return []
    seconds = elapsed.total_seconds()
    events = [
        *_tick_mess(life, seconds),
        *_tick_tantrum(life, now, seconds),
        *_tick_nap(life, now, seconds),
    ]
    if (
        new_slot
        and now - slot <= MAX_CREDITED_GAP
        and not is_napping(life)
        and not is_open(life, Chore.TANTRUM)
    ):
        events.append(start_nap(life))
    due = life.tantrum_due_at
    if due is None or due.date() < now.date():
        due = life.tantrum_due_at = next_tantrum(now, rng)
    if not is_napping(life) and not is_open(life, Chore.TANTRUM) and due <= now:
        events.append(open_tantrum(life))
        life.tantrum_due_at = next_tantrum(_midnight(now) + timedelta(days=1), rng)
    return events


def _tick_mess(life: Life, seconds: float) -> list[ChoreEvent]:
    """Count down the gap, then the open mess or the pending one.

    A posted mess left until it runs out gives him a cold, if he can catch one.
    """
    life.mess_gap = max(life.mess_gap - seconds, 0.0)
    if is_open(life, Chore.MESS):
        life.mess_left = max(life.mess_left - seconds, 0.0)
        if is_open(life, Chore.MESS) or life.mess_message_id is None:
            return []
        events = [ChoreEvent(ChoreEventKind.MESS_LEFT, life.mess_message_id)]
        if catch_sniffles(life):
            events.append(ChoreEvent(ChoreEventKind.SNIFFLES))
        return events
    if life.mess_in > 0:
        life.mess_in = max(life.mess_in - seconds, 0.0)
        if life.mess_in == 0:
            return [open_mess(life)]
    return []


def _tick_tantrum(life: Life, now: datetime, seconds: float) -> list[ChoreEvent]:
    """Count down an open tantrum; a posted one nobody scolded spoils him."""
    if not is_open(life, Chore.TANTRUM):
        return []
    life.tantrum_left = max(life.tantrum_left - seconds, 0.0)
    if is_open(life, Chore.TANTRUM) or life.tantrum_message_id is None:
        return []
    change_meter(life, Meter.MOOD, -TANTRUM_MOOD_PENALTY)
    life.spoiled_until = _midnight(now) + timedelta(days=1)
    return [ChoreEvent(ChoreEventKind.TANTRUM_MISSED, life.tantrum_message_id)]


def _tick_nap(life: Life, now: datetime, seconds: float) -> list[ChoreEvent]:
    """Count down his nap and its lights window.

    Posted lights nobody turned off cost Mood and leave him cranky for
    CRANKY_FOR after the rest of the nap.
    """
    if not is_napping(life):
        return []
    life.nap_left = max(life.nap_left - seconds, 0.0)
    if not is_open(life, Chore.NAP):
        return []
    life.lights_left = max(life.lights_left - seconds, 0.0)
    if is_open(life, Chore.NAP) or life.nap_message_id is None:
        return []
    change_meter(life, Meter.MOOD, -LIGHTS_MOOD_PENALTY)
    life.cranky_until = now + timedelta(seconds=life.nap_left) + CRANKY_FOR
    return [ChoreEvent(ChoreEventKind.LIGHTS_MISSED, life.nap_message_id)]
