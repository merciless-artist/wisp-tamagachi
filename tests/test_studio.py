"""Tests for the Studio setup and staff commands, run against fake Discord objects."""

import asyncio
import re
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import app
from cogs import faq, feeding, groups, pictures, studio
from cogs.speech import POKE_ID
from cogs.studio import (
    HOUSE_PANEL,
    StudioError,
    ensure_studio,
    rules_text,
    studio_thread,
)
from db.badges import BadgeRepo
from db.database import Database
from db.lives import LifeRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.life import new_egg
from wisp.links import TrackKind
from wisp.text import MESSAGE_LIMIT, SEPARATOR, text_length

GUILD_ID = 100
FORUM_ID = 10
OTHER_FORUM_ID = 11
HOUSE_ID = 20
TRACKS_ID = 30
COMMAND_CHANNEL_ID = 40

STATUS = "☀️ | Status"
MEALTIME = "🧡 | Mealtime"
VAULT = "🔒| The ViiBR Vault"
JAM = "⚡｜Jam Space"
FAQ = "📙｜Wisp FAQ"
THREAD_NAMES = (STATUS, MEALTIME, VAULT, JAM, FAQ)
THREAD_TITLES = ("Status", "Mealtime", "The ViiBR Vault", "Jam Space", "Wisp FAQ")
OLD_NAMES = ("Status", "Mealtime", "The ViiBR Vault", "The Jam Space", "How Wisp Works")
THUMBNAILS = {
    MEALTIME: "thumbs/mealtime.png",
    VAULT: "vault.png",
    JAM: "thumbs/jam_space.png",
    FAQ: "thumbs/faq.png",
}
FAQ_PICTURES = (
    "00_how_wisp_works.png",
    "01_the_basics.png",
    "02_feeding_him.png",
    "03_vault_and_snack_pack.png",
    "04_lunchbox_and_gifts.png",
    "05_your_bond.png",
    "06_growing_up.png",
    "07_talking_to_him.png",
    "08_games.png",
    "09_end_of_a_life.png",
    "10_fair_play.png",
)
FAQ_TITLES = (
    "How Wisp Works",
    "The Basics",
    "Feeding Him",
    "The ViiBR Vault and Your Snack Pack",
    "Wisp's Lunchbox and Gifts",
    "Your Bond",
    "Growing Up",
    "Talking to Him",
    "Games",
    "The End of a Life",
    "Fair Play",
)
EMOJI = "[🀀-🿿☀-♩♫-➿️]"
THREAD_ATTRS = (
    "status_thread_id",
    "mealtime_thread_id",
    "vault_thread_id",
    "jam_thread_id",
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
        self.deleted: list[int] = []
        self.created_names: list[str] = []
        self._next_id = 1000
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.id = HOUSE_ID
        self.house.mention = f"<#{HOUSE_ID}>"
        self.house.send = AsyncMock(side_effect=self._house_post)
        self.house.fetch_message = AsyncMock(side_effect=self._house_find)
        self.house_messages: dict[int, MagicMock] = {}
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.features = []
        self.roles: dict[int, MagicMock] = {}
        self.guild.get_role.side_effect = self.roles.get
        self.guild.create_role = AsyncMock(side_effect=self._create_role)
        self.guild.get_channel.side_effect = self._get_channel
        self.guild.get_channel_or_thread.side_effect = self._get_house
        self.forum = self.make_forum(forum_id)
        self.forums = {forum_id: self.forum}

    def _create_role(self, *, name: str, **_fields: Any) -> MagicMock:
        self._next_id += 1
        role = MagicMock(spec=discord.Role)
        role.id = self._next_id
        role.name = name
        role.display_icon = None
        self.roles[role.id] = role
        return role

    def _house_post(self, content: str | None = None, **fields: Any) -> MagicMock:
        self._next_id += 1
        message = MagicMock(spec=discord.Message)
        message.id = self._next_id
        message.content = content
        message.sent_kwargs = fields
        message.pinned = False
        message.pin = AsyncMock(side_effect=lambda: setattr(message, "pinned", True))
        message.components = button_rows(fields.get("view"))
        message.attachments = file_names([fields["file"]] if "file" in fields else [])
        message.edit = AsyncMock(
            side_effect=lambda **edited: self._house_edit(message, edited)
        )
        self.house_messages[message.id] = message
        return message

    def _house_edit(self, message: MagicMock, edited: dict[str, Any]) -> MagicMock:
        if "view" in edited:
            message.components = button_rows(edited["view"])
        if "attachments" in edited:
            message.attachments = file_names(edited["attachments"])
        return message

    def _house_find(self, message_id: int) -> MagicMock:
        if message_id not in self.house_messages:
            raise discord.NotFound(MagicMock(status=404), "Unknown Message")
        return self.house_messages[message_id]

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

    def _get_house(self, channel_id: int) -> MagicMock | None:
        return self.house if channel_id == HOUSE_ID else None

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
        thread.posts = []
        thread.send = AsyncMock(
            side_effect=lambda *args, **fields: self._post(thread, *args, **fields)
        )
        thread.edit = AsyncMock(side_effect=lambda **fields: self._edit(thread, fields))
        thread.fetch_message = AsyncMock(
            side_effect=lambda message_id: self._find(thread, message_id)
        )
        thread.get_partial_message.side_effect = lambda message_id: self._partial(
            thread, message_id
        )
        art = [kwargs["file"].filename] if "file" in kwargs else []
        message = self._message(thread, thread.id, content, art)
        self.threads[thread.id] = thread
        self.created_names.append(name)
        thread.create_kwargs = kwargs
        return discord.channel.ThreadWithMessage(thread, message)

    def add_thread(self, name: str, content: str) -> MagicMock:
        """A thread that already exists in the forum, as an older Wisp left it."""
        created = self._create_thread(self.forum.id, name=name, content=content)
        return self.threads[created.thread.id]

    def _message(
        self,
        thread: MagicMock,
        message_id: int,
        content: str | None,
        attachments: list[str],
    ) -> MagicMock:
        message = MagicMock(spec=discord.Message)
        message.id = message_id
        message.thread_id = thread.id
        message.content = content
        message.attachments = attachments
        message.sent_kwargs = {}
        message.pinned = False
        message.pin = AsyncMock(side_effect=lambda: setattr(message, "pinned", True))
        message.edit = AsyncMock(
            side_effect=lambda **fields: self._edit_message(message, fields)
        )
        self.messages[message_id] = message
        return message

    def _post(
        self, thread: MagicMock, content: str | None = None, **fields: Any
    ) -> MagicMock:
        self._next_id += 1
        art = fields.get("file")
        if art is not None:
            art.close()
        message = self._message(
            thread, self._next_id, content, [] if art is None else [art.filename]
        )
        message.sent_kwargs = fields
        thread.posts.append(message)
        return message

    def _partial(self, thread: MagicMock, message_id: int) -> MagicMock:
        async def edit(**fields: Any) -> MagicMock:
            found: MagicMock = await self._find(thread, message_id).edit(**fields)
            return found

        async def delete() -> None:
            self._find(thread, message_id)
            del self.messages[message_id]
            self.deleted.append(message_id)

        partial = MagicMock(spec=discord.PartialMessage)
        partial.id = message_id
        partial.edit = AsyncMock(side_effect=edit)
        partial.delete = AsyncMock(side_effect=delete)
        return partial

    def _edit(self, thread: MagicMock, fields: dict[str, Any]) -> MagicMock:
        for name, value in fields.items():
            setattr(thread, name, value)
        return thread

    def _edit_message(self, message: MagicMock, fields: dict[str, Any]) -> MagicMock:
        if "attachments" in fields:
            message.attachments = [file.filename for file in fields["attachments"]]
            for file in fields["attachments"]:
                file.close()
        if "content" in fields:
            message.content = fields["content"]
        return message

    def _find(self, thread: MagicMock, message_id: int) -> MagicMock:
        message = self.messages.get(message_id)
        if message is None or message.thread_id != thread.id:
            raise discord.NotFound(MagicMock(status=404), "Unknown Message")
        return message

    def live_posts(self, thread: MagicMock) -> list[MagicMock]:
        """The thread's posts after its first, leaving out deleted ones."""
        return [post for post in thread.posts if post.id in self.messages]

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        if channel_id not in self.threads:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return self.threads[channel_id]

    def thread_named(self, name: str) -> MagicMock:
        (match,) = [t for t in self.threads.values() if t.name == name]
        return match


def file_names(files: list[discord.File]) -> list[str]:
    """The names of uploaded files, closed once read."""
    for file in files:
        file.close()
    return [file.filename for file in files]


def button_rows(view: discord.ui.View | None) -> list[discord.ActionRow]:
    """The component rows Discord would return for a message sent with `view`."""
    if view is None:
        return []
    rows: list[Any] = view.to_components()
    return [discord.ActionRow(row) for row in rows]


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


def house_posts(server: FakeServer) -> list[Any]:
    """The House sends other than the Poke Wisp panel."""
    return [
        call
        for call in server.house.send.await_args_list
        if call.args != (HOUSE_PANEL,)
    ]


def panels(server: FakeServer) -> list[MagicMock]:
    return [
        message
        for message in server.house_messages.values()
        if message.content == HOUSE_PANEL
    ]


def thumbnail_added(message: MagicMock) -> bool:
    return any("attachments" in call.kwargs for call in message.edit.await_args_list)


def add_thumbnails(art_dir: Path) -> None:
    for relative in THUMBNAILS.values():
        path = art_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")


@pytest.fixture(autouse=True)
def art_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An ASSETS folder with only stand-in FAQ pictures, so no real art is sent."""
    faq_pictures = tmp_path / "faq"
    faq_pictures.mkdir()
    for name in FAQ_PICTURES:
        (faq_pictures / name).write_bytes(b"png")
    monkeypatch.setattr(studio, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(faq, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(pictures, "ASSETS_DIR", tmp_path)
    return tmp_path


def add_stage_art(art_dir: Path, *names: str) -> None:
    stages = art_dir / "stages"
    stages.mkdir(exist_ok=True)
    for name in names:
        (stages / f"{name}.png").write_bytes(b"png")


@pytest.fixture
def bot(
    db: Database, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.badges = BadgeRepo(db)
    wisp_bot.lives = LifeRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


def make_ctx(server: FakeServer, bot: app.WispBot) -> MagicMock:
    """A staff command used in a plain text channel of the fake guild."""
    ctx = MagicMock(spec=commands.Context)
    ctx.bot = bot
    ctx.guild = server.guild
    ctx.channel = MagicMock(spec=discord.TextChannel)
    ctx.channel.id = COMMAND_CHANNEL_ID
    ctx.channel.send = AsyncMock()
    return ctx


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


async def run_setup(
    bot: app.WispBot, server: FakeServer, tracks: MagicMock | None = None
) -> MagicMock:
    ctx = make_ctx(server, bot)
    await invoke(
        studio.setup_studio,
        ctx,
        server.house,
        server.forum,
        tracks or make_channel(discord.TextChannel, TRACKS_ID),
    )
    return ctx


async def invoke(command: Any, *args: Any) -> None:
    await command.callback(*args)


def sent_text(ctx: MagicMock) -> str:
    """The one answer posted in the command's channel, unable to ping."""
    send = ctx.channel.send
    send.assert_awaited_once()
    (text,) = send.await_args.args
    assert set(send.await_args.kwargs) == {"allowed_mentions"}
    mentions = send.await_args.kwargs["allowed_mentions"]
    assert mentions.to_dict() == discord.AllowedMentions.none().to_dict()
    assert isinstance(text, str)
    return text


# ---
# Setup
# ---


async def test_setup_creates_five_threads_with_the_vault(
    bot: app.WispBot, server: FakeServer
) -> None:
    ctx = await run_setup(bot, server)

    assert server.created_names == list(THREAD_NAMES)
    settings = await bot.settings.get(GUILD_ID)
    assert settings.house_channel_id == HOUSE_ID
    assert settings.studio_forum_id == FORUM_ID
    assert settings.tracks_channel_id == TRACKS_ID
    for name, attr in zip(THREAD_NAMES, THREAD_ATTRS, strict=True):
        assert getattr(settings, attr) == server.thread_named(name).id

    status = server.thread_named(STATUS)
    vault = server.thread_named(VAULT)
    rules_thread = server.thread_named(FAQ)
    assert settings.status_message_id == server.messages[status.id].id
    assert settings.vault_message_id == server.messages[vault.id].id
    for thread in (status, vault):
        server.messages[thread.id].pin.assert_awaited_once()
    for name in (MEALTIME, JAM, FAQ):
        thread = server.thread_named(name)
        server.messages[thread.id].pin.assert_not_awaited()

    rules_thread.edit.assert_awaited_once_with(locked=True)
    for thread in server.threads.values():
        assert thread.create_kwargs == {"auto_archive_duration": 10080}

    text = sent_text(ctx)
    assert f"Created threads: {', '.join(THREAD_TITLES)}" in text
    assert "・Badge roles created: Pickle Diplomat, Flame Keeper" in text
    assert not re.search(EMOJI, text)
    assert "Errors" not in text
    assert house_posts(server) == []


async def test_a_new_rules_post_shows_the_current_food_values(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, viibr_meal_points=12)

    await run_setup(bot, server)

    *_sections, rules_post = server.live_posts(server.thread_named(FAQ))
    assert rules_post.content == rules_text({TrackKind.VIIBR: 12, TrackKind.SUNO: 1})


async def test_new_threads_carry_their_thumbnails(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    add_thumbnails(art_dir)

    await run_setup(bot, server)

    attached = {
        thread.name: thread.create_kwargs.pop("file")
        for thread in server.threads.values()
        if "file" in thread.create_kwargs
    }
    assert {name: art.filename for name, art in attached.items()} == {
        MEALTIME: "mealtime.png",
        VAULT: "vault.png",
        JAM: "jam_space.png",
        FAQ: "faq.png",
    }
    for art in attached.values():
        art.close()
    assert not any(thumbnail_added(message) for message in server.messages.values())


async def test_threads_without_art_are_text_only(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)

    for thread in server.threads.values():
        assert thread.create_kwargs == {"auto_archive_duration": 10080}


async def test_a_starter_without_a_picture_gets_its_thumbnail(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    await run_setup(bot, server)
    add_thumbnails(art_dir)

    await ensure_studio(bot, GUILD_ID)

    for name, relative in THUMBNAILS.items():
        thread = server.thread_named(name)
        thread.fetch_message.assert_any_await(thread.id)
        assert server.messages[thread.id].attachments == [Path(relative).name]
    assert not thumbnail_added(server.messages[server.thread_named(STATUS).id])
    assert house_posts(server) == []


async def test_a_starter_that_has_a_picture_is_left_alone(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    add_thumbnails(art_dir)
    await run_setup(bot, server)

    await ensure_studio(bot, GUILD_ID)

    assert not any(thumbnail_added(message) for message in server.messages.values())


async def test_thumbnail_failure_is_posted_in_its_thread(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    await run_setup(bot, server)
    add_thumbnails(art_dir)
    mealtime = server.thread_named(MEALTIME)
    server.messages[mealtime.id].edit.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await ensure_studio(bot, GUILD_ID)

    (line,) = mealtime.send.await_args.args
    assert line.startswith("Error in adding the thumbnail to Mealtime: Forbidden")
    jam_starter = server.messages[server.thread_named(JAM).id]
    assert jam_starter.attachments == ["jam_space.png"]
    assert house_posts(server) == []


async def test_setup_is_idempotent(bot: app.WispBot, server: FakeServer) -> None:
    await run_setup(bot, server)
    first = await bot.settings.get(GUILD_ID)

    ctx = await run_setup(bot, server)

    assert server.created_names == list(THREAD_NAMES)
    assert await bot.settings.get(GUILD_ID) == first
    assert "Studio threads: all five already exist" in sent_text(ctx)
    assert server.thread_named(FAQ).edit.await_count == 1
    assert server.messages[server.thread_named(STATUS).id].pin.await_count == 1
    assert house_posts(server) == []


async def test_setup_recreates_deleted_thread(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    before = await bot.settings.get(GUILD_ID)
    old = server.thread_named(MEALTIME)
    del server.threads[old.id]

    settings = await ensure_studio(bot, GUILD_ID)

    assert server.created_names == [*THREAD_NAMES, MEALTIME]
    assert settings.mealtime_thread_id not in (None, old.id)
    assert settings.mealtime_thread_id == server.thread_named(MEALTIME).id
    assert settings.status_thread_id == before.status_thread_id
    assert settings.status_message_id == before.status_message_id
    (post,) = house_posts(server)
    assert post.args == ("Wisp's Studio: recreated Mealtime.",)
    assert post.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )


async def test_setup_recreates_a_pinned_card_thread_with_new_message_ids(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    before = await bot.settings.get(GUILD_ID)
    del server.threads[before.vault_thread_id or 0]

    settings = await ensure_studio(bot, GUILD_ID)

    assert settings.vault_thread_id != before.vault_thread_id
    assert settings.vault_message_id != before.vault_message_id
    new_thread = server.thread_named(VAULT)
    server.messages[new_thread.id].pin.assert_awaited_once()


async def test_pin_failure_is_posted_in_its_thread_and_setup_carries_on(
    bot: app.WispBot, server: FakeServer
) -> None:
    original = server.forum.create_thread.side_effect

    def failing_pin(**kwargs: Any) -> discord.channel.ThreadWithMessage:
        created: discord.channel.ThreadWithMessage = original(**kwargs)
        server.messages[created.thread.id].pin.side_effect = discord.Forbidden(
            MagicMock(status=403), "Missing Permissions"
        )
        return created

    server.forum.create_thread.side_effect = failing_pin

    await run_setup(bot, server)

    assert server.created_names == list(THREAD_NAMES)
    for name, title in ((STATUS, "Status"), (VAULT, "The ViiBR Vault")):
        (line,) = server.thread_named(name).send.await_args.args
        assert line.startswith(f"Error in pinning the card in {title}: Forbidden")
    server.thread_named(MEALTIME).send.assert_not_awaited()
    assert house_posts(server) == []


async def test_lock_failure_is_posted_in_its_thread_and_setup_carries_on(
    bot: app.WispBot, server: FakeServer
) -> None:
    original = server.forum.create_thread.side_effect

    def failing_lock(**kwargs: Any) -> discord.channel.ThreadWithMessage:
        created: discord.channel.ThreadWithMessage = original(**kwargs)
        if kwargs["name"] == FAQ:
            server.threads[created.thread.id].edit.side_effect = discord.Forbidden(
                MagicMock(status=403), "Missing Permissions"
            )
        return created

    server.forum.create_thread.side_effect = failing_lock

    await run_setup(bot, server)

    assert server.created_names == list(THREAD_NAMES)
    (line,) = server.thread_named(FAQ).send.await_args_list[0].args
    assert line.startswith("Error in locking Wisp FAQ: Forbidden")
    assert house_posts(server) == []


async def test_rerun_locks_an_existing_unlocked_rules_thread(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    rules_thread = server.thread_named(FAQ)
    rules_thread.locked = False

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    assert rules_thread.locked is True
    assert rules_thread.edit.await_count == 2


async def test_rerun_renames_threads_that_have_their_old_names(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    for thread, old in zip(server.threads.values(), OLD_NAMES, strict=True):
        thread.name = old

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    assert [thread.name for thread in server.threads.values()] == list(THREAD_NAMES)
    for thread in server.threads.values():
        thread.edit.assert_any_await(name=thread.name)
    assert house_posts(server) == []


async def test_rename_failure_is_posted_in_its_thread_and_the_rest_carry_on(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    mealtime = server.thread_named(MEALTIME)
    jam = server.thread_named(JAM)
    mealtime.name = "Mealtime"
    mealtime.edit.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )
    jam.name = "The Jam Space"

    await ensure_studio(bot, GUILD_ID)

    (line,) = mealtime.send.await_args.args
    assert line.startswith("Error in renaming Mealtime: Forbidden")
    assert jam.name == JAM
    assert house_posts(server) == []


async def test_rerun_pins_an_existing_unpinned_card(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    status_message = server.messages[server.thread_named(STATUS).id]
    status_message.pinned = False

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    assert status_message.pinned is True
    assert status_message.pin.await_count == 2
    vault_message = server.messages[server.thread_named(VAULT).id]
    vault_message.pin.assert_awaited_once()


async def test_rerun_skips_a_card_whose_message_is_gone(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    status = server.thread_named(STATUS)
    del server.messages[status.id]

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    assert house_posts(server) == []


async def test_thread_in_another_forum_is_recreated(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    server.add_forum(OTHER_FORUM_ID)
    await bot.settings.update(GUILD_ID, studio_forum_id=OTHER_FORUM_ID)

    settings = await ensure_studio(bot, GUILD_ID)

    assert len(server.created_names) == 2 * len(THREAD_NAMES)
    for attr in THREAD_ATTRS:
        thread_id = getattr(settings, attr)
        assert server.threads[thread_id].parent_id == OTHER_FORUM_ID


async def test_archived_thread_is_unarchived_not_recreated(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    mealtime = server.thread_named(MEALTIME)
    mealtime.archived = True

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == list(THREAD_NAMES)
    mealtime.edit.assert_awaited_once_with(archived=False)
    assert house_posts(server) == []


async def test_ensure_studio_without_a_forum_raises(bot: app.WispBot) -> None:
    with pytest.raises(StudioError, match="!wisp setup"):
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
# Wisp FAQ
# ---


def toc_lines(thread_id: int, message_ids: tuple[int, ...] | None) -> list[str]:
    assert message_ids is not None
    return [
        f"# [{title}](<https://discord.com/channels/{GUILD_ID}/{thread_id}/{id_}>)"
        for title, id_ in zip(FAQ_TITLES, message_ids, strict=True)
    ]


def sends_without_pinging(kwargs: dict[str, Any]) -> bool:
    return bool(
        kwargs["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
    )


def assert_faq_built(posts: list[MagicMock]) -> list[MagicMock]:
    """Check the posts are the eleven FAQ pictures then the rules post."""
    *sections, rules_post = posts
    assert [section.attachments for section in sections] == [
        [name] for name in FAQ_PICTURES
    ]
    assert all(section.content is None for section in sections)
    assert rules_post.attachments == []
    assert all(
        sends_without_pinging(post.sent_kwargs) for post in [*sections, rules_post]
    )
    return [*sections, rules_post]


async def test_setup_builds_the_faq_in_order(
    bot: app.WispBot, server: FakeServer
) -> None:
    tracks = make_channel(discord.TextChannel, TRACKS_ID)

    await run_setup(bot, server, tracks)

    thread = server.thread_named(FAQ)
    (first_post,) = [
        call.kwargs["content"]
        for call in server.forum.create_thread.await_args_list
        if call.kwargs["name"] == FAQ
    ]
    assert first_post == "Loading the FAQ..."
    *sections, rules_post = assert_faq_built(server.live_posts(thread))
    assert rules_post.content == rules_text(rules.MEAL_POINTS)
    settings = await bot.settings.get(GUILD_ID)
    assert settings.faq_message_ids == tuple(section.id for section in sections)
    assert settings.rules_message_id == rules_post.id
    starter = server.messages[thread.id]
    assert starter.content.splitlines() == toc_lines(
        thread.id, settings.faq_message_ids
    )
    assert sends_without_pinging(starter.edit.await_args.kwargs)
    assert thread.locked is True
    tracks.send.assert_not_called()
    assert house_posts(server) == []


async def test_the_faq_thread_has_its_thumbnail_and_table_of_contents(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    add_thumbnails(art_dir)

    await run_setup(bot, server)

    thread = server.thread_named(FAQ)
    starter = server.messages[thread.id]
    assert starter.attachments == ["faq.png"]
    settings = await bot.settings.get(GUILD_ID)
    assert starter.content.splitlines() == toc_lines(
        thread.id, settings.faq_message_ids
    )


async def test_food_command_edits_the_faq_rules_post(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    thread = server.thread_named(FAQ)
    posts = server.live_posts(thread)

    await invoke(feeding.set_food, make_ctx(server, bot), 12, 1)

    assert server.live_posts(thread) == posts
    assert posts[-1].content == rules_text({TrackKind.VIIBR: 12, TrackKind.SUNO: 1})
    assert sends_without_pinging(posts[-1].edit.await_args.kwargs)


async def test_an_old_how_wisp_works_thread_is_renamed_and_filled(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    add_thumbnails(art_dir)
    old = server.add_thread("How Wisp Works", rules_text(rules.MEAL_POINTS))
    old.locked = True
    await bot.settings.update(
        GUILD_ID,
        studio_forum_id=FORUM_ID,
        rules_thread_id=old.id,
        rules_message_id=old.id,
    )

    await ensure_studio(bot, GUILD_ID)

    assert server.created_names == ["How Wisp Works", STATUS, MEALTIME, VAULT, JAM]
    assert old.name == FAQ
    *sections, rules_post = assert_faq_built(server.live_posts(old))
    settings = await bot.settings.get(GUILD_ID)
    assert settings.rules_message_id == rules_post.id
    starter = server.messages[old.id]
    assert starter.attachments == ["faq.png"]
    assert starter.content.splitlines() == toc_lines(
        old.id, tuple(section.id for section in sections)
    )
    assert server.deleted == []
    assert house_posts(server) == []


async def test_a_built_faq_is_not_built_again(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    thread = server.thread_named(FAQ)
    posts = list(thread.posts)

    await ensure_studio(bot, GUILD_ID)

    assert thread.posts == posts
    assert server.deleted == []


async def test_missing_faq_pictures_are_posted_in_the_thread_and_setup_carries_on(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    missing = art_dir / "faq" / "05_your_bond.png"
    missing.unlink()

    ctx = await run_setup(bot, server)

    thread = server.thread_named(FAQ)
    (report,) = [post.content for post in thread.posts]
    assert report.startswith("Error in building the Wisp FAQ: FileNotFoundError")
    assert "05_your_bond.png" in report
    assert (await bot.settings.get(GUILD_ID)).faq_message_ids is None
    assert sent_text(ctx).startswith("♪ Wisp is set up.")
    assert house_posts(server) == []

    missing.write_bytes(b"png")
    await ensure_studio(bot, GUILD_ID)

    assert len(server.live_posts(thread)) == 1 + len(FAQ_PICTURES) + 1


async def test_a_build_that_fails_part_way_keeps_what_it_posted(
    bot: app.WispBot, server: FakeServer
) -> None:
    original = server.forum.create_thread.side_effect

    def flaky_faq(**kwargs: Any) -> discord.channel.ThreadWithMessage:
        created: discord.channel.ThreadWithMessage = original(**kwargs)
        if kwargs["name"] == FAQ:
            fake = server.threads[created.thread.id]
            post = fake.send.side_effect
            sends = 0

            def send(*args: Any, **fields: Any) -> MagicMock:
                nonlocal sends
                sends += 1
                if sends == 3:
                    raise discord.HTTPException(MagicMock(status=500), "Server Error")
                posted: MagicMock = post(*args, **fields)
                return posted

            fake.send.side_effect = send
        return created

    server.forum.create_thread.side_effect = flaky_faq

    await run_setup(bot, server)

    thread = server.thread_named(FAQ)
    first, second, report = server.live_posts(thread)
    assert report.content.startswith("Error in building the Wisp FAQ: HTTPException")
    settings = await bot.settings.get(GUILD_ID)
    assert settings.faq_message_ids == (first.id, second.id)
    assert server.messages[thread.id].content == "Loading the FAQ..."

    await ensure_studio(bot, GUILD_ID)

    assert server.deleted == [first.id, second.id]
    report_left, *rebuilt = server.live_posts(thread)
    assert report_left is report
    assert_faq_built(rebuilt)


async def test_a_faq_with_the_wrong_number_of_sections_is_rebuilt(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    thread = server.thread_named(FAQ)
    before = await bot.settings.get(GUILD_ID)
    assert before.faq_message_ids is not None
    await bot.settings.update(GUILD_ID, faq_message_ids=before.faq_message_ids[:-1])

    await ensure_studio(bot, GUILD_ID)

    assert server.deleted == [*before.faq_message_ids[:-1], before.rules_message_id]
    after = await bot.settings.get(GUILD_ID)
    assert after.faq_message_ids is not None
    assert len(after.faq_message_ids) == len(FAQ_PICTURES)
    live = server.live_posts(thread)
    assert live[0].id == before.faq_message_ids[-1]
    assert_faq_built(live[1:])


async def test_faq_command_deletes_and_reposts_the_faq(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    thread = server.thread_named(FAQ)
    before = await bot.settings.get(GUILD_ID)
    assert before.faq_message_ids is not None
    old_ids = [*before.faq_message_ids, before.rules_message_id]
    ctx = make_ctx(server, bot)

    await invoke(studio.rebuild_faq, ctx)

    assert server.deleted == old_ids
    *sections, rules_post = assert_faq_built(server.live_posts(thread))
    after = await bot.settings.get(GUILD_ID)
    assert after.faq_message_ids == tuple(section.id for section in sections)
    assert after.rules_message_id == rules_post.id
    assert rules_post.content == rules_text(rules.MEAL_POINTS)
    starter = server.messages[thread.id]
    assert starter.content.splitlines() == toc_lines(thread.id, after.faq_message_ids)
    assert sent_text(ctx) == "♪ The Wisp FAQ is rebuilt."
    assert server.created_names == list(THREAD_NAMES)
    assert house_posts(server) == []


async def test_faq_command_skips_posts_already_gone_and_never_the_first_post(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    thread = server.thread_named(FAQ)
    before = await bot.settings.get(GUILD_ID)
    assert before.faq_message_ids is not None
    gone, *kept = before.faq_message_ids
    del server.messages[gone]
    del server.messages[before.rules_message_id or 0]
    await bot.settings.update(GUILD_ID, rules_message_id=thread.id)
    ctx = make_ctx(server, bot)

    await invoke(studio.rebuild_faq, ctx)

    assert server.deleted == kept
    assert thread.id in server.messages
    assert_faq_built(server.live_posts(thread))
    assert sent_text(ctx) == "♪ The Wisp FAQ is rebuilt."


async def test_faq_command_without_a_studio_says_how_to_set_it_up(
    bot: app.WispBot, server: FakeServer
) -> None:
    ctx = make_ctx(server, bot)

    await invoke(studio.rebuild_faq, ctx)

    assert "!wisp setup" in sent_text(ctx)
    assert server.created_names == []


def test_table_of_contents_fits_one_message() -> None:
    biggest = tuple(10**20 - index for index in range(len(FAQ_TITLES)))

    text = faq.table_of_contents(10**20, 10**20, biggest)

    assert text.splitlines() == [
        f"# [{title}](<https://discord.com/channels/{10**20}/{10**20}/{id_}>)"
        for title, id_ in zip(FAQ_TITLES, biggest, strict=True)
    ]
    assert len(text) < MESSAGE_LIMIT


# ---
# House panel
# ---


def has_poke_button(message: MagicMock) -> bool:
    return [
        child.custom_id for row in message.components for child in row.children
    ] == [POKE_ID]


async def test_setup_posts_and_pins_the_poke_panel_in_the_house(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)

    (panel,) = panels(server)
    assert panel.pinned
    assert has_poke_button(panel)
    assert panel.sent_kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    assert (await bot.settings.get(GUILD_ID)).house_panel_message_id == panel.id
    assert not re.search(EMOJI, HOUSE_PANEL)


async def test_setup_gives_the_panel_wisps_current_picture(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    add_stage_art(art_dir, "egg", "baby")
    await bot.lives.insert(GUILD_ID, new_egg(1, discord.utils.utcnow()))

    await run_setup(bot, server)

    (panel,) = panels(server)
    assert panel.attachments == ["egg.png"]
    assert bot.shown_images[(GUILD_ID, "house_panel_message_id")] == (
        panel.id,
        "egg.png",
    )


async def test_a_rerun_adds_the_picture_to_a_panel_without_one(
    bot: app.WispBot, server: FakeServer, art_dir: Path
) -> None:
    await run_setup(bot, server)
    (panel,) = panels(server)
    assert panel.attachments == []
    add_stage_art(art_dir, "egg")
    await bot.lives.insert(GUILD_ID, new_egg(1, discord.utils.utcnow()))

    await run_setup(bot, server)

    assert panels(server) == [panel]
    assert panel.attachments == ["egg.png"]
    (edit,) = panel.edit.await_args_list
    assert set(edit.kwargs) == {"attachments"}


async def test_a_panel_without_art_is_posted_and_pinned_without_a_picture(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.lives.insert(GUILD_ID, new_egg(1, discord.utils.utcnow()))

    ctx = await run_setup(bot, server)

    (panel,) = panels(server)
    assert panel.attachments == []
    assert panel.pinned
    assert sent_text(ctx).startswith("♪ Wisp is set up.")


async def test_a_rerun_leaves_the_panel_alone(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    (panel,) = panels(server)

    await run_setup(bot, server)

    assert panels(server) == [panel]
    panel.pin.assert_awaited_once()
    panel.edit.assert_not_awaited()
    assert (await bot.settings.get(GUILD_ID)).house_panel_message_id == panel.id


async def test_a_rerun_pins_the_panel_again_and_gives_back_its_button(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    (panel,) = panels(server)
    panel.pinned = False
    panel.components = []

    await run_setup(bot, server)

    assert panels(server) == [panel]
    assert panel.pinned
    assert has_poke_button(panel)


async def test_a_deleted_panel_is_posted_again(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    (old,) = panels(server)
    del server.house_messages[old.id]

    await run_setup(bot, server)

    (panel,) = panels(server)
    assert panel is not old
    assert panel.pinned
    assert (await bot.settings.get(GUILD_ID)).house_panel_message_id == panel.id


async def test_a_panel_that_cannot_be_pinned_is_reported_where_setup_ran(
    bot: app.WispBot, server: FakeServer
) -> None:
    original = server.house.send.side_effect

    def unpinnable(*args: Any, **kwargs: Any) -> MagicMock:
        message: MagicMock = original(*args, **kwargs)
        message.pin.side_effect = discord.Forbidden(
            MagicMock(status=403), "Missing Permissions"
        )
        return message

    server.house.send.side_effect = unpinnable

    ctx = await run_setup(bot, server)

    (panel,) = panels(server)
    assert not panel.pinned
    assert (await bot.settings.get(GUILD_ID)).house_panel_message_id == panel.id
    report, answer = (call.args[0] for call in ctx.channel.send.await_args_list)
    assert report.startswith(
        "Error in setting up the Poke Wisp panel in Wisp's House: Forbidden"
    )
    assert answer.startswith("♪ Wisp is set up.")
    assert house_posts(server) == []


# ---
# studio_thread
# ---


async def test_studio_thread_returns_the_stored_thread(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)

    thread = await studio_thread(bot, GUILD_ID, "mealtime_thread_id")

    assert thread is server.thread_named(MEALTIME)
    thread.edit.assert_not_awaited()


async def test_studio_thread_unarchives(bot: app.WispBot, server: FakeServer) -> None:
    await run_setup(bot, server)
    mealtime = server.thread_named(MEALTIME)
    mealtime.archived = True

    thread = await studio_thread(bot, GUILD_ID, "mealtime_thread_id")

    assert thread is mealtime
    mealtime.edit.assert_awaited_once_with(archived=False)


async def test_studio_thread_recreates_a_deleted_thread(
    bot: app.WispBot, server: FakeServer
) -> None:
    await run_setup(bot, server)
    old = server.thread_named(MEALTIME)
    del server.threads[old.id]

    thread = await studio_thread(bot, GUILD_ID, "mealtime_thread_id")

    assert thread is not old
    assert thread is server.thread_named(MEALTIME)
    assert (await bot.settings.get(GUILD_ID)).mealtime_thread_id == thread.id
    assert len(house_posts(server)) == 1


async def test_studio_thread_rejects_an_unknown_setting(
    bot: app.WispBot,
) -> None:
    with pytest.raises(ValueError, match="frozen"):
        await studio_thread(bot, GUILD_ID, "frozen")


# ---
# Roles
# ---


async def test_roles_add_list_remove(bot: app.WispBot, server: FakeServer) -> None:
    ctx = make_ctx(server, bot)
    await invoke(studio.roles_list, ctx)
    assert "No qualifying roles" in sent_text(ctx)

    for role_id in (7, 5, 7):
        ctx = make_ctx(server, bot)
        await invoke(studio.roles_add, ctx, make_role(role_id))
        assert f"<@&{role_id}>" in sent_text(ctx)
    assert await bot.settings.roles(GUILD_ID) == {5, 7}

    ctx = make_ctx(server, bot)
    await invoke(studio.roles_list, ctx)
    listed = sent_text(ctx)
    assert listed.index("<@&5>") < listed.index("<@&7>")

    ctx = make_ctx(server, bot)
    await invoke(studio.roles_remove, ctx, make_role(5))
    assert "<@&5>" in sent_text(ctx)
    assert await bot.settings.roles(GUILD_ID) == {7}


# ---
# Freeze
# ---


async def test_freeze_sets_flag(bot: app.WispBot, server: FakeServer) -> None:
    ctx = make_ctx(server, bot)
    await invoke(studio.freeze, ctx)
    assert (await bot.settings.get(GUILD_ID)).frozen is True
    assert "frozen" in sent_text(ctx).lower()

    ctx = make_ctx(server, bot)
    await invoke(studio.unfreeze, ctx)
    assert (await bot.settings.get(GUILD_ID)).frozen is False
    assert "unfrozen" in sent_text(ctx).lower()


# ---
# Members' slash group
# ---


def assert_guild_only(group: app_commands.Group) -> None:
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


def test_members_group_is_open_to_everyone_in_guilds() -> None:
    assert groups.wisp.default_permissions is None
    assert_guild_only(groups.wisp)


# ---
# Extension
# ---


async def test_the_studio_commands_join_the_bot(bot: app.WispBot) -> None:
    await studio.setup(bot)

    assert bot.get_command("setup") is studio.setup_studio
    assert bot.get_command("freeze") is studio.freeze
    assert bot.get_command("unfreeze") is studio.unfreeze
    assert bot.get_command("eggs") is None
    assert bot.get_command("faq") is studio.rebuild_faq
    assert bot.get_command("roles") is studio.roles
    assert bot.get_command("roles add") is studio.roles_add
    assert bot.get_command("roles remove") is studio.roles_remove
    assert bot.get_command("roles list") is studio.roles_list


def test_studio_is_a_loaded_extension() -> None:
    assert "cogs.studio" in app.EXTENSIONS


# ---
# Rules post text
# ---


def test_rules_text_is_headed_as_the_quick_rules() -> None:
    assert rules_text(rules.MEAL_POINTS).startswith("♪ Quick rules (current numbers)\n")


def test_rules_text_fits_one_message() -> None:
    assert text_length(rules_text(rules.MEAL_POINTS)) < MESSAGE_LIMIT
    biggest = {kind: rules.MEAL_POINTS_MAX for kind in TrackKind}
    assert text_length(rules_text(biggest)) < MESSAGE_LIMIT


def test_rules_text_fits_with_every_number_at_four_digits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "DAILY_MEAL_CAP",
        "MEET_AFTER_DAYS",
        "NAME_MAX",
        "OLD_FOGEY_AT_DAY",
        "FAREWELL_AT_DAY",
        "LAST_EMBER_GIFTS",
        "EGG_FOOD_NEEDED",
        "COAL_EGG_FOOD",
        "GIFT_COST",
        "BOND_PER_KEPT_GIFT",
        "COLLECTION_BOND_BONUS",
        "HAPPY_FULL_AT_PEOPLE",
        "PLAYS_PER_DAY",
        "SICK_EXTRA_MEAL_CAP",
    ):
        monkeypatch.setattr(rules, name, 9999)
    monkeypatch.setattr(rules, "SICK_FOR", timedelta(hours=9999))
    monkeypatch.setattr(
        rules,
        "BOND_TIERS",
        (("New face", 0), ("Familiar", 9999), ("Friend", 9999), ("Bandmate", 9999)),
    )
    monkeypatch.setattr(
        rules, "BAN_LADDER", (timedelta(days=9999), timedelta(days=9999), None)
    )

    text = rules_text({kind: 9999 for kind in TrackKind})

    assert "9999" in text
    assert text_length(text) < MESSAGE_LIMIT


def test_rules_text_shows_the_food_values_it_is_given() -> None:
    text = rules_text({TrackKind.VIIBR: 12, TrackKind.SUNO: 1})

    assert "・viibrmusic.com track: 12 meal points" in text
    assert "・Suno track: 1 meal point" in text


def test_rules_text_has_meters_vault_life_and_talking_sections() -> None:
    text = rules_text(rules.MEAL_POINTS)

    for heading in (
        "His meters",
        "The ViiBR Vault",
        "His life",
        "Talking to Wisp",
    ):
        assert f"\n{heading}\n" in text, heading
    assert "The Lunchbox" not in text
    assert "/wisp vault" in text
    assert "leaderboard" in text
    assert "Old Fogey" in text
    assert "Last Ember" in text
    assert "coal" in text
    assert "neglect" in text
    assert "Mention or reply to him in Wisp's House" in text
    assert "your lunchbox" not in text.lower()


def test_rules_text_points_to_the_snack_pack_and_wisps_lunchbox() -> None:
    text = rules_text(rules.MEAL_POINTS)

    section = text.split("\nThe ViiBR Vault\n")[1].split("\n\n")[0]
    assert (
        "・/wisp snackpack: your snacks and keepsakes. "
        "/wisp lunchbox: his favorites and gifts" in section
    )


def test_rules_text_explains_the_three_meters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rules, "HAPPY_FULL_AT_PEOPLE", 7)
    monkeypatch.setattr(rules, "PLAYS_PER_DAY", 3)

    text = rules_text(rules.MEAL_POINTS)

    section = text.split("\nHis meters\n")[1].split("\n\n")[0]
    full, happy, care = section.split("\n")
    assert full.startswith("・Full: tracks and snacks")
    assert "hangry" in full and "dies at 0" in full
    assert happy.startswith("・Happy: your first poke or chat each day earns 1 point")
    assert "7 people in 24 h" in happy and "Rockstar" in happy
    assert care.startswith("・Care: rhyme duels (1 point, 3 a day) and gifts")
    assert "lonely" in care and "never hurt" in care
    assert "\nWho can feed him and earn points\n" in text


def test_rules_text_explains_the_cold_and_the_bigger_meal_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rules, "DAILY_MEAL_CAP", 20)
    monkeypatch.setattr(rules, "SICK_EXTRA_MEAL_CAP", 7)
    monkeypatch.setattr(rules, "SICK_FOR", timedelta(hours=36))

    text = rules_text(rules.MEAL_POINTS)

    assert "・Your meals and snacks count up to 20 points a day" in text
    cold = next(line for line in text.split("\n") if "cold" in line)
    assert "Once before Adult" in cold
    assert "36-hour cold" in cold
    assert "he can't die" in cold
    assert "meals count up to 27 a day" in cold


def test_rules_text_does_not_say_talking_earns_no_points() -> None:
    text = rules_text(rules.MEAL_POINTS)

    assert "no bond or points" not in text
    assert "Talking earns no bond" in text


def test_rules_text_explains_gifts_with_numbers_from_the_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rules, "GIFT_COST", 107)
    monkeypatch.setattr(rules, "BOND_PER_KEPT_GIFT", 109)
    monkeypatch.setattr(rules, "COLLECTION_BOND_BONUS", 113)

    text = rules_text(rules.MEAL_POINTS)

    section = text.split("\nThe ViiBR Vault\n")[1].split("\n\n")[0]
    assert "snacks and gifts" in section
    assert "・Gifts cost 107 points and he might not keep them" in section
    assert "109 bond" in section and "113 more" in section
    assert "New Wisps start over" in section


def test_rules_text_covers_every_topic() -> None:
    text = rules_text(rules.MEAL_POINTS)
    for phrase in (
        "Active Lounger or higher",
        "/wisp board",
        "Suno",
        "viibrmusic.com",
        "track drop",
        "bond",
        "/wisp snackpack",
        "banned",
    ):
        assert phrase in text, phrase
    for tier, _needed in rules.BOND_TIERS:
        assert tier in text


def test_rules_text_uses_bot_style() -> None:
    text = rules_text(rules.MEAL_POINTS)
    assert "・" in text
    assert "♪" in text
    assert SEPARATOR in text
    assert not re.search(EMOJI, text.replace(SEPARATOR, ""))


def test_rules_text_numbers_come_from_the_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rules, "MEAL_POINTS", {TrackKind.VIIBR: 41, TrackKind.SUNO: 43})
    monkeypatch.setattr(rules, "DAILY_MEAL_CAP", 47)
    monkeypatch.setattr(rules, "HAPPY_FULL_AT_PEOPLE", 107)
    monkeypatch.setattr(rules, "PLAYS_PER_DAY", 109)
    monkeypatch.setattr(rules, "SICK_EXTRA_MEAL_CAP", 113)
    monkeypatch.setattr(rules, "SICK_FOR", timedelta(hours=127))
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
    monkeypatch.setattr(rules, "OLD_FOGEY_AT_DAY", 83)
    monkeypatch.setattr(rules, "FAREWELL_AT_DAY", 89)
    monkeypatch.setattr(rules, "LAST_EMBER_GIFTS", 97)
    monkeypatch.setattr(rules, "EGG_FOOD_NEEDED", 101)
    monkeypatch.setattr(rules, "COAL_EGG_FOOD", 103)

    text = rules_text(rules.MEAL_POINTS)

    for number in (41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103):
        assert str(number) in text, number
    for number in (107, 109, 127, 160):
        assert str(number) in text, number
    assert "permanent" in text
