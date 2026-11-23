"""Wisp's Craving: a once-a-day snack guess in the member's room.

A round starts from /wisp play craving, or from the Wisp's Craving button in
the private games menu. Wisp craves one snack; the member picks guesses from
a menu in their room. The round is stored as soon as it starts, so a restart
picks it up where it was and starting again never rerolls the snack.
"""

import random
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.games import ROOM_BUSY, check_game, craving_live, enter_room, reward_game
from cogs.groups import play, require_guild
from cogs.players import (
    EXPECTED_FAILURES,
    FROZEN_REASON,
    NOT_ALIVE_REASON,
    blocker_reason,
    bot_of,
    is_frozen,
    member_blocker,
    press,
    report_failure,
    say_privately,
)
from cogs.rooms import RoomError, open_room
from cogs.snacks import show_pack_in_room
from db.activity import InteractionKind
from db.cravings import Round
from wisp.craving import (
    Verdict,
    guesses_left,
    hint_for,
    is_idle,
    judge,
    pick_craving,
    snacks_left,
)
from wisp.life import Life, Mood, Phase, mood
from wisp.lines import Moment
from wisp.rules import CRAVING_TIMEOUT, SNACK_BY_KEY, Snack
from wisp.text import daily_reset

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_CRAVING_ID: Final = "wisp:play:craving"
_GUESS_TEMPLATE: Final = re.compile(
    r"wisp:craving:(?P<user>[0-9]+):(?P<day>[0-9]{4}-[0-9]{2}-[0-9]{2})"
)
_MENU_CONTEXT: Final = "the Craving menu"

_BANNED: Final = "♪ Wisp is not playing with you right now."
_SOMEONE_ELSES: Final = "♪ This is someone else's Craving."
_OVER: Final = "♪ This Craving is over."
_STILL_ON: Final = "♪ Your Craving is still on."
_NOT_COUNTED: Final = "♪ This Craving didn't count toward his Wellbeing: "
_BOND_FULL: Final = "your bond with him is full for today"

# ---
# Posting a round
# ---


def _round_text(line: str, round_: Round) -> str:
    """Wisp's `line`, then the hint for the guesses so far and the guesses left."""
    return "\n".join(
        [
            line,
            f"・Hint: {hint_for(round_.snack, len(round_.guesses))}",
            f"・Guesses left: {guesses_left(round_.guesses)}",
        ]
    )


def _menu(bot: "WispBot", round_: Round) -> discord.ui.View:
    """The menu of the snacks the member has not guessed yet."""
    options = [
        discord.SelectOption(
            label=snack.name,
            value=snack.key,
            emoji=bot.emojis_by_name.get(snack.emoji_name),
        )
        for snack in snacks_left(round_.guesses)
    ]
    view = discord.ui.View(timeout=None)
    view.add_item(GuessMenu(round_.user_id, round_.day, options))
    return view


async def _post_round(
    bot: "WispBot", room: discord.Thread, round_: Round, line: str
) -> None:
    await room.send(
        _round_text(line, round_), view=_menu(bot, round_), allowed_mentions=_NO_PING
    )


# ---
# Ending a round
# ---


class Ending(Enum):
    """How a round ended."""

    WON = "won"
    LOST = "lost"
    TIMED_OUT = "timed out"


_ENDING_MOMENTS: Final = {
    Ending.WON: Moment.CRAVING_WON,
    Ending.LOST: Moment.CRAVING_LOST,
    Ending.TIMED_OUT: Moment.CRAVING_TIMED_OUT,
}


@dataclass(frozen=True)
class _Ended:
    """A round that just ended: how, the receipt and how Wisp felt."""

    round: Round
    ending: Ending
    receipt: str
    feeling: Mood


def _feeling(life: Life | None) -> Mood:
    """How Wisp feels in a Craving line; happy when there is no life to ask."""
    return Mood.HAPPY if life is None else mood(life)


def _note(snack: Snack, ending: Ending) -> str:
    craved = f"I was craving {snack.article} {snack.name}"
    if ending is Ending.WON:
        return f"{craved} and they guessed it"
    return f"{craved} and they couldn't guess it"


async def _end(
    bot: "WispBot", round_: Round, ending: Ending, now: datetime
) -> _Ended | None:
    """End an open round, give what it earned and note it; None if it had ended.

    A win puts the snack in the member's Snack Pack, marked as won. Win or
    lose, the round counts like a game while Wisp is alive and not frozen.
    Call this under `bot.guild_lock`.
    """
    guild_id, user_id = round_.guild_id, round_.user_id
    won = ending is Ending.WON
    idle_before = now - CRAVING_TIMEOUT if ending is Ending.TIMED_OUT else None
    if not await bot.cravings.end(
        guild_id, user_id, round_.day, won=won, now=now, idle_before=idle_before
    ):
        return None
    snack = SNACK_BY_KEY[round_.snack]
    if won:
        await bot.activity_log.add_snack(guild_id, user_id, snack.key, won=True)
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or life.phase is not Phase.ALIVE:
        receipt = _NOT_COUNTED + NOT_ALIVE_REASON
    elif await is_frozen(bot, guild_id):
        receipt = _NOT_COUNTED + FROZEN_REASON
    else:
        reward = await reward_game(
            bot, guild_id, user_id, life, life.id, InteractionKind.CRAVING, now
        )
        bond = f"bond +{reward.bond}" if reward.bond else _BOND_FULL
        receipt = (
            f"♪ Your Craving counted ・ {reward.wellbeing} ・ {bond} ・ {reward.coins}"
        )
    await bot.notes.add(guild_id, user_id, _note(snack, ending), now)
    return _Ended(round_, ending, receipt, _feeling(life))


