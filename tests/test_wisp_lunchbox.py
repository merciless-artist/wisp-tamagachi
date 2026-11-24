"""Tests for Wisp's own lunchbox, WiSP'S FAVORITES: songs, snacks, emoji, gifts.

Discord objects are fakes; the repositories are the real ones, and song pages
come from a local stand-in for viibrmusic.com.
"""

import json
import random
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from discord import app_commands

import app
from cogs import groups, wisp_lunchbox
from cogs.share_links import ShareLinkResolver
from cogs.wisp_lunchbox import LunchboxButton, lunchbox_text, pick_favorite_song
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.gifts import GiftRepo
from db.lives import LifeRepo
from db.lunchbox import WispLunchboxRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from tests.layout import layout_text
from wisp import rules
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.links import Track, TrackKind
from wisp.rules import GIFT_BY_KEY, SONG_TITLE_LIMIT, Stage
from wisp.text import LAYOUT_TEXT_LIMIT, USER_ERROR, text_length

GUILD_ID = 100
OTHER_GUILD_ID = 200
FORUM_ID = 10
HOUSE_ID = 20
MEALTIME_ID = 30
TRACKS_ID = 40
LOUNGE_ID = 50
FIRST = 1
SECOND = 2
NOW = datetime(2026, 10, 23, 0, 5, tzinfo=UTC)
YESTERDAY = date(2026, 10, 22)
NO_PING = discord.AllowedMentions.none().to_dict()
# Wisp's app emojis Myra's layout is made of.
LAYOUT_EMOJIS = (
    "headerbarright",
    "wisp_waveform",
    "headerbarleft",
    "boing_bass",
    "portable_speaker",
    "wisp_play",
    "wisp_pause",
    "wisp_stop",
    "headerbar",
    "mic2",
)
TITLE_BAR = "<:headerbarright:1><:wisp_waveform:2><:headerbarleft:3>"
FOOTER_BAR = (
    "<:headerbarright:1><:headerbar:9><:wisp_waveform:2>"
    "<:headerbar:9><:headerbarleft:3>"
)
TITLE = f"# {TITLE_BAR} **WiSP'S FAVORITES** {TITLE_BAR}"
SPEAKER = "<:portable_speaker:5>"
SNACKS = "### <:wisp_play:6>**FAVORITE SNACKS**"
EMOJI = "## <:wisp_pause:7> **FAVORITE EMOJI**"
GIFTS = "## <:wisp_stop:8>  **FAVORITE GIFTS**"
FOOTER = f"### ・{FOOTER_BAR}<:mic2:10>https://viibrmusic.com {FOOTER_BAR}・"
BLANK = "** **"
NONE_YET = "### ・none yet"


def top(songs: int) -> str:
    return f"## <:boing_bass:4> **TOP {songs} SONGS**"


# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House and the Mealtime thread."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.mealtime = MagicMock(spec=discord.Thread)
        self.mealtime.id = MEALTIME_ID
        self.mealtime.parent_id = FORUM_ID
        self.mealtime.archived = False
        self.mealtime.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get
        self.members: dict[int, MagicMock] = {}
        self.guild.get_member.side_effect = self.members.get

    def add_member(self, user_id: int, display_name: str) -> None:
        member = MagicMock(spec=discord.Member)
        member.id = user_id
        member.display_name = display_name
        self.members[user_id] = member

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        if channel_id != MEALTIME_ID:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return self.mealtime


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
    wisp_bot.wisp_lunchbox = WispLunchboxRepo(db)
    wisp_bot.gifts = GiftRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture
def repo(db: Database) -> WispLunchboxRepo:
    return WispLunchboxRepo(db)


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    give_emojis(bot)
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        mealtime_thread_id=MEALTIME_ID,
        tracks_channel_id=TRACKS_ID,
    )


def uuid_of(ident: int) -> str:
    return f"00000000-0000-0000-0000-{ident:012d}"


def viibr(ident: int) -> Track:
    uuid = uuid_of(ident)
    return Track(
        TrackKind.VIIBR, f"viibr:{uuid}", f"https://viibrmusic.com/songs/{uuid}"
    )


def suno(ident: int) -> Track:
    uuid = f"11111111-0000-0000-0000-{ident:012d}"
    return Track(TrackKind.SUNO, f"suno:{uuid}", f"https://suno.com/song/{uuid}")


async def fed(
    bot: app.WispBot,
    track: Track,
    at: datetime,
    user_id: int = FIRST,
    guild_id: int = GUILD_ID,
) -> None:
    assert await bot.activity_log.record_feed(guild_id, 1, user_id, track, 5, 9, at)


