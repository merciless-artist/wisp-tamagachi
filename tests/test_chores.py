"""Tests for the chores: messes, tantrums and naps, as pure rules."""

import random
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest

from wisp.chores import (
    ChoreEvent,
    ChoreEventKind,
    do_chore,
    is_napping,
    is_open,
    message_id,
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
    MOOD_START,
    NAP_HOURS,
    SICK_FOR,
    TICK_EVERY,
    Chore,
    Stage,
)

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
DAY = datetime(2026, 11, 2, tzinfo=UTC)
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


def test_an_unposted_mess_gives_no_cold() -> None:
    life = alive()
    open_mess(life)
    assert run(life, T0 + timedelta(hours=6)) == []
    assert life.sniffles_left == 0.0
    assert not is_open(life, Chore.MESS)


def test_a_cleanup_adds_five_wellbeing_and_closes_the_mess() -> None:
    life = alive(wellbeing_stretch=3600.0)
    open_mess(life)
    assert do_chore(life, Chore.MESS) is True
    assert life.wellbeing == 55.0
    assert life.wellbeing_stretch == 3600.0
    assert not is_open(life, Chore.MESS)
    assert do_chore(life, Chore.MESS) is False
    assert life.wellbeing == 55.0


# ---
# Tantrums
# ---


def _naps_around(moment: datetime) -> list[datetime]:
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        day + timedelta(days=offset, hours=hour)
        for offset in (-1, 0, 1)
        for hour in NAP_HOURS
    ]


@pytest.mark.parametrize("after", [utc(0), utc(9, 50), utc(23, 59)])
def test_next_tantrum_is_always_awake(after: datetime) -> None:
    for seed in range(200):
        due = next_tantrum(after, random.Random(seed))
        assert after <= due < after + timedelta(days=2)
        for nap in _naps_around(due):
            assert not (
                nap - timedelta(minutes=15) <= due < nap + timedelta(hours=1)
            ), (seed, due)


