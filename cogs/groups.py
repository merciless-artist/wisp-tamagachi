"""The slash command groups the cogs attach their commands to.

`wisp` is the members' group. `wispadmin` holds only the slash forms of
`!wisp setup` and `!wisp faq`; every other staff command is typed.
"""

from typing import Final

import discord
from discord import app_commands

_GUILDS_ONLY: Final = app_commands.AppCommandContext(
    guild=True, dm_channel=False, private_channel=False
)
_GUILD_INSTALL: Final = app_commands.AppInstallationType(guild=True, user=False)

wisp = app_commands.Group(
    name="wisp",
    description="Play with Wisp.",
    guild_only=True,
    allowed_contexts=_GUILDS_ONLY,
    allowed_installs=_GUILD_INSTALL,
)
play = app_commands.Group(name="play", description="Play games with Wisp.", parent=wisp)
wispadmin = app_commands.Group(
    name="wispadmin",
    description="Staff settings for Wisp.",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),
    allowed_contexts=_GUILDS_ONLY,
    allowed_installs=_GUILD_INSTALL,
)


def require_guild(interaction: discord.Interaction) -> int:
    """Return the id of the guild an interaction came from.

    Raises:
        app_commands.NoPrivateMessage: The interaction is not in a guild.
    """
    if interaction.guild_id is None:
        raise app_commands.NoPrivateMessage()
    return interaction.guild_id