async def _announce(
    bot: "WispBot",
    room: discord.Thread,
    member: discord.abc.User,
    ended: _Ended,
) -> None:
    """Say in the room how the round ended and what it gave.

    After a win the member's Snack Pack in the room is posted again.
    """
    snack = SNACK_BY_KEY[ended.round.snack]
    fields = {"snack": snack.name}
    if ended.ending is Ending.WON:
        player = await bot.players.get(ended.round.guild_id, member.id)
        fields["name"] = player.name or member.display_name
    line = bot.lines.pick(_ENDING_MOMENTS[ended.ending], ended.feeling, **fields)
    await room.send(f"{line}\n{ended.receipt}", allowed_mentions=_NO_PING)
    if ended.ending is Ending.WON:
        await show_pack_in_room(bot, room.guild, member, where=room)


async def end_idle_cravings(bot: "WispBot", now: datetime) -> None:
    """End every open round left without a guess for CRAVING_TIMEOUT as a loss.

    Wisp says so in each member's room. A member who left the server has
    their round ended without a post. A Discord failure is reported in that
    round's server and never stops the others.

    Raises:
        pymysql.err.Error: The database failed.
    """
    for round_ in await bot.cravings.idle_since(now - CRAVING_TIMEOUT):
        async with bot.guild_lock(round_.guild_id):
            ended = await _end(bot, round_, Ending.TIMED_OUT, now)
        guild = bot.get_guild(round_.guild_id)
        if ended is None or guild is None:
            continue
        member = guild.get_member(round_.user_id)
        try:
            if member is None:
                member = await guild.fetch_member(round_.user_id)
        except discord.NotFound:
            continue
        except discord.HTTPException as error:
            await bot.report_error(guild, "ending an idle Craving", error)
            continue
        try:
            room = await open_room(bot, guild, member)
            await _announce(bot, room, member, ended)
        except (RoomError, discord.HTTPException) as error:
            await bot.report_error(guild, "ending an idle Craving", error)


# ---
# Starting a round
# ---


async def _open_round(
    interaction: discord.Interaction, round_: Round | None, line: str
) -> None:
    """Post today's round in the member's room under Wisp's `line`.

    A new round is started; an open one is posted again with its current
    hint and menu.
    """
    bot = bot_of(interaction)
    user = interaction.user
    room = await enter_room(interaction)
    if room is None:
        return
    now = discord.utils.utcnow()
    if round_ is None:
        snack = pick_craving(random.Random())
        round_ = await bot.cravings.start(room.guild.id, user.id, snack.key, now)
    await _post_round(bot, room, round_, line)
    await say_privately(interaction, f"♪ Your Craving is on in {room.mention}.")


async def _host(interaction: discord.Interaction, guild_id: int) -> None:
    """Start or pick up the member's round for today, or say why they can't.

    A round left idle past CRAVING_TIMEOUT is ended as a loss first. The room
    is held while the round is posted, so two starts at once post it once,
    and a round from before midnight that is still live keeps it busy.
    """
    bot = bot_of(interaction)
    user = interaction.user
    now = discord.utils.utcnow()
    player = await bot.players.get(guild_id, user.id)
    life = await check_game(
        bot, guild_id, player, now, banned=_BANNED, things="Cravings"
    )
    if isinstance(life, str):
        await say_privately(interaction, life)
        return
    blocker = await member_blocker(bot, guild_id, user, now)
    if blocker is not None:
        reason = await blocker_reason(bot, guild_id, blocker)
        await say_privately(interaction, f"♪ You can't play Wisp's Craving: {reason}")
        return
    round_ = await bot.cravings.today(guild_id, user.id, now)
    if round_ is not None and round_.ended_at is None and is_idle(round_.last_at, now):
        room = await enter_room(interaction)
        if room is None:
            return
        async with bot.guild_lock(guild_id):
            ended = await _end(bot, round_, Ending.TIMED_OUT, now)
        if ended is not None:
            await _announce(bot, room, user, ended)
        round_ = await bot.cravings.today(guild_id, user.id, now)
    if round_ is not None and round_.ended_at is not None:
        await say_privately(
            interaction,
            f"♪ You've already had today's Craving. Next one {daily_reset(now)}.",
        )
        return
    key = (guild_id, user.id)
    if key in bot.room_games:
        await say_privately(interaction, ROOM_BUSY)
        return
    bot.room_games.add(key)
    try:
        if round_ is None and await craving_live(bot, guild_id, user.id, now):
            await say_privately(interaction, ROOM_BUSY)
            return
        line = (
            _STILL_ON
            if round_ is not None
            else bot.lines.pick(
                Moment.CRAVING_START, mood(life), name=player.name or user.display_name
            )
        )
        await _open_round(interaction, round_, line)
    finally:
        bot.room_games.discard(key)


