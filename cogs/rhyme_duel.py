"""Rhyme Duel: one member and Wisp trade rhymes in the member's room.

A duel starts from /wisp play rhyme, or from the Rhyme Duel button in the
private games menu the Status post's Play button opens.
"""

import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

import discord

from cogs.craving import CravingButton
from cogs.games import ROOM_BUSY, check_game, craving_live, enter_room, reward_game
from cogs.groups import play, require_guild
from cogs.players import (
    FROZEN_REASON,
    NOT_ALIVE_REASON,
    blocker_reason,
    bot_of,
    is_frozen,
    maybe_meet,
    member_blocker,
    press,
    say_privately,
)
from cogs.vault import refresh_vault
from db.activity import InteractionKind
from wisp.language import Language
from wisp.life import Life, Phase, mood
from wisp.lines import Moment
from wisp.rhymes import (
    clean_word,
    opening_word,
    rhyme_kind,
    same_word_key,
    score,
    wisp_reply,
)
from wisp.rules import PLAYS_PER_DAY, RHYME_TURN
from wisp.text import (
    MESSAGE_LIMIT,
    SEPARATOR,
    clip,
    count,
    daily_reset,
    frame_of,
    text_length,
)

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_CUT: Final = "..."
_PLAY_ID: Final = "wisp:play"
_RHYME_DUEL_ID: Final = "wisp:play:rhyme"
_PICK_A_GAME: Final = "♪ Pick a game to play with Wisp."

_BANNED: Final = "♪ Wisp is not dueling with you right now."
_NOT_COUNTED: Final = "♪ This duel didn't count toward his Wellbeing: "
_NO_RHYME: Final = "you didn't score a rhyme."
_TIMED_OUT: Final = "Time ran out"
_NOT_ONE_WORD: Final = "That wasn't one word"

# ---
# The duel
# ---


@dataclass(frozen=True)
class _Outcome:
    """How a duel ended: who got stuck and why, every word said and the score."""

    ending: Moment
    reason: str | None
    chain: list[str]
    points: int


def _bold(word: str) -> str:
    return f"**{word}**"


async def _duel(
    bot: "WispBot",
    thread: discord.Thread,
    user_id: int,
    life: Life,
    rng: random.Random,
    language: Language,
) -> _Outcome:
    """Trade rhymes in `language` until someone is stuck; only the player's
    messages count.

    Wisp opens with a word, then each turn the player must answer with one
    unused word that rhymes with the last one, within RHYME_TURN. A word is
    used when any spelling of it was said.
    """
    chain = [opening_word(rng, language=language)]
    points = 0
    opener = bot.lines.pick(Moment.RHYME_START, mood(life), word=_bold(chain[0]))
    await thread.send(
        f"{opener}\n・The word to rhyme is: {_bold(chain[0])}",
        allowed_mentions=_NO_PING,
    )

    def is_turn(message: discord.Message) -> bool:
        return message.author.id == user_id and message.channel.id == thread.id

    while True:
        try:
            message = await bot.wait_for(
                "message", check=is_turn, timeout=RHYME_TURN.total_seconds()
            )
        except TimeoutError:
            return _Outcome(Moment.RHYME_PLAYER_STUCK, _TIMED_OUT, chain, points)
        answer = clean_word(message.content, language=language)
        if answer is None:
            return _Outcome(Moment.RHYME_PLAYER_STUCK, _NOT_ONE_WORD, chain, points)
        said = {same_word_key(word, language=language) for word in chain}
        if same_word_key(answer, language=language) in said:
            reason = f"{answer} was already used"
            return _Outcome(Moment.RHYME_PLAYER_STUCK, reason, chain, points)
        kind = rhyme_kind(chain[-1], answer, language=language)
        if kind is None:
            reason = f"{answer} doesn't rhyme with {chain[-1]}"
            return _Outcome(Moment.RHYME_PLAYER_STUCK, reason, chain, points)
        chain.append(answer)
        points += score(kind)
        reply = wisp_reply(
            answer, set(chain), life.stage, len(chain) // 2, rng, language=language
        )
        if reply is None:
            return _Outcome(Moment.RHYME_WISP_STUCK, None, chain, points)
        chain.append(reply)
        await thread.send(f"♪ {reply}", allowed_mentions=_NO_PING)


