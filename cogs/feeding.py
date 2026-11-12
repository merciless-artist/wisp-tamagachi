"""Feeding: tracks shared in the track drop feed Wisp and are forwarded to Mealtime.

Staff set how many meal points each kind of track is worth with !wisp food. A
track that feeds him gets his reaction on the post; one that does not gets a
note in his House saying why.
"""

import random
from datetime import datetime
from typing import TYPE_CHECKING, Final

import aiohttp
import discord
from discord.ext import commands

from cogs.announce import post_events, post_in_house, say_in_mealtime, show_in_thread
from cogs.channels import in_channel
from cogs.players import (
    BLOCKER_REASONS,
    Blocker,
    blocker_reason,
    feeder_blocker,
    maybe_meet,
)
from cogs.staff import StaffContext, guild_of, is_command, reply, usage_line
from cogs.studio import TRACK_LABELS, rules_post
from db.activity import InteractionKind
from db.settings import meal_points
from wisp.bond import daily_meal_cap, meal_grant
from wisp.chores import schedule_mess
from wisp.life import Event, Life, Mood, feed, is_over, mood
from wisp.lines import Moment
from wisp.links import ShareLink, Track, TrackKind, find_track
from wisp.rules import BOND_PER_VIIBR_TRACK, FED_REACTION, MEAL_POINTS_MAX
from wisp.text import count, daily_reset

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_MOOD_EMOJIS: Final = {
    Mood.HAPPY: "wisp_happy",
    Mood.HANGRY: "wisp_hangry",
    Mood.LONELY: "wisp_sad",
}
_NO_WISP: Final = "there's no living Wisp to feed right now."
_REPEAT: Final = "that track was already fed."
_NO_SONG: Final = "that viibrmusic.com share link names no song."
_WORTHLESS: Final = "staff have set that kind of track to 0 meal points."


class NotFed(Exception):
    """The reason a track post did not feed Wisp, worded for the member."""


# ---
# Listener
# ---


