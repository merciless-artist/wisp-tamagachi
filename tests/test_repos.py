"""Tests for the storage repositories, run against the real test database."""

import asyncio
import dataclasses
import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pymysql
import pytest

from db.activity import ActivityRepo, InteractionKind
from db.badges import BadgeRepo, OwnedBadge, PendingBadge
from db.database import Database, to_db_time
from db.keepsakes import KeepsakeKind, KeepsakeRepo
from db.lives import LifeRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import Settings, SettingsRepo
from wisp.bond import PickleStance
from wisp.life import EventKind, Phase, new_egg
from wisp.links import Track, TrackKind
from wisp.rules import CARE_START, COAL_EGG_FOOD, NOTE_MAX_CHARS, NOTES_KEPT, Stage

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


async def test_settings_get_does_not_write(db: Database) -> None:
    repo = SettingsRepo(db)
    assert await repo.get(GUILD) == Settings()
    assert await repo.guilds() == []


async def test_settings_default_then_update(db: Database) -> None:
    repo = SettingsRepo(db)
    assert await repo.get(GUILD) == Settings()
    assert await repo.guilds() == []

    await repo.update(GUILD, tracks_channel_id=55, frozen=True)
    assert await repo.guilds() == [GUILD]
    settings = await repo.get(GUILD)
    assert settings.tracks_channel_id == 55
    assert settings.frozen is True
    assert settings.house_channel_id is None

    await repo.update(GUILD, tracks_channel_id=None)
    assert (await repo.get(GUILD)).tracks_channel_id is None
    assert await repo.get(OTHER_GUILD) == Settings()


async def test_faq_message_ids_round_trip(db: Database) -> None:
    repo = SettingsRepo(db)
    assert (await repo.get(GUILD)).faq_message_ids is None
    big = 1_234_567_890_123_456_789

    await repo.update(GUILD, faq_message_ids=(big, big + 1, 7))
    assert (await repo.get(GUILD)).faq_message_ids == (big, big + 1, 7)
    assert (await SettingsRepo(db).get(GUILD)).faq_message_ids == (big, big + 1, 7)

    await repo.update(GUILD, faq_message_ids=None)
    assert (await SettingsRepo(db).get(GUILD)).faq_message_ids is None


async def test_a_long_faq_id_list_round_trips(db: Database) -> None:
    repo = SettingsRepo(db)
    ids = tuple(1_234_567_890_123_456_789 + number for number in range(500))

    await repo.update(GUILD, faq_message_ids=ids)

    assert (await SettingsRepo(db).get(GUILD)).faq_message_ids == ids


@pytest.mark.parametrize("stored", ["not json", "5", "null", '["a"]', "{}x"])
async def test_unreadable_faq_message_ids_read_as_none_and_are_logged(
    db: Database, caplog: pytest.LogCaptureFixture, stored: str
) -> None:
    repo = SettingsRepo(db)
    await repo.update(GUILD, house_channel_id=5, faq_message_ids=(1, 2))
    await db.execute(
        f"UPDATE {db.t('settings')} SET faq_message_ids = %s WHERE guild_id = %s",
        (stored, GUILD),
    )

    with caplog.at_level(logging.ERROR, logger="wisp"):
        settings = await SettingsRepo(db).get(GUILD)

    assert settings.faq_message_ids is None
    assert settings.house_channel_id == 5
    assert "faq_message_ids" in caplog.text


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


async def test_settings_are_read_once_then_served_from_the_cache(
    db: Database,
) -> None:
    repo = SettingsRepo(db)
    await repo.update(GUILD, tracks_channel_id=55)
    assert (await repo.get(GUILD)).tracks_channel_id == 55

    await db.execute(
        f"UPDATE {db.t('settings')} SET tracks_channel_id = 66 WHERE guild_id = %s",
        (GUILD,),
    )

    assert (await repo.get(GUILD)).tracks_channel_id == 55
    assert (await SettingsRepo(db).get(GUILD)).tracks_channel_id == 66


async def test_update_refreshes_the_cached_settings(db: Database) -> None:
    repo = SettingsRepo(db)
    assert (await repo.get(GUILD)).tracks_channel_id is None

    await repo.update(GUILD, tracks_channel_id=55)

    assert (await repo.get(GUILD)).tracks_channel_id == 55


