"""Tests for Wisp's life story: what gets saved and what he is told."""

from datetime import UTC, datetime, timedelta

import pytest

from db.database import Database
from db.story import LifeStoryRepo
from wisp.life import Event, EventKind, Life, Phase, feed, new_egg
from wisp.rules import LIFE_STORY_ENTRIES, PAST_LIVES_REMEMBERED, SICK_FOR, Stage
from wisp.story import (
    Entry,
    EntryKind,
    entries_from,
    life_story,
    member_ids,
    past_lives,
)

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
GUILD_ID = 1
LIFE_ID = 7
MEMBER = 42
NAMES = {MEMBER: "Cat"}


def alive(stage: Stage = Stage.TEEN, **changes: object) -> Life:
    """A living Wisp at `stage`, hatched five days before NOW."""
    life = new_egg(1, NOW - timedelta(days=6))
    life.phase = Phase.ALIVE
    life.stage = life.peak_stage = stage
    life.hatched_at = NOW - timedelta(days=5)
    life.had_cold = True
    for field, value in changes.items():
        setattr(life, field, value)
    return life


def ended(version: int, phase: Phase, stage: Stage, days: int) -> Life:
    """A finished life that hatched and ended `days` days later."""
    life = alive(stage, version=version, phase=phase, ended_at=NOW)
    life.hatched_at = NOW - timedelta(days=days)
    life.last_tick_at = NOW
    return life


def told(
    life: Life, entries: tuple[Entry, ...] = (), past: tuple[Life, ...] = ()
) -> str:
    return life_story(life, entries, past, NAMES, NOW)


def entry(
    kind: EntryKind,
    stage: Stage = Stage.BABY,
    member_id: int | None = None,
    days_ago: int = 2,
) -> Entry:
    return Entry(kind, stage, member_id, NOW - timedelta(days=days_ago))


# ---
# What gets saved
# ---


@pytest.mark.parametrize(
    ("event", "kind"),
    [
        (EventKind.SICK, EntryKind.POX_CAUGHT),
        (EventKind.RECOVERED, EntryKind.POX_OVER),
        (EventKind.STAGE_UP, EntryKind.GREW_UP),
        (EventKind.GREW_OLD, EntryKind.GREW_UP),
    ],
)
def test_the_moments_worth_saving_become_entries(
    event: EventKind, kind: EntryKind
) -> None:
    events = [Event(event, Stage.CHILD, member_id=MEMBER)]

    assert entries_from(events, NOW) == [Entry(kind, Stage.CHILD, MEMBER, NOW)]


@pytest.mark.parametrize(
    "event",
    [
        Event(EventKind.HUNGRY),
        Event(EventKind.LONELY, Stage.TEEN),
        Event(EventKind.METER_DROP),
        Event(EventKind.SICK),
    ],
)
def test_everything_else_is_not_saved(event: Event) -> None:
    assert entries_from([event], NOW) == []


def test_a_meal_that_ends_the_pox_names_who_fed_it() -> None:
    life = alive(Stage.CHILD, cold_left=60.0)

    assert feed(life, 5, MEMBER, NOW) == [
        Event(EventKind.RECOVERED, Stage.CHILD, member_id=MEMBER)
    ]


def test_the_members_a_story_names_include_who_hatched_him() -> None:
    life = alive(hatched_by=9)
    entries = [entry(EntryKind.MEDICINE, member_id=MEMBER), entry(EntryKind.GREW_UP)]

    assert member_ids(life, entries) == {9, MEMBER}


def test_a_story_with_nobody_in_it_names_nobody() -> None:
    assert member_ids(alive(), [entry(EntryKind.GREW_UP)]) == set()


# ---
# What he is told
# ---


def test_he_is_told_when_he_hatched_and_who_hatched_him() -> None:
    story = told(alive(hatched_by=MEMBER))

    assert "- You hatched 5 days ago. Cat fed you the meal that hatched you." in story


def test_a_hatcher_he_cannot_name_is_left_out() -> None:
    story = told(alive(hatched_by=999))

    assert "- You hatched 5 days ago.\n" in story


