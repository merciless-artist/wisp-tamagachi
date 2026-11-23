"""Rooms: each member's one private thread off Wisp's House.

A member's games and their pinned Snack Pack live in their room. It is made
once, reused forever, and made again only when it was deleted or sits under
an old House.
"""

import asyncio
from typing import TYPE_CHECKING

import discord

from wisp.rules import ROOM_ARCHIVE_MINUTES, ROOM_NAME_MAX
from wisp.text import clip

if TYPE_CHECKING:
    from app import WispBot

# ---
# Finding and making rooms
# ---


class RoomError(LookupError):
    """Wisp's House is not set, cannot be seen or is not a text channel.

    Its message can be shown to the member.
    """


def room_name(name: str) -> str:
    """The room's thread name for a member Wisp calls `name`, cut to fit Discord."""
    return clip(f"♪ {name}'s room", ROOM_NAME_MAX)


def _welcome(member: discord.abc.User) -> str:
    return "\n".join(
        [
            f"♪ This is your room with Wisp, {member.mention}.",
            "・Your games with him happen here.",
            "・Your Snack Pack is pinned here. "
            "Open it any time with /wisp snackpack.",
        ]
    )


async def _house(bot: "WispBot", guild: discord.Guild) -> discord.TextChannel:
    """The guild's House, where rooms are made.

    Raises:
        RoomError: The House is not set, cannot be seen or is not a text channel.
    """
    house_id = (await bot.settings.get(guild.id)).house_channel_id
    house = None if house_id is None else guild.get_channel_or_thread(house_id)
    if not isinstance(house, discord.TextChannel):
        raise RoomError("Wisp's House isn't set up, so he can't open your room yet.")
    return house


async def _stored_room(
    bot: "WispBot", house_id: int, thread_id: int | None
) -> discord.Thread | None:
    """The stored room when it still exists under the House `house_id`, else None."""
    if thread_id is None:
        return None
    try:
        channel = await bot.fetch_channel(thread_id)
    except discord.NotFound:
        return None
    if not isinstance(channel, discord.Thread) or channel.parent_id != house_id:
        return None
    return channel


async def open_room(
    bot: "WispBot", guild: discord.Guild, member: discord.abc.User
) -> discord.Thread:
    """Return the member's room, ready to post in, making it when needed.

    A stored room that is archived is reopened. One that was deleted, or sits
    under an old House, is made again: a private thread off the House that
    only the member is added to, with a welcome post. Two calls at once make
    one room. Discord's refusals are raised as they come.

    Raises:
        RoomError: The House is not set, cannot be seen or is not a text channel.
    """
    key = (guild.id, member.id)
    async with bot.room_locks.setdefault(key, asyncio.Lock()):
        house = await _house(bot, guild)
        player = await bot.players.get(guild.id, member.id)
        room = await _stored_room(bot, house.id, player.room_thread_id)
        if room is not None:
            return await room.edit(archived=False) if room.archived else room
        room = await house.create_thread(
            name=room_name(player.name or member.display_name),
            type=discord.ChannelType.private_thread,
            invitable=False,
            auto_archive_duration=ROOM_ARCHIVE_MINUTES,
        )
        await room.add_user(member)
        await room.send(
            _welcome(member),
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=[member], replied_user=False
            ),
        )
        await bot.players.set_room(guild.id, member.id, room.id)
        return room


async def rename_room(bot: "WispBot", guild_id: int, user_id: int, name: str) -> None:
    """Rename the member's room for the name Wisp now calls them.

    A room that is not stored or no longer reachable is left alone; it gets
    the right name when it is made again. A failure is reported, never raised.
    """
    guild = bot.get_guild(guild_id)
    try:
        settings = await bot.settings.get(guild_id)
        player = await bot.players.get(guild_id, user_id)
        if settings.house_channel_id is None:
            return
        room = await _stored_room(bot, settings.house_channel_id, player.room_thread_id)
        if room is not None:
            await room.edit(name=room_name(name), archived=False)
    except discord.HTTPException as error:
        await bot.report_error(guild, "renaming a room", error)
