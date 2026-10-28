"""Tests for Wisp's own lunchbox: favorite songs, his favorite snack and emoji.

Discord objects are fakes; the repositories are the real ones.
"""

import json
import random
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from discord import app_commands

import app
from cogs import groups, wisp_lunchbox
from cogs.share_links import ShareLinkResolver
from cogs.wisp_lunchbox import lunchbox_text, pick_favorite_song, song_link
from db.activity import ActivityRepo
from db.database import Database
from db.gifts import GiftRepo
from db.lives import LifeRepo
from db.lunchbox import WispLunchboxRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from tests.layout import assert_fits_its_box
from wisp import rules
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.links import Track, TrackKind
from wisp.rules import Stage
from wisp.text import (
    MESSAGE_LIMIT,
    SECTION_BREAK,
    bars,
    box_room,
    text_length,
    visual_width,
)

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
TITLE = "𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍 𝄇𝄡𝄚𝄚𝄚𝄚𝄂"
BOX_TOP = "╔══════════════════════╗"
BOX_BOTTOM = "╚══════════════════════╝"
BOTTOM_BAR = bars("𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍")[1]
NONE_YET = "║𝄡 none yet"
SONGS = "║𝄡𝄚𝄂𝄆 **Favorite songs**"
SNACK = "║𝄡𝄚𝄂𝄆 **Favorite snack**"
EMOJI = "║𝄡𝄚𝄂𝄆 **Favorite emoji**"
COLLECTIONS = "║𝄡𝄚𝄂𝄆 **Collections**"
SPEC_LINES = frozenset(
    (Path(__file__).parent.parent / "DOCS" / "specs" / "2026-10-27-house-style.md")
    .read_bytes()
    .decode("utf-8")
    .splitlines()
)

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


@dataclass
class SongSite:
    """A stand-in for viibrmusic.com's song pages that records what it was asked."""

    artists: dict[str, str] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)
    busy: set[str] = field(default_factory=set)

    async def page(self, request: web.Request) -> web.Response:
        uuid = request.match_info["uuid"]
        self.asked.append(uuid)
        if uuid in self.busy:
            return web.Response(status=503)
        if uuid not in self.artists:
            return web.Response(status=404)
        data = json.dumps(
            {"@type": "MusicRecording", "byArtist": {"name": self.artists[uuid]}}
        )
        return web.Response(
            text=f'<html><script type="application/ld+json">{data}</script></html>',
            content_type="text/html",
        )


@pytest.fixture(autouse=True)
async def songs(bot: app.WispBot) -> AsyncIterator[SongSite]:
    """viibrmusic.com's song pages, served locally for the bot's resolver."""
    site = SongSite()
    application = web.Application()
    application.router.add_get("/songs/{uuid}", site.page)
    server = TestServer(application)
    await server.start_server()
    bot.share_links = ShareLinkResolver(
        origins={"viibrmusic.com": str(server.make_url("/"))}
    )
    try:
        yield site
    finally:
        await bot.share_links.close()
        await server.close()


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        mealtime_thread_id=MEALTIME_ID,
        tracks_channel_id=TRACKS_ID,
    )


def viibr(ident: int) -> Track:
    uuid = f"00000000-0000-0000-0000-{ident:012d}"
    return Track(
        TrackKind.VIIBR, f"viibr:{uuid}", f"https://viibrmusic.com/songs/{uuid}"
    )


def uuid_of(track: Track) -> str:
    return track.key.removeprefix("viibr:")


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


async def lay(bot: app.WispBot, full: float = 50.0) -> Life:
    life = new_egg(1, NOW - timedelta(days=2))
    life.phase = Phase.ALIVE
    life.full = full
    life.stage = life.peak_stage = Stage.BABY
    life.hatched_at = life.stage_started_at = NOW - timedelta(days=1)
    return await bot.lives.insert(GUILD_ID, life)


def give_emojis(bot: app.WispBot, *names: str) -> None:
    bot.emojis_by_name = {
        name: cast(discord.Emoji, discord.PartialEmoji(name=name, id=index))
        for index, name in enumerate(names, start=1)
    }


def emoji_text(name: str, index: int) -> str:
    return f"<:{name}:{index}>"


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


