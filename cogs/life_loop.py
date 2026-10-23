"""The life loop: time passes for Wisp, events are announced and his card stays live."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import discord
import pymysql
from discord.ext import commands, tasks

from cogs.announce import post_events, say_in_house, show_in_thread
from cogs.lunchbox import feed_view
from cogs.players import status_text
from cogs.vault import refresh_vault
from wisp.bond import happiness
from wisp.life import Event, Life, Phase, is_over, new_egg, tick
from wisp.lines import Moment
from wisp.rules import HAPPINESS_WINDOW, QUIET_AFTER, TICK_EVERY

if TYPE_CHECKING:
    from app import WispBot

# ---
# Loop
# ---


class LifeLoop(commands.Cog):
    """Ticks every guild's Wisp, announces what happens and keeps the status card."""

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self._quiet_announced: set[int] = set()

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
        await self.bot.report_error(None, "life loop", error)
        await asyncio.sleep(TICK_EVERY.total_seconds())
        self.tick_loop.restart()

    async def run_tick(self, now: datetime) -> None:
        """Advance every guild to `now`, one failing guild never stopping the rest.

        Guilds without a House channel or a Status thread, and guilds the bot
        can no longer see, are skipped. A database or Discord failure in one
        guild is reported with that guild.
        """
        for guild_id in await self.bot.settings.guilds():
            try:
                await self._tick_guild(guild_id, now)
            except (pymysql.err.Error, discord.HTTPException) as error:
                await self.bot.report_error(
                    self.bot.get_guild(guild_id), "life loop", error
                )

    # ---
    # One guild
    # ---

    async def _tick_guild(self, guild_id: int, now: datetime) -> None:
        bot = self.bot
        settings = await bot.settings.get(guild_id)
        if settings.house_channel_id is None or settings.status_thread_id is None:
            return
        if bot.get_guild(guild_id) is None:
            return
        frozen = settings.frozen
        happy = happiness(
            await bot.activity_log.people_since(guild_id, now - HAPPINESS_WINDOW)
        )
        events: list[Event] = []
        laid: Life | None = None
        async with bot.guild_lock(guild_id):
            life = await bot.lives.current(guild_id)
            if life is None or is_over(life):
                version = await bot.lives.next_version(guild_id)
                laid = await bot.lives.insert(guild_id, new_egg(version, now))
            else:
                events = await self._advance(guild_id, life, now, frozen, happy)
        if laid is not None:
            await say_in_house(bot, guild_id, Moment.NEW_EGG, laid)
        await post_events(bot, guild_id, events)
        current = await bot.lives.current(guild_id)
        if current is None:
            return
        await self._speak_if_quiet(guild_id, current, frozen, now)
        await self._update_card(guild_id, current, now, happy)
        await refresh_vault(bot, guild_id)

    async def _advance(
        self, guild_id: int, life: Life, now: datetime, frozen: bool, happy: int
    ) -> list[Event]:
        """Tick a life and save it, even when frozen; return what happened."""
        caretakers = 0
        if (
            life.phase is Phase.ALIVE
            and life.id is not None
            and life.stage_started_at is not None
        ):
            caretakers = await self.bot.activity_log.caretakers(
                guild_id, life.id, life.stage_started_at
            )
        events = tick(life, now, frozen=frozen, happiness=happy, caretakers=caretakers)
        await self.bot.lives.save(guild_id, life)
        return events

    # ---
    # Quiet
    # ---

    async def _speak_if_quiet(
        self, guild_id: int, life: Life, frozen: bool, now: datetime
    ) -> None:
        """Say one quiet line per stretch of no interaction; speak again after one."""
        people = await self.bot.activity_log.people_since(guild_id, now - QUIET_AFTER)
        if people:
            self._quiet_announced.discard(guild_id)
            return
        if frozen or life.phase is not Phase.ALIVE or guild_id in self._quiet_announced:
            return
        self._quiet_announced.add(guild_id)
        await say_in_house(self.bot, guild_id, Moment.QUIET, life)

    # ---
    # Status card
    # ---

    async def _update_card(
        self, guild_id: int, life: Life, now: datetime, happy: int
    ) -> None:
        """Show the live status card in the Status thread."""
        if is_over(life):
            return
        await show_in_thread(
            self.bot,
            guild_id,
            "status_thread_id",
            "status_message_id",
            await status_text(self.bot, guild_id, life, now, happy),
            "status card",
            feed_view(),
        )


async def setup(bot: "WispBot") -> None:
    """Load the life loop cog."""
    await bot.add_cog(LifeLoop(bot))
