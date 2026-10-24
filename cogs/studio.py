"""Wisp's Studio: the forum threads he lives in and the staff settings for them."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord
from discord import app_commands

from cogs.assets import ASSETS_DIR
from cogs.faq import fill_faq
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
# Rules post text
# ---


def _ban_line() -> str:
    steps = [
        "permanently" if length is None else count(length // timedelta(days=1), "day")
        for length in rules.BAN_LADDER
    ]
    return f"・Offenses: banned {', then '.join(steps)}"


def rules_text(meal_values: Mapping[TrackKind, int]) -> str:
    """Return the Wisp FAQ's rules post, the live text after its pictures.

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
            "♪ Quick rules (current numbers)",
            "Wisp is one little guy for the whole server. Share music and he "
            "grows from an egg into a Rockstar. If nobody feeds him, he fades "
            "and a new egg takes his place.",
            SEPARATOR,
            "Who can feed him",
            "・Active Lounger or higher",
            "・Open /wisp board once to join in",
            "",
            "What counts",
            "・Suno and viibrmusic.com links in the track drop",
            *meals,
            "・Every track also earns leaderboard points",
            f"・Your meals count up to {daily_cap} a day",
            "・Each link only feeds him once, ever",
            "",
            "Your bond",
            "・viibrmusic.com tracks, games, snacks and kept gifts build your bond",
            f"・After {count(rules.MEET_AFTER_DAYS, 'different day')} with him, "
            "he learns your name",
            f"・Tiers: {tiers}",
            "",
            "The ViiBR Vault",
            "・/wisp vault spends leaderboard points on snacks and gifts",
            "・The leaderboard is the pinned Vault post",
            "・Snacks count toward the meal limit",
            f"・Gifts cost {count(rules.GIFT_COST, 'point')} and he might not keep "
            "them. One per collection a day",
            f"・He keeps one a day: {rules.BOND_PER_KEPT_GIFT} bond, "
            f"{rules.COLLECTION_BOND_BONUS} more for a full set. New Wisps start over",
            "",
            "Your Snack Pack",
            "・/wisp snackpack shows your saved snacks and keepsakes; feed them "
            "from his status card",
            "",
            "Wisp's lunchbox",
            "・/wisp lunchbox shows his favorite songs, snack, emoji and gifts",
            "",
            "His life",
            f"・Around day {rules.OLD_FOGEY_AT_DAY} he grows into an Old Fogey",
            f"・Around day {rules.FAREWELL_AT_DAY} he passes on, a lump of coal "
            "after a full life",
            f"・The coal becomes the next egg, with {rules.COAL_EGG_FOOD} of its "
            f"{egg_meals} already fed",
            f"・That life's top {count(rules.LAST_EMBER_GIFTS, 'sharer')} each get "
            "his Last Ember in their Snack Pack",
            "・Dying of neglect leaves no Last Ember",
            "",
            "Talking to Wisp",
            "・Mention him or reply to him in Wisp's House",
            "・He wobbles as an egg, babbles as a baby and talks as he grows",
            "・Once grown he sometimes chimes in and remembers what you say",
            "・Talking earns no bond or points",
            "",
            "Fair play",
            "・Fake links don't count; staff can strip points",
            f"・Names are capped at {count(rules.NAME_MAX, 'character')}",
            f"{_ban_line()}. Staff can lift bans",
        ]
    )


# ---
# Studio threads
# ---


def rules_post(settings: Settings) -> str:
    """The Wisp FAQ's rules post with the guild's own food values."""
    return rules_text(meal_points(settings))


@dataclass(frozen=True)
class StudioThread:
    """One thread of the Studio forum and the settings that remember it.

    `name` is the thread's exact name in the forum, emoji included; `title` is
    the plain name Wisp uses for it in his messages. `content` is the first
    post's text when the thread is created. `image` is the first post's
    picture, which the forum shows as the post's thumbnail, relative to the
    ASSETS folder.
    """

    attr: str
    name: str
    title: str
    content: str
    message_attr: str | None = None
    locked: bool = False
    image: str | None = None


STUDIO_THREADS: tuple[StudioThread, ...] = (
    StudioThread(
        "status_thread_id",
        "☀️ | Status",
        "Status",
        "Wisp's status card will appear here.",
        message_attr="status_message_id",
    ),
    StudioThread(
        "mealtime_thread_id",
        "🧡 | Mealtime",
        "Mealtime",
        "Every track that feeds Wisp lands here.",
        image="thumbs/mealtime.png",
    ),
    StudioThread(
        "vault_thread_id",
        "🔒| The ViiBR Vault",
        "The ViiBR Vault",
        "The ViiBR Vault is opening.",
        message_attr="vault_message_id",
        image="vault.png",
    ),
    StudioThread(
        "jam_thread_id",
        "⚡｜Jam Space",
        "Jam Space",
        "Wisp's music space: his favorite songs and the lyrics he is writing.",
        image="thumbs/jam_space.png",
    ),
    StudioThread(
        "rules_thread_id",
        "📙｜Wisp FAQ",
        "Wisp FAQ",
        "Loading the FAQ...",
        locked=True,
        image="thumbs/faq.png",
    ),
)

