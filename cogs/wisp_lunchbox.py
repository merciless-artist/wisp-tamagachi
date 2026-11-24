"""Wisp's own lunchbox, WiSP'S FAVORITES: songs, snacks, emoji and gifts.

The layout is Myra's, from `DOCS/specs/2026-11-23-wisps-favorites-layout.md`.
"""

import asyncio
import contextlib
import dataclasses
import random
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.announce import display_name, say_in_mealtime
from cogs.channels import in_channel, may_post_in, where_of
from cogs.groups import require_guild, wisp
from cogs.players import bot_of, press
from db.lunchbox import Favorite
from wisp.life import Life, mood
from wisp.lines import Moment
from wisp.rules import FAVORITE_SONGS_SHOWN, GIFT_BY_KEY, SNACK_BY_KEY
from wisp.text import (
    LAYOUT_TEXT_LIMIT,
    SPACER,
    Frame,
    frame_of,
    text_length,
    with_emoji,
)

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_LUNCHBOX_ID: Final = "wisp:lunchbox"
_TITLE: Final = "Wisp's favorites"
_NOTHING_YET: Final = "none yet"

# ---
# Song titles
# ---


async def with_titles(
    bot: "WispBot", guild_id: int, favorites: Sequence[Favorite]
) -> list[Favorite]:
    """`favorites`, each with its song's name, read and stored the first time.

    The pages of favorites not read yet are read now, all at once, and what
    was read is stored. A page that could not be read stays unread, to be
    tried the next time; it is never an error post.
    """
    unread = [favorite for favorite in favorites if favorite.title is None]
    titles = await asyncio.gather(
        *(bot.share_links.song_title(favorite.url) for favorite in unread)
    )
    read: dict[date, str] = {}
    for favorite, title in zip(unread, titles, strict=True):
        if title is not None:
            await bot.wisp_lunchbox.set_title(guild_id, favorite.day, title)
            read[favorite.day] = title
    return [
        dataclasses.replace(favorite, title=read.get(favorite.day, favorite.title))
        for favorite in favorites
    ]


