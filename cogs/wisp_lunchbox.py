"""Wisp's own lunchbox: favorite songs, snack and emoji, and gift collections."""

import random
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final

import discord

from cogs.announce import display_name, say_in_mealtime
from cogs.channels import may_post_in, where_of
from cogs.gifts import collection_lines
from cogs.groups import require_guild, wisp
from wisp.life import Life, mood
from wisp.lines import Moment
from wisp.rules import FAVORITE_SONGS_SHOWN, SNACK_BY_KEY
from wisp.text import (
    BOX_CLOSE,
    MESSAGE_LIMIT,
    SECTION_BREAK,
    box_open,
    fit,
    heading,
    item,
    sub,
    text_length,
    with_emoji,
)

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_NOTHING_YET: Final = item("none yet")
_TITLE: Final = "𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍"

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


def _favorite_snack(bot: "WispBot", life: Life | None) -> str:
    snack = None if life is None else SNACK_BY_KEY.get(life.favorite_snack or "")
    if snack is None:
        return _NOTHING_YET
    return item(with_emoji(bot.emoji(snack.emoji_name), snack.name))


async def _favorite_emoji(bot: "WispBot", guild_id: int) -> str:
    """His most used expression that is still uploaded."""
    for name in await bot.wisp_lunchbox.favorite_expressions(guild_id):
        if name in bot.emojis_by_name:
            return item(bot.emoji(name))
    return _NOTHING_YET


async def _collections(
    bot: "WispBot", guild_id: int, life: Life | None, room: int
) -> list[str]:
    """The gift collections of the current life, `life`, within `room`."""
    if life is None or life.id is None:
        return [_NOTHING_YET]
    kept = await bot.gifts.kept(guild_id, life.id)
    return collection_lines(bot, kept, room) or [_NOTHING_YET]


async def lunchbox_text(bot: "WispBot", guild_id: int) -> str:
    """Wisp's lunchbox in its frame, trimmed so it fits one message.

    Each song is its day and sharer, then its link. The collections list
    their gifts in whatever room the songs leave, and the oldest songs go
    when even the collections' short lines do not fit. The box always closes.
    """
    favorites = await bot.wisp_lunchbox.favorites(guild_id, FAVORITE_SONGS_SHOWN)
    life = await bot.lives.current(guild_id)
    songs = [
        "\n".join(
            [
                sub(f"{_short_day(favorite.day)} ・ <@{favorite.user_id}>"),
                item(favorite.url),
            ]
        )
        for favorite in favorites
    ]
    head = [*box_open(_TITLE), heading("Favorite songs")]
    middle = [
        *([] if songs else [_NOTHING_YET]),
        SECTION_BREAK,
        heading("Favorite snack"),
        _favorite_snack(bot, life),
        SECTION_BREAK,
        heading("Favorite emoji"),
        await _favorite_emoji(bot, guild_id),
        SECTION_BREAK,
        heading("Collections"),
    ]
    framing = "\n".join([*head, *songs, *middle, *BOX_CLOSE])
    room = MESSAGE_LIMIT - text_length(framing) - 1
    collections = await _collections(bot, guild_id, life, room)
    return fit(head, songs, [*middle, *collections, *BOX_CLOSE])


@wisp.command(name="lunchbox", description="See the things Wisp keeps in his lunchbox.")
async def wisp_lunchbox(interaction: discord.Interaction["WispBot"]) -> None:
    """Show Wisp's lunchbox in the channel where it was asked for. Anyone may look.

    It pings nobody and its song links show no previews. Asked for where Wisp
    never posts, such as the track drop, it goes to his House instead and the
    member is told so privately; with no House it is shown only to them.
    """
    bot = interaction.client
    guild_id = require_guild(interaction)
    settings = await bot.settings.get(guild_id)
    channel = where_of(interaction)
    if channel is not None and may_post_in(channel, settings.tracks_channel_id):
        await interaction.response.defer()
        await interaction.followup.send(
            await lunchbox_text(bot, guild_id),
            allowed_mentions=_NO_PING,
            suppress_embeds=True,
        )
        return
    await interaction.response.defer(ephemeral=True)
    text = await lunchbox_text(bot, guild_id)
    house = await bot.house_channel(interaction.guild)
    if house is None:
        await interaction.followup.send(
            text, ephemeral=True, allowed_mentions=_NO_PING, suppress_embeds=True
        )
        return
    await house.send(text, allowed_mentions=_NO_PING, suppress_embeds=True)
    await interaction.followup.send(
        f"♪ Wisp's lunchbox is open in <#{settings.house_channel_id}>.",
        ephemeral=True,
        allowed_mentions=_NO_PING,
    )


async def setup(bot: "WispBot") -> None:
    """Load Wisp's lunchbox; its command joins the shared group on import."""
