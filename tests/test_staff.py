"""Tests for the `!wisp` staff commands, typed as messages and run through the prefix.

Discord objects are fakes; the repositories are the real ones. Ids are full
length snowflakes, since the converters only read mentions of those.
"""

import asyncio
import importlib
from collections.abc import AsyncIterator, Iterable
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock

import discord
import pymysql
import pytest

import app
from cogs import discipline, feeding, groups, staff, studio
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import Settings, SettingsRepo
from wisp.rules import MEAL_POINTS_MAX

WISP_ID = 900000000000000001
OWNER_ID = 900000000000000002
STAFF_ID = 900000000000000003
MEMBER_ID = 900000000000000004
GUILD_ID = 910000000000000001
HOUSE_ID = 920000000000000001
TRACKS_ID = 920000000000000002
HERE_ID = 920000000000000003
TRACK_THREAD_ID = 920000000000000004
STUDIO_ID = 920000000000000005
FORUM_DROP_ID = 920000000000000006
STAFF_ROLE_ID = 930000000000000001
OTHER_ROLE_ID = 930000000000000002
NO_PING = discord.AllowedMentions.none().to_dict()
COMMANDS = (
    "setup, roles, faq, freeze, unfreeze, eggs, food, punish, unban, strip, "
    "resetname, staff"
)
FOOD_USAGE = (
    "♪ Usage: !wisp food <viibr points> <suno points> " f"(each 0 to {MEAL_POINTS_MAX})"
)

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
        self.house = self.add_channel(discord.TextChannel, HOUSE_ID, "house")
        self.tracks = self.add_channel(discord.TextChannel, TRACKS_ID, "tracks")
        self.here = self.add_channel(discord.TextChannel, HERE_ID, "staff-chat")
        self.track_thread = self.add_channel(discord.Thread, TRACK_THREAD_ID, "t")
        self.track_thread.parent_id = TRACKS_ID
        self.studio = self.add_channel(discord.ForumChannel, STUDIO_ID, "studio")
        self.forum_drop = self.add_channel(
            discord.ForumChannel, FORUM_DROP_ID, "forum-drop"
        )
        self.guild.text_channels = [self.house, self.tracks, self.here]
        self.guild.forums = [self.studio, self.forum_drop]
        self.roles = {
            role_id: make_role(role_id) for role_id in (STAFF_ROLE_ID, OTHER_ROLE_ID)
        }
        self.guild.get_channel.side_effect = self.channels.get
        self.guild.get_channel_or_thread.side_effect = self.channels.get
        self.guild._roles = self.roles
        self.guild.get_role.side_effect = self.roles.get
        self.guild.get_member.return_value = None
        self.guild.get_member_named.return_value = None
        self.guild.query_members = AsyncMock(return_value=[])

    def add_channel(self, spec: type, channel_id: int, name: str) -> MagicMock:
        channel = MagicMock(spec=spec)
        channel.id = channel_id
        channel.name = name
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
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.owner_id = OWNER_ID
    wisp = server.member(WISP_ID, bot=True)
    monkeypatch.setattr(app.WispBot, "user", wisp)
    monkeypatch.setattr(wisp_bot, "loop", asyncio.get_running_loop())
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    await wisp_bot.settings.update(
        GUILD_ID, house_channel_id=HOUSE_ID, tracks_channel_id=TRACKS_ID
    )
    for extension in (studio, feeding, discipline, staff):
        await extension.setup(wisp_bot)
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

    assert sent(server.here) == [f"♪ Wisp staff commands: {COMMANDS}"]


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


# ---
# Each command through the prefix
# ---


