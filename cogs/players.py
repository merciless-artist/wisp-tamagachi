"""Players: the status card text, chat credit and Wisp learning members' names."""

import contextlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Final, cast

import discord
import pymysql

from cogs.announce import say_in_house
from cogs.channels import where_of
from cogs.groups import require_guild
from db.activity import InteractionKind
from db.players import Player
from wisp.bond import should_meet
from wisp.card import CardFacts, render_status
from wisp.life import Life, Meter, Phase, add_growth, change_meter
from wisp.lines import Moment
from wisp.rules import (
    CHAT_CREDITS_PER_DAY,
    CHAT_POINTS,
    FEEDING_ROLES_SHOWN,
    GROWTH_PER_BOND_MOMENT,
    NAME_MAX,
    POKE_CREDITS_PER_DAY,
    WELLBEING_PER_CHAT,
    WELLBEING_PER_POKE,
)
from wisp.text import USER_ERROR, any_role, count, with_emoji
from wisp.voice import MINI_COIN_EMOJI

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
EXPECTED_FAILURES: Final = (pymysql.err.Error, discord.DiscordException)
NOT_TAKING: Final = "♪ Wisp is not taking snacks or gifts from you right now."

# ---
# Status card text
# ---


async def status_text(bot: "WispBot", guild_id: int, life: Life, now: datetime) -> str:
    """Render the status card for a life that is not over.

    Fed today counts the members who fed Wisp or gave him a snack since UTC
    midnight; the tracks are those fed on the same UTC day.

    Raises:
        RuntimeError: Wisp is not logged in, so the card cannot mention him.
    """
    wisp_user = bot.user
    if wisp_user is None:
        raise RuntimeError("Wisp is not logged in, so his card cannot mention him.")
    today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    viibr, suno = await bot.activity_log.tracks_today(guild_id, now)
    settings = await bot.settings.get(guild_id)
    facts = CardFacts(
        fed_today=await bot.activity_log.feeders_since(guild_id, today),
        viibr_tracks=viibr,
        suno_tracks=suno,
        wisp_id=wisp_user.id,
        house_id=settings.house_channel_id,
        tracks_id=settings.tracks_channel_id,
    )
    return render_status(life, now, facts, bot.emoji)


# ---
# Chat credit
# ---


@dataclass(frozen=True)
class Credit:
    """What a chat or poke credit did.

    `reason` says why nothing was credited, as the end of a sentence. When
    credited, `before` and `after` are the meter's value around the credit and
    `left` is how many more of that kind the member can still have today.
    """

    credited: bool
    reason: str | None = None
    before: float = 0.0
    after: float = 0.0
    left: int = 0


async def credit_chat(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    now: datetime,
) -> Credit:
    """Credit a member's mention of Wisp: Wellbeing for the first few of the day.

    See `_credit`.
    """
    return await _credit(
        bot,
        guild_id,
        member,
        InteractionKind.CHAT,
        WELLBEING_PER_CHAT,
        CHAT_CREDITS_PER_DAY,
        "mention",
        now,
    )


async def credit_poke(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    now: datetime,
) -> Credit:
    """Credit a member's poke of Wisp: Wellbeing for the first few of the day.

    See `_credit`.
    """
    return await _credit(
        bot,
        guild_id,
        member,
        InteractionKind.POKE,
        WELLBEING_PER_POKE,
        POKE_CREDITS_PER_DAY,
        "poke",
        now,
    )


