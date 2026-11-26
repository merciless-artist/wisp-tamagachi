"""Help pings: the helper role, pinged when Wisp needs a member's hand.

Staff choose the role with `!wisp helperrole`. Opening /wisp board gives it,
and Wisp's House posts for a mess, a tantrum and lights off ping it. A member
turns it off and on again with the button under their board, and one who
turned it off is never given it again by Wisp.
"""

import logging
import re
from typing import TYPE_CHECKING, Final

import discord
from discord.ext import commands

from cogs.groups import require_guild
from cogs.players import bot_of, press, say_privately
from cogs.staff import StaffContext, guild_of, reply
from cogs.studio import cannot_ping_line, helper_role
from wisp.life import Life

if TYPE_CHECKING:
    from app import WispBot

log = logging.getLogger("wisp")

HELP_PINGS_ID: Final = "wisp:helppings"
STOP_LABEL: Final = "Stop help pings"
GET_LABEL: Final = "Get help pings"
_GIVING: Final = "giving the helper role"
_BOARD_REASON: Final = "Opened /wisp board"
_ON_REASON: Final = "Turned help pings on"
_OFF_REASON: Final = "Turned help pings off"
_ON: Final = (
    "♪ Help pings are on. Wisp pings you when he needs a hand with a mess, "
    "a tantrum or the lights."
)
_OFF: Final = (
    "♪ Help pings are off, and Wisp won't give them back on his own. "
    f"Press {GET_LABEL} to turn them on again."
)
_NO_PING: Final = discord.AllowedMentions.none()
_NO_ROLE: Final = "♪ There are no help pings right now: staff haven't set a role."
_NOT_EVERYONE: Final = (
    "♪ Everyone has that role, so pinging it would ping the whole server. "
    "Pick another role."
)
_CANNOT_GIVE: Final = (
    "・Some members didn't get it; the error is above. Wisp needs Manage Roles, "
    "and his own role above {role}."
)

# ---
# The helper role
# ---


def _holds(member: discord.Member, role: discord.Role) -> bool:
    return any(held.id == role.id for held in member.roles)


async def help_ping_role(bot: "WispBot", guild_id: int, life: Life) -> int | None:
    """The role a House post asking for a hand pings, or None for no ping.

    There is none when no helper role is set or it was deleted, and a staff
    test life pings nobody.
    """
    if life.is_test:
        return None
    role = helper_role(bot.get_guild(guild_id), await bot.settings.get(guild_id))
    return None if role is None else role.id


async def give_on_board(
    bot: "WispBot", guild: discord.Guild, member: discord.Member
) -> bool | None:
    """Give the helper role to a member opening /wisp board, unless they turned
    it off.

    Returns whether they hold it now, or None when there is no helper role. A
    Discord failure is only logged, so the board always shows; they do not
    hold it then.
    """
    role = helper_role(guild, await bot.settings.get(guild.id))
    if role is None:
        return None
    if _holds(member, role):
        return True
    if (await bot.players.get(guild.id, member.id)).help_pings_off:
        return False
    try:
        await member.add_roles(role, reason=_BOARD_REASON)
    except discord.HTTPException as error:
        log.warning("Could not give %d the helper role: %s", member.id, error)
        return False
    return True


async def give_to_board_openers(
    bot: "WispBot",
    guild: discord.Guild,
    role: discord.Role,
    where: discord.abc.Messageable | None,
) -> tuple[int, bool]:
    """Give `role` to every member who opened /wisp board and lacks it.

    Members who turned help pings off and members who left the server are
    skipped. A Discord failure is reported in `where`; a Forbidden stops the
    rest, since Wisp may not give the role to anyone then. Returns how many
    members got it and whether any failed.
    """
    given = 0
    failed = False
    for player in await bot.players.activated(guild.id):
        if player.help_pings_off:
            continue
        try:
            member = await guild.fetch_member(player.user_id)
            if _holds(member, role):
                continue
            await member.add_roles(role, reason=_BOARD_REASON)
        except discord.NotFound:
            continue
        except discord.HTTPException as error:
            failed = True
            await bot.report_error(guild, _GIVING, error, where=where)
            if isinstance(error, discord.Forbidden):
                break
            continue
        given += 1
    return given, failed


