"""The ViiBR Vault card: the leaderboard, Wisp's versions and /wisp board."""

from datetime import datetime
from typing import TYPE_CHECKING, Final

import discord

from cogs.announce import show_in_thread
from cogs.groups import require_guild, wisp
from cogs.players import say_privately
from cogs.snacks import vault_view
from wisp.bond import tier_for
from wisp.life import Life, Phase, age_days
from wisp.rules import LEADERBOARD_SIZE, RHYME_LEADERBOARD_SIZE
from wisp.text import MESSAGE_LIMIT, SEPARATOR, count

if TYPE_CHECKING:
    from app import WispBot

_INTRO: Final = (
    "Snacks and the leaderboard. Shop or open your Snack Pack with the buttons below."
)

# ---
# Leaderboard
# ---


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


def _fit(head: list[str], history: list[str]) -> str:
    """Join the head and as many whole history lines as fit in one message."""
    lines = head
    for line in history:
        if len("\n".join([*lines, line])) > MESSAGE_LIMIT:
            break
        lines = [*lines, line]
    return "\n".join(lines)


async def render_leaderboard(bot: "WispBot", guild_id: int, now: datetime) -> str:
    """Build the Vault card: two top tens, the top rhymers, then every version.

    The history is trimmed from the oldest end so the text fits one message.
    """
    history = await bot.lives.history(guild_id)
    current_id = history[0].id if history else None
    this_life = (
        await bot.activity_log.top_this_life(guild_id, current_id, LEADERBOARD_SIZE)
        if current_id is not None
        else []
    )
    all_time = await bot.players.top_lifetime(guild_id, LEADERBOARD_SIZE)
    this_life_lines = [
        f"・{place}. <@{user_id}> ・ {count(points, 'point')}"
        for place, (user_id, points) in enumerate(this_life, start=1)
    ] or ["・Nobody has fed him yet"]
    all_time_lines = [
        f"・{place}. <@{player.user_id}> ・ {count(player.lifetime_points, 'point')}"
        f" ・ {tier_for(player.bond)}"
        for place, player in enumerate(all_time, start=1)
    ] or ["・Nobody has points yet"]
    rhymers = await bot.players.top_rhyme(guild_id, RHYME_LEADERBOARD_SIZE)
    rhyme_lines = [
        f"・{place}. <@{player.user_id}> ・ {count(player.best_rhyme_score, 'point')}"
        for place, player in enumerate(rhymers, start=1)
    ] or ["・Nobody has dueled him yet"]
    head = [
        "♪ The ViiBR Vault",
        _INTRO,
        SEPARATOR,
        "This life",
        *this_life_lines,
        SEPARATOR,
        "All time",
        *all_time_lines,
        SEPARATOR,
        "Rhyme Duel",
        *rhyme_lines,
        SEPARATOR,
        "Versions",
    ]
    versions = [version_line(life, now) for life in history] or ["・None yet"]
    return _fit(head, versions)


async def refresh_vault(bot: "WispBot", guild_id: int) -> None:
    """Bring the pinned Vault card in the Studio up to date, buttons included."""
    text = await render_leaderboard(bot, guild_id, discord.utils.utcnow())
    await show_in_thread(
        bot,
        guild_id,
        "vault_thread_id",
        "vault_message_id",
        text,
        "ViiBR Vault card",
        vault_view(),
    )


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
    await say_privately(
        interaction,
        await render_leaderboard(bot, guild_id, now),
        view=vault_view(),
    )


async def setup(bot: "WispBot") -> None:
    """Load the Vault extension; its command joins the shared group on import."""
