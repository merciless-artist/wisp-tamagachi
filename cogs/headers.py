"""Myra's header pictures over the menus, and the pinned cards in Studio threads.

Every menu is in the v3 emoji frame (`send_framed`): one Components V2
message of its header picture, then its text, closed by the frame's bottom
line, then any buttons. A pinned card in a Studio thread is one such message
too. Cards from before v3 were two messages, a header picture and the card
under it; the header's id is still kept in the settings so that old header
is deleted when the card is next posted.

The Leaderboard is not edited: when its text changes, a new card is posted
at the bottom of the thread and the old one is deleted.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.assets import ASSETS_DIR
from cogs.studio import StudioError, studio_thread

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()

Buttons = Sequence[Sequence[discord.ui.Item[Any]]]


def art(name: str) -> Path | None:
    """The picture `name` in the artwork folder, or None when it is missing."""
    path = ASSETS_DIR / name
    return path if path.is_file() else None


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
        for file in files:
            file.close()


def layout_text(message: discord.Message) -> str:
    """The text displays of a posted Components V2 message, joined in order.

    A message from before v3, with no text displays, reads as "".
    """
    return "\n".join(
        component.content
        for component in message.components
        if isinstance(component, discord.TextDisplay)
    )


# ---
# The emoji frame (house style v3)
# ---


def framed_layout(header: str, text: str, rows: Buttons = ()) -> discord.ui.LayoutView:
    """A menu as one Components V2 message: its header picture, then its text.

    Each of `rows` follows as an action row of its buttons. A missing header
    picture is left out. There is no container and no footer picture: the
    frame's bottom line closes the box.
    """
    layout = discord.ui.LayoutView(timeout=None)
    if (top := gallery(header)) is not None:
        layout.add_item(top)
    layout.add_item(discord.ui.TextDisplay(text))
    for row in rows:
        layout.add_item(discord.ui.ActionRow(*row))
    return layout


async def send_framed(
    send: Callable[..., Awaitable[Any]],
    header: str,
    text: str,
    rows: Buttons = (),
    **kwargs: Any,
) -> Any:
    """Send `text` under the `header` picture as one Components V2 message.

    Each of `rows` follows the text as a row of buttons. `kwargs` go with the
    send. The picture is closed once sent, or once the send failed. Returns
    what `send` returned, such as the message posted.
    """
    with gallery_files(header) as pictures:
        return await send(
            view=framed_layout(header, text, rows), files=pictures, **kwargs
        )


# ---
# Pinned cards
# ---


@dataclass(frozen=True)
class HeadedCard:
    """A pinned card in a Studio thread: one framed message under its header.

    `header` is a picture name in the artwork folder; `title_attr` is the
    Settings field of the header message a card from before v3 had above it,
    and `card_attr` that of the card; `label` names the card in error
    reports; `post` is what the thread's first message says when it has no
    picture. A card with `pinned` False is left unpinned, as a card kept at
    the bottom is.
    """

    header: str
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
    """Keep `card` showing `content` as the last post of the Studio thread.

    When the card now in the thread already says `content`, nothing is
    posted. Otherwise a fresh card goes at the bottom and the old one is
    deleted. A failure is posted in the thread, or in Wisp's House when the
    thread cannot be reached, once per streak of failures. It is never
    raised, so one broken display cannot stop the rest of a tick.
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
    """Post `card` again at the bottom unless it already says `content`.

    The old card is read from the thread, so a restart does not repost a
    board that has not changed, and a card someone deleted is posted again.
    A card from before v3 never says `content`, so it is replaced. The old
    card, and any header message from before v3, are deleted once the new
    card is stored; one that is already gone is fine, and any other failed
    delete is reported in the thread. A card that is still the thread's
    first message, as every card began, is brought over: that message keeps
    only its picture.
    """
    settings = await bot.settings.get(guild_id)
    old_title_id: int | None = getattr(settings, card.title_attr)
    old_card_id: int | None = getattr(settings, card.card_attr)
    in_first_post = old_card_id == thread.id
    if old_card_id is not None and not in_first_post:
        try:
            if layout_text(await thread.fetch_message(old_card_id)) == content:
                return
        except discord.NotFound:
            pass
    if in_first_post:
        await _keep_only_picture(thread, card.post)
    await _post_card(bot, guild_id, thread, content, card)
    await _delete_old(
        bot,
        guild_id,
        thread,
        card,
        [old_title_id, None if in_first_post else old_card_id],
    )


async def show_headed_card(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    content: str,
    rows: Buttons,
    card: HeadedCard,
    card_id: int | None,
) -> None:
    """Edit the card `card_id` in place, or post it when there is none.

    The edit keeps the header picture already attached to the card. A card
    that is gone is posted again. A card from before v3, which has its header
    as a message of its own, is replaced: the new card is posted and the old
    header and card are deleted. A card that is still the thread's first
    message, as every card began, is brought over the same way: that message
    keeps only its picture, the gallery thumbnail, and the card is posted
    under it.
    """
    title_id: int | None = getattr(await bot.settings.get(guild_id), card.title_attr)
    in_first_post = card_id == thread.id
    if card_id is not None and not in_first_post and title_id is None:
        try:
            await thread.get_partial_message(card_id).edit(
                view=framed_layout(card.header, content, rows),
                allowed_mentions=_NO_PING,
            )
            return
        except discord.NotFound:
            pass
    if in_first_post:
        await _keep_only_picture(thread, card.post)
    await _post_card(bot, guild_id, thread, content, card, rows)
    old_card = None if in_first_post else card_id
    await _delete_old(bot, guild_id, thread, card, [title_id, old_card])


async def _post_card(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    content: str,
    card: HeadedCard,
    rows: Buttons = (),
) -> None:
    """Post the framed card with its `rows` of buttons; store and pin it.

    The card's id is stored and the old header message's is cleared.
    """
    posted: discord.Message = await send_framed(
        thread.send, card.header, content, rows, allowed_mentions=_NO_PING
    )
    await bot.settings.update(
        guild_id, **{card.title_attr: None, card.card_attr: posted.id}
    )
    if not card.pinned:
        return
    try:
        await posted.pin()
    except discord.HTTPException as error:
        await bot.report_error(
            bot.get_guild(guild_id), f"pinning the {card.label}", error, where=thread
        )


async def _delete_old(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    card: HeadedCard,
    message_ids: Sequence[int | None],
) -> None:
    """Delete the old messages of `card`; one already gone is fine.

    Any other failed delete is reported in the thread.
    """
    for message_id in message_ids:
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
