"""Wisp: a Discord Tamagotchi fed by the tracks a server shares."""

import asyncio
import logging
import sys
from typing import Any, Final

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import config
from ai.chain import chain_from_config
from cogs.channels import may_post_in, where_of
from cogs.groups import wisp, wispadmin
from db.activity import ActivityRepo
from db.database import Database
from db.keepsakes import KeepsakeRepo
from db.lives import LifeRepo
from db.notes import NoteRepo
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
    "cogs.conversation",
    "cogs.life_loop",
    "cogs.discipline",
)

_REFUSAL = "That command is for staff."
_NO_PING: Final = discord.AllowedMentions.none()

# ---
# Command tree
# ---


class WispTree(app_commands.CommandTree["WispBot"]):
    """Command tree that tells the user when a command fails and posts the error."""

    async def on_error(
        self,
        interaction: discord.Interaction["WispBot"],
        error: app_commands.AppCommandError,
    ) -> None:
        """Refuse failed checks politely; otherwise tell the user and post the error.

        The error is posted in the channel or thread the command was used in. A
        bot that lacks permissions is a fault staff must fix, not a refusal.
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
        await self.client.report_error(
            interaction.guild, context, cause, where=where_of(interaction)
        )

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
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.db = Database(config.TABLE_PREFIX)
        self.settings = SettingsRepo(self.db)
        self.lives = LifeRepo(self.db)
        self.players = PlayerRepo(self.db)
        self.activity_log = ActivityRepo(self.db)
        self.keepsakes = KeepsakeRepo(self.db)
        self.notes = NoteRepo(self.db)
        self.ai = chain_from_config()
        self.lines = LinePicker()
        self.emojis_by_name: dict[str, discord.Emoji] = {}
        self._missing_emojis: set[str] = set()
        self.failing_displays: set[tuple[int, str]] = set()
        self.rhyme_duels: set[tuple[int, int]] = set()
        self._guild_locks: dict[int, asyncio.Lock] = {}
        self._startup_reports: list[tuple[str, str]] = []

    async def setup_hook(self) -> None:
        """Connect storage, fetch emojis, load the cogs and sync the commands.

        The cogs attach their commands to the shared groups as they load, so the
        groups join the command tree only once all of them are in. A cog that
        fails to load is logged now and posted in Wisp's House once the bot is
        ready.
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
                context = f"loading {extension}"
                log.error("Error in %s", context, exc_info=error)
                self._startup_reports.append((context, _report_line(context, error)))
        self.tree.add_command(wisp)
        self.tree.add_command(wispadmin)
        synced = await self.tree.sync()
        log.info("Synced %d commands", len(synced))

    async def on_ready(self) -> None:
        """Post the errors from startup in every Wisp's House, the first time only."""
        reports, self._startup_reports = self._startup_reports, []
        for context, line in reports:
            await self._post_everywhere(context, line)

    async def on_message(self, message: discord.Message) -> None:
        """Ignore direct messages. Guild messages reach the cogs' own listeners."""
        if message.guild is None:
            return

    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        """Report an exception raised in an event listener.

        The guild comes from the event's first argument when it has one. When
        that argument is a message, the error is posted in its channel.
        """
        error = sys.exc_info()[1]
        assert error is not None
        first = args[0] if args else None
        guild = getattr(first, "guild", None)
        await self.report_error(
            guild if isinstance(guild, discord.Guild) else None,
            event_method,
            error,
            where=first.channel if isinstance(first, discord.Message) else None,
        )

    async def close(self) -> None:
        """Shut the client down, then close the AI session and the database pool.

        A failure in one step never skips the later ones.
        """
        try:
            await super().close()
        finally:
            try:
                await self.ai.close()
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

    async def house_channel(
        self, guild: discord.Guild | None
    ) -> discord.abc.Messageable | None:
        """Return the guild's Wisp's House channel, or None if it cannot be used.

        A channel that is set but cannot be seen is logged.
        """
        if guild is None:
            return None
        channel_id = (await self.settings.get(guild.id)).house_channel_id
        if channel_id is None:
            return None
        channel = guild.get_channel_or_thread(channel_id)
        if isinstance(channel, discord.abc.Messageable):
            return channel
        log.error("Wisp's House %d is not available", channel_id)
        return None

    async def report_error(
        self,
        guild: discord.Guild | None,
        context: str,
        error: BaseException,
        *,
        where: discord.abc.Messageable | None = None,
    ) -> None:
        """Log an error and post it as plain text where it happened.

        `where` is the channel or thread the error happened in. Without one, or
        when it is in the track drop, the error goes to Wisp's House. This
        never raises: a failure to report is only logged.
        """
        log.error("Error in %s", context, exc_info=error)
        await self._post_report(guild, context, _report_line(context, error), where)

    async def report_error_everywhere(self, context: str, error: BaseException) -> None:
        """Log an error that belongs to no one guild and post it to every guild.

        This never raises: a failure to report is only logged.
        """
        log.error("Error in %s", context, exc_info=error)
        await self._post_everywhere(context, _report_line(context, error))

    async def _post_everywhere(self, context: str, line: str) -> None:
        """Post a report in Wisp's House of every guild Wisp is set up in.

        When the guilds cannot be listed for any reason, such as a closed or
        unconnected pool, the guilds the bot can see are used, so the report
        always goes out and the caller never sees an exception.
        """
        try:
            guilds = [
                guild
                for guild_id in await self.settings.guilds()
                if (guild := self.get_guild(guild_id)) is not None
            ]
        except Exception:
            log.exception("Could not list Wisp's guilds to report %s", context)
            guilds = list(self.guilds)
        for guild in guilds:
            await self._post_report(guild, context, line)

    async def _post_report(
        self,
        guild: discord.Guild | None,
        context: str,
        line: str,
        where: discord.abc.Messageable | None = None,
    ) -> None:
        """Post a report in `where`, else in Wisp's House.

        Where Wisp may not post (see `may_post_in`), the error goes to the House.
        When posting in `where` fails, through Discord or the network, the House
        is tried once. Without a guild the report is only logged.
        """
        if guild is None:
            return
        try:
            tracks_id = (await self.settings.get(guild.id)).tracks_channel_id
            if where is not None and may_post_in(where, tracks_id):
                try:
                    await where.send(line, allowed_mentions=_NO_PING)
                    return
                except (discord.DiscordException, aiohttp.ClientError, OSError):
                    log.exception("Could not post error report for %s", context)
            house = await self.house_channel(guild)
            if house is not None and house is not where:
                await house.send(line, allowed_mentions=_NO_PING)
        except Exception:
            log.exception("Could not post error report for %s", context)


def _report_line(context: str, error: BaseException) -> str:
    """The plain error report, cut to one message."""
    return f"Error in {context}: {type(error).__name__}: {error}"[:MESSAGE_LIMIT]


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