def sections(text: str) -> list[list[str]]:
    """The lunchbox's sections inside its frame."""
    lines = text.splitlines()
    assert lines[:2] == [TITLE, BOX_TOP]
    assert lines[-2:] == [BOX_BOTTOM, BOTTOM_BAR]
    return [
        part.splitlines() for part in "\n".join(lines[2:-2]).split(SECTION_BREAK + "\n")
    ]


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
    bot: app.WispBot, server: FakeServer
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
    life = await lay(bot, full=5.0)
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
    post = interaction.channel.send.await_args
    assert post.args == (await lunchbox_text(bot, GUILD_ID),)
    assert post.kwargs["allowed_mentions"].to_dict() == NO_PING
    assert post.kwargs["suppress_embeds"] is True
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
    server.house.send.assert_awaited_once()
    post = server.house.send.await_args
    assert post.args == (await lunchbox_text(bot, GUILD_ID),)
    assert post.kwargs["allowed_mentions"].to_dict() == NO_PING
    assert post.kwargs["suppress_embeds"] is True
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
    call = interaction.followup.send.await_args
    assert call.args == (await lunchbox_text(bot, GUILD_ID),)
    assert call.kwargs["ephemeral"] is True
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    assert call.kwargs["suppress_embeds"] is True


async def test_a_channel_that_cannot_be_placed_counts_as_the_track_drop(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(bot, server)
    interaction.channel = MagicMock(spec=discord.PartialMessageable)

    await open_lunchbox(bot, server, interaction)

    server.house.send.assert_awaited_once()
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)


async def test_an_empty_lunchbox_says_none_yet(bot: app.WispBot) -> None:
    text = await lunchbox_text(bot, GUILD_ID)

    assert sections(text) == [
        [SONGS, NONE_YET],
        [SNACK, NONE_YET],
        [EMOJI, NONE_YET],
        [COLLECTIONS, NONE_YET],
    ]
    for line in (TITLE, BOX_TOP, SONGS, SNACK, EMOJI, COLLECTIONS, BOTTOM_BAR):
        assert line in SPEC_LINES, line


async def test_the_lunchbox_shows_songs_snack_and_emoji(
    bot: app.WispBot, repo: WispLunchboxRepo, songs: SongSite
) -> None:
    songs.artists[uuid_of(viibr(2))] = "Foggy X Music"
    for ident, day in enumerate([date(2026, 10, 2), date(2026, 10, 22)], start=1):
        await fed(bot, viibr(ident), on(day), user_id=ident)
        await repo.pick_favorite(GUILD_ID, day, random.Random(), NOW)
    life = await lay(bot)
    life.favorite_snack = "cheese"
    await bot.lives.save(GUILD_ID, life)
    await repo.record_expressions(GUILD_ID, ["wisp_wink", "wisp_wink", "wisp_happy"])
    give_emojis(bot, "snack_cheese", "wisp_wink", "wisp_happy")

    text = await lunchbox_text(bot, GUILD_ID)

    assert sections(text) == [
        [
            SONGS,
            f"║𝄡𝄚𝄂 Oct 22 ・ <@{SECOND}>",
            f"║𝄡 [Foggy X Music]({viibr(2).url})",
            f"║𝄡𝄚𝄂 Oct 2 ・ <@{FIRST}>",
            f"║𝄡 [listen ♪]({viibr(1).url})",
        ],
        [SNACK, f"║𝄡 {emoji_text('snack_cheese', 1)} Cheese"],
        [EMOJI, f"║𝄡 {emoji_text('wisp_wink', 2)}"],
        [COLLECTIONS, NONE_YET],
    ]


async def test_the_favorite_snack_reads_without_its_emoji(bot: app.WispBot) -> None:
    life = await lay(bot)
    life.favorite_snack = "viibrwave"
    await bot.lives.save(GUILD_ID, life)

    text = await lunchbox_text(bot, GUILD_ID)

    assert [SNACK, "║𝄡 ViiBR Wave"] in sections(text)


async def test_an_egg_has_no_favorite_snack_yet(bot: app.WispBot) -> None:
    await bot.lives.insert(GUILD_ID, new_egg(2, NOW))

    text = await lunchbox_text(bot, GUILD_ID)

    assert [SNACK, NONE_YET] in sections(text)


