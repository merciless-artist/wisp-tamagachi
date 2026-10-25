"""Tests for the `!wisp` staff commands, typed as messages and run through the prefix.

Discord objects are fakes; the repositories are the real ones. Ids are full
length snowflakes, since the converters only read mentions of those.
"""

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest

import app
from cogs import staff
from db.database import Database
from db.settings import SettingsRepo

WISP_ID = 900000000000000001
OWNER_ID = 900000000000000002
STAFF_ID = 900000000000000003
MEMBER_ID = 900000000000000004
GUILD_ID = 910000000000000001
HOUSE_ID = 920000000000000001
TRACKS_ID = 920000000000000002
HERE_ID = 920000000000000003
TRACK_THREAD_ID = 920000000000000004
STAFF_ROLE_ID = 930000000000000001
OTHER_ROLE_ID = 930000000000000002
NO_PING = discord.AllowedMentions.none().to_dict()

# ---
# Fakes
# ---


def make_role(role_id: int) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = f"role{role_id}"
    role.mention = f"<@&{role_id}>"
    return role


class FakeServer:
    """A guild with Wisp's House, the track drop and a channel staff talk in."""

    def __init__(self) -> None:
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.channels: dict[int, MagicMock] = {}
        self.house = self.add_channel(discord.TextChannel, HOUSE_ID)
        self.tracks = self.add_channel(discord.TextChannel, TRACKS_ID)
        self.here = self.add_channel(discord.TextChannel, HERE_ID)
        self.track_thread = self.add_channel(discord.Thread, TRACK_THREAD_ID)
        self.track_thread.parent_id = TRACKS_ID
        self.roles = {
            role_id: make_role(role_id) for role_id in (STAFF_ROLE_ID, OTHER_ROLE_ID)
        }
        self.guild.get_channel.side_effect = self.channels.get
        self.guild.get_channel_or_thread.side_effect = self.channels.get
        self.guild._roles = self.roles
        self.guild.get_role.side_effect = self.roles.get
        self.guild.get_member.return_value = None

    def add_channel(self, spec: type, channel_id: int) -> MagicMock:
        channel = MagicMock(spec=spec)
        channel.id = channel_id
        channel.mention = f"<#{channel_id}>"
        channel.send = AsyncMock()
        self.channels[channel_id] = channel
        return channel

    def member(
        self,
        user_id: int,
        *,
        manage_guild: bool = False,
        role_ids: Iterable[int] = (),
        bot: bool = False,
    ) -> MagicMock:
        member = MagicMock(spec=discord.Member)
        member.id = user_id
        member.bot = bot
        member.guild = self.guild
        member.display_name = f"Member{user_id}"
        member.mention = f"<@{user_id}>"
        member.guild_permissions = discord.Permissions(manage_guild=manage_guild)
        member.roles = [make_role(role_id) for role_id in role_ids]
        return member

    def message(
        self,
        content: str,
        author: MagicMock,
        *,
        channel: MagicMock | None = None,
        mentions: Iterable[MagicMock] = (),
    ) -> MagicMock:
        message = MagicMock(spec=discord.Message)
        message.content = content
        message.guild = self.guild
        message.channel = channel or self.here
        message.author = author
        message.mentions = list(mentions)
        message.role_mentions = []
        return message

    def all_sent(self) -> list[str]:
        return [
            str(call.args[0])
            for channel in self.channels.values()
            for call in channel.send.await_args_list
        ]


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
async def bot(
    db: Database, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.owner_id = OWNER_ID
    wisp = server.member(WISP_ID, bot=True)
    monkeypatch.setattr(app.WispBot, "user", wisp)
    monkeypatch.setattr(wisp_bot, "loop", asyncio.get_running_loop())
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    await wisp_bot.settings.update(
        GUILD_ID, house_channel_id=HOUSE_ID, tracks_channel_id=TRACKS_ID
    )
    await staff.setup(wisp_bot)
    yield wisp_bot


@pytest.fixture
def boss(server: FakeServer) -> MagicMock:
    """A member with Manage Server."""
    return server.member(STAFF_ID, manage_guild=True)


async def say(bot: app.WispBot, message: MagicMock) -> None:
    """Deliver a message to the bot and wait for the events it dispatched."""
    pending = asyncio.all_tasks()
    await bot.on_message(message)
    await asyncio.gather(*(asyncio.all_tasks() - pending))


def sent(channel: MagicMock) -> list[str]:
    """The texts posted in a channel, each unable to ping anyone."""
    texts = []
    for call in channel.send.await_args_list:
        assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
        texts.append(call.args[0])
    return texts


# ---
# The prefix
# ---


async def test_bare_wisp_gets_no_reply(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    for content in ("!wisp", "!wisp ", "!WISP"):
        await say(bot, server.message(content, boss))

    assert server.all_sent() == []


async def test_an_unknown_command_lists_the_staff_commands(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    await say(bot, server.message("!wisp nonsense", boss))

    (text,) = sent(server.here)
    assert text == staff.command_list(bot)
    assert text.startswith("♪ Wisp staff commands: ")
    assert "staff" in text.split(": ", 1)[1].split(", ")


async def test_an_unknown_command_from_a_member_is_ignored(
    bot: app.WispBot, server: FakeServer
) -> None:
    await say(bot, server.message("!wisp nonsense", server.member(MEMBER_ID)))

    assert server.all_sent() == []


async def test_the_prefix_ignores_case_and_extra_spaces(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    await say(bot, server.message("!WiSp   STAFF   List", boss))

    (text,) = sent(server.here)
    assert text.startswith("♪ No staff roles yet.")


async def test_a_mention_of_wisp_runs_no_command(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    owner = server.member(OWNER_ID, manage_guild=True)
    wisp = server.member(WISP_ID, bot=True)
    for content in (
        f"<@{WISP_ID}> staff add <@&{STAFF_ROLE_ID}>",
        f"<@{WISP_ID}> !wisp staff add <@&{STAFF_ROLE_ID}>",
    ):
        await say(bot, server.message(content, owner, mentions=[wisp]))

    assert await bot.settings.staff_roles(GUILD_ID) == set()
    assert server.all_sent() == []


async def test_other_bots_cannot_run_commands(
    bot: app.WispBot, server: FakeServer
) -> None:
    other = server.member(MEMBER_ID, manage_guild=True, bot=True)

    await say(bot, server.message(f"!wisp staff add <@&{STAFF_ROLE_ID}>", other))

    assert await bot.settings.staff_roles(GUILD_ID) == set()
    assert server.all_sent() == []


# ---
# Who is staff
# ---


@pytest.mark.parametrize(
    "who", ["the app owner", "a Manage Server holder", "a staff role holder"]
)
async def test_each_kind_of_staff_can_use_the_commands(
    bot: app.WispBot, server: FakeServer, who: str
) -> None:
    await bot.settings.add_staff_role(GUILD_ID, STAFF_ROLE_ID)
    author = {
        "the app owner": server.member(OWNER_ID),
        "a Manage Server holder": server.member(STAFF_ID, manage_guild=True),
        "a staff role holder": server.member(MEMBER_ID, role_ids=[STAFF_ROLE_ID]),
    }[who]

    assert await staff.is_staff(bot, author)
    await say(bot, server.message("!wisp staff list", author))

    assert sent(server.here) == [f"♪ Wisp staff roles\n・<@&{STAFF_ROLE_ID}>"]


async def test_a_plain_member_is_ignored_without_a_word(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.add_staff_role(GUILD_ID, STAFF_ROLE_ID)
    member = server.member(MEMBER_ID, role_ids=[OTHER_ROLE_ID])
    bot.report_error = AsyncMock()  # type: ignore[method-assign]

    assert not await staff.is_staff(bot, member)
    for content in (
        "!wisp staff list",
        f"!wisp staff add <@&{OTHER_ROLE_ID}>",
        "!wisp staff add",
        "!wisp staff",
    ):
        await say(bot, server.message(content, member))

    assert await bot.settings.staff_roles(GUILD_ID) == {STAFF_ROLE_ID}
    assert server.all_sent() == []
    bot.report_error.assert_not_awaited()


async def test_the_owner_is_fetched_from_discord_once(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    bot.owner_id = None
    info = MagicMock(spec=discord.AppInfo)
    info.team = None
    info.owner = server.member(OWNER_ID)
    application_info = AsyncMock(return_value=info)
    monkeypatch.setattr(bot, "application_info", application_info)

    assert await staff.is_staff(bot, server.member(OWNER_ID))
    assert not await staff.is_staff(bot, server.member(MEMBER_ID))

    application_info.assert_awaited_once()


async def test_staff_roles_take_effect_at_once(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    holder = server.member(MEMBER_ID, role_ids=[STAFF_ROLE_ID])
    assert not await staff.is_staff(bot, holder)

    await say(bot, server.message(f"!wisp staff add <@&{STAFF_ROLE_ID}>", boss))
    assert await staff.is_staff(bot, holder)

    await say(bot, server.message(f"!wisp staff remove <@&{STAFF_ROLE_ID}>", boss))
    assert not await staff.is_staff(bot, holder)


# ---
# Staff roles
# ---


async def test_staff_roles_add_list_remove(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    await say(bot, server.message("!wisp staff list", boss))
    await say(bot, server.message(f"!wisp staff add <@&{OTHER_ROLE_ID}>", boss))
    await say(bot, server.message(f"!wisp staff add {STAFF_ROLE_ID}", boss))
    await say(bot, server.message("!wisp staff list", boss))
    await say(bot, server.message(f"!wisp staff remove <@&{OTHER_ROLE_ID}>", boss))

    assert sent(server.here) == [
        "♪ No staff roles yet. Members with Manage Server are always staff. "
        "Add a role with !wisp staff add @role.",
        f"♪ <@&{OTHER_ROLE_ID}> is now a Wisp staff role.",
        f"♪ <@&{STAFF_ROLE_ID}> is now a Wisp staff role.",
        f"♪ Wisp staff roles\n・<@&{STAFF_ROLE_ID}>\n・<@&{OTHER_ROLE_ID}>",
        f"♪ <@&{OTHER_ROLE_ID}> is no longer a Wisp staff role.",
    ]
    assert await bot.settings.staff_roles(GUILD_ID) == {STAFF_ROLE_ID}


@pytest.mark.parametrize(
    ("content", "usage"),
    [
        ("!wisp staff add", "♪ Usage: !wisp staff add @role"),
        ("!wisp staff add nobody", "♪ Usage: !wisp staff add @role"),
        (
            "!wisp staff remove <@&930000000000000099>",
            "♪ Usage: !wisp staff remove @role",
        ),
        ("!wisp staff", "♪ Usage: !wisp staff add @role | remove @role | list"),
        ("!wisp staff bogus", "♪ Usage: !wisp staff add @role | remove @role | list"),
    ],
)
async def test_wrong_arguments_get_one_usage_line(
    bot: app.WispBot,
    server: FakeServer,
    boss: MagicMock,
    content: str,
    usage: str,
) -> None:
    bot.report_error = AsyncMock()  # type: ignore[method-assign]

    await say(bot, server.message(content, boss))

    assert sent(server.here) == [usage]
    bot.report_error.assert_not_awaited()
    assert await bot.settings.staff_roles(GUILD_ID) == set()


# ---
# Where replies go
# ---


@pytest.mark.parametrize("where", ["the track drop", "a thread in the track drop"])
async def test_a_command_in_the_track_drop_is_answered_in_the_house(
    bot: app.WispBot, server: FakeServer, boss: MagicMock, where: str
) -> None:
    channel = server.tracks if where == "the track drop" else server.track_thread

    await say(bot, server.message("!wisp staff list", boss, channel=channel))
    await say(bot, server.message("!wisp staff add", boss, channel=channel))

    channel.send.assert_not_awaited()
    assert sent(server.house) == [
        "♪ No staff roles yet. Members with Manage Server are always staff. "
        "Add a role with !wisp staff add @role.",
        "♪ Usage: !wisp staff add @role",
    ]


async def test_a_command_that_fails_is_reported_in_its_channel(
    bot: app.WispBot,
    server: FakeServer,
    boss: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: Any) -> None:
        raise pymysql.err.OperationalError(2013, "Lost connection")

    monkeypatch.setattr(bot.settings, "add_staff_role", fail)

    await say(bot, server.message(f"!wisp staff add <@&{STAFF_ROLE_ID}>", boss))

    assert sent(server.here) == [
        "Error in !wisp staff add: OperationalError: (2013, 'Lost connection')"
    ]
    server.house.send.assert_not_awaited()


async def test_a_failure_in_the_track_drop_is_reported_in_the_house(
    bot: app.WispBot,
    server: FakeServer,
    boss: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: Any) -> None:
        raise pymysql.err.OperationalError(2013, "Lost connection")

    monkeypatch.setattr(bot.settings, "add_staff_role", fail)
    message = server.message(
        f"!wisp staff add <@&{STAFF_ROLE_ID}>", boss, channel=server.tracks
    )

    await say(bot, message)

    server.tracks.send.assert_not_awaited()
    assert sent(server.house) == [
        "Error in !wisp staff add: OperationalError: (2013, 'Lost connection')"
    ]


def test_the_staff_role_commands_are_a_loaded_extension() -> None:
    assert "cogs.staff" in app.EXTENSIONS
