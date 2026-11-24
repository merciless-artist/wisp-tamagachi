"""Staff's /wispadmin moody: add, list and remove the moody phrases.

Each server keeps its own phrases, by stage from Child on. The answers are
private. The game itself is in `cogs.moody`.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

import discord
from discord import app_commands

from cogs.groups import moody, require_guild
from cogs.staff import refused
from wisp.moody import Phrase, credit, problem, songs_short
from wisp.rules import MOODY_STAGES, Stage
from wisp.text import MESSAGE_LIMIT, count, text_length

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_STAGE_CHOICES: Final = [
    app_commands.Choice(name=stage.label, value=stage.value) for stage in MOODY_STAGES
]

# ---
# Staff commands
# ---


def _listed(phrase: Phrase) -> str:
    return f"#{phrase.id} ・ {phrase.text} ・ {credit(phrase)}"


def list_messages(stage: Stage, phrases: Sequence[Phrase]) -> list[str]:
    """The stage's phrases as private messages, each within MESSAGE_LIMIT."""
    if not phrases:
        return [f"♪ There are no moody phrases for {stage.label} yet."]
    lines = [f"♪ Moody phrases for {stage.label}"]
    if short := songs_short(phrases):
        lines.append(f"・Wisp needs {count(short, 'more different song')} to use them.")
    lines.extend(_listed(phrase) for phrase in phrases)
    messages: list[str] = []
    current = ""
    for line in lines:
        joined = f"{current}\n{line}" if current else line
        if current and text_length(joined) > MESSAGE_LIMIT:
            messages.append(current)
            joined = line
        current = joined
    messages.append(current)
    return messages


async def _answer(interaction: discord.Interaction["WispBot"], text: str) -> None:
    await interaction.followup.send(text, ephemeral=True, allowed_mentions=_NO_PING)


@moody.command(name="add", description="Add a song phrase Wisp may grumble.")
@app_commands.describe(
    stage="The stage that says it",
    phrase="The words, as Wisp will say them",
    artist="Who sings the song",
    song="The song's title",
    year="The year the song came out",
)
@app_commands.choices(stage=_STAGE_CHOICES)
async def add_phrase(
    interaction: discord.Interaction["WispBot"],
    stage: app_commands.Choice[str],
    phrase: str,
    artist: str,
    song: str,
    year: int,
) -> None:
    """Save a moody phrase for a stage, answered privately with its id."""
    if await refused(interaction):
        return
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    text, artist, song = phrase.strip(), artist.strip(), song.strip()
    if (why := problem(text, artist, song, year)) is not None:
        await _answer(interaction, why)
        return
    picked = Stage(stage.value)
    phrase_id = await interaction.client.moody.add(
        guild_id,
        picked,
        text,
        artist,
        song,
        year,
        interaction.user.id,
        discord.utils.utcnow(),
    )
    await _answer(interaction, f"♪ Moody phrase #{phrase_id} added for {picked.label}.")


@moody.command(name="list", description="List a stage's song phrases.")
@app_commands.describe(stage="The stage to list")
@app_commands.choices(stage=_STAGE_CHOICES)
async def list_phrases(
    interaction: discord.Interaction["WispBot"], stage: app_commands.Choice[str]
) -> None:
    """List a stage's moody phrases privately, split to fit Discord."""
    if await refused(interaction):
        return
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    picked = Stage(stage.value)
    phrases = await interaction.client.moody.for_stage(guild_id, picked)
    for text in list_messages(picked, phrases):
        await _answer(interaction, text)


@moody.command(name="remove", description="Remove a song phrase by its id.")
@app_commands.describe(id="The phrase's id, from /wispadmin moody list")
async def remove_phrase(interaction: discord.Interaction["WispBot"], id: int) -> None:
    """Delete one of this server's moody phrases, answered privately."""
    if await refused(interaction):
        return
    guild_id = require_guild(interaction)
    await interaction.response.defer(ephemeral=True)
    if await interaction.client.moody.remove(guild_id, id):
        await _answer(interaction, f"♪ Moody phrase #{id} removed.")
    else:
        await _answer(interaction, f"♪ There is no moody phrase #{id} here.")


async def setup(bot: "WispBot") -> None:
    """Nothing to register: the commands join the shared groups on import."""
