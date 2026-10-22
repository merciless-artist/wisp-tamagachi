"""Announcements in Wisp's House, shared by the feeding listener and the life loop."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord

from wisp.life import Event, EventKind, Life, is_over, mood, new_egg
from wisp.lines import FIELDS, Moment

if TYPE_CHECKING:
    from app import WispBot

ASSETS_DIR: Final = Path(__file__).resolve().parent.parent / "ASSETS"
_NO_PING: Final = discord.AllowedMentions.none()
_ENDINGS: Final = frozenset({EventKind.DIED, EventKind.EGG_COLD})
_BABY_STAGE: Final = "baby"

# ---
# Images
# ---


def _image_for(event: Event) -> Path | None:
    """Return the first existing image for an event, or None for text only."""
    stages = ASSETS_DIR / "stages"
    events = ASSETS_DIR / "events"
    candidates: list[Path] = []
    match event.kind:
        case EventKind.STAGE_UP if event.stage is not None:
            candidates = [stages / f"{event.stage.value}.png"]
        case EventKind.HATCHED:
            candidates = [stages / f"{_BABY_STAGE}.png", events / "hatched.png"]
        case EventKind.DIED | EventKind.EGG_COLD:
            candidates = [events / f"{event.kind.value}.png"]
    return next((path for path in candidates if path.is_file()), None)


# ---
# Wisp's House
# ---


class _House:
    """Wisp's House channel, resolved once so a missing one is reported once."""

    def __init__(self, bot: "WispBot", guild_id: int) -> None:
        self._bot = bot
        self._guild_id = guild_id
        self._guild: discord.Guild | None = None
        self._channel: discord.abc.Messageable | None = None

    async def open(self) -> None:
        """Find the House channel, or report to staff that it cannot be found."""
        self._guild = self._bot.get_guild(self._guild_id)
        settings = await self._bot.settings.get(self._guild_id)
        found = (
            self._guild.get_channel_or_thread(settings.house_channel_id)
            if self._guild is not None and settings.house_channel_id is not None
            else None
        )
        if isinstance(found, discord.abc.Messageable):
            self._channel = found
            return
        await self._bot.report_error(
            self._guild,
            "posting to Wisp's House",
            LookupError("the House channel is not set or cannot be seen"),
        )

    async def say(self, text: str, image: Path | None = None) -> None:
        """Post a line, with an image when given; a failure is reported to staff."""
        if self._channel is None:
            return
        extras: dict[str, Any] = {} if image is None else {"file": discord.File(image)}
        try:
            await self._channel.send(text, allowed_mentions=_NO_PING, **extras)
        except discord.DiscordException as error:
            await self._bot.report_error(self._guild, "posting to Wisp's House", error)


# ---
# Events
# ---


def _fields(moment: Moment, version: int, event: Event | None) -> dict[str, str]:
    available = {"version": str(version)}
    if event is not None and event.stage is not None:
        available["stage"] = event.stage.value
    return {name: available[name] for name in FIELDS[moment]}


def _line(
    bot: "WispBot", moment: Moment, life: Life, event: Event | None = None
) -> str:
    return bot.lines.pick(moment, mood(life), **_fields(moment, life.version, event))


async def say_in_house(
    bot: "WispBot", guild_id: int, moment: Moment, life: Life
) -> None:
    """Say one line for a moment in Wisp's House, in the mood of `life`.

    A missing House channel is reported to staff.
    """
    house = _House(bot, guild_id)
    await house.open()
    await house.say(_line(bot, moment, life))


async def _lay_next_egg(bot: "WispBot", guild_id: int, house: _House) -> None:
    """Insert the next egg once the current life is over, then announce it."""
    async with bot.guild_lock(guild_id):
        ended = await bot.lives.current(guild_id)
        if ended is None or not is_over(ended):
            return
        egg = await bot.lives.insert(
            guild_id,
            new_egg(await bot.lives.next_version(guild_id), discord.utils.utcnow()),
        )
    await house.say(_line(bot, Moment.NEW_EGG, egg))


async def post_events(bot: "WispBot", guild_id: int, events: list[Event]) -> None:
    """Announce life events in Wisp's House.

    Each event is spoken in Wisp's voice with the image for it when one exists.
    A death or a cold egg is followed by the next egg being laid and announced,
    unless the current life is not over, which means the ending is stale.
    A missing House channel is reported to staff once; the eggs are still laid.
    """
    if not events:
        return
    life = await bot.lives.current(guild_id)
    if life is None:
        return
    house = _House(bot, guild_id)
    await house.open()
    for event in events:
        if event.kind in _ENDINGS and not is_over(life):
            continue
        moment = Moment(event.kind.value)
        await house.say(_line(bot, moment, life, event), _image_for(event))
        if event.kind in _ENDINGS:
            await _lay_next_egg(bot, guild_id, house)
