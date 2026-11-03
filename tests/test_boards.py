"""Tests for the boards: chat typed in the Status and Vault posts is deleted.

Discord objects are fakes; the settings repository is the real one.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs.boards import Boards
from db.database import Database
from db.settings import SettingsRepo
from wisp.rules import BOARD_NOTICE_LIFETIME

GUILD_ID = 100
HOUSE_ID = 20
STATUS_ID = 41
VAULT_ID = 42
MEALTIME_ID = 43
STAFF_ROLE_ID = 7
MEMBER_ID = 1
OWNER_ID = 99
START = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
NO_PING = discord.AllowedMentions.none().to_dict()
NOTICE = f"♪ This post is just for buttons. Come chat in <#{HOUSE_ID}>."


# ---
# Fakes
# ---


def make_role(role_id: int) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.is_default.return_value = role_id == GUILD_ID
    return role


def make_member(
    user_id: int = MEMBER_ID,
    *,
    manage_guild: bool = False,
    role_ids: tuple[int, ...] = (),
    bot: bool = False,
) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = bot
    member.guild = GUILD
    member.guild_permissions = discord.Permissions(manage_guild=manage_guild)
    member.roles = [make_role(role_id) for role_id in (GUILD_ID, *role_ids)]
    return member


def make_thread(thread_id: int) -> MagicMock:
    thread = MagicMock(spec=discord.Thread)
    thread.id = thread_id
    thread.send = AsyncMock()
    return thread


GUILD = MagicMock(spec=discord.Guild)
GUILD.id = GUILD_ID


def make_message(
    channel: MagicMock,
    author: MagicMock | None = None,
    kind: discord.MessageType = discord.MessageType.default,
) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.guild = GUILD
    message.channel = channel
    message.author = author if author is not None else make_member()
    message.type = kind
    message.delete = AsyncMock()
    return message


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(discord.utils, "utcnow", fake)
    return fake


@pytest.fixture
async def cog(db: Database) -> Boards:
    bot = app.WispBot()
    bot.settings = SettingsRepo(db)
    bot.owner_id = OWNER_ID
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        status_thread_id=STATUS_ID,
        vault_thread_id=VAULT_ID,
        mealtime_thread_id=MEALTIME_ID,
    )
    await bot.settings.add_staff_role(GUILD_ID, STAFF_ROLE_ID)
    return Boards(bot)


def sent(thread: MagicMock) -> list[tuple[str, dict[str, Any]]]:
    return [(str(call.args[0]), call.kwargs) for call in thread.send.await_args_list]


# ---
# Deleting chat
# ---


@pytest.mark.parametrize("board_id", [STATUS_ID, VAULT_ID])
async def test_member_chat_in_a_board_is_deleted_with_a_notice_that_goes_away(
    cog: Boards, clock: Clock, board_id: int
) -> None:
    board = make_thread(board_id)
    message = make_message(board)

    await cog.on_message(message)

    message.delete.assert_awaited_once()
    ((text, kwargs),) = sent(board)
    assert text == NOTICE
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    assert kwargs["delete_after"] == BOARD_NOTICE_LIFETIME.total_seconds()


async def test_a_burst_of_chat_gets_one_notice_until_it_goes_away(
    cog: Boards, clock: Clock
) -> None:
    board = make_thread(STATUS_ID)
    burst = [make_message(board) for _ in range(3)]

    for message in burst:
        await cog.on_message(message)
        clock.now += timedelta(seconds=1)

    for message in burst:
        message.delete.assert_awaited_once()
    assert len(sent(board)) == 1

    clock.now = START + BOARD_NOTICE_LIFETIME
    await cog.on_message(make_message(board))
    assert len(sent(board)) == 2


async def test_each_board_has_its_own_notice(cog: Boards, clock: Clock) -> None:
    status, vault = make_thread(STATUS_ID), make_thread(VAULT_ID)

    await cog.on_message(make_message(status))
    await cog.on_message(make_message(vault))

    assert len(sent(status)) == 1
    assert len(sent(vault)) == 1


Author = Callable[[], MagicMock]


@pytest.mark.parametrize(
    "author",
    [
        lambda: make_member(manage_guild=True),
        lambda: make_member(role_ids=(STAFF_ROLE_ID,)),
        lambda: make_member(OWNER_ID),
        lambda: make_member(bot=True),
    ],
    ids=["manage server", "staff role", "app owner", "bot"],
)
async def test_staff_and_bots_may_post_in_a_board(
    cog: Boards, clock: Clock, author: Author
) -> None:
    board = make_thread(STATUS_ID)
    message = make_message(board, author())

    await cog.on_message(message)

    message.delete.assert_not_awaited()
    board.send.assert_not_awaited()


async def test_chat_in_other_studio_posts_is_left_alone(
    cog: Boards, clock: Clock
) -> None:
    mealtime = make_thread(MEALTIME_ID)
    message = make_message(mealtime)

    await cog.on_message(message)

    message.delete.assert_not_awaited()
    mealtime.send.assert_not_awaited()


async def test_discords_own_notices_in_a_board_are_left_alone(
    cog: Boards, clock: Clock
) -> None:
    board = make_thread(STATUS_ID)
    message = make_message(board, kind=discord.MessageType.pins_add)

    await cog.on_message(message)

    message.delete.assert_not_awaited()


async def test_a_failed_delete_is_posted_in_the_board(
    cog: Boards, clock: Clock
) -> None:
    board = make_thread(VAULT_ID)
    message = make_message(board)
    message.delete.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await cog.on_message(message)

    ((text, _),) = sent(board)
    assert text.startswith(
        "Error in keeping the ViiBR Vault post for buttons: Forbidden"
    )


async def test_chat_someone_already_deleted_still_gets_the_notice(
    cog: Boards, clock: Clock
) -> None:
    board = make_thread(STATUS_ID)
    message = make_message(board)
    message.delete.side_effect = discord.NotFound(
        MagicMock(status=404), "Unknown Message"
    )

    await cog.on_message(message)

    ((text, _),) = sent(board)
    assert text == NOTICE


def test_the_boards_cog_is_loaded() -> None:
    assert "cogs.boards" in app.EXTENSIONS
