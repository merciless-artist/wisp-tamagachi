"""Wisp's own lunchbox: favorite songs, snack and emoji, and gift collections."""

import contextlib
import functools
import random
import re
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final

import discord

from cogs.announce import display_name, say_in_mealtime
from cogs.channels import in_channel, may_post_in, where_of
from cogs.gifts import collection_lines
from cogs.groups import require_guild, wisp
from cogs.headers import send_framed
from cogs.players import bot_of, press
from db.lunchbox import Favorite
from wisp.life import Life, mood
from wisp.lines import Moment
from wisp.rules import FAVORITE_SONGS_SHOWN, SNACK_BY_KEY
from wisp.text import LAYOUT_TEXT_LIMIT, Frame, fit, frame_of, text_length, with_emoji

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_NOTHING_YET: Final = "none yet"
_HEADER: Final = "lunchbox_title.png"
_LUNCHBOX_ID: Final = "wisp:lunchbox"

# ---
# Favorite songs
# ---


async def pick_favorite_song(
    bot: "WispBot",
    guild: discord.Guild,
    life: Life,
    rng: random.Random,
    now: datetime,
) -> None:
    """Keep one of yesterday's viibrmusic.com tracks as his favorite, in Mealtime.

    Yesterday is the UTC day before `now`. Nothing happens when that day already
    has a favorite or had no viibrmusic.com feeds. He says it in the mood of
    `life`. A failed post is reported where it happened.
    """
    yesterday = now.astimezone(UTC).date() - timedelta(days=1)
    favorite = await bot.wisp_lunchbox.pick_favorite(guild.id, yesterday, rng, now)
    if favorite is None:
        return
    player = await bot.players.get(guild.id, favorite.user_id)
    line = bot.lines.pick(
        Moment.FAVORITE_SONG, mood(life), name=display_name(guild, player)
    )
    await say_in_mealtime(
        bot,
        guild,
        f"♪ Wisp put <@{favorite.user_id}>'s track in his lunchbox ・ "
        f"{favorite.url}\n{line}",
        "posting Wisp's favorite song to Mealtime",
    )


# ---
# The lunchbox
# ---


def _short_day(day: date) -> str:
    """A day as its short month and day of the month, such as "Oct 2"."""
    return f"{day:%b} {day.day}"


def _song(frame: Frame, number: int, favorite: Favorite) -> str:
    """A favorite song: its day and sharer, then its link, `#1 LISTEN HERE`."""
    shared = frame.wrap(
        frame.sub(f"{_short_day(favorite.day)} ・ <@{favorite.user_id}>")
    )
    return f"{shared}\n{frame.item(f'[#{number} LISTEN HERE]({favorite.url})')}"


def _favorite_snack(bot: "WispBot", frame: Frame, life: Life | None) -> str:
    snack = None if life is None else SNACK_BY_KEY.get(life.favorite_snack or "")
    if snack is None:
        return frame.item(_NOTHING_YET)
    return frame.item(with_emoji(bot.emoji(snack.emoji_name), snack.name))


async def _favorite_emoji(bot: "WispBot", frame: Frame, guild_id: int) -> str:
    """His most used expression that is still uploaded, then its name in code."""
    for name in await bot.wisp_lunchbox.favorite_expressions(guild_id):
        if name in bot.emojis_by_name:
            return frame.item(f"{bot.emoji(name)} `:{name}:`")
    return frame.item(_NOTHING_YET)


async def _collections(
    bot: "WispBot", frame: Frame, guild_id: int, life: Life | None, room: int
) -> list[str]:
    """The gift collections of the current life, `life`, within `room`."""
    nothing = [frame.item(_NOTHING_YET)]
    if life is None or life.id is None:
        return nothing
    kept = await bot.gifts.kept(guild_id, life.id)
    return collection_lines(bot, frame, kept, room) or nothing


