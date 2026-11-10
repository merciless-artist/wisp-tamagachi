"""Wisp's drawings: pictures he makes for members as presents, never on request.

He makes one when a member gives him a gift he loves, when their bond reaches
a new tier, for the member who fed the most tracks the day before, and, once a
day at a random time, for a member he likes. Each member gets at most one a UTC
day and the server a few.
"""

import random
from datetime import UTC, date, datetime, timedelta
from enum import Enum, auto
from io import BytesIO
from typing import TYPE_CHECKING, Final

import discord
from discord.ext import commands

from ai.chain import AllProvidersFailed, ProviderError
from cogs.announce import Upload, post_in_house
from cogs.assets import stage_art
from cogs.players import feeder_blocker
from cogs.staff import StaffContext, guild_of, reply
from db.activity import InteractionKind
from wisp.life import Life, Mood, Phase, is_over, mood
from wisp.lines import Moment
from wisp.rules import (
    DRAWING_FILE_NAME,
    DRAWING_LIKE_WINDOW,
    DRAWINGS_PER_DAY,
    DRAWINGS_PER_MEMBER_PER_DAY,
    Stage,
)
from wisp.voice import DrawReason, drawing_prompt, picture_prompt

if TYPE_CHECKING:
    from app import WispBot

NO_WORKER: Final = (
    "Wisp made no drawing: the picture worker address (CF_IMAGE_WORKER_URL) "
    "is not set."
)

_MOMENTS: Final = {
    DrawReason.GIFT: Moment.DRAWING_GIFT,
    DrawReason.BOND: Moment.DRAWING_BOND,
    DrawReason.TOP_FEEDER: Moment.DRAWING_TOP_FEEDER,
    DrawReason.LIKE: Moment.DRAWING_LIKE,
}
_LIKED_KINDS: Final = (
    InteractionKind.FEED,
    InteractionKind.SNACK,
    InteractionKind.FREE_SNACK,
    InteractionKind.CHAT,
    InteractionKind.PLAY,
)
_SECONDS_PER_DAY: Final = 24 * 60 * 60

# ---
# Making one
# ---


class DrawResult(Enum):
    """What came of a chance to draw for a member."""

    MADE = auto()
    SKIPPED = auto()
    FAILED = auto()


async def _living(bot: "WispBot", guild_id: int) -> Life | None:
    """The guild's Wisp when he is alive and not frozen, else None."""
    if (await bot.settings.get(guild_id)).frozen:
        return None
    life = await bot.lives.current(guild_id)
    return life if life is not None and life.phase is Phase.ALIVE else None


async def _may_draw_for(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    now: datetime,
) -> bool:
    """Whether the member can be given one now.

    There must be an image worker to draw it. They must be in the server, may
    feed him and not be banned, and neither they nor the server may be at the
    day's cap.
    """
    if (
        not bot.images.configured
        or not isinstance(member, discord.Member)
        or await feeder_blocker(bot, guild_id, member, now) is not None
    ):
        return False
    return (
        await bot.drawings.count_today(guild_id, now) < DRAWINGS_PER_DAY
        and await bot.drawings.count_today_for(guild_id, member.id, now)
        < DRAWINGS_PER_MEMBER_PER_DAY
    )


async def _make_picture(
    bot: "WispBot",
    guild_id: int,
    member_id: int,
    name: str,
    reason: DrawReason,
    stage: Stage,
    feeling: Mood,
) -> tuple[str, bytes]:
    """Have his AI write the scene, then have the worker draw it.

    The worker gets his picture for `stage` from ASSETS/stages to draw him
    from. Returns the image prompt the worker got and its picture.

    Raises:
        AllProvidersFailed: Every AI provider failed.
        ProviderError: His picture for the stage is missing, before any AI
            call, or the image worker failed.
    """
    art = stage_art(stage)
    if art is None:
        raise ProviderError(f"no picture of Wisp as a {stage.label} in ASSETS/stages")
    notes = await bot.notes.recent(guild_id, member_id)
    scene = await bot.ai.complete(drawing_prompt(reason, name, notes, stage, feeling))
    prompt = picture_prompt(scene)
    return prompt, await bot.images.draw(prompt, art.read_bytes())


