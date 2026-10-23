"""Rhyme Duel: one member and Wisp trade rhymes in a thread off his House."""

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import discord

from cogs.groups import play, require_guild
from cogs.players import can_feed, maybe_meet, say_privately
from cogs.vault import refresh_vault
from db.activity import InteractionKind
from wisp.bond import casual_bond_grant
from wisp.life import Life, Phase, add_growth, mood
from wisp.lines import Moment
from wisp.rhymes import clean_word, opening_word, rhyme_kind, score, wisp_reply
from wisp.rules import (
    BOND_PER_PLAY,
    GROWTH_PER_PLAY,
    PLAYS_PER_DAY,
    RHYME_THREAD_ARCHIVE_MINUTES,
    RHYME_TURN,
)
from wisp.text import MESSAGE_LIMIT, SEPARATOR, count

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_CUT: Final = "..."

_BANNED: Final = "♪ Wisp is not dueling with you right now."
_NOT_HATCHED: Final = "♪ Wisp isn't hatched yet. Rhymes have to wait until he is."
_ALREADY_DUELING: Final = (
    "♪ You already have a Rhyme Duel going. Finish that one first."
)
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
        reply = wisp_reply(answer, set(chain), life.stage, rng)
        if reply is None:
            return _Outcome(Moment.RHYME_WISP_STUCK, None, chain, points)
        chain.append(reply)
        await thread.send(f"♪ {reply}", allowed_mentions=_NO_PING)


def summary_text(line: str, reason: str | None, chain: list[str], points: int) -> str:
    """The end of a duel: Wisp's line, why it ended, the chain and the score.

    The oldest words are left out of the chain when it would not fit one message.
    If it still does not fit, the reason is cut short, and as a last resort the
    message itself.
    """
    reasons = [f"・{reason}"] if reason else []
    score_line = f"・Score: {count(points, 'point')}"
    shown = chain
    while True:
        trimmed = "... " if len(shown) < len(chain) else ""
        chain_line = f"・{trimmed}{' ・ '.join(shown)}"
        text = "\n".join([line, SEPARATOR, *reasons, chain_line, score_line])
        overflow = len(text) - MESSAGE_LIMIT
        if overflow <= 0:
            return text
        if shown:
            shown = shown[1:]
        elif reasons and len(reasons[0]) > overflow + len(_CUT):
            reasons = [reasons[0][: -(overflow + len(_CUT))] + _CUT]
        else:
            return text[:MESSAGE_LIMIT]


# ---
# Before and after
# ---


async def _open_thread(
    bot: "WispBot", guild_id: int, guild: discord.Guild | None, name: str
) -> discord.Thread:
    """Open the duel's public thread off Wisp's House.

    Raises:
        LookupError: The House is not set, cannot be seen or is not a text
            channel.
    """
    channel_id = (await bot.settings.get(guild_id)).house_channel_id
    house = (
        guild.get_channel_or_thread(channel_id)
        if guild is not None and channel_id is not None
        else None
    )
    if not isinstance(house, discord.TextChannel):
        raise LookupError("Wisp's House is not set or is not a text channel")
    return await house.create_thread(
        name=f"Rhyme Duel ・ {name}",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=RHYME_THREAD_ARCHIVE_MINUTES,
    )


async def _record_play(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    points: int,
) -> bool:
    """Count the duel as play and keep the score if it is the player's best.

    The play, with its bond and growth, only counts when the player scored a
    rhyme, can feed Wisp, Wisp is still alive and the member has had fewer
    than PLAYS_PER_DAY counted games today. The best score is always kept.
    Returns True on a new best score.
    """
    now = discord.utils.utcnow()
    log = bot.activity_log
    user_id = member.id
    async with bot.guild_lock(guild_id):
        life = await bot.lives.current(guild_id)
        if (
            points > 0
            and life is not None
            and life.id is not None
            and life.phase is Phase.ALIVE
            and await can_feed(bot, guild_id, member)
            and await log.plays_today(guild_id, user_id, now) < PLAYS_PER_DAY
        ):
            bond = casual_bond_grant(
                await log.casual_bond_today(guild_id, user_id, now), BOND_PER_PLAY
            )
            if bond:
                await bot.players.add_bond(guild_id, user_id, bond)
            await log.record_interaction(
                guild_id, life.id, user_id, InteractionKind.PLAY, bond, 0, now
            )
            add_growth(life, GROWTH_PER_PLAY)
            await bot.lives.save(guild_id, life)
        return await bot.players.record_rhyme_score(guild_id, user_id, points)


async def _host(interaction: discord.Interaction["WispBot"], guild_id: int) -> None:
    """Run one duel for the member, or say why they cannot have one."""
    bot = interaction.client
    user = interaction.user
    player = await bot.players.get(guild_id, user.id)
    life = await bot.lives.current(guild_id)
    if player.is_banned(discord.utils.utcnow()):
        await say_privately(interaction, _BANNED)
        return
    if life is None or life.phase is not Phase.ALIVE:
        await say_privately(interaction, _NOT_HATCHED)
        return
    thread = await _open_thread(
        bot, guild_id, interaction.guild, player.name or user.display_name
    )
    await say_privately(interaction, f"♪ Your Rhyme Duel is on in {thread.mention}.")
    outcome = await _duel(bot, thread, user.id, life, random.Random())
    line = bot.lines.pick(outcome.ending, mood(life))
    await thread.send(
        summary_text(line, outcome.reason, outcome.chain, outcome.points),
        allowed_mentions=_NO_PING,
    )
    new_best = await _record_play(bot, guild_id, user, outcome.points)
    try:
        await thread.edit(archived=True, locked=True)
    except discord.HTTPException as error:
        await bot.report_error(interaction.guild, "closing a Rhyme Duel thread", error)
    if new_best:
        await refresh_vault(bot, guild_id)
    await maybe_meet(bot, guild_id, user.id, display_name=user.display_name)


# ---
# Command
# ---


@play.command(name="rhyme", description="Trade rhymes with Wisp in a Rhyme Duel.")
async def play_rhyme(interaction: discord.Interaction["WispBot"]) -> None:
    """Start a Rhyme Duel; each member can only have one going at a time."""
    bot = interaction.client
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    key = (guild_id, interaction.user.id)
    if key in bot.rhyme_duels:
        await say_privately(interaction, _ALREADY_DUELING)
        return
    bot.rhyme_duels.add(key)
    try:
        await _host(interaction, guild_id)
    finally:
        bot.rhyme_duels.discard(key)


async def setup(bot: "WispBot") -> None:
    """Load the Rhyme Duel extension; its command joins the shared groups on import."""
