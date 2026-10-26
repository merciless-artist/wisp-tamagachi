"""Wisp's Studio: the forum threads he lives in and the staff settings for them."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord
from discord import app_commands
from discord.ext import commands

from cogs.assets import ASSETS_DIR
from cogs.badges import ensure_badge_roles
from cogs.channels import where_of
from cogs.faq import FAQ_SECTIONS, fill_faq
from cogs.groups import wispadmin
from cogs.pictures import Picture, art_kwargs, life_image
from cogs.speech import POKE_ID, poke_view
from cogs.staff import StaffContext, guild_of, refused, reply, usage_line
from db.settings import Settings, meal_points
from wisp import rules
from wisp.life import Life, is_over
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
HOUSE_PANEL: Final = "♪ Poke Wisp\n・tap the button, or mention @Wisp to talk"
_PANEL_CONTEXT: Final = "setting up the Poke Wisp panel in Wisp's House"
_PANEL_ATTR: Final = "house_panel_message_id"
_HOUSE_IS_TRACKS: Final = (
    "♪ Wisp's House can't be the track drop, since Wisp never posts there. "
    "Pick a different channel for one of them."
)
_PANEL_LABEL: Final = "Poke Wisp panel"
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
            "and a new egg takes over.",
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
            "・Be there as he grows to win a keepsake",
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
        raise StudioError("The Studio forum is not set. Run !wisp setup first.")
    forum = guild.get_channel(settings.studio_forum_id)
    if not isinstance(forum, discord.ForumChannel) or forum.is_media():
        raise StudioError(
            "The Studio channel is missing or is not a forum. "
            "Run !wisp setup again with a forum channel."
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
    new or does not have one stored post per section: a How Wisp Works thread
    from before the FAQ, a build that stopped part way or a release with a
    different number of sections.

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
        stored_sections = len(settings.faq_message_ids or ())
        if _FAQ_ATTR in created or stored_sections != len(FAQ_SECTIONS):
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
# House panel
# ---


def _has_poke_button(message: discord.Message) -> bool:
    return any(
        isinstance(child, discord.Button) and child.custom_id == POKE_ID
        for row in message.components
        if isinstance(row, discord.ActionRow)
        for child in row.children
    )


async def _stored_panel(
    house: discord.abc.Messageable, message_id: int | None
) -> discord.Message | None:
    if message_id is None:
        return None
    try:
        return await house.fetch_message(message_id)
    except discord.NotFound:
        return None


def _attachment_edit(
    panel: discord.Message,
) -> Callable[[discord.File | None], Awaitable[discord.Message]]:
    """An edit of the panel's picture alone; no picture clears it."""
    return lambda art: panel.edit(attachments=[] if art is None else [art])


def _remember(
    bot: "WispBot", guild_id: int, message_id: int, attached: str | None
) -> None:
    if attached is not None:
        bot.shown_images[(guild_id, _PANEL_ATTR)] = (message_id, attached)


async def ensure_house_panel(
    bot: "WispBot", guild: discord.Guild, where: discord.abc.Messageable | None
) -> None:
    """Make sure Wisp's House has its one pinned Poke Wisp panel.

    The panel shows Wisp's current picture when he has one. A stored panel
    that still exists is left alone, apart from pinning it again, giving it
    back its button and adding the picture when it has none. One that is gone
    is posted anew, with the picture, and pinned. A failure, such as a missing
    Pin Messages permission, is reported in `where`.
    """
    house = await bot.house_channel(guild)
    if house is None:
        return
    stored = (await bot.settings.get(guild.id)).house_panel_message_id
    life = await bot.lives.current(guild.id)
    image = None if life is None or is_over(life) else life_image(life)
    picture = Picture(bot, guild.id, where, _PANEL_ATTR, _PANEL_LABEL)
    try:
        panel = await _stored_panel(house, stored)
        if panel is None:
            panel, attached = await picture.attach(
                image,
                lambda art: house.send(
                    HOUSE_PANEL,
                    view=poke_view(),
                    allowed_mentions=_NO_PING,
                    **art_kwargs("file", art),
                ),
            )
            _remember(bot, guild.id, panel.id, attached)
            await bot.settings.update(guild.id, house_panel_message_id=panel.id)
        else:
            if not _has_poke_button(panel):
                await panel.edit(view=poke_view())
            if image is not None and not panel.attachments:
                _, attached = await picture.attach(image, _attachment_edit(panel))
                _remember(bot, guild.id, panel.id, attached)
        if not panel.pinned:
            await panel.pin()
    except discord.HTTPException as error:
        await bot.report_error(guild, _PANEL_CONTEXT, error, where=where)


