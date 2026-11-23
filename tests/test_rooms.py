"""Tests for members' rooms: private threads off Wisp's House.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs import rooms, vault
from cogs.players import NameModal
from cogs.rooms import RoomError, rename_room, room_name
from db.activity import ActivityRepo
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from wisp.rules import ROOM_ARCHIVE_MINUTES, ROOM_NAME_MAX
from wisp.text import clip

GUILD_ID = 100
HOUSE_ID = 20
OLD_HOUSE_ID = 21
CHANNEL_ID = 40
USER_ID = 1
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
WELCOME = "\n".join(
    [
        f"♪ This is your room with Wisp, <@{USER_ID}>.",
        "・Your games with him happen here.",
        "・Your Snack Pack is pinned here. Open it any time with /wisp snackpack.",
    ]
)

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House, whose private threads can be archived or deleted."""

    def __init__(self) -> None:
        self.threads: dict[int, MagicMock] = {}
        self._next_id = 5000
        self.house = self.make_house(HOUSE_ID)
        self.channels: dict[int, MagicMock] = {HOUSE_ID: self.house}
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = self.channels.get

    def make_house(self, house_id: int) -> MagicMock:
        house = MagicMock(spec=discord.TextChannel)
        house.id = house_id
        house.send = AsyncMock()
        house.create_thread = AsyncMock(
            side_effect=lambda **kwargs: self._create_thread(house_id, **kwargs)
        )
        return house

    def _create_thread(self, parent_id: int, *, name: str, **kwargs: Any) -> MagicMock:
        self._next_id += 1
        thread = MagicMock(spec=discord.Thread)
        thread.id = self._next_id
        thread.name = name
        thread.parent_id = parent_id
        thread.archived = False
        thread.mention = f"<#{thread.id}>"
        thread.create_kwargs = kwargs
        thread.add_user = AsyncMock()
        thread.send = AsyncMock()
        thread.edit = AsyncMock(side_effect=lambda **fields: self._edit(thread, fields))
        self.threads[thread.id] = thread
        return thread

    def _edit(self, thread: MagicMock, fields: dict[str, Any]) -> MagicMock:
        for name, value in fields.items():
            setattr(thread, name, value)
        return thread

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        if channel_id not in self.threads:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return self.threads[channel_id]

    def only_room(self) -> MagicMock:
        (room,) = self.threads.values()
        return room


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
    wisp_bot.story = LifeStoryRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


async def configure(bot: app.WispBot, house_id: int = HOUSE_ID) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=house_id)


def make_member(user_id: int = USER_ID, display_name: str = "Member1") -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.display_name = display_name
    member.mention = f"<@{user_id}>"
    return member


def make_interaction(bot: app.WispBot, server: FakeServer) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.channel.id = CHANNEL_ID
    interaction.channel.send = AsyncMock()
    interaction.user = make_member()
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def board(bot: app.WispBot, server: FakeServer) -> MagicMock:
    interaction = make_interaction(bot, server)
    command: Any = vault.wisp_board
    await command.callback(interaction)
    return interaction


async def open_room(
    bot: app.WispBot, guild: discord.Guild, member: discord.abc.User
) -> MagicMock:
    """`rooms.open_room`, returning the fake thread it found or made."""
    return cast(MagicMock, await rooms.open_room(bot, guild, member))


async def stored_room(bot: app.WispBot, user_id: int = USER_ID) -> int | None:
    return (await bot.players.get(GUILD_ID, user_id)).room_thread_id


# ---
# Making rooms
# ---


async def test_board_makes_a_private_room_on_first_join(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)

    interaction = await board(bot, server)

    server.house.create_thread.assert_awaited_once()
    room = server.only_room()
    assert room.name == "♪ Member1's room"
    assert room.create_kwargs == {
        "type": discord.ChannelType.private_thread,
        "invitable": False,
        "auto_archive_duration": ROOM_ARCHIVE_MINUTES,
    }
    room.add_user.assert_awaited_once_with(interaction.user)
    room.send.assert_awaited_once()
    assert room.send.await_args.args == (WELCOME,)
    mentions = room.send.await_args.kwargs["allowed_mentions"]
    assert mentions.to_dict() == {"parse": [], "users": [USER_ID]}
    assert await stored_room(bot) == room.id
    assert (await bot.players.get(GUILD_ID, USER_ID)).activated_at is not None


