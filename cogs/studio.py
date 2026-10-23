"""Wisp's Studio: the forum threads he lives in and the staff settings for them."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

import discord
from discord import app_commands

from cogs.assets import ASSETS_DIR
from cogs.groups import require_guild, wispadmin
from db.settings import Settings, meal_points
from wisp import rules
from wisp.links import TrackKind
from wisp.text import SEPARATOR, count

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_ARCHIVE_AFTER_MINUTES: Final = 10080
_NUMBER_WORDS: Final = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)
TRACK_LABELS: dict[TrackKind, str] = {
    TrackKind.VIIBR: "viibrmusic.com track",
    TrackKind.SUNO: "Suno track",
}

# ---
# How Wisp Works text
# ---


def _ban_lines() -> list[str]:
    lines = []
    for offence, length in enumerate(rules.BAN_LADDER, start=1):
        if length is None:
            lines.append(f"・Offense {offence}: banned from Wisp permanently")
        else:
            days = count(length // timedelta(days=1), "day")
            lines.append(f"・Offense {offence}: banned from Wisp for {days}")
    return lines


def rules_text(meal_values: Mapping[TrackKind, int]) -> str:
    """Return the How Wisp Works post.

    The meal points are the guild's effective values; every other number is
    taken from the rules.
    """
    meals = [
        f"・{TRACK_LABELS[kind]}: {count(points, 'meal point')}"
        for kind, points in meal_values.items()
    ]
    (first_name, _), *later_tiers = rules.BOND_TIERS
    tiers = ", ".join(
        [first_name, *(f"{name} at {needed}" for name, needed in later_tiers)]
    )
    daily_cap = count(rules.DAILY_MEAL_CAP, "point")
    egg_meals = count(rules.EGG_FOOD_NEEDED, "meal point")
    return "\n".join(
        [
            "♪ How Wisp Works",
            "Wisp is one little guy for the whole server. Share music and he "
            "grows from an egg into a Rockstar. If nobody feeds him, he fades "
            "away and a new egg takes his place.",
            SEPARATOR,
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
            f"・After {count(rules.MEET_AFTER_DAYS, 'different day')} with him, "
            "he learns your name",
            f"・Tiers: {tiers}",
            "",
            "The ViiBR Vault",
            "・/wisp vault buys snacks with your leaderboard points",
            "・The leaderboard lives on the pinned Vault post",
            "・Snacks count toward the daily limit, so music stays his real food",
            "",
            "Your lunchbox",
            "・/wisp lunchbox shows your saved snacks and keepsakes",
            "・Feed saved snacks to him from his status card",
            "",
            "His life",
            f"・Around day {rules.OLD_FOGEY_AT_DAY} he gets old and becomes an "
            "Old Fogey",
            f"・Around day {rules.FAREWELL_AT_DAY} he passes on after a full "
            "life, as a lump of coal",
            "・The coal becomes the next egg, already fed "
            f"{rules.COAL_EGG_FOOD} of the {egg_meals} it needs",
            f"・The top {count(rules.LAST_EMBER_GIFTS, 'sharer')} of that life "
            "each get his Last Ember",
            "・A Wisp who goes out from neglect leaves no gifts",
            "",
            "Talking to Wisp",
            "・Mention him or reply to him in Wisp's House",
            "・He wobbles as an egg, babbles as a baby and learns to talk as he "
            "grows",
            "・Once grown he sometimes chimes in and remembers what you tell him",
            "・Talking earns nothing: no bond and no points",
            "",
            "Fair play",
            "・Fake links do not count, and staff can strip points",
            f"・Names are capped at {count(rules.NAME_MAX, 'character')}",
            *_ban_lines(),
            "・Staff can lift any ban",
        ]
    )


# ---
# Studio threads
# ---


def rules_post(settings: Settings) -> str:
    """The How Wisp Works post with the guild's own food values."""
    return rules_text(meal_points(settings))


