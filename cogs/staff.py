"""Staff commands: typed `!wisp <command>` text commands, for staff only.

Members play through the /wisp slash commands; staff type their commands so
they never dig through slash menus. Anyone who is not staff is ignored without
a word. Bare `!wisp` is kept free for the help menu. Setup and the FAQ rebuild
also have /wispadmin slash forms, which refuse non-staff privately.
"""

import logging
from typing import TYPE_CHECKING, Any, Final, TypeAlias

import discord
from discord.ext import commands

from cogs.channels import may_post_in

if TYPE_CHECKING:
    from app import WispBot

log = logging.getLogger("wisp")

PREFIX: Final = "!wisp "
STAFF_ONLY: Final = "That command is for staff."
_NO_PING: Final = discord.AllowedMentions.none()

StaffContext: TypeAlias = commands.Context["WispBot"]

# ---
# Who is staff
# ---


async def is_staff(bot: "WispBot", member: discord.Member) -> bool:
    """Whether a member may use the staff commands.

    Staff have Manage Server, hold one of the guild's staff roles, or own
    Wisp's Discord application, which counts in every server. discord.py
    fetches the owner once and keeps it.
    """
    if member.guild_permissions.manage_guild:
        return True
    staff_roles = await bot.settings.staff_roles(member.guild.id)
    if not staff_roles.isdisjoint(role.id for role in member.roles):
        return True
    return await bot.is_owner(member)


async def refused(interaction: discord.Interaction["WispBot"]) -> bool:
    """Turn away a staff slash command from anyone but staff; True if refused.

    The refusal is private. Discord already hides the command from members
    without Manage Server, unless a server's integration settings show it.
    """
    user = interaction.user
    if isinstance(user, discord.Member) and await is_staff(interaction.client, user):
        return False
    await interaction.response.send_message(STAFF_ONLY, ephemeral=True)
    return True


async def staff_check(ctx: StaffContext) -> bool:
    """The check every staff command runs before its arguments are read."""
    return isinstance(ctx.author, discord.Member) and await is_staff(
        ctx.bot, ctx.author
    )


def is_command(content: str) -> bool:
    """Whether a message's text starts with the `!wisp ` prefix, in any case."""
    return content[: len(PREFIX)].lower() == PREFIX


def command_prefix(_bot: "WispBot", message: discord.Message) -> str:
    """The `!wisp ` prefix in whatever case the message typed it."""
    content = message.content
    return content[: len(PREFIX)] if is_command(content) else PREFIX


# ---
# Replies
# ---


def guild_of(ctx: StaffContext) -> discord.Guild:
    """The guild a staff command was used in.

    Raises:
        commands.NoPrivateMessage: The command did not come from a guild.
    """
    if ctx.guild is None:
        raise commands.NoPrivateMessage()
    return ctx.guild


async def reply(ctx: StaffContext, text: str) -> None:
    """Answer a staff command in its channel, pinging nobody.

    Where Wisp may not post, such as the track drop, the answer goes to his
    House instead; with no House it is only logged.
    """
    bot = ctx.bot
    guild = guild_of(ctx)
    channel: discord.abc.Messageable = ctx.channel
    tracks_id = (await bot.settings.get(guild.id)).tracks_channel_id
    if not may_post_in(channel, tracks_id):
        house = await bot.house_channel(guild)
        if house is None:
            log.warning("No House to answer %s in", command_context(ctx))
            return
        channel = house
    await channel.send(text, allowed_mentions=_NO_PING)


def usage_line(command: commands.Command[Any, ..., Any]) -> str:
    """How to type a staff command, for when its arguments are wrong."""
    return f"♪ Usage: {PREFIX}{command.qualified_name} {command.usage or ''}".rstrip()


def command_list(bot: "WispBot") -> str:
    """The staff command names, for an unknown command."""
    return f"♪ Wisp staff commands: {', '.join(bot.all_commands)}"


def command_context(ctx: StaffContext) -> str:
    """The command as an error report names it, such as "!wisp roles add"."""
    command = ctx.command
    return f"{PREFIX}{command.qualified_name}" if command else "a staff command"


# ---
# Staff roles
# ---


@commands.group(
    name="staff",
    invoke_without_command=True,
    case_insensitive=True,
    usage="add @role | remove @role | list",
)
async def staff(ctx: StaffContext) -> None:
    """Explain the staff role commands when no known one was typed."""
    await reply(ctx, usage_line(staff))


@staff.command(name="add", usage="@role")
async def staff_add(ctx: StaffContext, role: discord.Role) -> None:
    """Make a role's members Wisp staff."""
    await ctx.bot.settings.add_staff_role(guild_of(ctx).id, role.id)
    await reply(ctx, f"♪ {role.mention} is now a Wisp staff role.")


@staff.command(name="remove", usage="@role")
async def staff_remove(ctx: StaffContext, role: discord.Role) -> None:
    """Stop a role's members being Wisp staff."""
    await ctx.bot.settings.remove_staff_role(guild_of(ctx).id, role.id)
    await reply(ctx, f"♪ {role.mention} is no longer a Wisp staff role.")


@staff.command(name="list")
async def staff_list(ctx: StaffContext) -> None:
    """List the staff roles."""
    role_ids = await ctx.bot.settings.staff_roles(guild_of(ctx).id)
    if role_ids:
        mentions = (f"・<@&{role_id}>" for role_id in sorted(role_ids))
        text = "\n".join(["♪ Wisp staff roles", *mentions])
    else:
        text = (
            "♪ No staff roles yet. Members with Manage Server are always staff. "
            f"Add a role with {PREFIX}staff add @role."
        )
    await reply(ctx, text)


async def setup(bot: "WispBot") -> None:
    """Load the staff role commands."""
    bot.add_command(staff)
