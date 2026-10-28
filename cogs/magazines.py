"""Magazines: the Rockstar covers the Vault sells and the Snack Pack keeps.

Buying one happens in the Vault (see `cogs.snacks`). The covers are on the
shelf only while the living Wisp is a Rockstar; a member keeps every cover
they bought, from every life.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord

from cogs.assets import ASSETS_DIR
from db.magazines import OwnedMagazine
from wisp.life import Life, Phase
from wisp.rules import MAGAZINE_BY_KEY, MAGAZINE_COST, MAGAZINES, Magazine, Stage
from wisp.text import heading, item, with_emoji
from wisp.voice import MINI_COIN_EMOJI

if TYPE_CHECKING:
    from app import WispBot

MAGAZINE_ART: Final = ASSETS_DIR / "mags"
OWNED: Final = "owned"


def on_the_shelf(life: Life) -> bool:
    """Whether the magazines are sold in this life now: only while he is a Rockstar."""
    return life.phase is Phase.ALIVE and life.stage is Stage.ROCKSTAR


def cover_art(magazine: Magazine) -> Path:
    """Where the cover's picture for posting is on disk."""
    return MAGAZINE_ART / f"{magazine.key}_cover.jpg"


async def magazines_owned(
    bot: "WispBot", guild_id: int, user_id: int
) -> set[str] | None:
    """The magazines the member has for the current life, or None when none are sold.

    None means the section and its select are left out of the Vault.
    """
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or not on_the_shelf(life):
        return None
    return await bot.magazines.owned(guild_id, user_id, life.id)


# ---
# The Vault
# ---


def magazine_section(bot: "WispBot", owned: set[str]) -> list[str]:
    """The Vault's Magazines lines: each cover's name and price, then any owned."""
    price = with_emoji(bot.emoji(MINI_COIN_EMOJI), f"{MAGAZINE_COST} WC")
    lines = [heading("Magazines")]
    for magazine in MAGAZINES:
        line = item(f"{magazine.name}・{price}")
        lines.append(f"{line}・{OWNED}" if magazine.key in owned else line)
    return lines


def magazine_options(owned: set[str]) -> list[discord.SelectOption]:
    """The covers the member does not have this life, as the Vault's select options."""
    return [
        discord.SelectOption(
            label=magazine.name, value=magazine.key, description=f"{MAGAZINE_COST} WC"
        )
        for magazine in MAGAZINES
        if magazine.key not in owned
    ]


# ---
# The Snack Pack
# ---


def magazine_pack_lines(owned: list[OwnedMagazine]) -> list[str]:
    """One line per magazine the member ever bought, in the order given.

    Each reads "Wisp v3's VIIBRATIONS cover". A cover no longer sold reads as
    its stored key's words.
    """
    return [
        item(f"Wisp v{bought.version}'s {_name(bought.magazine)}") for bought in owned
    ]


def _name(key: str) -> str:
    magazine = MAGAZINE_BY_KEY.get(key)
    return magazine.name if magazine else key.replace("_", " ").title()