def on(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


async def lay(bot: app.WispBot, health: float = 50.0) -> Life:
    life = new_egg(1, NOW - timedelta(days=2))
    life.phase = Phase.ALIVE
    life.health = health
    life.stage = life.peak_stage = Stage.BABY
    life.hatched_at = life.stage_started_at = NOW - timedelta(days=1)
    return await bot.lives.insert(GUILD_ID, life)


def give_emojis(bot: app.WispBot, *names: str, layout: bool = True) -> None:
    """Upload the layout's emojis (ids 1 to 10) unless `layout` is off, then `names`."""
    uploaded = [*(LAYOUT_EMOJIS if layout else ()), *names]
    bot.emojis_by_name = {
        name: cast(discord.Emoji, discord.PartialEmoji(name=name, id=index))
        for index, name in enumerate(uploaded, start=1)
    }


# ---
# Local viibrmusic.com
# ---


@dataclass
class Site:
    """A stand-in for viibrmusic.com's song pages that records what it was asked.

    `names` gives a song's name by uuid; any other song has no page. A uuid in
    `failing` answers with a server error.
    """

    names: dict[str, str] = field(default_factory=dict)
    failing: set[str] = field(default_factory=set)
    asked: list[str] = field(default_factory=list)

    async def song(self, request: web.Request) -> web.StreamResponse:
        uuid = request.match_info["uuid"]
        self.asked.append(uuid)
        if uuid in self.failing:
            return web.Response(status=500)
        if uuid not in self.names:
            return web.Response(status=404)
        block = json.dumps({"@type": "MusicRecording", "name": self.names[uuid]})
        page = f'<script type="application/ld+json">{block}</script>'
        return web.Response(text=page, content_type="text/html")

    def name(self, ident: int, title: str) -> None:
        self.names[uuid_of(ident)] = title


@pytest.fixture(autouse=True)
async def site(bot: app.WispBot) -> AsyncIterator[Site]:
    """viibrmusic.com for the bot, so no test reads the real site."""
    pages = Site()
    routes = web.Application()
    routes.router.add_get("/songs/{uuid}", pages.song)
    server = TestServer(routes)
    await server.start_server()
    bot.share_links = ShareLinkResolver(
        origins={"viibrmusic.com": str(server.make_url("/"))},
        timeout=timedelta(seconds=2),
    )
    try:
        yield pages
    finally:
        await bot.share_links.close()
        await server.close()


def say(bot: app.WispBot, line: str = "mine now") -> MagicMock:
    bot.lines = MagicMock()
    bot.lines.pick.return_value = line
    return cast(MagicMock, bot.lines.pick)


def make_interaction(
    bot: app.WispBot, server: FakeServer, user_id: int = FIRST
) -> MagicMock:
    """An interaction in a lounge channel of the server."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.channel.id = LOUNGE_ID
    interaction.channel.send = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def open_lunchbox(
    bot: app.WispBot, server: FakeServer, interaction: MagicMock | None = None
) -> MagicMock:
    interaction = interaction or make_interaction(bot, server)
    command: Any = wisp_lunchbox.wisp_lunchbox
    await command.callback(interaction)
    return interaction


def posted(call: Any) -> str:
    """The lunchbox one send posted: one layout of its text, no picture."""
    assert "content" not in call.kwargs and call.args == ()
    assert "files" not in call.kwargs
    view = call.kwargs["view"]
    assert isinstance(view, discord.ui.LayoutView)
    (shown,) = view.children
    assert isinstance(shown, discord.ui.TextDisplay)
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    return layout_text(view)


async def keep(bot: app.WispBot, ident: int, day: date, user_id: int = FIRST) -> None:
    """Feed `viibr(ident)` on `day` and keep it as that day's favorite."""
    await fed(bot, viibr(ident), on(day), user_id=user_id)
    assert await bot.wisp_lunchbox.pick_favorite(GUILD_ID, day, random.Random(), NOW)


async def kept_gift(bot: app.WispBot, life: Life, gift: str) -> None:
    assert life.id is not None
    await bot.gifts.record(GUILD_ID, life.id, FIRST, gift, True, NOW)


async def ate(bot: app.WispBot, life: Life, *snacks: str) -> None:
    assert life.id is not None
    for snack in snacks:
        await bot.activity_log.record_interaction(
            GUILD_ID, life.id, FIRST, InteractionKind.SNACK, 0, 8, NOW, snack=snack
        )


# ---
# Picking a favorite song
# ---


async def test_a_favorite_comes_only_from_the_days_viibr_feeds(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    await fed(bot, suno(1), on(YESTERDAY, 9))
    for ident in (2, 3, 4):
        await fed(bot, viibr(ident), on(YESTERDAY, ident), user_id=ident)
    await fed(bot, viibr(5), on(YESTERDAY - timedelta(days=1)))
    await fed(bot, viibr(6), on(YESTERDAY + timedelta(days=1), 0))

    favorite = await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(3), NOW)

    assert favorite is not None
    assert favorite.day == YESTERDAY
    assert favorite.url in {viibr(ident).url for ident in (2, 3, 4)}
    assert favorite.track_key == f"viibr:{favorite.url.rsplit('/', 1)[1]}"
    assert favorite.user_id == int(favorite.url[-1])
    assert await repo.favorites(GUILD_ID, 10) == [favorite]


async def test_a_share_link_feed_counts_as_a_viibr_feed(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    shared = Track(TrackKind.VIIBR, viibr(2).key, "https://viibrmusic.com/s/bDBmywB5")
    await fed(bot, suno(1), on(YESTERDAY, 9))
    await fed(bot, shared, on(YESTERDAY, 10))

    favorite = await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(3), NOW)

    assert favorite is not None
    assert (favorite.url, favorite.track_key) == (shared.url, shared.key)


async def test_the_pick_is_random_among_the_days_viibr_feeds(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    picks = set()
    for seed in range(4):
        day = YESTERDAY - timedelta(days=seed)
        for ident in range(1, 5):
            await fed(bot, viibr(100 * (seed + 1) + ident), on(day, ident))
        favorite = await repo.pick_favorite(GUILD_ID, day, random.Random(seed), NOW)
        assert favorite is not None
        picks.add(favorite.url[-1])

    assert len(picks) > 1


async def test_a_day_without_viibr_feeds_has_no_favorite(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    await fed(bot, suno(1), on(YESTERDAY))

    assert await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW) is None
    assert await repo.favorites(GUILD_ID, 10) == []


async def test_a_day_is_picked_only_once(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    await fed(bot, viibr(1), on(YESTERDAY))
    first = await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW)

    again = await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW)

    assert first is not None
    assert again is None
    assert await repo.favorites(GUILD_ID, 10) == [first]


async def test_favorites_are_per_guild(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    await fed(bot, viibr(1), on(YESTERDAY), guild_id=OTHER_GUILD_ID)

    assert await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW) is None
    assert await repo.pick_favorite(OTHER_GUILD_ID, YESTERDAY, random.Random(), NOW)
    assert await repo.favorites(GUILD_ID, 10) == []


async def test_favorites_are_newest_first_up_to_the_limit(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    days = [YESTERDAY - timedelta(days=offset) for offset in (2, 0, 1)]
    for ident, day in enumerate(days, start=1):
        await fed(bot, viibr(ident), on(day))
        await repo.pick_favorite(GUILD_ID, day, random.Random(), NOW)

    newest = await repo.favorites(GUILD_ID, 2)

    assert [favorite.day for favorite in newest] == sorted(days, reverse=True)[:2]


# ---
# Announcing it
# ---


async def test_the_favorite_is_announced_in_mealtime_without_pings(
    bot: app.WispBot, server: FakeServer, site: Site
) -> None:
    life = await lay(bot)
    await fed(bot, viibr(1), on(YESTERDAY))
    server.add_member(FIRST, "Member1")
    pick = say(bot, "mine now")

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)

    server.mealtime.send.assert_awaited_once()
    (text,) = server.mealtime.send.await_args.args
    assert text == (
        f"♪ Wisp put <@{FIRST}>'s track in his lunchbox ・ {viibr(1).url}\nmine now"
    )
    kwargs = server.mealtime.send.await_args.kwargs
    assert set(kwargs) == {"allowed_mentions"}
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    pick.assert_called_once_with(Moment.FAVORITE_SONG, Mood.HAPPY, name="Member1")
    server.house.send.assert_not_awaited()
    (favorite,) = await bot.wisp_lunchbox.favorites(GUILD_ID, 10)
    assert favorite.title == ""
    assert site.asked == [uuid_of(1)]


async def test_the_announcement_names_the_song_he_read(
    bot: app.WispBot, server: FakeServer, site: Site
) -> None:
    life = await lay(bot)
    await fed(bot, viibr(1), on(YESTERDAY))
    site.name(1, "Time Goes *Foggy*")
    say(bot, "mine now")

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)

    (text,) = server.mealtime.send.await_args.args
    assert text == (
        f'♪ Wisp put <@{FIRST}>\'s track "Time Goes \\*Foggy\\*" in his lunchbox ・ '
        f"{viibr(1).url}\nmine now"
    )
    (favorite,) = await bot.wisp_lunchbox.favorites(GUILD_ID, 10)
    assert favorite.title == "Time Goes *Foggy*"


