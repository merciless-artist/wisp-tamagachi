"""Myra's header pictures: a title above a message and a footer under it.

A plain message can only show a picture under its text, so a headed message
is two: the header picture on its own, then the text with the footer
attached. The Vault, a Components V2 message, holds both in one message as
media galleries. A pinned card in a Studio thread keeps its header message
beside it in the settings, so both are posted again together.
"""

import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.assets import ASSETS_DIR
from cogs.studio import StudioError, studio_thread

if TYPE_CHECKING:
    from app import WispBot

FOOTER: Final = "box_footer.png"
_NO_PING: Final = discord.AllowedMentions.none()


def art(name: str) -> Path | None:
    """The picture `name` in the artwork folder, or None when it is missing."""
    path = ASSETS_DIR / name
    return path if path.is_file() else None


def art_file(name: str) -> dict[str, Any]:
    """The keyword that attaches the picture `name` to a send, if there is one."""
    path = art(name)
    return {} if path is None else {"file": discord.File(path)}


async def send_headed(
    send: Callable[..., Awaitable[Any]], header: str, text: str, **kwargs: Any
) -> None:
    """Send the `header` picture on its own, then `text` with the footer under it.

    `kwargs` go with the text. A missing picture is left out.
    """
    if top := art_file(header):
        await send(**top)
    await send(text, **kwargs, **art_file(FOOTER))


# ---
# Components V2
# ---


def gallery(name: str) -> discord.ui.MediaGallery[Any] | None:
    """A media gallery showing the attached picture `name`, or None when missing."""
    if art(name) is None:
        return None
    return discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{name}"))


def gallery_files(*names: str) -> list[discord.File]:
    """The files a layout's galleries of `names` show, leaving out missing ones."""
    return [discord.File(path) for name in names if (path := art(name)) is not None]


# ---
# Pinned cards
# ---


@dataclass(frozen=True)
class HeadedCard:
    """A pinned card in a Studio thread with a header message above it.

    `header` and `footer` are picture names in the artwork folder;
    `title_attr` and `card_attr` are the Settings fields of the header
    message and the card; `label` names the card in error reports; `post`
    is what the thread's first message says when it has no picture.
    """

    header: str
    footer: str
    title_attr: str
    card_attr: str
    label: str
    post: str


async def show_headed_in_thread(
    bot: "WispBot",
    guild_id: int,
    thread_attr: str,
    content: str,
    view: discord.ui.View,
    card: HeadedCard,
) -> None:
    """Keep `card` showing `content` in the Studio thread at `thread_attr`.

    A failure is posted in the thread, or in Wisp's House when the thread
    cannot be reached, once per streak of failures. It is never raised, so
    one broken display cannot stop the rest of a tick.
    """
    key = (guild_id, card.card_attr)
    thread: discord.Thread | None = None
    try:
        thread = await studio_thread(bot, guild_id, thread_attr)
        card_id: int | None = getattr(await bot.settings.get(guild_id), card.card_attr)
        await show_headed_card(bot, guild_id, thread, content, view, card, card_id)
    except (discord.DiscordException, StudioError) as error:
        if key not in bot.failing_displays:
            bot.failing_displays.add(key)
            await bot.report_error(
                bot.get_guild(guild_id),
                f"updating the {card.label}",
                error,
                where=thread,
            )
    else:
        bot.failing_displays.discard(key)


async def show_headed_card(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    content: str,
    view: discord.ui.View,
    card: HeadedCard,
    card_id: int | None,
) -> None:
    """Edit the card `card_id`, or post the header and the card when there is none.

    Only the text and buttons are edited, so the footer under the card stays.
    A card that is gone is posted again under a fresh header, and the old
    header, if still there, is deleted so the two stay together. A card that
    is still the thread's first message, as every card began, is brought over
    the same way: that message keeps only its picture, the gallery thumbnail,
    and the header and card are posted under it.
    """
    title_id: int | None = getattr(await bot.settings.get(guild_id), card.title_attr)
    in_first_post = card_id == thread.id
    if card_id is not None and not in_first_post:
        try:
            await thread.get_partial_message(card_id).edit(
                content=content, view=view, allowed_mentions=_NO_PING
            )
            return
        except discord.NotFound:
            pass
    if in_first_post:
        await _keep_only_picture(thread, card.post)
    if title_id is not None:
        with contextlib.suppress(discord.NotFound):
            await thread.get_partial_message(title_id).delete()
    header = art_file(card.header)
    title = await thread.send(**header) if header else None
    posted = await thread.send(
        content, view=view, allowed_mentions=_NO_PING, **art_file(card.footer)
    )
    await bot.settings.update(
        guild_id,
        **{
            card.title_attr: None if title is None else title.id,
            card.card_attr: posted.id,
        },
    )
    try:
        await posted.pin()
    except discord.HTTPException as error:
        await bot.report_error(
            bot.get_guild(guild_id), f"pinning the {card.label}", error, where=thread
        )


async def _keep_only_picture(thread: discord.Thread, post: str) -> None:
    """Take the card's text and buttons off the thread's first message.

    Its picture stays; with no picture it says `post`, since a message needs
    text or a picture. A first message that is gone is left alone.
    """
    with contextlib.suppress(discord.NotFound):
        starter = await thread.fetch_message(thread.id)
        await starter.edit(
            content=None if starter.attachments else f"♪ {post}",
            view=None,
            allowed_mentions=_NO_PING,
        )