async def _credit(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    kind: InteractionKind,
    amount: float,
    per_day: int,
    noun: str,
    now: datetime,
) -> Credit:
    """Record one credited chat or poke, fill Wellbeing and pay the day's point.

    A credit records an interaction of `kind`, which earns no bond or growth,
    moves Wellbeing by `amount` and restarts its stretch. It is given only
    while Wisp has a life and is not frozen, to a member who is not banned and
    can feed him,
    and only until the member has had `per_day` of that kind on the UTC day of
    `now`. The first credit of the day, of either kind, also pays CHAT_POINTS.
    A refusal names its reason.
    """
    async with bot.guild_lock(guild_id):
        life = await bot.lives.current(guild_id)
        if life is None or life.id is None:
            return Credit(False, NOT_ALIVE_REASON)
        if await is_frozen(bot, guild_id):
            return Credit(False, FROZEN_REASON)
        blocker = await member_blocker(bot, guild_id, member, now)
        if blocker is not None:
            return Credit(False, await blocker_reason(bot, guild_id, blocker))
        log = bot.activity_log
        chats = await log.chats_today(guild_id, member.id, now)
        pokes = await log.pokes_today(guild_id, member.id, now)
        had = chats if kind is InteractionKind.CHAT else pokes
        if had >= per_day:
            return Credit(False, f"you've used your {count(per_day, noun)} for today.")
        await log.record_interaction(guild_id, life.id, member.id, kind, 0, 0, now)
        before = life.wellbeing
        change_meter(life, Meter.WELLBEING, amount, ends_stretch=True)
        await bot.lives.save(guild_id, life)
        if chats + pokes == 0:
            await bot.players.add_points(guild_id, member.id, CHAT_POINTS)
    return Credit(True, None, before, life.wellbeing, per_day - had - 1)


# ---
# Who feeds Wisp
# ---


class Blocker(Enum):
    """Why a member may not feed Wisp."""

    BANNED = "banned"
    NO_ROLE = "no role"
    NOT_OPENED = "not opened"


BLOCKER_REASONS: Final = {
    Blocker.BANNED: "you are banned from feeding Wisp right now.",
    Blocker.NO_ROLE: "you don't have a role that can feed Wisp.",
    Blocker.NOT_OPENED: "you haven't opened /wisp board yet.",
}
"""Why not, as the end of a sentence; see `blocker_reason` for the roles."""
NOT_ALIVE_REASON: Final = "Wisp isn't alive right now."
FROZEN_REASON: Final = (
    "Wisp is frozen right now, so nothing can change until staff unfreeze him."
)


async def _missing_requirement(
    bot: "WispBot", guild_id: int, member: discord.Member
) -> Blocker | None:
    """NO_ROLE or NOT_OPENED when the member lacks a feeding requirement."""
    qualifying = await bot.settings.roles(guild_id)
    if qualifying.isdisjoint(role.id for role in member.roles):
        return Blocker.NO_ROLE
    if (await bot.players.get(guild_id, member.id)).activated_at is None:
        return Blocker.NOT_OPENED
    return None


async def feeder_blocker(
    bot: "WispBot", guild_id: int, member: discord.Member, now: datetime
) -> Blocker | None:
    """The first reason the member may not feed Wisp, or None when they may.

    A ban comes first, then a missing role, then /wisp board not opened.
    """
    if (await bot.players.get(guild_id, member.id)).is_banned(now):
        return Blocker.BANNED
    return await _missing_requirement(bot, guild_id, member)


async def member_blocker(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    now: datetime,
) -> Blocker | None:
    """`feeder_blocker` for anyone: a user who is not a server member has no role."""
    if not isinstance(member, discord.Member):
        return Blocker.NO_ROLE
    return await feeder_blocker(bot, guild_id, member, now)


async def blocker_reason(bot: "WispBot", guild_id: int, blocker: Blocker) -> str:
    """Why the member may not feed Wisp, as the end of a sentence.

    A missing role names the server's feeding roles as mentions, which ping
    nobody since every send turns pings off; with none set it says "a role
    that can feed Wisp".
    """
    if blocker is not Blocker.NO_ROLE:
        return BLOCKER_REASONS[blocker]
    roles = await bot.settings.roles(guild_id)
    if not roles:
        return BLOCKER_REASONS[blocker]
    named = any_role(roles, FEEDING_ROLES_SHOWN)
    return f"you don't have a role that can feed Wisp: {named}."


async def is_frozen(bot: "WispBot", guild_id: int) -> bool:
    """Whether staff have frozen Wisp's time in this guild."""
    return (await bot.settings.get(guild_id)).frozen


async def chore_refusal_text(bot: "WispBot", guild_id: int, blocker: Blocker) -> str:
    """What a member who may not feed Wisp is told when they try to do a chore."""
    return (
        f"♪ You can't take care of Wisp: {await blocker_reason(bot, guild_id, blocker)}"
    )


