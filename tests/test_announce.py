"""Tests for Wisp's House announcements, the next life and pinned messages.

Discord objects are fakes; the repositories are the real ones.
"""

import logging
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest

import app
from ai.chain import AllProvidersFailed
from ai.prompt import Prompt
from cogs import announce, pictures
from cogs.announce import (
    BEGIN_AGAIN,
    BEGIN_ID,
    begin_again,
    begin_view,
    ending_image,
    lay_first_egg,
    post_events,
    show_in_thread,
)
from cogs.pictures import life_image
from db.activity import ActivityRepo, InteractionKind
from db.badges import BadgeRepo
from db.database import Database
from db.keepsakes import KeepsakeRepo
from db.lives import LifeRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.life import Event, EventKind, Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.links import Track, TrackKind
from wisp.rules import Stage

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
STATUS_ID = 60
BOARD_ID = 61
STATUS_MESSAGE_ID = 777
BOARD_MESSAGE_ID = 778
REPOSTED_ID = 888
NAMED = 1
MEMBER = 2
NAMELESS = 3
FOURTH = 4

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
    """A guild with Wisp's House and the Status and Vault threads."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.status = FakeThread(STATUS_ID)
        self.board = FakeThread(BOARD_ID)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get
        self.members: dict[int, MagicMock] = {}
        self.guild.get_member.side_effect = self.members.get

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
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    wisp_bot.keepsakes = KeepsakeRepo(db)
    wisp_bot.badges = BadgeRepo(db)
    wisp_bot.notes = NoteRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture(autouse=True)
def ai(bot: app.WispBot, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Wisp's AI voice, answering with no words so goodbyes stay canned."""
    complete = AsyncMock(return_value="")
    monkeypatch.setattr(bot.ai, "complete", complete)
    return complete


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        status_thread_id=STATUS_ID,
        status_message_id=STATUS_MESSAGE_ID,
        vault_thread_id=BOARD_ID,
        vault_message_id=BOARD_MESSAGE_ID,
    )


async def show_status(
    bot: app.WispBot,
    content: str = "card",
    view: discord.ui.View | None = None,
    image: Path | None = None,
) -> None:
    await show_in_thread(
        bot,
        GUILD_ID,
        "status_thread_id",
        "status_message_id",
        content,
        "status card",
        view,
        image,
    )


