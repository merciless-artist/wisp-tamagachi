"""Tests for the chores: messes, tantrums and naps, as pure rules."""

import random
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from wisp.chores import (
    ChoreEvent,
    ChoreEventKind,
    do_chore,
    drop_chore,
    is_napping,
    is_open,
    message_id,
    nap_ends_at,
    nap_time_text,
    next_nap_text,
    next_tantrum,
    open_mess,
    open_tantrum,
    schedule_mess,
    set_message_id,
    start_nap,
    tick_chores,
    wake,
)
from wisp.life import Life, Phase, credited_gap, new_egg
from wisp.rules import (
    HEALTH_PER_CLEANUP,
    NAP_LOCAL_HOURS,
    SICK_FOR,
    TANTRUM_WINDOW,
    TICK_EVERY,
    WELLBEING_START,
    Chore,
    Stage,
)

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
DAY = datetime(2026, 11, 2, tzinfo=UTC)
QUIET_BEFORE_NAP = TANTRUM_WINDOW + TICK_EVERY
PACIFIC = ZoneInfo("America/Los_Angeles")
NEVER = T0 + timedelta(days=365)
POST = 77


def alive(at: datetime = T0, **fields: object) -> Life:
    """A living Baby that hatched at `at`, with no nap or tantrum coming.

    Pass `nap_slot=None` or a `tantrum_due_at` to let those happen.
    """
    life = new_egg(1, at)
    life.phase = Phase.ALIVE
    life.stage = Stage.BABY
    life.peak_stage = Stage.BABY
    life.health = 50.0
    life.hatched_at = at
    life.stage_started_at = at
    life.nap_slot = NEVER
    life.tantrum_due_at = NEVER
    for name, value in fields.items():
        setattr(life, name, value)
    return life


def tick_at(life: Life, now: datetime, *, frozen: bool = False) -> list[ChoreEvent]:
    """One loop tick at `now`, crediting time the way the life loop does."""
    elapsed = credited_gap(life, now, frozen=frozen)
    life.last_tick_at = now
    return tick_chores(life, now, elapsed, random.Random(7), frozen=frozen)


def run(life: Life, until: datetime, *, frozen: bool = False) -> list[ChoreEvent]:
    """Tick every TICK_EVERY from his last tick up to `until`."""
    events: list[ChoreEvent] = []
    now = life.last_tick_at
    while now < until:
        now = min(now + TICK_EVERY, until)
        events += tick_at(life, now, frozen=frozen)
    return events


def changed(
    life: Life, action: Callable[[Life], ChoreEvent]
) -> tuple[ChoreEvent, dict[str, object]]:
    """What `action` returned, and the fields it changed with their new values."""
    before = asdict(life)
    returned = action(life)
    after = asdict(life)
    return returned, {
        name: after[name] for name in after if before[name] != after[name]
    }


def utc(hour: int, minute: int = 0) -> datetime:
    """That time on DAY."""
    return DAY + timedelta(hours=hour, minutes=minute)


def event(kind: ChoreEventKind, post: int | None = None) -> ChoreEvent:
    return ChoreEvent(kind, post)


def pacific(day: date, hour: int) -> datetime:
    """That hour on the Pacific clock on `day`, in UTC."""
    return datetime.combine(day, time(hour), PACIFIC).astimezone(UTC)


def naps_started(start: datetime, end: datetime) -> list[datetime]:
    """When an awake Wisp ticked from `start` dozes off, every tick up to `end`."""
    life = alive(at=start, nap_slot=None)
    starts: list[datetime] = []
    now = start
    while now < end:
        now += TICK_EVERY
        if event(ChoreEventKind.NAP) in tick_at(life, now):
            starts.append(now)
    return starts


# ---
# Opening a chore
# ---


def test_open_mess_sets_only_the_mess() -> None:
    life = alive(mess_in=120.0, mess_message_id=5)
    assert changed(life, open_mess) == (
        event(ChoreEventKind.MESS),
        {
            "mess_in": 0.0,
            "mess_left": 21600.0,
            "mess_gap": 21600.0,
            "mess_message_id": None,
        },
    )