class Feeding(commands.Cog):
    """Turns tracks posted by qualifying members into meals for Wisp.

    `rng` picks when the mess a fed track makes is due.
    """

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self.rng = random.Random()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Feed Wisp from a new message in the track drop, if it qualifies.

        Only the first valid track link in a message counts and each track
        counts once ever. A fed track gets Wisp's reaction; a track post that
        does not feed him gets one note in his House naming the member and the
        reason. Wisp never posts in the track drop, and chat and staff commands
        there are ignored. A viibrmusic.com share link counts as the song it
        names, which the site is asked for once the member qualifies, outside
        the guild lock.
        """
        guild = message.guild
        author = message.author
        if guild is None or author.bot or not isinstance(author, discord.Member):
            return
        if is_command(message.content):
            return
        found = find_track(message.content)
        if found is None:
            return
        settings = await self.bot.settings.get(guild.id)
        if not in_channel(message.channel, settings.tracks_channel_id):
            return
        now = discord.utils.utcnow()
        player = await self.bot.players.get(guild.id, author.id)
        blocker = await feeder_blocker(self.bot, guild.id, author, now)
        if blocker is not None:
            reason = await blocker_reason(self.bot, guild.id, blocker)
            await self._refuse(guild, author, reason)
            return
        track = (
            await self._resolve(guild, author, found)
            if isinstance(found, ShareLink)
            else found
        )
        if track is None:
            return
        points = meal_points(settings)[track.kind]
        try:
            events, feeling = await self._feed(
                guild.id, author.id, track, points, message.id, now
            )
        except NotFed as refusal:
            await self._refuse(guild, author, str(refusal))
            return
        await self._react(guild, message)
        name = player.name or author.display_name
        await self._forward(guild, author, track, name, feeling)
        await post_events(self.bot, guild.id, events)
        await maybe_meet(
            self.bot, guild.id, author.id, display_name=author.display_name
        )

    async def _resolve(
        self, guild: discord.Guild, member: discord.Member, link: ShareLink
    ) -> Track | None:
        """The song a share link names, or None when it names none.

        When viibrmusic.com cannot be reached the link is not fed, and the error
        goes to Wisp's House, since he never posts in the track drop. A link for
        no song is explained there too.
        """
        try:
            track = await self.bot.share_links.resolve(link)
        except (aiohttp.ClientError, TimeoutError) as error:
            await self.bot.report_error(
                guild, "checking a viibrmusic.com share link", error
            )
            return None
        if track is None:
            await self._refuse(guild, member, _NO_SONG)
        return track

    async def _refuse(
        self, guild: discord.Guild, member: discord.Member, reason: str
    ) -> None:
        """Tell Wisp's House why a member's track post did not feed him.

        The member is mentioned without a ping.
        """
        await post_in_house(
            self.bot,
            guild.id,
            f"♪ {member.mention} your track didn't feed Wisp: {reason}",
        )

    async def _react(self, guild: discord.Guild, message: discord.Message) -> None:
        """React to a fed track post with Wisp's emoji, when it is uploaded.

        A failed reaction goes to Wisp's House and never undoes the feed.
        """
        emoji = self.bot.app_emoji(FED_REACTION)
        if emoji is None:
            return
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException as error:
            await self.bot.report_error(guild, "reacting to a fed track", error)

    async def _feed(
        self,
        guild_id: int,
        user_id: int,
        track: Track,
        points: int,
        message_id: int,
        now: datetime,
    ) -> tuple[list[Event], Mood]:
        """Record a feed worth `points` and apply it.

        As much of it as fits under the member's daily meal limit is
        credited, through `credit_feed`.

        Raises:
            NotFed: Nothing was fed; the error says why.
        """
        bot = self.bot
        async with bot.guild_lock(guild_id):
            if (await bot.players.get(guild_id, user_id)).is_banned(now):
                raise NotFed(BLOCKER_REASONS[Blocker.BANNED])
            life = await bot.lives.current(guild_id)
            if life is None or is_over(life):
                raise NotFed(_NO_WISP)
            eaten = await bot.activity_log.meal_points_today(guild_id, user_id, now)
            cap = daily_meal_cap(life)
            grant = meal_grant(eaten, points, cap)
            if grant == 0:
                if points == 0:
                    raise NotFed(_WORTHLESS)
                raise NotFed(
                    "you've reached the daily meal limit "
                    f"({eaten} of {cap} meal points today, "
                    f"resets at {daily_reset(now)})."
                )
            events = await credit_feed(
                bot, guild_id, life, user_id, track, grant, message_id, now, self.rng
            )
            return events, mood(life)

    async def _forward(
        self,
        guild: discord.Guild,
        author: discord.Member,
        track: Track,
        name: str,
        feeling: Mood,
    ) -> None:
        """Post the track and Wisp's reaction in Mealtime.

        A failure is posted in Mealtime, or in Wisp's House when Mealtime cannot
        be reached.
        """
        reaction = self.bot.lines.pick(Moment.TRACK_FED, feeling, name=name)
        emoji = self.bot.emoji(_MOOD_EMOJIS[feeling])
        text = (
            f"♪ {author.mention} fed Wisp ・ {track.url}\n"
            f"{f'{emoji} ' if emoji else ''}{reaction}"
        )
        await say_in_mealtime(self.bot, guild, text, "forwarding a track to Mealtime")


# ---
# Crediting a feed
# ---


async def credit_feed(
    bot: "WispBot",
    guild_id: int,
    life: Life,
    user_id: int,
    track: Track,
    grant: int,
    message_id: int,
    now: datetime,
    rng: random.Random,
) -> list[Event]:
    """Credit a member with feeding `life` `track`, worth `grant` meal points.

    The feed is recorded, the member earns its points (and bond, for a
    viibrmusic.com track), Wisp eats and a mess is made due when one may
    come; `rng` picks when. Returns what happened to him. Call this under the
    guild lock; `life` is saved.

    Raises:
        NotFed: The life is not stored, or the guild already fed that track.
    """
    if life.id is None:
        raise NotFed(_NO_WISP)
    if not await bot.activity_log.record_feed(
        guild_id, life.id, user_id, track, grant, message_id, now
    ):
        raise NotFed(_REPEAT)
    bond = BOND_PER_VIIBR_TRACK if track.kind is TrackKind.VIIBR else 0
    await bot.activity_log.record_interaction(
        guild_id, life.id, user_id, InteractionKind.FEED, bond, grant, now
    )
    await bot.players.add_points(guild_id, user_id, grant)
    if bond:
        await bot.players.add_bond(guild_id, user_id, bond)
    events = feed(life, grant, user_id, now)
    schedule_mess(life, rng)
    await bot.lives.save(guild_id, life)
    return events


# ---
# Feeding roles and food values
# ---


async def refresh_rules(bot: "WispBot", guild_id: int) -> None:
    """Bring the Wisp FAQ's rules post up to date with the food values and roles.

    Takes no guild lock. A Discord failure is posted by `show_in_thread`, never
    raised.

    Raises:
        pymysql.err.Error: The database failed.
    """
    await show_in_thread(
        bot,
        guild_id,
        "rules_thread_id",
        "rules_message_id",
        await rules_post(bot, guild_id),
        "Wisp FAQ rules post",
    )


@commands.group(
    name="roles",
    invoke_without_command=True,
    case_insensitive=True,
    usage="add @role | remove @role | list",
)
async def roles(ctx: StaffContext) -> None:
    """Explain the feeding role commands when no known one was typed."""
    await reply(ctx, usage_line(roles))


@roles.command(name="add", usage="@role")
async def roles_add(ctx: StaffContext, role: discord.Role) -> None:
    """Add a qualifying role; the rules post names the roles, so it follows."""
    guild_id = guild_of(ctx).id
    await ctx.bot.settings.add_role(guild_id, role.id)
    await refresh_rules(ctx.bot, guild_id)
    await reply(ctx, f"♪ {role.mention} can now feed Wisp.")


@roles.command(name="remove", usage="@role")
async def roles_remove(ctx: StaffContext, role: discord.Role) -> None:
    """Remove a qualifying role; the rules post follows."""
    guild_id = guild_of(ctx).id
    await ctx.bot.settings.remove_role(guild_id, role.id)
    await refresh_rules(ctx.bot, guild_id)
    await reply(ctx, f"♪ {role.mention} no longer feeds Wisp.")


@roles.command(name="list")
async def roles_list(ctx: StaffContext) -> None:
    """List the qualifying roles."""
    role_ids = await ctx.bot.settings.roles(guild_of(ctx).id)
    if role_ids:
        mentions = (f"・<@&{role_id}>" for role_id in sorted(role_ids))
        text = "\n".join(["♪ Roles that can feed Wisp", *mentions])
    else:
        text = "♪ No qualifying roles yet. Add one with !wisp roles add @role."
    await reply(ctx, text)


@commands.command(
    name="food",
    usage=f"<viibr points> <suno points> (each 0 to {MEAL_POINTS_MAX})",
)
async def set_food(
    ctx: StaffContext,
    viibr: commands.Range[int, 0, MEAL_POINTS_MAX],
    suno: commands.Range[int, 0, MEAL_POINTS_MAX],
) -> None:
    """Save both food values and update the Wisp FAQ's rules post to match."""
    bot = ctx.bot
    guild_id = guild_of(ctx).id
    await bot.settings.update(guild_id, viibr_meal_points=viibr, suno_meal_points=suno)
    await refresh_rules(bot, guild_id)
    await reply(
        ctx,
        f"♪ Food values: {TRACK_LABELS[TrackKind.VIIBR]} "
        f"{count(viibr, 'meal point')}, {TRACK_LABELS[TrackKind.SUNO]} "
        f"{count(suno, 'meal point')}.",
    )


async def setup(bot: "WispBot") -> None:
    """Load the feeding cog and the feeding role and food commands."""
    await bot.add_cog(Feeding(bot))
    bot.add_command(roles)
    bot.add_command(set_food)