async def show_board(bot: app.WispBot, content: str = "board") -> None:
    await show_in_thread(
        bot,
        GUILD_ID,
        "vault_thread_id",
        "vault_message_id",
        content,
        "ViiBR Vault card",
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
    server.house.send.assert_not_awaited()


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
    assert settings.vault_message_id == REPOSTED_ID
    assert settings.status_message_id == STATUS_MESSAGE_ID
    server.house.send.assert_not_awaited()


async def test_no_stored_message_posts_one(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, status_message_id=None)

    await show_status(bot)

    server.status.edit.assert_not_awaited()
    server.status.thread.send.assert_awaited_once()
    assert (await bot.settings.get(GUILD_ID)).status_message_id == REPOSTED_ID


async def test_a_view_rides_along_on_the_edit(
    bot: app.WispBot, server: FakeServer
) -> None:
    view = discord.ui.View(timeout=None)

    await show_status(bot, view=view)

    assert server.status.edit.await_args.kwargs["view"] is view


async def test_a_view_rides_along_on_the_repost(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.status.edit.side_effect = not_found()
    view = discord.ui.View(timeout=None)

    await show_status(bot, view=view)

    assert server.status.thread.send.await_args.kwargs["view"] is view


async def test_without_a_view_the_message_keeps_its_buttons(
    bot: app.WispBot, server: FakeServer
) -> None:
    await show_status(bot)
    server.status.edit.side_effect = not_found()
    await show_status(bot)

    assert "view" not in server.status.edit.await_args.kwargs
    assert "view" not in server.status.thread.send.await_args.kwargs


# ---
# Pictures
# ---


def picture(tmp_path: Path, name: str) -> Path:
    path = tmp_path / f"{name}.png"
    path.write_bytes(b"png")
    return path


def attached(kwargs: dict[str, Any]) -> list[str]:
    files: list[discord.File] = kwargs.get("attachments", [])
    for file in files:
        file.close()
    return [file.filename for file in files]


async def test_a_picture_is_attached_on_the_first_edit(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    await show_status(bot, image=picture(tmp_path, "egg"))

    assert attached(server.status.edit.await_args.kwargs) == ["egg.png"]


async def test_an_unchanged_picture_is_not_uploaded_again(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    egg = picture(tmp_path, "egg")
    await show_status(bot, image=egg)
    await show_status(bot, "next tick", image=egg)

    first, second = server.status.edit.await_args_list
    assert attached(first.kwargs) == ["egg.png"]
    assert second.kwargs["content"] == "next tick"
    assert "attachments" not in second.kwargs


async def test_a_new_picture_replaces_the_old_one(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    await show_status(bot, image=picture(tmp_path, "egg"))
    await show_status(bot, image=picture(tmp_path, "baby"))

    assert attached(server.status.edit.await_args.kwargs) == ["baby.png"]


async def test_a_new_card_message_gets_the_picture_again(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    egg = picture(tmp_path, "egg")
    await show_status(bot, image=egg)
    await bot.settings.update(GUILD_ID, status_message_id=STATUS_MESSAGE_ID + 1)

    await show_status(bot, image=egg)

    server.status.thread.get_partial_message.assert_called_with(STATUS_MESSAGE_ID + 1)
    assert attached(server.status.edit.await_args.kwargs) == ["egg.png"]


async def test_a_reposted_card_carries_its_picture(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    server.status.edit.side_effect = not_found()

    await show_status(bot, image=picture(tmp_path, "egg"))

    art = server.status.thread.send.await_args.kwargs["file"]
    art.close()
    assert art.filename == "egg.png"


def refuse_pictures(field: str) -> Any:
    """A Discord call that refuses any picture and accepts plain text."""

    def call(*_args: Any, **kwargs: Any) -> None:
        if field in kwargs:
            raise forbidden()

    return call


async def test_a_refused_picture_still_updates_the_card_text(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    server.status.edit.side_effect = refuse_pictures("attachments")

    await show_status(bot, "the text", image=picture(tmp_path, "egg"))

    with_picture, without = server.status.edit.await_args_list
    assert attached(with_picture.kwargs) == ["egg.png"]
    assert without.kwargs["content"] == "the text"
    assert "attachments" not in without.kwargs
    (report,) = server.status.thread.send.await_args.args
    assert report.startswith("Error in attaching the status card picture: Forbidden")
    server.house.send.assert_not_awaited()


async def test_a_refused_picture_is_reported_once_per_streak_and_tried_again(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    egg = picture(tmp_path, "egg")
    server.status.edit.side_effect = refuse_pictures("attachments")
    await show_status(bot, image=egg)
    await show_status(bot, image=egg)
    assert server.status.edit.await_count == 4
    assert server.status.thread.send.await_count == 1

    server.status.edit.side_effect = None
    await show_status(bot, image=egg)
    assert attached(server.status.edit.await_args.kwargs) == ["egg.png"]
    await show_status(bot, image=egg)
    assert "attachments" not in server.status.edit.await_args.kwargs

    server.status.edit.side_effect = refuse_pictures("attachments")
    await show_status(bot, image=picture(tmp_path, "baby"))
    assert server.status.thread.send.await_count == 2


async def test_a_picture_failure_does_not_hide_a_card_failure(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    server.status.edit.side_effect = refuse_pictures("attachments")
    await show_status(bot, image=picture(tmp_path, "egg"))

    server.status.edit.side_effect = forbidden()
    await show_status(bot)

    reports = [call.args[0] for call in server.status.thread.send.await_args_list]
    assert [report.split(":")[0] for report in reports] == [
        "Error in attaching the status card picture",
        "Error in updating the status card",
    ]


async def test_a_reposted_card_whose_picture_is_refused_is_posted_as_text(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    server.status.edit.side_effect = not_found()
    refuse = refuse_pictures("file")

    def send(*args: Any, **kwargs: Any) -> MagicMock:
        refuse(*args, **kwargs)
        return server.status.reposted

    server.status.thread.send.side_effect = send

    await show_status(bot, "the text", image=picture(tmp_path, "egg"))

    sends = server.status.thread.send.await_args_list
    sends[0].kwargs["file"].close()
    assert sends[1].args == ("the text",)
    assert "file" not in sends[1].kwargs
    assert (
        sends[2]
        .args[0]
        .startswith("Error in attaching the status card picture: Forbidden")
    )
    assert (await bot.settings.get(GUILD_ID)).status_message_id == REPOSTED_ID
    server.status.reposted.pin.assert_awaited_once()


async def test_without_a_picture_the_attachment_is_kept(
    bot: app.WispBot, server: FakeServer, tmp_path: Path
) -> None:
    await show_status(bot, image=picture(tmp_path, "egg"))
    await show_status(bot)
    await show_board(bot)

    assert "attachments" not in server.status.edit.await_args.kwargs
    assert "attachments" not in server.board.edit.await_args.kwargs


# ---
# Failures
# ---


async def test_pin_failure_is_posted_in_the_thread_and_the_message_kept(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.board.edit.side_effect = not_found()
    server.board.reposted.pin.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await show_board(bot)

    assert (await bot.settings.get(GUILD_ID)).vault_message_id == REPOSTED_ID
    assert server.board.thread.send.await_count == 2
    (report,) = server.board.thread.send.await_args.args
    assert report.startswith("Error in pinning the ViiBR Vault card: Forbidden")
    server.house.send.assert_not_awaited()


async def test_edit_failure_is_posted_in_the_thread_with_the_label(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.status.edit.side_effect = forbidden()

    await show_status(bot)

    server.status.thread.send.assert_awaited_once()
    (report,) = server.status.thread.send.await_args.args
    assert report.startswith("Error in updating the status card: Forbidden")
    server.house.send.assert_not_awaited()


async def test_failure_is_reported_once_per_streak(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.status.edit.side_effect = forbidden()
    await show_status(bot)
    await show_status(bot)
    assert server.status.thread.send.await_count == 1

    server.status.edit.side_effect = None
    await show_status(bot)
    server.status.edit.side_effect = forbidden()
    await show_status(bot)

    assert server.status.thread.send.await_count == 2


async def test_streaks_are_tracked_per_display(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.status.edit.side_effect = forbidden()
    server.board.edit.side_effect = forbidden()

    await show_status(bot)
    await show_board(bot)
    await show_status(bot)
    await show_board(bot)

    assert server.status.thread.send.await_count == 1
    assert server.board.thread.send.await_count == 1


async def test_unreachable_studio_is_posted_in_the_house_not_raised(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, studio_forum_id=None, status_thread_id=None)

    await show_status(bot)

    server.house.send.assert_awaited_once()
    (report,) = server.house.send.await_args.args
    assert report.startswith("Error in updating the status card: StudioError")


# ---
# Growing old, the farewell and the next life
# ---


@pytest.fixture
def assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(announce, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(pictures, "ASSETS_DIR", tmp_path)
    return tmp_path


def add_image(assets: Path, folder: str, name: str, suffix: str = ".png") -> None:
    target = assets / folder / f"{name}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"art")


async def ended_life(bot: app.WispBot, phase: Phase, version: int = 3) -> Life:
    now = discord.utils.utcnow()
    life = new_egg(version, now - timedelta(days=rules.FAREWELL_AT_DAY + 1))
    life.phase = phase
    life.stage = Stage.OLD_FOGEY if phase is Phase.PASSED else Stage.ADULT
    life.peak_stage = Stage.ADULT
    life.hatched_at = now - timedelta(days=rules.FAREWELL_AT_DAY)
    life.ended_at = now
    return await bot.lives.insert(GUILD_ID, life)


async def shared(bot: app.WispBot, life: Life, points: dict[int, int]) -> None:
    """Record one feed per member worth the given meal points."""
    assert life.id is not None
    for user_id, meal_points in points.items():
        track = Track(TrackKind.SUNO, f"track-{user_id}", f"https://suno.com/{user_id}")
        await bot.activity_log.record_feed(
            GUILD_ID,
            life.id,
            user_id,
            track,
            meal_points,
            user_id,
            discord.utils.utcnow(),
        )


async def known_sharers(bot: app.WispBot, server: FakeServer, life: Life) -> None:
    """Four sharers: one named for Wisp, one only a server member, two unknown."""
    await shared(bot, life, {NAMED: 10, MEMBER: 6, NAMELESS: 3, FOURTH: 1})
    await bot.players.set_name(GUILD_ID, NAMED, "Aria")
    member = MagicMock(spec=discord.Member)
    member.display_name = "Bea"
    server.members[MEMBER] = member


def said(text: str, moment: Moment, **fields: str) -> bool:
    return text in {line.format(**fields) for line in LINES[(moment, Mood.HAPPY)]}


def gift_said(text: str, name: str, version: int) -> bool:
    heading, goodbye = text.split("\n")
    return heading == f"♪ {name} gets Wisp v{version}'s Last Ember" and said(
        goodbye, Moment.LAST_EMBER, name=name, version=str(version)
    )


def sends_without_pinging(kwargs: dict[str, Any]) -> bool:
    return bool(
        kwargs["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
    )


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


async def embers(bot: app.WispBot, user_id: int) -> list[str]:
    return [keepsake.title for keepsake in await bot.keepsakes.of(GUILD_ID, user_id)]


def asks_to_begin_again(post: Any) -> bool:
    """Whether a House post is the question, with its one Begin again button."""
    view = post.kwargs.get("view")
    if post.args[0] != BEGIN_AGAIN or view is None or view.timeout is not None:
        return False
    (button,) = view.children
    return (
        isinstance(button, discord.ui.Button)
        and (button.label, button.custom_id, button.disabled)
        == ("Begin again", BEGIN_ID, False)
        and "file" not in post.kwargs
        and sends_without_pinging(post.kwargs)
    )


async def test_farewell_posts_line_then_gifts_then_asks_to_begin_again(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "events", "farewell")
    add_image(assets, "stages", "coal_egg")
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    posts = server.house.send.await_args_list
    assert len(posts) == 5
    farewell, named, member, nameless, question = posts
    assert said(farewell.args[0], Moment.FAREWELL, version="3")
    assert farewell.kwargs["file"].filename == "farewell.png"
    assert gift_said(named.args[0], "Aria", 3)
    assert gift_said(member.args[0], "Bea", 3)
    assert gift_said(nameless.args[0], f"<@{NAMELESS}>", 3)
    assert asks_to_begin_again(question)
    assert all(sends_without_pinging(post.kwargs) for post in posts)
    assert [old.version for old in await bot.lives.history(GUILD_ID)] == [3]
    for user_id in (NAMED, MEMBER, NAMELESS):
        assert await embers(bot, user_id) == ["Wisp v3's Last Ember"]
    assert await embers(bot, FOURTH) == []


@pytest.mark.parametrize(
    ("phase", "event"),
    [
        (Phase.DEAD, EventKind.DIED),
        (Phase.COLD, EventKind.EGG_COLD),
        (Phase.PASSED, EventKind.FAREWELL),
    ],
)
async def test_every_ending_asks_to_begin_again_and_lays_no_egg(
    bot: app.WispBot, server: FakeServer, assets: Path, phase: Phase, event: EventKind
) -> None:
    life = await ended_life(bot, phase)

    await post_events(bot, GUILD_ID, [Event(event)])

    ending, question = server.house.send.await_args_list
    assert said(ending.args[0], Moment(event.value), version="3")
    assert "view" not in ending.kwargs
    assert asks_to_begin_again(question)
    assert (await current_life(bot)).id == life.id
    assert await bot.lives.next_version(GUILD_ID) == 4


async def test_a_stale_ending_asks_nothing(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await bot.lives.insert(GUILD_ID, new_egg(1, discord.utils.utcnow()))

    await post_events(bot, GUILD_ID, [Event(EventKind.DIED)])

    server.house.send.assert_not_awaited()


async def test_the_begin_again_button_can_be_shown_used() -> None:
    view = begin_view(disabled=True)

    (button,) = view.children
    assert isinstance(button, discord.ui.Button)
    assert (button.label, button.custom_id, button.disabled) == (
        "Begin again",
        BEGIN_ID,
        True,
    )
    assert BEGIN_ID == "wisp:begin"


@pytest.mark.parametrize(
    ("phase", "picture"),
    [
        (Phase.DEAD, "died.png"),
        (Phase.COLD, "egg_cold.png"),
        (Phase.PASSED, "farewell.png"),
        (Phase.ALIVE, None),
        (Phase.EGG, None),
    ],
)
def test_an_ended_life_shows_the_picture_of_its_ending(
    assets: Path, phase: Phase, picture: str | None
) -> None:
    for name in ("died", "egg_cold", "farewell"):
        add_image(assets, "events", name)
    life = new_egg(1, discord.utils.utcnow())
    life.phase = phase

    image = ending_image(life)

    assert (None if image is None else image.name) == picture


async def test_begin_again_after_farewell_lays_one_coal_egg_halfway_hatched(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "coal_egg")
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)
    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])
    server.house.send.reset_mock()

    egg = await begin_again(bot, GUILD_ID, discord.utils.utcnow())
    again = await begin_again(bot, GUILD_ID, discord.utils.utcnow())

    assert egg is not None and again is None
    assert (egg.version, egg.phase, egg.from_coal) == (4, Phase.EGG, True)
    assert egg.egg_food == rules.COAL_EGG_FOOD == rules.EGG_FOOD_NEEDED // 2
    (coal,) = server.house.send.await_args_list
    assert said(coal.args[0], Moment.COAL_EGG, version="4")
    assert coal.kwargs["file"].filename == "coal_egg.png"
    assert sends_without_pinging(coal.kwargs)
    assert [old.version for old in await bot.lives.history(GUILD_ID)] == [4, 3]
    for user_id in (NAMED, MEMBER, NAMELESS):
        assert await embers(bot, user_id) == ["Wisp v3's Last Ember"]


async def test_begin_again_gives_embers_an_unannounced_farewell_never_gave(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)

    await begin_again(bot, GUILD_ID, discord.utils.utcnow())

    named, member, nameless, coal = server.house.send.await_args_list
    assert gift_said(named.args[0], "Aria", 3)
    assert gift_said(member.args[0], "Bea", 3)
    assert gift_said(nameless.args[0], f"<@{NAMELESS}>", 3)
    assert said(coal.args[0], Moment.COAL_EGG, version="4")
    assert "file" not in coal.kwargs
    for user_id in (NAMED, MEMBER, NAMELESS):
        assert await embers(bot, user_id) == ["Wisp v3's Last Ember"]


async def test_banned_top_sharer_gets_no_ember(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)
    now = discord.utils.utcnow()
    await bot.players.set_offense(GUILD_ID, MEMBER, 1, now + timedelta(days=1), False)

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    _farewell, named, nameless, question = [
        call.args[0] for call in server.house.send.await_args_list
    ]
    assert gift_said(named, "Aria", 3)
    assert gift_said(nameless, f"<@{NAMELESS}>", 3)
    assert question == BEGIN_AGAIN
    assert await embers(bot, MEMBER) == []
    assert await embers(bot, FOURTH) == []


async def test_expired_ban_does_not_stop_the_ember(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)
    now = discord.utils.utcnow()
    await bot.players.set_offense(GUILD_ID, MEMBER, 1, now - timedelta(days=1), False)

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    assert await embers(bot, MEMBER) == ["Wisp v3's Last Ember"]


async def test_neglect_death_gives_no_gifts_and_begins_again_with_a_fresh_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "coal_egg")
    life = await ended_life(bot, Phase.DEAD)
    await known_sharers(bot, server, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.DIED)])
    egg = await begin_again(bot, GUILD_ID, discord.utils.utcnow())

    died, question, laid = server.house.send.await_args_list
    assert said(died.args[0], Moment.DIED, version="3")
    assert asks_to_begin_again(question)
    assert said(laid.args[0], Moment.NEW_EGG, version="4")
    assert "file" not in laid.kwargs
    assert egg is not None
    assert (egg.version, egg.from_coal, egg.egg_food) == (4, False, 0)
    assert (await current_life(bot)).id == egg.id
    for user_id in (NAMED, MEMBER, NAMELESS, FOURTH):
        assert await embers(bot, user_id) == []


async def test_first_life_is_a_fresh_egg_without_asking(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await lay_first_egg(bot, GUILD_ID, discord.utils.utcnow())

    egg = await current_life(bot)
    assert (egg.version, egg.phase, egg.from_coal) == (1, Phase.EGG, False)
    (laid,) = server.house.send.await_args_list
    assert said(laid.args[0], Moment.NEW_EGG, version="1")
    assert "file" not in laid.kwargs
    (button,) = laid.kwargs["view"].children
    assert isinstance(button, discord.ui.Button)
    assert button.custom_id == "wisp:poke"


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD, Phase.PASSED, Phase.EGG])
async def test_the_first_egg_is_only_for_a_server_that_never_had_a_wisp(
    bot: app.WispBot, server: FakeServer, assets: Path, phase: Phase
) -> None:
    life = await ended_life(bot, phase)

    await lay_first_egg(bot, GUILD_ID, discord.utils.utcnow())

    assert (await current_life(bot)).id == life.id
    server.house.send.assert_not_awaited()


async def test_a_new_egg_is_announced_with_the_egg_picture(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "egg")
    add_image(assets, "stages", "coal_egg")
    await ended_life(bot, Phase.DEAD)

    await begin_again(bot, GUILD_ID, discord.utils.utcnow())

    (laid,) = server.house.send.await_args_list
    assert said(laid.args[0], Moment.NEW_EGG, version="4")
    assert laid.kwargs["file"].filename == "egg.png"
    assert sends_without_pinging(laid.kwargs)


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.COLD, Phase.PASSED])
async def test_the_new_egg_post_has_the_poke_button(
    bot: app.WispBot, server: FakeServer, assets: Path, phase: Phase
) -> None:
    await ended_life(bot, phase)

    await begin_again(bot, GUILD_ID, discord.utils.utcnow())

    (laid,) = server.house.send.await_args_list
    view = laid.kwargs["view"]
    (button,) = view.children
    assert isinstance(button, discord.ui.Button)
    assert (button.label, button.custom_id) == ("Poke Wisp", "wisp:poke")
    assert view.timeout is None


async def test_a_coal_egg_without_its_own_picture_shows_the_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "egg")
    await ended_life(bot, Phase.PASSED)

    await begin_again(bot, GUILD_ID, discord.utils.utcnow())

    (coal,) = server.house.send.await_args_list
    assert said(coal.args[0], Moment.COAL_EGG, version="4")
    assert coal.kwargs["file"].filename == "egg.png"


@pytest.mark.parametrize(
    ("phase", "stage", "from_coal", "files", "expected"),
    [
        (Phase.EGG, Stage.EGG, False, ["egg", "coal_egg"], "egg.png"),
        (Phase.HATCHING, Stage.EGG, False, ["egg"], "egg.png"),
        (Phase.EGG, Stage.EGG, True, ["egg", "coal_egg"], "coal_egg.png"),
        (Phase.HATCHING, Stage.EGG, True, ["egg"], "egg.png"),
        (Phase.ALIVE, Stage.TEEN, False, ["egg", "teen"], "teen.png"),
        (Phase.ALIVE, Stage.OLD_FOGEY, True, ["old_fogey"], "old_fogey.png"),
        (Phase.ALIVE, Stage.ADULT, False, ["egg", "teen"], None),
        (Phase.EGG, Stage.EGG, True, ["coal_egg"], "coal_egg.png"),
        (Phase.EGG, Stage.EGG, False, [], None),
        (Phase.DEAD, Stage.ADULT, False, ["egg", "adult"], None),
    ],
)
def test_life_image_is_his_current_picture(
    assets: Path,
    phase: Phase,
    stage: Stage,
    from_coal: bool,
    files: list[str],
    expected: str | None,
) -> None:
    for name in files:
        add_image(assets, "stages", name)
    life = new_egg(1, discord.utils.utcnow())
    life.phase = phase
    life.stage = stage
    life.from_coal = from_coal

    image = life_image(life)

    assert (None if image is None else image.name) == expected


async def test_begin_again_leaves_a_living_wisp_alone(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await bot.lives.insert(GUILD_ID, new_egg(1, discord.utils.utcnow()))

    assert await begin_again(bot, GUILD_ID, discord.utils.utcnow()) is None

    assert [old.version for old in await bot.lives.history(GUILD_ID)] == [1]
    server.house.send.assert_not_awaited()


async def test_farewell_with_missing_house_is_logged_once_and_gifts_still_given(
    bot: app.WispBot,
    server: FakeServer,
    assets: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=None)
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    assert (await current_life(bot)).version == 3
    assert await embers(bot, NAMED) == ["Wisp v3's Last Ember"]
    server.house.send.assert_not_awaited()
    assert caplog.text.count("Error in posting to Wisp's House") == 1


async def test_grew_old_is_announced_with_its_image(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "old_fogey")
    life = new_egg(1, discord.utils.utcnow() - timedelta(days=50))
    life.phase = Phase.ALIVE
    life.full = 80.0
    life.stage = Stage.OLD_FOGEY
    life.peak_stage = Stage.ADULT
    await bot.lives.insert(GUILD_ID, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.GREW_OLD, Stage.OLD_FOGEY)])

    (post,) = server.house.send.await_args_list
    assert said(post.args[0], Moment.GREW_OLD)
    assert post.kwargs["file"].filename == "old_fogey.png"
    assert sends_without_pinging(post.kwargs)


async def test_last_ember_goodbye_uses_ai_then_falls_back(
    bot: app.WispBot, server: FakeServer, assets: Path, ai: AsyncMock
) -> None:
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)
    await bot.notes.add(GUILD_ID, NAMED, "plays bass", discord.utils.utcnow())
    outage = AllProvidersFailed([("gemini", "timed out")])
    answers: list[str | AllProvidersFailed] = [
        "thanks for every track, Aria. the ember's yours <note>x</note>",
        outage,
        outage,
    ]
    lock_held: list[bool] = []

    async def answer(_prompt: Prompt) -> str:
        lock_held.append(bot.guild_lock(GUILD_ID).locked())
        result = answers.pop(0)
        if isinstance(result, AllProvidersFailed):
            raise result
        return result

    ai.side_effect = answer

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    _farewell, named, report, member, nameless, question = [
        call.args[0] for call in server.house.send.await_args_list
    ]
    assert named == (
        "♪ Aria gets Wisp v3's Last Ember\n"
        "thanks for every track, Aria. the ember's yours"
    )
    assert gift_said(member, "Bea", 3)
    assert gift_said(nameless, f"<@{NAMELESS}>", 3)
    assert question == BEGIN_AGAIN
    to_aria, to_bea, _ = [call.args[0] for call in ai.await_args_list]
    assert "Wisp v3" in to_aria.user
    assert "Aria" in to_aria.user and "plays bass" in to_aria.user
    assert "Bea" in to_bea.user and "plays bass" not in to_bea.user
    assert lock_held == [False, False, False]
    assert report == "Error in Wisp's AI voice: AllProvidersFailed: gemini: timed out"


# ---
# Milestone keepsakes
# ---


async def growing_life(bot: app.WispBot, *, hatched_by: int | None = None) -> Life:
    """A living Wisp v1 whose egg was filled by `hatched_by`."""
    life = new_egg(1, discord.utils.utcnow() - timedelta(days=3))
    life.phase = Phase.ALIVE
    life.full = 80.0
    life.stage = life.peak_stage = Stage.BABY
    life.hatched_by = hatched_by
    return await bot.lives.insert(GUILD_ID, life)


async def interacted(bot: app.WispBot, life: Life, user_id: int, ago: int) -> None:
    """Record an interaction `ago` minutes back."""
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        user_id,
        InteractionKind.PLAY,
        0,
        0,
        discord.utils.utcnow() - timedelta(minutes=ago),
    )


def keepsake_said(text: str, name: str, title: str) -> bool:
    heading, line = text.split("\n")
    return heading == f"♪ {name} gets {title}" and said(
        line, Moment.KEEPSAKE_WON, name=name
    )


async def test_hatching_gives_the_eggshell_to_whoever_filled_the_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "keepsakes", "eggshell")
    life = await growing_life(bot, hatched_by=NAMED)
    life.phase = Phase.HATCHING
    await bot.lives.save(GUILD_ID, life)
    await bot.players.set_name(GUILD_ID, NAMED, "Aria")
    await interacted(bot, life, MEMBER, 1)

    await post_events(bot, GUILD_ID, [Event(EventKind.HATCH_STARTED)])

    cracking, won = server.house.send.await_args_list
    assert said(cracking.args[0], Moment.HATCH_STARTED, version="1")
    assert keepsake_said(won.args[0], "Aria", "Wisp v1's Eggshell")
    assert won.kwargs["file"].filename == "eggshell.png"
    assert sends_without_pinging(won.kwargs)
    assert await embers(bot, NAMED) == ["Wisp v1's Eggshell"]
    assert await embers(bot, MEMBER) == []


async def test_hatch_started_posts_its_animated_picture(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "events", "hatch_started", ".gif")
    life = await growing_life(bot, hatched_by=NAMED)
    life.phase = Phase.HATCHING
    await bot.lives.save(GUILD_ID, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.HATCH_STARTED)])

    cracking = server.house.send.await_args_list[0]
    assert said(cracking.args[0], Moment.HATCH_STARTED, version="1")
    assert cracking.kwargs["file"].filename == "hatch_started.gif"


async def test_an_event_gif_beats_its_png(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "events", "hatch_started")
    add_image(assets, "events", "hatch_started", ".gif")
    life = await growing_life(bot, hatched_by=NAMED)
    life.phase = Phase.HATCHING
    await bot.lives.save(GUILD_ID, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.HATCH_STARTED)])

    assert server.house.send.await_args_list[0].kwargs["file"].filename == (
        "hatch_started.gif"
    )


