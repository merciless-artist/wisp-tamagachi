"""Players: /wisp status and board, the Billboard and Wisp learning members' names."""

import contextlib
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, cast

import discord

from cogs.announce import say_in_house, show_in_thread
from cogs.groups import require_guild, wisp
from wisp.bond import happiness, should_meet, tier_for
from wisp.card import render_status
from wisp.life import Life, Phase, add_growth, age_days, is_over
from wisp.lines import Moment
from wisp.rules import GROWTH_PER_BOND_MOMENT, HAPPINESS_WINDOW, NAME_MAX
from wisp.text import MESSAGE_LIMIT, SEPARATOR, USER_ERROR, count

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_TOP: Final = 10

# ---
# Billboard
# ---


def _version_line(life: Life, now: datetime) -> str:
    prefix = f"v{life.version} ・ "
    match life.phase:
        case Phase.EGG:
            return prefix + "still an egg"
        case Phase.HATCHING:
            return prefix + "hatching now"
        case Phase.ALIVE:
            return prefix + f"going strong ・ {count(age_days(life, now), 'day')}"
    if life.hatched_at is None:
        return prefix + "never hatched"
    facts = [
        f"lived {count(age_days(life, life.ended_at or now), 'day')}",
        f"reached {life.peak_stage.value.capitalize()}",
    ]
    if life.hatched_by is not None:
        facts.append(f"hatched by <@{life.hatched_by}>")
    return prefix + " ・ ".join(facts)


def _fit(head: list[str], history: list[str]) -> str:
    """Join the head and as many whole history lines as fit in one message."""
    lines = head
    for line in history:
        if len("\n".join([*lines, line])) > MESSAGE_LIMIT:
            break
        lines = [*lines, line]
    return "\n".join(lines)


async def render_billboard(bot: "WispBot", guild_id: int, now: datetime) -> str:
    """Build the Billboard: two top tens, then every version, newest first.

    The history is trimmed from the oldest end so the text fits one message.
    """
    history = await bot.lives.history(guild_id)
    current_id = history[0].id if history else None
    this_life = (
        await bot.activity_log.top_this_life(guild_id, current_id, _TOP)
        if current_id is not None
        else []
    )
    all_time = await bot.players.top_lifetime(guild_id, _TOP)
    this_life_lines = [
        f"・{place}. <@{user_id}> ・ {count(points, 'point')}"
        for place, (user_id, points) in enumerate(this_life, start=1)
    ] or ["・Nobody has fed him yet"]
    all_time_lines = [
        f"・{place}. <@{player.user_id}> ・ {count(player.lifetime_points, 'point')}"
        f" ・ {tier_for(player.bond)}"
        for place, player in enumerate(all_time, start=1)
    ] or ["・Nobody has points yet"]
    head = [
        "♪ The Billboard",
        SEPARATOR,
        "This life",
        *this_life_lines,
        SEPARATOR,
        "All time",
        *all_time_lines,
        SEPARATOR,
        "Versions",
    ]
    versions = [_version_line(life, now) for life in history] or ["・None yet"]
    return _fit(head, versions)


async def refresh_billboard(bot: "WispBot", guild_id: int) -> None:
    """Bring the pinned Billboard in the Studio up to date."""
    text = await render_billboard(bot, guild_id, discord.utils.utcnow())
    await show_in_thread(
        bot,
        guild_id,
        "billboard_thread_id",
        "billboard_message_id",
        text,
        "Billboard",
    )


# ---
# Status card text
# ---


async def status_text(
    bot: "WispBot", guild_id: int, life: Life, now: datetime, happy: int
) -> str:
    """Render the status card for a life that is not over."""
    today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return render_status(
        life,
        now,
        happiness=happy,
        fed_today=await bot.activity_log.people_since(guild_id, today),
    )


# ---
# Naming
# ---


def _bot(interaction: discord.Interaction) -> "WispBot":
    return cast("WispBot", interaction.client)


async def _name_refusal(interaction: discord.Interaction) -> str | None:
    """Why the member may not choose a name right now, or None if they may.

    A member who already has a name cannot change it; staff clear it to let
    them choose again. Banned members cannot name themselves either.
    """
    player = await _bot(interaction).players.get(
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
            await _bot(interaction).players.set_name(
                require_guild(interaction), interaction.user.id, name
            )
            reply = f"♪ Wisp will call you {name} from now on."
        await interaction.response.send_message(
            reply, ephemeral=True, allowed_mentions=_NO_PING
        )

    async def on_error(  # type: ignore[override]
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        """Report a failure to staff and tell the member."""
        await _bot(interaction).report_error(
            interaction.guild, "the naming form", error
        )
        with contextlib.suppress(discord.DiscordException):
            await interaction.response.send_message(USER_ERROR, ephemeral=True)


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
        """Turn away anyone but its member, and a member who may not name themselves."""
        if interaction.user.id != self.user_id:
            reply = "♪ That button is for someone else."
        elif (refusal := await _name_refusal(interaction)) is not None:
            reply = refusal
        else:
            return True
        await interaction.response.send_message(reply, ephemeral=True)
        return False

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open the name form."""
        await interaction.response.send_modal(NameModal())


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
    a mention when the caller has none).
    """
    if (await bot.players.get(guild_id, user_id)).met_at is not None:
        return
    async with bot.guild_lock(guild_id):
        life = await bot.lives.current(guild_id)
        player = await bot.players.get(guild_id, user_id)
        days = await bot.activity_log.distinct_days(guild_id, user_id)
        if life is None or not should_meet(days, met=player.met_at is not None):
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
        happy = happiness(
            await bot.activity_log.people_since(guild_id, now - HAPPINESS_WINDOW)
        )
        text = await status_text(bot, guild_id, life, now, happy)
    await interaction.followup.send(text, ephemeral=True, allowed_mentions=_NO_PING)


@wisp.command(name="board", description="See the leaderboard and Wisp's versions.")
async def wisp_board(interaction: discord.Interaction["WispBot"]) -> None:
    """Show the Billboard to the member who asked, and join them in on first use."""
    bot = interaction.client
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    now = discord.utils.utcnow()
    texts = []
    if (await bot.players.get(guild_id, interaction.user.id)).activated_at is None:
        await bot.players.activate(guild_id, interaction.user.id, now)
        texts.append("♪ You're on Wisp's radar now.")
    texts.append(await render_billboard(bot, guild_id, now))
    for text in texts:
        await interaction.followup.send(text, ephemeral=True, allowed_mentions=_NO_PING)


async def setup(bot: "WispBot") -> None:
    """Register the name button so it still works after a restart."""
    bot.add_dynamic_items(NameButton)
