"""Tests for the feeding pipeline and Wisp's House announcements.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from discord import app_commands

import app
from cogs import announce, feeding, groups
from cogs.announce import post_events
from cogs.feeding import Feeding
from cogs.share_links import ShareLinkResolver
from cogs.studio import rules_text
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.life import Event, EventKind, Life, Phase, new_egg
from wisp.links import ShareLink, Track, TrackKind
from wisp.rules import Stage

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
TRACKS_ID = 30
MEALTIME_ID = 50
RULES_ID = 51
RULES_MESSAGE_ID = 52
QUALIFYING_ROLE = 7
OTHER_ROLE = 8
FIRST_USER = 1
SECOND_USER = 2

VIIBR_URL = "https://viibrmusic.com/songs/11111111-1111-1111-1111-111111111111"
VIIBR_URL_2 = "https://viibrmusic.com/songs/22222222-2222-2222-2222-222222222222"
SUNO_URL = "https://suno.com/song/33333333-3333-3333-3333-333333333333"


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
        self.rules_edit: Any = AsyncMock()
        self.rules = MagicMock(spec=discord.Thread)
        self.rules.id = RULES_ID
        self.rules.parent_id = FORUM_ID
        self.rules.archived = False
        self.rules.get_partial_message.return_value = MagicMock(
            spec=discord.PartialMessage, edit=self.rules_edit
        )
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.channels: dict[int, MagicMock] = {HOUSE_ID: self.house}
        self.guild.get_channel_or_thread.side_effect = self.channels.get

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        threads = {MEALTIME_ID: self.mealtime, RULES_ID: self.rules}
        if channel_id not in threads:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return threads[channel_id]


def make_member(user_id: int = FIRST_USER, role_id: int = QUALIFYING_ROLE) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = False
    member.roles = [role]
    member.display_name = f"Member{user_id}"
    member.mention = f"<@{user_id}>"
    return member


def make_channel(channel_id: int = TRACKS_ID) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    return channel


def make_thread(parent_id: int, thread_id: int = 999) -> MagicMock:
    thread = MagicMock(spec=discord.Thread)
    thread.id = thread_id
    thread.parent_id = parent_id
    return thread


class MessageFactory:
    """Builds fake messages with increasing ids in the fake guild."""

    def __init__(self, guild: MagicMock) -> None:
        self._guild = guild
        self._next_id = 5000

    def __call__(
        self,
        content: str,
        *,
        author: MagicMock | None = None,
        channel: MagicMock | None = None,
    ) -> MagicMock:
        self._next_id += 1
        message = MagicMock(spec=discord.Message)
        message.id = self._next_id
        message.guild = self._guild
        message.author = author if author is not None else make_member()
        message.channel = channel if channel is not None else make_channel()
        message.content = content
        return message


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
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture
def cog(bot: app.WispBot) -> Feeding:
    return Feeding(bot)


@pytest.fixture
def message(server: FakeServer) -> MessageFactory:
    return MessageFactory(server.guild)


async def configure(
    bot: app.WispBot, *, roles: tuple[int, ...] = (QUALIFYING_ROLE,)
) -> None:
    await bot.settings.update(
        GUILD_ID,
        tracks_channel_id=TRACKS_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        mealtime_thread_id=MEALTIME_ID,
    )
    for role_id in roles:
        await bot.settings.add_role(GUILD_ID, role_id)


async def activate(bot: app.WispBot, user_id: int = FIRST_USER) -> None:
    await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())


async def start_life(
    bot: app.WispBot,
    *,
    phase: Phase = Phase.ALIVE,
    care: float = 50.0,
    egg_food: int = 0,
) -> Life:
    now = discord.utils.utcnow()
    life = new_egg(1, now)
    life.phase = phase
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.BABY
        life.hatched_at = life.stage_started_at = now
    life.care = care
    life.egg_food = egg_food
    return await bot.lives.insert(GUILD_ID, life)


@pytest.fixture
async def ready(bot: app.WispBot) -> Life:
    """A configured guild with a living Wisp and one activated member."""
    await configure(bot)
    await activate(bot)
    return await start_life(bot)


def sends_without_pinging(kwargs: dict[str, Any]) -> bool:
    """Whether a send used AllowedMentions.none() and nothing else but a file."""
    mentions = kwargs["allowed_mentions"]
    return set(kwargs) <= {"allowed_mentions", "file"} and (
        mentions.to_dict() == discord.AllowedMentions.none().to_dict()
    )


def mentions_version(text: str, version: int) -> bool:
    return re.search(rf"(?<!\d){version}(?!\d)", text) is not None


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


async def assert_untouched(bot: app.WispBot, server: FakeServer) -> None:
    """Nothing was fed, recorded or posted."""
    life = await current_life(bot)
    assert life.care == 50.0
    assert life.egg_food == 0
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert (player.lifetime_points, player.bond) == (0, 0)
    now = discord.utils.utcnow()
    assert await bot.activity_log.meal_points_today(GUILD_ID, FIRST_USER, now) == 0
    server.mealtime.send.assert_not_awaited()
    server.house.send.assert_not_awaited()


# ---
# Feeding
# ---


async def test_viibr_track_feeds_five_and_forwards(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    post = message(f"new one {VIIBR_URL}")

    await cog.on_message(post)

    life = await current_life(bot)
    assert life.care == 55.0
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert player.lifetime_points == 5
    assert player.balance == 5
    assert player.bond == rules.BOND_PER_VIIBR_TRACK
    now = discord.utils.utcnow()
    assert await bot.activity_log.meal_points_today(GUILD_ID, FIRST_USER, now) == 5

    server.mealtime.send.assert_awaited_once()
    (text,) = server.mealtime.send.await_args.args
    first, second = text.split("\n")
    assert first == f"♪ <@{FIRST_USER}> fed Wisp ・ {VIIBR_URL}"
    assert second and not second.startswith("♪")
    assert sends_without_pinging(server.mealtime.send.await_args.kwargs)
    assert post.method_calls == []
    server.house.send.assert_not_awaited()


async def test_forward_line_uses_chosen_name_and_hangry_mood(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await configure(bot)
    await activate(bot)
    await bot.players.set_name(GUILD_ID, FIRST_USER, "Sparkle")
    await start_life(bot, care=5.0)
    emojis = {"wisp_hangry": "<:wisp_hangry:1>", "wisp_happy": "<:wisp_happy:2>"}
    monkeypatch.setattr(bot, "emoji", lambda name: emojis[name])
    picked: list[tuple[Any, ...]] = []

    def pick(moment: Any, mood: Any, **fields: str) -> str:
        picked.append((moment, mood, fields))
        return "line"

    monkeypatch.setattr(bot.lines, "pick", pick)

    await cog.on_message(message(SUNO_URL))

    assert [(m.value, mood.value, f) for m, mood, f in picked] == [
        ("track_fed", "hangry", {"name": "Sparkle"})
    ]
    (text,) = server.mealtime.send.await_args.args
    assert text.split("\n")[1] == "<:wisp_hangry:1> line"


async def test_happy_mood_gets_the_happy_emoji(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bot, "emoji", lambda name: {"wisp_happy": "<:wisp_happy:2>"}.get(name, "")
    )

    await cog.on_message(message(SUNO_URL))

    (text,) = server.mealtime.send.await_args.args
    assert text.split("\n")[1].startswith("<:wisp_happy:2> ")


async def test_suno_track_feeds_one_no_bond(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await cog.on_message(message(SUNO_URL))

    assert (await current_life(bot)).care == 51.0
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert (player.lifetime_points, player.bond) == (1, 0)
    server.mealtime.send.assert_awaited_once()


async def test_staff_food_values_set_what_each_track_feeds(
    cog: Feeding,
    bot: app.WispBot,
    message: MessageFactory,
    ready: Life,
) -> None:
    await bot.settings.update(GUILD_ID, viibr_meal_points=12)

    await cog.on_message(message(VIIBR_URL))
    await cog.on_message(message(SUNO_URL))

    assert (await current_life(bot)).care == 50.0 + 12 + rules.MEAL_POINTS[
        TrackKind.SUNO
    ]
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert player.lifetime_points == 12 + rules.MEAL_POINTS[TrackKind.SUNO]


async def test_unset_food_values_use_the_rules(
    cog: Feeding,
    bot: app.WispBot,
    message: MessageFactory,
    ready: Life,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rules, "MEAL_POINTS", {TrackKind.VIIBR: 7, TrackKind.SUNO: 2})
    await bot.settings.update(GUILD_ID, suno_meal_points=3)

    await cog.on_message(message(VIIBR_URL))
    await cog.on_message(message(SUNO_URL))

    assert (await current_life(bot)).care == 50.0 + 7 + 3


def make_staff_interaction(bot: app.WispBot) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild_id = GUILD_ID
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def test_food_command_saves_the_values_and_updates_the_rules_post(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await bot.settings.update(
        GUILD_ID, rules_thread_id=RULES_ID, rules_message_id=RULES_MESSAGE_ID
    )
    interaction = make_staff_interaction(bot)
    command: Any = feeding.set_food

    await command.callback(interaction, 12, 1)

    settings = await bot.settings.get(GUILD_ID)
    assert (settings.viibr_meal_points, settings.suno_meal_points) == (12, 1)
    server.rules.get_partial_message.assert_called_once_with(RULES_MESSAGE_ID)
    expected = rules_text({TrackKind.VIIBR: 12, TrackKind.SUNO: 1})
    assert server.rules_edit.await_args.kwargs["content"] == expected
    interaction.followup.send.assert_awaited_once_with(
        "♪ Food values: viibrmusic.com track 12 meal points, "
        "Suno track 1 meal point.",
        ephemeral=True,
    )
    server.house.send.assert_not_awaited()


def test_food_command_takes_two_staff_values_from_zero_to_the_maximum() -> None:
    command = groups.wispadmin.get_command("food")
    assert isinstance(command, app_commands.Command)
    params = {parameter.name: parameter for parameter in command.parameters}
    assert list(params) == ["viibr", "suno"]
    for parameter in params.values():
        assert (parameter.min_value, parameter.max_value) == (
            0,
            rules.MEAL_POINTS_MAX,
        )
    assert command.checks


async def test_unqualified_role_is_silent(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await cog.on_message(message(VIIBR_URL, author=make_member(role_id=OTHER_ROLE)))

    await assert_untouched(bot, server)


async def test_no_roles_configured_is_silent(
    cog: Feeding, bot: app.WispBot, server: FakeServer, message: MessageFactory
) -> None:
    await configure(bot, roles=())
    await activate(bot)
    await start_life(bot)

    await cog.on_message(message(VIIBR_URL))

    await assert_untouched(bot, server)


async def test_not_activated_is_silent(
    cog: Feeding, bot: app.WispBot, server: FakeServer, message: MessageFactory
) -> None:
    await configure(bot)
    await start_life(bot)

    await cog.on_message(message(VIIBR_URL))

    await assert_untouched(bot, server)


@pytest.mark.parametrize("offense", ["forever", "future"])
async def test_banned_is_silent(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
    offense: str,
) -> None:
    until = discord.utils.utcnow() + timedelta(hours=1)
    await bot.players.set_offense(
        GUILD_ID,
        FIRST_USER,
        1,
        until if offense == "future" else None,
        offense == "forever",
    )

    await cog.on_message(message(VIIBR_URL))

    await assert_untouched(bot, server)


async def test_ban_landing_after_the_first_check_stops_the_feed(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_player = bot.players.get
    reads = 0

    async def get_then_ban(guild_id: int, user_id: int) -> Any:
        nonlocal reads
        player = await read_player(guild_id, user_id)
        reads += 1
        if reads == 1:
            await bot.players.set_offense(guild_id, user_id, 1, None, True)
        return player

    monkeypatch.setattr(bot.players, "get", get_then_ban)

    await cog.on_message(message(VIIBR_URL))

    monkeypatch.setattr(bot.players, "get", read_player)
    await assert_untouched(bot, server)


async def test_expired_ban_feeds_again(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    past = discord.utils.utcnow() - timedelta(hours=1)
    await bot.players.set_offense(GUILD_ID, FIRST_USER, 1, past, False)

    await cog.on_message(message(VIIBR_URL))

    assert (await current_life(bot)).care == 55.0


async def test_duplicate_track_is_silent(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await cog.on_message(message(VIIBR_URL))
    await cog.on_message(message(f"again {VIIBR_URL}"))

    assert (await current_life(bot)).care == 55.0
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert (player.lifetime_points, player.bond) == (5, 10)
    server.mealtime.send.assert_awaited_once()


# ---
# viibrmusic.com share links
# ---

SHARE_CODE = "bDBmywB5"
SHARE_URL = f"https://viibrmusic.com/s/{SHARE_CODE}"


@pytest.fixture
async def viibr_site(bot: app.WispBot) -> AsyncIterator[list[str]]:
    """A local viibrmusic.com whose share link names VIIBR_URL's song.

    It yields the paths it was asked for.
    """
    asked: list[str] = []

    async def share(request: web.Request) -> web.Response:
        asked.append(request.path)
        if request.match_info["code"] != SHARE_CODE:
            return web.Response(status=404)
        return web.Response(status=307, headers={"Location": VIIBR_URL})

    site = web.Application()
    site.router.add_get("/s/{code}", share)
    server = TestServer(site)
    await server.start_server()
    bot.share_links = ShareLinkResolver(
        origins={"viibrmusic.com": str(server.make_url("/"))}
    )
    try:
        yield asked
    finally:
        await bot.share_links.close()
        await server.close()


async def test_a_share_link_feeds_wisp_once_as_its_song(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
    viibr_site: list[str],
) -> None:
    await cog.on_message(message(f"new one {SHARE_URL}"))
    await cog.on_message(message(f"same song {VIIBR_URL}"))

    assert viibr_site == [f"/s/{SHARE_CODE}"]
    assert (await current_life(bot)).care == 55.0
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert (player.lifetime_points, player.bond) == (5, 10)
    server.mealtime.send.assert_awaited_once()
    (forwarded,) = server.mealtime.send.await_args.args
    assert SHARE_URL in forwarded
    assert VIIBR_URL not in forwarded
    server.house.send.assert_not_awaited()


async def test_a_share_link_for_no_song_is_silent(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
    viibr_site: list[str],
) -> None:
    await cog.on_message(message("https://viibrmusic.com/s/zzzzzzzz"))

    assert viibr_site == ["/s/zzzzzzzz"]
    await assert_untouched(bot, server)


async def test_a_share_link_is_not_checked_for_a_member_who_cannot_feed(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
    viibr_site: list[str],
) -> None:
    await cog.on_message(message(SHARE_URL, author=make_member(role_id=OTHER_ROLE)))
    await cog.on_message(message(SHARE_URL, channel=make_channel(TRACKS_ID + 1)))

    assert viibr_site == []
    await assert_untouched(bot, server)


async def test_a_share_link_is_resolved_outside_the_guild_lock(
    cog: Feeding,
    bot: app.WispBot,
    message: MessageFactory,
    ready: Life,
    viibr_site: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held: list[bool] = []
    resolve = bot.share_links.resolve

    async def resolve_and_check(link: ShareLink) -> Track | None:
        held.append(bot.guild_lock(GUILD_ID).locked())
        return await resolve(link)

    monkeypatch.setattr(bot.share_links, "resolve", resolve_and_check)

    await cog.on_message(message(SHARE_URL))

    assert held == [False]
    assert (await current_life(bot)).care == 55.0


async def test_an_unreachable_viibr_site_is_reported_in_the_house_and_not_fed(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    gone = TestServer(web.Application())
    await gone.start_server()
    origin = str(gone.make_url("/"))
    await gone.close()
    bot.share_links = ShareLinkResolver(origins={"viibrmusic.com": origin})
    post = message(SHARE_URL)

    try:
        await cog.on_message(post)
    finally:
        await bot.share_links.close()

    (report,) = [call.args[0] for call in server.house.send.await_args_list]
    assert report.startswith(
        "Error in checking a viibrmusic.com share link: ClientConnectorError"
    )
    post.channel.send.assert_not_called()
    server.mealtime.send.assert_not_awaited()
    assert (await current_life(bot)).care == 50.0
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert (player.lifetime_points, player.bond) == (0, 0)


async def test_daily_cap_clamps_then_silences(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    now = discord.utils.utcnow()
    life_id = ready.id
    assert life_id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID, life_id, FIRST_USER, InteractionKind.FEED, 0, 12, now
    )

    await cog.on_message(message(VIIBR_URL))
    await cog.on_message(message(VIIBR_URL_2))

    assert (await current_life(bot)).care == 53.0
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert player.lifetime_points == 3
    assert await bot.activity_log.meal_points_today(GUILD_ID, FIRST_USER, now) == 15
    server.mealtime.send.assert_awaited_once()


async def test_one_feed_per_message(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await cog.on_message(message(f"{SUNO_URL} and {VIIBR_URL}"))

    assert (await current_life(bot)).care == 51.0
    server.mealtime.send.assert_awaited_once()
    (text,) = server.mealtime.send.await_args.args
    assert SUNO_URL in text
    assert VIIBR_URL not in text


async def test_post_in_tracks_forum_thread_counts(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await cog.on_message(message(VIIBR_URL, channel=make_thread(parent_id=TRACKS_ID)))

    assert (await current_life(bot)).care == 55.0
    server.mealtime.send.assert_awaited_once()


@pytest.mark.parametrize(
    "channel",
    [make_channel(999), make_thread(parent_id=999)],
    ids=["other-channel", "thread-of-other-channel"],
)
async def test_other_channels_ignored(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
    channel: MagicMock,
) -> None:
    await cog.on_message(message(VIIBR_URL, channel=channel))

    await assert_untouched(bot, server)


async def test_simultaneous_feeds_both_count(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await activate(bot, SECOND_USER)

    await asyncio.gather(
        cog.on_message(message(VIIBR_URL, author=make_member(FIRST_USER))),
        cog.on_message(message(VIIBR_URL_2, author=make_member(SECOND_USER))),
    )

    assert (await current_life(bot)).care == 60.0
    assert server.mealtime.send.await_count == 2
    for user_id in (FIRST_USER, SECOND_USER):
        assert (await bot.players.get(GUILD_ID, user_id)).lifetime_points == 5


async def test_egg_feed_that_completes_starts_hatching_event(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
) -> None:
    await configure(bot)
    await activate(bot)
    await start_life(bot, phase=Phase.EGG, care=0.0, egg_food=rules.EGG_FOOD_NEEDED - 5)

    await cog.on_message(message(VIIBR_URL))

    life = await current_life(bot)
    assert life.phase is Phase.HATCHING
    assert life.hatched_by == FIRST_USER
    server.house.send.assert_awaited_once()
    (text,) = server.house.send.await_args.args
    assert mentions_version(text, 1)
    assert sends_without_pinging(server.house.send.await_args.kwargs)
    server.mealtime.send.assert_awaited_once()


async def test_no_life_is_ignored_and_key_not_recorded(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
) -> None:
    await configure(bot)
    await activate(bot)

    await cog.on_message(message(VIIBR_URL))

    server.mealtime.send.assert_not_awaited()
    life = await start_life(bot)
    assert life.id is not None
    track = Track(TrackKind.VIIBR, VIIBR_URL.rsplit("/", 1)[1], VIIBR_URL)
    recorded = await bot.activity_log.record_feed(
        GUILD_ID, life.id, FIRST_USER, track, 5, 1, discord.utils.utcnow()
    )
    assert recorded is True


async def test_bot_authors_and_direct_messages_are_ignored(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    robot = make_member()
    robot.bot = True
    direct = message(VIIBR_URL)
    direct.guild = None

    await cog.on_message(message(VIIBR_URL, author=robot))
    await cog.on_message(direct)

    await assert_untouched(bot, server)


async def test_message_without_a_track_is_silent(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await cog.on_message(message("just chatting https://example.com/song"))

    await assert_untouched(bot, server)


async def test_chat_without_a_track_reads_no_settings(
    cog: Feeding,
    bot: app.WispBot,
    message: MessageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get = AsyncMock()
    monkeypatch.setattr(bot.settings, "get", get)

    await cog.on_message(message("just chatting"))

    get.assert_not_awaited()


async def test_finished_life_is_not_fed(
    cog: Feeding, bot: app.WispBot, server: FakeServer, message: MessageFactory
) -> None:
    await configure(bot)
    await activate(bot)
    await start_life(bot, phase=Phase.DEAD)

    await cog.on_message(message(VIIBR_URL))

    server.mealtime.send.assert_not_awaited()
    now = discord.utils.utcnow()
    assert await bot.activity_log.meal_points_today(GUILD_ID, FIRST_USER, now) == 0


async def test_failed_forward_is_posted_in_mealtime_and_keeps_the_feed(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    server.mealtime.send.side_effect = [
        discord.HTTPException(MagicMock(status=400), "Invalid Form Body"),
        None,
    ]

    await cog.on_message(message(VIIBR_URL))

    assert (await current_life(bot)).care == 55.0
    assert server.mealtime.send.await_count == 2
    report = server.mealtime.send.await_args
    assert report.args[0].startswith(
        "Error in forwarding a track to Mealtime: HTTPException"
    )
    assert sends_without_pinging(report.kwargs)
    server.house.send.assert_not_awaited()


async def test_forward_failure_goes_to_the_house_when_mealtime_cannot_be_posted_to(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    server.mealtime.send.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Access"
    )

    await cog.on_message(message(VIIBR_URL))

    assert (await current_life(bot)).care == 55.0
    assert server.mealtime.send.await_count == 2
    server.house.send.assert_awaited_once()
    (report,) = server.house.send.await_args.args
    assert report.startswith("Error in forwarding a track to Mealtime: Forbidden")
    assert sends_without_pinging(server.house.send.await_args.kwargs)


async def test_forward_failure_without_a_mealtime_thread_goes_to_the_house(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await bot.settings.update(GUILD_ID, studio_forum_id=None)

    await cog.on_message(message(VIIBR_URL))

    server.mealtime.send.assert_not_awaited()
    (report,) = server.house.send.await_args.args
    assert report.startswith("Error in forwarding a track to Mealtime: StudioError")


@pytest.mark.parametrize("in_thread", [False, True])
async def test_a_listener_error_in_the_track_drop_is_posted_in_the_house(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
    monkeypatch: pytest.MonkeyPatch,
    in_thread: bool,
) -> None:
    channel = make_thread(TRACKS_ID) if in_thread else make_channel()
    channel.send = AsyncMock()
    post = message(VIIBR_URL, channel=channel)
    monkeypatch.setattr(
        bot.lives, "current", AsyncMock(side_effect=RuntimeError("bug"))
    )

    try:
        await cog.on_message(post)
    except RuntimeError:
        await bot.on_error("on_message", post)

    channel.send.assert_not_awaited()
    server.house.send.assert_awaited_once()
    assert server.house.send.await_args.args == (
        "Error in on_message: RuntimeError: bug",
    )


# ---
# Meeting Wisp
# ---


async def test_third_day_of_feeding_introduces_him_after_the_posts(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    assert ready.id is not None
    now = discord.utils.utcnow()
    for days in (2, 1):
        await bot.activity_log.record_interaction(
            GUILD_ID,
            ready.id,
            FIRST_USER,
            InteractionKind.PLAY,
            0,
            0,
            now - timedelta(days=days),
        )
    order: list[str] = []
    server.mealtime.send.side_effect = lambda *a, **k: order.append("mealtime")
    server.house.send.side_effect = lambda *a, **k: order.append("house")

    await cog.on_message(message(VIIBR_URL))

    assert order == ["mealtime", "house"]
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert player.met_at is not None
    assert (await current_life(bot)).growth == rules.GROWTH_PER_BOND_MOMENT
    (button,) = server.house.send.await_args.kwargs["view"].children
    assert button.item.custom_id == f"wisp:name:{FIRST_USER}"


async def test_first_day_of_feeding_does_not_introduce_him(
    cog: Feeding,
    bot: app.WispBot,
    server: FakeServer,
    message: MessageFactory,
    ready: Life,
) -> None:
    await cog.on_message(message(VIIBR_URL))

    server.house.send.assert_not_awaited()
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).met_at is None


# ---
# Announcements
# ---


@pytest.fixture
def assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(announce, "ASSETS_DIR", tmp_path)
    return tmp_path


def add_image(assets: Path, folder: str, name: str) -> None:
    target = assets / folder / f"{name}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"png")


async def test_stage_up_posts_line_with_stage_image(
    bot: app.WispBot, server: FakeServer, ready: Life, assets: Path
) -> None:
    await configure(bot)
    add_image(assets, "stages", "child")

    await post_events(bot, GUILD_ID, [Event(EventKind.STAGE_UP, Stage.CHILD)])

    server.house.send.assert_awaited_once()
    (text,) = server.house.send.await_args.args
    assert "child" in text
    kwargs = server.house.send.await_args.kwargs
    assert sends_without_pinging(kwargs)
    assert kwargs["file"].filename == "child.png"


async def test_missing_image_means_text_only(
    bot: app.WispBot, server: FakeServer, ready: Life, assets: Path
) -> None:
    await configure(bot)

    await post_events(bot, GUILD_ID, [Event(EventKind.STAGE_UP, Stage.TEEN)])

    assert "file" not in server.house.send.await_args.kwargs
    assert sends_without_pinging(server.house.send.await_args.kwargs)


@pytest.mark.parametrize(
    ("folder", "name", "event"),
    [
        ("stages", "baby", Event(EventKind.HATCHED)),
        ("events", "hatched", Event(EventKind.HATCHED)),
    ],
)
async def test_hatched_image_falls_back_between_folders(
    bot: app.WispBot,
    server: FakeServer,
    ready: Life,
    assets: Path,
    folder: str,
    name: str,
    event: Event,
) -> None:
    await configure(bot)
    add_image(assets, folder, name)

    await post_events(bot, GUILD_ID, [event])

    assert server.house.send.await_args.kwargs["file"].filename == f"{name}.png"


async def test_death_announces_and_lays_the_next_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await configure(bot)
    add_image(assets, "events", "died")
    life = await start_life(bot, phase=Phase.DEAD, care=0.0)
    assert life.version == 1

    await post_events(bot, GUILD_ID, [Event(EventKind.DIED)])

    egg = await current_life(bot)
    assert (egg.version, egg.phase) == (2, Phase.EGG)
    assert server.house.send.await_count == 2
    died, new_egg_post = server.house.send.await_args_list
    assert died.kwargs["file"].filename == "died.png"
    assert mentions_version(died.args[0], 1)
    assert mentions_version(new_egg_post.args[0], 2)
    assert sends_without_pinging(new_egg_post.kwargs)
    assert "file" not in new_egg_post.kwargs


async def test_cold_egg_lays_the_next_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await configure(bot)
    await start_life(bot, phase=Phase.COLD, care=0.0)

    await post_events(bot, GUILD_ID, [Event(EventKind.EGG_COLD)])

    assert (await current_life(bot)).version == 2
    assert server.house.send.await_count == 2


async def test_repeated_death_event_lays_only_one_egg(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await configure(bot)
    await start_life(bot, phase=Phase.DEAD, care=0.0)

    await post_events(bot, GUILD_ID, [Event(EventKind.DIED)])
    await post_events(bot, GUILD_ID, [Event(EventKind.DIED)])

    assert (await current_life(bot)).version == 2


@pytest.mark.parametrize("kind", [EventKind.DIED, EventKind.EGG_COLD])
async def test_stale_ending_is_not_announced(
    bot: app.WispBot, server: FakeServer, ready: Life, assets: Path, kind: EventKind
) -> None:
    await configure(bot)

    await post_events(bot, GUILD_ID, [Event(kind)])

    server.house.send.assert_not_awaited()
    assert (await current_life(bot)).version == 1


async def test_missing_house_channel_is_logged_once_and_egg_still_laid(
    bot: app.WispBot,
    server: FakeServer,
    assets: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await configure(bot)
    await bot.settings.update(GUILD_ID, house_channel_id=None)
    await start_life(bot, phase=Phase.DEAD, care=0.0)

    with caplog.at_level(logging.ERROR, logger="wisp"):
        await post_events(bot, GUILD_ID, [Event(EventKind.DIED)])

    assert (await current_life(bot)).version == 2
    server.house.send.assert_not_awaited()
    assert caplog.text.count("Error in posting to Wisp's House") == 1


async def test_failed_house_post_is_reported_and_egg_still_laid(
    bot: app.WispBot, server: FakeServer, assets: Path
) -> None:
    await configure(bot)
    await start_life(bot, phase=Phase.DEAD, care=0.0)
    server.house.send.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Access"
    )

    await post_events(bot, GUILD_ID, [Event(EventKind.DIED)])

    assert (await current_life(bot)).version == 2
    assert server.house.send.await_count == 4
    (report,) = server.house.send.await_args_list[1].args
    assert report.startswith("Error in posting to Wisp's House: Forbidden")


async def test_no_events_posts_nothing(
    bot: app.WispBot, server: FakeServer, ready: Life
) -> None:
    await configure(bot)

    await post_events(bot, GUILD_ID, [])

    server.house.send.assert_not_awaited()
