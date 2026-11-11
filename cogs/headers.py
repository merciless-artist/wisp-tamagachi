"""Myra's header pictures: a title above a message and a footer under it.

A plain message can only show a picture under its text, so a headed message
is two: the header picture on its own, then the text with the footer
attached. The Vault, a Components V2 message, holds both in one message as
media galleries. A menu in the v3 emoji frame (`send_framed`) is one
Components V2 message too: its header picture, then its text, closed by the
frame's bottom line instead of a footer. A pinned card in a Studio thread
keeps its header message beside it in the settings, so both are posted again
together.

The Leaderboard is not edited: when its text changes, a new header and card
are posted at the bottom of the thread and the old pair is deleted.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.assets import ASSETS_DIR
from cogs.studio import StudioError, studio_thread
from wisp.text import FRAME_EMOJIS, UNICODE_FRAME, Frame, emoji_frame

if TYPE_CHECKING:
    from app import WispBot

FOOTER: Final = "box_footer.png"
_NO_PING: Final = discord.AllowedMentions.none()


def art(name: str) -> Path | None:
    """The picture `name` in the artwork folder, or None when it is missing."""
    path = ASSETS_DIR / name
    return path if path.is_file() else None


def _open(name: str) -> discord.File | None:
    """The picture `name` opened for sending, or None when it is missing."""
    path = art(name)
    return None if path is None else discord.File(path)


def _close(*pictures: discord.File | None) -> None:
    for picture in pictures:
        if picture is not None:
            picture.close()


async def send_headed(
    send: Callable[..., Awaitable[Any]], header: str, text: str, **kwargs: Any
) -> None:
    """Send the `header` picture on its own, then `text` with the footer under it.

    `kwargs` go with the text. A missing picture is left out. Both pictures
    are closed once sent, or once a send failed.
    """
    top, bottom = _open(header), _open(FOOTER)
    try:
        if top is not None:
            await send(file=top)
        await send(text, **kwargs, **({} if bottom is None else {"file": bottom}))
    finally:
        _close(top, bottom)


# ---
# Components V2
# ---


def gallery(name: str) -> discord.ui.MediaGallery[Any] | None:
    """A media gallery showing the attached picture `name`, or None when missing."""
    if art(name) is None:
        return None
    return discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{name}"))


@contextlib.contextmanager
def gallery_files(*names: str) -> Iterator[list[discord.File]]:
    """The files a layout's galleries of `names` show, leaving out missing ones.

    They are closed when the block ends, after the send or its failure.
    """
    files = [discord.File(path) for name in names if (path := art(name)) is not None]
    try:
        yield files
    finally:
        _close(*files)


# ---
# The emoji frame (house style v3)
# ---


def frame_of(bot: "WispBot") -> Frame:
    """Myra's emoji frame from Wisp's app emojis, or the Unicode frame.

    The frame is all or nothing: with any of its emojis not uploaded, the
    whole box falls back to the Unicode pieces, so a half-emoji box never
    shows. The missing emoji is logged by `bot.emoji`.
    """
    pieces = [bot.emoji(name) for name in FRAME_EMOJIS]
    return emoji_frame(*pieces) if all(pieces) else UNICODE_FRAME


def framed_layout(header: str, text: str) -> discord.ui.LayoutView:
    """A menu as one Components V2 message: its header picture, then its text.

    A missing header picture is left out. There is no container and no footer
    picture: the frame's bottom line closes the box.
    """
    layout = discord.ui.LayoutView(timeout=None)
    if (top := gallery(header)) is not None:
        layout.add_item(top)
    layout.add_item(discord.ui.TextDisplay(text))
    return layout


async def send_framed(
    send: Callable[..., Awaitable[Any]], header: str, text: str, **kwargs: Any
) -> None:
    """Send `text` under the `header` picture as one Components V2 message.

    `kwargs` go with the send. The picture is closed once sent, or once the
    send failed.
    """
    with gallery_files(header) as pictures:
        await send(view=framed_layout(header, text), files=pictures, **kwargs)


# ---
# Pinned cards
# ---


@dataclass(frozen=True)
class HeadedCard:
    """A pinned card in a Studio thread with a header message above it.

    `header` and `footer` are picture names in the artwork folder;
    `title_attr` and `card_attr` are the Settings fields of the header
    message and the card; `label` names the card in error reports; `post`
    is what the thread's first message says when it has no picture. A card
    with `pinned` False is left unpinned, as a card kept at the bottom is.
    """

    header: str
    footer: str
    title_attr: str
    card_attr: str
    label: str
    post: str
    pinned: bool = True


async def repost_headed_in_thread(
    bot: "WispBot",
    guild_id: int,
    thread_attr: str,
    content: str,
    card: HeadedCard,
) -> None:
    """Keep `card` showing `content` as the last posts of the Studio thread.

    When the card now in the thread already says `content`, nothing is
    posted. Otherwise a fresh header and card go at the bottom and the old
    pair is deleted. A failure is posted in the thread, or in Wisp's House
    when the thread cannot be reached, once per streak of failures. It is
    never raised, so one broken display cannot stop the rest of a tick.
    """
    key = (guild_id, card.card_attr)
    thread: discord.Thread | None = None
    try:
        thread = await studio_thread(bot, guild_id, thread_attr)
        lock = bot.display_locks.setdefault(key, asyncio.Lock())
        async with lock:
            await repost_headed_card(bot, guild_id, thread, content, card)
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


async def repost_headed_card(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    content: str,
    card: HeadedCard,
) -> None:
    """Post `card` again under a fresh header unless it already says `content`.

    The old card is read from the thread, so a restart does not repost a
    board that has not changed, and a card someone deleted is posted again.
    The old header and card are deleted once the new pair is stored; one
    that is already gone is fine, and any other failed delete is reported
    in the thread. A header whose card could not be posted is deleted again.
    A card that is still the thread's first message, as every
    card began, is brought over: that message keeps only its picture.
    """
    settings = await bot.settings.get(guild_id)
    old_title_id: int | None = getattr(settings, card.title_attr)
    old_card_id: int | None = getattr(settings, card.card_attr)
    in_first_post = old_card_id == thread.id
    if old_card_id is not None and not in_first_post:
        try:
            if (await thread.fetch_message(old_card_id)).content == content:
                return
        except discord.NotFound:
            pass
    if in_first_post:
        await _keep_only_picture(thread, card.post)
    await _post_headed(bot, guild_id, thread, content, card)
    stale = [old_title_id, None if in_first_post else old_card_id]
    for message_id in stale:
        if message_id is None:
            continue
        try:
            await thread.get_partial_message(message_id).delete()
        except discord.NotFound:
            pass
        except discord.HTTPException as error:
            await bot.report_error(
                bot.get_guild(guild_id),
                f"deleting the old {card.label}",
                error,
                where=thread,
            )


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
    await _post_headed(bot, guild_id, thread, content, card, view)


async def _post_headed(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    content: str,
    card: HeadedCard,
    view: discord.ui.View | None = None,
) -> None:
    """Post the header, then the card with its footer and `view`; store and pin it."""
    extras: dict[str, Any] = {"allowed_mentions": _NO_PING}
    if view is not None:
        extras["view"] = view
    pictures = [_open(card.header), _open(card.footer)]
    header, footer = pictures
    try:
        title = None if header is None else await thread.send(file=header)
        if footer is not None:
            extras["file"] = footer
        try:
            posted = await thread.send(content, **extras)
        except discord.HTTPException:
            if title is not None:
                with contextlib.suppress(discord.HTTPException):
                    await title.delete()
            raise
    finally:
        _close(*pictures)
    await bot.settings.update(
        guild_id,
        **{
            card.title_attr: None if title is None else title.id,
            card.card_attr: posted.id,
        },
    )
    if not card.pinned:
        return
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
