"""Tests for the shared pinned-message helper.

Discord objects are fakes; the repositories are the real ones.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs.announce import show_in_thread
from db.database import Database
from db.settings import SettingsRepo

GUILD_ID = 100
FORUM_ID = 10
ERRORS_ID = 40
STATUS_ID = 60
BOARD_ID = 61
STATUS_MESSAGE_ID = 777
BOARD_MESSAGE_ID = 778
REPOSTED_ID = 888

# ---
# Fakes
# ---


class FakeThread:
    """A Studio thread whose stored message can be edited, lost or reposted."""

    def __init__(self, thread_id: int) -> None:
        self.reposted = MagicMock(spec=discord.Message)
        self.reposted.id = REPOSTED_ID
        self.reposted.pin = AsyncMock()
        self.edit: Any = AsyncMock()
        partial = MagicMock(spec=discord.PartialMessage)
        partial.edit = self.edit
        self.thread = MagicMock(spec=discord.Thread)
        self.thread.id = thread_id
        self.thread.parent_id = FORUM_ID
        self.thread.archived = False
        self.thread.send = AsyncMock(return_value=self.reposted)
        self.thread.get_partial_message.return_value = partial


class FakeServer:
    """A guild with an errors channel and the Status and Billboard threads."""

    def __init__(self) -> None:
        self.errors = MagicMock(spec=discord.TextChannel)
        self.errors.send = AsyncMock()
        self.status = FakeThread(STATUS_ID)
        self.board = FakeThread(BOARD_ID)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {ERRORS_ID: self.errors}.get

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        threads = {STATUS_ID: self.status.thread, BOARD_ID: self.board.thread}
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
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        studio_forum_id=FORUM_ID,
        error_channel_id=ERRORS_ID,
        status_thread_id=STATUS_ID,
        status_message_id=STATUS_MESSAGE_ID,
        billboard_thread_id=BOARD_ID,
        billboard_message_id=BOARD_MESSAGE_ID,
    )


async def show_status(bot: app.WispBot, content: str = "card") -> None:
    await show_in_thread(
        bot, GUILD_ID, "status_thread_id", "status_message_id", content, "status card"
    )


async def show_board(bot: app.WispBot, content: str = "board") -> None:
    await show_in_thread(
        bot,
        GUILD_ID,
        "billboard_thread_id",
        "billboard_message_id",
        content,
        "Billboard",
    )


def not_found() -> discord.NotFound:
    return discord.NotFound(MagicMock(status=404), "Unknown Message")


def forbidden() -> discord.Forbidden:
    return discord.Forbidden(MagicMock(status=403), "Missing Access")


# ---
# Editing and reposting
# ---


async def test_stored_message_is_edited_without_pinging(
    bot: app.WispBot, server: FakeServer
) -> None:
    await show_status(bot, "hello")

    server.status.thread.get_partial_message.assert_called_once_with(STATUS_MESSAGE_ID)
    server.status.edit.assert_awaited_once()
    kwargs = server.status.edit.await_args.kwargs
    assert kwargs["content"] == "hello"
    assert kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    server.status.thread.send.assert_not_awaited()
    server.errors.send.assert_not_awaited()


async def test_each_display_uses_its_own_thread_and_message(
    bot: app.WispBot, server: FakeServer
) -> None:
    await show_board(bot, "the board")

    server.board.thread.get_partial_message.assert_called_once_with(BOARD_MESSAGE_ID)
    assert server.board.edit.await_args.kwargs["content"] == "the board"
    server.status.edit.assert_not_awaited()


async def test_lost_message_is_reposted_pinned_and_stored(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.board.edit.side_effect = not_found()

    await show_board(bot, "the board")

    send = server.board.thread.send
    send.assert_awaited_once()
    assert send.await_args.args == ("the board",)
    assert send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    server.board.reposted.pin.assert_awaited_once()
    settings = await bot.settings.get(GUILD_ID)
    assert settings.billboard_message_id == REPOSTED_ID
    assert settings.status_message_id == STATUS_MESSAGE_ID
    server.errors.send.assert_not_awaited()


async def test_no_stored_message_posts_one(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, status_message_id=None)

    await show_status(bot)

    server.status.edit.assert_not_awaited()
    server.status.thread.send.assert_awaited_once()
    assert (await bot.settings.get(GUILD_ID)).status_message_id == REPOSTED_ID


# ---
# Failures
# ---


async def test_pin_failure_is_reported_with_the_label_and_the_message_kept(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.board.edit.side_effect = not_found()
    server.board.reposted.pin.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await show_board(bot)

    assert (await bot.settings.get(GUILD_ID)).billboard_message_id == REPOSTED_ID
    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report.startswith("Error in pinning the Billboard: Forbidden")


async def test_edit_failure_is_reported_with_the_label(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.status.edit.side_effect = forbidden()

    await show_status(bot)

    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report.startswith("Error in updating the status card: Forbidden")


async def test_failure_is_reported_once_per_streak(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.status.edit.side_effect = forbidden()
    await show_status(bot)
    await show_status(bot)
    assert server.errors.send.await_count == 1

    server.status.edit.side_effect = None
    await show_status(bot)
    server.status.edit.side_effect = forbidden()
    await show_status(bot)

    assert server.errors.send.await_count == 2


async def test_streaks_are_tracked_per_display(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.status.edit.side_effect = forbidden()
    server.board.edit.side_effect = forbidden()

    await show_status(bot)
    await show_board(bot)
    await show_status(bot)
    await show_board(bot)

    assert server.errors.send.await_count == 2


async def test_unreachable_studio_is_reported_not_raised(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, studio_forum_id=None, status_thread_id=None)

    await show_status(bot)

    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report.startswith("Error in updating the status card: StudioError")
