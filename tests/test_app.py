import logging
from collections.abc import Iterator
from dataclasses import fields
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import discord
import pymysql
import pytest
from discord import app_commands
from discord.ext import commands

import app
from cogs import groups
from db.settings import Settings
from wisp.text import USER_ERROR


@pytest.fixture
def bot() -> Iterator[app.WispBot]:
    yield app.WispBot()


def make_channel() -> MagicMock:
    return MagicMock(spec=discord.TextChannel)


def make_guild(channel: MagicMock | None, guild_id: int = 7) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.get_channel_or_thread.return_value = channel
    return guild


def make_interaction(response_done: bool, guild: MagicMock | None) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.channel = make_channel()
    interaction.command = MagicMock()
    interaction.command.qualified_name = "wisp feed"
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = response_done
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_emoji(text: str) -> MagicMock:
    emoji = MagicMock(spec=discord.Emoji)
    emoji.__str__.return_value = text  # type: ignore[attr-defined]
    return emoji


# ---
# Configuration
# ---


def test_intents_ignore_direct_messages_and_privileged_extras(
    bot: app.WispBot,
) -> None:
    intents = bot.intents
    assert intents.message_content
    assert not (intents.dm_messages or intents.dm_reactions or intents.dm_typing)
    assert not (intents.members or intents.presences)
    assert intents.guild_messages


def test_no_text_commands_are_registered(bot: app.WispBot) -> None:
    assert bot.help_command is None
    assert not bot.commands


def test_every_send_pings_nobody_by_default(bot: app.WispBot) -> None:
    mentions = bot.allowed_mentions
    assert mentions is not None
    assert mentions.to_dict() == discord.AllowedMentions.none().to_dict()


# ---
# Direct messages
# ---


async def test_direct_messages_are_ignored(bot: app.WispBot) -> None:
    repos = {
        name: MagicMock() for name in ("settings", "lives", "players", "activity_log")
    }
    for name, repo in repos.items():
        setattr(bot, name, repo)
    message = MagicMock(spec=discord.Message)
    message.guild = None

    await bot.on_message(message)

    assert all(repo.mock_calls == [] for repo in repos.values())


# ---
# Application emojis
# ---


def test_missing_emoji_returns_empty_and_logs_once(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="wisp"):
        assert bot.emoji("wisp_happy") == ""
        assert bot.emoji("wisp_happy") == ""
        assert bot.emoji("wisp_sad") == ""

    missing = [r.getMessage() for r in caplog.records if "emoji" in r.getMessage()]
    assert len(missing) == 2
    assert "wisp_happy" in missing[0]
    assert "wisp_sad" in missing[1]


def test_known_emoji_returns_its_text(bot: app.WispBot) -> None:
    bot.emojis_by_name["wisp_happy"] = make_emoji("<:wisp_happy:123>")
    assert bot.emoji("wisp_happy") == "<:wisp_happy:123>"


# ---
# Error reporting
# ---

HOUSE_ID = 555
TRACKS_ID = 777
NO_PING = discord.AllowedMentions.none().to_dict()


def configured(bot: app.WispBot) -> AsyncMock:
    """Give the bot settings with a House and a track drop; return the fake."""
    settings = AsyncMock()
    settings.get.return_value = Settings(
        house_channel_id=HOUSE_ID, tracks_channel_id=TRACKS_ID
    )
    bot.settings = settings
    return settings


def make_sender(
    spec: type = discord.TextChannel,
    channel_id: int = 900,
    parent_id: int | None = None,
    fails: bool = False,
) -> MagicMock:
    channel = MagicMock(spec=spec)
    channel.id = channel_id
    if parent_id is not None:
        channel.parent_id = parent_id
    channel.send = AsyncMock(
        side_effect=(
            discord.Forbidden(MagicMock(status=403), "Missing Access")
            if fails
            else None
        )
    )
    return channel


def make_house(fails: bool = False) -> MagicMock:
    return make_sender(channel_id=HOUSE_ID, fails=fails)