@pytest.fixture
def no_studio_work(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stand in for the Studio and badge role work, which test_studio covers."""
    calls: list[str] = []

    async def ensure_studio(bot: app.WispBot, guild_id: int) -> Settings:
        calls.append("studio")
        return await bot.settings.get(guild_id)

    async def ensure_badge_roles(
        _bot: app.WispBot, _guild: object, where: object
    ) -> list[str]:
        calls.append(f"badges in {getattr(where, 'id', None)}")
        return ["・Badge roles: all 2 ready"]

    monkeypatch.setattr(studio, "ensure_studio", ensure_studio)
    monkeypatch.setattr(studio, "ensure_badge_roles", ensure_badge_roles)
    return calls


@pytest.mark.parametrize(
    "arguments",
    [
        f"<#{HOUSE_ID}> <#{STUDIO_ID}> <#{TRACKS_ID}>",
        f"{HOUSE_ID} {STUDIO_ID} {TRACKS_ID}",
        "house studio tracks",
    ],
    ids=["mentions", "ids", "names"],
)
async def test_setup(
    bot: app.WispBot,
    server: FakeServer,
    boss: MagicMock,
    no_studio_work: list[str],
    arguments: str,
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=None, tracks_channel_id=None)

    await say(bot, server.message(f"!wisp setup {arguments}", boss))

    settings = await bot.settings.get(GUILD_ID)
    assert (
        settings.house_channel_id,
        settings.studio_forum_id,
        settings.tracks_channel_id,
    ) == (HOUSE_ID, STUDIO_ID, TRACKS_ID)
    assert no_studio_work == ["studio", f"badges in {HERE_ID}"]
    assert sent(server.here) == [
        "♪ Wisp is set up.\n"
        f"・Wisp's House: <#{HOUSE_ID}>\n"
        f"・Wisp's Studio: <#{STUDIO_ID}>\n"
        f"・Track drop: <#{TRACKS_ID}>\n"
        "・Studio threads: all five already exist\n"
        "・Badge roles: all 2 ready"
    ]


async def test_setup_takes_a_forum_as_the_track_drop(
    bot: app.WispBot, server: FakeServer, boss: MagicMock, no_studio_work: list[str]
) -> None:
    content = f"!wisp setup <#{HOUSE_ID}> <#{STUDIO_ID}> <#{FORUM_DROP_ID}>"

    await say(bot, server.message(content, boss))

    assert (await bot.settings.get(GUILD_ID)).tracks_channel_id == FORUM_DROP_ID


@pytest.mark.parametrize(
    "arguments",
    [
        f"<#{HOUSE_ID}> <#{HERE_ID}> <#{TRACKS_ID}>",
        f"<#{STUDIO_ID}> <#{STUDIO_ID}> <#{TRACKS_ID}>",
        f"<#{HOUSE_ID}> <#{STUDIO_ID}>",
        f"<#{HOUSE_ID}> <#{STUDIO_ID}> <#920000000000000099>",
    ],
    ids=["a text studio", "a forum house", "no track drop", "an unknown channel"],
)
async def test_setup_with_the_wrong_channels_gets_the_usage_line(
    bot: app.WispBot,
    server: FakeServer,
    boss: MagicMock,
    no_studio_work: list[str],
    arguments: str,
) -> None:
    await say(bot, server.message(f"!wisp setup {arguments}", boss))

    assert sent(server.here) == ["♪ Usage: !wisp setup #house #studio #tracks"]
    assert no_studio_work == []
    assert (await bot.settings.get(GUILD_ID)).studio_forum_id is None


async def test_roles(bot: app.WispBot, server: FakeServer, boss: MagicMock) -> None:
    for content in (
        "!wisp roles list",
        f"!wisp roles add <@&{OTHER_ROLE_ID}>",
        f"!wisp roles add <@&{STAFF_ROLE_ID}>",
        "!wisp roles list",
        f"!wisp roles remove <@&{STAFF_ROLE_ID}>",
        "!wisp roles add",
        "!wisp roles",
    ):
        await say(bot, server.message(content, boss))

    assert sent(server.here) == [
        "♪ No qualifying roles yet. Add one with !wisp roles add @role.",
        f"♪ <@&{OTHER_ROLE_ID}> can now feed Wisp.",
        f"♪ <@&{STAFF_ROLE_ID}> can now feed Wisp.",
        f"♪ Roles that can feed Wisp\n・<@&{STAFF_ROLE_ID}>\n・<@&{OTHER_ROLE_ID}>",
        f"♪ <@&{STAFF_ROLE_ID}> no longer feeds Wisp.",
        "♪ Usage: !wisp roles add @role",
        "♪ Usage: !wisp roles add @role | remove @role | list",
    ]
    assert await bot.settings.roles(GUILD_ID) == {OTHER_ROLE_ID}
    assert await bot.settings.staff_roles(GUILD_ID) == set()


async def test_food(
    bot: app.WispBot,
    server: FakeServer,
    boss: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refresh = AsyncMock()
    monkeypatch.setattr(feeding, "refresh_rules", refresh)

    await say(bot, server.message("!wisp food 12 0", boss))

    settings = await bot.settings.get(GUILD_ID)
    assert (settings.viibr_meal_points, settings.suno_meal_points) == (12, 0)
    refresh.assert_awaited_once_with(bot, GUILD_ID)
    assert sent(server.here) == [
        "♪ Food values: viibrmusic.com track 12 meal points, "
        "Suno track 0 meal points."
    ]


@pytest.mark.parametrize(
    "arguments", ["", "5", "five 1", f"{MEAL_POINTS_MAX + 1} 1", "1 -1"]
)
async def test_food_out_of_range_or_missing_gets_the_usage_line(
    bot: app.WispBot, server: FakeServer, boss: MagicMock, arguments: str
) -> None:
    await say(bot, server.message(f"!wisp food {arguments}", boss))

    assert sent(server.here) == [FOOD_USAGE]
    settings = await bot.settings.get(GUILD_ID)
    assert (settings.viibr_meal_points, settings.suno_meal_points) == (None, None)


async def test_freeze_and_unfreeze(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    await say(bot, server.message("!wisp freeze", boss))
    assert (await bot.settings.get(GUILD_ID)).frozen is True

    await say(bot, server.message("!wisp unfreeze", boss))
    assert (await bot.settings.get(GUILD_ID)).frozen is False

    assert sent(server.here) == [
        "♪ Wisp is frozen. His care will not drain until you unfreeze him.",
        "♪ Wisp is unfrozen. His care drains normally again.",
    ]


async def test_eggs(bot: app.WispBot, server: FakeServer, boss: MagicMock) -> None:
    await say(bot, server.message("!wisp eggs off", boss))
    assert (await bot.settings.get(GUILD_ID)).lay_eggs is False

    await say(bot, server.message("!wisp eggs maybe", boss))
    await say(bot, server.message("!wisp eggs", boss))
    assert (await bot.settings.get(GUILD_ID)).lay_eggs is False

    await say(bot, server.message("!wisp eggs on", boss))
    assert (await bot.settings.get(GUILD_ID)).lay_eggs is True

    assert sent(server.here) == [
        "♪ New eggs are off. When Wisp's life ends, no new egg will be laid "
        "until you turn eggs back on.",
        "♪ Usage: !wisp eggs on|off",
        "♪ Usage: !wisp eggs on|off",
        "♪ New eggs are on. A new egg arrives within a few minutes.",
    ]


async def test_faq(
    bot: app.WispBot,
    server: FakeServer,
    boss: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = MagicMock(spec=discord.Thread)
    fill_faq = AsyncMock()
    monkeypatch.setattr(studio, "studio_thread", AsyncMock(return_value=thread))
    monkeypatch.setattr(studio, "fill_faq", fill_faq)

    await say(bot, server.message("!wisp faq", boss))

    fill_faq.assert_awaited_once_with(bot, GUILD_ID, thread, ANY)
    assert sent(server.here) == ["♪ The Wisp FAQ is rebuilt."]


async def test_faq_without_a_studio_says_how_to_set_it_up(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    await say(bot, server.message("!wisp faq", boss))

    assert sent(server.here) == ["The Studio forum is not set. Run !wisp setup first."]


async def test_punish_takes_the_rest_of_the_line_as_the_reason(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    cheater = server.member(MEMBER_ID)
    content = f"!wisp punish <@{MEMBER_ID}> posted   a fake link, twice"

    await say(bot, server.message(content, boss, mentions=[cheater]))

    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert player.offenses == 1
    assert sent(server.here) == [
        f"♪ <@{STAFF_ID}> punished <@{MEMBER_ID}> (offense 1, 1 day): "
        "posted   a fake link, twice\n"
        "・Wisp has no life right now, so nothing was posted in his House."
    ]


@pytest.mark.parametrize(
    "arguments", ["", f"<@{MEMBER_ID}>", "nobody at all", f"<@{MEMBER_ID}> {'x' * 501}"]
)
async def test_punish_without_a_member_or_reason_gets_the_usage_line(
    bot: app.WispBot, server: FakeServer, boss: MagicMock, arguments: str
) -> None:
    cheater = server.member(MEMBER_ID)
    message = server.message(f"!wisp punish {arguments}", boss, mentions=[cheater])

    await say(bot, message)

    assert sent(server.here) == ["♪ Usage: !wisp punish @member <reason>"]
    assert (await bot.players.get(GUILD_ID, MEMBER_ID)).offenses == 0


async def test_unban_strip_and_resetname(
    bot: app.WispBot, server: FakeServer, boss: MagicMock
) -> None:
    member = server.member(MEMBER_ID)
    mention = f"<@{MEMBER_ID}>"
    await bot.players.set_offense(GUILD_ID, MEMBER_ID, 1, None, True)
    await bot.players.add_points(GUILD_ID, MEMBER_ID, 10)
    await bot.players.set_name(GUILD_ID, MEMBER_ID, "Nova")

    for content in (
        f"!wisp unban {mention}",
        f"!wisp strip {mention} 4",
        f"!wisp strip {mention} 0",
        f"!wisp strip {mention}",
        f"!wisp resetname {mention}",
        "!wisp unban",
    ):
        await say(bot, server.message(content, boss, mentions=[member]))

    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert not player.is_banned(discord.utils.utcnow())
    assert (player.balance, player.name) == (6, None)
    assert sent(server.here) == [
        f"♪ {mention} can play with Wisp again. Their offense count stays at 1.",
        f"♪ Took 4 points from {mention}.",
        "♪ Usage: !wisp strip @member <points>",
        "♪ Usage: !wisp strip @member <points>",
        f"♪ Wisp forgot {mention}'s name. They can choose a new one.",
        "♪ Usage: !wisp unban @member",
    ]


# ---
# The slash commands
# ---


def test_the_staff_slash_group_is_gone() -> None:
    assert not hasattr(groups, "wispadmin")


def test_the_members_slash_commands_are_still_registered() -> None:
    for extension in app.EXTENSIONS:
        importlib.import_module(extension)
    names = {command.qualified_name for command in groups.wisp.walk_commands()}

    assert names == {
        "wisp status",
        "wisp vault",
        "wisp snackpack",
        "wisp board",
        "wisp lunchbox",
        "wisp play",
        "wisp play rhyme",
    }
