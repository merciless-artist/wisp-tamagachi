"""The Wisp FAQ thread: banner pictures, a table of contents and the rules."""

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
    """One section of the FAQ: its pictures in ASSETS/faq, in order, and its title.

    Each picture is a wide banner holding one question, and is posted as a
    message of its own.
    """

    pictures: tuple[str, ...]
    title: str


def _banners(stem: str, count: int) -> tuple[str, ...]:
    """The file names `{stem}_1.png` to `{stem}_{count}.png`."""
    return tuple(f"{stem}_{number}.png" for number in range(1, count + 1))


FAQ_SECTIONS: tuple[FaqSection, ...] = (
    FaqSection(_banners("00_how_wisp_works", 1), "How Wisp Works"),
    FaqSection(_banners("01_basics", 4), "The Basics"),
    FaqSection(_banners("02_feeding", 4), "Feeding Him"),
    FaqSection(_banners("03_vault", 5), "The ViiBR Vault and Your Snack Pack"),
    FaqSection(_banners("04_lunchbox", 3), "Wisp's Lunchbox and Gifts"),
    FaqSection(_banners("05_bond", 3), "Your Bond"),
    FaqSection(_banners("06_growing", 4), "Growing Up"),
    FaqSection(_banners("07_talking", 4), "Talking to Him"),
    FaqSection(_banners("08_games", 2), "Games"),
    FaqSection(_banners("09_ending", 3), "The End of a Life"),
    FaqSection(_banners("10_fair", 2), "Fair Play"),
)

FAQ_PICTURE_COUNT: Final = sum(len(section.pictures) for section in FAQ_SECTIONS)


def table_of_contents(guild_id: int, thread_id: int, message_ids: Sequence[int]) -> str:
    """One heading per section, each a link that jumps to its first picture.

    Args:
        guild_id: The guild the thread is in.
        thread_id: The FAQ thread.
        message_ids: The id of every picture's message, in posting order.

    Raises:
        ValueError: There is not exactly one id per picture.
    """
    if len(message_ids) != FAQ_PICTURE_COUNT:
        raise ValueError(
            f"Expected {FAQ_PICTURE_COUNT} picture messages, got {len(message_ids)}"
        )
    lines: list[str] = []
    position = 0
    for section in FAQ_SECTIONS:
        lines.append(
            f"# [{section.title}]"
            f"(<https://discord.com/channels/{guild_id}/{thread_id}"
            f"/{message_ids[position]}>)"
        )
        position += len(section.pictures)
    return "\n".join(lines)


# ---
# Building the thread
# ---


async def fill_faq(
    bot: "WispBot", guild_id: int, thread: discord.Thread, rules: str
) -> None:
    """Post the FAQ's pictures and rules post, then point the first post at them.

    Every picture is a message of its own, in order. Wisp's own earlier
    pictures, whether one per section or one per question, and rules post, as
    stored, are deleted first; the thread's first post never is. What was
    posted is stored even when posting stops part way, so the next setup or
    !wisp faq clears it.

    Raises:
        FileNotFoundError: A picture is missing; nothing has changed.
        discord.HTTPException: Discord refused a delete, post or edit.
    """
    pictures = [
        ASSETS_DIR / "faq" / name
        for section in FAQ_SECTIONS
        for name in section.pictures
    ]
    if missing := [path.name for path in pictures if not path.is_file()]:
        raise FileNotFoundError(f"Missing FAQ pictures: {', '.join(missing)}")
    await _delete_old(bot, guild_id, thread)
    picture_ids: list[int] = []
    stored: dict[str, Any] = {}
    try:
        for picture in pictures:
            posted = await thread.send(
                file=discord.File(picture), allowed_mentions=_NO_PING
            )
            picture_ids.append(posted.id)
        stored["rules_message_id"] = (
            await thread.send(rules, allowed_mentions=_NO_PING)
        ).id
    finally:
        await bot.settings.update(
            guild_id, faq_message_ids=tuple(picture_ids) or None, **stored
        )
    await thread.get_partial_message(thread.id).edit(
        content=table_of_contents(guild_id, thread.id, picture_ids),
        allowed_mentions=_NO_PING,
    )


async def _delete_old(bot: "WispBot", guild_id: int, thread: discord.Thread) -> None:
    """Delete the stored pictures and rules post that still exist."""
    settings = await bot.settings.get(guild_id)
    old = [*(settings.faq_message_ids or ()), settings.rules_message_id]
    for message_id in old:
        if message_id is None or message_id == thread.id:
            continue
        try:
            await thread.get_partial_message(message_id).delete()
        except discord.NotFound:
            continue
