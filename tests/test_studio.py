"""Tests for the Studio setup cog, run against fake Discord objects."""

import asyncio
import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import app
from cogs import studio
from cogs.studio import Studio, StudioError, ensure_studio, rules_text, studio_thread
from db.database import Database
from db.settings import SettingsRepo
from wisp import rules
from wisp.links import TrackKind

GUILD_ID = 100
FORUM_ID = 10
OTHER_FORUM_ID = 11
HOUSE_ID = 20
TRACKS_ID = 30
ERRORS_ID = 40

THREAD_NAMES = (
    "Status",
    "Mealtime",
    "The Lunchbox",
    "The Jam Space",
    "The Billboard",
    "How Wisp Works",
)
THREAD_ATTRS = (
    "status_thread_id",
    "mealtime_thread_id",
    "lunchbox_thread_id",
    "jam_thread_id",
    "billboard_thread_id",
    "rules_thread_id",
)


# ---
# Fakes
# ---


class FakeServer:
    """A guild with a Studio forum whose threads can be archived or deleted."""

    def __init__(self, forum_id: int = FORUM_ID) -> None:
        self.threads: dict[int, MagicMock] = {}
        self.messages: dict[int, MagicMock] = {}
        self.created_names: list[str] = []
        self._next_id = 1000
        self.errors = MagicMock(spec=discord.TextChannel)
        self.errors.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel.side_effect = self._get_channel
        self.guild.get_channel_or_thread.side_effect = self._get_errors
        self.forum = self.make_forum(forum_id)
        self.forums = {forum_id: self.forum}

    def make_forum(self, forum_id: int) -> MagicMock:
        forum = MagicMock(spec=discord.ForumChannel)
        forum.id = forum_id
        forum.is_media.return_value = False
        forum.mention = f"<#{forum_id}>"
        forum.guild = self.guild
        forum.create_thread = AsyncMock(
            side_effect=lambda **kwargs: self._create_thread(forum_id, **kwargs)
        )
        return forum

    def add_forum(self, forum_id: int) -> MagicMock:
        forum = self.make_forum(forum_id)
        self.forums[forum_id] = forum
        return forum

    def _get_channel(self, channel_id: int) -> MagicMock | None:
        return self.forums.get(channel_id)

    def _get_errors(self, channel_id: int) -> MagicMock | None:
        return self.errors if channel_id == ERRORS_ID else None

    def _create_thread(
        self, forum_id: int, *, name: str, content: str, **kwargs: Any
    ) -> discord.channel.ThreadWithMessage:
        self._next_id += 1
        thread = MagicMock(spec=discord.Thread)
        thread.id = self._next_id
        thread.name = name
        thread.parent_id = forum_id
        thread.archived = False
        thread.locked = False
        thread.edit = AsyncMock(side_effect=lambda **fields: self._edit(thread, fields))
        thread.fetch_message = AsyncMock(
            side_effect=lambda message_id: self._fetch_message(thread, message_id)
        )
        self._next_id += 1
        message = MagicMock(spec=discord.Message)
        message.id = self._next_id
        message.content = content
        message.pinned = False
        message.pin = AsyncMock(side_effect=lambda: setattr(message, "pinned", True))
        self.threads[thread.id] = thread
        self.messages[thread.id] = message
        self.created_names.append(name)
        thread.create_kwargs = kwargs
        return discord.channel.ThreadWithMessage(thread, message)

    def _edit(self, thread: MagicMock, fields: dict[str, Any]) -> MagicMock:
        for name, value in fields.items():
            setattr(thread, name, value)
        return thread

    def _fetch_message(self, thread: MagicMock, message_id: int) -> MagicMock:
        message = self.messages.get(thread.id)
        if message is None or message.id != message_id:
            raise discord.NotFound(MagicMock(status=404), "Unknown Message")
        return message

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        if channel_id not in self.threads:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return self.threads[channel_id]

    def thread_named(self, name: str) -> MagicMock:
        (match,) = [t for t in self.threads.values() if t.name == name]
        return match


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


@pytest.fixture
def cog(bot: app.WispBot) -> Studio:
    return Studio(bot)


def make_interaction(server: FakeServer, *, staff: bool = True) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.permissions = discord.Permissions(manage_guild=staff)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_channel(spec: type, channel_id: int) -> MagicMock:
    channel = MagicMock(spec=spec)
    channel.id = channel_id
    channel.mention = f"<#{channel_id}>"
    return channel


def make_role(role_id: int) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.mention = f"<@&{role_id}>"
    return role


async def run_setup(cog: Studio, server: FakeServer) -> MagicMock:
    interaction = make_interaction(server)
    await invoke(
        cog.setup_studio,
        cog,
        interaction,
        make_channel(discord.TextChannel, HOUSE_ID),
        server.forum,
        make_channel(discord.TextChannel, TRACKS_ID),
        make_channel(discord.TextChannel, ERRORS_ID),
    )
    return interaction


