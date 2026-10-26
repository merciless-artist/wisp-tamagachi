"""Talking in Wisp's House: answers, chiming in and the Poke Wisp button."""

import logging
import random
import re
import time
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Final

import discord
import pymysql
from discord.ext import commands

from ai.prompt import Prompt
from cogs.announce import post_in_house
from cogs.assets import nap_image
from cogs.channels import where_of
from cogs.groups import require_guild
from cogs.players import (
    EXPECTED_FAILURES,
    bot_of,
    credit_chat,
    report_failure,
    say_privately,
)
from cogs.speech import POKE_ID, ai_reply, expressions, poke_button
from cogs.staff import is_command
from db.players import Player
from wisp.bond import tier_for
from wisp.life import Life, mood
from wisp.lines import Moment
from wisp.rules import CHIME_IN_CHANCE, CHIME_IN_GAP, CONTEXT_LINE_CHARS
from wisp.voice import (
    EGG_EXPRESSION,
    EMOJI_NAME_PATTERN,
    ChatLine,
    Fed,
    OwnEmoji,
    PokeFlavor,
    Poker,
    Speaker,
    Talk,
    build_prompt,
    chimes_in,
    egg_prompt,
    keeps_notes,
    own_emojis,
    poke_flavor,
    talk_level,
)

if TYPE_CHECKING:
    from app import WispBot

log = logging.getLogger("wisp")

_NO_PING: Final = discord.AllowedMentions.none()
_CONTEXT: Final = "talking in Wisp's House"
_FALLBACK: Final = {
    Talk.EGG: Moment.EGG_POKE,
    Talk.BABY: Moment.BABY_TALK,
    Talk.AI: Moment.CHAT_FALLBACK,
}
_MEMBER_MENTION: Final = re.compile(r"<@!?(\d+)>")
_ROLE_OR_CHANNEL_MENTION: Final = re.compile(r"<(?:@&|#)\d+>")
_CUSTOM_EMOJI: Final = re.compile(rf"<a?:({EMOJI_NAME_PATTERN}):\d+>")

_POKE_CONTEXT: Final = "the Poke Wisp button"
_POKE_BANNED: Final = "♪ Wisp isn't answering you right now."
_POKE_NOBODY: Final = "♪ There's nobody to poke right now."
_POKE_COOLING: Final = "♪ Give him a second."
_POKE_DONE: Final = "♪ You poked Wisp."

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
# Prompts
# ---


async def _fed(bot: "WispBot", guild_id: int, life: Life, user_id: int) -> Fed:
    """How much the member has fed this life, next to its biggest feeder.

    Everyone tied for the most counts as having fed it most.
    """
    if life.id is None:
        return Fed.NOTHING
    log = bot.activity_log
    points = await log.fed_this_life(guild_id, life.id, user_id)
    if points == 0:
        return Fed.NOTHING
    ((_, most),) = await log.top_this_life(guild_id, life.id, 1)
    return Fed.MOST if points >= most else Fed.SOME


async def _prompt(
    bot: "WispBot",
    guild_id: int,
    life: Life,
    level: Talk,
    player: Player,
    name: str,
    chat: Sequence[ChatLine],
    text: str | None,
    *,
    poked: PokeFlavor | None = None,
    emojis: Sequence[OwnEmoji] = (),
) -> Prompt:
    """The prompt for Wisp's answer, in the voice for `level`.

    `text` is what the member said to him, or None for a poke, which `poked`
    flavors. `emojis` are the emojis of his that `text` used.
    """
    if level is Talk.EGG:
        poker = Poker(name, await _fed(bot, guild_id, life, player.user_id))
        return egg_prompt(
            life,
            poker,
            chat,
            text or "",
            emoji=EGG_EXPRESSION in bot.emojis_by_name,
            poked=poked,
            own_emojis=emojis,
        )
    remembers = keeps_notes(life.stage)
    notes = await bot.notes.recent(guild_id, player.user_id) if remembers else []
    speaker = Speaker(name, tier_for(player.bond), tuple(notes), player.pickle_stance)
    return build_prompt(
        life.stage,
        mood(life),
        speaker,
        chat,
        text,
        expressions=expressions(bot, life.stage),
        poked=poked,
        own_emojis=emojis,
    )


# ---
# Listener
# ---