async def test_a_read_that_overlaps_an_update_is_not_cached(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = SettingsRepo(db)
    await repo.update(GUILD, tracks_channel_id=55)
    fetchone = db.fetchone
    fetched, release = asyncio.Event(), asyncio.Event()

    async def slow_fetchone(query: str, params: Any = ()) -> Any:
        row = await fetchone(query, params)
        fetched.set()
        await release.wait()
        return row

    monkeypatch.setattr(db, "fetchone", slow_fetchone)
    reading = asyncio.ensure_future(repo.get(GUILD))
    await fetched.wait()
    await repo.update(GUILD, tracks_channel_id=66)
    release.set()
    assert (await reading).tracks_channel_id == 55
    monkeypatch.setattr(db, "fetchone", fetchone)

    assert (await repo.get(GUILD)).tracks_channel_id == 66


async def test_cached_settings_cannot_be_changed_by_a_caller(db: Database) -> None:
    repo = SettingsRepo(db)
    settings = await repo.get(GUILD)

    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.frozen = True  # type: ignore[misc]


async def test_roles_are_cached_until_a_role_changes(db: Database) -> None:
    repo = SettingsRepo(db)
    await repo.add_role(GUILD, 7)
    assert await repo.roles(GUILD) == {7}

    await db.execute(
        f"INSERT INTO {db.t('qualifying_roles')} (guild_id, role_id) VALUES (%s, 8)",
        (GUILD,),
    )
    assert await repo.roles(GUILD) == {7}

    await repo.remove_role(GUILD, 7)
    assert await repo.roles(GUILD) == {8}
    await repo.add_role(GUILD, 9)
    assert await repo.roles(GUILD) == {8, 9}


async def test_staff_role_list_round_trip(db: Database) -> None:
    repo = SettingsRepo(db)
    assert await repo.staff_roles(GUILD) == set()

    await repo.add_staff_role(GUILD, 7)
    await repo.add_staff_role(GUILD, 7)
    await repo.add_staff_role(GUILD, 8)
    await repo.add_staff_role(OTHER_GUILD, 9)
    assert await repo.staff_roles(GUILD) == {7, 8}

    await repo.remove_staff_role(GUILD, 7)
    assert await repo.staff_roles(GUILD) == {8}
    assert await repo.staff_roles(OTHER_GUILD) == {9}


async def test_staff_roles_and_feeding_roles_are_separate(db: Database) -> None:
    repo = SettingsRepo(db)
    await repo.add_staff_role(GUILD, 7)
    await repo.add_role(GUILD, 8)

    assert await repo.staff_roles(GUILD) == {7}
    assert await repo.roles(GUILD) == {8}
    await repo.remove_role(GUILD, 7)
    assert await repo.staff_roles(GUILD) == {7}


async def test_staff_roles_are_cached_until_a_staff_role_changes(
    db: Database,
) -> None:
    repo = SettingsRepo(db)
    await repo.add_staff_role(GUILD, 7)
    assert await repo.staff_roles(GUILD) == {7}

    await db.execute(
        f"INSERT INTO {db.t('staff_roles')} (guild_id, role_id) VALUES (%s, 8)",
        (GUILD,),
    )
    assert await repo.staff_roles(GUILD) == {7}

    await repo.remove_staff_role(GUILD, 7)
    assert await repo.staff_roles(GUILD) == {8}
    await repo.add_staff_role(GUILD, 9)
    assert await repo.staff_roles(GUILD) == {8, 9}


async def test_guilds_lists_configured_guilds(db: Database) -> None:
    repo = SettingsRepo(db)
    assert await repo.guilds() == []
    await repo.update(OTHER_GUILD, frozen=False)
    await repo.update(GUILD, frozen=False)
    assert await repo.guilds() == [GUILD, OTHER_GUILD]


# ---
# Latest interactor and keepsake kinds
# ---


async def test_latest_interactor_is_the_last_member_to_interact_with_the_life(
    db: Database,
) -> None:
    repo = ActivityRepo(db)
    assert await repo.latest_interactor(GUILD, 1) is None

    await repo.record_interaction(GUILD, 1, 10, InteractionKind.FEED, 0, 5, NOW)
    await repo.record_interaction(
        GUILD, 1, 11, InteractionKind.PLAY, 0, 0, NOW + timedelta(minutes=5)
    )
    await repo.record_interaction(
        GUILD, 1, 12, InteractionKind.SNACK, 0, 1, NOW - timedelta(minutes=5)
    )
    await repo.record_interaction(
        GUILD, 2, 13, InteractionKind.FEED, 0, 5, NOW + timedelta(hours=1)
    )
    await repo.record_interaction(
        OTHER_GUILD, 1, 14, InteractionKind.FEED, 0, 5, NOW + timedelta(hours=1)
    )

    assert await repo.latest_interactor(GUILD, 1) == 11


async def test_latest_interactor_breaks_a_tie_by_the_later_record(
    db: Database,
) -> None:
    repo = ActivityRepo(db)
    await repo.record_interaction(GUILD, 1, 10, InteractionKind.FEED, 0, 5, NOW)
    await repo.record_interaction(GUILD, 1, 11, InteractionKind.GIFT, 0, 0, NOW)

    assert await repo.latest_interactor(GUILD, 1) == 11


@pytest.mark.parametrize(
    "kind,title",
    [
        (KeepsakeKind.LAST_EMBER, "Wisp v3's Last Ember"),
        (KeepsakeKind.EGGSHELL, "Wisp v3's Eggshell"),
        (KeepsakeKind.FIRST_SPARK, "Wisp v3's First Spark"),
        (KeepsakeKind.TEEN_SPARK, "Wisp v3's Teen Spark"),
        (KeepsakeKind.ADULT_SPARK, "Wisp v3's Adult Spark"),
        (KeepsakeKind.GUITAR_PICK, "Wisp v3's Guitar Pick"),
        (KeepsakeKind.TIME_PIECE, "Wisp v3's Time Piece"),
    ],
)
async def test_every_keepsake_kind_is_stored_and_titled(
    db: Database, kind: KeepsakeKind, title: str
) -> None:
    repo = KeepsakeRepo(db)

    assert await repo.give(GUILD, 1, kind, 3, NOW)

    (kept,) = await repo.of(GUILD, 1)
    assert (kept.kind, kept.title) == (kind, title)


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
    second.full = 42.5
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


async def test_the_food_meter_is_stored_in_the_care_column(db: Database) -> None:
    repo = LifeRepo(db)
    life = await repo.insert(GUILD, new_egg(1, NOW))
    life.full = 42.5
    await repo.save(GUILD, life)

    row = await db.fetchone(
        f"SELECT care FROM {db.t('lives')} WHERE id = %s", (life.id,)
    )
    assert row is not None
    assert row["care"] == 42.5
    loaded = await repo.current(GUILD)
    assert loaded is not None
    assert loaded.full == 42.5


async def test_care_round_trips_through_the_fondness_column(db: Database) -> None:
    repo = LifeRepo(db)
    life = await repo.insert(GUILD, new_egg(1, NOW))
    assert life.care == CARE_START
    life.care = 23.5
    life.lonely_warned = True
    await repo.save(GUILD, life)

    row = await db.fetchone(
        f"SELECT care, fondness, lonely_warned FROM {db.t('lives')} WHERE id = %s",
        (life.id,),
    )
    assert row == {"care": life.full, "fondness": 23.5, "lonely_warned": 1}
    loaded = await repo.current(GUILD)
    assert loaded is not None
    assert (loaded.care, loaded.lonely_warned) == (23.5, True)
    loaded.lonely_warned = False
    await repo.save(GUILD, loaded)
    assert await repo.current(GUILD) == loaded


async def test_the_cold_round_trips(db: Database) -> None:
    repo = LifeRepo(db)
    life = await repo.insert(GUILD, new_egg(1, NOW))
    assert (life.cold_due_at, life.cold_left, life.had_cold) == (None, 0.0, False)
    life.cold_due_at = NOW + timedelta(days=3, hours=5)
    life.cold_left = 4321.5
    life.had_cold = True
    await repo.save(GUILD, life)

    row = await db.fetchone(
        f"SELECT cold_due_at, cold_left, had_cold FROM {db.t('lives')} WHERE id = %s",
        (life.id,),
    )
    assert row is not None
    assert (row["cold_left"], row["had_cold"]) == (4321.5, 1)
    loaded = await repo.current(GUILD)
    assert loaded == life
    loaded.cold_due_at = None
    loaded.cold_left = 0.0
    await repo.save(GUILD, loaded)
    assert await repo.current(GUILD) == loaded


async def test_from_coal_round_trips(db: Database) -> None:
    repo = LifeRepo(db)
    coal = new_egg(1, NOW)
    coal.from_coal = True
    coal.egg_food = COAL_EGG_FOOD
    await repo.insert(GUILD, coal)
    current = await repo.current(GUILD)
    assert current is not None
    assert current.from_coal
    assert current.egg_food == COAL_EGG_FOOD
    current.from_coal = False
    await repo.save(GUILD, current)
    refreshed = await repo.current(GUILD)
    assert refreshed is not None
    assert not refreshed.from_coal


async def test_old_fogey_stage_fits_the_column(db: Database) -> None:
    repo = LifeRepo(db)
    life = await repo.insert(GUILD, new_egg(1, NOW))
    life.phase = Phase.PASSED
    life.stage = Stage.OLD_FOGEY
    life.peak_stage = Stage.ROCKSTAR
    await repo.save(GUILD, life)
    assert await repo.current(GUILD) == life


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


async def test_pickle_stance_round_trip(db: Database) -> None:
    repo = PlayerRepo(db)
    assert (await repo.get(GUILD, USER)).pickle_stance is None

    await repo.set_pickle_stance(GUILD, USER, PickleStance.LOVE)
    assert (await repo.get(GUILD, USER)).pickle_stance is PickleStance.LOVE
    assert (await repo.get(GUILD, OTHER_USER)).pickle_stance is None

    await repo.set_pickle_stance(GUILD, USER, PickleStance.HATE)
    assert (await repo.get(GUILD, USER)).pickle_stance is PickleStance.HATE

    await repo.set_pickle_stance(GUILD, USER, None)
    assert (await repo.get(GUILD, USER)).pickle_stance is None


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


async def test_rhyme_score_only_keeps_a_new_best(db: Database) -> None:
    repo = PlayerRepo(db)
    assert (await repo.get(GUILD, USER)).best_rhyme_score == 0

    assert await repo.record_rhyme_score(GUILD, USER, 0) is False
    assert await repo.record_rhyme_score(GUILD, USER, 6) is True
    assert await repo.record_rhyme_score(GUILD, USER, 6) is False
    assert await repo.record_rhyme_score(GUILD, USER, 4) is False
    assert (await repo.get(GUILD, USER)).best_rhyme_score == 6
    assert await repo.record_rhyme_score(GUILD, USER, 9) is True
    assert (await repo.get(GUILD, USER)).best_rhyme_score == 9
    assert (await repo.get(OTHER_GUILD, USER)).best_rhyme_score == 0


async def test_rhyme_score_for_a_new_player_creates_them(db: Database) -> None:
    repo = PlayerRepo(db)
    assert await repo.record_rhyme_score(GUILD, OTHER_USER, 3) is True
    assert (await repo.get(GUILD, OTHER_USER)).best_rhyme_score == 3


async def test_top_rhyme_orders_limits_and_skips_zero(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.record_rhyme_score(GUILD, 1, 5)
    await repo.record_rhyme_score(GUILD, 2, 9)
    await repo.record_rhyme_score(GUILD, 3, 5)
    await repo.get(GUILD, 4)
    await repo.record_rhyme_score(OTHER_GUILD, 5, 50)

    top = await repo.top_rhyme(GUILD, 10)
    assert [(player.user_id, player.best_rhyme_score) for player in top] == [
        (2, 9),
        (1, 5),
        (3, 5),
    ]
    assert [player.user_id for player in await repo.top_rhyme(GUILD, 2)] == [2, 1]


# ---
# Activity
# ---


async def test_plays_today_counts_only_todays_play(db: Database) -> None:
    repo = ActivityRepo(db)
    for kind, at in [
        (InteractionKind.PLAY, NOW),
        (InteractionKind.PLAY, MIDNIGHT),
        (InteractionKind.SNACK, NOW),
        (InteractionKind.PLAY, MIDNIGHT - timedelta(seconds=1)),
    ]:
        await repo.record_interaction(GUILD, 1, USER, kind, 0, 0, at)
    await repo.record_interaction(GUILD, 1, OTHER_USER, InteractionKind.PLAY, 0, 0, NOW)

    assert await repo.plays_today(GUILD, USER, NOW) == 2
    assert await repo.plays_today(OTHER_GUILD, USER, NOW) == 0


async def test_duplicate_track_feeds_once(db: Database) -> None:
    repo = ActivityRepo(db)
    assert await repo.record_feed(GUILD, 1, USER, track("a"), 1, 900, NOW) is True
    assert (
        await repo.record_feed(GUILD, 1, OTHER_USER, track("a"), 1, 901, NOW) is False
    )
    assert await repo.record_feed(GUILD, 1, USER, track("b"), 1, 902, NOW) is True
    assert await repo.record_feed(OTHER_GUILD, 1, USER, track("a"), 1, 903, NOW) is True


async def test_other_integrity_errors_are_not_reported_as_duplicates(
    db: Database,
) -> None:
    broken = Track(TrackKind.SUNO, "suno:x", None)  # type: ignore[arg-type]
    with pytest.raises(pymysql.err.IntegrityError):
        await ActivityRepo(db).record_feed(GUILD, 1, USER, broken, 1, 1, NOW)


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


def test_db_time_truncates_to_whole_seconds() -> None:
    moment = datetime(2026, 10, 20, 23, 59, 59, 900_000, tzinfo=UTC)
    assert to_db_time(moment) == datetime(2026, 10, 20, 23, 59, 59)


async def test_fraction_of_a_second_stays_in_its_utc_day(db: Database) -> None:
    repo = ActivityRepo(db)
    late = MIDNIGHT - timedelta(microseconds=100_000)
    await repo.record_interaction(GUILD, 1, USER, InteractionKind.FEED, 10, 4, late)
    await repo.record_interaction(
        GUILD, 1, USER, InteractionKind.FREE_SNACK, 1, 2, late
    )

    assert await repo.meal_points_today(GUILD, USER, MIDNIGHT) == 0
    assert await repo.free_snack_used_today(GUILD, USER, MIDNIGHT) is False
    assert await repo.meal_points_today(GUILD, USER, late) == 6
    assert await repo.free_snack_used_today(GUILD, USER, late) is True
    assert await repo.distinct_days(GUILD, USER) == 1


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


async def test_chatted_today_is_once_per_utc_day(db: Database) -> None:
    repo = ActivityRepo(db)
    assert await repo.chatted_today(GUILD, USER, NOW) is False

    await repo.record_interaction(GUILD, 1, USER, InteractionKind.CHAT, 0, 0, NOW)
    await repo.record_interaction(GUILD, 1, OTHER_USER, InteractionKind.PLAY, 0, 0, NOW)
    await repo.record_interaction(
        GUILD, 1, 3, InteractionKind.CHAT, 0, 0, MIDNIGHT - timedelta(seconds=1)
    )

    assert await repo.chatted_today(GUILD, USER, NOW) is True
    assert await repo.chatted_today(GUILD, USER, MIDNIGHT + timedelta(days=1)) is False
    assert await repo.chatted_today(GUILD, OTHER_USER, NOW) is False
    assert await repo.chatted_today(GUILD, 3, NOW) is False
    assert await repo.chatted_today(OTHER_GUILD, USER, NOW) is False


async def test_chatters_since_counts_only_chats(db: Database) -> None:
    repo = ActivityRepo(db)
    since = NOW - timedelta(hours=24)
    chat = InteractionKind.CHAT
    await repo.record_interaction(GUILD, 1, 1, chat, 0, 0, since - timedelta(hours=1))
    await repo.record_interaction(GUILD, 1, 2, chat, 0, 0, since)
    await repo.record_interaction(GUILD, 1, 2, chat, 0, 0, NOW)
    await repo.record_interaction(GUILD, 1, 3, chat, 0, 0, NOW)
    await repo.record_interaction(GUILD, 1, 4, InteractionKind.FEED, 10, 5, NOW)
    await repo.record_interaction(GUILD, 1, 5, InteractionKind.PLAY, 3, 0, NOW)
    await repo.record_interaction(OTHER_GUILD, 1, 6, chat, 0, 0, NOW)

    assert await repo.chatters_since(GUILD, since) == 2
    assert await repo.chatters_since(OTHER_GUILD, since) == 1
    assert await repo.chatters_since(GUILD, NOW + timedelta(seconds=1)) == 0


async def test_feeders_since_counts_only_feeding(db: Database) -> None:
    repo = ActivityRepo(db)
    since = NOW - timedelta(hours=24)
    for user, kind in [
        (1, InteractionKind.FEED),
        (2, InteractionKind.SNACK),
        (3, InteractionKind.FREE_SNACK),
        (3, InteractionKind.FEED),
        (4, InteractionKind.PLAY),
        (5, InteractionKind.GIFT),
        (6, InteractionKind.CHAT),
    ]:
        await repo.record_interaction(GUILD, 1, user, kind, 0, 0, NOW)
    await repo.record_interaction(
        GUILD, 1, 7, InteractionKind.FEED, 0, 0, since - timedelta(seconds=1)
    )
    await repo.record_interaction(OTHER_GUILD, 1, 8, InteractionKind.FEED, 0, 0, NOW)

    assert await repo.feeders_since(GUILD, since) == 3
    assert await repo.feeders_since(OTHER_GUILD, since) == 1


async def test_chat_rows_do_not_count_as_caretakers_or_last_interactor(
    db: Database,
) -> None:
    repo = ActivityRepo(db)
    since = NOW - timedelta(hours=24)
    await repo.record_interaction(GUILD, 1, 1, InteractionKind.SNACK, 1, 2, NOW)
    await repo.record_interaction(
        GUILD, 1, 2, InteractionKind.CHAT, 0, 0, NOW + timedelta(minutes=1)
    )
    await repo.record_interaction(
        GUILD, 2, 3, InteractionKind.CHAT, 0, 0, NOW + timedelta(minutes=2)
    )

    assert await repo.caretakers(GUILD, 1, since) == 1
    assert await repo.caretakers(GUILD, 2, since) == 0
    assert await repo.latest_interactor(GUILD, 1) == 1
    assert await repo.latest_interactor(GUILD, 2) is None


async def test_chats_still_count_as_activity_and_toward_meeting(
    db: Database,
) -> None:
    repo = ActivityRepo(db)
    since = NOW - timedelta(hours=24)
    for at in (MIDNIGHT, MIDNIGHT + timedelta(days=1)):
        await repo.record_interaction(GUILD, 1, USER, InteractionKind.CHAT, 0, 0, at)

    assert await repo.people_since(GUILD, since) == 1
    assert await repo.distinct_days(GUILD, USER) == 2
    assert await repo.meal_points_today(GUILD, USER, NOW) == 0
    assert await repo.casual_bond_today(GUILD, USER, NOW) == 0


async def test_tracks_today_splits_viibr_and_suno(db: Database) -> None:
    repo = ActivityRepo(db)
    feeds = [
        (GUILD, track("a", TrackKind.VIIBR), NOW),
        (GUILD, track("b", TrackKind.VIIBR), MIDNIGHT),
        (GUILD, track("c", TrackKind.SUNO), NOW),
        (GUILD, track("d", TrackKind.SUNO), NOW),
        (GUILD, track("e", TrackKind.SUNO), NOW),
        (GUILD, track("f", TrackKind.VIIBR), MIDNIGHT - timedelta(seconds=1)),
        (GUILD, track("g", TrackKind.SUNO), MIDNIGHT + timedelta(days=1)),
        (OTHER_GUILD, track("h", TrackKind.VIIBR), NOW),
    ]
    for index, (guild, fed, at) in enumerate(feeds):
        await repo.record_feed(guild, 1, USER, fed, 1, 900 + index, at)

    assert await repo.tracks_today(GUILD, NOW) == (2, 3)
    assert await repo.tracks_today(OTHER_GUILD, NOW) == (1, 0)
    assert await repo.tracks_today(GUILD, MIDNIGHT + timedelta(days=5)) == (0, 0)


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


async def test_fed_this_life_sums_one_members_feeds_of_one_life(
    db: Database,
) -> None:
    repo = ActivityRepo(db)
    await repo.record_feed(GUILD, 1, 10, track("a"), 1, 1, NOW)
    await repo.record_feed(GUILD, 1, 10, track("b", TrackKind.VIIBR), 5, 2, NOW)
    await repo.record_feed(GUILD, 1, 20, track("c"), 1, 3, NOW)
    await repo.record_feed(GUILD, 2, 10, track("d"), 1, 4, NOW)
    await repo.record_feed(OTHER_GUILD, 1, 10, track("e"), 1, 5, NOW)

    assert await repo.fed_this_life(GUILD, 1, 10) == 6
    assert await repo.fed_this_life(GUILD, 1, 20) == 1
    assert await repo.fed_this_life(GUILD, 1, 30) == 0
    assert await repo.fed_this_life(GUILD, 3, 10) == 0


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


# ---
# Keepsakes
# ---


async def test_keepsake_given_once_per_version(db: Database) -> None:
    repo = KeepsakeRepo(db)
    ember = KeepsakeKind.LAST_EMBER
    later = NOW + timedelta(days=3)

    assert await repo.give(GUILD, USER, ember, 4, later) is True
    assert await repo.give(GUILD, USER, ember, 3, NOW) is True
    assert await repo.give(GUILD, USER, ember, 3, later) is False

    keepsakes = await repo.of(GUILD, USER)
    assert [(item.kind, item.version, item.given_at) for item in keepsakes] == [
        (ember, 3, NOW),
        (ember, 4, later),
    ]
    assert [item.title for item in keepsakes] == [
        "Wisp v3's Last Ember",
        "Wisp v4's Last Ember",
    ]


async def test_keepsakes_read_by_version_then_in_the_order_given(
    db: Database,
) -> None:
    repo = KeepsakeRepo(db)
    for kind, version, minutes in (
        (KeepsakeKind.TEEN_SPARK, 2, 30),
        (KeepsakeKind.LAST_EMBER, 1, 90),
        (KeepsakeKind.EGGSHELL, 2, 0),
        (KeepsakeKind.TIME_PIECE, 1, 60),
        (KeepsakeKind.FIRST_SPARK, 2, 10),
    ):
        await repo.give(GUILD, USER, kind, version, NOW + timedelta(minutes=minutes))

    assert [(item.version, item.kind) for item in await repo.of(GUILD, USER)] == [
        (1, KeepsakeKind.TIME_PIECE),
        (1, KeepsakeKind.LAST_EMBER),
        (2, KeepsakeKind.EGGSHELL),
        (2, KeepsakeKind.FIRST_SPARK),
        (2, KeepsakeKind.TEEN_SPARK),
    ]


async def test_keepsakes_are_per_member_and_guild(db: Database) -> None:
    repo = KeepsakeRepo(db)
    ember = KeepsakeKind.LAST_EMBER
    assert await repo.give(GUILD, USER, ember, 3, NOW) is True
    assert await repo.give(GUILD, OTHER_USER, ember, 3, NOW) is True
    assert await repo.give(OTHER_GUILD, USER, ember, 3, NOW) is True

    assert [item.version for item in await repo.of(GUILD, USER)] == [3]
    assert await repo.of(GUILD, 99) == []
    assert await repo.of(OTHER_GUILD, OTHER_USER) == []


async def test_other_integrity_errors_are_not_reported_as_already_given(
    db: Database,
) -> None:
    with pytest.raises(pymysql.err.IntegrityError):
        await KeepsakeRepo(db).give(
            GUILD, USER, KeepsakeKind.LAST_EMBER, None, NOW  # type: ignore[arg-type]
        )


# ---
# Notes
# ---


async def test_notes_keep_only_the_newest(db: Database) -> None:
    repo = NoteRepo(db)
    await repo.add(GUILD, OTHER_USER, "someone else", NOW)
    await repo.add(OTHER_GUILD, USER, "another server", NOW)
    notes = [f"fact {index}" for index in range(NOTES_KEPT + 2)]
    for index, note in enumerate(notes):
        await repo.add(GUILD, USER, note, NOW + timedelta(minutes=index))

    assert await repo.recent(GUILD, USER) == notes[2:]
    assert await repo.recent(GUILD, OTHER_USER) == ["someone else"]
    assert await repo.recent(OTHER_GUILD, USER) == ["another server"]
    assert await repo.recent(GUILD, 99) == []


async def test_notes_in_the_same_second_keep_their_order(db: Database) -> None:
    repo = NoteRepo(db)
    for note in ("first", "second", "third"):
        await repo.add(GUILD, USER, note, NOW)
    assert await repo.recent(GUILD, USER) == ["first", "second", "third"]


async def test_notes_are_truncated(db: Database) -> None:
    repo = NoteRepo(db)
    await repo.add(GUILD, USER, "x" * (NOTE_MAX_CHARS + 50), NOW)
    assert await repo.recent(GUILD, USER) == ["x" * NOTE_MAX_CHARS]


async def test_refund_restores_the_balance_only(db: Database) -> None:
    repo = PlayerRepo(db)
    await repo.add_points(GUILD, USER, 30)
    assert await repo.spend(GUILD, USER, 25)

    await repo.refund(GUILD, USER, 25)

    player = await repo.get(GUILD, USER)
    assert (player.balance, player.lifetime_points) == (30, 30)


async def test_badge_roles_are_stored_per_guild_and_replaced(db: Database) -> None:
    repo = BadgeRepo(db)
    await repo.set_role(GUILD, "team_wisp", 11)
    await repo.set_role(GUILD, "egg_warmer", 12)
    await repo.set_role(OTHER_GUILD, "team_wisp", 21)
    await repo.set_role(GUILD, "team_wisp", 13)

    assert await repo.role_ids(GUILD) == {"team_wisp": 13, "egg_warmer": 12}
    assert await repo.role_ids(OTHER_GUILD) == {"team_wisp": 21}
    assert await repo.role_ids(99) == {}


async def test_a_badge_is_bought_once_per_life(db: Database) -> None:
    repo = BadgeRepo(db)
    assert await repo.record(GUILD, USER, "team_wisp", 1, 3, NOW)
    assert not await repo.record(GUILD, USER, "team_wisp", 1, 3, NOW)
    assert await repo.record(GUILD, USER, "team_wisp", 2, 4, NOW)
    assert await repo.record(GUILD, USER, "egg_warmer", 1, 3, NOW)

    assert await repo.owned(GUILD, USER, 1) == {"team_wisp", "egg_warmer"}
    assert await repo.owned(GUILD, USER, 2) == {"team_wisp"}
    assert await repo.owned(GUILD, OTHER_USER, 1) == set()


async def test_a_forgotten_purchase_is_gone(db: Database) -> None:
    repo = BadgeRepo(db)
    await repo.record(GUILD, USER, "team_wisp", 1, 3, NOW)
    await repo.record(GUILD, USER, "egg_warmer", 1, 3, NOW)

    await repo.forget(GUILD, USER, "team_wisp", 1)

    assert await repo.owned(GUILD, USER, 1) == {"egg_warmer"}
    assert await repo.record(GUILD, USER, "team_wisp", 1, 3, NOW)


async def test_badges_of_a_member_come_newest_life_first(db: Database) -> None:
    repo = BadgeRepo(db)
    await repo.record(GUILD, USER, "egg_warmer", 1, 3, NOW)
    await repo.record(GUILD, USER, "team_wisp", 2, 4, NOW)
    await repo.record(GUILD, USER, "flame_keeper", 2, 4, NOW + timedelta(hours=1))
    await repo.record(GUILD, OTHER_USER, "bandmate", 2, 4, NOW)

    assert await repo.of(GUILD, USER) == [
        OwnedBadge("flame_keeper", 4, NOW + timedelta(hours=1)),
        OwnedBadge("team_wisp", 4, NOW),
        OwnedBadge("egg_warmer", 3, NOW),
    ]
    assert await repo.of(OTHER_GUILD, USER) == []


async def ended_life(db: Database, version: int, ended: bool) -> int:
    life = new_egg(version, NOW)
    if ended:
        life.phase = Phase.DEAD
        life.ended_at = NOW
    inserted = await LifeRepo(db).insert(GUILD, life)
    assert inserted.id is not None
    return inserted.id


async def test_pending_badges_are_the_unmarked_ones_of_ended_lives(
    db: Database,
) -> None:
    repo = BadgeRepo(db)
    gone = await ended_life(db, 1, ended=True)
    living = await ended_life(db, 2, ended=False)
    await repo.record(GUILD, USER, "egg_warmer", gone, 1, NOW)
    await repo.record(GUILD, USER, "team_wisp", gone, 1, NOW)
    await repo.record(GUILD, OTHER_USER, "team_wisp", gone, 1, NOW)
    await repo.record(GUILD, USER, "bandmate", living, 2, NOW)

    assert await repo.pending(GUILD) == [
        PendingBadge(USER, "egg_warmer", gone, 1),
        PendingBadge(USER, "team_wisp", gone, 1),
        PendingBadge(OTHER_USER, "team_wisp", gone, 1),
    ]

    await repo.mark_removed(GUILD, USER, gone, {"egg_warmer", "team_wisp"}, NOW)

    assert await repo.pending(GUILD) == [PendingBadge(OTHER_USER, "team_wisp", gone, 1)]
    assert await repo.pending(OTHER_GUILD) == []
    assert [badge.badge for badge in await repo.of(GUILD, USER)] == [
        "bandmate",
        "egg_warmer",
        "team_wisp",
    ]


async def test_a_badge_bought_again_retires_its_older_purchases(db: Database) -> None:
    repo = BadgeRepo(db)
    first = await ended_life(db, 1, ended=True)
    second = await ended_life(db, 2, ended=True)
    current = await ended_life(db, 3, ended=False)
    await repo.record(GUILD, USER, "egg_warmer", first, 1, NOW)
    await repo.record(GUILD, USER, "egg_warmer", second, 2, NOW)
    await repo.record(GUILD, USER, "team_wisp", second, 2, NOW)
    await repo.record(GUILD, OTHER_USER, "egg_warmer", second, 2, NOW)
    await repo.record(GUILD, USER, "egg_warmer", current, 3, NOW)

    await repo.retire_older(GUILD, USER, "egg_warmer", current, NOW)

    assert await repo.pending(GUILD) == [
        PendingBadge(USER, "team_wisp", second, 2),
        PendingBadge(OTHER_USER, "egg_warmer", second, 2),
    ]
