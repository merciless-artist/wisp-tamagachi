"""Talking in Wisp's House: he answers members and sometimes chimes in, by stage."""

import random
import re
from collections import deque
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Final

import discord
from discord.ext import commands

from cogs.speech import ai_reply, expressions
from db.players import Player
from wisp.bond import tier_for
from wisp.life import Life, mood
from wisp.lines import Moment
from wisp.rules import (
    CHIME_IN_CHANCE,
    CHIME_IN_GAP,
    CONTEXT_LINE_CHARS,
    CONTEXT_LINES,
    TALK_COOLDOWN,
)
from wisp.voice import (
    EGG_EXPRESSION,
    ChatLine,
    Fed,
    Poker,
    Speaker,
    Talk,
    build_prompt,
    chimes_in,
    egg_prompt,
    keeps_notes,
    talk_level,
)

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_CONTEXT: Final = "talking in Wisp's House"
_FALLBACK: Final = {
    Talk.EGG: Moment.EGG_POKE,
    Talk.BABY: Moment.BABY_TALK,
    Talk.AI: Moment.CHAT_FALLBACK,
}
_MEMBER_MENTION: Final = re.compile(r"<@!?(\d+)>")
_ROLE_OR_CHANNEL_MENTION: Final = re.compile(r"<(?:@&|#)\d+>")
_CUSTOM_EMOJI: Final = re.compile(r"<a?:(\w+):\d+>")

# ---
# Reading the chat
# ---


def _clean(message: discord.Message, wisp: discord.ClientUser) -> str:
    """The message's text on one line, without Discord markup.

    A mentioned member becomes their display name; Wisp's own mention and any
    other mention are dropped. Custom emojis become ":name:", the way Wisp
    writes his own.
    """
    names = {
        user.id: user.display_name for user in message.mentions if user.id != wisp.id
    }
    text = _MEMBER_MENTION.sub(
        lambda match: names.get(int(match.group(1)), ""), message.content
    )
    text = _CUSTOM_EMOJI.sub(r":\1:", _ROLE_OR_CHANNEL_MENTION.sub("", text))
    return " ".join(text.split())


def _aimed_at(message: discord.Message, wisp: discord.ClientUser) -> bool:
    """Whether the message mentions Wisp or his role, or replies to him."""
    if any(user.id == wisp.id for user in message.mentions):
        return True
    guild = message.guild
    if guild is not None and guild.self_role in message.role_mentions:
        return True
    reference = message.reference
    replied_to = reference.resolved if reference is not None else None
    return isinstance(replied_to, discord.Message) and replied_to.author.id == wisp.id


async def _reply(message: discord.Message, text: str) -> None:
    await message.reply(text, mention_author=False, allowed_mentions=_NO_PING)


# ---
# Listener
# ---