def test_open_tantrum_sets_only_the_tantrum() -> None:
    life = alive(tantrum_message_id=5)
    assert changed(life, open_tantrum) == (
        event(ChoreEventKind.TANTRUM),
        {"tantrum_left": 900.0, "tantrum_message_id": None},
    )


def test_start_nap_sets_only_the_nap() -> None:
    life = alive(nap_message_id=5)
    assert changed(life, start_nap) == (
        event(ChoreEventKind.NAP),
        {"nap_left": 3600.0, "lights_left": 900.0, "nap_message_id": None},
    )


def test_message_ids_are_kept_per_chore() -> None:
    life = alive()
    for post, chore in enumerate(Chore, start=1):
        set_message_id(life, chore, post)
    assert [message_id(life, chore) for chore in Chore] == [1, 2, 3]
    assert life.mess_message_id == 1
    assert life.tantrum_message_id == 2
    assert life.nap_message_id == 3


# ---
# Messes
# ---


def test_a_fed_track_schedules_a_mess_30_to_90_minutes_later() -> None:
    delays = set()
    for seed in range(50):
        life = alive()
        schedule_mess(life, random.Random(seed))
        assert 1800 <= life.mess_in <= 5400
        delays.add(life.mess_in)
    assert len(delays) > 1


@pytest.mark.parametrize("busy", ["mess_in", "mess_left", "mess_gap"])
def test_no_mess_is_scheduled_while_one_is_open_pending_or_too_soon(
    busy: str,
) -> None:
    life = alive()
    setattr(life, busy, 100.0)
    schedule_mess(life, random.Random(1))
    assert (life.mess_in, life.mess_left, life.mess_gap) == tuple(
        100.0 if name == busy else 0.0 for name in ("mess_in", "mess_left", "mess_gap")
    )


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
def test_only_a_living_wisp_gets_a_mess_scheduled(phase: Phase) -> None:
    life = alive(phase=phase)
    schedule_mess(life, random.Random(1))
    assert life.mess_in == 0.0


def test_a_mess_appears_when_its_delay_runs_out() -> None:
    life = alive(mess_in=600.0, mess_message_id=5)
    assert run(life, T0 + timedelta(minutes=5)) == []
    assert life.mess_in == 300.0
    assert run(life, T0 + timedelta(minutes=10)) == [event(ChoreEventKind.MESS)]
    assert is_open(life, Chore.MESS)
    assert life.mess_in == 0.0
    assert life.mess_left == 21600
    assert life.mess_gap == 21600
    assert life.mess_message_id is None


def test_the_gap_between_messes_counts_down_after_a_cleanup() -> None:
    life = alive()
    open_mess(life)
    run(life, T0 + timedelta(hours=1))
    do_chore(life, Chore.MESS)
    run(life, T0 + timedelta(hours=6) - TICK_EVERY)
    schedule_mess(life, random.Random(1))
    assert life.mess_in == 0.0
    run(life, T0 + timedelta(hours=6))
    schedule_mess(life, random.Random(1))
    assert life.mess_in > 0


def test_a_mess_left_six_hours_gives_him_a_cold() -> None:
    life = alive()
    open_mess(life)
    set_message_id(life, Chore.MESS, POST)
    assert run(life, T0 + timedelta(hours=6) - TICK_EVERY) == []
    assert is_open(life, Chore.MESS)
    assert run(life, T0 + timedelta(hours=6)) == [
        event(ChoreEventKind.MESS_LEFT, POST),
        event(ChoreEventKind.SNIFFLES),
    ]
    assert life.sniffles_left == 172800
    assert not is_open(life, Chore.MESS)


@pytest.mark.parametrize(
    "illness",
    [{"cold_left": SICK_FOR.total_seconds()}, {"sniffles_left": 3600.0}],
    ids=["monster pox", "a cold"],
)
def test_a_mess_left_while_sick_gives_no_second_illness(
    illness: dict[str, float],
) -> None:
    life = alive()
    for name, value in illness.items():
        setattr(life, name, value)
    open_mess(life)
    set_message_id(life, Chore.MESS, POST)
    assert run(life, T0 + timedelta(hours=6)) == [event(ChoreEventKind.MESS_LEFT, POST)]
    assert life.sniffles_left == illness.get("sniffles_left", 0.0)
    assert not is_open(life, Chore.MESS)