async def start_craving(interaction: discord.Interaction) -> None:
    """Start Wisp's Craving; the answer is private and the game is in the room."""
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True, thinking=True)
    await _host(interaction, guild_id)


@play.command(name="craving", description="Guess the snack Wisp is craving.")
async def play_craving(interaction: discord.Interaction["WispBot"]) -> None:
    """Start Wisp's Craving for the member."""
    await start_craving(interaction)


class CravingButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_CRAVING_ID),
):
    """The Wisp's Craving button in the games menu; it starts one like the command.

    Its custom id is fixed, so the button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Wisp's Craving",
                style=discord.ButtonStyle.primary,
                custom_id=_CRAVING_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "CravingButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Start Wisp's Craving for whoever pressed it."""
        await press(interaction, "the Wisp's Craving button", start_craving)


# ---
# Guessing
# ---


async def _guess(
    interaction: discord.Interaction, user_id: int, day: date, guess: str
) -> None:
    """Judge one pick from the menu and answer it in the room.

    The round is read again under the guild lock, so it works after a restart
    and two quick picks are judged one after the other. The menu that was
    picked from is taken away; a wrong guess posts a new one without it, and
    a pick from an old menu posts the round again. A pick on a round that
    went idle ends it as a loss.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    await interaction.response.defer()
    await interaction.edit_original_response(view=None)
    room = await enter_room(interaction)
    if room is None:
        return
    now = discord.utils.utcnow()
    ended: _Ended | None = None
    line: str | None = None
    async with bot.guild_lock(guild_id):
        round_ = await bot.cravings.get(guild_id, user_id, day)
        if round_ is None or round_.ended_at is not None:
            round_ = None
        elif is_idle(round_.last_at, now):
            ended = await _end(bot, round_, Ending.TIMED_OUT, now)
        elif guess in round_.guesses or guess not in SNACK_BY_KEY:
            line = _STILL_ON
        else:
            verdict = judge(round_.snack, round_.guesses, guess)
            if verdict is Verdict.RIGHT:
                ended = await _end(bot, round_, Ending.WON, now)
            else:
                round_ = await bot.cravings.add_guess(
                    guild_id, user_id, day, guess, now
                )
                if verdict is Verdict.OUT:
                    ended = await _end(bot, round_, Ending.LOST, now)
                else:
                    line = bot.lines.pick(
                        Moment.CRAVING_NOPE,
                        _feeling(await bot.lives.current(guild_id)),
                        snack=SNACK_BY_KEY[guess].name,
                    )
    if ended is not None:
        await _announce(bot, room, interaction.user, ended)
    elif round_ is None:
        await say_privately(interaction, _OVER)
    elif line is not None:
        await _post_round(bot, room, round_, line)


class GuessMenu(
    discord.ui.DynamicItem[discord.ui.Select[Any]],
    template=_GUESS_TEMPLATE,
):
    """The menu of snacks in a Craving round, which only its member may pick from.

    The member's id and the round's UTC day are in its custom id, so it keeps
    working after the bot restarts and across midnight.
    """

    def __init__(
        self,
        user_id: int,
        day: date,
        options: list[discord.SelectOption] | None = None,
    ) -> None:
        super().__init__(
            discord.ui.Select(
                custom_id=f"wisp:craving:{user_id}:{day.isoformat()}",
                placeholder="Guess the snack",
                options=options or [],
            )
        )
        self.user_id = user_id
        self.day = day

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
        /,
    ) -> "GuessMenu":
        """Rebuild the menu a pick reached."""
        return cls(int(match["user"]), date.fromisoformat(match["day"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Turn away anyone but the round's member, privately."""
        if interaction.user.id == self.user_id:
            return True
        try:
            await interaction.response.send_message(_SOMEONE_ELSES, ephemeral=True)
        except EXPECTED_FAILURES as error:
            await report_failure(interaction, _MENU_CONTEXT, error)
        return False

    async def callback(self, interaction: discord.Interaction) -> None:
        """Judge the member's pick."""
        guess = self.item.values[0]

        async def judged(pressed: discord.Interaction) -> None:
            await _guess(pressed, self.user_id, self.day, guess)

        await press(interaction, _MENU_CONTEXT, judged)


async def setup(bot: "WispBot") -> None:
    """Register the Craving button and menu so they work after a restart.

    The command joins the shared groups on import.
    """
    bot.add_dynamic_items(CravingButton, GuessMenu)
