"""Wisp's Status post: his picture, the Wisp Stats title and his live card.

The post's first message shows only Wisp's picture, so the Studio's gallery
shows him. Under it come Myra's Wisp Stats title picture on its own, then the
card, which carries the same picture so it shows under the card and closes
it, and the card's buttons. The card is pinned and edited in place.
"""

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.assets import ASSETS_DIR
from cogs.pictures import Picture
from cogs.studio import StudioError, studio_thread

if TYPE_CHECKING:
    from app import WispBot

_TITLE_NAME: Final = "stats_title.png"
_CARD_ATTR: Final = "status_message_id"
_LABEL: Final = "status card"
_PICTURE_KEY: Final = "status picture"
_NO_PICTURE: Final = "♪ Wisp's status"
_NO_PING: Final = discord.AllowedMentions.none()


def _title() -> Path | None:
    """Myra's Wisp Stats title picture, or None when it is missing."""
    path = ASSETS_DIR / _TITLE_NAME
    return path if path.is_file() else None


def _title_file() -> dict[str, Any]:
    """The keyword that attaches the title picture to a send, if there is one."""
    title = _title()
    return {} if title is None else {"file": discord.File(title)}


# ---
# The Status post
# ---


async def show_status(
    bot: "WispBot",
    guild_id: int,
    content: str,
    view: discord.ui.View,
    image: Path | None,
    *,
    clear_image: bool = False,
) -> None:
    """Show Wisp's picture and `content` in the Status post.

    Args:
        bot: The running bot.
        guild_id: The guild whose Studio to use.
        content: The card's text.
        view: The card's buttons.
        image: Wisp's picture for the post's first message, or None to leave
            it as it is.
        clear_image: With no `image`, take the picture off instead.

    A post from before the title and card had their own messages, whose first
    message is still the card, is brought over: its first message keeps only
    the picture and the title and card are posted under it. A failure is
    posted in the thread, or in Wisp's House when the thread cannot be
    reached, once per streak of failures. It is never raised.
    """
    key = (guild_id, _CARD_ATTR)
    thread: discord.Thread | None = None
    try:
        thread = await studio_thread(bot, guild_id, "status_thread_id")
        card_id = (await bot.settings.get(guild_id)).status_message_id
        posted = card_id is not None and card_id != thread.id
        await _show_picture(bot, guild_id, thread, image, clear_image, posted)
        await _show_card(
            bot, guild_id, thread, content, view, card_id if posted else None
        )
    except (discord.DiscordException, StudioError) as error:
        if key not in bot.failing_displays:
            bot.failing_displays.add(key)
            await bot.report_error(
                bot.get_guild(guild_id), f"updating the {_LABEL}", error, where=thread
            )
    else:
        bot.failing_displays.discard(key)


async def _show_picture(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    image: Path | None,
    clear_image: bool,
    posted: bool,
) -> None:
    """Keep the post's first message showing only Wisp's picture.

    It is edited only when the picture is not the one this process last
    showed there, or while the card still lives in it (`posted` is False).
    With no picture to show it says "♪ Wisp's status", since a message needs
    text or a picture. A first message that is gone is left alone.
    """
    key = (guild_id, _PICTURE_KEY)
    wanted = image.name if image is not None else ("" if clear_image else None)
    if posted and (wanted is None or bot.shown_images.get(key) == (thread.id, wanted)):
        return
    starter = thread.get_partial_message(thread.id)
    picture = Picture(bot, guild_id, thread, _CARD_ATTR, _LABEL)
    try:
        _, attached = await picture.attach(
            image if wanted else None,
            lambda art: starter.edit(
                content=None if art is not None else _NO_PICTURE,
                view=None,
                attachments=[] if art is None else [art],
                allowed_mentions=_NO_PING,
            ),
        )
    except discord.NotFound:
        return
    bot.shown_images[key] = (thread.id, attached or "")


async def _show_card(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    content: str,
    view: discord.ui.View,
    card_id: int | None,
) -> None:
    """Edit the card `card_id`, or post the title and the card when there is none.

    Only the text and buttons are edited, so the title picture under the card
    stays. A card that is gone is posted again with its title, and the old
    title, if still there, is deleted so the two stay together.
    """
    if card_id is not None:
        try:
            await thread.get_partial_message(card_id).edit(
                content=content, view=view, allowed_mentions=_NO_PING
            )
            return
        except discord.NotFound:
            pass
    title_id = (await bot.settings.get(guild_id)).status_title_message_id
    if title_id is not None:
        with contextlib.suppress(discord.NotFound):
            await thread.get_partial_message(title_id).delete()
    title_art = _title_file()
    title = await thread.send(**title_art) if title_art else None
    card = await thread.send(
        content, view=view, allowed_mentions=_NO_PING, **_title_file()
    )
    await bot.settings.update(
        guild_id,
        status_title_message_id=None if title is None else title.id,
        status_message_id=card.id,
    )
    try:
        await card.pin()
    except discord.HTTPException as error:
        await bot.report_error(
            bot.get_guild(guild_id), f"pinning the {_LABEL}", error, where=thread
        )
