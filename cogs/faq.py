"""The Wisp FAQ thread: one picture per section, a table of contents and the rules."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.assets import ASSETS_DIR

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()

# ---
# Sections
# ---


@dataclass(frozen=True)
class FaqSection:
    """One section of the FAQ: its picture in ASSETS/faq and its title."""

    picture: str
    title: str


FAQ_SECTIONS: tuple[FaqSection, ...] = (
    FaqSection("00_how_wisp_works.png", "How Wisp Works"),
    FaqSection("01_the_basics.png", "The Basics"),
    FaqSection("02_feeding_him.png", "Feeding Him"),
    FaqSection("03_vault_and_snack_pack.png", "The ViiBR Vault and Your Snack Pack"),
    FaqSection("04_lunchbox_and_gifts.png", "Wisp's Lunchbox and Gifts"),
    FaqSection("05_your_bond.png", "Your Bond"),
    FaqSection("06_growing_up.png", "Growing Up"),
    FaqSection("07_talking_to_him.png", "Talking to Him"),
    FaqSection("08_games.png", "Games"),
    FaqSection("09_end_of_a_life.png", "The End of a Life"),
    FaqSection("10_fair_play.png", "Fair Play"),
)


def table_of_contents(guild_id: int, thread_id: int, message_ids: Sequence[int]) -> str:
    """One heading per section, each a link that jumps to its picture."""
    return "\n".join(
        f"# [{section.title}]"
        f"(<https://discord.com/channels/{guild_id}/{thread_id}/{message_id}>)"
        for section, message_id in zip(FAQ_SECTIONS, message_ids, strict=True)
    )


# ---
# Building the thread
# ---


async def fill_faq(
    bot: "WispBot", guild_id: int, thread: discord.Thread, rules: str
) -> None:
    """Post the FAQ's pictures and rules post, then point the first post at them.

    Wisp's own earlier sections and rules post, as stored, are deleted first;
    the thread's first post never is. What was posted is stored even when
    posting stops part way, so /wispadmin faq can clear it.

    Raises:
        FileNotFoundError: A section picture is missing; nothing has changed.
        discord.HTTPException: Discord refused a delete, post or edit.
    """
    pictures = [ASSETS_DIR / "faq" / section.picture for section in FAQ_SECTIONS]
    if missing := [path.name for path in pictures if not path.is_file()]:
        raise FileNotFoundError(f"Missing FAQ pictures: {', '.join(missing)}")
    await _delete_old(bot, guild_id, thread)
    section_ids: list[int] = []
    stored: dict[str, Any] = {}
    try:
        for picture in pictures:
            posted = await thread.send(
                file=discord.File(picture), allowed_mentions=_NO_PING
            )
            section_ids.append(posted.id)
        stored["rules_message_id"] = (
            await thread.send(rules, allowed_mentions=_NO_PING)
        ).id
    finally:
        await bot.settings.update(
            guild_id, faq_message_ids=tuple(section_ids) or None, **stored
        )
    await thread.get_partial_message(thread.id).edit(
        content=table_of_contents(guild_id, thread.id, section_ids),
        allowed_mentions=_NO_PING,
    )


async def _delete_old(bot: "WispBot", guild_id: int, thread: discord.Thread) -> None:
    """Delete the stored sections and rules post that still exist."""
    settings = await bot.settings.get(guild_id)
    old = [*(settings.faq_message_ids or ()), settings.rules_message_id]
    for message_id in old:
        if message_id is None or message_id == thread.id:
            continue
        try:
            await thread.get_partial_message(message_id).delete()
        except discord.NotFound:
            continue
