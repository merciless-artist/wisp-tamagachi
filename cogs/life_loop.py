"""The life loop: time passes for Wisp, events are announced and his card stays live.

After an ending the loop lays nothing: staff press Begin again for the next egg.
"""

import asyncio
import random
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord
import pymysql
from discord.ext import commands, tasks

from cogs.announce import (
    BEGIN_ID,
    begin_again,
    begin_button,
    begin_view,
    ending_image,
    lay_first_egg,
    post_events,
    say_in_house,
)
from cogs.assets import nap_image
from cogs.badges import sweep_badges
from cogs.channels import where_of
from cogs.chores import post_chores
from cogs.drawings import DailyDrawings
from cogs.groups import require_guild
from cogs.pictures import life_image
from cogs.players import (
    EXPECTED_FAILURES,
    bot_of,
    report_failure,
    say_privately,
    status_text,
    test_press,
)
from cogs.staff import StaffContext, guild_of, is_staff, reply
from cogs.status_card import show_status, status_view
from cogs.studio import refresh_house_panel
from cogs.vault import refresh_vault
from cogs.wisp_lunchbox import pick_favorite_song
from wisp.card import WAITING
from wisp.chores import ChoreEvent, is_napping, tick_chores
from wisp.life import (
    Event,
    EventKind,
    Life,
    Phase,
    credited_gap,
    is_over,
    schedule_cold,
    tick,
)
from wisp.lines import Moment
from wisp.rules import PAID_SNACKS, PEOPLE_WINDOW, QUIET_AFTER, TICK_EVERY

if TYPE_CHECKING:
    from app import WispBot

_BEGIN_CONTEXT: Final = "the Begin again button"
_STAFF_ONLY: Final = "♪ Only staff can start a new Wisp."
_ALREADY_HERE: Final = "♪ Wisp is already here."
_ON_ITS_WAY: Final = "♪ A new egg is on its way."

# ---
# Loop
# ---