def summary_text(
    line: str,
    reason: str | None,
    chain: list[str],
    points: int,
    *,
    divider: str = SEPARATOR,
) -> str:
    """The end of a duel: Wisp's line, `divider`, why it ended, the chain and
    the score.

    The oldest words are left out of the chain when it would not fit one message.
    If it still does not fit, the reason is cut short, and as a last resort the
    message itself. The message is measured by `text_length` and never cut
    inside a character.
    """
    reasons = [f"・{reason}"] if reason else []
    score_line = f"・Score: {count(points, 'point')}"
    shown = chain
    while True:
        trimmed = "... " if len(shown) < len(chain) else ""
        chain_line = f"・{trimmed}{' ・ '.join(shown)}"
        text = "\n".join([line, divider, *reasons, chain_line, score_line])
        overflow = text_length(text) - MESSAGE_LIMIT
        if overflow <= 0:
            return text
        kept = text_length(reasons[0]) - overflow - len(_CUT) if reasons else 0
        if shown:
            shown = shown[1:]
        elif kept > 0:
            reasons = [clip(reasons[0], kept) + _CUT]
        else:
            return clip(text, MESSAGE_LIMIT)


# ---
# Before and after
# ---


@dataclass(frozen=True)
class _Played:
    """What a finished duel did: the best score and what to tell the player."""

    new_best: bool
    receipt: str


def _verdict(
    points: int,
    life: Life | None,
    frozen: bool,
    blocked: str | None,
    plays: int,
    now: datetime,
) -> tuple[Life, int] | str:
    """The living life and its id when the duel counts as play, else why not.

    `blocked` is why the player may not feed Wisp, or None when they may.
    """
    if points <= 0:
        return _NO_RHYME
    if life is None or life.id is None or life.phase is not Phase.ALIVE:
        return NOT_ALIVE_REASON
    if frozen:
        return FROZEN_REASON
    if blocked is not None:
        return blocked
    if plays >= PLAYS_PER_DAY:
        played = count(PLAYS_PER_DAY, "counted game")
        return f"you've already played {played} today (resets at {daily_reset(now)})."
    return life, life.id


async def _record_play(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    points: int,
) -> _Played:
    """Count the duel as play and keep the score if it is the player's best.

    The play, with its bond, growth, care and Vault point, only counts when the
    player scored a rhyme, Wisp is alive and not frozen, the player can feed
    Wisp and has had fewer than PLAYS_PER_DAY counted games today. The best
    score is always kept. The receipt says what the duel did or exactly why it
    did not count.
    """
    now = discord.utils.utcnow()
    user_id = member.id
    async with bot.guild_lock(guild_id):
        plays = await bot.activity_log.plays_today(guild_id, user_id, now)
        blocker = await member_blocker(bot, guild_id, member, now)
        verdict = _verdict(
            points,
            await bot.lives.current(guild_id),
            await is_frozen(bot, guild_id),
            None if blocker is None else await blocker_reason(bot, guild_id, blocker),
            plays,
            now,
        )
        if isinstance(verdict, str):
            receipt = _NOT_COUNTED + verdict
        else:
            life, life_id = verdict
            reward = await reward_game(
                bot, guild_id, user_id, life, life_id, InteractionKind.PLAY, now
            )
            left = count(PLAYS_PER_DAY - plays - 1, "counted game")
            receipt = (
                f"♪ Your duel counted. {reward.wellbeing}. {reward.coins}. "
                f"{left} left today."
            )
        best = await bot.players.record_rhyme_score(guild_id, user_id, points)
    return _Played(best, receipt)