LONELY_ART = {
    "cry_baby": ".gif",
    "grumpy_baby": ".png",
    "grumpy": ".gif",
    "cry_teen": ".gif",
}


async def lonely_post(
    bot: app.WispBot, server: FakeServer, stage: Stage
) -> tuple[str, dict[str, Any]]:
    """Post a LONELY event for a Wisp of `stage` and return the House post."""
    life = await growing_life(bot)
    life.stage = life.peak_stage = stage
    await bot.lives.save(GUILD_ID, life)
    await post_events(bot, GUILD_ID, [Event(EventKind.LONELY, stage)])
    (post,) = server.house.send.await_args_list
    return post.args[0], post.kwargs


@pytest.mark.parametrize(
    ("stage", "pictures"),
    [
        (Stage.BABY, {"cry_baby.gif", "grumpy_baby.png"}),
        (Stage.CHILD, {"grumpy.gif"}),
        (Stage.TEEN, {"cry_teen.gif"}),
        (Stage.ADULT, {"cry_teen.gif"}),
        (Stage.ROCKSTAR, {"cry_teen.gif"}),
        (Stage.OLD_FOGEY, {"cry_teen.gif"}),
    ],
)
async def test_lonely_post_has_a_picture_for_his_stage(
    bot: app.WispBot,
    server: FakeServer,
    assets: Path,
    stage: Stage,
    pictures: set[str],
) -> None:
    for name, suffix in LONELY_ART.items():
        add_image(assets, "moments", name, suffix)

    text, kwargs = await lonely_post(bot, server, stage)

    assert said(text, Moment.LONELY)
    assert kwargs["file"].filename in pictures
    assert sends_without_pinging(kwargs)