async def test_an_emoji_no_longer_uploaded_gives_way_to_the_next(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    await repo.record_expressions(GUILD_ID, ["wisp_gone", "wisp_gone", "wisp_happy"])
    give_emojis(bot, "wisp_happy")

    text = await lunchbox_text(bot, GUILD_ID)

    assert [EMOJI, f"║𝄡 {emoji_text('wisp_happy', 1)}"] in sections(text)


async def test_no_uploaded_emoji_shows_none_yet(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    await repo.record_expressions(GUILD_ID, ["wisp_gone"])

    text = await lunchbox_text(bot, GUILD_ID)

    assert [EMOJI, NONE_YET] in sections(text)


async def test_the_lunchbox_shows_the_newest_songs_only(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    days = [YESTERDAY - timedelta(days=offset) for offset in range(12)]
    for ident, day in enumerate(days, start=1):
        await fed(bot, viibr(ident), on(day))
        await repo.pick_favorite(GUILD_ID, day, random.Random(), NOW)

    songs = sections(await lunchbox_text(bot, GUILD_ID))[0][1:]

    assert len(songs) == 2 * rules.FAVORITE_SONGS_SHOWN
    assert songs[0].startswith("║𝄡𝄚𝄂 Oct 22 ・")
    assert songs[1].startswith("║𝄡 [listen ♪](https://viibrmusic.com/")
    assert len(await repo.favorites(GUILD_ID, 100)) == 12


async def test_a_long_lunchbox_drops_the_oldest_songs_to_fit(
    bot: app.WispBot, db: Database
) -> None:
    long_url = "https://viibrmusic.com/songs/" + "x" * 220
    for offset in range(rules.FAVORITE_SONGS_SHOWN):
        await db.execute(
            f"INSERT INTO {db.t('favorites')} "
            "(guild_id, day, user_id, track_key, url, picked_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                GUILD_ID,
                YESTERDAY - timedelta(days=offset),
                10**17 + offset,
                f"viibr:{offset}",
                long_url,
                NOW.replace(tzinfo=None),
            ),
        )

    text = await lunchbox_text(bot, GUILD_ID)

    assert text_length(text) <= MESSAGE_LIMIT
    songs = sections(text)[0][1:]
    assert 0 < len(songs) < 2 * rules.FAVORITE_SONGS_SHOWN
    assert len(songs) % 2 == 0
    assert songs[0].startswith("║𝄡𝄚𝄂 Oct 22 ・")
    assert songs[-1] == f"║𝄡 [listen ♪]({long_url})"
    assert [EMOJI, NONE_YET] in sections(text)
    assert_fits_its_box(text)


# ---
# Song links
# ---


async def test_a_songs_artist_is_asked_once_and_kept(
    bot: app.WispBot, repo: WispLunchboxRepo, songs: SongSite
) -> None:
    track = viibr(7)
    songs.artists[uuid_of(track)] = "Foggy X Music"
    await fed(bot, track, on(YESTERDAY))
    await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW)

    first = await lunchbox_text(bot, GUILD_ID)
    second = await lunchbox_text(bot, GUILD_ID)

    assert first == second
    assert f"║𝄡 [Foggy X Music]({track.url})" in first.splitlines()
    assert songs.asked == [uuid_of(track)]
    (favorite,) = await repo.favorites(GUILD_ID, 10)
    assert favorite.artist == "Foggy X Music"


async def test_a_song_page_with_no_artist_is_kept_as_none_known(
    bot: app.WispBot, repo: WispLunchboxRepo, songs: SongSite
) -> None:
    track = viibr(8)
    await fed(bot, track, on(YESTERDAY))
    await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW)

    await lunchbox_text(bot, GUILD_ID)
    text = await lunchbox_text(bot, GUILD_ID)

    assert f"║𝄡 [listen ♪]({track.url})" in text.splitlines()
    assert songs.asked == [uuid_of(track)]
    (favorite,) = await repo.favorites(GUILD_ID, 10)
    assert favorite.artist == ""