async def test_an_unreadable_page_is_announced_without_a_name_and_left_unread(
    bot: app.WispBot, server: FakeServer, site: Site
) -> None:
    life = await lay(bot)
    await fed(bot, viibr(1), on(YESTERDAY))
    site.failing.add(uuid_of(1))
    say(bot, "mine now")

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)

    (text,) = server.mealtime.send.await_args.args
    assert text.startswith(f"♪ Wisp put <@{FIRST}>'s track in his lunchbox ・ ")
    (favorite,) = await bot.wisp_lunchbox.favorites(GUILD_ID, 10)
    assert favorite.title is None
    assert server.house.send.await_count == 0


@pytest.mark.parametrize(
    ("chosen", "display", "expected"),
    [
        ("Zed", "Member1", "Zed"),
        (None, "Member1", "Member1"),
        (None, None, f"<@{FIRST}>"),
    ],
)
async def test_the_favorite_line_names_the_member_as_elsewhere(
    bot: app.WispBot,
    server: FakeServer,
    chosen: str | None,
    display: str | None,
    expected: str,
) -> None:
    life = await lay(bot)
    await fed(bot, viibr(1), on(YESTERDAY))
    if chosen is not None:
        await bot.players.set_name(GUILD_ID, FIRST, chosen)
    if display is not None:
        server.add_member(FIRST, display)
    pick = say(bot)

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)

    pick.assert_called_once_with(Moment.FAVORITE_SONG, Mood.HAPPY, name=expected)


