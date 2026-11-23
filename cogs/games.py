"""What every game with Wisp shares: the member's room and the reward.

Games run in the member's room, one at a time, and a counted game gives the
same bond, growth, Wellbeing and wisp coin whichever game it was.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

import discord
from discord import app_commands

from cogs.channels import where_of
from cogs.players import FROZEN_REASON, bot_of, is_frozen, no_wisp_text, say_privately
from cogs.rooms import RoomError, open_room
from db.activity import InteractionKind
from db.players import Player
from wisp.bond import casual_bond_grant
from wisp.chores import is_napping, nap_ends_at
from wisp.craving import is_idle
from wisp.life import Life, Meter, Phase, add_growth, change_meter
from wisp.rules import BOND_PER_PLAY, GROWTH_PER_PLAY, PLAY_POINTS, WELLBEING_PER_PLAY
from wisp.text import meter_receipt, timestamp, with_emoji
from wisp.voice import MINI_COIN_EMOJI

if TYPE_CHECKING:
    from app import WispBot

ROOM_BUSY: Final = (
    "♪ You already have a game going in your room. Finish that one first."
)

# ---
# Before a game
# ---


async def check_game(
    bot: "WispBot",
    guild_id: int,
    player: Player,
    now: datetime,
    *,
    banned: str,
    things: str,
) -> Life | str:
    """The living Wisp a game can start with, or what to tell the member.

    A ban comes first, with `banned`; then no living Wisp, named as `things`
    (capitalised and plural, such as "Rhymes"); then a freeze; then a nap.
    """
    life = await bot.lives.current(guild_id)
    if player.is_banned(now):
        return banned
    if life is None or life.phase is not Phase.ALIVE:
        return no_wisp_text(life, things)
    if await is_frozen(bot, guild_id):
        return f"♪ {FROZEN_REASON}"
    if is_napping(life):
        until = timestamp(nap_ends_at(life, now))
        return f"♪ Wisp is napping until {until}. Poke him awake first."
    return life


async def room_busy(bot: "WispBot", guild_id: int, user_id: int, now: datetime) -> bool:
    """Whether the member's room has a game going: a duel, or a live Craving.

    A Craving round that has gone idle no longer holds the room; it ends as a
    timeout when it is next touched.
    """
    if (guild_id, user_id) in bot.room_games:
        return True
    craving = await bot.cravings.today(guild_id, user_id, now)
    return (
        craving is not None
        and craving.ended_at is None
        and not is_idle(craving.last_at, now)
    )


# ---
# The room
# ---


async def enter_room(interaction: discord.Interaction) -> discord.Thread | None:
    """Open the member's room for a game, or tell them why it can't open.

    When the House is missing, the failure is posted where the game was
    started and the member is told the reason privately; the game does not
    start, and the room is tried again next time. Discord's refusals are
    raised as they come.

    Raises:
        app_commands.NoPrivateMessage: The interaction is not in a guild.
    """
    guild = interaction.guild
    if guild is None:
        raise app_commands.NoPrivateMessage()
    bot = bot_of(interaction)
    try:
        return await open_room(bot, guild, interaction.user)
    except RoomError as error:
        await bot.report_error(
            guild, "opening a room", error, where=where_of(interaction)
        )
        await say_privately(interaction, f"♪ {error}")
        return None


# ---
# The reward
# ---


@dataclass(frozen=True)
class Reward:
    """What a counted game gave.

    `bond` is the bond added, 0 once today's casual cap is reached;
    `wellbeing` and `coins` are the receipt's text for them.
    """

    bond: int
    wellbeing: str
    coins: str


async def reward_game(
    bot: "WispBot",
    guild_id: int,
    user_id: int,
    life: Life,
    life_id: int,
    kind: InteractionKind,
    now: datetime,
) -> Reward:
    """Give a counted game's bond, growth, care, Wellbeing and wisp coin.

    The bond shares the daily casual cap with snacks and the other games. The
    game is recorded as `kind`. Call this under `bot.guild_lock`.
    """
    log = bot.activity_log
    bond = casual_bond_grant(
        await log.casual_bond_today(guild_id, user_id, now), BOND_PER_PLAY
    )
    if bond:
        await bot.players.add_bond(guild_id, user_id, bond)
    await log.record_interaction(guild_id, life_id, user_id, kind, bond, 0, now)
    await bot.players.add_points(guild_id, user_id, PLAY_POINTS)
    add_growth(life, GROWTH_PER_PLAY)
    before = life.wellbeing
    change_meter(life, Meter.WELLBEING, WELLBEING_PER_PLAY, ends_stretch=True)
    await bot.lives.save(guild_id, life)
    return Reward(
        bond,
        meter_receipt("Wellbeing", before, life.wellbeing),
        with_emoji(bot.emoji(MINI_COIN_EMOJI), f"+{PLAY_POINTS} WC"),
    )
