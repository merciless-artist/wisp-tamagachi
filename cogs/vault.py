"""The Leaderboard post: the top lists, Wisp's versions and /wisp board."""

import functools
from datetime import datetime
from typing import TYPE_CHECKING, Final

import discord

from cogs.groups import require_guild, wisp
from cogs.headers import FOOTER, HeadedCard, repost_headed_in_thread, send_headed
from cogs.players import say_privately
from cogs.snacks import vault_view
from wisp.bond import tier_for
from wisp.life import Life, Phase, age_days
from wisp.rules import LEADERBOARD_SIZE, RHYME_LEADERBOARD_SIZE
from wisp.text import (
    BLANK,
    box_bottom,
    box_top,
    count,
    fit,
    heading,
    item,
    sections,
    sub,
    wrap,
    wrapped,
)

if TYPE_CHECKING:
    from app import WispBot

_HEADER: Final = "leaderboard_title.png"
_CARD: Final = HeadedCard(
    header=_HEADER,
    footer=FOOTER,
    title_attr="vault_title_message_id",
    card_attr="vault_message_id",
    label="Leaderboard card",
    post="Leaderboard",
)
_NO_PING: Final = discord.AllowedMentions.none()

# ---
# Leaderboard
# ---


def _intro(status_thread_id: int | None) -> tuple[str, ...]:
    """The card's opening lines, saying where to shop the Vault."""
    where = "the Status post" if status_thread_id is None else f"<#{status_thread_id}>"
    return (
        sub("The leaderboard."),
        BLANK,
        item(f"Shop the Vault with the button on {where}."),
        BLANK,
    )


def version_line(life: Life, now: datetime) -> str:
    """Describe one of Wisp's versions in a single line, starting `v{n} ・ `."""
    prefix = f"v{life.version} ・ "
    match life.phase:
        case Phase.EGG:
            return prefix + (
                "still an egg ・ from coal" if life.from_coal else "still an egg"
            )
        case Phase.HATCHING:
            return prefix + "hatching now"
        case Phase.ALIVE:
            days = count(age_days(life, now), "day")
            return prefix + f"going strong ・ {days} ・ {life.stage.label}"
        case Phase.COLD:
            return prefix + "never hatched"
        case Phase.PASSED | Phase.DEAD:
            days = count(age_days(life, life.ended_at or now), "day")
            facts = [
                (
                    f"lived a full life ・ {days}"
                    if life.phase is Phase.PASSED
                    else f"went out after {days}"
                ),
                f"peak {life.peak_stage.label}",
            ]
            if life.hatched_by is not None:
                facts.append(f"hatched by <@{life.hatched_by}>")
            return prefix + " ・ ".join(facts)


async def render_leaderboard(bot: "WispBot", guild_id: int, now: datetime) -> str:
    """Build the Leaderboard card: two top tens, top rhymers, then every version.

    The history is trimmed from the oldest end so the text fits one message;
    the box always closes. Each list ends with a blank line, as in Myra's
    draft, and every line is wrapped to fit the box.
    """
    settings = await bot.settings.get(guild_id)
    history = await bot.lives.history(guild_id)
    current_id = history[0].id if history else None
    this_life = (
        await bot.activity_log.top_this_life(guild_id, current_id, LEADERBOARD_SIZE)
        if current_id is not None
        else []
    )
    all_time = await bot.players.top_lifetime(guild_id, LEADERBOARD_SIZE)
    this_life_lines = [
        item(f"{place}. <@{user_id}> ・ {count(points, 'point')}")
        for place, (user_id, points) in enumerate(this_life, start=1)
    ] or [item("Nobody has fed him yet")]
    all_time_lines = [
        item(
            f"{place}. <@{player.user_id}> ・ {count(player.lifetime_points, 'point')}"
            f" ・ {tier_for(player.bond)}"
        )
        for place, player in enumerate(all_time, start=1)
    ] or [item("Nobody has points yet")]
    rhymers = await bot.players.top_rhyme(guild_id, RHYME_LEADERBOARD_SIZE)
    rhyme_lines = [
        item(
            f"{place}. <@{player.user_id}> ・ {count(player.best_rhyme_score, 'point')}"
        )
        for place, player in enumerate(rhymers, start=1)
    ] or [item("Nobody has dueled him yet")]
    head = [
        box_top(),
        *wrapped(
            sections(
                _intro(settings.status_thread_id),
                [heading("This life"), *this_life_lines, BLANK],
                [heading("All time"), *all_time_lines, BLANK],
                [heading("Rhyme Duel"), *rhyme_lines, BLANK],
                [heading("Versions")],
            )
        ),
    ]
    versions = [wrap(item(version_line(life, now))) for life in history] or [
        item("None yet")
    ]
    return fit(head, versions, [BLANK, box_bottom()])


async def refresh_vault(bot: "WispBot", guild_id: int) -> None:
    """Repost the Leaderboard card at the bottom of its thread if its text changed."""
    text = await render_leaderboard(bot, guild_id, discord.utils.utcnow())
    await repost_headed_in_thread(bot, guild_id, "vault_thread_id", text, _CARD)


# ---
# Commands
# ---


@wisp.command(name="board", description="See the leaderboard and Wisp's versions.")
async def wisp_board(interaction: discord.Interaction["WispBot"]) -> None:
    """Show the Vault card to the member who asked, and join them in on first use."""
    bot = interaction.client
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    now = discord.utils.utcnow()
    if (await bot.players.get(guild_id, interaction.user.id)).activated_at is None:
        await bot.players.activate(guild_id, interaction.user.id, now)
        await say_privately(interaction, "♪ You're on Wisp's radar now.")
    await send_headed(
        functools.partial(interaction.followup.send, ephemeral=True),
        _HEADER,
        await render_leaderboard(bot, guild_id, now),
        view=vault_view(),
        allowed_mentions=_NO_PING,
    )


async def setup(bot: "WispBot") -> None:
    """Load the Vault extension; its command joins the shared group on import."""