def test_the_lonely_pictures_are_in_the_repo() -> None:
    moments = Path(announce.__file__).resolve().parent.parent / "ASSETS" / "moments"
    for names in rules.LONELY_PICTURES.values():
        for name in names:
            assert (moments / name).is_file(), name


async def test_a_lonely_picture_is_picked_from_the_ones_on_disk(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "moments", "grumpy_baby")

    _, kwargs = await lonely_post(bot, server, Stage.BABY)

    assert kwargs["file"].filename == "grumpy_baby.png"


async def test_both_baby_pictures_get_their_turn(
    bot: app.WispBot,
    server: FakeServer,
    assets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_image(assets, "moments", "cry_baby", ".gif")
    add_image(assets, "moments", "grumpy_baby")
    offered: list[list[str]] = []

    def choose(pictures: list[Path]) -> Path:
        offered.append(sorted(path.name for path in pictures))
        return pictures[-1]

    monkeypatch.setattr(announce, "choice", choose)

    _, kwargs = await lonely_post(bot, server, Stage.BABY)

    assert offered == [["cry_baby.gif", "grumpy_baby.png"]]
    assert kwargs["file"].filename == "grumpy_baby.png"


async def test_a_lonely_post_without_its_picture_is_text_only(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "moments", "cry_teen", ".gif")

    text, kwargs = await lonely_post(bot, server, Stage.CHILD)

    assert said(text, Moment.LONELY)
    assert "file" not in kwargs


SICK_ART = ("sick_baby", "sick_child", "sick_teen")


async def event_post(
    bot: app.WispBot, server: FakeServer, event: Event
) -> tuple[str, dict[str, Any]]:
    """Post one event for a living Wisp of the event's stage; return the post."""
    life = await growing_life(bot)
    if event.stage is not None:
        life.stage = life.peak_stage = event.stage
    await bot.lives.save(GUILD_ID, life)
    await post_events(bot, GUILD_ID, [event])
    (post,) = server.house.send.await_args_list
    return post.args[0], post.kwargs


@pytest.mark.parametrize(
    ("stage", "picture"),
    [
        (Stage.BABY, "sick_baby.png"),
        (Stage.CHILD, "sick_child.png"),
        (Stage.TEEN, "sick_teen.png"),
    ],
)
async def test_sick_post_shows_his_stage_picture(
    bot: app.WispBot, server: FakeServer, assets: Path, stage: Stage, picture: str
) -> None:
    for name in SICK_ART:
        add_image(assets, "moments", name)

    text, kwargs = await event_post(bot, server, Event(EventKind.SICK, stage))

    assert said(text, Moment.SICK)
    assert kwargs["file"].filename == picture
    assert sends_without_pinging(kwargs)


async def test_a_sick_post_without_its_picture_is_text_only(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "moments", "sick_baby")

    text, kwargs = await event_post(bot, server, Event(EventKind.SICK, Stage.TEEN))

    assert said(text, Moment.SICK)
    assert "file" not in kwargs


def test_the_sick_pictures_are_in_the_repo() -> None:
    moments = Path(announce.__file__).resolve().parent.parent / "ASSETS" / "moments"
    assert set(rules.SICK_PICTURES) == {Stage.BABY, Stage.CHILD, Stage.TEEN}
    for name in rules.SICK_PICTURES.values():
        assert (moments / name).is_file(), name


async def test_recovered_post_shows_him_well_again(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "child")
    add_image(assets, "moments", "sick_child")

    text, kwargs = await event_post(
        bot, server, Event(EventKind.RECOVERED, Stage.CHILD)
    )

    assert said(text, Moment.RECOVERED)
    assert kwargs["file"].filename == "child.png"


@pytest.mark.parametrize(
    ("stage", "files", "expected"),
    [
        (Stage.BABY, ["stages/baby", "moments/sick_baby"], "sick_baby.png"),
        (Stage.CHILD, ["stages/child", "moments/sick_child"], "sick_child.png"),
        (Stage.TEEN, ["stages/teen", "moments/sick_teen"], "sick_teen.png"),
        (Stage.TEEN, ["stages/teen"], "teen.png"),
        (Stage.ADULT, ["stages/adult", "moments/sick_teen"], "adult.png"),
    ],
)
def test_the_card_picture_is_the_sick_one_while_sick(
    assets: Path, stage: Stage, files: list[str], expected: str
) -> None:
    for path in files:
        folder, name = path.split("/")
        add_image(assets, folder, name)
    life = new_egg(1, discord.utils.utcnow())
    life.phase = Phase.ALIVE
    life.stage = stage
    life.cold_left = rules.SICK_FOR.total_seconds()

    image = life_image(life)

    assert image is not None and image.name == expected
    life.cold_left = 0.0
    assert life_image(life) == assets / "stages" / f"{stage.value}.png"


async def test_hatched_keeps_the_baby_picture_first(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "baby")
    add_image(assets, "events", "hatched", ".gif")
    await growing_life(bot, hatched_by=NAMED)

    await post_events(bot, GUILD_ID, [Event(EventKind.HATCHED)])

    assert server.house.send.await_args_list[0].kwargs["file"].filename == "baby.png"


async def test_keepsake_art_prefers_the_animated_gif(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "keepsakes", "eggshell")
    (assets / "keepsakes" / "eggshell.gif").write_bytes(b"GIF")
    life = await growing_life(bot, hatched_by=NAMED)
    life.phase = Phase.HATCHING
    await bot.lives.save(GUILD_ID, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.HATCH_STARTED)])

    _cracking, won = server.house.send.await_args_list
    assert won.kwargs["file"].filename == "eggshell.gif"


