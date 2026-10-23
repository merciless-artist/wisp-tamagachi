"""Channel helpers shared by the bot and its cogs."""

import discord


def in_channel(channel: object, channel_id: int | None) -> bool:
    """Whether `channel` is the channel `channel_id` or a thread or post inside it."""
    if channel_id is None:
        return False
    parent_id = channel.parent_id if isinstance(channel, discord.Thread) else None
    return channel_id in (getattr(channel, "id", None), parent_id)


def where_of(interaction: discord.Interaction) -> discord.abc.Messageable | None:
    """The channel or thread an interaction happened in, if Wisp can post there."""
    channel = interaction.channel
    return channel if isinstance(channel, discord.abc.Messageable) else None