class LifeLoop(commands.Cog):
    """Ticks every guild's Wisp, announces what happens and keeps the status card.

    `rng` picks his favorite snack when he hatches, his favorite song of
    each day, when his childhood cold is due and when he throws a tantrum.
    """

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self.rng = random.Random()
        self.drawings = DailyDrawings(bot, self.rng)
        self._quiet_announced: set[int] = set()
        self._watching_since: dict[int, datetime] = {}

    async def cog_load(self) -> None:
        """Start ticking."""
        self.tick_loop.start()

    async def cog_unload(self) -> None:
        """Stop ticking."""
        self.tick_loop.cancel()

    @tasks.loop(seconds=TICK_EVERY.total_seconds())
    async def tick_loop(self) -> None:
        await self.run_tick(discord.utils.utcnow())

    @tick_loop.before_loop
    async def _before_tick_loop(self) -> None:
        await self.bot.wait_until_ready()

    @tick_loop.error
    async def _on_tick_loop_error(self, error: BaseException) -> None:
        await self.bot.report_error_everywhere("life loop", error)
        await asyncio.sleep(TICK_EVERY.total_seconds())
        self.tick_loop.restart()

    async def run_tick(self, now: datetime) -> None:
        """Advance every guild to `now`, one failing guild never stopping the rest.

        Guilds without a House channel or a Status thread, and guilds the bot
        can no longer see, are skipped, and so is a guild with a staff test
        life running: its steps tick it themselves. A database or Discord
        failure in one guild is reported with that guild.
        """
        for guild_id in await self.bot.settings.guilds():
            if guild_id in self.bot.test_runs:
                continue
            try:
                await self.tick_guild(guild_id, now)
            except (pymysql.err.Error, discord.HTTPException) as error:
                await self.bot.report_error(
                    self.bot.get_guild(guild_id), "life loop", error
                )

    # ---
    # One guild
    # ---

    async def tick_guild(self, guild_id: int, now: datetime) -> None:
        """Advance one guild to `now` and bring its posts, card and Vault up to date.

        Takes `bot.guild_lock`, so it must be called outside it.

        Raises:
            pymysql.err.Error: The database failed.
            discord.HTTPException: Discord failed.
        """
        bot = self.bot
        settings = await bot.settings.get(guild_id)
        if settings.house_channel_id is None or settings.status_thread_id is None:
            return
        guild = bot.get_guild(guild_id)
        if guild is None:
            return
        frozen = settings.frozen
        ticked: Life | None = None
        events: list[Event] = []
        chores: list[ChoreEvent] = []
        async with bot.guild_lock(guild_id):
            life = await bot.lives.current(guild_id)
            if life is not None and not is_over(life):
                events, chores = await self._advance(guild_id, life, now, frozen)
                ticked = life
        if ticked is None:
            await lay_first_egg(bot, guild_id, now)
        else:
            await post_events(bot, guild_id, events)
            await post_chores(bot, guild_id, ticked, chores)
        await sweep_badges(bot, guild_id, now)
        current = await bot.lives.current(guild_id)
        if current is None:
            return
        await self._speak_if_quiet(guild_id, current, frozen, now)
        await show_status_card(bot, guild_id, current, now)
        await refresh_house_panel(bot, guild_id, current)
        await refresh_vault(bot, guild_id)
        if not is_over(current):
            await pick_favorite_song(bot, guild, current, self.rng, now)
        await self.drawings.run(guild_id, now)

    async def _advance(
        self, guild_id: int, life: Life, now: datetime, frozen: bool
    ) -> tuple[list[Event], list[ChoreEvent]]:
        """Tick a life and its chores and save it, even when frozen.

        Returns what happened to him and what his chores did. A young Wisp's
        cold is scheduled first, so one already due starts on this tick. A
        Wisp who hatches picks his favorite snack, never the free one, or its
        line would answer every member's daily free snack. His chores count
        the same time his meters do.
        """
        caretakers = people = 0
        if (
            life.phase is Phase.ALIVE
            and life.id is not None
            and life.stage_started_at is not None
        ):
            caretakers = await self.bot.activity_log.caretakers(
                guild_id, life.id, life.stage_started_at
            )
            people = await self.bot.activity_log.people_since(
                guild_id, now - PEOPLE_WINDOW
            )
        schedule_cold(life, self.rng)
        elapsed = credited_gap(life, now, frozen=frozen)
        events = tick(
            life,
            now,
            frozen=frozen,
            caretakers=caretakers,
            people=people,
        )
        if any(event.kind is EventKind.HATCHED for event in events):
            life.favorite_snack = self.rng.choice(PAID_SNACKS).key
        chores = tick_chores(life, now, elapsed, self.rng, frozen=frozen)
        await self.bot.lives.save(guild_id, life)
        return events, chores

    # ---
    # Quiet
    # ---

    async def _speak_if_quiet(
        self, guild_id: int, life: Life, frozen: bool, now: datetime
    ) -> None:
        """Say one quiet line per stretch of quiet in his House; speak again after one.

        The House is quiet once QUIET_AFTER has passed with no member talking
        there or poking him. Until a member does after a restart, the quiet is
        counted from this run's first tick, so a restart never makes him say
        it at once. He says nothing while frozen, napping or not alive.
        """
        quiet_for = self.bot.talk.quiet_for(guild_id, now)
        if quiet_for is None:
            quiet_for = now - self._watching_since.setdefault(guild_id, now)
        if quiet_for < QUIET_AFTER:
            self._quiet_announced.discard(guild_id)
            return
        if (
            frozen
            or life.phase is not Phase.ALIVE
            or is_napping(life)
            or guild_id in self._quiet_announced
        ):
            return
        self._quiet_announced.add(guild_id)
        await say_in_house(
            self.bot, guild_id, Moment.QUIET, life, image=nap_image(life.stage)
        )


# ---
# Status card
# ---