@pytest.mark.parametrize(
    ("days_ago", "words"), [(0, "Today"), (1, "Yesterday"), (3, "3 days ago")]
)
def test_a_moment_says_how_long_ago_it_was(days_ago: int, words: str) -> None:
    story = told(alive(), (entry(EntryKind.GREW_UP, Stage.TEEN, days_ago=days_ago),))

    assert f"- {words}: you grew into a Teen." in story


def test_his_pox_is_told_with_the_stage_he_had_it_at() -> None:
    story = told(alive(), (entry(EntryKind.POX_CAUGHT),))

    assert "- 2 days ago, as a Baby: you caught Monster Pox." in story


def test_a_pox_that_ran_its_course_says_so() -> None:
    story = told(alive(), (entry(EntryKind.POX_OVER),))

    assert "your Monster Pox ran its course and you got better." in story


def test_a_pox_that_was_fed_away_says_who_finished_it() -> None:
    story = told(alive(), (entry(EntryKind.POX_OVER, member_id=MEMBER),))

    assert "you got over Monster Pox early because people kept" in story
    assert "Cat fed you the one that finished it." in story


def test_medicine_says_who_gave_it() -> None:
    story = told(alive(), (entry(EntryKind.MEDICINE, member_id=MEMBER),))

    assert "as a Baby: Cat gave you medicine and cured your cold." in story


def test_medicine_from_someone_he_cannot_name_still_counts() -> None:
    story = told(alive(), (entry(EntryKind.MEDICINE, member_id=999),))

    assert "Someone gave you medicine" in story


def test_a_cold_is_told() -> None:
    story = told(alive(), (entry(EntryKind.COLD_CAUGHT),))

    assert "as a Baby: you caught a cold." in story


@pytest.mark.parametrize(
    ("stage", "behind"),
    [
        (Stage.CHILD, "Baby"),
        (Stage.TEEN, "Baby, Child"),
        (Stage.OLD_FOGEY, "Baby, Child, Teen, Adult"),
    ],
)
def test_the_stages_behind_him_come_from_the_life(stage: Stage, behind: str) -> None:
    assert f"already lived through: {behind}." in told(alive(stage))


def test_a_baby_has_no_stages_behind_him() -> None:
    assert "already lived through" not in told(alive(Stage.BABY))


def test_rockstar_is_only_behind_him_when_it_is_on_record() -> None:
    life = alive(Stage.OLD_FOGEY)

    story = told(life, (entry(EntryKind.GREW_UP, Stage.ROCKSTAR),))

    assert "already lived through: Baby, Child, Teen, Adult, Rockstar." in story


def test_a_pox_from_before_the_story_is_still_known() -> None:
    assert "Earlier in this life you had Monster Pox" in told(alive())


def test_a_pox_on_record_is_not_told_twice() -> None:
    story = told(alive(), (entry(EntryKind.POX_CAUGHT),))

    assert "Earlier in this life" not in story


def test_having_never_had_pox_is_said() -> None:
    story = told(alive(had_cold=False))

    assert "- You have not had Monster Pox in this life." in story
    assert "Earlier in this life" not in story


def test_after_the_pox_he_knows_he_is_better() -> None:
    assert "- You are not sick right now. If anyone asks, you're all better." in told(
        alive()
    )


def test_after_a_cold_he_knows_he_is_better() -> None:
    story = told(alive(had_cold=False), (entry(EntryKind.COLD_CAUGHT),))

    assert "you're all better." in story


def test_a_wisp_who_was_never_sick_is_not_told_he_got_better() -> None:
    story = told(alive(had_cold=False))

    assert "- You are not sick right now." in story
    assert "all better" not in story


@pytest.mark.parametrize(
    "changes",
    [{"cold_left": SICK_FOR.total_seconds()}, {"sniffles_left": 60.0}],
)
def test_while_he_is_sick_he_is_not_told_he_is_well(changes: dict[str, float]) -> None:
    story = told(alive(**changes))

    assert "not sick right now" not in story