async def refusal_text(bot: "WispBot", guild_id: int, blocker: Blocker) -> str:
    """What a member who may not feed Wisp is told when they try to give him things."""
    if blocker is Blocker.BANNED:
        return NOT_TAKING
    reason = await blocker_reason(bot, guild_id, blocker)
    return f"♪ Wisp can't take that from you: {reason}"


def no_wisp_text(life: Life | None, things: str) -> str:
    """Why `things` cannot happen: Wisp has not hatched, or is not alive.

    `things` is capitalised and plural, such as "Snacks".
    """
    if life is not None and life.phase in (Phase.EGG, Phase.HATCHING):
        return f"♪ Wisp isn't hatched yet. {things} have to wait until he is."
    return f"♪ Wisp isn't alive right now, so {things.lower()} have to wait."


def too_poor_text(bot: "WispBot", line: str, cost: int, balance: int) -> str:
    """Wisp's not-enough-points `line` with what the thing costs and the balance."""
    price = with_emoji(bot.emoji(MINI_COIN_EMOJI), f"{cost} WC")
    return f"{line}\n♪ That costs {price} and you have {balance}."


class Refusal(Exception):
    """A reason the member cannot do something with Wisp right now, worded for them."""


async def require_unfrozen(bot: "WispBot", guild_id: int) -> None:
    """Stop an action while Wisp is frozen.

    Raises:
        Refusal: Staff have frozen Wisp, with the reason.
    """
    if await is_frozen(bot, guild_id):
        raise Refusal(f"♪ {FROZEN_REASON}")


async def check_member(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    now: datetime,
) -> Player:
    """Return the member's player when they may feed Wisp and give him gifts.

    Raises:
        Refusal: The member is banned or cannot feed Wisp, with the reason.
    """
    blocker = await member_blocker(bot, guild_id, member, now)
    if blocker is not None:
        raise Refusal(await refusal_text(bot, guild_id, blocker))
    return await bot.players.get(guild_id, member.id)


# ---
# Interaction helpers
# ---


def bot_of(interaction: discord.Interaction) -> "WispBot":
    """Return the running bot an interaction came from."""
    return cast("WispBot", interaction.client)


async def say_privately(
    interaction: discord.Interaction,
    text: str,
    *,
    view: discord.ui.View | None = None,
) -> None:
    """Answer a deferred interaction with a private message, with buttons if given."""
    extras: dict[str, Any] = {} if view is None else {"view": view}
    await interaction.followup.send(
        text, ephemeral=True, allowed_mentions=_NO_PING, **extras
    )


async def report_failure(
    interaction: discord.Interaction, context: str, error: BaseException
) -> None:
    """Post a failure where it happened and tell the member it is posted there.

    Persistent buttons have no error hook of their own, so they catch
    `EXPECTED_FAILURES` and call this.
    """
    await bot_of(interaction).report_error(
        interaction.guild, context, error, where=where_of(interaction)
    )
    with contextlib.suppress(discord.DiscordException):
        if interaction.response.is_done():
            await interaction.followup.send(USER_ERROR, ephemeral=True)
        else:
            await interaction.response.send_message(USER_ERROR, ephemeral=True)


async def press(
    interaction: discord.Interaction,
    context: str,
    action: Callable[[discord.Interaction], Awaitable[None]],
    failures: tuple[type[BaseException], ...] = EXPECTED_FAILURES,
) -> None:
    """Run what a persistent button does, reporting a failure as `context`.

    Persistent buttons have no error hook of their own, so the `failures` they
    can expect are caught here.
    """
    try:
        await action(interaction)
    except failures as error:
        await report_failure(interaction, context, error)


# ---
# Naming
# ---


async def _name_refusal(interaction: discord.Interaction) -> str | None:
    """Why the member may not choose a name right now, or None if they may.

    A member who already has a name cannot change it; staff clear it to let
    them choose again. Banned members cannot name themselves either.
    """
    player = await bot_of(interaction).players.get(
        require_guild(interaction), interaction.user.id
    )
    if player.is_banned(discord.utils.utcnow()):
        return "♪ Wisp is not taking names from you right now."
    if player.name is not None:
        return (
            "♪ Wisp already knows your name. Staff can reset it if it needs to change."
        )
    return None