_THREAD_ATTRS = frozenset(spec.attr for spec in STUDIO_THREADS)
_FAQ_ATTR: Final = "rules_thread_id"
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


def _thumbnail(spec: StudioThread) -> Path | None:
    """The thread's thumbnail picture, or None when it has none or it is missing."""
    if spec.image is None or not (path := ASSETS_DIR / spec.image).is_file():
        return None
    return path


async def _create_thread(
    bot: "WispBot", forum: discord.ForumChannel, spec: StudioThread
) -> tuple[discord.Thread, int]:
    """Create one Studio thread and remember it; return it and its first message id."""
    art: dict[str, Any] = {}
    if (path := _thumbnail(spec)) is not None:
        art["file"] = discord.File(path)
    created = await forum.create_thread(
        name=spec.name,
        content=spec.content,
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
    """Name the thread, lock the FAQ, add the thumbnail and pin the card.

    Whatever is already done is skipped. A failed step is posted in the thread
    and retried the next time the Studio is ensured. A card whose message is
    gone is left for the status loop to repost.
    """
    if thread.name != spec.name:
        try:
            await thread.edit(name=spec.name)
        except discord.HTTPException as error:
            await bot.report_error(guild, f"renaming {spec.title}", error, where=thread)
    if spec.locked and not thread.locked:
        try:
            await thread.edit(locked=True)
        except discord.HTTPException as error:
            await bot.report_error(guild, f"locking {spec.title}", error, where=thread)
    await _add_thumbnail(bot, guild, thread, spec)
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
            guild, f"pinning the card in {spec.title}", error, where=thread
        )


async def _add_thumbnail(
    bot: "WispBot", guild: discord.Guild, thread: discord.Thread, spec: StudioThread
) -> None:
    """Give the thread's first post its picture when it has no attachment yet.

    A forum thread's first post has the thread's id. A post that is gone is
    left alone.
    """
    if (path := _thumbnail(spec)) is None:
        return
    try:
        starter = await thread.fetch_message(thread.id)
        if not starter.attachments:
            await starter.edit(attachments=[discord.File(path)])
    except discord.NotFound:
        return
    except discord.HTTPException as error:
        await bot.report_error(
            guild, f"adding the thumbnail to {spec.title}", error, where=thread
        )


async def _build_faq(
    bot: "WispBot", guild: discord.Guild, thread: discord.Thread
) -> None:
    """Fill the Wisp FAQ thread; a failure is posted in it."""
    rules = rules_post(await bot.settings.get(guild.id))
    try:
        await fill_faq(bot, guild.id, thread, rules)
    except (discord.HTTPException, OSError) as error:
        await bot.report_error(guild, "building the Wisp FAQ", error, where=thread)


async def ensure_studio(bot: "WispBot", guild_id: int) -> Settings:
    """Create any Studio thread that is missing and return the guild's settings.

    Threads that already exist are left alone apart from reopening an archived
    one, renaming one whose name has changed, giving a first post with no
    attachment its thumbnail and finishing any lock or pin that is still
    missing. Threads that were stored but have been deleted are recreated, and
    Wisp's House is told about them. The Wisp FAQ is filled when its thread is
    new or has no stored sections, such as a How Wisp Works thread from before
    the FAQ.

    Raises:
        StudioError: The Studio forum is not set or is not a forum.
    """
    async with _studio_locks.setdefault(guild_id, asyncio.Lock()):
        settings = await bot.settings.get(guild_id)
        forum = _studio_forum(bot, guild_id, settings)
        recreated: list[str] = []
        threads: dict[str, discord.Thread] = {}
        created: set[str] = set()
        for spec in STUDIO_THREADS:
            stored: int | None = getattr(settings, spec.attr)
            thread = await _open_thread(bot, forum.id, stored)
            message_id: int | None
            if thread is None:
                thread, message_id = await _create_thread(bot, forum, spec)
                created.add(spec.attr)
                if stored is not None:
                    recreated.append(spec.title)
            else:
                message_id = (
                    getattr(settings, spec.message_attr) if spec.message_attr else None
                )
            await _finish_thread(bot, forum.guild, thread, spec, message_id)
            threads[spec.attr] = thread
        if _FAQ_ATTR in created or not settings.faq_message_ids:
            await _build_faq(bot, forum.guild, threads[_FAQ_ATTR])
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
        spec.title
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


@wispadmin.command(name="faq", description="Rebuild the Wisp FAQ thread.")
@app_commands.checks.has_permissions(manage_guild=True)
async def rebuild_faq(interaction: discord.Interaction["WispBot"]) -> None:
    """Delete Wisp's own FAQ posts and post them fresh with a new contents list.

    Staff use it after the FAQ pictures change. A Discord failure goes to the
    command tree's error handler.
    """
    bot = interaction.client
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        thread = await studio_thread(bot, guild_id, _FAQ_ATTR)
    except StudioError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    async with _studio_locks.setdefault(guild_id, asyncio.Lock()):
        rules = rules_post(await bot.settings.get(guild_id))
        await fill_faq(bot, guild_id, thread, rules)
    await interaction.followup.send("♪ The Wisp FAQ is rebuilt.", ephemeral=True)


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
