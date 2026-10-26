"""Players: /wisp status and Wisp learning members' names."""

import contextlib
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, cast

import discord
import pymysql

from cogs.announce import say_in_house
from cogs.channels import where_of
from cogs.groups import require_guild, wisp
from db.activity import InteractionKind
from db.players import Player
from wisp.bond import happiness, should_meet
from wisp.card import CardFacts, render_status
from wisp.life import Life, Phase, add_growth, is_over
from wisp.lines import Moment
from wisp.rules import CHAT_POINTS, GROWTH_PER_BOND_MOMENT, HAPPINESS_WINDOW, NAME_MAX
from wisp.text import USER_ERROR, count

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
EXPECTED_FAILURES: Final = (pymysql.err.Error, discord.DiscordException)
NOT_TAKING: Final = "♪ Wisp is not taking snacks or gifts from you right now."
CANNOT_FEED: Final = (
    "♪ Only members at Active Lounger or higher who have opened /wisp board "
    "can feed Wisp."
)

# ---
# Status card text
# ---


async def status_text(
    bot: "WispBot", guild_id: int, life: Life, now: datetime, happy: int
) -> str:
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
        happiness=happy,
        fed_today=await bot.activity_log.feeders_since(guild_id, today),
        viibr_tracks=viibr,
        suno_tracks=suno,
        wisp_id=wisp_user.id,
        house_id=settings.house_channel_id,
    )
    return render_status(life, now, facts)


# ---
# Happy and chat credit
# ---


async def current_happiness(bot: "WispBot", guild_id: int, now: datetime) -> int:
    """How happy Wisp is: how many members chatted with him in the last day."""
    return happiness(
        await bot.activity_log.chatters_since(guild_id, now - HAPPINESS_WINDOW)
    )


async def credit_chat(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    life: Life,
    now: datetime,
) -> bool:
    """Give a member the day's chat credit for poking or mentioning Wisp.

    The first poke or mention of the UTC day records a CHAT interaction, which
    makes Wisp happy but earns no bond or growth, and gives CHAT_POINTS. Only a
    member who is not banned and can feed Wisp earns it. Returns whether it was
    given.
    """
    if life.id is None:
        return False
    player = await bot.players.get(guild_id, member.id)
    if player.is_banned(now) or not await can_feed(bot, guild_id, member):
        return False
    if await bot.activity_log.chatted_today(guild_id, member.id, now):
        return False
    await bot.activity_log.record_interaction(
        guild_id, life.id, member.id, InteractionKind.CHAT, 0, 0, now
    )
    await bot.players.add_points(guild_id, member.id, CHAT_POINTS)
    return True


# ---
# Who feeds Wisp
# ---


async def can_feed(
    bot: "WispBot", guild_id: int, member: discord.User | discord.Member
) -> bool:
    """Whether a member may feed Wisp and count as playing with him.

    They need a qualifying role and must have opened /wisp board once. Bans are
    checked separately, since they get their own reply.
    """
    if not isinstance(member, discord.Member):
        return False
    qualifying = await bot.settings.roles(guild_id)
    if qualifying.isdisjoint(role.id for role in member.roles):
        return False
    return (await bot.players.get(guild_id, member.id)).activated_at is not None


class Refusal(Exception):
    """A reason the member cannot do something with Wisp right now, worded for them."""


async def check_member(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    now: datetime,
) -> Player:
    """Return the member's player when they may feed Wisp and give him gifts.

    Raises:
        Refusal: The member is banned or cannot feed Wisp.
    """
    player = await bot.players.get(guild_id, member.id)
    if player.is_banned(now):
        raise Refusal(NOT_TAKING)
    if not await can_feed(bot, guild_id, member):
        raise Refusal(CANNOT_FEED)
    return player


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
    name. Until they do, he uses their name from the server (`display_name`, or
    a mention when the caller has none). An egg does not talk, so a member is
    only met once Wisp has hatched.
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
        view=view,
    )


# ---
# Commands
# ---


@wisp.command(name="status", description="See how Wisp is doing.")
async def wisp_status(interaction: discord.Interaction["WispBot"]) -> None:
    """Show Wisp's status card, only to the member who asked."""
    bot = interaction.client
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    now = discord.utils.utcnow()
    life = await bot.lives.current(guild_id)
    if life is None or is_over(life):
        text = "♪ Wisp has no life to show right now. A new egg will be laid soon."
    else:
        happy = await current_happiness(bot, guild_id, now)
        text = await status_text(bot, guild_id, life, now, happy)
    await say_privately(interaction, text)


async def setup(bot: "WispBot") -> None:
    """Register the name button so it still works after a restart."""
    bot.add_dynamic_items(NameButton)
