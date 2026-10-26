"""Tests for the life loop and the live status card.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
import random
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest

import app
from cogs import announce, life_loop, pictures
from cogs.conversation import PokeButton
from cogs.life_loop import LifeLoop
from cogs.snacks import FeedButton
from cogs.studio import HOUSE_PANEL
from db.activity import ActivityRepo, InteractionKind
from db.badges import BadgeRepo
from db.database import Database
from db.keepsakes import KeepsakeRepo
from db.lives import LifeRepo
from db.lunchbox import WispLunchboxRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.bond import happiness
from wisp.card import bar, render_status
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.links import Track, TrackKind
from wisp.rules import PAID_SNACKS, SNACKS, Stage

GUILD_ID = 100
BADGE_ROLE_ID = 4242
FORUM_ID = 10
HOUSE_ID = 20
STATUS_ID = 60
VAULT_ID = 61
FREE_SNACK_SEED = 2
MEALTIME_ID = 62
CARD_ID = 777
VAULT_MESSAGE_ID = 778
REPOSTED_CARD_ID = 888
PANEL_ID = 999
USER_ID = 1
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
FULL_GAP = rules.MAX_CREDITED_GAP

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House and the Status and Vault threads."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.card = MagicMock(spec=discord.Message)
        self.card.id = REPOSTED_CARD_ID
        self.card.pin = AsyncMock()
        self.card_edit: Any = AsyncMock()
        self.status = MagicMock(spec=discord.Thread)
        self.status.id = STATUS_ID
        self.status.parent_id = FORUM_ID
        self.status.archived = False
        self.status.send = AsyncMock(return_value=self.card)
        self.partial = MagicMock(spec=discord.PartialMessage)
        self.partial.edit = self.card_edit
        self.status.get_partial_message.return_value = self.partial
        self.vault_edit: Any = AsyncMock()
        self.vault = MagicMock(spec=discord.Thread)
        self.vault.id = VAULT_ID
        self.vault.parent_id = FORUM_ID
        self.vault.archived = False
        self.vault.send = AsyncMock()
        self.vault.get_partial_message.return_value = MagicMock(
            spec=discord.PartialMessage, edit=self.vault_edit
        )
        self.mealtime = MagicMock(spec=discord.Thread)
        self.mealtime.id = MEALTIME_ID
        self.mealtime.parent_id = FORUM_ID
        self.mealtime.archived = False
        self.mealtime.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house}
        self.guild.get_channel_or_thread.side_effect = channels.get
        self.guild.get_member.return_value = None

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        threads = {
            STATUS_ID: self.status,
            VAULT_ID: self.vault,
            MEALTIME_ID: self.mealtime,
        }
        if channel_id not in threads:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return threads[channel_id]


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


def house_reports(server: FakeServer) -> list[str]:
    """The error lines posted in Wisp's House."""
    lines = [str(call.args[0]) for call in server.house.send.await_args_list]
    return [line for line in lines if line.startswith("Error in ")]


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
    wisp_bot.wisp_lunchbox = WispLunchboxRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture
def cog(bot: app.WispBot) -> LifeLoop:
    return LifeLoop(bot)


async def configure(bot: app.WispBot, *, frozen: bool = False) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        status_thread_id=STATUS_ID,
        status_message_id=CARD_ID,
        vault_thread_id=VAULT_ID,
        vault_message_id=VAULT_MESSAGE_ID,
        mealtime_thread_id=MEALTIME_ID,
        frozen=frozen,
    )


async def lay(
    bot: app.WispBot,
    *,
    phase: Phase = Phase.ALIVE,
    full: float = 50.0,
    version: int = 1,
    gap: timedelta = FULL_GAP,
    phase_seconds: float = 0.0,
    stage: Stage = Stage.BABY,
) -> Life:
    """Insert a life whose last tick was `gap` before NOW."""
    life = new_egg(version, NOW - gap)
    life.phase = phase
    life.full = full
    life.phase_seconds = phase_seconds
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = stage
        life.hatched_at = life.stage_started_at = NOW - timedelta(hours=1)
    return await bot.lives.insert(GUILD_ID, life)


async def interact(
    bot: app.WispBot,
    life: Life,
    at: datetime,
    kind: InteractionKind = InteractionKind.PLAY,
    user_id: int = USER_ID,
) -> None:
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID, life.id, user_id, kind, 0, 0, at
    )


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


def house_texts(server: FakeServer) -> list[str]:
    return [call.args[0] for call in server.house.send.await_args_list]


def mentions_version(text: str, version: int) -> bool:
    return re.search(rf"(?<!\d){version}(?!\d)", text) is not None