@pytest.mark.parametrize(
    ("chore", "start"),
    [(Chore.MESS, open_mess), (Chore.TANTRUM, open_tantrum), (Chore.NAP, start_nap)],
)
def test_a_chore_with_no_post_is_dropped_at_no_cost(
    chore: Chore, start: Callable[[Life], ChoreEvent]
) -> None:
    life = alive()
    start(life)
    before = (life.health, life.wellbeing, life.spoiled_until, life.cranky_until)
    assert drop_chore(life, chore) is True
    assert not is_open(life, chore)
    assert life.mess_gap == 0.0
    assert (life.health, life.wellbeing, life.spoiled_until, life.cranky_until) == (
        before
    )
    assert drop_chore(life, chore) is False


def test_a_dropped_nap_lets_him_sleep_on() -> None:
    life = alive()
    start_nap(life)
    drop_chore(life, Chore.NAP)
    assert is_napping(life)


def test_a_posted_chore_is_never_dropped() -> None:
    life = alive()
    open_mess(life)
    set_message_id(life, Chore.MESS, POST)
    assert drop_chore(life, Chore.MESS) is False
    assert is_open(life, Chore.MESS)
    assert life.mess_gap > 0


def test_a_dropped_mess_does_not_hold_back_the_next() -> None:
    life = alive()
    open_mess(life)
    drop_chore(life, Chore.MESS)
    schedule_mess(life, random.Random(1))
    assert life.mess_in > 0


def test_an_unposted_mess_gives_no_cold() -> None:
    life = alive()
    open_mess(life)
    assert run(life, T0 + timedelta(hours=6)) == []
    assert life.sniffles_left == 0.0
    assert not is_open(life, Chore.MESS)


def test_a_cleanup_adds_five_health_and_ends_the_wellbeing_stretch() -> None:
    life = alive(health_stretch=3600.0, wellbeing_stretch=3600.0)
    open_mess(life)
    assert do_chore(life, Chore.MESS) is True
    assert HEALTH_PER_CLEANUP == 5
    assert life.health == 55.0
    assert life.wellbeing == WELLBEING_START
    assert (life.health_stretch, life.wellbeing_stretch) == (3600.0, 0.0)
    assert not is_open(life, Chore.MESS)
    assert do_chore(life, Chore.MESS) is False
    assert life.health == 55.0


# ---
# Tantrums
# ---


def _naps_around(moment: datetime) -> list[datetime]:
    return [
        pacific(moment.date() + timedelta(days=offset), hour)
        for offset in (-2, -1, 0, 1, 2)
        for hour in NAP_LOCAL_HOURS
    ]


@pytest.mark.parametrize(
    "after",
    [
        utc(0),
        utc(14, 50),
        utc(23, 59),
        datetime(2026, 3, 7, 23, 59, tzinfo=UTC),
        datetime(2026, 3, 8, 0, tzinfo=UTC),
        datetime(2026, 3, 8, 13, 50, tzinfo=UTC),
        datetime(2026, 10, 31, 23, 59, tzinfo=UTC),
        datetime(2026, 11, 1, 0, tzinfo=UTC),
        datetime(2026, 11, 1, 4, 50, tzinfo=UTC),
    ],
)
def test_next_tantrum_is_always_awake(after: datetime) -> None:
    for seed in range(200):
        due = next_tantrum(after, random.Random(seed))
        assert after <= due < after + timedelta(days=2)
        for nap in _naps_around(due):
            assert not (nap - QUIET_BEFORE_NAP <= due < nap + timedelta(hours=1)), (
                seed,
                due,
            )


