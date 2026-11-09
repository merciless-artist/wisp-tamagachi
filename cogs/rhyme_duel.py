"""Rhyme Duel: one member and Wisp trade rhymes in a thread off his House.

A duel starts from /wisp play rhyme, or from the Rhyme Duel button in the
private games menu the Status post's Play button opens.
"""

import random
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import discord

from cogs.announce import post_in_house
from cogs.groups import play, require_guild
from cogs.players import (
    EXPECTED_FAILURES,
    FROZEN_REASON,
    NOT_ALIVE_REASON,
    blocker_reason,
    bot_of,
    is_frozen,
    maybe_meet,
    member_blocker,
    no_wisp_text,
    press,
    say_privately,
)
from cogs.vault import refresh_vault
from db.activity import InteractionKind
from wisp.bond import casual_bond_grant
from wisp.chores import is_napping, nap_ends_at, nap_time_text
from wisp.life import Life, Meter, Phase, add_growth, change_meter, mood
from wisp.lines import Moment
from wisp.rhymes import clean_word, opening_word, rhyme_kind, score, wisp_reply
from wisp.rules import (
    BOND_PER_PLAY,
    GROWTH_PER_PLAY,
    PLAY_POINTS,
    PLAYS_PER_DAY,
    RHYME_THREAD_ARCHIVE_MINUTES,
    RHYME_TURN,
    WELLBEING_PER_PLAY,
)
from wisp.text import (
    MESSAGE_LIMIT,
    SEPARATOR,
    clip,
    count,
    meter_receipt,
    text_length,
    with_emoji,
)
from wisp.voice import MINI_COIN_EMOJI

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_CUT: Final = "..."
_PLAY_ID: Final = "wisp:play"
_RHYME_DUEL_ID: Final = "wisp:play:rhyme"
_PICK_A_GAME: Final = "♪ Pick a game to play with Wisp."

_BANNED: Final = "♪ Wisp is not dueling with you right now."
_ALREADY_DUELING: Final = (
    "♪ You already have a Rhyme Duel going. Finish that one first."
)
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