class NameModal(discord.ui.Modal, title="Tell Wisp your name"):
    """The form where a member tells Wisp what to call them."""

    name = discord.ui.TextInput["NameModal"](
        label="What should Wisp call you?", max_length=NAME_MAX
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Save the trimmed name, or say why it cannot be used."""
        name = self.name.value.strip()
        if (refusal := await _name_refusal(interaction)) is not None:
            reply = refusal
        elif not name:
            reply = "♪ Wisp needs something to call you. Press the button to try again."
        elif len(name) > NAME_MAX:
            reply = f"♪ Wisp only remembers names up to {count(NAME_MAX, 'character')}."
        else:
            await bot_of(interaction).players.set_name(
                require_guild(interaction), interaction.user.id, name
            )
            reply = f"♪ Wisp will call you {name} from now on."
        await interaction.response.send_message(
            reply, ephemeral=True, allowed_mentions=_NO_PING
        )

    async def on_error(  # type: ignore[override]
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        """Report a failure and tell the member."""
        await report_failure(interaction, "the naming form", error)


class NameButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(r"wisp:name:(?P<user_id>[0-9]+)"),
):
    """The Tell Wisp your name button, which only its member can press.

    The member's id is in the button's custom id, so the button keeps working
    after the bot restarts.
    """

    def __init__(self, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Tell Wisp your name",
                style=discord.ButtonStyle.primary,
                custom_id=f"wisp:name:{user_id}",
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "NameButton":
        """Rebuild the button from the member id in its custom id."""
        return cls(int(match["user_id"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Turn away anyone but its member, and a member who may not name themselves.

        A failure is reported and also turns the member away.
        """
        try:
            reply: str | None
            if interaction.user.id != self.user_id:
                reply = "♪ That button is for someone else."
            else:
                reply = await _name_refusal(interaction)
            if reply is None:
                return True
            await interaction.response.send_message(reply, ephemeral=True)
        except EXPECTED_FAILURES as error:
            await report_failure(interaction, "the name button", error)
        return False

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open the name form; a failure is reported."""
        try:
            await interaction.response.send_modal(NameModal())
        except EXPECTED_FAILURES as error:
            await report_failure(interaction, "the name button", error)


# ---
# Meeting Wisp
# ---


async def maybe_meet(
    bot: "WispBot", guild_id: int, user_id: int, *, display_name: str | None = None
) -> None:
    """Let Wisp meet a member who has now spent enough different days with him.

    Call this after every interaction. Once, the member is marked as met, Wisp
    grows a little and says hello in his House with a button to tell him their
    name. The hello tags and pings that member, so it is not lost in a busy
    chat. Until they answer, he uses their name from the server
    (`display_name`, or a mention when the caller has none). An egg does not
    talk, so a member is only met once Wisp has hatched.
    """
    if (await bot.players.get(guild_id, user_id)).met_at is not None:
        return
    async with bot.guild_lock(guild_id):
        life = await bot.lives.current(guild_id)
        player = await bot.players.get(guild_id, user_id)
        days = await bot.activity_log.distinct_days(guild_id, user_id)
        if (
            life is None
            or life.phase is not Phase.ALIVE
            or not should_meet(days, met=player.met_at is not None)
        ):
            return
        await bot.players.mark_met(guild_id, user_id, discord.utils.utcnow())
        add_growth(life, GROWTH_PER_BOND_MOMENT)
        await bot.lives.save(guild_id, life)
    view = discord.ui.View(timeout=None)
    view.add_item(NameButton(user_id))
    await say_in_house(
        bot,
        guild_id,
        Moment.MEET,
        life,
        name=player.name or display_name or f"<@{user_id}>",
        prefix=f"<@{user_id}> ",
        view=view,
        ping=user_id,
    )


async def setup(bot: "WispBot") -> None:
    """Register the name button so it still works after a restart."""
    bot.add_dynamic_items(NameButton)