def _title(favorite: Favorite) -> str:
    """The song's name as Discord should show it, or "" when it has none."""
    return discord.utils.escape_markdown(favorite.title or "")


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
    has a favorite or had no viibrmusic.com feeds. He reads the song's name
    from its page and keeps it, and the post names it when he has it. He says
    it in the mood of `life`. A failed post is reported where it happened.
    """
    yesterday = now.astimezone(UTC).date() - timedelta(days=1)
    picked = await bot.wisp_lunchbox.pick_favorite(guild.id, yesterday, rng, now)
    if picked is None:
        return
    (favorite,) = await with_titles(bot, guild.id, [picked])
    player = await bot.players.get(guild.id, favorite.user_id)
    line = bot.lines.pick(
        Moment.FAVORITE_SONG, mood(life), name=display_name(guild, player)
    )
    title = _title(favorite)
    track = f'track "{title}"' if title else "track"
    await say_in_mealtime(
        bot,
        guild,
        f"♪ Wisp put <@{favorite.user_id}>'s {track} in his lunchbox ・ "
        f"{favorite.url}\n{line}",
        "posting Wisp's favorite song to Mealtime",
    )


# ---
# The lunchbox
# ---


def _songs(bot: "WispBot", frame: Frame, favorites: Sequence[Favorite]) -> list[str]:
    """The songs: two lines each, `SPACER` before each one and after the last."""
    shown = f"Top {len(favorites)} songs" if favorites else "Top songs"
    lines = [frame.heading(shown, 0), SPACER]
    if not favorites:
        return [*lines, frame.big_item(_NOTHING_YET), SPACER]
    speaker = bot.emoji("portable_speaker")
    for number, favorite in enumerate(favorites, start=1):
        day = f"{favorite.day:%b}".upper() + f" {favorite.day.day}"
        title = _title(favorite)
        named = f"{title}・" if title else ""
        listen = with_emoji(speaker, f"{named}[♫ listen here]({favorite.url})")
        lines += [
            frame.note(f"**{number:02d} · {day}** — <@{favorite.user_id}>"),
            frame.note(listen),
            SPACER,
        ]
    return lines


async def _snacks(
    bot: "WispBot", frame: Frame, guild_id: int, life: Life | None
) -> list[str]:
    """His favorite snack this life, then the one he ate most if it differs."""
    heading = frame.heading("Favorite snacks", 1, size="###", gap="")
    if life is None or life.id is None:
        return [heading, frame.big_item(_NOTHING_YET)]
    most = await bot.activity_log.most_eaten_snack(guild_id, life.id)
    keys = dict.fromkeys(key for key in (life.favorite_snack, most) if key)
    items = [
        frame.big_item(f"{snack.name} {emoji}".rstrip())
        for key in keys
        if (snack := SNACK_BY_KEY.get(key)) is not None
        for emoji in [bot.emoji(snack.emoji_name)]
    ]
    return [heading, *(items or [frame.big_item(_NOTHING_YET)])]


async def _emoji(bot: "WispBot", frame: Frame, guild_id: int) -> list[str]:
    """His most used expression that is still uploaded, then its name in code."""
    heading = frame.heading("Favorite emoji", 2)
    for name in await bot.wisp_lunchbox.favorite_expressions(guild_id):
        if name in bot.emojis_by_name:
            return [heading, frame.big_item(f"{bot.emoji(name)} `:{name}:`")]
    return [heading, frame.big_item(_NOTHING_YET)]


async def _gifts(bot: "WispBot", guild_id: int, life: Life | None) -> list[str]:
    """The gifts this life kept, oldest first, as their emojis at his stage.

    A gift whose emoji is not uploaded shows its name.
    """
    if life is None or life.id is None:
        return []
    return [
        bot.emoji(gift.emoji_name(life.stage)) or gift.name
        for attempt in await bot.gifts.kept(guild_id, life.id)
        if (gift := GIFT_BY_KEY.get(attempt.gift)) is not None
    ]


def _gift_line(frame: Frame, gifts: Sequence[str], room: int) -> str:
    """The gifts on one line joined by `・`, as many as fit in `room`."""
    line = frame.big_item(_NOTHING_YET)
    for shown in range(1, len(gifts) + 1):
        tried = frame.big_item("・".join(gifts[:shown]))
        if text_length(tried) > room:
            break
        line = tried
    return line


async def lunchbox_text(bot: "WispBot", guild_id: int) -> str:
    """WiSP'S FAVORITES in Myra's layout, the text of one layout message.

    His newest favorite songs, each named when its page names it; his
    favorite snacks; his favorite emoji; and the gifts this life kept,
    trimmed to fit the message. Its title, headings and footer are the
    shared house style's (`wisp.text.Frame`); an emoji of the layout that is
    not uploaded is left out.
    """
    frame = frame_of(bot.emoji)
    favorites = await with_titles(
        bot,
        guild_id,
        await bot.wisp_lunchbox.favorites(guild_id, FAVORITE_SONGS_SHOWN),
    )
    life = await bot.lives.current(guild_id)
    before = [
        frame.title(_TITLE),
        *_songs(bot, frame, favorites),
        *await _snacks(bot, frame, guild_id, life),
        *await _emoji(bot, frame, guild_id),
        frame.heading("Favorite gifts", 3, gap="  "),
    ]
    after = [frame.footer]
    room = LAYOUT_TEXT_LIMIT - text_length("\n".join([*before, *after])) - 2
    gifts = _gift_line(frame, await _gifts(bot, guild_id, life), room)
    return "\n".join([*before, gifts, *after])


def _layout(text: str) -> discord.ui.LayoutView:
    """The lunchbox as one Components V2 message of its text."""
    layout = discord.ui.LayoutView(timeout=None)
    layout.add_item(discord.ui.TextDisplay(text))
    return layout


async def _post(send: Callable[..., Awaitable[Any]], text: str, **kwargs: Any) -> None:
    """Send the lunchbox with `send`, pinging nobody; `kwargs` go with the send."""
    await send(view=_layout(text), allowed_mentions=_NO_PING, **kwargs)


async def _send_privately(interaction: discord.Interaction, text: str) -> None:
    """Answer a deferred interaction with the lunchbox, only to the member."""
    await _post(interaction.followup.send, text, ephemeral=True)


@wisp.command(name="lunchbox", description="See the things Wisp keeps in his lunchbox.")
async def wisp_lunchbox(interaction: discord.Interaction["WispBot"]) -> None:
    """Show Wisp's lunchbox in the channel where it was asked for. Anyone may look.

    It is one Components V2 message of its text, Myra's layout, and it
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
        await _post(channel.send, text)
        with contextlib.suppress(discord.HTTPException):
            await interaction.delete_original_response()
        return
    house = await bot.house_channel(interaction.guild)
    if house is None:
        await _send_privately(interaction, text)
        return
    await _post(house.send, text)
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
    """The Lunchbox button on the Interaction post; it shows the lunchbox privately.

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