@dataclass(frozen=True)
class StudioThread:
    """One thread of the Studio forum and the settings that remember it.

    `content` is the first post's text, or a function that writes it from the
    guild's settings when the thread is created.
    """

    attr: str
    name: str
    content: str | Callable[[Settings], str]
    message_attr: str | None = None
    locked: bool = False
    image: str | None = None


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
        "vault_thread_id",
        "The ViiBR Vault",
        "The ViiBR Vault is opening.",
        message_attr="vault_message_id",
        image="vault.png",
    ),
    StudioThread(
        "jam_thread_id",
        "The Jam Space",
        "Wisp's music space: his favorite songs and the lyrics he is writing.",
    ),
    StudioThread(
        "rules_thread_id",
        "How Wisp Works",
        rules_post,
        message_attr="rules_message_id",
        locked=True,
    ),
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
    bot: "WispBot", forum: discord.ForumChannel, spec: StudioThread, settings: Settings
) -> tuple[discord.Thread, int]:
    """Create one Studio thread and remember it; return it and its first message id."""
    art: dict[str, Any] = {}
    if spec.image is not None and (path := ASSETS_DIR / spec.image).is_file():
        art["file"] = discord.File(path)
    content = spec.content if isinstance(spec.content, str) else spec.content(settings)
    created = await forum.create_thread(
        name=spec.name,
        content=content,
        auto_archive_duration=_ARCHIVE_AFTER_MINUTES,
        **art,
    )
    values = {spec.attr: created.thread.id}
    if spec.message_attr is not None:
        values[spec.message_attr] = created.message.id
    await bot.settings.update(forum.guild.id, **values)
    return created.thread, created.message.id


async def _finish_thread(
    bot: "WispBot",
    guild: discord.Guild,
    thread: discord.Thread,
    spec: StudioThread,
    message_id: int | None,
) -> None:
    """Lock the rules thread and pin the card, skipping whatever is already done.

    A failed step is posted in the thread and retried the next time the Studio
    is ensured. A card whose message is gone is left for the status loop to
    repost.
    """
    if spec.locked and not thread.locked:
        try:
            await thread.edit(locked=True)
        except discord.HTTPException as error:
            await bot.report_error(guild, f"locking {spec.name}", error, where=thread)
    if spec.message_attr is None or message_id is None:
        return
    try:
        message = await thread.fetch_message(message_id)
        if not message.pinned:
            await message.pin()
    except discord.NotFound:
        return
    except discord.HTTPException as error:
        await bot.report_error(
            guild, f"pinning the card in {spec.name}", error, where=thread
        )


async def ensure_studio(bot: "WispBot", guild_id: int) -> Settings:
    """Create any Studio thread that is missing and return the guild's settings.

    Threads that already exist are left alone apart from reopening an archived
    one and finishing any lock or pin that is still missing. Threads that were
    stored but have been deleted are recreated, and Wisp's House is told about
    them.

    Raises:
        StudioError: The Studio forum is not set or is not a forum.
    """
    async with _studio_locks.setdefault(guild_id, asyncio.Lock()):
        settings = await bot.settings.get(guild_id)
        forum = _studio_forum(bot, guild_id, settings)
        recreated: list[str] = []
        for spec in STUDIO_THREADS:
            stored: int | None = getattr(settings, spec.attr)
            thread = await _open_thread(bot, forum.id, stored)
            message_id: int | None
            if thread is None:
                thread, message_id = await _create_thread(bot, forum, spec, settings)
                if stored is not None:
                    recreated.append(spec.name)
            else:
                message_id = (
                    getattr(settings, spec.message_attr) if spec.message_attr else None
                )
            await _finish_thread(bot, forum.guild, thread, spec, message_id)
        settings = await bot.settings.get(guild_id)
    if recreated:
        await _announce(bot, forum.guild, recreated)
    return settings


async def _announce(bot: "WispBot", guild: discord.Guild, names: list[str]) -> None:
    house = await bot.house_channel(guild)
    if house is None:
        return
    try:
        await house.send(
            f"Wisp's Studio: recreated {', '.join(names)}.", allowed_mentions=_NO_PING
        )
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


roles = app_commands.Group(
    name="roles", description="Roles that can feed Wisp.", parent=wispadmin
)


