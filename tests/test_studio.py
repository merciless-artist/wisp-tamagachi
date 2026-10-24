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

import app
from cogs import faq, feeding, groups, studio
from cogs.studio import StudioError, ensure_studio, rules_text, studio_thread
from db.database import Database
from db.settings import SettingsRepo
from wisp import rules
from wisp.links import TrackKind
from wisp.text import MESSAGE_LIMIT

GUILD_ID = 100
FORUM_ID = 10
OTHER_FORUM_ID = 11
HOUSE_ID = 20
TRACKS_ID = 30

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
        self.house.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel.side_effect = self._get_channel
        self.guild.get_channel_or_thread.side_effect = self._get_house
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


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


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
    pictures = tmp_path / "faq"
    pictures.mkdir()
    for name in FAQ_PICTURES:
        (pictures / name).write_bytes(b"png")
    monkeypatch.setattr(studio, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(faq, "ASSETS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def bot(
    db: Database, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


def make_interaction(
    server: FakeServer, bot: app.WispBot, *, staff: bool = True
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
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


async def run_setup(
    bot: app.WispBot, server: FakeServer, tracks: MagicMock | None = None
) -> MagicMock:
    interaction = make_interaction(server, bot)
    await invoke(
        studio.setup_studio,
        interaction,
        server.house,
        server.forum,
        tracks or make_channel(discord.TextChannel, TRACKS_ID),
    )
    return interaction


async def invoke(command: Any, *args: Any) -> None:
    await command.callback(*args)


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


async def test_setup_creates_five_threads_with_the_vault(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = await run_setup(bot, server)

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

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    text = sent_text(interaction)
    assert f"Created threads: {', '.join(THREAD_TITLES)}" in text
    assert not re.search(EMOJI, text)
    assert "Errors" not in text
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_not_awaited()


async def test_setup_is_idempotent(bot: app.WispBot, server: FakeServer) -> None:
    await run_setup(bot, server)
    first = await bot.settings.get(GUILD_ID)

    interaction = await run_setup(bot, server)

    assert server.created_names == list(THREAD_NAMES)
    assert await bot.settings.get(GUILD_ID) == first
    assert "Studio threads: all five already exist" in sent_text(interaction)
    assert server.thread_named(FAQ).edit.await_count == 1
    assert server.messages[server.thread_named(STATUS).id].pin.await_count == 1
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_awaited_once()
    (line,) = server.house.send.await_args.args
    assert line == "Wisp's Studio: recreated Mealtime."
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == (
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
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_not_awaited()


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
    server.house.send.assert_not_awaited()


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

    await invoke(feeding.set_food, make_interaction(server, bot), 12, 1)

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
    server.house.send.assert_not_awaited()


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

    interaction = await run_setup(bot, server)

    thread = server.thread_named(FAQ)
    (report,) = [post.content for post in thread.posts]
    assert report.startswith("Error in building the Wisp FAQ: FileNotFoundError")
    assert "05_your_bond.png" in report
    assert (await bot.settings.get(GUILD_ID)).faq_message_ids is None
    assert sent_text(interaction).startswith("♪ Wisp is set up.")
    server.house.send.assert_not_awaited()

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
    interaction = make_interaction(server, bot)

    await invoke(studio.rebuild_faq, interaction)

    assert server.deleted == old_ids
    *sections, rules_post = assert_faq_built(server.live_posts(thread))
    after = await bot.settings.get(GUILD_ID)
    assert after.faq_message_ids == tuple(section.id for section in sections)
    assert after.rules_message_id == rules_post.id
    assert rules_post.content == rules_text(rules.MEAL_POINTS)
    starter = server.messages[thread.id]
    assert starter.content.splitlines() == toc_lines(thread.id, after.faq_message_ids)
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert sent_text(interaction) == "♪ The Wisp FAQ is rebuilt."
    assert server.created_names == list(THREAD_NAMES)
    server.house.send.assert_not_awaited()


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
    interaction = make_interaction(server, bot)

    await invoke(studio.rebuild_faq, interaction)

    assert server.deleted == kept
    assert thread.id in server.messages
    assert_faq_built(server.live_posts(thread))
    assert sent_text(interaction) == "♪ The Wisp FAQ is rebuilt."


async def test_faq_command_without_a_studio_says_how_to_set_it_up(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(server, bot)

    await invoke(studio.rebuild_faq, interaction)

    assert "/wispadmin setup" in sent_text(interaction)
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
    server.house.send.assert_awaited_once()


async def test_studio_thread_rejects_an_unknown_setting(
    bot: app.WispBot,
) -> None:
    with pytest.raises(ValueError, match="frozen"):
        await studio_thread(bot, GUILD_ID, "frozen")


# ---
# Roles
# ---


async def test_roles_add_list_remove(bot: app.WispBot, server: FakeServer) -> None:
    interaction = make_interaction(server, bot)
    await invoke(studio.roles_list, interaction)
    assert "No qualifying roles" in sent_text(interaction)

    for role_id in (7, 5, 7):
        interaction = make_interaction(server, bot)
        await invoke(studio.roles_add, interaction, make_role(role_id))
        assert f"<@&{role_id}>" in sent_text(interaction)
    assert await bot.settings.roles(GUILD_ID) == {5, 7}

    interaction = make_interaction(server, bot)
    await invoke(studio.roles_list, interaction)
    listed = sent_text(interaction)
    assert listed.index("<@&5>") < listed.index("<@&7>")

    interaction = make_interaction(server, bot)
    await invoke(studio.roles_remove, interaction, make_role(5))
    assert "<@&5>" in sent_text(interaction)
    assert await bot.settings.roles(GUILD_ID) == {7}


# ---
# Freeze
# ---


async def test_freeze_sets_flag(bot: app.WispBot, server: FakeServer) -> None:
    interaction = make_interaction(server, bot)
    await invoke(studio.freeze, interaction)
    assert (await bot.settings.get(GUILD_ID)).frozen is True
    assert "frozen" in sent_text(interaction).lower()

    interaction = make_interaction(server, bot)
    await invoke(studio.unfreeze, interaction)
    assert (await bot.settings.get(GUILD_ID)).frozen is False
    assert "unfrozen" in sent_text(interaction).lower()


# ---
# Staff only
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


async def test_staff_only(bot: app.WispBot, server: FakeServer) -> None:
    group = groups.wispadmin
    assert group.default_permissions == discord.Permissions(manage_guild=True)
    assert_guild_only(group)

    leaves = [
        command
        for command in group.walk_commands()
        if isinstance(command, app_commands.Command)
    ]
    assert {command.qualified_name for command in leaves} >= {
        "wispadmin setup",
        "wispadmin roles add",
        "wispadmin roles remove",
        "wispadmin roles list",
        "wispadmin freeze",
        "wispadmin unfreeze",
        "wispadmin faq",
    }
    for command in leaves:
        assert command.checks, command.qualified_name
        for check in command.checks:
            assert check(make_interaction(server, bot, staff=True))
            with pytest.raises(app_commands.MissingPermissions):
                check(make_interaction(server, bot, staff=False))


def test_members_group_is_open_to_everyone_in_guilds() -> None:
    assert groups.wisp.default_permissions is None
    assert_guild_only(groups.wisp)


def test_setup_command_options() -> None:
    command = groups.wispadmin.get_command("setup")
    assert isinstance(command, app_commands.Command)
    params = {parameter.name: parameter for parameter in command.parameters}
    assert list(params) == ["house", "studio", "tracks"]
    assert discord.ChannelType.forum in params["studio"].channel_types
    assert discord.ChannelType.text not in params["studio"].channel_types
    assert discord.ChannelType.forum in params["tracks"].channel_types
    assert discord.ChannelType.text in params["tracks"].channel_types


# ---
# Extension
# ---


async def test_studio_commands_hang_off_the_shared_group(bot: app.WispBot) -> None:
    await studio.setup(bot)

    assert groups.wispadmin.get_command("setup") is studio.setup_studio
    assert groups.wispadmin.get_command("freeze") is studio.freeze
    assert groups.wispadmin.get_command("faq") is studio.rebuild_faq
    roles = groups.wispadmin.get_command("roles")
    assert isinstance(roles, app_commands.Group)
    assert roles.get_command("add") is studio.roles_add


def test_studio_is_a_loaded_extension() -> None:
    assert "cogs.studio" in app.EXTENSIONS


# ---
# Rules post text
# ---


def test_rules_text_is_headed_as_the_quick_rules() -> None:
    assert rules_text(rules.MEAL_POINTS).startswith("♪ Quick rules (current numbers)\n")


def test_rules_text_fits_one_message() -> None:
    assert len(rules_text(rules.MEAL_POINTS)) < MESSAGE_LIMIT
    biggest = {kind: rules.MEAL_POINTS_MAX for kind in TrackKind}
    assert len(rules_text(biggest)) < MESSAGE_LIMIT


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
    ):
        monkeypatch.setattr(rules, name, 9999)
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
    assert len(text) < MESSAGE_LIMIT


def test_rules_text_shows_the_food_values_it_is_given() -> None:
    text = rules_text({TrackKind.VIIBR: 12, TrackKind.SUNO: 1})

    assert "・viibrmusic.com track: 12 meal points" in text
    assert "・Suno track: 1 meal point" in text


def test_rules_text_has_vault_snack_pack_life_and_talking_sections() -> None:
    text = rules_text(rules.MEAL_POINTS)

    for heading in (
        "The ViiBR Vault",
        "Your Snack Pack",
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
    assert "Mention him or reply to him in Wisp's House" in text
    section = text.split("\nYour Snack Pack\n")[1].split("\n\n")[0]
    assert "/wisp snackpack" in section
    assert "keepsake" in section
    assert "Last Ember in their Snack Pack" in text
    assert "your lunchbox" not in text.lower()


def test_rules_text_points_to_wisps_lunchbox() -> None:
    text = rules_text(rules.MEAL_POINTS)

    section = text.split("\nWisp's lunchbox\n")[1].split("\n\n")[0]
    assert (
        section == "・/wisp lunchbox shows his favorite songs, snack, emoji and gifts"
    )


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
    assert "・♪ ────────・──────── ♪・" in text
    assert not re.search(EMOJI, text)


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
    monkeypatch.setattr(rules, "OLD_FOGEY_AT_DAY", 83)
    monkeypatch.setattr(rules, "FAREWELL_AT_DAY", 89)
    monkeypatch.setattr(rules, "LAST_EMBER_GIFTS", 97)
    monkeypatch.setattr(rules, "EGG_FOOD_NEEDED", 101)
    monkeypatch.setattr(rules, "COAL_EGG_FOOD", 103)

    text = rules_text(rules.MEAL_POINTS)

    for number in (41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103):
        assert str(number) in text, number
    assert "permanent" in text
