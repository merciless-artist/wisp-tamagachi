"""Wisp's Studio: the forum threads he lives in and the staff settings for them."""

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands

from cogs.assets import ASSETS_DIR, BANNERS
from cogs.badges import ensure_badge_roles
from cogs.channels import where_of
from cogs.faq import FAQ_PICTURE_COUNT, fill_faq
from cogs.groups import wispadmin
from cogs.pictures import Picture, art_kwargs, life_image
from cogs.rooms import RoomError, ensure_rooms
from cogs.speech import POKE_ID, poke_view
from cogs.staff import StaffContext, guild_of, refused, reply, usage_line
from db.settings import Settings, meal_points
from wisp import rules
from wisp.chores import nap_starts_on
from wisp.life import Life, is_over
from wisp.links import TrackKind
from wisp.text import (
    MESSAGE_LIMIT,
    SEPARATOR,
    any_role,
    count,
    frame_of,
    text_length,
    timestamp,
)

if TYPE_CHECKING:
    from app import WispBot

log = logging.getLogger("wisp")
_NO_PING: Final = discord.AllowedMentions.none()
_LINK_SCHEMES: Final = frozenset({"http", "https"})
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
_GENERAL_IS_TRACKS: Final = (
    "♪ General chat can't be the track drop, since Wisp never posts there. "
    "Pick a different channel for one of them."
)
_PANEL_LABEL: Final = "Poke Wisp panel"
_NO_FEEDING_ROLES: Final = (
    "・No feeding roles yet, so nobody can feed Wisp. "
    "Add one with !wisp roles add @role."
)
_NO_HELPER_ROLE: Final = (
    "・No helper role yet, so nobody is pinged when Wisp needs a hand. "
    "Set one with !wisp helperrole @role."
)
_HELPER_ROLE_DELETED: Final = (
    "・The helper role was deleted, so nobody is pinged. "
    "Set one with !wisp helperrole @role."
)
_CANNOT_PING: Final = (
    "・Wisp can't ping {role} yet. Turn on 'Allow anyone to @mention this role' "
    "for it, or give Wisp Mention Everyone in his House."
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


def rules_text(
    meal_values: Mapping[TrackKind, int],
    feeding_roles: Collection[int] = (),
    *,
    day: date,
    divider: str = SEPARATOR,
) -> str:
    """Return the Wisp FAQ's rules post, the live text after its pictures.

    The meal points are the guild's effective values and `feeding_roles` the
    roles that can feed Wisp, named as mentions (the post pings nobody);
    every other number is taken from the rules. The nap times are his naps
    on `day`, as timestamps. `divider` is the line under the opening lines.
    """
    feeders = any_role(feeding_roles, rules.FEEDING_ROLES_SHOWN) or (
        "a role that can feed Wisp"
    )
    meals = [
        f"・{TRACK_LABELS[kind]}: {count(points, 'meal point')}"
        for kind, points in meal_values.items()
    ]
    (first_name, _), *later_tiers = rules.BOND_TIERS
    tiers = ", ".join(
        [first_name, *(f"{name} {needed}" for name, needed in later_tiers)]
    )
    daily_cap = rules.DAILY_MEAL_CAP
    sick_cap = rules.DAILY_MEAL_CAP + rules.SICK_EXTRA_MEAL_CAP
    sick_hours = rules.SICK_FOR // timedelta(hours=1)
    pox_minutes = rules.POX_HEALED_PER_MEAL_POINT // timedelta(minutes=1)
    health_hours = rules.HEALTH_STRETCH // timedelta(hours=1)
    chat_points = count(rules.CHAT_POINTS, "point")
    rockstar_days = rules.ROCKSTAR_WELLBEING_FOR // timedelta(days=1)
    nap_times = ", ".join(timestamp(start) for start in nap_starts_on(day))
    return "\n".join(
        [
            "♪ Quick rules (current numbers)",
            "One Wisp per server: share music and he grows.",
            divider,
            "Who can feed him and earn points",
            f"・Anyone with {feeders} who opened /wisp board",
            "",
            "What counts",
            "・Links in the track drop:",
            *meals,
            "・Each link feeds him once, for leaderboard points. "
            f"Up to {daily_cap} a day",
            "",
            "His meters",
            "・Health: tracks, cleanups. A track fills more when fewer feed. "
            f"{health_hours} h with no track costs "
            f"{rules.HEALTH_PENALTY:g}. Hangry when low, dies at 0",
            f"・Wellbeing: chats ({rules.CHAT_CREDITS_PER_DAY} a day), pokes "
            f"({rules.POKE_CREDITS_PER_DAY} a day), duels "
            f"({rules.PLAYS_PER_DAY} a day), snacks, gifts. Low is lonely, "
            f"never hurt. Rockstar: {rules.ROCKSTAR_WELLBEING} for "
            f"{rockstar_days} days",
            "",
            "Chores",
            "・First press wins WC",
            f"・Clean up his mess in {_short_span(rules.MESS_LEFT_FOR)} or he "
            "catches a cold; "
            f"medicine ({rules.MEDICINE_COST} WC) cures it",
            f"・Scold a tantrum in {_short_span(rules.TANTRUM_WINDOW)} or "
            "Wellbeing drops "
            f"{rules.TANTRUM_WELLBEING_PENALTY:g}",
            f"・Lights off at naps ({nap_times}) in "
            f"{_short_span(rules.LIGHTS_WINDOW)} "
            f"or Wellbeing drops {rules.LIGHTS_WELLBEING_PENALTY:g}",
            "",
            "Your bond",
            "・Tracks, games, snacks, gifts build it",
            f"・After {count(rules.MEET_AFTER_DAYS, 'different day')}, "
            "he learns your name",
            f"・Tiers: {tiers}",
            "",
            "The ViiBR Vault",
            "・/wisp vault spends WC on snacks and gifts",
            f"・Gifts cost {rules.GIFT_COST} WC and he might not keep "
            "them. One per collection a day",
            f"・He keeps one a day: {rules.BOND_PER_KEPT_GIFT} bond, "
            f"+{rules.COLLECTION_BOND_BONUS} for a full set. New Wisps start over",
            "・/wisp snackpack: your snacks and keepsakes. /wisp lunchbox: his "
            "favorites and gifts",
            "",
            "His life",
            f"・Old Fogey at day {rules.OLD_FOGEY_AT_DAY}, passes on at day "
            f"{rules.FAREWELL_AT_DAY}; his coal is a new egg, "
            f"{rules.COAL_EGG_FOOD} of {rules.EGG_FOOD_NEEDED} fed",
            f"・That life's top {count(rules.LAST_EMBER_GIFTS, 'sharer')} get his "
            "Last Ember, unless he was neglected",
            f"・Once, as a Baby or Child: Monster Pox, {sick_hours} h max, "
            f"{pox_minutes} min off per meal point. He can't die, tracks count up "
            f"to {sick_cap} a day",
            "",
            "Talking to Wisp",
            "・Mention or reply to him in Wisp's House. Talking earns no bond",
            f"・First chat or poke each day earns {chat_points}",
            "",
            "Fair play",
            "・No fake links; staff strip points. Names max " f"{rules.NAME_MAX} chars",
            f"{_ban_line()}",
        ]
    )


# ---
# Studio threads
# ---


def _short_span(length: timedelta) -> str:
    """A chore's window for the rules post: "4 h" in whole hours, else "55 min"."""
    minutes = length // timedelta(minutes=1)
    return f"{minutes // 60} h" if minutes % 60 == 0 else f"{minutes} min"


async def rules_post(bot: "WispBot", guild_id: int) -> str:
    """The Wisp FAQ's rules post with the guild's own food values and roles,
    and today's (UTC) nap times.

    The divider is the house style's footer bar, unless that takes the post
    over one message: then it is a blank line. The bar is five app emojis,
    about 150 characters, which a long post may have no room for.
    """
    values = meal_points(await bot.settings.get(guild_id))
    roles = await bot.settings.roles(guild_id)
    day = discord.utils.utcnow().date()
    framed = rules_text(values, roles, day=day, divider=frame_of(bot.emoji).divider)
    if text_length(framed) <= MESSAGE_LIMIT:
        return framed
    return rules_text(values, roles, day=day, divider="")


@dataclass(frozen=True)
class StudioThread:
    """One thread of the Studio forum and the settings that remember it.

    `name` is the thread's exact name in the forum, emoji included; `title` is
    the plain name Wisp uses for it in his messages. `content` is the first
    post's text when the thread is created. `image` is the first post's one
    picture, Myra's banner for the post, which the forum shows as the post's
    thumbnail, relative to the ASSETS folder. The Status post has none here:
    its banner follows Wisp's stage, so the status card shows it
    (`cogs.status_card`). The `pinned_post` stays at the top of the forum and
    every other post is unpinned, since Discord pins one post per forum; the
    posts are ensured in order, so the old pin comes off before the new one
    goes on. The card in `message_attr`
    is pinned in its thread unless `pin_card` is False, as for the
    Leaderboard, whose card must stay the thread's last post.
    """

    attr: str
    name: str
    title: str
    content: str
    message_attr: str | None = None
    locked: bool = False
    image: str | None = None
    pinned_post: bool = False
    pin_card: bool = True


STUDIO_THREADS: tuple[StudioThread, ...] = (
    StudioThread(
        "status_thread_id",
        "☀️ | STATUS (ʜᴇᴀʟᴛʜ | ᴡᴇʟʟʙᴇɪɴɢ | ʟɪꜰᴇ ꜱᴛᴀɢᴇ)",
        "Status",
        "Wisp's status card will appear here.",
        message_attr="status_message_id",
    ),
    StudioThread(
        "mealtime_thread_id",
        "🧡 | MEALTIME (ᴡʜᴀᴛ ᴡiꜱᴘ ᴀᴛᴇ)",
        "Mealtime",
        "Every track that feeds Wisp lands here.",
        image=f"{BANNERS}/mealtime.png",
    ),
    StudioThread(
        "vault_thread_id",
        "🏆 | LEADERBOARD (ᴡʜᴏ ɪꜱ ᴡɪɴɴɪɴɢ)",
        "Leaderboard",
        "The Leaderboard is opening.",
        message_attr="vault_message_id",
        image=f"{BANNERS}/leaderboard.png",
        pin_card=False,
    ),
    StudioThread(
        "jam_thread_id",
        "⚡｜JAM SPACE (ᴡiꜱᴘ'ꜱ ᴍᴜꜱɪᴄ)",
        "Jam Space",
        "Wisp's music space: his favorite songs and the lyrics he is writing.",
        image=f"{BANNERS}/jamspace.png",
    ),
    StudioThread(
        "rules_thread_id",
        "📙｜WiSP FAQ (ʀᴜʟᴇꜱ | ɪɴꜰᴏ)",
        "Wisp FAQ",
        "Loading the FAQ...",
        locked=True,
        image=f"{BANNERS}/faq.png",
    ),
    StudioThread(
        "shop_thread_id",
        "🛍️ | ViiBR VAULT (ꜱʜᴏᴘ ꜰᴏʀ ᴛᴏʏꜱ | ꜱɴᴀᴄᴋꜱ | ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ)",
        "ViiBR Vault",
        "♪ The ViiBR Vault\n"
        "・Pick something from a shelf's menu. Only you see your receipt.\n"
        "・Snacks go in your Snack Pack, to feed him later. Gifts, badges and "
        "medicine work right away.",
        image=f"{BANNERS}/viibrvault.png",
    ),
    StudioThread(
        "interaction_thread_id",
        "🕹️ | INTERACT (ᴘᴏᴋᴇ | ᴘʟᴀʏ | ꜱɴᴀᴄᴋꜱ | ʟᴜɴᴄʜʙᴏx)",
        "Interaction",
        "♪ Interaction\n・Feed, poke, shop and play with Wisp with the buttons below.",
        image=f"{BANNERS}/interaction.png",
        pinned_post=True,
    ),
)

_THREAD_ATTRS = frozenset(spec.attr for spec in STUDIO_THREADS)
_FAQ_ATTR: Final = "rules_thread_id"
_SHOP_ATTR: Final = "shop_thread_id"
_INTERACTION_ATTR: Final = "interaction_thread_id"
STUDIO_ENSURED: Final = "studio_ensured"
"""The event dispatched with the guild id each time the Studio is ensured."""
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


def _banner(spec: StudioThread) -> Path | None:
    """The thread's banner, or None when it has none or it is missing."""
    if spec.image is None or not (path := ASSETS_DIR / spec.image).is_file():
        return None
    return path


def _upload_name(path: Path) -> str:
    """A banner's file name in Discord: its path under ASSETS with "_" for "/",
    then the first 8 hex digits of its SHA-256.

    The folder tells a banner from older art of the same file name, such as
    thumbs/mealtime.png, and the digits change whenever Myra redraws a banner
    under the same name, so setup knows to swap it in.
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    flat = path.relative_to(ASSETS_DIR).with_suffix("").as_posix().replace("/", "_")
    return f"{flat}_{digest}{path.suffix}"


def _banner_file(path: Path) -> discord.File:
    """The banner as a Discord file under its upload name."""
    return discord.File(path, filename=_upload_name(path))


async def _show_as_gallery(bot: "WispBot", forum: discord.ForumChannel) -> None:
    """Make gallery the Studio forum's default layout; a failure goes to the House."""
    if forum.default_layout == discord.ForumLayoutType.gallery_view:
        return
    try:
        await forum.edit(default_layout=discord.ForumLayoutType.gallery_view)
    except discord.HTTPException as error:
        await bot.report_error(
            forum.guild, "setting Wisp's Studio to gallery view", error
        )


async def _create_thread(
    bot: "WispBot", forum: discord.ForumChannel, spec: StudioThread
) -> tuple[discord.Thread, int]:
    """Create one Studio thread and remember it; return it and its first message id.

    The banner's file is closed once the thread is made, or has failed.
    """
    path = _banner(spec)
    banner = None if path is None else _banner_file(path)
    try:
        created = await forum.create_thread(
            name=spec.name,
            content=spec.content,
            auto_archive_duration=rules.STUDIO_THREAD_ARCHIVE_MINUTES,
            **art_kwargs("file", banner),
        )
    finally:
        if banner is not None:
            banner.close()
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
    """Name the thread, lock or unlock it and pin or unpin the post as its spec
    says, give the first post its banner, pin the card if it should be.

    Whatever is already done is skipped. A failed step is posted in the thread
    and retried the next time the Studio is ensured. A card whose message is
    gone is left for the status loop to repost.
    """
    if thread.name != spec.name:
        try:
            await thread.edit(name=spec.name)
        except discord.HTTPException as error:
            await bot.report_error(guild, f"renaming {spec.title}", error, where=thread)
    if thread.locked != spec.locked:
        step = "locking" if spec.locked else "unlocking"
        try:
            await thread.edit(locked=spec.locked)
        except discord.HTTPException as error:
            await bot.report_error(guild, f"{step} {spec.title}", error, where=thread)
    if thread.flags.pinned != spec.pinned_post:
        step = "pinning" if spec.pinned_post else "unpinning"
        try:
            await thread.edit(pinned=spec.pinned_post)
        except discord.HTTPException as error:
            await bot.report_error(
                guild, f"{step} the {spec.title} post", error, where=thread
            )
    await _set_banner(bot, guild, thread, spec)
    if spec.message_attr is None or message_id is None or not spec.pin_card:
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


async def _set_banner(
    bot: "WispBot", guild: discord.Guild, thread: discord.Thread, spec: StudioThread
) -> None:
    """Make the banner the thread's first post's only picture.

    A post that already has just the banner, by upload name, is left alone;
    otherwise its attachments, such as Wisp's older art, are replaced. A forum
    thread's first post has the thread's id. A post that is gone, or a thread
    with no banner, is left alone. The file is closed once the edit is done or
    failed.
    """
    if (path := _banner(spec)) is None:
        return
    try:
        starter = await thread.fetch_message(thread.id)
        have = [attachment.filename for attachment in starter.attachments]
        if have == [_upload_name(path)]:
            return
        banner = _banner_file(path)
        try:
            await starter.edit(attachments=[banner])
        finally:
            banner.close()
    except discord.NotFound:
        return
    except discord.HTTPException as error:
        await bot.report_error(
            guild, f"adding the banner to {spec.title}", error, where=thread
        )


async def _build_faq(
    bot: "WispBot", guild: discord.Guild, thread: discord.Thread
) -> None:
    """Fill the Wisp FAQ thread; a failure is posted in it."""
    rules = await rules_post(bot, guild.id)
    try:
        await fill_faq(bot, guild.id, thread, rules)
    except (discord.HTTPException, OSError) as error:
        await bot.report_error(guild, "building the Wisp FAQ", error, where=thread)


async def ensure_studio(bot: "WispBot", guild_id: int) -> Settings:
    """Create any Studio thread that is missing and return the guild's settings.

    The forum is set to show as a gallery when it does not already. Threads
    that already exist are left alone apart from reopening an archived
    one, renaming one whose name has changed, making the banner a first
    post's only picture, locking or unlocking it as its spec says and
    finishing any pin that is still missing. Only the FAQ is locked: a locked
    post's buttons and menus don't work for members. Threads that were stored
    but have been deleted are recreated, and Wisp's House is told about them.
    The Wisp FAQ is filled when its thread is new or does not have one stored
    post per picture: a How Wisp Works thread
    from before the FAQ, a build that stopped part way or a release with a
    different set of pictures (such as one picture per section). A new ViiBR
    Vault thread forgets the shelves stored for the old one, so the life loop
    posts them in it (`cogs.shop.ensure_shelves`). A new Interaction thread
    forgets the card stored for the old one. Once done, STUDIO_ENSURED is
    dispatched, so the Interaction post is drawn again with the current Vault
    link (`cogs.interaction`).

    Raises:
        StudioError: The Studio forum is not set or is not a forum.
    """
    async with _studio_locks.setdefault(guild_id, asyncio.Lock()):
        settings = await bot.settings.get(guild_id)
        forum = _studio_forum(bot, guild_id, settings)
        await _show_as_gallery(bot, forum)
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
        stored_pictures = len(settings.faq_message_ids or ())
        if _FAQ_ATTR in created or stored_pictures != FAQ_PICTURE_COUNT:
            await _build_faq(bot, forum.guild, threads[_FAQ_ATTR])
        if _SHOP_ATTR in created:
            await bot.settings.update(guild_id, shop_message_ids=None)
        if _INTERACTION_ATTR in created:
            await bot.settings.update(guild_id, interaction_message_id=None)
        settings = await bot.settings.get(guild_id)
    if recreated:
        await _announce(bot, forum.guild, recreated)
    bot.dispatch(STUDIO_ENSURED, guild_id)
    return settings


def _thread_list(titles: list[str]) -> str:
    """Thread titles, each in quotes, so a title with a comma reads as one."""
    return ", ".join(f'"{title}"' for title in titles)


async def _announce(bot: "WispBot", guild: discord.Guild, names: list[str]) -> None:
    house = await bot.house_channel(guild)
    if house is None:
        return
    try:
        await house.send(
            f"Wisp's Studio: recreated {_thread_list(names)}.",
            allowed_mentions=_NO_PING,
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


def post_url(guild_id: int, thread_id: int | None) -> str | None:
    """A link that jumps to the Studio post `thread_id`, or None before it exists."""
    if thread_id is None:
        return None
    return f"https://discord.com/channels/{guild_id}/{thread_id}"


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

_PIN_MESSAGES: Final = discord.Permissions(1 << 51)
"""Discord's Pin Messages permission, which this discord.py has no name for."""
_HOUSE_PERMISSIONS: Final = (
    ("Create Private Threads", discord.Permissions(create_private_threads=True)),
    ("Send Messages in Threads", discord.Permissions(send_messages_in_threads=True)),
    ("Manage Threads", discord.Permissions(manage_threads=True)),
    ("Pin Messages", _PIN_MESSAGES),
)


def missing_house_permissions(
    house: discord.TextChannel, me: discord.Member
) -> list[str]:
    """The permissions members' rooms need that Wisp lacks in his House, by name.

    An administrator has them all, Pin Messages included, though discord.py's
    administrator permissions leave its bit out.
    """
    have = house.permissions_for(me)
    if have.administrator:
        return []
    return [name for name, needed in _HOUSE_PERMISSIONS if not needed <= have]


def helper_role(guild: discord.Guild | None, settings: Settings) -> discord.Role | None:
    """The guild's helper role, or None when none is set or it was deleted."""
    if guild is None or settings.helper_role_id is None:
        return None
    return guild.get_role(settings.helper_role_id)


def cannot_ping_line(
    role: discord.Role, house: discord.abc.GuildChannel | None, me: discord.Member
) -> list[str]:
    """The warning for staff when Discord won't let Wisp ping `role`, else none.

    A role ping only notifies anyone when the role may be mentioned by anyone
    or Wisp has Mention Everyone where he posts: in his House, or anywhere on
    the server while no House is set.
    """
    if role.mentionable:
        return []
    have = me.guild_permissions if house is None else house.permissions_for(me)
    return [] if have.mention_everyone else [_CANNOT_PING.format(role=role.mention)]


def _helper_lines(
    guild: discord.Guild, settings: Settings, house: discord.TextChannel
) -> list[str]:
    """What setup says about the helper role: its name, or that there is none."""
    role = helper_role(guild, settings)
    if role is None:
        return [
            _NO_HELPER_ROLE if settings.helper_role_id is None else _HELPER_ROLE_DELETED
        ]
    return [
        f"・Helper role: {role.mention}",
        *cannot_ping_line(role, house, guild.me),
    ]


async def set_up(
    bot: "WispBot",
    guild: discord.Guild,
    house: discord.TextChannel,
    studio: discord.ForumChannel,
    tracks: discord.TextChannel | discord.ForumChannel,
    where: discord.abc.Messageable | None,
    *,
    general: discord.TextChannel | None = None,
) -> str:
    """Save the channels, then make the House panel, Studio threads and badge roles.

    `general` is the server's general chat, where Wisp shares each new stage;
    without one he shares it only in his House. Failures along the way are
    reported in `where`. A House or general chat that is also the track drop
    is refused, since Wisp never posts there. Returns the answer for staff,
    which says when no feeding role is set yet, since nobody can feed him then,
    names the helper role (warning when Wisp can't ping it) or says there is
    none or that it was deleted, and says which House
    permissions members' rooms still need. With those
    permissions in place, every member who opened /wisp board and has no
    storage locker gets one.
    """
    if house.id == tracks.id:
        return _HOUSE_IS_TRACKS
    if general is not None and general.id == tracks.id:
        return _GENERAL_IS_TRACKS
    before = await bot.settings.get(guild.id)
    await bot.settings.update(
        guild.id,
        house_channel_id=house.id,
        studio_forum_id=studio.id,
        tracks_channel_id=tracks.id,
        general_channel_id=None if general is None else general.id,
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
        f"Created threads: {_thread_list(created)}"
        if created
        else f"Studio threads: all {_NUMBER_WORDS[len(STUDIO_THREADS)]} already exist"
    )
    badge_lines = await ensure_badge_roles(bot, guild, where)
    roles_line = [] if await bot.settings.roles(guild.id) else [_NO_FEEDING_ROLES]
    helper_lines = _helper_lines(guild, after, house)
    missing = missing_house_permissions(house, guild.me)
    permissions_line = (
        [f"・Wisp needs these in his House: {', '.join(missing)}"] if missing else []
    )
    lockers_line = [] if missing else [await _lockers_line(bot, guild, where)]
    return "\n".join(
        [
            "♪ Wisp is set up.",
            f"・Wisp's House: {house.mention}",
            f"・Wisp's Studio: {studio.mention}",
            f"・Track drop: {tracks.mention}",
            f"・General chat: {'off' if general is None else general.mention}",
            f"・{threads}",
            *roles_line,
            *helper_lines,
            *permissions_line,
            *lockers_line,
            *badge_lines,
        ]
    )


async def _lockers_line(
    bot: "WispBot", guild: discord.Guild, where: discord.abc.Messageable | None
) -> str:
    """Make the storage lockers members are missing and say how many were made."""
    try:
        made = await ensure_rooms(bot, guild, where)
    except RoomError as error:
        return f"・Storage lockers: {error}"
    return f"・New storage lockers: {made}"


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
        rules = await rules_post(bot, guild_id)
        await fill_faq(bot, guild_id, thread, rules)
    return "♪ The Wisp FAQ is rebuilt."


@wispadmin.command(
    name="setup", description="Set Wisp's channels, Studio and badge roles."
)
@app_commands.describe(
    house="Where Wisp talks and announces his big moments",
    studio="The forum for Wisp's Studio threads",
    tracks="The track drop channel Wisp eats from",
    general="General chat, where Wisp shares each new stage (leave empty for none)",
)
async def setup_slash(
    interaction: discord.Interaction["WispBot"],
    house: discord.TextChannel,
    studio: discord.ForumChannel,
    tracks: discord.TextChannel | discord.ForumChannel,
    general: discord.TextChannel | None = None,
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
        general=general,
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


@commands.command(name="setup", usage="#house #studio #tracks [#general]")
async def setup_studio(
    ctx: StaffContext,
    house: discord.TextChannel,
    studio: discord.ForumChannel,
    tracks: discord.TextChannel | discord.ForumChannel,
    general: discord.TextChannel | None = None,
) -> None:
    """Save the channels, then make the House panel, Studio threads and badges."""
    answer = await set_up(
        ctx.bot, guild_of(ctx), house, studio, tracks, ctx.channel, general=general
    )
    await reply(ctx, answer)


@commands.command(name="faq")
async def rebuild_faq(ctx: StaffContext) -> None:
    """Rebuild the Wisp FAQ after its pictures change."""
    await reply(ctx, await rebuild(ctx.bot, guild_of(ctx).id))


@commands.command(name="freeze")
async def freeze(ctx: StaffContext) -> None:
    """Freeze Wisp so his meters, chores and age pause."""
    await ctx.bot.settings.update(guild_of(ctx).id, frozen=True)
    await reply(
        ctx,
        "♪ Wisp is frozen. His meters, chores and age pause until you unfreeze him.",
    )


@commands.command(name="unfreeze")
async def unfreeze(ctx: StaffContext) -> None:
    """Unfreeze Wisp so his meters, chores and age run again."""
    await ctx.bot.settings.update(guild_of(ctx).id, frozen=False)
    await reply(ctx, "♪ Wisp is unfrozen. His meters, chores and age run again.")


def _http_link(argument: str) -> str:
    """Accept an http(s) URL as typed; anything else is a bad argument."""
    try:
        parts = urlsplit(argument)
    except ValueError as error:
        raise commands.BadArgument(f"Not a link: {argument}") from error
    if parts.scheme not in _LINK_SCHEMES or not parts.hostname:
        raise commands.BadArgument(f"Not an http(s) link: {argument}")
    return argument


@commands.command(name="song", usage="<link> <words...>")
async def song(
    ctx: StaffContext, link: Annotated[str, _http_link], *, words: str
) -> None:
    """Post staff's words and a song link in Jam Space as if Wisp wrote them.

    Nothing is added to the post, and the link is left to show its player. A
    post that would not fit in one message is refused with the usage and the
    limit, and the command message is kept so its words can be shortened.
    Otherwise the command message is deleted afterwards; a failed delete is
    only logged. A Jam Space that cannot be reached raises, so the error is
    reported where the command was used and nothing is posted.
    """
    post = f"{words}\n{link}"
    if text_length(post) > MESSAGE_LIMIT:
        await reply(
            ctx,
            f"{usage_line(song)} ・ the words and the link together fit in "
            f"{MESSAGE_LIMIT:,} characters",
        )
        return
    thread = await studio_thread(ctx.bot, guild_of(ctx).id, "jam_thread_id")
    await thread.send(post, allowed_mentions=_NO_PING)
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        log.warning("Could not delete the !wisp song message %d", ctx.message.id)


_MEMBER_PINGS: Final = discord.AllowedMentions(
    everyone=False, roles=False, users=True, replied_user=False
)


@commands.command(name="say", usage="[#channel] <words...> (and any pictures)")
async def say_as_wisp(
    ctx: StaffContext,
    channel: discord.TextChannel | discord.Thread | None = None,
    *,
    words: str = "",
) -> None:
    """Post staff's words, and the pictures attached to the command, as Wisp.

    The post goes in `channel`, or where the command was used without one.
    Member mentions ping; @everyone, @here and roles never do. A command with
    neither words nor pictures, or with words too long for one message, gets
    the usage and keeps the command message. Otherwise the command message is
    deleted afterwards; a failed delete is only logged. A post Discord
    refuses raises, so it is reported where the command was used and the
    command message is kept.
    """
    if not words and not ctx.message.attachments:
        await reply(ctx, f"{usage_line(say_as_wisp)} ・ add words, pictures or both")
        return
    if text_length(words) > MESSAGE_LIMIT:
        await reply(
            ctx,
            f"{usage_line(say_as_wisp)} ・ the words fit in "
            f"{MESSAGE_LIMIT:,} characters",
        )
        return
    files = [await attachment.to_file() for attachment in ctx.message.attachments]
    try:
        await (channel or ctx.channel).send(
            words or None, files=files, allowed_mentions=_MEMBER_PINGS
        )
    finally:
        for file in files:
            file.close()
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        log.warning("Could not delete the !wisp say message %d", ctx.message.id)


async def setup(bot: "WispBot") -> None:
    """Load the Studio staff commands."""
    for command in (setup_studio, rebuild_faq, freeze, unfreeze, song, say_as_wisp):
        bot.add_command(command)