async def draw_for(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    reason: DrawReason,
    now: datetime,
) -> DrawResult:
    """Make the member a drawing and post it in Wisp's House, if he may.

    SKIPPED, quietly and before any AI call, when no image worker address is
    set. SKIPPED too when he is not alive or is frozen, the member may not feed
    him, is banned or is not in the server, or a daily cap is reached. A
    failure of the AI, the worker or the post is reported where members see
    it, as `Error in making a drawing for <name>`, and nothing is recorded, so
    the next trigger can try again. Call this outside the guild lock: it waits
    for the worker.
    """
    async with bot.drawing_lock(guild_id):
        life = await _living(bot, guild_id)
        if life is None or life.id is None:
            return DrawResult.SKIPPED
        if not await _may_draw_for(bot, guild_id, member, now):
            return DrawResult.SKIPPED
        player = await bot.players.get(guild_id, member.id)
        name = player.name or member.display_name
        try:
            _, picture = await _make_picture(
                bot, guild_id, member.id, name, reason, life.stage, mood(life)
            )
        except (AllProvidersFailed, ProviderError) as error:
            await bot.report_error(
                bot.get_guild(guild_id), f"making a drawing for {name}", error
            )
            return DrawResult.FAILED
        line = bot.lines.pick(_MOMENTS[reason], mood(life), name=f"<@{member.id}>")
        post = await post_in_house(
            bot,
            guild_id,
            f"♪ {line}",
            image=Upload(picture, DRAWING_FILE_NAME),
            ping=member.id,
        )
        if post is None:
            return DrawResult.FAILED
        await bot.drawings.record(
            guild_id, member.id, life.id, reason.value, post.id, now
        )
        return DrawResult.MADE


# ---
# Each tick
# ---