async def _duel(
    bot: "WispBot",
    thread: discord.Thread,
    user_id: int,
    life: Life,
    rng: random.Random,
) -> _Outcome:
    """Trade rhymes until someone is stuck; only the player's messages count.

    Wisp opens with a word, then each turn the player must answer with one
    unused word that rhymes with the last one, within RHYME_TURN.
    """
    chain = [opening_word(rng)]
    points = 0
    await thread.send(
        bot.lines.pick(Moment.RHYME_START, mood(life), word=chain[0]),
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
        answer = clean_word(message.content)
        if answer is None:
            return _Outcome(Moment.RHYME_PLAYER_STUCK, _NOT_ONE_WORD, chain, points)
        if answer in chain:
            reason = f"{answer} was already used"
            return _Outcome(Moment.RHYME_PLAYER_STUCK, reason, chain, points)
        kind = rhyme_kind(chain[-1], answer)
        if kind is None:
            reason = f"{answer} doesn't rhyme with {chain[-1]}"
            return _Outcome(Moment.RHYME_PLAYER_STUCK, reason, chain, points)
        chain.append(answer)
        points += score(kind)
        reply = wisp_reply(answer, set(chain), life.stage, len(chain) // 2, rng)
        if reply is None:
            return _Outcome(Moment.RHYME_WISP_STUCK, None, chain, points)
        chain.append(reply)
        await thread.send(f"♪ {reply}", allowed_mentions=_NO_PING)


def summary_text(line: str, reason: str | None, chain: list[str], points: int) -> str:
    """The end of a duel: Wisp's line, why it ended, the chain and the score.

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
        text = "\n".join([line, SEPARATOR, *reasons, chain_line, score_line])
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


class NoHouseError(LookupError):
    """Wisp's House is not set, cannot be seen or is not a text channel."""


async def _open_thread(
    bot: "WispBot", guild_id: int, guild: discord.Guild | None, name: str
) -> discord.Thread:
    """Open the duel's public thread off Wisp's House.

    Raises:
        NoHouseError: The House is not set, cannot be seen or is not a text
            channel.
    """
    channel_id = (await bot.settings.get(guild_id)).house_channel_id
    house = (
        guild.get_channel_or_thread(channel_id)
        if guild is not None and channel_id is not None
        else None
    )
    if not isinstance(house, discord.TextChannel):
        raise NoHouseError("Wisp's House is not set or is not a text channel")
    return await house.create_thread(
        name=f"Rhyme Duel ・ {name}",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=RHYME_THREAD_ARCHIVE_MINUTES,
    )


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
        return f"you've already played {played} today (resets at 00:00 UTC)."
    return life, life.id


async def _count_play(
    bot: "WispBot", guild_id: int, user_id: int, life: Life, life_id: int, plays: int
) -> str:
    """Give the play's bond, growth, care, Wellbeing and point; return the receipt."""
    now = discord.utils.utcnow()
    log = bot.activity_log
    bond = casual_bond_grant(
        await log.casual_bond_today(guild_id, user_id, now), BOND_PER_PLAY
    )
    if bond:
        await bot.players.add_bond(guild_id, user_id, bond)
    await log.record_interaction(
        guild_id, life_id, user_id, InteractionKind.PLAY, bond, 0, now
    )
    await bot.players.add_points(guild_id, user_id, PLAY_POINTS)
    add_growth(life, GROWTH_PER_PLAY)
    before = life.wellbeing
    change_meter(life, Meter.WELLBEING, WELLBEING_PER_PLAY, ends_stretch=True)
    await bot.lives.save(guild_id, life)
    wellbeing = meter_receipt("Wellbeing", before, life.wellbeing)
    coins = with_emoji(bot.emoji(MINI_COIN_EMOJI), f"+{PLAY_POINTS} WC")
    left = count(PLAYS_PER_DAY - plays - 1, "counted game")
    return f"♪ Your duel counted. {wellbeing}. {coins}. {left} left today."


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
        )
        if isinstance(verdict, str):
            receipt = _NOT_COUNTED + verdict
        else:
            life, life_id = verdict
            receipt = await _count_play(bot, guild_id, user_id, life, life_id, plays)
        best = await bot.players.record_rhyme_score(guild_id, user_id, points)
    return _Played(best, receipt)


async def _host(interaction: discord.Interaction, guild_id: int) -> None:
    """Run one duel for the member, or say why they cannot have one.

    The command and the Rhyme Duel button both come here, so both refuse the
    same way, a nap included.
    """
    bot = bot_of(interaction)
    user = interaction.user
    now = discord.utils.utcnow()
    player = await bot.players.get(guild_id, user.id)
    life = await bot.lives.current(guild_id)
    if player.is_banned(now):
        await say_privately(interaction, _BANNED)
        return
    if life is None or life.phase is not Phase.ALIVE:
        await say_privately(interaction, no_wisp_text(life, "Rhymes"))
        return
    if is_napping(life):
        until = nap_time_text(nap_ends_at(life, now))
        await say_privately(
            interaction, f"♪ Wisp is napping until {until}. Poke him awake first."
        )
        return
    thread = await _open_thread(
        bot, guild_id, interaction.guild, player.name or user.display_name
    )
    started = f"♪ Your Rhyme Duel is on in {thread.mention}."
    await say_privately(interaction, started)
    await post_in_house(
        bot, guild_id, f"♪ <@{user.id}> started a Rhyme Duel in {thread.mention}"
    )
    outcome = await _duel(bot, thread, user.id, life, random.Random())
    line = bot.lines.pick(outcome.ending, mood(life))
    await thread.send(
        summary_text(line, outcome.reason, outcome.chain, outcome.points),
        allowed_mentions=_NO_PING,
    )
    played = await _record_play(bot, guild_id, user, outcome.points)
    try:
        await thread.send(played.receipt, allowed_mentions=_NO_PING)
    except discord.HTTPException as error:
        await bot.report_error(
            interaction.guild, "sending a Rhyme Duel receipt", error, where=thread
        )
    try:
        await thread.edit(archived=True, locked=True)
    except discord.HTTPException as error:
        await bot.report_error(
            interaction.guild, "closing a Rhyme Duel thread", error, where=thread
        )
    if played.new_best:
        await refresh_vault(bot, guild_id)
    await maybe_meet(bot, guild_id, user.id, display_name=user.display_name)


# ---
# Starting a duel
# ---


async def start_duel(interaction: discord.Interaction) -> None:
    """Start a Rhyme Duel; each member can only have one going at a time.

    The answer is private. It is a new message even when a button was
    pressed, so the duel's receipt is added under it as for the command.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True, thinking=True)
    key = (guild_id, interaction.user.id)
    if key in bot.rhyme_duels:
        await say_privately(interaction, _ALREADY_DUELING)
        return
    bot.rhyme_duels.add(key)
    try:
        await _host(interaction, guild_id)
    finally:
        bot.rhyme_duels.discard(key)


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
        await press(
            interaction,
            "the Rhyme Duel button",
            start_duel,
            (*EXPECTED_FAILURES, NoHouseError),
        )


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