async def refresh_house_panel(bot: "WispBot", guild_id: int, life: Life) -> None:
    """Keep the House panel's picture on Wisp as he is now; the tick calls this.

    Only the attachment is edited, and only when the picture is not the one
    this process last attached; after a restart it is attached once more. A
    life that is over, missing art or a panel that is gone leave the panel
    alone; setup posts a missing one again. A failure is reported in the House
    once per streak.
    """
    image = None if is_over(life) else life_image(life)
    message_id = (await bot.settings.get(guild_id)).house_panel_message_id
    key = (guild_id, _PANEL_ATTR)
    if (
        image is None
        or message_id is None
        or bot.shown_images.get(key) == (message_id, image.name)
    ):
        return
    guild = bot.get_guild(guild_id)
    house = await bot.house_channel(guild)
    if house is None:
        return
    picture = Picture(bot, guild_id, house, _PANEL_ATTR, _PANEL_LABEL)
    try:
        panel = await house.fetch_message(message_id)
        _, attached = await picture.attach(image, _attachment_edit(panel))
    except discord.NotFound:
        bot.failing_displays.discard(key)
        return
    except discord.HTTPException as error:
        if key not in bot.failing_displays:
            bot.failing_displays.add(key)
            await bot.report_error(
                guild, f"updating the {_PANEL_LABEL} picture", error, where=house
            )
        return
    bot.failing_displays.discard(key)
    _remember(bot, guild_id, message_id, attached)


# ---
# Setup and FAQ, shared by both ways staff run them
# ---


async def set_up(
    bot: "WispBot",
    guild: discord.Guild,
    house: discord.TextChannel,
    studio: discord.ForumChannel,
    tracks: discord.TextChannel | discord.ForumChannel,
    where: discord.abc.Messageable | None,
) -> str:
    """Save the channels, then make the House panel, Studio threads and badge roles.

    Failures along the way are reported in `where`. A House that is also the
    track drop is refused, since Wisp never posts there. Returns the answer
    for staff.
    """
    if house.id == tracks.id:
        return _HOUSE_IS_TRACKS
    before = await bot.settings.get(guild.id)
    await bot.settings.update(
        guild.id,
        house_channel_id=house.id,
        studio_forum_id=studio.id,
        tracks_channel_id=tracks.id,
    )
    await ensure_house_panel(bot, guild, where)
    try:
        after = await ensure_studio(bot, guild.id)
    except StudioError as error:
        return str(error)
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
    badge_lines = await ensure_badge_roles(bot, guild, where)
    return "\n".join(
        [
            "♪ Wisp is set up.",
            f"・Wisp's House: {house.mention}",
            f"・Wisp's Studio: {studio.mention}",
            f"・Track drop: {tracks.mention}",
            f"・{threads}",
            *badge_lines,
        ]
    )


async def rebuild(bot: "WispBot", guild_id: int) -> str:
    """Delete Wisp's own FAQ posts and post them fresh with a new contents list.

    Staff use it after the FAQ pictures change. A Discord failure is raised to
    the command's error handler. Returns the answer for staff.
    """
    try:
        thread = await studio_thread(bot, guild_id, _FAQ_ATTR)
    except StudioError as error:
        return str(error)
    async with _studio_locks.setdefault(guild_id, asyncio.Lock()):
        rules = rules_post(await bot.settings.get(guild_id))
        await fill_faq(bot, guild_id, thread, rules)
    return "♪ The Wisp FAQ is rebuilt."