class DailyDrawings:
    """The drawings the life loop decides on: bond tiers, the top feeder and likes.

    `rng` picks the second of the UTC day when he likes someone, and whom.
    What it tried today is kept in memory, so a failed try waits for the next
    day instead of repeating every tick; the drawings table keeps a restart
    from making a second one of the same daily kind.
    """

    def __init__(self, bot: "WispBot", rng: random.Random) -> None:
        self._bot = bot
        self._rng = rng
        self._top_feeder_day: dict[int, date] = {}
        self._like_plan: dict[int, tuple[date, datetime]] = {}
        self._like_day: dict[int, date] = {}

    async def run(self, guild_id: int, now: datetime) -> None:
        """Make whichever drawings are due in a guild at `now`.

        Bond tiers reached while he was frozen or not alive are forgotten.
        """
        bot = self._bot
        if await _living(bot, guild_id) is None:
            bot.players.take_tier_ups(guild_id)
            return
        for user_id in bot.players.take_tier_ups(guild_id):
            await self._draw_for_id(guild_id, user_id, DrawReason.BOND, now)
        await self._top_feeder(guild_id, now)
        await self._like(guild_id, now)

    async def _top_feeder(self, guild_id: int, now: datetime) -> None:
        """At the day's first tick, thank yesterday's top feeder.

        The next one in line is thanked when the top one cannot have a drawing.
        """
        today = now.astimezone(UTC).date()
        if self._top_feeder_day.get(guild_id) == today:
            return
        self._top_feeder_day[guild_id] = today
        feeders = await self._bot.activity_log.top_track_feeders(guild_id, now)
        reason = DrawReason.TOP_FEEDER
        if feeders and not await self._bot.drawings.reason_made_today(
            guild_id, reason.value, now
        ):
            await self._draw_for_first(guild_id, feeders, reason, now)

    async def _like(self, guild_id: int, now: datetime) -> None:
        """Once a UTC day, from a random second on, draw for a member he likes.

        He picks at random among the members who fed him, chatted with him or
        played with him in the last DRAWING_LIKE_WINDOW.
        """
        today = now.astimezone(UTC).date()
        plan = self._like_plan.get(guild_id)
        if plan is None or plan[0] != today:
            start = now.astimezone(UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            due = start + timedelta(seconds=self._rng.randrange(_SECONDS_PER_DAY))
            plan = self._like_plan[guild_id] = (today, due)
        if now < plan[1] or self._like_day.get(guild_id) == today:
            return
        self._like_day[guild_id] = today
        members = await self._bot.activity_log.members_since(
            guild_id, now - DRAWING_LIKE_WINDOW, _LIKED_KINDS
        )
        reason = DrawReason.LIKE
        if members and not await self._bot.drawings.reason_made_today(
            guild_id, reason.value, now
        ):
            self._rng.shuffle(members)
            await self._draw_for_first(guild_id, members, reason, now)

    async def _draw_for_first(
        self, guild_id: int, user_ids: list[int], reason: DrawReason, now: datetime
    ) -> None:
        """Draw for the first of `user_ids` who can have one, and no one after."""
        for user_id in user_ids:
            if await self._draw_for_id(guild_id, user_id, reason, now) is not (
                DrawResult.SKIPPED
            ):
                return

    async def _draw_for_id(
        self, guild_id: int, user_id: int, reason: DrawReason, now: datetime
    ) -> DrawResult:
        """Draw for a member by id; SKIPPED when they are no longer in the server."""
        guild = self._bot.get_guild(guild_id)
        member = None if guild is None else guild.get_member(user_id)
        if member is None:
            return DrawResult.SKIPPED
        return await draw_for(self._bot, guild_id, member, reason, now)


# ---
# The staff test
# ---

_TEST_USAGE: Final = f"[@member] [{' | '.join(Stage)}]"


def _stage_word(argument: str) -> Stage:
    """Read a stage in any case, with or without its underscore: old_fogey, OldFogey."""
    word = argument.lower().replace("_", "")
    for stage in Stage:
        if stage.value.replace("_", "") == word:
            return stage
    raise commands.BadArgument(f"Not a stage: {argument}")


@commands.command(name="testdrawing", usage=_TEST_USAGE)
async def testdrawing(
    ctx: StaffContext,
    member: discord.Member | None = None,
    stage: Stage | None = commands.parameter(converter=_stage_word, default=None),
) -> None:
    """Have Wisp draw one picture right here, so staff can see how he draws.

    It is for `member` (whoever typed it when left out), with Wisp as he looks
    at `stage` (his stage now when left out). It skips the daily caps and is
    neither posted in his House nor counted, and it pings nobody. The image
    prompt the worker got comes with it. With no Wisp alive or as an egg, a
    stage must be named. An AI or worker failure is reported as
    `Error in making a test drawing`.
    """
    bot = ctx.bot
    guild = guild_of(ctx)
    if not bot.images.configured:
        await reply(ctx, f"♪ {NO_WORKER}")
        return
    life = await bot.lives.current(guild.id)
    living = None if life is None or is_over(life) else life
    if stage is None:
        if living is None:
            await reply(ctx, f"♪ Wisp has no life now, so name a stage: {_TEST_USAGE}")
            return
        stage = living.stage
    target = member or ctx.author
    player = await bot.players.get(guild.id, target.id)
    name = player.name or target.display_name
    feeling = Mood.HAPPY if living is None else mood(living)
    try:
        prompt, picture = await _make_picture(
            bot, guild.id, target.id, name, DrawReason.LIKE, stage, feeling
        )
    except (AllProvidersFailed, ProviderError) as error:
        await bot.report_error(guild, "making a test drawing", error)
        return
    await reply(
        ctx,
        f"♪ Test drawing for {target.mention}, with Wisp as a {stage.label}. "
        f"It isn't counted.\n・Prompt: {prompt}",
        picture=discord.File(BytesIO(picture), filename=DRAWING_FILE_NAME),
    )


async def setup(bot: "WispBot") -> None:
    """Load `!wisp testdrawing`."""
    bot.add_command(testdrawing)
