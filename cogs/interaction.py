"""The Interaction post: everything a member can do with Wisp, one button each.

The Studio's Interaction post has its card under its first message: one
Components V2 message of Myra's lines, each followed by its button on a row
of its own. The buttons keep the persistent custom ids the status card's
buttons had, so presses work after a restart and old status cards still
work. The card is drawn each time the Studio is ensured (setup included),
edited in place, and posted again when it is gone.
"""

import asyncio
from typing import TYPE_CHECKING, Any, Final

import discord
from discord.ext import commands

from cogs.conversation import PokeButton
from cogs.rhyme_duel import PlayButton
from cogs.snacks import FeedButton, ShopButton, SnackPackButton
from cogs.studio import StudioError, post_url, studio_thread
from cogs.wisp_lunchbox import LunchboxButton

if TYPE_CHECKING:
    from app import WispBot

_THREAD_ATTR: Final = "interaction_thread_id"
_CARD_KEY: Final = "interaction_message_id"
_CONTEXT: Final = "drawing the Interaction post"
_NO_PING: Final = discord.AllowedMentions.none()
_VAULT_LABEL: Final = "ViiBR Vault"


# ---
# The card
# ---


def interaction_lines(vault_link: str | None) -> list[tuple[str, discord.ui.Item[Any]]]:
    """Myra's lines, in order, each with the button under it.

    ViiBR Vault jumps to `vault_link`, the ViiBR Vault post; before there is
    one it opens the Vault privately.
    """
    vault: discord.ui.Item[Any] = (
        ShopButton(_VAULT_LABEL)
        if vault_link is None
        else discord.ui.Button(
            label=_VAULT_LABEL, style=discord.ButtonStyle.link, url=vault_link
        )
    )
    return [
        ("Feed Wisp a treat other than a music track!", FeedButton()),
        ("Poke Wisp to earn engagement points and Wisp Coins!", PokeButton("Poke")),
        ("Visit the ViiBR Vault to buy presents and vanity roles!", vault),
        (
            "Check your Snack Pack items here or check your personal storage locker",
            SnackPackButton("Snack Pack"),
        ),
        ("Play games with Wisp!", PlayButton()),
        (
            "Check out Wisp's Lunchbox with his favorite songs, toys and more!",
            LunchboxButton(),
        ),
    ]


def interaction_layout(vault_link: str | None) -> discord.ui.LayoutView:
    """The card: each of Myra's lines, then its button on a row of its own."""
    layout = discord.ui.LayoutView(timeout=None)
    for text, button in interaction_lines(vault_link):
        layout.add_item(discord.ui.TextDisplay(text))
        layout.add_item(discord.ui.ActionRow(button))
    return layout


# ---
# Drawing the post
# ---


async def show_interaction(bot: "WispBot", guild_id: int) -> None:
    """Draw the Interaction post's card with the current ViiBR Vault link.

    The stored card is edited in place; one that is gone, or was never
    posted, is posted and stored. A guild without an Interaction post is
    left alone. A failure is posted in the post, or in Wisp's House when it
    cannot be reached. It is never raised.
    """
    if (await bot.settings.get(guild_id)).interaction_thread_id is None:
        return
    thread: discord.Thread | None = None
    try:
        thread = await studio_thread(bot, guild_id, _THREAD_ATTR)
        async with bot.display_locks.setdefault((guild_id, _CARD_KEY), asyncio.Lock()):
            await _draw(bot, guild_id, thread)
    except (discord.DiscordException, StudioError) as error:
        await bot.report_error(bot.get_guild(guild_id), _CONTEXT, error, where=thread)


async def _draw(bot: "WispBot", guild_id: int, thread: discord.Thread) -> None:
    settings = await bot.settings.get(guild_id)
    layout = interaction_layout(post_url(guild_id, settings.shop_thread_id))
    if settings.interaction_message_id is not None:
        try:
            await thread.get_partial_message(settings.interaction_message_id).edit(
                view=layout, allowed_mentions=_NO_PING
            )
            return
        except discord.NotFound:
            pass
    posted = await thread.send(view=layout, allowed_mentions=_NO_PING)
    await bot.settings.update(guild_id, interaction_message_id=posted.id)


# ---
# Listener
# ---


class Interaction(commands.Cog):
    """Draws the Interaction post each time the Studio is ensured."""

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_studio_ensured(self, guild_id: int) -> None:
        """Draw the post for the guild whose Studio was just ensured."""
        await show_interaction(self.bot, guild_id)


async def setup(bot: "WispBot") -> None:
    """Load the Interaction cog."""
    await bot.add_cog(Interaction(bot))