class Conversation(commands.Cog):
    """Wisp in his House: he answers when spoken to and sometimes chimes in.

    Talking to him earns no bond. A member's first mention or poke of the UTC
    day also records a chat, which makes him happy and earns a Vault point.
    The recent chat and the talk cooldown live in `bot.talk`, shared with pokes.
    """

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self.rng = random.Random()
        self._chimed_at: dict[int, datetime] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Remember a line said in Wisp's House, then answer it or maybe chime in.

        Only the House channel itself counts, not its threads. Every line,
        Wisp's own included, joins the recent chat; bots are never answered and
        never count as the House stirring. A staff command is not talk: it is
        not heard, answered or chimed in on.
        """
        received = time.monotonic()
        guild = message.guild
        if guild is None or is_command(message.content):
            return
        settings = await self.bot.settings.get(guild.id)
        wisp = self.bot.user
        if message.channel.id != settings.house_channel_id or wisp is None:
            return
        text = _clean(message, wisp)
        talk = self.bot.talk
        line = ChatLine(message.author.display_name, text[:CONTEXT_LINE_CHARS])
        earlier = talk.hear(guild.id, line)
        if message.author.bot:
            return
        now = discord.utils.utcnow()
        talk.stir(guild.id, now)
        if _aimed_at(message, wisp):
            await self._answer(message, guild, text, earlier, now, received)
        else:
            await self._maybe_chime_in(message, guild, talk.chat(guild.id), now)

    async def _answer(
        self,
        message: discord.Message,
        guild: discord.Guild,
        text: str,
        earlier: Sequence[ChatLine],
        now: datetime,
        received: float,
    ) -> None:
        """Answer someone talking to Wisp, as his stage allows.

        A member answered or poked through within TALK_COOLDOWN gets nothing. A
        failure to post is reported in the House. The time from receiving the
        message to posting the answer is logged.
        """
        life = await self.bot.lives.current(guild.id)
        level = talk_level(life)
        if life is None or level is Talk.SILENT:
            return
        player = await self.bot.players.get(guild.id, message.author.id)
        if player.is_banned(now):
            return
        if not self.bot.talk.take_turn(guild.id, player.user_id, now):
            return
        try:
            await credit_chat(self.bot, guild.id, message.author, life, now)
        except pymysql.err.Error as error:
            await self.bot.report_error(guild, _CONTEXT, error, where=message.channel)
        try:
            await self._talk(message, guild, life, level, player, text, earlier, now)
        except discord.HTTPException as error:
            await self.bot.report_error(guild, _CONTEXT, error, where=message.channel)
        else:
            log.info(
                "Answered a mention in guild %d in %.1f s",
                guild.id,
                time.monotonic() - received,
            )

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
        emojis = own_emojis(_CUSTOM_EMOJI.findall(message.content), bot.emojis_by_name)
        prompt = await _prompt(
            bot,
            guild.id,
            life,
            level,
            player,
            player.name or message.author.display_name,
            earlier,
            text,
            emojis=emojis,
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
        if keeps_notes(life.stage) and reply.note is not None:
            await bot.notes.add(guild.id, player.user_id, reply.note, now)

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
            life.stage,
            mood(life),
            None,
            chat,
            None,
            expressions=expressions(self.bot, life.stage),
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


# ---
# The Poke Wisp button
# ---


async def _poke(interaction: discord.Interaction) -> None:
    """Poke Wisp: post who poked him and his reaction in the House.

    Banned members, a poke with nobody alive to take it and a member still
    within TALK_COOLDOWN of their last answer are told privately instead. The
    time from the press to the House post is logged.
    """
    received = time.monotonic()
    await interaction.response.defer(ephemeral=True, thinking=True)
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    now = discord.utils.utcnow()
    talk = bot.talk
    player = await bot.players.get(guild_id, user.id)
    if player.is_banned(now):
        await say_privately(interaction, _POKE_BANNED)
        return
    life = await bot.lives.current(guild_id)
    level = talk_level(life)
    if life is None or level is Talk.SILENT:
        await say_privately(interaction, _POKE_NOBODY)
        return
    if not talk.take_turn(guild_id, user.id, now):
        await say_privately(interaction, _POKE_COOLING)
        return
    try:
        await credit_chat(bot, guild_id, user, life, now)
    except pymysql.err.Error as error:
        await bot.report_error(
            interaction.guild, _POKE_CONTEXT, error, where=where_of(interaction)
        )
    quiet_for = talk.quiet_for(guild_id, now)
    flavor = poke_flavor(mood(life), talk.poke(guild_id, now), quiet_for, now, talk.rng)
    talk.stir(guild_id, now)
    name = player.name or user.display_name
    reaction = await _reaction(interaction, life, level, player, name, flavor)
    poked = "the egg" if level is Talk.EGG else "Wisp"
    nap = nap_image(life.stage) if flavor is PokeFlavor.WOKE_UP else None
    await post_in_house(bot, guild_id, f"♪ {name} poked {poked}\n{reaction}", nap)
    log.info(
        "Answered a poke in guild %d in %.1f s", guild_id, time.monotonic() - received
    )
    await say_privately(interaction, _POKE_DONE)


async def _reaction(
    interaction: discord.Interaction,
    life: Life,
    level: Talk,
    player: Player,
    name: str,
    flavor: PokeFlavor,
) -> str:
    """Wisp's reaction to a poke from his AI voice, or a canned one when it fails.

    It keeps only the expressions a hatched Wisp used.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    chat = bot.talk.chat(guild_id)
    prompt = await _prompt(
        bot, guild_id, life, level, player, name, chat, None, poked=flavor
    )
    reply = await ai_reply(bot, interaction.guild, prompt)
    if reply is not None:
        if level is not Talk.EGG:
            await bot.wisp_lunchbox.record_expressions(guild_id, reply.expressions)
        return reply.text
    if level is Talk.EGG:
        return bot.lines.pick(Moment.EGG_POKE, mood(life))
    return bot.lines.pick(Moment.POKED, mood(life), name=name)


class PokeButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(POKE_ID),
):
    """The Poke Wisp button, on the status card and the House's new-egg posts.

    Its custom id is fixed, so the button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(poke_button())

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "PokeButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Poke Wisp, reporting a failure where the button was pressed."""
        try:
            await _poke(interaction)
        except EXPECTED_FAILURES as error:
            await report_failure(interaction, _POKE_CONTEXT, error)


async def setup(bot: "WispBot") -> None:
    """Load the conversation cog."""
    await bot.add_cog(Conversation(bot))