def test_next_tantrum_moves_to_the_next_day_when_today_has_no_awake_time_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("wisp.chores.NAP_LOCAL_HOURS", (7, 13, 15))
    for seed in range(50):
        due = next_tantrum(utc(23, 30), random.Random(seed))
        assert (
            datetime(2026, 11, 3, tzinfo=UTC) <= due < utc(22, 40) + timedelta(days=1)
        )


def test_a_tantrum_starts_when_due() -> None:
    life = alive(tantrum_due_at=T0 + timedelta(minutes=10), tantrum_message_id=5)
    assert run(life, T0 + timedelta(minutes=5)) == []
    assert run(life, T0 + timedelta(minutes=10)) == [event(ChoreEventKind.TANTRUM)]
    assert is_open(life, Chore.TANTRUM)
    assert life.tantrum_left == 900
    assert life.tantrum_message_id is None
    assert life.tantrum_due_at is not None
    assert life.tantrum_due_at.date() == datetime(2026, 11, 3).date()


def test_a_tantrum_due_during_a_nap_waits_until_he_wakes() -> None:
    life = alive(at=utc(14, 55), nap_slot=None, tantrum_due_at=utc(15, 20))
    assert run(life, utc(15, 55)) == [event(ChoreEventKind.NAP)]
    assert not is_open(life, Chore.TANTRUM)
    assert run(life, utc(16)) == [event(ChoreEventKind.TANTRUM)]
    assert not is_napping(life)


def test_a_tantrum_due_at_the_last_awake_moment_closes_before_the_nap() -> None:
    due = utc(15) - QUIET_BEFORE_NAP - timedelta(microseconds=1)
    life = alive(at=utc(14, 35), nap_slot=None, tantrum_due_at=due)
    assert tick_at(life, due) == [event(ChoreEventKind.TANTRUM)]
    assert run(life, utc(15)) == [event(ChoreEventKind.NAP)]
    assert not is_open(life, Chore.TANTRUM)
    assert is_napping(life)


def test_a_tantrum_due_during_an_outage_waits_out_the_nap_coming() -> None:
    life = alive(at=utc(14), nap_slot=None, tantrum_due_at=utc(14, 20))
    assert tick_at(life, utc(14, 45)) == []
    assert not is_open(life, Chore.TANTRUM)
    assert life.tantrum_due_at is not None
    assert utc(16) <= life.tantrum_due_at < DAY + timedelta(days=1)
    assert run(life, utc(15)) == [event(ChoreEventKind.NAP)]
    assert event(ChoreEventKind.TANTRUM) in run(life, utc(23, 55))


def test_a_tantrum_closing_on_the_naps_first_tick_lets_the_nap_start() -> None:
    life = alive(at=utc(14, 45), nap_slot=None)
    open_tantrum(life)
    assert run(life, utc(15)) == [event(ChoreEventKind.NAP)]
    assert not is_open(life, Chore.TANTRUM)
    assert is_napping(life)


def test_a_due_time_from_an_earlier_day_is_rolled_again() -> None:
    life = alive(tantrum_due_at=T0 - timedelta(days=1))
    now = T0 + TICK_EVERY
    assert run(life, now) == []
    assert not is_open(life, Chore.TANTRUM)
    assert life.tantrum_due_at is not None
    assert life.tantrum_due_at > now
    assert life.tantrum_due_at.date() == now.date()


def test_a_missed_tantrum_costs_fifteen_wellbeing_and_spoils_him() -> None:
    life = alive()
    open_tantrum(life)
    set_message_id(life, Chore.TANTRUM, POST)
    assert run(life, T0 + timedelta(minutes=10)) == []
    assert run(life, T0 + timedelta(minutes=15)) == [
        event(ChoreEventKind.TANTRUM_MISSED, POST)
    ]
    assert life.wellbeing == 35.0
    assert life.spoiled_until == datetime(2026, 11, 3, tzinfo=UTC)
    assert not is_open(life, Chore.TANTRUM)


def test_an_unposted_tantrum_costs_nothing() -> None:
    life = alive()
    open_tantrum(life)
    assert run(life, T0 + timedelta(minutes=15)) == []
    assert life.wellbeing == WELLBEING_START
    assert life.spoiled_until is None
    assert not is_open(life, Chore.TANTRUM)