@pytest.mark.parametrize(
    "stage,title",
    [
        (Stage.CHILD, "Wisp v1's First Spark"),
        (Stage.TEEN, "Wisp v1's Teen Spark"),
        (Stage.ADULT, "Wisp v1's Adult Spark"),
        (Stage.ROCKSTAR, "Wisp v1's Guitar Pick"),
    ],
)
async def test_a_stage_up_gives_its_keepsake_to_the_latest_interactor(
    bot: app.WispBot, server: FakeServer, assets: Path, stage: Stage, title: str
) -> None:
    life = await growing_life(bot)
    await interacted(bot, life, NAMED, 30)
    await interacted(bot, life, MEMBER, 2)
    member = MagicMock(spec=discord.Member)
    member.display_name = "Bea"
    server.members[MEMBER] = member

    await post_events(bot, GUILD_ID, [Event(EventKind.STAGE_UP, stage)])

    grew, won = server.house.send.await_args_list
    assert said(grew.args[0], Moment.STAGE_UP, stage=stage.value)
    assert keepsake_said(won.args[0], "Bea", title)
    assert "file" not in won.kwargs
    assert sends_without_pinging(won.kwargs)
    assert await embers(bot, MEMBER) == [title]
    assert await embers(bot, NAMED) == []


async def test_growing_old_gives_the_time_piece(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "keepsakes", "time_piece")
    life = await growing_life(bot)
    await interacted(bot, life, NAMELESS, 1)

    await post_events(bot, GUILD_ID, [Event(EventKind.GREW_OLD, Stage.OLD_FOGEY)])

    _old, won = server.house.send.await_args_list
    title = "Wisp v1's Time Piece"
    assert keepsake_said(won.args[0], f"<@{NAMELESS}>", title)
    assert won.kwargs["file"].filename == "time_piece.png"
    assert await embers(bot, NAMELESS) == [title]


