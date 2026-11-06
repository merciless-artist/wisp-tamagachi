"""Boards: the Status and Leaderboard posts are for their own use, not for chat.

The posts stay unlocked, since a locked post's buttons and menus don't work
for members, so Wisp deletes what members type there instead.
"""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class Board:
    """A post kept free of chat: its title and what it is just for."""

    title: str
    purpose: str


_STATUS: Final = Board("Status", "buttons")
_LEADERBOARD: Final = Board("Leaderboard", "the leaderboard")


def board_for(settings: Settings, channel_id: int) -> Board | None:
    """The board whose post `channel_id` is, or None."""
    boards = {
        settings.status_thread_id: _STATUS,
        settings.vault_thread_id: _LEADERBOARD,
    }
    return boards.get(channel_id)


def board_notice(settings: Settings, board: Board) -> str:
    """What Wisp says when he deletes chat from a board."""
    notice = f"♪ This post is just for {board.purpose}."
    if settings.house_channel_id is None:
        return notice
    return f"{notice} Come chat in <#{settings.house_channel_id}>."


# ---
# Listener
# ---


class Boards(commands.Cog):
    """Deletes what members type in the Status and Leaderboard posts."""

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
        board = board_for(settings, message.channel.id)
        if board is None:
            return
        if isinstance(author, discord.Member) and await is_staff(self.bot, author):
            return
        context = f"keeping the {board.title} post for {board.purpose}"
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
                board_notice(settings, board),
                allowed_mentions=_NO_PING,
                delete_after=BOARD_NOTICE_LIFETIME.total_seconds(),
            )
        except discord.HTTPException as error:
            await self.bot.report_error(guild, context, error, where=message.channel)


async def setup(bot: "WispBot") -> None:
    """Load the boards cog."""
    await bot.add_cog(Boards(bot))
