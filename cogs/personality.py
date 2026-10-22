"""Personality: Wisp's answer to compliments in his House."""

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

import discord
from discord.ext import commands

from cogs.announce import ASSETS_DIR
from wisp.life import Mood, mood
from wisp.lines import Moment
from wisp.rules import COMPLIMENT_COOLDOWN

if TYPE_CHECKING:
    from app import WispBot

FALLBACK_GIF_URL: Final = "https://i.imgur.com/G0SZAsT.gif"
_NO_PING: Final = discord.AllowedMentions.none()

# Whole words and phrases only, so "bestie" and "sweetest" are not compliments.
COMPLIMENTS: Final = (
    "cute",
    "adorable",
    "love you",
    "best",
    "good boy",
    "sweet",
    "amazing",
    "precious",
)
_COMPLIMENT: Final = re.compile(
    r"(?<!\w)(?:"
    + "|".join(r"\s+".join(map(re.escape, phrase.split())) for phrase in COMPLIMENTS)
    + r")(?!\w)",
    re.IGNORECASE,
)

# ---
# Listener
# ---


class Personality(commands.Cog):
    """Answers compliments aimed at Wisp with "no u", or a hangry line."""

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self._last_answer: dict[int, datetime] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Answer a compliment to Wisp in his House, at most once per cooldown.

        The message must come from a member in the House channel or a thread in
        it, and either mention Wisp or reply to one of his messages. A hangry
        Wisp answers with a line; otherwise he sends ASSETS/no_u.gif, or its
        link when the file is missing. He answers with no life, or one that is
        not alive, as well: he is still cute.
        """
        guild = message.guild
        if guild is None or message.author.bot:
            return
        if _COMPLIMENT.search(message.content) is None:
            return
        settings = await self.bot.settings.get(guild.id)
        if not _in_house(message, settings.house_channel_id):
            return
        if self._cooling_down(message):
            return
        if not await self._aimed_at_wisp(message):
            return
        self._last_answer[message.channel.id] = message.created_at
        try:
            await message.reply(
                **await self._answer(guild.id),
                mention_author=False,
                allowed_mentions=_NO_PING,
            )
        except discord.DiscordException as error:
            await self.bot.report_error(guild, "answering a compliment", error)

    def _cooling_down(self, message: discord.Message) -> bool:
        last = self._last_answer.get(message.channel.id)
        return last is not None and message.created_at - last < COMPLIMENT_COOLDOWN

    async def _aimed_at_wisp(self, message: discord.Message) -> bool:
        """Whether the message mentions Wisp or replies to one of his messages."""
        if self.bot.user in message.mentions:
            return True
        reference = message.reference
        if reference is None or reference.message_id is None:
            return False
        replied_to = reference.resolved
        if replied_to is None:
            try:
                replied_to = await message.channel.fetch_message(reference.message_id)
            except discord.NotFound:
                return False
        return (
            isinstance(replied_to, discord.Message)
            and replied_to.author == self.bot.user
        )

    async def _answer(self, guild_id: int) -> dict[str, Any]:
        """The `reply` arguments for Wisp's answer: a line, the GIF or its link."""
        life = await self.bot.lives.current(guild_id)
        if life is not None and mood(life) is Mood.HANGRY:
            line = self.bot.lines.pick(Moment.COMPLIMENT_HANGRY, Mood.HANGRY)
            return {"content": line}
        gif = ASSETS_DIR / "no_u.gif"
        if gif.is_file():
            return {"file": discord.File(gif)}
        return {"content": FALLBACK_GIF_URL}


def _in_house(message: discord.Message, house_id: int | None) -> bool:
    """Whether a message is in Wisp's House or in a thread inside it."""
    channel = message.channel
    parent_id = channel.parent_id if isinstance(channel, discord.Thread) else None
    return house_id is not None and house_id in (channel.id, parent_id)


async def setup(bot: "WispBot") -> None:
    """Load the personality cog."""
    await bot.add_cog(Personality(bot))