@wispadmin.command(
    name="setup", description="Set Wisp's channels, Studio and badge roles."
)
@app_commands.describe(
    house="Where Wisp talks and announces his big moments",
    studio="The forum for Wisp's Studio threads",
    tracks="The track drop channel Wisp eats from",
)
async def setup_slash(
    interaction: discord.Interaction["WispBot"],
    house: discord.TextChannel,
    studio: discord.ForumChannel,
    tracks: discord.TextChannel | discord.ForumChannel,
) -> None:
    """The slash form of `!wisp setup`, answered privately."""
    if await refused(interaction) or interaction.guild is None:
        return
    await interaction.response.defer(ephemeral=True)
    text = await set_up(
        interaction.client,
        interaction.guild,
        house,
        studio,
        tracks,
        where_of(interaction),
    )
    await interaction.followup.send(text, ephemeral=True, allowed_mentions=_NO_PING)


@wispadmin.command(name="faq", description="Rebuild the Wisp FAQ thread.")
async def faq_slash(interaction: discord.Interaction["WispBot"]) -> None:
    """The slash form of `!wisp faq`, answered privately."""
    if await refused(interaction) or interaction.guild_id is None:
        return
    await interaction.response.defer(ephemeral=True)
    text = await rebuild(interaction.client, interaction.guild_id)
    await interaction.followup.send(text, ephemeral=True, allowed_mentions=_NO_PING)


# ---
# Staff commands
# ---


@commands.command(name="setup", usage="#house #studio #tracks")
async def setup_studio(
    ctx: StaffContext,
    house: discord.TextChannel,
    studio: discord.ForumChannel,
    tracks: discord.TextChannel | discord.ForumChannel,
) -> None:
    """Save the channels, then make the House panel, Studio threads and badges."""
    await reply(
        ctx, await set_up(ctx.bot, guild_of(ctx), house, studio, tracks, ctx.channel)
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
    """Add a qualifying role."""
    await ctx.bot.settings.add_role(guild_of(ctx).id, role.id)
    await reply(ctx, f"♪ {role.mention} can now feed Wisp.")


@roles.command(name="remove", usage="@role")
async def roles_remove(ctx: StaffContext, role: discord.Role) -> None:
    """Remove a qualifying role."""
    await ctx.bot.settings.remove_role(guild_of(ctx).id, role.id)
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


@commands.command(name="faq")
async def rebuild_faq(ctx: StaffContext) -> None:
    """Rebuild the Wisp FAQ after its pictures change."""
    await reply(ctx, await rebuild(ctx.bot, guild_of(ctx).id))


@commands.command(name="freeze")
async def freeze(ctx: StaffContext) -> None:
    """Freeze Wisp so his meters stop draining."""
    await ctx.bot.settings.update(guild_of(ctx).id, frozen=True)
    await reply(
        ctx, "♪ Wisp is frozen. His meters will not drain until you unfreeze him."
    )


@commands.command(name="unfreeze")
async def unfreeze(ctx: StaffContext) -> None:
    """Unfreeze Wisp so his meters drain normally."""
    await ctx.bot.settings.update(guild_of(ctx).id, frozen=False)
    await reply(ctx, "♪ Wisp is unfrozen. His meters drain normally again.")


@commands.command(name="eggs", usage="on|off")
async def eggs(ctx: StaffContext, state: str) -> None:
    """Turn laying the next egg on or off, in any case. A living Wisp is not affected.

    Turned back on with no living Wisp, the life loop lays the egg on its next
    tick. Anything but on or off gets the usage line.
    """
    choice = state.lower()
    if choice not in ("on", "off"):
        await reply(ctx, usage_line(eggs))
        return
    bot = ctx.bot
    guild_id = guild_of(ctx).id
    on = choice == "on"
    await bot.settings.update(guild_id, lay_eggs=on)
    if not on:
        text = (
            "♪ New eggs are off. When Wisp's life ends, no new egg will be laid "
            "until you turn eggs back on."
        )
    else:
        life = await bot.lives.current(guild_id)
        text = "♪ New eggs are on."
        if life is None or is_over(life):
            text += " A new egg arrives within a few minutes."
    await reply(ctx, text)


async def setup(bot: "WispBot") -> None:
    """Load the Studio staff commands."""
    for command in (setup_studio, roles, rebuild_faq, freeze, unfreeze, eggs):
        bot.add_command(command)