def test_a_scold_closes_the_tantrum() -> None:
    life = alive()
    open_tantrum(life)
    set_message_id(life, Chore.TANTRUM, POST)
    assert do_chore(life, Chore.TANTRUM) is True
    assert not is_open(life, Chore.TANTRUM)
    assert run(life, T0 + timedelta(minutes=15)) == []
    assert life.wellbeing == WELLBEING_START
    assert life.spoiled_until is None
    assert do_chore(life, Chore.TANTRUM) is False


# ---
# Naps
# ---


@pytest.mark.parametrize("hour", [6, 15, 21])
def test_naps_start_at_seven_one_and_ten_pacific(hour: int) -> None:
    life = alive(at=utc(hour) - timedelta(hours=1), nap_slot=None, nap_message_id=5)
    assert run(life, utc(hour) - TICK_EVERY) == []
    assert run(life, utc(hour)) == [event(ChoreEventKind.NAP)]
    assert is_napping(life)
    assert is_open(life, Chore.NAP)
    assert life.nap_left == 3600
    assert life.lights_left == 900
    assert life.nap_slot == utc(hour)
    assert life.nap_message_id is None


@pytest.mark.parametrize(
    ("day", "hours"),
    [
        (date(2026, 3, 7), (6, 15, 21)),
        (date(2026, 3, 8), (6, 14, 20)),
        (date(2026, 3, 9), (5, 14, 20)),
        (date(2026, 10, 31), (5, 14, 20)),
        (date(2026, 11, 1), (5, 15, 21)),
        (date(2026, 11, 2), (6, 15, 21)),
    ],
)
def test_each_utc_day_naps_at_its_pacific_slots_across_daylight_saving(
    day: date, hours: tuple[int, ...]
) -> None:
    midnight = datetime.combine(day, time(), UTC)
    starts = naps_started(midnight - TICK_EVERY, midnight + timedelta(days=1))
    assert starts == [midnight + timedelta(hours=hour) for hour in hours]
    assert [start.astimezone(PACIFIC).hour for start in starts] == [22, 7, 13]


@pytest.mark.parametrize("first", [date(2026, 3, 5), date(2026, 10, 29)])
def test_no_pacific_slot_is_lost_or_doubled_at_the_utc_midnight_seam(
    first: date,
) -> None:
    days = [first + timedelta(days=offset) for offset in range(6)]
    start = datetime.combine(days[0], time(), UTC)
    end = datetime.combine(days[-1], time(), UTC) + timedelta(days=1)
    expected = sorted(
        moment
        for day in [days[0] - timedelta(days=1), *days]
        for hour in NAP_LOCAL_HOURS
        if start < (moment := pacific(day, hour)) <= end
    )
    assert len(expected) == 18
    assert naps_started(start, end) == expected


@pytest.mark.parametrize(
    ("now", "nap"),
    [
        (DAY, "next nap 10pm Pacific"),
        (utc(5, 59), "next nap 10pm Pacific"),
        (utc(6), "next nap 7am Pacific"),
        (utc(12), "next nap 7am Pacific"),
        (utc(15), "next nap 1pm Pacific"),
        (utc(21), "next nap 10pm Pacific"),
        (utc(23, 59), "next nap 10pm Pacific"),
        (datetime(2026, 3, 8, 13, 59, tzinfo=UTC), "next nap 7am Pacific"),
        (datetime(2026, 3, 8, 23, 59, tzinfo=UTC), "next nap 10pm Pacific"),
        (datetime(2026, 11, 1, 4, 59, tzinfo=UTC), "next nap 10pm Pacific"),
        (datetime(2026, 11, 1, 5, 0, tzinfo=UTC), "next nap 7am Pacific"),
    ],
)
def test_the_next_nap_is_the_first_start_after_now(now: datetime, nap: str) -> None:
    assert next_nap_text(now) == nap


