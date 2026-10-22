import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import app
from cogs import groups
from db.settings import Settings


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


async def test_report_error_posts_plain_line(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    channel = make_channel()
    channel.send = AsyncMock()
    guild = make_guild(channel)
    bot.settings = AsyncMock()
    bot.settings.get.return_value = Settings(error_channel_id=555)
    error = ValueError("bad feed")

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.report_error(guild, "feeding", error)

    guild.get_channel_or_thread.assert_called_once_with(555)
    channel.send.assert_awaited_once_with("Error in feeding: ValueError: bad feed")
    assert any(
        record.exc_info and record.exc_info[1] is error for record in caplog.records
    )


async def test_report_error_truncates_to_discord_limit(bot: app.WispBot) -> None:
    channel = make_channel()
    channel.send = AsyncMock()
    bot.settings = AsyncMock()
    bot.settings.get.return_value = Settings(error_channel_id=555)

    await bot.report_error(make_guild(channel), "tick", RuntimeError("x" * 5000))

    (sent,) = channel.send.await_args.args
    assert len(sent) == 2000
    assert sent.startswith("Error in tick: RuntimeError: xxx")


async def test_report_error_without_error_channel_only_logs(
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

    await bot.report_error(None, "startup", RuntimeError("boom"))

    assert bot.settings.mock_calls == []


async def test_report_error_survives_a_failed_post(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    channel = make_channel()
    channel.send = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(status=403), "Missing Access")
    )
    bot.settings = AsyncMock()
    bot.settings.get.return_value = Settings(error_channel_id=555)

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.report_error(make_guild(channel), "tick", RuntimeError("boom"))

    assert "Could not post error report" in caplog.text


async def test_report_error_survives_a_missing_channel(
    bot: app.WispBot, caplog: pytest.LogCaptureFixture
) -> None:
    bot.settings = AsyncMock()
    bot.settings.get.return_value = Settings(error_channel_id=555)

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await bot.report_error(make_guild(None), "tick", RuntimeError("boom"))

    assert "Could not post error report" in caplog.text


# ---
# Command tree errors
# ---


@pytest.mark.parametrize(
    ("response_done", "used", "unused"),
    [(False, "response", "followup"), (True, "followup", "response")],
)
async def test_tree_error_tells_user_then_reports(
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
    send.assert_awaited_once_with(
        "Something went wrong. Staff have been told.", ephemeral=True
    )
    other = (
        interaction.followup.send
        if used == "response"
        else interaction.response.send_message
    )
    other.assert_not_awaited()
    bot.report_error.assert_awaited_once_with(guild, "/wisp feed", original)


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

    bot.report_error.assert_awaited_once_with(None, "/wisp feed", error)


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

    bot.report_error.assert_awaited_once_with(None, "/wisp feed", error)


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
        "Something went wrong. Staff have been told.", ephemeral=True
    )
    bot.report_error.assert_awaited_once_with(guild, "/wisp feed", error)


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
    bot.report_error = AsyncMock()  # type: ignore[method-assign]

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
    bot.report_error.assert_awaited_once()
    call = bot.report_error.await_args
    assert call is not None
    guild, context, error = call.args
    assert guild is None
    assert "cogs.broken" in context
    assert isinstance(error, commands.ExtensionFailed)


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


async def test_close_before_connecting_is_safe() -> None:
    await app.WispBot().close()


# ---
# Unhandled listener errors
# ---


async def test_unhandled_listener_error_is_reported_with_its_guild(
    bot: app.WispBot,
) -> None:
    guild = make_guild(make_channel())
    message = MagicMock(spec=discord.Message)
    message.guild = guild
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = ValueError("bad listener")

    try:
        raise error
    except ValueError:
        await bot.on_error("on_message", message)

    bot.report_error.assert_awaited_once_with(guild, "on_message", error)


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

    bot.report_error.assert_awaited_once_with(None, "on_ready", error)