async def test_the_favorite_line_follows_his_mood(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot, health=5.0)
    await fed(bot, viibr(1), on(YESTERDAY))
    pick = say(bot)

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)

    assert pick.call_args.args == (Moment.FAVORITE_SONG, Mood.HANGRY)


async def test_a_second_pick_that_day_announces_nothing(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await fed(bot, viibr(1), on(YESTERDAY))

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)
    await pick_favorite_song(
        bot, server.guild, life, random.Random(), NOW + timedelta(hours=3)
    )

    server.mealtime.send.assert_awaited_once()


async def test_no_viibr_feeds_yesterday_announces_nothing(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await fed(bot, suno(1), on(YESTERDAY))
    await fed(bot, viibr(2), on(YESTERDAY + timedelta(days=1), 0))

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)

    server.mealtime.send.assert_not_awaited()
    server.house.send.assert_not_awaited()


async def test_a_failed_announcement_is_posted_in_mealtime(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await fed(bot, viibr(1), on(YESTERDAY))
    server.mealtime.send.side_effect = [
        discord.HTTPException(MagicMock(status=500), "boom"),
        None,
    ]

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)

    report = server.mealtime.send.await_args.args[0]
    assert report.startswith(
        "Error in posting Wisp's favorite song to Mealtime: HTTPException"
    )
    assert len(await bot.wisp_lunchbox.favorites(GUILD_ID, 10)) == 1
    server.house.send.assert_not_awaited()


async def test_an_unreachable_mealtime_is_reported_in_the_house(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await fed(bot, viibr(1), on(YESTERDAY))
    await bot.settings.update(GUILD_ID, mealtime_thread_id=None, studio_forum_id=None)

    await pick_favorite_song(bot, server.guild, life, random.Random(), NOW)

    (report,) = server.house.send.await_args.args
    assert report.startswith(
        "Error in posting Wisp's favorite song to Mealtime: StudioError"
    )
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        NO_PING
    )


# ---
# Favorite emoji
# ---


async def test_expression_uses_are_counted_most_used_first(
    repo: WispLunchboxRepo,
) -> None:
    await repo.record_expressions(GUILD_ID, ["wisp_happy", "wisp_wink"])
    await repo.record_expressions(GUILD_ID, ["wisp_wink", "wisp_wink"])
    await repo.record_expressions(GUILD_ID, ["wisp_cool"])
    await repo.record_expressions(OTHER_GUILD_ID, ["wisp_cool", "wisp_cool"])

    assert await repo.favorite_expressions(GUILD_ID) == [
        "wisp_wink",
        "wisp_cool",
        "wisp_happy",
    ]
    assert await repo.favorite_expressions(OTHER_GUILD_ID) == ["wisp_cool"]


