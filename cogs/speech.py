"""Wisp's AI voice in Discord: asking the provider chain and reporting outages."""

from typing import TYPE_CHECKING, Final

import discord

from ai.chain import AllProvidersFailed
from ai.prompt import Prompt
from cogs.assets import COIN_EMOJI
from wisp.voice import EGG_EXPRESSION, Reply, parse_reply

if TYPE_CHECKING:
    from app import WispBot

_EXPRESSION_PREFIX: Final = "wisp_"
_NOT_HIS_FACES: Final = frozenset({COIN_EMOJI, EGG_EXPRESSION})
_OUTAGE_STREAK: Final = "ai"
_CONTEXT: Final = "Wisp's AI voice"


def expressions(bot: "WispBot") -> list[str]:
    """Names of hatched Wisp's uploaded face emojis, sorted.

    The coin is not a face, and the egg's face is only the egg's.
    """
    return sorted(
        name
        for name in bot.emojis_by_name
        if name.startswith(_EXPRESSION_PREFIX) and name not in _NOT_HIS_FACES
    )


async def ai_reply(
    bot: "WispBot", guild: discord.Guild | None, prompt: Prompt
) -> Reply | None:
    """Ask Wisp's AI voice for a line, cleaned for posting.

    Returns None when every provider failed or no words were left after
    cleaning. An outage is reported in Wisp's House once per streak per guild,
    and the next answer ends the streak.
    """
    try:
        raw = await bot.ai.complete(prompt)
    except AllProvidersFailed as error:
        await _report_outage(bot, guild, error)
        return None
    if guild is not None:
        bot.failing_displays.discard((guild.id, _OUTAGE_STREAK))
    reply = parse_reply(raw, bot.emoji)
    return reply if reply.text else None


async def _report_outage(
    bot: "WispBot", guild: discord.Guild | None, error: AllProvidersFailed
) -> None:
    """Report that the AI voice is down, unless this guild's streak was reported."""
    if guild is not None:
        key = (guild.id, _OUTAGE_STREAK)
        if key in bot.failing_displays:
            return
        bot.failing_displays.add(key)
    await bot.report_error(guild, _CONTEXT, error)