def test_next_tantrum_moves_to_the_next_day_when_today_has_no_awake_time_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("wisp.chores.NAP_HOURS", (2, 10, 23))
    for seed in range(50):
        due = next_tantrum(utc(23, 30), random.Random(seed))
        assert (
            datetime(2026, 11, 3, tzinfo=UTC) <= due < utc(22, 45) + timedelta(days=1)
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
    life = alive(at=utc(9, 55), nap_slot=None, tantrum_due_at=utc(10, 20))
    assert run(life, utc(10, 55)) == [event(ChoreEventKind.NAP)]
    assert not is_open(life, Chore.TANTRUM)
    assert run(life, utc(11)) == [event(ChoreEventKind.TANTRUM)]
    assert not is_napping(life)


def test_a_due_time_from_an_earlier_day_is_rolled_again() -> None:
    life = alive(tantrum_due_at=T0 - timedelta(days=1))
    now = T0 + TICK_EVERY
    assert run(life, now) == []
    assert not is_open(life, Chore.TANTRUM)
    assert life.tantrum_due_at is not None
    assert life.tantrum_due_at > now
    assert life.tantrum_due_at.date() == now.date()


def test_a_missed_tantrum_costs_fifteen_mood_and_spoils_him_until_midnight() -> None:
    life = alive()
    open_tantrum(life)
    set_message_id(life, Chore.TANTRUM, POST)
    assert run(life, T0 + timedelta(minutes=10)) == []
    assert run(life, T0 + timedelta(minutes=15)) == [
        event(ChoreEventKind.TANTRUM_MISSED, POST)
    ]
    assert life.mood_meter == 35.0
    assert life.spoiled_until == datetime(2026, 11, 3, tzinfo=UTC)
    assert not is_open(life, Chore.TANTRUM)


def test_an_unposted_tantrum_costs_nothing() -> None:
    life = alive()
    open_tantrum(life)
    assert run(life, T0 + timedelta(minutes=15)) == []
    assert life.mood_meter == MOOD_START
    assert life.spoiled_until is None
    assert not is_open(life, Chore.TANTRUM)


def test_a_scold_closes_the_tantrum() -> None:
    life = alive()
    open_tantrum(life)
    set_message_id(life, Chore.TANTRUM, POST)
    assert do_chore(life, Chore.TANTRUM) is True
    assert not is_open(life, Chore.TANTRUM)
    assert run(life, T0 + timedelta(minutes=15)) == []
    assert life.mood_meter == MOOD_START
    assert life.spoiled_until is None
    assert do_chore(life, Chore.TANTRUM) is False


# ---
# Naps
# ---


@pytest.mark.parametrize("hour", [2, 10, 18])
def test_naps_start_at_two_ten_and_eighteen_utc(hour: int) -> None:
    life = alive(at=utc(hour) - timedelta(hours=1), nap_slot=None, nap_message_id=5)
    assert run(life, utc(hour) - TICK_EVERY) == []
    assert run(life, utc(hour)) == [event(ChoreEventKind.NAP)]
    assert is_napping(life)
    assert is_open(life, Chore.NAP)
    assert life.nap_left == 3600
    assert life.lights_left == 900
    assert life.nap_slot == utc(hour)
    assert life.nap_message_id is None


def test_a_nap_start_missed_by_an_outage_is_skipped() -> None:
    life = alive(at=utc(9, 50), nap_slot=None)
    assert tick_at(life, utc(9, 55)) == []
    assert tick_at(life, utc(10, 20)) == []
    assert life.nap_slot == utc(10)
    assert not is_napping(life)
    assert life.mood_meter == MOOD_START
    assert life.cranky_until is None


def test_a_nap_start_while_frozen_is_skipped() -> None:
    life = alive(at=utc(9, 50), nap_slot=None)
    assert run(life, utc(10), frozen=True) == []
    assert tick_at(life, utc(10, 5)) == []
    assert life.nap_slot == utc(10)
    assert not is_napping(life)


def _napping_at_ten() -> Life:
    life = alive(at=utc(9, 55), nap_slot=None)
    assert tick_at(life, utc(10)) == [event(ChoreEventKind.NAP)]
    return life


def test_missed_lights_cost_ten_mood_and_make_him_cranky() -> None:
    life = _napping_at_ten()
    set_message_id(life, Chore.NAP, POST)
    assert run(life, utc(10, 10)) == []
    assert tick_at(life, utc(10, 15)) == [event(ChoreEventKind.LIGHTS_MISSED, POST)]
    assert life.mood_meter == 40.0
    assert life.cranky_until == utc(10, 15) + timedelta(minutes=45) + timedelta(hours=1)
    assert not is_open(life, Chore.NAP)
    assert is_napping(life)


def test_unposted_lights_cost_nothing() -> None:
    life = _napping_at_ten()
    assert run(life, utc(10, 15)) == []
    assert life.mood_meter == MOOD_START
    assert life.cranky_until is None
    assert not is_open(life, Chore.NAP)
    assert is_napping(life)


def test_lights_off_closes_the_window_and_he_sleeps_on() -> None:
    life = _napping_at_ten()
    set_message_id(life, Chore.NAP, POST)
    assert do_chore(life, Chore.NAP) is True
    assert not is_open(life, Chore.NAP)
    assert run(life, utc(10, 30)) == []
    assert is_napping(life)
    assert life.nap_left == 1800
    assert life.mood_meter == MOOD_START
    assert life.cranky_until is None
    assert do_chore(life, Chore.NAP) is False


def test_he_wakes_after_an_hour_of_counted_time() -> None:
    life = _napping_at_ten()
    do_chore(life, Chore.NAP)
    assert tick_at(life, utc(11, 30)) == []
    assert life.nap_left == 2700
    assert is_napping(life)
    run(life, utc(12, 10))
    assert is_napping(life)
    run(life, utc(12, 15))
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
    assert life.mood_meter == MOOD_START
    assert life.cranky_until == T0 + timedelta(hours=1)


def test_no_nap_starts_over_an_open_tantrum() -> None:
    life = alive(at=utc(9, 55), nap_slot=None)
    open_tantrum(life)
    assert run(life, utc(10, 30)) == []
    assert life.nap_slot == utc(10)
    assert not is_napping(life)
    assert not is_open(life, Chore.TANTRUM)


# ---
# Every chore
# ---


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
def test_only_a_living_wisp_has_chores(phase: Phase) -> None:
    life = alive(
        at=utc(9, 55), phase=phase, mess_in=300.0, nap_slot=None, tantrum_due_at=None
    )
    open_tantrum(life)
    before = asdict(life)
    assert tick_at(life, utc(10)) == []
    assert asdict(life) == {**before, "last_tick_at": utc(10)}


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