@pytest.mark.parametrize(
    ("moment", "shown"),
    [
        (utc(21), "1pm Pacific"),
        (utc(2, 5), "6:05pm Pacific"),
        (utc(20), "12pm Pacific"),
        (utc(20, 30), "12:30pm Pacific"),
        (utc(8), "12am Pacific"),
        (utc(8, 1), "12:01am Pacific"),
        (utc(15), "7am Pacific"),
        (datetime(2026, 7, 1, 21, tzinfo=UTC), "2pm Pacific"),
    ],
)
def test_a_nap_time_reads_on_the_pacific_clock(moment: datetime, shown: str) -> None:
    assert nap_time_text(moment) == shown


@pytest.mark.parametrize(
    ("left", "ends"),
    [
        (timedelta(minutes=30), "2:45am Pacific"),
        (timedelta(minutes=30, seconds=1), "2:46am Pacific"),
        (timedelta(seconds=1), "2:16am Pacific"),
        (timedelta(hours=1), "3:15am Pacific"),
    ],
)
def test_a_nap_ends_when_its_time_left_runs_out_rounded_up(
    left: timedelta, ends: str
) -> None:
    life = alive(nap_left=left.total_seconds())
    assert nap_time_text(nap_ends_at(life, utc(10, 15))) == ends


SLOTS_EITHER_SIDE_OF_A_CHANGE = [
    utc(15),
    datetime(2026, 3, 8, 14, tzinfo=UTC),
    datetime(2026, 11, 1, 15, tzinfo=UTC),
]


@pytest.mark.parametrize("slot", SLOTS_EITHER_SIDE_OF_A_CHANGE)
def test_a_nap_start_missed_by_an_outage_is_skipped(slot: datetime) -> None:
    life = alive(at=slot - timedelta(minutes=10), nap_slot=None)
    assert tick_at(life, slot - TICK_EVERY) == []
    assert tick_at(life, slot + timedelta(minutes=20)) == []
    assert life.nap_slot == slot
    assert not is_napping(life)
    assert life.wellbeing == WELLBEING_START
    assert life.cranky_until is None


@pytest.mark.parametrize("slot", SLOTS_EITHER_SIDE_OF_A_CHANGE)
def test_a_nap_start_while_frozen_is_skipped(slot: datetime) -> None:
    life = alive(at=slot - timedelta(minutes=10), nap_slot=None)
    assert run(life, slot, frozen=True) == []
    assert tick_at(life, slot + TICK_EVERY) == []
    assert life.nap_slot == slot
    assert not is_napping(life)


@pytest.mark.parametrize(
    ("old_slot", "next_slot"),
    [(utc(2), utc(6)), (utc(10), utc(15)), (utc(18), utc(21))],
)
def test_a_nap_stored_on_the_old_utc_slots_finishes_then_naps_go_pacific(
    old_slot: datetime, next_slot: datetime
) -> None:
    life = alive(
        at=old_slot + timedelta(minutes=30), nap_slot=old_slot, nap_left=1800.0
    )
    assert run(life, old_slot + timedelta(hours=1)) == []
    assert not is_napping(life)
    assert run(life, next_slot - TICK_EVERY) == []
    assert run(life, next_slot) == [event(ChoreEventKind.NAP)]
    assert life.nap_slot == next_slot


def _napping_at_seven_pacific() -> Life:
    life = alive(at=utc(14, 55), nap_slot=None)
    assert tick_at(life, utc(15)) == [event(ChoreEventKind.NAP)]
    return life


def test_missed_lights_cost_ten_wellbeing_and_make_him_cranky() -> None:
    life = _napping_at_seven_pacific()
    set_message_id(life, Chore.NAP, POST)
    assert run(life, utc(15, 10)) == []
    assert tick_at(life, utc(15, 15)) == [event(ChoreEventKind.LIGHTS_MISSED, POST)]
    assert life.wellbeing == 40.0
    assert life.cranky_until == utc(15, 15) + timedelta(minutes=45) + timedelta(hours=1)
    assert not is_open(life, Chore.NAP)
    assert is_napping(life)


