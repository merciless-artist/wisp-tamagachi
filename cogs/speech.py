"""Wisp's AI voice in Discord: the provider chain, outages and talk in his House."""

import random
from collections import deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

import discord

from ai.chain import AllProvidersFailed
from ai.prompt import Prompt
from wisp.rules import (
    CONTEXT_LINES,
    NAP_STAGES,
    POKE_STREAK_GAP,
    TALK_COOLDOWN,
    Stage,
)
from wisp.voice import (
    COIN_EMOJI,
    EGG_EXPRESSION,
    MINI_COIN_EMOJI,
    NAP_EMOJI,
    STAGE_FACES,
    ChatLine,
    Reply,
    parse_reply,
)

if TYPE_CHECKING:
    from app import WispBot

POKE_ID: Final = "wisp:poke"
_EXPRESSION_PREFIX: Final = "wisp_"
_NOT_HIS_FACES: Final = frozenset({COIN_EMOJI, MINI_COIN_EMOJI, EGG_EXPRESSION})
_OUTAGE_STREAK: Final = "ai"
_CONTEXT: Final = "Wisp's AI voice"

# ---
# Asking the AI
# ---


def expressions(bot: "WispBot", stage: Stage) -> list[str]:
    """Names of hatched Wisp's uploaded emojis he can use at `stage`.

    A stage in `STAGE_FACES` gets its own faces, in that order, where uploaded.
    Every other stage gets all his uploaded faces, sorted: the coins are not
    faces, the egg's face is only the egg's and the nap is only for the stages
    that have nap art.
    """
    if (faces := STAGE_FACES.get(stage)) is not None:
        return [name for name in faces if name in bot.emojis_by_name]
    unavailable = (
        _NOT_HIS_FACES if stage in NAP_STAGES else _NOT_HIS_FACES | {NAP_EMOJI}
    )
    return sorted(
        name
        for name in bot.emojis_by_name
        if name.startswith(_EXPRESSION_PREFIX) and name not in unavailable
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


# ---
# Talk in the House
# ---


class HouseTalk:
    """What Wisp keeps in memory about talk in each guild's House.

    Mentions and pokes share one TALK_COOLDOWN per member, so neither can be
    used to get round the other. `rng` rolls how he takes each poke.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng if rng is not None else random.Random()
        self._chat: dict[int, deque[ChatLine]] = {}
        self._answered_at: dict[tuple[int, int], datetime] = {}
        self._stirred_at: dict[int, datetime] = {}
        self._pokes: dict[tuple[int, int], tuple[datetime, int]] = {}

    def hear(self, guild_id: int, line: ChatLine) -> tuple[ChatLine, ...]:
        """Add a line to the House's recent chat; return the lines before it."""
        chat = self._chat.setdefault(guild_id, deque(maxlen=CONTEXT_LINES))
        earlier = tuple(chat)
        chat.append(line)
        return earlier

    def chat(self, guild_id: int) -> tuple[ChatLine, ...]:
        """The House's recent chat, oldest first."""
        return tuple(self._chat.get(guild_id, ()))

    def stir(self, guild_id: int, now: datetime) -> None:
        """Note that a member said something in the House or poked Wisp."""
        self._stirred_at[guild_id] = now

    def quiet_for(self, guild_id: int, now: datetime) -> timedelta | None:
        """How long since a member last stirred the House; None if none has."""
        stirred = self._stirred_at.get(guild_id)
        return None if stirred is None else now - stirred

    def take_turn(self, guild_id: int, user_id: int, now: datetime) -> bool:
        """Claim an answer for the member; False within TALK_COOLDOWN of the last."""
        key = (guild_id, user_id)
        last = self._answered_at.get(key)
        if last is not None and now - last < TALK_COOLDOWN:
            return False
        self._answered_at[key] = now
        return True

    def poke(self, guild_id: int, user_id: int, now: datetime) -> int:
        """Count the member's poke; return how many they have made in a row.

        A poke within POKE_STREAK_GAP of the member's last one adds to their
        streak; a later one starts a new streak at 1.
        """
        key = (guild_id, user_id)
        last = self._pokes.get(key)
        streak = last[1] + 1 if last and now - last[0] < POKE_STREAK_GAP else 1
        self._pokes[key] = (now, streak)
        return streak


def poke_button() -> "discord.ui.Button[discord.ui.View]":
    """The Poke Wisp button. Presses reach `PokeButton` by its custom id."""
    return discord.ui.Button(
        label="Poke Wisp", style=discord.ButtonStyle.secondary, custom_id=POKE_ID
    )


def poke_view() -> discord.ui.View:
    """A view with just the Poke Wisp button, for the House's new-egg posts."""
    view = discord.ui.View(timeout=None)
    view.add_item(poke_button())
    return view
