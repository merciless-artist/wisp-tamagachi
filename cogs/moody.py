"""Moody phrases: name the song Wisp grumbled.

Staff add song lines for each stage from Child on (`cogs.moody_staff`). When
Wisp is in a bad way his AI answer now and then works one in, word for word,
with a menu under it; the first member to pick the right song wins wisp
coins. Rounds and guesses are stored, so the menu keeps working after a
restart.
"""

import asyncio
import random
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.groups import require_guild
from cogs.players import bot_of, press, say_privately
from cogs.rooms import NOT_JOINED
from db.moody import MoodyRound
from wisp.life import Life
from wisp.moody import (
    Phrase,
    is_moody,
    option_label,
    options_for,
    pick_phrase,
    with_phrase,
    won_line,
)
from wisp.rules import (
    MOODY_PHRASE_CHANCE,
    MOODY_PHRASE_GAP,
    MOODY_PHRASE_REWARD,
    MOODY_ROUND_FOR,
)
from wisp.text import MESSAGE_LIMIT, count

if TYPE_CHECKING:
    from app import WispBot

_MENU_TEMPLATE: Final = re.compile(r"wisp:moody:(?P<round>[0-9]+)")
_MENU_CONTEXT: Final = "the moody phrase menu"
_PLACEHOLDER: Final = "♪ Name that song"

_BANNED: Final = "♪ Wisp is not playing with you right now."
_NOPE: Final = "♪ Nope, not that one."
_ALREADY: Final = "♪ You already took your guess."
_TOO_LATE: Final = "♪ Too late, this one's done."

_draw_locks: dict[int, asyncio.Lock] = {}

# ---
# Starting a round
# ---


@dataclass(frozen=True)
class Draw:
    """A stored round about to go out with one of Wisp's AI answers."""

    round_id: int
    phrase: Phrase
    options: tuple[Phrase, ...]


async def draw(
    bot: "WispBot", guild_id: int, life: Life, now: datetime, rng: random.Random
) -> Draw | None:
    """Maybe open a round for Wisp's next AI answer; None when there is none.

    Only while he is moody (see `wisp.moody.is_moody`), on a roll of
    MOODY_PHRASE_CHANCE, MOODY_PHRASE_GAP after the server's last round and
    once his stage has enough songs. The round is stored at once, so two
    answers at the same moment never both carry one.
    """
    if not is_moody(life, now) or rng.random() >= MOODY_PHRASE_CHANCE:
        return None
    async with _draw_locks.setdefault(guild_id, asyncio.Lock()):
        last = await bot.moody.last_round(guild_id)
        if last is not None and now - last.opened_at < MOODY_PHRASE_GAP:
            return None
        phrases = await bot.moody.for_stage(guild_id, life.stage)
        phrase = pick_phrase(phrases, None if last is None else last.phrase_id, rng)
        if phrase is None:
            return None
        options = options_for(phrase, phrases, rng)
        round_id = await bot.moody.open_round(
            guild_id, phrase.id, [option.id for option in options], now
        )
    return Draw(round_id, phrase, tuple(options))


def _menu(
    round_id: int, phrases: Sequence[Phrase], *, disabled: bool = False
) -> discord.ui.View:
    options = [
        discord.SelectOption(label=option_label(phrase), value=str(phrase.id))
        for phrase in phrases
    ]
    view = discord.ui.View(timeout=None)
    view.add_item(MoodyMenu(round_id, options, disabled=disabled))
    return view


def view_kwargs(view: discord.ui.View | None) -> dict[str, Any]:
    """The keyword that sends `view`, or none at all without one."""
    return {} if view is None else {"view": view}


Send = Callable[[str, discord.ui.View | None], Awaitable[discord.Message]]


