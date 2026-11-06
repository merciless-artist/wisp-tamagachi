"""Talking in Wisp's House: answers, chiming in and the Poke Wisp button."""

import asyncio
import logging
import random
import re
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord
import pymysql
from discord.ext import commands

from ai.chain import ProviderError
from ai.prompt import Prompt
from cogs.announce import post_in_house
from cogs.assets import nap_image
from cogs.channels import where_of
from cogs.chores import wake_by_poke
from cogs.groups import require_guild
from cogs.pictures import art_kwargs, sick_talk_image
from cogs.players import (
    EXPECTED_FAILURES,
    bot_of,
    credit_chat,
    credit_poke,
    maybe_meet,
    report_failure,
    say_privately,
)
from cogs.speech import POKE_ID, ai_reply, dances, expressions, poke_button
from cogs.staff import is_command
from db.players import Player
from wisp.bond import tier_for
from wisp.chores import is_napping
from wisp.life import Life, Sickness, mood, sickness
from wisp.lines import Moment
from wisp.rules import (
    CHIME_IN_CHANCE,
    CHIME_IN_GAP,
    CONTEXT_LINE_CHARS,
    VISION_EMBED_WAIT,
    VISION_TYPES,
)
from wisp.text import strip_emoji
from wisp.voice import (
    EGG_EXPRESSION,
    EMOJI_NAME_PATTERN,
    TRACK_DROP,
    ChatLine,
    Fed,
    OwnEmoji,
    PokeFlavor,
    Poker,
    Sight,
    Speaker,
    Talk,
    build_prompt,
    chimes_in,
    egg_prompt,
    feelings_of,
    keeps_notes,
    link_track_drop,
    own_emojis,
    poke_flavor,
    sick_hours,
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
_ROLE_MENTION: Final = re.compile(r"<@&\d+>")
_CHANNEL_MENTION: Final = re.compile(r"<#(\d+)>")
# Channel names open with an emoji and a divider, as in "⏪｜general-chat".
_NAME_DIVIDERS: Final = "｜|・-_ "
_CUSTOM_EMOJI: Final = re.compile(rf"<a?:({EMOJI_NAME_PATTERN}):\d+>")

# Stickers with a picture to show; a Lottie sticker is an animation file.
_STICKER_PICTURES: Final = frozenset(
    {
        discord.StickerFormatType.png,
        discord.StickerFormatType.apng,
        discord.StickerFormatType.gif,
    }
)

_LINK: Final = re.compile(r"https?://\S+")
# Embed types that are a picture; a link preview of a song or video is not.
_PICTURE_EMBEDS: Final = frozenset({"image", "gifv"})

_POKE_CONTEXT: Final = "the Poke Wisp button"
_POKE_BANNED: Final = "♪ Wisp isn't answering you right now."
_POKE_NOBODY: Final = "♪ There's nobody to poke right now."
_POKE_COOLING: Final = "♪ Give him a second."
_POKE_DONE: Final = "♪ You poked Wisp."

# ---
# Reading the chat
# ---


def _channel_name(
    guild: discord.Guild | None, channel_id: int, tracks_channel_id: int | None
) -> str:
    """How Wisp reads a channel link: the track drop as #track-drop, others as #name.

    The emoji and divider a name opens with are left out. A channel he can't
    see is dropped.
    """
    if channel_id == tracks_channel_id:
        return TRACK_DROP
    channel = None if guild is None else guild.get_channel(channel_id)
    if channel is None:
        return ""
    return f"#{strip_emoji(channel.name).lstrip(_NAME_DIVIDERS)}"


def _clean(
    message: discord.Message, wisp: discord.ClientUser, tracks_channel_id: int | None
) -> str:
    """The message's text on one line, without Discord markup.

    A mentioned member becomes their display name; Wisp's own mention and role
    mentions are dropped. A channel link becomes its name, so Wisp can read
    back where he sent people. Custom emojis become ":name:", the way Wisp
    writes his own.
    """
    names = {
        user.id: user.display_name for user in message.mentions if user.id != wisp.id
    }
    text = _MEMBER_MENTION.sub(
        lambda match: names.get(int(match.group(1)), ""), message.content
    )
    text = _CHANNEL_MENTION.sub(
        lambda match: _channel_name(
            message.guild, int(match.group(1)), tracks_channel_id
        ),
        _ROLE_MENTION.sub("", text),
    )
    return " ".join(_CUSTOM_EMOJI.sub(r":\1:", text).split())


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


def _picture_url(message: discord.Message) -> str | None:
    """The link to the first picture the message carries, or None.

    An image attachment comes first, then a sticker's image, then an embed's
    image or thumbnail: Tenor and Giphy links show up as embeds.
    """
    for attachment in message.attachments:
        kind = (attachment.content_type or "").split(";")[0].strip().lower()
        if kind in VISION_TYPES:
            return attachment.url
    for sticker in message.stickers:
        if sticker.format in _STICKER_PICTURES:
            return sticker.url
    for embed in message.embeds:
        if embed.type not in _PICTURE_EMBEDS:
            continue
        for part in (embed.image, embed.thumbnail):
            if (link := part.proxy_url or part.url) is not None:
                return link
    return None


async def _with_late_embeds(message: discord.Message) -> discord.Message | None:
    """The message as it is after VISION_EMBED_WAIT, or None if it can't be read.

    Discord often adds the embed of a pasted GIF link in an edit after the
    message is posted, so the one `on_message` saw may not have it yet.
    """
    await asyncio.sleep(VISION_EMBED_WAIT.total_seconds())
    try:
        return await message.channel.fetch_message(message.id)
    except discord.HTTPException:
        return None


async def _sight(bot: "WispBot", message: discord.Message) -> Sight | None:
    """What the picture in the message shows, or None if it carries no picture.

    A message with a link but no picture yet is read again once, since its embed
    may still be on its way. A picture that can't be read is logged, not
    posted, and comes back as one Wisp couldn't see.
    """
    link = _picture_url(message)
    if link is None and _LINK.search(message.content):
        refreshed = await _with_late_embeds(message)
        link = None if refreshed is None else _picture_url(refreshed)
    if link is None:
        return None
    try:
        return Sight(await bot.vision.describe(link))
    except ProviderError as error:
        log.warning("Could not read a picture in guild %s: %s", message.guild, error)
        return Sight(None)


async def _reply(
    bot: "WispBot", message: discord.Message, text: str, image: Path | None = None
) -> None:
    """Reply to `message` with `text`, and `image` when given.

    A picture Discord refuses is dropped: the words are sent again without it
    and the refusal is reported once per streak.
    """
    if image is None:
        await _send_reply(message, text, None)
        return
    guild_id = message.guild.id if message.guild is not None else 0
    key = (guild_id, "reply picture")
    try:
        await _send_reply(message, text, image)
    except discord.NotFound:
        raise
    except discord.HTTPException as error:
        await _send_reply(message, text, None)
        if key not in bot.failing_displays:
            bot.failing_displays.add(key)
            await bot.report_error(
                message.guild,
                "attaching the sick reply picture",
                error,
                where=message.channel,
            )
        return
    bot.failing_displays.discard(key)


async def _send_reply(message: discord.Message, text: str, image: Path | None) -> None:
    art = None if image is None else discord.File(image)
    try:
        await message.reply(
            text,
            mention_author=False,
            allowed_mentions=_NO_PING,
            **art_kwargs("file", art),
        )
    finally:
        if art is not None:
            art.close()


def _sick_moment(life: Life, level: Talk) -> Moment | None:
    """The canned line set that says he is sick and with what, or None if he is well.

    Monster Pox wins over a cold; a Baby says it in baby words.
    """
    baby = level is Talk.BABY
    match sickness(life):
        case Sickness.POX:
            return Moment.POX_BABY_TALK if baby else Moment.POX_TALK
        case Sickness.COLD:
            return Moment.COLD_BABY_TALK if baby else Moment.COLD_TALK
        case None:
            return None


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


async def _track_drop(bot: "WispBot", guild: discord.Guild | None) -> str | None:
    """The track drop's channel link, or None when it isn't set or can't be seen."""
    if guild is None:
        return None
    channel_id = (await bot.settings.get(guild.id)).tracks_channel_id
    channel = None if channel_id is None else guild.get_channel(channel_id)
    return None if channel is None else channel.mention


async def _prompt(
    bot: "WispBot",
    guild_id: int,
    life: Life,
    level: Talk,
    player: Player,
    name: str,
    chat: Sequence[ChatLine],
    text: str | None,
    now: datetime,
    *,
    poked: PokeFlavor | None = None,
    emojis: Sequence[OwnEmoji] = (),
    track_drop: bool = False,
    sight: Sight | None = None,
) -> Prompt:
    """The prompt for Wisp's answer, in the voice for `level`.

    `text` is what the member said to him, or None for a poke, which `poked`
    flavors. `emojis` are the emojis of his that `text` used. `track_drop`
    says whether he can send people to the track drop. `sight` is the picture
    that came with `text`. A hatched Wisp knows how many tracks the member fed
    him on the UTC day of `now`.
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
    speaker = Speaker(
        name,
        tier_for(player.bond),
        tuple(notes),
        player.pickle_stance,
        await bot.activity_log.tracks_fed_today(guild_id, player.user_id, now),
    )
    return build_prompt(
        life.stage,
        mood(life),
        speaker,
        chat,
        text,
        expressions=expressions(bot, life.stage),
        dances=dances(bot, life.stage),
        poked=poked,
        own_emojis=emojis,
        feelings=feelings_of(life, now),
        hours_left=sick_hours(life),
        track_drop=track_drop,
        sight=sight,
    )


# ---
# Listener
# ---


class Conversation(commands.Cog):
    """Wisp in his House: he answers when spoken to and sometimes chimes in.

    Talking to him earns no bond. A member's first three mentions of the UTC
    day each fill his Wellbeing and their first three pokes his Mood; the
    day's first credit of either kind also earns a Vault point.
    The recent chat and the talk cooldown live in `bot.talk`, shared with pokes.
    """

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self.rng = random.Random()
        self._chimed_at: dict[int, datetime] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Remember a line said in Wisp's House, then answer it or maybe chime in.

        Only the House channel itself counts, not its threads or the Studio's
        posts, so Burrito's post is left to Burrito. Every line, Wisp's own
        included, joins the recent chat; bots are never answered and never
        count as the House stirring. A staff command is not talk: it is not
        heard, answered or chimed in on.
        """
        received = time.monotonic()
        guild = message.guild
        if guild is None or is_command(message.content):
            return
        settings = await self.bot.settings.get(guild.id)
        wisp = self.bot.user
        if message.channel.id != settings.house_channel_id or wisp is None:
            return
        text = _clean(message, wisp, settings.tracks_channel_id)
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
        if is_napping(life):
            await self._snore(message, guild, life)
            return
        credited = False
        try:
            credited = await credit_chat(self.bot, guild.id, message.author, now)
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
        if credited:
            await _meet_after_chat(
                self.bot, guild.id, guild, message.author, _CONTEXT, message.channel
            )

    async def _snore(
        self, message: discord.Message, guild: discord.Guild, life: Life
    ) -> None:
        """Answer a mention with a sleepy noise: no AI, no credit."""
        try:
            await _reply(
                self.bot, message, self.bot.lines.pick(Moment.NAP_TALK, mood(life))
            )
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
        emojis = own_emojis(_CUSTOM_EMOJI.findall(message.content), bot.emojis_by_name)
        track_drop = await _track_drop(bot, guild)
        async with message.channel.typing():
            prompt = await _prompt(
                bot,
                guild.id,
                life,
                level,
                player,
                player.name or message.author.display_name,
                earlier,
                text,
                now,
                emojis=emojis,
                track_drop=track_drop is not None,
                sight=None if level is Talk.EGG else await _sight(bot, message),
            )
            reply = await ai_reply(bot, guild, prompt)
        picture = sick_talk_image(life, bot.talk.rng)
        if reply is None:
            moment = _sick_moment(life, level) or _FALLBACK[level]
            await _reply(bot, message, bot.lines.pick(moment, mood(life)), picture)
            return
        await _reply(bot, message, link_track_drop(reply.text, track_drop), picture)
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
        if is_napping(life):
            return
        if (await self.bot.players.get(guild.id, message.author.id)).is_banned(now):
            return
        if not self._chime_in_due(guild.id, now):
            return
        self._chimed_at[guild.id] = now
        track_drop = await _track_drop(self.bot, guild)
        prompt = build_prompt(
            life.stage,
            mood(life),
            None,
            chat,
            None,
            expressions=expressions(self.bot, life.stage),
            dances=dances(self.bot, life.stage),
            feelings=feelings_of(life, now),
            hours_left=sick_hours(life),
            track_drop=track_drop is not None,
        )
        reply = await ai_reply(self.bot, guild, prompt)
        if reply is None:
            return
        try:
            await message.channel.send(
                link_track_drop(reply.text, track_drop), allowed_mentions=_NO_PING
            )
        except discord.HTTPException as error:
            await self.bot.report_error(guild, _CONTEXT, error, where=message.channel)
            return
        await self.bot.wisp_lunchbox.record_expressions(guild.id, reply.expressions)


# ---
# The Poke Wisp button
# ---


async def _poke(interaction: discord.Interaction) -> None:
    """Poke Wisp: tag who poked him in the House, with his reaction.

    Banned members, a poke with nobody alive to take it and a member still
    within TALK_COOLDOWN of their last answer are told privately instead. A
    poke on a napping Wisp wakes him cranky: it earns no credit and he answers
    waking up. The time from the press to the House post is logged.
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
    woken = await wake_by_poke(bot, guild_id, user.id, now)
    credited = False
    if woken is None:
        try:
            credited = await credit_poke(bot, guild_id, user, now)
        except pymysql.err.Error as error:
            await bot.report_error(
                interaction.guild, _POKE_CONTEXT, error, where=where_of(interaction)
            )
    quiet_for = talk.quiet_for(guild_id, now)
    streak = talk.poke(guild_id, user.id, now)
    flavor = poke_flavor(mood(life), streak, quiet_for, talk.rng)
    if woken is not None:
        life = woken
        flavor = PokeFlavor.WOKE_UP
    talk.stir(guild_id, now)
    name = player.name or user.display_name
    reaction = await _reaction(interaction, life, level, player, name, flavor, now)
    poked = "the egg" if level is Talk.EGG else "Wisp"
    image = (
        nap_image(life.stage)
        if flavor is PokeFlavor.WOKE_UP
        else sick_talk_image(life, talk.rng)
    )
    await post_in_house(
        bot, guild_id, f"♪ <@{user.id}> poked {poked}\n{reaction}", image, ping=user.id
    )
    log.info(
        "Answered a poke in guild %d in %.1f s", guild_id, time.monotonic() - received
    )
    await say_privately(interaction, _POKE_DONE)
    if credited:
        await _meet_after_chat(
            bot, guild_id, interaction.guild, user, _POKE_CONTEXT, where_of(interaction)
        )


async def _meet_after_chat(
    bot: "WispBot",
    guild_id: int,
    guild: discord.Guild | None,
    member: discord.User | discord.Member,
    context: str,
    where: discord.abc.Messageable | None,
) -> None:
    """Let Wisp meet a member whose chat credit was just given.

    A failure is reported as `context` and never stops the answer.
    """
    try:
        await maybe_meet(bot, guild_id, member.id, display_name=member.display_name)
    except pymysql.err.Error as error:
        await bot.report_error(guild, context, error, where=where)


async def _reaction(
    interaction: discord.Interaction,
    life: Life,
    level: Talk,
    player: Player,
    name: str,
    flavor: PokeFlavor,
    now: datetime,
) -> str:
    """Wisp's reaction to a poke from his AI voice, or a canned one when it fails.

    It keeps only the expressions a hatched Wisp used.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    chat = bot.talk.chat(guild_id)
    track_drop = await _track_drop(bot, interaction.guild)
    prompt = await _prompt(
        bot,
        guild_id,
        life,
        level,
        player,
        name,
        chat,
        None,
        now,
        poked=flavor,
        track_drop=track_drop is not None,
    )
    reply = await ai_reply(bot, interaction.guild, prompt)
    if reply is not None:
        if level is not Talk.EGG:
            await bot.wisp_lunchbox.record_expressions(guild_id, reply.expressions)
        return link_track_drop(reply.text, track_drop)
    if level is Talk.EGG:
        return bot.lines.pick(Moment.EGG_POKE, mood(life))
    if (sick := _sick_moment(life, level)) is not None:
        return bot.lines.pick(sick, mood(life))
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