def test_unposted_lights_cost_nothing() -> None:
    life = _napping_at_seven_pacific()
    assert run(life, utc(15, 15)) == []
    assert life.wellbeing == WELLBEING_START
    assert life.cranky_until is None
    assert not is_open(life, Chore.NAP)
    assert is_napping(life)


def test_lights_off_closes_the_window_and_he_sleeps_on() -> None:
    life = _napping_at_seven_pacific()
    set_message_id(life, Chore.NAP, POST)
    assert do_chore(life, Chore.NAP) is True
    assert not is_open(life, Chore.NAP)
    assert run(life, utc(15, 30)) == []
    assert is_napping(life)
    assert life.nap_left == 1800
    assert life.wellbeing == WELLBEING_START
    assert life.cranky_until is None
    assert do_chore(life, Chore.NAP) is False


def test_he_wakes_after_an_hour_of_counted_time() -> None:
    life = _napping_at_seven_pacific()
    do_chore(life, Chore.NAP)
    assert tick_at(life, utc(16, 30)) == []
    assert life.nap_left == 2700
    assert is_napping(life)
    run(life, utc(17, 10))
    assert is_napping(life)
    run(life, utc(17, 15))
    assert not is_napping(life)
    assert life.nap_left == 0.0


@pytest.mark.parametrize("lights_off", [False, True])
def test_wake_ends_the_nap_and_says_whether_the_lights_were_on(
    lights_off: bool,
) -> None:
    life = alive()
    start_nap(life)
    if lights_off:
        do_chore(life, Chore.NAP)
    assert wake(life, T0) is not lights_off
    assert not is_napping(life)
    assert not is_open(life, Chore.NAP)
    assert life.wellbeing == WELLBEING_START
    assert life.cranky_until == T0 + timedelta(hours=1)


def test_a_poke_after_missed_lights_never_shortens_the_crankiness() -> None:
    life = _napping_at_seven_pacific()
    set_message_id(life, Chore.NAP, POST)
    run(life, utc(15, 15))
    cranky_until = life.cranky_until
    assert cranky_until == utc(17)
    assert wake(life, utc(15, 20)) is False
    assert life.cranky_until == cranky_until


def test_a_lights_window_never_outlasts_the_nap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("wisp.chores.LIGHTS_WINDOW", timedelta(hours=2))
    life = _napping_at_seven_pacific()
    set_message_id(life, Chore.NAP, POST)
    assert run(life, utc(15, 55)) == []
    assert run(life, utc(16)) == [event(ChoreEventKind.LIGHTS_MISSED, POST)]
    assert not is_napping(life)
    assert not is_open(life, Chore.NAP)
    assert life.cranky_until == utc(17)


def test_no_nap_starts_over_an_open_tantrum() -> None:
    life = alive(at=utc(14, 55), nap_slot=None)
    open_tantrum(life)
    assert run(life, utc(15, 30)) == []
    assert life.nap_slot == utc(15)
    assert not is_napping(life)
    assert not is_open(life, Chore.TANTRUM)


# ---
# Every chore
# ---


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
def test_only_a_living_wisp_has_chores(phase: Phase) -> None:
    life = alive(
        at=utc(14, 55), phase=phase, mess_in=300.0, nap_slot=None, tantrum_due_at=None
    )
    open_tantrum(life)
    before = asdict(life)
    assert tick_at(life, utc(15)) == []
    assert asdict(life) == {**before, "last_tick_at": utc(15)}


def test_frozen_time_pauses_every_chore() -> None:
    life = alive(mess_in=600.0)
    open_tantrum(life)
    start_nap(life)
    later = alive(at=T0)
    open_mess(later)
    for wisp in (life, later):
        before = asdict(wisp)
        assert run(wisp, T0 + timedelta(hours=1), frozen=True) == []
        assert asdict(wisp) == {**before, "last_tick_at": T0 + timedelta(hours=1)}


def test_a_chore_never_counts_more_than_the_credited_gap() -> None:
    life = alive()
    open_mess(life)
    open_tantrum(life)
    assert tick_at(life, T0 + timedelta(hours=3)) == []
    assert life.mess_left == 21600 - 900
    assert life.tantrum_left == 0.0
