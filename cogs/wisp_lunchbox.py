"""Wisp's own lunchbox: favorite songs, snack and emoji, and gift collections."""

import random
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final

import discord

from cogs.announce import display_name, say_in_mealtime
from cogs.gifts import collection_lines
from cogs.groups import require_guild, wisp
from wisp.life import Life, mood
from wisp.lines import Moment
from wisp.rules import FAVORITE_SONGS_SHOWN, SNACK_BY_KEY
from wisp.text import SEPARATOR, fit, with_emoji

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_NOTHING_YET: Final = "・Nothing yet"

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


async def _favorite_snack(bot: "WispBot", guild_id: int) -> str:
    life = await bot.lives.current(guild_id)
    snack = None if life is None else SNACK_BY_KEY.get(life.favorite_snack or "")
    if snack is None:
        return _NOTHING_YET
    return f"・{with_emoji(bot.emoji(snack.emoji_name), snack.name)}"


async def _favorite_emoji(bot: "WispBot", guild_id: int) -> str:
    """His most used expression that is still uploaded."""
    for name in await bot.wisp_lunchbox.favorite_expressions(guild_id):
        if name in bot.emojis_by_name:
            return f"・{bot.emoji(name)}"
    return _NOTHING_YET


async def _collections(bot: "WispBot", guild_id: int) -> list[str]:
    """The current life's gift collections."""
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None:
        return [_NOTHING_YET]
    kept = await bot.gifts.kept(guild_id, life.id)
    return collection_lines(bot, kept) or [_NOTHING_YET]


async def lunchbox_text(bot: "WispBot", guild_id: int) -> str:
    """Wisp's lunchbox, trimmed from the oldest song so it fits one message."""
    favorites = await bot.wisp_lunchbox.favorites(guild_id, FAVORITE_SONGS_SHOWN)
    songs = [
        f"・{_short_day(favorite.day)} ・ <@{favorite.user_id}> ・ {favorite.url}"
        for favorite in favorites
    ]
    head = ["♪ Wisp's lunchbox", SEPARATOR, "Favorite songs"]
    tail = [
        *([] if songs else [_NOTHING_YET]),
        SEPARATOR,
        "Favorite snack",
        await _favorite_snack(bot, guild_id),
        "Favorite emoji",
        await _favorite_emoji(bot, guild_id),
        SEPARATOR,
        "Collections",
        *await _collections(bot, guild_id),
    ]
    return fit(head, songs, tail)


@wisp.command(name="lunchbox", description="See the things Wisp keeps in his lunchbox.")
async def wisp_lunchbox(interaction: discord.Interaction["WispBot"]) -> None:
    """Show Wisp's lunchbox, only to the member who asked. Anyone may look."""
    bot = interaction.client
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(
        await lunchbox_text(bot, guild_id),
        ephemeral=True,
        allowed_mentions=_NO_PING,
        suppress_embeds=True,
    )


async def setup(bot: "WispBot") -> None:
    """Load Wisp's lunchbox; its command joins the shared group on import."""