async def show_status_card(
    bot: "WispBot", guild_id: int, life: Life, now: datetime
) -> None:
    """Show `life` in the Status post: his picture first, then the card.

    While he goes on it is his live card with its buttons (`status_view`),
    under his current picture. Once his life is over it says Wisp is
    waiting for staff to begin again and carries only the Begin again button,
    so staff always have one to press even when the House's question was never
    posted or is gone; the post shows the picture of how his life ended, or no
    picture when that is missing.
    """
    view: discord.ui.View
    image: Path | None
    if is_over(life):
        content, view, image = WAITING, begin_view(), ending_image(life)
    else:
        content = await status_text(bot, guild_id, life, now)
        view, image = status_view(), life_image(life)
    await show_status(
        bot, guild_id, content, view, image, clear_image=image is None and is_over(life)
    )


# ---
# Begin again
# ---


class BeginButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(BEGIN_ID),
):
    """The Begin again button on the House's question after Wisp's life ends.

    Only staff may press it. Its custom id is fixed, so the button keeps
    working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(begin_button())

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "BeginButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Begin again, reporting a failure where the button was pressed."""
        try:
            await _begin(interaction)
        except EXPECTED_FAILURES as error:
            await report_failure(interaction, _BEGIN_CONTEXT, error)


async def _begin(interaction: discord.Interaction) -> None:
    """Begin again for the presser, unless a staff test life holds the button.

    While a test life runs in the guild, only its runner's press counts.
    """
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild_id = require_guild(interaction)
    async with test_press(interaction, guild_id) as allowed:
        if allowed:
            await _begin_for(interaction, guild_id)


async def _begin_for(interaction: discord.Interaction, guild_id: int) -> None:
    """Lay the next egg for staff, retiring the pressed button either way.

    Anyone else is turned away. A press that finds Wisp already here lays
    nothing; its button is disabled all the same, since it is stale. The
    button is retired before the egg is shown, so a press on the waiting
    status card ends with the egg's own card. The answer is private.
    """
    bot = bot_of(interaction)
    user = interaction.user
    if not isinstance(user, discord.Member) or not await is_staff(bot, user):
        await say_privately(interaction, _STAFF_ONLY)
        return
    now = discord.utils.utcnow()
    egg = await begin_again(bot, guild_id, now)
    await _retire_question(interaction)
    if egg is None:
        await say_privately(interaction, _ALREADY_HERE)
        return
    await _show_egg(bot, guild_id, egg, now)
    await say_privately(interaction, _ON_ITS_WAY)


async def _show_egg(bot: "WispBot", guild_id: int, egg: Life, now: datetime) -> None:
    """Show a new egg on the status card and House panel now, not on the next tick."""
    await show_status_card(bot, guild_id, egg, now)
    await refresh_house_panel(bot, guild_id, egg)


async def _retire_question(interaction: discord.Interaction) -> None:
    """Disable the pressed question's button; a failure is reported, never raised."""
    if interaction.message is None:
        return
    try:
        await interaction.message.edit(view=begin_view(disabled=True))
    except discord.HTTPException as error:
        await bot_of(interaction).report_error(
            interaction.guild, _BEGIN_CONTEXT, error, where=where_of(interaction)
        )


@commands.command(name="begin")
async def begin(ctx: StaffContext) -> None:
    """Begin again by typing, for when no Begin again button can be pressed.

    Like the button it lays nothing while Wisp is here. Only staff reach it.
    """
    bot = ctx.bot
    guild_id = guild_of(ctx).id
    now = discord.utils.utcnow()
    egg = await begin_again(bot, guild_id, now)
    if egg is None:
        await reply(ctx, _ALREADY_HERE)
        return
    await _show_egg(bot, guild_id, egg, now)
    await reply(ctx, _ON_ITS_WAY)


async def setup(bot: "WispBot") -> None:
    """Load the life loop cog, its `!wisp begin` and the Begin again button.

    The button is registered so it still works after a restart.
    """
    await bot.add_cog(LifeLoop(bot))
    bot.add_command(begin)
    bot.add_dynamic_items(BeginButton)