async def post(bot: "WispBot", drawn: Draw | None, text: str, send: Send) -> None:
    """Send Wisp's answer through `send`, with the round's phrase and menu.

    Without a round the text goes as it is. A round whose answer Discord
    refused is deleted, so it never holds back the next one.

    Raises:
        discord.HTTPException: Discord refused the answer.
    """
    if drawn is None:
        await send(text, None)
        return
    try:
        sent = await send(
            with_phrase(text, drawn.phrase, MESSAGE_LIMIT),
            _menu(drawn.round_id, drawn.options),
        )
    except discord.HTTPException:
        await bot.moody.drop_round(drawn.round_id)
        raise
    await bot.moody.set_message(drawn.round_id, sent.id)


async def abandon(bot: "WispBot", drawn: Draw | None) -> None:
    """Delete a round whose AI answer never came."""
    if drawn is not None:
        await bot.moody.drop_round(drawn.round_id)


# ---
# Guessing
# ---


def _is_over(round_: MoodyRound, now: datetime) -> bool:
    """Whether a round was won already or is older than MOODY_ROUND_FOR."""
    return round_.winner_id is not None or now - round_.opened_at > MOODY_ROUND_FOR


async def _guess(interaction: discord.Interaction, round_id: int, chosen: int) -> None:
    """Judge a member's one guess and answer privately.

    Only members who opened /wisp board may guess. The first right guess
    wins: the coins are paid once, the menu is shut and the reply names the
    winner and the song, pinging only them.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user_id = interaction.user.id
    await interaction.response.defer()
    now = discord.utils.utcnow()
    player = await bot.players.get(guild_id, user_id)
    if player.is_banned(now):
        await say_privately(interaction, _BANNED)
        return
    if player.activated_at is None:
        await say_privately(interaction, f"♪ {NOT_JOINED}")
        return
    round_ = await bot.moody.get_round(guild_id, round_id)
    phrases = {} if round_ is None else await bot.moody.by_ids(guild_id, round_.options)
    answer = None if round_ is None else phrases.get(round_.phrase_id)
    if round_ is None or answer is None or _is_over(round_, now):
        await say_privately(interaction, _TOO_LATE)
        return
    if not await bot.moody.take_guess(round_id, user_id):
        await say_privately(interaction, _ALREADY)
        return
    if chosen != answer.id:
        await say_privately(interaction, _NOPE)
        return
    if not await bot.moody.win(round_id, user_id):
        await say_privately(interaction, _TOO_LATE)
        return
    await bot.players.add_points(guild_id, user_id, MOODY_PHRASE_REWARD)
    shown = [phrases[option] for option in round_.options if option in phrases]
    said = "" if interaction.message is None else interaction.message.content
    await interaction.edit_original_response(
        content=f"{said}\n{won_line(user_id, answer)}",
        view=_menu(round_id, shown, disabled=True),
        allowed_mentions=discord.AllowedMentions(
            everyone=False,
            roles=False,
            users=[discord.Object(user_id)],
            replied_user=False,
        ),
    )
    await say_privately(
        interaction, f"♪ That's it! +{count(MOODY_PHRASE_REWARD, 'wisp coin')}"
    )


class MoodyMenu(
    discord.ui.DynamicItem[discord.ui.Select[Any]],
    template=_MENU_TEMPLATE,
):
    """The name-that-song menu under one of Wisp's moody replies.

    The round's id is in its custom id, so it keeps working after a restart.
    """

    def __init__(
        self,
        round_id: int,
        options: list[discord.SelectOption] | None = None,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Select(
                custom_id=f"wisp:moody:{round_id}",
                placeholder=_PLACEHOLDER,
                options=options or [],
                disabled=disabled,
            )
        )
        self.round_id = round_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
        /,
    ) -> "MoodyMenu":
        """Rebuild the menu a pick reached."""
        return cls(int(match["round"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        """Judge the member's pick."""
        chosen = int(self.item.values[0])

        async def judged(pressed: discord.Interaction) -> None:
            await _guess(pressed, self.round_id, chosen)

        await press(interaction, _MENU_CONTEXT, judged)


async def setup(bot: "WispBot") -> None:
    """Register the menu so it works after a restart."""
    bot.add_dynamic_items(MoodyMenu)