async def _host(interaction: discord.Interaction, guild_id: int) -> None:
    """Run one duel for the member, or say why they cannot have one.

    The command and the Rhyme Duel button both come here, so both refuse the
    same way, a freeze, a nap and a room that can't open included. A freeze
    that starts during the duel keeps it from counting instead. The duel
    leaves the room open for the member's next game.
    """
    bot = bot_of(interaction)
    user = interaction.user
    player = await bot.players.get(guild_id, user.id)
    life = await check_game(
        bot,
        guild_id,
        player,
        discord.utils.utcnow(),
        banned=_BANNED,
        things="Rhymes",
    )
    if isinstance(life, str):
        await say_privately(interaction, life)
        return
    thread = await enter_room(interaction)
    if thread is None:
        return
    started = f"♪ Your Rhyme Duel is on in {thread.mention}."
    await say_privately(interaction, started)
    outcome = await _duel(bot, thread, user.id, life, random.Random(), Language.EN)
    line = bot.lines.pick(outcome.ending, mood(life))
    await thread.send(
        summary_text(
            line,
            outcome.reason,
            outcome.chain,
            outcome.points,
            divider=frame_of(bot.emoji).divider,
        ),
        allowed_mentions=_NO_PING,
    )
    played = await _record_play(bot, guild_id, user, outcome.points)
    try:
        await thread.send(played.receipt, allowed_mentions=_NO_PING)
    except discord.HTTPException as error:
        await bot.report_error(
            interaction.guild, "sending a Rhyme Duel receipt", error, where=thread
        )
    if played.new_best:
        await refresh_vault(bot, guild_id)
    await maybe_meet(bot, guild_id, user.id, display_name=user.display_name)


# ---
# Starting a duel
# ---


async def start_duel(interaction: discord.Interaction) -> None:
    """Start a Rhyme Duel; a member's room runs one game at a time, a live
    Wisp's Craving included.

    The answer is private. It is a new message even when a button was
    pressed, so the duel's receipt is added under it as for the command.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True, thinking=True)
    key = (guild_id, interaction.user.id)
    if key in bot.room_games:
        await say_privately(interaction, ROOM_BUSY)
        return
    bot.room_games.add(key)
    try:
        now = discord.utils.utcnow()
        if await craving_live(bot, guild_id, interaction.user.id, now):
            await say_privately(interaction, ROOM_BUSY)
            return
        await _host(interaction, guild_id)
    finally:
        bot.room_games.discard(key)


@play.command(name="rhyme", description="Trade rhymes with Wisp in a Rhyme Duel.")
async def play_rhyme(interaction: discord.Interaction["WispBot"]) -> None:
    """Start a Rhyme Duel for the member."""
    await start_duel(interaction)


class RhymeDuelButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_RHYME_DUEL_ID),
):
    """The Rhyme Duel button in the games menu; it starts a duel like the command.

    Its custom id is fixed, so the button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Rhyme Duel",
                style=discord.ButtonStyle.primary,
                custom_id=_RHYME_DUEL_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "RhymeDuelButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Start a Rhyme Duel for whoever pressed it."""
        await press(interaction, "the Rhyme Duel button", start_duel)


# ---
# The games menu
# ---


async def _offer_games(interaction: discord.Interaction) -> None:
    """Show the presser the games they can play with Wisp, privately.

    The menu is a follow-up sent with `wait`, so discord.py files its view
    under the menu's own message id. Its buttons are persistent and work
    after the view times out; filed under the shared key a direct answer
    gets, the timeout could unregister the Rhyme Duel button for everyone.
    """
    await interaction.response.defer(ephemeral=True, thinking=True)
    view = discord.ui.View(timeout=None)
    view.add_item(RhymeDuelButton())
    view.add_item(CravingButton())
    await interaction.followup.send(
        _PICK_A_GAME, view=view, ephemeral=True, allowed_mentions=_NO_PING, wait=True
    )


class PlayButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_PLAY_ID),
):
    """The Play button on the status card, which opens the games menu privately.

    Its custom id is fixed, so the button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Play",
                style=discord.ButtonStyle.primary,
                custom_id=_PLAY_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "PlayButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open the games menu for whoever pressed it."""
        await press(interaction, "the Play button", _offer_games)


async def setup(bot: "WispBot") -> None:
    """Register the game buttons so they still work after a restart.

    The command joins the shared groups on import.
    """
    bot.add_dynamic_items(PlayButton, RhymeDuelButton)
