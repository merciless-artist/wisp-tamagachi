"""Boards: the Status and ViiBR Vault posts are for their buttons, not for chat.

The posts stay unlocked, since a locked post's buttons and menus don't work
for members, so Wisp deletes what members type there instead.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Final

import discord
from discord.ext import commands

from cogs.staff import is_staff
from db.settings import Settings
from wisp.rules import BOARD_NOTICE_LIFETIME

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_CHAT: Final = (discord.MessageType.default, discord.MessageType.reply)
_JUST_BUTTONS: Final = "♪ This post is just for buttons."


def board_title(settings: Settings, channel_id: int) -> str | None:
    """The title of the board whose post `channel_id` is, or None."""
    boards = {
        settings.status_thread_id: "Status",
        settings.vault_thread_id: "ViiBR Vault",
    }
    return boards.get(channel_id)


def board_notice(settings: Settings) -> str:
    """What Wisp says when he deletes chat from a board."""
    if settings.house_channel_id is None:
        return _JUST_BUTTONS
    return f"{_JUST_BUTTONS} Come chat in <#{settings.house_channel_id}>."


# ---
# Listener
# ---


class Boards(commands.Cog):
    """Deletes what members type in the Status and ViiBR Vault posts."""

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self._notice_until: dict[int, datetime] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Delete a member's message in a board and say what the post is for.

        Bots, staff and Discord's own notices are left alone. The notice
        deletes itself after BOARD_NOTICE_LIFETIME, and while one is showing
        in a post no second one is sent, so a burst of messages gets one.
        A failure is posted in the post.
        """
        guild = message.guild
        author = message.author
        if guild is None or author.bot or message.type not in _CHAT:
            return
        settings = await self.bot.settings.get(guild.id)
        title = board_title(settings, message.channel.id)
        if title is None:
            return
        if isinstance(author, discord.Member) and await is_staff(self.bot, author):
            return
        context = f"keeping the {title} post for buttons"
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.HTTPException as error:
            await self.bot.report_error(guild, context, error, where=message.channel)
            return
        now = discord.utils.utcnow()
        if self._notice_until.get(message.channel.id, now) > now:
            return
        self._notice_until[message.channel.id] = now + BOARD_NOTICE_LIFETIME
        try:
            await message.channel.send(
                board_notice(settings),
                allowed_mentions=_NO_PING,
                delete_after=BOARD_NOTICE_LIFETIME.total_seconds(),
            )
        except discord.HTTPException as error:
            await self.bot.report_error(guild, context, error, where=message.channel)


async def setup(bot: "WispBot") -> None:
    """Load the boards cog."""
    await bot.add_cog(Boards(bot))
