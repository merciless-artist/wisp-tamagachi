"""Discipline: staff commands to punish cheaters and correct mistakes."""

import random
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord
from discord import app_commands

from cogs.announce import ASSETS_DIR, say_in_house
from cogs.groups import require_guild, wispadmin
from wisp.lines import Moment
from wisp.rules import BAN_LADDER
from wisp.text import count

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_IMAGE_SUFFIXES: Final = frozenset({".png", ".gif", ".jpg", ".webp"})
_REASON_MAX: Final = 500
_MAX_POINTS: Final = 2**31 - 1

# ---
# Helpers
# ---


async def _reply(interaction: discord.Interaction, text: str) -> None:
    """Answer the staff member privately, whether or not the command deferred."""
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True, allowed_mentions=_NO_PING)
    else:
        await interaction.response.send_message(
            text, ephemeral=True, allowed_mentions=_NO_PING
        )


async def _refuse_bot(interaction: discord.Interaction, member: discord.Member) -> bool:
    """Tell staff that bots take no part in Wisp; True if `member` is one."""
    if not member.bot:
        return False
    await _reply(
        interaction, f"♪ {member.mention} is a bot, and bots do not play with Wisp."
    )
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


async def _log_to_staff(bot: "WispBot", guild: discord.Guild | None, text: str) -> bool:
    """Post a line to the staff errors channel; False if it could not be posted."""
    channel = await bot.staff_channel(guild)
    if channel is None:
        return False
    try:
        await channel.send(text, allowed_mentions=_NO_PING)
    except discord.HTTPException as error:
        await bot.report_error(guild, "logging the punishment", error)
        return False
    return True


# ---
# Punishment
# ---


@wispadmin.command(name="punish", description="Ban a member from Wisp.")
@app_commands.describe(
    member="The member who broke the rules",
    reason="Why; only staff see this",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def punish(
    interaction: discord.Interaction["WispBot"],
    member: discord.Member,
    reason: app_commands.Range[str, 1, _REASON_MAX],
) -> None:
    """Give the member their next offense and the ban that goes with it.

    Wisp announces the ban in his House without the reason, which goes to the
    errors channel as a staff log.
    """
    bot = interaction.client
    guild_id = require_guild(interaction)
    if await _refuse_bot(interaction, member):
        return
    await interaction.response.defer(ephemeral=True)
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
    if life is None:
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
    duration = _duration(length)
    logged = await _log_to_staff(
        bot,
        interaction.guild,
        f"♪ {interaction.user.mention} punished {member.mention} "
        f"(offense {offense}, {duration}): {reason}",
    )
    if not logged:
        notes.append("The reason was not recorded: the errors channel is unavailable.")
    await _reply(
        interaction,
        "\n".join(
            [
                f"♪ {member.mention} is banned from Wisp (offense {offense}, "
                f"{duration}).",
                *(f"・{note}" for note in notes),
            ]
        ),
    )


# ---
# Corrections
# ---


@wispadmin.command(name="unban", description="Lift a member's ban from Wisp.")
@app_commands.describe(member="The member to let back in")
@app_commands.checks.has_permissions(manage_guild=True)
async def unban(
    interaction: discord.Interaction["WispBot"], member: discord.Member
) -> None:
    """End the member's ban; their offense count stays, so the ladder goes on."""
    bot = interaction.client
    guild_id = require_guild(interaction)
    if await _refuse_bot(interaction, member):
        return
    await interaction.response.defer(ephemeral=True)
    player = await bot.players.get(guild_id, member.id)
    if not player.is_banned(discord.utils.utcnow()):
        await _reply(interaction, f"♪ {member.mention} is not banned.")
        return
    await bot.players.set_offense(guild_id, member.id, player.offenses, None, False)
    await _reply(
        interaction,
        f"♪ {member.mention} can play with Wisp again. "
        f"Their offense count stays at {player.offenses}.",
    )


@wispadmin.command(name="strip", description="Take leaderboard points from a member.")
@app_commands.describe(member="The member to take points from", points="How many")
@app_commands.checks.has_permissions(manage_guild=True)
async def strip(
    interaction: discord.Interaction["WispBot"],
    member: discord.Member,
    points: app_commands.Range[int, 1, _MAX_POINTS],
) -> None:
    """Take points from the member's balance and lifetime total, never below 0."""
    if await _refuse_bot(interaction, member):
        return
    await interaction.response.defer(ephemeral=True)
    await interaction.client.players.strip_points(
        require_guild(interaction), member.id, points
    )
    await _reply(interaction, f"♪ Took {count(points, 'point')} from {member.mention}.")


@wispadmin.command(name="resetname", description="Make Wisp forget a member's name.")
@app_commands.describe(member="The member whose name to clear")
@app_commands.checks.has_permissions(manage_guild=True)
async def resetname(
    interaction: discord.Interaction["WispBot"], member: discord.Member
) -> None:
    """Clear the member's name so they can choose again from Wisp's button."""
    if await _refuse_bot(interaction, member):
        return
    await interaction.response.defer(ephemeral=True)
    await interaction.client.players.set_name(
        require_guild(interaction), member.id, None
    )
    await _reply(
        interaction,
        f"♪ Wisp forgot {member.mention}'s name. They can choose a new one.",
    )


async def setup(bot: "WispBot") -> None:
    """Load the discipline extension; its commands join the shared groups on import."""
