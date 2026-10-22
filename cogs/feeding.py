"""Feeding: tracks shared in the track drop feed Wisp and are forwarded to Mealtime."""

from datetime import datetime
from typing import TYPE_CHECKING, Final

import discord
from discord.ext import commands

from cogs.announce import post_events
from cogs.players import maybe_meet
from cogs.studio import StudioError, studio_thread
from db.activity import InteractionKind
from wisp.bond import meal_grant
from wisp.life import Event, Mood, feed, is_over, mood
from wisp.lines import Moment
from wisp.links import Track, TrackKind, find_track
from wisp.rules import BOND_PER_VIIBR_TRACK, MEAL_POINTS

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_MOOD_EMOJIS: Final = {Mood.HAPPY: "wisp_happy", Mood.HANGRY: "wisp_hangry"}

# ---
# Rules for who counts
# ---


def _in_tracks_channel(message: discord.Message, tracks_channel_id: int | None) -> bool:
    """Whether a message is in the track drop or in a thread/post inside it."""
    channel = message.channel
    parent_id = channel.parent_id if isinstance(channel, discord.Thread) else None
    return tracks_channel_id is not None and tracks_channel_id in (
        channel.id,
        parent_id,
    )


# ---
# Listener
# ---


class Feeding(commands.Cog):
    """Turns tracks posted by qualifying members into meals for Wisp."""

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Feed Wisp from a new message in the track drop, if it qualifies.

        Only the first valid track link in a message counts, each track counts
        once ever, and the post itself is never reacted to, edited or replied to.
        Anything that does not qualify is ignored without a word.
        """
        guild = message.guild
        author = message.author
        if guild is None or author.bot or not isinstance(author, discord.Member):
            return
        settings = await self.bot.settings.get(guild.id)
        if not _in_tracks_channel(message, settings.tracks_channel_id):
            return
        track = find_track(message.content)
        if track is None:
            return
        qualifying = await self.bot.settings.roles(guild.id)
        if qualifying.isdisjoint(role.id for role in author.roles):
            return
        now = discord.utils.utcnow()
        player = await self.bot.players.get(guild.id, author.id)
        if player.activated_at is None or player.is_banned(now):
            return
        fed = await self._feed(guild.id, author.id, track, message.id, now)
        if fed is None:
            return
        events, feeling = fed
        name = player.name or author.display_name
        await self._forward(guild, author, track, name, feeling)
        await post_events(self.bot, guild.id, events)
        await maybe_meet(
            self.bot, guild.id, author.id, display_name=author.display_name
        )

    async def _feed(
        self, guild_id: int, user_id: int, track: Track, message_id: int, now: datetime
    ) -> tuple[list[Event], Mood] | None:
        """Record the feed and apply it to Wisp; None when nothing was fed."""
        bot = self.bot
        async with bot.guild_lock(guild_id):
            if (await bot.players.get(guild_id, user_id)).is_banned(now):
                return None
            life = await bot.lives.current(guild_id)
            if life is None or life.id is None or is_over(life):
                return None
            eaten = await bot.activity_log.meal_points_today(guild_id, user_id, now)
            grant = meal_grant(eaten, MEAL_POINTS[track.kind])
            if grant == 0:
                return None
            if not await bot.activity_log.record_feed(
                guild_id, life.id, user_id, track, grant, message_id, now
            ):
                return None
            bond = BOND_PER_VIIBR_TRACK if track.kind is TrackKind.VIIBR else 0
            await bot.activity_log.record_interaction(
                guild_id, life.id, user_id, InteractionKind.FEED, bond, grant, now
            )
            await bot.players.add_points(guild_id, user_id, grant)
            if bond:
                await bot.players.add_bond(guild_id, user_id, bond)
            events = feed(life, grant, user_id, now)
            await bot.lives.save(guild_id, life)
            return events, mood(life)

    async def _forward(
        self,
        guild: discord.Guild,
        author: discord.Member,
        track: Track,
        name: str,
        feeling: Mood,
    ) -> None:
        """Post the track and Wisp's reaction in Mealtime; failures go to staff."""
        reaction = self.bot.lines.pick(Moment.TRACK_FED, feeling, name=name)
        emoji = self.bot.emoji(_MOOD_EMOJIS[feeling])
        text = (
            f"♪ {author.mention} fed Wisp ・ {track.url}\n"
            f"{f'{emoji} ' if emoji else ''}{reaction}"
        )
        try:
            thread = await studio_thread(self.bot, guild.id, "mealtime_thread_id")
            await thread.send(text, allowed_mentions=_NO_PING)
        except (discord.DiscordException, StudioError) as error:
            await self.bot.report_error(guild, "forwarding a track to Mealtime", error)


async def setup(bot: "WispBot") -> None:
    """Load the feeding cog."""
    await bot.add_cog(Feeding(bot))