async def test_the_room_is_named_for_the_name_wisp_knows(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await bot.players.set_name(GUILD_ID, USER_ID, "Kit")

    room = await open_room(bot, server.guild, make_member())

    assert room.name == "♪ Kit's room"


async def test_the_room_is_reused(bot: app.WispBot, server: FakeServer) -> None:
    await configure(bot)

    await board(bot, server)
    await board(bot, server)

    server.house.create_thread.assert_awaited_once()
    server.only_room().send.assert_awaited_once()


async def test_an_old_member_gets_one_room_on_next_use(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await bot.players.activate(GUILD_ID, USER_ID, NOW)
    member = make_member()

    first, second = await asyncio.gather(
        open_room(bot, server.guild, member), open_room(bot, server.guild, member)
    )

    assert first is second
    server.house.create_thread.assert_awaited_once()
    assert await stored_room(bot) == first.id


async def test_two_members_get_their_own_rooms(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)

    mine = await open_room(bot, server.guild, make_member(1, "One"))
    theirs = await open_room(bot, server.guild, make_member(2, "Two"))

    assert mine is not theirs
    assert (await stored_room(bot, 1), await stored_room(bot, 2)) == (
        mine.id,
        theirs.id,
    )


async def test_an_archived_room_is_reopened(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    room = await open_room(bot, server.guild, make_member())
    room.archived = True

    again = await open_room(bot, server.guild, make_member())

    assert again is room
    room.edit.assert_awaited_once_with(archived=False)
    assert room.archived is False
    server.house.create_thread.assert_awaited_once()


async def test_a_deleted_room_is_made_again(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    old = await open_room(bot, server.guild, make_member())
    del server.threads[old.id]

    new = await open_room(bot, server.guild, make_member())

    assert new.id != old.id
    assert await stored_room(bot) == new.id
    new.send.assert_awaited_once()


async def test_a_room_under_an_old_house_is_made_again(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot, OLD_HOUSE_ID)
    server.channels[OLD_HOUSE_ID] = server.make_house(OLD_HOUSE_ID)
    old = await open_room(bot, server.guild, make_member())
    await configure(bot, HOUSE_ID)

    new = await open_room(bot, server.guild, make_member())

    assert old.parent_id == OLD_HOUSE_ID
    assert new.parent_id == HOUSE_ID
    server.house.create_thread.assert_awaited_once()
    assert await stored_room(bot) == new.id


async def test_a_new_room_forgets_the_old_rooms_snack_pack(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    old = await open_room(bot, server.guild, make_member())
    await bot.players.set_room_pack(GUILD_ID, USER_ID, 55)
    del server.threads[old.id]

    await open_room(bot, server.guild, make_member())

    assert (await bot.players.get(GUILD_ID, USER_ID)).room_pack_message_id is None


@pytest.mark.parametrize("house_id", [None, 999])
async def test_no_house_raises_room_error(
    bot: app.WispBot, server: FakeServer, house_id: int | None
) -> None:
    if house_id is not None:
        await configure(bot, house_id)

    with pytest.raises(RoomError, match="House"):
        await open_room(bot, server.guild, make_member())

    server.house.create_thread.assert_not_awaited()
    assert await stored_room(bot) is None


async def test_board_still_works_when_the_room_fails(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    make_thread = server.house.create_thread.side_effect
    server.house.create_thread.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    interaction = await board(bot, server)

    radar, leaderboard = interaction.followup.send.await_args_list
    assert "radar" in radar.args[0]
    assert isinstance(leaderboard.kwargs["view"], discord.ui.LayoutView)
    interaction.channel.send.assert_awaited_once()
    (report,) = interaction.channel.send.await_args.args
    assert report.startswith("Error in making a room: Forbidden: 403")
    assert await stored_room(bot) is None

    server.house.create_thread.side_effect = make_thread
    await board(bot, server)

    assert await stored_room(bot) == server.only_room().id


async def test_board_without_a_house_still_shows_the_board(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = await board(bot, server)

    (report,) = interaction.channel.send.await_args.args
    assert report.startswith("Error in making a room: RoomError: Wisp's House")
    assert len(interaction.followup.send.await_args_list) == 2


def test_room_name_fits_discord() -> None:
    assert room_name("Kit") == "♪ Kit's room"
    assert room_name("x" * 200) == clip("♪ " + "x" * 200 + "'s room", ROOM_NAME_MAX)
    assert len(room_name("x" * 200)) == ROOM_NAME_MAX


# ---
# Renaming rooms
# ---


def fill(modal: NameModal, text: str) -> None:
    payload: Any = {"value": text}
    modal.name._refresh_state(MagicMock(), payload)


async def test_learning_a_name_renames_the_room(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    room = await open_room(bot, server.guild, make_member())
    room.archived = True
    modal = NameModal()
    fill(modal, "Kit")

    await modal.on_submit(make_interaction(bot, server))

    room.edit.assert_awaited_once_with(name="♪ Kit's room", archived=False)
    assert room.name == "♪ Kit's room"


async def test_learning_a_name_without_a_room_makes_none(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    modal = NameModal()
    fill(modal, "Kit")

    await modal.on_submit(make_interaction(bot, server))

    assert (await bot.players.get(GUILD_ID, USER_ID)).name == "Kit"
    server.house.create_thread.assert_not_awaited()


async def test_a_deleted_room_is_not_renamed_or_reported(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    room = await open_room(bot, server.guild, make_member())
    del server.threads[room.id]

    await rename_room(bot, GUILD_ID, USER_ID, "Kit")

    room.edit.assert_not_awaited()
    server.house.send.assert_not_awaited()


async def test_a_failed_rename_is_reported_not_raised(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    room = await open_room(bot, server.guild, make_member())
    room.edit.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await rename_room(bot, GUILD_ID, USER_ID, "Kit")

    (report,) = server.house.send.await_args.args
    assert report.startswith("Error in renaming a room: Forbidden: 403")
