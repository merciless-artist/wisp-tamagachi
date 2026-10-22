"""Tests for the storage repositories, run against the real test database."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import Settings, SettingsRepo
from wisp.life import EventKind, Phase, new_egg
from wisp.links import Track, TrackKind
from wisp.rules import Stage

GUILD = 100
OTHER_GUILD = 200
USER = 1
OTHER_USER = 2
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
MIDNIGHT = datetime(2026, 10, 20, tzinfo=UTC)


def track(ident: str, kind: TrackKind = TrackKind.SUNO) -> Track:
    return Track(kind, f"{kind}:{ident}", f"https://example.test/{ident}")


# ---
# Settings
# ---


async def test_settings_default_then_update(db: Database) -> None:
    repo = SettingsRepo(db)
    assert await repo.get(GUILD) == Settings()

    await repo.update(GUILD, tracks_channel_id=55, frozen=True)
    settings = await repo.get(GUILD)
    assert settings.tracks_channel_id == 55
    assert settings.frozen is True
    assert settings.house_channel_id is None

    await repo.update(GUILD, tracks_channel_id=None)
    assert (await repo.get(GUILD)).tracks_channel_id is None
    assert await repo.get(OTHER_GUILD) == Settings()


async def test_update_rejects_unknown_field(db: Database) -> None:
    with pytest.raises(ValueError, match="nonsense"):
        await SettingsRepo(db).update(GUILD, nonsense=1)


async def test_role_list_round_trip(db: Database) -> None:
    repo = SettingsRepo(db)
    assert await repo.roles(GUILD) == set()

    await repo.add_role(GUILD, 7)
    await repo.add_role(GUILD, 7)
    await repo.add_role(GUILD, 8)
    await repo.add_role(OTHER_GUILD, 9)
    assert await repo.roles(GUILD) == {7, 8}

    await repo.remove_role(GUILD, 7)
    assert await repo.roles(GUILD) == {8}
    assert await repo.roles(OTHER_GUILD) == {9}


async def test_guilds_lists_configured_guilds(db: Database) -> None:
    repo = SettingsRepo(db)
    assert await repo.guilds() == []
    await repo.get(OTHER_GUILD)
    await repo.update(GUILD, frozen=False)
    assert await repo.guilds() == [GUILD, OTHER_GUILD]


# ---
# Lives
# ---


async def test_life_insert_save_current_history(db: Database) -> None:
    repo = LifeRepo(db)
    assert await repo.current(GUILD) is None

    first = await repo.insert(GUILD, new_egg(1, NOW))
    assert first.id is not None
    assert await repo.current(GUILD) == first

    second = await repo.insert(GUILD, new_egg(2, NOW + timedelta(days=3)))
    second.phase = Phase.ALIVE
    second.stage = second.peak_stage = Stage.CHILD
    second.care = 42.5
    second.growth = 9
    second.phase_seconds = 120.5
    second.hatch_started_at = NOW + timedelta(days=4)
    second.hatched_at = NOW + timedelta(days=5)
    second.stage_started_at = NOW + timedelta(days=6)
    second.high_happiness_since = NOW + timedelta(days=7)
    second.warned = EventKind.HUNGRY
    second.hatched_by = 77
    await repo.save(GUILD, second)

    current = await repo.current(GUILD)
    assert current == second
    assert current is not None
    assert current.laid_at.tzinfo is not None
    assert current.laid_at.utcoffset() == timedelta(0)
    assert await repo.history(GUILD) == [second, first]
    assert await repo.history(OTHER_GUILD) == []


async def test_save_clears_optional_fields(db: Database) -> None:
    repo = LifeRepo(db)
    life = await repo.insert(GUILD, new_egg(1, NOW))
    life.warned = EventKind.FADING
    life.ended_at = NOW
    await repo.save(GUILD, life)
    life.warned = None
    life.ended_at = None
    await repo.save(GUILD, life)
    assert await repo.current(GUILD) == life


async def test_save_requires_inserted_life(db: Database) -> None:
    with pytest.raises(ValueError, match="inserted"):
        await LifeRepo(db).save(GUILD, new_egg(1, NOW))


async def test_next_version_counts_cold_eggs(db: Database) -> None:
    repo = LifeRepo(db)
    assert await repo.next_version(GUILD) == 1

    egg = await repo.insert(GUILD, new_egg(1, NOW))
    egg.phase = Phase.COLD
    egg.ended_at = NOW + timedelta(hours=48)
    await repo.save(GUILD, egg)

    assert await repo.next_version(GUILD) == 2
    assert await repo.next_version(OTHER_GUILD) == 1


# ---
# Players
# ---


async def test_player_created_with_defaults_on_first_read(db: Database) -> None:
    player = await PlayerRepo(db).get(GUILD, USER)
    assert player.user_id == USER
    assert player.lifetime_points == player.balance == player.bond == 0
    assert player.offenses == 0
    assert player.banned_forever is False
    assert player.activated_at is None
    assert player.met_at is None
    assert player.name is None
    assert player.banned_until is None


async def test_points_add_to_lifetime_and_balance(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.add_points(GUILD, USER, 5)
    await repo.add_points(GUILD, USER, 3)
    player = await repo.get(GUILD, USER)
    assert (player.lifetime_points, player.balance) == (8, 8)
    assert (await repo.get(OTHER_GUILD, USER)).balance == 0


async def test_spend_refuses_overdraft(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.add_points(GUILD, USER, 5)
    assert await repo.spend(GUILD, USER, 6) is False
    assert (await repo.get(GUILD, USER)).balance == 5
    assert await repo.spend(GUILD, USER, 5) is True
    assert (await repo.get(GUILD, USER)).balance == 0
    assert await repo.spend(GUILD, USER, 1) is False


async def test_spend_never_lowers_lifetime(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.add_points(GUILD, USER, 10)
    await repo.spend(GUILD, USER, 4)
    player = await repo.get(GUILD, USER)
    assert (player.lifetime_points, player.balance) == (10, 6)


async def test_spend_nothing_always_succeeds(db: Database) -> None:
    repo = PlayerRepo(db)
    assert await repo.spend(GUILD, USER, 0) is True
    await repo.add_points(GUILD, OTHER_USER, 2)
    assert await repo.spend(GUILD, OTHER_USER, 0) is True
    assert (await repo.get(GUILD, OTHER_USER)).balance == 2


async def test_spend_unknown_player_is_refused(db: Database) -> None:
    assert await PlayerRepo(db).spend(GUILD, USER, 1) is False


async def test_activate_keeps_first_time(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.activate(GUILD, USER, NOW)
    await repo.activate(GUILD, USER, NOW + timedelta(days=1))
    assert (await repo.get(GUILD, USER)).activated_at == NOW


async def test_bond_name_and_meeting(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.add_bond(GUILD, USER, 10)
    await repo.add_bond(GUILD, USER, 3)
    await repo.set_name(GUILD, USER, "Mira")
    await repo.mark_met(GUILD, USER, NOW)
    player = await repo.get(GUILD, USER)
    assert (player.bond, player.name, player.met_at) == (13, "Mira", NOW)

    await repo.set_name(GUILD, USER, None)
    assert (await repo.get(GUILD, USER)).name is None


async def test_offense_round_trip(db: Database) -> None:
    repo = PlayerRepo(db)
    until = NOW + timedelta(days=7)
    await repo.set_offense(GUILD, USER, 2, until, False)
    player = await repo.get(GUILD, USER)
    assert (player.offenses, player.banned_until) == (2, until)
    assert player.banned_forever is False

    await repo.set_offense(GUILD, USER, 3, None, True)
    player = await repo.get(GUILD, USER)
    assert (player.offenses, player.banned_until) == (3, None)
    assert player.banned_forever is True


async def test_strip_points_never_goes_negative(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.add_points(GUILD, USER, 10)
    await repo.spend(GUILD, USER, 8)
    await repo.strip_points(GUILD, USER, 5)
    player = await repo.get(GUILD, USER)
    assert (player.lifetime_points, player.balance) == (5, 0)
    await repo.strip_points(GUILD, USER, 99)
    player = await repo.get(GUILD, USER)
    assert (player.lifetime_points, player.balance) == (0, 0)


async def test_top_lifetime_orders_limits_and_skips_zero(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.add_points(GUILD, 1, 5)
    await repo.add_points(GUILD, 2, 9)
    await repo.add_points(GUILD, 3, 5)
    await repo.get(GUILD, 4)
    await repo.add_points(OTHER_GUILD, 5, 50)

    top = await repo.top_lifetime(GUILD, 10)
    assert [player.user_id for player in top] == [2, 1, 3]
    assert [player.user_id for player in await repo.top_lifetime(GUILD, 2)] == [2, 1]


# ---
# Activity
# ---


async def test_duplicate_track_feeds_once(db: Database) -> None:
    repo = ActivityRepo(db)
    assert await repo.record_feed(GUILD, 1, USER, track("a"), 1, 900, NOW) is True
    assert (
        await repo.record_feed(GUILD, 1, OTHER_USER, track("a"), 1, 901, NOW) is False
    )
    assert await repo.record_feed(GUILD, 1, USER, track("b"), 1, 902, NOW) is True
    assert await repo.record_feed(OTHER_GUILD, 1, USER, track("a"), 1, 903, NOW) is True


@pytest.mark.parametrize(
    "now",
    [NOW, MIDNIGHT, datetime(2026, 10, 20, 23, 59, 59, tzinfo=UTC)],
)
async def test_daily_counts_reset_at_utc_midnight(db: Database, now: datetime) -> None:
    repo = ActivityRepo(db)
    before = MIDNIGHT - timedelta(seconds=1)
    after = MIDNIGHT + timedelta(days=1)
    await repo.record_interaction(GUILD, 1, USER, InteractionKind.FEED, 10, 4, before)
    await repo.record_interaction(GUILD, 1, USER, InteractionKind.PLAY, 3, 0, before)
    await repo.record_interaction(GUILD, 1, USER, InteractionKind.FEED, 10, 5, MIDNIGHT)
    await repo.record_interaction(GUILD, 1, USER, InteractionKind.SNACK, 1, 2, NOW)
    await repo.record_interaction(GUILD, 1, USER, InteractionKind.PLAY, 3, 0, NOW)
    await repo.record_interaction(GUILD, 1, USER, InteractionKind.FEED, 10, 8, after)

    assert await repo.meal_points_today(GUILD, USER, now) == 7
    assert await repo.casual_bond_today(GUILD, USER, now) == 4
    assert await repo.meal_points_today(GUILD, OTHER_USER, now) == 0
    assert await repo.meal_points_today(OTHER_GUILD, USER, now) == 0


async def test_daily_counts_use_the_utc_day_of_a_local_time(db: Database) -> None:
    repo = ActivityRepo(db)
    await repo.record_interaction(
        GUILD, 1, USER, InteractionKind.FEED, 10, 6, MIDNIGHT - timedelta(hours=1)
    )
    local = datetime(2026, 10, 20, 8, 0, tzinfo=timezone(timedelta(hours=10)))
    assert await repo.meal_points_today(GUILD, USER, local) == 6


async def test_distinct_days(db: Database) -> None:
    repo = ActivityRepo(db)
    assert await repo.distinct_days(GUILD, USER) == 0
    for at in (
        MIDNIGHT,
        NOW,
        MIDNIGHT + timedelta(days=1, hours=5),
        MIDNIGHT + timedelta(days=3),
    ):
        await repo.record_interaction(GUILD, 1, USER, InteractionKind.PLAY, 0, 0, at)
    await repo.record_interaction(GUILD, 1, OTHER_USER, InteractionKind.PLAY, 0, 0, NOW)
    assert await repo.distinct_days(GUILD, USER) == 3


async def test_people_and_caretakers_since(db: Database) -> None:
    repo = ActivityRepo(db)
    since = NOW - timedelta(hours=24)
    kind = InteractionKind.SNACK
    await repo.record_interaction(GUILD, 1, 1, kind, 0, 0, since - timedelta(hours=1))
    await repo.record_interaction(GUILD, 1, 2, kind, 0, 0, since)
    await repo.record_interaction(GUILD, 1, 2, kind, 0, 0, NOW)
    await repo.record_interaction(GUILD, 2, 3, kind, 0, 0, NOW)
    await repo.record_interaction(OTHER_GUILD, 1, 4, kind, 0, 0, NOW)

    assert await repo.people_since(GUILD, since) == 2
    assert await repo.people_since(OTHER_GUILD, since) == 1
    assert await repo.caretakers(GUILD, 1, since) == 1
    assert await repo.caretakers(GUILD, 1, since - timedelta(hours=2)) == 2
    assert await repo.caretakers(GUILD, 2, since) == 1


async def test_top_this_life_orders_by_points(db: Database) -> None:
    repo = ActivityRepo(db)
    await repo.record_feed(GUILD, 1, 10, track("a"), 1, 1, NOW)
    await repo.record_feed(GUILD, 1, 20, track("b", TrackKind.VIIBR), 5, 2, NOW)
    await repo.record_feed(GUILD, 1, 10, track("c", TrackKind.VIIBR), 5, 3, NOW)
    await repo.record_feed(GUILD, 1, 30, track("d"), 1, 4, NOW)
    await repo.record_feed(GUILD, 2, 40, track("e"), 1, 5, NOW)

    assert await repo.top_this_life(GUILD, 1, 10) == [(10, 6), (20, 5), (30, 1)]
    assert await repo.top_this_life(GUILD, 1, 1) == [(10, 6)]
    assert await repo.top_this_life(GUILD, 3, 10) == []


async def test_inventory_add_and_take(db: Database) -> None:
    repo = ActivityRepo(db)
    assert await repo.inventory(GUILD, USER) == {}

    await repo.add_snack(GUILD, USER, "cheese")
    await repo.add_snack(GUILD, USER, "cheese")
    await repo.add_snack(GUILD, USER, "pickles")
    assert await repo.inventory(GUILD, USER) == {"cheese": 2, "pickles": 1}

    assert await repo.take_snack(GUILD, USER, "cheese") is True
    assert await repo.take_snack(GUILD, USER, "pickles") is True
    assert await repo.inventory(GUILD, USER) == {"cheese": 1}


async def test_take_snack_refuses_empty_inventory(db: Database) -> None:
    repo = ActivityRepo(db)
    assert await repo.take_snack(GUILD, USER, "cheese") is False
    await repo.add_snack(GUILD, USER, "cheese")
    assert await repo.take_snack(GUILD, USER, "cheese") is True
    assert await repo.take_snack(GUILD, USER, "cheese") is False
    assert await repo.take_snack(GUILD, OTHER_USER, "cheese") is False
    assert await repo.inventory(GUILD, USER) == {}


async def test_free_snack_used_once_per_utc_day(db: Database) -> None:
    repo = ActivityRepo(db)
    assert await repo.free_snack_used_today(GUILD, USER, NOW) is False

    await repo.record_interaction(GUILD, 1, USER, InteractionKind.SNACK, 1, 5, NOW)
    assert await repo.free_snack_used_today(GUILD, USER, NOW) is False

    free = MIDNIGHT - timedelta(seconds=1)
    await repo.record_interaction(
        GUILD, 1, USER, InteractionKind.FREE_SNACK, 1, 2, free
    )
    assert await repo.free_snack_used_today(GUILD, USER, NOW) is False

    await repo.record_interaction(GUILD, 1, USER, InteractionKind.FREE_SNACK, 1, 2, NOW)
    assert await repo.free_snack_used_today(GUILD, USER, NOW) is True
    assert await repo.free_snack_used_today(GUILD, OTHER_USER, NOW) is False
    assert await repo.casual_bond_today(GUILD, USER, NOW) == 2
