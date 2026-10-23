"""Tests for Wisp's House announcements, the next life and pinned messages.

Discord objects are fakes; the repositories are the real ones.
"""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from ai.chain import AllProvidersFailed
from ai.prompt import Prompt
from cogs import announce
from cogs.announce import next_life, post_events, show_in_thread
from db.activity import ActivityRepo
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
ERRORS_ID = 40
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
    """A guild with Wisp's House, an errors channel and the Status and Vault threads."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.errors = MagicMock(spec=discord.TextChannel)
        self.errors.send = AsyncMock()
        self.status = FakeThread(STATUS_ID)
        self.board = FakeThread(BOARD_ID)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {
            HOUSE_ID: self.house,
            ERRORS_ID: self.errors,
        }.get
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
        error_channel_id=ERRORS_ID,
        status_thread_id=STATUS_ID,
        status_message_id=STATUS_MESSAGE_ID,
        vault_thread_id=BOARD_ID,
        vault_message_id=BOARD_MESSAGE_ID,
    )


async def show_status(
    bot: app.WispBot, content: str = "card", view: discord.ui.View | None = None
) -> None:
    await show_in_thread(
        bot,
        GUILD_ID,
        "status_thread_id",
        "status_message_id",
        content,
        "status card",
        view,
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
    assert settings.vault_message_id == REPOSTED_ID
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

    assert (await bot.settings.get(GUILD_ID)).vault_message_id == REPOSTED_ID
    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report.startswith("Error in pinning the ViiBR Vault card: Forbidden")


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


# ---
# Growing old, the farewell and the next life
# ---


@pytest.fixture
def assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(announce, "ASSETS_DIR", tmp_path)
    return tmp_path


def add_image(assets: Path, folder: str, name: str) -> None:
    target = assets / folder / f"{name}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"png")


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


async def test_farewell_posts_line_then_gifts_then_coal_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "events", "farewell")
    add_image(assets, "stages", "coal_egg")
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    posts = server.house.send.await_args_list
    assert len(posts) == 5
    farewell, named, member, nameless, coal = posts
    assert said(farewell.args[0], Moment.FAREWELL, version="3")
    assert farewell.kwargs["file"].filename == "farewell.png"
    assert gift_said(named.args[0], "Aria", 3)
    assert gift_said(member.args[0], "Bea", 3)
    assert gift_said(nameless.args[0], f"<@{NAMELESS}>", 3)
    assert said(coal.args[0], Moment.COAL_EGG, version="4")
    assert coal.kwargs["file"].filename == "coal_egg.png"
    assert all(sends_without_pinging(post.kwargs) for post in posts)
    egg = await current_life(bot)
    assert (egg.version, egg.phase, egg.from_coal) == (4, Phase.EGG, True)
    assert egg.egg_food == rules.COAL_EGG_FOOD
    for user_id in (NAMED, MEMBER, NAMELESS):
        assert await embers(bot, user_id) == ["Wisp v3's Last Ember"]
    assert await embers(bot, FOURTH) == []


async def test_coal_egg_without_its_image_is_text_only(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await ended_life(bot, Phase.PASSED)

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    farewell, coal = server.house.send.await_args_list
    assert "file" not in farewell.kwargs
    assert said(coal.args[0], Moment.COAL_EGG, version="4")
    assert "file" not in coal.kwargs


async def test_next_life_after_farewell_is_idempotent(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)

    await next_life(bot, GUILD_ID, discord.utils.utcnow())
    posted = server.house.send.await_count
    await next_life(bot, GUILD_ID, discord.utils.utcnow())

    assert posted == 4
    assert server.house.send.await_count == posted
    assert [old.version for old in await bot.lives.history(GUILD_ID)] == [4, 3]
    for user_id in (NAMED, MEMBER, NAMELESS):
        assert await embers(bot, user_id) == ["Wisp v3's Last Ember"]


async def test_banned_top_sharer_gets_no_ember(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)
    now = discord.utils.utcnow()
    await bot.players.set_offense(GUILD_ID, MEMBER, 1, now + timedelta(days=1), False)

    await next_life(bot, GUILD_ID, now)

    named, nameless, coal = [call.args[0] for call in server.house.send.await_args_list]
    assert gift_said(named, "Aria", 3)
    assert gift_said(nameless, f"<@{NAMELESS}>", 3)
    assert said(coal, Moment.COAL_EGG, version="4")
    assert await embers(bot, MEMBER) == []
    assert await embers(bot, FOURTH) == []


async def test_expired_ban_does_not_stop_the_ember(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)
    now = discord.utils.utcnow()
    await bot.players.set_offense(GUILD_ID, MEMBER, 1, now - timedelta(days=1), False)

    await next_life(bot, GUILD_ID, now)

    assert await embers(bot, MEMBER) == ["Wisp v3's Last Ember"]


async def test_neglect_death_gives_no_gifts_and_a_fresh_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "coal_egg")
    life = await ended_life(bot, Phase.DEAD)
    await known_sharers(bot, server, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.DIED)])

    died, laid = server.house.send.await_args_list
    assert said(died.args[0], Moment.DIED, version="3")
    assert said(laid.args[0], Moment.NEW_EGG, version="4")
    assert "file" not in laid.kwargs
    egg = await current_life(bot)
    assert (egg.version, egg.from_coal, egg.egg_food) == (4, False, 0)
    for user_id in (NAMED, MEMBER, NAMELESS, FOURTH):
        assert await embers(bot, user_id) == []


async def test_first_life_is_a_fresh_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await next_life(bot, GUILD_ID, discord.utils.utcnow())

    egg = await current_life(bot)
    assert (egg.version, egg.phase, egg.from_coal) == (1, Phase.EGG, False)
    (laid,) = server.house.send.await_args_list
    assert said(laid.args[0], Moment.NEW_EGG, version="1")


async def test_next_life_leaves_a_living_wisp_alone(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await bot.lives.insert(GUILD_ID, new_egg(1, discord.utils.utcnow()))

    await next_life(bot, GUILD_ID, discord.utils.utcnow())

    assert [old.version for old in await bot.lives.history(GUILD_ID)] == [1]
    server.house.send.assert_not_awaited()


async def test_farewell_with_missing_house_is_reported_once_and_gifts_still_given(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=None)
    life = await ended_life(bot, Phase.PASSED)
    await known_sharers(bot, server, life)

    await post_events(bot, GUILD_ID, [Event(EventKind.FAREWELL)])

    assert (await current_life(bot)).version == 4
    assert await embers(bot, NAMED) == ["Wisp v3's Last Ember"]
    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report.startswith("Error in posting to Wisp's House")


async def test_grew_old_is_announced_with_its_image(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    add_image(assets, "stages", "old_fogey")
    life = new_egg(1, discord.utils.utcnow() - timedelta(days=50))
    life.phase = Phase.ALIVE
    life.care = 80.0
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

    await next_life(bot, GUILD_ID, discord.utils.utcnow())

    named, member, nameless, coal = [
        call.args[0] for call in server.house.send.await_args_list
    ]
    assert named == (
        "♪ Aria gets Wisp v3's Last Ember\n"
        "thanks for every track, Aria. the ember's yours"
    )
    assert gift_said(member, "Bea", 3)
    assert gift_said(nameless, f"<@{NAMELESS}>", 3)
    assert said(coal, Moment.COAL_EGG, version="4")
    to_aria, to_bea, _ = [call.args[0] for call in ai.await_args_list]
    assert "Wisp v3" in to_aria.user
    assert "Aria" in to_aria.user and "plays bass" in to_aria.user
    assert "Bea" in to_bea.user and "plays bass" not in to_bea.user
    assert lock_held == [False, False, False]
    server.errors.send.assert_awaited_once()
    (report,) = server.errors.send.await_args.args
    assert report == "Error in Wisp's AI voice: AllProvidersFailed: gemini: timed out"