class Conversation(commands.Cog):
    """Wisp in his House: he answers when spoken to and sometimes chimes in.

    Talking to him earns no bond and no happiness, and leaves no interaction.
    """

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self.rng = random.Random()
        self._chat: dict[int, deque[ChatLine]] = {}
        self._answered_at: dict[tuple[int, int], datetime] = {}
        self._chimed_at: dict[int, datetime] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Remember a line said in Wisp's House, then answer it or maybe chime in.

        Only the House channel itself counts, not its threads. Every line,
        Wisp's own included, joins the recent chat; bots are never answered.
        """
        guild = message.guild
        if guild is None:
            return
        settings = await self.bot.settings.get(guild.id)
        wisp = self.bot.user
        if message.channel.id != settings.house_channel_id or wisp is None:
            return
        text = _clean(message, wisp)
        chat = self._chat.setdefault(guild.id, deque(maxlen=CONTEXT_LINES))
        earlier = tuple(chat)
        chat.append(ChatLine(message.author.display_name, text[:CONTEXT_LINE_CHARS]))
        if message.author.bot:
            return
        now = discord.utils.utcnow()
        if _aimed_at(message, wisp):
            await self._answer(message, guild, text, earlier, now)
        else:
            await self._maybe_chime_in(message, guild, tuple(chat), now)

    async def _answer(
        self,
        message: discord.Message,
        guild: discord.Guild,
        text: str,
        earlier: Sequence[ChatLine],
        now: datetime,
    ) -> None:
        """Answer someone talking to Wisp, as his stage allows.

        A member who was answered within TALK_COOLDOWN gets nothing. A failure
        to post is reported in the House.
        """
        life = await self.bot.lives.current(guild.id)
        level = talk_level(life)
        if life is None or level is Talk.SILENT:
            return
        player = await self.bot.players.get(guild.id, message.author.id)
        if player.is_banned(now):
            return
        key = (guild.id, player.user_id)
        last = self._answered_at.get(key)
        if last is not None and now - last < TALK_COOLDOWN:
            return
        self._answered_at[key] = now
        try:
            await self._talk(message, guild, life, level, player, text, earlier, now)
        except discord.HTTPException as error:
            await self.bot.report_error(guild, _CONTEXT, error, where=message.channel)

    async def _talk(
        self,
        message: discord.Message,
        guild: discord.Guild,
        life: Life,
        level: Talk,
        player: Player,
        text: str,
        earlier: Sequence[ChatLine],
        now: datetime,
    ) -> None:
        """Answer in Wisp's AI voice for `level`, or with its canned line on failure.

        The egg's answers keep nothing. From Baby on, a pickle stance in the
        answer is saved and the expressions it used count toward his favorite
        emoji; a note is saved only from Adult on.
        """
        bot = self.bot
        name = player.name or message.author.display_name
        remembers = keeps_notes(life.stage)
        if level is Talk.EGG:
            poker = Poker(name, await self._fed(guild.id, life, player.user_id))
            has_face = EGG_EXPRESSION in bot.emojis_by_name
            prompt = egg_prompt(life, poker, earlier, text, emoji=has_face)
        else:
            notes = (
                await bot.notes.recent(guild.id, player.user_id) if remembers else []
            )
            speaker = Speaker(
                name, tier_for(player.bond), tuple(notes), player.pickle_stance
            )
            prompt = build_prompt(
                life.stage,
                mood(life),
                speaker,
                earlier,
                text,
                expressions=expressions(bot),
            )
        async with message.channel.typing():
            reply = await ai_reply(bot, guild, prompt)
        if reply is None:
            await _reply(message, bot.lines.pick(_FALLBACK[level], mood(life)))
            return
        await _reply(message, reply.text)
        if level is Talk.EGG:
            return
        await bot.wisp_lunchbox.record_expressions(guild.id, reply.expressions)
        if reply.pickle_stance is not None:
            await bot.players.set_pickle_stance(
                guild.id, player.user_id, reply.pickle_stance
            )
        if remembers and reply.note is not None:
            await bot.notes.add(guild.id, player.user_id, reply.note, now)

    async def _fed(self, guild_id: int, life: Life, user_id: int) -> Fed:
        """How much the member has fed this life, next to its biggest feeder.

        Everyone tied for the most counts as having fed it most.
        """
        if life.id is None:
            return Fed.NOTHING
        log = self.bot.activity_log
        points = await log.fed_this_life(guild_id, life.id, user_id)
        if points == 0:
            return Fed.NOTHING
        ((_, most),) = await log.top_this_life(guild_id, life.id, 1)
        return Fed.MOST if points >= most else Fed.SOME

    def _chime_in_due(self, guild_id: int, now: datetime) -> bool:
        """Whether CHIME_IN_GAP has passed since this guild's last chime-in."""
        last = self._chimed_at.get(guild_id)
        return last is None or now - last >= CHIME_IN_GAP

    async def _maybe_chime_in(
        self,
        message: discord.Message,
        guild: discord.Guild,
        chat: Sequence[ChatLine],
        now: datetime,
    ) -> None:
        """Now and then, from Adult on, join the chat with one AI line.

        At most once per CHIME_IN_GAP per guild. The gap is checked again after
        the lookups, since another message may have chimed in meanwhile. Nothing
        is said when the AI fails. Only the expressions a posted line used are
        kept, toward his favorite emoji.
        """
        if not self._chime_in_due(guild.id, now) or (
            self.rng.random() >= CHIME_IN_CHANCE
        ):
            return
        life = await self.bot.lives.current(guild.id)
        if life is None or talk_level(life) is not Talk.AI or not chimes_in(life.stage):
            return
        if (await self.bot.players.get(guild.id, message.author.id)).is_banned(now):
            return
        if not self._chime_in_due(guild.id, now):
            return
        self._chimed_at[guild.id] = now
        prompt = build_prompt(
            life.stage, mood(life), None, chat, None, expressions=expressions(self.bot)
        )
        reply = await ai_reply(self.bot, guild, prompt)
        if reply is None:
            return
        try:
            await message.channel.send(reply.text, allowed_mentions=_NO_PING)
        except discord.HTTPException as error:
            await self.bot.report_error(guild, _CONTEXT, error, where=message.channel)
            return
        await self.bot.wisp_lunchbox.record_expressions(guild.id, reply.expressions)


async def setup(bot: "WispBot") -> None:
    """Load the conversation cog."""
    await bot.add_cog(Conversation(bot))