def posted(channel: MagicMock) -> list[str]:
    """The lines a fake channel was sent, checking each one pinged nobody."""
    lines = []
    for call in channel.send.await_args_list:
        assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
        (line,) = call.args
        lines.append(line)
    return lines


async def test_house_channel_is_the_configured_house(bot: app.WispBot) -> None:
    house = make_house()
    guild = make_guild(house)
    configured(bot)

    assert await bot.house_channel(guild) is house
    guild.get_channel_or_thread.assert_called_once_with(HOUSE_ID)


async def test_house_channel_is_none_when_unset_or_without_a_guild(
    bot: app.WispBot,
) -> None:
    guild = make_guild(make_house())
    bot.settings = AsyncMock()
    bot.settings.get.return_value = Settings()

    assert await bot.house_channel(guild) is None
    assert await bot.house_channel(None) is None
    guild.get_channel_or_thread.assert_not_called()


async def test_house_channel_is_none_and_logged_when_it_cannot_be_seen(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    configured(bot)

    with caplog.at_level(logging.ERROR, logger="wisp"):
        assert await bot.house_channel(make_guild(None)) is None

    assert f"Wisp's House {HOUSE_ID} is not available" in caplog.text


def test_there_is_no_errors_channel_any_more(bot: app.WispBot) -> None:
    assert not hasattr(bot, "staff_channel")
    assert "error_channel_id" not in {field.name for field in fields(Settings)}


async def test_report_error_without_a_place_posts_the_plain_line_in_the_house(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    house = make_house()
    configured(bot)
    error = ValueError("bad feed")

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.report_error(make_guild(house), "feeding", error)

    assert posted(house) == ["Error in feeding: ValueError: bad feed"]
    assert any(
        record.exc_info and record.exc_info[1] is error for record in caplog.records
    )


async def test_report_error_posts_where_it_happened_and_not_in_the_house(
    bot: app.WispBot,
) -> None:
    house = make_house()
    thread = make_sender(discord.Thread, channel_id=901, parent_id=10)
    configured(bot)

    await bot.report_error(
        make_guild(house), "the Feed button", RuntimeError("boom"), where=thread
    )

    assert posted(thread) == ["Error in the Feed button: RuntimeError: boom"]
    house.send.assert_not_awaited()


async def test_report_error_truncates_to_discord_limit(bot: app.WispBot) -> None:
    channel = make_sender()
    configured(bot)

    await bot.report_error(
        make_guild(make_house()), "tick", RuntimeError("x" * 5000), where=channel
    )

    (sent,) = posted(channel)
    assert len(sent) == 2000
    assert sent.startswith("Error in tick: RuntimeError: xxx")


async def test_report_error_falls_back_to_the_house_when_where_fails(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    house = make_house()
    thread = make_sender(discord.Thread, channel_id=901, parent_id=10, fails=True)
    configured(bot)

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.report_error(
            make_guild(house), "closing a thread", RuntimeError("boom"), where=thread
        )

    thread.send.assert_awaited_once()
    assert posted(house) == ["Error in closing a thread: RuntimeError: boom"]
    assert "Could not post error report for closing a thread" in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        aiohttp.ClientConnectionError("connection reset"),
        TimeoutError(),
        OSError("network is unreachable"),
    ],
    ids=["aiohttp", "timeout", "os error"],
)
async def test_report_error_falls_back_to_the_house_on_a_transport_failure(
    bot: app.WispBot, failure: Exception
) -> None:
    house = make_house()
    thread = make_sender(discord.Thread, channel_id=901, parent_id=10)
    thread.send.side_effect = failure
    configured(bot)

    await bot.report_error(
        make_guild(house), "closing a thread", RuntimeError("boom"), where=thread
    )

    thread.send.assert_awaited_once()
    assert posted(house) == ["Error in closing a thread: RuntimeError: boom"]


@pytest.mark.parametrize(
    ("spec", "channel_id", "parent_id"),
    [
        (discord.TextChannel, TRACKS_ID, None),
        (discord.Thread, 902, TRACKS_ID),
        (discord.PartialMessageable, 903, None),
    ],
    ids=["the track drop", "a thread in the track drop", "a channel Wisp cannot place"],
)
async def test_report_error_never_posts_in_the_track_drop(
    bot: app.WispBot, spec: type, channel_id: int, parent_id: int | None
) -> None:
    house = make_house()
    where = make_sender(spec, channel_id, parent_id)
    configured(bot)

    await bot.report_error(
        make_guild(house), "on_message", RuntimeError("boom"), where=where
    )

    where.send.assert_not_awaited()
    assert posted(house) == ["Error in on_message: RuntimeError: boom"]


async def test_report_error_logs_only_when_where_and_the_house_both_fail(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    house = make_house(fails=True)
    thread = make_sender(discord.Thread, channel_id=901, parent_id=10, fails=True)
    configured(bot)

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.report_error(
            make_guild(house), "tick", RuntimeError("boom"), where=thread
        )

    thread.send.assert_awaited_once()
    house.send.assert_awaited_once()
    assert caplog.text.count("Could not post error report for tick") == 2


async def test_report_error_does_not_retry_the_house_when_it_was_where(
    bot: app.WispBot,
) -> None:
    house = make_house(fails=True)
    configured(bot)

    await bot.report_error(
        make_guild(house), "talking", RuntimeError("boom"), where=house
    )

    house.send.assert_awaited_once()


async def test_report_error_without_a_house_only_logs(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    guild = make_guild(None)
    bot.settings = AsyncMock()
    bot.settings.get.return_value = Settings()

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.report_error(guild, "tick", RuntimeError("boom"))

    guild.get_channel_or_thread.assert_not_called()
    assert "boom" in caplog.text


async def test_report_error_without_guild_only_logs(bot: app.WispBot) -> None:
    bot.settings = MagicMock()
    channel = make_sender()

    await bot.report_error(None, "startup", RuntimeError("boom"), where=channel)

    assert bot.settings.mock_calls == []
    channel.send.assert_not_awaited()


async def test_report_error_survives_unreadable_settings(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    bot.settings = AsyncMock()
    bot.settings.get.side_effect = pymysql.err.OperationalError(2003, "down")
    channel = make_sender()

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.report_error(
            make_guild(make_house()), "tick", RuntimeError("boom"), where=channel
        )

    channel.send.assert_not_awaited()
    assert "Could not post error report for tick" in caplog.text


# ---
# Command tree errors
# ---


@pytest.mark.parametrize(
    ("response_done", "used", "unused"),
    [(False, "response", "followup"), (True, "followup", "response")],
)
async def test_tree_error_tells_user_then_reports_where_it_happened(
    bot: app.WispBot, response_done: bool, used: str, unused: str
) -> None:
    guild = make_guild(None)
    interaction = make_interaction(response_done, guild)
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    original = ValueError("bad")
    error = app_commands.CommandInvokeError(MagicMock(), original)

    await bot.tree.on_error(interaction, error)

    send = (
        interaction.response.send_message
        if used == "response"
        else interaction.followup.send
    )
    send.assert_awaited_once_with(USER_ERROR, ephemeral=True)
    other = (
        interaction.followup.send
        if used == "response"
        else interaction.response.send_message
    )
    other.assert_not_awaited()
    bot.report_error.assert_awaited_once_with(
        guild, "/wisp feed", original, where=interaction.channel
    )


async def test_a_slash_command_failure_is_posted_in_its_channel(
    bot: app.WispBot,
) -> None:
    house = make_house()
    here = make_sender(channel_id=904)
    guild = make_guild(None)
    guild.get_channel_or_thread.side_effect = {HOUSE_ID: house}.get
    interaction = make_interaction(False, guild)
    interaction.channel = here
    configured(bot)
    error = app_commands.CommandInvokeError(MagicMock(), ValueError("bad"))

    await bot.tree.on_error(interaction, error)

    assert posted(here) == ["Error in /wisp feed: ValueError: bad"]
    house.send.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        "That didn't work. The error is posted in this channel.", ephemeral=True
    )


async def test_tree_error_where_nothing_can_be_posted_is_reported_without_a_place(
    bot: app.WispBot,
) -> None:
    interaction = make_interaction(False, None)
    interaction.channel = MagicMock(spec=discord.CategoryChannel)
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = app_commands.AppCommandError("plain")

    await bot.tree.on_error(interaction, error)

    bot.report_error.assert_awaited_once_with(None, "/wisp feed", error, where=None)


async def test_tree_error_reports_even_when_user_reply_fails(
    bot: app.WispBot,
) -> None:
    interaction = make_interaction(False, None)
    interaction.response.send_message.side_effect = discord.HTTPException(
        MagicMock(status=404), "Unknown interaction"
    )
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = app_commands.AppCommandError("plain")

    await bot.tree.on_error(interaction, error)

    bot.report_error.assert_awaited_once_with(
        None, "/wisp feed", error, where=interaction.channel
    )


async def test_tree_error_reports_when_interaction_was_already_answered(
    bot: app.WispBot,
) -> None:
    interaction = make_interaction(False, None)
    interaction.response.send_message.side_effect = discord.InteractionResponded(
        interaction
    )
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = app_commands.AppCommandError("plain")

    await bot.tree.on_error(interaction, error)

    bot.report_error.assert_awaited_once_with(
        None, "/wisp feed", error, where=interaction.channel
    )


@pytest.mark.parametrize(
    ("response_done", "used"), [(False, "response"), (True, "followup")]
)
@pytest.mark.parametrize(
    "error",
    [
        app_commands.CheckFailure("no"),
        app_commands.MissingPermissions(["manage_guild"]),
    ],
)
async def test_check_failure_is_refused_not_reported(
    bot: app.WispBot,
    response_done: bool,
    used: str,
    error: app_commands.AppCommandError,
) -> None:
    interaction = make_interaction(response_done, make_guild(None))
    bot.report_error = AsyncMock()  # type: ignore[method-assign]

    await bot.tree.on_error(interaction, error)

    send = (
        interaction.response.send_message
        if used == "response"
        else interaction.followup.send
    )
    send.assert_awaited_once_with("That command is for staff.", ephemeral=True)
    bot.report_error.assert_not_awaited()


async def test_missing_bot_permissions_is_a_bot_fault_not_a_refusal(
    bot: app.WispBot,
) -> None:
    guild = make_guild(None)
    interaction = make_interaction(False, guild)
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = app_commands.BotMissingPermissions(["manage_threads"])

    await bot.tree.on_error(interaction, error)

    interaction.response.send_message.assert_awaited_once_with(
        USER_ERROR, ephemeral=True
    )
    bot.report_error.assert_awaited_once_with(
        guild, "/wisp feed", error, where=interaction.channel
    )


# ---
# Per-guild locks
# ---


def test_guild_lock_is_shared_per_guild(bot: app.WispBot) -> None:
    assert bot.guild_lock(1) is bot.guild_lock(1)
    assert bot.guild_lock(1) is not bot.guild_lock(2)


# ---
# Startup and shutdown
# ---


async def test_setup_hook_runs_in_order_and_survives_a_bad_extension(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    emoji = make_emoji("<:a:1>")
    emoji.name = "a"

    async def connect() -> None:
        calls.append("connect")

    async def create_tables(_db: object) -> None:
        calls.append("tables")

    async def fetch_emojis() -> list[MagicMock]:
        calls.append("emojis")
        return [emoji]

    async def load_extension(name: str) -> None:
        calls.append(f"load {name}")
        if name == "cogs.broken":
            raise commands.ExtensionFailed(name, ValueError("nope"))

    async def sync() -> list[object]:
        calls.append("sync")
        return []

    monkeypatch.setattr(app, "EXTENSIONS", ("cogs.broken", "cogs.fine"))
    monkeypatch.setattr(app, "create_tables", create_tables)
    monkeypatch.setattr(bot.db, "connect", connect)
    monkeypatch.setattr(bot, "fetch_application_emojis", fetch_emojis)
    monkeypatch.setattr(bot, "load_extension", load_extension)
    add_command = bot.tree.add_command

    def record_add_command(command: app_commands.Group, **kwargs: object) -> None:
        calls.append(f"add {command.name}")
        add_command(command, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(bot.tree, "sync", sync)
    monkeypatch.setattr(bot.tree, "add_command", record_add_command)

    await bot.setup_hook()

    assert calls == [
        "connect",
        "tables",
        "emojis",
        "load cogs.broken",
        "load cogs.fine",
        "add wisp",
        "add wispadmin",
        "sync",
    ]
    assert bot.tree.get_command("wisp") is groups.wisp
    assert bot.tree.get_command("wispadmin") is groups.wispadmin
    assert bot.emojis_by_name == {"a": emoji}


async def test_a_failed_extension_reaches_every_house_once_after_ready(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    first, second = make_house(), make_house()
    guilds = {7: make_guild(first, 7), 8: make_guild(second, 8)}
    configured(bot).guilds.return_value = [7, 8]
    monkeypatch.setattr(bot, "get_guild", guilds.get)

    async def load_extension(name: str) -> None:
        raise commands.ExtensionFailed(name, ValueError("nope"))

    monkeypatch.setattr(app, "EXTENSIONS", ("cogs.broken",))
    monkeypatch.setattr(app, "create_tables", AsyncMock())
    monkeypatch.setattr(bot.db, "connect", AsyncMock())
    monkeypatch.setattr(bot, "fetch_application_emojis", AsyncMock(return_value=[]))
    monkeypatch.setattr(bot, "load_extension", load_extension)
    monkeypatch.setattr(bot.tree, "sync", AsyncMock(return_value=[]))

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.setup_hook()

    assert "cogs.broken" in caplog.text
    first.send.assert_not_awaited()

    await bot.on_ready()
    await bot.on_ready()

    for house in (first, second):
        (line,) = posted(house)
        assert line.startswith("Error in loading cogs.broken: ExtensionFailed:")


async def test_reporting_everywhere_posts_in_every_house(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = make_house(), make_house()
    guilds = {7: make_guild(first, 7), 8: make_guild(second, 8)}
    configured(bot).guilds.return_value = [7, 8]
    monkeypatch.setattr(bot, "get_guild", guilds.get)

    await bot.report_error_everywhere("life loop", RuntimeError("boom"))

    for house in (first, second):
        assert posted(house) == ["Error in life loop: RuntimeError: boom"]


@pytest.mark.parametrize(
    "failure",
    [
        pymysql.err.OperationalError(2003, "down"),
        RuntimeError("the pool is closed"),
        AttributeError("'NoneType' object has no attribute 'acquire'"),
    ],
    ids=["database down", "closed pool", "unconnected pool"],
)
async def test_reporting_everywhere_falls_back_to_the_guilds_the_bot_sees(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    house = make_house()
    configured(bot).guilds.side_effect = failure
    monkeypatch.setattr(
        app.WispBot, "guilds", property(lambda _self: [make_guild(house)])
    )

    await bot.report_error_everywhere("life loop", RuntimeError("boom"))

    assert posted(house) == ["Error in life loop: RuntimeError: boom"]


async def test_close_closes_the_database_after_the_client(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def close_db() -> None:
        calls.append("db")

    original_close = commands.Bot.close

    async def close_client(self: commands.Bot) -> None:
        await original_close(self)
        calls.append("client")

    monkeypatch.setattr(bot.db, "close", close_db)
    monkeypatch.setattr(commands.Bot, "close", close_client)

    await bot.close()

    assert calls == ["client", "db"]


async def test_close_closes_the_database_even_if_the_client_fails(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    close_db = AsyncMock()

    async def failing_close(self: commands.Bot) -> None:
        raise RuntimeError("client close failed")

    monkeypatch.setattr(bot.db, "close", close_db)
    monkeypatch.setattr(commands.Bot, "close", failing_close)

    with pytest.raises(RuntimeError, match="client close failed"):
        await bot.close()

    close_db.assert_awaited_once()


async def test_close_closes_the_ai_session_between_the_client_and_the_database(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def close_ai() -> None:
        calls.append("ai")

    async def close_db() -> None:
        calls.append("db")

    async def close_client(self: commands.Bot) -> None:
        calls.append("client")

    monkeypatch.setattr(bot.ai, "close", close_ai)
    monkeypatch.setattr(bot.db, "close", close_db)
    monkeypatch.setattr(commands.Bot, "close", close_client)

    await bot.close()

    assert calls == ["client", "ai", "db"]


async def test_close_closes_the_ai_session_even_if_the_client_fails(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    close_ai = AsyncMock()
    close_db = AsyncMock()

    async def failing_close(self: commands.Bot) -> None:
        raise RuntimeError("client close failed")

    monkeypatch.setattr(bot.ai, "close", close_ai)
    monkeypatch.setattr(bot.db, "close", close_db)
    monkeypatch.setattr(commands.Bot, "close", failing_close)

    with pytest.raises(RuntimeError, match="client close failed"):
        await bot.close()

    close_ai.assert_awaited_once()
    close_db.assert_awaited_once()


async def test_close_closes_the_database_even_if_the_ai_session_fails(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    close_db = AsyncMock()

    async def failing_close_ai() -> None:
        raise RuntimeError("ai close failed")

    monkeypatch.setattr(bot.ai, "close", failing_close_ai)
    monkeypatch.setattr(bot.db, "close", close_db)
    monkeypatch.setattr(commands.Bot, "close", AsyncMock())

    with pytest.raises(RuntimeError, match="ai close failed"):
        await bot.close()

    close_db.assert_awaited_once()


async def test_close_before_connecting_is_safe() -> None:
    await app.WispBot().close()


# ---
# Unhandled listener errors
# ---


def make_message(guild: MagicMock, channel: MagicMock) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.guild = guild
    message.channel = channel
    return message


async def test_unhandled_listener_error_is_reported_where_its_message_was(
    bot: app.WispBot,
) -> None:
    guild = make_guild(make_channel())
    message = make_message(guild, make_sender())
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = ValueError("bad listener")

    try:
        raise error
    except ValueError:
        await bot.on_error("on_message", message)

    bot.report_error.assert_awaited_once_with(
        guild, "on_message", error, where=message.channel
    )


async def test_unhandled_listener_error_without_a_message_is_reported_without_a_place(
    bot: app.WispBot,
) -> None:
    guild = make_guild(make_channel())
    thread = MagicMock(spec=discord.Thread)
    thread.guild = guild
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = ValueError("bad listener")

    try:
        raise error
    except ValueError:
        await bot.on_error("on_thread_create", thread)

    bot.report_error.assert_awaited_once_with(
        guild, "on_thread_create", error, where=None
    )


@pytest.mark.parametrize(
    ("channel_id", "posted_in"), [(904, "its channel"), (TRACKS_ID, "the House")]
)
async def test_a_listener_error_is_posted_in_its_channel_unless_it_is_the_track_drop(
    bot: app.WispBot, channel_id: int, posted_in: str
) -> None:
    house = make_house()
    here = make_sender(channel_id=channel_id)
    guild = make_guild(None)
    guild.get_channel_or_thread.side_effect = {HOUSE_ID: house}.get
    configured(bot)

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        await bot.on_error("on_message", make_message(guild, here))

    line = "Error in on_message: RuntimeError: boom"
    if posted_in == "the House":
        here.send.assert_not_awaited()
        assert posted(house) == [line]
    else:
        assert posted(here) == [line]
        house.send.assert_not_awaited()


@pytest.mark.parametrize("args", [(), (MagicMock(spec=[]),), (None,)])
async def test_unhandled_listener_error_without_a_guild_is_reported_without_one(
    bot: app.WispBot, args: tuple[object, ...]
) -> None:
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = RuntimeError("boom")

    try:
        raise error
    except RuntimeError:
        await bot.on_error("on_ready", *args)

    bot.report_error.assert_awaited_once_with(None, "on_ready", error, where=None)


async def test_tests_never_reach_a_real_ai_provider() -> None:
    bot = app.WispBot()

    assert bot.ai.providers == ()