def test_while_he_has_the_pox_it_is_not_called_over() -> None:
    assert "Earlier in this life" not in told(alive(cold_left=60.0))


def test_he_is_told_not_to_make_up_a_past() -> None:
    assert "Never make up anything else about your past" in told(alive())


# ---
# The Wisps before him
# ---


def test_a_full_past_life_is_remembered() -> None:
    past = ended(3, Phase.PASSED, Stage.OLD_FOGEY, 30)

    story = told(alive(version=4), past=(past,))

    assert "fire sprites remember their past lives" in story
    assert "- Wisp v3 grew into an Old Fogey and passed on after 30 days." in story


def test_a_life_that_faded_is_remembered() -> None:
    past = ended(2, Phase.DEAD, Stage.CHILD, 1)

    assert "- Wisp v2 faded away as a Child after 1 day." in told(alive(), past=(past,))


def test_no_past_lives_means_no_past_section() -> None:
    assert "fire sprites" not in told(alive())


def test_only_hatched_finished_lives_count_as_past() -> None:
    cold_egg = new_egg(2, NOW)
    cold_egg.phase = Phase.COLD
    finished = ended(1, Phase.DEAD, Stage.BABY, 2)

    assert past_lives([alive(version=3), cold_egg, finished]) == [finished]


def test_past_lives_keep_only_the_newest() -> None:
    history = [
        ended(version, Phase.DEAD, Stage.BABY, 2)
        for version in range(PAST_LIVES_REMEMBERED + 3, 0, -1)
    ]

    kept = past_lives(history)

    assert [life.version for life in kept] == [
        PAST_LIVES_REMEMBERED + 3 - offset for offset in range(PAST_LIVES_REMEMBERED)
    ]


# ---
# Storage
# ---


async def test_saved_moments_come_back_oldest_first(db: Database) -> None:
    repo = LifeStoryRepo(db)
    older = Entry(EntryKind.POX_CAUGHT, Stage.BABY, None, NOW - timedelta(days=1))
    newer = Entry(EntryKind.MEDICINE, Stage.CHILD, MEMBER, NOW)

    await repo.add(GUILD_ID, LIFE_ID, [older, newer])

    assert await repo.recent(GUILD_ID, LIFE_ID) == [older, newer]


async def test_moments_stay_with_their_own_life_and_server(db: Database) -> None:
    repo = LifeStoryRepo(db)
    mine = Entry(EntryKind.GREW_UP, Stage.TEEN, None, NOW)
    await repo.add(GUILD_ID, LIFE_ID, [mine])

    assert await repo.recent(GUILD_ID, LIFE_ID + 1) == []
    assert await repo.recent(GUILD_ID + 1, LIFE_ID) == []


async def test_only_the_newest_moments_are_read_in_order(db: Database) -> None:
    repo = LifeStoryRepo(db)
    entries = [
        Entry(EntryKind.COLD_CAUGHT, Stage.TEEN, None, NOW + timedelta(minutes=index))
        for index in range(LIFE_STORY_ENTRIES + 2)
    ]
    await repo.add(GUILD_ID, LIFE_ID, entries)

    assert await repo.recent(GUILD_ID, LIFE_ID) == entries[2:]


async def test_moments_in_the_same_second_keep_their_order(db: Database) -> None:
    repo = LifeStoryRepo(db)
    first = Entry(EntryKind.GREW_UP, Stage.CHILD, None, NOW)
    second = Entry(EntryKind.POX_CAUGHT, Stage.CHILD, None, NOW)

    await repo.add(GUILD_ID, LIFE_ID, [first, second])

    assert await repo.recent(GUILD_ID, LIFE_ID) == [first, second]


def test_a_staff_test_life_is_not_a_past_life() -> None:
    tested = ended(2, Phase.PASSED, Stage.OLD_FOGEY, 1)
    tested.is_test = True
    real = ended(1, Phase.DEAD, Stage.BABY, 2)

    assert past_lives([tested, real]) == [real]