async def lunchbox_text(bot: "WispBot", guild_id: int) -> str:
    """Wisp's lunchbox in Myra's emoji frame, trimmed to fit one layout message.

    Each song is its day and sharer, then a numbered `LISTEN HERE` link. The
    collections list their gifts in whatever room the songs leave, and the
    oldest songs go when even the collections' short lines do not fit. The
    box always closes, and every line is wrapped to fit it.
    """
    frame = frame_of(bot.emoji)
    favorites = await bot.wisp_lunchbox.favorites(guild_id, FAVORITE_SONGS_SHOWN)
    life = await bot.lives.current(guild_id)
    songs = [
        _song(frame, number, favorite)
        for number, favorite in enumerate(favorites, start=1)
    ]
    head = [frame.heading("Favorite songs")]
    middle = [
        *([] if songs else [frame.item(_NOTHING_YET)]),
        frame.blank,
        frame.section_break,
        frame.heading("Favorite snack"),
        _favorite_snack(bot, frame, life),
        frame.section_break,
        frame.heading("Favorite emoji"),
        await _favorite_emoji(bot, frame, guild_id),
        frame.section_break,
        frame.heading("Collections"),
    ]
    close = [frame.blank, frame.bottom]
    framing = "\n".join([*head, *songs, *middle, *close])
    room = LAYOUT_TEXT_LIMIT - text_length(framing) - 1
    collections = await _collections(bot, frame, guild_id, life, room)
    return fit(head, songs, [*middle, *collections, *close], LAYOUT_TEXT_LIMIT)


async def _send_privately(interaction: discord.Interaction, text: str) -> None:
    """Answer a deferred interaction with the lunchbox, only to the member."""
    await send_framed(
        functools.partial(interaction.followup.send, ephemeral=True),
        _HEADER,
        text,
        allowed_mentions=_NO_PING,
    )


@wisp.command(name="lunchbox", description="See the things Wisp keeps in his lunchbox.")
async def wisp_lunchbox(interaction: discord.Interaction["WispBot"]) -> None:
    """Show Wisp's lunchbox in the channel where it was asked for. Anyone may look.

    It is one Components V2 message, its header picture over its text, and it
    pings nobody. The interaction is acknowledged privately and the lunchbox
    posted as a message of its own, so a failure tells only the member; the
    private acknowledgement is then removed; failing to remove it is ignored,
    since the lunchbox is already out. Asked for in a Studio thread, which
    keeps to its own cards, it is shown only to the member. Asked for where
    Wisp never posts, such as the track drop, it goes to his House instead
    and the member is told so privately; with no House it is shown only to
    them.
    """
    bot = interaction.client
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    settings = await bot.settings.get(guild_id)
    text = await lunchbox_text(bot, guild_id)
    channel = where_of(interaction)
    if in_channel(channel, settings.studio_forum_id):
        await _send_privately(interaction, text)
        return
    if channel is not None and may_post_in(channel, settings.tracks_channel_id):
        await send_framed(channel.send, _HEADER, text, allowed_mentions=_NO_PING)
        with contextlib.suppress(discord.HTTPException):
            await interaction.delete_original_response()
        return
    house = await bot.house_channel(interaction.guild)
    if house is None:
        await _send_privately(interaction, text)
        return
    await send_framed(house.send, _HEADER, text, allowed_mentions=_NO_PING)
    await interaction.followup.send(
        f"♪ Wisp's lunchbox is open in <#{settings.house_channel_id}>.",
        ephemeral=True,
        allowed_mentions=_NO_PING,
    )


async def _show_privately(interaction: discord.Interaction) -> None:
    """Show Wisp's lunchbox only to the member who pressed the button."""
    await interaction.response.defer(ephemeral=True, thinking=True)
    await _send_privately(
        interaction,
        await lunchbox_text(bot_of(interaction), require_guild(interaction)),
    )


class LunchboxButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_LUNCHBOX_ID),
):
    """The Lunchbox button on the status card; it shows the lunchbox privately.

    Anyone may look, as with /wisp lunchbox. Its custom id is fixed, so the
    button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Lunchbox",
                style=discord.ButtonStyle.secondary,
                custom_id=_LUNCHBOX_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "LunchboxButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Show the lunchbox to whoever pressed it."""
        await press(interaction, "the Lunchbox button", _show_privately)


async def setup(bot: "WispBot") -> None:
    """Register the Lunchbox button so it still works after a restart.

    The command joins the shared group on import.
    """
    bot.add_dynamic_items(LunchboxButton)
