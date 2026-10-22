"""Wisp's Studio: the forum threads he lives in and the staff settings for them."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import discord
from discord import app_commands
from discord.ext import commands

from db.settings import Settings
from wisp import rules
from wisp.links import TrackKind

if TYPE_CHECKING:
    from app import WispBot

_ARCHIVE_AFTER_MINUTES: Final = 10080
_SEPARATOR = "・♪ ────────・──────── ♪・"
_TRACK_LABELS: dict[TrackKind, str] = {
    TrackKind.VIIBR: "viibrmusic.com track",
    TrackKind.SUNO: "Suno track",
}

# ---
# How Wisp Works text
# ---


def _count(amount: int, noun: str) -> str:
    return f"{amount} {noun}" if amount == 1 else f"{amount} {noun}s"


def _ban_lines() -> list[str]:
    lines = []
    for offence, length in enumerate(rules.BAN_LADDER, start=1):
        if length is None:
            lines.append(f"・Offense {offence}: banned from Wisp permanently")
        else:
            days = _count(length // timedelta(days=1), "day")
            lines.append(f"・Offense {offence}: banned from Wisp for {days}")
    return lines


def rules_text() -> str:
    """Return the How Wisp Works post, with every number taken from the rules."""
    meals = [
        f"・{_TRACK_LABELS[kind]}: {_count(points, 'meal point')}"
        for kind, points in rules.MEAL_POINTS.items()
    ]
    (first_name, _), *later_tiers = rules.BOND_TIERS
    tiers = ", ".join(
        [first_name, *(f"{name} at {needed}" for name, needed in later_tiers)]
    )
    daily_cap = _count(rules.DAILY_MEAL_CAP, "point")
    return "\n".join(
        [
            "♪ How Wisp Works",
            "Wisp is one little guy for the whole server. Share music and he "
            "grows from an egg into a Rockstar. If nobody feeds him, he fades "
            "away and a new egg takes his place.",
            _SEPARATOR,
            "Who can feed him",
            "・Active Lounger or higher",
            "・Open /wisp board once to join in",
            "",
            "What counts",
            "・Suno and viibrmusic.com track links in the track drop",
            *meals,
            "・Every track also earns you leaderboard points",
            f"・Each person's meals count up to {daily_cap} a day",
            "・The same link only feeds him once, ever",
            "",
            "Your bond",
            "・Sharing viibrmusic.com tracks, playing and giving snacks all build "
            "your bond with him",
            f"・After {_count(rules.MEET_AFTER_DAYS, 'different day')} with him, "
            "he learns your name",
            f"・Tiers: {tiers}",
            "",
            "The Lunchbox",
            "・/wisp lunchbox opens his snack box",
            "・Spend leaderboard points on snacks that fill his care",
            "・Snacks count toward the daily limit, so music stays his real food",
            "",
            "Fair play",
            "・Fake links do not count, and staff can strip points",
            f"・Names are capped at {_count(rules.NAME_MAX, 'character')}",
            *_ban_lines(),
            "・Staff can lift any ban",
        ]
    )


# ---
# Studio threads
# ---


@dataclass(frozen=True)
class StudioThread:
    """One thread of the Studio forum and the settings that remember it."""

    attr: str
    name: str
    content: str
    message_attr: str | None = None
    locked: bool = False


STUDIO_THREADS: tuple[StudioThread, ...] = (
    StudioThread(
        "status_thread_id",
        "Status",
        "Wisp's status card will appear here.",
        message_attr="status_message_id",
    ),
    StudioThread(
        "mealtime_thread_id",
        "Mealtime",
        "Every track that feeds Wisp lands here.",
    ),
    StudioThread(
        "lunchbox_thread_id",
        "The Lunchbox",
        "Snacks, badges and song listens. Open the lunchbox with /wisp lunchbox.",
    ),
    StudioThread(
        "jam_thread_id",
        "The Jam Space",
        "Wisp's music space: his favorite songs and the lyrics he is writing.",
    ),
    StudioThread(
        "billboard_thread_id",
        "The Billboard",
        "The leaderboard and Wisp's version history will appear here.",
        message_attr="billboard_message_id",
    ),
    StudioThread("rules_thread_id", "How Wisp Works", rules_text(), locked=True),
)

_THREAD_ATTRS = frozenset(spec.attr for spec in STUDIO_THREADS)
_studio_locks: dict[int, asyncio.Lock] = {}


class StudioError(Exception):
    """The Studio cannot be reached; the message tells staff how to fix it."""


def _studio_forum(
    bot: "WispBot", guild_id: int, settings: Settings
) -> discord.ForumChannel:
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise StudioError("Wisp cannot see this server.")
    if settings.studio_forum_id is None:
        raise StudioError("The Studio forum is not set. Run /wispadmin setup first.")
    forum = guild.get_channel(settings.studio_forum_id)
    if not isinstance(forum, discord.ForumChannel) or forum.is_media():
        raise StudioError(
            "The Studio channel is missing or is not a forum. "
            "Run /wispadmin setup again with a forum channel."
        )
    return forum


async def _open_thread(
    bot: "WispBot", forum_id: int | None, thread_id: int | None
) -> discord.Thread | None:
    """Return a stored Studio thread, unarchived, or None if it is gone."""
    if thread_id is None:
        return None
    try:
        channel = await bot.fetch_channel(thread_id)
    except discord.NotFound:
        return None
    if not isinstance(channel, discord.Thread) or channel.parent_id != forum_id:
        return None
    if channel.archived:
        return await channel.edit(archived=False)
    return channel


async def _create_thread(
    bot: "WispBot", forum: discord.ForumChannel, spec: StudioThread
) -> None:
    """Create one Studio thread, remember it, then pin or lock it as needed."""
    created = await forum.create_thread(
        name=spec.name,
        content=spec.content,
        auto_archive_duration=_ARCHIVE_AFTER_MINUTES,
    )
    values = {spec.attr: created.thread.id}
    if spec.message_attr is not None:
        values[spec.message_attr] = created.message.id
    await bot.settings.update(forum.guild.id, **values)
    if spec.message_attr is not None:
        try:
            await created.message.pin()
        except discord.HTTPException as error:
            await bot.report_error(forum.guild, f"pinning the {spec.name} card", error)
    if spec.locked:
        await created.thread.edit(locked=True)


async def ensure_studio(bot: "WispBot", guild_id: int) -> Settings:
    """Create any Studio thread that is missing and return the guild's settings.

    Threads that already exist are left alone, and archived ones are reopened.
    Threads that were stored but have been deleted are recreated, and staff are
    told about them in the errors channel.

    Raises:
        StudioError: The Studio forum is not set or is not a forum.
    """
    async with _studio_locks.setdefault(guild_id, asyncio.Lock()):
        settings = await bot.settings.get(guild_id)
        forum = _studio_forum(bot, guild_id, settings)
        recreated: list[str] = []
        for spec in STUDIO_THREADS:
            stored: int | None = getattr(settings, spec.attr)
            if await _open_thread(bot, forum.id, stored) is not None:
                continue
            await _create_thread(bot, forum, spec)
            if stored is not None:
                recreated.append(spec.name)
        settings = await bot.settings.get(guild_id)
    if recreated:
        await _announce(bot, forum.guild, settings, recreated)
    return settings


async def _announce(
    bot: "WispBot", guild: discord.Guild, settings: Settings, names: list[str]
) -> None:
    if settings.error_channel_id is None:
        return
    channel = guild.get_channel_or_thread(settings.error_channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        return
    try:
        await channel.send(f"Wisp's Studio: recreated {', '.join(names)}.")
    except discord.HTTPException as error:
        await bot.report_error(guild, "announcing recreated Studio threads", error)


async def studio_thread(bot: "WispBot", guild_id: int, attr: str) -> discord.Thread:
    """Return one of the guild's Studio threads, ready to post in.

    Args:
        bot: The running bot.
        guild_id: The guild whose Studio to use.
        attr: The Settings field that holds the thread id, such as
            "mealtime_thread_id".

    An archived thread is reopened. A thread that no longer exists is recreated
    (see ensure_studio) and the new one is returned.

    Raises:
        ValueError: attr is not a Studio thread setting.
        StudioError: The Studio forum is not set or is not a forum.
    """
    if attr not in _THREAD_ATTRS:
        raise ValueError(f"Not a Studio thread setting: {attr}")
    settings = await bot.settings.get(guild_id)
    thread = await _open_thread(bot, settings.studio_forum_id, getattr(settings, attr))
    if thread is not None:
        return thread
    settings = await ensure_studio(bot, guild_id)
    thread = await _open_thread(bot, settings.studio_forum_id, getattr(settings, attr))
    if thread is None:
        raise StudioError(f"Could not open the Studio thread {attr}.")
    return thread


# ---
# Staff commands
# ---


def _guild_id(interaction: discord.Interaction["WispBot"]) -> int:
    if interaction.guild_id is None:
        raise app_commands.NoPrivateMessage()
    return interaction.guild_id


class Studio(commands.Cog):
    """The /wispadmin commands: Studio setup, qualifying roles and the freeze."""

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot

    wispadmin = app_commands.Group(
        name="wispadmin",
        description="Staff settings for Wisp.",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
        allowed_contexts=app_commands.AppCommandContext(
            guild=True, dm_channel=False, private_channel=False
        ),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
    )
    roles = app_commands.Group(
        name="roles",
        description="Roles that can feed Wisp.",
        parent=wispadmin,
    )

    @wispadmin.command(name="setup", description="Set Wisp's channels and Studio.")
    @app_commands.describe(
        house="Where Wisp talks and announces his big moments",
        studio="The forum for Wisp's Studio threads",
        tracks="The track drop channel Wisp eats from",
        errors="Where Wisp reports errors to staff",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_studio(
        self,
        interaction: discord.Interaction["WispBot"],
        house: discord.TextChannel,
        studio: discord.ForumChannel,
        tracks: discord.TextChannel | discord.ForumChannel,
        errors: discord.TextChannel,
    ) -> None:
        """Save the channels, then create whichever Studio threads are missing."""
        guild_id = _guild_id(interaction)
        await interaction.response.defer(ephemeral=True)
        before = await self.bot.settings.get(guild_id)
        await self.bot.settings.update(
            guild_id,
            house_channel_id=house.id,
            studio_forum_id=studio.id,
            tracks_channel_id=tracks.id,
            error_channel_id=errors.id,
        )
        try:
            after = await ensure_studio(self.bot, guild_id)
        except StudioError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        created = [
            spec.name
            for spec in STUDIO_THREADS
            if getattr(before, spec.attr) != getattr(after, spec.attr)
        ]
        threads = (
            f"Created threads: {', '.join(created)}"
            if created
            else "Studio threads: all six already exist"
        )
        await interaction.followup.send(
            "\n".join(
                [
                    "♪ Wisp is set up.",
                    f"・Wisp's House: {house.mention}",
                    f"・Wisp's Studio: {studio.mention}",
                    f"・Track drop: {tracks.mention}",
                    f"・Errors: {errors.mention}",
                    f"・{threads}",
                ]
            ),
            ephemeral=True,
        )

    @roles.command(name="add", description="Let a role's members feed Wisp.")
    @app_commands.describe(role="The role to add")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def roles_add(
        self, interaction: discord.Interaction["WispBot"], role: discord.Role
    ) -> None:
        """Add a qualifying role."""
        await self.bot.settings.add_role(_guild_id(interaction), role.id)
        await interaction.response.send_message(
            f"♪ {role.mention} can now feed Wisp.", ephemeral=True
        )

    @roles.command(name="remove", description="Stop a role's members feeding Wisp.")
    @app_commands.describe(role="The role to remove")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def roles_remove(
        self, interaction: discord.Interaction["WispBot"], role: discord.Role
    ) -> None:
        """Remove a qualifying role."""
        await self.bot.settings.remove_role(_guild_id(interaction), role.id)
        await interaction.response.send_message(
            f"♪ {role.mention} no longer feeds Wisp.", ephemeral=True
        )

    @roles.command(name="list", description="Show the roles that can feed Wisp.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def roles_list(self, interaction: discord.Interaction["WispBot"]) -> None:
        """List the qualifying roles."""
        role_ids = await self.bot.settings.roles(_guild_id(interaction))
        if role_ids:
            mentions = (f"・<@&{role_id}>" for role_id in sorted(role_ids))
            text = "\n".join(["♪ Roles that can feed Wisp", *mentions])
        else:
            text = "♪ No qualifying roles yet. Add one with /wispadmin roles add."
        await interaction.response.send_message(text, ephemeral=True)

    @wispadmin.command(name="freeze", description="Pause Wisp's care draining.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def freeze(self, interaction: discord.Interaction["WispBot"]) -> None:
        """Freeze Wisp so his care stops draining."""
        await self.bot.settings.update(_guild_id(interaction), frozen=True)
        await interaction.response.send_message(
            "♪ Wisp is frozen. His care will not drain until you unfreeze him.",
            ephemeral=True,
        )

    @wispadmin.command(name="unfreeze", description="Let Wisp's care drain again.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def unfreeze(self, interaction: discord.Interaction["WispBot"]) -> None:
        """Unfreeze Wisp so his care drains normally."""
        await self.bot.settings.update(_guild_id(interaction), frozen=False)
        await interaction.response.send_message(
            "♪ Wisp is unfrozen. His care drains normally again.", ephemeral=True
        )


async def setup(bot: "WispBot") -> None:
    """Load the Studio cog."""
    await bot.add_cog(Studio(bot))