async def test_no_expressions_recorded_means_none(repo: WispLunchboxRepo) -> None:
    await repo.record_expressions(GUILD_ID, [])

    assert await repo.favorite_expressions(GUILD_ID) == []


# ---
# /wisp lunchbox
# ---


async def test_the_lunchbox_is_posted_publicly_where_it_was_asked_for(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = await open_lunchbox(bot, server)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    (post,) = interaction.channel.send.await_args_list
    assert posted(post) == await lunchbox_text(bot, GUILD_ID)
    interaction.delete_original_response.assert_awaited_once_with()
    interaction.followup.send.assert_not_awaited()
    server.house.send.assert_not_awaited()


async def test_a_failed_delete_of_the_private_answer_is_ignored(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(bot, server)
    gone = discord.NotFound(MagicMock(status=404), "Unknown Webhook")
    interaction.delete_original_response.side_effect = gone

    await open_lunchbox(bot, server, interaction)

    interaction.channel.send.assert_awaited_once()
    interaction.delete_original_response.assert_awaited_once_with()
    interaction.followup.send.assert_not_awaited()
    server.house.send.assert_not_awaited()


async def test_a_public_post_that_fails_leaves_the_answer_private(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(bot, server)
    refused = discord.Forbidden(MagicMock(status=403), "Missing Permissions")
    interaction.channel.send.side_effect = refused

    with pytest.raises(discord.Forbidden):
        await open_lunchbox(bot, server, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.delete_original_response.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()


@pytest.mark.parametrize("in_thread", [False, True])
async def test_asked_for_in_the_track_drop_it_goes_to_the_house(
    bot: app.WispBot, server: FakeServer, in_thread: bool
) -> None:
    interaction = make_interaction(bot, server)
    if in_thread:
        interaction.channel = MagicMock(spec=discord.Thread)
        interaction.channel.id = 99
        interaction.channel.parent_id = TRACKS_ID
    else:
        interaction.channel.id = TRACKS_ID

    await open_lunchbox(bot, server, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.channel.send.assert_not_awaited()
    (post,) = server.house.send.await_args_list
    assert posted(post) == await lunchbox_text(bot, GUILD_ID)
    told = interaction.followup.send.await_args
    assert told.args == (f"♪ Wisp's lunchbox is open in <#{HOUSE_ID}>.",)
    assert told.kwargs["ephemeral"] is True
    assert told.kwargs["allowed_mentions"].to_dict() == NO_PING


async def test_in_the_track_drop_with_no_house_it_is_shown_privately(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=None)
    interaction = make_interaction(bot, server)
    interaction.channel.id = TRACKS_ID

    await open_lunchbox(bot, server, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    server.house.send.assert_not_awaited()
    (call,) = interaction.followup.send.await_args_list
    assert call.kwargs["ephemeral"] is True
    assert posted(call) == await lunchbox_text(bot, GUILD_ID)


async def test_a_channel_that_cannot_be_placed_counts_as_the_track_drop(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(bot, server)
    interaction.channel = MagicMock(spec=discord.PartialMessageable)

    await open_lunchbox(bot, server, interaction)

    server.house.send.assert_awaited_once()
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)


async def test_asked_for_in_a_studio_thread_it_is_shown_privately(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(bot, server)
    interaction.channel = MagicMock(spec=discord.Thread)
    interaction.channel.id = 98
    interaction.channel.parent_id = FORUM_ID
    interaction.channel.send = AsyncMock()

    await open_lunchbox(bot, server, interaction)

    interaction.channel.send.assert_not_awaited()
    server.house.send.assert_not_awaited()
    (call,) = interaction.followup.send.await_args_list
    assert call.kwargs["ephemeral"] is True
    assert posted(call) == await lunchbox_text(bot, GUILD_ID)
    interaction.delete_original_response.assert_not_awaited()


async def test_an_empty_lunchbox_says_none_yet(bot: app.WispBot) -> None:
    text = await lunchbox_text(bot, GUILD_ID)

    assert text.splitlines() == [
        TITLE,
        "## <:boing_bass:4> **TOP SONGS**",
        BLANK,
        NONE_YET,
        BLANK,
        SNACKS,
        NONE_YET,
        EMOJI,
        NONE_YET,
        GIFTS,
        NONE_YET,
        FOOTER,
    ]


async def test_the_whole_lunchbox_matches_myras_draft(
    bot: app.WispBot, site: Site
) -> None:
    await keep(bot, 1, date(2026, 10, 2), user_id=FIRST)
    await keep(bot, 2, date(2026, 11, 13), user_id=SECOND)
    site.name(2, "Time Goes Foggy X")
    life = await lay(bot)
    life.favorite_snack = "cheese"
    await bot.lives.save(GUILD_ID, life)
    await ate(bot, life, "pickles", "cheese", "pickles")
    await bot.wisp_lunchbox.record_expressions(GUILD_ID, ["wisp_wink"])
    await kept_gift(bot, life, "alien_green")
    await kept_gift(bot, life, "book_blue")
    give_emojis(bot, "snack_cheese", "snack_pickles", "wisp_wink", "gift_alien_green")

    text = await lunchbox_text(bot, GUILD_ID)

    assert text.splitlines() == [
        TITLE,
        top(2),
        BLANK,
        f" **01 · NOV 13** — <@{SECOND}>",
        f" {SPEAKER} Time Goes Foggy X・[♫ listen here]({viibr(2).url})",
        BLANK,
        f" **02 · OCT 2** — <@{FIRST}>",
        f" {SPEAKER} [♫ listen here]({viibr(1).url})",
        BLANK,
        SNACKS,
        "### ・Cheese <:snack_cheese:11>",
        "### ・Pickles <:snack_pickles:12>",
        EMOJI,
        "### ・<:wisp_wink:13> `:wisp_wink:`",
        GIFTS,
        f"### ・<:gift_alien_green:14>・{GIFT_BY_KEY['book_blue'].name}",
        FOOTER,
    ]


async def test_a_song_title_is_read_once_and_kept(bot: app.WispBot, site: Site) -> None:
    await keep(bot, 1, YESTERDAY)
    await keep(bot, 2, YESTERDAY - timedelta(days=1))
    site.name(1, "Neon")

    first = await lunchbox_text(bot, GUILD_ID)
    again = await lunchbox_text(bot, GUILD_ID)

    assert first == again
    assert f" {SPEAKER} Neon・[♫ listen here]({viibr(1).url})" in first
    assert sorted(site.asked) == [uuid_of(1), uuid_of(2)]
    titles = [
        favorite.title for favorite in await bot.wisp_lunchbox.favorites(GUILD_ID, 10)
    ]
    assert titles == ["Neon", ""]


async def test_a_page_that_cannot_be_read_is_tried_again_next_time(
    bot: app.WispBot, site: Site
) -> None:
    await keep(bot, 1, YESTERDAY)
    site.failing.add(uuid_of(1))

    first = await lunchbox_text(bot, GUILD_ID)
    site.failing.clear()
    site.name(1, "Later")
    again = await lunchbox_text(bot, GUILD_ID)

    assert f" {SPEAKER} [♫ listen here]({viibr(1).url})" in first.splitlines()
    assert f" {SPEAKER} Later・[♫ listen here]({viibr(1).url})" in again
    assert site.asked == [uuid_of(1), uuid_of(1)]


async def test_a_song_name_cannot_break_the_layout(
    bot: app.WispBot, site: Site
) -> None:
    await keep(bot, 1, YESTERDAY)
    site.name(1, "**big** _tilt_ [x](y)")

    text = await lunchbox_text(bot, GUILD_ID)

    song = text.splitlines()[4]
    assert song.startswith(f" {SPEAKER} \\*\\*big\\*\\* \\_tilt\\_ ")
    assert song.endswith(f"・[♫ listen here]({viibr(1).url})")


async def test_the_title_spells_him_wisp(bot: app.WispBot) -> None:
    assert (await lunchbox_text(bot, GUILD_ID)).startswith(
        "# <:headerbarright:1><:wisp_waveform:2><:headerbarleft:3> **WiSP'S FAVORITES**"
    )


async def test_missing_layout_emojis_are_left_out_cleanly(bot: app.WispBot) -> None:
    give_emojis(bot, "wisp_stop", layout=False)

    text = await lunchbox_text(bot, GUILD_ID)

    assert text.splitlines() == [
        "# **WiSP'S FAVORITES**",
        "## **TOP SONGS**",
        BLANK,
        NONE_YET,
        BLANK,
        "### **FAVORITE SNACKS**",
        NONE_YET,
        "## **FAVORITE EMOJI**",
        NONE_YET,
        "## <:wisp_stop:1>  **FAVORITE GIFTS**",
        NONE_YET,
        "### ・https://viibrmusic.com",
    ]


async def test_a_snack_with_no_emoji_shows_its_name(bot: app.WispBot) -> None:
    life = await lay(bot)
    life.favorite_snack = "viibrwave"
    await bot.lives.save(GUILD_ID, life)

    text = await lunchbox_text(bot, GUILD_ID)

    assert [SNACKS, "### ・ViiBR Wave"] == text.splitlines()[5:7]


@pytest.mark.parametrize(
    ("favorite", "eaten", "shown"),
    [
        ("cheese", ["cheese", "cheese"], ["Cheese"]),
        ("cheese", [], ["Cheese"]),
        (None, ["pickles"], ["Pickles"]),
        ("cheese", ["pickles", "sinewave", "pickles"], ["Cheese", "Pickles"]),
    ],
)
async def test_his_favorite_snacks_are_at_most_two(
    bot: app.WispBot, favorite: str | None, eaten: list[str], shown: list[str]
) -> None:
    life = await lay(bot)
    life.favorite_snack = favorite
    await bot.lives.save(GUILD_ID, life)
    await ate(bot, life, *eaten)

    lines = (await lunchbox_text(bot, GUILD_ID)).splitlines()

    start = lines.index(SNACKS) + 1
    assert lines[start : lines.index(EMOJI)] == [f"### ・{name}" for name in shown]


async def test_snacks_of_an_earlier_life_do_not_count(bot: app.WispBot) -> None:
    old = new_egg(0, NOW - timedelta(days=9))
    old = await bot.lives.insert(GUILD_ID, old)
    await ate(bot, old, "pickles")
    old.phase = Phase.DEAD
    await bot.lives.save(GUILD_ID, old)
    await lay(bot)

    lines = (await lunchbox_text(bot, GUILD_ID)).splitlines()

    assert lines[lines.index(SNACKS) + 1] == NONE_YET


async def test_an_egg_has_no_favorite_snack_yet(bot: app.WispBot) -> None:
    await bot.lives.insert(GUILD_ID, new_egg(2, NOW))

    lines = (await lunchbox_text(bot, GUILD_ID)).splitlines()

    assert lines[lines.index(SNACKS) + 1] == NONE_YET


async def test_an_emoji_no_longer_uploaded_gives_way_to_the_next(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    await repo.record_expressions(GUILD_ID, ["wisp_gone", "wisp_gone", "wisp_happy"])
    give_emojis(bot, "wisp_happy")

    lines = (await lunchbox_text(bot, GUILD_ID)).splitlines()

    assert lines[lines.index(EMOJI) + 1] == "### ・<:wisp_happy:11> `:wisp_happy:`"


async def test_no_uploaded_emoji_shows_none_yet(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    await repo.record_expressions(GUILD_ID, ["wisp_gone"])

    lines = (await lunchbox_text(bot, GUILD_ID)).splitlines()

    assert lines[lines.index(EMOJI) + 1] == NONE_YET


async def test_gifts_show_this_lifes_kept_gifts_at_his_stage(
    bot: app.WispBot, db: Database
) -> None:
    life = await lay(bot)
    assert life.id is not None
    gift = next(gift for gift in GIFT_BY_KEY.values() if gift.grows)
    await kept_gift(bot, life, gift.key)
    await bot.gifts.record(GUILD_ID, life.id, FIRST, "book_red", False, NOW)
    await bot.gifts.record(GUILD_ID, life.id + 1, FIRST, "book_green", True, NOW)
    give_emojis(bot, gift.emoji_name(Stage.BABY))

    lines = (await lunchbox_text(bot, GUILD_ID)).splitlines()

    assert lines[lines.index(GIFTS) + 1] == f"### ・<:{gift.emoji_name(Stage.BABY)}:11>"


async def test_the_lunchbox_shows_the_newest_songs_only(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    days = [YESTERDAY - timedelta(days=offset) for offset in range(12)]
    for ident, day in enumerate(days, start=1):
        await keep(bot, ident, day)

    lines = (await lunchbox_text(bot, GUILD_ID)).splitlines()

    shown = rules.FAVORITE_SONGS_SHOWN
    assert lines[1] == top(shown)
    assert lines[3] == f" **01 · OCT 22** — <@{FIRST}>"
    assert lines[4] == f" {SPEAKER} [♫ listen here]({viibr(1).url})"
    assert lines[3 * shown] == f" **{shown:02d} · OCT {23 - shown}** — <@{FIRST}>"
    assert lines[3 * shown + 2 : 3 * shown + 4] == [BLANK, SNACKS]
    assert len(await repo.favorites(GUILD_ID, 100)) == 12


async def test_the_fullest_lunchbox_fits_one_message(
    bot: app.WispBot, db: Database, site: Site
) -> None:
    long_url = "https://viibrmusic.com/songs/" + "x" * 220
    for offset in range(rules.FAVORITE_SONGS_SHOWN):
        await db.execute(
            f"INSERT INTO {db.t('favorites')} "
            "(guild_id, day, user_id, track_key, url, picked_at, title) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                GUILD_ID,
                YESTERDAY - timedelta(days=offset),
                10**17 + offset,
                f"viibr:{offset}",
                long_url,
                NOW.replace(tzinfo=None),
                "\U0001d54e" * SONG_TITLE_LIMIT,
            ),
        )
    life = await lay(bot)
    keys = list(GIFT_BY_KEY)
    for index in range(300):
        await kept_gift(bot, life, keys[index % len(keys)])
    give_emojis(bot, *(gift.emoji_name(Stage.BABY) for gift in GIFT_BY_KEY.values()))

    text = await lunchbox_text(bot, GUILD_ID)

    assert text_length(text) <= LAYOUT_TEXT_LIMIT
    lines = text.splitlines()
    assert lines[-1] == FOOTER
    gifts = lines[-2].removeprefix("### ・").split("・")
    assert 10 < len(gifts) < 300
    assert all(gift.startswith("<:gift_") and gift.endswith(">") for gift in gifts)
    assert site.asked == []


async def test_a_banned_member_can_still_look(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.players.set_offense(GUILD_ID, FIRST, 3, None, True)

    interaction = await open_lunchbox(bot, server)

    assert posted(interaction.channel.send.await_args).startswith(TITLE)


# ---
# The Lunchbox button
# ---


async def test_the_lunchbox_button_shows_the_lunchbox_privately(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(bot, server)

    await LunchboxButton().callback(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    (call,) = interaction.followup.send.await_args_list
    assert call.kwargs["ephemeral"] is True
    assert posted(call) == await lunchbox_text(bot, GUILD_ID)
    interaction.channel.send.assert_not_awaited()
    server.house.send.assert_not_awaited()


async def test_a_banned_member_can_still_look_with_the_button(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.players.set_offense(GUILD_ID, FIRST, 3, None, True)
    interaction = make_interaction(bot, server)

    await LunchboxButton().callback(interaction)

    assert posted(interaction.followup.send.await_args).startswith(TITLE)


async def test_a_failing_lunchbox_button_is_reported_where_it_was_pressed(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    interaction = make_interaction(bot, server)
    interaction.response.is_done.return_value = True
    error = pymysql.err.OperationalError(2013, "Lost connection")
    monkeypatch.setattr(bot.wisp_lunchbox, "favorites", AsyncMock(side_effect=error))
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await LunchboxButton().callback(interaction)

    reported.assert_awaited_once_with(
        server.guild, "the Lunchbox button", error, where=interaction.channel
    )
    interaction.followup.send.assert_awaited_once_with(USER_ERROR, ephemeral=True)


async def test_the_lunchbox_button_survives_a_restart(
    bot: app.WispBot, server: FakeServer
) -> None:
    match = LunchboxButton.__discord_ui_compiled_template__.fullmatch("wisp:lunchbox")
    assert match is not None

    restored = await LunchboxButton.from_custom_id(
        make_interaction(bot, server), MagicMock(spec=discord.ui.Button), match
    )

    assert isinstance(restored, LunchboxButton)
    assert (restored.item.label, restored.item.custom_id) == (
        "Lunchbox",
        "wisp:lunchbox",
    )


async def test_the_lunchbox_button_is_registered_at_startup(bot: app.WispBot) -> None:
    bot.add_dynamic_items = MagicMock()  # type: ignore[method-assign]

    await wisp_lunchbox.setup(bot)

    bot.add_dynamic_items.assert_called_once_with(LunchboxButton)


# ---
# Extension
# ---


def test_the_lunchbox_command_is_wisps_own() -> None:
    assert groups.wisp.get_command("lunchbox") is wisp_lunchbox.wisp_lunchbox
    assert isinstance(wisp_lunchbox.wisp_lunchbox, app_commands.Command)
    assert (
        wisp_lunchbox.wisp_lunchbox.description
        == "See the things Wisp keeps in his lunchbox."
    )


def test_the_lunchbox_is_a_loaded_extension() -> None:
    assert "cogs.wisp_lunchbox" in app.EXTENSIONS


def test_the_bot_has_the_lunchbox_repo() -> None:
    assert isinstance(app.WispBot().wisp_lunchbox, WispLunchboxRepo)