# ---
# First run
# ---


async def test_first_run_lays_egg_v1(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase, egg.last_tick_at) == (1, Phase.EGG, NOW)
    server.house.send.assert_awaited_once()
    assert mentions_version(house_texts(server)[0], 1)
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    content = server.card_edit.await_args.kwargs["content"]
    assert content.startswith("♪ WISP v1 ・ EGG")


async def test_unconfigured_guilds_are_skipped_silently(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.update(GUILD_ID + 1, status_thread_id=STATUS_ID)

    await cog.run_tick(NOW)

    assert await bot.lives.current(GUILD_ID) is None
    assert await bot.lives.current(GUILD_ID + 1) is None
    server.house.send.assert_not_awaited()
    server.status.send.assert_not_awaited()


# ---
# Wisp's lunchbox
# ---


def viibr_track(ident: int) -> Track:
    uuid = f"00000000-0000-0000-0000-{ident:012d}"
    return Track(
        TrackKind.VIIBR, f"viibr:{uuid}", f"https://viibrmusic.com/songs/{uuid}"
    )


@pytest.mark.parametrize("seed", [1, 2, 3])
async def test_hatching_picks_his_favorite_snack_with_the_cogs_rng(
    cog: LifeLoop, bot: app.WispBot, seed: int
) -> None:
    await configure(bot)
    await lay(
        bot, phase=Phase.HATCHING, phase_seconds=rules.HATCHING_TIME.total_seconds()
    )
    cog.rng = random.Random(seed)

    await cog.run_tick(NOW)

    life = await current_life(bot)
    assert life.phase is Phase.ALIVE
    assert life.favorite_snack == random.Random(seed).choice(PAID_SNACKS).key


async def test_his_favorite_snack_is_never_the_free_one(
    cog: LifeLoop, bot: app.WispBot
) -> None:
    await configure(bot)
    await lay(
        bot, phase=Phase.HATCHING, phase_seconds=rules.HATCHING_TIME.total_seconds()
    )
    cog.rng = random.Random(FREE_SNACK_SEED)

    await cog.run_tick(NOW)

    favorite = (await current_life(bot)).favorite_snack
    assert random.Random(FREE_SNACK_SEED).choice(SNACKS).key == "sinewave"
    assert favorite == random.Random(FREE_SNACK_SEED).choice(PAID_SNACKS).key
    assert all(snack.cost > 0 for snack in PAID_SNACKS)


async def test_only_hatching_picks_a_favorite_snack(
    cog: LifeLoop, bot: app.WispBot
) -> None:
    await configure(bot)
    await lay(bot, phase=Phase.HATCHING)

    await cog.run_tick(NOW)

    assert (await current_life(bot)).favorite_snack is None


async def test_a_living_wisp_keeps_his_favorite_snack(
    cog: LifeLoop, bot: app.WispBot
) -> None:
    await configure(bot)
    life = await lay(bot)
    life.favorite_snack = "cheese"
    await bot.lives.save(GUILD_ID, life)

    await cog.run_tick(NOW)

    assert (await current_life(bot)).favorite_snack == "cheese"


async def test_the_tick_picks_yesterdays_favorite_song_once(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    assert life.id is not None
    track = viibr_track(1)
    await bot.activity_log.record_feed(
        GUILD_ID, life.id, USER_ID, track, 5, 9, NOW - timedelta(days=1)
    )

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + rules.TICK_EVERY)
    await LifeLoop(bot).run_tick(NOW + 2 * rules.TICK_EVERY)

    server.mealtime.send.assert_awaited_once()
    (text,) = server.mealtime.send.await_args.args
    assert text.startswith(f"♪ Wisp put <@{USER_ID}>'s track in his lunchbox ・ ")
    assert track.url in text
    (favorite,) = await bot.wisp_lunchbox.favorites(GUILD_ID, 10)
    assert favorite.url == track.url


async def test_an_unconfigured_guild_picks_no_favorite_song(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(
        GUILD_ID, house_channel_id=HOUSE_ID, mealtime_thread_id=MEALTIME_ID
    )
    await bot.activity_log.record_feed(
        GUILD_ID, 1, USER_ID, viibr_track(1), 5, 9, NOW - timedelta(days=1)
    )

    await cog.run_tick(NOW)

    assert await bot.wisp_lunchbox.favorites(GUILD_ID, 10) == []
    server.mealtime.send.assert_not_awaited()


def test_the_cog_has_an_injectable_rng(cog: LifeLoop) -> None:
    assert isinstance(cog.rng, random.Random)


# ---
# Status card
# ---


async def test_tick_edits_status_message(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await interact(bot, life, NOW - timedelta(hours=2))
    await interact(bot, life, NOW - timedelta(hours=2), InteractionKind.CHAT)

    await cog.run_tick(NOW)

    after = await current_life(bot)
    assert after.last_tick_at == NOW
    assert after.full < 50.0
    server.status.get_partial_message.assert_called_once_with(CARD_ID)
    server.card_edit.assert_awaited_once()
    kwargs = server.card_edit.await_args.kwargs
    assert kwargs["content"] == render_status(
        after, NOW, happiness=happiness(1), fed_today=1
    )
    assert kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    server.status.send.assert_not_awaited()
    server.house.send.assert_not_awaited()


async def test_fed_today_counts_only_the_current_utc_day(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    before_midnight = NOW.replace(hour=0, minute=0) - timedelta(minutes=1)
    await interact(bot, life, before_midnight, InteractionKind.CHAT)

    await cog.run_tick(NOW)

    after = await current_life(bot)
    assert server.card_edit.await_args.kwargs["content"] == render_status(
        after, NOW, happiness=happiness(1), fed_today=0
    )


async def test_happy_counts_only_chatters(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    recently = NOW - timedelta(hours=2)
    await interact(bot, life, recently, InteractionKind.FEED, user_id=2)
    await interact(bot, life, recently, InteractionKind.SNACK, user_id=3)
    await interact(bot, life, recently, InteractionKind.CHAT, user_id=4)

    await cog.run_tick(NOW)

    content = server.card_edit.await_args.kwargs["content"]
    assert f"happiness  {bar(happiness(1))}  {happiness(1)}" in content


async def test_missing_status_message_is_reposted(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.card_edit.side_effect = discord.NotFound(
        MagicMock(status=404), "Unknown Message"
    )

    await cog.run_tick(NOW)

    server.status.send.assert_awaited_once()
    (text,) = server.status.send.await_args.args
    assert text.startswith("♪ WISP v1 ・ BABY")
    assert server.status.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    server.card.pin.assert_awaited_once()
    stored = (await bot.settings.get(GUILD_ID)).status_message_id
    assert stored == REPOSTED_CARD_ID
    assert house_reports(server) == []


async def test_edited_status_keeps_feed_and_poke_buttons(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)

    await cog.run_tick(NOW)

    view = server.card_edit.await_args.kwargs["view"]
    feed, poke = view.children
    assert isinstance(feed, FeedButton)
    assert isinstance(poke, PokeButton)
    assert view.timeout is None


async def test_reposted_status_keeps_feed_and_poke_buttons(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.card_edit.side_effect = discord.NotFound(
        MagicMock(status=404), "Unknown Message"
    )

    await cog.run_tick(NOW)

    view = server.status.send.await_args.kwargs["view"]
    feed, poke = view.children
    assert isinstance(feed, FeedButton)
    assert feed.item.custom_id == "wisp:feed"
    assert isinstance(poke, PokeButton)
    assert poke.item.custom_id == "wisp:poke"
    assert view.timeout is None


async def test_card_is_posted_when_none_is_stored(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await bot.settings.update(GUILD_ID, status_message_id=None)
    await lay(bot)

    await cog.run_tick(NOW)

    server.card_edit.assert_not_awaited()
    server.status.send.assert_awaited_once()
    assert (await bot.settings.get(GUILD_ID)).status_message_id == REPOSTED_CARD_ID


async def test_pin_failure_is_posted_in_the_status_thread_and_the_card_kept(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.card_edit.side_effect = discord.NotFound(
        MagicMock(status=404), "Unknown Message"
    )
    server.card.pin.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await cog.run_tick(NOW)

    assert (await bot.settings.get(GUILD_ID)).status_message_id == REPOSTED_CARD_ID
    assert server.status.send.await_count == 2
    (report,) = server.status.send.await_args.args
    assert report.startswith("Error in pinning the status card: Forbidden")
    assert house_reports(server) == []


async def test_forbidden_card_edit_is_posted_in_the_status_thread(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.card_edit.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Access"
    )

    await cog.run_tick(NOW)

    assert (await current_life(bot)).last_tick_at == NOW
    server.status.send.assert_awaited_once()
    (report,) = server.status.send.await_args.args
    assert report.startswith("Error in updating the status card: Forbidden")
    assert server.status.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    assert house_reports(server) == []


async def test_card_failure_goes_to_the_house_when_the_status_thread_is_gone(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await bot.settings.update(GUILD_ID, studio_forum_id=None)
    await lay(bot)

    await cog.run_tick(NOW)

    assert any(
        report.startswith("Error in updating the status card: StudioError")
        for report in house_reports(server)
    )
    server.status.send.assert_not_awaited()


async def test_card_failure_is_reported_once_per_streak(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    forbidden = discord.Forbidden(MagicMock(status=403), "Missing Access")
    server.card_edit.side_effect = forbidden

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + FULL_GAP)
    assert server.status.send.await_count == 1

    server.card_edit.side_effect = None
    await cog.run_tick(NOW + 2 * FULL_GAP)
    server.card_edit.side_effect = forbidden
    await cog.run_tick(NOW + 3 * FULL_GAP)

    assert server.status.send.await_count == 2


# ---
# Status card picture
# ---


@pytest.fixture
def stage_art(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stage art with only the egg and the baby."""
    stages = tmp_path / "stages"
    stages.mkdir()
    for name in ("egg", "baby"):
        (stages / f"{name}.png").write_bytes(b"png")
    monkeypatch.setattr(announce, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(pictures, "ASSETS_DIR", tmp_path)
    return stages


def card_pictures(server: FakeServer) -> list[list[str]]:
    """The pictures attached on each card edit, in order."""
    pictures: list[list[str]] = []
    for call in server.card_edit.await_args_list:
        files: list[discord.File] = call.kwargs.get("attachments", [])
        for file in files:
            file.close()
        pictures.append([file.filename for file in files])
    return pictures


async def with_panel(bot: app.WispBot, server: FakeServer) -> MagicMock:
    """Configure the guild with a Poke Wisp panel in the House."""
    await configure(bot)
    await bot.settings.update(GUILD_ID, house_panel_message_id=PANEL_ID)
    panel = MagicMock(spec=discord.Message)
    panel.id = PANEL_ID
    panel.edit = AsyncMock(return_value=panel)
    server.house.fetch_message = AsyncMock(return_value=panel)
    return panel


def panel_pictures(panel: MagicMock) -> list[list[str]]:
    """The pictures put on the panel by each edit; edits touch nothing else."""
    pictures_shown: list[list[str]] = []
    for call in panel.edit.await_args_list:
        assert set(call.kwargs) == {"attachments"}
        files: list[discord.File] = call.kwargs["attachments"]
        for file in files:
            file.close()
        pictures_shown.append([file.filename for file in files])
    return pictures_shown


async def test_the_panel_switches_to_the_baby_on_hatch_and_skips_unchanged_ticks(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, stage_art: Path
) -> None:
    panel = await with_panel(bot, server)
    almost = rules.HATCHING_TIME - FULL_GAP
    await lay(
        bot,
        phase=Phase.HATCHING,
        gap=timedelta(minutes=1),
        phase_seconds=almost.total_seconds(),
    )

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + timedelta(minutes=2))
    await cog.run_tick(NOW + timedelta(minutes=2) + FULL_GAP)
    await cog.run_tick(NOW + timedelta(minutes=4) + FULL_GAP)

    assert (await current_life(bot)).phase is Phase.ALIVE
    assert panel_pictures(panel) == [["egg.png"], ["baby.png"]]
    assert house_reports(server) == []


async def test_a_restart_puts_the_panel_picture_on_once_more(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, stage_art: Path
) -> None:
    panel = await with_panel(bot, server)

    await cog.run_tick(NOW)
    bot.shown_images.clear()
    await cog.run_tick(NOW + timedelta(minutes=2))
    await cog.run_tick(NOW + timedelta(minutes=4))

    assert panel_pictures(panel) == [["egg.png"], ["egg.png"]]


async def test_a_missing_panel_is_left_alone_by_the_tick(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, stage_art: Path
) -> None:
    await with_panel(bot, server)
    server.house.fetch_message.side_effect = discord.NotFound(
        MagicMock(status=404), "Unknown Message"
    )

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + timedelta(minutes=2))

    assert house_reports(server) == []
    assert (await bot.settings.get(GUILD_ID)).house_panel_message_id == PANEL_ID
    assert all(
        call.args[:1] != (HOUSE_PANEL,) for call in server.house.send.await_args_list
    )


async def test_missing_art_leaves_the_panel_alone(
    cog: LifeLoop,
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(announce, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(pictures, "ASSETS_DIR", tmp_path)
    panel = await with_panel(bot, server)

    await cog.run_tick(NOW)

    server.house.fetch_message.assert_not_awaited()
    panel.edit.assert_not_awaited()
    assert house_reports(server) == []


async def test_a_refused_panel_picture_falls_back_and_is_reported_once(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, stage_art: Path
) -> None:
    panel = await with_panel(bot, server)
    refused = discord.HTTPException(MagicMock(status=400), "Invalid Form Body")
    panel.edit.side_effect = [refused, panel, refused, panel]

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + timedelta(minutes=2))

    assert panel_pictures(panel) == [["egg.png"], [], ["egg.png"], []]
    (report,) = house_reports(server)
    assert report.startswith(
        "Error in attaching the Poke Wisp panel picture: HTTPException"
    )


async def test_the_card_shows_the_egg_picture(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, stage_art: Path
) -> None:
    await configure(bot)

    await cog.run_tick(NOW)

    assert card_pictures(server) == [["egg.png"]]


async def test_the_card_switches_to_the_baby_on_hatch_and_skips_unchanged_ticks(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, stage_art: Path
) -> None:
    await configure(bot)
    almost = rules.HATCHING_TIME - FULL_GAP
    await lay(
        bot,
        phase=Phase.HATCHING,
        gap=timedelta(minutes=1),
        phase_seconds=almost.total_seconds(),
    )

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + timedelta(minutes=2))
    await cog.run_tick(NOW + timedelta(minutes=2) + FULL_GAP)
    await cog.run_tick(NOW + timedelta(minutes=4) + FULL_GAP)

    assert (await current_life(bot)).phase is Phase.ALIVE
    assert card_pictures(server) == [["egg.png"], [], ["baby.png"], []]


async def test_missing_art_never_breaks_the_card(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, stage_art: Path
) -> None:
    await configure(bot)
    life = await lay(bot)
    life.stage = life.peak_stage = Stage.TEEN
    await bot.lives.save(GUILD_ID, life)

    await cog.run_tick(NOW)

    assert card_pictures(server) == [[]]
    content = server.card_edit.await_args.kwargs["content"]
    assert content.startswith("♪ WISP v1 ・ TEEN")
    assert house_reports(server) == []
    server.status.send.assert_not_awaited()


# ---
# The Vault
# ---


async def test_tick_refreshes_the_vault_after_the_status_card(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await bot.players.add_points(GUILD_ID, USER_ID, 5)
    await interact(bot, life, NOW - timedelta(hours=2))
    order: list[str] = []
    server.card_edit.side_effect = lambda **_: order.append("card")
    server.vault_edit.side_effect = lambda **_: order.append("vault")

    await cog.run_tick(NOW)

    assert order == ["card", "vault"]
    content = server.vault_edit.await_args.kwargs["content"]
    assert content.startswith("♪ The ViiBR Vault")
    assert f"<@{USER_ID}>" in content


async def test_vault_failure_is_reported_without_losing_the_card(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)
    server.vault_edit.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Access"
    )

    await cog.run_tick(NOW)

    server.card_edit.assert_awaited_once()
    server.vault.send.assert_awaited_once()
    (report,) = server.vault.send.await_args.args
    assert report.startswith("Error in updating the ViiBR Vault card: Forbidden")


# ---
# Events
# ---


async def test_death_posts_died_then_new_egg_with_next_version(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot, full=0.01)

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase) == (2, Phase.EGG)
    died, laid = house_texts(server)
    assert mentions_version(died, 1)
    assert mentions_version(laid, 2)
    content = server.card_edit.await_args.kwargs["content"]
    assert content.startswith("♪ WISP v2 ・ EGG")


async def test_cold_egg_uses_up_version(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    nearly_cold = rules.EGG_WARMTH.total_seconds() - 1
    await lay(bot, phase=Phase.EGG, full=0.0, phase_seconds=nearly_cold)

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase) == (2, Phase.EGG)
    cold = (await bot.lives.history(GUILD_ID))[-1]
    assert (cold.version, cold.phase, cold.ended_at) == (1, Phase.COLD, NOW)
    assert len(house_texts(server)) == 2
    assert await bot.lives.next_version(GUILD_ID) == 3


async def test_finished_life_is_replaced_by_next_egg(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot, phase=Phase.DEAD, full=0.0)

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase) == (2, Phase.EGG)
    (laid,) = house_texts(server)
    assert mentions_version(laid, 2)
    assert not mentions_version(laid, 1)
    content = server.card_edit.await_args.kwargs["content"]
    assert content.startswith("♪ WISP v2 ・ EGG")

    await cog.run_tick(NOW + FULL_GAP)

    assert (await current_life(bot)).version == 2
    server.house.send.assert_awaited_once()


async def test_over_life_at_tick_start_uses_next_life(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    passed = await lay(bot, phase=Phase.PASSED, full=40.0)
    assert passed.id is not None
    track = Track(TrackKind.VIIBR, "track", "https://viibrmusic.com/songs/track")
    await bot.activity_log.record_feed(
        GUILD_ID, passed.id, USER_ID, track, 5, 1, NOW - timedelta(days=1)
    )

    await cog.run_tick(NOW)

    egg = await current_life(bot)
    assert (egg.version, egg.phase, egg.from_coal) == (2, Phase.EGG, True)
    assert egg.last_tick_at == NOW
    outage, gift, laid = house_texts(server)
    assert outage.startswith("Error in Wisp's AI voice: AllProvidersFailed")
    assert gift.startswith(f"♪ <@{USER_ID}> gets Wisp v1's Last Ember\n")
    assert mentions_version(laid, 2)
    keepsakes = await bot.keepsakes.of(GUILD_ID, USER_ID)
    assert [keepsake.title for keepsake in keepsakes] == ["Wisp v1's Last Ember"]
    content = server.card_edit.await_args.kwargs["content"]
    assert content.startswith("♪ WISP v2 ・ EGG")


async def test_frozen_guild_does_not_drain(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot, frozen=True)
    await lay(bot, full=50.0)

    await cog.run_tick(NOW)

    life = await current_life(bot)
    assert life.full == 50.0
    assert life.phase_seconds == 0.0
    assert life.last_tick_at == NOW
    server.house.send.assert_not_awaited()
    server.card_edit.assert_awaited_once()


# ---
# The childhood cold
# ---


class LowRng(random.Random):
    """An rng whose `uniform` always lands on the low end of its range."""

    def uniform(self, a: float, b: float) -> float:
        return a


async def legacy_child(bot: app.WispBot) -> Life:
    """A Child hatched five days ago, saved before colds existed."""
    life = await lay(bot, full=80.0, stage=Stage.CHILD)
    life.hatched_at = life.stage_started_at = NOW - timedelta(days=5)
    await bot.lives.save(GUILD_ID, life)
    return life


async def test_a_legacy_child_catches_his_cold_on_the_next_tick(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, stage_art: Path
) -> None:
    await configure(bot)
    (stage_art.parent / "moments").mkdir()
    (stage_art.parent / "moments" / "sick_child.png").write_bytes(b"png")
    await legacy_child(bot)
    cog.rng = LowRng()

    await cog.run_tick(NOW)

    life = await current_life(bot)
    assert life.cold_due_at == NOW - timedelta(days=5) + rules.COLD_EARLIEST
    assert life.had_cold
    assert life.cold_left == (rules.SICK_FOR - FULL_GAP).total_seconds()
    sick_lines = set(LINES[(Moment.SICK, Mood.HAPPY)])
    (post,) = [
        call for call in server.house.send.await_args_list if call.args[0] in sick_lines
    ]
    assert post.kwargs["file"].filename == "sick_child.png"
    assert card_pictures(server) == [["sick_child.png"]]


async def test_a_frozen_child_gets_his_cold_scheduled_but_not_started(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot, frozen=True)
    await legacy_child(bot)
    cog.rng = LowRng()

    await cog.run_tick(NOW)

    life = await current_life(bot)
    assert life.cold_due_at == NOW - timedelta(days=5) + rules.COLD_EARLIEST
    assert (life.had_cold, life.cold_left) == (False, 0.0)
    server.house.send.assert_not_awaited()


# ---
# Quiet
# ---


async def test_quiet_line_once_per_stretch(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot, gap=timedelta(minutes=5))

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + timedelta(minutes=5))
    assert server.house.send.await_count == 1

    await interact(bot, life, NOW + timedelta(minutes=6))
    await cog.run_tick(NOW + timedelta(minutes=10))
    assert server.house.send.await_count == 1

    await cog.run_tick(NOW + timedelta(minutes=10) + rules.QUIET_AFTER)
    assert server.house.send.await_count == 2
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )


@pytest.mark.parametrize(
    ("stage", "picture"),
    [
        (Stage.BABY, "nap.gif"),
        (Stage.CHILD, "nap.gif"),
        (Stage.TEEN, None),
        (Stage.ADULT, None),
    ],
)
async def test_the_quiet_post_shows_the_nap_picture_only_while_young(
    cog: LifeLoop,
    bot: app.WispBot,
    server: FakeServer,
    stage: Stage,
    picture: str | None,
) -> None:
    await configure(bot)
    await lay(bot, gap=timedelta(minutes=5), stage=stage)

    await cog.run_tick(NOW)

    (post,) = server.house.send.await_args_list
    shown = post.kwargs["file"].filename if "file" in post.kwargs else None
    assert shown == picture


async def test_no_quiet_line_before_the_quiet_time(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await interact(bot, life, NOW - rules.QUIET_AFTER + timedelta(seconds=1))

    await cog.run_tick(NOW)

    server.house.send.assert_not_awaited()


async def test_no_quiet_line_while_frozen(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot, frozen=True)
    await lay(bot)

    await cog.run_tick(NOW)

    server.house.send.assert_not_awaited()


async def test_no_quiet_line_for_an_egg(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot, phase=Phase.EGG, full=0.0)

    await cog.run_tick(NOW)

    server.house.send.assert_not_awaited()


@pytest.mark.parametrize(("full", "expected"), [(80.0, Mood.HAPPY), (5.0, Mood.HANGRY)])
async def test_quiet_line_matches_his_mood(
    cog: LifeLoop,
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    full: float,
    expected: Mood,
) -> None:
    await configure(bot)
    await lay(bot, full=full, version=3)
    picked: list[tuple[Moment, Mood, dict[str, str]]] = []

    def pick(moment: Moment, mood: Mood, **fields: str) -> str:
        picked.append((moment, mood, fields))
        return "line"

    monkeypatch.setattr(bot.lines, "pick", pick)

    await cog.run_tick(NOW)

    assert [(m, mood) for m, mood, _ in picked if m is Moment.QUIET] == [
        (Moment.QUIET, expected)
    ]


# ---
# Guild isolation
# ---


async def test_failing_guild_is_reported_and_the_next_one_still_ticks(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken_id = GUILD_ID - 1
    broken_guild = MagicMock(spec=discord.Guild)
    broken_guild.id = broken_id
    guilds = {broken_id: broken_guild, GUILD_ID: server.guild}
    monkeypatch.setattr(bot, "get_guild", guilds.get)
    for guild_id in guilds:
        await bot.settings.update(
            guild_id,
            house_channel_id=HOUSE_ID,
            studio_forum_id=FORUM_ID,
            status_thread_id=STATUS_ID,
            status_message_id=CARD_ID,
            vault_thread_id=VAULT_ID,
            vault_message_id=VAULT_MESSAGE_ID,
        )
    await lay(bot)
    current = bot.lives.current

    async def current_or_fail(guild_id: int) -> Life | None:
        if guild_id == broken_id:
            raise pymysql.err.OperationalError(2013, "Lost connection")
        return await current(guild_id)

    monkeypatch.setattr(bot.lives, "current", current_or_fail)
    reported: Any = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + FULL_GAP)

    assert (await current_life(bot)).last_tick_at == NOW + FULL_GAP
    assert reported.await_count == 2
    for call in reported.await_args_list:
        guild, context, error = call.args
        assert guild is broken_guild
        assert context == "life loop"
        assert isinstance(error, pymysql.err.OperationalError)


async def test_discord_failure_in_one_guild_is_reported_with_that_guild(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await configure(bot)
    await lay(bot)
    forbidden = discord.Forbidden(MagicMock(status=403), "Missing Access")
    monkeypatch.setattr(life_loop, "post_events", AsyncMock(side_effect=forbidden))
    reported: Any = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await cog.run_tick(NOW)

    reported.assert_awaited_once_with(server.guild, "life loop", forbidden)


async def test_guild_the_bot_cannot_see_is_skipped(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await configure(bot)
    await lay(bot, full=50.0)
    monkeypatch.setattr(bot, "get_guild", lambda _id: None)

    await cog.run_tick(NOW)

    life = await current_life(bot)
    assert life.last_tick_at == NOW - FULL_GAP
    server.house.send.assert_not_awaited()
    server.card_edit.assert_not_awaited()
    server.status.send.assert_not_awaited()


# ---
# The loop
# ---


async def test_loop_error_is_posted_in_every_house_and_loop_continues(
    cog: LifeLoop,
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = FakeServer()
    other.guild.id = GUILD_ID + 1
    guilds = {GUILD_ID: server.guild, GUILD_ID + 1: other.guild}
    monkeypatch.setattr(bot, "get_guild", guilds.get)
    for guild_id in guilds:
        await bot.settings.update(guild_id, house_channel_id=HOUSE_ID)
    ticks = 0
    recovered = asyncio.Event()

    async def flaky(now: datetime) -> None:
        nonlocal ticks
        ticks += 1
        if ticks == 1:
            raise RuntimeError("database went away")
        recovered.set()

    monkeypatch.setattr(cog, "run_tick", flaky)
    monkeypatch.setattr(bot, "wait_until_ready", AsyncMock())
    monkeypatch.setattr(life_loop, "TICK_EVERY", timedelta(milliseconds=10))
    cog.tick_loop.change_interval(seconds=0.01)

    await cog.cog_load()
    try:
        await asyncio.wait_for(recovered.wait(), timeout=5)
    finally:
        await cog.cog_unload()

    line = "Error in life loop: RuntimeError: database went away"
    for house in (server.house, other.house):
        house.send.assert_awaited_once()
        assert house.send.await_args.args == (line,)
    assert ticks >= 2


async def test_loop_waits_before_restarting_after_an_error(
    cog: LifeLoop, bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = AsyncMock(side_effect=RuntimeError("bug"))
    monkeypatch.setattr(cog, "run_tick", ticks)
    monkeypatch.setattr(bot, "wait_until_ready", AsyncMock())
    monkeypatch.setattr(bot, "report_error_everywhere", AsyncMock())

    await cog.cog_load()
    await asyncio.sleep(0.2)
    await cog.cog_unload()
    await asyncio.sleep(0.05)

    assert ticks.await_count == 1
    assert not cog.tick_loop.is_running()


async def test_unload_stops_the_loop(
    cog: LifeLoop, bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot, "wait_until_ready", AsyncMock())
    monkeypatch.setattr(cog, "run_tick", AsyncMock())

    await cog.cog_load()
    assert cog.tick_loop.is_running()
    await cog.cog_unload()
    await asyncio.sleep(0)

    assert not cog.tick_loop.is_running()


def test_the_loop_runs_every_tick_interval(cog: LifeLoop) -> None:
    assert cog.tick_loop.seconds == rules.TICK_EVERY.total_seconds()


async def test_cog_is_registered_and_set_up(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_cog: Any = AsyncMock()
    monkeypatch.setattr(bot, "add_cog", add_cog)

    await life_loop.setup(bot)

    assert "cogs.life_loop" in app.EXTENSIONS
    (added,) = add_cog.await_args.args
    assert isinstance(added, LifeLoop)


async def test_with_eggs_off_the_tick_lays_nothing_until_they_are_on(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await bot.settings.update(GUILD_ID, lay_eggs=False)
    ended = new_egg(1, NOW - timedelta(days=70))
    ended.phase = Phase.PASSED
    ended.stage = ended.peak_stage = Stage.OLD_FOGEY
    ended.hatched_at = NOW - timedelta(days=61)
    ended.ended_at = NOW - timedelta(hours=1)
    await bot.lives.insert(GUILD_ID, ended)

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + rules.TICK_EVERY)

    current = await bot.lives.current(GUILD_ID)
    assert current is not None and current.version == 1
    server.house.send.assert_not_awaited()

    await bot.settings.update(GUILD_ID, lay_eggs=True)
    await cog.run_tick(NOW + 2 * rules.TICK_EVERY)

    egg = await bot.lives.current(GUILD_ID)
    assert egg is not None
    assert (egg.version, egg.phase, egg.from_coal) == (2, Phase.EGG, True)
    (laid,) = [call.args[0] for call in server.house.send.await_args_list]
    assert laid in {
        line.format(version="2") for line in LINES[(Moment.COAL_EGG, Mood.HAPPY)]
    }


async def test_eggs_off_changes_nothing_while_he_is_alive(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await bot.settings.update(GUILD_ID, lay_eggs=False)
    life = await lay(bot, full=80.0)

    await cog.run_tick(NOW)

    current = await bot.lives.current(GUILD_ID)
    assert current is not None and current.id == life.id
    assert current.phase is Phase.ALIVE
    assert current.full < 80.0
    server.card_edit.assert_awaited_once()


async def test_a_restart_between_the_egg_and_the_badges_is_healed_on_the_next_tick(
    cog: LifeLoop, bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    ended = new_egg(1, NOW - timedelta(days=3))
    ended.phase = Phase.DEAD
    ended.ended_at = NOW - timedelta(hours=1)
    ended = await bot.lives.insert(GUILD_ID, ended)
    assert ended.id is not None
    await lay(bot, phase=Phase.EGG, version=2)
    await bot.badges.set_role(GUILD_ID, "egg_warmer", BADGE_ROLE_ID)
    await bot.badges.record(GUILD_ID, 1, "egg_warmer", ended.id, 1, NOW)
    role = MagicMock(spec=discord.Role)
    server.guild.get_role.side_effect = {BADGE_ROLE_ID: role}.get
    member = MagicMock(spec=discord.Member)
    member.remove_roles = AsyncMock()
    server.guild.fetch_member = AsyncMock(return_value=member)

    await cog.run_tick(NOW)
    await cog.run_tick(NOW + rules.TICK_EVERY)

    member.remove_roles.assert_awaited_once_with(role, reason="Wisp v1's life ended")
    assert await bot.badges.pending(GUILD_ID) == []
    assert house_reports(server) == []