@wispadmin.command(name="setup", description="Set Wisp's channels and Studio.")
@app_commands.describe(
    house="Where Wisp talks and announces his big moments",
    studio="The forum for Wisp's Studio threads",
    tracks="The track drop channel Wisp eats from",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_studio(
    interaction: discord.Interaction["WispBot"],
    house: discord.TextChannel,
    studio: discord.ForumChannel,
    tracks: discord.TextChannel | discord.ForumChannel,
) -> None:
    """Save the channels, then create whichever Studio threads are missing."""
    bot = interaction.client
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    before = await bot.settings.get(guild_id)
    await bot.settings.update(
        guild_id,
        house_channel_id=house.id,
        studio_forum_id=studio.id,
        tracks_channel_id=tracks.id,
    )
    try:
        after = await ensure_studio(bot, guild_id)
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
        else f"Studio threads: all {_NUMBER_WORDS[len(STUDIO_THREADS)]} already exist"
    )
    await interaction.followup.send(
        "\n".join(
            [
                "♪ Wisp is set up.",
                f"・Wisp's House: {house.mention}",
                f"・Wisp's Studio: {studio.mention}",
                f"・Track drop: {tracks.mention}",
                f"・{threads}",
            ]
        ),
        ephemeral=True,
    )


@roles.command(name="add", description="Let a role's members feed Wisp.")
@app_commands.describe(role="The role to add")
@app_commands.checks.has_permissions(manage_guild=True)
async def roles_add(
    interaction: discord.Interaction["WispBot"], role: discord.Role
) -> None:
    """Add a qualifying role."""
    await interaction.client.settings.add_role(require_guild(interaction), role.id)
    await interaction.response.send_message(
        f"♪ {role.mention} can now feed Wisp.", ephemeral=True
    )


@roles.command(name="remove", description="Stop a role's members feeding Wisp.")
@app_commands.describe(role="The role to remove")
@app_commands.checks.has_permissions(manage_guild=True)
async def roles_remove(
    interaction: discord.Interaction["WispBot"], role: discord.Role
) -> None:
    """Remove a qualifying role."""
    await interaction.client.settings.remove_role(require_guild(interaction), role.id)
    await interaction.response.send_message(
        f"♪ {role.mention} no longer feeds Wisp.", ephemeral=True
    )


@roles.command(name="list", description="Show the roles that can feed Wisp.")
@app_commands.checks.has_permissions(manage_guild=True)
async def roles_list(interaction: discord.Interaction["WispBot"]) -> None:
    """List the qualifying roles."""
    role_ids = await interaction.client.settings.roles(require_guild(interaction))
    if role_ids:
        mentions = (f"・<@&{role_id}>" for role_id in sorted(role_ids))
        text = "\n".join(["♪ Roles that can feed Wisp", *mentions])
    else:
        text = "♪ No qualifying roles yet. Add one with /wispadmin roles add."
    await interaction.response.send_message(text, ephemeral=True)


@wispadmin.command(name="freeze", description="Pause Wisp's care draining.")
@app_commands.checks.has_permissions(manage_guild=True)
async def freeze(interaction: discord.Interaction["WispBot"]) -> None:
    """Freeze Wisp so his care stops draining."""
    await interaction.client.settings.update(require_guild(interaction), frozen=True)
    await interaction.response.send_message(
        "♪ Wisp is frozen. His care will not drain until you unfreeze him.",
        ephemeral=True,
    )


@wispadmin.command(name="unfreeze", description="Let Wisp's care drain again.")
@app_commands.checks.has_permissions(manage_guild=True)
async def unfreeze(interaction: discord.Interaction["WispBot"]) -> None:
    """Unfreeze Wisp so his care drains normally."""
    await interaction.client.settings.update(require_guild(interaction), frozen=False)
    await interaction.response.send_message(
        "♪ Wisp is unfrozen. His care drains normally again.", ephemeral=True
    )


async def setup(bot: "WispBot") -> None:
    """Load the Studio extension; its commands join the shared groups on import."""