async def test_an_unreachable_site_reads_listen_and_is_asked_again(
    bot: app.WispBot, repo: WispLunchboxRepo
) -> None:
    gone = TestServer(web.Application())
    await gone.start_server()
    origin = str(gone.make_url("/"))
    await gone.close()
    await bot.share_links.close()
    bot.share_links = ShareLinkResolver(origins={"viibrmusic.com": origin})
    track = viibr(9)
    await fed(bot, track, on(YESTERDAY))
    await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW)

    text = await lunchbox_text(bot, GUILD_ID)

    assert f"║𝄡 [listen ♪]({track.url})" in text.splitlines()
    (favorite,) = await repo.favorites(GUILD_ID, 10)
    assert favorite.artist is None


async def test_a_busy_site_reads_listen_and_the_artist_is_asked_again(
    bot: app.WispBot, repo: WispLunchboxRepo, songs: SongSite
) -> None:
    track = viibr(10)
    songs.artists[uuid_of(track)] = "Foggy X Music"
    songs.busy.add(uuid_of(track))
    await fed(bot, track, on(YESTERDAY))
    await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW)

    busy = await lunchbox_text(bot, GUILD_ID)

    assert f"║𝄡 [listen ♪]({track.url})" in busy.splitlines()
    (favorite,) = await repo.favorites(GUILD_ID, 10)
    assert favorite.artist is None

    songs.busy.clear()
    back = await lunchbox_text(bot, GUILD_ID)

    assert f"║𝄡 [Foggy X Music]({track.url})" in back.splitlines()
    assert songs.asked == [uuid_of(track), uuid_of(track)]
    (favorite,) = await repo.favorites(GUILD_ID, 10)
    assert favorite.artist == "Foggy X Music"


async def test_an_artist_with_line_breaks_is_kept_and_shown_on_one_line(
    bot: app.WispBot, repo: WispLunchboxRepo, songs: SongSite
) -> None:
    track = viibr(11)
    songs.artists[uuid_of(track)] = "Foggy" + chr(10) + "  X" + chr(9) + "Music"
    await fed(bot, track, on(YESTERDAY))
    await repo.pick_favorite(GUILD_ID, YESTERDAY, random.Random(), NOW)

    text = await lunchbox_text(bot, GUILD_ID)

    assert f"║𝄡 [Foggy X Music]({track.url})" in text.splitlines()
    (favorite,) = await repo.favorites(GUILD_ID, 10)
    assert favorite.artist == "Foggy X Music"
    assert_fits_its_box(text)


def test_a_stored_artist_with_line_breaks_is_shown_on_one_line() -> None:
    url = viibr(1).url

    line = song_link("Foggy" + chr(10) + chr(10) + "X  Music", url)

    assert line == f"║𝄡 [Foggy X Music]({url})"
    assert song_link(chr(10) + " ", url) == f"║𝄡 [listen ♪]({url})"


def test_a_long_artist_is_shortened_to_fit_the_box() -> None:
    url = viibr(1).url

    line = song_link("The Extraordinarily Long Named Artist Collective", url)

    assert line.startswith("║𝄡 [The Extraordinarily")
    assert line.endswith(f"…]({url})")
    assert visual_width(line) <= box_room()
    assert "\n" not in line


def test_an_artists_markdown_is_escaped() -> None:
    url = viibr(1).url

    assert song_link("a_b*c [x]", url) == f"║𝄡 [a\\_b\\*c (x)]({url})"


def test_no_artist_reads_listen() -> None:
    assert song_link("", viibr(1).url) == f"║𝄡 [listen ♪]({viibr(1).url})"


async def test_the_fullest_lunchbox_stays_in_its_box(
    bot: app.WispBot, repo: WispLunchboxRepo, songs: SongSite
) -> None:
    days = [YESTERDAY - timedelta(days=offset) for offset in range(12)]
    for ident, day in enumerate(days, start=1):
        songs.artists[uuid_of(viibr(ident))] = "W" * 40
        await fed(bot, viibr(ident), on(day), user_id=10**17 + ident)
        await repo.pick_favorite(GUILD_ID, day, random.Random(), NOW)

    text = await lunchbox_text(bot, GUILD_ID)

    assert text_length(text) <= MESSAGE_LIMIT
    assert_fits_its_box(text)


async def test_a_banned_member_can_still_look(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.players.set_offense(GUILD_ID, FIRST, 3, None, True)

    interaction = await open_lunchbox(bot, server)

    (text,) = interaction.channel.send.await_args.args
    assert text.startswith(TITLE)


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
