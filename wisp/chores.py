"""Wisp's chores: messes, tantrums and naps.

Pure game logic. Nothing here touches the database, Discord or the clock;
callers pass the current time (timezone-aware UTC) and their rng. Deadlines
run on counted time, like his meters; only the nap start times are wall-clock,
set on the NAP_TIMEZONE clock and worked with as UTC moments.
"""

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum, auto
from zoneinfo import ZoneInfo

from wisp.life import Life, Meter, Phase, catch_sniffles, change_meter, end_stretch
from wisp.rules import (
    CRANKY_FOR,
    HEALTH_PER_CLEANUP,
    LIGHTS_WELLBEING_PENALTY,
    LIGHTS_WINDOW,
    MAX_CREDITED_GAP,
    MESS_DELAY_MAX,
    MESS_DELAY_MIN,
    MESS_GAP,
    MESS_LEFT_FOR,
    NAP_FOR,
    NAP_LOCAL_HOURS,
    NAP_TIMEZONE,
    TANTRUM_WELLBEING_PENALTY,
    TANTRUM_WINDOW,
    TICK_EVERY,
    Chore,
)

_MICROSECOND = timedelta(microseconds=1)
_QUIET_BEFORE_NAP = TANTRUM_WINDOW + TICK_EVERY
_NAP_ZONE = ZoneInfo(NAP_TIMEZONE)

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
    """Close an open chore; a cleanup also fills Health and ends the Wellbeing stretch.

    Returns False, and changes nothing, when the chore was not open.
    """
    if not is_open(life, chore):
        return False
    match chore:
        case Chore.MESS:
            life.mess_left = 0.0
            change_meter(life, Meter.HEALTH, HEALTH_PER_CLEANUP)
            end_stretch(life, Meter.WELLBEING)
        case Chore.TANTRUM:
            life.tantrum_left = 0.0
        case Chore.NAP:
            life.lights_left = 0.0
    return True


def drop_chore(life: Life, chore: Chore) -> bool:
    """Close `chore` when it is open with no post, as if it never came.

    Nobody could press a chore that has no post, so it costs him nothing, and
    a dropped mess does not hold the next one back. Returns whether it was
    dropped.
    """
    if not is_open(life, chore) or message_id(life, chore) is not None:
        return False
    match chore:
        case Chore.MESS:
            life.mess_left = 0.0
            life.mess_gap = 0.0
        case Chore.TANTRUM:
            life.tantrum_left = 0.0
        case Chore.NAP:
            life.lights_left = 0.0
    return True


def wake(life: Life, now: datetime) -> bool:
    """End his nap at once and leave him cranky, with no Wellbeing penalty.

    He stays cranky for at least CRANKY_FOR, longer when missed lights already
    made him so. Returns whether the lights were still on.
    """
    lights_were_on = is_open(life, Chore.NAP)
    life.nap_left = 0.0
    life.lights_left = 0.0
    life.cranky_until = max(life.cranky_until or now, now + CRANKY_FOR)
    return lights_were_on


# ---
# When naps and tantrums happen
# ---


def _midnight(moment: datetime) -> datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def latest_nap_start(now: datetime) -> datetime:
    """The latest nap start at or before `now`."""
    return max(start for start in _nap_starts(_midnight(now)) if start <= now)


def next_nap_start(now: datetime) -> datetime:
    """When his next nap starts after `now`; at a nap's start, the one after."""
    return min(start for start in _nap_starts(_midnight(now)) if start > now)


def nap_starts_on(day: date) -> list[datetime]:
    """His nap starts of `day` on the NAP_TIMEZONE clock, in order, as UTC moments.

    As timestamps they show members the nap times of day in their own time
    zone, right for the daylight saving of `day`.
    """
    return [_on_nap_clock(day, hour) for hour in sorted(NAP_LOCAL_HOURS)]


def _on_nap_clock(day: date, hour: int) -> datetime:
    """`hour` o'clock on `day` on the NAP_TIMEZONE clock, as a UTC moment."""
    return datetime.combine(day, time(hour), _NAP_ZONE).astimezone(UTC)


