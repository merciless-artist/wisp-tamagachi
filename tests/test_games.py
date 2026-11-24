"""Tests for what games share: entering the member's room and the reward.

Discord objects are fakes; the repositories are the real ones.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import app
from cogs.games import Reward, enter_room, reward_game
from cogs.rooms import RoomError
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from wisp.life import Life, Phase, new_egg
from wisp.rules import (
    BOND_PER_PLAY,
    DAILY_CASUAL_BOND_CAP,
    GROWTH_PER_PLAY,
    PLAY_POINTS,
    WELLBEING_PER_PLAY,
    Stage,
)

GUILD_ID = 100
HOUSE_ID = 20
USER_ID = 1
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)

# ---
# Fixtures
# ---


@pytest.fixture
def bot(db: Database) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.story = LifeStoryRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    yield wisp_bot


async def lay(bot: app.WispBot) -> tuple[Life, int]:
    life = new_egg(1, NOW - timedelta(days=1))
    life.phase = Phase.ALIVE
    life.health = 50.0
    life.wellbeing = 40.0
    life.stage = life.peak_stage = Stage.BABY
    life.hatched_at = life.stage_started_at = NOW
    life = await bot.lives.insert(GUILD_ID, life)
    assert life.id is not None
    return life, life.id


def make_interaction(bot: app.WispBot, guild: MagicMock | None) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = guild
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = USER_ID
    interaction.user.display_name = "Member1"
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


# ---
# The reward
# ---


@pytest.mark.parametrize("kind", [InteractionKind.PLAY, InteractionKind.CRAVING])
async def test_reward_game_gives_a_counted_game(
    bot: app.WispBot, db: Database, kind: InteractionKind
) -> None:
    life, life_id = await lay(bot)
    growth = life.growth

    async with bot.guild_lock(GUILD_ID):
        reward = await reward_game(bot, GUILD_ID, USER_ID, life, life_id, kind, NOW)

    assert reward == Reward(
        BOND_PER_PLAY,
        f"Wellbeing +{WELLBEING_PER_PLAY} (now {40 + WELLBEING_PER_PLAY})",
        f"+{PLAY_POINTS} WC",
    )
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.bond, player.balance) == (BOND_PER_PLAY, PLAY_POINTS)
    saved = await bot.lives.current(GUILD_ID)
    assert saved is not None
    assert saved.wellbeing == 40 + WELLBEING_PER_PLAY
    assert saved.growth == growth + GROWTH_PER_PLAY
    rows = await db.fetchall(
        f"SELECT kind, bond FROM {db.t('interactions')} WHERE user_id = %s",
        (USER_ID,),
    )
    assert rows == [{"kind": kind.value, "bond": BOND_PER_PLAY}]


async def test_reward_game_records_the_kind_and_caps_the_bond(
    bot: app.WispBot, db: Database
) -> None:
    life, life_id = await lay(bot)
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life_id,
        USER_ID,
        InteractionKind.SNACK,
        DAILY_CASUAL_BOND_CAP,
        0,
        NOW,
    )

    async with bot.guild_lock(GUILD_ID):
        reward = await reward_game(
            bot, GUILD_ID, USER_ID, life, life_id, InteractionKind.CRAVING, NOW
        )

    assert reward.bond == 0
    assert reward.wellbeing.startswith(f"Wellbeing +{WELLBEING_PER_PLAY} ")
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 0
    saved = await bot.lives.current(GUILD_ID)
    assert saved is not None and saved.wellbeing == 40 + WELLBEING_PER_PLAY
    rows = await db.fetchall(f"SELECT kind FROM {db.t('interactions')} ORDER BY id")
    assert [row["kind"] for row in rows] == ["snack", "craving"]


# ---
# Entering the room
# ---


async def test_enter_room_returns_the_room(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    guild = MagicMock(spec=discord.Guild)
    room = MagicMock(spec=discord.Thread)
    opened = AsyncMock(return_value=room)
    monkeypatch.setattr("cogs.games.open_room", opened)
    interaction = make_interaction(bot, guild)

    assert await enter_room(interaction) is room

    opened.assert_awaited_once_with(bot, guild, interaction.user)
    interaction.followup.send.assert_not_awaited()


async def test_enter_room_refuses_with_the_reason_and_reports_it(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    guild = MagicMock(spec=discord.Guild)
    refused = RoomError(
        "Wisp's House isn't set up, so he can't open your storage locker yet."
    )
    monkeypatch.setattr("cogs.games.open_room", AsyncMock(side_effect=refused))
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)
    interaction = make_interaction(bot, guild)

    assert await enter_room(interaction) is None

    reported.assert_awaited_once_with(
        guild, "opening a room", refused, where=interaction.channel
    )
    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args is not None
    assert interaction.followup.send.await_args.args == (
        "♪ Wisp's House isn't set up, so he can't open your storage locker yet.",
    )
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True


async def test_enter_room_lets_discord_refusals_through(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    refused = discord.Forbidden(MagicMock(status=403), "Missing Permissions")
    monkeypatch.setattr("cogs.games.open_room", AsyncMock(side_effect=refused))

    with pytest.raises(discord.Forbidden):
        await enter_room(make_interaction(bot, MagicMock(spec=discord.Guild)))


async def test_enter_room_needs_a_guild(bot: app.WispBot) -> None:
    with pytest.raises(app_commands.NoPrivateMessage):
        await enter_room(make_interaction(bot, None))
