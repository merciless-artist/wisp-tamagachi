"""Wisp: a Discord Tamagotchi fed by the tracks a server shares."""

import asyncio
import logging
import sys
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

import config
from cogs.groups import wisp, wispadmin
from db.activity import ActivityRepo
from db.database import Database
from db.keepsakes import KeepsakeRepo
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.schema import create_tables
from db.settings import SettingsRepo
from wisp.lines import LinePicker
from wisp.text import MESSAGE_LIMIT, USER_ERROR

log = logging.getLogger("wisp")

EXTENSIONS: tuple[str, ...] = (
    "cogs.studio",
    "cogs.players",
    "cogs.lunchbox",
    "cogs.vault",
    "cogs.rhyme_duel",
    "cogs.feeding",
    "cogs.life_loop",
    "cogs.discipline",
)

_REFUSAL = "That command is for staff."

# ---
# Command tree
# ---


class WispTree(app_commands.CommandTree["WispBot"]):
    """Command tree that tells the user and staff when a command fails."""

    async def on_error(
        self,
        interaction: discord.Interaction["WispBot"],
        error: app_commands.AppCommandError,
    ) -> None:
        """Refuse failed checks politely; otherwise apologise and report to staff.

        A bot that lacks permissions is a fault staff must fix, not a refusal.
        """
        command = interaction.command
        context = f"/{command.qualified_name}" if command else "an interaction"
        if isinstance(error, app_commands.CheckFailure) and not isinstance(
            error, app_commands.BotMissingPermissions
        ):
            await self._reply(interaction, _REFUSAL, context)
            return
        cause = (
            error.original
            if isinstance(error, app_commands.CommandInvokeError)
            else error
        )
        await self._reply(interaction, USER_ERROR, context)
        await self.client.report_error(interaction.guild, context, cause)

    async def _reply(
        self, interaction: discord.Interaction["WispBot"], text: str, context: str
    ) -> None:
        """Send an ephemeral message; a failure to send is logged, never raised."""
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.DiscordException:
            log.exception("Could not reply to the user in %s", context)


# ---
# Bot
# ---


class WispBot(commands.Bot):
    """The bot: shared storage, Wisp's voice, error reporting and per-guild locks."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = False
        intents.dm_reactions = False
        intents.dm_typing = False
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            tree_cls=WispTree,
        )
        self.db = Database(config.TABLE_PREFIX)
        self.settings = SettingsRepo(self.db)
        self.lives = LifeRepo(self.db)
        self.players = PlayerRepo(self.db)
        self.activity_log = ActivityRepo(self.db)
        self.keepsakes = KeepsakeRepo(self.db)
        self.lines = LinePicker()
        self.emojis_by_name: dict[str, discord.Emoji] = {}
        self._missing_emojis: set[str] = set()
        self.failing_displays: set[tuple[int, str]] = set()
        self.rhyme_duels: set[tuple[int, int]] = set()
        self._guild_locks: dict[int, asyncio.Lock] = {}

    async def setup_hook(self) -> None:
        """Connect storage, fetch emojis, load the cogs and sync the commands.

        The cogs attach their commands to the shared groups as they load, so the
        groups join the command tree only once all of them are in.
        """
        await self.db.connect()
        await create_tables(self.db)
        log.info("Database ready")
        self.emojis_by_name = {
            emoji.name: emoji for emoji in await self.fetch_application_emojis()
        }
        for extension in EXTENSIONS:
            try:
                await self.load_extension(extension)
            except commands.ExtensionError as error:
                await self.report_error(None, f"loading {extension}", error)
        self.tree.add_command(wisp)
        self.tree.add_command(wispadmin)
        synced = await self.tree.sync()
        log.info("Synced %d commands", len(synced))

    async def on_message(self, message: discord.Message) -> None:
        """Ignore direct messages. Guild messages reach the cogs' own listeners."""
        if message.guild is None:
            return

    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        """Report an exception raised in an event listener to staff.

        The guild comes from the event's first argument when it has one.
        """
        error = sys.exc_info()[1]
        assert error is not None
        guild = getattr(args[0], "guild", None) if args else None
        await self.report_error(
            guild if isinstance(guild, discord.Guild) else None, event_method, error
        )

    async def close(self) -> None:
        """Shut the client down, then close the database pool."""
        try:
            await super().close()
        finally:
            await self.db.close()

    def emoji(self, name: str) -> str:
        """Return an application emoji's text, or "" if it has not been uploaded."""
        found = self.emojis_by_name.get(name)
        if found is not None:
            return str(found)
        if name not in self._missing_emojis:
            self._missing_emojis.add(name)
            log.warning("Application emoji %r has not been uploaded", name)
        return ""

    def guild_lock(self, guild_id: int) -> asyncio.Lock:
        """Return the lock that serialises life updates for one guild."""
        return self._guild_locks.setdefault(guild_id, asyncio.Lock())

    async def staff_channel(
        self, guild: discord.Guild | None
    ) -> discord.abc.Messageable | None:
        """Return the guild's staff errors channel, or None if it cannot be used.

        A channel that is set but cannot be seen is logged.
        """
        if guild is None:
            return None
        channel_id = (await self.settings.get(guild.id)).error_channel_id
        if channel_id is None:
            return None
        channel = guild.get_channel_or_thread(channel_id)
        if isinstance(channel, discord.abc.Messageable):
            return channel
        log.error("Staff channel %d is not available", channel_id)
        return None

    async def report_error(
        self, guild: discord.Guild | None, context: str, error: BaseException
    ) -> None:
        """Log an error and post it as plain text to the guild's error channel.

        This never raises: a failure to report is only logged.
        """
        log.error("Error in %s", context, exc_info=error)
        line = f"Error in {context}: {type(error).__name__}: {error}"
        try:
            channel = await self.staff_channel(guild)
            if channel is not None:
                await channel.send(line[:MESSAGE_LIMIT])
        except Exception:
            log.exception("Could not post error report for %s", context)


# ---
# Startup
# ---


def main() -> None:
    """Configure logging and run the bot until it is stopped."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    WispBot().run(config.TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