def nap_ends_at(life: Life, now: datetime) -> datetime:
    """When his nap ends if nothing pauses it, rounded up to the minute.

    His nap counts down on counted time, so it is `now` plus what is left.
    """
    end = now + timedelta(seconds=life.nap_left)
    whole = end.replace(second=0, microsecond=0)
    return whole if whole == end else whole + timedelta(minutes=1)


def _nap_starts_on(day: datetime) -> list[datetime]:
    """Every nap start inside the UTC day from `day`, in order.

    The starts are NAP_LOCAL_HOURS on the NAP_TIMEZONE clock, so they move in
    UTC when daylight saving starts and ends. A UTC day holds starts of two
    local days, and each start falls inside exactly one UTC day.
    """
    end = day + timedelta(days=1)
    starts = (
        _on_nap_clock(day.date() + timedelta(days=offset), hour)
        for offset in (-1, 0, 1)
        for hour in NAP_LOCAL_HOURS
    )
    return sorted(start for start in starts if day <= start < end)


def _nap_starts(day: datetime) -> list[datetime]:
    """Every nap start of the UTC day from `day`, the day before and the day after."""
    return [
        start
        for offset in (-1, 0, 1)
        for start in _nap_starts_on(day + timedelta(days=offset))
    ]


def _awake_windows(day: datetime) -> list[tuple[datetime, datetime]]:
    """The UTC day from `day`, minus every nap and the quiet time before it.

    The quiet time, _QUIET_BEFORE_NAP, is TANTRUM_WINDOW plus TICK_EVERY: a
    tantrum opens on the first tick at or after its due time, up to TICK_EVERY
    late, and must still close before the nap's first tick. Naps starting the
    day before and the day after count too, clipped to the day.
    """
    end_of_day = day + timedelta(days=1)
    busy = sorted(
        (start - _QUIET_BEFORE_NAP, start + NAP_FOR) for start in _nap_starts(day)
    )
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


def _is_awake(now: datetime) -> bool:
    """Whether `now` is in one of its UTC day's awake windows."""
    return any(begin <= now < end for begin, end in _awake_windows(_midnight(now)))


def _is_nap_coming(now: datetime) -> bool:
    """Whether `now` is in the quiet time just before a nap starts."""
    return any(
        start - _QUIET_BEFORE_NAP <= now < start
        for start in _nap_starts(_midnight(now))
    )


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
    before this tick, is skipped. No nap starts over an open tantrum. A due
    tantrum opens only while he is awake and outside a nap's time; one due
    during a nap waits for its end, and one that comes due in the quiet time
    before a nap (after an outage) is rolled again for after it.
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
    if due <= now and not is_napping(life) and not is_open(life, Chore.TANTRUM):
        if _is_awake(now):
            events.append(open_tantrum(life))
            life.tantrum_due_at = next_tantrum(_midnight(now) + timedelta(days=1), rng)
        elif _is_nap_coming(now):
            life.tantrum_due_at = next_tantrum(now, rng)
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
    change_meter(life, Meter.WELLBEING, -TANTRUM_WELLBEING_PENALTY)
    life.spoiled_until = _midnight(now) + timedelta(days=1)
    return [ChoreEvent(ChoreEventKind.TANTRUM_MISSED, life.tantrum_message_id)]


def _tick_nap(life: Life, now: datetime, seconds: float) -> list[ChoreEvent]:
    """Count down his nap and its lights window, which closes by the nap's end.

    Posted lights nobody turned off cost Wellbeing and leave him cranky for
    CRANKY_FOR after the rest of the nap.
    """
    if not is_napping(life):
        return []
    life.nap_left = max(life.nap_left - seconds, 0.0)
    if not is_open(life, Chore.NAP):
        return []
    life.lights_left = min(max(life.lights_left - seconds, 0.0), life.nap_left)
    if is_open(life, Chore.NAP) or life.nap_message_id is None:
        return []
    change_meter(life, Meter.WELLBEING, -LIGHTS_WELLBEING_PENALTY)
    life.cranky_until = now + timedelta(seconds=life.nap_left) + CRANKY_FOR
    return [ChoreEvent(ChoreEventKind.LIGHTS_MISSED, life.nap_message_id)]