# ---
# The help pings button
# ---


class HelpPingsButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(HELP_PINGS_ID),
):
    """The button under /wisp board that turns the presser's help pings off or on.

    It reads "Stop help pings" for a member who holds the helper role and
    "Get help pings" for one who doesn't, and is relabelled on the board after
    each press. A press goes by the role the presser holds then, not by the
    label. Its custom id is fixed, so the button keeps working after the bot
    restarts, whatever its label.
    """

    def __init__(self, holds: bool = True) -> None:
        super().__init__(
            discord.ui.Button(
                label=STOP_LABEL if holds else GET_LABEL,
                style=discord.ButtonStyle.secondary,
                custom_id=HELP_PINGS_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "HelpPingsButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Turn the presser's help pings off or on, privately."""
        await press(interaction, "the help pings button", self._toggle)

    async def _toggle(self, interaction: discord.Interaction) -> None:
        """Turn help pings off for a presser who holds the role, on for one who
        doesn't, then relabel this button on their board to match.

        The role changes first, so a failed change records nothing.
        """
        await interaction.response.defer()
        bot = bot_of(interaction)
        guild_id = require_guild(interaction)
        member = interaction.user
        role = helper_role(interaction.guild, await bot.settings.get(guild_id))
        if role is None or not isinstance(member, discord.Member):
            await say_privately(interaction, _NO_ROLE)
            return
        turning_on = not _holds(member, role)
        if turning_on:
            await member.add_roles(role, reason=_ON_REASON)
        else:
            await member.remove_roles(role, reason=_OFF_REASON)
        await bot.players.set_help_pings_off(guild_id, member.id, not turning_on)
        self.item.label = STOP_LABEL if turning_on else GET_LABEL
        await interaction.edit_original_response(
            view=self.view, allowed_mentions=_NO_PING
        )
        await say_privately(interaction, _ON if turning_on else _OFF)


# ---
# Staff commands
# ---


@commands.group(
    name="helperrole",
    invoke_without_command=True,
    case_insensitive=True,
    usage="@role | off",
)
async def helperrole(ctx: StaffContext, role: discord.Role) -> None:
    """Make `role` the helper role and give it to everyone who opened /wisp board.

    @everyone is refused, since pinging it pings the whole server. The answer
    warns when Discord won't let Wisp ping the role, so staff can fix it.
    """
    if role.is_default():
        await reply(ctx, _NOT_EVERYONE)
        return
    guild = guild_of(ctx)
    await ctx.bot.settings.update(guild.id, helper_role_id=role.id)
    given, failed = await give_to_board_openers(ctx.bot, guild, role, ctx.channel)
    settings = await ctx.bot.settings.get(guild.id)
    house = (
        None
        if settings.house_channel_id is None
        else guild.get_channel(settings.house_channel_id)
    )
    lines = [
        f"♪ {role.mention} is Wisp's helper role now. His mess, tantrum and "
        "lights off posts in his House ping it.",
        f"・Given to {given} of the members who opened /wisp board",
        *cannot_ping_line(role, house, guild.me),
    ]
    if failed:
        lines.append(_CANNOT_GIVE.format(role=role.mention))
    await reply(ctx, "\n".join(lines))


@helperrole.command(name="off")
async def helperrole_off(ctx: StaffContext) -> None:
    """Clear the helper role, so the House posts ping nobody."""
    await ctx.bot.settings.update(guild_of(ctx).id, helper_role_id=None)
    await reply(ctx, "♪ Wisp has no helper role now, so his House posts ping nobody.")


async def setup(bot: "WispBot") -> None:
    """Load the helper role command and register the help pings button."""
    bot.add_command(helperrole)
    bot.add_dynamic_items(HelpPingsButton)