async def test_a_milestone_with_nobody_there_gives_nothing(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await growing_life(bot)

    await post_events(
        bot,
        GUILD_ID,
        [Event(EventKind.HATCH_STARTED), Event(EventKind.STAGE_UP, Stage.CHILD)],
    )

    assert server.house.send.await_count == 2
    for user_id in (NAMED, MEMBER, NAMELESS):
        assert await embers(bot, user_id) == []


async def test_a_banned_member_gets_no_milestone_keepsake(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    life = await growing_life(bot, hatched_by=NAMED)
    await interacted(bot, life, NAMED, 1)
    now = discord.utils.utcnow()
    await bot.players.set_offense(GUILD_ID, NAMED, 1, now + timedelta(days=1), False)

    await post_events(
        bot,
        GUILD_ID,
        [Event(EventKind.HATCH_STARTED), Event(EventKind.STAGE_UP, Stage.CHILD)],
    )

    assert server.house.send.await_count == 2
    assert await embers(bot, NAMED) == []


async def test_a_milestone_keepsake_is_given_once(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    life = await growing_life(bot)
    await interacted(bot, life, NAMED, 1)
    grew = [Event(EventKind.STAGE_UP, Stage.TEEN)]

    await post_events(bot, GUILD_ID, grew)
    await post_events(bot, GUILD_ID, grew)

    assert server.house.send.await_count == 3
    assert await embers(bot, NAMED) == ["Wisp v1's Teen Spark"]


async def test_the_last_ember_carries_its_art_when_it_exists(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "keepsakes", "last_ember")
    life = await ended_life(bot, Phase.PASSED)
    await shared(bot, life, {NAMED: 10})

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    _farewell, ember, _question = server.house.send.await_args_list
    assert ember.kwargs["file"].filename == "last_ember.png"
    assert sends_without_pinging(ember.kwargs)


def lost_connection() -> pymysql.err.OperationalError:
    return pymysql.err.OperationalError(2013, "Lost connection")


async def test_a_failed_keepsake_is_reported_and_later_events_still_post(
    bot: app.WispBot,
    server: FakeServer,
    assets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    life = await growing_life(bot)
    await interacted(bot, life, NAMED, 1)
    monkeypatch.setattr(bot.keepsakes, "give", AsyncMock(side_effect=lost_connection()))

    await post_events(
        bot,
        GUILD_ID,
        [
            Event(EventKind.STAGE_UP, Stage.CHILD),
            Event(EventKind.GREW_OLD, Stage.OLD_FOGEY),
        ],
    )

    child, report, old, second_report = [
        call.args[0] for call in server.house.send.await_args_list
    ]
    assert said(child, Moment.STAGE_UP, stage="child")
    assert said(old, Moment.GREW_OLD)
    for line in (report, second_report):
        assert line.startswith("Error in giving a keepsake: OperationalError")
    assert all(" gets " not in line for line in (child, old))


async def test_a_failed_keepsake_never_stops_the_question(
    bot: app.WispBot,
    server: FakeServer,
    assets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    life = await ended_life(bot, Phase.PASSED)
    await shared(bot, life, {NAMED: 10})
    await bot.players.set_name(GUILD_ID, NAMED, "Aria")
    monkeypatch.setattr(bot.notes, "recent", AsyncMock(side_effect=lost_connection()))

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    farewell, report, question = [
        call.args[0] for call in server.house.send.await_args_list
    ]
    assert said(farewell, Moment.FAREWELL, version="3")
    assert report.startswith("Error in giving a keepsake: OperationalError")
    assert question == BEGIN_AGAIN
    assert await embers(bot, NAMED) == ["Wisp v3's Last Ember"]
