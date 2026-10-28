"""Discipline: staff commands to punish cheaters and correct mistakes."""

import random
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord
from discord.ext import commands

from cogs.announce import say_in_house
from cogs.assets import ASSETS_DIR
from cogs.staff import StaffContext, guild_of, reply
from wisp.life import is_over
from wisp.lines import Moment
from wisp.rules import BAN_LADDER
from wisp.text import count

if TYPE_CHECKING:
    from app import WispBot

_IMAGE_SUFFIXES: Final = frozenset({".png", ".gif", ".jpg", ".webp"})
_REASON_MAX: Final = 500
_MAX_POINTS: Final = 2**31 - 1

# ---
# Helpers
# ---


async def _refuse_bot(ctx: StaffContext, member: discord.Member) -> bool:
    """Tell staff that bots take no part in Wisp; True if `member` is one."""
    if not member.bot:
        return False
    await reply(ctx, f"♪ {member.mention} is a bot, and bots do not play with Wisp.")
    return True


def _shame_image() -> Path | None:
    """A random image from ASSETS/shame, or None when the folder has none."""
    images = sorted(
        path
        for path in (ASSETS_DIR / "shame").glob("*")
        if path.suffix.lower() in _IMAGE_SUFFIXES and path.is_file()
    )
    return random.choice(images) if images else None


def _duration(length: timedelta | None) -> str:
    if length is None:
        return "permanent"
    return count(length // timedelta(days=1), "day")


# ---
# Punishment
# ---


@commands.command(name="punish", usage="@member <reason>")
async def punish(
    ctx: StaffContext,
    member: discord.Member,
    *,
    reason: commands.Range[str, 1, _REASON_MAX],
) -> None:
    """Give the member their next offense and the ban that goes with it.

    Wisp announces the ban in his House without the reason, unless there is
    no living Wisp to say it. The reason goes in the public answer, with the
    staff member who gave it.
    """
    bot = ctx.bot
    guild_id = guild_of(ctx).id
    if await _refuse_bot(ctx, member):
        return
    async with bot.guild_lock(guild_id):
        player = await bot.players.get(guild_id, member.id)
        offense = player.offenses + 1
        length = BAN_LADDER[min(player.offenses, len(BAN_LADDER) - 1)]
        await bot.players.set_offense(
            guild_id,
            member.id,
            offense,
            None if length is None else discord.utils.utcnow() + length,
            length is None,
        )
    notes = []
    life = await bot.lives.current(guild_id)
    if life is None or is_over(life):
        notes.append("Wisp has no life right now, so nothing was posted in his House.")
    else:
        await say_in_house(
            bot,
            guild_id,
            Moment.BANNED,
            life,
            name=player.name or member.display_name,
            image=_shame_image(),
        )
    await reply(
        ctx,
        "\n".join(
            [
                f"♪ {ctx.author.mention} punished {member.mention} "
                f"(offense {offense}, {_duration(length)}): {reason}",
                *(f"・{note}" for note in notes),
            ]
        ),
    )


# ---
# Corrections
# ---


@commands.command(name="unban", usage="@member")
async def unban(ctx: StaffContext, member: discord.Member) -> None:
    """End the member's ban; their offense count stays, so the ladder goes on."""
    bot = ctx.bot
    guild_id = guild_of(ctx).id
    if await _refuse_bot(ctx, member):
        return
    player = await bot.players.get(guild_id, member.id)
    if not player.is_banned(discord.utils.utcnow()):
        await reply(ctx, f"♪ {member.mention} is not banned.")
        return
    await bot.players.set_offense(guild_id, member.id, player.offenses, None, False)
    await reply(
        ctx,
        f"♪ {member.mention} can play with Wisp again. "
        f"Their offense count stays at {player.offenses}.",
    )


@commands.command(name="strip", usage="@member <points>")
async def strip(
    ctx: StaffContext,
    member: discord.Member,
    points: commands.Range[int, 1, _MAX_POINTS],
) -> None:
    """Take points from the member's balance and lifetime total, never below 0."""
    if await _refuse_bot(ctx, member):
        return
    await ctx.bot.players.strip_points(guild_of(ctx).id, member.id, points)
    await reply(ctx, f"♪ Took {count(points, 'point')} from {member.mention}.")


@commands.command(name="resetname", usage="@member")
async def resetname(ctx: StaffContext, member: discord.Member) -> None:
    """Clear the member's name so they can choose again from Wisp's button."""
    if await _refuse_bot(ctx, member):
        return
    await ctx.bot.players.set_name(guild_of(ctx).id, member.id, None)
    await reply(
        ctx, f"♪ Wisp forgot {member.mention}'s name. They can choose a new one."
    )


async def setup(bot: "WispBot") -> None:
    """Load the discipline commands."""
    for command in (punish, unban, strip, resetname):
        bot.add_command(command)
