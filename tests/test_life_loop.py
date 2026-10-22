"""Tests for the life loop and the live status card.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest

import app
from cogs import life_loop
from cogs.life_loop import LifeLoop
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.bond import happiness
from wisp.card import render_status
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.rules import Stage

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
ERRORS_ID = 40
STATUS_ID = 60
BILLBOARD_ID = 61
CARD_ID = 777
BILLBOARD_MESSAGE_ID = 778
REPOSTED_CARD_ID = 888
USER_ID = 1
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
FULL_GAP = rules.MAX_CREDITED_GAP

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House, an errors channel and the Status thread."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.errors = MagicMock(spec=discord.TextChannel)
        self.errors.send = AsyncMock()
        self.card = MagicMock(spec=discord.Message)
        self.card.id = REPOSTED_CARD_ID
        self.card.pin = AsyncMock()
        self.card_edit: Any = AsyncMock()
        self.status = MagicMock(spec=discord.Thread)
        self.status.id = STATUS_ID
        self.status.parent_id = FORUM_ID
        self.status.archived = False
        self.status.send = AsyncMock(return_value=self.card)
        self.partial = MagicMock(spec=discord.PartialMessage)
        self.partial.edit = self.card_edit
        self.status.get_partial_message.return_value = self.partial
        self.billboard_edit: Any = AsyncMock()
        self.billboard = MagicMock(spec=discord.Thread)
        self.billboard.id = BILLBOARD_ID
        self.billboard.parent_id = FORUM_ID
        self.billboard.archived = False
        self.billboard.get_partial_message.return_value = MagicMock(
            spec=discord.PartialMessage, edit=self.billboard_edit
        )
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house, ERRORS_ID: self.errors}
        self.guild.get_channel_or_thread.side_effect = channels.get

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        threads = {STATUS_ID: self.status, BILLBOARD_ID: self.billboard}
        if channel_id not in threads:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return threads[channel_id]


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def bot(
    db: Database, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture
def cog(bot: app.WispBot) -> LifeLoop:
    return LifeLoop(bot)


async def configure(bot: app.WispBot, *, frozen: bool = False) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        error_channel_id=ERRORS_ID,
        status_thread_id=STATUS_ID,
        status_message_id=CARD_ID,
        billboard_thread_id=BILLBOARD_ID,
        billboard_message_id=BILLBOARD_MESSAGE_ID,
        frozen=frozen,
    )


async def lay(
    bot: app.WispBot,
    *,
    phase: Phase = Phase.ALIVE,
    care: float = 50.0,
    version: int = 1,
    gap: timedelta = FULL_GAP,
    phase_seconds: float = 0.0,
) -> Life:
    """Insert a life whose last tick was `gap` before NOW."""
    life = new_egg(version, NOW - gap)
    life.phase = phase
    life.care = care
    life.phase_seconds = phase_seconds
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.BABY
        life.hatched_at = life.stage_started_at = NOW - timedelta(hours=1)
    return await bot.lives.insert(GUILD_ID, life)


async def interact(bot: app.WispBot, life: Life, at: datetime) -> None:
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID, life.id, USER_ID, InteractionKind.PLAY, 0, 0, at
    )


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


def house_texts(server: FakeServer) -> list[str]:
    return [call.args[0] for call in server.house.send.await_args_list]


def mentions_version(text: str, version: int) -> bool:
    return re.search(rf"(?<!\d){version}(?!\d)", text) is not None


# ---
# First run
# ---


async def test_first_run_lays_egg_v1(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase, egg.last_tick_at) == (1, Phase.EGG, NOW)
    server.house.send.assert_awaited_once()
    assert mentions_version(house_texts(server)[0], 1)
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    content = server.card_edit.await_args.kwargs["content"]
    assert content.startswith("♪ WISP v1 ・ EGG")


async def test_unconfigured_guilds_are_skipped_silently(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.update(GUILD_ID + 1, status_thread_id=STATUS_ID)

    await cog.run_tick(NOW)

    assert await bot.lives.current(GUILD_ID) is None
    assert await bot.lives.current(GUILD_ID + 1) is None
    server.house.send.assert_not_awaited()
    server.errors.send.assert_not_awaited()


# ---
# Status card
# ---


async def test_tick_edits_status_message(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await interact(bot, life, NOW - timedelta(hours=2))

    await cog.run_tick(NOW)

    after = await current_life(bot)
    assert after.last_tick_at == NOW
    assert after.care < 50.0
    server.status.get_partial_message.assert_called_once_with(CARD_ID)
    server.card_edit.assert_awaited_once()
    kwargs = server.card_edit.await_args.kwargs
    assert kwargs["content"] == render_status(
        after, NOW, happiness=happiness(1), fed_today=1
    )
    assert kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    server.status.send.assert_not_awaited()
    server.house.send.assert_not_awaited()


async def test_fed_today_counts_only_the_current_utc_day(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await interact(bot, life, NOW.replace(hour=0, minute=0) - timedelta(minutes=1))

    await cog.run_tick(NOW)

    after = await current_life(bot)
    assert server.card_edit.await_args.kwargs["content"] == render_status(
        after, NOW, happiness=happiness(1), fed_today=0
    )


async def test_missing_status_message_is_reposted(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.card_edit.side_effect = discord.NotFound(
        MagicMock(status=404), "Unknown Message"
    )

    await cog.run_tick(NOW)

    server.status.send.assert_awaited_once()
    (text,) = server.status.send.await_args.args
    assert text.startswith("♪ WISP v1 ・ BABY")
    assert server.status.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    server.card.pin.assert_awaited_once()
    stored = (await bot.settings.get(GUILD_ID)).status_message_id
    assert stored == REPOSTED_CARD_ID
    server.errors.send.assert_not_awaited()


async def test_card_is_posted_when_none_is_stored(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await bot.settings.update(GUILD_ID, status_message_id=None)
    await lay(bot)

    await cog.run_tick(NOW)

    server.card_edit.assert_not_awaited()
    server.status.send.assert_awaited_once()
    assert (await bot.settings.get(GUILD_ID)).status_message_id == REPOSTED_CARD_ID


async def test_pin_failure_is_reported_and_the_card_kept(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.card_edit.side_effect = discord.NotFound(
        MagicMock(status=404), "Unknown Message"
    )
    server.card.pin.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await cog.run_tick(NOW)

    assert (await bot.settings.get(GUILD_ID)).status_message_id == REPOSTED_CARD_ID
    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report.startswith("Error in pinning the status card: Forbidden")


async def test_forbidden_card_edit_is_reported_and_the_tick_kept(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.card_edit.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Access"
    )

    await cog.run_tick(NOW)

    assert (await current_life(bot)).last_tick_at == NOW
    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report.startswith("Error in updating the status card: Forbidden")


async def test_card_failure_is_reported_once_per_streak(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    forbidden = discord.Forbidden(MagicMock(status=403), "Missing Access")
    server.card_edit.side_effect = forbidden

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + FULL_GAP)
    assert server.errors.send.await_count == 1

    server.card_edit.side_effect = None
    await cog.run_tick(NOW + 2 * FULL_GAP)
    server.card_edit.side_effect = forbidden
    await cog.run_tick(NOW + 3 * FULL_GAP)

    assert server.errors.send.await_count == 2


# ---
# Billboard
# ---


async def test_tick_refreshes_the_billboard_after_the_status_card(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await bot.players.add_points(GUILD_ID, USER_ID, 5)
    await interact(bot, life, NOW - timedelta(hours=2))
    order: list[str] = []
    server.card_edit.side_effect = lambda **_: order.append("card")
    server.billboard_edit.side_effect = lambda **_: order.append("billboard")

    await cog.run_tick(NOW)

    assert order == ["card", "billboard"]
    content = server.billboard_edit.await_args.kwargs["content"]
    assert content.startswith("♪ The Billboard")
    assert f"<@{USER_ID}>" in content


async def test_billboard_failure_is_reported_without_losing_the_card(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.billboard_edit.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Access"
    )

    await cog.run_tick(NOW)

    server.card_edit.assert_awaited_once()
    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report.startswith("Error in updating the Billboard: Forbidden")


# ---
# Events
# ---


async def test_death_posts_died_then_new_egg_with_next_version(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot, care=0.01)

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase) == (2, Phase.EGG)
    died, laid = house_texts(server)
    assert mentions_version(died, 1)
    assert mentions_version(laid, 2)
    content = server.card_edit.await_args.kwargs["content"]
    assert content.startswith("♪ WISP v2 ・ EGG")


async def test_cold_egg_uses_up_version(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    nearly_cold = rules.EGG_WARMTH.total_seconds() - 1
    await lay(bot, phase=Phase.EGG, care=0.0, phase_seconds=nearly_cold)

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase) == (2, Phase.EGG)
    cold = (await bot.lives.history(GUILD_ID))[-1]
    assert (cold.version, cold.phase, cold.ended_at) == (1, Phase.COLD, NOW)
    assert len(house_texts(server)) == 2
    assert await bot.lives.next_version(GUILD_ID) == 3


async def test_finished_life_is_replaced_by_next_egg(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot, phase=Phase.DEAD, care=0.0)

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase) == (2, Phase.EGG)
    (laid,) = house_texts(server)
    assert mentions_version(laid, 2)
    assert not mentions_version(laid, 1)
    content = server.card_edit.await_args.kwargs["content"]
    assert content.startswith("♪ WISP v2 ・ EGG")

    await cog.run_tick(NOW + FULL_GAP)

    assert (await current_life(bot)).version == 2
    server.house.send.assert_awaited_once()


async def test_frozen_guild_does_not_drain(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot, frozen=True)
    await lay(bot, care=50.0)

    await cog.run_tick(NOW)

    life = await current_life(bot)
    assert life.care == 50.0
    assert life.phase_seconds == 0.0
    assert life.last_tick_at == NOW
    server.house.send.assert_not_awaited()
    server.card_edit.assert_awaited_once()


# ---
# Quiet
# ---


async def test_quiet_line_once_per_stretch(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot, gap=timedelta(minutes=5))

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + timedelta(minutes=5))
    assert server.house.send.await_count == 1

    await interact(bot, life, NOW + timedelta(minutes=6))
    await cog.run_tick(NOW + timedelta(minutes=10))
    assert server.house.send.await_count == 1

    await cog.run_tick(NOW + timedelta(minutes=10) + rules.QUIET_AFTER)
    assert server.house.send.await_count == 2
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )


async def test_no_quiet_line_before_the_quiet_time(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await interact(bot, life, NOW - rules.QUIET_AFTER + timedelta(seconds=1))

    await cog.run_tick(NOW)

    server.house.send.assert_not_awaited()


async def test_no_quiet_line_while_frozen(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot, frozen=True)
    await lay(bot)

    await cog.run_tick(NOW)

    server.house.send.assert_not_awaited()


async def test_no_quiet_line_for_an_egg(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot, phase=Phase.EGG, care=0.0)

    await cog.run_tick(NOW)

    server.house.send.assert_not_awaited()


@pytest.mark.parametrize(("care", "expected"), [(80.0, Mood.HAPPY), (5.0, Mood.HANGRY)])
async def test_quiet_line_matches_his_mood(
    cog: LifeLoop,
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    care: float,
    expected: Mood,
) -> None:
    await configure(bot)
    await lay(bot, care=care, version=3)
    picked: list[tuple[Moment, Mood, dict[str, str]]] = []

    def pick(moment: Moment, mood: Mood, **fields: str) -> str:
        picked.append((moment, mood, fields))
        return "line"

    monkeypatch.setattr(bot.lines, "pick", pick)

    await cog.run_tick(NOW)

    assert [(m, mood) for m, mood, _ in picked if m is Moment.QUIET] == [
        (Moment.QUIET, expected)
    ]


# ---
# Guild isolation
# ---


async def test_failing_guild_is_reported_and_the_next_one_still_ticks(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken_id = GUILD_ID - 1
    broken_guild = MagicMock(spec=discord.Guild)
    broken_guild.id = broken_id
    guilds = {broken_id: broken_guild, GUILD_ID: server.guild}
    monkeypatch.setattr(bot, "get_guild", guilds.get)
    for guild_id in guilds:
        await bot.settings.update(
            guild_id,
            house_channel_id=HOUSE_ID,
            studio_forum_id=FORUM_ID,
            error_channel_id=ERRORS_ID,
            status_thread_id=STATUS_ID,
            status_message_id=CARD_ID,
            billboard_thread_id=BILLBOARD_ID,
            billboard_message_id=BILLBOARD_MESSAGE_ID,
        )
    await lay(bot)
    current = bot.lives.current

    async def current_or_fail(guild_id: int) -> Life | None:
        if guild_id == broken_id:
            raise pymysql.err.OperationalError(2013, "Lost connection")
        return await current(guild_id)

    monkeypatch.setattr(bot.lives, "current", current_or_fail)
    reported: Any = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + FULL_GAP)

    assert (await current_life(bot)).last_tick_at == NOW + FULL_GAP
    assert reported.await_count == 2
    for call in reported.await_args_list:
        guild, context, error = call.args
        assert guild is broken_guild
        assert context == "life loop"
        assert isinstance(error, pymysql.err.OperationalError)


async def test_discord_failure_in_one_guild_is_reported_with_that_guild(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await configure(bot)
    await lay(bot)
    forbidden = discord.Forbidden(MagicMock(status=403), "Missing Access")
    monkeypatch.setattr(life_loop, "post_events", AsyncMock(side_effect=forbidden))
    reported: Any = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await cog.run_tick(NOW)

    reported.assert_awaited_once_with(server.guild, "life loop", forbidden)


async def test_guild_the_bot_cannot_see_is_skipped(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await configure(bot)
    await lay(bot, care=50.0)
    monkeypatch.setattr(bot, "get_guild", lambda _id: None)

    await cog.run_tick(NOW)

    life = await current_life(bot)
    assert life.last_tick_at == NOW - FULL_GAP
    server.house.send.assert_not_awaited()
    server.card_edit.assert_not_awaited()
    server.errors.send.assert_not_awaited()


# ---
# The loop
# ---


async def test_loop_error_is_reported_and_loop_continues(
    cog: LifeLoop,
    bot: app.WispBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = 0
    recovered = asyncio.Event()
    reported: Any = AsyncMock()

    async def flaky(now: datetime) -> None:
        nonlocal ticks
        ticks += 1
        if ticks == 1:
            raise RuntimeError("database went away")
        recovered.set()

    monkeypatch.setattr(cog, "run_tick", flaky)
    monkeypatch.setattr(bot, "report_error", reported)
    monkeypatch.setattr(bot, "wait_until_ready", AsyncMock())
    monkeypatch.setattr(life_loop, "TICK_EVERY", timedelta(milliseconds=10))
    cog.tick_loop.change_interval(seconds=0.01)

    await cog.cog_load()
    try:
        await asyncio.wait_for(recovered.wait(), timeout=5)
    finally:
        await cog.cog_unload()

    reported.assert_awaited_once()
    guild, context, error = reported.await_args.args
    assert guild is None
    assert context == "life loop"
    assert isinstance(error, RuntimeError)
    assert ticks >= 2


async def test_loop_waits_before_restarting_after_an_error(
    cog: LifeLoop, bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = AsyncMock(side_effect=RuntimeError("bug"))
    monkeypatch.setattr(cog, "run_tick", ticks)
    monkeypatch.setattr(bot, "wait_until_ready", AsyncMock())
    monkeypatch.setattr(bot, "report_error", AsyncMock())

    await cog.cog_load()
    await asyncio.sleep(0.2)
    await cog.cog_unload()
    await asyncio.sleep(0.05)

    assert ticks.await_count == 1
    assert not cog.tick_loop.is_running()


async def test_unload_stops_the_loop(
    cog: LifeLoop, bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot, "wait_until_ready", AsyncMock())
    monkeypatch.setattr(cog, "run_tick", AsyncMock())

    await cog.cog_load()
    assert cog.tick_loop.is_running()
    await cog.cog_unload()
    await asyncio.sleep(0)

    assert not cog.tick_loop.is_running()


def test_the_loop_runs_every_tick_interval(cog: LifeLoop) -> None:
    assert cog.tick_loop.seconds == rules.TICK_EVERY.total_seconds()


async def test_cog_is_registered_and_set_up(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_cog: Any = AsyncMock()
    monkeypatch.setattr(bot, "add_cog", add_cog)

    await life_loop.setup(bot)

    assert "cogs.life_loop" in app.EXTENSIONS
    (added,) = add_cog.await_args.args
    assert isinstance(added, LifeLoop)
