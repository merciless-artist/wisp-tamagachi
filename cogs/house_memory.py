"""Wisp's long memory at work: what comes back to him, and what he keeps.

A memory problem is reported once per streak and never stops him talking.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Final

from ai.chain import ProviderError
from cogs.announce import display_name
from wisp.life import Life
from wisp.memories import Found, Memory, MemoryStoreError, choose, memories_text
from wisp.rules import CONTEXT_LINE_CHARS, MEMORY_RECENT_SKIP

if TYPE_CHECKING:
    from app import WispBot

log = logging.getLogger("wisp")

_CONTEXT: Final = "using Wisp's long memory"
_FAILURES: Final = (ProviderError, MemoryStoreError)


async def _report_once(bot: "WispBot", guild_id: int, error: Exception) -> None:
    key = (guild_id, _CONTEXT)
    if key in bot.failing_displays:
        log.warning("%s failed again in guild %d: %s", _CONTEXT, guild_id, error)
        return
    bot.failing_displays.add(key)
    await bot.report_error(bot.get_guild(guild_id), _CONTEXT, error)


async def _closest(
    bot: "WispBot", guild_id: int, text: str, member_id: int | None, now: datetime
) -> list[Found]:
    """The memories closest to `text` that come back to him, now strengthened."""
    store = bot.memory
    assert store is not None
    embedding = await bot.embedder.for_search(text)
    before = now - MEMORY_RECENT_SKIP
    mine = (
        []
        if member_id is None
        else await store.from_member(guild_id, member_id, embedding, before)
    )
    house = await store.from_house(guild_id, embedding, before, excluding=member_id)
    chosen = choose(mine, house, now)
    await store.recalled(chosen, now)
    return chosen


async def recall(
    bot: "WispBot",
    guild_id: int,
    life: Life,
    text: str,
    member_id: int | None,
    now: datetime,
) -> str:
    """What he remembers that is close to `text`, for his prompt; "" for nothing.

    `member_id` is who he is answering, by Discord ID, and their memories come
    first; None, when he chimes in on his own, searches the whole House. He
    recalls nothing with no words to go on, or during a staff test life.
    """
    if bot.memory is None or life.is_test or not text:
        return ""
    try:
        chosen = await _closest(bot, guild_id, text, member_id, now)
    except _FAILURES as error:
        await _report_once(bot, guild_id, error)
        return ""
    bot.failing_displays.discard((guild_id, _CONTEXT))
    guild = bot.get_guild(guild_id)
    names = {
        found.memory.member_id: display_name(
            guild, await bot.players.get(guild_id, found.memory.member_id)
        )
        for found in chosen
    }
    return memories_text(chosen, life.id, names, now)


async def keep(
    bot: "WispBot",
    guild_id: int,
    life: Life,
    key: str,
    member_id: int,
    said: str,
    reply: str,
    now: datetime,
) -> None:
    """Save what a member said to him and what he said back.

    `key` is unique to the exchange and `member_id` is who spoke, by Discord
    ID. Nothing is saved with no words, or during a staff test life.
    """
    store = bot.memory
    if store is None or life.is_test or life.id is None or not said:
        return
    memory = Memory(
        member_id,
        life.id,
        life.version,
        said[:CONTEXT_LINE_CHARS],
        reply[:CONTEXT_LINE_CHARS],
        now,
        0,
        now,
    )
    try:
        embedding = await bot.embedder.for_saving(f"{memory.said}\n{memory.reply}")
        await store.add(guild_id, key, memory, embedding)
    except _FAILURES as error:
        await _report_once(bot, guild_id, error)
