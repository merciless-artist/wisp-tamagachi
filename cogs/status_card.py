"""Wisp's Status post: his picture, then his live card under the Wisp Stats title.

The post's first message shows only Wisp's picture, so the Studio's gallery
shows him. Under it is the card, one Components V2 message: Myra's Wisp
Stats title picture, the card in her emoji frame, then the card's buttons:
everything a member can do with Wisp, each answering privately. The card
is pinned and edited in place.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord

from cogs.conversation import PokeButton
from cogs.headers import Buttons, HeadedCard, show_headed_card
from cogs.pictures import Picture
from cogs.rhyme_duel import PlayButton
from cogs.snacks import FeedButton, ShopButton, SnackPackButton
from cogs.studio import StudioError, studio_thread
from cogs.wisp_lunchbox import LunchboxButton

if TYPE_CHECKING:
    from app import WispBot

_TITLE_NAME: Final = "stats_title.png"
_CARD_ATTR: Final = "status_message_id"
_LABEL: Final = "status card"
_PICTURE_KEY: Final = "status picture"
_NO_PICTURE: Final = "♪ Wisp's status"
_NO_PING: Final = discord.AllowedMentions.none()
_CARD: Final = HeadedCard(
    header=_TITLE_NAME,
    title_attr="status_title_message_id",
    card_attr=_CARD_ATTR,
    label=_LABEL,
    post=_NO_PICTURE.removeprefix("♪ "),
)
_BUTTONS_PER_ROW: Final = 3


# ---
# The card's buttons
# ---


def status_buttons() -> Buttons:
    """The live status card's buttons, three to a row.

    Feed Wisp, Poke Wisp and Vault, then Snack Pack, Play and Lunchbox. Each
    is persistent, so an old card keeps working after a restart.
    """
    buttons: list[discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]]] = [
        FeedButton(),
        PokeButton(),
        ShopButton("Vault"),
        SnackPackButton("Snack Pack"),
        PlayButton(),
        LunchboxButton(),
    ]
    return [
        buttons[start : start + _BUTTONS_PER_ROW]
        for start in range(0, len(buttons), _BUTTONS_PER_ROW)
    ]


# ---
# The Status post
# ---


async def show_status(
    bot: "WispBot",
    guild_id: int,
    content: str,
    rows: Buttons,
    image: Path | None,
    *,
    clear_image: bool = False,
) -> None:
    """Show Wisp's picture and `content` in the Status post.

    Args:
        bot: The running bot.
        guild_id: The guild whose Studio to use.
        content: The card's text.
        rows: The card's rows of buttons.
        image: Wisp's picture for the post's first message, or None to leave
            it as it is.
        clear_image: With no `image`, take the picture off instead.

    A post from before the card had a message of its own, whose first
    message is still the card, is brought over: its first message keeps only
    the picture and the card is posted under it. A failure is
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
        await show_headed_card(
            bot, guild_id, thread, content, rows, _CARD, card_id if posted else None
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