async def invoke(command: Any, cog: Studio, *args: Any) -> None:
    await command.callback(cog, *args)


def sent_text(interaction: MagicMock) -> str:
    send = (
        interaction.followup.send
        if interaction.response.defer.await_count
        else interaction.response.send_message
    )
    send.assert_awaited_once()
    (text,) = send.await_args.args
    assert send.await_args.kwargs == {"ephemeral": True}
    assert isinstance(text, str)
    return text


# ---
# Setup
# ---


async def test_setup_creates_all_six_threads(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    interaction = await run_setup(cog, server)

    assert server.created_names == list(THREAD_NAMES)
    settings = await bot.settings.get(GUILD_ID)
    assert settings.house_channel_id == HOUSE_ID
    assert settings.studio_forum_id == FORUM_ID
    assert settings.tracks_channel_id == TRACKS_ID
    assert settings.error_channel_id == ERRORS_ID
    for name, attr in zip(THREAD_NAMES, THREAD_ATTRS, strict=True):
        assert getattr(settings, attr) == server.thread_named(name).id

    status = server.thread_named("Status")
    billboard = server.thread_named("The Billboard")
    assert settings.status_message_id == server.messages[status.id].id
    assert settings.billboard_message_id == server.messages[billboard.id].id
    server.messages[status.id].pin.assert_awaited_once()
    server.messages[billboard.id].pin.assert_awaited_once()
    for name in ("Mealtime", "The Lunchbox", "The Jam Space", "How Wisp Works"):
        thread = server.thread_named(name)
        server.messages[thread.id].pin.assert_not_awaited()

    rules_thread = server.thread_named("How Wisp Works")
    assert server.messages[rules_thread.id].content == rules_text()
    rules_thread.edit.assert_awaited_once_with(locked=True)
    for thread in server.threads.values():
        assert thread.create_kwargs == {"auto_archive_duration": 10080}

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    text = sent_text(interaction)
    assert all(name in text for name in THREAD_NAMES)
    server.errors.send.assert_not_awaited()


async def test_setup_is_idempotent(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    first = await bot.settings.get(GUILD_ID)

    interaction = await run_setup(cog, server)

    assert server.created_names == list(THREAD_NAMES)
    assert await bot.settings.get(GUILD_ID) == first
    assert "already" in sent_text(interaction)
    assert server.thread_named("How Wisp Works").edit.await_count == 1
    assert server.messages[server.thread_named("Status").id].pin.await_count == 1
    server.errors.send.assert_not_awaited()


async def test_setup_recreates_deleted_thread(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    before = await bot.settings.get(GUILD_ID)
    old = server.thread_named("Mealtime")
    del server.threads[old.id]

    settings = await ensure_studio(bot, GUILD_ID)

    assert server.created_names == [*THREAD_NAMES, "Mealtime"]
    assert settings.mealtime_thread_id not in (None, old.id)
    assert settings.mealtime_thread_id == server.thread_named("Mealtime").id
    assert settings.status_thread_id == before.status_thread_id
    assert settings.status_message_id == before.status_message_id
    server.errors.send.assert_awaited_once()
    (line,) = server.errors.send.await_args.args
    assert "Mealtime" in line
    assert "Status" not in line


async def test_setup_recreates_a_pinned_card_thread_with_new_message_ids(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    before = await bot.settings.get(GUILD_ID)
    del server.threads[before.billboard_thread_id or 0]

    settings = await ensure_studio(bot, GUILD_ID)

    assert settings.billboard_thread_id != before.billboard_thread_id
    assert settings.billboard_message_id != before.billboard_message_id
    new_thread = server.thread_named("The Billboard")
    server.messages[new_thread.id].pin.assert_awaited_once()


async def test_pin_failure_is_reported_and_setup_carries_on(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    original = server.forum.create_thread.side_effect

    def failing_pin(**kwargs: Any) -> discord.channel.ThreadWithMessage:
        created: discord.channel.ThreadWithMessage = original(**kwargs)
        server.messages[created.thread.id].pin.side_effect = discord.Forbidden(
            MagicMock(status=403), "Missing Permissions"
        )
        return created

    server.forum.create_thread.side_effect = failing_pin

    await run_setup(cog, server)

    assert server.created_names == list(THREAD_NAMES)
    lines = [call.args[0] for call in server.errors.send.await_args_list]
    assert any("pinning the card in Status" in line for line in lines)
    assert any("pinning the card in The Billboard" in line for line in lines)


async def test_lock_failure_is_reported_and_setup_carries_on(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    original = server.forum.create_thread.side_effect

    def failing_lock(**kwargs: Any) -> discord.channel.ThreadWithMessage:
        created: discord.channel.ThreadWithMessage = original(**kwargs)
        if kwargs["name"] == "How Wisp Works":
            server.threads[created.thread.id].edit.side_effect = discord.Forbidden(
                MagicMock(status=403), "Missing Permissions"
            )
        return created

    server.forum.create_thread.side_effect = failing_lock

    await run_setup(cog, server)

    assert server.created_names == list(THREAD_NAMES)
    (line,) = [call.args[0] for call in server.errors.send.await_args_list]
    assert line.startswith("Error in locking How Wisp Works: Forbidden")


async def test_rerun_locks_an_existing_unlocked_rules_thread(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    rules_thread = server.thread_named("How Wisp Works")
    rules_thread.locked = False

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    assert rules_thread.locked is True
    assert rules_thread.edit.await_count == 2


async def test_rerun_pins_an_existing_unpinned_card(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    status_message = server.messages[server.thread_named("Status").id]
    status_message.pinned = False

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    assert status_message.pinned is True
    assert status_message.pin.await_count == 2
    billboard_message = server.messages[server.thread_named("The Billboard").id]
    billboard_message.pin.assert_awaited_once()


async def test_rerun_skips_a_card_whose_message_is_gone(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    status = server.thread_named("Status")
    del server.messages[status.id]

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    server.errors.send.assert_not_awaited()


async def test_thread_in_another_forum_is_recreated(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    server.add_forum(OTHER_FORUM_ID)
    await bot.settings.update(GUILD_ID, studio_forum_id=OTHER_FORUM_ID)

    settings = await ensure_studio(bot, GUILD_ID)

    assert len(server.created_names) == 12
    for attr in THREAD_ATTRS:
        thread_id = getattr(settings, attr)
        assert server.threads[thread_id].parent_id == OTHER_FORUM_ID


async def test_archived_thread_is_unarchived_not_recreated(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    mealtime = server.thread_named("Mealtime")
    mealtime.archived = True

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    mealtime.edit.assert_awaited_once_with(archived=False)
    server.errors.send.assert_not_awaited()


async def test_ensure_studio_without_a_forum_raises(bot: app.WispBot) -> None:
    with pytest.raises(StudioError, match="/wispadmin setup"):
        await ensure_studio(bot, GUILD_ID)


async def test_ensure_studio_with_a_non_forum_raises(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.forums[FORUM_ID] = MagicMock(spec=discord.TextChannel)
    await bot.settings.update(GUILD_ID, studio_forum_id=FORUM_ID)

    with pytest.raises(StudioError, match="forum"):
        await ensure_studio(bot, GUILD_ID)


async def test_ensure_studio_with_a_media_channel_raises(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.forum.is_media.return_value = True
    await bot.settings.update(GUILD_ID, studio_forum_id=FORUM_ID)

    with pytest.raises(StudioError, match="forum"):
        await ensure_studio(bot, GUILD_ID)


async def test_concurrent_ensure_creates_each_thread_once(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, studio_forum_id=FORUM_ID)

    await asyncio.gather(ensure_studio(bot, GUILD_ID), ensure_studio(bot, GUILD_ID))

    assert server.created_names == list(THREAD_NAMES)


# ---
# studio_thread
# ---


async def test_studio_thread_returns_the_stored_thread(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)

    thread = await studio_thread(bot, GUILD_ID, "mealtime_thread_id")

    assert thread is server.thread_named("Mealtime")
    thread.edit.assert_not_awaited()


async def test_studio_thread_unarchives(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    mealtime = server.thread_named("Mealtime")
    mealtime.archived = True

    thread = await studio_thread(bot, GUILD_ID, "mealtime_thread_id")

    assert thread is mealtime
    mealtime.edit.assert_awaited_once_with(archived=False)


async def test_studio_thread_recreates_a_deleted_thread(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(cog, server)
    old = server.thread_named("Mealtime")
    del server.threads[old.id]

    thread = await studio_thread(bot, GUILD_ID, "mealtime_thread_id")

    assert thread is not old
    assert thread is server.thread_named("Mealtime")
    assert (await bot.settings.get(GUILD_ID)).mealtime_thread_id == thread.id
    server.errors.send.assert_awaited_once()


async def test_studio_thread_rejects_an_unknown_setting(
    bot: app.WispBot,
) -> None:
    with pytest.raises(ValueError, match="frozen"):
        await studio_thread(bot, GUILD_ID, "frozen")


# ---
# Roles
# ---


async def test_roles_add_list_remove(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(server)
    await invoke(cog.roles_list, cog, interaction)
    assert "No qualifying roles" in sent_text(interaction)

    for role_id in (7, 5, 7):
        interaction = make_interaction(server)
        await invoke(cog.roles_add, cog, interaction, make_role(role_id))
        assert f"<@&{role_id}>" in sent_text(interaction)
    assert await bot.settings.roles(GUILD_ID) == {5, 7}

    interaction = make_interaction(server)
    await invoke(cog.roles_list, cog, interaction)
    listed = sent_text(interaction)
    assert listed.index("<@&5>") < listed.index("<@&7>")

    interaction = make_interaction(server)
    await invoke(cog.roles_remove, cog, interaction, make_role(5))
    assert "<@&5>" in sent_text(interaction)
    assert await bot.settings.roles(GUILD_ID) == {7}


# ---
# Freeze
# ---


async def test_freeze_sets_flag(
    cog: Studio, bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(server)
    await invoke(cog.freeze, cog, interaction)
    assert (await bot.settings.get(GUILD_ID)).frozen is True
    assert "frozen" in sent_text(interaction).lower()

    interaction = make_interaction(server)
    await invoke(cog.unfreeze, cog, interaction)
    assert (await bot.settings.get(GUILD_ID)).frozen is False
    assert "unfrozen" in sent_text(interaction).lower()


# ---
# Staff only
# ---


async def test_staff_only(cog: Studio, server: FakeServer) -> None:
    group = cog.wispadmin
    assert group.default_permissions == discord.Permissions(manage_guild=True)
    assert group.guild_only
    contexts = group.allowed_contexts
    assert contexts is not None
    assert (contexts.guild, contexts.dm_channel, contexts.private_channel) == (
        True,
        False,
        False,
    )
    installs = group.allowed_installs
    assert installs is not None
    assert (installs.guild, installs.user) == (True, False)

    leaves = [
        command
        for command in group.walk_commands()
        if isinstance(command, app_commands.Command)
    ]
    assert {command.qualified_name for command in leaves} == {
        "wispadmin setup",
        "wispadmin roles add",
        "wispadmin roles remove",
        "wispadmin roles list",
        "wispadmin freeze",
        "wispadmin unfreeze",
    }
    for command in leaves:
        assert command.checks, command.qualified_name
        for check in command.checks:
            assert check(make_interaction(server, staff=True))
            with pytest.raises(app_commands.MissingPermissions):
                check(make_interaction(server, staff=False))


def test_setup_command_options(cog: Studio) -> None:
    command = cog.wispadmin.get_command("setup")
    assert isinstance(command, app_commands.Command)
    params = {parameter.name: parameter for parameter in command.parameters}
    assert list(params) == ["house", "studio", "tracks", "errors"]
    assert discord.ChannelType.forum in params["studio"].channel_types
    assert discord.ChannelType.text not in params["studio"].channel_types
    assert discord.ChannelType.forum in params["tracks"].channel_types
    assert discord.ChannelType.text in params["tracks"].channel_types


# ---
# Extension
# ---


async def test_setup_registers_the_cog(bot: app.WispBot) -> None:
    bot.add_cog = AsyncMock()  # type: ignore[method-assign]

    await studio.setup(bot)

    bot.add_cog.assert_awaited_once()
    call = bot.add_cog.await_args
    assert call is not None
    (added,) = call.args
    assert isinstance(added, Studio)


def test_studio_is_a_loaded_extension() -> None:
    assert "cogs.studio" in app.EXTENSIONS


# ---
# How Wisp Works text
# ---


def test_rules_text_fits_one_message() -> None:
    assert len(rules_text()) < 2000


def test_rules_text_covers_every_topic() -> None:
    text = rules_text()
    for phrase in (
        "Active Lounger or higher",
        "/wisp board",
        "Suno",
        "viibrmusic.com",
        "track drop",
        "bond",
        "/wisp lunchbox",
        "banned",
    ):
        assert phrase in text, phrase
    for tier, _needed in rules.BOND_TIERS:
        assert tier in text


def test_rules_text_uses_bot_style() -> None:
    text = rules_text()
    assert "・" in text
    assert "♪" in text
    assert "・♪ ────────・──────── ♪・" in text
    emoji = "[🀀-🿿☀-♩♫-➿️]"
    assert not re.search(emoji, text)


def test_rules_text_numbers_come_from_the_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rules, "MEAL_POINTS", {TrackKind.VIIBR: 41, TrackKind.SUNO: 43})
    monkeypatch.setattr(rules, "DAILY_MEAL_CAP", 47)
    monkeypatch.setattr(rules, "MEET_AFTER_DAYS", 53)
    monkeypatch.setattr(
        rules,
        "BOND_TIERS",
        (("New face", 0), ("Familiar", 59), ("Friend", 61), ("Bandmate", 67)),
    )
    monkeypatch.setattr(
        rules,
        "BAN_LADDER",
        (timedelta(days=71), timedelta(days=73), None),
    )
    monkeypatch.setattr(rules, "NAME_MAX", 79)

    text = rules_text()

    for number in (41, 43, 47, 53, 59, 61, 67, 71, 73, 79):
        assert str(number) in text, number
    assert "permanent" in text
